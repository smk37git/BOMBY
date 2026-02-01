"""YouTube platform listener"""
import requests
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .polling_base import Poller, BasePlatformPoller, start_poller
from .twitch import send_alert
from .models import PlatformConnection, WidgetConfig

yt_poller = Poller('YOUTUBE')


class YouTubePoller(BasePlatformPoller):
    PLATFORM = 'youtube'
    POLL_INTERVAL = 10.0
    MAX_ERRORS = 10
    
    def __init__(self, poller, user_id, key):
        super().__init__(poller, user_id, key)
        self._last_state = {
            'consecutive_not_live': 0,
            'subscriber_check_counter': 0,
            'processed_chat_ids': set(),
        }
        self.channel_layer = get_channel_layer()
    
    def poll(self) -> bool:
        conn = self.get_connection()
        if not conn:
            return False
        
        token = conn.access_token
        
        # Check if live
        resp = requests.get(
            'https://www.googleapis.com/youtube/v3/liveBroadcasts',
            params={'part': 'snippet,contentDetails', 'broadcastType': 'all', 'mine': 'true', 'maxResults': 5},
            headers={'Authorization': f'Bearer {token}'},
            timeout=10
        )
        
        if resp.status_code != 200:
            print(f'[YOUTUBE] API error {resp.status_code}')
            self._last_state['consecutive_not_live'] += 1
            if self._last_state['consecutive_not_live'] >= 5:
                return False
            return True
        
        # Find active broadcast
        items = resp.json().get('items', [])
        active_broadcast = next((item for item in items if 'liveChatId' in item['snippet']), None)
        
        if not active_broadcast:
            self._last_state['consecutive_not_live'] += 1
            print(f'[YOUTUBE] No active broadcast ({self._last_state["consecutive_not_live"]}/10)')
            if self._last_state['consecutive_not_live'] >= 10:
                return False
            return True
        
        self._last_state['consecutive_not_live'] = 0
        live_chat_id = active_broadcast['snippet']['liveChatId']
        
        # Check subscribers periodically
        self._check_subscribers(conn, token)
        
        # Poll live chat
        self._poll_chat(conn, token, live_chat_id)
        
        self.reset_errors()
        return True
    
    def _check_subscribers(self, conn, token):
        """Check for new subscribers every 6 polls (~60 seconds)"""
        self._last_state['subscriber_check_counter'] += 1
        if self._last_state['subscriber_check_counter'] < 6:
            return
        
        self._last_state['subscriber_check_counter'] = 0
        
        try:
            resp = requests.get(
                'https://www.googleapis.com/youtube/v3/subscriptions',
                params={'part': 'snippet', 'myRecentSubscribers': 'true', 'maxResults': 50},
                headers={'Authorization': f'Bearer {token}'},
                timeout=10
            )
            
            if resp.status_code != 200:
                print(f'[YOUTUBE] Subscription API error {resp.status_code}')
                return
            
            sub_data = resp.json()
            known_subs = set(conn.metadata.get('yt_subscribers', []))
            current_subs = {
                item['snippet']['resourceId']['channelId']
                for item in sub_data.get('items', [])
            }
            
            new_subs = current_subs - known_subs
            if new_subs:
                for item in sub_data.get('items', []):
                    channel_id = item['snippet']['resourceId']['channelId']
                    if channel_id in new_subs:
                        self.send_alert('subscribe', {'username': item['snippet']['title']})
                        print(f'[YOUTUBE] New sub: {item["snippet"]["title"]}')
                
                conn.metadata['yt_subscribers'] = list(current_subs)
                conn.save()
                
        except Exception as e:
            print(f'[YOUTUBE] Subscriber check failed: {e}')
    
    def _poll_chat(self, conn, token, live_chat_id):
        """Poll live chat for messages and events"""
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
        
        if resp.status_code != 200:
            print(f'[YOUTUBE] Chat API error {resp.status_code}')
            return
        
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
        self.POLL_INTERVAL = new_interval
    
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