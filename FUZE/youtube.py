"""YouTube platform listener"""
import requests
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .polling_base import Poller, BasePlatformPoller, start_poller
from .twitch import send_alert
from .models import PlatformConnection, WidgetConfig
from .views_helpers import broadcast_viewer_count

yt_poller = Poller('YOUTUBE')


class YouTubePoller(BasePlatformPoller):
    PLATFORM = 'youtube'
    POLL_INTERVAL = 10.0  # Chat/subscriber polling when live
    MAX_ERRORS = 10
    
    def __init__(self, poller, user_id, key):
        super().__init__(poller, user_id, key)
        self._last_state = {
            'subscriber_check_counter': 0,
            'broadcast_check_counter': 0,
            'processed_chat_ids': set(),
            'last_viewers': 0,
            'live_chat_id': None,
            'video_id': None,
        }
        self.channel_layer = get_channel_layer()
    
    def poll(self) -> bool:
        conn = self.get_connection()
        if not conn:
            return False
        
        token = conn.access_token
        
        # Only check broadcast status every 60 polls (~10 min) or if we don't have a chat ID
        # This saves 100 quota units per skipped check
        need_broadcast_check = (
            not self._last_state['live_chat_id'] or 
            self._last_state['broadcast_check_counter'] >= 60
        )
        
        if need_broadcast_check:
            self._last_state['broadcast_check_counter'] = 0
            
            resp = requests.get(
                'https://www.googleapis.com/youtube/v3/liveBroadcasts',
                params={'part': 'snippet', 'broadcastStatus': 'active', 'maxResults': 1},
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )
            
            if resp.status_code in (401, 403):
                return False
            
            if resp.status_code != 200:
                return False
            
            items = resp.json().get('items', [])
            active = next((i for i in items if 'liveChatId' in i.get('snippet', {})), None)
            
            if not active:
                self._last_state['live_chat_id'] = None
                return False  # Not live
            
            self._last_state['live_chat_id'] = active['snippet']['liveChatId']
            self._last_state['video_id'] = active['id']
        
        self._last_state['broadcast_check_counter'] += 1
        
        # Poll chat - if this fails with 403/404, stream likely ended
        if not self._poll_chat(conn, token, self._last_state['live_chat_id']):
            self._last_state['live_chat_id'] = None  # Force recheck
            return True  # Keep alive, will recheck broadcast next poll
        
        # Subscriber check every 6 polls (~1 min) - costs only 1 unit
        self._check_subscribers(conn, token)
        
        # Viewer count every 30 polls (~5 min) - costs 1 unit
        if self._last_state['broadcast_check_counter'] % 30 == 0:
            self._check_viewer_count(conn, token, self._last_state['video_id'])
        
        self.reset_errors()
        return True
    
    def _check_viewer_count(self, conn, token, video_id):
        if not video_id:
            return
        try:
            resp = requests.get(
                'https://www.googleapis.com/youtube/v3/videos',
                params={'part': 'liveStreamingDetails', 'id': video_id},
                headers={'Authorization': f'Bearer {token}'},
                timeout=5
            )
            if resp.status_code == 200:
                videos = resp.json().get('items', [])
                if videos:
                    viewers = int(videos[0].get('liveStreamingDetails', {}).get('concurrentViewers', 0))
                    if viewers != self._last_state.get('last_viewers', 0):
                        self._last_state['last_viewers'] = viewers
                        broadcast_viewer_count(self.user_id, 'youtube', viewers)
        except Exception:
            pass
    
    def _check_subscribers(self, conn, token):
        """Check subscribers every 30 polls (~5 min)"""
        self._last_state['subscriber_check_counter'] += 1
        if self._last_state['subscriber_check_counter'] < 30:
            return
        
        self._last_state['subscriber_check_counter'] = 0
        
        try:
            resp = requests.get(
                'https://www.googleapis.com/youtube/v3/subscriptions',
                params={'part': 'subscriberSnippet', 'myRecentSubscribers': 'true', 'maxResults': 50},
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )
            
            if resp.status_code != 200:
                return
            
            sub_data = resp.json()
            items = sub_data.get("items", [])
            if items:
                print(f'[YOUTUBE] Subscriber check: found {len(items)} recent subscribers')
            known_subs = set(conn.metadata.get('yt_subscribers', []))
            current_subs = {
                item['subscriberSnippet']['channelId']
                for item in sub_data.get('items', [])
                if 'subscriberSnippet' in item
            }
            
            new_subs = current_subs - known_subs
            if new_subs:
                for item in sub_data.get('items', []):
                    if 'subscriberSnippet' not in item:
                        continue
                    channel_id = item['subscriberSnippet']['channelId']
                    if channel_id in new_subs:
                        self.send_alert('subscribe', {'username': item['subscriberSnippet']['title']})
                        print(f'[YOUTUBE] ✓ New sub: {item["subscriberSnippet"]["title"]}')
                
                conn.metadata['yt_subscribers'] = list(current_subs)
                conn.save()
                
        except Exception:
            pass  # Silent fail
    
    def _poll_chat(self, conn, token, live_chat_id):
        """Poll live chat - returns False if stream ended"""
        page_token = conn.metadata.get('yt_page_token')
        params = {
            'liveChatId': live_chat_id,
            'part': 'snippet,authorDetails',
            'maxResults': 200
        }
        if page_token:
            params['pageToken'] = page_token
        
        resp = requests.get(
            'https://www.googleapis.com/youtube/v3/liveChat/messages',
            params=params,
            headers={'Authorization': f'Bearer {token}'},
            timeout=10
        )
        
        if resp.status_code in (403, 404):
            return False  # Chat ended = stream ended
        
        if resp.status_code != 200:
            return True  # Other error, keep trying
        
        data = resp.json()
        chat_enabled = WidgetConfig.objects.filter(
            user_id=self.user_id,
            widget_type='chat_box',
            enabled=True
        ).exists()
        
        processed = self._last_state['processed_chat_ids']
        
        for msg in data.get('items', []):
            msg_id = msg['id']
            snippet = msg['snippet']
            author = msg['authorDetails']['displayName']
            
            # SuperChat
            if 'superChatDetails' in snippet:
                self.send_alert('superchat', {
                    'username': author,
                    'amount': snippet['superChatDetails']['amountDisplayString']
                })
                print(f'[YOUTUBE] SuperChat: {author}')
            
            # New Member
            elif 'newSponsorDetails' in snippet:
                self.send_alert('member', {'username': author})
                print(f'[YOUTUBE] New member: {author}')
            
            # Regular chat message
            if chat_enabled and msg_id not in processed:
                processed.add(msg_id)
                self._send_chat_message(msg)
        
        # Limit processed_chat_ids size
        if len(processed) > 1000:
            processed.clear()
        
        # Update poll interval from API response
        conn.metadata['yt_page_token'] = data.get('nextPageToken')
        conn.save()
        
        new_interval = data.get('pollingIntervalMillis', 5000) / 1000
        self.POLL_INTERVAL = max(new_interval, 5.0)  # Minimum 5s
        return True
    
    def _send_chat_message(self, msg):
        """Send chat message to WebSocket"""
        snippet = msg['snippet']
        author_details = msg['authorDetails']
        
        message_text = snippet.get('displayMessage', '')
        if not message_text and 'textMessageDetails' in snippet:
            message_text = snippet['textMessageDetails'].get('messageText', '')
        
        if not message_text:
            return
        
        badges = []
        if author_details.get('isChatOwner'):
            badges.append('broadcaster')
        if author_details.get('isChatModerator'):
            badges.append('moderator')
        if author_details.get('isChatSponsor'):
            badges.append('member')
        if author_details.get('isVerified'):
            badges.append('verified')
        
        async_to_sync(self.channel_layer.group_send)(
            f'chat_{self.user_id}',
            {
                'type': 'chat_message',
                'data': {
                    'username': author_details['displayName'],
                    'message': message_text,
                    'badges': badges,
                    'color': '#FF0000',
                    'platform': 'youtube',
                    'emotes': []
                }
            }
        )


def start_youtube_listener(user_id: int, access_token: str) -> bool:
    """Start YouTube listener for user"""
    print(f'[YOUTUBE] Starting listener for user {user_id}')
    return start_poller(yt_poller, YouTubePoller, user_id, str(user_id))


def stop_youtube_listener(user_id: int):
    """Stop YouTube listener"""
    print(f'[YOUTUBE] Stopping for user {user_id}')
    yt_poller.stop(str(user_id))