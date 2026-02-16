from django.conf import settings
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
import anthropic
import os
import json
import uuid
from datetime import date
from django.core.cache import cache
import re
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from .models import *
from ACCOUNTS.models import Conversation, Message
from decimal import Decimal
from google.cloud import storage
import hmac
import hashlib
import time
from functools import wraps
from django.contrib.auth.decorators import login_required
from .widget_generator import generate_widget_html
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import random
from .twitch import send_alert
from .youtube import start_youtube_listener, stop_youtube_listener
from .kick import start_kick_listener, stop_kick_listener
from .facebook import start_facebook_listener, stop_facebook_listener
from .tiktok import start_tiktok_listener, stop_tiktok_listener
import requests
import base64
from .twitch_chat import start_twitch_chat
from .kick_chat import start_kick_chat
from .facebook_chat import start_facebook_chat
from .utils.email_utils import send_fuzeobs_invoice_email
from .views_helpers import (
    get_client_ip, activate_fuzeobs_user, update_active_session,
    cleanup_old_sessions, send_widget_refresh
)

# Website Imports
from django.shortcuts import redirect
from django.urls import reverse
from django.db.models import Count, Sum, Avg, Q, Max, OuterRef, Subquery, IntegerField, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
import secrets
from django.contrib.auth import login
from .models import WidgetConfig

# Payements
from django.views.decorators.http import require_POST
from django.contrib import messages
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY

User = get_user_model()

# ====== VERSION / UPDATES ======

FUZEOBS_VERSION = '0.11.0'

@require_http_methods(["GET"])
def fuzeobs_check_update(request):
    platform = request.GET.get('platform', 'windows')
    
    urls = {
        'windows': 'https://storage.googleapis.com/fuzeobs-public/fuzeobs-installer/FuzeOBS-Installer.exe',
        'darwin': 'https://storage.googleapis.com/fuzeobs-public/fuzeobs-installer/FuzeOBS-Installer.dmg',
        'linux': 'https://storage.googleapis.com/fuzeobs-public/fuzeobs-installer/FuzeOBS-Installer.deb',
    }
    
    return JsonResponse({
        'version': FUZEOBS_VERSION,
        'download_url': urls.get(platform, urls['windows']),
        'changelog': 'Welcome Page Added',
        'mandatory': False
    })


FUZEOBS_PATCH_NOTES = {
    'version': FUZEOBS_VERSION,
    'changelog': 'Welcome Page Added, App Styling Updates',
    'notes': [
        '- Added Welcome Page with multiple features',
        '- Streaming Tip of the Day',
        '- Personalized Schedule Maker',
        '- Stream Recap + Analytic Info',
        '- Collab Finder to make contacts with other content creators',
        '- Leaderboard to rank users by streaming hours',
    ]
}

@require_http_methods(["GET"])
def fuzeobs_patch_notes(request):
    return JsonResponse(FUZEOBS_PATCH_NOTES)


class SecureAuth:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode()
    
    def create_signed_token(self, user_id: int, tier: str) -> str:
        timestamp = int(time.time())
        message = f"{user_id}:{tier}:{timestamp}"
        signature = hmac.new(self.secret_key, message.encode(), hashlib.sha256).hexdigest()
        return f"{message}:{signature}"
    
    def verify_token(self, token: str) -> dict:
        try:
            parts = token.split(':')
            if len(parts) != 4:
                return {'valid': False}
            user_id, tier, timestamp, signature = parts
            message = f"{user_id}:{tier}:{timestamp}"
            expected = hmac.new(self.secret_key, message.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return {'valid': False}
            if int(time.time()) - int(timestamp) > 2592000:  # 30 days
                return {'valid': False}
            return {'valid': True, 'user_id': int(user_id), 'tier': tier}
        except:
            return {'valid': False}

auth_manager = SecureAuth(os.environ.get('FUZEOBS_SECRET_KEY', os.environ.get('DJANGO_SECRET_KEY')))

def require_tier(min_tier):
    """Decorator enforcing tier requirements SERVER-SIDE"""
    tier_hierarchy = {'free': 0, 'pro': 1, 'lifetime': 2}
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return JsonResponse({'error': 'No token'}, status=401)
            token = auth_header.replace('Bearer ', '')
            verification = auth_manager.verify_token(token)
            if not verification['valid']:
                return JsonResponse({'error': 'Invalid token'}, status=401)
            try:
                user = User.objects.get(id=verification['user_id'])
                if user.fuzeobs_tier != verification['tier']:
                    return JsonResponse({'error': 'Token mismatch'}, status=401)
            except User.DoesNotExist:
                return JsonResponse({'error': 'User not found'}, status=401)
            if tier_hierarchy.get(user.fuzeobs_tier, 0) < tier_hierarchy.get(min_tier, 0):
                return JsonResponse({'error': 'Insufficient tier', 'required': min_tier}, status=403)
            request.fuzeobs_user = user
            return func(request, *args, **kwargs)
        return wrapper
    return decorator

def get_user_from_token(token):
    """Secure token verification - returns user regardless of tier change"""
    verification = auth_manager.verify_token(token)
    if not verification['valid']:
        return None
    try:
        user = User.objects.get(id=verification['user_id'])
        # Store original token tier for checking later
        user._token_tier = verification['tier']
        return user
    except User.DoesNotExist:
        return None

# ===== VALIDATORS =====
def validate_username(username):
    """Validate username matches Django rules"""
    if not username:
        raise ValidationError("Username is required")
    if len(username) > 20:
        raise ValidationError("Username must be 20 characters or fewer")
    if not re.match(r'^[\w.@+-]+$', username):
        raise ValidationError("Username can only contain letters, digits and @/./+/-/_ characters")
    from ACCOUNTS.validators import contains_profanity
    if contains_profanity(username):
        raise ValidationError("Username contains inappropriate language")
    return username

# ===== AUTHENTICATION ENDPOINTS =====

@csrf_exempt
def fuzeobs_signup(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    data = json.loads(request.body)
    email = data.get('email')
    username = data.get('username')
    password = data.get('password')
    
    try:
        validate_username(username)
    except ValidationError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    if len(password) < 8:
        return JsonResponse({'success': False, 'error': 'Password must be at least 8 characters'}, status=400)
    
    if User.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'Email already registered'}, status=400)
    
    if User.objects.filter(username=username).exists():
        return JsonResponse({'success': False, 'error': 'Username already taken'}, status=400)
    
    user = User.objects.create_user(username=username, email=email, password=password)
    user.fuzeobs_tier = 'free'
    session_id = data.get('session_id')
    activate_fuzeobs_user(user)
    update_active_session(user, session_id, get_client_ip(request))
    user.save()

    # Track signup activity
    UserActivity.objects.create(
        user=user,
        activity_type='signup',
        source='app'
    )

    token = auth_manager.create_signed_token(user.id, 'free')
    
    token = auth_manager.create_signed_token(user.id, 'free')
    return JsonResponse({
        'success': True,
        'token': token,
        'tier': 'free',
        'email': user.email,
        'username': user.username
    })

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_login(request):
    try:
        # Rate limiting by IP
        ip = get_client_ip(request)
        attempts_key = f'fuzeobs_login_attempts_{ip}'
        attempts = cache.get(attempts_key, 0)
        
        if attempts >= 5:
            return JsonResponse({
                'success': False, 
                'error': 'Too many login attempts. Please try again in 15 minutes.'
            }, status=429)
        
        data = json.loads(request.body)
        email_or_username = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email_or_username or not password:
            cache.set(attempts_key, attempts + 1, 900)  # 15 min
            return JsonResponse({'success': False, 'error': 'Email/username and password required'})
        
        user = None
        if '@' in email_or_username:
            try:
                user_obj = User.objects.get(email=email_or_username)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        else:
            user = authenticate(username=email_or_username, password=password)
        
        if not user:
            try:
                user_obj = User.objects.get(email=email_or_username)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        
        if user:
            cache.delete(attempts_key)
            
            # Track login activity
            UserActivity.objects.create(
                user=user,
                activity_type='login',
                source='app'
            )

            session_id = data.get('session_id')
            activate_fuzeobs_user(user)
            update_active_session(user, session_id, get_client_ip(request))
            
            token = auth_manager.create_signed_token(user.id, user.fuzeobs_tier)
            return JsonResponse({
                'success': True,
                'token': token,
                'email': user.email,
                'username': user.username,
                'tier': user.fuzeobs_tier,
                'profile_picture': f'https://bomby.us{user.profile_picture.url}' if user.profile_picture else None
            })
        else:
            # Failed login - increment attempts
            cache.set(attempts_key, attempts + 1, 900)  # 15 min
            return JsonResponse({'success': False, 'error': 'Invalid credentials'})
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
def fuzeobs_google_auth_init(request):
    """Initiate Google OAuth flow for FuzeOBS"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    data = json.loads(request.body)
    session_id = data.get('session_id')
    
    if not session_id:
        return JsonResponse({'error': 'session_id required'}, status=400)
    
    # Generate state token and store session mapping
    state_token = secrets.token_urlsafe(32)
    cache.set(f'fuzeobs_oauth_state_{state_token}', session_id, timeout=600)  # 10 min
    
    # Build Google OAuth URL
    auth_url = f"https://bomby.us/accounts/google/login/?next=https://bomby.us/fuzeobs/google-callback?state={state_token}"
    
    return JsonResponse({
        'success': True,
        'auth_url': auth_url,
        'state': state_token
    })

@csrf_exempt
def fuzeobs_google_callback(request):
    """Handle Google OAuth callback for FuzeOBS"""
    state = request.GET.get('state')
    
    if not state:
        return HttpResponse("Invalid state", status=400)
    
    session_id = cache.get(f'fuzeobs_oauth_state_{state}')
    if not session_id:
        return HttpResponse("State expired or invalid", status=400)
    
    # User is now authenticated via allauth
    if not request.user.is_authenticated:
        return HttpResponse("Authentication failed", status=401)
    
    user = request.user
    
    # FIX: Use signed token instead of random token
    token = auth_manager.create_signed_token(user.id, user.fuzeobs_tier)
    
    # Store token for session retrieval
    cache.set(f'fuzeobs_google_token_{session_id}', {
        'token': token,
        'email': user.email,
        'username': user.username,
        'tier': user.fuzeobs_tier
    }, timeout=120)  # 2 minutes to retrieve
    
    # Update user's FuzeOBS activation
    activate_fuzeobs_user(user)
    update_active_session(user, session_id, get_client_ip(request))
    
    # Track activity
    UserActivity.objects.create(
        user=user,
        activity_type='login',
        source='app'
    )
    
    return render(request, 'FUZEOBS/google_success.html')


@csrf_exempt
def fuzeobs_google_auth_poll(request):
    """Poll for completed Google OAuth"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    data = json.loads(request.body)
    session_id = data.get('session_id')
    
    if not session_id:
        return JsonResponse({'error': 'session_id required'}, status=400)
    
    # Check if auth completed
    auth_data = cache.get(f'fuzeobs_google_token_{session_id}')
    
    if auth_data:
        cache.delete(f'fuzeobs_google_token_{session_id}')
        
        return JsonResponse({
            'success': True,
            'completed': True,
            'token': auth_data['token'],
            'email': auth_data['email'],
            'username': auth_data['username'],
            'tier': auth_data['tier']
        })
    
    return JsonResponse({
        'success': True,
        'completed': False
    })

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def fuzeobs_verify(request):
    if request.method == "OPTIONS":
        return JsonResponse({'status': 'ok'})
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'valid': False, 'authenticated': False, 'reachable': True})
    
    token = auth_header.replace('Bearer ', '')
    if token == 'none':
        return JsonResponse({'valid': False, 'authenticated': False, 'reachable': True})
    
    user = get_user_from_token(token)
    if user:
        session_id = request.META.get('HTTP_X_SESSION_ID')
        if session_id:
            update_active_session(user, session_id, get_client_ip(request))
        
        # Check if 3-month plan has expired
        if user.fuzeobs_tier == 'pro':
            try:
                sub = FuzeOBSSubscription.objects.get(user=user, is_active=True)
                if sub.expires_at and sub.expires_at <= timezone.now():
                    user.fuzeobs_tier = 'free'
                    user.save()
                    sub.is_active = False
                    sub.plan_type = 'free'
                    sub.save()
                    TierChange.objects.create(
                        user=user,
                        from_tier='pro',
                        to_tier='free',
                        reason='3month_expired'
                    )
            except FuzeOBSSubscription.DoesNotExist:
                pass
        
        response_data = {
            'valid': True,
            'authenticated': True,
            'tier': user.fuzeobs_tier,
            'email': user.email,
            'username': user.username,
            'profile_picture': f'https://bomby.us{user.profile_picture.url}' if user.profile_picture else None,
            'reachable': True
        }
        
        # Issue new token if tier changed
        token_tier = getattr(user, '_token_tier', None)
        if token_tier and user.fuzeobs_tier != token_tier:
            response_data['new_token'] = auth_manager.create_signed_token(user.id, user.fuzeobs_tier)
        
        return JsonResponse(response_data)
    
    return JsonResponse({'valid': False, 'authenticated': False, 'reachable': True})

# ===== QUICK START =====

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_quickstart_dismiss(request):
    """Dismiss quick-start modal for logged-in user"""
    user = request.fuzeobs_user
    user.quickstart_dismissed = True
    user.save()
    return JsonResponse({'success': True})

@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuzeobs_quickstart_check(request):
    """Check if user has dismissed quick-start modal"""
    user = request.fuzeobs_user
    return JsonResponse({'dismissed': user.quickstart_dismissed})

# ===== TEMPLATES =====

@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_list_templates(request):
    """List available templates based on user tier"""
    auth_header = request.headers.get('Authorization', '')
    user = None
    
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        user = get_user_from_token(token)
    
    templates = [
        {'id': 'simple', 'name': 'Simple Stream', 'tier': 'free'},
        {'id': 'gaming', 'name': 'Gaming Stream', 'tier': 'free'},
    ]
    
    if user and user.fuzeobs_tier in ['pro', 'lifetime']:
        templates.extend([
            {'id': 'just-chatting', 'name': 'Just Chatting', 'tier': 'premium'},
            {'id': 'tutorial', 'name': 'Desktop Tutorial', 'tier': 'premium'},
            {'id': 'podcast', 'name': 'Podcast', 'tier': 'premium'},
        ])
    
    return JsonResponse({'templates': templates})

@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_get_template(request, template_id):
    auth_header = request.headers.get('Authorization', '')
    user = None
    
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        user = get_user_from_token(token)
    
    free_templates = ['simple', 'gaming']
    premium_templates = ['just-chatting', 'tutorial', 'podcast']
    
    if template_id in premium_templates:
        if not user or user.fuzeobs_tier not in ['pro', 'lifetime']:
            return JsonResponse({'error': 'Premium required'}, status=403)
    
    if template_id not in free_templates + premium_templates:
        return JsonResponse({'error': 'Template not found'}, status=404)
    
    try:
        client = storage.Client()
        bucket = client.bucket('bomby-user-uploads')
        blob = bucket.blob(f'fuzeobs-templates/{template_id}.json')
        template_data = json.loads(blob.download_as_text())
        return JsonResponse(template_data)
    except:
        return JsonResponse({'error': 'Template not found'}, status=404)

@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_get_background(request, background_id):
    from django.http import HttpResponse
    try:
        client = storage.Client()
        bucket = client.bucket('bomby-user-uploads')
        blob = bucket.blob(f'fuzeobs-templates/scene-backgrounds/{background_id}.png')
        image_data = blob.download_as_bytes()
        return HttpResponse(image_data, content_type='image/png')
    except:
        return JsonResponse({'error': 'Background not found'}, status=404)

# ===== AI CHAT =====

