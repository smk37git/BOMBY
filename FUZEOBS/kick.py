import json
import websocket
import threading
from .twitch import send_alert

# Global dict to track active listeners
kick_listeners = {}

def start_kick_listener(user_id, channel_slug):
    """Start real-time Kick listener via Pusher WebSocket"""
    print(f'[KICK] ========== START LISTENER ==========')
    print(f'[KICK] user_id={user_id}, channel={channel_slug}')
    
    if channel_slug in kick_listeners:
        print(f'[KICK] Already listening to {channel_slug}')
        return
    
    def on_message(ws, message):
        try:
            print(f'[KICK] ===== MESSAGE RECEIVED =====')
            print(f'[KICK] Raw: {message[:200]}...')  # First 200 chars
            data = json.loads(message)
            event = data.get('event')
            print(f'[KICK] Event type: {event}')
            print(f'[KICK] Full data: {json.dumps(data, indent=2)[:500]}')
            
            if event == 'App\\Events\\FollowersUpdated':
                print(f'[KICK] ✓ FOLLOW EVENT for user {user_id}')
                send_alert(user_id, 'follow', 'kick', {'username': 'Someone'})
            elif event == 'App\\Events\\SubscriptionEvent':
                print(f'[KICK] ✓ SUB EVENT for user {user_id}')
                payload = json.loads(data.get('data', '{}'))
                send_alert(user_id, 'subscribe', 'kick', {
                    'username': payload.get('username', 'Someone')
                })
            else:
                print(f'[KICK] ℹ Other event: {event}')
        except Exception as e:
            print(f'[KICK WS ERROR] {e}')
            import traceback
            traceback.print_exc()
    
    def on_open(ws):
        channel_name = f'channel.{channel_slug}'
        print(f'[KICK] ========== CONNECTED ==========')
        print(f'[KICK] Subscribing to: {channel_name}')
        subscribe_msg = json.dumps({
            'event': 'pusher:subscribe',
            'data': {'channel': channel_name}
        })
        print(f'[KICK] Sending: {subscribe_msg}')
        ws.send(subscribe_msg)
        print(f'[KICK] ✓ Subscribe sent')
    
    def on_error(ws, error):
        print(f'[KICK WS ERROR] ❌ {error}')
        import traceback
        traceback.print_exc()
    
    def on_close(ws, close_status_code, close_msg):
        print(f'[KICK] ========== DISCONNECTED ==========')
        print(f'[KICK] Channel: {channel_slug}')
        print(f'[KICK] Status: {close_status_code}, Msg: {close_msg}')
        kick_listeners.pop(channel_slug, None)
    
    def run_ws():
        ws_url = 'wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c?protocol=7&client=js&version=7.0.0'
        print(f'[KICK] Creating WebSocket to: {ws_url}')
        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        kick_listeners[channel_slug] = ws
        print(f'[KICK] Starting WebSocket run_forever()...')
        ws.run_forever()
        print(f'[KICK] WebSocket run_forever() ended')
    
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