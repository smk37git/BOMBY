import time
import requests
import threading
from .twitch import send_alert

# Global dict to track active pollers
kick_pollers = {}
kick_poller_lock = threading.Lock()

def start_kick_listener(user_id, channel_slug):
    """Start 3-second polling for Kick channel"""
    print(f'[KICK] Starting 3s polling for {channel_slug} (user {user_id})')
    
    with kick_poller_lock:
        if channel_slug in kick_pollers:
            print(f'[KICK] Already polling {channel_slug}')
            return
        
        # Mark as active
        kick_pollers[channel_slug] = {'active': True, 'user_id': user_id}
    
    def poll_loop():
        last_followers = None
        last_subs = None
        error_count = 0
        max_errors = 5
        
        print(f'[KICK] ✓ Polling started for {channel_slug}')
        
        while True:
            # Check if still active
            with kick_poller_lock:
                if channel_slug not in kick_pollers or not kick_pollers[channel_slug]['active']:
                    print(f'[KICK] Polling stopped for {channel_slug}')
                    break
            
            try:
                # Poll Kick API
                resp = requests.get(
                    f'https://kick.com/api/v2/channels/{channel_slug}',
                    timeout=2,
                    headers={'User-Agent': 'FuzeOBS/1.0'}
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    
                    followers = data.get('followers_count', 0)
                    subs = data.get('subscribers_count', 0)
                    
                    # Initialize on first poll
                    if last_followers is None:
                        last_followers = followers
                        last_subs = subs
                        print(f'[KICK] Initialized - Followers: {followers}, Subs: {subs}')
                    else:
                        # Check for new followers
                        if followers > last_followers:
                            count = followers - last_followers
                            print(f'[KICK] ✓ New follower(s)! +{count} (now {followers})')
                            # Send one alert per new follower (max 5 to prevent spam)
                            for _ in range(min(count, 5)):
                                send_alert(user_id, 'follow', 'kick', {'username': 'Someone'})
                            last_followers = followers
                        
                        # Check for new subs
                        if subs > last_subs:
                            count = subs - last_subs
                            print(f'[KICK] ✓ New sub(s)! +{count} (now {subs})')
                            for _ in range(min(count, 5)):
                                send_alert(user_id, 'subscribe', 'kick', {'username': 'Someone'})
                            last_subs = subs
                    
                    # Reset error count on success
                    error_count = 0
                    
                elif resp.status_code == 404:
                    print(f'[KICK] ❌ Channel {channel_slug} not found')
                    break
                else:
                    print(f'[KICK] API error {resp.status_code} for {channel_slug}')
                    error_count += 1
                    
            except requests.Timeout:
                print(f'[KICK] Timeout polling {channel_slug}')
                error_count += 1
            except Exception as e:
                print(f'[KICK] Error polling {channel_slug}: {e}')
                error_count += 1
            
            # Stop if too many errors
            if error_count >= max_errors:
                print(f'[KICK] ❌ Too many errors, stopping polling for {channel_slug}')
                with kick_poller_lock:
                    kick_pollers.pop(channel_slug, None)
                break
            
            # Wait 3 seconds before next poll
            time.sleep(3)
    
    # Start polling thread
    thread = threading.Thread(target=poll_loop, daemon=True, name=f'kick-{channel_slug}')
    thread.start()

def stop_kick_listener(channel_slug):
    """Stop Kick polling"""
    print(f'[KICK] Stopping polling for {channel_slug}')
    
    with kick_poller_lock:
        if channel_slug in kick_pollers:
            kick_pollers[channel_slug]['active'] = False
            print(f'[KICK] ✓ Polling will stop for {channel_slug}')
        else:
            print(f'[KICK] No active poller for {channel_slug}')