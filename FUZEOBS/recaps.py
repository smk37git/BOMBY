"""Stream Recaps - fetches recent VODs/streams from connected platforms"""
import requests
from datetime import timedelta
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json

from .models import PlatformConnection, StreamRecap
from django.conf import settings


def _fetch_twitch_recaps(conn):
    """Fetch recent Twitch VODs via Helix API"""
    from .twitch import get_app_access_token
    recaps = []
    try:
        app_token = get_app_access_token()
        # Get user ID from username
        user_resp = requests.get(
            'https://api.twitch.tv/helix/users',
            params={'login': conn.platform_username},
            headers={
                'Authorization': f'Bearer {app_token}',
                'Client-Id': settings.TWITCH_CLIENT_ID,
            },
            timeout=5,
        )
        if user_resp.status_code != 200:
            return recaps
        users = user_resp.json().get('data', [])
        if not users:
            return recaps
        broadcaster_id = users[0]['id']

        # Fetch recent VODs
        resp = requests.get(
            'https://api.twitch.tv/helix/videos',
            params={
                'user_id': broadcaster_id,
                'type': 'archive',
                'first': 10,
            },
            headers={
                'Authorization': f'Bearer {app_token}',
                'Client-Id': settings.TWITCH_CLIENT_ID,
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return recaps

        for v in resp.json().get('data', []):
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

        # Try to get clip counts for each stream
        for recap in recaps:
            if recap['stream_id']:
                try:
                    clips_resp = requests.get(
                        'https://api.twitch.tv/helix/clips',
                        params={
                            'broadcaster_id': broadcaster_id,
                            'first': 1,
                            'started_at': recap['date'],
                        },
                        headers={
                            'Authorization': f'Bearer {app_token}',
                            'Client-Id': settings.TWITCH_CLIENT_ID,
                        },
                        timeout=3,
                    )
                    if clips_resp.status_code == 200:
                        clip_data = clips_resp.json()
                        # Pagination total isn't available, but we can check data length
                        recap['clips'] = len(clip_data.get('data', []))
                except Exception:
                    pass
    except Exception as e:
        print(f'[RECAPS] Twitch error: {e}')
    return recaps


def _parse_twitch_duration(dur_str):
    """Convert '3h24m10s' to '3h 24m'"""
    if not dur_str:
        return '0m'
    hours, minutes = 0, 0
    import re
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
    """Fetch recent YouTube live streams"""
    recaps = []
    try:
        # Search for past live broadcasts
        resp = requests.get(
            'https://www.googleapis.com/youtube/v3/search',
            params={
                'part': 'snippet',
                'channelId': conn.platform_user_id,
                'type': 'video',
                'eventType': 'completed',
                'order': 'date',
                'maxResults': 10,
            },
            headers={'Authorization': f'Bearer {conn.access_token}'},
            timeout=10,
        )
        if resp.status_code != 200:
            # Try with 'mine' param if channelId doesn't work
            resp = requests.get(
                'https://www.googleapis.com/youtube/v3/search',
                params={
                    'part': 'snippet',
                    'forMine': 'true',
                    'type': 'video',
                    'eventType': 'completed',
                    'order': 'date',
                    'maxResults': 10,
                },
                headers={'Authorization': f'Bearer {conn.access_token}'},
                timeout=10,
            )
            if resp.status_code != 200:
                return recaps

        video_ids = []
        snippets = {}
        for item in resp.json().get('items', []):
            vid = item['id'].get('videoId', '')
            if vid:
                video_ids.append(vid)
                snippets[vid] = item.get('snippet', {})

        if not video_ids:
            return recaps

        # Get video details (duration, views)
        details_resp = requests.get(
            'https://www.googleapis.com/youtube/v3/videos',
            params={
                'part': 'contentDetails,statistics,liveStreamingDetails',
                'id': ','.join(video_ids),
            },
            headers={'Authorization': f'Bearer {conn.access_token}'},
            timeout=10,
        )
        if details_resp.status_code != 200:
            # Return basic info without details
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
            return recaps

        for v in details_resp.json().get('items', []):
            vid = v['id']
            s = snippets.get(vid, {})
            stats = v.get('statistics', {})
            duration = _parse_yt_duration(v.get('contentDetails', {}).get('duration', ''))
            recaps.append({
                'platform': 'youtube',
                'title': s.get('title', 'Untitled'),
                'date': s.get('publishedAt', ''),
                'duration': duration,
                'views': int(stats.get('viewCount', 0)),
                'vod_url': f'https://youtube.com/watch?v={vid}',
                'clips': 0,
                'stream_id': vid,
            })
    except Exception as e:
        print(f'[RECAPS] YouTube error: {e}')
    return recaps


def _parse_yt_duration(dur_str):
    """Convert ISO 8601 duration 'PT3H24M10S' to '3h 24m'"""
    if not dur_str:
        return '0m'
    import re
    hours, minutes = 0, 0
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

        for v in resp.json()[:10]:
            duration_seconds = v.get('livestream', {}).get('duration', 0) or v.get('duration', 0)
            recaps.append({
                'platform': 'kick',
                'title': v.get('session_title', v.get('livestream', {}).get('session_title', 'Untitled')),
                'date': v.get('created_at', v.get('start_time', '')),
                'duration': _seconds_to_duration(duration_seconds),
                'views': v.get('views', v.get('live_stream_view_count', 0)),
                'vod_url': f'https://kick.com/{conn.platform_username}/video/{v.get("uuid", v.get("id", ""))}',
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
    """Convert seconds to 'Xh Ym' format"""
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


def fetch_and_save_recaps(user):
    """Fetch recaps from all connected platforms and save to DB"""
    connections = PlatformConnection.objects.filter(user=user)
    all_recaps = []

    for conn in connections:
        fetcher = PLATFORM_FETCHERS.get(conn.platform)
        if fetcher:
            try:
                platform_recaps = fetcher(conn)
                all_recaps.extend(platform_recaps)
            except Exception as e:
                print(f'[RECAPS] Error fetching {conn.platform}: {e}')

    # Sort by date descending
    all_recaps.sort(key=lambda r: r.get('date', ''), reverse=True)

    # Keep top 10
    all_recaps = all_recaps[:10]

    # Save to DB (replace old recaps)
    StreamRecap.objects.filter(user=user).delete()
    for r in all_recaps:
        StreamRecap.objects.create(
            user=user,
            platform=r['platform'],
            title=r.get('title', 'Untitled'),
            date=r.get('date', ''),
            duration=r.get('duration', ''),
            views=r.get('views', 0),
            vod_url=r.get('vod_url', ''),
            clips=r.get('clips', 0),
            stream_id=r.get('stream_id', ''),
        )

    return all_recaps


def _recaps_to_json(recaps_qs):
    """Convert queryset to JSON-serializable list"""
    return [
        {
            'platform': r.platform,
            'title': r.title,
            'date': r.date,
            'duration': r.duration,
            'views': r.views,
            'vod_url': r.vod_url,
            'clips': r.clips,
        }
        for r in recaps_qs
    ]


# ============ VIEWS ============

@csrf_exempt
def fuzeobs_recaps(request):
    """GET cached recaps from DB"""
    from .views import get_user_from_token
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'No token'}, status=401)
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)

    cached = StreamRecap.objects.filter(user=user).order_by('-date')[:10]

    if cached.exists():
        return JsonResponse({'success': True, 'recaps': _recaps_to_json(cached)})

    # No cached data - try fetching
    recaps = fetch_and_save_recaps(user)
    return JsonResponse({'success': True, 'recaps': recaps})


@csrf_exempt
def fuzeobs_recaps_refresh(request):
    """POST - force refresh recaps from platform APIs"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    from .views import get_user_from_token
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'No token'}, status=401)
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)

    recaps = fetch_and_save_recaps(user)
    return JsonResponse({'success': True, 'recaps': recaps})