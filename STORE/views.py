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
import datetime
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
    
    # Explicitly disable browser caching
    response = render(request, 'STORE/store.html', {'products': products})
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

def stream_setup(request):
    return render(request, 'STORE/stream_setup.html')

def stream_store(request):
    return render(request, 'STORE/stream_store.html')

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

# Orders
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
                return JsonResponse({'status': 'success'})
            
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
        orders = Order.objects.filter(user=request.user).exclude(product_id=4).order_by('-created_at')
        
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
def stream_store(request):
    """Stream store view with access control"""
    # Check if user can access (supporter, client, admin)
    if not user_can_access_stream_store(request.user):
        # Show the purchase page (not purchase history)
        product = Product.objects.get(id=4)
        return render(request, 'STORE/stream_store_purchase.html', {'product': product})
    
    # User has access, show the actual store    
    assets = StreamAsset.objects.filter(is_active=True)
    return render(request, 'STORE/stream_store.html', {'assets': assets})

@login_required
def stream_store_purchase(request):
    """Page for purchasing stream store access"""
    # If already a client/supporter/admin, redirect to store
    if user_can_access_stream_store(request.user):
        return redirect('STORE:stream_store')
        
    product = Product.objects.get(id=4)
    
    if request.method == 'POST':
        # Create a new order that's already completed
        order = Order.objects.create(
            user=request.user,
            product=product,
            status='completed',
            completed_at=timezone.now(),
            is_paid=True 
        )
        
        # Update user role to supporter
        request.user.promote_to_supporter()
        
        messages.success(request, "You now have access to the Stream Store!")
        return redirect('STORE:stream_store')
    
    # Change this line to use stream_store_purchase.html
    return render(request, 'STORE/stream_store_purchase.html', {'product': product})

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
    """Download stream asset with support for different versions"""
    asset = get_object_or_404(StreamAsset, id=asset_id)
    
    # Check access permission
    if not user_can_access_stream_store(request.user):
        messages.error(request, "You need client or supporter status to download assets")
        return redirect('STORE:stream_store_purchase')
    
    # Get version if specified
    version_id = request.GET.get('version_id', None)
    
    try:
        from google.cloud import storage
        
        client = storage.Client()
        bucket = client.bucket('bomby-user-uploads')
        
        # Determine file path based on version
        if version_id:
            try:
                version = asset.versions.get(id=version_id)
                file_path = version.file_path
            except AssetVersion.DoesNotExist:
                file_path = asset.file_path
        else:
            file_path = asset.file_path
        
        blob = bucket.blob(file_path)
        
        # Check if file exists
        if not blob.exists():
            messages.error(request, f"File not found: {file_path}")
            return redirect('STORE:stream_asset_detail', asset_id=asset_id)
        
        # Direct download
        content = blob.download_as_bytes()
        filename = file_path.split('/')[-1]
        
        response = HttpResponse(content, content_type='application/octet-stream')
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
    """Admin view for managing orders"""
    search_query = request.GET.get('search', '')
    
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
        orders = Order.objects.all().order_by('-created_at')
    
    # Get all users and products for the add order form
    User = get_user_model()
    all_users = User.objects.all().order_by('username')
    all_products = Product.objects.filter(is_active=True).order_by('name')
    
    context = {
        'orders': orders,
        'search_query': search_query,
        'all_users': all_users,
        'all_products': all_products
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
    """Delete selected orders"""
    selected_orders = request.POST.get('selected_orders', '')
    
    if selected_orders:
        order_ids = [int(id) for id in selected_orders.split(',')]
        
        # Count before deletion for message
        count = len(order_ids)
        
        # Delete orders
        Order.objects.filter(id__in=order_ids).delete()
        
        messages.success(
            request, 
            f"{count} order{'s' if count > 1 else ''} deleted successfully."
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
            comment=comment
        )
        
        messages.success(request, f"Review added successfully for {product.name}.")
            
    except Product.DoesNotExist:
        messages.error(request, "Selected product does not exist.")
    except Exception as e:
        messages.error(request, f"Error creating review: {str(e)}")
    
    return redirect('STORE:review_management')

## PAYMENT PROCESSING ##
def payment_page(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    context = {
        'product': product,
        'paypal_client_id': settings.PAYPAL_CLIENT_ID,
    }
    
    response = render(request, 'STORE/payment_page.html', context)
    
    # Comprehensive CSP that addresses all the error types
    response['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://*.paypal.com https://*.paypalobjects.com https://*.google.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://*.paypal.com https://*.paypalobjects.com https://unpkg.com https://maxcdn.bootstrapcdn.com; "
        "font-src 'self' data: https://cdnjs.cloudflare.com https://*.paypal.com https://*.paypalobjects.com https://fonts.gstatic.com https://unpkg.com https://maxcdn.bootstrapcdn.com; "
        "connect-src 'self' https://*.paypal.com https://*.paypal.cn https://*.paypalobjects.com https://objects.paypal.cn "
        "https://192.55.233.1 https://*.google.com https://www.google.com https://browser-intake-us5-datadoghq.com https://*.qualtrics.com; "
        "frame-src 'self' https://*.paypal.com https://*.google.com; "
        "img-src 'self' data: https://*.paypal.com https://*.paypalobjects.com https://*.google.com;"
    )
    
    # Add cache control headers
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    
    return response

@login_required
def payment_success(request):
    payment_id = request.GET.get('paymentId')
    product_id = request.GET.get('product_id')
    
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    # Create order (using your existing code)
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
        from .utils.email_utils import send_invoice_email
        send_invoice_email(request, order, invoice)
        
    except Exception as e:
        # Log error but don't stop the flow
        print(f"Error generating invoice: {e}")
    
    # Continue with your existing email sending
    if int(product_id) == 4:
        try:
            # You might want to customize this for stream store
            send_completed_order_email(request, order)
        except Exception as e:
            print(f"Error sending completed order email: {e}")
        
        messages.success(request, "Payment successful! You now have access to the Stream Store.")
        return redirect('STORE:stream_store')
    else:
        try:
            send_pending_order_email(request, order)
        except Exception as e:
            print(f"Error sending pending order email: {e}")
        
        messages.success(request, "Payment successful! Please fill out the required information.")
        return redirect('STORE:order_form', order_id=order.id)

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