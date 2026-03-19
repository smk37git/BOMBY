"""Facebook chat polling"""
import time
import requests

from .chat_base import ChatRegistry, is_chat_enabled, send_chat_message, start_chat_thread
from .models import PlatformConnection

fb_chat = ChatRegistry('FB CHAT')


def _poll_loop(user_id: int, page_id: str):
    """Main polling loop for Facebook chat"""
    processed_comments = set()
    live_video_id = None
    error_count = 0
    
    print(f'[FB CHAT] ✓ Polling started for page {page_id}')
    
    while fb_chat.is_active(user_id):
        try:
            if not is_chat_enabled(user_id):
                time.sleep(5)
                continue
            
            # Refresh token from DB
            try:
                conn = PlatformConnection.objects.get(user_id=user_id, platform='facebook')
            except PlatformConnection.DoesNotExist:
                print(f'[FB CHAT] Connection deleted for user {user_id}')
                break
            
            token = conn.access_token
            
            # Find active live video
            live_resp = requests.get(
                f'https://graph.facebook.com/v18.0/{page_id}/live_videos',
                params={'access_token': token, 'fields': 'id,status', 'limit': 1},
                timeout=5
            )
            
            if live_resp.status_code != 200:
                error_count += 1
                if error_count >= 10:
                    print(f'[FB CHAT] Too many errors, stopping')
                    break
                time.sleep(5)
                continue
            
            live_data = live_resp.json()
            active_streams = [v for v in live_data.get('data', []) if v.get('status') == 'LIVE']
            
            if not active_streams:
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
                new_comments = [c for c in comments if c['id'] not in processed_comments]
                
                for comment in new_comments:
                    processed_comments.add(comment['id'])
                
                # Send in chronological order (oldest first)
                for comment in reversed(new_comments):
                    username = comment.get('from', {}).get('name', 'Anonymous')
                    message = comment.get('message', '')
                    
                    if not message.strip():
                        continue
                    
                    # Skip Stars system messages
                    if 'sent' in message.lower() and 'star' in message.lower():
                        continue
                    
                    print(f'[FB CHAT] {username}: {message[:50]}')
                    send_chat_message(user_id, username, message, 'facebook', color='#1877F2')
                
                error_count = 0
            else:
                print(f'[FB CHAT] Comments API error {comments_resp.status_code}')
                error_count += 1
                
        except Exception as e:
            print(f'[FB CHAT] Error: {e}')
            error_count += 1
        
        if error_count >= 10:
            print(f'[FB CHAT] Too many errors, stopping')
            break
        
        time.sleep(3)
    
    fb_chat.unregister(user_id)
    print(f'[FB CHAT] Exited for user {user_id}')


def start_facebook_chat(user_id: int, page_id: str, access_token: str) -> bool:
    """Start polling Facebook live video comments for chat"""
    print(f'[FB CHAT] Starting for page {page_id} (user {user_id})')
    
    if not fb_chat.register(user_id, {'active': True, 'page_id': page_id}):
        return True  # Already running
    
    start_chat_thread('fb-chat', _poll_loop, user_id, page_id)
    return True


def stop_facebook_chat(user_id: int) -> bool:
    """Stop Facebook chat polling"""
    print(f'[FB CHAT] Stopping for user {user_id}')
    return fb_chat.stop(user_id)