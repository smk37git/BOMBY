import asyncio
import websockets
from channels.layers import get_channel_layer

active_connections = {}

async def twitch_irc_connect(channel_name, user_id, oauth_token):
    """Connect to Twitch IRC using user's OAuth token"""
    uri = "wss://irc-ws.chat.twitch.tv:443"
    
    try:
        async with websockets.connect(uri) as websocket:
            await websocket.send(f"PASS oauth:{oauth_token}")
            await websocket.send(f"NICK {channel_name}")
            await websocket.send(f"JOIN #{channel_name}")
            await websocket.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
            
            print(f"[IRC] Connected to #{channel_name}")
            
            channel_layer = get_channel_layer()
            
            while True:
                try:
                    message = await websocket.recv()
                    
                    if message.startswith('PING'):
                        await websocket.send('PONG :tmi.twitch.tv')
                        continue
                    
                    if 'PRIVMSG' in message:
                        parts = message.split('PRIVMSG', 1)
                        if len(parts) == 2:
                            tags = parts[0]
                            content = parts[1].split(':', 1)
                            
                            if len(content) == 2:
                                msg_text = content[1].strip()
                                username = ""
                                badges = []
                                color = "#FFFFFF"
                                
                                for tag in tags.split(';'):
                                    if tag.startswith('display-name='):
                                        username = tag.split('=', 1)[1]
                                    elif tag.startswith('badges='):
                                        badge_str = tag.split('=', 1)[1]
                                        if badge_str:
                                            badges = [b.split('/')[0] for b in badge_str.split(',')]
                                    elif tag.startswith('color='):
                                        c = tag.split('=', 1)[1]
                                        if c:
                                            color = c
                                
                                await channel_layer.group_send(
                                    f'chat_{user_id}',
                                    {
                                        'type': 'chat_message',
                                        'data': {
                                            'username': username,
                                            'message': msg_text,
                                            'badges': badges,
                                            'color': color,
                                            'platform': 'twitch'
                                        }
                                    }
                                )
                
                except websockets.exceptions.ConnectionClosed:
                    print(f"[IRC] Connection closed")
                    break
                except Exception as e:
                    print(f"[IRC] Error: {e}")
                    break
    except Exception as e:
        print(f"[IRC] Connection error: {e}")

def start_twitch_chat(channel_name, user_id, oauth_token):
    """Start IRC in background thread"""
    if user_id in active_connections:
        return False
    
    loop = asyncio.new_event_loop()
    
    def run():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(twitch_irc_connect(channel_name, user_id, oauth_token))
    
    import threading
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    
    active_connections[user_id] = thread
    return True

def stop_twitch_chat(user_id):
    """Stop IRC connection"""
    if user_id in active_connections:
        del active_connections[user_id]
        return True
    return False