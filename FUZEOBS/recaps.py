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


# ============ DURATION HELPERS ============

def _parse_twitch_duration(dur_str):
    """Convert Twitch format '3h24m10s' to '3h 24m'"""
    if not dur_str:
        return '0m'
    hours = minutes = seconds = 0
    h = re.search(r'(\d+)h', dur_str)
    m = re.search(r'(\d+)m', dur_str)
    s = re.search(r'(\d+)s', dur_str)
    if h: hours = int(h.group(1))
    if m: minutes = int(m.group(1))
    if s: seconds = int(s.group(1))
    if hours > 0:
        return f'{hours}h {minutes}m'
    if minutes > 0:
        return f'{minutes}m'
    return f'{seconds}s'


def _parse_yt_duration(dur_str):
    """Convert ISO 8601 'PT3H24M10S' to '3h 24m'"""
    if not dur_str:
        return '0m'
    hours = minutes = seconds = 0
    h = re.search(r'(\d+)H', dur_str)
    m = re.search(r'(\d+)M', dur_str)
    s = re.search(r'(\d+)S', dur_str)
    if h: hours = int(h.group(1))
    if m: minutes = int(m.group(1))
    if s: seconds = int(s.group(1))
    if hours > 0:
        return f'{hours}h {minutes}m'
    if minutes > 0:
        return f'{minutes}m'
    return f'{seconds}s'


def _seconds_to_duration(seconds):
    """Convert raw seconds to '3h 24m'"""
    if not seconds or seconds <= 0:
        return '0m'
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f'{hours}h {minutes}m'
    if minutes > 0:
        return f'{minutes}m'
    return f'{seconds}s'


# ============ TWITCH ============
# Get Videos: id, stream_id, user_id, user_name, title, created_at, url,
#   view_count, language, type, duration ("6h26m14s"). NO game_id/game_name.
# Get Clips: id, url, broadcaster_name, game_id, title, view_count, created_at, duration
# Get Streams: id, user_id, game_id, game_name, title, viewer_count, started_at

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

        # Get channel info for game_name (since /videos doesn't include it)
        channel_game = ''
        try:
            ch_resp = requests.get(
                'https://api.twitch.tv/helix/channels',
                params={'broadcaster_id': broadcaster_id},
                headers=headers,
                timeout=5,
            )
            if ch_resp.status_code == 200:
                ch_data = ch_resp.json().get('data', [])
                if ch_data:
                    channel_game = ch_data[0].get('game_name', '')
        except Exception:
            pass

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
                    'peak_viewers': 0,
                    'category': channel_game,
                    'vod_url': v.get('url', ''),
                    'clips': 0,
                    'stream_id': v.get('stream_id', v.get('id', '')),
                })

        # 2) No VODs — try clips (any user can have clips made of them)
        if not recaps:
            clips_resp = requests.get(
                'https://api.twitch.tv/helix/clips',
                params={'broadcaster_id': broadcaster_id, 'first': 10},
                headers=headers,
                timeout=5,
            )
            if clips_resp.status_code == 200:
                clips = clips_resp.json().get('data', [])
                # Batch-resolve game_ids to game_names
                game_ids = list(set(c.get('game_id', '') for c in clips if c.get('game_id')))
                game_names = {}
                if game_ids:
                    try:
                        games_resp = requests.get(
                            'https://api.twitch.tv/helix/games',
                            params={'id': game_ids[:100]},
                            headers=headers,
                            timeout=5,
                        )
                        if games_resp.status_code == 200:
                            for g in games_resp.json().get('data', []):
                                game_names[g['id']] = g.get('name', '')
                    except Exception:
                        pass

                for c in clips:
                    recaps.append({
                        'platform': 'twitch',
                        'title': c.get('title', 'Clip'),
                        'date': c.get('created_at', ''),
                        'duration': f"{c.get('duration', 0):.0f}s",
                        'views': c.get('view_count', 0),
                        'peak_viewers': 0,
                        'category': game_names.get(c.get('game_id', ''), ''),
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
                        'peak_viewers': s.get('viewer_count', 0),
                        'category': s.get('game_name', ''),
                        'vod_url': f"https://twitch.tv/{conn.platform_username}",
                        'clips': 0,
                        'stream_id': s.get('id', ''),
                    })

    except Exception as e:
        print(f'[RECAPS] Twitch error: {e}')
    return recaps


