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
    """AI chat streaming endpoint"""
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
    
    # Reset monthly usage if new month (for ALL tiers)
    if not user.fuzeobs_usage_reset_date or user.fuzeobs_usage_reset_date.month != date.today().month:
        user.fuzeobs_ai_usage_monthly = 0
        user.fuzeobs_usage_reset_date = date.today()
        user.save()
    
    # Check free tier limit
    if user.fuzeobs_tier == 'free' and user.fuzeobs_ai_usage_monthly >= 2:
        return JsonResponse({'error': 'Free tier limit reached (2/month). Upgrade to Pro for unlimited.'}, status=403)
    
    # Smart model selection (Pro/Lifetime use Haiku after 500)
    if user.fuzeobs_tier in ['pro', 'lifetime']:
        model = "claude-haiku-3-5-20241022" if user.fuzeobs_ai_usage_monthly > 500 else "claude-sonnet-4-20250514"
    else:
        model = "claude-haiku-3-5-20241022"  # Free always uses cheaper model
    
    # Get message
    data = json.loads(request.body)
    message = data.get('message', '')
    
    # Stream response
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    def generate():
        try:
            with client.messages.stream(
                model=model,
                max_tokens=2048,
                system="You are FuzeOBS AI Assistant, an expert in OBS Studio, streaming, and content creation. Help users with OBS configuration, encoder settings (NVENC, x264, AMF, QSV), streaming platforms (Twitch, YouTube, Kick), StreamLabs, plugins, performance optimization, scene setup, and audio configuration. Keep responses concise but thorough.",
                messages=[{"role": "user", "content": message}]
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {text}\n\n"
            
            # Track usage
            user.fuzeobs_ai_usage_monthly += 1
            user.save()
            
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: [ERROR] {str(e)}\n\n"
    
    return StreamingHttpResponse(generate(), content_type='text/event-stream')


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