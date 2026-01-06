import json
import logging
import requests
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction
from ulauncher.api.shared.action.HideWindowAction import HideWindowAction
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction

logger = logging.getLogger(__name__)

HARDCOVER_API_URL = "https://api.hardcover.app/v1/graphql"
HARDCOVER_BASE_URL = "https://hardcover.app"


class HardcoverExtension(Extension):
    def __init__(self):
        super(HardcoverExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())


class HardcoverAPI:
    """Wrapper for Hardcover GraphQL API"""

    def __init__(self, api_token):
        # Strip whitespace and quotes from token
        self.api_token = api_token.strip().strip('"').strip("'") if api_token else ""
        
        self.headers = {
            "Content-Type": "application/json",
        }
        
        if self.api_token:
            self.headers["Authorization"] = f"Bearer {self.api_token}"
            logger.info(f"Token length: {len(self.api_token)}")

    def get_user_info(self):
        """Get current user information"""
        query = """
        query {
          me {
            id
            username
            name
          }
        }
        """
        
        payload = {"query": query}
        
        try:
            response = requests.post(
                HARDCOVER_API_URL,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code != 200:
                return None
            
            data = response.json()
            if "errors" in data:
                return None
            
            return data.get("data", {}).get("me", {})
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return None

    def check_book_in_library(self, user_id, book_id):
        """Check if a book is already in user's library"""
        query = """
        query CheckBook($user_id: Int!, $book_id: Int!) {
          user_books(
            where: {
              user_id: {_eq: $user_id},
              book_id: {_eq: $book_id}
            }
            limit: 1
          ) {
            id
            status_id
          }
        }
        """
        
        payload = {
            "query": query,
            "variables": {
                "user_id": user_id,
                "book_id": book_id
            }
        }
        
        logger.info(f"Checking if book {book_id} is in library for user {user_id}")
        
        try:
            response = requests.post(
                HARDCOVER_API_URL,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            
            logger.debug(f"Check library response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"HTTP Error checking library: {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            
            logger.debug(f"Check library response: {json.dumps(data, indent=2)[:500]}")
            
            if "errors" in data:
                logger.error(f"GraphQL errors checking library: {data['errors']}")
                return None
            
            user_books = data.get("data", {}).get("user_books", [])
            logger.info(f"Found {len(user_books)} matching user_books entries")
            
            return user_books[0] if user_books else None
        except Exception as e:
            logger.error(f"Error checking book in library: {e}", exc_info=True)
            return None



    def add_book_to_library(self, book_id, status_id=1, rating=None):
        """
        Add or update a book in user's library
        status_id: 1=Want to Read, 2=Currently Reading, 3=Read, 4=Paused, 5=DNF, 6=Ignored
        rating: Optional float (0.5 to 5.0)
        """
        # Use the correct mutation format from Hardcover developers
        mutation = """
        mutation ChangeBookStatus($bookId: Int!, $status: Int, $rating: Float) {
          insert_user_book(object: {book_id: $bookId, status_id: $status, rating: $rating}) {
            id
            book_id
            status_id
            rating
          }
        }
        """
        
        variables = {
            "bookId": book_id,
            "status": status_id
        }
        
        if rating is not None:
            variables["rating"] = rating
        
        payload = {
            "query": mutation,
            "variables": variables
        }
        
        logger.info(f"Adding book {book_id} with status {status_id}")
        logger.debug(f"Mutation payload: {json.dumps(payload, indent=2)}")
        
        try:
            response = requests.post(
                HARDCOVER_API_URL,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            
            logger.info(f"Add book response status: {response.status_code}")
            logger.debug(f"Response: {response.text}")
            
            if response.status_code != 200:
                return {"success": False, "error": f"HTTP {response.status_code}"}
            
            data = response.json()
            
            if "errors" in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                return {"success": False, "error": str(data['errors'])}
            
            result = data.get("data", {}).get("insert_user_book", {})
            if result:
                logger.info(f"Successfully added book {book_id} to library")
                return {"success": True, "data": result}
            else:
                return {"success": False, "error": "No data returned"}
                
        except Exception as e:
            logger.error(f"Error adding book: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def search(self, query, query_type="Book", per_page=10, page=1):
        """
        Search using Hardcover's GraphQL API
        query_type: Author, Book, Character, List, Prompt, Publisher, Series, User
        """
        graphql_query = """
        query Search($query: String!, $query_type: String!, $per_page: Int!, $page: Int!) {
          search(
            query: $query,
            query_type: $query_type,
            per_page: $per_page,
            page: $page
          ) {
            results
          }
        }
        """

        payload = {
            "query": graphql_query,
            "variables": {
                "query": query,
                "query_type": query_type,
                "per_page": per_page,
                "page": page
            }
        }

        logger.info(f"Searching for '{query}' (type: {query_type})")

        try:
            response = requests.post(
                HARDCOVER_API_URL,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"HTTP Error {response.status_code}: {response.text}")
                return []
            
            data = response.json()
            
            # Check for GraphQL errors
            if "errors" in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                return []
            
            # Get the Typesense results structure
            search_data = data.get("data", {}).get("search", {})
            results_obj = search_data.get("results", {})
            
            # The actual results are in results.hits[].document
            hits = results_obj.get("hits", [])
            
            logger.info(f"Found {results_obj.get('found', 0)} total results")
            logger.info(f"Got {len(hits)} hits in this page")
            
            # Extract documents from hits
            parsed_results = []
            for i, hit in enumerate(hits):
                document = hit.get("document", {})
                if document:
                    parsed_results.append(document)
                else:
                    logger.warning(f"Hit {i} has no document")
            
            logger.info(f"Extracted {len(parsed_results)} documents")
            
            return parsed_results
            
        except Exception as e:
            logger.error(f"Error searching: {e}", exc_info=True)
            return []


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument() or ""
        api_token = extension.preferences.get("api_token", "")
        user_id = extension.preferences.get("user_id", "")
        
        # Check if API token is set
        if not api_token or not api_token.strip():
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='API Token Required',
                    description='Please set your Hardcover API token in extension preferences',
                    on_enter=HideWindowAction()
                )
            ])
        
        try:
            limit = int(extension.preferences.get("results_limit", "10"))
        except ValueError:
            limit = 10

        # Special command to get user info
        if query.lower() in ["me", "whoami"]:
            api = HardcoverAPI(api_token)
            user_info = api.get_user_info()
            
            if user_info:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name=f"Hello, {user_info.get('name', user_info.get('username', 'User'))}!",
                        description=f"User ID: {user_info.get('id')} | Username: @{user_info.get('username')} | Copy your User ID and add it to preferences",
                        on_enter=CopyToClipboardAction(str(user_info.get('id')))
                    )
                ])
            else:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='Error getting user info',
                        description='Check your API token',
                        on_enter=HideWindowAction()
                    )
                ])

        if not query:
            items = [
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Search Hardcover',
                    description='Type to search for books, authors, series, or lists',
                    on_enter=HideWindowAction()
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Get User Info',
                    description='hc me - Get your user ID',
                    on_enter=HideWindowAction()
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Books (default)',
                    description='hc <book name>',
                    on_enter=HideWindowAction()
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Authors',
                    description='hc author <name>',
                    on_enter=HideWindowAction()
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Series',
                    description='hc series <name>',
                    on_enter=HideWindowAction()
                )
            ]
            
            if user_id:
                items.insert(1, ExtensionResultItem(
                    icon='images/icon.png',
                    name='Add to Library',
                    description='Alt+Enter on any book to add to Want to Read',
                    on_enter=HideWindowAction()
                ))
            
            return RenderResultListAction(items)

        # Parse command
        parts = query.split(None, 1)
        command = parts[0].lower()
        search_query = parts[1] if len(parts) > 1 else query

        api = HardcoverAPI(api_token)
        items = []

        # Determine search type
        if command in ["author", "authors"] and len(parts) > 1:
            query_type = "Author"
        elif command in ["series"] and len(parts) > 1:
            query_type = "Series"
        elif command in ["list", "lists"] and len(parts) > 1:
            query_type = "List"
        else:
            query_type = "Book"
            # If no command specified, search the full query
            if command not in ["author", "authors", "series", "list", "lists"]:
                search_query = query

        logger.info(f"Query type: {query_type}, Search query: '{search_query}'")

        # Perform search
        results = api.search(search_query, query_type=query_type, per_page=limit)
        
        # Create items
        for result in results:
            if query_type == "Book":
                items.append(create_book_item(result, user_id, api))
            elif query_type == "Author":
                items.append(create_author_item(result))
            elif query_type == "Series":
                items.append(create_series_item(result))
            elif query_type == "List":
                items.append(create_list_item(result))

        if not items:
            items.append(ExtensionResultItem(
                icon='images/icon.png',
                name='No results found',
                description=f'No results for "{search_query}"',
                on_enter=HideWindowAction()
            ))

        return RenderResultListAction(items)


