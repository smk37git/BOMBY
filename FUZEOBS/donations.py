"""
Donations/Tipping System for FuzeOBS
Handles PayPal OAuth, donation page, and alert triggering
"""
import os
import json
import secrets
import requests
from decimal import Decimal
from datetime import datetime
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

PAYPAL_BASE = 'https://api-m.paypal.com' if not getattr(settings, 'PAYPAL_SANDBOX_MODE', False) else 'https://api-m.sandbox.paypal.com'
PAYPAL_CLIENT_ID = os.environ.get('PAYPAL_DONATE_CLIENT_ID', settings.PAYPAL_CLIENT_ID)
PAYPAL_SECRET = os.environ.get('PAYPAL_DONATE_SECRET', settings.PAYPAL_SECRET)


def get_paypal_access_token():
    """Get PayPal OAuth access token for API calls"""
    resp = requests.post(
        f'{PAYPAL_BASE}/v1/oauth2/token',
        auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        data={'grant_type': 'client_credentials'},
        headers={'Accept': 'application/json'}
    )
    if resp.status_code == 200:
        return resp.json().get('access_token')
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
        
        return JsonResponse({
            'paypal_connected': bool(ds.paypal_email),
            'paypal_email': ds.paypal_email or '',
            'donation_url': f'https://bomby.us/fuzeobs/donate/{ds.donation_token}' if ds.paypal_email else '',
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


@csrf_exempt
@require_http_methods(["POST"])
def paypal_connect(request):
    """Initiate PayPal OAuth connection"""
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    ds, _ = DonationSettings.objects.get_or_create(user=user)
    
    # Generate state for OAuth
    state = secrets.token_urlsafe(32)
    ds.oauth_state = state
    ds.save()
    
    # PayPal OAuth URL
    redirect_uri = 'https://bomby.us/fuzeobs/donations/paypal/callback'
    scopes = 'openid email https://uri.paypal.com/services/paypalattributes'
    
    auth_url = (
        f'{PAYPAL_BASE.replace("api-m", "www")}/signin/authorize'
        f'?client_id={PAYPAL_CLIENT_ID}'
        f'&response_type=code'
        f'&scope={scopes}'
        f'&redirect_uri={redirect_uri}'
        f'&state={state}'
    )
    
    return JsonResponse({'auth_url': auth_url})


@csrf_exempt
def paypal_callback(request):
    """Handle PayPal OAuth callback"""
    code = request.GET.get('code')
    state = request.GET.get('state')
    
    if not code or not state:
        return HttpResponse('<script>window.close();</script>')
    
    try:
        ds = DonationSettings.objects.get(oauth_state=state)
    except DonationSettings.DoesNotExist:
        return HttpResponse('<script>alert("Invalid state"); window.close();</script>')
    
    # Exchange code for tokens
    redirect_uri = 'https://bomby.us/fuzeobs/donations/paypal/callback'
    resp = requests.post(
        f'{PAYPAL_BASE}/v1/oauth2/token',
        auth=(PAYPAL_CLIENT_ID, PAYPAL_SECRET),
        data={
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': redirect_uri,
        },
        headers={'Accept': 'application/json'}
    )
    
    if resp.status_code != 200:
        return HttpResponse('<script>alert("Failed to connect"); window.close();</script>')
    
    tokens = resp.json()
    access_token = tokens.get('access_token')
    
    # Get user info
    user_resp = requests.get(
        f'{PAYPAL_BASE}/v1/identity/oauth2/userinfo?schema=paypalv1.1',
        headers={'Authorization': f'Bearer {access_token}'}
    )
    
    if user_resp.status_code == 200:
        user_info = user_resp.json()
        emails = user_info.get('emails', [])
        primary_email = next((e['value'] for e in emails if e.get('primary')), emails[0]['value'] if emails else '')
        
        ds.paypal_email = primary_email
        ds.paypal_merchant_id = user_info.get('payer_id', '')
        ds.oauth_state = ''
        ds.save()
    
    return HttpResponse('''
        <html><body style="background:#000;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
        <div style="text-align:center;">
            <h2>✓ PayPal Connected!</h2>
            <p>You can close this window.</p>
            <script>setTimeout(()=>window.close(), 2000);</script>
        </div>
        </body></html>
    ''')


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
    """Public donation page for viewers"""
    try:
        ds = DonationSettings.objects.select_related('user').get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return HttpResponse('Donation page not found', status=404)
    
    if not ds.paypal_email:
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
        'paypal_client_id': PAYPAL_CLIENT_ID,
    }
    
    return render(request, 'FUZEOBS/donation_page.html', context)


@csrf_exempt
@require_http_methods(["POST"])
def create_donation_order(request, token):
    """Create PayPal order for donation"""
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
    
    access_token = get_paypal_access_token()
    if not access_token:
        return JsonResponse({'error': 'Payment service unavailable'}, status=500)
    
    # Create PayPal order
    order_resp = requests.post(
        f'{PAYPAL_BASE}/v2/checkout/orders',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        },
        json={
            'intent': 'CAPTURE',
            'purchase_units': [{
                'amount': {
                    'currency_code': ds.currency,
                    'value': str(amount),
                },
                'description': f'Donation to {ds.user.username}',
                'payee': {
                    'email_address': ds.paypal_email,
                },
            }],
            'application_context': {
                'brand_name': f'{ds.user.username} - FuzeOBS',
                'shipping_preference': 'NO_SHIPPING',
            }
        }
    )
    
    if order_resp.status_code not in (200, 201):
        return JsonResponse({'error': 'Failed to create order'}, status=500)
    
    order = order_resp.json()
    
    # Save pending donation
    Donation.objects.create(
        streamer=ds.user,
        paypal_order_id=order['id'],
        donor_name=donor_name,
        message=message,
        amount=amount,
        currency=ds.currency,
        status='pending',
    )
    
    return JsonResponse({'order_id': order['id']})


