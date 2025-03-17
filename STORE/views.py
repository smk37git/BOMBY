from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.db import transaction
from django.db.models import Q
from .models import Order, OrderForm, OrderMessage, OrderAttachment, Review, Product
from .forms import OrderQuestionsForm, MessageForm, ReviewForm
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from django.contrib.auth import get_user_model
import json

def store(request):
    products = [
        Product.objects.get(id=1),  # Basic Package
        Product.objects.get(id=2),  # Standard Package
        Product.objects.get(id=3),  # Premium Package
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

# Orders
@login_required
def purchase_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_active=True)
    
    # Create order
    order = Order.objects.create(
        user=request.user,
        product=product,
        status='pending'
    )
    
    # Update user role to client
    if not request.user.is_client:
        request.user.promote_to_client()
    
    # Redirect to form questions page
    messages.success(request, f"Order created successfully! Please fill out the required information.")
    return redirect('STORE:order_form', order_id=order.id)

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
            
            messages.success(request, "Thank you for your information! Your order is now in progress.")
            return redirect('STORE:order_details', order_id=order.id)
    else:
        form = OrderQuestionsForm()
    
    return render(request, 'STORE/order_form.html', {'form': form, 'order': order})

@login_required
def order_details(request, order_id):
    # Allow both client and admin to view this page
    order = get_object_or_404(Order, id=order_id)
    
    # Only owner or staff can view
    if request.user != order.user and not request.user.is_staff:
        return HttpResponseForbidden("You don't have permission to view this order")
    
    # Handle message form
    if request.method == 'POST':
        form = MessageForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                message = form.save(commit=False)
                message.order = order
                message.sender = request.user
                message.save()
                
                # Process attachments - access them directly from request.FILES
                files = request.FILES.getlist('attachments')
                for file in files:
                    OrderAttachment.objects.create(message=message, file=file)
            
            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'status': 'success'})
            
            return redirect('STORE:order_details', order_id=order.id)
    else:
        form = MessageForm()
    
    # Get all messages for this order
    messages_list = OrderMessage.objects.filter(order=order).order_by('created_at')
    
    # Prepare review form if applicable - only show for completed orders without reviews
    review_form = None
    if order.status == 'completed' and request.user == order.user:
        # Check if review exists using a direct query instead of hasattr
        review_exists = Review.objects.filter(order=order).exists()
        if not review_exists:
            review_form = ReviewForm()
    
    # Get the order's review if it exists, using direct query
    try:
        order_review = Review.objects.get(order=order)
    except Review.DoesNotExist:
        order_review = None
    
    context = {
        'order': order,
        'form': form,
        'messages_list': messages_list,
        'review_form': review_form,
        'order_review': order_review,
    }
    
    return render(request, 'STORE/order_details.html', context)

@login_required
def mark_completed(request, order_id):
    if not request.user.is_staff:
        return HttpResponseForbidden("Only staff can complete orders")
    
    order = get_object_or_404(Order, id=order_id)
    order.status = 'completed'
    order.save()
    
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
    if request.user.is_staff:
        # Staff sees all orders
        orders = Order.objects.all().order_by('-created_at')
    else:
        # Users see their own orders
        orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    return render(request, 'STORE/my_orders.html', {'orders': orders})

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
                order.status = new_status
                order.save()
                updated_count += 1
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