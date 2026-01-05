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
        self.api_token = api_token
        self.headers = {
            "Content-Type": "application/json",
        }
        if api_token:
            self.headers["Authorization"] = f"Bearer {api_token}"

    def search_books(self, query, limit=10):
        """Search for books"""
        graphql_query = """
        query SearchBooks($query: String!, $limit: Int!) {
          search(query: $query, limit: $limit) {
            works {
              id
              title
              description
              slug
              cached_image
              contributions {
                author {
                  name
                }
              }
              default_physical_edition {
                isbn_13
                release_date
              }
            }
          }
        }
        """

        payload = {
            "query": graphql_query,
            "variables": {"query": query, "limit": limit}
        }

        try:
            response = requests.post(
                HARDCOVER_API_URL,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("search", {}).get("works", [])
        except Exception as e:
            logger.error(f"Error searching books: {e}")
            return []

    def search_authors(self, query, limit=10):
        """Search for authors"""
        graphql_query = """
        query SearchAuthors($query: String!, $limit: Int!) {
          authors(where: {name: {_ilike: $query}}, limit: $limit) {
            id
            name
            bio
            slug
            cached_image
          }
        }
        """

        payload = {
            "query": graphql_query,
            "variables": {"query": f"%{query}%", "limit": limit}
        }

        try:
            response = requests.post(
                HARDCOVER_API_URL,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("authors", [])
        except Exception as e:
            logger.error(f"Error searching authors: {e}")
            return []

    def get_book_details(self, book_id):
        """Get detailed information about a book"""
        graphql_query = """
        query GetBook($id: Int!) {
          books_by_pk(id: $id) {
            id
            title
            description
            slug
            cached_image
            contributions {
              author {
                name
              }
            }
            editions {
              id
              title
              isbn_13
              pages
              release_date
              edition_format
            }
          }
        }
        """

        payload = {
            "query": graphql_query,
            "variables": {"id": int(book_id)}
        }

        try:
            response = requests.post(
                HARDCOVER_API_URL,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("books_by_pk")
        except Exception as e:
            logger.error(f"Error getting book details: {e}")
            return None


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument() or ""
        api_token = extension.preferences.get("api_token", "")
        
        if not api_token:
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
                    description='Type to search for books or authors',
                    on_enter=HideWindowAction()
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Search Books',
                    description='Type: book <query>',
                    on_enter=HideWindowAction()
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Search Authors',
                    description='Type: author <query>',
                    on_enter=HideWindowAction()
                )
            ])

        # Parse command
        parts = query.split(None, 1)
        command = parts[0].lower() if parts else ""
        search_query = parts[1] if len(parts) > 1 else ""

        api = HardcoverAPI(api_token)
        items = []

        if command == "author" and search_query:
            # Search for authors
            authors = api.search_authors(search_query, limit)
            for author in authors:
                name = author.get("name", "Unknown Author")
                bio = author.get("bio", "No bio available")[:100]
                slug = author.get("slug", "")
                
                items.append(ExtensionResultItem(
                    icon='images/icon.png',
                    name=name,
                    description=bio,
                    on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/authors/{slug}")
                ))

        elif command == "book" and search_query:
            # Search for books
            books = api.search_books(search_query, limit)
            for book in books:
                items.append(create_book_item(book))

        else:
            # Default search for books
            if query:
                books = api.search_books(query, limit)
                for book in books:
                    items.append(create_book_item(book))

        if not items:
            items.append(ExtensionResultItem(
                icon='images/icon.png',
                name='No results found',
                description=f'No results for "{query}"',
                on_enter=HideWindowAction()
            ))

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
    title = book.get("title", "Unknown Title")
    description = book.get("description", "")
    slug = book.get("slug", "")
    
    authors = book.get("contributions", [])
    author_names = ", ".join([c.get("author", {}).get("name", "") for c in authors if c.get("author")])
    
    edition = book.get("default_physical_edition") or {}
    release_date = edition.get("release_date", "")
    
    # Build description
    desc_parts = []
    if author_names:
        desc_parts.append(f"By {author_names}")
    if release_date:
        desc_parts.append(f"Released: {release_date}")
    if description:
        desc_parts.append(description[:100] + "..." if len(description) > 100 else description)
    
    full_description = " | ".join(desc_parts) if desc_parts else "No description available"

    return ExtensionResultItem(
        icon='images/icon.png',
        name=title,
        description=full_description,
        on_enter=OpenUrlAction(f"{HARDCOVER_BASE_URL}/books/{slug}")
    )


if __name__ == '__main__':
    HardcoverExtension().run()
