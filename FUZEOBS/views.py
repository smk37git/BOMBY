from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate
from ACCOUNTS.models import User
import json
from datetime import date
import anthropic
import os

TIER_CONFIG = {
    'free': {
        'ai_daily_limit': 5,
        'ai_model': 'claude-3-5-haiku-20241022',
        'advanced_setup': False,
        'scene_templates': False,
        'benchmarking': False
    },
    'pro': {
        'ai_daily_limit': 999999,
        'ai_model': 'claude-sonnet-4-20250514',
        'advanced_setup': True,
        'scene_templates': True,
        'benchmarking': True
    },
    'lifetime': {
        'ai_daily_limit': 999999,
        'ai_model': 'claude-sonnet-4-20250514',
        'advanced_setup': True,
        'scene_templates': True,
        'benchmarking': True
    }
}

def verify_token(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header[7:]
    if token == 'guest':
        return 'guest'
    
    try:
        user_id, token_val = token.split(':', 1)
        user = User.objects.get(id=int(user_id))
        
        from django.contrib.auth.tokens import default_token_generator
        if default_token_generator.check_token(user, token_val):
            return user
    except:
        pass
    
    return None

def check_and_reset_daily_usage(user):
    if isinstance(user, str):
        return
    
    today = date.today()
    if user.fuzeobs_usage_reset_date != today:
        user.fuzeobs_ai_usage_monthly = 0
        user.fuzeobs_usage_reset_date = today
        user.save()

def check_ai_usage(user):
    if isinstance(user, str):
        return False, "Login required for AI features"
    
    check_and_reset_daily_usage(user)
    
    tier_config = TIER_CONFIG.get(user.fuzeobs_tier, TIER_CONFIG['free'])
    daily_limit = tier_config['ai_daily_limit']
    
    if user.fuzeobs_ai_usage_monthly >= daily_limit:
        return False, f"Daily AI limit reached ({daily_limit} messages). Resets at midnight."
    
    return True, None

def check_feature_access(user, feature):
    if isinstance(user, str):
        return False
    
    tier_config = TIER_CONFIG.get(user.fuzeobs_tier, TIER_CONFIG['free'])
    return tier_config.get(feature, False)

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_signup(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')
        username = data.get('username')
        password = data.get('password')
        
        if User.objects.filter(email=email).exists():
            return JsonResponse({'success': False, 'error': 'Email already registered'}, status=400)
        
        if User.objects.filter(username=username).exists():
            return JsonResponse({'success': False, 'error': 'Username taken'}, status=400)
        
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            fuzeobs_tier='free',
            fuzeobs_usage_reset_date=date.today()
        )
        
        from django.contrib.auth.tokens import default_token_generator
        token = default_token_generator.make_token(user)
        
        return JsonResponse({
            'success': True,
            'email': user.email,
            'username': user.username,
            'tier': 'free',
            'token': f"{user.id}:{token}"
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_login(request):
    try:
        data = json.loads(request.body)
        email = data.get('email')
        password = data.get('password')
        
        user = authenticate(request, username=email, password=password)
        if not user:
            try:
                user_obj = User.objects.get(email=email)
                user = authenticate(request, username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        
        if user:
            from django.contrib.auth.tokens import default_token_generator
            token = default_token_generator.make_token(user)
            
            return JsonResponse({
                'success': True,
                'email': user.email,
                'username': user.username,
                'tier': user.fuzeobs_tier,
                'token': f"{user.id}:{token}"
            })
        else:
            return JsonResponse({'success': False, 'error': 'Invalid credentials'}, status=401)
            
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_verify(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'valid': False}, status=401)
    
    check_and_reset_daily_usage(user)
    
    tier_config = TIER_CONFIG[user.fuzeobs_tier]
    
    return JsonResponse({
        'valid': True,
        'email': user.email,
        'username': user.username,
        'tier': user.fuzeobs_tier,
        'ai_usage_today': user.fuzeobs_ai_usage_monthly,
        'ai_daily_limit': tier_config['ai_daily_limit']
    })

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_ai_chat(request):
    user = verify_token(request)
    
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    can_use, error = check_ai_usage(user)
    if not can_use:
        return JsonResponse({'error': error}, status=403)
    
    try:
        data = json.loads(request.body)
        message = data.get('message', '')
        
        tier_config = TIER_CONFIG[user.fuzeobs_tier]
        model = tier_config['ai_model']
        
        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        
        def generate():
            try:
                with client.messages.stream(
                    model=model,
                    max_tokens=2048,
                    messages=[{
                        "role": "user",
                        "content": f"{message}\n\nProvide OBS optimization advice in a concise, helpful manner."
                    }]
                ) as stream:
                    for text in stream.text_stream:
                        yield f"data: {json.dumps({'content': text})}\n\n"
                
                yield f"data: {json.dumps({'done': True})}\n\n"
                
                user.fuzeobs_ai_usage_monthly += 1
                user.save()
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return StreamingHttpResponse(generate(), content_type='text/event-stream')
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_save_chat(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    try:
        data = json.loads(request.body)
        chat_entry = data.get('chat')
        
        if not isinstance(user.fuzeobs_chat_history, list):
            user.fuzeobs_chat_history = []
        
        user.fuzeobs_chat_history.append(chat_entry)
        user.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_get_chats(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'chats': []})
    
    chats = user.fuzeobs_chat_history if isinstance(user.fuzeobs_chat_history, list) else []
    return JsonResponse({'chats': chats})

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_delete_chat(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    try:
        data = json.loads(request.body)
        chat_id = data.get('chat_id')
        
        if isinstance(user.fuzeobs_chat_history, list):
            user.fuzeobs_chat_history = [c for c in user.fuzeobs_chat_history if c.get('id') != chat_id]
            user.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_clear_chats(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    try:
        user.fuzeobs_chat_history = []
        user.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_analyze_benchmark(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    if not check_feature_access(user, 'benchmarking'):
        return JsonResponse({'error': 'Pro or Lifetime tier required'}, status=403)
    
    can_use, error = check_ai_usage(user)
    if not can_use:
        return JsonResponse({'error': error}, status=403)
    
    try:
        data = json.loads(request.body)
        benchmark_data = data.get('benchmark_data', '')
        
        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        
        response = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": f"Analyze this OBS benchmark:\n\n{benchmark_data}\n\nProvide detailed optimization recommendations."
            }]
        )
        
        user.fuzeobs_ai_usage_monthly += 1
        user.save()
        
        return JsonResponse({
            'success': True,
            'analysis': response.content[0].text
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_get_profiles(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'profiles': []})
    
    profiles = []
    return JsonResponse({'profiles': profiles})

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_create_profile(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    try:
        data = json.loads(request.body)
        return JsonResponse({'success': True, 'profile_id': 1})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["PUT"])
def fuzeobs_update_profile(request, profile_id):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    return JsonResponse({'success': True})

@csrf_exempt
@require_http_methods(["DELETE"])
def fuzeobs_delete_profile(request, profile_id):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    return JsonResponse({'success': True})

@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_list_templates(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    if not check_feature_access(user, 'scene_templates'):
        return JsonResponse({'error': 'Pro or Lifetime tier required'}, status=403)
    
    templates = [
        {'id': 'gaming-basic', 'name': 'Gaming Basic', 'description': 'Basic gaming layout'},
        {'id': 'streaming-pro', 'name': 'Streaming Pro', 'description': 'Professional streaming'},
        {'id': 'recording-hq', 'name': 'Recording HQ', 'description': 'High quality recording'}
    ]
    
    return JsonResponse({'templates': templates})

@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_get_template(request, template_id):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    if not check_feature_access(user, 'scene_templates'):
        return JsonResponse({'error': 'Pro or Lifetime tier required'}, status=403)
    
    template = {
        'id': template_id,
        'name': f'Template {template_id}',
        'scenes': [{'name': 'Main Scene', 'sources': []}],
        'settings': {}
    }
    
    return JsonResponse({'template': template})

@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_get_background(request, background_id):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    if not check_feature_access(user, 'scene_templates'):
        return JsonResponse({'error': 'Pro or Lifetime tier required'}, status=403)
    
    return JsonResponse({'error': 'Not implemented - backgrounds served locally'}, status=501)

@csrf_exempt
@require_http_methods(["POST"])
def fuzeobs_quickstart_dismiss(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'error': 'Login required'}, status=401)
    
    user.quickstart_dismissed = True
    user.save()
    return JsonResponse({'success': True})

@csrf_exempt
@require_http_methods(["GET"])
def fuzeobs_quickstart_check(request):
    user = verify_token(request)
    if not user or user == 'guest':
        return JsonResponse({'dismissed': False})
    
    return JsonResponse({'dismissed': user.quickstart_dismissed})