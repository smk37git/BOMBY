import time
import requests
import threading
from .twitch import send_alert
from .models import PlatformConnection

# Global dict to track active pollers
fb_pollers = {}
fb_poller_lock = threading.Lock()

def start_facebook_listener(user_id, page_id, access_token):
    """Start 5-second polling for Facebook Page during live stream"""
    print(f'[FACEBOOK] Starting polling for page {page_id} (user {user_id})')
    
    with fb_poller_lock:
        if page_id in fb_pollers:
            print(f'[FACEBOOK] Already polling {page_id}')
            return True
        
        fb_pollers[page_id] = {'active': True, 'user_id': user_id}
    
    def poll_loop():
        last_followers = None
        last_stars_total = 0
        processed_comments = set()
        live_video_id = None
        error_count = 0
        max_errors = 5
        
        print(f'[FACEBOOK] ✓ Polling started for page {page_id}')
        
        while True:
            with fb_poller_lock:
                if page_id not in fb_pollers or not fb_pollers[page_id]['active']:
                    print(f'[FACEBOOK] Polling stopped for {page_id}')
                    break
            
            try:
                # Refresh access token from DB
                conn = PlatformConnection.objects.get(user_id=user_id, platform='facebook')
                current_token = conn.access_token
                
                # Check for live videos
                live_resp = requests.get(
                    f'https://graph.facebook.com/v18.0/{page_id}/live_videos',
                    params={
                        'access_token': current_token,
                        'fields': 'id,status',
                        'limit': 1
                    },
                    timeout=3
                )
                
                if live_resp.status_code == 200:
                    live_data = live_resp.json()
                    active_streams = [v for v in live_data.get('data', []) if v.get('status') == 'LIVE']
                    
                    if active_streams:
                        live_video_id = active_streams[0]['id']
                        print(f'[FACEBOOK] Live stream detected: {live_video_id}')
                        
                        # Poll live video comments for Stars
                        comments_resp = requests.get(
                            f'https://graph.facebook.com/v18.0/{live_video_id}/comments',
                            params={
                                'access_token': current_token,
                                'fields': 'id,from,message,created_time',
                                'filter': 'stream',
                                'limit': 50
                            },
                            timeout=3
                        )
                        
                        if comments_resp.status_code == 200:
                            comments = comments_resp.json().get('data', [])
                            
                            for comment in comments:
                                comment_id = comment['id']
                                if comment_id not in processed_comments:
                                    processed_comments.add(comment_id)
                                    message = comment.get('message', '')
                                    username = comment.get('from', {}).get('name', 'Someone')
                                    
                                    # Check for Facebook Stars in comment
                                    if 'sent' in message.lower() and 'star' in message.lower():
                                        # Parse star count from message (format: "sent X Stars")
                                        import re
                                        star_match = re.search(r'(\d+)\s*[Ss]tar', message)
                                        if star_match:
                                            star_count = star_match.group(1)
                                            send_alert(user_id, 'stars', 'facebook', {
                                                'username': username,
                                                'amount': star_count
                                            })
                                            print(f'[FACEBOOK] ✓ Stars! {username} sent {star_count} Stars')
                    else:
                        live_video_id = None
                
                # Poll follower count
                page_resp = requests.get(
                    f'https://graph.facebook.com/v18.0/{page_id}',
                    params={
                        'access_token': current_token,
                        'fields': 'followers_count'
                    },
                    timeout=3
                )
                
                if page_resp.status_code == 200:
                    page_data = page_resp.json()
                    followers = page_data.get('followers_count', 0)
                    
                    if last_followers is None:
                        last_followers = followers
                        print(f'[FACEBOOK] Initialized - Followers: {followers}')
                    elif followers > last_followers:
                        count = followers - last_followers
                        print(f'[FACEBOOK] ✓ New follower(s)! +{count} (now {followers})')
                        for _ in range(min(count, 5)):
                            send_alert(user_id, 'follow', 'facebook', {'username': 'Someone'})
                        last_followers = followers
                    
                    error_count = 0
                    
                elif page_resp.status_code == 404:
                    print(f'[FACEBOOK] ✗ Page {page_id} not found')
                    break
                else:
                    print(f'[FACEBOOK] API error {page_resp.status_code}')
                    error_count += 1
                    
            except PlatformConnection.DoesNotExist:
                print(f'[FACEBOOK] Connection not found for user {user_id}')
                break
            except requests.Timeout:
                print(f'[FACEBOOK] Timeout polling {page_id}')
                error_count += 1
            except Exception as e:
                print(f'[FACEBOOK] Error polling {page_id}: {e}')
                error_count += 1
            
            if error_count >= max_errors:
                print(f'[FACEBOOK] ✗ Too many errors, stopping polling for {page_id}')
                with fb_poller_lock:
                    fb_pollers.pop(page_id, None)
                break
            
            time.sleep(5)
        
        with fb_poller_lock:
            fb_pollers.pop(page_id, None)
        print(f'[FACEBOOK] Listener exited for page {page_id}')
    
    thread = threading.Thread(target=poll_loop, daemon=True, name=f'facebook-{page_id}')
    thread.start()
    return True

def stop_facebook_listener(page_id):
    """Stop Facebook polling"""
    print(f'[FACEBOOK] Stopping polling for {page_id}')
    
    with fb_poller_lock:
        if page_id in fb_pollers:
            fb_pollers[page_id]['active'] = False
            print(f'[FACEBOOK] ✓ Polling will stop for {page_id}')
        else:
            print(f'[FACEBOOK] No active poller for {page_id}')