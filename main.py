import logging
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.OpenUrlAction import OpenUrlAction
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.HideWindowAction import HideWindowAction

# Import our ported logic
from api import HardcoverAPI

logger = logging.getLogger(__name__)

class HardcoverExtension(Extension):
    def __init__(self):
        super(HardcoverExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())

class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = event.get_argument() or ""
        api_token = extension.preferences['api_token']
        
        # Initialize API
        api = HardcoverAPI(api_token)
        
        items = []

        # MODE 1: Browse My Library (if query starts with "my ")
        if query.lower().startswith("my "):
            cmd = query[3:].lower().strip()
            
            # Sub-menu for library status
            if not cmd:
                return RenderResultListAction([
                    ExtensionResultItem(icon='images/icon.png', name='Currently Reading', description='Show books you are reading', on_enter=ExtensionCustomAction({'action': 'list_books', 'status': 2}, keep_app_open=True)),
                    ExtensionResultItem(icon='images/icon.png', name='Want to Read', description='Show your wishlist', on_enter=ExtensionCustomAction({'action': 'list_books', 'status': 1}, keep_app_open=True)),
                    ExtensionResultItem(icon='images/icon.png', name='Read', description='Show finished books', on_enter=ExtensionCustomAction({'action': 'list_books', 'status': 3}, keep_app_open=True)),
                ])
        
        # MODE 2: List Books (triggered by the menu above, but handled here for filtering if needed)
        # (This is usually better handled via ItemEnterEvent, see below)

        # MODE 3: General Search (Default)
        if len(query) > 2:
            results = api.search_books(query)
            
            if not results:
                return RenderResultListAction([
                    ExtensionResultItem(icon='images/icon.png', name='No results', description='Try another title', on_enter=HideWindowAction())
                ])

            for book in results:
                # Primary Action: Open in Browser
                # Alt Action: Add to "Want to Read" (Status 1)
                items.append(ExtensionResultItem(
                    icon='images/icon.png',
                    name=book['title'],
                    description=f"by {book['author']}",
                    on_enter=OpenUrlAction(f"https://hardcover.app/books/{book['slug']}"),
                    on_alt_enter=ExtensionCustomAction({
                        'action': 'add_book',
                        'slug': book['slug'],
                        'status': 1 # Default to 'Want to Read'
                    }, keep_app_open=False)
                ))
            return RenderResultListAction(items)
            
        else:
            # Default State
            return RenderResultListAction([
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='Search Hardcover',
                    description='Type to search books...',
                    on_enter=None
                ),
                ExtensionResultItem(
                    icon='images/icon.png',
                    name='My Library',
                    description='Type "my " to browse your lists',
                    on_enter=None 
                    # Note: The user has to type "my " manually or use a keyword 
                    # to trigger the logic above, unless we set query to "my " here.
                )
            ])

class ItemEnterEventListener(EventListener):
    def on_event(self, event, extension):
        data = event.get_data()
        action = data.get('action')
        api_token = extension.preferences['api_token']
        api = HardcoverAPI(api_token)

        # Action: List Books by Status
        if action == 'list_books':
            status_id = data.get('status')
            books = api.get_user_books_by_status(status_id)
            
            items = []
            for book in books:
                items.append(ExtensionResultItem(
                    icon='images/icon.png',
                    name=book['title'],
                    description=f"by {book['author']}",
                    on_enter=OpenUrlAction(f"https://hardcover.app/books/{book['slug']}")
                ))
            
            if not items:
                 items.append(ExtensionResultItem(icon='images/icon.png', name='Empty List', description='No books found in this list.', on_enter=HideWindowAction()))
            
            return RenderResultListAction(items)

        # Action: Add Book
        if action == 'add_book':
            slug = data.get('slug')
            status = data.get('status')
            success = api.add_book_to_library(slug, status)
            
            if success:
                logger.info(f"Added {slug} to library")
                # Usually we can't show a notification easily without an external lib, 
                # so we just hide the window.
            else:
                logger.error("Failed to add book")
            
            return HideWindowAction()

if __name__ == '__main__':
    HardcoverExtension().run()
