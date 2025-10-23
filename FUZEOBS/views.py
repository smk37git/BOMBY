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

User = get_user_model()

def validate_username(username):
    """Validate username matches Django rules"""
    if not username:
        raise ValidationError("Username is required")
    
    if len(username) > 20:
        raise ValidationError("Username must be 20 characters or fewer")
    
    # Django's default username validator pattern
    if not re.match(r'^[\w.@+-]+$', username):
        raise ValidationError("Username can only contain letters, digits and @/./+/-/_ characters")
    
    # Import and use the same profanity checker from validators.py
    from ACCOUNTS.validators import contains_profanity
    if contains_profanity(username):
        raise ValidationError("Username contains inappropriate language")
    
    return username

@csrf_exempt
def fuzeobs_signup(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    data = json.loads(request.body)
    email = data.get('email')
    username = data.get('username')
    password = data.get('password')
    
    # Validate username
    try:
        validate_username(username)
    except ValidationError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
    
    # Validate password length (Django default minimum is 8)
    if len(password) < 8:
        return JsonResponse({'success': False, 'error': 'Password must be at least 8 characters'}, status=400)
    
    if User.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'Email already registered'}, status=400)
    
    if User.objects.filter(username=username).exists():
        return JsonResponse({'success': False, 'error': 'Username already taken'}, status=400)
    
    user = User.objects.create_user(username=username, email=email, password=password)
    user.fuzeobs_tier = 'free'
    user.save()
    
    token = f"{user.id}:{user.email}"
    return JsonResponse({
        'success': True,
        'token': token,
        'tier': 'free',
        'email': user.email,
        'username': user.username
    })

@csrf_exempt
def fuzeobs_login(request):
    try:
        data = json.loads(request.body)
        email_or_username = data.get('email', '').strip()
        password = data.get('password', '')
        remember_me = data.get('remember_me', False)
        
        if not email_or_username or not password:
            return JsonResponse({
                'success': False,
                'error': 'Email/username and password required'
            })
        
        # Try to authenticate with username first, then email
        user = None
        if '@' in email_or_username:
            # Looks like email
            try:
                user_obj = User.objects.get(email=email_or_username)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        else:
            # Try as username
            user = authenticate(username=email_or_username, password=password)
        
        # If still no user, try as email even without @ (fallback)
        if not user:
            try:
                user_obj = User.objects.get(email=email_or_username)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        
        if user:
            # Use same token format as signup: user_id:email
            token = f"{user.id}:{user.email}"
            
            return JsonResponse({
                'success': True,
                'token': token,
                'email': user.email,
                'username': user.username,
                'tier': user.fuzeobs_tier
            })
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid credentials'
            })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Login failed'
        }, status=500)

@csrf_exempt
def fuzeobs_verify(request):
    """Verify token and return user info"""
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

