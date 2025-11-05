from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
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
from .models import FuzeOBSProfile
from google.cloud import storage
import hmac
import hashlib
import time
from functools import wraps

# Website Imports
from django.shortcuts import render
from django.shortcuts import redirect
from .models import DownloadTracking
from django.db.models import Count, Sum, Avg, Q, Max
from django.utils import timezone
from datetime import timedelta
from .models import AIUsage, UserActivity, TierChange
from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from .models import DownloadTracking, FuzeOBSChat

User = get_user_model()

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
        'version': '0.9.4',
        'download_url': 'https://storage.googleapis.com/fuzeobs-public/fuzeobs-installer/FuzeOBS-Installer.exe',
        'changelog': 'FuzeOBS Analytics on Bomby + User Tracking',
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
    update_active_session(user, session_id, request.META.get('REMOTE_ADDR'))
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
        ip = request.META.get('REMOTE_ADDR', 'unknown')
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
            update_active_session(user, session_id, request.META.get('REMOTE_ADDR'))
            
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
def fuzeobs_verify(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'valid': False}, status=401)
    
    token = auth_header[7:]
    user = get_user_from_token(token)
    
    if not user:
        return JsonResponse({'valid': False}, status=401)
    
    # Try to get session_id from body, but don't fail if empty
    session_id = None
    try:
        if request.body:
            data = json.loads(request.body)
            session_id = data.get('session_id')
    except:
        pass
    
    # Only track if we have session_id
    if session_id:
        activate_fuzeobs_user(user)
        update_active_session(user, session_id, request.META.get('REMOTE_ADDR'))
    
    return JsonResponse({
        'valid': True,
        'email': user.email,
        'username': user.username,
        'tier': user.fuzeobs_tier,
        'token': token
    })

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
@require_tier('free')
def fuzeobs_ai_chat(request):
    """AI chat streaming endpoint with tier-based rate limiting and file upload"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    user = request.fuzeobs_user
    tier = user.fuzeobs_tier
    user_id = f'user_{user.id}'
    
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
            response['Access-Control-Allow-Origin'] = '*'
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
            response['Access-Control-Allow-Origin'] = '*'
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
        response['Access-Control-Allow-Origin'] = '*'
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
            response['Access-Control-Allow-Origin'] = '*'
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
            
            AIUsage.objects.create(
                user=user,
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
    response['Access-Control-Allow-Origin'] = '*'
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
    
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
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
    
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
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
    
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
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
    
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
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
    response['Access-Control-Allow-Origin'] = '*'
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
        data = json.loads(request.body)
        profile_id = data.get('id', profile_id)
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
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    return redirect('https://storage.googleapis.com/fuzeobs-public/fuzeobs-installer/FuzeOBS-Installer.exe')

@staff_member_required
def fuzeobs_download_mac(request):
    DownloadTracking.objects.create(
        platform='mac',
        version='0.9.4',
        user=request.user if request.user.is_authenticated else None,
        ip_address=request.META.get('REMOTE_ADDR'),
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
    free_ai = AIUsage.objects.filter(timestamp__gte=date_from, user__fuzeobs_tier='free').aggregate(
        count=Count('id'), cost=Sum('estimated_cost')
    )
    paid_ai = AIUsage.objects.filter(timestamp__gte=date_from).exclude(user__fuzeobs_tier='free').aggregate(
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
    cost_by_tier_raw = AIUsage.objects.filter(timestamp__gte=date_from).values('user__fuzeobs_tier').annotate(
        request_count=Count('id'), 
        total_cost=Sum('estimated_cost')
    )
    
    cost_by_tier = []
    for item in cost_by_tier_raw:
        tier = item['user__fuzeobs_tier'] or 'unknown'
        cost_by_tier.append({
            'tier_key': tier,
            'tier_display': tier.title(),
            'request_count': item['request_count'],
            'total_cost': round(float(item['total_cost'] or 0), 2)
        })
    
    # Top users by AI usage
    top_users = AIUsage.objects.filter(timestamp__gte=date_from).values(
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