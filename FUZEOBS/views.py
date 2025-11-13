from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
import anthropic
import os
import json
from datetime import date
from django.core.cache import cache
import re
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from .models import FuzeOBSProfile, DownloadTracking, AIUsage, UserActivity, TierChange, ActiveSession, PlatformConnection, MediaLibrary, WidgetConfig, WidgetEvent
from google.cloud import storage
import hmac
import hashlib
import time
from functools import wraps
from django.contrib.auth.decorators import login_required
from .widget_generator import generate_widget_html, generate_alert_box_html, generate_chat_box_html, upload_to_gcs
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

# Website Imports
from django.shortcuts import render
from django.shortcuts import redirect
from django.db.models import Count, Sum, Avg, Q, Max
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
import secrets
from django.contrib.auth import login
from .models import WidgetConfig

User = get_user_model()
# ====== HELPER FUNCTIONS =======

def get_client_ip(request):
    """Get real client IP, handling proxies correctly"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')

# ====== SEND ANALYTIC DATA =======

def activate_fuzeobs_user(user):
    if not user.fuzeobs_activated:
        user.fuzeobs_activated = True
        user.fuzeobs_first_login = timezone.now()
    user.fuzeobs_last_active = timezone.now()
    user.fuzeobs_total_sessions += 1
    user.save()

def update_active_session(user, session_id, ip_address=None):
    from .models import ActiveSession
    ActiveSession.objects.update_or_create(
        session_id=session_id,
        defaults={'user': user, 'ip_address': ip_address, 'last_ping': timezone.now(), 'is_anonymous': False}
    )

def cleanup_old_sessions():
    from .models import ActiveSession
    threshold = timezone.now() - timedelta(minutes=5)
    ActiveSession.objects.filter(last_ping__lt=threshold).delete()

# ====== VERSION / UPDATES ======

@require_http_methods(["GET"])
def fuzeobs_check_update(request):
    return JsonResponse({
        'version': '0.9.9',
        'download_url': 'https://storage.googleapis.com/fuzeobs-public/fuzeobs-installer/FuzeOBS-Installer.exe',
        'changelog': 'Responsiveness Update. Shoud look good on 1440p, 1080p, 1200p',
        'mandatory': False
    })

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
    """Secure token verification"""
    verification = auth_manager.verify_token(token)
    if not verification['valid']:
        return None
    try:
        user = User.objects.get(id=verification['user_id'])
        if user.fuzeobs_tier != verification['tier']:
            return None
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
                'tier': user.fuzeobs_tier
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
        return JsonResponse({
            'valid': True,
            'authenticated': True,
            'tier': user.fuzeobs_tier,
            'email': user.email,
            'username': user.username,
            'reachable': True
        })
    
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
        model = "claude-sonnet-4-20250514"
        
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
        model = "claude-3-5-haiku-20241022"
    
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
                'learning': '- Break down for beginners\n- Use analogies'
            }
            
            style_prompt = style_instructions.get(style, style_instructions['normal'])
            
            with client.messages.stream(
                model=model,
                max_tokens=4000,
                system=f"""You are the FuzeOBS AI Assistant - an expert in OBS Studio, streaming, and broadcast technology.