@csrf_exempt
def fuzeobs_ai_chat(request):
    """AI chat streaming endpoint with tier-based rate limiting and file upload"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    # Get user from token (allow anonymous)
    auth_header = request.headers.get('Authorization', '')
    user = None
    tier = 'free'
    
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        user = get_user_from_token(token)
        if user:
            tier = user.fuzeobs_tier
            user_id = f'user_{user.id}'
        else:
            user_id = f'anon_{get_client_ip(request)}'
    else:
        user_id = f'anon_{get_client_ip(request)}'
    today = date.today().isoformat()
    daily_key = f'fuzeobs_daily_{user_id}_{today}'
    daily_count = cache.get(daily_key, 0)
    
    # Tier limits
    if tier in ['pro', 'lifetime']:
        rate_key = f'fuzeobs_pro_rate_{user_id}'
        rate_count = cache.get(rate_key, 0)
        
        if rate_count >= 100:
            def limit_msg():
                message_data = {'text': '**Rate Limit Reached**\n\nYou\'ve used 100 messages in 5 hours. Please wait before sending more.'}
                yield "data: " + json.dumps(message_data) + "\n\n"
                yield "data: [DONE]\n\n"
            response = StreamingHttpResponse(limit_msg(), content_type='text/event-stream; charset=utf-8')
            response['Cache-Control'] = 'no-cache'            
            return response
        
        cache.set(rate_key, rate_count + 1, 18000)
        model = "claude-opus-4-5-20251101"
        
    else:  # free tier
        if daily_count >= 5:
            def limit_msg():
                message_data = {'text': '**Daily Limit Reached**\n\nYou\'ve used your 5 free messages today. Upgrade to Pro for unlimited access.'}
                yield "data: " + json.dumps(message_data) + "\n\n"
                yield "data: [DONE]\n\n"
            response = StreamingHttpResponse(limit_msg(), content_type='text/event-stream; charset=utf-8')
            response['Cache-Control'] = 'no-cache'            
            return response
        
        cache.set(daily_key, daily_count + 1, 86400)
        model = "claude-haiku-4-5-20251001"
    
    # Anti-spam: 10 messages per minute
    spam_key = f'fuzeobs_spam_{user_id}'
    spam_count = cache.get(spam_key, 0)
    if spam_count >= 10:
        def spam_msg():
            message_data = {'text': '**Slow Down**\n\nMaximum 10 messages per minute. Please wait a moment.'}
            yield "data: " + json.dumps(message_data) + "\n\n"
            yield "data: [DONE]\n\n"
        response = StreamingHttpResponse(spam_msg(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'        
        return response
    cache.set(spam_key, spam_count + 1, 60)
    
    # Handle both JSON and FormData
    import base64
    
    if request.content_type and 'multipart/form-data' in request.content_type:
        files = request.FILES.getlist('files')[:5]
        message = request.POST.get('message', '').strip()
        style = request.POST.get('style', 'normal')
    else:
        files = []
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        style = data.get('style', 'normal')
    
    if not message and not files:
        return JsonResponse({'error': 'Empty message'}, status=400)
    
    if message:
        off_topic_keywords = [
            'homework', 'essay', 'assignment', 'math problem', 'solve for', 
            'write code', 'python script', 'javascript function', 'sql query',
            'history of', 'who was', 'biography', 'recipe', 'medical advice'
        ]
        
        if any(keyword in message.lower() for keyword in off_topic_keywords):
            def off_topic_message():
                message_data = {'text': '**Off-Topic Query Detected**\n\nThis AI assistant is specifically designed for OBS Studio and streaming questions only.'}
                yield "data: " + json.dumps(message_data) + "\n\n"
                yield "data: [DONE]\n\n"
            
            response = StreamingHttpResponse(off_topic_message(), content_type='text/event-stream; charset=utf-8')
            response['Cache-Control'] = 'no-cache'            
            return response
    
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    # Fetch platform data for logged-in users (cached, fast)
    platform_context = ""
    if user:
        try:
            from .recaps import _fetch_all_recaps, FOLLOWER_FETCHERS
            
            connections = PlatformConnection.objects.filter(user=user)
            connected = [c.platform for c in connections]
            
            if connected:
                parts = [f"Connected platforms: {', '.join(connected)}"]
                
                # Follower counts (cached 5 min)
                follower_cache_key = f'followers:{user.id}'
                follower_data = cache.get(follower_cache_key)
                if not follower_data:
                    followers = {}
                    total = 0
                    for conn in connections:
                        fetcher = FOLLOWER_FETCHERS.get(conn.platform)
                        if fetcher:
                            try:
                                count = fetcher(conn)
                                followers[conn.platform] = count
                                total += count
                            except Exception:
                                followers[conn.platform] = 0
                    follower_data = {'total': total, 'platforms': followers}
                    cache.set(follower_cache_key, follower_data, 300)
                
                if follower_data.get('platforms'):
                    follower_parts = [f"{p}: {c}" for p, c in follower_data['platforms'].items() if c > 0]
                    if follower_parts:
                        parts.append(f"Follower counts — {', '.join(follower_parts)} (Total: {follower_data['total']})")
                
                # Recent streams (cached 5 min)
                recap_cache_key = f'recaps:{user.id}'
                recaps = cache.get(recap_cache_key)
                if recaps is None:
                    try:
                        recaps = _fetch_all_recaps(user)
                        cache.set(recap_cache_key, recaps, 300)
                    except Exception:
                        recaps = []
                
                if recaps:
                    parts.append("Recent streams:")
                    for r in recaps[:5]:
                        line = f"  - [{r.get('platform','?').upper()}] \"{r.get('title','Untitled')}\" — {r.get('duration','?')}"
                        if r.get('views'):
                            line += f", {r['views']} views"
                        if r.get('peak_viewers'):
                            line += f", peak {r['peak_viewers']} viewers"
                        if r.get('category'):
                            line += f", category: {r['category']}"
                        if r.get('date'):
                            line += f" ({r['date'][:10]})"
                        parts.append(line)
                
                platform_context = "\n".join(parts)
        except Exception as e:
            print(f"[AI] Platform data fetch error: {e}")
            platform_context = ""
    
    start_time = time.time()
    input_tokens = 0
    output_tokens = 0
    success = True
    error_msg = ""
    
    def generate():
        nonlocal input_tokens, output_tokens, success, error_msg
        try:
            content = []
            
            for file in files:
                ext = file.name.lower().split('.')[-1]
                if ext in ['jpg', 'jpeg', 'png']:
                    encoded = base64.b64encode(file.read()).decode('utf-8')
                    content.append({
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': f'image/{"jpeg" if ext == "jpg" else ext}',
                            'data': encoded
                        }
                    })
                elif ext == 'json':
                    file_content = file.read().decode('utf-8')
                    content.append({
                        'type': 'text',
                        'text': f"[Uploaded file: {file.name}]\n```json\n{file_content}\n```"
                    })
            
            if message:
                content.append({'type': 'text', 'text': message})
            
            messages_content = content if files else message
            
            style_instructions = {
                'normal': '- Start with a direct answer\n- Provide exact settings when applicable',
                'concise': '- Be extremely brief\n- Only essential information',
                'explanatory': '- Detailed step-by-step\n- Include background context',
                'formal': '- Professional technical language\n- Structured format',
                'learning': '- Break down for beginners\n- Use analogies',
                'sassy': '- Be playfully sassy and sarcastic - eye rolls, dramatic sighs, witty comebacks\n- Use phrases like "Oh honey...", "Bless your heart", "Let me spell it out..."\n- Roast common mistakes gently\n- Still provide the correct, helpful answer after the sass'
            }
            
            style_prompt = style_instructions.get(style, style_instructions['normal'])
            
            with client.messages.stream(
                model=model,
                max_tokens=4000,
                system=[
                    {
                        "type": "text",
                        "text": """You are the FuzeOBS AI Assistant - an expert in OBS Studio, streaming, and broadcast technology.

