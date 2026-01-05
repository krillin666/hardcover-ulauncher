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

# Hardcover's public search endpoint and key
# Sourced from Hardcover's public configuration
TYPESENSE_URL = "https://search.hardcover.app/collections/books/documents/search"
TYPESENSE_API_KEY = "7JRcb63AvYIo2WJvE3IzH4f8j1z9fHcC" 

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
                    description='Search for books on Hardcover...',
                    on_enter=None
                )
            ])

        # ---------------------------------------------------------
        # SEARCH STRATEGY: Typesense (External Search Engine)
        # ---------------------------------------------------------
        
        # 1. Mimic the browser headers to avoid "Read timed out" / 403
        headers = {
            "X-TYPESENSE-API-KEY": TYPESENSE_API_KEY,
            "Origin": "https://hardcover.app",
            "Referer": "https://hardcover.app/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        # 2. Configure the search parameters
        params = {
            "q": query,
            "query_by": "title,author_names",
            "sort_by": "users_read_count:desc", # Sort by popularity
            "per_page": 8,
            "filter_by": "users_read_count:>0"  # Filter out empty stubs if necessary
        }

        try:
            # We use a short timeout because search should be fast. 
            # If it hangs, the firewall is blocking us.
            response = requests.get(
                TYPESENSE_URL, 
                params=params, 
                headers=headers, 
                timeout=5
            )

            if response.status_code != 200:
                logger.error(f"Search Error {response.status_code}: {response.text}")
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='Search Unavailable',
                        description=f'Status: {response.status_code}. See logs.',
                        on_enter=OpenUrlAction("https://hardcover.app/browse")
                    )
                ])

            data = response.json()
            hits = data.get('hits', [])
            items = []

            for hit in hits:
                doc = hit.get('document', {})
                title = doc.get('title')
                slug = doc.get('slug')
                
                # Author handling
                authors = doc.get('author_names', [])
                author_text = authors[0] if authors else "Unknown Author"
                
                # Image handling (Typesense usually has an image_url or similar field)
                # If available in 'doc', you can parse it here.
                
                book_url = f"https://hardcover.app/books/{slug}"

                items.append(ExtensionResultItem(
                    icon='images/icon.png',
                    name=title,
                    description=f"by {author_text}",
                    on_enter=OpenUrlAction(book_url)
                ))

            if not items:
                return RenderResultListAction([
                    ExtensionResultItem(
                        icon='images/icon.png',
                        name='No books found',
                        description=f"Try a different search term for '{query}'",
                        on_enter=OpenUrlAction(f"https://hardcover.app/books?q={query}")
                    )
                ])

            return RenderResultListAction(items)

        except Exception as e:
            logger.error(f"Connection Error: {e}")
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Connection Failed',
                    description='Could not reach Hardcover search server.',
                    on_enter=OpenUrlAction("https://hardcover.app")
                )
            ])

if __name__ == '__main__':
    HardcoverExtension().run()