Core Guidelines:
- ONLY answer questions about OBS, streaming, encoding, hardware for streaming, and related topics
- Provide specific settings, numbers, and exact configuration steps
- Consider the user's hardware when giving recommendations
- Be direct and technical - users want actionable solutions
- If hardware specs are provided, optimize recommendations for that setup (If you don't know it, ask the user to scan their hardware in the Detection Tab)
- When analyzing images or files, be specific about what you see and provide detailed guidance

FuzeOBS Tiers:
- There are 3 Tiers of FuzeOBS (Free/Pro/Lifetime)
- The Pro/Lifetime tiers will include unlimted AI (on a smarter model) messages, Advanced Output OBS settings, Benchmarking, and more detailed scene collections
- The Free tier will have 5 AI messages a day (on a lower-performing model), Simple Output OBS Settings, No Benchmarking, Simple Scene collections
- If a Free tier user is requesting Pro/Lifetime features or assistance, recommend the Pro tier LIGHTLY as means of assistance

FuzeOBS -- How it Works:
- There are 10 FuzeOBS tabs
- Tab 01 -- System Detection (Will detect a users hardware, monitors, and provide graded rating for: streaming, recording, gaming)
- Tab 02 -- Configuration (Configure primary settings [Use Case, Platform, Quality Preference, Output mode (Simple = Free / Advanced = Pro/Lifetime), Scene Template (Simple Template = Free / All Templates = Pro/Lifetime)]. It will also provide a configuration summary and allow the user to generate a config file with the settings pre-applied.
- Tab 03 -- Optimization (User setups websocket connection to OBS by creating password and entering it into FuzeOBS. Then it will once again read the configuration files and the user can click a button to "Apply to OBS")
- Tab 04 -- Audio (User learns how to setup audio (default configuration = default audio devices), recommends filters for audio devices)
- Tab 05 -- Scene Setup (User can learn EVERYTHING they need to know about setting up OBS scenes. How to add sources, move sources, manipulate sources, and how to organzie sources)
- Tab 06 -- Tools (User learns how to connect StreamLabs OBS dashboard tools (Alert Box, Chat Box, etc...) to their OBS. Learns about other widgets and how to install and use cloudbot with all its features. Also learns how browser sources work)
- Tab 07 -- Plugins (User learns how OBS plugins work, how to install them, and provides a set list of popular plugins)
- Tab 08 -- Documentation (Lots of topics about OBS, streaming, troubleshooting. Essentially a mini-wiki covering the entire spectrum of OBS and streaming knowledge)
- Tab 09 -- Benchmark (Pro/Lifetime users can benchmark their OBS after setting up their streams. It will analyze all their stats from component usage, to network stats, to quality. It will provide a graded report with stats and even allow AI to analyze it to understand results)
- Tab 10 -- Fuze-AI (AI model that will answer any streaming related or OBS or FuzeOBS question!)

FuzeOBS -- Additional Functions:
- Profiles Button -- Allows users to save different configuration setups. Great to easily switch out settings and configurations.
- Import/Export buttons -- Allows users to easily import or export other configuration files that will apply to OBS via Tab 03.
- Test Websocket button on the sidebar, is the button to click to test the websocket connection on Tab 03 - Optimization.
- Launch OBS button -- Launches OBS easily from FuzeOBS

Topics You Handle:
✓ OBS settings and configuration
✓ Encoding (NVENC, x264, QuickSync, etc.)
✓ Bitrate, resolution, and quality settings
✓ Stream performance and optimization
✓ Hardware compatibility and recommendations
✓ Scene setup, sources, and filters
✓ Audio configuration and mixing
✓ Platform-specific settings (Twitch, YouTube, etc.)
✓ Troubleshooting dropped frames, lag, quality issues, network issues
✓ Analyzing screenshots of OBS interfaces
✓ Reviewing scene collection and profile JSON files

Topics You Redirect:
✗ General programming or coding tasks
✗ Non-streaming related hardware/software
✗ Unrelated technical support (aside from WiFi/Ethernet troubleshooting like resetting a router)
✗ General knowledge questions

A potential problem for webcams not appearing even though they are activated in OBS:
- User has incorrect resolution set for webcam. If a webcam can only support 720p max, but has 1080p set it will NOT show.
- However, if a webcam has a max of 1080p, but it is set to 720p, it will show at a lower resolution than the max.

Response Style:
{style_prompt}""",
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
            
            if model == "claude-sonnet-4-20250514":
                cost = (input_tokens / 1_000_000 * 3) + (output_tokens / 1_000_000 * 15)
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

def activate_fuzeobs_user(user):
    """Mark user as FuzeOBS user on first app login"""
    from .models import ActiveSession
    if not user.fuzeobs_activated:
        user.fuzeobs_activated = True
        user.fuzeobs_first_login = timezone.now()
    user.fuzeobs_last_active = timezone.now()
    user.fuzeobs_total_sessions += 1
    user.save()

def update_active_session(user, session_id, ip_address=None):
    """Update or create active session"""
    from .models import ActiveSession
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
    from .models import ActiveSession
    threshold = timezone.now() - timedelta(minutes=5)
    ActiveSession.objects.filter(last_ping__lt=threshold).delete()

# ====== WEBSITE VIEWS =======
def fuzeobs_view(request):
    return render(request, 'FUZEOBS/fuzeobs.html')

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

@staff_member_required
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
    
    context = {
        'view_user': view_user,
        'ai_usage': ai_usage,
        'ai_stats': ai_stats,
        'success_rate': success_rate,
        'user_chats': user_chats,
        'activity': activity,
        'days': days
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
        'cost_by_tier': cost_by_tier,
        'top_users': top_users,
        'feature_usage': feature_usage,
        'feature_usage_json': json.dumps(feature_usage),
        'recent_tier_changes': recent_tier_changes,
        'template_usage': template_usage,
        'dau_data': dau_data,
        'dau_json': json.dumps(dau_data),
    }
    
    return render(request, 'FUZEOBS/fuzeobs_analytics.html', context)

@staff_member_required
def fuzeobs_all_users_view(request):
    # All FuzeOBS users with activity stats
    all_users = User.objects.filter(fuzeobs_activated=True).annotate(
        last_activity=Max('useractivity__timestamp'),
        total_ai_requests=Count('aiusage', distinct=True),
        total_ai_cost=Sum('aiusage__estimated_cost')
    ).order_by('-total_ai_requests')
    
    context = {'all_users': all_users}
    return render(request, 'FUZEOBS/fuzeobs_all_users.html', context)

# ===== WIDGETS SYSTEM =====
import uuid

# Widget HTML generators
def generate_widget_html(widget):
    """Generate HTML for widget based on type"""
    widget_type = widget.widget_type
    config = widget.config
    widget_id = widget.id
    user_id = widget.user.id
    
    base_template = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{widget.name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            background: transparent; 
            font-family: 'Arial', sans-serif;
            overflow: hidden;
        }}
        .widget-container {{ 
            width: 100vw; 
            height: 100vh; 
            position: relative;
        }}
    </style>
</head>
<body>
    <div class="widget-container" id="widget-{widget_id}">
        {get_widget_content(widget_type, config, widget_id)}
    </div>
    <script>
        const WIDGET_ID = {widget_id};
        const USER_ID = {user_id};
        const WS_URL = 'wss://bomby.us/ws/fuzeobs-alerts/' + USER_ID + '/';
        
        {get_widget_script(widget_type, config)}
    </script>
</body>
</html>"""
    
    return base_template

def get_widget_content(widget_type, config, widget_id):
    """Get HTML content for specific widget type"""
    if widget_type == 'alert_box':
        return """
        <div class="alert-container" style="display: none; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center;">
            <div class="alert-image"></div>
            <div class="alert-text" style="font-size: 32px; font-weight: bold; color: white; margin-top: 20px;"></div>
        </div>
        """
    elif widget_type == 'chat_box':
        return """
        <div class="chat-container" style="position: absolute; bottom: 0; left: 0; width: 400px; height: 600px; background: rgba(0,0,0,0.7); overflow-y: auto; padding: 10px;">
            <div class="chat-messages"></div>
        </div>
        """
    elif widget_type == 'event_list':
        return """
        <div class="event-list" style="position: absolute; top: 0; right: 0; width: 300px; background: rgba(0,0,0,0.8); padding: 15px;">
            <h3 style="color: white; margin-bottom: 10px;">Recent Events</h3>
            <div class="events"></div>
        </div>
        """
    elif widget_type == 'goal_bar':
        return """
        <div class="goal-container" style="position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); width: 600px; background: rgba(0,0,0,0.8); padding: 20px; border-radius: 10px;">
            <div class="goal-title" style="color: white; font-size: 24px; margin-bottom: 10px;">Goal Title</div>
            <div class="progress-bar" style="width: 100%; height: 30px; background: #333; border-radius: 5px; overflow: hidden;">
                <div class="progress-fill" style="width: 0%; height: 100%; background: linear-gradient(90deg, #00ff00, #00cc00); transition: width 0.3s;"></div>
            </div>
            <div class="goal-text" style="color: white; margin-top: 10px; text-align: center;">$0 / $1000</div>
        </div>
        """
    return "<div>Widget content</div>"

def get_widget_script(widget_type, config):
    """Get JavaScript for specific widget type"""
    base_script = """
        const eventConfigs = {};
        const defaultConfig = {
            enabled: true,
            alert_animation: 'fade',
            font_size: 32,
            text_color: '#FFFFFF',
            message_template: '{name} just followed!',
            duration: 5,
            sound_volume: 50
        };
        
        // Load event configs
        fetch('/fuzeobs/widgets/events/config/' + USER_ID)
            .then(r => r.json())
            .then(data => {
                Object.assign(eventConfigs, data.configs);
                console.log('Loaded configs:', eventConfigs);
            })
            .catch(err => console.log('Using defaults:', err));
        
        let ws;
        function connectWebSocket() {
            ws = new WebSocket(WS_URL);
            ws.onopen = () => console.log('Widget connected');
            ws.onmessage = (event) => handleEvent(JSON.parse(event.data));
            ws.onerror = (error) => console.error('WebSocket error:', error);
            ws.onclose = () => setTimeout(connectWebSocket, 3000);
        }
        
        function handleEvent(data) {
            console.log('Event received:', data);
            const configKey = data.platform + '-' + data.event_type;
            const config = eventConfigs[configKey] || defaultConfig;
            const eventData = data.event_data || {};
            
            if (!config.enabled) return;
            
            let message = config.message_template || defaultConfig.message_template;
            message = message.replace(/{name}/g, eventData.username || 'Someone');
            message = message.replace(/{amount}/g, eventData.amount || '');
            
            showAlert(message, config, eventData);
        }
    """
    
    if widget_type == 'alert_box':
        return base_script + """
        function showAlert(message, config, eventData) {
            const container = document.querySelector('.alert-container');
            const imgDiv = container.querySelector('.alert-image');
            const text = container.querySelector('.alert-text');
            
            // Image
            if (config.image_url) {
                imgDiv.innerHTML = '<img src="' + config.image_url + '" style="max-width: 300px; max-height: 300px;">';
            } else {
                imgDiv.innerHTML = '';
            }
            
            // Text
            text.textContent = message;
            text.style.fontSize = (config.font_size || 32) + 'px';
            text.style.color = config.text_color || '#FFFFFF';
            
            // Sound
            if (config.sound_url) {
                const audio = new Audio(config.sound_url);
                audio.volume = (config.sound_volume || 50) / 100;
                audio.play().catch(err => console.log('Audio failed:', err));
            }
            
            // Animation
            container.style.display = 'block';
            const animation = config.alert_animation || 'fade';
            container.style.animation = animation + 'In 0.5s ease-out forwards';
            
            // Duration
            const duration = (config.duration || 5) * 1000;
            setTimeout(() => {
                container.style.animation = 'fadeOut 0.5s';
                setTimeout(() => container.style.display = 'none', 500);
            }, duration);
        }
        
        connectWebSocket();
        """
    elif widget_type == 'chat_box':
        return base_script + """
        function addChatMessage(username, message) {
            const messages = document.querySelector('.chat-messages');
            const msg = document.createElement('div');
            msg.style.cssText = 'color: white; margin-bottom: 10px; padding: 5px; background: rgba(255,255,255,0.1); border-radius: 5px;';
            msg.innerHTML = '<strong>' + username + ':</strong> ' + message;
            messages.appendChild(msg);
            messages.scrollTop = messages.scrollHeight;
        }
        
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.event_type === 'chat_message') {
                addChatMessage(data.event_data.username, data.event_data.message);
            }
        };
        
        connectWebSocket();
        """
    
    return base_script + "connectWebSocket();"


@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuzeobs_get_widgets(request):
    """Get all widgets for authenticated user"""
    user = request.fuzeobs_user
    widgets = WidgetConfig.objects.filter(user=user).order_by('-updated_at')
    
    return JsonResponse({
        'widgets': [{
            'id': w.id,
            'type': w.widget_type,
            'name': w.name,
            'config': w.config,
            'url': w.gcs_url or f'https://storage.googleapis.com/bomby-user-uploads/fuzeobs-widgets/{user.id}/{w.id}.html',
            'created_at': w.created_at.isoformat(),
            'updated_at': w.updated_at.isoformat()
        } for w in widgets]
    })

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_save_widget(request):
    user = request.fuzeobs_user
    try:
        data = json.loads(request.body)
        widget_id = data.get('widget_id')
        
        if widget_id:
            widget = WidgetConfig.objects.get(id=widget_id, user=user)
            widget.name = data.get('name', widget.name)
            widget.config = data.get('config', widget.config)
        else:
            widget = WidgetConfig.objects.create(
                user=user,
                widget_type=data['widget_type'],
                name=data['name'],
                config=data.get('config', {})
            )
        
        widget_html = generate_widget_html(widget)
        
        client = storage.Client()
        bucket = client.bucket('fuzeobs-public')
        blob = bucket.blob(f'widgets/{user.id}/{widget.id}.html')
        blob.upload_from_string(widget_html, content_type='text/html')
        blob.make_public()
        
        # Use bomby.us URL
        widget.gcs_url = f'https://bomby.us/fuzeobs/widgets/{user.id}/{widget.id}.html'
        widget.save()
        
        UserActivity.objects.create(
            user=user,
            activity_type='widget_create' if not widget_id else 'widget_update',
            source='app',
            details={'widget_type': widget.widget_type, 'widget_id': widget.id}
        )
        
        return JsonResponse({
            'success': True,
            'id': widget.id,
            'url': widget.gcs_url,
            'widget': {
                'id': widget.id,
                'type': widget.widget_type,
                'name': widget.name,
                'config': widget.config,
                'url': widget.gcs_url
            }
        })
    except WidgetConfig.DoesNotExist:
        return JsonResponse({'error': 'Widget not found'}, status=404)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
@require_http_methods(["DELETE"])
@require_tier('free')
def fuzeobs_delete_widget(request, widget_id):
    """Delete widget"""
    user = request.fuzeobs_user
    
    try:
        widget = WidgetConfig.objects.get(id=widget_id, user=user)
        
        # Delete from GCS
        try:
            client = storage.Client()
            bucket = client.bucket('bomby-user-uploads')
            blob_path = f'fuzeobs-widgets/{user.id}/{widget.id}.html'
            blob = bucket.blob(blob_path)
            blob.delete()
        except:
            pass  # Ignore GCS errors
        
        widget.delete()
        
        return JsonResponse({'success': True})
        
    except WidgetConfig.DoesNotExist:
        return JsonResponse({'error': 'Widget not found'}, status=404)

# ===== PLATFORM CONNECTIONS =====

PLATFORM_OAUTH_CONFIG = {
    'twitch': {
        'auth_url': 'https://id.twitch.tv/oauth2/authorize',
        'token_url': 'https://id.twitch.tv/oauth2/token',
        'client_id': os.environ.get('TWITCH_CLIENT_ID', ''),
        'client_secret': os.environ.get('TWITCH_CLIENT_SECRET', ''),
        'scopes': ['channel:read:subscriptions', 'bits:read', 'channel:read:redemptions']
    },
    'youtube': {
        'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token_url': 'https://oauth2.googleapis.com/token',
        'client_id': os.environ.get('YOUTUBE_CLIENT_ID', ''),
        'client_secret': os.environ.get('YOUTUBE_CLIENT_SECRET', ''),
        'scopes': ['https://www.googleapis.com/auth/youtube.readonly']
    },
    'kick': {
        'auth_url': 'https://kick.com/oauth2/authorize',
        'token_url': 'https://kick.com/oauth2/token',
        'client_id': os.environ.get('KICK_CLIENT_ID', ''),
        'client_secret': os.environ.get('KICK_CLIENT_SECRET', ''),
        'scopes': ['channel:subscriptions', 'channel:events']
    }
}

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
    """Initiate OAuth flow for platform"""
    user = request.fuzeobs_user
    
    try:
        data = json.loads(request.body)
        platform = data['platform']
        
        if platform not in PLATFORM_OAUTH_CONFIG:
            return JsonResponse({'error': 'Invalid platform'}, status=400)
        
        config = PLATFORM_OAUTH_CONFIG[platform]
        
        # Generate state token for CSRF protection
        state = secrets.token_urlsafe(32)
        cache.set(f'oauth_state_{state}', {'user_id': user.id, 'platform': platform}, timeout=600)
        
        # Build OAuth URL
        redirect_uri = f'https://bomby.us/fuzeobs/callback/{platform}'
        scopes = ' '.join(config['scopes'])
        
        auth_url = f"{config['auth_url']}?client_id={config['client_id']}&redirect_uri={redirect_uri}&response_type=code&scope={scopes}&state={state}"
        
        return JsonResponse({
            'success': True,
            'auth_url': auth_url,
            'state': state
        })
        
    except Exception as e:
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
        
        PlatformConnection.objects.filter(user=user, platform=platform).delete()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def fuzeobs_platform_callback(request, platform):
    """OAuth callback handler"""
    code = request.GET.get('code')
    state = request.GET.get('state')
    
    if not code or not state:
        return HttpResponse('Invalid callback', status=400)
    
    # Verify state
    state_data = cache.get(f'oauth_state_{state}')
    if not state_data or state_data['platform'] != platform:
        return HttpResponse('Invalid state', status=400)
    
    user = User.objects.get(id=state_data['user_id'])
    config = PLATFORM_OAUTH_CONFIG[platform]
    
    # Exchange code for token
    import requests
    redirect_uri = f'https://bomby.us/fuzeobs/callback/{platform}'
    
    token_response = requests.post(config['token_url'], 
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data={
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        })
    
    if token_response.status_code != 200:
        return HttpResponse('Token exchange failed', status=400)
    
    token_data = token_response.json()
    access_token = token_data['access_token']
    refresh_token = token_data.get('refresh_token', '')
    expires_in = token_data.get('expires_in', 3600)
    
    # Get user info from platform
    username = get_platform_username(platform, access_token)
    
    # Save connection
    PlatformConnection.objects.update_or_create(
        user=user,
        platform=platform,
        defaults={
            'platform_username': username,
            'access_token': access_token,
            'refresh_token': refresh_token,
            'expires_at': timezone.now() + timedelta(seconds=expires_in)
        }
    )
    
    # Clean up state
    cache.delete(f'oauth_state_{state}')
    
    return render(request, 'FUZEOBS/platform_connected.html', {'platform': platform})

def get_platform_username(platform, access_token):
    """Get username from platform API"""
    import requests
    
    if platform == 'twitch':
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Client-Id': PLATFORM_OAUTH_CONFIG['twitch']['client_id']
        }
        response = requests.get('https://api.twitch.tv/helix/users', headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data['data'][0]['login']
    
    elif platform == 'youtube':
        response = requests.get(
            'https://www.googleapis.com/youtube/v3/channels',
            params={'part': 'snippet', 'mine': 'true'},
            headers={'Authorization': f'Bearer {access_token}'}
        )
        if response.status_code == 200:
            data = response.json()
            return data['items'][0]['snippet']['title']
    
    elif platform == 'kick':
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get('https://kick.com/api/v1/user', headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data['username']
    
    return 'Unknown'


# ===== MEDIA LIBRARY =====
@csrf_exempt
@xframe_options_exempt
def fuzeobs_serve_widget(request, user_id, widget_id):
    """Serve widget from GCS through our domain"""
    try:
        client = storage.Client()
        bucket = client.bucket('fuzeobs-public')
        blob = bucket.blob(f'widgets/{user_id}/{widget_id}.html')
        
        if not blob.exists():
            return HttpResponse('Not found', status=404)
        
        content = blob.download_as_bytes()
        response = HttpResponse(content, content_type='text/html')
        response['Cache-Control'] = 'no-cache'
        response['Access-Control-Allow-Origin'] = '*'
        # Remove X-Frame-Options to allow OBS embedding
        if 'X-Frame-Options' in response:
            del response['X-Frame-Options']
        return response
    except Exception as e:
        return HttpResponse('Error', status=500)

@csrf_exempt
def fuzeobs_serve_media(request, user_id, filename):
    """Serve media from GCS through our domain"""
    try:
        client = storage.Client()
        bucket = client.bucket('fuzeobs-public')
        blob = bucket.blob(f'media/{user_id}/{filename}')
        
        if not blob.exists():
            return HttpResponse('Not found', status=404)
        
        content = blob.download_as_bytes()
        response = HttpResponse(content, content_type=blob.content_type or 'application/octet-stream')
        response['Cache-Control'] = 'public, max-age=86400'
        return response
    except:
        return HttpResponse('Error', status=500)

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
    
    return JsonResponse({
        'media': [{
            'id': m.id,
            'name': m.name,
            'type': m.media_type,
            'url': m.file_url,
            'size': m.file_size,
            'uploaded_at': m.uploaded_at.isoformat()
        } for m in media],
        'total_size': total_size,
        'max_size': max_size
    })

from datetime import timedelta
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
    blob.upload_from_file(file, content_type=file.content_type)
    blob.make_public()
    
    # Use bomby.us URL
    file_url = f'https://bomby.us/fuzeobs/media/{user.id}/{filename}'
    
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
    """Save event configuration"""
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
        
        # Regenerate widget HTML with new config
        widget_html = generate_widget_html(widget)
        client = storage.Client()
        bucket = client.bucket('fuzeobs-public')
        blob_path = f'widgets/{user.id}/{widget.id}.html'
        blob = bucket.blob(blob_path)
        blob.upload_from_string(widget_html, content_type='text/html')
        
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
@require_http_methods(["GET"])
def fuzeobs_get_widget_event_configs(request, user_id):
    """Get all event configurations for user's widgets"""
    try:
        widgets = WidgetConfig.objects.filter(user_id=user_id)
        configs = {}
        
        for widget in widgets:
            events = WidgetEvent.objects.filter(widget=widget, enabled=True)
            for event in events:
                key = f"{event.platform}-{event.event_type}"
                configs[key] = event.config
                configs[key]['enabled'] = True
        
        return JsonResponse({'configs': configs})
    except Exception as e:
        return JsonResponse({'configs': {}})

# ==== ALERT TESTING ====
@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuzeobs_test_alert(request):
    """Send test alert via WebSocket"""
    user = request.fuzeobs_user
    
    try:
        data = json.loads(request.body)
        event_type = data.get('event_type', 'follow')
        platform = data.get('platform', 'twitch')
        
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'alerts_{user.id}',
            {
                'type': 'alert_event',
                'data': {
                    'event_type': event_type,
                    'platform': platform,
                    'event_data': {'username': 'Test_User',
                    'amount': '100' if event_type in ['bits', 'superchat'] else None,
                    }
                }
            }
        )
        
        return JsonResponse({'success': True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=400)