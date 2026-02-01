import json
import requests
from functools import wraps
from typing import Optional, Callable
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import ActiveSession, PlatformConnection, WidgetConfig


# ============ SESSION MANAGEMENT ============

def get_client_ip(request) -> str:
    """Get real client IP, handling proxies"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def activate_fuzeobs_user(user):
    """Mark user as FuzeOBS user on first app login"""
    if not user.fuzeobs_activated:
        user.fuzeobs_activated = True
        user.fuzeobs_first_login = timezone.now()
    user.fuzeobs_last_active = timezone.now()
    user.fuzeobs_total_sessions += 1
    user.save()


def update_active_session(user, session_id: str, ip_address: str = None):
    """Update or create active session"""
    ActiveSession.objects.update_or_create(
        session_id=session_id,
        defaults={
            'user': user,
            'ip_address': ip_address,
            'last_ping': timezone.now(),
            'is_anonymous': False
        }
    )


def cleanup_old_sessions():
    """Remove sessions inactive for 5+ minutes"""
    threshold = timezone.now() - timedelta(minutes=5)
    ActiveSession.objects.filter(last_ping__lt=threshold).delete()


# ============ WIDGET REFRESH ============

# Maps widget_type -> (group_prefix, event_type, per_platform)
WIDGET_REFRESH_CONFIG = {
    'chat_box': ('chat', 'chat_message', False),
    'alert_box': ('alerts', 'alert_event', True),
    'event_list': ('alerts', 'alert_event', 'all'),  # Special: all platforms
    'goal_bar': ('goals', 'goal_update', False),
    'labels': ('labels', 'label_update', False),
    'viewer_count': ('viewers', 'viewer_update', False),
    'sponsor_banner': ('sponsor', 'sponsor_update', False),
}


def send_widget_refresh(user_id: int, widget_type: str, platform: str = None):
    """
    Send refresh signal to widget WebSocket.
    Replaces the long if/elif chain in fuzeobs_save_widget.
    """
    config = WIDGET_REFRESH_CONFIG.get(widget_type)
    if not config:
        return
    
    group_prefix, event_type, per_platform = config
    channel_layer = get_channel_layer()
    
    if per_platform == 'all':
        # Send to all platform groups (event_list)
        for plat in ['twitch', 'youtube', 'kick', 'facebook', 'tiktok']:
            async_to_sync(channel_layer.group_send)(
                f'{group_prefix}_{user_id}_{plat}',
                {'type': event_type, 'data': {'type': 'refresh'}}
            )
    elif per_platform and platform:
        # Platform-specific group (alert_box)
        async_to_sync(channel_layer.group_send)(
            f'{group_prefix}_{user_id}_{platform}',
            {'type': event_type, 'data': {'type': 'refresh'}}
        )
    else:
        # User-only group
        async_to_sync(channel_layer.group_send)(
            f'{group_prefix}_{user_id}',
            {'type': event_type, 'data': {'type': 'refresh'}}
        )


# ============ VIEWER COUNT HELPERS ============

def get_platform_viewer_count(user_id: int, platform: str) -> int:
    """
    Unified viewer count fetching.
    Replaces 5 separate endpoint functions.
    """
    try:
        conn = PlatformConnection.objects.get(user_id=user_id, platform=platform)
    except PlatformConnection.DoesNotExist:
        return 0
    
    fetchers = {
        'twitch': _get_twitch_viewers,
        'youtube': _get_youtube_viewers,
        'kick': _get_kick_viewers,
        'facebook': _get_facebook_viewers,
        'tiktok': lambda c: 0,  # TikTok doesn't provide viewer count
    }
    
    fetcher = fetchers.get(platform)
    if not fetcher:
        return 0
    
    try:
        return fetcher(conn)
    except Exception as e:
        print(f'[VIEWER] {platform} error: {e}')
        return 0


def _get_twitch_viewers(conn: PlatformConnection) -> int:
    from .twitch import get_app_access_token
    app_token = get_app_access_token()
    
    resp = requests.get(
        'https://api.twitch.tv/helix/streams',
        params={'user_login': conn.platform_username},
        headers={
            'Authorization': f'Bearer {app_token}',
            'Client-Id': settings.TWITCH_CLIENT_ID
        },
        timeout=5
    )
    
    if resp.status_code == 200:
        streams = resp.json().get('data', [])
        if streams:
            return streams[0].get('viewer_count', 0)
    return 0


def _get_youtube_viewers(conn: PlatformConnection) -> int:
    # Find active broadcast
    resp = requests.get(
        'https://www.googleapis.com/youtube/v3/liveBroadcasts',
        params={
            'part': 'snippet,status',
            'broadcastType': 'all',
            'mine': 'true',
            'maxResults': 5
        },
        headers={'Authorization': f'Bearer {conn.access_token}'},
        timeout=10
    )
    
    if resp.status_code != 200:
        return 0
    
    for broadcast in resp.json().get('items', []):
        if broadcast.get('status', {}).get('lifeCycleStatus') == 'live':
            video_id = broadcast['id']
            
            video_resp = requests.get(
                'https://www.googleapis.com/youtube/v3/videos',
                params={'part': 'liveStreamingDetails', 'id': video_id},
                headers={'Authorization': f'Bearer {conn.access_token}'},
                timeout=10
            )
            
            if video_resp.status_code == 200:
                videos = video_resp.json().get('items', [])
                if videos:
                    return int(videos[0].get('liveStreamingDetails', {}).get('concurrentViewers', 0))
    return 0


def _get_kick_viewers(conn: PlatformConnection) -> int:
    resp = requests.get(
        f'https://kick.com/api/v2/channels/{conn.platform_username}',
        headers={'User-Agent': 'FuzeOBS/1.0'},
        timeout=5
    )
    
    if resp.status_code == 200:
        livestream = resp.json().get('livestream')
        if livestream:
            return livestream.get('viewer_count', 0)
    return 0


def _get_facebook_viewers(conn: PlatformConnection) -> int:
    resp = requests.get(
        f'https://graph.facebook.com/v18.0/{conn.platform_user_id}/live_videos',
        params={
            'access_token': conn.access_token,
            'fields': 'id,status,live_views',
            'limit': 1
        },
        timeout=5
    )
    
    if resp.status_code == 200:
        for video in resp.json().get('data', []):
            if video.get('status') == 'LIVE':
                return video.get('live_views', 0)
    return 0


# ============ CHAT WIDGET CHECK ============

def is_chat_enabled(user_id: int) -> bool:
    """Check if chat widget is enabled - used by all chat handlers"""
    return WidgetConfig.objects.filter(
        user_id=user_id,
        widget_type='chat_box',
        enabled=True
    ).exists()


# ============ JSON BODY PARSER ============

def parse_json_body(request) -> Optional[dict]:
    """Safely parse JSON request body"""
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return None