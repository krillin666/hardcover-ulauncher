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
            if not query:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='Enter a search term',
                        description='Please enter a book title.',
                        on_enter=None
                    )
                ])
    
            # Hardcover Typesense Configuration (Public Search Key)
            # Sourced from Hardcover's public configuration/blogs
            TYPESENSE_URL = "https://search.hardcover.app/collections/books/documents/search"
            TYPESENSE_API_KEY = "7JRcb63AvYIo2WJvE3IzH4f8j1z9fHcC" 
    
            params = {
                "q": query,
                "query_by": "title,author_names",
                "sort_by": "users_read_count:desc",
                "per_page": 8
            }
            
            headers = {
                "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY
            }
    
            try:
                response = requests.get(TYPESENSE_URL, params=params, headers=headers, timeout=5)
                
                if response.status_code != 200:
                    logger.error(f"Typesense Error: {response.status_code} - {response.text}")
                    return RenderResultListAction([
                        ExtensionResultItem(
                            icon='images/icon.png',
                            name='Search Failed',
                            description='Could not connect to Hardcover Search.',
                            on_enter=None
                        )
                    ])
    
                data = response.json()
                hits = data.get('hits', [])
                items = []
    
                for hit in hits:
                    doc = hit.get('document', {})
                    title = doc.get('title')
                    slug = doc.get('slug')
                    # Authors are a list in Typesense, usually
                    authors = doc.get('author_names', [])
                    author_name = authors[0] if authors else "Unknown Author"
                    
                    # Image URL handling (Typesense usually returns a path or full URL)
                    # You might need to adjust based on the exact response, but this is a safe fallback
                    
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
                logger.error(f"Error fetching data: {e}")
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='Error',
                        description='Check logs for details.',
                        on_enter=None
                    )
                ])

if __name__ == '__main__':
    HardcoverExtension().run()
