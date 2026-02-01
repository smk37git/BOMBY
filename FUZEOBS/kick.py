"""Kick platform listener"""
from .polling_base import Poller, BasePlatformPoller, start_poller, safe_request

kick_poller = Poller('KICK')


class KickPoller(BasePlatformPoller):
    PLATFORM = 'kick'
    POLL_INTERVAL = 3.0
    
    def __init__(self, poller, user_id, key):
        super().__init__(poller, user_id, key)
        self.channel_slug = key
        self._last_state = {'followers': None, 'subs': None}
    
    def poll(self) -> bool:
        resp = safe_request(
            f'https://kick.com/api/v2/channels/{self.channel_slug}',
            headers={'User-Agent': 'FuzeOBS/1.0'},
            timeout=2
        )
        
        if resp is None:
            return not self.handle_error(f'Timeout polling {self.channel_slug}')
        
        if resp.status_code == 404:
            print(f'[KICK] ✗ Channel {self.channel_slug} not found')
            return False
        
        if resp.status_code != 200:
            return not self.handle_error(f'API error {resp.status_code}')
        
        data = resp.json()
        followers = data.get('followers_count', 0)
        subs = data.get('subscribers_count', 0)
        
        # Initialize on first poll
        if self._last_state['followers'] is None:
            self._last_state = {'followers': followers, 'subs': subs}
            print(f'[KICK] Initialized - Followers: {followers}, Subs: {subs}')
        else:
            # Check for changes
            self._check_followers(followers)
            self._check_subs(subs)
        
        self.reset_errors()
        return True
    
    def _check_followers(self, current):
        last = self._last_state['followers']
        if current > last:
            count = min(current - last, 5)
            print(f'[KICK] ✓ New follower(s)! +{current - last} (now {current})')
            for _ in range(count):
                self.send_alert('follow', {'username': self.channel_slug})
            self._last_state['followers'] = current
    
    def _check_subs(self, current):
        last = self._last_state['subs']
        if current > last:
            count = min(current - last, 5)
            print(f'[KICK] ✓ New sub(s)! +{current - last} (now {current})')
            for _ in range(count):
                self.send_alert('subscribe', {'username': self.channel_slug})
            self._last_state['subs'] = current


def start_kick_listener(user_id: int, channel_slug: str) -> bool:
    """Start 3-second polling for Kick channel"""
    print(f'[KICK] Starting 3s polling for {channel_slug} (user {user_id})')
    return start_poller(kick_poller, KickPoller, user_id, channel_slug)


def stop_kick_listener(channel_slug: str):
    """Stop Kick polling"""
    print(f'[KICK] Stopping polling for {channel_slug}')
    kick_poller.stop(channel_slug)