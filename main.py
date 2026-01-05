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

# Hardcover uses a Hasura-based GraphQL API
API_ENDPOINT = "https://api.hardcover.app/v1/graphql"

class HardcoverExtension(Extension):
    def __init__(self):
        super(HardcoverExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())

class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument()
        api_token = extension.preferences['api_token']

        if not query or not api_token:
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Enter a search term',
                    description='Please enter a book title and ensure your API token is set.',
                    on_enter=None
                )
            ])

        # GraphQL query to search for books by title
        # We use ilike for case-insensitive partial matching
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

        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

        # Wrap query in % for SQL-like wildcard search
        variables = {"q": f"%{query}%"}

        try:
            response = requests.post(
                API_ENDPOINT,
                json={'query': graphql_query, 'variables': variables},
                headers=headers,
                timeout=5
            )
            response.raise_for_status()
            data = response.json()
            
            books = data.get('data', {}).get('books', [])
            items = []

            for book in books:
                title = book.get('title')
                slug = book.get('slug')
                
                # Extract author name
                authors = book.get('contributions', [])
                author_name = "Unknown Author"
                if authors:
                    author_name = authors[0].get('author', {}).get('name', 'Unknown Author')

                # Construct the Hardcover URL
                book_url = f"https://hardcover.app/books/{slug}"

                items.append(ExtensionResultItem(
                    icon='images/icon.png', # Ensure you have an icon.png in an images/ folder
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
                    description='Could not search Hardcover. Check logs or API token.',
                    on_enter=None
                )
            ])

if __name__ == '__main__':
    HardcoverExtension().run()
