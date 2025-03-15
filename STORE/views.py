from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test
import json
from .models import Product

def store(request):
    products = Product.objects.all()
    return render(request, 'STORE/store.html', {'products': products})

# Stream setup service views
def basic_package(request):
    product = get_object_or_404(Product, id=1)
    return render(request, 'STORE/basic_package.html', {'product': product})

def standard_package(request):
    product = get_object_or_404(Product, id=2)
    return render(request, 'STORE/standard_package.html', {'product': product})

def premium_package(request):
    product = get_object_or_404(Product, id=3)
    return render(request, 'STORE/premium_package.html', {'product': product})

def stream_setup(request):
    return render(request, 'STORE/stream_setup.html')

# Website building views
def basic_website(request):
    product = get_object_or_404(Product, id=5)
    return render(request, 'STORE/basic_website.html', {'product': product})

def ecommerce_website(request):
    product = get_object_or_404(Product, id=6)
    return render(request, 'STORE/ecommerce_website.html', {'product': product})

def custom_project(request):
    product = get_object_or_404(Product, id=7)
    return render(request, 'STORE/custom_project.html', {'product': product})

# Admin Views
@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def toggle_product_status(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    
    # Parse the request body to get the active status
    try:
        data = json.loads(request.body)
        is_active = data.get('active', not product.is_active)
    except json.JSONDecodeError:
        # If no JSON body, just toggle the current state
        is_active = not product.is_active
    
    # Update the product status
    product.is_active = is_active
    product.save()
    
    return JsonResponse({
        'success': True,
        'product_id': product_id,
        'is_active': product.is_active,
        'message': f'Product {product_id} status updated successfully'
    })