def fuzeobs_ai_chat(request):
    """AI chat streaming endpoint with rate limiting and topic validation"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    token = auth_header[7:]
    user = get_user_from_token(token)
    
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    # Rate limiting - 10 requests per minute per user
    rate_limit_key = f'fuzeobs_ratelimit_{user.id}'
    request_count = cache.get(rate_limit_key, 0)
    
    if request_count >= 10:
        def rate_limit_message():
            message_data = {'text': '**Rate Limit Exceeded**\n\nPlease wait a moment before sending another message. Maximum 10 messages per minute.'}
            yield "data: " + json.dumps(message_data) + "\n\n"
            yield "data: [DONE]\n\n"
        
        response = StreamingHttpResponse(rate_limit_message(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'
        response['Access-Control-Allow-Origin'] = '*'
        return response
    
    # Increment rate limit counter
    cache.set(rate_limit_key, request_count + 1, 60)  # 60 second window
    
    # Reset monthly usage if new month
    if not user.fuzeobs_usage_reset_date or user.fuzeobs_usage_reset_date.month != date.today().month:
        user.fuzeobs_ai_usage_monthly = 0
        user.fuzeobs_usage_reset_date = date.today()
        user.save()
    
    # Check free tier limit
    if user.fuzeobs_tier == 'free' and user.fuzeobs_ai_usage_monthly >= 2:
        def limit_message():
            message_data = {'text': '**Free Tier Limit Reached**\n\nYou have used your 2 free AI queries this month. Upgrade to Pro for unlimited access to the AI assistant.'}
            yield "data: " + json.dumps(message_data) + "\n\n"
            yield "data: [DONE]\n\n"
        
        response = StreamingHttpResponse(limit_message(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'
        response['Access-Control-Allow-Origin'] = '*'
        return response
    
    data = json.loads(request.body)
    message = data.get('message', '').strip()
    
    if not message:
        return JsonResponse({'error': 'Empty message'}, status=400)
    
    # Topic validation - check for non-streaming keywords
    off_topic_keywords = [
        'homework', 'essay', 'assignment', 'math problem', 'solve for', 
        'write code', 'python script', 'javascript function', 'sql query',
        'history of', 'who was', 'biography', 'recipe', 'medical advice'
    ]
    
    message_lower = message.lower()
    if any(keyword in message_lower for keyword in off_topic_keywords):
        def off_topic_response():
            response_text = "**Topic Not Supported**\n\nThis assistant is specifically designed for OBS streaming setup and troubleshooting. Please ask questions related to:\n\n- OBS configuration and settings\n- Stream quality and performance\n- Hardware encoding setup\n- Scene and source management\n- Audio configuration\n- Streaming troubleshooting\n\nFor general topics or coding assistance, please use a different AI assistant."
            yield "data: " + json.dumps({'text': response_text}) + "\n\n"
            yield "data: [DONE]\n\n"
        
        response = StreamingHttpResponse(off_topic_response(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'
        response['Access-Control-Allow-Origin'] = '*'
        return response
    
    # Get conversation history
    history = data.get('history', [])
    
    # Build message array for Claude
    messages = []
    for msg in history:
        messages.append({
            'role': msg['role'],
            'content': msg['content']
        })
    
    messages.append({
        'role': 'user',
        'content': message
    })
    
    def generate():
        try:
            client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
            
            system_prompt = """You are Fuze-AI, an expert OBS streaming assistant integrated into FuzeOBS - an automated OBS configuration tool. Your role is to help users with OBS setup, streaming configuration, performance optimization, and troubleshooting.

Your expertise includes:
- OBS settings and configuration (encoding, bitrate, resolution, FPS)
- Hardware encoder setup (NVENC, AMD AMF, QuickSync)
- Stream quality optimization for different platforms (Twitch, YouTube, Facebook)
- Performance tuning and system resource management
- Scene composition and source management
- Audio configuration and mixing
- Troubleshooting common streaming issues

Guidelines:
- Provide clear, actionable advice specific to OBS and streaming
- When discussing settings, explain the impact on stream quality and performance
- Consider hardware limitations when making recommendations
- Be concise but thorough - users want practical solutions
- If asked about non-streaming topics, politely redirect to your specialization
- Use markdown formatting for readability

Respond helpfully and professionally to assist users with their OBS streaming needs."""
            
            with client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=2048,
                temperature=0.7,
                system=system_prompt,
                messages=messages
            ) as stream:
                for text in stream.text_stream:
                    yield "data: " + json.dumps({'text': text}) + "\n\n"
                
                yield "data: [DONE]\n\n"
            
            # Increment usage counter
            user.fuzeobs_ai_usage_monthly += 1
            user.save()
            
        except Exception as e:
            error_data = {'text': f'**Error**: {str(e)}'}
            yield "data: " + json.dumps(error_data) + "\n\n"
            yield "data: [DONE]\n\n"
    
    response = StreamingHttpResponse(generate(), content_type='text/event-stream; charset=utf-8')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    response['Access-Control-Allow-Origin'] = '*'
    
    return response

@csrf_exempt
def get_user_tier(request):
    """Get user tier info"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'tier': 'free'})
    
    try:
        token = auth_header[7:]
        user = get_user_from_token(token)
        
        if user:
            return JsonResponse({
                'tier': user.fuzeobs_tier,
                'ai_usage': user.fuzeobs_ai_usage_monthly,
                'email': user.email
            })
    except:
        pass
    
    return JsonResponse({'tier': 'free'})