class ItemEnterEventListener(EventListener):
    def on_event(self, event, extension):
        data = event.get_data()
        action = data.get("action")
        
        if action == "add_to_library":
            api_token = extension.preferences.get("api_token", "")
            api = HardcoverAPI(api_token)
            
            book_id = data.get("book_id")
            book_title = data.get("book_title")
            user_id = data.get("user_id")
            
            # Convert book_id to int
            try:
                book_id = int(book_id)
                user_id = int(user_id)
            except (ValueError, TypeError) as e:
                logger.error(f"Invalid book_id or user_id: {e}")
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='Error',
                        description='Invalid book or user ID',
                        on_enter=HideWindowAction()
                    )
                ])
            
            # Check if book is already in library
            existing = api.check_book_in_library(user_id, book_id)
            
            if existing:
                status_names = {1: "Want to Read", 2: "Currently Reading", 3: "Read", 
                               4: "Paused", 5: "Did Not Finish", 6: "Ignored"}
                status_name = status_names.get(existing.get("status_id"), "Unknown")
                
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='Book Already in Library',
                        description=f'"{book_title}" is already marked as "{status_name}"',
                        on_enter=HideWindowAction()
                    )
                ])
            
            # Add book to library
            result = api.add_book_to_library(book_id, status_id=1)
            
            if result.get("success"):
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='✓ Added to Want to Read',
                        description=f'"{book_title}" has been added to your library',
                        on_enter=HideWindowAction()
                    )
                ])
            else:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='Error Adding Book',
                        description=f'Error: {result.get("error", "Unknown error")}',
                        on_enter=HideWindowAction()
                    )
                ])
        
        return HideWindowAction()


