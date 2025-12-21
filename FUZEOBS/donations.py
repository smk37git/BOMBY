"""
Donations/Tipping System for FuzeOBS
Uses PayPal OAuth to get Payer ID, then Donate SDK for payments
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

logger = logging.getLogger(__name__)

# PayPal Configuration
PAYPAL_SANDBOX_MODE = getattr(settings, 'PAYPAL_SANDBOX_MODE', False)
PAYPAL_BASE = 'https://api-m.sandbox.paypal.com' if PAYPAL_SANDBOX_MODE else 'https://api-m.paypal.com'
PAYPAL_WEB_BASE = 'https://www.sandbox.paypal.com' if PAYPAL_SANDBOX_MODE else 'https://www.paypal.com'
PAYPAL_CLIENT_ID = getattr(settings, 'PAYPAL_CLIENT_ID', '') or ''
PAYPAL_SECRET = getattr(settings, 'PAYPAL_SECRET', '') or ''


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
            
            # Connected if we have payer_id or email
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
            })
        
        # POST - update settings
        data = json.loads(request.body)
        ds.min_amount = data.get('min_amount', ds.min_amount)
        ds.currency = data.get('currency', ds.currency)
        ds.page_title = data.get('page_title', ds.page_title)
        ds.page_message = data.get('page_message', ds.page_message)
        ds.show_recent_donations = data.get('show_recent_donations', ds.show_recent_donations)
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
        ds.oauth_state = state
        ds.save()
        
        redirect_uri = 'https://bomby.us/fuzeobs/donations/paypal/callback'
        
        # Request openid + paypalattributes for payer_id
        auth_url = (
            f'{PAYPAL_WEB_BASE}/signin/authorize'
            f'?client_id={PAYPAL_CLIENT_ID}'
            f'&response_type=code'
            f'&scope=openid'
            f'&redirect_uri={redirect_uri}'
            f'&state={state}'
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
        ds = DonationSettings.objects.get(oauth_state=state)
    except DonationSettings.DoesNotExist:
        return HttpResponse('<script>alert("Invalid state"); window.close();</script>')
    
    redirect_uri = 'https://bomby.us/fuzeobs/donations/paypal/callback'
    
    try:
        # Exchange code for tokens
        resp = requests.post(
            f'{PAYPAL_BASE}/v1/oauth2/token',
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
        
        logger.info(f"Token keys: {list(tokens.keys())}")
        
        payer_id = None
        email = None
        
        # Try to decode id_token if present
        id_token = tokens.get('id_token')
        if id_token:
            try:
                payload = id_token.split('.')[1]
                payload += '=' * (4 - len(payload) % 4)
                decoded = json.loads(base64.urlsafe_b64decode(payload))
                logger.info(f"id_token claims: {list(decoded.keys())}")
                payer_id = decoded.get('payer_id') or decoded.get('sub')
                email = decoded.get('email')
            except Exception as e:
                logger.error(f"id_token decode error: {e}")
        
        # Try userinfo endpoint
        if not payer_id:
            user_resp = requests.get(
                f'{PAYPAL_BASE}/v1/identity/oauth2/userinfo?schema=paypalv1.1',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=30
            )
            logger.info(f"Userinfo response: {user_resp.status_code}")
            logger.info(f"Userinfo body: {user_resp.text[:500]}")
            
            if user_resp.status_code == 200:
                user_info = user_resp.json()
                payer_id = user_info.get('payer_id') or user_info.get('user_id')
                emails = user_info.get('emails', [])
                if emails:
                    email = next((e['value'] for e in emails if e.get('primary')), emails[0].get('value'))
        
        # Try openid userinfo
        if not payer_id:
            user_resp2 = requests.get(
                f'{PAYPAL_BASE}/v1/identity/openidconnect/userinfo?schema=openid',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=30
            )
            logger.info(f"OpenID userinfo response: {user_resp2.status_code}")
            logger.info(f"OpenID userinfo body: {user_resp2.text[:500]}")
            
            if user_resp2.status_code == 200:
                user_info2 = user_resp2.json()
                payer_id = user_info2.get('payer_id') or user_info2.get('user_id') or user_info2.get('sub')
                if not email:
                    email = user_info2.get('email')
        
        if payer_id or email:
            ds.paypal_merchant_id = payer_id or ''
            ds.paypal_email = email or ''
            ds.oauth_state = ''
            ds.save()
            
            logger.info(f"PayPal connected: payer_id={payer_id}, email={email}")
            
            return render(request, 'FUZEOBS/paypal_connected.html', {'success': True})
        else:
            logger.error("Could not get payer_id or email from PayPal")
            return render(request, 'FUZEOBS/paypal_connected.html', {
                'success': False,
                'error': 'Could not retrieve PayPal account info. Please enable "PayPal account ID" in your app settings.'
            })
        
    except Exception as e:
        logger.error(f"PayPal callback exception: {e}")
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
    """Public donation page using PayPal Donate SDK"""
    try:
        ds = DonationSettings.objects.select_related('user').get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return HttpResponse('Donation page not found', status=404)
    
    # Need either payer_id or email for Donate SDK
    business_id = ds.paypal_merchant_id or ds.paypal_email
    if not business_id:
        return HttpResponse('Donations not configured', status=404)
    
    recent_donations = []
    if ds.show_recent_donations:
        recent_donations = list(
            Donation.objects.filter(streamer=ds.user, status='completed')
            .order_by('-created_at')[:5]
            .values('donor_name', 'amount', 'currency', 'created_at')
        )
    
    context = {
        'streamer': ds.user.username,
        'page_title': ds.page_title,
        'page_message': ds.page_message,
        'min_amount': float(ds.min_amount),
        'suggested_amounts': ds.suggested_amounts,
        'currency': ds.currency,
        'recent_donations': recent_donations,
        'token': token,
        'business_id': business_id,
        'paypal_env': 'sandbox' if PAYPAL_SANDBOX_MODE else 'production',
    }
    
    return render(request, 'FUZEOBS/donation_page.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def create_donation_order(request, token):
    """Record donation intent (Donate SDK handles actual payment)"""
    try:
        ds = DonationSettings.objects.select_related('user').get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
    data = json.loads(request.body)
    amount = Decimal(str(data.get('amount', 0)))
    donor_name = data.get('name', 'Anonymous')[:100]
    message = data.get('message', '')[:500]
    
    if amount < ds.min_amount:
        return JsonResponse({'error': f'Minimum donation is {ds.min_amount} {ds.currency}'}, status=400)
    
    # Create pending donation record
    donation = Donation.objects.create(
        streamer=ds.user,
        paypal_order_id=f'pending_{secrets.token_hex(8)}',
        donor_name=donor_name,
        message=message,
        amount=amount,
        currency=ds.currency,
        status='pending',
    )
    
    return JsonResponse({'donation_id': donation.id})


@csrf_exempt
@require_http_methods(["POST"])
def capture_donation(request, token):
    """Mark donation as complete and trigger alerts (called after Donate SDK success)"""
    try:
        ds = DonationSettings.objects.select_related('user').get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
    data = json.loads(request.body)
    donation_id = data.get('donation_id')
    tx_id = data.get('tx')  # Transaction ID from Donate SDK
    
    try:
        donation = Donation.objects.get(id=donation_id, streamer=ds.user)
    except Donation.DoesNotExist:
        return JsonResponse({'error': 'Donation not found'}, status=404)
    
    # Update donation record
    donation.status = 'completed'
    if tx_id:
        donation.paypal_order_id = tx_id
    donation.save()
    
    # Trigger alerts
    trigger_donation_alert(ds.user.id, {
        'type': 'donation',
        'name': donation.donor_name,
        'amount': float(donation.amount),
        'currency': donation.currency,
        'message': donation.message,
        'formatted_amount': f'{donation.currency} {donation.amount:.2f}',
    })
    
    return JsonResponse({'success': True})


def trigger_donation_alert(user_id, data):
    """Send donation alert to widgets"""
    channel_layer = get_channel_layer()
    
    alert_data = {
        'type': 'donation',
        'event_type': 'donation',
        'platform': 'donation',
        'event_data': {
            'username': data['name'],
            'amount': data['formatted_amount'],
            'raw_amount': data['amount'],
            'currency': data['currency'],
            'message': data['message'],
        },
        'name': data['name'],
        'amount': data['amount'],
        'currency': data['currency'],
        'message': data['message'],
        'formatted_amount': data['formatted_amount'],
    }
    
    for platform in ['twitch', 'youtube', 'kick', 'facebook', 'tiktok']:
        async_to_sync(channel_layer.group_send)(
            f'alerts_{user_id}_{platform}',
            {'type': 'alert_event', 'data': alert_data}
        )
    
    async_to_sync(channel_layer.group_send)(
        f'goals_{user_id}',
        {'type': 'goal_update', 'data': {
            'type': 'donation',
            'amount': data['amount'],
            'currency': data['currency'],
        }}
    )
    
    async_to_sync(channel_layer.group_send)(
        f'labels_{user_id}',
        {'type': 'label_update', 'data': {
            'label_type': 'latest_donation',
            'name': data['name'],
            'amount': data['formatted_amount'],
            'message': data['message'],
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