@csrf_exempt
def fuzeobs_save_chat(request):
    """Save chat history for user"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)
    
    try:
        token = auth_header[7:]
        user = get_user_from_token(token)
        
        if not user:
            return JsonResponse({'success': False, 'error': 'Invalid token'}, status=401)
        
        data = json.loads(request.body)
        chat_data = data.get('chat')
        
        if not chat_data:
            return JsonResponse({'success': False, 'error': 'No chat data'}, status=400)
        
        # Store chat in cache with 30 day expiry
        chat_key = f'fuzeobs_chat_{user.id}_{chat_data.get("id")}'
        cache.set(chat_key, chat_data, 2592000)  # 30 days
        
        # Store chat ID in user's chat list
        user_chats_key = f'fuzeobs_chats_{user.id}'
        chat_list = cache.get(user_chats_key, [])
        
        # Add to front of list if not exists
        chat_id = chat_data.get('id')
        if chat_id not in [c.get('id') for c in chat_list]:
            chat_list.insert(0, {
                'id': chat_id,
                'title': chat_data.get('title', 'Untitled Chat'),
                'updated_at': chat_data.get('updated_at')
            })
            cache.set(user_chats_key, chat_list, 2592000)
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
def fuzeobs_get_chats(request):
    """Get user's chat history list"""
    if request.method != 'GET':
        return JsonResponse({'error': 'GET only'}, status=405)
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'chats': []})
    
    try:
        token = auth_header[7:]
        user = get_user_from_token(token)
        
        if not user:
            return JsonResponse({'chats': []})
        
        user_chats_key = f'fuzeobs_chats_{user.id}'
        chat_list = cache.get(user_chats_key, [])
        
        return JsonResponse({'chats': chat_list})
    except:
        return JsonResponse({'chats': []})

@csrf_exempt  
def fuzeobs_get_chat(request, chat_id):
    """Get specific chat by ID"""
    if request.method != 'GET':
        return JsonResponse({'error': 'GET only'}, status=405)
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        token = auth_header[7:]
        user = get_user_from_token(token)
        
        if not user:
            return JsonResponse({'error': 'Invalid token'}, status=401)
        
        chat_key = f'fuzeobs_chat_{user.id}_{chat_id}'
        chat_data = cache.get(chat_key)
        
        if not chat_data:
            return JsonResponse({'error': 'Chat not found'}, status=404)
        
        return JsonResponse({'chat': chat_data})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
def fuzeobs_delete_chat(request, chat_id):
    """Delete specific chat"""
    if request.method != 'DELETE':
        return JsonResponse({'error': 'DELETE only'}, status=405)
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        token = auth_header[7:]
        user = get_user_from_token(token)
        
        if not user:
            return JsonResponse({'error': 'Invalid token'}, status=401)
        
        # Delete chat data
        chat_key = f'fuzeobs_chat_{user.id}_{chat_id}'
        cache.delete(chat_key)
        
        # Remove from user's chat list
        user_chats_key = f'fuzeobs_chats_{user.id}'
        chat_list = cache.get(user_chats_key, [])
        chat_list = [c for c in chat_list if c.get('id') != chat_id]
        cache.set(user_chats_key, chat_list, 2592000)
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def get_user_from_token(token):
    """Simple token verification - format: user_id:email"""
    try:
        user_id, email = token.split(':', 1)
        return User.objects.get(id=int(user_id), email=email)
    except:
        return None