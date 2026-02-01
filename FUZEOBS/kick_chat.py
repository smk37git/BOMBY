"""Kick chat via Pusher WebSocket"""
import asyncio
import websockets
import json
import requests
import re
import threading
from channels.layers import get_channel_layer

from .chat_base import ChatRegistry, is_chat_enabled

kick_chat = ChatRegistry('KICK CHAT')


async def _ws_connect(channel_slug: str, user_id: int, access_token: str):
    """Connect to Kick chat via Pusher WebSocket"""
    
    # Get chatroom ID from Kick API
    try:
        resp = requests.get(
            f'https://kick.com/api/v2/channels/{channel_slug}',
            timeout=5,
            headers={'User-Agent': 'FuzeOBS/1.0', 'Authorization': f'Bearer {access_token}'}
        )
        if resp.status_code != 200:
            print(f'[KICK CHAT] Channel {channel_slug} not found (status {resp.status_code})')
            return
        
        chatroom_id = resp.json().get('chatroom', {}).get('id')
        if not chatroom_id:
            print(f'[KICK CHAT] No chatroom for {channel_slug}')
            return
            
    except Exception as e:
        print(f'[KICK CHAT] API error: {e}')
        return
    
    uri = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0-rc2&flash=false"
    
    try:
        async with websockets.connect(uri) as ws:
            # Wait for connection
            msg = await ws.recv()
            if json.loads(msg).get('event') == 'pusher:connection_established':
                print(f'[KICK CHAT] Connected to Pusher')
            
            # Subscribe to chatroom
            await ws.send(json.dumps({
                "event": "pusher:subscribe",
                "data": {"channel": f"chatrooms.{chatroom_id}.v2"}
            }))
            print(f'[KICK CHAT] Connected to {channel_slug} (room {chatroom_id})')
            
            channel_layer = get_channel_layer()
            
            while True:
                try:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    event = data.get('event')
                    
                    if event == 'pusher:ping':
                        await ws.send(json.dumps({'event': 'pusher:pong', 'data': {}}))
                        continue
                    
                    if event == 'pusher_internal:subscription_succeeded':
                        print(f'[KICK CHAT] ✓ Subscription successful!')
                        continue
                    
                    if event == 'App\\Events\\ChatMessageEvent':
                        # Check if enabled (async-safe)
                        has_enabled = await asyncio.to_thread(is_chat_enabled, user_id)
                        if not has_enabled:
                            continue
                        
                        message_data = json.loads(data.get('data', '{}'))
                        sender = message_data.get('sender', {})
                        identity = sender.get('identity', {})
                        
                        username = sender.get('username', 'Unknown')
                        content = message_data.get('content', '')
                        color = identity.get('color') or '#FFFFFF'
                        
                        # Get badges
                        badges = []
                        if identity.get('badges'):
                            badges = [b['type'] for b in identity['badges'] if 'type' in b]
                        
                        # Extract emotes [emote:ID:name]
                        emotes = [
                            {'id': m.group(1), 'name': m.group(2), 'start': m.start(), 'end': m.end()}
                            for m in re.finditer(r'\[emote:(\d+):([^\]]+)\]', content)
                        ]
                        
                        print(f'[KICK CHAT] {username}: {content[:50]}')
                        
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
                                    'emotes': emotes
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
    finally:
        kick_chat.unregister(user_id)


def start_kick_chat(channel_slug: str, user_id: int, access_token: str) -> bool:
    """Start Kick chat in background thread"""
    if not kick_chat.register(user_id, {'active': True}):
        return False
    
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_ws_connect(channel_slug, user_id, access_token))
    
    thread = threading.Thread(target=run, daemon=True, name=f'kick-chat-{user_id}')
    thread.start()
    return True


def stop_kick_chat(user_id: int) -> bool:
    """Stop Kick chat"""
    return kick_chat.stop(user_id)