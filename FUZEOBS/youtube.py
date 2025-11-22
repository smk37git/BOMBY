import requests
import time
import threading
from django.conf import settings
from .twitch import send_alert
from .models import PlatformConnection

# Global dict to track active pollers
yt_pollers = {}
yt_poller_lock = threading.Lock()

def start_youtube_listener(user_id, access_token):
    """Start polling YouTube live chat"""
    print(f'[YOUTUBE] Starting polling for user {user_id}')
    
    with yt_poller_lock:
        if user_id in yt_pollers:
            print(f'[YOUTUBE] Already polling for user {user_id}')
            return
        yt_pollers[user_id] = {'active': True}
    
    def poll_loop():
        error_count = 0
        max_errors = 5
        
        while True:
            with yt_poller_lock:
                if user_id not in yt_pollers or not yt_pollers[user_id]['active']:
                    print(f'[YOUTUBE] Polling stopped for user {user_id}')
                    break
            
            try:
                conn = PlatformConnection.objects.get(user_id=user_id, platform='youtube')
                current_token = conn.access_token
                
                # Get active broadcast
                resp = requests.get(
                    'https://www.googleapis.com/youtube/v3/liveBroadcasts',
                    params={'part': 'snippet', 'broadcastStatus': 'active', 'mine': 'true'},
                    headers={'Authorization': f'Bearer {current_token}'},
                    timeout=5
                )
                
                if resp.status_code != 200:
                    print(f'[YOUTUBE] No active broadcast (status {resp.status_code})')
                    time.sleep(10)
                    continue
                
                data = resp.json()
                if not data.get('items'):
                    print(f'[YOUTUBE] No active livestream')
                    time.sleep(10)
                    continue
                
                live_chat_id = data['items'][0]['snippet'].get('liveChatId')
                if not live_chat_id:
                    print(f'[YOUTUBE] No live chat ID')
                    time.sleep(10)
                    continue
                
                # Poll for new subscribers (every 5th poll to save quota)
                if not hasattr(poll_loop, 'poll_count'):
                    poll_loop.poll_count = 0
                poll_loop.poll_count += 1
                
                if poll_loop.poll_count % 5 == 0:
                    try:
                        sub_resp = requests.get(
                            'https://www.googleapis.com/youtube/v3/subscriptions',
                            params={'part': 'snippet', 'mySubscribers': 'true', 'maxResults': 50},
                            headers={'Authorization': f'Bearer {current_token}'},
                            timeout=5
                        )
                        
                        if sub_resp.status_code == 200:
                            sub_data = sub_resp.json()
                            known_subs = set(conn.metadata.get('yt_subscribers', []))
                            current_subs = {item['snippet']['channelId'] for item in sub_data.get('items', [])}
                            
                            new_subs = current_subs - known_subs
                            for item in sub_data.get('items', []):
                                if item['snippet']['channelId'] in new_subs:
                                    send_alert(user_id, 'subscribe', 'youtube', {
                                        'username': item['snippet']['title']
                                    })
                                    print(f'[YOUTUBE] New subscriber: {item["snippet"]["title"]}')
                            
                            conn.metadata['yt_subscribers'] = list(current_subs)
                            conn.save()
                    except Exception as e:
                        print(f'[YOUTUBE] Subscriber check error: {e}')
                
                # Get page token
                page_token = conn.metadata.get('yt_page_token')
                
                params = {
                    'liveChatId': live_chat_id,
                    'part': 'snippet,authorDetails',
                    'maxResults': 200
                }
                if page_token:
                    params['pageToken'] = page_token
                
                chat_resp = requests.get(
                    'https://www.googleapis.com/youtube/v3/liveChat/messages',
                    params=params,
                    headers={'Authorization': f'Bearer {current_token}'},
                    timeout=5
                )
                
                if chat_resp.status_code == 200:
                    chat_data = chat_resp.json()
                    
                    # Process messages
                    for msg in chat_data.get('items', []):
                        snippet = msg['snippet']
                        author = msg['authorDetails']['displayName']
                        
                        # Super Chat
                        if 'superChatDetails' in snippet:
                            details = snippet['superChatDetails']
                            send_alert(user_id, 'superchat', 'youtube', {
                                'username': author,
                                'amount': details['amountDisplayString']
                            })
                            print(f'[YOUTUBE] Super Chat: {author} - {details["amountDisplayString"]}')
                        
                        # Super Sticker
                        elif 'superStickerDetails' in snippet:
                            details = snippet['superStickerDetails']
                            send_alert(user_id, 'supersticker', 'youtube', {
                                'username': author,
                                'amount': details['amountDisplayString']
                            })
                            print(f'[YOUTUBE] Super Sticker: {author} - {details["amountDisplayString"]}')
                        
                        # New Member
                        elif 'newSponsorDetails' in snippet:
                            send_alert(user_id, 'member', 'youtube', {
                                'username': author
                            })
                            print(f'[YOUTUBE] New Member: {author}')
                        
                        # Member Milestone
                        elif 'memberMilestoneChatDetails' in snippet:
                            details = snippet['memberMilestoneChatDetails']
                            send_alert(user_id, 'milestone', 'youtube', {
                                'username': author,
                                'months': details.get('memberMonth', 0)
                            })
                            print(f'[YOUTUBE] Milestone: {author} - {details.get("memberMonth")}mo')
                        
                        # Member Gift
                        elif 'membershipGiftingDetails' in snippet:
                            send_alert(user_id, 'gift', 'youtube', {
                                'username': author
                            })
                            print(f'[YOUTUBE] Gift: {author}')
                    
                    # Save next page token and polling interval
                    conn.metadata['yt_page_token'] = chat_data.get('nextPageToken')
                    conn.save()
                    
                    # Use API-suggested polling interval (converted from ms to seconds)
                    poll_interval = chat_data.get('pollingIntervalMillis', 5000) / 1000
                    error_count = 0
                    
                else:
                    print(f'[YOUTUBE] Chat API error {chat_resp.status_code}')
                    poll_interval = 5
                    error_count += 1
                
            except PlatformConnection.DoesNotExist:
                print(f'[YOUTUBE] Connection not found for user {user_id}')
                break
            except Exception as e:
                print(f'[YOUTUBE] Error: {e}')
                poll_interval = 5
                error_count += 1
            
            if error_count >= max_errors:
                print(f'[YOUTUBE] Too many errors, stopping')
                with yt_poller_lock:
                    yt_pollers.pop(user_id, None)
                break
            
            time.sleep(poll_interval)
    
    thread = threading.Thread(target=poll_loop, daemon=True, name=f'youtube-{user_id}')
    thread.start()

def stop_youtube_listener(user_id):
    """Stop YouTube polling"""
    print(f'[YOUTUBE] Stopping polling for user {user_id}')
    
    with yt_poller_lock:
        if user_id in yt_pollers:
            yt_pollers[user_id]['active'] = False
        else:
            print(f'[YOUTUBE] No active poller for user {user_id}')