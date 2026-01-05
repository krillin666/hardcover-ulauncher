import logging
import requests
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction

logger = logging.getLogger(__name__)

# Standard GraphQL Endpoint
API_ENDPOINT = "https://api.hardcover.app/v1/graphql"

class HardcoverExtension(Extension):
    def __init__(self):
        super(HardcoverExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())

class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument()
        raw_token = extension.preferences['api_token']
        api_token = raw_token.replace("Bearer ", "").strip()

        if not query or not api_token:
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Enter a search term',
                    description='Please enter a book title.',
                    on_enter=None
                )
            ])

        # ---------------------------------------------------------
        # ATTEMPT 1: The "search_books" function (Hasura Full Text)
        # This is the standard replacement when _ilike is banned.
        # ---------------------------------------------------------
        graphql_query = """
        query Search($q: String!) {
            search_books(
                args: {query: $q}
                limit: 8
            ) {
                title
                slug
                contributions {
                    author {
                        name
                    }
                }
            }
        }
        """

        # Headers
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "Ulauncher-Hardcover/1.0"
        }

        # The search_books function usually takes a simple string, no % wildcards needed
        variables = {"q": query}

        try:
            response = requests.post(
                API_ENDPOINT,
                json={'query': graphql_query, 'variables': variables},
                headers=headers,
                timeout=10
            )

            if response.status_code != 200:
                logger.error(f"API Error: {response.status_code} - {response.text}")
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='API Error',
                        description='Could not verify API token or schema.',
                        on_enter=OpenUrlAction("https://hardcover.app/account/api")
                    )
                ])

            data = response.json()
            
            # Check for GraphQL errors specifically (like if search_books doesn't exist)
            if 'errors' in data:
                logger.error(f"GraphQL Error: {data['errors']}")
                # If search_books failed, fallback to strict match? 
                # For now, let's just show the error to debug.
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='Search Error',
                        description='The search query format was rejected.',
                        on_enter=None
                    )
                ])

            # Note: The key here is 'search_books', not 'books'
            books = data.get('data', {}).get('search_books', [])
            
            items = []
            for book in books:
                title = book.get('title')
                slug = book.get('slug')
                
                contributions = book.get('contributions', [])
                author_name = "Unknown Author"
                if contributions:
                    author_name = contributions[0].get('author', {}).get('name', 'Unknown Author')

                book_url = f"https://hardcover.app/books/{slug}"

                items.append(ExtensionResultItem(
                    icon='images/icon.png',
                    name=title,
                    description=f"by {author_name}",
                    on_enter=OpenUrlAction(book_url)
                ))

            if not items:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='No results found',
                        description=f"No books found for '{query}'",
                        on_enter=OpenUrlAction(f"https://hardcover.app/books?q={query}")
                    )
                ])

            return RenderResultListAction(items)

        except Exception as e:
            logger.error(f"Extension Error: {e}")
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Extension Error',
                    description=str(e),
                    on_enter=None
                )
            ])

if __name__ == '__main__':
    HardcoverExtension().run()
