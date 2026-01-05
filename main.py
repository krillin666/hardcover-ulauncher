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

logger = logging.getLogger(__name__)

HARDCOVER_API_URL = "https://api.hardcover.app/v1/graphql"
HARDCOVER_BASE_URL = "https://hardcover.app"


class HardcoverExtension(Extension):
    def __init__(self):
        super(HardcoverExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())


class HardcoverAPI:
    """Wrapper for Hardcover GraphQL API"""

    def __init__(self, api_token):
        # Strip whitespace and quotes from token
        self.api_token = api_token.strip().strip('"').strip("'") if api_token else ""
        
        self.headers = {
            "Content-Type": "application/json",
        }
        
        if self.api_token:
            # Format exactly like the working curl command
            self.headers["Authorization"] = f"Bearer {self.api_token}"
            logger.info(f"Token length: {len(self.api_token)}")
            logger.debug(f"Authorization header: Bearer {self.api_token[:20]}...{self.api_token[-20:]}")

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
            
            # Get results
            search_data = data.get("data", {}).get("search", {})
            results_json = search_data.get("results", [])
            
            logger.info(f"Got {len(results_json)} raw results")
            
            # Parse JSON strings
            parsed_results = []
            for result_str in results_json:
                try:
                    parsed = json.loads(result_str)
                    parsed_results.append(parsed)
                except json.JSONDecodeError as e:
                    logger.error(f"Error parsing result: {e}")
                    continue
            
            logger.info(f"Parsed {len(parsed_results)} results")
            return parsed_results
            
        except Exception as e:
            logger.error(f"Error searching: {e}", exc_info=True)
            return []


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument() or ""
        api_token = extension.preferences.get("api_token", "")
        
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
            ])

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
                items.append(create_book_item(result))
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


def create_book_item(book):
    """Create item from book data"""
    title = book.get("title", "Unknown Title")
    slug = book.get("slug", "")
    
    author_names = book.get("author_names", [])
    authors_str = ", ".join(author_names) if isinstance(author_names, list) else ""
    
    release_year = book.get("release_year", "")
    rating = book.get("rating", "")
    
    desc_parts = []
    if authors_str:
        desc_parts.append(f"By {authors_str}")
    if release_year:
        desc_parts.append(str(release_year))
    if rating:
        desc_parts.append(f"⭐ {rating}")
    
    description = " | ".join(desc_parts) if desc_parts else "Book"

    return ExtensionResultItem(
        icon='images/icon.png',
        name=title,
        description=description,
        on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/books/{slug}")
    )


def create_author_item(author):
    """Create item from author data"""
    name = author.get("name", "Unknown Author")
    slug = author.get("slug", "")
    books_count = author.get("books_count", 0)
    
    description = f"📚 {books_count} books" if books_count else "Author"

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
