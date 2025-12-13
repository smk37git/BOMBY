"""
Stripe Donations/Tipping System for FuzeOBS
"""
import json
import stripe
from decimal import Decimal
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from django.conf import settings
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import DonationSettings, Donation
from .views import get_user_from_token

stripe.api_key = settings.STRIPE_SECRET_KEY
SITE_URL = 'https://bomby.us'


@csrf_exempt
@require_http_methods(["GET", "POST"])
def donation_settings(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    from django.db import models
    ds, _ = DonationSettings.objects.get_or_create(
        user=user,
        defaults={
            'page_title': f'Support {user.username}!',
            'page_message': 'Thanks for supporting the stream!',
        }
    )
    
    if request.method == 'GET':
        stripe_connected = False
        stripe_email = ''
        if ds.stripe_account_id:
            try:
                account = stripe.Account.retrieve(ds.stripe_account_id)
                stripe_connected = account.charges_enabled and account.payouts_enabled
                stripe_email = account.email or ''
            except:
                pass
        
        total = Donation.objects.filter(streamer=user, status='completed').aggregate(
            total=models.Sum('amount')
        )['total'] or 0
        
        return JsonResponse({
            'stripe_connected': stripe_connected,
            'stripe_email': stripe_email,
            'donation_url': f'{SITE_URL}/fuzeobs/donate/{ds.donation_token}' if stripe_connected else '',
            'min_amount': float(ds.min_amount),
            'suggested_amounts': ds.suggested_amounts,
            'currency': ds.currency,
            'page_title': ds.page_title,
            'page_message': ds.page_message,
            'show_recent_donations': ds.show_recent_donations,
            'total_received': float(total),
        })
    
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
def stripe_connect(request):
    import traceback
    import sys
    
    try:
        auth = request.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        
        user = get_user_from_token(auth.replace('Bearer ', ''))
        if not user:
            return JsonResponse({'error': 'Invalid token'}, status=401)
        
        ds, _ = DonationSettings.objects.get_or_create(user=user)
        
        if not ds.stripe_account_id:
            account = stripe.Account.create(
                type="express",
                email=user.email,
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                metadata={"fuzeobs_user_id": str(user.id), "username": user.username}
            )
            ds.stripe_account_id = account.id
            ds.save()
        
        account_link = stripe.AccountLink.create(
            account=ds.stripe_account_id,
            refresh_url=f"{SITE_URL}/fuzeobs/donations/stripe/refresh",
            return_url=f"{SITE_URL}/fuzeobs/donations/stripe/complete",
            type="account_onboarding",
        )
        
        return JsonResponse({'url': account_link.url})
    except Exception as e:
        print(f"STRIPE CONNECT ERROR: {e}")
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def stripe_connect_refresh(request):
    return HttpResponse('''
        <html><body style="background:#000;color:#fff;font-family:sans-serif;text-align:center;padding-top:100px;">
        <h2>Session expired</h2>
        <p>Please try connecting again from the app.</p>
        </body></html>
    ''')


@csrf_exempt
def stripe_connect_complete(request):
    return HttpResponse('''
        <html><body style="background:#000;color:#fff;font-family:sans-serif;text-align:center;padding-top:100px;">
        <h2>✓ Stripe Connected!</h2>
        <p>You can close this window.</p>
        <script>setTimeout(()=>window.close(), 2000);</script>
        </body></html>
    ''')


@csrf_exempt
@require_http_methods(["GET"])
def stripe_connect_status(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    try:
        ds = DonationSettings.objects.get(user=user)
        if not ds.stripe_account_id:
            return JsonResponse({'connected': False, 'onboarding_complete': False})
        
        account = stripe.Account.retrieve(ds.stripe_account_id)
        return JsonResponse({
            'connected': True,
            'onboarding_complete': account.charges_enabled and account.payouts_enabled,
            'charges_enabled': account.charges_enabled,
            'payouts_enabled': account.payouts_enabled,
        })
    except:
        return JsonResponse({'connected': False, 'onboarding_complete': False})


@csrf_exempt
@require_http_methods(["POST"])
def stripe_disconnect(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    DonationSettings.objects.filter(user=user).update(stripe_account_id='')
    return JsonResponse({'disconnected': True})


@csrf_exempt
@require_http_methods(["GET"])
def stripe_dashboard(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    try:
        ds = DonationSettings.objects.get(user=user)
        if not ds.stripe_account_id:
            return JsonResponse({'error': 'Not connected'}, status=400)
        
        login_link = stripe.Account.create_login_link(ds.stripe_account_id)
        return JsonResponse({'url': login_link.url})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def donation_page(request, token):
    try:
        ds = DonationSettings.objects.select_related('user').get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return HttpResponse('Not found', status=404)
    
    if not ds.stripe_account_id:
        return HttpResponse('Donations not configured', status=400)
    
    recent_donations = []
    if ds.show_recent_donations:
        recent_donations = list(Donation.objects.filter(
            streamer=ds.user, status='completed'
        ).order_by('-created_at')[:5].values('donor_name', 'amount', 'currency'))
    
    return render(request, 'FUZEOBS/donation_page.html', {
        'page_title': ds.page_title,
        'page_message': ds.page_message,
        'streamer': ds.user.username,
        'min_amount': ds.min_amount,
        'suggested_amounts': ds.suggested_amounts,
        'currency': ds.currency,
        'recent_donations': recent_donations,
        'token': token,
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
    })


@csrf_exempt
@require_http_methods(["POST"])
def create_payment_intent(request, token):
    try:
        ds = DonationSettings.objects.select_related('user').get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
    if not ds.stripe_account_id:
        return JsonResponse({'error': 'Donations not configured'}, status=400)
    
    try:
        data = json.loads(request.body)
        amount = Decimal(str(data.get('amount', 0)))
        donor_name = data.get('name', 'Anonymous')[:100]
        message = data.get('message', '')[:500]
        
        if amount < ds.min_amount:
            return JsonResponse({'error': f'Minimum is {ds.min_amount} {ds.currency}'}, status=400)
        
        amount_cents = int(amount * 100)
        platform_fee = int(amount_cents * 0.025)
        
        donation = Donation.objects.create(
            streamer=ds.user,
            donor_name=donor_name,
            message=message,
            amount=amount,
            currency=ds.currency,
            status='pending',
        )
        
        payment_intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=ds.currency.lower(),
            application_fee_amount=platform_fee,
            transfer_data={'destination': ds.stripe_account_id},
            metadata={
                'donation_id': str(donation.id),
                'donor_name': donor_name,
                'streamer_id': str(ds.user.id),
                'streamer': ds.user.username,
            },
            description=f"Donation to {ds.user.username}",
        )
        
        donation.stripe_payment_intent = payment_intent.id
        donation.save()
        
        return JsonResponse({
            'client_secret': payment_intent.client_secret,
            'donation_id': str(donation.id),
        })
        
    except stripe.error.StripeError as e:
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'error': 'Payment failed'}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def confirm_donation(request, token):
    try:
        ds = DonationSettings.objects.select_related('user').get(donation_token=token)
    except DonationSettings.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
    data = json.loads(request.body)
    payment_intent_id = data.get('payment_intent')
    
    if not payment_intent_id:
        return JsonResponse({'error': 'Missing payment_intent'}, status=400)
    
    try:
        pi = stripe.PaymentIntent.retrieve(payment_intent_id)
        if pi.status != 'succeeded':
            return JsonResponse({'error': 'Payment not completed'}, status=400)
        
        donation_id = pi.metadata.get('donation_id')
        donation = Donation.objects.get(id=donation_id, streamer=ds.user)
        
        if donation.status == 'completed':
            return JsonResponse({'success': True})
        
        donation.status = 'completed'
        donation.save()
        
        trigger_donation_alert(ds.user.id, {
            'type': 'donation',
            'name': donation.donor_name,
            'amount': float(donation.amount),
            'currency': donation.currency,
            'message': donation.message,
            'formatted_amount': f'{donation.currency} {donation.amount:.2f}',
        })
        
        return JsonResponse({'success': True})
        
    except Donation.DoesNotExist:
        return JsonResponse({'error': 'Donation not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def stripe_donation_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    webhook_secret = getattr(settings, 'STRIPE_DONATION_WEBHOOK_SECRET', settings.STRIPE_WEBHOOK_SECRET)
    
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    if event['type'] == 'payment_intent.succeeded':
        pi = event['data']['object']
        donation_id = pi['metadata'].get('donation_id')
        
        if donation_id:
            try:
                donation = Donation.objects.get(id=donation_id)
                if donation.status != 'completed':
                    donation.status = 'completed'
                    donation.save()
                    
                    trigger_donation_alert(donation.streamer.id, {
                        'type': 'donation',
                        'name': donation.donor_name,
                        'amount': float(donation.amount),
                        'currency': donation.currency,
                        'message': donation.message,
                        'formatted_amount': f'{donation.currency} {donation.amount:.2f}',
                    })
            except Donation.DoesNotExist:
                pass
    
    elif event['type'] == 'payment_intent.payment_failed':
        pi = event['data']['object']
        donation_id = pi['metadata'].get('donation_id')
        if donation_id:
            Donation.objects.filter(id=donation_id).update(status='failed')
    
    return JsonResponse({'received': True})


def trigger_donation_alert(user_id, data):
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
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    user = get_user_from_token(auth.replace('Bearer ', ''))
    if not user:
        return JsonResponse({'error': 'Invalid token'}, status=401)
    
    donations = Donation.objects.filter(streamer=user, status='completed').order_by('-created_at')[:50]
    
    return JsonResponse({
        'donations': [{
            'id': str(d.id),
            'donor_name': d.donor_name,
            'amount': float(d.amount),
            'currency': d.currency,
            'message': d.message,
            'created_at': d.created_at.isoformat(),
        } for d in donations]
    })