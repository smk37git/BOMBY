import json
import websocket
import threading
from .twitch import send_alert

# Global dict to track active listeners
kick_listeners = {}

def start_kick_listener(user_id, channel_slug):
    """Start real-time Kick listener via Pusher WebSocket"""
    if channel_slug in kick_listeners:
        return  # Already listening
    
    def on_message(ws, message):
        try:
            data = json.loads(message)
            event = data.get('event')
            
            if event == 'App\\Events\\FollowersUpdated':
                send_alert(user_id, 'follow', 'kick', {'username': 'Someone'})
            elif event == 'App\\Events\\SubscriptionEvent':
                payload = json.loads(data.get('data', '{}'))
                send_alert(user_id, 'subscribe', 'kick', {
                    'username': payload.get('username', 'Someone')
                })
        except Exception as e:
            print(f'[KICK WS ERROR] {e}')
    
    def on_open(ws):
        # Subscribe to channel
        ws.send(json.dumps({
            'event': 'pusher:subscribe',
            'data': {'channel': f'channel.{channel_slug}'}
        }))
        print(f'[KICK] Listening to {channel_slug}')
    
    def on_error(ws, error):
        print(f'[KICK WS ERROR] {error}')
    
    def on_close(ws, close_status_code, close_msg):
        print(f'[KICK] Disconnected from {channel_slug}')
        kick_listeners.pop(channel_slug, None)
    
    def run_ws():
        ws = websocket.WebSocketApp(
            'wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c?protocol=7&client=js&version=7.0.0',
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        kick_listeners[channel_slug] = ws
        ws.run_forever()
    
    thread = threading.Thread(target=run_ws, daemon=True)
    thread.start()

def stop_kick_listener(channel_slug):
    """Stop Kick listener"""
    ws = kick_listeners.pop(channel_slug, None)
    if ws:
        ws.close()