import requests
from django.conf import settings
from .twitch import send_alert
from .models import PlatformConnection

def poll_super_chats(access_token, user_id):
    """Poll super chats with cursor tracking"""
    try:
        conn = PlatformConnection.objects.get(user_id=user_id, platform='youtube')
    except PlatformConnection.DoesNotExist:
        return False
    
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
    
    # Get cursor from metadata
    page_token = conn.metadata.get('yt_page_token')
    
    params = {'liveChatId': live_chat_id, 'part': 'snippet,authorDetails'}
    if page_token:
        params['pageToken'] = page_token
    
    chat_resp = requests.get(
        'https://www.googleapis.com/youtube/v3/liveChat/messages',
        params=params,
        headers={'Authorization': f'Bearer {access_token}'}
    )
    
    if chat_resp.status_code == 200:
        data = chat_resp.json()
        for msg in data.get('items', []):
            if 'superChatDetails' in msg['snippet']:
                details = msg['snippet']['superChatDetails']
                send_alert(user_id, 'superchat', 'youtube', {
                    'username': msg['authorDetails']['displayName'],
                    'amount': details['amountDisplayString']
                })
        
        # Save next page token
        conn.metadata['yt_page_token'] = data.get('nextPageToken')
        conn.save()
    
    return True