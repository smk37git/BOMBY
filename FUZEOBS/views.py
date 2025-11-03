from django.http import StreamingHttpResponse, JsonResponse, FileResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
import anthropic
import os
import json
from datetime import date, timedelta
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
from django.conf import settings

User = get_user_model()

# ====== VERSION / UPDATES ======

@require_http_methods(["GET"])
def fuzeobs_check_update(request):
    """Return update info with GCS signed URL (bypasses Cloud Run 32MB limit)"""
    try:
        client = storage.Client()
        bucket = client.bucket('bomby-user-uploads')
        blob = bucket.blob('fuzeobs-installer/FuzeOBS-Installer.exe')
        
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="GET"
        )
        
        return JsonResponse({
            'version': '0.9.3', # Update the version
            'download_url': signed_url,
            'changelog': 'Bug fixes and performance improvements', # Update the description
            'mandatory': False
        })
    except Exception as e:
        print(f"Update check error: {e}")
        return JsonResponse({'error': 'Update check failed'}, status=500)


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
    user.save()
    
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
            # Success - clear attempts and create secure token
            cache.delete(attempts_key)
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
    """Verify token is still valid and return user info"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'valid': False}, status=401)
    
    token = auth_header[7:]
    user = get_user_from_token(token)
    
    if not user:
        return JsonResponse({'valid': False}, status=401)
    
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
    
    # Check content type to determine how to parse
    if request.content_type and 'multipart/form-data' in request.content_type:
        # FormData with potential files
        files = request.FILES.getlist('files')[:5]  # Max 5 files
        message = request.POST.get('message', '').strip()
        style = request.POST.get('style', 'normal')
    else:
        # JSON only (no files)
        files = []
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        style = data.get('style', 'normal')
    
    if not message and not files:
        return JsonResponse({'error': 'Empty message'}, status=400)
    
    # Topic validation (only on text)
    if message:
        off_topic_keywords = [
            'homework', 'essay', 'assignment', 'math problem', 'solve for', 
            'write code', 'python script', 'javascript function', 'sql query',
            'history of', 'who was', 'biography', 'recipe', 'medical advice'
        ]
        
        if any(keyword in message.lower() for keyword in off_topic_keywords):
            def off_topic_message():
                message_data = {'text': '**Off-Topic Query Detected**\n\nThis AI assistant is specifically designed for OBS Studio and streaming questions only. Please ask about:\n\n• OBS settings and configuration\n• Stream quality and encoding\n• Hardware compatibility\n• Streaming platforms (Twitch, YouTube, etc.)\n• Audio/video capture issues\n• Scene setup and sources\n\nFor other topics, please use a general-purpose AI assistant.'}
                yield "data: " + json.dumps(message_data) + "\n\n"
                yield "data: [DONE]\n\n"
            
            response = StreamingHttpResponse(off_topic_message(), content_type='text/event-stream; charset=utf-8')
            response['Cache-Control'] = 'no-cache'
            response['Access-Control-Allow-Origin'] = '*'
            return response
    
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    def generate():
        try:
            # Build content array
            content = []
            
            # Add files first
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
            
            # Add text message
            if message:
                content.append({'type': 'text', 'text': message})
            
            # Use content array if files, otherwise just message string
            messages_content = content if files else message
            
            # Style instructions
            style_instructions = {
                'normal': '- Start with a direct answer\n- Provide exact settings when applicable\n- Explain WHY a setting matters\n- Offer alternatives if relevant\n- Keep responses focused and scannable',
                'concise': '- Be extremely brief and to-the-point\n- Use bullet points for lists\n- Only essential information\n- No explanations unless critical\n- Maximum efficiency',
                'explanatory': '- Provide detailed step-by-step explanations\n- Explain the reasoning behind each recommendation\n- Include background context\n- Anticipate follow-up questions\n- Educational and thorough',
                'formal': '- Use professional technical language\n- Structured and organized format\n- Precise terminology\n- Comprehensive coverage\n- Business-appropriate tone',
                'learning': '- Break down concepts for beginners\n- Use analogies and examples\n- Explain technical terms\n- Build understanding progressively\n- Patient and encouraging tone'
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
            yield "data: [DONE]\n\n"
        except Exception as e:
            print(f"AI Error: {e}")
            yield f"data: {json.dumps({'text': 'Error processing request.'})}\n\n"
            yield "data: [DONE]\n\n"
    
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
            )[:50]
            
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