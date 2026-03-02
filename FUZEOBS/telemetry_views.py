"""Telemetry views for FuzeOBS anonymous analytics"""
import json
from datetime import timedelta
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.utils import timezone
from django.db.models import Count

from .models import TelemetryEvent


@csrf_exempt
@require_POST
def fuzeobs_telemetry_ingest(request):
    """Unauthenticated endpoint for anonymous telemetry batches."""
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    events = body.get('events', [])
    if not events or len(events) > 100:
        return JsonResponse({'error': 'events must be 1-100 items'}, status=400)

    objects = []
    for e in events:
        device_id = (e.get('device_id') or '')[:32]
        event_name = (e.get('event') or '')[:100]
        if not device_id or not event_name:
            continue
        objects.append(TelemetryEvent(
            device_id=device_id,
            session_id=(e.get('session_id') or '')[:32],
            event=event_name,
            properties=e.get('properties') or {},
            app_version=(e.get('app_version') or '')[:20],
            os_name=(e.get('os') or '')[:20],
            os_version=(e.get('os_version') or '')[:50],
            client_timestamp=e.get('timestamp'),
        ))

    if objects:
        TelemetryEvent.objects.bulk_create(objects, ignore_conflicts=True)

    return JsonResponse({'ok': True, 'ingested': len(objects)})


@require_GET
def fuzeobs_telemetry_dashboard(request):
    """JSON dashboard for /analytics page. Staff only."""
    if not request.user.is_staff:
        return JsonResponse({'error': 'Forbidden'}, status=403)

    days = min(int(request.GET.get('days', 7)), 90)
    since = timezone.now() - timedelta(days=days)
    qs = TelemetryEvent.objects.filter(created_at__gte=since)

    unique_devices = qs.values('device_id').distinct().count()
    unique_sessions = qs.values('session_id').distinct().count()
    total_events = qs.count()

    # Session durations
    session_durations = list(
        qs.filter(event='session_end')
        .values_list('properties__duration_seconds', flat=True)
    )
    avg_duration = sum(d for d in session_durations if d) / max(len(session_durations), 1)

    # Daily active devices
    from django.db.models.functions import TruncDate
    daily_active = list(
        qs.annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(devices=Count('device_id', distinct=True))
        .order_by('day')
        .values('day', 'devices')
    )

    # Top events
    top_events = list(
        qs.values('event').annotate(count=Count('id')).order_by('-count')[:20]
    )

    # Setup funnel
    funnel_events = [
        'app_launched', 'system_detected', 'config_generated',
        'obs_connected', 'widget_configured', 'platform_connected',
        'scene_injected',
    ]
    funnel = {evt: qs.filter(event=evt).values('device_id').distinct().count() for evt in funnel_events}

    # OS breakdown
    os_breakdown = list(
        qs.values('os_name').annotate(count=Count('device_id', distinct=True)).order_by('-count')
    )

    # Version breakdown
    version_breakdown = list(
        qs.values('app_version').annotate(count=Count('device_id', distinct=True)).order_by('-count')
    )

    # Tab views
    tab_views = list(
        qs.filter(event='tab_viewed')
        .values('properties__tab')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Login funnel
    login_funnel = {
        'shown': qs.filter(event='login_shown').values('device_id').distinct().count(),
        'dismissed': qs.filter(event='login_dismissed').values('device_id').distinct().count(),
        'completed': qs.filter(event='login_completed').values('device_id').distinct().count(),
    }

    # Recent errors
    recent_errors = list(
        qs.filter(event='error')
        .order_by('-created_at')
        .values('device_id', 'properties', 'app_version', 'os_name', 'created_at')[:20]
    )

    return JsonResponse({
        'period_days': days,
        'unique_devices': unique_devices,
        'unique_sessions': unique_sessions,
        'total_events': total_events,
        'avg_session_seconds': round(avg_duration, 1),
        'daily_active': [{'day': str(d['day']), 'devices': d['devices']} for d in daily_active],
        'top_events': top_events,
        'funnel': funnel,
        'os_breakdown': os_breakdown,
        'version_breakdown': version_breakdown,
        'tab_views': tab_views,
        'login_funnel': login_funnel,
        'recent_errors': [{**e, 'created_at': str(e['created_at'])} for e in recent_errors],
    })