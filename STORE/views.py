from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from .models import Order, OrderForm, OrderMessage, OrderAttachment, Review, Product, Invoice
from .forms import OrderQuestionsForm, MessageForm, ReviewForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
from ACCOUNTS.models import Message, Conversation
import json
from django.http import HttpResponse
from google.cloud import storage
from datetime import datetime
from .models import StreamAsset, UserAsset, AssetVersion, AssetMedia
from .utils.email_utils import (
    send_pending_order_email,
    send_in_progress_order_email, 
    send_completed_order_email,
    send_invoice_email
)
import os
import uuid
from django.conf import settings
from django.db import connection
from django.db.models import Count, Avg, Sum, Q, F
from datetime import timedelta
from .models import PageView, ProductInteraction, Donation
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from decimal import Decimal
from .models import DiscountCode

def store(request):
    products = [
        Product.objects.get(id=1),  # Basic Package
        Product.objects.get(id=2),  # Standard Package
        Product.objects.get(id=3),  # Premium Package
        Product.objects.get(id=4),  # Stream Store
        Product.objects.get(id=5),  # Basic Website
        Product.objects.get(id=6),  # E-commerce Website
        Product.objects.get(id=7),  # Custom Project
    ]
    
    # Check if user has an active discount code
    discount_code = None
    if request.user.is_authenticated:
        discount_code = DiscountCode.objects.filter(
            user=request.user,
            is_used=False
        ).first()
    
    # Explicitly disable browser caching
    response = render(request, 'STORE/store.html', {
        'products': products,
        'discount_code': discount_code
    })
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