# ============ YOUTUBE ============
# Search (eventType=completed): snippet.title, snippet.publishedAt
# Videos: contentDetails.duration (ISO 8601), statistics.viewCount,
#   liveStreamingDetails.concurrentViewers (peak during live),
#   liveStreamingDetails.actualStartTime, liveStreamingDetails.actualEndTime

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

        # Full details: duration, views, peak concurrent viewers
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
                live_details = v.get('liveStreamingDetails', {})

                # Prefer actualStartTime over publishedAt
                date = live_details.get('actualStartTime', s.get('publishedAt', ''))

                # Calculate real stream duration from start/end if available
                duration = ''
                actual_start = live_details.get('actualStartTime')
                actual_end = live_details.get('actualEndTime')
                if actual_start and actual_end:
                    try:
                        from datetime import datetime
                        start_dt = datetime.fromisoformat(actual_start.replace('Z', '+00:00'))
                        end_dt = datetime.fromisoformat(actual_end.replace('Z', '+00:00'))
                        diff_seconds = int((end_dt - start_dt).total_seconds())
                        duration = _seconds_to_duration(diff_seconds)
                    except Exception:
                        duration = _parse_yt_duration(v.get('contentDetails', {}).get('duration', ''))
                else:
                    duration = _parse_yt_duration(v.get('contentDetails', {}).get('duration', ''))

                recaps.append({
                    'platform': 'youtube',
                    'title': s.get('title', 'Untitled'),
                    'date': date,
                    'duration': duration,
                    'views': int(stats.get('viewCount', 0)),
                    'peak_viewers': int(live_details.get('concurrentViewers', 0)),
                    'category': '',
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
                    'peak_viewers': 0,
                    'category': '',
                    'vod_url': f'https://youtube.com/watch?v={vid}',
                    'clips': 0,
                    'stream_id': vid,
                })
    except Exception as e:
        print(f'[RECAPS] YouTube error: {e}')
    return recaps


# ============ KICK ============
# /api/v2/channels/{username}/videos returns:
#   uuid, session_title, created_at, views, duration,
#   livestream: { duration, viewer_count, categories: [{name}] }
# VOD URL: https://kick.com/{username}/videos/{uuid}

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
        items = data if isinstance(data, list) else (data.get('data') or data.get('value', []))

        for v in items[:10]:
            livestream = v.get('livestream') or {}
            video_obj = v.get('video') or {}

            # Kick returns duration in MILLISECONDS, not seconds
            duration_ms = livestream.get('duration', 0) or v.get('duration', 0)
            duration_seconds = int(duration_ms / 1000) if duration_ms > 0 else 0

            cats = v.get('categories') or livestream.get('categories') or []
            category = cats[0].get('name', '') if cats else ''

            # UUID lives inside the nested 'video' object
            video_uuid = video_obj.get('uuid', '') or v.get('slug', '')
            if not video_uuid:
                print(f'[RECAPS] Kick video missing uuid, video_obj keys: {list(video_obj.keys())}')

            recaps.append({
                'platform': 'kick',
                'title': v.get('session_title', livestream.get('session_title', 'Untitled')),
                'date': v.get('created_at', v.get('start_time', '')),
                'duration': _seconds_to_duration(duration_seconds),
                'views': v.get('views', v.get('live_stream_view_count', 0)),
                'peak_viewers': v.get('viewer_count', 0),
                'category': category,
                'vod_url': f"https://kick.com/{conn.platform_username}/videos/{video_uuid}" if video_uuid else f"https://kick.com/{conn.platform_username}",
                'clips': 0,
                'stream_id': str(v.get('id', '')),
            })
    except Exception as e:
        print(f'[RECAPS] Kick error: {e}')
    return recaps


# ============ FACEBOOK ============
# /{page_id}/live_videos fields:
#   id, title, creation_time, live_views, status, description, video {id}
# NOTE: peak_concurrent_viewers requires Insights API (separate permission)
# Video URL: https://facebook.com/{video_id}

def _fetch_facebook_recaps(conn):
    """Fetch recent Facebook live videos"""
    recaps = []
    try:
        resp = requests.get(
            f'https://graph.facebook.com/v18.0/{conn.platform_user_id}/live_videos',
            params={
                'access_token': conn.access_token,
                'fields': 'id,title,creation_time,live_views,status,description,video',
                'limit': 10,
            },
            timeout=5,
        )
        if resp.status_code != 200:
            return recaps

        for v in resp.json().get('data', []):
            video_id = v.get('video', {}).get('id', v.get('id', ''))
            status = v.get('status', '')
            title = v.get('title') or ''
            if not title:
                desc = v.get('description', '')
                title = (desc[:80] + '...') if len(desc) > 80 else desc
            title = title or 'Facebook Live'

            recaps.append({
                'platform': 'facebook',
                'title': title,
                'date': v.get('creation_time', ''),
                'duration': 'LIVE' if status == 'LIVE' else '',
                'views': v.get('live_views', 0),
                'peak_viewers': 0,  # Only via Insights API
                'category': '',
                'vod_url': f'https://facebook.com/{video_id}' if video_id else '',
                'clips': 0,
                'stream_id': str(v.get('id', '')),
            })
    except Exception as e:
        print(f'[RECAPS] Facebook error: {e}')
    return recaps


# ============ TIKTOK ============
# TikTok does NOT provide a past broadcasts/VOD API.
# Past streams are not saved unless the creator explicitly enables it,
# and even then there's no public API to retrieve them.

def _fetch_tiktok_recaps(conn):
    """TikTok has no past broadcast API — returns empty"""
    return []


# ============ FETCHER MAP ============

PLATFORM_FETCHERS = {
    'twitch': _fetch_twitch_recaps,
    'youtube': _fetch_youtube_recaps,
    'kick': _fetch_kick_recaps,
    'facebook': _fetch_facebook_recaps,
    'tiktok': _fetch_tiktok_recaps,
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

    recaps = _fetch_all_recaps(user)
    cache.set(cache_key, recaps, 300)
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