def create_book_item(book, user_id, api):
    """Create item from book data"""
    title = book.get("title", "Unknown Title")
    slug = book.get("slug", "")
    book_id = book.get("id")
    
    # Convert book_id to int if it's a string
    if book_id is not None:
        try:
            book_id = int(book_id)
        except (ValueError, TypeError):
            logger.warning(f"Could not convert book_id to int: {book_id}")
            book_id = None
    
    author_names = book.get("author_names", [])
    authors_str = ", ".join(author_names) if isinstance(author_names, list) else ""
    
    release_year = book.get("release_year", "")
    rating = book.get("rating", "")
    users_count = book.get("users_count", 0)
    
    desc_parts = []
    if authors_str:
        desc_parts.append(f"By {authors_str}")
    if release_year:
        desc_parts.append(str(release_year))
    if rating:
        desc_parts.append(f"⭐ {rating:.1f}")
    if users_count:
        desc_parts.append(f"👥 {users_count}")
    
    description = " | ".join(desc_parts) if desc_parts else "Book"
    
    # Check if user has this book in library
    in_library = False
    if user_id and api and book_id:
        try:
            logger.debug(f"Checking library status for book '{title}' (ID: {book_id})")
            existing = api.check_book_in_library(int(user_id), book_id)
            in_library = existing is not None
            logger.debug(f"Book in library: {in_library}")
        except Exception as e:
            logger.error(f"Error checking library for book {book_id}: {e}", exc_info=True)
    else:
        if not user_id:
            logger.debug("User ID not set, skipping library check")
        if not book_id:
            logger.warning(f"Book '{title}' has no ID!")
    
    if in_library:
        description = "📚 In Library | " + description

    # Prepare on_alt_enter action if not in library
    on_alt_enter = None
    if user_id and not in_library and book_id:
        on_alt_enter = ExtensionCustomAction(
            {
                "action": "add_to_library",
                "book_id": book_id,  # Already converted to int
                "book_title": title,
                "user_id": user_id
            },
            keep_app_open=True
        )
        # Add hint to description
        description += " | Alt+Enter to add"

    item = ExtensionResultItem(
        icon='images/icon.png',
        name=title,
        description=description,
        on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/books/{slug}"),
        on_alt_enter=on_alt_enter
    )
    
    return item

def create_author_item(author):
    """Create item from author data"""
    name = author.get("name", "Unknown Author")
    slug = author.get("slug", "")
    books_count = author.get("books_count", 0)
    
    # Get some book titles
    books = author.get("books", [])
    if isinstance(books, list) and books:
        books_preview = ", ".join(books[:3])
        if len(books) > 3:
            books_preview += "..."
        description = f"📚 {books_count} books | {books_preview}"
    else:
        description = f"📚 {books_count} books"

    return ExtensionResultItem(
        icon='images/icon.png',
        name=name,
        description=description,
        on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/authors/{slug}")
    )


def create_series_item(series):
    """Create item from series data"""
    name = series.get("name", "Unknown Series")
    slug = series.get("slug", "")
    author_name = series.get("author_name", "")
    books_count = series.get("books_count", 0)
    
    desc_parts = []
    if author_name:
        desc_parts.append(f"By {author_name}")
    if books_count:
        desc_parts.append(f"{books_count} books")
    
    description = " | ".join(desc_parts) if desc_parts else "Series"

    return ExtensionResultItem(
        icon='images/icon.png',
        name=name,
        description=description,
        on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/series/{slug}")
    )


def create_list_item(list_data):
    """Create item from list data"""
    name = list_data.get("name", "Untitled List")
    slug = list_data.get("slug", "")
    books_count = list_data.get("books_count", 0)
    
    user = list_data.get("user", {})
    username = user.get("username", "Unknown") if isinstance(user, dict) else "Unknown"
    
    description = f"By @{username} | {books_count} books" if books_count else f"By @{username}"

    return ExtensionResultItem(
        icon='images/icon.png',
        name=name,
        description=description,
        on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/lists/{slug}")
    )


if __name__ == '__main__':
    HardcoverExtension().run()
