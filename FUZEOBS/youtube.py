import requests
import time
import threading
from .twitch import send_alert
from .models import PlatformConnection

yt_pollers = {}
yt_poller_lock = threading.Lock()

def start_youtube_listener(user_id, access_token):
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
        subscriber_check_counter = 0
        
        while True:
            with yt_poller_lock:
                if user_id not in yt_pollers or not yt_pollers[user_id]['active']:
                    break
            
            try:
                conn = PlatformConnection.objects.get(user_id=user_id, platform='youtube')
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
                    consecutive_not_live += 1
                    if consecutive_not_live >= 5:
                        break
                    time.sleep(poll_interval)
                    continue
                
                # Find active broadcast
                items = resp.json().get('items', [])
                active_broadcast = None
                for item in items:
                    if 'liveChatId' in item['snippet']:
                        active_broadcast = item
                        break
                
                if not active_broadcast:
                    consecutive_not_live += 1
                    print(f'[YOUTUBE] No active broadcast ({consecutive_not_live}/10)')
                    if consecutive_not_live >= 10:
                        break
                    time.sleep(poll_interval)
                    continue
                
                consecutive_not_live = 0
                live_chat_id = active_broadcast['snippet']['liveChatId']
                
                # Check subscribers every 6 polls (~60 seconds)
                subscriber_check_counter += 1
                if subscriber_check_counter >= 6:
                    subscriber_check_counter = 0
                    try:
                        sub_resp = requests.get(
                            'https://www.googleapis.com/youtube/v3/subscriptions',
                            params={'part': 'snippet', 'myRecentSubscribers': 'true', 'maxResults': 50},
                            headers={'Authorization': f'Bearer {token}'},
                            timeout=10
                        )
                        
                        if sub_resp.status_code == 200:
                            sub_data = sub_resp.json()
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
                                        send_alert(user_id, 'subscribe', 'youtube', {
                                            'username': item['snippet']['title']
                                        })
                                        print(f'[YOUTUBE] New sub: {item["snippet"]["title"]}')
                                
                                conn.metadata['yt_subscribers'] = list(current_subs)
                                conn.save()
                        else:
                            print(f'[YOUTUBE] Subscription API error {sub_resp.status_code}')
                    except Exception as e:
                        print(f'[YOUTUBE] Subscriber check failed: {e}')
                
                # Poll live chat (SuperChats, Members)
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
                        
                        # SuperChat
                        if 'superChatDetails' in snippet:
                            send_alert(user_id, 'superchat', 'youtube', {
                                'username': author,
                                'amount': snippet['superChatDetails']['amountDisplayString']
                            })
                            print(f'[YOUTUBE] SuperChat: {author}')
                        
                        # New Member
                        elif 'newSponsorDetails' in snippet:
                            send_alert(user_id, 'member', 'youtube', {
                                'username': author
                            })
                            print(f'[YOUTUBE] New member: {author}')
                    
                    conn.metadata['yt_page_token'] = data.get('nextPageToken')
                    conn.save()
                    poll_interval = data.get('pollingIntervalMillis', 5000) / 1000
                    error_count = 0
                else:
                    print(f'[YOUTUBE] Chat API error {chat_resp.status_code}')
                    error_count += 1
                    
            except PlatformConnection.DoesNotExist:
                print(f'[YOUTUBE] Connection deleted')
                break
            except Exception as e:
                print(f'[YOUTUBE] Error: {e}')
                error_count += 1
            
            if error_count >= 10:
                print(f'[YOUTUBE] Too many errors, stopping')
                break
            
            time.sleep(poll_interval)
        
        with yt_poller_lock:
            yt_pollers.pop(user_id, None)
        print(f'[YOUTUBE] Listener stopped for user {user_id}')
    
    thread = threading.Thread(target=poll_loop, daemon=True, name=f'yt-{user_id}')
    thread.start()
    return True

def stop_youtube_listener(user_id):
    print(f'[YOUTUBE] Stopping for user {user_id}')
    with yt_poller_lock:
        if user_id in yt_pollers:
            yt_pollers[user_id]['active'] = False