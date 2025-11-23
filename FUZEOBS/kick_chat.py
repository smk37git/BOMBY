import asyncio
import websockets
import json
import requests
from channels.layers import get_channel_layer

active_kick_chats = {}

async def kick_chat_connect(channel_slug, user_id):
    """Connect to Kick chat via Pusher WebSocket"""
    
    # Get chatroom ID from Kick API
    try:
        resp = requests.get(f'https://kick.com/api/v2/channels/{channel_slug}', timeout=5)
        if resp.status_code != 200:
            print(f'[KICK CHAT] Channel {channel_slug} not found')
            return
        
        data = resp.json()
        chatroom_id = data.get('chatroom', {}).get('id')
        if not chatroom_id:
            print(f'[KICK CHAT] No chatroom for {channel_slug}')
            return
            
    except Exception as e:
        print(f'[KICK CHAT] API error: {e}')
        return
    
    # Connect to Pusher WebSocket
    uri = "wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c?protocol=7&client=js&version=8.4.0-rc2&flash=false"
    
    try:
        async with websockets.connect(uri) as ws:
            # Subscribe to chatroom
            subscribe_msg = {
                "event": "pusher:subscribe",
                "data": {
                    "channel": f"chatrooms.{chatroom_id}.v2",
                    "auth": ""
                }
            }
            await ws.send(json.dumps(subscribe_msg))
            print(f'[KICK CHAT] Connected to {channel_slug} (room {chatroom_id})')
            
            channel_layer = get_channel_layer()
            
            while True:
                try:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    # Handle chat messages
                    if data.get('event') == 'App\\Events\\ChatMessageEvent':
                        message_data = json.loads(data.get('data', '{}'))
                        sender = message_data.get('sender', {})
                        
                        username = sender.get('username', 'Unknown')
                        content = message_data.get('content', '')
                        
                        # Get color from identity
                        identity = sender.get('identity', {})
                        color = identity.get('color') or '#FFFFFF'
                        
                        # Get badges
                        badges = []
                        if message_data.get('sender', {}).get('identity', {}).get('badges'):
                            badge_list = message_data['sender']['identity']['badges']
                            badges = [b['type'] for b in badge_list if 'type' in b]
                        
                        # Send to WebSocket
                        await channel_layer.group_send(
                            f'chat_{user_id}',
                            {
                                'type': 'chat_message',
                                'data': {
                                    'username': username,
                                    'message': content,
                                    'badges': badges,
                                    'color': color,
                                    'platform': 'kick'
                                }
                            }
                        )
                        
                except websockets.exceptions.ConnectionClosed:
                    print(f'[KICK CHAT] Connection closed for {channel_slug}')
                    break
                except Exception as e:
                    print(f'[KICK CHAT] Error: {e}')
                    break
                    
    except Exception as e:
        print(f'[KICK CHAT] Connection error: {e}')

def start_kick_chat(channel_slug, user_id):
    """Start Kick chat in background thread"""
    if user_id in active_kick_chats:
        return False
    
    loop = asyncio.new_event_loop()
    
    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(kick_chat_connect(channel_slug, user_id))
    
    import threading
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    
    active_kick_chats[user_id] = thread
    return True

def stop_kick_chat(user_id):
    """Stop Kick chat"""
    if user_id in active_kick_chats:
        del active_kick_chats[user_id]
        return True
    return False