# Stream setup service views
def basic_package(request):
    product = Product.objects.get(id=1)
    product_reviews = get_all_reviews()
    
    context = {
        'product': product,
        'product_reviews': product_reviews,
    }
    
    response = render(request, 'STORE/basic_package.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def standard_package(request):
    product = Product.objects.get(id=2)
    product_reviews = get_all_reviews()
    
    response = render(request, 'STORE/standard_package.html', {
        'product': product,
        'product_reviews': product_reviews
    })
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def premium_package(request):
    product = Product.objects.get(id=3)
    product_reviews = get_all_reviews()
    
    response = render(request, 'STORE/premium_package.html', {
        'product': product,
        'product_reviews': product_reviews
    })
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def donation_page(request):
    """View for custom donation amount"""
    # Check if user cancelled a payment
    cancelled = request.GET.get('cancelled', False)
    if cancelled:
        messages.info(request, "Payment was cancelled. You can try again when you're ready.")
    
    return render(request, 'STORE/donation_page.html', {
        'paypal_client_id': settings.PAYPAL_CLIENT_ID,
    })

def donation_payment(request):
    """Handle processing a donation with custom amount"""
    if request.method == 'POST':
        amount = request.POST.get('amount')
        
        try:
            # Validate amount is a positive number
            amount = float(amount)
            if amount <= 0:
                raise ValueError("Amount must be positive")
                
            # Format with 2 decimal places
            amount = "{:.2f}".format(amount)
                
            # Create donation object (not saving yet)
            donation = Donation(amount=amount)
            if request.user.is_authenticated:
                donation.user = request.user
                
            # Redirect to payment processing
            return render(request, 'STORE/donation_payment.html', {
                'amount': amount,
                'paypal_client_id': settings.PAYPAL_CLIENT_ID,
                'donation_id': str(uuid.uuid4())  # Generate a temporary ID
            })
                
        except (ValueError, TypeError) as e:
            messages.error(request, f"Invalid donation amount: {str(e)}")
            
    return redirect('STORE:donation_page')

def donation_success(request):
    """Handle successful donation and promote to supporter"""
    donation_id = request.GET.get('donation_id')
    payment_id = request.GET.get('paymentId')
    amount = request.GET.get('amount')
    
    try:
        # Verify payment with PayPal
        is_verified, payment_data = verify_paypal_payment(payment_id)
        
        if not is_verified:
            messages.error(request, "Payment verification failed. Please contact support.")
            return redirect('STORE:donation_page')
        
        # Create and save donation record
        donation = Donation(
            amount=amount,
            payment_id=payment_id,
            is_paid=is_verified
        )
        
        if request.user.is_authenticated:
            donation.user = request.user
            
            # Promote user to supporter if donation is $10 or more
            if float(amount) >= 10 and not request.user.is_supporter and hasattr(request.user, 'promote_to_supporter'):
                request.user.promote_to_supporter()
        
        donation.save()
        
        # Send receipt email
        from .utils.email_utils import send_donation_receipt
        try:
            send_donation_receipt(request, donation)
        except Exception as e:
            print(f"Error sending donation receipt: {e}")
        
        # Show the payment success page instead of redirecting
        return render(request, 'STORE/payment_success.html', {
            'donation': donation,
            'is_donation': True
        })
            
    except Exception as e:
        print(f"Error processing donation: {str(e)}")
        messages.error(request, "There was an error processing your donation payment.")
        
    return redirect('STORE:store')

def stream_store(request):
    """Stream store view with access control"""
    # Check if user can access (supporter, client, admin)
    if request.user.is_authenticated and user_can_access_stream_store(request.user):
        # User has access, show the actual store    
        assets = StreamAsset.objects.filter(is_active=True)
        return render(request, 'STORE/stream_store.html', {'assets': assets})
    else:
        # Show the purchase page (not purchase history)
        product = Product.objects.get(id=4)
        product_reviews = get_all_reviews()
        return render(request, 'STORE/stream_store_purchase.html', {
            'product': product,
            'product_reviews': product_reviews
        })

def basic_website(request):
    product = Product.objects.get(id=5)
    product_reviews = get_all_reviews()
    
    response = render(request, 'STORE/basic_website.html', {
        'product': product,
        'product_reviews': product_reviews
    })
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def ecommerce_website(request):
    product = Product.objects.get(id=6)
    product_reviews = get_all_reviews()
    
    response = render(request, 'STORE/ecommerce_website.html', {
        'product': product,
        'product_reviews': product_reviews
    })
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate' 
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def custom_project(request):
    product = Product.objects.get(id=7)
    product_reviews = get_all_reviews()
    
    response = render(request, 'STORE/custom_project.html', {
        'product': product,
        'product_reviews': product_reviews
    })
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

# Get Reviews
def get_all_reviews():
    """Helper function to get all reviews across products"""
    return Review.objects.all().select_related('order__user', 'order__product')

# Message about Product
@login_required
def message_general(request):
    # Get first staff user
    staff_user = get_user_model().objects.filter(is_staff=True).first()
    
    if not staff_user:
        messages.error(request, "No staff members available to message.")
        return redirect('STORE:store')
    
    # Get or create conversation
    conversation = Conversation.objects.filter(
        participants=request.user
    ).filter(
        participants=staff_user
    ).first()
    
    if not conversation:
        conversation = Conversation.objects.create()
        conversation.participants.add(request.user, staff_user)
        conversation.save()
    
    # Create a general message
    message = Message.objects.create(
        sender=request.user,
        recipient=staff_user,
        content="I'm interested in discussing your stream setup!",
        conversation=conversation
    )
    
    # Update conversation's last_message
    conversation.last_message = message
    conversation.save()
    
    return redirect('ACCOUNTS:conversation', user_id=staff_user.id)

@login_required
def start_message_from_product(request, product_id):
    # Get product info
    product = get_object_or_404(Product, id=product_id)
    
    # Get first staff user
    staff_user = get_user_model().objects.filter(is_staff=True).first()
    
    if not staff_user:
        messages.error(request, "No staff members available to message.")
        return redirect('STORE:store')
    
    # Get or create conversation
    conversation = Conversation.objects.filter(
        participants=request.user
    ).filter(
        participants=staff_user
    ).first()
    
    if not conversation:
        conversation = Conversation.objects.create()
        conversation.participants.add(request.user, staff_user)
        conversation.save()
    
    # Create a message with product info embedded - include price now
    message = Message.objects.create(
        sender=request.user,
        recipient=staff_user,
        content=f"I'm interested in discussing about the {product.name}!",
        conversation=conversation
    )
    
    # Update conversation's last_message
    conversation.last_message = message
    conversation.save()
    
    return redirect('ACCOUNTS:conversation', user_id=staff_user.id)

@login_required
def check_new_order_messages(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        
        # Verify permission - only owner or staff can view
        if request.user != order.user and not request.user.is_staff:
            return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
        
        # Get timestamp from query param
        since = request.GET.get('since', None)
        if not since:
            return JsonResponse({'status': 'success', 'new_messages': []})
        
        try:
            # Parse ISO format date with timezone
            since_datetime = datetime.fromisoformat(since.replace('Z', '+00:00'))
            # Add a small buffer to avoid duplicates
            since_datetime = since_datetime + timedelta(seconds=1)
            
            # Query for new messages
            new_messages = OrderMessage.objects.filter(
                order=order,
                created_at__gt=since_datetime
            ).exclude(sender=request.user).order_by('created_at')
            
        except ValueError:
            # If date parsing fails, return empty
            return JsonResponse({'status': 'success', 'new_messages': []})
        
        # Format messages for JSON response
        messages_data = []
        for msg in new_messages:
            # Mark as read
            if not msg.is_read and msg.sender != request.user:
                msg.is_read = True
                msg.save()
            
            # Get attachments
            attachments_data = []
            for attachment in msg.attachments.all():
                attachments_data.append({
                    'url': attachment.file.url,
                    'filename': attachment.filename or attachment.file.name.split('/')[-1]
                })
            
            messages_data.append({
                'message': msg.message,
                'created_at': msg.created_at.isoformat(),
                'sender_username': msg.sender.username,
                'avatar_url': msg.sender.profile_picture.url if hasattr(msg.sender, 'profile_picture') and msg.sender.profile_picture else None,
                'is_mine': msg.sender == request.user,
                'attachments': attachments_data
            })
        
        return JsonResponse({
            'status': 'success',
            'new_messages': messages_data
        })
    except Exception as e:
        import traceback
        print(f"Error in check_new_order_messages: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# Orders
def verify_paypal_payment(payment_id):
    """Verify PayPal payment status using PayPal API"""
    import requests
    import os
    import base64
    
    # Get credentials
    client_id = os.environ.get('PAYPAL_CLIENT_ID')
    client_secret = os.environ.get('PAYPAL_SECRET')
    
    # Get OAuth token
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        'Authorization': f'Basic {auth}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    # Get access token
    token_url = "https://api.paypal.com/v1/oauth2/token"
    token_data = "grant_type=client_credentials"
    token_response = requests.post(token_url, headers=headers, data=token_data)
    
    if token_response.status_code != 200:
        return False, "Failed to authenticate with PayPal"
    
    access_token = token_response.json()['access_token']
    
    # Check payment status using v2 API for order capture
    order_url = f"https://api.paypal.com/v2/checkout/orders/{payment_id}"
    order_headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    order_response = requests.get(order_url, headers=order_headers)
    
    if order_response.status_code != 200:
        return False, f"Failed to verify payment status: {order_response.status_code}"
    
    order_data = order_response.json()
    order_status = order_data.get('status', '')
    
    return order_status == 'COMPLETED', order_data

@login_required
def purchase_product(request, product_id):
    """Handle product purchase by redirecting to payment page"""
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    # Just redirect to payment page, no role changes yet
    return redirect('STORE:payment_page', product_id=product_id)

@login_required
def order_form(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    
    # Check if form already exists
    if hasattr(order, 'form'):
        return redirect('STORE:order_details', order_id=order.id)
    
    if request.method == 'POST':
        form = OrderQuestionsForm(request.POST)
        if form.is_valid():
            order_form = form.save(commit=False)
            order_form.order = order
            order_form.save()
            
            # Update order status
            order.status = 'in_progress'
            order.save()
            
            # Send in-progress email
            try:
                send_in_progress_order_email(request, order)
            except Exception as e:
                print(f"Error sending in-progress email: {e}")
            
            messages.success(request, "Thank you for your information! Your order is now in progress.")
            return redirect('STORE:order_details', order_id=order.id)
    else:
        form = OrderQuestionsForm()
    
    return render(request, 'STORE/order_form.html', {'form': form, 'order': order})

@login_required
def order_details(request, order_id):
    # Get the order object
    order = get_object_or_404(Order, id=order_id)
    
    # Redirect Stream Store orders to the stream store
    if order.product_id == 4:  # Stream Store product
        messages.info(request, "Stream Store is an access product, not a traditional order.")
        return redirect('STORE:stream_store')
    
    # Verify permission - only owner or staff can view
    if request.user != order.user and not request.user.is_staff:
        return HttpResponseForbidden("You don't have permission to view this order")
    
    # Handle message form submission
    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                message = form.save(commit=False)
                message.order = order
                message.sender = request.user
                message.save()
                
                # Process attachments
                files = request.FILES.getlist('attachments')
                for file in files:
                    OrderAttachment.objects.create(message=message, file=file)
            
            # Handle AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                attachments_data = []
                for attachment in message.attachments.all():
                    attachments_data.append({
                        'url': attachment.file.url,
                        'filename': attachment.filename
                    })
                return JsonResponse({
                    'status': 'success',
                    'attachments': attachments_data
                })
            
            return redirect('STORE:order_details', order_id=order.id)
    else:
        form = MessageForm()
    
    # Get all messages for this order
    messages_list = OrderMessage.objects.filter(order=order).order_by('created_at')
    
    # Mark messages as read if the current user is the recipient
    if request.user.is_staff:
        # Staff is viewing - mark messages from non-staff as read
        unread_messages = messages_list.filter(sender__is_staff=False, is_read=False)
    else:
        # Customer is viewing - mark messages from staff as read
        unread_messages = messages_list.filter(sender__is_staff=True, is_read=False)
    
    for message in unread_messages:
        message.is_read = True
        message.save()
    
    # Prepare review form if applicable - only for completed orders without reviews
    review_form = None
    if order.status == 'completed' and request.user == order.user:
        review_exists = Review.objects.filter(order=order).exists()
        if not review_exists:
            review_form = ReviewForm()
    
    # Get order review if it exists
    try:
        order_review = Review.objects.get(order=order)
    except Review.DoesNotExist:
        order_review = None
    
    # Get order invoice if it exists
    try:
        order_invoice = Invoice.objects.get(order=order)
    except Invoice.DoesNotExist:
        order_invoice = None
        
    context = {
        'order': order,
        'form': form,
        'messages_list': messages_list,
        'review_form': review_form,
        'order_review': order_review,
        'order_invoice': order_invoice,
    }
    
    return render(request, 'STORE/order_details.html', context)

@login_required
def get_unread_order_messages_count(request):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            if request.user.is_staff:
                # For staff, count unread messages from clients
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT COUNT(*) FROM "STORE_ordermessage" 
                        JOIN "ACCOUNTS_user" ON "STORE_ordermessage"."sender_id" = "ACCOUNTS_user"."id"
                        WHERE "ACCOUNTS_user"."is_staff" = FALSE AND "STORE_ordermessage"."is_read" = FALSE
                    """)
                    unread_count = cursor.fetchone()[0]
            else:
                # For regular users, count unread messages from staff
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT COUNT(*) FROM "STORE_ordermessage"
                        JOIN "ACCOUNTS_user" ON "STORE_ordermessage"."sender_id" = "ACCOUNTS_user"."id" 
                        JOIN "STORE_order" ON "STORE_ordermessage"."order_id" = "STORE_order"."id"
                        WHERE "ACCOUNTS_user"."is_staff" = TRUE AND "STORE_ordermessage"."is_read" = FALSE AND "STORE_order"."user_id" = %s
                    """, [request.user.id])
                    unread_count = cursor.fetchone()[0]
            
            return JsonResponse({'unread_count': unread_count})
        except Exception as e:
            print(f"Error getting unread count: {e}")
            return JsonResponse({'unread_count': 0})
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
def mark_completed(request, order_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("Only staff can complete orders")
    
    order = get_object_or_404(Order, id=order_id)
    order.status = 'completed'
    order.save()
    
    # Send completed order email
    try:
        send_completed_order_email(request, order)
    except Exception as e:
        print(f"Error sending completed order email: {e}")
    
    messages.success(request, "Order has been marked as completed!")
    return redirect('STORE:order_details', order_id=order.id)

@login_required
def submit_review(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user, status='completed')
    
    # Check if review already exists
    if hasattr(order, 'review'):
        messages.error(request, "You have already submitted a review for this order")
        return redirect('STORE:order_details', order_id=order.id)
    
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            try:
                review = form.save(commit=False)
                review.order = order
                review.save()
                messages.success(request, "Thank you for your review!")
            except ValidationError as e:
                messages.error(request, e.message)
        else:
            # Handle validation errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{error}")
    
    return redirect('STORE:order_details', order_id=order.id)

@login_required
def my_orders(request):
    # Get appropriate orders based on user role
    if request.user.is_staff:
        # Staff sees all orders
        orders = Order.objects.all().order_by('-created_at')
        
        # For each order, count unread messages
        for order in orders:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM "STORE_ordermessage"
                    JOIN "ACCOUNTS_user" ON "STORE_ordermessage"."sender_id" = "ACCOUNTS_user"."id"
                    WHERE "STORE_ordermessage"."order_id" = %s 
                    AND "ACCOUNTS_user"."is_staff" = FALSE
                    AND "STORE_ordermessage"."is_read" = FALSE
                """, [order.id])
                unread_count = cursor.fetchone()[0]
            
            order.has_unread_messages = unread_count > 0
            order.unread_message_count = unread_count
    else:
        # Users see their own orders, excluding Stream Store access
        orders = Order.objects.filter(user=request.user)
        
        # For each order, count unread messages
        for order in orders:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM "STORE_ordermessage"
                    JOIN "ACCOUNTS_user" ON "STORE_ordermessage"."sender_id" = "ACCOUNTS_user"."id"
                    WHERE "STORE_ordermessage"."order_id" = %s 
                    AND "ACCOUNTS_user"."is_staff" = TRUE
                    AND "STORE_ordermessage"."is_read" = FALSE
                """, [order.id])
                unread_count = cursor.fetchone()[0]
            
            order.has_unread_messages = unread_count > 0
            order.unread_message_count = unread_count
    
    # Check if user has stream store access
    stream_store_access = user_can_access_stream_store(request.user)
    
    # Get stream store purchase for display
    stream_purchase = None
    if not request.user.is_staff:
        stream_purchase = Order.objects.filter(
            user=request.user, 
            product_id=4
        ).order_by('-created_at').first()
    
    return render(request, 'STORE/my_orders.html', {
        'orders': orders,
        'stream_store_access': stream_store_access,
        'stream_purchase': stream_purchase
    })

# Stream Store Views
def user_can_access_stream_store(user):
    """Check if user can access stream store"""
    if not user.is_authenticated:
        return False
        
    # Clients and admins always have access
    if user.is_client or user.is_admin_user:
        return True
        
    # Check if user has purchased stream store access
    has_stream_store = Order.objects.filter(
        user=user,
        product_id=4,  # Stream Store product ID
        status='completed',
        is_paid=True
    ).exists()
    
    return has_stream_store

@login_required
def stream_asset_detail(request, asset_id):
    """Stream asset detail page with support for multiple media files and versions"""
    if not user_can_access_stream_store(request.user):
        messages.error(request, "This area requires client or supporter status")
        return redirect('STORE:stream_store_purchase')
        
    asset = get_object_or_404(StreamAsset, id=asset_id, is_active=True)
    
    # Make sure we prefetch the related media and versions for efficiency
    asset.media.all()
    asset.versions.all()
    
    return render(request, 'STORE/stream_asset.html', {
        'asset': asset
    })

@login_required
def download_asset(request, asset_id):
    asset = get_object_or_404(StreamAsset, id=asset_id)
    
    # Check access permission
    if not user_can_access_stream_store(request.user):
        messages.error(request, "You need client or supporter status to download assets")
        return redirect('STORE:stream_store_purchase')
    
    # Get version if specified
    version_id = request.GET.get('version_id', None)
    
    try:
        # Determine file path based on version
        if version_id:
            try:
                version = asset.versions.get(id=version_id)
                file_path = version.file_path
            except AssetVersion.DoesNotExist:
                file_path = asset.file_path
        else:
            file_path = asset.file_path
        
        from django.http import StreamingHttpResponse
        
        def file_iterator(file_path, chunk_size=8192):
            client = storage.Client()
            bucket = client.bucket('bomby-user-uploads')
            blob = bucket.blob(file_path)
            
            # Download in chunks directly from GCS
            with blob.open("rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        
        # Get filename from path
        filename = file_path.split('/')[-1]
        
        # Create streaming response with appropriate headers
        response = StreamingHttpResponse(
            file_iterator(file_path),
            content_type='application/octet-stream'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
        
    except Exception as e:
        print(f"Download error: {type(e).__name__}: {str(e)}")
        messages.error(request, "Error downloading file. Please try again later.")
        return redirect('STORE:stream_asset_detail', asset_id=asset_id)

@login_required
def become_supporter(request):
    """Allow users to pay $10 to become supporters"""
    if request.user.is_supporter:
        messages.info(request, "You are already a supporter!")
        return redirect('STORE:stream_store')
    
    if request.method == 'POST':
        # Process payment would go here in production
        
        # Update user role
        request.user.promote_to_supporter()
        messages.success(request, "You are now a supporter with access to the Stream Store!")
        return redirect('STORE:stream_store')
    
    return render(request, 'STORE/become_supporter.html')

# Stream Asset Management (Admin)
@login_required
@user_passes_test(lambda u: u.is_staff)
def stream_asset_management(request):
    """Admin view for managing stream assets"""
    search_query = request.GET.get('search', '')
    
    if search_query:
        assets = StreamAsset.objects.filter(name__icontains=search_query)
    else:
        assets = StreamAsset.objects.all().order_by('-created_at')
    
    context = {
        'assets': assets,
        'search_query': search_query
    }
    
    response = render(request, 'STORE/stream_asset_management.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@login_required
@user_passes_test(lambda u: u.is_staff)
def add_stream_asset(request):
    """Admin view to add stream assets with multiple media files and versions using chunked uploads"""
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description', '')
        price = request.POST.get('price', 0.00)
        is_active = request.POST.get('is_active') == 'true'
        
        # Get file paths from hidden inputs instead of actual files
        main_file_path = request.POST.get('main_file_path')
        thumbnail_path = request.POST.get('thumbnail_path')
        
        if main_file_path:
            # Create database record
            asset = StreamAsset(
                name=name,
                description=description,
                price=price,
                is_active=is_active,
                file_path=main_file_path
            )
            asset.save()
            
            # Process thumbnail
            if thumbnail_path:
                media = AssetMedia(
                    asset=asset,
                    type='image',
                    file_path=thumbnail_path,
                    is_thumbnail=True,
                    order=0
                )
                media.save()
            
            # Process additional media files
            media_types = request.POST.getlist('media_types[]', [])
            media_file_paths = request.POST.getlist('media_file_paths[]', [])
            
            for i, media_path in enumerate(media_file_paths):
                if not media_path:  # Skip empty paths
                    continue
                    
                # Determine media type
                media_type = media_types[i] if i < len(media_types) else 'image'
                
                media = AssetMedia(
                    asset=asset,
                    type=media_type,
                    file_path=media_path,
                    is_thumbnail=False,
                    order=i+1
                )
                media.save()
            
            # Process versions based on checkboxes for main file
            if request.POST.get('use_as_static') == 'true':
                version = AssetVersion(
                    asset=asset,
                    name='Static',
                    type='static',
                    file_path=main_file_path  # Reuse the main file
                )
                version.save()
                
            if request.POST.get('use_as_animated') == 'true':
                version = AssetVersion(
                    asset=asset,
                    name='Animated',
                    type='animated',
                    file_path=main_file_path  # Reuse the main file
                )
                version.save()
                
            if request.POST.get('use_as_video') == 'true':
                version = AssetVersion(
                    asset=asset,
                    name='Video',
                    type='video',
                    file_path=main_file_path  # Reuse the main file
                )
                version.save()
            
            # Process additional versions
            version_names = request.POST.getlist('version_names[]', [])
            version_types = request.POST.getlist('version_types[]', [])
            version_file_paths = request.POST.getlist('version_file_paths[]', [])
            
            for i in range(min(len(version_names), len(version_types), len(version_file_paths))):
                if not version_file_paths[i]:  # Skip empty paths
                    continue
                    
                version = AssetVersion(
                    asset=asset,
                    name=version_names[i],
                    type=version_types[i],
                    file_path=version_file_paths[i]
                )
                version.save()
            
            messages.success(request, f"Asset '{name}' added successfully!")
            return redirect('STORE:stream_asset_management')
        else:
            messages.error(request, "You must provide a main asset file")
    
    return render(request, 'STORE/add_stream_asset.html')

CHUNK_UPLOAD_DIR = os.path.join(settings.MEDIA_ROOT, 'chunk_uploads')
os.makedirs(CHUNK_UPLOAD_DIR, exist_ok=True)

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def handle_chunked_upload(request):
    """Handle chunked file uploads"""
    action = request.POST.get('action')
    upload_id = request.POST.get('upload_id')
    
    if action == 'init':
        # Initialize a new upload
        filename = request.POST.get('filename')
        filesize = request.POST.get('filesize')
        filetype = request.POST.get('filetype')
        
        # Create a directory for this upload
        upload_dir = os.path.join(CHUNK_UPLOAD_DIR, upload_id)
        os.makedirs(upload_dir, exist_ok=True)
        
        # Store metadata
        metadata = {
            'filename': filename,
            'filesize': filesize,
            'filetype': filetype,
            'chunks_received': 0,
            'total_chunks': 0
        }
        
        with open(os.path.join(upload_dir, 'metadata.json'), 'w') as f:
            json.dump(metadata, f)
        
        return JsonResponse({
            'uploadId': upload_id,
            'status': 'initialized'
        })
        
    elif action == 'upload':
        # Handle chunk upload
        chunk_index = int(request.POST.get('chunk_index'))
        total_chunks = int(request.POST.get('total_chunks'))
        chunk = request.FILES.get('chunk')
        
        # Get the upload directory
        upload_dir = os.path.join(CHUNK_UPLOAD_DIR, upload_id)
        
        # Update metadata
        metadata_path = os.path.join(upload_dir, 'metadata.json')
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        metadata['total_chunks'] = total_chunks
        metadata['chunks_received'] += 1
        
        # Save the chunk
        chunk_path = os.path.join(upload_dir, f"chunk_{chunk_index}")
        with open(chunk_path, 'wb') as f:
            for chunk_data in chunk.chunks():
                f.write(chunk_data)
        
        # Update metadata
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f)
        
        return JsonResponse({
            'uploadId': upload_id,
            'status': 'chunk_received',
            'chunk_index': chunk_index,
            'total_chunks': total_chunks
        })
        
    elif action == 'finalize':
        # Combine chunks and finalize the upload
        filename = request.POST.get('filename')
        upload_dir = os.path.join(CHUNK_UPLOAD_DIR, upload_id)
        
        # Read metadata
        with open(os.path.join(upload_dir, 'metadata.json'), 'r') as f:
            metadata = json.load(f)
        
        # Check if all chunks are received
        if metadata['chunks_received'] != metadata['total_chunks']:
            return JsonResponse({
                'status': 'error',
                'message': 'Not all chunks received'
            }, status=400)
        
        # Combine chunks into a single file
        full_file_path = os.path.join(upload_dir, filename)
        with open(full_file_path, 'wb') as output_file:
            for i in range(metadata['total_chunks']):
                chunk_path = os.path.join(upload_dir, f"chunk_{i}")
                with open(chunk_path, 'rb') as chunk_file:
                    output_file.write(chunk_file.read())
        
        # For stream assets, upload to GCS bucket
        file_path = ""
        try:
            # Determine destination path based on file type
            if filename.lower().endswith(('.mp4', '.webm', '.mov', '.avi')):
                destination = f"stream_assets/media/{filename}"
            elif filename.lower().endswith('.zip'):
                destination = f"stream_assets/{filename}"
            else:
                # Default for images and other files
                destination = f"stream_assets/media/{filename}"
            
            # Upload to Google Cloud Storage
            client = storage.Client()
            bucket = client.bucket('bomby-user-uploads')
            blob = bucket.blob(destination)
            
            # Upload the combined file
            blob.upload_from_filename(full_file_path)
            
            file_path = destination
        except Exception as e:
            # Log the error but don't fail the request
            print(f"GCS Upload error: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': f'Failed to upload to storage: {str(e)}'
            }, status=500)
        
        # Cleanup: Delete the temp directory after successful upload
        # This is optional - you may want to keep files for debugging
        import shutil
        shutil.rmtree(upload_dir)
        
        return JsonResponse({
            'status': 'complete',
            'file_path': file_path,
            'filename': filename
        })
    
    # Invalid action
    return JsonResponse({
        'status': 'error',
        'message': 'Invalid action'
    }, status=400)

@login_required
@user_passes_test(lambda u: u.is_staff)
def edit_stream_asset(request, asset_id):
    """View for editing a stream asset with multiple media and versions"""
    asset = get_object_or_404(StreamAsset, id=asset_id)
    
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        price = request.POST.get('price', asset.price)
        is_active = request.POST.get('is_active') == 'true'
        
        asset.name = name
        asset.description = description
        asset.price = price
        asset.is_active = is_active
        asset.save()
        
        # Process thumbnail if a new one was uploaded
        thumbnail = request.FILES.get('thumbnail')
        if thumbnail:
            # Delete old thumbnail if exists
            AssetMedia.objects.filter(asset=asset, is_thumbnail=True).delete()
            
            # Create new thumbnail
            media = AssetMedia(
                asset=asset,
                type='image',
                file=thumbnail,
                is_thumbnail=True,
                order=0
            )
            media.save()
        
        # Handle removed media
        removed_media = request.POST.getlist('remove_media', [])
        for media_id in removed_media:
            try:
                media = AssetMedia.objects.get(id=media_id, asset=asset)
                media.delete()
            except AssetMedia.DoesNotExist:
                pass
        
        # Add new media
        media_files = request.FILES.getlist('new_media_files')
        for i, media_file in enumerate(media_files):
            media_type = request.POST.getlist('new_media_types')[i] if i < len(request.POST.getlist('new_media_types')) else 'image'
            
            # Get the next order value
            next_order = AssetMedia.objects.filter(asset=asset).exclude(is_thumbnail=True).count() + 1
            
            media = AssetMedia(
                asset=asset,
                type=media_type,
                file=media_file,
                is_thumbnail=False,
                order=next_order
            )
            media.save()
        
        # Handle removed versions
        removed_versions = request.POST.getlist('remove_version', [])
        for version_id in removed_versions:
            try:
                version = AssetVersion.objects.get(id=version_id, asset=asset)
                version.delete()
            except AssetVersion.DoesNotExist:
                pass
        
        # Add new versions
        version_names = request.POST.getlist('new_version_names', [])
        version_types = request.POST.getlist('new_version_types', [])
        version_files = request.FILES.getlist('new_version_files', [])
        
        for i in range(min(len(version_names), len(version_types), len(version_files))):
            version_file = version_files[i]
            version_path = f'stream_assets/versions/{version_file.name}'
            
            version = AssetVersion(
                asset=asset,
                name=version_names[i],
                type=version_types[i],
                file_path=version_path
            )
            version.save()
            
            # Upload version file
            try:
                from google.cloud import storage
                
                client = storage.Client()
                bucket = client.bucket('bomby-user-uploads')
                blob = bucket.blob(version_path)
                blob.upload_from_file(version_file)
            except Exception as e:
                messages.warning(request, f"Version '{version_names[i]}' added to database, but file upload issue: {str(e)}")
        
        messages.success(request, f"Asset '{name}' updated successfully.")
        return redirect('STORE:stream_asset_management')
    
    context = {
        'asset': asset,
        'media': asset.media.all(),
        'versions': asset.versions.all()
    }
    return render(request, 'STORE/edit_stream_asset.html', context)

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def bulk_change_asset_status(request):
    """Change status for multiple assets at once"""
    selected_assets = request.POST.get('selected_assets', '')
    new_status = request.POST.get('status') == 'true'
    
    if selected_assets:
        asset_ids = [int(id) for id in selected_assets.split(',')]
        
        # Update all selected assets
        StreamAsset.objects.filter(id__in=asset_ids).update(is_active=new_status)
        
        status_text = 'active' if new_status else 'inactive'
        messages.success(request, f"{len(asset_ids)} asset{'s' if len(asset_ids) > 1 else ''} set to {status_text}.")
    
    return redirect('STORE:stream_asset_management')

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def delete_stream_assets(request):
    """Delete selected assets and their files from storage bucket"""
    selected_assets = request.POST.get('selected_assets', '')
    
    if selected_assets:
        asset_ids = [int(id) for id in selected_assets.split(',')]
        
        # Count before deletion for message
        count = len(asset_ids)
        
        try:
            # Connect to Google Cloud Storage
            client = storage.Client()
            bucket = client.bucket('bomby-user-uploads')
            
            # Fetch assets before deletion to get file paths
            assets_to_delete = StreamAsset.objects.filter(id__in=asset_ids).prefetch_related('media', 'versions')
            
            for asset in assets_to_delete:
                # Delete main asset file
                if asset.file_path:
                    blob = bucket.blob(asset.file_path)
                    if blob.exists():
                        blob.delete()
                
                # Delete thumbnail file if present
                if asset.thumbnail:
                    thumbnail_path = f'stream_assets/thumbnails/{os.path.basename(asset.thumbnail.name)}'
                    blob = bucket.blob(thumbnail_path)
                    if blob.exists():
                        blob.delete()
                
                # Delete media files
                for media in asset.media.all():
                    if media.file_path:
                        blob = bucket.blob(media.file_path)
                        if blob.exists():
                            blob.delete()
                
                # Delete version files
                for version in asset.versions.all():
                    if version.file_path:
                        blob = bucket.blob(version.file_path)
                        if blob.exists():
                            blob.delete()
            
            # Now delete the database records
            StreamAsset.objects.filter(id__in=asset_ids).delete()
            
            messages.success(request, f"{count} asset{'s' if count > 1 else ''} and associated files deleted successfully.")
            
        except Exception as e:
            # Log the error but still try to delete database records
            print(f"Error deleting files from storage: {str(e)}")
            StreamAsset.objects.filter(id__in=asset_ids).delete()
            messages.warning(
                request, 
                f"{count} asset{'s' if count > 1 else ''} deleted from database, but some storage files may remain."
            )
    
    return redirect('STORE:stream_asset_management')

# Admin Views
@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def toggle_product_status(request, product_id):
    from django.db import connection
    
    # Parse the request body to get the active status
    try:
        data = json.loads(request.body)
        is_active = data.get('active', False)
    except json.JSONDecodeError:
        is_active = False
    
    # Direct SQL update with parameterized query
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE \"STORE_product\" SET is_active = %s WHERE id = %s",
            [is_active, product_id]
        )
    
    return JsonResponse({
        'success': True,
        'product_id': product_id,
        'is_active': is_active,
        'message': f'Product {product_id} status updated to {is_active} successfully'
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def force_inactive(request, product_id):
    """Force a product to inactive state"""
    from django.db import connection
    
    # Direct SQL update - no ORM
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE \"STORE_product\" SET is_active = false WHERE id = %s",
            [product_id]
        )
    
    return JsonResponse({
        'success': True,
        'product_id': product_id,
        'is_active': False
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def force_active(request, product_id):
    """Force a product to active state"""
    from django.db import connection
    
    # Direct SQL update - no ORM
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE \"STORE_product\" SET is_active = true WHERE id = %s",
            [product_id]
        )
    
    return JsonResponse({
        'success': True,
        'product_id': product_id,
        'is_active': True
    })

# Product Management Views
@login_required
@user_passes_test(lambda u: u.is_staff)
def product_management(request):
    """View for managing products"""
    search_query = request.GET.get('search', '')
    
    if search_query:
        products = Product.objects.filter(name__icontains=search_query)
    else:
        products = Product.objects.all()
    
    context = {
        'products': products,
        'search_query': search_query
    }
    
    # Add cache control headers
    response = render(request, 'STORE/product_management.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@login_required
@user_passes_test(lambda u: u.is_staff)
def edit_product(request, product_id):
    """View for editing a product"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.method == 'POST':
        # Process the form data
        name = request.POST.get('name')
        price = request.POST.get('price')
        description = request.POST.get('description')
        is_active = request.POST.get('is_active') == 'true'
        
        # Update the product
        product.name = name
        product.price = price
        product.description = description
        product.is_active = is_active
        product.save()
        
        messages.success(request, f"Product '{name}' updated successfully.")
        return redirect('STORE:product_management')
    
    context = {
        'product': product
    }
    
    # Add cache control headers
    response = render(request, 'STORE/edit_product.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def bulk_change_product_status(request):
    """Change status for multiple products at once"""
    selected_products = request.POST.get('selected_products', '')
    new_status = request.POST.get('status') == 'true'
    
    if selected_products:
        product_ids = [int(id) for id in selected_products.split(',')]
        
        # Update all selected products
        from django.db import connection
        with connection.cursor() as cursor:
            # Using parameterized query for safety
            status_value = 'true' if new_status else 'false'
            placeholders = ','.join(['%s'] * len(product_ids))
            query = f"UPDATE \"STORE_product\" SET is_active = {status_value} WHERE id IN ({placeholders})"
            cursor.execute(query, product_ids)
        
        status_text = 'active' if new_status else 'inactive'
        messages.success(
            request, 
            f"{len(product_ids)} product{'s' if len(product_ids) > 1 else ''} set to {status_text}."
        )
    
    return redirect('STORE:product_management')

@login_required
@user_passes_test(lambda u: u.is_staff)
def create_product(request):
    """View for creating a new product"""
    if request.method == 'POST':
        # Process the form data
        name = request.POST.get('name')
        price = request.POST.get('price')
        description = request.POST.get('description')
        is_active = request.POST.get('is_active') == 'true'
        
        # Create the product without specifying ID (let Django auto-assign it)
        try:
            product = Product()
            product.name = name
            product.price = price
            product.description = description
            product.is_active = is_active
            product.save()
        except Exception as e:
            messages.error(request, f"Error creating product: {str(e)}")
            return redirect('STORE:create_product')
        
        messages.success(request, f"Product '{name}' created successfully.")
        return redirect('STORE:product_management')
    
    # Add cache control headers
    response = render(request, 'STORE/create_product.html')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def delete_products(request):
    """Delete selected products"""
    selected_products = request.POST.get('selected_products', '')
    
    if selected_products:
        product_ids = [int(id) for id in selected_products.split(',')]
        
        # Count before deletion for message
        count = len(product_ids)
        
        # Delete products
        Product.objects.filter(id__in=product_ids).delete()
        
        messages.success(
            request, 
            f"{count} product{'s' if count > 1 else ''} deleted successfully."
        )
    
    return redirect('STORE:product_management')

# Order Management Views
@login_required
@user_passes_test(lambda u: u.is_staff)
def order_management(request):
    """Admin view for managing orders and donations"""
    search_query = request.GET.get('search', '')
    
    # Orders section
    if search_query:
        # Search by order ID or username
        try:
            # Try to convert to integer for order ID search
            order_id = int(search_query)
            order_filter = Q(id=order_id)
        except ValueError:
            order_filter = Q(user__username__icontains=search_query)
            
        orders = Order.objects.filter(order_filter)
    else:
        orders = Order.objects.all()
    
    # Donations section
    if search_query:
        # Search donations by username or payment ID
        donation_filter = Q(user__username__icontains=search_query) | Q(payment_id__icontains=search_query)
        donations = Donation.objects.filter(donation_filter)
    else:
        donations = Donation.objects.all()
    
    # Calculate donation total for analytics
    donation_total = 0
    for donation in donations:
        if donation.amount:
            donation_total += float(donation.amount)
    
    # Combine orders and donations into a single list
    combined_items = []
    
    # Add orders
    for order in orders:
        combined_items.append({
            'type': 'order',
            'id': order.id,
            'user': order.user,
            'product': order.product,
            'created_at': order.created_at,
            'status': order.status,
            'due_date': order.due_date,
        })
    
    # Add donations
    for donation in donations:
        combined_items.append({
            'type': 'donation',
            'id': donation.id,
            'user': donation.user,
            'amount': donation.amount,
            'created_at': donation.created_at,
            'is_paid': donation.is_paid,
        })
    
    # Sort by created_at date (newest first)
    combined_items.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Get all users and products for the add order form
    User = get_user_model()
    all_users = User.objects.all().order_by('username')
    all_products = Product.objects.filter(is_active=True).order_by('name')
    
    context = {
        'orders': orders,
        'donations': donations,
        'combined_items': combined_items,
        'donation_total': donation_total, 
        'search_query': search_query,
        'all_users': all_users,
        'all_products': all_products,
    }
    
    response = render(request, 'STORE/order_management.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_change_order_status(request):
    """Change status for selected orders"""
    selected_orders = request.POST.get('selected_orders', '')
    new_status = request.POST.get('status')
    
    if selected_orders and new_status in dict(Order.STATUS_CHOICES):
        order_ids = [int(id) for id in selected_orders.split(',')]
        
        # Update all selected orders
        updated_count = 0
        for order_id in order_ids:
            try:
                order = Order.objects.get(id=order_id)
                old_status = order.status
                order.status = new_status
                order.save()
                updated_count += 1
                
                # Send appropriate emails based on status change
                if old_status != new_status:
                    if new_status == 'in_progress':
                        try:
                            send_in_progress_order_email(request, order)
                        except Exception as e:
                            print(f"Error sending in-progress email: {e}")
                    elif new_status == 'completed':
                        try:
                            send_completed_order_email(request, order)
                        except Exception as e:
                            print(f"Error sending completed email: {e}")
            except Order.DoesNotExist:
                continue
        
        messages.success(
            request, 
            f"{updated_count} order{'s' if updated_count > 1 else ''} updated to {dict(Order.STATUS_CHOICES)[new_status]}."
        )
    
    return redirect('STORE:order_management')

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_add_order(request):
    """Add a new order for a user"""
    User = get_user_model()
    
    user_id = request.POST.get('user_id')
    product_id = request.POST.get('product_id')
    
    try:
        user = User.objects.get(id=user_id)
        product = Product.objects.get(id=product_id)
        
        # Create the order
        order = Order.objects.create(
            user=user,
            product=product,
            status='pending'
        )
        
        # Update user role to client if they aren't already
        if hasattr(user, 'is_client') and not user.is_client:
            if hasattr(user, 'promote_to_client'):
                user.promote_to_client()
        
        messages.success(
            request,
            f"Order #{order.id} for {product.name} created successfully for user {user.username}."
        )
    except User.DoesNotExist:
        messages.error(request, "Selected user does not exist.")
    except Product.DoesNotExist:
        messages.error(request, "Selected product does not exist.")
    except Exception as e:
        messages.error(request, f"Error creating order: {str(e)}")
    
    return redirect('STORE:order_management')

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_delete_orders(request):
    """Delete selected orders and donations"""
    selected_orders = request.POST.get('selected_orders', '')
    selected_donations = request.POST.get('selected_donations', '')
    
    deleted_count = 0
    
    # Delete orders if any selected
    if selected_orders:
        order_ids = [int(id) for id in selected_orders.split(',')]
        # Count before deletion for message
        order_count = len(order_ids)
        # Delete orders
        Order.objects.filter(id__in=order_ids).delete()
        deleted_count += order_count
    
    # Delete donations if any selected
    if selected_donations:
        donation_ids = [int(id) for id in selected_donations.split(',')]
        # Count before deletion for message
        donation_count = len(donation_ids)
        # Delete donations
        Donation.objects.filter(id__in=donation_ids).delete()
        deleted_count += donation_count
    
    if deleted_count > 0:
        messages.success(
            request, 
            f"{deleted_count} item{'s' if deleted_count > 1 else ''} deleted successfully."
        )
    
    return redirect('STORE:order_management')

@login_required
@user_passes_test(lambda u: u.is_staff)
def review_management(request):
    """Admin view for managing reviews"""
    search_query = request.GET.get('search', '')
    
    if search_query:
        # Search by order ID, review ID, or username
        try:
            # Try to convert to integer for ID searches
            id_query = int(search_query)
            review_filter = Q(id=id_query) | Q(order__id=id_query)
        except ValueError:
            review_filter = Q(order__user__username__icontains=search_query)
            
        reviews = Review.objects.filter(review_filter)
    else:
        reviews = Review.objects.all().order_by('-created_at')
    
    # Get orders without reviews for the add review form
    available_orders = Order.objects.filter(status='completed').exclude(
        id__in=Review.objects.values_list('order__id', flat=True)
    ).order_by('-created_at')
    
    # Get all active products
    all_products = Product.objects.filter(is_active=True).order_by('name')
    
    context = {
        'reviews': reviews,
        'search_query': search_query,
        'available_orders': available_orders,
        'all_products': all_products
    }
    
    response = render(request, 'STORE/review_management.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@login_required
@user_passes_test(lambda u: u.is_staff)
def review_details(request, review_id):
    """View a single review in detail"""
    review = get_object_or_404(Review, id=review_id)
    
    context = {
        'review': review
    }
    
    response = render(request, 'STORE/review_details.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_edit_review(request, review_id):
    """Admin view for editing a review"""
    review = get_object_or_404(Review, id=review_id)
    
    if request.method == 'POST':
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            form.save()
            messages.success(request, "Review updated successfully.")
            return redirect('STORE:review_management')
    else:
        form = ReviewForm(instance=review)
    
    context = {
        'form': form,
        'review': review
    }
    
    response = render(request, 'STORE/edit_review.html', context)
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_delete_reviews(request):
    """Delete selected reviews"""
    selected_reviews = request.POST.get('selected_reviews', '')
    
    if selected_reviews:
        review_ids = [int(id) for id in selected_reviews.split(',')]
        
        # Count before deletion for message
        count = len(review_ids)
        
        # Delete reviews
        Review.objects.filter(id__in=review_ids).delete()
        
        messages.success(
            request, 
            f"{count} review{'s' if count > 1 else ''} deleted successfully."
        )
    
    return redirect('STORE:review_management')

@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_add_review(request):
    """Admin view for adding a review directly for a product"""
    product_id = request.POST.get('product_id')
    rating = request.POST.get('rating')
    comment = request.POST.get('comment')
    is_fiverr = request.POST.get('is_fiverr') == 'on'
    fiverr_username = request.POST.get('fiverr_username', '')
    
    try:
        if not product_id:
            messages.error(request, "You must select a product")
            return redirect('STORE:review_management')
            
        product = Product.objects.get(id=product_id)
        
        # Get the staff user making the request
        staff_user = request.user
        
        # Create a mock order for this review
        mock_order = Order.objects.create(
            user=staff_user,
            product_id=product_id,
            status='completed',
            completed_at=timezone.now()
        )
        
        # Create the review
        review = Review.objects.create(
            order=mock_order,
            rating=rating,
            comment=comment,
            is_fiverr=is_fiverr,
            fiverr_username=fiverr_username if is_fiverr else None
        )
        
        messages.success(request, f"Review added successfully for {product.name}.")
            
    except Product.DoesNotExist:
        messages.error(request, "Selected product does not exist.")
    except Exception as e:
        messages.error(request, f"Error creating review: {str(e)}")
    
    return redirect('STORE:review_management')

## PAYMENT PROCESSING ##
@require_POST
@login_required
def apply_discount(request, product_id):
    """Apply a discount code to a product"""
    product = get_object_or_404(Product, id=product_id, is_active=True)
    discount_code = request.POST.get('discount_code', '').strip()
    
    try:
        # Check if the code exists and is valid
        discount = DiscountCode.objects.get(
            code=discount_code,
            user=request.user,
            is_used=False
        )
        
        # Calculate discounted price
        discount_percent = discount.percentage
        discounted_price = float(product.price) * (1 - discount_percent/100)
        discounted_price = round(discounted_price, 2)
        
        # Store discount info in session for later use
        request.session['discount_code_id'] = discount.id
        
        context = {
            'product': product,
            'paypal_client_id': settings.PAYPAL_CLIENT_ID,
            'discount_applied': True,
            'discounted_price': discounted_price
        }
        
        return render(request, 'STORE/payment_page.html', context)
        
    except DiscountCode.DoesNotExist:
        # Code doesn't exist or is already used
        context = {
            'product': product,
            'paypal_client_id': settings.PAYPAL_CLIENT_ID,
            'discount_error': 'Invalid or expired discount code.'
        }
        
        return render(request, 'STORE/payment_page.html', context)

def payment_page(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    # Check if user cancelled a payment
    cancelled = request.GET.get('cancelled', False)
    if cancelled:
        messages.info(request, "Payment was cancelled. You can try when you're ready.")
    
    # Check if user has an unused discount code
    discount_code = None
    has_discount = False
    discount_applied = False
    discounted_price = None
    discount_error = None
    
    if request.user.is_authenticated:
        discount_code = DiscountCode.objects.filter(
            user=request.user,
            is_used=False
        ).first()
        
        if discount_code:
            has_discount = True
            
        # Check if a discount is being applied
        if request.method == 'POST' and 'discount_code' in request.POST:
            code = request.POST.get('discount_code', '').strip()
            try:
                discount = DiscountCode.objects.get(
                    code=code,
                    user=request.user,
                    is_used=False
                )
                
                # Calculate discounted price
                discount_percent = discount.percentage
                discounted_price = round(float(product.price) * (1 - discount_percent/100), 2)
                discount_applied = True
                
                # Store in session for later processing
                request.session['discount_code_id'] = discount.id
                
            except DiscountCode.DoesNotExist:
                discount_error = "Invalid or expired discount code."
    
    context = {
        'product': product,
        'paypal_client_id': settings.PAYPAL_CLIENT_ID,
        'has_discount': has_discount,
        'discount_code': discount_code,
        'discount_applied': discount_applied,
        'discounted_price': discounted_price,
        'discount_error': discount_error
    }
    
    response = render(request, 'STORE/payment_page.html', context)
    
    # Add cache control headers
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response

@login_required
def payment_success(request):
    payment_id = request.GET.get('paymentId')
    product_id = request.GET.get('product_id')
    discount_applied = request.GET.get('discount_applied', False)
    
    is_verified, payment_data = verify_paypal_payment(payment_id)
    if not is_verified:
        messages.error(request, "Payment verification failed. Please contact support.")
        return redirect('STORE:store')
    
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    # If a discount was applied, mark it as used
    if discount_applied and request.session.get('discount_code_id'):
        try:
            discount = DiscountCode.objects.get(
                id=request.session.get('discount_code_id'),
                user=request.user,
                is_used=False
            )
            
            # Mark as used
            discount.is_used = True
            discount.used_at = timezone.now()
            discount.save()
            
            # Clear from session
            del request.session['discount_code_id']
            
        except DiscountCode.DoesNotExist:
            # Log the error but continue with order creation
            print(f"Error: Discount code not found for session id {request.session.get('discount_code_id')}")
    
    # Create order
    if int(product_id) == 4:  # Stream Store product
        order = Order.objects.create(
            user=request.user,
            product=product,
            status='completed',
            payment_id=payment_id,
            is_paid=True
        )
        
        # Promote to supporter if not already client/admin
        if not (request.user.is_client or request.user.is_admin_user):
            request.user.promote_to_supporter()
    else:
        # Regular product flow
        order = Order.objects.create(
            user=request.user,
            product=product,
            status='pending',
            payment_id=payment_id,
            is_paid=True
        )
        
        # Promote user to client
        if not request.user.is_client:
            request.user.promote_to_client()
    
    # Generate invoice
    try:
        # Create invoice record
        invoice = Invoice(order=order)
        invoice.invoice_number = f"INV-{order.created_at.year}-{order.created_at.month:02d}-{order.id}"
        invoice.save()
        
        # Send invoice email
        send_invoice_email(request, order, invoice)
        
    except Exception as e:
        # Log error but don't stop the flow
        print(f"Error generating invoice: {e}")
    
    # Send appropriate emails based on product type
    if int(product_id) == 4:
        try:
            send_completed_order_email(request, order)
        except Exception as e:
            print(f"Error sending completed order email: {e}")
    else:
        try:
            send_pending_order_email(request, order)
        except Exception as e:
            print(f"Error sending pending order email: {e}")
    
    return render(request, 'STORE/payment_success.html', {
        'order': order,
    })

@login_required
def download_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    # Verify permission - only owner or staff can download
    if request.user != order.user and not request.user.is_staff:
        return HttpResponseForbidden("You don't have permission to access this invoice")
    
    try:
        invoice = Invoice.objects.get(order=order)
        if invoice.pdf_file:
            # Serve the file
            response = HttpResponse(invoice.pdf_file, content_type='application/pdf')
            response['Content-Disposition'] = f'attachment; filename="{os.path.basename(invoice.pdf_file.name)}"'
            return response
        else:
            messages.error(request, "Invoice file not found")
    except Invoice.DoesNotExist:
        messages.error(request, "No invoice available for this order")
    
    return redirect('STORE:order_details', order_id=order.id)

@login_required
def view_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    # Verify permission - only owner or staff can view
    if request.user != order.user and not request.user.is_staff:
        return HttpResponseForbidden("You don't have permission to view this invoice")
    
    try:
        invoice = Invoice.objects.get(order=order)
        
        # Generate HTML invoice
        from .utils.invoice_utils import generate_invoice_html
        invoice_html = generate_invoice_html(order)
        
        return HttpResponse(invoice_html)
    except Invoice.DoesNotExist:
        messages.error(request, "No invoice available for this order")
        return redirect('STORE:order_details', order_id=order.id)

@login_required
def payment_cancel(request):
    messages.error(request, "Payment was cancelled. Please try again.")
    return redirect('STORE:store')

# Store Analyitcs
@user_passes_test(lambda u: u.is_staff)
def store_analytics(request):
    """Analytics dashboard for store metrics with period comparison"""
    
    # Time frame filters
    time_frame = request.GET.get('time_frame', 'all')
    
    # Set current period ranges
    now = timezone.now()
    if time_frame == 'day':
        current_start = now - timedelta(hours=24)
        previous_start = current_start - timedelta(hours=24)
        current_orders = Order.objects.filter(created_at__gte=current_start)
        current_donations = Donation.objects.filter(created_at__gte=current_start)
    elif time_frame == 'week':
        current_start = now - timedelta(days=7)
        previous_start = current_start - timedelta(days=7)
        current_orders = Order.objects.filter(created_at__gte=current_start)
        current_donations = Donation.objects.filter(created_at__gte=current_start)
    elif time_frame == 'month':
        current_start = now - timedelta(days=30)
        previous_start = current_start - timedelta(days=30)
        current_orders = Order.objects.filter(created_at__gte=current_start)
        current_donations = Donation.objects.filter(created_at__gte=current_start)
    elif time_frame == 'year':
        current_start = now - timedelta(days=365)
        previous_start = current_start - timedelta(days=365)
        current_orders = Order.objects.filter(created_at__gte=current_start)
        current_donations = Donation.objects.filter(created_at__gte=current_start)
    else:
        # All time - split history in half for comparison
        oldest_order = Order.objects.order_by('created_at').first()
        if oldest_order:
            total_days = (now - oldest_order.created_at).days
            mid_point = oldest_order.created_at + timedelta(days=total_days/2)
            current_orders = Order.objects.all()
            current_donations = Donation.objects.all()
            previous_start = oldest_order.created_at
            current_start = mid_point
        else:
            current_orders = Order.objects.all()
            current_donations = Donation.objects.all()
            previous_start = now - timedelta(days=365)
            current_start = previous_start
    
    # Exclude Fiverr orders by filtering out orders with reviews marked as Fiverr
    fiverr_order_ids = Review.objects.filter(is_fiverr=True).values_list('order_id', flat=True)
    current_orders = current_orders.exclude(id__in=fiverr_order_ids)
    
    # Get previous period orders and donations
    if current_start and previous_start:
        previous_orders = Order.objects.filter(
            created_at__gte=previous_start,
            created_at__lt=current_start
        ).exclude(id__in=fiverr_order_ids)
        
        previous_donations = Donation.objects.filter(
            created_at__gte=previous_start,
            created_at__lt=current_start
        )
    else:
        previous_orders = Order.objects.none()
        previous_donations = Donation.objects.none()
    
    # Basic order metrics
    total_orders = current_orders.count()
    completed_orders = current_orders.filter(status='completed').count()
    in_progress_orders = current_orders.filter(status='in_progress').count()
    pending_orders = current_orders.filter(status='pending').count()
    
    # Previous period metrics
    prev_order_count = previous_orders.count()
    
    # Calculate percentages for each status
    if total_orders > 0:
        completion_rate = (completed_orders / total_orders * 100)
        in_progress_percent = (in_progress_orders / total_orders * 100)
        pending_percent = (pending_orders / total_orders * 100)
    else:
        completion_rate = in_progress_percent = pending_percent = 0
    
    # Calculate trend percentages
    if prev_order_count > 0:
        orders_trend = ((total_orders - prev_order_count) / prev_order_count * 100)
    else:
        orders_trend = 100 if total_orders > 0 else 0
    
    # Calculate total revenue and comparison
    total_revenue = 0
    product_sales = []
    
    # Get all products with their orders for current period
    products_with_orders = Product.objects.filter(
        id__in=current_orders.values_list('product_id', flat=True)
    ).distinct()
    
    for product in products_with_orders:
        # Count orders for this product
        product_order_count = current_orders.filter(product=product).count()
        
        if product_order_count > 0:
            product_sales.append({
                'product__name': product.name,
                'count': product_order_count,
                'unit_price': float(product.price or 0),
            })
            
            # Add to total revenue (price * count)
            if product.price:
                total_revenue += product.price * product_order_count
    
    # Calculate previous period revenue
    prev_revenue = 0
    for product in Product.objects.filter(id__in=previous_orders.values_list('product_id', flat=True)):
        prev_product_count = previous_orders.filter(product=product).count()
        if product.price:
            prev_revenue += product.price * prev_product_count
    
    # Donation metrics
    total_donations = current_donations.count()
    donation_amount = current_donations.aggregate(sum=Sum('amount'))['sum'] or 0
    
    # Previous period donation metrics
    prev_donation_count = previous_donations.count()
    prev_donation_amount = previous_donations.aggregate(sum=Sum('amount'))['sum'] or 0
    
    # Calculate donation trends
    if prev_donation_count > 0:
        donation_count_trend = ((total_donations - prev_donation_count) / prev_donation_count * 100)
    else:
        donation_count_trend = 100 if total_donations > 0 else 0
        
    if prev_donation_amount > 0:
        donation_amount_trend = ((donation_amount - prev_donation_amount) / prev_donation_amount * 100)
    else:
        donation_amount_trend = 100 if donation_amount > 0 else 0
    
    # Add donation amount to total revenue
    total_revenue += donation_amount
    prev_revenue += prev_donation_amount
    
    # Calculate revenue trend
    if prev_revenue > 0:
        revenue_trend = ((total_revenue - prev_revenue) / prev_revenue * 100)
    else:
        revenue_trend = 100 if total_revenue > 0 else 0
        
    # Store absolute values for the template
    orders_trend_abs = abs(orders_trend)
    revenue_trend_abs = abs(revenue_trend)
    donation_count_trend_abs = abs(donation_count_trend)
    donation_amount_trend_abs = abs(donation_amount_trend)
    
    # Sort by count
    product_sales = sorted(product_sales, key=lambda x: x['count'], reverse=True)
    
    # Review metrics - exclude Fiverr reviews
    avg_rating = Review.objects.filter(
        order__in=current_orders
    ).filter(
        is_fiverr=False
    ).aggregate(
        avg=Avg('rating')
    )['avg'] or 0
    
    review_count = Review.objects.filter(
        order__in=current_orders
    ).filter(
        is_fiverr=False
    ).count()
    
    # Get all products for page views
    all_products = Product.objects.all()
    
    # Prepare product view data
    page_view_data = []

    for product in all_products:
        # Get view count for this product within the time frame
        if time_frame != 'all' and current_start:
            # This prevents counting multiple refreshes from the same visitor
            views_count = PageView.objects.filter(
                product=product, 
                timestamp__gte=current_start
            ).values('session_id').distinct().count()
        else:
            views_count = PageView.objects.filter(
                product=product
            ).values('session_id').distinct().count()
            
        # Count orders that aren't from Fiverr
        product_orders = current_orders.filter(product=product).count()
        conversion_rate = (product_orders / views_count * 100) if views_count > 0 else 0
        
        page_view_data.append({
            'name': product.name,
            'views': views_count,
            'conversion_rate': round(conversion_rate, 1)
        })
    
    # Sort by views (descending)
    page_view_data = sorted(page_view_data, key=lambda x: x['views'], reverse=True)
    
    # Convert to JSON for JavaScript
    import json
    page_views_json = json.dumps(page_view_data)
    
    context = {
        'time_frame': time_frame,
        'total_orders': total_orders,
        'completed_orders': completed_orders,
        'in_progress_orders': in_progress_orders,
        'pending_orders': pending_orders,
        'completion_rate': round(completion_rate, 1),
        'in_progress_percent': round(in_progress_percent, 1),
        'pending_percent': round(pending_percent, 1),
        'total_revenue': round(total_revenue, 2),
        'product_sales': product_sales,
        'avg_rating': round(avg_rating, 1),
        'review_count': review_count,
        'page_views': page_view_data,
        'page_views_json': page_views_json,
        'orders_trend': round(orders_trend, 1),
        'revenue_trend': round(revenue_trend, 1),
        'orders_trend_abs': round(orders_trend_abs, 1),
        'revenue_trend_abs': round(revenue_trend_abs, 1),
        'total_donations': total_donations,
        'donation_amount': round(donation_amount, 2),
        'donation_count_trend': round(donation_count_trend, 1),
        'donation_amount_trend': round(donation_amount_trend, 1),
        'donation_count_trend_abs': round(donation_count_trend_abs, 1),
        'donation_amount_trend_abs': round(donation_amount_trend_abs, 1),
    }
    
    return render(request, 'STORE/store_analytics.html', context)