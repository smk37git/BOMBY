"""Leaderboard - ranks users by stream hours from connected platforms"""
import os
import re
import time
import hmac
import hashlib
import requests
from datetime import datetime, timedelta, timezone as dt_tz

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings

from .models import PlatformConnection, LeaderboardEntry


def _parse_date_aware(date_str):
    """Parse various date formats into timezone-aware datetime. Returns None on failure."""
    if not date_str:
        return None
    try:
        clean = date_str.strip().replace(' ', 'T').replace('Z', '+00:00')
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_tz.utc)
        return dt
    except Exception:
        pass
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
        try:
            dt = datetime.strptime(date_str.replace('Z', '').split('+')[0], fmt)
            return dt.replace(tzinfo=dt_tz.utc)
        except Exception:
            continue
    print(f'[LEADERBOARD] Could not parse date: {date_str}')
    return None


User = get_user_model()


# ============ AUTH ============

def _verify_token(token):
    secret = os.environ.get('FUZEOBS_SECRET_KEY', os.environ.get('DJANGO_SECRET_KEY', '')).encode()
    try:
        parts = token.split(':')
        if len(parts) != 5:
            return None
        user_id, tier, timestamp, token_version, signature = parts
        message = f"{user_id}:{tier}:{timestamp}:{token_version}"
        expected = hmac.new(secret, message.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        if int(time.time()) - int(timestamp) > 2592000:
            return None
        user = User.objects.get(id=int(user_id))
        if getattr(user, 'fuzeobs_token_version', 0) != int(token_version):
            return None
        return user
    except Exception:
        return None


def _get_user(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return None
    return _verify_token(auth.replace('Bearer ', ''))


# ============ DURATION PARSING ============

def _duration_to_minutes(dur_str):
    """Convert '3h 24m' or '3h24m10s' or 'PT3H24M10S' to minutes"""
    if not dur_str or dur_str == 'LIVE':
        return 0
    minutes = 0
    h = re.search(r'(\d+)[hH]', dur_str)
    m = re.search(r'(\d+)[mM]', dur_str)
    s = re.search(r'(\d+)[sS]', dur_str)
    if h:
        minutes += int(h.group(1)) * 60
    if m:
        minutes += int(m.group(1))
    if s:
        minutes += int(s.group(1)) // 60
    return minutes


# ============ FETCH HOURS FROM PLATFORMS ============

def _fetch_twitch_hours(conn):
    """Get total stream minutes from Twitch VODs"""
    from .twitch import get_app_access_token
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
            headers=headers, timeout=5,
        )
        if user_resp.status_code != 200:
            return 0, 0, 0
        users = user_resp.json().get('data', [])
        if not users:
            return 0, 0, 0
        broadcaster_id = users[0]['id']
        
        # Fetch VODs (up to 100)
        vod_resp = requests.get(
            'https://api.twitch.tv/helix/videos',
            params={'user_id': broadcaster_id, 'type': 'archive', 'first': 100},
            headers=headers, timeout=5,
        )
        if vod_resp.status_code != 200:
            return 0, 0, 0
        
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        total = weekly = monthly = 0
        for v in vod_resp.json().get('data', []):
            mins = _duration_to_minutes(v.get('duration', ''))
            total += mins
            created = v.get('created_at', '')
            if created:
                dt = _parse_date_aware(created)
                if dt:
                    if dt >= week_ago:
                        weekly += mins
                    if dt >= month_ago:
                        monthly += mins
        
        return total, weekly, monthly
    except Exception as e:
        print(f'[LEADERBOARD] Twitch error: {e}')
        return 0, 0, 0


def _fetch_youtube_hours(conn):
    """Get total stream minutes from YouTube past broadcasts"""
    try:
        # Search for past live broadcasts
        resp = requests.get(
            'https://www.googleapis.com/youtube/v3/search',
            params={
                'part': 'snippet',
                'channelId': conn.platform_user_id,
                'eventType': 'completed',
                'type': 'video',
                'maxResults': 50,
                'order': 'date',
            },
            headers={'Authorization': f'Bearer {conn.access_token}'},
            timeout=10,
        )
        if resp.status_code != 200:
            return 0, 0, 0
        
        video_ids = [item['id']['videoId'] for item in resp.json().get('items', []) if 'videoId' in item.get('id', {})]
        if not video_ids:
            return 0, 0, 0
        
        # Get durations
        vid_resp = requests.get(
            'https://www.googleapis.com/youtube/v3/videos',
            params={'part': 'contentDetails,liveStreamingDetails,snippet', 'id': ','.join(video_ids)},
            headers={'Authorization': f'Bearer {conn.access_token}'},
            timeout=10,
        )
        if vid_resp.status_code != 200:
            return 0, 0, 0
        
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        total = weekly = monthly = 0
        for v in vid_resp.json().get('items', []):
            live_details = v.get('liveStreamingDetails', {})
            start = live_details.get('actualStartTime', '')
            end = live_details.get('actualEndTime', '')
            
            if start and end:
                start_dt = _parse_date_aware(start)
                end_dt = _parse_date_aware(end)
                if start_dt and end_dt:
                    mins = int((end_dt - start_dt).total_seconds()) // 60
                else:
                    mins = _duration_to_minutes(v.get('contentDetails', {}).get('duration', ''))
            else:
                mins = _duration_to_minutes(v.get('contentDetails', {}).get('duration', ''))
            
            total += mins
            
            pub_date = v.get('snippet', {}).get('publishedAt', '')
            if pub_date:
                dt = _parse_date_aware(pub_date)
                if dt:
                    if dt >= week_ago:
                        weekly += mins
                    if dt >= month_ago:
                        monthly += mins
        
        return total, weekly, monthly
    except Exception as e:
        print(f'[LEADERBOARD] YouTube error: {e}')
        return 0, 0, 0


def _fetch_kick_hours(conn):
    """Get total stream minutes from Kick VODs"""
    try:
        resp = requests.get(
            f'https://kick.com/api/v2/channels/{conn.platform_username}/videos',
            headers={'User-Agent': 'FuzeOBS/1.0'},
            timeout=5,
        )
        if resp.status_code != 200:
            return 0, 0, 0
        
        data = resp.json()
        items = data if isinstance(data, list) else (data.get('data') or data.get('value', []))
        
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        
        total = weekly = monthly = 0
        for v in items:
            # Kick returns duration in milliseconds at top level
            duration_ms = v.get('duration', 0) or 0
            mins = int(duration_ms / 1000) // 60 if duration_ms > 0 else 0
            
            total += mins
            
            created = v.get('created_at', v.get('start_time', ''))
            if created:
                dt = _parse_date_aware(created)
                if dt:
                    if dt >= week_ago:
                        weekly += mins
                    if dt >= month_ago:
                        monthly += mins
        
        return total, weekly, monthly
    except Exception as e:
        print(f'[LEADERBOARD] Kick error: {e}')
        return 0, 0, 0


PLATFORM_HOUR_FETCHERS = {
    'twitch': _fetch_twitch_hours,
    'youtube': _fetch_youtube_hours,
    'kick': _fetch_kick_hours,
    # facebook/tiktok don't expose duration data reliably
}


def _sync_user_hours(user):
    """Aggregate stream hours across all connected platforms for a user"""
    connections = PlatformConnection.objects.filter(user=user)
    
    total = weekly = monthly = 0
    for conn in connections:
        fetcher = PLATFORM_HOUR_FETCHERS.get(conn.platform)
        if fetcher:
            try:
                t, w, m = fetcher(conn)
                total += t
                weekly += w
                monthly += m
            except Exception as e:
                print(f'[LEADERBOARD] Sync error {conn.platform}: {e}')
    
    return total, weekly, monthly


# ============ VIEWS ============

@csrf_exempt
def fuzeobs_leaderboard(request, period='all'):
    """GET - get leaderboard rankings (anonymous OK)"""
    user = _get_user(request)  # None if no token
    
    cache_key = f'leaderboard:{period}'
    cached = cache.get(cache_key)
    
    if cached is not None:
        leaderboard = cached
    else:
        order_field = {
            'week': '-weekly_stream_minutes',
            'month': '-monthly_stream_minutes',
            'all': '-total_stream_minutes',
        }.get(period, '-total_stream_minutes')
        
        minutes_field = {
            'week': 'weekly_stream_minutes',
            'month': 'monthly_stream_minutes',
            'all': 'total_stream_minutes',
        }.get(period, 'total_stream_minutes')
        
        entries = (
            LeaderboardEntry.objects
            .filter(opted_in=True)
            .select_related('user')
            .order_by(order_field, '-last_synced', 'user__username')[:50]
        )
        
        leaderboard = []
        for rank, entry in enumerate(entries, 1):
            mins = getattr(entry, minutes_field)
            hours = mins // 60
            remaining_mins = mins % 60
            rank_change = (entry.previous_rank - rank) if entry.previous_rank > 0 else 0
            
            leaderboard.append({
                'rank': rank,
                'username': entry.user.username,
                'profile_picture': _get_profile_pic(entry.user),
                'hours': hours,
                'minutes': remaining_mins,
                'total_minutes': mins,
                'rank_change': rank_change,
                'is_self': False,
            })
        
        cache.set(cache_key, leaderboard, 120)
    
    # Patch is_self and get user_entry only if authenticated
    if user:
        leaderboard = [
            {**e, 'is_self': e['username'] == user.username}
            for e in leaderboard
        ]
        user_entry = _get_user_rank_info(user, period)
    else:
        user_entry = None
    
    return JsonResponse({'success': True, 'leaderboard': leaderboard, 'user_entry': user_entry})


def _get_profile_pic(user):
    if hasattr(user, 'profile_picture') and user.profile_picture:
        return f'https://bomby.us{user.profile_picture.url}'
    return None


def _get_user_rank_info(user, period):
    """Get current user's leaderboard status"""
    try:
        entry = LeaderboardEntry.objects.get(user=user)
    except LeaderboardEntry.DoesNotExist:
        return {'opted_in': False, 'rank': 0, 'total_minutes': 0}
    
    if not entry.opted_in:
        return {'opted_in': False, 'rank': 0, 'total_minutes': 0}
    
    minutes_field = {
        'week': 'weekly_stream_minutes',
        'month': 'monthly_stream_minutes',
        'all': 'total_stream_minutes',
    }.get(period, 'total_stream_minutes')
    
    user_mins = getattr(entry, minutes_field)
    
    # Calculate rank (matches sort: most minutes, then most recent sync)
    from django.db.models import Q
    rank = (
        LeaderboardEntry.objects
        .filter(opted_in=True)
        .filter(
            Q(**{f'{minutes_field}__gt': user_mins}) |
            Q(**{f'{minutes_field}': user_mins}, last_synced__gt=entry.last_synced)
        )
        .count() + 1
    )
    
    hours = user_mins // 60
    remaining = user_mins % 60
    rank_change = (entry.previous_rank - rank) if entry.previous_rank > 0 else 0
    
    return {
        'opted_in': True,
        'rank': rank,
        'hours': hours,
        'minutes': remaining,
        'total_minutes': user_mins,
        'rank_change': rank_change,
        'last_synced': entry.last_synced.isoformat() if entry.last_synced else None,
    }


@csrf_exempt
def fuzeobs_leaderboard_optin(request):
    """POST - opt in to leaderboard (creates entry + syncs hours)"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    user = _get_user(request)
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    entry, created = LeaderboardEntry.objects.get_or_create(user=user)
    entry.opted_in = True
    
    # Sync hours on opt-in
    total, weekly, monthly = _sync_user_hours(user)
    entry.total_stream_minutes = total
    entry.weekly_stream_minutes = weekly
    entry.monthly_stream_minutes = monthly
    entry.last_synced = timezone.now()
    entry.save()
    
    # Invalidate cache
    for period in ('week', 'month', 'all'):
        cache.delete(f'leaderboard:{period}')
    
    return JsonResponse({'success': True, 'total_minutes': total, 'weekly_minutes': weekly, 'monthly_minutes': monthly})


@csrf_exempt
def fuzeobs_leaderboard_optout(request):
    """POST - opt out of leaderboard"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    user = _get_user(request)
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    try:
        entry = LeaderboardEntry.objects.get(user=user)
        entry.opted_in = False
        entry.save()
    except LeaderboardEntry.DoesNotExist:
        pass
    
    for period in ('week', 'month', 'all'):
        cache.delete(f'leaderboard:{period}')
    
    return JsonResponse({'success': True})


@csrf_exempt
def fuzeobs_leaderboard_sync(request):
    """POST - manually refresh your hours"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    user = _get_user(request)
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    try:
        entry = LeaderboardEntry.objects.get(user=user, opted_in=True)
    except LeaderboardEntry.DoesNotExist:
        return JsonResponse({'error': 'Not opted in'}, status=400)
    
    # Rate limit: once per 5 minutes
    if entry.last_synced and (timezone.now() - entry.last_synced).total_seconds() < 300:
        return JsonResponse({'error': 'Sync available every 5 minutes', 'retry_after': 300}, status=429)
    
    # Store current rank as previous before re-sync
    minutes_field = 'total_stream_minutes'
    current_mins = entry.total_stream_minutes
    current_rank = (
        LeaderboardEntry.objects
        .filter(opted_in=True, total_stream_minutes__gt=current_mins)
        .count() + 1
    )
    entry.previous_rank = current_rank
    entry.save(update_fields=['previous_rank'])
    
    total, weekly, monthly = _sync_user_hours(user)
    entry.total_stream_minutes = total
    entry.weekly_stream_minutes = weekly
    entry.monthly_stream_minutes = monthly
    entry.last_synced = timezone.now()
    entry.save()
    
    for period in ('week', 'month', 'all'):
        cache.delete(f'leaderboard:{period}')
    
    return JsonResponse({
        'success': True,
        'total_minutes': total,
        'weekly_minutes': weekly,
        'monthly_minutes': monthly,
    })


@csrf_exempt
def fuzeobs_leaderboard_cron_sync(request):
    """Called by Cloud Scheduler every 24h to sync all opted-in users"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)

    cron_secret = request.headers.get('X-Cron-Secret', '')
    expected = os.environ.get('CRON_SECRET', '')
    if not expected or not hmac.compare_digest(cron_secret, expected):
        return JsonResponse({'error': 'Forbidden'}, status=403)

    entries = LeaderboardEntry.objects.filter(opted_in=True).select_related('user')
    synced = 0
    errors = 0

    # Snapshot current ranks BEFORE syncing new hours
    ranked_entries = (
        LeaderboardEntry.objects
        .filter(opted_in=True)
        .order_by('-total_stream_minutes', 'user__username')
    )
    for rank, entry in enumerate(ranked_entries, 1):
        if entry.previous_rank != rank:
            entry.previous_rank = rank
            entry.save(update_fields=['previous_rank'])

    # Now sync hours (ranks will shift based on new data)
    for entry in entries:
        try:
            total, weekly, monthly = _sync_user_hours(entry.user)
            entry.total_stream_minutes = total
            entry.weekly_stream_minutes = weekly
            entry.monthly_stream_minutes = monthly
            entry.last_synced = timezone.now()
            entry.save()
            synced += 1
        except Exception as e:
            print(f'[LEADERBOARD CRON] Error {entry.user.username}: {e}')
            errors += 1

    for period in ('week', 'month', 'all'):
        cache.delete(f'leaderboard:{period}')

    return JsonResponse({'success': True, 'synced': synced, 'errors': errors})