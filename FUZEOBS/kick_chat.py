import asyncio
import websockets
import json
import requests
from channels.layers import get_channel_layer

active_kick_chats = {}

async def kick_chat_connect(channel_slug, user_id, access_token):
    """Connect to Kick chat via Pusher WebSocket with OAuth"""
    
    # Get chatroom ID from Kick API
    try:
        resp = requests.get(
            f'https://kick.com/api/v2/channels/{channel_slug}', 
            timeout=5,
            headers={
                'User-Agent': 'FuzeOBS/1.0',
                'Authorization': f'Bearer {access_token}'
            }
        )
        if resp.status_code != 200:
            print(f'[KICK CHAT] Channel {channel_slug} not found (status {resp.status_code})')
            return
        
        data = resp.json()
        chatroom_id = data.get('chatroom', {}).get('id')
        if not chatroom_id:
            print(f'[KICK CHAT] No chatroom for {channel_slug}')
            return
            
    except Exception as e:
        print(f'[KICK CHAT] API error: {e}')
        return
    
    # Get Pusher auth from Kick
    socket_id = None
    pusher_auth = None
    
    # Connect to Pusher WebSocket
    uri = "wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c?protocol=7&client=js&version=8.4.0-rc2&flash=false"
    
    try:
        async with websockets.connect(uri) as ws:
            # Wait for connection established to get socket_id
            msg = await ws.recv()
            data = json.loads(msg)
            if data.get('event') == 'pusher:connection_established':
                connection_data = json.loads(data['data'])
                socket_id = connection_data['socket_id']
                print(f'[KICK CHAT] Got socket_id: {socket_id}')
            
            # Get auth signature from Kick
            try:
                auth_resp = requests.post(
                    'https://kick.com/broadcasting/auth',
                    json={
                        'socket_id': socket_id,
                        'channel_name': f'chatrooms.{chatroom_id}.v2'
                    },
                    headers={
                        'Authorization': f'Bearer {access_token}',
                        'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Origin': 'https://kick.com',
                        'Referer': f'https://kick.com/{channel_slug}'
                    },
                    timeout=5
                )
                if auth_resp.status_code == 200:
                    auth_data = auth_resp.json()
                    pusher_auth = auth_data.get('auth')
                    print(f'[KICK CHAT] Got Pusher auth')
                else:
                    print(f'[KICK CHAT] Auth failed: {auth_resp.status_code} - {auth_resp.text}')
                    return
            except Exception as e:
                print(f'[KICK CHAT] Auth request error: {e}')
                return
            
            # Subscribe to chatroom with auth
            subscribe_msg = {
                "event": "pusher:subscribe",
                "data": {
                    "channel": f"chatrooms.{chatroom_id}.v2",
                    "auth": pusher_auth
                }
            }
            await ws.send(json.dumps(subscribe_msg))
            print(f'[KICK CHAT] Connected to {channel_slug} (room {chatroom_id})')
            
            channel_layer = get_channel_layer()
            
            while True:
                try:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    
                    # Handle Pusher ping/pong
                    if data.get('event') == 'pusher:ping':
                        await ws.send(json.dumps({'event': 'pusher:pong', 'data': {}}))
                        print(f'[KICK CHAT] Pong sent')
                        continue
                    
                    # Check for subscription success
                    if data.get('event') == 'pusher_internal:subscription_succeeded':
                        print(f'[KICK CHAT] ✓ Subscription successful!')
                        continue
                    
                    # Handle chat messages
                    if data.get('event') == 'App\\Events\\ChatMessageEvent':
                        print(f'[KICK CHAT] Message received')
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
                        
                        print(f'[KICK CHAT] Sending to chat: {username}: {content}')
                        
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
                    import traceback
                    traceback.print_exc()
                    
    except Exception as e:
        print(f'[KICK CHAT] Connection error: {e}')

def start_kick_chat(channel_slug, user_id, access_token):
    """Start Kick chat in background thread"""
    if user_id in active_kick_chats:
        return False
    
    loop = asyncio.new_event_loop()
    
    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(kick_chat_connect(channel_slug, user_id, access_token))
    
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