Core Guidelines:
- ONLY answer questions about OBS, streaming, encoding, hardware for streaming, and related topics
- Provide specific settings, numbers, and exact configuration steps
- Consider the user's hardware when giving recommendations
- Be direct and technical - users want actionable solutions
- If hardware specs are provided, optimize recommendations for that setup (If you don't know it, ask the user to scan their hardware in the Detection Tab)
- When analyzing images or files, be specific about what you see and provide detailed guidance
- You may have the user's live platform data (connected platforms, follower counts, recent streams). Use this to personalize advice — reference their actual categories, stream durations, viewer counts, and growth trends when relevant. If you don't have their data, suggest they connect platforms on the Welcome Tab.

FuzeOBS Tiers:
- There are 3 Tiers of FuzeOBS (Free/Pro/Lifetime)
- The Pro/Lifetime tiers include unlimited AI (on a smarter model) messages, Advanced Output OBS settings, Benchmarking, more detailed scene collections, and more configuration profiles
- The Free tier has 5 AI messages a day (on a lower-performing model), Simple Output OBS Settings, No Benchmarking, Simple Scene collections, and 1 configuration profile
- If a Free tier user is requesting Pro/Lifetime features or assistance, recommend the Pro tier LIGHTLY as means of assistance

User Accounts:
- FuzeOBS accounts are managed through bomby.us (profile pictures, usernames, etc.)
- Users can edit their profile at bomby.us/accounts/edit-profile
- Platform connections (Twitch, YouTube, Kick, Facebook, TikTok) are managed within the FuzeOBS app on the Welcome Tab

FuzeOBS Tabs - Detailed Guide:

Welcome Tab (Home):
- Streaming Tip of the Day: Random rotating tips about streaming with categories (Audio, Video, Growth, Engagement, etc.). Click SHUFFLE for a new tip.
- Platform Connections: Connect/disconnect streaming platforms (Twitch, YouTube, Kick, Facebook, TikTok). Shows X/5 connected. Required for widgets, leaderboard, and recaps.
- Go Live Checklist: Per-platform pre-stream checklist. Check off items before going live. Different steps for each platform.
- Stream Countdown: Set a countdown timer for your next stream. Two modes:
  * One-Time: Set a specific date/time, optional title, select which platforms.
  * Recurring: Set a weekly schedule with day-of-week selection, time, title, and platforms. Shows countdown to next occurrence.
- Stream Recaps: View recent streams, VODs, and clips from connected platforms. Two sub-tabs:
  * Recent: Shows past broadcasts with duration, views, peak viewers, category.
  * Stats: Aggregated streaming statistics.
  * Supported: Twitch (VODs, requires Affiliate/Partner for VOD storage), YouTube (past live broadcasts), Kick (past broadcasts with category), Facebook (recent live videos with views).
  * Not supported: TikTok (no past broadcast API data).
- Collab Finder: Find streaming partners and collaboration opportunities.
  * Browse posts by category: Duo Queue, Group Stream, Podcast/Talk Show, Tournament, Charity Event, Creative Collab, IRL Stream, Other.
  * Filter by category and platform.
  * Create posts with: title, description, category, platforms, tags (up to 5), collab size (Duo, Small Group 3-5, Large Group 6+, Any Size), availability/timezone.
  * Express interest in posts, message other users about collabs.
  * Edit/delete your own posts. View "My Posts" separately.
- Leaderboard: Stream Hours ranking of FuzeOBS users.
  * Opt-in/opt-out (voluntary participation).
  * Periods: This Week, This Month, All Time.
  * Ranks by total stream hours across connected platforms. Hours sync automatically every 24 hours.
  * Supported: Twitch (VOD durations, requires Affiliate/Partner), YouTube (past live broadcast durations), Kick (past broadcast durations).
  * Not supported: Facebook (no reliable stream duration data), TikTok (no past broadcast API data).
  * Shows rank changes (up/down/stable).
- Patch Notes: Displays current version number and latest release notes/changelog.
- Review: Users can leave a review of FuzeOBS (platform, 1-5 star rating, text up to 300 chars). Reviews need approval before appearing on the main page. Users can edit their existing review.

Tab 01 - System Detection: Scans hardware (CPU, GPU, RAM, monitors, storage). User clicks SCAN to detect. Shows performance ratings (A+ to C). Select audio input/output and webcam from dropdowns. Identifies bottlenecks with warnings.

Tab 02 - Configuration: Generates optimized OBS settings. Select use case, platform, quality, output mode (Simple/Advanced), scene template, camera resolution. Click GENERATE to create config. Pro users unlock Advanced mode and extra templates.

Tab 03 - Optimization: Review generated settings and apply to OBS via WebSocket. Enter OBS WebSocket password (6+ chars). Ensure OBS is running. Click APPLY TO OBS to push settings. Shows connection status and device assignments.

Tab 04 - Audio I/O: Displays audio track configuration with sample rate, channels, bitrate. View global audio settings and track assignments. Recommended filters: Noise Suppression, Noise Gate, Compressor.

Tab 05 - Scene Setup: Browse templates (Simple Stream, Gaming, Just Chatting, Tutorial, Podcast). Premade JSON are auto-imported into OBS via Tab 03.

Tab 06 - Widgets & Tools: Create stream widgets with multi-platform support (Twitch, YouTube, Kick, Facebook, TikTok). Connect platforms first, select widget type, customize settings, copy Browser Source URL to OBS. All widgets have an AI CSS Styler that can generate custom CSS via chat.

Tab 07 - Plugins: Discover popular OBS plugins with descriptions and difficulty ratings. Access download links and installation guides.

Tab 08 - Documentation: Comprehensive OBS learning resources. Search through Basics, Sources, Audio, Advanced Features, Streaming, Recording, Troubleshooting.

Tab 09 - Performance Monitor: Real-time CPU/GPU usage, memory, encoding performance, dropped frames. Run benchmarks (Pro/Lifetime only). AI can analyze results and recommend updates.

Tab 10 - AI Assistant: This chat - answers OBS questions and troubleshooting.

FuzeOBS Widgets (Tab 06) - Detailed:

Donations:
- Accept viewer donations via PayPal. Connect PayPal account, set currency, minimum amount, suggested amounts.
- Customize donation page: title, message, show/hide recent donations.
- Donation URL is shareable. Can toggle donations enabled/disabled.
- Can clear donation history.
- Donations trigger Alert Box if configured.

Alert Box:
- On-screen alerts for stream events. Per-platform event types:
  * Twitch: follow, subscribe, bits, raid, host
  * YouTube: subscribe, superchat, member
  * Kick: follow, subscribe, gift_sub
  * Facebook: follow, stars
  * TikTok: follow, gift, share, like
  * Donation: donation (cross-platform)
- Each event type has its own config: alert image, alert sound, alert duration, text template with variables ({name}, {amount}, {viewers}, {count}, {gift}, {tier}, {months}, {message}).
- Layouts: Image Above, Text Over Image, Image Left, Image Right.
- Animations: Fade, Slide, Bounce, Zoom, Rotate.
- Text Animations: None, Wiggle, Bounce, Pulse, Wave.
- Font options: Arial, Helvetica, Times New Roman, Georgia, Courier New, Impact, Comic Sans MS, Verdana. Weights: Normal, Bold, Light, Semi-Bold.
- Text shadow toggle.
- TTS (Text-to-Speech): Available for donation, bits, superchat, and stars events. Enable TTS, configure TTS template.
- Custom CSS with toggle. AI CSS Styler can generate CSS through chat.
- Upload custom alert images and sounds.

Chat Box:
- Live chat overlay from all connected platforms in one unified view.
- Styles: Clean, Boxed, Chunky, Old School, Twitch.
- Platform toggles: show/hide each platform's chat independently.
- Show platform icon next to messages.
- Moderation: hide bot messages, hide commands (messages starting with !), muted users list, bad words filter.
- Chat notification: enable sound notification for new messages, set notification sound, volume, and optional message count threshold.
- Message animation toggle.
- Chat delay (seconds).
- Display: always show messages, or hide after X seconds.
- Font color, font size customization.
- Custom CSS with AI CSS Styler.

Event List:
- Scrolling list of recent stream events across all platforms.
- Styles: Clean, Boxed, Compact, Fuze, Bomby.
- Animations: Slide, Fade, Bounce, Zoom.
- Toggle which platforms and event types to show.
- Per-event message templates with variables:
  * Twitch: Follow ({name}), Subscribe ({name}, {tier}), Resub ({name}, {months}, {tier}), Gift Sub ({name}, {count}, {tier}), Bits ({name}, {amount}), Raid ({name}, {viewers})
  * YouTube: Subscribe ({name}), Member ({name}, {tier}), Super Chat ({name}, {amount})
  * Kick: Follow ({name}), Subscribe ({name}), Gift Sub ({name}, {count})
  * Facebook: Follow ({name}), Stars ({name}, {amount})
  * TikTok: Follow ({name}), Gift ({name}, {gift}, {count}), Share ({name}), Like ({name}, {count})
  * Donation: ({name}, {amount}, {message})
- Minimum thresholds for bits, stars, donations, super chats, gifts.
- Theme color, font size, max events shown.
- Custom CSS with AI CSS Styler.

Goal Bar:
- Visual progress bar for stream goals. Platform-specific goal types:
  * All platforms: Donation Goal (tip)
  * Twitch: Follower Goal, Subscriber Goal (with sub type: Subscriber Count or Sub Points), Bit Goal
  * YouTube: Subscriber Goal, Member Goal, Super Chat Goal
  * Kick: Follower Goal, Subscriber Goal
  * Facebook: Follower Goal, Stars Goal
  * TikTok: Follower Goal, Gift Goal
- Bar styles: Standard, Neon, Glass, Retro, Gradient.
- Layouts: Standard, Condensed.
- Configurable: title, goal amount, starting amount, end date, bar color, background color, bar thickness, font, text color.
- Show/hide percentage and numbers.
- Custom CSS with AI CSS Styler.

Labels:
- Dynamic text labels showing real-time stream data. Platform-specific label types:
  * All platforms: Latest Donation, Top Donation (Session), Top Donation (All Time), Total Donations (Session)
  * Twitch: Latest Follower, Latest Subscriber, Latest Cheerer, Latest Raider, Latest Gifter, Top Cheerer (Session), Top Gifter (Session), Session Followers, Session Subscribers
  * YouTube: Latest Subscriber, Latest Member, Latest Super Chat, Top Super Chat (Session), Session Subscribers, Session Members
  * Kick: Latest Follower, Latest Subscriber, Latest Gifter, Top Gifter (Session), Session Followers, Session Subscribers
  * Facebook: Latest Follower, Latest Stars, Top Stars (Session), Session Followers
  * TikTok: Latest Follower, Latest Gifter, Latest Sharer, Session Followers
- Configurable: prefix/suffix text, font family (Arial, Helvetica, Impact, Verdana, Georgia, Roboto, Montserrat, Open Sans, Oswald, Bebas Neue), font size, weight, text style, text color.
- Text shadow with shadow color.
- Background: enable/disable, color, opacity, padding, radius.
- Show platform icon toggle.
- Text animations: None, Fade, Slide, Bounce, Pulse.
- Custom CSS with AI CSS Styler.

Viewer Count:
- Display current viewer count from connected platforms. Customize font, size, color, icon.
- Custom CSS with AI CSS Styler.

Sponsor Banner:
- Rotating banner for sponsor/partner logos.
- Upload images (up to 2). Placements: Single (1 image) or Double (2 images rotating).
- Per-image display duration.
- Show/hide duration timing.
- Banner width and height.
- Animations: Fade, Bounce, Pulse, Rotate, Slide, Zoom.
- Background: transparent or solid color.
- Custom CSS with AI CSS Styler.

AI CSS Styler (available in all widgets):
- Chat-based CSS generator within each widget's config panel.
- Describe the look you want and AI generates custom CSS.
- CSS is auto-applied and saved to the widget.
- Available for: Alert Box, Chat Box, Event List, Goal Bar, Labels, Viewer Count, Sponsor Banner.

FuzeOBS Tools & Actions:
- Configuration Profiles: Save/load OBS configurations AND all widget configurations together. Profile limits: Free=1, Pro=3, Lifetime=5. Click PROFILES in topbar, name and save. Loading a profile restores both OBS settings and all widget configs (including per-event alert box settings).
- Export Configuration: Save current config to JSON for backup/sharing. Generate config first, then click EXPORT CONFIG.
- Import Configuration: Load previously exported config file. Overwrites current config.
- Launch OBS: Launch OBS directly from FuzeOBS sidebar.
- Test WebSocket: Test WebSocket connection from sidebar (for Tab 03).

Supported Platforms:
- Twitch (purple, #9146FF) - Full support: chat, alerts, labels, goals, events, leaderboard, recaps
- YouTube (red, #FF0000) - Full support: chat, alerts, labels, goals, events, leaderboard, recaps
- Kick (green, #53FC18) - Full support: chat, alerts, labels, goals, events, leaderboard, recaps
- Facebook (blue, #1877F2) - Partial support: chat, alerts, labels, goals, events, recaps. No leaderboard (no reliable stream duration API).
- TikTok (pink, #FE2858) - Partial support: chat, alerts, labels, goals, events. No leaderboard or recaps (no past broadcast API data).

Topics You Handle:
✓ OBS settings and configuration
✓ Encoding (NVENC, x264, QuickSync, etc.)
✓ Bitrate, resolution, and quality settings
✓ Stream performance and optimization
✓ Hardware compatibility and recommendations
✓ Scene setup, sources, and filters
✓ Audio configuration and mixing
✓ Platform-specific settings (Twitch, YouTube, Kick, Facebook, TikTok)
✓ Troubleshooting dropped frames, lag, quality issues, network issues
✓ Analyzing screenshots of OBS interfaces
✓ Reviewing scene collection and profile JSON files
✓ FuzeOBS widgets setup and customization (all widget types)
✓ WebSocket connection issues
✓ FuzeOBS features: Welcome Tab, Leaderboard, Collab Finder, Stream Countdown, Stream Recaps, Profiles, Reviews
✓ Platform connection issues and setup

Topics You Redirect:
✗ General programming or coding tasks
✗ Non-streaming related hardware/software
✗ Unrelated technical support (aside from WiFi/Ethernet troubleshooting like resetting a router)
✗ General knowledge questions

Common Issues:
- Webcams not appearing: Incorrect resolution set. If webcam max is 720p but 1080p is set, it won't show. Lower resolution than max works fine.
- WebSocket won't connect: Ensure OBS is running, password is 6+ chars, OBS WebSocket server is enabled in OBS Tools menu.
- Widgets not updating: Check platform connection status, ensure stream is live for real-time widgets.
- Leaderboard shows 0 hours: Hours sync every 24 hours. Twitch requires Affiliate/Partner for VOD storage. Ensure platforms are connected.
- Stream Recaps empty: Ensure platform is connected. TikTok recaps not supported. Twitch requires Affiliate/Partner for VODs.
- Profile limit reached: Free=1 profile, Pro=3, Lifetime=5. Delete an existing profile or upgrade tier.
- AI CSS Styler not working: Describe the look you want in plain language. CSS is auto-applied to the widget preview.""",
                        "cache_control": {"type": "ephemeral"}
                    },
                    {
                        "type": "text",
                        "text": f"Response Style:\n{style_prompt}"
                    }
                ] + ([{
                    "type": "text",
                    "text": f"This user's streaming data (use to personalize advice):\n{platform_context}"
                }] if platform_context else []),
                messages=[{"role": "user", "content": messages_content}]
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
                
                final_message = stream.get_final_message()
                input_tokens = final_message.usage.input_tokens
                output_tokens = final_message.usage.output_tokens
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            success = False
            error_msg = str(e)
            print(f"AI Error: {e}")
            yield f"data: {json.dumps({'text': 'Error processing request.'})}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            response_time = time.time() - start_time
            total_tokens = input_tokens + output_tokens
            
            if model == "claude-opus-4-5-20251101":
                cost = (input_tokens / 1_000_000 * 5) + (output_tokens / 1_000_000 * 25)
            else:
                cost = (input_tokens / 1_000_000 * 1) + (output_tokens / 1_000_000 * 5)
            
            # Track all AI usage (both logged-in and anonymous)
            AIUsage.objects.create(
                user=user,
                user_tier=tier,
                is_anonymous=(user is None),
                tokens_used=total_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=cost,
                request_type='chat',
                response_time=response_time,
                success=success,
                error_message=error_msg
            )
    
    response = StreamingHttpResponse(generate(), content_type='text/event-stream; charset=utf-8')
    response['Cache-Control'] = 'no-cache'    
    return response

# ===== CHAT HISTORY =====

@csrf_exempt
@require_tier('free')
def fuzeobs_save_chat(request):
    """Save chat for logged-in users only"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
    elif request.method != 'POST':
        response = JsonResponse({'error': 'POST only'}, status=405)
    else:
        user = request.fuzeobs_user
        data = json.loads(request.body)
        chat_data = data.get('chat')
        
        if not chat_data or not isinstance(chat_data, dict):
            response = JsonResponse({'error': 'Invalid chat data'}, status=400)
        else:
            chat_history = list(user.fuzeobs_chat_history)
            
            # Normalize existing chats
            normalized_history = []
            for item in chat_history:
                if isinstance(item, dict):
                    if 'chat' in item and isinstance(item['chat'], dict) and 'id' in item['chat']:
                        normalized_history.append(item['chat'])
                    elif 'id' in item:
                        normalized_history.append(item)
            
            existing_index = next((i for i, c in enumerate(normalized_history) if c.get('id') == chat_data.get('id')), None)
            
            if existing_index is not None:
                normalized_history[existing_index] = chat_data
            else:
                normalized_history.append(chat_data)
            
            user.fuzeobs_chat_history = sorted(
                normalized_history,
                key=lambda x: x.get('updated_at', 0),
                reverse=True
            )[:10]
            
            user.save()
            response = JsonResponse({'success': True})    
            return response

@csrf_exempt
@require_tier('free')
def fuzeobs_get_chats(request):
    """Get all chats for logged-in users only"""
    if request.method != 'GET':
        response = JsonResponse({'error': 'GET only'}, status=405)
    else:
        user = request.fuzeobs_user
        chats = user.fuzeobs_chat_history if user.fuzeobs_chat_history else []
        response = JsonResponse({'chats': chats})    
        return response

@csrf_exempt
@require_tier('free')
def fuzeobs_delete_chat(request):
    """Delete specific chat for logged-in users only"""
    if request.method != 'POST':
        response = JsonResponse({'error': 'POST only'}, status=405)
    else:
        user = request.fuzeobs_user
        data = json.loads(request.body)
        chat_id = data.get('chatId')
        
        if hasattr(user, 'fuzeobs_chat_history'):
            user.fuzeobs_chat_history = [
                c for c in user.fuzeobs_chat_history 
                if c.get("id") != chat_id
            ]
            user.save()
        
        response = JsonResponse({'success': True})    
        return response

@csrf_exempt
@require_tier('free')
def fuzeobs_clear_chats(request):
    """Clear all chats for logged-in users only"""
    if request.method != 'POST':
        response = JsonResponse({'error': 'POST only'}, status=405)
    else:
        user = request.fuzeobs_user
        user.fuzeobs_chat_history = []
        user.save()
        response = JsonResponse({'success': True})    
        return response

# ===== BENCHMARKING (PRO / LIFETIME ONLY) =====

@csrf_exempt
@require_tier('pro')
def fuzeobs_analyze_benchmark(request):
    """Analyze benchmark results with AI - PRO ONLY"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    user = request.fuzeobs_user
    data = json.loads(request.body)
    benchmark_data = data.get('benchmark_data', '').strip()
    
    if not benchmark_data:
        return JsonResponse({'error': 'No benchmark data'}, status=400)
    
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    model = "claude-sonnet-4-20250514"
    
    def generate():
        try:
            with client.messages.stream(
                model=model,
                max_tokens=6000,
                system="""You are the FuzeOBS Performance Analysis Expert. Analyze benchmark results and provide:

1. **Performance Summary** - Brief overview
2. **Critical Issues** - Severe problems (if any)
3. **Detailed Analysis** - CPU, GPU, Network, Frame Drops
4. **Recommended Actions** - Numbered priority list with exact settings
5. **Advanced Optimizations** - Fine-tuning for good streams

Always provide EXACT settings (bitrate numbers, preset names). Explain WHY each change helps. Consider their specific hardware.""",
                messages=[{"role": "user", "content": f"Analyze this streaming benchmark:\n\n{benchmark_data}"}]
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            print(f"AI Error: {e}")
            yield "data: [ERROR] Failed to analyze.\n\n"
    
    response = StreamingHttpResponse(generate(), content_type='text/event-stream; charset=utf-8')
    response['Cache-Control'] = 'no-cache'    
    return response

# ===== PROFILES =====

@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuzeobs_get_profiles(request):
    user = request.fuzeobs_user
    profiles = FuzeOBSProfile.objects.filter(user=user)
    return JsonResponse({
        'profiles': [{
            'id': p.id,
            'name': p.name,
            'config': p.config,
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat()
        } for p in profiles]
    })

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_create_profile(request):
    user = request.fuzeobs_user
    try:
        data = json.loads(request.body)
        profile = FuzeOBSProfile.objects.create(
            user=user,
            name=data['name'],
            config=data['config']
        )
        return JsonResponse({'success': True, 'id': profile.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@csrf_exempt
@require_http_methods(["DELETE"])
@require_tier('free')
def fuzeobs_delete_profile(request, profile_id):
    user = request.fuzeobs_user
    try:
        profile = FuzeOBSProfile.objects.get(id=profile_id, user=user)
        profile.delete()
        return JsonResponse({'success': True})
    except FuzeOBSProfile.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

@csrf_exempt
@require_http_methods(["PUT"])
@require_tier('free')
def fuzeobs_update_profile(request, profile_id):
    user = request.fuzeobs_user
    try:
        profile = FuzeOBSProfile.objects.get(id=profile_id, user=user)
        data = json.loads(request.body)
        profile.name = data.get('name', profile.name)
        profile.config = data.get('config', profile.config)
        profile.save()
        return JsonResponse({'success': True})
    except FuzeOBSProfile.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
# ====== WEBSITE VIEWS =======
def fuzeobs_view(request):
    # Track page view
    from .models import FuzeOBSPageView, FuzeOBSReview
    try:
        session_id = request.session.session_key or ''
        if not session_id:
            request.session.create()
            session_id = request.session.session_key
        FuzeOBSPageView.objects.create(
            page='landing',
            session_id=session_id,
            user=request.user if request.user.is_authenticated else None
        )
    except:
        pass
    
    # Get featured reviews
    featured_reviews = FuzeOBSReview.objects.filter(featured=True).select_related('user')[:20]
    
    return render(request, 'FUZEOBS/fuzeobs.html', {
        'fuzeobs_version': FUZEOBS_VERSION,
        'featured_reviews': featured_reviews,
    })

@staff_member_required
def fuzeobs_download_windows(request):
    DownloadTracking.objects.create(
        platform='windows',
        version='0.9.4',
        user=request.user if request.user.is_authenticated else None,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    return redirect('https://storage.googleapis.com/fuzeobs-public/fuzeobs-installer/FuzeOBS-Installer.exe')

@staff_member_required
def fuzeobs_download_mac(request):
    DownloadTracking.objects.create(
        platform='mac',
        version='0.9.4',
        user=request.user if request.user.is_authenticated else None,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    return redirect('https://storage.googleapis.com/fuzeobs-public/fuzeobs-installer/FuzeOBS-Installer.exe')


def fuzeobs_install_guide(request):
    return render(request, 'FUZEOBS/fuzeobs_installation_guide.html', {
        'fuzeobs_version': FUZEOBS_VERSION,
    })

# ====== PRICING & PAYMENT VIEWS =======
FUZEOBS_PLANS = {
    'pro': {
        'name': 'Pro',
        'price': '7.50',
        'stripe_price_id': settings.FUZEOBS_STRIPE_PRICE_MONTHLY,
        'mode': 'subscription',
    },
    '3month': {
        'name': 'Pro (3-Month)',
        'price': '20.00',
        'stripe_price_id': settings.FUZEOBS_STRIPE_PRICE_3MONTH,
        'mode': 'payment',
    },
    'lifetime': {
        'name': 'Lifetime',
        'price': '45.00',
        'stripe_price_id': settings.FUZEOBS_STRIPE_PRICE_LIFETIME,
        'mode': 'payment',
    },
}

def fuzeobs_pricing(request):
    # Track page view
    from .models import FuzeOBSPageView
    try:
        session_id = request.session.session_key or ''
        if not session_id:
            request.session.create()
            session_id = request.session.session_key
        FuzeOBSPageView.objects.create(
            page='pricing',
            session_id=session_id,
            user=request.user if request.user.is_authenticated else None
        )
    except:
        pass
    
    current_plan = 'free'
    if request.user.is_authenticated:
        current_plan = request.user.fuzeobs_tier or 'free'
    return render(request, 'FUZEOBS/fuzeobs_pricing.html', {'current_plan': current_plan})

@login_required
def fuzeobs_payment(request, plan_type):
    if plan_type not in FUZEOBS_PLANS:
        return redirect('FUZEOBS:pricing')
    
    current_plan = request.user.fuzeobs_tier or 'free'
    
    # Block invalid purchases
    if current_plan == 'lifetime':
        messages.info(request, "You already have Lifetime access!")
        return redirect('FUZEOBS:pricing')
    if current_plan == 'pro' and plan_type == 'pro':
        messages.info(request, "You already have Pro! Consider upgrading to Lifetime.")
        return redirect('FUZEOBS:pricing')
    
    plan = FUZEOBS_PLANS[plan_type]
    return render(request, 'FUZEOBS/fuzeobs_payment.html', {
        'plan_type': plan_type,
        'plan_name': plan['name'],
        'price': plan['price'],
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
    })

@login_required
@require_POST
def fuzeobs_create_checkout_session(request):
    try:
        data = json.loads(request.body)
        plan_type = data.get('plan_type')
        
        if plan_type not in FUZEOBS_PLANS:
            return JsonResponse({'error': 'Invalid plan'}, status=400)
        
        plan = FUZEOBS_PLANS[plan_type]
        return_url = request.build_absolute_uri('/fuzeobs/payment/success/') + '?session_id={CHECKOUT_SESSION_ID}'
        
        session = stripe.checkout.Session.create(
            ui_mode='embedded',
            customer_email=request.user.email,
            line_items=[{'price': plan['stripe_price_id'], 'quantity': 1}],
            mode=plan['mode'],
            return_url=return_url,
            redirect_on_completion='if_required',
            metadata={
                'user_id': str(request.user.id),
                'plan_type': plan_type,
                'product': 'fuzeobs',
            }
        )
        
        return JsonResponse({'clientSecret': session.client_secret, 'sessionId': session.id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def fuzeobs_payment_success(request):
    session_id = request.GET.get('session_id')
    
    if not session_id:
        messages.error(request, "Invalid payment session.")
        return redirect('FUZEOBS:pricing')
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        is_complete = session.status == 'complete' or session.payment_status == 'paid'
        
        if not is_complete:
            messages.error(request, "Payment not completed.")
            return redirect('FUZEOBS:pricing')
        
        plan_type = session.metadata.get('plan_type', 'pro')
        user_id = session.metadata.get('user_id')
        plan = FUZEOBS_PLANS.get(plan_type, FUZEOBS_PLANS['pro'])
        
        # Verify the logged-in user matches the payment user
        if str(request.user.id) != str(user_id):
            messages.error(request, "Payment session mismatch.")
            return redirect('FUZEOBS:pricing')
        
        # Check if already processed (prevent duplicates)
        existing_purchase = FuzeOBSPurchase.objects.filter(payment_id=session_id).first()
        if existing_purchase:
            return render(request, 'FUZEOBS/fuzeobs_payment_success.html', {
                'plan_type': plan_type,
                'plan_name': plan['name'],
                'purchase': existing_purchase
            })
        
        try:
            user = User.objects.get(id=user_id)
            old_tier = user.fuzeobs_tier
            user.fuzeobs_tier = 'lifetime' if plan_type == 'lifetime' else 'pro'
            
            try:
                user.promote_to_supporter()
            except Exception as e:
                print(f"[FUZEOBS] promote_to_supporter failed: {e}")
            
            # Activate as FuzeOBS user (counts in total users)
            activate_fuzeobs_user(user)
            user.save()
            
            # Cancel existing Pro subscription if upgrading to Lifetime
            if plan_type == 'lifetime':
                try:
                    existing_sub = FuzeOBSSubscription.objects.get(user=user, is_active=True)
                    if existing_sub.stripe_subscription_id:
                        stripe.Subscription.cancel(existing_sub.stripe_subscription_id)
                    existing_sub.is_active = False
                    existing_sub.plan_type = 'lifetime'
                    existing_sub.save()
                except FuzeOBSSubscription.DoesNotExist:
                    pass
            
            TierChange.objects.create(
                user=user,
                from_tier=old_tier,
                to_tier=user.fuzeobs_tier,
                reason='stripe_purchase'
            )
            
            purchase = FuzeOBSPurchase.objects.create(
                user=user,
                plan_type=plan_type,
                amount=Decimal(plan['price']),
                payment_id=session_id,
                is_paid=True
            )
            
            # Send invoice email
            try:
                send_fuzeobs_invoice_email(request, user, purchase, plan_type)
            except Exception as e:
                print(f"Failed to send invoice email: {e}")
            
            # Save subscription info for Pro plans
            if plan_type == 'pro' and session.subscription:
                FuzeOBSSubscription.objects.update_or_create(
                    user=user,
                    defaults={
                        'plan_type': 'pro',
                        'stripe_customer_id': session.customer,
                        'stripe_subscription_id': session.subscription,
                        'is_active': True
                    }
                )
            
            # Save 3-month plan with expiration
            if plan_type == '3month':
                from datetime import timedelta
                FuzeOBSSubscription.objects.update_or_create(
                    user=user,
                    defaults={
                        'plan_type': 'pro',
                        'stripe_customer_id': session.customer or '',
                        'stripe_subscription_id': '',
                        'is_active': True,
                        'expires_at': timezone.now() + timedelta(days=90),
                    }
                )
        except User.DoesNotExist:
            pass
        
        return render(request, 'FUZEOBS/fuzeobs_payment_success.html', {
            'plan_type': plan_type,
            'plan_name': plan['name'],
            'purchase': {
                'created_at': timezone.now(),
                'amount': plan['price'],
            }
        })
        
    except stripe.error.StripeError:
        messages.error(request, "Payment verification failed.")
        return redirect('FUZEOBS:pricing')

@csrf_exempt
@require_POST
def fuzeobs_stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        payment_id = session.get('payment_intent') or session.get('id')
        
        # === FUZEOBS PURCHASES ===
        if metadata.get('product') == 'fuzeobs':
            user_id = metadata.get('user_id')
            plan_type = metadata.get('plan_type')
            
            if FuzeOBSPurchase.objects.filter(payment_id=payment_id).exists():
                return JsonResponse({'status': 'already_processed'})
            
            try:
                user = User.objects.get(id=user_id)
                old_tier = user.fuzeobs_tier
                user.fuzeobs_tier = 'lifetime' if plan_type == 'lifetime' else 'pro'
                
                try:
                    user.promote_to_supporter()
                except Exception as e:
                    print(f"[FUZEOBS] promote_to_supporter failed: {e}")
                
                activate_fuzeobs_user(user)
                user.save()
                
                if plan_type == 'lifetime':
                    try:
                        existing_sub = FuzeOBSSubscription.objects.get(user=user, is_active=True)
                        if existing_sub.stripe_subscription_id:
                            stripe.Subscription.cancel(existing_sub.stripe_subscription_id)
                        existing_sub.is_active = False
                        existing_sub.plan_type = 'lifetime'
                        existing_sub.save()
                    except FuzeOBSSubscription.DoesNotExist:
                        pass
                
                TierChange.objects.create(
                    user=user,
                    from_tier=old_tier,
                    to_tier=user.fuzeobs_tier,
                    reason='stripe_webhook'
                )
                
                amount = Decimal(FUZEOBS_PLANS.get(plan_type, {}).get('price', '7.50'))
                purchase = FuzeOBSPurchase.objects.create(
                    user=user,
                    plan_type=plan_type,
                    amount=amount,
                    payment_id=payment_id,
                    is_paid=True
                )
                
                try:
                    send_fuzeobs_invoice_email(request, user, purchase, plan_type)
                except Exception as e:
                    print(f'[FUZEOBS] Invoice email failed: {e}')
                
                if plan_type == 'pro' and session.get('subscription'):
                    FuzeOBSSubscription.objects.update_or_create(
                        user=user,
                        defaults={
                            'plan_type': 'pro',
                            'stripe_customer_id': session.get('customer'),
                            'stripe_subscription_id': session.get('subscription'),
                            'is_active': True
                        }
                    )
                
                if plan_type == '3month':
                    from datetime import timedelta
                    FuzeOBSSubscription.objects.update_or_create(
                        user=user,
                        defaults={
                            'plan_type': 'pro',
                            'stripe_customer_id': session.get('customer', ''),
                            'stripe_subscription_id': '',
                            'is_active': True,
                            'expires_at': timezone.now() + timedelta(days=90),
                        }
                    )
            except User.DoesNotExist:
                pass
        
        # === STORE PRODUCT PURCHASES ===
        elif metadata.get('type') == 'product':
            from STORE.models import Order, Product
            product_id = metadata.get('product_id')
            user_id = metadata.get('user_id')
            
            if product_id and user_id and payment_id:
                if not Order.objects.filter(payment_id=payment_id).exists():
                    try:
                        user = User.objects.get(id=user_id)
                        product = Product.objects.get(id=product_id)
                        
                        status = 'completed' if int(product_id) == 4 else 'pending'
                        Order.objects.create(
                            user=user,
                            product=product,
                            status=status,
                            payment_id=payment_id,
                            is_paid=True
                        )
                    except Exception as e:
                        print(f"[STORE] Webhook order creation error: {e}")
        
        # === STORE DONATIONS ===
        elif metadata.get('type') == 'donation':
            from STORE.models import Donation
            amount = metadata.get('amount')
            user_id = metadata.get('user_id')
            
            if amount and payment_id:
                if not Donation.objects.filter(payment_id=payment_id).exists():
                    try:
                        donation = Donation.objects.create(
                            amount=amount,
                            payment_id=payment_id,
                            is_paid=True
                        )
                        if user_id:
                            donation.user = User.objects.get(id=user_id)
                            donation.save()
                    except Exception as e:
                        print(f"[STORE] Webhook donation creation error: {e}")
    
    # Handle FUZEOBS subscription cancellation
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        try:
            sub = FuzeOBSSubscription.objects.get(stripe_subscription_id=subscription['id'])
            sub.is_active = False
            sub.save()
            
            user = sub.user
            old_tier = user.fuzeobs_tier
            user.fuzeobs_tier = 'free'
            user.save()
            TierChange.objects.create(
                user=user,
                from_tier=old_tier,
                to_tier='free',
                reason='subscription_cancelled'
            )
        except FuzeOBSSubscription.DoesNotExist:
            pass
    
    return JsonResponse({'status': 'success'})

@login_required
def fuzeobs_manage_subscription(request):
    """Subscription management page"""
    try:
        sub = FuzeOBSSubscription.objects.get(user=request.user)
        # Get subscription details from Stripe if active
        stripe_sub = None
        if sub.stripe_subscription_id and sub.is_active:
            try:
                stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
            except:
                pass
        
        return render(request, 'FUZEOBS/fuzeobs_manage_subscription.html', {
            'subscription': sub,
            'stripe_sub': stripe_sub,
            'cancel_at_period_end': stripe_sub.cancel_at_period_end if stripe_sub else False,
            'current_period_end': stripe_sub.current_period_end if stripe_sub else None,
        })
    except FuzeOBSSubscription.DoesNotExist:
        messages.error(request, "No subscription found.")
        return redirect('ACCOUNTS:purchase_history')

@login_required
@require_POST
def fuzeobs_cancel_subscription(request):
    """Cancel user's Pro subscription"""
    try:
        sub = FuzeOBSSubscription.objects.get(user=request.user, is_active=True)
        if sub.stripe_subscription_id:
            # Cancel at period end (user keeps access until billing cycle ends)
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                cancel_at_period_end=True
            )
            messages.success(request, "Your subscription will cancel at the end of your billing period. You'll keep Pro access until then.")
        else:
            messages.error(request, "No active subscription found.")
    except FuzeOBSSubscription.DoesNotExist:
        messages.error(request, "No active subscription found.")
    
    return redirect('FUZEOBS:manage_subscription')

@login_required
@require_POST
def fuzeobs_reactivate_subscription(request):
    """Reactivate a cancelled subscription"""
    try:
        sub = FuzeOBSSubscription.objects.get(user=request.user, is_active=True)
        if sub.stripe_subscription_id:
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                cancel_at_period_end=False
            )
            messages.success(request, "Your subscription has been reactivated.")
        else:
            messages.error(request, "No subscription found.")
    except FuzeOBSSubscription.DoesNotExist:
        messages.error(request, "No subscription found.")
    
    return redirect('FUZEOBS:manage_subscription')

def fuzeobs_user_detail(request, user_id):
    view_user = get_object_or_404(User, id=user_id)
    days = int(request.GET.get('days', 30))
    cutoff = timezone.now() - timedelta(days=days)
    
    # AI usage
    ai_usage_qs = AIUsage.objects.filter(user=view_user, timestamp__gte=cutoff).order_by('-timestamp')
    ai_stats = ai_usage_qs.aggregate(
        total_cost=Sum('estimated_cost'),
        total_tokens=Sum('tokens_used'),
        total_requests=Count('id')
    )

    # Success rate
    success_count = ai_usage_qs.filter(success=True).count()
    total_count = ai_usage_qs.count()
    success_rate = round((success_count / total_count * 100), 1) if total_count > 0 else 0

    # Get sliced for display
    ai_usage = ai_usage_qs
    
    # Chats
    user_chats = view_user.fuzeobs_chat_history if view_user.fuzeobs_chat_history else []
    
    # Activity
    activity = UserActivity.objects.filter(user=view_user, timestamp__gte=cutoff).order_by('-timestamp')
    
    # Widgets
    widgets = WidgetConfig.objects.filter(user=view_user, enabled=True)
    
    # Media library storage
    media_stats = MediaLibrary.objects.filter(user=view_user).aggregate(
        total_files=Count('id'),
        total_size=Sum('file_size')
    )
    media_size_mb = round((media_stats['total_size'] or 0) / (1024 * 1024), 2)
    
    # Donation settings
    try:
        donation_settings = DonationSettings.objects.get(user=view_user)
        donation_url = request.build_absolute_uri(f'/fuzeobs/donate/{donation_settings.donation_token}')
    except DonationSettings.DoesNotExist:
        donation_settings = None
        donation_url = None
    
    context = {
        'view_user': view_user,
        'ai_usage': ai_usage,
        'ai_stats': ai_stats,
        'success_rate': success_rate,
        'user_chats': user_chats,
        'activity': activity,
        'days': days,
        'widgets': widgets,
        'media_files': media_stats['total_files'] or 0,
        'media_size_mb': media_size_mb,
        'donation_settings': donation_settings,
        'donation_url': donation_url,
    }
    
    return render(request, 'FUZEOBS/user_detail.html', context)

@staff_member_required
def fuzeobs_chat_detail(request, user_id, chat_index):
    view_user = get_object_or_404(User, id=user_id)
    user_chats = view_user.fuzeobs_chat_history if view_user.fuzeobs_chat_history else []
    
    if chat_index >= len(user_chats):
        return redirect('FUZEOBS:user_detail', user_id=user_id)
    
    chat = user_chats[chat_index]
    
    context = {
        'view_user': view_user,
        'chat': chat,
        'chat_index': chat_index
    }
    
    return render(request, 'FUZEOBS/chat_detail.html', context)

@staff_member_required
def fuzeobs_analytics_view(request):
    cleanup_old_sessions()
    
    days = int(request.GET.get('days', 30))
    date_from = timezone.now() - timedelta(days=days)
    
    # Query ONLY FuzeOBS users
    fuzeobs_users = User.objects.filter(fuzeobs_activated=True)
    total_users = fuzeobs_users.count()
    new_users = fuzeobs_users.filter(fuzeobs_first_login__gte=date_from).count()
    
    # Active users from sessions
    from .models import ActiveSession
    active_users = ActiveSession.objects.filter(user__isnull=False).values('user').distinct().count()
    
    # Downloads
    downloads = DownloadTracking.objects.filter(timestamp__gte=date_from)
    total_downloads = downloads.count()
    downloads_by_platform = list(downloads.values('platform').annotate(count=Count('id')))
    
    # AI usage
    ai_stats = AIUsage.objects.filter(timestamp__gte=date_from).aggregate(
        total=Count('id'),
        success_count=Count('id', filter=Q(success=True)),
        total_cost=Sum('estimated_cost'),
        avg_tokens=Avg('tokens_used'),
        avg_response_time=Avg('response_time')
    )
    
    total_requests = ai_stats['total'] or 0
    success_rate = round((ai_stats['success_count'] or 0) / total_requests * 100, 1) if total_requests > 0 else 0
    total_cost = round(float(ai_stats['total_cost'] or 0), 2)
    avg_tokens = round(ai_stats['avg_tokens'] or 0)
    avg_response_time = round(ai_stats['avg_response_time'] or 0, 2)
    
    # AI cost by tier (free vs paid)
    free_ai = AIUsage.objects.filter(timestamp__gte=date_from, user_tier='free').aggregate(
        count=Count('id'), cost=Sum('estimated_cost')
    )
    paid_ai = AIUsage.objects.filter(timestamp__gte=date_from).exclude(user_tier='free').aggregate(
        count=Count('id'), cost=Sum('estimated_cost')
    )
    
    free_cost = round(float(free_ai['cost'] or 0), 2)
    paid_cost = round(float(paid_ai['cost'] or 0), 2)
    free_requests = free_ai['count'] or 0
    paid_requests = paid_ai['count'] or 0
    
    # Tier distribution
    tier_distribution = list(fuzeobs_users.values('fuzeobs_tier').annotate(count=Count('id')))
    for tier in tier_distribution:
        tier['tier'] = tier.pop('fuzeobs_tier')
    
    # Upgrades/downgrades
    upgrades = TierChange.objects.filter(timestamp__gte=date_from).exclude(from_tier='free', to_tier='free').exclude(to_tier='free').count()
    downgrades = TierChange.objects.filter(timestamp__gte=date_from, to_tier='free').count()
    
    # Revenue tracking (from actual purchases for accurate amounts)
    purchases_in_range = FuzeOBSPurchase.objects.filter(
        created_at__gte=date_from, is_paid=True
    )
    pro_purchases = purchases_in_range.filter(plan_type='pro').count()
    three_month_purchases = purchases_in_range.filter(plan_type='3month').count()
    lifetime_purchases = purchases_in_range.filter(plan_type='lifetime').count()

    pro_revenue = float(purchases_in_range.filter(plan_type='pro').aggregate(t=Sum('amount'))['t'] or 0)
    three_month_revenue = float(purchases_in_range.filter(plan_type='3month').aggregate(t=Sum('amount'))['t'] or 0)
    lifetime_revenue = float(purchases_in_range.filter(plan_type='lifetime').aggregate(t=Sum('amount'))['t'] or 0)
    total_revenue = pro_revenue + three_month_revenue + lifetime_revenue
    
    # Cost by tier (detailed)
    cost_by_tier_raw = AIUsage.objects.filter(timestamp__gte=date_from).values('user_tier').annotate(
        request_count=Count('id'), 
        total_cost=Sum('estimated_cost')
    )
    
    cost_by_tier = []
    for item in cost_by_tier_raw:
        tier = item['user_tier'] or 'unknown'
        cost_by_tier.append({
            'tier_key': tier,
            'tier_display': tier.title(),
            'request_count': item['request_count'],
            'total_cost': round(float(item['total_cost'] or 0), 2)
        })
    
    # Top users by AI usage (exclude anonymous)
    top_users = AIUsage.objects.filter(
        timestamp__gte=date_from,
        user__isnull=False
    ).values(
        'user__id', 'user__username', 'user__fuzeobs_tier'
    ).annotate(
        total_cost=Sum('estimated_cost'),
        total_requests=Count('id')
    ).order_by('-total_cost')[:10]
    
    # Feature usage
    feature_usage = list(UserActivity.objects.filter(timestamp__gte=date_from).values('activity_type').annotate(count=Count('id')).order_by('-count'))
    
    # Recent tier changes
    recent_tier_changes = TierChange.objects.select_related('user').filter(timestamp__gte=date_from)[:20]
    
    # Error tracking
    error_count = AIUsage.objects.filter(timestamp__gte=date_from, success=False).count()
    error_rate = round((error_count / total_requests * 100), 1) if total_requests > 0 else 0
    
    # Template usage
    template_usage = list(UserActivity.objects.filter(
        timestamp__gte=date_from, 
        activity_type='template_use'
    ).values('details__template_id').annotate(count=Count('id')).order_by('-count')[:10])
    
    # Daily active users trend
    dau_data = []
    for i in range(min(days, 30)):
        day = timezone.now() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0)
        day_end = day.replace(hour=23, minute=59, second=59)
        dau = UserActivity.objects.filter(timestamp__range=[day_start, day_end]).values('user').distinct().count()
        dau_data.append({'date': day.strftime('%m/%d'), 'count': dau})
    dau_data.reverse()
    
    # Page views tracking
    from .models import FuzeOBSPageView
    landing_views = FuzeOBSPageView.objects.filter(page='landing', timestamp__gte=date_from).values('session_id').distinct().count()
    pricing_views = FuzeOBSPageView.objects.filter(page='pricing', timestamp__gte=date_from).values('session_id').distinct().count()
    
    # Review counts
    total_reviews = FuzeOBSReview.objects.count()
    featured_reviews = FuzeOBSReview.objects.filter(featured=True).count()
    
    context = {
        'days': days,
        'total_users': total_users,
        'new_users': new_users,
        'active_users': active_users,
        'total_downloads': total_downloads,
        'downloads_by_platform': downloads_by_platform,
        'downloads_json': json.dumps(downloads_by_platform),
        'total_requests': total_requests,
        'success_rate': success_rate,
        'error_rate': error_rate,
        'total_cost': total_cost,
        'free_cost': free_cost,
        'paid_cost': paid_cost,
        'free_requests': free_requests,
        'paid_requests': paid_requests,
        'avg_tokens': avg_tokens,
        'avg_response_time': avg_response_time,
        'tier_distribution': tier_distribution,
        'tier_distribution_json': json.dumps(tier_distribution),
        'upgrades': upgrades,
        'downgrades': downgrades,
        'pro_purchases': pro_purchases,
        'three_month_purchases': three_month_purchases,
        'lifetime_purchases': lifetime_purchases,
        'pro_revenue': pro_revenue,
        'three_month_revenue': three_month_revenue,
        'lifetime_revenue': lifetime_revenue,
        'total_revenue': total_revenue,
        'cost_by_tier': cost_by_tier,
        'top_users': top_users,
        'feature_usage': feature_usage,
        'feature_usage_json': json.dumps(feature_usage),
        'recent_tier_changes': recent_tier_changes,
        'template_usage': template_usage,
        'dau_data': dau_data,
        'dau_json': json.dumps(dau_data),
        'landing_views': landing_views,
        'pricing_views': pricing_views,
        'total_reviews': total_reviews,
        'featured_reviews': featured_reviews,
    }
    
    return render(request, 'FUZEOBS/fuzeobs_analytics.html', context)

@staff_member_required
def fuzeobs_all_users_view(request):
    from django.core.paginator import Paginator
    from django.db.models import OuterRef, Subquery, IntegerField, DecimalField, Value, Count, Sum
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    
    # Use subqueries
    ai_requests_subq = AIUsage.objects.filter(user=OuterRef('pk')).values('user').annotate(
        cnt=Count('id')
    ).values('cnt')[:1]
    
    ai_cost_subq = AIUsage.objects.filter(user=OuterRef('pk')).values('user').annotate(
        total=Sum('estimated_cost')
    ).values('total')[:1]
    
    last_activity_subq = UserActivity.objects.filter(user=OuterRef('pk')).order_by(
        '-timestamp'
    ).values('timestamp')[:1]
    
    all_users = User.objects.filter(fuzeobs_activated=True).annotate(
        total_ai_requests=Coalesce(Subquery(ai_requests_subq, output_field=IntegerField()), Value(0)),
        total_ai_cost=Coalesce(Subquery(ai_cost_subq, output_field=DecimalField()), Value(Decimal('0'))),
        last_activity=Subquery(last_activity_subq)
    ).order_by('-total_ai_requests')
    
    paginator = Paginator(all_users, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'all_users': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'FUZEOBS/fuzeobs_all_users.html', context)

@staff_member_required
@require_http_methods(["GET", "POST"])
def fuzeobs_reset_analytics(request):
    """Admin view to reset analytics data for testing"""
    if request.method == 'POST':
        reset_type = request.POST.getlist('reset_type')
        deleted = {}
        
        if 'tier_changes' in reset_type:
            deleted['tier_changes'] = TierChange.objects.all().delete()[0]
        if 'ai_usage' in reset_type:
            deleted['ai_usage'] = AIUsage.objects.all().delete()[0]
        if 'user_activity' in reset_type:
            deleted['user_activity'] = UserActivity.objects.all().delete()[0]
        if 'downloads' in reset_type:
            deleted['downloads'] = DownloadTracking.objects.all().delete()[0]
        if 'active_sessions' in reset_type:
            deleted['active_sessions'] = ActiveSession.objects.all().delete()[0]
        if 'page_views' in reset_type:
            from .models import FuzeOBSPageView
            deleted['page_views'] = FuzeOBSPageView.objects.all().delete()[0]
        
        return render(request, 'FUZEOBS/fuzeobs_reset_analytics.html', {
            'deleted': deleted,
            'success': True
        })
    
    return render(request, 'FUZEOBS/fuzeobs_reset_analytics.html')

# ===== WIDGETS SYSTEM =====
# Widget HTML generators

@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuzeobs_get_widgets(request):
    """Get all widgets for user - fetch ALL platforms, not filtered"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        user = get_user_from_token(token)
    else:
        user = None
    
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    # Don't filter by platform - return ALL widgets
    widgets = WidgetConfig.objects.filter(user=user).order_by('-updated_at')
    
    return JsonResponse({
        'widgets': [{
            'id': w.id,
            'type': w.widget_type,
            'platform': w.platform,
            'goal_type': w.goal_type,
            'name': w.name,
            'config': w.config,
            'url': f'https://bomby.us/fuzeobs/w/{w.token}',
            'created_at': w.created_at.isoformat(),
            'updated_at': w.updated_at.isoformat(),
            'enabled': w.enabled
        } for w in widgets]
    })

@xframe_options_exempt
@require_http_methods(["GET"])
def fuzeobs_serve_widget(request, token):
    """Serve widget by token - clean URL"""
    try:
        widget = WidgetConfig.objects.get(token=token)
        html = generate_widget_html(widget)
        response = HttpResponse(html, content_type='text/html')
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    except WidgetConfig.DoesNotExist:
        return HttpResponse('Widget not found', status=404)

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_save_widget(request):
    """Save widget - handles auth inline"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        user = get_user_from_token(token)
    else:
        user = None
    
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        data = json.loads(request.body)
        widget_type = data['widget_type']
        goal_type = data.get('goal_type', '')
        
        # For goal_bar and labels: use 'all' platform, goal_type determines what it tracks
        # For viewer_count, chat_box, sponsor_banner: always 'all' platform
        # For alert_box, event_list: use specified platform
        if widget_type in ('viewer_count', 'chat_box', 'sponsor_banner'):
            platform = 'all'
        else:
            platform = data.get('platform', 'all')
        
        # Lookup and create logic
        if widget_type in ('goal_bar', 'labels'):
            # Include goal_type in lookup
            widget, created = WidgetConfig.objects.get_or_create(
                user=user,
                widget_type=widget_type,
                platform=platform,
                goal_type=goal_type,
                defaults={
                    'name': data.get('name', f'{widget_type.replace("_", " ").title()} - {goal_type.replace("_", " ").title()}'),
                    'config': data.get('config', {}),
                    'enabled': False
                }
            )
        else:
            # For other widgets: just widget_type + platform (goal_type is always empty)
            widget, created = WidgetConfig.objects.get_or_create(
                user=user,
                widget_type=widget_type,
                platform=platform,
                goal_type='',
                defaults={
                    'name': data.get('name', f'{widget_type.replace("_", " ").title()} - {platform.title()}'),
                    'config': data.get('config', {}),
                    'enabled': False
                }
            )
        
        # Update if not created
        if not created:
            if 'name' in data:
                widget.name = data['name']
            if 'config' in data:
                widget.config = data['config']
            widget.save()
            
            # Send refresh to widget in OBS
            send_widget_refresh(user.id, widget_type, platform)
        else:
            # Auto-create default event configs for alert_box
            if widget_type == 'alert_box':
                EVENT_TEMPLATES = {
                    'twitch': {
                        'follow': '{name} just followed!',
                        'subscribe': '{name} just subscribed!',
                        'bits': '{name} donated {amount} bits!',
                        'raid': '{name} just raided with {viewers} viewers!',
                        'host': '{name} just hosted with {viewers} viewers!',
                    },
                    'youtube': {
                        'subscribe': '{name} just subscribed!',
                        'member': '{name} became a member!',
                        'superchat': '{name} sent {amount} in Super Chat!',
                    },
                    'kick': {
                        'follow': '{name} just followed!',
                        'subscribe': '{name} just subscribed!',
                        'gift_sub': '{name} gifted {amount} subs!',
                    }
                }
                
                templates = EVENT_TEMPLATES.get(platform, {})
                for event_type, message_template in templates.items():
                    WidgetEvent.objects.get_or_create(
                        widget=widget,
                        event_type=event_type,
                        platform=platform,
                        defaults={
                            'enabled': True,
                            'config': {
                                'message_template': message_template,
                                'duration': 5,
                                'alert_animation': 'fade',
                                'font_size': 32,
                                'font_weight': 'normal',
                                'font_family': 'Arial',
                                'text_color': '#FFFFFF',
                                'sound_volume': 50,
                                'layout': 'image_above'
                            }
                        }
                    )
        
        UserActivity.objects.create(
            user=user,
            activity_type='widget_create' if created else 'widget_update',
            source='app',
            details={'widget_type': widget.widget_type, 'platform': platform, 'widget_id': widget.id, 'goal_type': goal_type}
        )
        
        widget_url = f'https://bomby.us/fuzeobs/w/{widget.token}'
        
        return JsonResponse({
            'success': True,
            'id': widget.id,
            'url': widget_url,
            'widget': {
                'id': widget.id,
                'type': widget.widget_type,
                'platform': widget.platform,
                'goal_type': widget.goal_type,
                'name': widget.name,
                'config': widget.config,
                'url': widget_url,
                'enabled': widget.enabled
            }
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
@require_http_methods(["DELETE"])
@require_tier('free')
def fuzeobs_delete_widget(request, widget_type):
    """Delete ALL widgets of a type for user - cascades to events via model FK"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        user = get_user_from_token(token)
    else:
        user = None
    
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        # Delete ALL widgets of this type for user
        deleted_count, _ = WidgetConfig.objects.filter(user=user, widget_type=widget_type).delete()
        return JsonResponse({'success': True, 'deleted': deleted_count})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)
@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_toggle_widget(request):
    """Toggle widget enabled/disabled state"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        user = get_user_from_token(token)
    else:
        user = None
    
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        data = json.loads(request.body)
        widget_id = data.get('widget_id')
        enabled = data.get('enabled', True)
        
        widget = WidgetConfig.objects.get(id=widget_id, user=user)
        widget.enabled = enabled
        widget.save()
        
        return JsonResponse({'success': True, 'enabled': widget.enabled})
    except WidgetConfig.DoesNotExist:
        return JsonResponse({'error': 'Widget not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ===== PLATFORM CONNECTIONS =====

PLATFORM_OAUTH_CONFIG = {
    'twitch': {
        'auth_url': 'https://id.twitch.tv/oauth2/authorize',
        'token_url': 'https://id.twitch.tv/oauth2/token',
        'client_id': os.environ.get('TWITCH_CLIENT_ID', ''),
        'client_secret': os.environ.get('TWITCH_CLIENT_SECRET', ''),
        'scopes': ['channel:read:subscriptions', 'bits:read', 'channel:read:redemptions', 'moderator:read:followers', 'chat:read']
    },
    'youtube': {
        'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token_url': 'https://oauth2.googleapis.com/token',
        'client_id': os.environ.get('YOUTUBE_CLIENT_ID', ''),
        'client_secret': os.environ.get('YOUTUBE_CLIENT_SECRET', ''),
        'scopes': [
            'https://www.googleapis.com/auth/youtube.readonly',
            'https://www.googleapis.com/auth/youtube.force-ssl'
        ]
    },
    'kick': {
        'auth_url': 'https://id.kick.com/oauth/authorize',
        'token_url': 'https://id.kick.com/oauth/token',
        'client_id': os.environ.get('KICK_CLIENT_ID', ''),
        'client_secret': os.environ.get('KICK_CLIENT_SECRET', ''),
        'scopes': ['user:read', 'channel:read', 'events:subscribe']
    },
    'facebook': {
        'auth_url': 'https://www.facebook.com/v18.0/dialog/oauth',
        'token_url': 'https://graph.facebook.com/v18.0/oauth/access_token',
        'client_id': os.environ.get('FACEBOOK_CLIENT_ID', ''),
        'client_secret': os.environ.get('FACEBOOK_CLIENT_SECRET', ''),
        'scopes': ['pages_show_list', 'pages_read_engagement']
    },
    'tiktok': {
        'auth_url': 'https://www.tiktok.com/v2/auth/authorize',
        'token_url': 'https://open.tiktokapis.com/v2/oauth/token/',
        'client_id': os.environ.get('TIKTOK_CLIENT_KEY', ''),
        'client_secret': os.environ.get('TIKTOK_CLIENT_SECRET', ''),
        'scopes': ['user.info.profile', 'user.info.stats']
    }
}

def generate_pkce_pair():
    """Generate PKCE code_verifier and code_challenge"""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge

@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuzeobs_get_platforms(request):
    """Get connected platforms for user"""
    user = request.fuzeobs_user
    platforms = PlatformConnection.objects.filter(user=user)
    
    return JsonResponse({
        'platforms': [{
            'platform': p.platform,
            'username': p.platform_username,
            'connected_at': p.connected_at.isoformat(),
            'expires_at': p.expires_at.isoformat() if p.expires_at else None
        } for p in platforms]
    })

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_connect_platform(request):
    user = request.fuzeobs_user
    try:
        data = json.loads(request.body)
        platform = data['platform']
        
        if platform not in PLATFORM_OAUTH_CONFIG:
            return JsonResponse({'error': 'Invalid platform'}, status=400)
        
        config = PLATFORM_OAUTH_CONFIG[platform]
        state = secrets.token_urlsafe(32)
        
        if platform in ('kick', 'tiktok'):
            code_verifier, code_challenge = generate_pkce_pair()
            cache.set(f'oauth_state_{state}', {'user_id': user.id, 'platform': platform, 'code_verifier': code_verifier}, timeout=600)
        else:
            cache.set(f'oauth_state_{state}', {'user_id': user.id, 'platform': platform}, timeout=600)
        
        redirect_uri = f'https://bomby.us/fuzeobs/callback/{platform}'
        scopes = ' '.join(config['scopes']) if platform != 'tiktok' else ','.join(config['scopes'])
        
        if platform == 'tiktok':
            auth_url = f"{config['auth_url']}?client_key={config['client_id']}&redirect_uri={redirect_uri}&response_type=code&scope={scopes}&state={state}&code_challenge={code_challenge}&code_challenge_method=S256"
        else:
            auth_url = f"{config['auth_url']}?client_id={config['client_id']}&redirect_uri={redirect_uri}&response_type=code&scope={scopes}&state={state}"
        
        if platform == 'youtube':
            auth_url += '&access_type=offline&prompt=consent'
        elif platform == 'kick':
            auth_url += f'&code_challenge={code_challenge}&code_challenge_method=S256'
        elif platform == 'twitch':
            auth_url += '&force_verify=true'  

        return JsonResponse({'success': True, 'auth_url': auth_url, 'state': state})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_tiktok_exchange(request):
    """Exchange TikTok auth code for token (desktop localhost flow)"""
    user = request.fuzeobs_user
    try:
        data = json.loads(request.body)
        code = data['code']
        state = data['state']
        
        state_data = cache.get(f'oauth_state_{state}')
        if not state_data or state_data['platform'] != 'tiktok':
            return JsonResponse({'error': 'Invalid state'}, status=400)
        
        config = PLATFORM_OAUTH_CONFIG['tiktok']
        redirect_uri = 'http://localhost:5050/tiktok-callback'
        
        token_data = {
            'client_key': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
            'code_verifier': state_data['code_verifier']
        }
        
        token_response = requests.post(config['token_url'], 
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=token_data)
        
        if token_response.status_code != 200:
            print(f'[TIKTOK] Token exchange failed: {token_response.text}')
            return JsonResponse({'error': f'Token exchange failed: {token_response.text}'}, status=400)
        
        token_json = token_response.json()
        print(f'[TIKTOK] Token response: {token_json}')
        
        if 'error' in token_json or token_json.get('error_code'):
            error_msg = token_json.get('error_description') or token_json.get('message') or str(token_json)
            return JsonResponse({'error': f'TikTok error: {error_msg}'}, status=400)
        
        access_token = token_json.get('access_token') or token_json.get('data', {}).get('access_token')
        refresh_token = token_json.get('refresh_token') or token_json.get('data', {}).get('refresh_token', '')
        expires_in = token_json.get('expires_in') or token_json.get('data', {}).get('expires_in', 86400)
        
        if not access_token:
            return JsonResponse({'error': f'No access token in response: {token_json}'}, status=400)
        
        username, platform_user_id = get_platform_username('tiktok', access_token)
        
        PlatformConnection.objects.update_or_create(
            user=user,
            platform='tiktok',
            defaults={
                'platform_username': username,
                'platform_user_id': platform_user_id,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_at': timezone.now() + timedelta(seconds=expires_in)
            }
        )
        
        try:
            start_tiktok_listener(user.id, username)
            print(f'[TIKTOK] Started listener for user {user.id} (@{username})')
        except Exception as e:
            print(f'[TIKTOK] Error starting listener: {e}')
        
        cache.delete(f'oauth_state_{state}')
        
        return JsonResponse({'success': True, 'username': username})
    except Exception as e:
        print(f'[TIKTOK] Exchange error: {e}')
        return JsonResponse({'error': str(e)}, status=400)
    
@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_disconnect_platform(request):
    """Disconnect platform"""
    user = request.fuzeobs_user
    
    try:
        data = json.loads(request.body)
        platform = data['platform']
        
        # Stop Kick listener if disconnecting Kick
        if platform == 'kick':
            try:
                conn = PlatformConnection.objects.get(user=user, platform=platform)
                stop_kick_listener(conn.platform_username)
            except: pass

        # Stop YouTube listener if disconnecting YouTube
        elif platform == 'youtube':
            try:
                stop_youtube_listener(user.id)
            except:
                pass
        
        # Stop Facebook listener if disconnecting Facebook
        elif platform == 'facebook':
            try:
                conn = PlatformConnection.objects.get(user=user, platform=platform)
                stop_facebook_listener(conn.platform_user_id)
            except:
                pass

        # Stop TikTok listener if disconnecting TikTok
        elif platform == 'tiktok':
            try:
                stop_tiktok_listener(user.id)
            except:
                pass
        
        PlatformConnection.objects.filter(user=user, platform=platform).delete()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def fuzeobs_platform_callback(request, platform):
    """OAuth callback handler"""
    from .twitch import subscribe_twitch_events
    
    code = request.GET.get('code')
    state = request.GET.get('state')
    
    if not code or not state:
        return HttpResponse('Invalid callback', status=400)
    
    state_data = cache.get(f'oauth_state_{state}')
    if not state_data or state_data['platform'] != platform:
        return HttpResponse('Invalid state', status=400)
    
    user = User.objects.get(id=state_data['user_id'])
    config = PLATFORM_OAUTH_CONFIG[platform]
    
    redirect_uri = f'https://bomby.us/fuzeobs/callback/{platform}'
    
    # Build token request - TikTok uses client_key instead of client_id
    if platform == 'tiktok':
        token_data = {
            'client_key': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        }
    else:
        token_data = {
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        }
    
    # Add code_verifier for Kick and TikTok (PKCE)
    if platform in ('kick', 'tiktok') and 'code_verifier' in state_data:
        token_data['code_verifier'] = state_data['code_verifier']
    
    token_response = requests.post(config['token_url'], 
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data=token_data)
    
    if token_response.status_code != 200:
        print(f'[{platform.upper()}] Token exchange failed: {token_response.text}')
        return HttpResponse(f'Token exchange failed: {token_response.text}', status=400)
    
    token_json = token_response.json()
    
    # TikTok may nest tokens in 'data' object
    if platform == 'tiktok':
        access_token = token_json.get('access_token') or token_json.get('data', {}).get('access_token')
        refresh_token = token_json.get('refresh_token') or token_json.get('data', {}).get('refresh_token', '')
        expires_in = token_json.get('expires_in') or token_json.get('data', {}).get('expires_in', 86400)
    else:
        access_token = token_json['access_token']
        refresh_token = token_json.get('refresh_token', '')
        expires_in = token_json.get('expires_in', 3600)
    
    # Facebook returns page token as 3rd value
    if platform == 'facebook':
        username, platform_user_id, page_token = get_platform_username(platform, access_token)
        actual_token = page_token
    else:
        username, platform_user_id = get_platform_username(platform, access_token)
        actual_token = access_token
    
    PlatformConnection.objects.update_or_create(
        user=user,
        platform=platform,
        defaults={
            'platform_username': username,
            'platform_user_id': platform_user_id,
            'access_token': actual_token,
            'refresh_token': refresh_token,
            'expires_at': timezone.now() + timedelta(seconds=expires_in)
        }
    )
    
    # Subscribe to platform events
    if platform == 'twitch' and platform_user_id:
        try:
            subscribe_twitch_events(user.id, platform_user_id, access_token)
        except Exception as e:
            print(f'Error subscribing to Twitch events: {e}')
    elif platform == 'youtube':
        try:
            start_youtube_listener(user.id, access_token)
            print(f'[YOUTUBE] Started listener for user {user.id}')
        except Exception as e:
            print(f'[YOUTUBE] Error starting listener: {e}')
    elif platform == 'kick':
        try:
            start_kick_listener(user.id, username)
            print(f'[KICK] Started listener for user {user.id} ({username})')
        except Exception as e:
            print(f'[KICK] Error starting listener: {e}')
    elif platform == 'facebook':
        try:
            start_facebook_listener(user.id, platform_user_id, actual_token)
            print(f'[FACEBOOK] Started listener for user {user.id}, page {platform_user_id}')
        except Exception as e:
            print(f'[FACEBOOK] Error starting listener: {e}')
    elif platform == 'tiktok':
        try:
            start_tiktok_listener(user.id, username)
            print(f'[TIKTOK] Started listener for user {user.id} (@{username})')
        except Exception as e:
            print(f'[TIKTOK] Error starting listener: {e}')
    
    cache.delete(f'oauth_state_{state}')
    
    return render(request, 'FUZEOBS/platform_connected.html', {'platform': platform})

def get_platform_username(platform, access_token):
    """Get username and user ID from platform API"""
    import requests
    
    if platform == 'twitch':
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Client-Id': PLATFORM_OAUTH_CONFIG['twitch']['client_id']
        }
        response = requests.get('https://api.twitch.tv/helix/users', headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data['data'][0]['login'], data['data'][0]['id']
    
    elif platform == 'youtube':
        # First try the channels API
        response = requests.get(
            'https://www.googleapis.com/youtube/v3/channels',
            params={'part': 'snippet', 'mine': 'true'},
            headers={'Authorization': f'Bearer {access_token}'}
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('items'):
                return data['items'][0]['snippet']['title'], data['items'][0]['id']
        
        # Fallback to userinfo (no quota cost)
        userinfo_resp = requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        if userinfo_resp.status_code == 200:
            userinfo = userinfo_resp.json()
            return userinfo.get('name', 'YouTube User'), userinfo.get('sub', '')
        
        return 'YouTube User', ''
    
    elif platform == 'kick':
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get('https://api.kick.com/public/v1/users', 
                                   headers=headers, 
                                   timeout=10)
            print(f'[KICK] /users Status: {response.status_code}')
            print(f'[KICK] /users Response: {response.text[:1000]}')
            
            if response.status_code == 200:
                data = response.json()
                print(f'[KICK] Parsed JSON: {data}')
                
                if data.get('data') and len(data['data']) > 0:
                    user = data['data'][0]
                    username = user.get('name', 'Kick User')
                    user_id = str(user.get('user_id', ''))
                    
                    print(f'[KICK] Extracted - Username: {username}, ID: {user_id}')
                    return username, user_id
                else:
                    print('[KICK] No user data in response')
                    return 'Kick User', ''
            else:
                print(f'[KICK] Failed with status {response.status_code}')
                return 'Kick User', ''
                
        except Exception as e:
            print(f'[KICK] Exception: {e}')
            import traceback
            traceback.print_exc()
            return 'Kick User', ''
    
    elif platform == 'facebook':
        response = requests.get(
            'https://graph.facebook.com/v18.0/me/accounts',
            params={'access_token': access_token}
        )
        print(f'[FACEBOOK] /me/accounts: {response.status_code} - {response.text[:500]}')
        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                page = data['data'][0]
                # Return page token as 3rd element
                return page.get('name', 'Facebook Page'), page.get('id', ''), page.get('access_token', access_token)
        return 'Facebook User', '', access_token
    
    if platform == 'tiktok':
        resp = requests.get(
            'https://open.tiktokapis.com/v2/user/info/',
            params={'fields': 'open_id,display_name,avatar_url'},
            headers={'Authorization': f'Bearer {access_token}'}
        )
        print(f'[TIKTOK] User info: {resp.status_code} - {resp.text[:500]}')
        if resp.status_code == 200:
            data = resp.json().get('data', {}).get('user', {})
            return data.get('display_name', 'TikTok User'), data.get('open_id', '')
        return 'TikTok User', ''
    
    return 'Unknown', ''

# ===== MEDIA LIBRARY =====
@csrf_exempt
@xframe_options_exempt
@csrf_exempt
@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuzeobs_get_media(request):
    """Get user's media library"""
    user = request.fuzeobs_user
    media = MediaLibrary.objects.filter(user=user).order_by('-uploaded_at')
    
    total_size = sum(m.file_size for m in media)
    max_size = 25 * 1024 * 1024  # 25MB for free, could increase for pro
    
    if user.fuzeobs_tier in ['pro', 'lifetime']:
        max_size = 100 * 1024 * 1024  # 100MB
    
    DEFAULT_MEDIA = [
        {
            'id': 'default-image',
            'name': 'Default Alert Image',
            'type': 'image',
            'url': 'https://storage.googleapis.com/fuzeobs-public/media/default-alert.gif',
            'size': 0,
            'is_default': True,
        },
        {
            'id': 'default-sound',
            'name': 'Default Alert Sound',
            'type': 'sound',
            'url': 'https://storage.googleapis.com/fuzeobs-public/media/default-alert.mp3',
            'size': 0,
            'is_default': True,
        },
    ]
    
    user_media = [{
        'id': m.id,
        'name': m.name,
        'type': m.media_type,
        'url': m.file_url,
        'size': m.file_size,
        'is_default': False,
        'uploaded_at': m.uploaded_at.isoformat()
    } for m in media]
    
    return JsonResponse({
        'media': DEFAULT_MEDIA + user_media,
        'total_size': total_size,
        'max_size': max_size
    })

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_upload_media(request):
    user = request.fuzeobs_user
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'error': 'No file'}, status=400)
    
    max_size = 100 * 1024 * 1024 if user.fuzeobs_tier in ['pro', 'lifetime'] else 25 * 1024 * 1024
    current = sum(m.file_size for m in MediaLibrary.objects.filter(user=user))
    
    if current + file.size > max_size:
        return JsonResponse({'error': 'Storage limit exceeded'}, status=400)
    
    if file.content_type.startswith('image'):
        media_type = 'image'
    elif file.content_type.startswith('audio'):
        media_type = 'sound'
    elif file.content_type.startswith('video'):
        media_type = 'video'
    else:
        return JsonResponse({'error': 'Invalid type'}, status=400)
    
    client = storage.Client()
    bucket = client.bucket('fuzeobs-public')
    ext = file.name.split('.')[-1]
    filename = f'{uuid.uuid4()}.{ext}'
    blob = bucket.blob(f'media/{user.id}/{filename}')
    blob.upload_from_file(
        file, 
        content_type=file.content_type,
        predefined_acl='publicRead'
    )
    blob.cache_control = 'public, max-age=31536000'
    blob.patch()
    
    file_url = blob.public_url
    
    media = MediaLibrary.objects.create(
        user=user,
        name=file.name,
        media_type=media_type,
        file_url=file_url,
        file_size=file.size
    )
    
    return JsonResponse({
        'success': True,
        'media': {
            'id': media.id,
            'name': media.name,
            'type': media.media_type,
            'url': media.file_url,
            'size': media.file_size
        }
    })

@csrf_exempt
@require_http_methods(["DELETE"])
@require_tier('free')
def fuzeobs_delete_media(request, media_id):
    user = request.fuzeobs_user
    try:
        media = MediaLibrary.objects.get(id=media_id, user=user)
        
        try:
            client = storage.Client()
            bucket = client.bucket('fuzeobs-public')
            blob_path = '/'.join(media.file_url.split('/')[-3:])
            blob = bucket.blob(blob_path)
            blob.delete()
        except:
            pass
        
        media.delete()
        return JsonResponse({'success': True})
    except MediaLibrary.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

# ===== WIDGET EVENTS =====

@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuzeobs_get_widget_events(request, widget_id):
    """Get event configurations for widget"""
    user = request.fuzeobs_user
    
    try:
        widget = WidgetConfig.objects.get(id=widget_id, user=user)
        
        # Auto-create missing default events if widget is alert_box
        if widget.widget_type == 'alert_box':
            EVENT_TEMPLATES = {
                'twitch': {
                    'follow': '{name} just followed!',
                    'subscribe': '{name} just subscribed!',
                    'bits': '{name} donated {amount} bits!',
                    'raid': '{name} just raided with {viewers} viewers!',
                    'host': '{name} just hosted with {viewers} viewers!',
                },
                'youtube': {
                    'subscribe': '{name} just subscribed!',
                    'superchat': '{name} sent {amount} in Super Chat!',
                    'supersticker': '{name} sent a Super Sticker!',
                    'member': '{name} became a member!',
                    'milestone': '{name} hit {months} month milestone!',
                    'gift': '{name} gifted memberships!',
                },
                'kick': {
                    'follow': '{name} just followed!',
                    'subscribe': '{name} just subscribed!',
                    'gift_sub': '{name} gifted {amount} subs!',
                }
            }
            
            templates = EVENT_TEMPLATES.get(widget.platform, {})
            for event_type, message_template in templates.items():
                WidgetEvent.objects.get_or_create(
                    widget=widget,
                    event_type=event_type,
                    platform=widget.platform,
                    defaults={
                        'enabled': True,
                        'config': {
                            'message_template': message_template,
                            'duration': 5,
                            'alert_animation': 'fade',
                            'font_size': 32,
                            'font_weight': 'normal',
                            'font_family': 'Arial',
                            'text_color': '#FFFFFF',
                            'sound_volume': 50,
                            'layout': 'image_above'
                        }
                    }
                )
        events = WidgetEvent.objects.filter(widget=widget)
        
        return JsonResponse({
            'events': [{
                'id': e.id,
                'event_type': e.event_type,
                'platform': e.platform,
                'enabled': e.enabled,
                'config': e.config
            } for e in events]
        })
        
    except WidgetConfig.DoesNotExist:
        return JsonResponse({'error': 'Widget not found'}, status=404)

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_save_widget_event(request):
    user = request.fuzeobs_user
    
    try:
        data = json.loads(request.body)
        widget_id = data['widget_id']
        event_type = data['event_type']
        platform = data['platform']
        config = data.get('config', {})
        
        widget = WidgetConfig.objects.get(id=widget_id, user=user)
        
        event, created = WidgetEvent.objects.update_or_create(
            widget=widget,
            event_type=event_type,
            platform=platform,
            defaults={
                'enabled': True,
                'config': config
            }
        )
        
        # Send refresh message to OBS via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'alerts_{user.id}_{platform}',
            {
                'type': 'alert_event',
                'data': {
                    'type': 'refresh'
                }
            }
        )
        
        return JsonResponse({
            'success': True,
            'event': {
                'id': event.id,
                'event_type': event.event_type,
                'platform': event.platform,
                'enabled': event.enabled,
                'config': event.config
            }
        })
        
    except WidgetConfig.DoesNotExist:
        return JsonResponse({'error': 'Widget not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
@require_http_methods(["DELETE"])
@require_tier('free')
def fuzeobs_delete_widget_event(request, event_id):
    """Delete event configuration"""
    user = request.fuzeobs_user
    
    try:
        event = WidgetEvent.objects.get(id=event_id, widget__user=user)
        event.delete()
        return JsonResponse({'success': True})
        
    except WidgetEvent.DoesNotExist:
        return JsonResponse({'error': 'Event not found'}, status=404)
    
@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_test_alert(request):
    try:
        data = json.loads(request.body)
        event_type = data.get('event_type')
        platform = data.get('platform')
        widget_type = data.get('widget_type', 'alert_box')
        
        user = request.fuzeobs_user
        
        # Build event data based on event type
        random_amount = random.randint(1, 100)
        
        # Format amount based on event type
        if event_type == 'bits':
            formatted_amount = str(random.randint(100, 5000))  # bits are just numbers
        elif event_type == 'stars':
            formatted_amount = str(random.randint(10, 500))  # stars are just numbers
        else:
            formatted_amount = f'${random_amount:.2f}'  # donations/superchat use $
        
        event_data = {
            'username': 'FuzeOBS',
            'amount': formatted_amount,
            'raw_amount': random_amount,
            'viewers': random.randint(1, 2000),
            'count': random.randint(1, 100),
            'gift': 'Rose',
            'message': 'Test message!',
            'months': random.randint(1, 24),
        }
        
        channel_layer = get_channel_layer()
        
        # Route to correct channel based on widget_type
        if widget_type == 'labels':
            # Send to labels channel
            async_to_sync(channel_layer.group_send)(
                f'labels_{user.id}',
                {
                    'type': 'label_update',
                    'data': {
                        'type': event_type,
                        'event_type': event_type,
                        'platform': platform,
                        'event_data': event_data,
                    }
                }
            )
        elif widget_type == 'event_list':
            # Send to donations channel for event list (it listens there)
            if platform == 'donation' or event_type == 'donation':
                async_to_sync(channel_layer.group_send)(
                    f'donations_{user.id}',
                    {
                        'type': 'donation_event',
                        'data': {
                            'type': 'donation',
                            'event_type': 'donation',
                            'platform': 'donation',
                            'event_data': event_data,
                        }
                    }
                )
            else:
                # Send to platform-specific alerts channel for event list
                async_to_sync(channel_layer.group_send)(
                    f'alerts_{user.id}_{platform}',
                    {
                        'type': 'alert_event',
                        'data': {
                            'platform': platform,
                            'event_type': event_type,
                            'event_data': event_data,
                        }
                    }
                )
        elif widget_type == 'goal_bar':
            # For donation/tip goals, send to donations channel
            if platform == 'donation' or event_type == 'donation':
                async_to_sync(channel_layer.group_send)(
                    f'donations_{user.id}',
                    {
                        'type': 'donation_event',
                        'data': {
                            'type': 'donation',
                            'event_type': 'donation',
                            'platform': 'donation',
                            'event_data': event_data,
                        }
                    }
                )
            else:
                # For other goals (follower, subscriber, etc.), send to alerts channel
                async_to_sync(channel_layer.group_send)(
                    f'alerts_{user.id}_{platform}',
                    {
                        'type': 'alert_event',
                        'data': {
                            'platform': platform,
                            'event_type': event_type,
                            'event_data': event_data,
                        }
                    }
                )
        else:
            # Default: send to alertbox channel
            # For donations, also send to donations channel
            if platform == 'donation' or event_type == 'donation':
                async_to_sync(channel_layer.group_send)(
                    f'donations_{user.id}',
                    {
                        'type': 'donation_event',
                        'data': {
                            'type': 'donation',
                            'event_type': 'donation',
                            'platform': 'donation',
                            'event_data': event_data,
                        }
                    }
                )
            else:
                async_to_sync(channel_layer.group_send)(
                    f'alerts_{user.id}_{platform}',
                    {
                        'type': 'alert_event',
                        'data': {
                            'platform': platform,
                            'event_type': event_type,
                            'event_data': event_data,
                            'clear_existing': True
                        }
                    }
                )
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
    
@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_get_widget_event_configs(request, user_id, platform):
    """Get event configurations for user's widgets - supports 'all' platform"""
    try:
        if platform == 'all':
            # For 'all' platform, get events from all alert_box widgets for this user
            widgets = WidgetConfig.objects.filter(user_id=user_id, widget_type='alert_box')
        else:
            widgets = WidgetConfig.objects.filter(user_id=user_id, platform=platform)
        
        configs = {}
        
        for widget in widgets:
            if platform == 'all':
                # Get events for all platforms
                events = WidgetEvent.objects.filter(widget=widget, enabled=True)
            else:
                events = WidgetEvent.objects.filter(widget=widget, platform=platform, enabled=True)
            
            for event in events:
                key = f"{event.platform}-{event.event_type}"
                configs[key] = event.config
                configs[key]['enabled'] = True
        
        response = JsonResponse({'configs': configs})
        response['Access-Control-Allow-Origin'] = '*'
        response['Cache-Control'] = 'no-cache'
        return response
    except Exception as e:
        response = JsonResponse({'configs': {}})
        response['Access-Control-Allow-Origin'] = '*'
        return response
    
# =========== TWITCH ALERTS ===========
@csrf_exempt
def fuzeobs_twitch_webhook(request):
    """Receive Twitch EventSub webhooks"""
    import hmac
    import hashlib
    
    message_id = request.headers.get('Twitch-Eventsub-Message-Id', '')
    timestamp = request.headers.get('Twitch-Eventsub-Message-Timestamp', '')
    signature = request.headers.get('Twitch-Eventsub-Message-Signature', '')
    
    body = request.body.decode('utf-8')
    message = message_id + timestamp + body
    expected = 'sha256=' + hmac.new(
        settings.TWITCH_WEBHOOK_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected, signature):
        return JsonResponse({'error': 'Invalid signature'}, status=403)
    
    data = json.loads(body)
    msg_type = request.headers.get('Twitch-Eventsub-Message-Type')
    
    # DEBUG: print(f'[WEBHOOK] Type: {msg_type}')
    
    if msg_type == 'webhook_callback_verification':
        return HttpResponse(data['challenge'], content_type='text/plain')
    
    if msg_type == 'notification':
        event = data['event']
        sub_type = data['subscription']['type']
        condition = data['subscription']['condition']
        
        # DEBUG: print(f'[WEBHOOK] Event: {sub_type}')
        # DEBUG: print(f'[WEBHOOK] Event data: {event}')
        
        broadcaster_id = condition.get('broadcaster_user_id') or condition.get('to_broadcaster_user_id')
        try:
            conn = PlatformConnection.objects.get(platform='twitch', platform_user_id=broadcaster_id)
            
            # DEBUG: print(f'[WEBHOOK] Found user: {conn.user.id}')
            
            event_map = {
                'channel.follow': ('follow', {'username': event.get('user_name', event.get('user_login', 'Unknown'))}),
                'channel.subscribe': ('subscribe', {'username': event.get('user_name', 'Unknown')}),
                'channel.subscription.gift': ('subscribe', {'username': event.get('user_name', 'Anonymous'), 'amount': event.get('total', 1)}),
                'channel.cheer': ('bits', {'username': event.get('user_name', 'Unknown'), 'amount': event.get('bits', 0)}),
                'channel.raid': ('raid', {'username': event.get('from_broadcaster_user_name', 'Unknown'), 'viewers': event.get('viewers', 0)}),
            }
            
            if sub_type in event_map:
                event_type, event_data = event_map[sub_type]
                # DEBUG: print(f'[WEBHOOK] Sending alert: {event_type} - {event_data}')
                send_alert(conn.user.id, event_type, 'twitch', event_data)
                # DEBUG: print(f'[WEBHOOK] Alert sent!')
        except Exception as e:
            print(f'[WEBHOOK ERROR] {e}')
    
    return JsonResponse({'status': 'ok'})

# =========== YOUTUBE ALERTS ===========
@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_youtube_start_listener(request, user_id):
    """Start YouTube listener if user is live"""
    try:
        conn = PlatformConnection.objects.get(user_id=user_id, platform='youtube')
        from .youtube import start_youtube_listener
        started = start_youtube_listener(user_id, conn.access_token)
        
        response = JsonResponse({'started': started})
        response['Access-Control-Allow-Origin'] = '*'
        return response
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'started': False})
    except Exception as e:
        print(f'[YOUTUBE] Error starting listener: {e}')
        return JsonResponse({'started': False})
    
# =========== FACEBOOK ALERTS ===========
@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_facebook_start_listener(request, user_id):
    """Start Facebook listener"""
    try:
        conn = PlatformConnection.objects.get(user_id=user_id, platform='facebook')
        started = start_facebook_listener(user_id, conn.platform_user_id, conn.access_token)
        
        response = JsonResponse({'started': started})
        response['Access-Control-Allow-Origin'] = '*'
        return response
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'started': False})
    except Exception as e:
        print(f'[FACEBOOK] Error starting listener: {e}')
        return JsonResponse({'started': False})

# =========== KICK ALERTS ===========
@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_kick_start_listener(request, user_id):
    """Start Kick listener"""
    try:
        conn = PlatformConnection.objects.get(user_id=user_id, platform='kick')
        started = start_kick_listener(user_id, conn.platform_username)
        
        response = JsonResponse({'started': started})
        response['Access-Control-Allow-Origin'] = '*'
        return response
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'started': False})
    except Exception as e:
        print(f'[KICK] Error starting listener: {e}')
        return JsonResponse({'started': False})

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_kick_webhook(request):
    """Handle Kick webhook events"""
    try:
        event_type = request.headers.get('Kick-Event-Type', '')
        data = json.loads(request.body)
        
        # Follow event
        if event_type == 'channel.followed':
            follower_username = data.get('follower', {}).get('username', 'Someone')
            broadcaster_id = data.get('broadcaster', {}).get('user_id')
            
            try:
                conn = PlatformConnection.objects.get(platform='kick', platform_user_id=str(broadcaster_id))
                send_alert(conn.user_id, 'follow', 'kick', {'username': follower_username})
                print(f'[KICK] Webhook follow: {follower_username}')
            except PlatformConnection.DoesNotExist:
                print(f'[KICK] No connection for broadcaster {broadcaster_id}')
        
        # New subscription event
        elif event_type == 'channel.subscription.new':
            subscriber_username = data.get('subscriber', {}).get('username', 'Someone')
            broadcaster_id = data.get('broadcaster', {}).get('user_id')
            
            try:
                conn = PlatformConnection.objects.get(platform='kick', platform_user_id=str(broadcaster_id))
                send_alert(conn.user_id, 'subscribe', 'kick', {'username': subscriber_username})
                print(f'[KICK] Webhook sub: {subscriber_username}')
            except PlatformConnection.DoesNotExist:
                print(f'[KICK] No connection for broadcaster {broadcaster_id}')
        
        # Gift subscription event
        elif event_type == 'channel.subscription.gifts':
            gifter = data.get('gifter', {})
            gifter_username = gifter.get('username') if not gifter.get('is_anonymous') else 'Anonymous'
            giftees = data.get('giftees', [])
            gift_count = len(giftees)
            broadcaster_id = data.get('broadcaster', {}).get('user_id')
            
            try:
                conn = PlatformConnection.objects.get(platform='kick', platform_user_id=str(broadcaster_id))
                send_alert(conn.user_id, 'gift_sub', 'kick', {
                    'username': gifter_username,
                    'amount': gift_count
                })
                print(f'[KICK] Webhook gift sub: {gifter_username} gifted {gift_count}')
            except PlatformConnection.DoesNotExist:
                print(f'[KICK] No connection for broadcaster {broadcaster_id}')
        
        return JsonResponse({'status': 'ok'}, status=200)
    
    except Exception as e:
        print(f'[KICK] Webhook error: {e}')
        return JsonResponse({'error': str(e)}, status=500)

# =========== TIKTOK ALERTS ===========
@csrf_exempt
def fuzeobs_tiktok_start_listener(request, user_id):
    """Start TikTok listener - needs username only"""
    try:
        conn = PlatformConnection.objects.get(user_id=user_id, platform='tiktok')
        tiktok_username = conn.platform_username  # Store @username when connecting
        started = start_tiktok_listener(user_id, tiktok_username)
        return JsonResponse({'started': started})
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'error': 'Not connected'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
# =========== CHATBOX ===========  
@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_twitch_chat_start(request, user_id):
    """Start Twitch chat IRC using user's OAuth token"""
    try:
        user = User.objects.get(id=user_id)
        conn = PlatformConnection.objects.get(user=user, platform='twitch')
        
        # Refresh token if expired
        if conn.expires_at and conn.expires_at < timezone.now():
            # Twitch token refresh
            resp = requests.post('https://id.twitch.tv/oauth2/token', data={
                'client_id': settings.TWITCH_CLIENT_ID,
                'client_secret': settings.TWITCH_CLIENT_SECRET,
                'grant_type': 'refresh_token',
                'refresh_token': conn.refresh_token
            })
            if resp.status_code == 200:
                data = resp.json()
                conn.access_token = data['access_token']
                conn.refresh_token = data.get('refresh_token', conn.refresh_token)
                conn.expires_at = timezone.now() + timedelta(seconds=data['expires_in'])
                conn.save()

        started = start_twitch_chat(conn.platform_username, user_id, conn.access_token)
        
        return JsonResponse({'started': started})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)
    
