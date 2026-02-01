"""Twitch IRC chat"""
import asyncio
import websockets
import threading
from channels.layers import get_channel_layer

from .chat_base import ChatRegistry, is_chat_enabled

twitch_chat = ChatRegistry('IRC')


async def _irc_connect(channel_name: str, user_id: int, oauth_token: str):
    """Connect to Twitch IRC using user's OAuth token"""
    uri = "wss://irc-ws.chat.twitch.tv:443"
    
    channel_name = channel_name.lower().lstrip('#')
    if oauth_token.startswith('oauth:'):
        oauth_token = oauth_token[6:]
    
    print(f"[IRC] Connecting to #{channel_name} (user {user_id})")
    
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(f"PASS oauth:{oauth_token}")
            await ws.send(f"NICK {channel_name}")
            await ws.send(f"JOIN #{channel_name}")
            await ws.send("CAP REQ :twitch.tv/tags twitch.tv/commands")
            
            print(f"[IRC] Auth sent, waiting for response...")
            
            channel_layer = get_channel_layer()
            join_confirmed = False
            
            while True:
                try:
                    message = await ws.recv()
                    
                    if message.startswith('PING'):
                        await ws.send('PONG :tmi.twitch.tv')
                        continue
                    
                    if not message.startswith('PING'):
                        print(f"[IRC] << {message[:150]}")
                    
                    if ':tmi.twitch.tv 366' in message or 'End of /NAMES list' in message:
                        if not join_confirmed:
                            print(f"[IRC] ✓ Successfully joined #{channel_name}")
                            join_confirmed = True
                    
                    if 'Login authentication failed' in message or 'Login unsuccessful' in message:
                        print(f"[IRC] ✗ Authentication failed")
                        break
                    
                    if 'PRIVMSG' not in message:
                        continue
                    
                    # Parse PRIVMSG
                    parts = message.split('PRIVMSG', 1)
                    if len(parts) != 2:
                        continue
                    
                    tags = parts[0]
                    content = parts[1].split(':', 1)
                    if len(content) != 2:
                        continue
                    
                    msg_text = content[1].strip()
                    username, badges, color, emotes = _parse_tags(tags)
                    
                    # Fallback username from prefix
                    if not username:
                        prefix = tags.split(' ')[0]
                        if prefix.startswith(':') and '!' in prefix:
                            username = prefix.split('!')[0][1:]
                    username = username or "Anonymous"
                    
                    # Check if enabled
                    has_enabled = await asyncio.to_thread(is_chat_enabled, user_id)
                    if not has_enabled:
                        continue
                    
                    print(f"[IRC] Forwarding: {username}: {msg_text}")
                    
                    await channel_layer.group_send(
                        f'chat_{user_id}',
                        {
                            'type': 'chat_message',
                            'data': {
                                'username': username,
                                'message': msg_text,
                                'badges': badges,
                                'color': color,
                                'platform': 'twitch',
                                'emotes': emotes
                            }
                        }
                    )
                
                except websockets.exceptions.ConnectionClosed:
                    print(f"[IRC] Connection closed")
                    break
                except Exception as e:
                    print(f"[IRC] Error: {e}")
                    import traceback
                    traceback.print_exc()
                    
    except Exception as e:
        print(f"[IRC] Connection error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        twitch_chat.unregister(user_id)


def _parse_tags(tags: str):
    """Parse IRC tags into username, badges, color, emotes"""
    username = ""
    badges = []
    color = "#FFFFFF"
    emotes = []
    emotes_tag = ""
    
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
        elif tag.startswith('emotes='):
            emotes_tag = tag.split('=', 1)[1]
    
    # Parse emotes: emoteID:start-end,start-end/emoteID:start-end
    if emotes_tag:
        for emote_group in emotes_tag.split('/'):
            if ':' not in emote_group:
                continue
            emote_id, positions = emote_group.split(':', 1)
            for pos in positions.split(','):
                if '-' in pos:
                    start, end = pos.split('-')
                    emotes.append({'id': emote_id, 'start': int(start), 'end': int(end) + 1})
    
    return username, badges, color, emotes


def start_twitch_chat(channel_name: str, user_id: int, oauth_token: str) -> bool:
    """Start IRC in background thread"""
    if not twitch_chat.register(user_id, {'active': True}):
        return False
    
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_irc_connect(channel_name, user_id, oauth_token))
    
    thread = threading.Thread(target=run, daemon=True, name=f'twitch-irc-{user_id}')
    thread.start()
    return True


def stop_twitch_chat(user_id: int) -> bool:
    """Stop IRC connection"""
    return twitch_chat.stop(user_id)