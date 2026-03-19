"""Facebook platform listener"""
import re
import requests
from .polling_base import Poller, BasePlatformPoller, start_poller, safe_request
from .models import PlatformConnection
from .views_helpers import broadcast_viewer_count

fb_poller = Poller('FACEBOOK')


class FacebookPoller(BasePlatformPoller):
    PLATFORM = 'facebook'
    POLL_INTERVAL = 5.0
    
    def __init__(self, poller, user_id, key, access_token=None):
        super().__init__(poller, user_id, key)
        self.page_id = key
        self._last_state = {
            'followers': None,
            'processed_comments': set(),
            'live_video_id': None,
            'last_viewers': 0
        }
    
    def poll(self) -> bool:
        conn = self.get_connection()
        if not conn:
            return False
        
        token = conn.access_token
        
        # Check for live videos and poll comments
        self._check_live_stream(token)
        
        # Poll follower count
        return self._check_followers(token)
    
    def _check_live_stream(self, token: str):
        resp = safe_request(
            f'https://graph.facebook.com/v18.0/{self.page_id}/live_videos',
            params={'access_token': token, 'fields': 'id,status,live_views', 'limit': 1},
            timeout=3
        )
        
        if not resp or resp.status_code != 200:
            return
        
        live_data = resp.json()
        active_streams = [v for v in live_data.get('data', []) if v.get('status') == 'LIVE']
        
        if not active_streams:
            self._last_state['live_video_id'] = None
            return
        
        live_video = active_streams[0]
        live_video_id = live_video['id']
        self._last_state['live_video_id'] = live_video_id
        
        # Broadcast viewer count if changed
        viewers = live_video.get('live_views', 0)
        if viewers != self._last_state.get('last_viewers', 0):
            self._last_state['last_viewers'] = viewers
            broadcast_viewer_count(self.user_id, 'facebook', viewers)
        
        # Poll comments for Stars
        self._poll_live_comments(token, live_video_id)
    
    def _poll_live_comments(self, token: str, video_id: str):
        resp = safe_request(
            f'https://graph.facebook.com/v18.0/{video_id}/comments',
            params={
                'access_token': token,
                'fields': 'id,from,message,created_time',
                'filter': 'stream',
                'limit': 50
            },
            timeout=3
        )
        
        if not resp or resp.status_code != 200:
            return
        
        processed = self._last_state['processed_comments']
        
        for comment in resp.json().get('data', []):
            comment_id = comment['id']
            if comment_id in processed:
                continue
            
            processed.add(comment_id)
            message = comment.get('message', '')
            username = comment.get('from', {}).get('name', 'Someone')
            
            # Check for Stars
            if 'sent' in message.lower() and 'star' in message.lower():
                star_match = re.search(r'(\d+)\s*[Ss]tar', message)
                if star_match:
                    star_count = star_match.group(1)
                    self.send_alert('stars', {
                        'username': username,
                        'amount': star_count
                    })
                    print(f'[FACEBOOK] ✓ Stars! {username} sent {star_count} Stars')
    
    def _check_followers(self, token: str) -> bool:
        resp = safe_request(
            f'https://graph.facebook.com/v18.0/{self.page_id}',
            params={'access_token': token, 'fields': 'followers_count'},
            timeout=3
        )
        
        if not resp:
            return not self.handle_error('Timeout')
        
        if resp.status_code == 404:
            print(f'[FACEBOOK] ✗ Page {self.page_id} not found')
            return False
        
        if resp.status_code != 200:
            return not self.handle_error(f'API error {resp.status_code}')
        
        followers = resp.json().get('followers_count', 0)
        last = self._last_state['followers']
        
        if last is None:
            self._last_state['followers'] = followers
            print(f'[FACEBOOK] Initialized - Followers: {followers}')
        elif followers > last:
            count = min(followers - last, 5)
            print(f'[FACEBOOK] ✓ New follower(s)! +{followers - last} (now {followers})')
            for _ in range(count):
                self.send_alert('follow', {'username': 'Someone'})
            self._last_state['followers'] = followers
        
        self.reset_errors()
        return True


def start_facebook_listener(user_id: int, page_id: str, access_token: str) -> bool:
    """Start 5-second polling for Facebook Page"""
    print(f'[FACEBOOK] Starting polling for page {page_id} (user {user_id})')
    return start_poller(fb_poller, FacebookPoller, user_id, page_id, access_token=access_token)


def stop_facebook_listener(page_id: str):
    """Stop Facebook polling"""
    print(f'[FACEBOOK] Stopping polling for {page_id}')
    fb_poller.stop(page_id)