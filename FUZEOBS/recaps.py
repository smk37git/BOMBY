"""Stream Recaps - fetches recent VODs/streams from connected platforms"""
import os
import re
import time
import hmac
import hashlib
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model

from .models import PlatformConnection
from django.conf import settings

User = get_user_model()


# ============ AUTH (inlined to avoid circular import with views.py) ============

def _verify_token(token):
    """Verify auth token - mirrors views.py SecureAuth logic"""
    secret = os.environ.get('FUZEOBS_SECRET_KEY', os.environ.get('DJANGO_SECRET_KEY', '')).encode()
    try:
        parts = token.split(':')
        if len(parts) != 4:
            return None
        user_id, tier, timestamp, signature = parts
        message = f"{user_id}:{tier}:{timestamp}"
        expected = hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        if int(time.time()) - int(timestamp) > 2592000:
            return None
        return User.objects.get(id=int(user_id))
    except Exception:
        return None


def _get_user(request):
    """Extract user from Authorization header"""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    return _verify_token(auth.replace('Bearer ', ''))


# ============ PLATFORM FETCHERS ============

def _fetch_twitch_recaps(conn):
    """
    Fetch recent Twitch data.
    VODs require Affiliate/Partner. For non-affiliates we fall back
    to clips, then current live stream info.
    """
    from .twitch import get_app_access_token
    recaps = []
    try:
        app_token = get_app_access_token()
        headers = {
            'Authorization': f'Bearer {app_token}',
            'Client-Id': settings.TWITCH_CLIENT_ID,
        }

        # Resolve broadcaster_id
        user_resp = requests.get(
            'https://api.twitch.tv/helix/users',
            params={'login': conn.platform_username},
            headers=headers,
            timeout=5,
        )
        if user_resp.status_code != 200:
            return recaps
        users = user_resp.json().get('data', [])
        if not users:
            return recaps
        broadcaster_id = users[0]['id']

        # 1) Try VODs (Affiliate/Partner only)
        vod_resp = requests.get(
            'https://api.twitch.tv/helix/videos',
            params={'user_id': broadcaster_id, 'type': 'archive', 'first': 10},
            headers=headers,
            timeout=5,
        )
        if vod_resp.status_code == 200:
            vods = vod_resp.json().get('data', [])
            for v in vods:
                recaps.append({
                    'platform': 'twitch',
                    'title': v.get('title', 'Untitled'),
                    'date': v.get('created_at', ''),
                    'duration': _parse_twitch_duration(v.get('duration', '')),
                    'views': v.get('view_count', 0),
                    'vod_url': v.get('url', ''),
                    'clips': 0,
                    'stream_id': v.get('stream_id', v.get('id', '')),
                })

        # 2) No VODs — try clips as fallback
        if not recaps:
            clips_resp = requests.get(
                'https://api.twitch.tv/helix/clips',
                params={'broadcaster_id': broadcaster_id, 'first': 10},
                headers=headers,
                timeout=5,
            )
            if clips_resp.status_code == 200:
                for c in clips_resp.json().get('data', []):
                    recaps.append({
                        'platform': 'twitch',
                        'title': c.get('title', 'Clip'),
                        'date': c.get('created_at', ''),
                        'duration': f"{c.get('duration', 0):.0f}s",
                        'views': c.get('view_count', 0),
                        'vod_url': c.get('url', ''),
                        'clips': 0,
                        'stream_id': c.get('id', ''),
                    })

        # 3) Still nothing — check if currently live
        if not recaps:
            stream_resp = requests.get(
                'https://api.twitch.tv/helix/streams',
                params={'user_id': broadcaster_id},
                headers=headers,
                timeout=5,
            )
            if stream_resp.status_code == 200:
                streams = stream_resp.json().get('data', [])
                if streams:
                    s = streams[0]
                    recaps.append({
                        'platform': 'twitch',
                        'title': s.get('title', 'Live Stream'),
                        'date': s.get('started_at', ''),
                        'duration': 'LIVE',
                        'views': s.get('viewer_count', 0),
                        'vod_url': f"https://twitch.tv/{conn.platform_username}",
                        'clips': 0,
                        'stream_id': s.get('id', ''),
                    })

    except Exception as e:
        print(f'[RECAPS] Twitch error: {e}')
    return recaps


