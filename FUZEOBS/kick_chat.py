import asyncio
import websockets
import json
import requests
import re
from channels.layers import get_channel_layer

active_kick_chats = {}

async def kick_chat_connect(channel_slug, user_id, access_token):
    """Connect to Kick chat via Pusher WebSocket"""
    
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
    
    # Connect to Pusher WebSocket (public channel - no auth needed)
    uri = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0-rc2&flash=false"
    
    try:
        async with websockets.connect(uri) as ws:
            # Wait for connection established
            msg = await ws.recv()
            data = json.loads(msg)
            if data.get('event') == 'pusher:connection_established':
                print(f'[KICK CHAT] Connected to Pusher')
            
            # Subscribe to chatroom
            subscribe_msg = {
                "event": "pusher:subscribe",
                "data": {
                    "channel": f"chatrooms.{chatroom_id}.v2"
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
                        
                        # Extract Kick emotes from content [emote:ID:name]
                        emote_data = []
                        for match in re.finditer(r'\[emote:(\d+):([^\]]+)\]', content):
                            emote_data.append({
                                'id': match.group(1),
                                'name': match.group(2),
                                'start': match.start(),
                                'end': match.end()
                            })
                        
                        # Check if chat widget is enabled
                        from .models import WidgetConfig
                        has_enabled = await asyncio.to_thread(
                            lambda: WidgetConfig.objects.filter(
                                user_id=user_id,
                                widget_type='chat_box',
                                enabled=True
                            ).exists()
                        )
                        
                        if not has_enabled:
                            continue
                        
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
                                    'platform': 'kick',
                                    'emotes': emote_data
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