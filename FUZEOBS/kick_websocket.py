import asyncio
import websockets
import json
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings

def send_alert(user_id, event_type, platform, event_data):
    """Send alert to platform-specific widget WebSocket"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'alerts_{user_id}_{platform}',
        {
            'type': 'alert_event',
            'data': {
                'event_type': event_type,
                'platform': platform,
                'event_data': event_data
            }
        }
    )

async def connect_kick_websocket(channel_id, user_id):
    """Connect to Kick's public WebSocket for channel events"""
    uri = "wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c?protocol=7&client=js&version=7.6.0&flash=false"
    
    async with websockets.connect(uri) as websocket:
        # Subscribe to channel events
        subscribe_msg = {
            "event": "pusher:subscribe",
            "data": {
                "auth": "",
                "channel": f"channel.{channel_id}"
            }
        }
        await websocket.send(json.dumps(subscribe_msg))
        
        # Listen for events
        async for message in websocket:
            try:
                data = json.loads(message)
                event_name = data.get('event', '')
                
                if event_name == 'App\\Events\\FollowersUpdated':
                    event_data = json.loads(data.get('data', '{}'))
                    send_alert(user_id, 'follow', 'kick', {
                        'username': event_data.get('username', 'Someone'),
                        'followed_at': event_data.get('followed_at')
                    })
                
                elif event_name == 'App\\Events\\SubscriptionEvent':
                    event_data = json.loads(data.get('data', '{}'))
                    send_alert(user_id, 'subscribe', 'kick', {
                        'username': event_data.get('username', 'Someone'),
                        'months': event_data.get('months', 1)
                    })
                
                elif event_name == 'App\\Events\\GiftedSubscriptionsEvent':
                    event_data = json.loads(data.get('data', '{}'))
                    send_alert(user_id, 'gift_sub', 'kick', {
                        'username': event_data.get('gifter_username', 'Someone'),
                        'gift_count': event_data.get('gifted_usernames', [])
                    })
                
                elif event_name == 'App\\Events\\ChatMessageEvent':
                    event_data = json.loads(data.get('data', '{}'))
                    # Check if it's a tip/donation in the message
                    if event_data.get('type') == 'tip':
                        send_alert(user_id, 'tip', 'kick', {
                            'username': event_data.get('sender', {}).get('username', 'Someone'),
                            'amount': event_data.get('amount', 0)
                        })
                
            except Exception as e:
                print(f'[KICK] Error processing message: {e}')
                continue

def start_kick_listener(channel_id, user_id):
    """Start Kick WebSocket listener in background"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(connect_kick_websocket(channel_id, user_id))
    except Exception as e:
        print(f'[KICK] Connection error: {e}')
    finally:
        loop.close()