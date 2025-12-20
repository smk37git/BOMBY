import time
import requests
import threading
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import PlatformConnection, WidgetConfig

# Track active chat pollers
fb_chat_pollers = {}
fb_chat_lock = threading.Lock()

def start_facebook_chat(user_id, page_id, access_token):
    """Start polling Facebook live video comments for chat"""
    print(f'[FB CHAT] Starting for page {page_id} (user {user_id})')
    
    with fb_chat_lock:
        if user_id in fb_chat_pollers:
            print(f'[FB CHAT] Already polling for user {user_id}')
            return True
        fb_chat_pollers[user_id] = {'active': True, 'page_id': page_id}
    
    def poll_loop():
        processed_comments = set()
        live_video_id = None
        error_count = 0
        max_errors = 10
        channel_layer = get_channel_layer()
        
        print(f'[FB CHAT] ✓ Polling started for page {page_id}')
        
        while True:
            with fb_chat_lock:
                if user_id not in fb_chat_pollers or not fb_chat_pollers[user_id]['active']:
                    print(f'[FB CHAT] Stopped for user {user_id}')
                    break
            
            try:
                # Check if chat widget is enabled
                has_enabled = WidgetConfig.objects.filter(
                    user_id=user_id,
                    widget_type='chat_box',
                    enabled=True
                ).exists()
                
                if not has_enabled:
                    time.sleep(5)
                    continue
                
                # Refresh token from DB
                conn = PlatformConnection.objects.get(user_id=user_id, platform='facebook')
                token = conn.access_token
                
                # Find active live video
                live_resp = requests.get(
                    f'https://graph.facebook.com/v18.0/{page_id}/live_videos',
                    params={
                        'access_token': token,
                        'fields': 'id,status',
                        'limit': 1
                    },
                    timeout=5
                )
                
                if live_resp.status_code != 200:
                    error_count += 1
                    time.sleep(5)
                    continue
                
                live_data = live_resp.json()
                active_streams = [v for v in live_data.get('data', []) if v.get('status') == 'LIVE']
                
                if not active_streams:
                    # Not live, wait longer
                    live_video_id = None
                    time.sleep(10)
                    continue
                
                current_video_id = active_streams[0]['id']
                
                # New stream? Reset processed comments
                if current_video_id != live_video_id:
                    live_video_id = current_video_id
                    processed_comments.clear()
                    print(f'[FB CHAT] Live stream: {live_video_id}')
                
                # Poll comments
                comments_resp = requests.get(
                    f'https://graph.facebook.com/v18.0/{live_video_id}/comments',
                    params={
                        'access_token': token,
                        'fields': 'id,from{id,name,picture},message,created_time',
                        'filter': 'stream',
                        'order': 'reverse_chronological',
                        'limit': 50
                    },
                    timeout=5
                )
                
                if comments_resp.status_code == 200:
                    comments = comments_resp.json().get('data', [])
                    
                    # Process newest first, but send in chronological order
                    new_comments = []
                    for comment in comments:
                        comment_id = comment['id']
                        if comment_id not in processed_comments:
                            processed_comments.add(comment_id)
                            new_comments.append(comment)
                    
                    # Send in chronological order (oldest first)
                    for comment in reversed(new_comments):
                        sender = comment.get('from', {})
                        username = sender.get('name', 'Anonymous')
                        message = comment.get('message', '')
                        
                        if not message.strip():
                            continue
                        
                        # Skip Stars system messages
                        if 'sent' in message.lower() and 'star' in message.lower():
                            continue
                        
                        print(f'[FB CHAT] {username}: {message[:50]}')
                        
                        async_to_sync(channel_layer.group_send)(
                            f'chat_{user_id}',
                            {
                                'type': 'chat_message',
                                'data': {
                                    'username': username,
                                    'message': message,
                                    'badges': [],
                                    'color': '#1877F2',
                                    'platform': 'facebook',
                                    'emotes': []
                                }
                            }
                        )
                    
                    error_count = 0
                else:
                    print(f'[FB CHAT] Comments API error {comments_resp.status_code}')
                    error_count += 1
                    
            except PlatformConnection.DoesNotExist:
                print(f'[FB CHAT] Connection deleted for user {user_id}')
                break
            except Exception as e:
                print(f'[FB CHAT] Error: {e}')
                error_count += 1
            
            if error_count >= max_errors:
                print(f'[FB CHAT] Too many errors, stopping')
                break
            
            # Poll every 3 seconds during live
            time.sleep(3)
        
        with fb_chat_lock:
            fb_chat_pollers.pop(user_id, None)
        print(f'[FB CHAT] Exited for user {user_id}')
    
    thread = threading.Thread(target=poll_loop, daemon=True, name=f'fb-chat-{user_id}')
    thread.start()
    return True

def stop_facebook_chat(user_id):
    """Stop Facebook chat polling"""
    print(f'[FB CHAT] Stopping for user {user_id}')
    
    with fb_chat_lock:
        if user_id in fb_chat_pollers:
            fb_chat_pollers[user_id]['active'] = False
            return True
    return False