@csrf_exempt
def fuzeobs_kick_chat_start(request, user_id):
    """Start Kick chat listener"""
    try:
        user = User.objects.get(id=user_id)
        conn = PlatformConnection.objects.get(user=user, platform='kick')
        started = start_kick_chat(conn.platform_username, user_id, conn.access_token)
        return JsonResponse({'started': started})
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'started': False, 'error': 'Not connected'})
    except Exception as e:
        print(f'[KICK CHAT] Error: {e}')
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def fuzeobs_facebook_chat_start(request, user_id):
    """Start Facebook chat polling"""
    try:
        user = User.objects.get(id=user_id)
        conn = PlatformConnection.objects.get(user=user, platform='facebook')
        started = start_facebook_chat(user_id, conn.platform_user_id, conn.access_token)
        return JsonResponse({'started': started})
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'started': False, 'error': 'Not connected'})
    except Exception as e:
        print(f'[FB CHAT] Error: {e}')
        return JsonResponse({'error': str(e)}, status=400)
    
# =========== LABELS ===========    
@csrf_exempt
def fuzeobs_get_label_data(request, user_id):
    """Get persisted label session data for widget reload"""
    from .models import LabelSessionData
    
    data = {}
    for item in LabelSessionData.objects.filter(user_id=user_id):
        data[item.label_type] = item.data
    return JsonResponse({'data': data})