@csrf_exempt
@require_http_methods(["POST"])
def capture_donation(request, token):
    """Capture PayPal payment and trigger alerts"""
    try:
        ds = DonationSettings.objects.select_related('user').get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
    data = json.loads(request.body)
    order_id = data.get('order_id')
    
    try:
        donation = Donation.objects.get(paypal_order_id=order_id, streamer=ds.user)
    except Donation.DoesNotExist:
        return JsonResponse({'error': 'Donation not found'}, status=404)
    
    access_token = get_paypal_access_token()
    if not access_token:
        return JsonResponse({'error': 'Payment service unavailable'}, status=500)
    
    # Capture payment
    capture_resp = requests.post(
        f'{PAYPAL_BASE}/v2/checkout/orders/{order_id}/capture',
        headers={
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
    )
    
    if capture_resp.status_code not in (200, 201):
        donation.status = 'failed'
        donation.save()
        return JsonResponse({'error': 'Payment capture failed'}, status=500)
    
    capture = capture_resp.json()
    
    if capture.get('status') == 'COMPLETED':
        donation.status = 'completed'
        donation.paypal_capture_id = capture.get('id', '')
        donation.save()
        
        # Trigger alerts to all widgets
        trigger_donation_alert(ds.user.id, {
            'type': 'donation',
            'name': donation.donor_name,
            'amount': float(donation.amount),
            'currency': donation.currency,
            'message': donation.message,
            'formatted_amount': f'{donation.currency} {donation.amount:.2f}',
        })
        
        return JsonResponse({'success': True})
    
    donation.status = 'failed'
    donation.save()
    return JsonResponse({'error': 'Payment not completed'}, status=500)


def trigger_donation_alert(user_id, data):
    """Send donation alert to all applicable widgets"""
    channel_layer = get_channel_layer()
    
    # Format for Event List and Alert Box (consistent structure)
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
        # Flat fields for Alert Box compatibility
        'name': data['name'],
        'amount': data['amount'],
        'currency': data['currency'],
        'message': data['message'],
        'formatted_amount': data['formatted_amount'],
    }
    
    # Alert Box + Event List - send to all platform channels
    for platform in ['twitch', 'youtube', 'kick', 'facebook', 'tiktok']:
        async_to_sync(channel_layer.group_send)(
            f'alerts_{user_id}_{platform}',
            {'type': 'alert_event', 'data': alert_data}
        )
    
    # Goal Bar - update progress
    async_to_sync(channel_layer.group_send)(
        f'goals_{user_id}',
        {'type': 'goal_update', 'data': {
            'type': 'donation',
            'amount': data['amount'],
            'currency': data['currency'],
        }}
    )
    
    # Labels - update latest donation
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
    """Get donation history for streamer"""
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