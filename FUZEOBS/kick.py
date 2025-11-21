import json
import websocket
import threading
import time
from .twitch import send_alert

# Global dict to track active listeners
kick_listeners = {}
# Cache the working Pusher cluster
_cached_cluster = None
_cluster_lock = threading.Lock()

PUSHER_KEY = 'eb1d5f283081a78b932c'
PUSHER_CLUSTERS = ['mt1', 'us2', 'us3', 'eu', 'ap1', 'ap2', 'ap3', 'ap4']

def detect_kick_cluster():
    """Auto-detect working Kick Pusher cluster"""
    global _cached_cluster
    
    with _cluster_lock:
        if _cached_cluster:
            print(f'[KICK] Using cached cluster: {_cached_cluster}')
            return _cached_cluster
        
        print(f'[KICK] Detecting Pusher cluster...')
        
        for cluster in PUSHER_CLUSTERS:
            try:
                url = f'wss://ws-{cluster}.pusher.com/app/{PUSHER_KEY}?protocol=7&client=js&version=8.4.0-rc2'
                print(f'[KICK] Testing cluster: {cluster}')
                
                ws = websocket.create_connection(url, timeout=3)
                
                # Send test subscribe
                ws.send(json.dumps({
                    'event': 'pusher:subscribe',
                    'data': {'channel': 'test-channel'}
                }))
                
                # Wait for response
                response = ws.recv()
                ws.close()
                
                data = json.loads(response)
                
                # Check if we got an error about cluster
                if data.get('event') == 'pusher:error':
                    error_code = data.get('data', {}).get('code')
                    if error_code == 4001:  # Wrong cluster
                        print(f'[KICK] ✗ Cluster {cluster} wrong')
                        continue
                
                # No cluster error = correct cluster!
                print(f'[KICK] ✓ Found working cluster: {cluster}')
                _cached_cluster = cluster
                return cluster
                
            except Exception as e:
                print(f'[KICK] ✗ Cluster {cluster} failed: {e}')
                continue
        
        print(f'[KICK] ❌ No working cluster found, using mt1 as fallback')
        _cached_cluster = 'mt1'
        return 'mt1'

def start_kick_listener(user_id, channel_slug):
    """Start real-time Kick listener via Pusher WebSocket"""
    print(f'[KICK] ========== START LISTENER ==========')
    print(f'[KICK] user_id={user_id}, channel={channel_slug}')
    
    if channel_slug in kick_listeners:
        print(f'[KICK] Already listening to {channel_slug}')
        return
    
    # Detect cluster first
    cluster = detect_kick_cluster()
    ws_url = f'wss://ws-{cluster}.pusher.com/app/{PUSHER_KEY}?protocol=7&client=js&version=8.4.0-rc2'
    
    def on_message(ws, message):
        try:
            print(f'[KICK] ===== MESSAGE RECEIVED =====')
            data = json.loads(message)
            event = data.get('event')
            print(f'[KICK] Event: {event}')
            
            # Handle connection established
            if event == 'pusher:connection_established':
                print(f'[KICK] ✓ Connection established')
                return
            
            # Handle subscription success
            if event == 'pusher_internal:subscription_succeeded':
                print(f'[KICK] ✓ Subscribed to channel')
                return
            
            # Handle errors
            if event == 'pusher:error':
                error_data = data.get('data', {})
                print(f'[KICK] ❌ Error: {error_data}')
                # If cluster error, clear cache and reconnect
                if error_data.get('code') == 4001:
                    global _cached_cluster
                    _cached_cluster = None
                    print(f'[KICK] Cluster cache cleared, will retry')
                return
            
            # Handle follow events
            if event == 'App\\Events\\FollowersUpdated':
                print(f'[KICK] ✓ FOLLOW EVENT for user {user_id}')
                send_alert(user_id, 'follow', 'kick', {'username': 'Someone'})
                return
            
            # Handle subscription events
            if event == 'App\\Events\\SubscriptionEvent':
                print(f'[KICK] ✓ SUB EVENT for user {user_id}')
                event_data = json.loads(data.get('data', '{}'))
                send_alert(user_id, 'subscribe', 'kick', {
                    'username': event_data.get('username', 'Someone')
                })
                return
            
            # Log other events for debugging
            print(f'[KICK] ℹ Other event: {event}')
            print(f'[KICK] Data: {json.dumps(data, indent=2)[:300]}')
            
        except Exception as e:
            print(f'[KICK] ❌ Message error: {e}')
            import traceback
            traceback.print_exc()
    
    def on_open(ws):
        channel_name = f'channel.{channel_slug}'
        print(f'[KICK] ========== CONNECTED ==========')
        print(f'[KICK] Cluster: {cluster}')
        print(f'[KICK] Subscribing to: {channel_name}')
        
        subscribe_msg = json.dumps({
            'event': 'pusher:subscribe',
            'data': {'channel': channel_name}
        })
        ws.send(subscribe_msg)
        print(f'[KICK] ✓ Subscribe sent')
    
    def on_error(ws, error):
        print(f'[KICK] ❌ WebSocket error: {error}')
    
    def on_close(ws, close_status_code, close_msg):
        print(f'[KICK] ========== DISCONNECTED ==========')
        print(f'[KICK] Channel: {channel_slug}')
        print(f'[KICK] Status: {close_status_code}, Msg: {close_msg}')
        kick_listeners.pop(channel_slug, None)
    
    def run_ws():
        print(f'[KICK] Connecting to: {ws_url}')
        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        kick_listeners[channel_slug] = ws
        print(f'[KICK] Starting WebSocket...')
        ws.run_forever()
        print(f'[KICK] WebSocket ended')
    
    thread = threading.Thread(target=run_ws, daemon=True)
    thread.start()
    print(f'[KICK] ✓ Thread started for {channel_slug}')

def stop_kick_listener(channel_slug):
    """Stop Kick listener"""
    print(f'[KICK] ========== STOP LISTENER ==========')
    print(f'[KICK] Channel: {channel_slug}')
    ws = kick_listeners.pop(channel_slug, None)
    if ws:
        ws.close()
        print(f'[KICK] ✓ Listener stopped')
    else:
        print(f'[KICK] No listener found for {channel_slug}')