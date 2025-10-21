from django.shortcuts import render
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
import anthropic
import os
import json
from datetime import date
from django.core.cache import cache
import random

User = get_user_model()

@csrf_exempt
def fuzeobs_signup(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    data = json.loads(request.body)
    email = data.get('email')
    username = data.get('username')
    password = data.get('password')
    
    if User.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'Email already registered'}, status=400)
    
    if User.objects.filter(username=username).exists():
        return JsonResponse({'success': False, 'error': 'Username already taken'}, status=400)
    
    user = User.objects.create_user(username=username, email=email, password=password)
    user.fuzeobs_tier = 'free'  # Changed to free
    user.save()
    
    token = f"{user.id}:{user.email}"
    return JsonResponse({
        'success': True,
        'token': token,
        'tier': 'free',
        'email': user.email
    })

@csrf_exempt
def fuzeobs_login(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    data = json.loads(request.body)
    email = data.get('email')
    password = data.get('password')
    
    try:
        user = User.objects.get(email=email)
        if user.check_password(password):
            token = f"{user.id}:{user.email}"
            
            return JsonResponse({
                'success': True,
                'token': token,
                'tier': user.fuzeobs_tier,
                'email': user.email
            })
        else:
            return JsonResponse({'success': False, 'error': 'Invalid credentials'}, status=401)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Invalid credentials'}, status=401)

@csrf_exempt
def fuzeobs_verify(request):
    """Verify user has pro access"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        response = JsonResponse({'has_pro': False}, status=401)
    else:
        token = auth_header[7:]
        user = get_user_from_token(token)
        
        if not user:
            response = JsonResponse({'has_pro': False}, status=401)
        else:
            response = JsonResponse({
                'has_pro': user.fuzeobs_tier in ['pro', 'lifetime'],
                'tier': user.fuzeobs_tier
            })
    
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response

@csrf_exempt
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
        def off_topic_message():
            message_data = {'text': '**Off-Topic Query Detected**\n\nThis AI assistant is specifically designed for OBS Studio and streaming questions only. Please ask about:\n\n• OBS settings and configuration\n• Stream quality and encoding\n• Hardware compatibility\n• Streaming platforms (Twitch, YouTube, etc.)\n• Audio/video capture issues\n• Scene setup and sources\n\nFor other topics, please use a general-purpose AI assistant.'}
            yield "data: " + json.dumps(message_data) + "\n\n"
            yield "data: [DONE]\n\n"
        
        response = StreamingHttpResponse(off_topic_message(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'
        response['Access-Control-Allow-Origin'] = '*'
        return response
    
    # Increment usage BEFORE streaming
    user.fuzeobs_ai_usage_monthly += 1
    user.save()
    
    # Model selection
    if user.fuzeobs_tier in ['pro', 'lifetime']:
        model = "claude-3-5-haiku-20241022" if user.fuzeobs_ai_usage_monthly > 500 else "claude-sonnet-4-20250514"
    else:
        model = "claude-3-5-haiku-20241022"
    
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    def generate():
        """Generator function for SSE streaming"""
        try:
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                system=f"""You are the FuzeOBS AI Assistant - expert in OBS Studio and streaming.

USER TIER: {user.fuzeobs_tier.upper()}

Write clear, natural responses with proper spacing and line breaks.

CRITICAL: You ONLY answer questions about:
- OBS Studio (settings, configuration, troubleshooting)
- Streaming (Twitch, YouTube, Kick, Facebook Gaming)
- Encoding (x264, NVENC, AMD AMF, QuickSync) - BASIC INFO ONLY FOR FREE USERS
- Hardware for streaming (GPUs, CPUs, capture cards) or that the user provided
- Benchmark results and recommendations
- Audio/video capture and setup
- Scene creation and sources
- Streaming performance and optimization

If asked about ANY other topic (homework, coding unrelated to OBS, general knowledge, recipes, etc.), politely redirect them:
"I'm specifically designed to help with OBS Studio and streaming questions only. For other topics, please use a general-purpose AI assistant."

IMPORTANT: When creating numbered lists, use descriptive headers instead of numbered items. For example:
- Use "**Encoder Settings:**" instead of "1. Encoder Settings"
- Use "**Stream Output:**" instead of "2. Stream Output"

{'ADVANCED ENCODER RESTRICTION (FREE TIER):' if user.fuzeobs_tier == 'free' else ''}
{'You may NOT provide detailed advanced encoder settings to free users. This includes:' if user.fuzeobs_tier == 'free' else ''}
{'- NVENC preset details (p1-p7), tuning modes, multipass, lookahead, psycho_aq, b-frames' if user.fuzeobs_tier == 'free' else ''}
{'- x264 CPU usage presets beyond "veryfast", tune options, advanced rate control' if user.fuzeobs_tier == 'free' else ''}
{'- AMD/QSV advanced parameters' if user.fuzeobs_tier == 'free' else ''}
{'- Profile/level settings (baseline, main, high)' if user.fuzeobs_tier == 'free' else ''}
{'' if user.fuzeobs_tier == 'free' else ''}
{'When free users ask about advanced encoder settings, respond:' if user.fuzeobs_tier == 'free' else ''}
{'"**Advanced encoder optimization is a Pro feature.** The FuzeOBS configurator automatically selects optimal advanced settings for your hardware. For manual fine-tuning of encoder parameters like presets, multipass, and tuning modes, upgrade to Pro for full AI guidance on these settings."' if user.fuzeobs_tier == 'free' else ''}
{'' if user.fuzeobs_tier == 'free' else ''}
{'You CAN provide to free users:' if user.fuzeobs_tier == 'free' else ''}
{'- Basic encoder selection (NVENC vs x264 vs AMD)' if user.fuzeobs_tier == 'free' else ''}
{'- General resolution, FPS, and bitrate recommendations' if user.fuzeobs_tier == 'free' else ''}
{'- Hardware compatibility information' if user.fuzeobs_tier == 'free' else ''}
{'- Troubleshooting dropped frames, lag, or quality issues' if user.fuzeobs_tier == 'free' else ''}

For 1080p 60fps on Twitch, use 6000 kbps.

This is the sweet spot for excellent quality without hitting Twitch's 8000 kbps limit. Going higher risks viewer buffering.

Recommended settings:
- Resolution: 1920x1080
- FPS: 60
- Bitrate: 6000 kbps
- Encoder: NVENC (if you have RTX GPU) or x264 on "veryfast"

Key tip: Consistent upload speed matters more than raw bitrate. Test your connection first.

What's your current upload speed and GPU? I can help optimize your encoder settings.""",
                messages=[{"role": "user", "content": message}]
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            print(f"AI Stream Error: {e}")
            yield "data: [ERROR] Failed to generate response. Please try again.\n\n"
    
    response = StreamingHttpResponse(generate(), content_type='text/event-stream; charset=utf-8')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    response['X-Accel-Buffering'] = 'no'
    response['Connection'] = 'keep-alive'
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Credentials'] = 'false'
    
    return response

@csrf_exempt
def fuzeobs_save_chat(request):
    """Save chat history for user"""
    if request.method != 'POST':
        response = JsonResponse({'error': 'POST only'}, status=405)
    else:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            response = JsonResponse({'error': 'Unauthorized'}, status=401)
        else:
            token = auth_header[7:]
            user = get_user_from_token(token)
            
            if not user:
                response = JsonResponse({'error': 'Invalid token'}, status=401)
            else:
                data = json.loads(request.body)
                chat_data = data.get('chat')
                
                if not chat_data:
                    response = JsonResponse({'error': 'No chat data provided'}, status=400)
                else:
                    if not user.fuzeobs_chat_history:
                        user.fuzeobs_chat_history = []
                    
                    # Create a new list to trigger Django's change detection
                    chat_history = list(user.fuzeobs_chat_history)  # Make a copy
                    
                    # Normalize existing chats - unwrap any that have {chat: {...}} structure
                    normalized_history = []
                    for item in chat_history:
                        if isinstance(item, dict):
                            # Check if this item has a nested 'chat' key
                            if 'chat' in item and isinstance(item['chat'], dict) and 'id' in item['chat']:
                                normalized_history.append(item['chat'])  # Unwrap
                            elif 'id' in item:
                                normalized_history.append(item)  # Already correct format
                            # Skip malformed items that have neither structure
                        # Skip non-dict items
                    
                    # Find existing chat by ID
                    existing_index = next((i for i, c in enumerate(normalized_history) if c.get('id') == chat_data.get('id')), None)
                    
                    if existing_index is not None:
                        # Replace the entire dict, don't update in place
                        normalized_history[existing_index] = chat_data
                    else:
                        normalized_history.append(chat_data)
                    
                    # Reassign the field to trigger change detection
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
def fuzeobs_get_chats(request):
    """Get all chats for user"""
    if request.method != 'GET':
        response = JsonResponse({'error': 'GET only'}, status=405)
    else:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            response = JsonResponse({'chats': []})
        else:
            token = auth_header[7:]
            user = get_user_from_token(token)
            
            if not user:
                response = JsonResponse({'chats': []})
            else:
                chats = user.fuzeobs_chat_history if user.fuzeobs_chat_history else []
                response = JsonResponse({'chats': chats})
    
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    return response

@csrf_exempt
def fuzeobs_delete_chat(request):
    """Delete specific chat"""
    if request.method != 'POST':
        response = JsonResponse({'error': 'POST only'}, status=405)
    else:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            response = JsonResponse({'error': 'Unauthorized'}, status=401)
        else:
            token = auth_header[7:]
            user = get_user_from_token(token)
            
            if not user:
                response = JsonResponse({'error': 'Invalid token'}, status=401)
            else:
                data = json.loads(request.body)
                chat_id = data.get('chatId')
                
                if hasattr(user, 'fuzeobs_chat_history'):
                    user.fuzeobs_chat_history = [
                        c for c in user.fuzeobs_chat_history 
                        if c['id'] != chat_id
                    ]
                    user.save()
                
                response = JsonResponse({'success': True})
    
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    return response

@csrf_exempt
def fuzeobs_clear_chats(request):
    """Clear all chats"""
    if request.method != 'POST':
        response = JsonResponse({'error': 'POST only'}, status=405)
    else:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            response = JsonResponse({'error': 'Unauthorized'}, status=401)
        else:
            token = auth_header[7:]
            user = get_user_from_token(token)
            
            if not user:
                response = JsonResponse({'error': 'Invalid token'}, status=401)
            else:
                user.fuzeobs_chat_history = []
                user.save()
                response = JsonResponse({'success': True})
    
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    return response

@csrf_exempt
def fuzeobs_analyze_benchmark(request):
    """Analyze benchmark results with AI - PRO ONLY"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    token = auth_header[7:]
    user = get_user_from_token(token)
    
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    if user.fuzeobs_tier not in ['pro', 'lifetime']:
        def pro_required():
            message_data = {'text': '**Pro Feature Required**\n\nAI benchmark analysis is exclusive to Pro users.'}
            yield "data: " + json.dumps(message_data) + "\n\n"
            yield "data: [DONE]\n\n"
        
        response = StreamingHttpResponse(pro_required(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'
        response['Access-Control-Allow-Origin'] = '*'
        return response
    
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

def get_user_from_token(token):
    """Simple token verification"""
    try:
        user_id, email = token.split(':')
        return User.objects.get(id=int(user_id), email=email)
    except:
        return None