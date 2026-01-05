import json
import logging
import requests
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction
from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction
from ulauncher.api.shared.action.HideWindowAction import HideWindowAction

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
        self.api_token = api_token.strip() if api_token else ""
        self.headers = {
            "Content-Type": "application/json",
        }
        # Note: Search API doesn't require authentication
        # Auth is only needed for mutations (adding books, updating status, etc.)

    def search(self, query, query_type="Book", per_page=10, page=1):
        """
        Generic search function using Hardcover's search API
        
        query_type can be: Author, Book, Character, List, Prompt, Publisher, Series, User
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
            query
            query_type
            page
            per_page
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

        logger.info(f"Searching for '{query}' (type: {query_type}, limit: {per_page})")
        logger.debug(f"Request payload: {json.dumps(payload, indent=2)}")

        try:
            response = requests.post(
                HARDCOVER_API_URL,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            
            logger.info(f"Response status: {response.status_code}")
            logger.debug(f"Response headers: {response.headers}")
            
            response.raise_for_status()
            data = response.json()
            
            logger.debug(f"Full response data: {json.dumps(data, indent=2)}")
            
            # Check for errors in GraphQL response
            if "errors" in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                return []
            
            # Parse results which come as JSON strings
            search_data = data.get("data", {}).get("search", {})
            logger.info(f"Search data keys: {search_data.keys() if search_data else 'None'}")
            
            results_json = search_data.get("results", [])
            logger.info(f"Number of raw results: {len(results_json)}")
            
            if results_json:
                logger.debug(f"First raw result: {results_json[0][:200] if results_json[0] else 'Empty'}")
            
            # Parse each result from JSON string
            parsed_results = []
            for i, result_str in enumerate(results_json):
                try:
                    parsed = json.loads(result_str)
                    parsed_results.append(parsed)
                    if i == 0:
                        logger.debug(f"First parsed result: {json.dumps(parsed, indent=2)[:500]}")
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing result {i}: {e}")
                    logger.error(f"Problematic result string: {result_str[:200]}")
                    continue
            
            logger.info(f"Successfully parsed {len(parsed_results)} results")
            return parsed_results
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {e.response.status_code}: {e.response.text}")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error searching: {e}", exc_info=True)
            return []

    def search_books(self, query, limit=10):
        """Search for books"""
        return self.search(query, query_type="Book", per_page=limit)

    def search_authors(self, query, limit=10):
        """Search for authors"""
        return self.search(query, query_type="Author", per_page=limit)
    
    def search_series(self, query, limit=10):
        """Search for series"""
        return self.search(query, query_type="Series", per_page=limit)
    
    def search_lists(self, query, limit=10):
        """Search for lists"""
        return self.search(query, query_type="List", per_page=limit)


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument() or ""
        api_token = extension.preferences.get("api_token", "")
        
        logger.info(f"Received query: '{query}'")
        logger.info(f"API token present: {bool(api_token)}")

        try:
            limit = int(extension.preferences.get("results_limit", "10"))
        except ValueError:
            limit = 10

        if not query:
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Search Hardcover',
                    description='Type to search for books, authors, series, or lists',
                    on_enter=HideWindowAction()
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Search Books (default)',
                    description='hc <book name>',
                    on_enter=HideWindowAction()
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Search Authors',
                    description='hc author <author name>',
                    on_enter=HideWindowAction()
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Search Series',
                    description='hc series <series name>',
                    on_enter=HideWindowAction()
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Search Lists',
                    description='hc list <list name>',
                    on_enter=HideWindowAction()
                )
            ])

        # Parse command
        parts = query.split(None, 1)
        command = parts[0].lower() if parts else ""
        search_query = parts[1] if len(parts) > 1 else query

        logger.info(f"Command: '{command}', Search query: '{search_query}'")

        api = HardcoverAPI(api_token)
        items = []

        try:
            if command in ["author", "authors"] and len(parts) > 1:
                # Search for authors
                logger.info("Searching for authors")
                authors = api.search_authors(search_query, limit)
                logger.info(f"Found {len(authors)} authors")
                for author in authors:
                    items.append(create_author_item(author))

            elif command in ["series"] and len(parts) > 1:
                # Search for series
                logger.info("Searching for series")
                series_list = api.search_series(search_query, limit)
                logger.info(f"Found {len(series_list)} series")
                for series in series_list:
                    items.append(create_series_item(series))

            elif command in ["list", "lists"] and len(parts) > 1:
                # Search for lists
                logger.info("Searching for lists")
                lists = api.search_lists(search_query, limit)
                logger.info(f"Found {len(lists)} lists")
                for list_item in lists:
                    items.append(create_list_item(list_item))

            else:
                # Default search for books
                if command in ["author", "authors", "series", "list", "lists"] and len(parts) == 1:
                    items.append(ExtensionResultItem(
                        icon='images/icon.png',
                        name=f'Type a {command} name to search',
                        description=f'Example: hc {command} <name>',
                        on_enter=HideWindowAction()
                    ))
                else:
                    logger.info("Searching for books")
                    books = api.search_books(search_query, limit)
                    logger.info(f"Found {len(books)} books")
                    for book in books:
                        items.append(create_book_item(book))

        except Exception as e:
            logger.error(f"Error processing search: {e}", exc_info=True)
            items.append(ExtensionResultItem(
                icon='images/icon.png',
                name='Error occurred',
                description=f'Error: {str(e)}',
                on_enter=HideWindowAction()
            ))

        if not items:
            logger.warning("No items to display")
            items.append(ExtensionResultItem(
                icon='images/icon.png',
                name='No results found',
                description=f'No results for "{search_query}"',
                on_enter=HideWindowAction()
            ))

        logger.info(f"Returning {len(items)} items")
        return RenderResultListAction(items)


class ItemEnterEventListener(EventListener):
    def on_event(self, event, extension):
        data = event.get_data()
        action = data.get("action")

        if action == "open_url":
            return OpenUrlAction(data.get("url"))
        
        return HideWindowAction()


def create_book_item(book):
    """Create an ExtensionResultItem from book data"""
    logger.debug(f"Creating book item from: {json.dumps(book, indent=2)[:300]}")
    
    title = book.get("title", "Unknown Title")
    slug = book.get("slug", "")
    
    # Get author names
    author_names = book.get("author_names", [])
    if isinstance(author_names, list):
        authors_str = ", ".join(author_names)
    else:
        authors_str = str(author_names) if author_names else "Unknown Author"
    
    # Get additional info
    release_year = book.get("release_year", "")
    rating = book.get("rating", "")
    users_count = book.get("users_count", 0)
    
    # Build description
    desc_parts = []
    if authors_str:
        desc_parts.append(f"By {authors_str}")
    if release_year:
        desc_parts.append(f"Released: {release_year}")
    if rating:
        desc_parts.append(f"⭐ {rating}")
    if users_count:
        desc_parts.append(f"👥 {users_count} readers")
    
    full_description = " | ".join(desc_parts) if desc_parts else "No information available"

    return ExtensionResultItem(
        icon='images/icon.png',
        name=title,
        description=full_description,
        on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/books/{slug}")
    )


def create_author_item(author):
    """Create an ExtensionResultItem from author data"""
    logger.debug(f"Creating author item from: {json.dumps(author, indent=2)[:300]}")
    
    name = author.get("name", "Unknown Author")
    slug = author.get("slug", "")
    books_count = author.get("books_count", 0)
    
    # Get book titles
    books = author.get("books", [])
    if isinstance(books, list) and books:
        books_preview = ", ".join(books[:3])
        if len(books) > 3:
            books_preview += "..."
    else:
        books_preview = "No books listed"
    
    description = f"📚 {books_count} books | {books_preview}"

    return ExtensionResultItem(
        icon='images/icon.png',
        name=name,
        description=description,
        on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/authors/{slug}")
    )


def create_series_item(series):
    """Create an ExtensionResultItem from series data"""
    logger.debug(f"Creating series item from: {json.dumps(series, indent=2)[:300]}")
    
    name = series.get("name", "Unknown Series")
    slug = series.get("slug", "")
    author_name = series.get("author_name", "")
    books_count = series.get("books_count", 0)
    
    # Get book titles
    books = series.get("books", [])
    if isinstance(books, list) and books:
        books_preview = ", ".join([b.get("title", "") if isinstance(b, dict) else str(b) for b in books[:3]])
        if len(books) > 3:
            books_preview += "..."
    else:
        books_preview = ""
    
    desc_parts = []
    if author_name:
        desc_parts.append(f"By {author_name}")
    if books_count:
        desc_parts.append(f"{books_count} books")
    if books_preview:
        desc_parts.append(books_preview)
    
    description = " | ".join(desc_parts) if desc_parts else "No information available"

    return ExtensionResultItem(
        icon='images/icon.png',
        name=name,
        description=description,
        on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/series/{slug}")
    )


def create_list_item(list_data):
    """Create an ExtensionResultItem from list data"""
    logger.debug(f"Creating list item from: {json.dumps(list_data, indent=2)[:300]}")
    
    name = list_data.get("name", "Untitled List")
    slug = list_data.get("slug", "")
    books_count = list_data.get("books_count", 0)
    likes_count = list_data.get("likes_count", 0)
    
    # Get user info
    user = list_data.get("user", {})
    username = user.get("username", "Unknown") if isinstance(user, dict) else "Unknown"
    
    # Get book titles
    books = list_data.get("books", [])
    if isinstance(books, list) and books:
        books_preview = ", ".join(books[:3])
        if len(books) > 3:
            books_preview += "..."
    else:
        books_preview = ""
    
    desc_parts = [f"By @{username}"]
    if books_count:
        desc_parts.append(f"📚 {books_count} books")
    if likes_count:
        desc_parts.append(f"❤️ {likes_count} likes")
    if books_preview:
        desc_parts.append(books_preview)
    
    description = " | ".join(desc_parts)

    return ExtensionResultItem(
        icon='images/icon.png',
        name=name,
        description=description,
        on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/lists/{slug}")
    )


if __name__ == '__main__':
    HardcoverExtension().run()
