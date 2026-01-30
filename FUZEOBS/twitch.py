import requests
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.conf import settings

def get_app_access_token():
    """Get app access token for EventSub"""
    resp = requests.post('https://id.twitch.tv/oauth2/token', data={
        'client_id': settings.TWITCH_CLIENT_ID,
        'client_secret': settings.TWITCH_CLIENT_SECRET,
        'grant_type': 'client_credentials'
    })
    return resp.json()['access_token']

def subscribe_twitch_events(user_id, broadcaster_id, user_access_token):
    """Subscribe to Twitch events"""
    app_token = get_app_access_token()
    
    headers = {
        'Authorization': f'Bearer {app_token}',
        'Client-Id': settings.TWITCH_CLIENT_ID,
        'Content-Type': 'application/json'
    }
    
    events = [
        ('channel.follow', '2', {'broadcaster_user_id': broadcaster_id, 'moderator_user_id': broadcaster_id}),
        ('channel.subscribe', '1', {'broadcaster_user_id': broadcaster_id}),
        ('channel.subscription.gift', '1', {'broadcaster_user_id': broadcaster_id}),
        ('channel.cheer', '1', {'broadcaster_user_id': broadcaster_id}),
        ('channel.raid', '1', {'to_broadcaster_user_id': broadcaster_id}),
    ]
    
    for event_type, version, condition in events:
        payload = {
            'type': event_type,
            'version': version,
            'condition': condition,
            'transport': {
                'method': 'webhook',
                'callback': 'https://bomby.us/fuzeobs/twitch-webhook',
                'secret': settings.TWITCH_WEBHOOK_SECRET
            }
        }
        resp = requests.post(
            'https://api.twitch.tv/helix/eventsub/subscriptions',
            headers=headers,
            json=payload
        )
        print(f'[TWITCH] {event_type}: {resp.status_code}')
        if resp.status_code != 202:
            print(f'[ERROR] {resp.text}')

def send_alert(user_id, event_type, platform, event_data):
    """Send alert to universal widget WebSocket (alerts_{user_id}_all)"""
    from .models import WidgetConfig
    
    # Check if any enabled alert widget exists for this user
    has_enabled_widget = WidgetConfig.objects.filter(
        user_id=user_id,
        widget_type__in=['alert_box', 'event_list', 'goal_bar', 'labels'],
        enabled=True
    ).exists()
    
    if not has_enabled_widget:
        return  # Skip if no enabled widgets
    
    channel_layer = get_channel_layer()
    # Send to universal channel - all platforms go through one WebSocket
    async_to_sync(channel_layer.group_send)(
        f'alerts_{user_id}_all',
        {
            'type': 'alert_event',
            'data': {
                'event_type': event_type,
                'platform': platform,
                'event_data': event_data
            }
        }
    )