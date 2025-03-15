from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
import json
from .models import Product
from datetime import datetime
from django.views.decorators.csrf import csrf_exempt

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
@csrf_exempt
@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def toggle_product_status(request, product_id):
    # Get product
    product = Product.objects.get(id=product_id)
    
    # Parse the request body to get the active status
    try:
        data = json.loads(request.body)
        is_active = data.get('active', not product.is_active)
    except json.JSONDecodeError:
        # If no JSON body, just toggle the current state
        is_active = not product.is_active
    
    # Set and save (simpler approach)
    product.is_active = is_active
    product.save()
    
    # Double check by fetching again
    fresh_product = Product.objects.get(id=product_id)
    
    # Force Django to commit the transaction
    from django.db import transaction
    transaction.commit()
    
    return JsonResponse({
        'success': True,
        'product_id': product_id,
        'original_is_active': product.is_active,
        'fresh_is_active': fresh_product.is_active,
        'requested_state': is_active,
        'message': f'Product {product_id} status updated successfully'
    })

def debug_product(request, product_id):
    # Try ORM approach only - skip direct SQL
    try:
        product = Product.objects.get(id=product_id)
        
        # Check direct database for table names first
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            tables = [row[0] for row in cursor.fetchall()]
        
        return JsonResponse({
            'product_from_orm': {
                'id': product.id,
                'name': product.name,
                'is_active': product.is_active,
            },
            'available_tables': tables,
            'model_table_name': Product._meta.db_table
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'error_type': type(e).__name__
        }, status=500)