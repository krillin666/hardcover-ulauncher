import logging
import requests
import json
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction

logger = logging.getLogger(__name__)

API_ENDPOINT = "https://api.hardcover.app/v1/graphql"

class HardcoverExtension(Extension):
    def __init__(self):
        super(HardcoverExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())

class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument()
        # Clean the token: remove whitespace and 'Bearer ' if the user pasted it
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

        # GraphQL query
        graphql_query = """
        query SearchBooks($q: String!) {
          books(where: {title: {_ilike: $q}}, limit: 8, order_by: {users_read_count: desc}) {
            title
            slug
            contributions {
              author {
                name
              }
            }
            images(where: {type: {_eq: "cover"}}, limit: 1) {
              url
            }
          }
        }
        """

        # FIX: Add a real User-Agent to bypass Cloudflare/WAF 403 errors
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        variables = {"q": f"%{query}%"}

        try:
            response = requests.post(
                API_ENDPOINT,
                json={'query': graphql_query, 'variables': variables},
                headers=headers,
                timeout=5
            )
            
            # Log the status if it fails
            if response.status_code != 200:
                logger.error(f"Hardcover API Error: {response.status_code} - {response.text}")
                response.raise_for_status()
                
            data = response.json()
            books = data.get('data', {}).get('books', [])
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
            logger.error(f"Error fetching data from Hardcover: {e}")
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Error',
                    description='Check Ulauncher logs for details (403/Forbidden often means invalid token)',
                    on_enter=OpenUrlAction("https://hardcover.app/account/api")
                )
            ])

if __name__ == '__main__':
    HardcoverExtension().run()
