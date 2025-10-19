from django.shortcuts import render

# Create your views here.
from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import get_user_model
import anthropic
import os
import json
from datetime import date

User = get_user_model()

@csrf_exempt
def fuzeobs_login(request):
    """Login endpoint for FuzeOBS desktop app"""
    if request.method != 'POST':
        response = JsonResponse({'error': 'POST only'}, status=405)
    else:
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')
        
        try:
            user = User.objects.get(email=email)
            if user.check_password(password):
                token = f"{user.id}:{user.email}"
                response = JsonResponse({
                    'success': True,
                    'token': token,
                    'tier': user.fuzeobs_tier,
                    'email': user.email
                })
            else:
                response = JsonResponse({'success': False, 'error': 'Invalid credentials'}, status=401)
        except User.DoesNotExist:
            response = JsonResponse({'success': False, 'error': 'Invalid credentials'}, status=401)
    
    # Add CORS headers
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    return response

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
    
    # Add CORS headers
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    return response


@csrf_exempt
def fuzeobs_ai_chat(request):
    """AI chat streaming endpoint with proper SSE implementation"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    # Verify user
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    token = auth_header[7:]
    user = get_user_from_token(token)
    
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    # Reset monthly usage if new month
    if not user.fuzeobs_usage_reset_date or user.fuzeobs_usage_reset_date.month != date.today().month:
        user.fuzeobs_ai_usage_monthly = 0
        user.fuzeobs_usage_reset_date = date.today()
        user.save()
    
    # Check free tier limit - allow the 2 free messages
    if user.fuzeobs_tier == 'free' and user.fuzeobs_ai_usage_monthly >= 2:
        return JsonResponse({
            'error': 'Free tier limit reached. You have used your 2 free queries this month.',
            'upgrade_required': True
        }, status=403)
    
    # Increment usage at START for free tier tracking
    if user.fuzeobs_tier == 'free':
        user.fuzeobs_ai_usage_monthly += 1
        user.save()
    
    # Model selection
    if user.fuzeobs_tier in ['pro', 'lifetime']:
        model = "claude-haiku-3-5-20241022" if user.fuzeobs_ai_usage_monthly > 500 else "claude-sonnet-4-20250514"
    else:
        model = "claude-haiku-3-5-20241022"
    
    # Get message
    data = json.loads(request.body)
    message = data.get('message', '').strip()
    
    if not message:
        return JsonResponse({'error': 'Empty message'}, status=400)
    
    # Initialize Anthropic client
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    def generate():
        """Generator function for SSE streaming"""
        try:
            # Stream from Anthropic
            with client.messages.stream(
                model=model,
                max_tokens=4096,
                system="""You are the FuzeOBS AI Assistant - an expert in OBS Studio and streaming.

COMMUNICATION STYLE:
- Write in clear, natural language like a knowledgeable friend
- Break complex topics into digestible explanations
- Use short paragraphs and bullet points for readability
- Avoid jargon unless necessary, then explain it
- Be encouraging and supportive

EXPERTISE AREAS:
- OBS configuration and troubleshooting
- Encoder settings (NVENC, x264, AMF, QSV)
- Streaming platforms (Twitch, YouTube, Kick)
- Bitrate and quality optimization
- Audio setup and mixing
- Scene design and sources
- Performance issues (dropped frames, lag, crashes)
- Plugin recommendations

WHEN ANSWERING:
- Start with a direct answer to the question
- Provide specific settings when relevant
- Explain why settings matter, not just what to set
- Tailor advice to user's hardware when possible
- For troubleshooting, suggest the most likely causes first

EXAMPLES OF GOOD RESPONSES:

Question: "What NVENC settings for quality?"
Answer: "For RTX 30/40 series, use these NVENC settings for best quality:

**Preset:** Quality (not Max Quality - minimal difference)
**Profile:** High
**Look-ahead & Psycho Visual Tuning:** ON

Why: RTX cards have excellent NVENC that rivals x264 medium. Look-ahead helps with motion, Psycho Visual improves perceived quality.

If you're on a GTX 1660 or older, consider x264 veryfast instead - older NVENC is less impressive."

Keep responses conversational but informative.""",
                messages=[{"role": "user", "content": message}]
            ) as stream:
                for text in stream.text_stream:
                    # Escape any potential SSE control characters
                    clean_text = text.replace('\n', ' ').replace('\r', ' ')
                    yield f"data: {clean_text}\n\n"
                    
            # Only increment for PRO users (free already incremented)
            if user.fuzeobs_tier in ['pro', 'lifetime']:
                user.fuzeobs_ai_usage_monthly += 1
                user.save()
            
            # Send completion signal
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            print(f"AI Stream Error: {e}")
            yield f"data: [ERROR] Failed to generate response. Please try again.\n\n"
    
    # Create streaming response with proper headers
    response = StreamingHttpResponse(
        generate(),
        content_type='text/event-stream; charset=utf-8'
    )
    
    # Essential headers for SSE and CORS
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    response['X-Accel-Buffering'] = 'no'
    response['Connection'] = 'keep-alive'
    
    # CORS headers
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response['Access-Control-Allow-Credentials'] = 'false'
    
    return response

def get_user_from_token(token):
    """Simple token verification - replace with JWT"""
    try:
        user_id, email = token.split(':')
        return User.objects.get(id=int(user_id), email=email)
    except:
        return None

def get_user_from_token(token):
    """Simple token verification - replace with JWT"""
    try:
        user_id, email = token.split(':')
        return User.objects.get(id=int(user_id), email=email)
    except:
        return None