@csrf_exempt
def fuzeobs_save_label_data(request, user_id):
    """Save label data when events occur - called from widget JS"""
    from .models import LabelSessionData
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        body = json.loads(request.body)
        label_type = body.get('label_type')
        data = body.get('data', {})
        
        if not label_type:
            return JsonResponse({'error': 'label_type required'}, status=400)
        
        LabelSessionData.objects.update_or_create(
            user_id=user_id,
            label_type=label_type,
            defaults={'data': data}
        )
        return JsonResponse({'saved': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
# =========== VIEWER COUNT ===========
# Factory pattern - replaces 5 identical functions
def _viewer_endpoint(platform: str):
    """Factory for viewer count endpoints"""
    from .views_helpers import get_platform_viewer_count
    
    @csrf_exempt
    @require_http_methods(["GET"])
    def endpoint(request, user_id):
        return JsonResponse({'viewers': get_platform_viewer_count(user_id, platform)})
    return endpoint

fuzeobs_get_twitch_viewers = _viewer_endpoint('twitch')
fuzeobs_get_youtube_viewers = _viewer_endpoint('youtube')
fuzeobs_get_kick_viewers = _viewer_endpoint('kick')
fuzeobs_get_facebook_viewers = _viewer_endpoint('facebook')
fuzeobs_get_tiktok_viewers = _viewer_endpoint('tiktok')

# ====== REVIEWS ======

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_submit_review(request):
    """Submit a review (requires auth)"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'success': False, 'error': 'Authentication required'}, status=401)
    
    token = auth_header.split(' ')[1]
    result = auth_manager.verify_token(token)
    
    if not result.get('valid'):
        return JsonResponse({'success': False, 'error': 'Invalid token'}, status=401)
    
    try:
        user = User.objects.get(id=result['user_id'])
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    platform = data.get('platform', '').lower()
    rating = data.get('rating')
    review_text = data.get('review', '').strip()
    
    # Validation
    if platform not in ['twitch', 'youtube', 'kick', 'tiktok', 'facebook', 'other']:
        return JsonResponse({'success': False, 'error': 'Invalid platform'}, status=400)
    
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return JsonResponse({'success': False, 'error': 'Rating must be 1-5'}, status=400)
    
    if not review_text or len(review_text) > 300:
        return JsonResponse({'success': False, 'error': 'Review must be 1-300 characters'}, status=400)
    
    # Profanity check
    from ACCOUNTS.validators import contains_profanity
    if contains_profanity(review_text):
        return JsonResponse({'success': False, 'error': 'Review contains inappropriate language'}, status=400)
    
    # Check if user already has a review
    from .models import FuzeOBSReview
    existing = FuzeOBSReview.objects.filter(user=user).first()
    if existing:
        # Update existing review
        existing.platform = platform
        existing.rating = rating
        existing.review = review_text
        existing.save()
        return JsonResponse({'success': True, 'message': 'Review updated'})
    
    # Create new review
    FuzeOBSReview.objects.create(
        user=user,
        platform=platform,
        rating=rating,
        review=review_text
    )
    
    return JsonResponse({'success': True, 'message': 'Review submitted'})


@require_http_methods(["GET"])
def fuzeobs_get_featured_reviews(request):
    """Get featured reviews for landing page (public)"""
    from .models import FuzeOBSReview
    
    reviews = FuzeOBSReview.objects.filter(featured=True).select_related('user')[:20]
    
    return JsonResponse({
        'success': True,
        'reviews': [{
            'username': r.user.username,
            'platform': r.platform,
            'rating': r.rating,
            'review': r.review,
            'profile_picture': r.user.profile_picture.url if r.user.profile_picture else None,
            'created_at': r.created_at.isoformat()
        } for r in reviews]
    })


# ====== REVIEWS ADMIN ======

@staff_member_required
def fuzeobs_reviews_admin(request):
    """Admin page for managing reviews"""
    from .models import FuzeOBSReview
    
    reviews = FuzeOBSReview.objects.select_related('user').all()
    featured_count = reviews.filter(featured=True).count()
    
    return render(request, 'FUZEOBS/fuzeobs_reviews.html', {
        'reviews': reviews,
        'total_reviews': reviews.count(),
        'featured_count': featured_count,
        'avg_rating': reviews.aggregate(Avg('rating'))['rating__avg'] or 0,
    })


@staff_member_required
@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_toggle_review_featured(request):
    """Toggle featured status of a review"""
    from .models import FuzeOBSReview
    
    try:
        data = json.loads(request.body)
        review_id = data.get('review_id')
        featured = data.get('featured', False)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    try:
        review = FuzeOBSReview.objects.get(id=review_id)
        review.featured = featured
        review.save()
        return JsonResponse({'success': True})
    except FuzeOBSReview.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Review not found'}, status=404)


@staff_member_required
@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_delete_review(request):
    """Delete a review"""
    from .models import FuzeOBSReview
    
    try:
        data = json.loads(request.body)
        review_id = data.get('review_id')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    try:
        review = FuzeOBSReview.objects.get(id=review_id)
        review.delete()
        return JsonResponse({'success': True})
    except FuzeOBSReview.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Review not found'}, status=404)


@staff_member_required
@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_create_review_admin(request):
    """Admin: Create a review manually"""
    from .models import FuzeOBSReview
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    username = data.get('username')
    platform = data.get('platform', '').lower()
    rating = data.get('rating')
    review_text = data.get('review', '').strip()
    featured = data.get('featured', False)
    
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    
    # Check for existing review
    if FuzeOBSReview.objects.filter(user=user).exists():
        return JsonResponse({'success': False, 'error': 'User already has a review'}, status=400)
    
    FuzeOBSReview.objects.create(
        user=user,
        platform=platform,
        rating=rating,
        review=review_text,
        featured=featured
    )
    
    return JsonResponse({'success': True})

@csrf_exempt
@require_http_methods(["POST"])
@staff_member_required
def edit_review_admin(request):
    data = json.loads(request.body)
    try:
        review = FuzeOBSReview.objects.get(id=data['review_id'])
        review.platform = data.get('platform', review.platform)
        review.rating = data.get('rating', review.rating)
        review.review = data.get('review', review.review)
        review.featured = data.get('featured', review.featured)
        review.save()
        return JsonResponse({'success': True})
    except FuzeOBSReview.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Review not found'}, status=404)

@csrf_exempt
@require_http_methods(["GET"])
def my_review(request):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)
    
    result = auth_manager.verify_token(token)
    if not result.get('valid'):
        return JsonResponse({'success': False, 'error': 'Invalid token'}, status=401)
    
    try:
        user = User.objects.get(id=result['user_id'])
        review = FuzeOBSReview.objects.filter(user=user).first()
        if review:
            return JsonResponse({
                'success': True,
                'review': {
                    'platform': review.platform,
                    'rating': review.rating,
                    'review': review.review,
                    'featured': review.featured,
                }
            })
        else:
            return JsonResponse({'success': True, 'review': None})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)

@csrf_exempt
@require_tier('free')
def fuzeobs_countdown(request):
    user = request.fuzeobs_user

    if request.method == 'GET':
        try:
            c = StreamCountdown.objects.get(user=user)
            result = {'success': True, 'countdown': None, 'schedule': None}
            if c.scheduled_at:
                result['countdown'] = {
                    'title': c.title,
                    'scheduled_at': c.scheduled_at.isoformat(),
                    'platforms': c.platforms,
                }
            if c.schedule_days:
                result['schedule'] = {
                    'title': c.title,
                    'days': c.schedule_days,
                    'time': c.schedule_time,
                    'platforms': c.platforms,
                }
            return JsonResponse(result)
        except StreamCountdown.DoesNotExist:
            return JsonResponse({'success': True, 'countdown': None, 'schedule': None})

    elif request.method == 'POST':
        data = json.loads(request.body)
        defaults = {
            'title': data.get('title', ''),
            'platforms': data.get('platforms', []),
        }

        # Recurring schedule
        if data.get('schedule_days'):
            defaults['schedule_days'] = data['schedule_days']
            defaults['schedule_time'] = data.get('schedule_time', '')
            defaults['scheduled_at'] = None
        # One-time countdown
        elif data.get('scheduled_at'):
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(data['scheduled_at'])
            if not dt:
                return JsonResponse({'error': 'Invalid datetime'}, status=400)
            defaults['scheduled_at'] = dt
            defaults['schedule_days'] = []
            defaults['schedule_time'] = ''
        else:
            return JsonResponse({'error': 'scheduled_at or schedule_days required'}, status=400)

        c, _ = StreamCountdown.objects.update_or_create(user=user, defaults=defaults)

        result = {'success': True, 'countdown': None, 'schedule': None}
        if c.scheduled_at:
            result['countdown'] = {
                'title': c.title,
                'scheduled_at': c.scheduled_at.isoformat(),
                'platforms': c.platforms,
            }
        if c.schedule_days:
            result['schedule'] = {
                'title': c.title,
                'days': c.schedule_days,
                'time': c.schedule_time,
                'platforms': c.platforms,
            }
        return JsonResponse(result)

    elif request.method == 'DELETE':
        StreamCountdown.objects.filter(user=user).delete()
        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ============ COLLAB FINDER ============
def _get_profile_pic_url(user):
    """Get full profile picture URL"""
    if hasattr(user, 'profile_picture') and user.profile_picture:
        return f'https://bomby.us{user.profile_picture.url}'
    return None

@csrf_exempt
@require_tier('free')
def collab_posts(request):
    """List collab posts (GET) or create one (POST)"""
    user = request.fuzeobs_user
    
    if request.method == 'GET':
        status_filter = request.GET.get('status', 'open')
        posts = CollabPost.objects.select_related('user').filter(status=status_filter)
        
        user_interests = set(
            CollabInterest.objects.filter(user=user).values_list('post_id', flat=True)
        )
        
        results = []
        for post in posts[:50]:
            results.append({
                'id': post.id,
                'title': post.title,
                'description': post.description[:150] + ('...' if len(post.description) > 150 else ''),
                'full_description': post.description,
                'category': post.category,
                'platforms': post.platforms,
                'tags': post.tags,
                'collab_size': post.collab_size,
                'availability': post.availability,
                'status': post.status,
                'interested_count': post.interested_count,
                'is_interested': post.id in user_interests,
                'is_owner': post.user_id == user.id,
                'username': post.user.username,
                'profile_picture': _get_profile_pic_url(post.user),
                'created_at': post.created_at.isoformat(),
            })
        
        return JsonResponse({'success': True, 'posts': results})
    
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        category = data.get('category', '')
        platforms = data.get('platforms', [])
        tags = data.get('tags', [])
        collab_size = data.get('collab_size', 'duo')
        availability = data.get('availability', '').strip()
        
        if not title or len(title) > 50:
            return JsonResponse({'success': False, 'error': 'Title required (max 50 chars)'}, status=400)
        if not description or len(description) > 200:
            return JsonResponse({'success': False, 'error': 'Description required (max 200 chars)'}, status=400)
        
        valid_categories = [c[0] for c in CollabPost.CATEGORY_CHOICES]
        if category not in valid_categories:
            return JsonResponse({'success': False, 'error': 'Invalid category'}, status=400)
        
        valid_platforms = ['twitch', 'youtube', 'kick', 'facebook', 'tiktok']
        platforms = [p for p in platforms if p in valid_platforms]
        if not platforms:
            return JsonResponse({'success': False, 'error': 'At least one platform required'}, status=400)
        
        valid_sizes = [s[0] for s in CollabPost.SIZE_CHOICES]
        if collab_size not in valid_sizes:
            collab_size = 'duo'
        
        tags = [t.strip()[:30] for t in tags[:5] if t.strip()]
        
        # Profanity check
        from ACCOUNTS.validators import contains_profanity
        for field_name, field_val in [('Title', title), ('Description', description), ('Availability', availability)]:
            if field_val and contains_profanity(field_val):
                return JsonResponse({'success': False, 'error': f'{field_name} contains inappropriate language'}, status=400)
        for tag in tags:
            if contains_profanity(tag):
                return JsonResponse({'success': False, 'error': 'Tags contain inappropriate language'}, status=400)
        
        active_count = CollabPost.objects.filter(user=user, status='open').count()
        if active_count >= 3:
            return JsonResponse({'success': False, 'error': 'Max 3 active posts allowed'}, status=400)
        
        post = CollabPost.objects.create(
            user=user,
            title=title,
            description=description,
            category=category,
            platforms=platforms,
            tags=tags,
            collab_size=collab_size,
            availability=availability,
        )
        
        return JsonResponse({'success': True, 'post_id': post.id})
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
@require_tier('free')
def collab_post_detail(request, post_id):
    """Update post (PUT) or delete (DELETE) own post"""
    user = request.fuzeobs_user
    
    try:
        post = CollabPost.objects.get(id=post_id)
    except CollabPost.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)
    
    if post.user_id != user.id:
        return JsonResponse({'success': False, 'error': 'Not your post'}, status=403)
    
    if request.method == 'PUT':
        data = json.loads(request.body)
        
        new_status = data.get('status')
        if new_status and new_status in ['open', 'filled', 'closed']:
            post.status = new_status
        
        if 'title' in data:
            title = data['title'].strip()
            if title and len(title) <= 50:
                post.title = title
        if 'description' in data:
            desc = data['description'].strip()
            if desc and len(desc) <= 200:
                post.description = desc
        if 'category' in data:
            valid_categories = [c[0] for c in CollabPost.CATEGORY_CHOICES]
            if data['category'] in valid_categories:
                post.category = data['category']
        if 'platforms' in data:
            valid_platforms = ['twitch', 'youtube', 'kick', 'facebook', 'tiktok']
            platforms = [p for p in data['platforms'] if p in valid_platforms]
            if platforms:
                post.platforms = platforms
        if 'tags' in data:
            post.tags = [t.strip()[:30] for t in data['tags'][:5] if t.strip()]
        if 'collab_size' in data:
            valid_sizes = [s[0] for s in CollabPost.SIZE_CHOICES]
            if data['collab_size'] in valid_sizes:
                post.collab_size = data['collab_size']
        if 'availability' in data:
            post.availability = data['availability'].strip()[:200]
        
        # Profanity check on all text fields
        from ACCOUNTS.validators import contains_profanity
        for field_name, field_val in [('Title', post.title), ('Description', post.description), ('Availability', post.availability)]:
            if field_val and contains_profanity(field_val):
                return JsonResponse({'success': False, 'error': f'{field_name} contains inappropriate language'}, status=400)
        for tag in post.tags:
            if contains_profanity(tag):
                return JsonResponse({'success': False, 'error': 'Tags contain inappropriate language'}, status=400)
        
        post.save()
        return JsonResponse({'success': True})
    
    elif request.method == 'DELETE':
        post.delete()
        return JsonResponse({'success': True})
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
@require_tier('free')
def collab_interest(request, post_id):
    """Toggle interest on a collab post (POST)"""
    user = request.fuzeobs_user
    
    try:
        post = CollabPost.objects.get(id=post_id)
    except CollabPost.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)
    
    if post.user_id == user.id:
        return JsonResponse({'success': False, 'error': 'Cannot express interest in your own post'}, status=400)
    
    existing = CollabInterest.objects.filter(post=post, user=user).first()
    if existing:
        existing.delete()
        post.interested_count = max(0, post.interested_count - 1)
        post.save()
        return JsonResponse({'success': True, 'interested': False, 'count': post.interested_count})
    else:
        CollabInterest.objects.create(post=post, user=user)
        post.interested_count += 1
        post.save()
        return JsonResponse({'success': True, 'interested': True, 'count': post.interested_count})

@csrf_exempt
@require_tier('free')
def collab_my_posts(request):
    """Get current user's collab posts"""
    user = request.fuzeobs_user
    
    posts = CollabPost.objects.filter(user=user)
    results = []
    for post in posts:
        interested_users = []
        for interest in CollabInterest.objects.select_related('user').filter(post=post):
            interested_users.append({
                'user_id': interest.user.id,
                'username': interest.user.username,
                'profile_picture': _get_profile_pic_url(interest.user),
                'created_at': interest.created_at.isoformat(),
            })
        
        results.append({
            'id': post.id,
            'title': post.title,
            'description': post.description,
            'category': post.category,
            'platforms': post.platforms,
            'tags': post.tags,
            'collab_size': post.collab_size,
            'availability': post.availability,
            'status': post.status,
            'interested_count': post.interested_count,
            'interested_users': interested_users,
            'created_at': post.created_at.isoformat(),
        })
    
    return JsonResponse({'success': True, 'posts': results})

@csrf_exempt
@require_tier('free')
def collab_send_message(request):
    """Send a message to a user from collab finder"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    user = request.fuzeobs_user
    data = json.loads(request.body)
    target_username = data.get('username', '').strip()
    content = data.get('message', '').strip()
    
    if not target_username or not content:
        return JsonResponse({'success': False, 'error': 'Username and message required'}, status=400)
    
    if len(content) > 500:
        return JsonResponse({'success': False, 'error': 'Message too long (max 500 chars)'}, status=400)
    
    from ACCOUNTS.validators import contains_profanity
    if contains_profanity(content):
        return JsonResponse({'success': False, 'error': 'Message contains inappropriate language'}, status=400)
    
    try:
        recipient = User.objects.get(username=target_username)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    
    if recipient.id == user.id:
        return JsonResponse({'success': False, 'error': 'Cannot message yourself'}, status=400)
    
    # Find or create conversation
    conversation = Conversation.objects.filter(
        participants=user
    ).filter(
        participants=recipient
    ).first()
    
    if not conversation:
        conversation = Conversation.objects.create()
        conversation.participants.add(user, recipient)
    
    # Create message
    message = Message.objects.create(
        sender=user,
        recipient=recipient,
        content=content,
        conversation=conversation
    )
    
    conversation.last_message = message
    conversation.save()
    
    return JsonResponse({'success': True, 'message_id': message.id})