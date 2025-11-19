import requests
from django.conf import settings
from .twitch_eventsub import send_alert
import xml.etree.ElementTree as ET

def subscribe_youtube_channel(channel_id, user_id):
    """Subscribe to YouTube channel via PubSubHubbub (webhook-based like Twitch)"""
    resp = requests.post('https://pubsubhubbub.appspot.com/subscribe', data={
        'hub.callback': f'https://bomby.us/fuzeobs/youtube-webhook?user_id={user_id}',
        'hub.topic': f'https://www.youtube.com/xml/feeds/videos.xml?channel_id={channel_id}',
        'hub.verify': 'async',
        'hub.mode': 'subscribe',
        'hub.lease_seconds': 864000
    })
    return resp.status_code == 202

def handle_youtube_notification(xml_data, user_id):
    """Parse YouTube PubSubHubbub notification"""
    try:
        root = ET.fromstring(xml_data)
        entry = root.find('{http://www.w3.org/2005/Atom}entry')
        if entry:
            video_id = entry.find('{http://yt:schemas:google:com:2008}videoId', {'yt': 'http://yt:schemas:google:com:2008'})
            title = entry.find('{http://www.w3.org/2005/Atom}title')
            author = entry.find('{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name')
            
            # New video = likely new sub activity
            send_alert(user_id, 'subscribe', 'youtube', {
                'username': author.text if author is not None else 'New Subscriber'
            })
    except Exception as e:
        print(f'[YOUTUBE] Parse error: {e}')

def poll_super_chats(access_token, user_id):
    """Only called when user is live"""
    resp = requests.get(
        'https://www.googleapis.com/youtube/v3/liveBroadcasts',
        params={'part': 'snippet', 'broadcastStatus': 'active', 'mine': 'true'},
        headers={'Authorization': f'Bearer {access_token}'}
    )
    
    if resp.status_code != 200 or not resp.json().get('items'):
        return False
    
    live_chat_id = resp.json()['items'][0]['snippet'].get('liveChatId')
    if not live_chat_id:
        return False
    
    # Get chat messages
    chat_resp = requests.get(
        'https://www.googleapis.com/youtube/v3/liveChat/messages',
        params={'liveChatId': live_chat_id, 'part': 'snippet,authorDetails'},
        headers={'Authorization': f'Bearer {access_token}'}
    )
    
    if chat_resp.status_code == 200:
        for msg in chat_resp.json().get('items', []):
            if 'superChatDetails' in msg['snippet']:
                details = msg['snippet']['superChatDetails']
                send_alert(user_id, 'superchat', 'youtube', {
                    'username': msg['authorDetails']['displayName'],
                    'amount': details['amountDisplayString']
                })
    
    return True