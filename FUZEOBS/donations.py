"""
Donations/Tipping System for FuzeOBS
Uses PayPal Orders API v2 for proper checkout with custom amounts
"""
import json
import secrets
import requests
import logging
import base64
from decimal import Decimal
from django.db import models
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import DonationSettings, Donation
from .views import get_user_from_token
from ACCOUNTS.validators import contains_profanity

logger = logging.getLogger(__name__)

# PayPal Configuration
PAYPAL_SANDBOX_MODE = getattr(settings, 'PAYPAL_SANDBOX_MODE', False)
PAYPAL_BASE = 'https://api-m.sandbox.paypal.com' if PAYPAL_SANDBOX_MODE else 'https://api-m.paypal.com'
PAYPAL_WEB_BASE = 'https://www.sandbox.paypal.com' if PAYPAL_SANDBOX_MODE else 'https://www.paypal.com'
PAYPAL_CLIENT_ID = getattr(settings, 'PAYPAL_CLIENT_ID', '') or ''
PAYPAL_SECRET = getattr(settings, 'PAYPAL_SECRET', '') or ''


def get_paypal_access_token():
    """Get PayPal access token for API calls"""
    try:
        auth = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_SECRET}".encode()).decode()
        resp = requests.post(
            f'{PAYPAL_BASE}/v1/oauth2/token',
            headers={
                'Authorization': f'Basic {auth}',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            data={'grant_type': 'client_credentials'},
            timeout=30
        )
        if resp.status_code == 200:
            return resp.json().get('access_token')
    except Exception as e:
        logger.error(f"Failed to get PayPal access token: {e}")
    return None


@csrf_exempt
@require_http_methods(["GET", "POST"])
def donation_settings(request):
    """Get or update donation settings"""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    try:
        ds, created = DonationSettings.objects.get_or_create(
            user=user,
            defaults={
                'page_title': f'Support {user.username}!',
                'page_message': 'Thanks for supporting the stream!',
            }
        )
        
        if request.method == 'GET':
            total = Donation.objects.filter(streamer=user, status='completed').aggregate(
                total=models.Sum('amount')
            )['total'] or 0
            
            connected = bool(ds.paypal_merchant_id or ds.paypal_email)
            
            return JsonResponse({
                'paypal_connected': connected,
                'paypal_email': ds.paypal_email or '',
                'paypal_payer_id': ds.paypal_merchant_id or '',
                'donation_url': f'https://bomby.us/fuzeobs/donate/{ds.donation_token}' if connected else '',
                'min_amount': float(ds.min_amount),
                'suggested_amounts': ds.suggested_amounts,
                'currency': ds.currency,
                'page_title': ds.page_title,
                'page_message': ds.page_message,
                'show_recent_donations': ds.show_recent_donations,
                'total_received': float(total),
                'enabled': ds.enabled,
            })
        
        data = json.loads(request.body)
        
        # Profanity filter for page_title and page_message
        page_title = data.get('page_title', ds.page_title)
        page_message = data.get('page_message', ds.page_message)
        
        if contains_profanity(page_title):
            return JsonResponse({'error': 'Page title contains inappropriate language'}, status=400)
        
        if contains_profanity(page_message):
            return JsonResponse({'error': 'Welcome message contains inappropriate language'}, status=400)
        
        ds.min_amount = data.get('min_amount', ds.min_amount)
        ds.currency = data.get('currency', ds.currency)
        ds.page_title = page_title
        ds.page_message = page_message
        ds.show_recent_donations = data.get('show_recent_donations', ds.show_recent_donations)
        ds.enabled = data.get('enabled', ds.enabled)
        if 'suggested_amounts' in data:
            ds.suggested_amounts = data['suggested_amounts']
        ds.save()
        
        return JsonResponse({'saved': True})
    except Exception as e:
        logger.error(f"donation_settings error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def paypal_connect(request):
    """Initiate PayPal OAuth to get Payer ID"""
    if not PAYPAL_CLIENT_ID or not PAYPAL_SECRET:
        return JsonResponse({'error': 'PayPal not configured'}, status=500)
    
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    try:
        ds, _ = DonationSettings.objects.get_or_create(user=user)
        
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(16)
        ds.oauth_state = f"{state}:{nonce}"
        ds.save()
        
        redirect_uri = 'https://bomby.us/fuzeobs/donations/paypal/callback'
        
        auth_url = (
            f'{PAYPAL_WEB_BASE}/signin/authorize'
            f'?client_id={PAYPAL_CLIENT_ID}'
            f'&response_type=code'
            f'&scope=openid+email+https://uri.paypal.com/services/paypalattributes'
            f'&redirect_uri={redirect_uri}'
            f'&state={state}'
            f'&nonce={nonce}'
        )
        
        logger.info(f"PayPal connect initiated for user {user.id}")
        return JsonResponse({'auth_url': auth_url})
    except Exception as e:
        logger.error(f"paypal_connect error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def paypal_callback(request):
    """Handle PayPal OAuth callback - extract payer_id"""
    code = request.GET.get('code')
    state = request.GET.get('state')
    error = request.GET.get('error')
    
    if error:
        logger.error(f"PayPal callback error: {error}")
        return render(request, 'FUZEOBS/paypal_connected.html', {
            'success': False,
            'error': error
        })
    
    if not code or not state:
        return HttpResponse('<script>window.close();</script>')
    
    try:
        ds = DonationSettings.objects.get(oauth_state__startswith=state)
    except DonationSettings.DoesNotExist:
        return HttpResponse('<script>alert("Invalid state"); window.close();</script>')
    
    redirect_uri = 'https://bomby.us/fuzeobs/donations/paypal/callback'
    
    try:
        identity_base = 'https://api.sandbox.paypal.com' if PAYPAL_SANDBOX_MODE else 'https://api.paypal.com'
        resp = requests.post(
            f'{identity_base}/v1/identity/openidconnect/tokenservice',
            auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': redirect_uri,
            },
            headers={'Accept': 'application/json'},
            timeout=30
        )
        
        logger.info(f"PayPal token response: {resp.status_code}")
        
        if resp.status_code != 200:
            logger.error(f"Token exchange failed: {resp.text}")
            return HttpResponse('<script>alert("Token exchange failed"); window.close();</script>')
        
        tokens = resp.json()
        access_token = tokens.get('access_token')
        
        payer_id = None
        email = None
        
        id_token = tokens.get('id_token')
        if id_token:
            try:
                payload = id_token.split('.')[1]
                payload += '=' * (4 - len(payload) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(payload))
                payer_id = decoded.get('payer_id') or decoded.get('sub')
                email = decoded.get('email')
            except Exception as e:
                logger.error(f"id_token decode error: {e}")
        
        if not payer_id:
            user_resp = requests.get(
                f'{identity_base}/v1/identity/openidconnect/userinfo/?schema=openid',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=30
            )
            if user_resp.status_code == 200:
                user_info = user_resp.json()
                payer_id = user_info.get('payer_id') or user_info.get('user_id')
                email = user_info.get('email')

        if payer_id or email:
            ds.paypal_merchant_id = payer_id or ''
            ds.paypal_email = email or ''
            ds.oauth_state = ''
            ds.save()
            
            return render(request, 'FUZEOBS/paypal_connected.html', {
                'success': True,
                'email': email
            })
        else:
            return render(request, 'FUZEOBS/paypal_connected.html', {
                'success': False,
                'error': 'Could not retrieve PayPal account info'
            })
    except Exception as e:
        logger.error(f"PayPal callback error: {e}")
        return render(request, 'FUZEOBS/paypal_connected.html', {
            'success': False,
            'error': f'Connection error: {str(e)}'
        })


@csrf_exempt
@require_http_methods(["POST"])
def paypal_disconnect(request):
    """Disconnect PayPal"""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    DonationSettings.objects.filter(user=user).update(
        paypal_email='',
        paypal_merchant_id='',
    )
    
    return JsonResponse({'disconnected': True})


def donation_page(request, token):
    """Public donation page using PayPal JS SDK"""
    try:
        ds = DonationSettings.objects.select_related('user').get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return HttpResponse('Donation page not found', status=404)
    
    if not ds.enabled:
        return HttpResponse('Donations are currently disabled', status=404)
    
    business_id = ds.paypal_email or ds.paypal_merchant_id
    if not business_id:
        return HttpResponse('Donations not configured', status=404)
    
    recent_donations = []
    if ds.show_recent_donations:
        recent_donations = list(
            Donation.objects.filter(streamer=ds.user, status='completed')
            .order_by('-created_at')[:5]
            .values('donor_name', 'amount', 'currency', 'created_at')
        )
    
    profile_picture = None
    if ds.user.profile_picture:
        profile_picture = ds.user.profile_picture.url
    
    context = {
        'streamer': ds.user.username,
        'profile_picture': profile_picture,
        'page_title': ds.page_title,
        'page_message': ds.page_message,
        'min_amount': float(ds.min_amount),
        'suggested_amounts': ds.suggested_amounts,
        'currency': ds.currency,
        'recent_donations': recent_donations,
        'show_recent_donations': ds.show_recent_donations,
        'token': token,
        'business_id': business_id,
        'paypal_client_id': PAYPAL_CLIENT_ID,
        'paypal_env': 'sandbox' if PAYPAL_SANDBOX_MODE else 'production',
    }
    
    return render(request, 'FUZEOBS/donation_page.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def create_donation_order(request, token):
    """Legacy endpoint - orders now created client-side"""
    return JsonResponse({'error': 'Orders are created client-side'}, status=400)


@csrf_exempt
@require_http_methods(["POST"])
def validate_donation(request, token):
    """Pre-validate donor name and message before PayPal flow"""
    try:
        ds = DonationSettings.objects.get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
    data = json.loads(request.body)
    donor_name = data.get('name', 'Anonymous')[:100]
    message = data.get('message', '')[:500]
    
    if contains_profanity(donor_name):
        return JsonResponse({'error': 'Name contains inappropriate language', 'field': 'name'}, status=400)
    
    if contains_profanity(message):
        return JsonResponse({'error': 'Message contains inappropriate language', 'field': 'message'}, status=400)
    
    return JsonResponse({'valid': True})


@csrf_exempt
@require_http_methods(["POST"])
def capture_donation(request, token):
    """Record donation after client-side PayPal capture"""
    try:
        ds = DonationSettings.objects.select_related('user').get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
    data = json.loads(request.body)
    order_id = data.get('order_id')
    donor_name = data.get('name', 'Anonymous')[:100]
    message = data.get('message', '')[:500]
    amount = Decimal(str(data.get('amount', 0)))
    
    # Profanity filter
    if contains_profanity(donor_name):
        return JsonResponse({'error': 'Name contains inappropriate language', 'field': 'name'}, status=400)
    
    if contains_profanity(message):
        return JsonResponse({'error': 'Message contains inappropriate language', 'field': 'message'}, status=400)
    
    # Create completed donation record
    donation = Donation.objects.create(
        streamer=ds.user,
        paypal_order_id=order_id or f'client_{secrets.token_hex(8)}',
        donor_name=donor_name,
        message=message,
        amount=amount,
        currency=ds.currency,
        status='completed',
    )
    
    # Currency symbols map
    currency_symbols = {
        'USD': '$', 'EUR': '€', 'GBP': '£', 'CAD': 'C$', 'AUD': 'A$',
        'JPY': '¥', 'CNY': '¥', 'KRW': '₩', 'INR': '₹', 'BRL': 'R$',
    }
    symbol = currency_symbols.get(ds.currency, ds.currency + ' ')
    
    # Trigger alerts to all widgets
    trigger_donation_alert(ds.user.id, {
        'name': donor_name,
        'amount': float(amount),
        'currency': ds.currency,
        'message': message,
        'formatted_amount': f'{symbol}{amount:.2f}',
    })
    
    return JsonResponse({'success': True})


def trigger_donation_alert(user_id, data):
    """Send donation alert to all widgets via their dedicated channels"""
    channel_layer = get_channel_layer()
    
    # Standard alert format for event list and alert box
    alert_data = {
        'type': 'donation',
        'event_type': 'donation',
        'platform': 'donation',
        'event_data': {
            'username': data['name'],
            'amount': data['formatted_amount'],  # "$1.00" for display
            'raw_amount': data['amount'],        # 1.0 for calculations
            'currency': data['currency'],
            'message': data['message'],
        },
    }
    
    # Send to donations channel ONLY (prevents duplicate events)
    # Event list and alert box subscribe to this channel
    async_to_sync(channel_layer.group_send)(
        f'donations_{user_id}',
        {'type': 'donation_event', 'data': alert_data}
    )
    
    # Send goal update with increment for tip goals
    async_to_sync(channel_layer.group_send)(
        f'goals_{user_id}',
        {'type': 'goal_update', 'data': {
            'type': 'goal_update',
            'event_type': 'donation',
            'increment': data['amount'],
            'currency': data['currency'],
        }}
    )
    
    # Send to labels - same format as alerts so handleEvent() works
    async_to_sync(channel_layer.group_send)(
        f'labels_{user_id}',
        {'type': 'label_update', 'data': {
            'type': 'donation',
            'event_type': 'donation',
            'platform': 'donation',
            'event_data': {
                'username': data['name'],
                'amount': data['amount'],  # raw number for parsing
                'formatted_amount': data['formatted_amount'],
                'message': data['message'],
            },
        }}
    )


@csrf_exempt
def donation_history(request):
    """Get donation history"""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    donations = Donation.objects.filter(streamer=user, status='completed').order_by('-created_at')[:50]
    
    return JsonResponse({
        'donations': [{
            'id': d.id,
            'donor_name': d.donor_name,
            'amount': float(d.amount),
            'currency': d.currency,
            'message': d.message,
            'created_at': d.created_at.isoformat(),
        } for d in donations]
    })

@csrf_exempt
@require_http_methods(["POST"])
def clear_donation_history(request):
    """Clear recent donation list"""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    deleted_count, _ = Donation.objects.filter(streamer=user).delete()
    return JsonResponse({'cleared': True, 'count': deleted_count})