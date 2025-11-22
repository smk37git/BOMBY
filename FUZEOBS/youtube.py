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
    """Start polling YouTube - force start regardless of live status check"""
    print(f'[YOUTUBE] Starting listener for user {user_id}')
    
    with yt_poller_lock:
        if user_id in yt_pollers:
            print(f'[YOUTUBE] Already polling')
            return True
        yt_pollers[user_id] = {'active': True}
    
    def poll_loop():
        error_count = 0
        consecutive_not_live = 0
        poll_interval = 10
        
        while True:
            with yt_poller_lock:
                if user_id not in yt_pollers or not yt_pollers[user_id]['active']:
                    break
            
            try:
                conn = PlatformConnection.objects.get(user_id=user_id, platform='youtube')
                token = conn.access_token
                
                # Check broadcasts with multiple statuses
                resp = requests.get(
                    'https://www.googleapis.com/youtube/v3/liveBroadcasts',
                    params={'part': 'snippet,contentDetails', 'broadcastType': 'all', 'mine': 'true', 'maxResults': 5},
                    headers={'Authorization': f'Bearer {token}'},
                    timeout=10
                )
                
                if resp.status_code != 200:
                    print(f'[YOUTUBE] API error {resp.status_code}: {resp.text}')
                    consecutive_not_live += 1
                    if consecutive_not_live >= 5:
                        print(f'[YOUTUBE] Stopping - API issues')
                        break
                    time.sleep(poll_interval)
                    continue
                
                items = resp.json().get('items', [])
                active_broadcast = None
                
                for item in items:
                    status = item['snippet']['liveChatId'] if 'liveChatId' in item['snippet'] else None
                    if status:
                        active_broadcast = item
                        break
                
                if not active_broadcast:
                    consecutive_not_live += 1
                    print(f'[YOUTUBE] No active broadcast ({consecutive_not_live}/10)')
                    if consecutive_not_live >= 10:
                        print(f'[YOUTUBE] Stopping - not live')
                        break
                    time.sleep(poll_interval)
                    continue
                
                consecutive_not_live = 0
                live_chat_id = active_broadcast['snippet']['liveChatId']
                
                # Poll chat messages
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
                    headers={'Authorization': f'Bearer {token}'},
                    timeout=10
                )
                
                if chat_resp.status_code == 200:
                    data = chat_resp.json()
                    
                    for msg in data.get('items', []):
                        snippet = msg['snippet']
                        author = msg['authorDetails']['displayName']
                        
                        if 'superChatDetails' in snippet:
                            send_alert(user_id, 'superchat', 'youtube', {
                                'username': author,
                                'amount': snippet['superChatDetails']['amountDisplayString']
                            })
                        elif 'newSponsorDetails' in snippet:
                            send_alert(user_id, 'member', 'youtube', {'username': author})
                    
                    conn.metadata['yt_page_token'] = data.get('nextPageToken')
                    conn.save()
                    poll_interval = data.get('pollingIntervalMillis', 5000) / 1000
                    error_count = 0
                else:
                    error_count += 1
                    
            except Exception as e:
                print(f'[YOUTUBE] Error: {e}')
                error_count += 1
            
            if error_count >= 10:
                print(f'[YOUTUBE] Too many errors')
                break
            
            time.sleep(poll_interval)
        
        with yt_poller_lock:
            yt_pollers.pop(user_id, None)
    
    thread = threading.Thread(target=poll_loop, daemon=True, name=f'yt-{user_id}')
    thread.start()
    return True

def stop_youtube_listener(user_id):
    """Stop YouTube polling"""
    print(f'[YOUTUBE] Stopping polling for user {user_id}')
    
    with yt_poller_lock:
        if user_id in yt_pollers:
            yt_pollers[user_id]['active'] = False
        else:
            print(f'[YOUTUBE] No active poller for user {user_id}')