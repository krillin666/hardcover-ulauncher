import requests
import logging

logger = logging.getLogger(__name__)

class HardcoverAPI:
    # Public Hardcover Search (Typesense) - Sourced from Web/Go logic
    SEARCH_URL = "https://search.hardcover.app/collections/books/documents/search"
    SEARCH_API_KEY = "7JRcb63AvYIo2WJvE3IzH4f8j1z9fHcC"
    
    # Main GraphQL Endpoint
    GRAPHQL_URL = "https://api.hardcover.app/v1/graphql"

    def __init__(self, api_token):
        self.api_token = api_token.replace("Bearer ", "").strip()
        self.headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            # Critical for bypassing WAF/Cloudflare
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }

    def search_books(self, query):
        """
        Equivalent to the Search logic in the Go implementation.
        Uses Typesense to bypass the GraphQL '_ilike' restriction.
        """
        if not query:
            return []

        # These headers mimic the web browser to prevent "Read Timeout"
        search_headers = {
            "X-TYPESENSE-API-KEY": self.SEARCH_API_KEY,
            "Origin": "https://hardcover.app",
            "Referer": "https://hardcover.app/",
        }
        
        params = {
            "q": query,
            "query_by": "title,author_names",
            "sort_by": "users_read_count:desc",
            "per_page": 8
        }

        try:
            r = requests.get(self.SEARCH_URL, params=params, headers=search_headers, timeout=5)
            r.raise_for_status()
            data = r.json()
            
            results = []
            for hit in data.get('hits', []):
                doc = hit.get('document', {})
                results.append({
                    "id": doc.get('id'), # internal ID
                    "title": doc.get('title'),
                    "slug": doc.get('slug'),
                    "author": doc.get('author_names', ["Unknown"])[0] if doc.get('author_names') else "Unknown",
                    "image": doc.get('image_url') # Sometimes available
                })
            return results
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def get_user_lists(self):
        """Fetches the user's custom lists."""
        query = """
        query GetMyLists {
            me {
                lists(order_by: {updated_at: desc}) {
                    id
                    name
                    books_count
                    slug
                }
            }
        }
        """
        return self._run_query(query).get('me', [{}])[0].get('lists', [])

    def get_user_books_by_status(self, status_id):
        """
        Fetches books from the user's library based on status.
        Status IDs: 1=Want to Read, 2=Currently Reading, 3=Read
        """
        query = """
        query GetUserBooks($status: Int!) {
            me {
                user_books(where: {status_id: {_eq: $status}}, limit: 10, order_by: {updated_at: desc}) {
                    book {
                        title
                        slug
                        contributions {
                            author { name }
                        }
                    }
                }
            }
        }
        """
        variables = {"status": status_id}
        data = self._run_query(query, variables)
        
        books = []
        # Safe navigation of the response
        me = data.get('me', [])
        if not me: return []
        
        user_books = me[0].get('user_books', [])
        for entry in user_books:
            b = entry.get('book', {})
            author = "Unknown"
            if b.get('contributions'):
                author = b['contributions'][0]['author']['name']
            
            books.append({
                "title": b.get('title'),
                "slug": b.get('slug'),
                "author": author
            })
        return books

    def add_book_to_library(self, book_slug, status_id):
        """
        Adds a book to the user's library.
        We first need the Book ID (INT), not just the slug.
        """
        # 1. Resolve Slug to ID
        id_query = """
        query GetBookID($slug: String!) {
            books(where: {slug: {_eq: $slug}}) { id }
        }
        """
        id_data = self._run_query(id_query, {"slug": book_slug})
        books = id_data.get('books', [])
        if not books:
            return False
        
        book_id = books[0]['id']

        # 2. Perform Mutation
        mutation = """
        mutation AddBook($book_id: Int!, $status_id: Int!) {
            insert_user_book_one(object: {book_id: $book_id, status_id: $status_id}) {
                id
            }
        }
        """
        variables = {"book_id": book_id, "status_id": status_id}
        try:
            self._run_query(mutation, variables)
            return True
        except Exception as e:
            logger.error(f"Mutation failed: {e}")
            return False

    def _run_query(self, query, variables=None):
        payload = {'query': query, 'variables': variables}
        r = requests.post(self.GRAPHQL_URL, json=payload, headers=self.headers, timeout=10)
        r.raise_for_status()
        json_resp = r.json()
        if 'errors' in json_resp:
            raise Exception(json_resp['errors'][0]['message'])
        return json_resp.get('data', {})
