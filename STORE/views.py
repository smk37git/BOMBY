from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
import json
from .models import Product
from datetime import datetime

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
    # Always get fresh data from database
    product = Product.objects.get(id=1)
    
    # Disable caching
    response = render(request, 'STORE/basic_package.html', {'product': product})
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def standard_package(request):
    product = Product.objects.get(id=2)
    
    # Add cache control headers
    response = render(request, 'STORE/standard_package.html', {'product': product})
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def premium_package(request):
    product = Product.objects.get(id=3)
    response = render(request, 'STORE/premium_package.html', {'product': product})
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def stream_setup(request):
    # Add cache control headers like the other views
    response = render(request, 'STORE/stream_setup.html')
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def basic_website(request):
    product = Product.objects.get(id=5)
    response = render(request, 'STORE/basic_website.html', {'product': product})
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def ecommerce_website(request):
    product = Product.objects.get(id=6)
    response = render(request, 'STORE/ecommerce_website.html', {'product': product})
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate' 
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

def custom_project(request):
    product = Product.objects.get(id=7)
    response = render(request, 'STORE/custom_project.html', {'product': product})
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    return response

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