"""
Base polling infrastructure for platform listeners.
"""
import time
import threading
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable
import requests

from .twitch import send_alert
from .models import PlatformConnection


class Poller:
    """Manages active pollers with thread-safe operations"""
    
    def __init__(self, name: str):
        self.name = name
        self._pollers: Dict[str, dict] = {}
        self._lock = threading.Lock()
    
    def is_active(self, key: str) -> bool:
        with self._lock:
            return key in self._pollers and self._pollers[key].get('active', False)
    
    def register(self, key: str, user_id: int, **extra) -> bool:
        """Register a new poller. Returns False if already exists."""
        with self._lock:
            if key in self._pollers:
                print(f'[{self.name}] Already polling {key}')
                return False
            self._pollers[key] = {'active': True, 'user_id': user_id, **extra}
            return True
    
    def stop(self, key: str) -> bool:
        """Mark poller for stopping"""
        with self._lock:
            if key in self._pollers:
                self._pollers[key]['active'] = False
                print(f'[{self.name}] Marked {key} for stop')
                return True
            print(f'[{self.name}] No active poller for {key}')
            return False
    
    def remove(self, key: str):
        """Remove poller from registry"""
        with self._lock:
            self._pollers.pop(key, None)
    
    def get_data(self, key: str) -> Optional[dict]:
        """Get poller data"""
        with self._lock:
            return self._pollers.get(key, {}).copy()


class BasePlatformPoller(ABC):
    """
    Base class for platform polling.
    Subclasses implement platform-specific logic.
    """
    
    PLATFORM: str = None
    POLL_INTERVAL: float = 5.0
    MAX_ERRORS: int = 5
    
    def __init__(self, poller: Poller, user_id: int, key: str):
        self.poller = poller
        self.user_id = user_id
        self.key = key
        self.error_count = 0
        self._last_state: Dict[str, Any] = {}
    
    @abstractmethod
    def poll(self) -> bool:
        """
        Execute one poll cycle.
        Returns True to continue, False to stop.
        """
        pass
    
    def get_connection(self) -> Optional[PlatformConnection]:
        """Get platform connection from DB"""
        try:
            return PlatformConnection.objects.get(
                user_id=self.user_id, 
                platform=self.PLATFORM
            )
        except PlatformConnection.DoesNotExist:
            print(f'[{self.poller.name}] Connection not found for user {self.user_id}')
            return None
    
    def send_alert(self, event_type: str, event_data: dict):
        """Send alert through unified system"""
        send_alert(self.user_id, event_type, self.PLATFORM, event_data)
    
    def handle_error(self, msg: str = None):
        """Increment error count, return True if should stop"""
        self.error_count += 1
        if msg:
            print(f'[{self.poller.name}] {msg}')
        return self.error_count >= self.MAX_ERRORS
    
    def reset_errors(self):
        """Reset error count on success"""
        self.error_count = 0
    
    def run(self):
        """Main polling loop"""
        print(f'[{self.poller.name}] ✓ Polling started for {self.key}')
        
        while self.poller.is_active(self.key):
            try:
                if not self.poll():
                    break
            except Exception as e:
                if self.handle_error(f'Error polling {self.key}: {e}'):
                    print(f'[{self.poller.name}] ✗ Too many errors, stopping {self.key}')
                    break
            
            time.sleep(self.POLL_INTERVAL)
        
        self.poller.remove(self.key)
        print(f'[{self.poller.name}] Listener exited for {self.key}')


def start_poller(poller: Poller, poller_class: type, user_id: int, key: str, **kwargs) -> bool:
    """Generic poller start function"""
    if not poller.register(key, user_id):
        return False
    
    instance = poller_class(poller, user_id, key, **kwargs)
    thread = threading.Thread(
        target=instance.run, 
        daemon=True, 
        name=f'{poller.name.lower()}-{key}'
    )
    thread.start()
    return True


# HTTP helper with retries
def safe_request(url: str, method: str = 'GET', timeout: int = 5, **kwargs) -> Optional[requests.Response]:
    """Make HTTP request with error handling"""
    try:
        resp = requests.request(method, url, timeout=timeout, **kwargs)
        return resp
    except requests.Timeout:
        return None
    except requests.RequestException:
        return None