def _parse_twitch_duration(dur_str):
    """Convert '3h24m10s' to '3h 24m'"""
    if not dur_str:
        return '0m'
    hours = minutes = 0
    h = re.search(r'(\d+)h', dur_str)
    m = re.search(r'(\d+)m', dur_str)
    if h:
        hours = int(h.group(1))
    if m:
        minutes = int(m.group(1))
    if hours > 0:
        return f'{hours}h {minutes}m'
    return f'{minutes}m'


def _fetch_youtube_recaps(conn):
    """Fetch recent YouTube completed live streams"""
    recaps = []
    try:
        search_params = {
            'part': 'snippet',
            'type': 'video',
            'eventType': 'completed',
            'order': 'date',
            'maxResults': 10,
        }
        if conn.platform_user_id:
            search_params['channelId'] = conn.platform_user_id
        else:
            search_params['forMine'] = 'true'

        resp = requests.get(
            'https://www.googleapis.com/youtube/v3/search',
            params=search_params,
            headers={'Authorization': f'Bearer {conn.access_token}'},
            timeout=10,
        )
        if resp.status_code != 200 and 'channelId' in search_params:
            search_params.pop('channelId')
            search_params['forMine'] = 'true'
            resp = requests.get(
                'https://www.googleapis.com/youtube/v3/search',
                params=search_params,
                headers={'Authorization': f'Bearer {conn.access_token}'},
                timeout=10,
            )
        if resp.status_code != 200:
            return recaps

        video_ids = []
        snippets = {}
        for item in resp.json().get('items', []):
            vid = item.get('id', {}).get('videoId', '')
            if vid:
                video_ids.append(vid)
                snippets[vid] = item.get('snippet', {})

        if not video_ids:
            return recaps

        details_resp = requests.get(
            'https://www.googleapis.com/youtube/v3/videos',
            params={
                'part': 'contentDetails,statistics,liveStreamingDetails',
                'id': ','.join(video_ids),
            },
            headers={'Authorization': f'Bearer {conn.access_token}'},
            timeout=10,
        )

        if details_resp.status_code == 200:
            for v in details_resp.json().get('items', []):
                vid = v['id']
                s = snippets.get(vid, {})
                stats = v.get('statistics', {})
                recaps.append({
                    'platform': 'youtube',
                    'title': s.get('title', 'Untitled'),
                    'date': s.get('publishedAt', ''),
                    'duration': _parse_yt_duration(v.get('contentDetails', {}).get('duration', '')),
                    'views': int(stats.get('viewCount', 0)),
                    'vod_url': f'https://youtube.com/watch?v={vid}',
                    'clips': 0,
                    'stream_id': vid,
                })
        else:
            for vid in video_ids:
                s = snippets.get(vid, {})
                recaps.append({
                    'platform': 'youtube',
                    'title': s.get('title', 'Untitled'),
                    'date': s.get('publishedAt', ''),
                    'duration': '',
                    'views': 0,
                    'vod_url': f'https://youtube.com/watch?v={vid}',
                    'clips': 0,
                    'stream_id': vid,
                })
    except Exception as e:
        print(f'[RECAPS] YouTube error: {e}')
    return recaps


def _parse_yt_duration(dur_str):
    """Convert ISO 8601 'PT3H24M10S' to '3h 24m'"""
    if not dur_str:
        return '0m'
    hours = minutes = 0
    h = re.search(r'(\d+)H', dur_str)
    m = re.search(r'(\d+)M', dur_str)
    if h:
        hours = int(h.group(1))
    if m:
        minutes = int(m.group(1))
    if hours > 0:
        return f'{hours}h {minutes}m'
    return f'{minutes}m'


