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
        return JsonResponse({'error': 'POST only'}, status=405)
    
    data = json.loads(request.body)
    email = data.get('email')
    password = data.get('password')
    
    try:
        user = User.objects.get(email=email)
        if user.check_password(password):
            # Generate simple token (use JWT in production)
            token = f"{user.id}:{user.email}"  # Replace with JWT
            
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
        return JsonResponse({'has_pro': False}, status=401)
    
    token = auth_header[7:]
    user = get_user_from_token(token)
    
    if not user:
        return JsonResponse({'has_pro': False}, status=401)
    
    return JsonResponse({
        'has_pro': user.fuzeobs_tier in ['pro', 'lifetime'],
        'tier': user.fuzeobs_tier
    })


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
    
    # Check free tier limit BEFORE incrementing
    if user.fuzeobs_tier == 'free' and user.fuzeobs_ai_usage_monthly >= 2:
        return JsonResponse({
            'error': 'Free tier limit reached (2/month). Upgrade to Pro for unlimited access.',
            'upgrade_required': True
        }, status=403)
    
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
                system="""You are FuzeOBS AI Assistant, an expert in OBS Studio, streaming, and content creation.

EXPERTISE:
- OBS Studio configuration and troubleshooting
- Hardware encoders (NVENC, AMF, QSV) and software encoding (x264)
- Streaming platforms (Twitch, YouTube, Kick, Facebook Gaming)
- Bitrate optimization and network streaming
- Audio configuration and mixing
- Scene composition and sources
- Filters and effects
- Performance optimization
- StreamElements/StreamLabs integration
- Plugin recommendations

RESPONSE STYLE:
- Be concise but thorough
- Provide specific numbers (bitrates, settings) when relevant
- Use bullet points for multiple items
- Give step-by-step instructions when needed
- Explain WHY settings matter, not just WHAT to set
- Recommend hardware-appropriate settings

KNOWLEDGE:
- Twitch max: 8000 kbps (Partner), 6000 kbps recommended
- YouTube max: 51000 kbps for 1080p60
- NVENC quality tiers: RTX 40/30 series = excellent, RTX 20/GTX 16 = good, GTX 10 = acceptable
- x264 presets: ultrafast to slow (slower = better quality, more CPU)
- Common issues: dropped frames (network), skipped frames (encoding overload), rendering lag (GPU/game load)""",
                messages=[{"role": "user", "content": message}]
            ) as stream:
                for text in stream.text_stream:
                    # Escape any potential SSE control characters
                    clean_text = text.replace('\n', ' ').replace('\r', ' ')
                    yield f"data: {clean_text}\n\n"
                    
            # Increment usage AFTER successful completion
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
    response['X-Accel-Buffering'] = 'no'  # Disable nginx buffering
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