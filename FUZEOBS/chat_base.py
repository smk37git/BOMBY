"""Base infrastructure for chat listeners"""
import threading
from typing import Dict, Any, Callable
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


class ChatRegistry:
    """Thread-safe registry for active chat connections"""
    
    def __init__(self, name: str):
        self.name = name
        self._active: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.Lock()
    
    def register(self, user_id: int, data: Dict[str, Any] = None) -> bool:
        """Register a chat connection. Returns False if already exists."""
        with self._lock:
            if user_id in self._active:
                print(f'[{self.name}] Already active for user {user_id}')
                return False
            self._active[user_id] = data or {'active': True}
            return True
    
    def unregister(self, user_id: int):
        """Remove a chat connection"""
        with self._lock:
            self._active.pop(user_id, None)
    
    def is_active(self, user_id: int) -> bool:
        """Check if connection is still active"""
        with self._lock:
            return user_id in self._active and self._active[user_id].get('active', False)
    
    def stop(self, user_id: int) -> bool:
        """Signal a connection to stop"""
        with self._lock:
            if user_id in self._active:
                self._active[user_id]['active'] = False
                return True
            return False
    
    def get(self, user_id: int) -> Dict[str, Any]:
        """Get connection data"""
        with self._lock:
            return self._active.get(user_id, {}).copy()


def is_chat_enabled(user_id: int) -> bool:
    """Check if chat widget is enabled for user"""
    from .models import WidgetConfig
    return WidgetConfig.objects.filter(
        user_id=user_id,
        widget_type='chat_box',
        enabled=True
    ).exists()


def send_chat_message(user_id: int, username: str, message: str, platform: str,
                      badges: list = None, color: str = '#FFFFFF', emotes: list = None):
    """Send a chat message to the user's chat widget"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'chat_{user_id}',
        {
            'type': 'chat_message',
            'data': {
                'username': username,
                'message': message,
                'badges': badges or [],
                'color': color,
                'platform': platform,
                'emotes': emotes or []
            }
        }
    )


def start_chat_thread(name: str, target: Callable, user_id: int, *args) -> threading.Thread:
    """Start a daemon thread for chat processing"""
    thread = threading.Thread(
        target=target,
        args=(user_id, *args),
        daemon=True,
        name=f'{name}-{user_id}'
    )
    thread.start()
    return thread