def _fetch_kick_recaps(conn):
    """Fetch recent Kick VODs"""
    recaps = []
    try:
        resp = requests.get(
            f'https://kick.com/api/v2/channels/{conn.platform_username}/videos',
            headers={'User-Agent': 'FuzeOBS/1.0'},
            timeout=5,
        )
        if resp.status_code != 200:
            return recaps

        data = resp.json()
        items = data if isinstance(data, list) else data.get('data', [])

        for v in items[:10]:
            duration_seconds = v.get('livestream', {}).get('duration', 0) or v.get('duration', 0)
            recaps.append({
                'platform': 'kick',
                'title': v.get('session_title', v.get('livestream', {}).get('session_title', 'Untitled')),
                'date': v.get('created_at', v.get('start_time', '')),
                'duration': _seconds_to_duration(duration_seconds),
                'views': v.get('views', v.get('live_stream_view_count', 0)),
                'vod_url': f"https://kick.com/{conn.platform_username}/video/{v.get('uuid', v.get('id', ''))}",
                'clips': 0,
                'stream_id': str(v.get('id', '')),
            })
    except Exception as e:
        print(f'[RECAPS] Kick error: {e}')
    return recaps


def _fetch_facebook_recaps(conn):
    """Fetch recent Facebook live videos"""
    recaps = []
    try:
        resp = requests.get(
            f'https://graph.facebook.com/v18.0/{conn.platform_user_id}/live_videos',
            params={
                'access_token': conn.access_token,
                'fields': 'id,title,creation_time,live_views,status,video',
                'limit': 10,
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return recaps

        for v in resp.json().get('data', []):
            video_id = v.get('video', {}).get('id', v.get('id', ''))
            recaps.append({
                'platform': 'facebook',
                'title': v.get('title', 'Facebook Live'),
                'date': v.get('creation_time', ''),
                'duration': '',
                'views': v.get('live_views', 0),
                'vod_url': f'https://facebook.com/{video_id}' if video_id else '',
                'clips': 0,
                'stream_id': str(v.get('id', '')),
            })
    except Exception as e:
        print(f'[RECAPS] Facebook error: {e}')
    return recaps


def _seconds_to_duration(seconds):
    if not seconds or seconds <= 0:
        return '0m'
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f'{hours}h {minutes}m'
    return f'{minutes}m'


PLATFORM_FETCHERS = {
    'twitch': _fetch_twitch_recaps,
    'youtube': _fetch_youtube_recaps,
    'kick': _fetch_kick_recaps,
    'facebook': _fetch_facebook_recaps,
}


def _fetch_all_recaps(user):
    """Fetch recaps from all connected platforms, return sorted list"""
    connections = PlatformConnection.objects.filter(user=user)
    all_recaps = []

    for conn in connections:
        fetcher = PLATFORM_FETCHERS.get(conn.platform)
        if fetcher:
            try:
                all_recaps.extend(fetcher(conn))
            except Exception as e:
                print(f'[RECAPS] Error fetching {conn.platform}: {e}')

    all_recaps.sort(key=lambda r: r.get('date', ''), reverse=True)
    return all_recaps[:10]


# ============ VIEWS ============

@csrf_exempt
def fuzeobs_recaps(request):
    """GET - return cached recaps"""
    user = _get_user(request)
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)

    from django.core.cache import cache
    cache_key = f'recaps:{user.id}'
    cached = cache.get(cache_key)

    if cached is not None:
        return JsonResponse({'success': True, 'recaps': cached})

    # No cache — fetch fresh
    recaps = _fetch_all_recaps(user)
    cache.set(cache_key, recaps, 300)  # 5 min cache
    return JsonResponse({'success': True, 'recaps': recaps})


@csrf_exempt
def fuzeobs_recaps_refresh(request):
    """POST - force refresh recaps from platform APIs"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    user = _get_user(request)
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)

    recaps = _fetch_all_recaps(user)

    from django.core.cache import cache
    cache.set(f'recaps:{user.id}', recaps, 300)

    return JsonResponse({'success': True, 'recaps': recaps})