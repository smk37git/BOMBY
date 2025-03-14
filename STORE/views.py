from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, user_passes_test

def store(request):
    """Main store view that displays all available products."""
    return render(request, 'STORE/store.html')

# Stream setup service views
def basic_package(request):
    """View for the Basic stream package product page."""
    return render(request, 'STORE/basic_package.html')

def standard_package(request):
    """View for the Standard stream package product page."""
    return render(request, 'STORE/standard_package.html')

def premium_package(request):
    """View for the Premium stream package product page."""
    return render(request, 'STORE/premium_package.html')

def stream_setup(request):
    """View for the Stream Setup showcase page."""
    return render(request, 'STORE/stream_setup.html')

# Website building views
def basic_website(request):
    """View for the Basic Website product page."""
    return render(request, 'STORE/basic_website.html')

def ecommerce_website(request):
    """View for the E-Commerce Website product page."""
    return render(request, 'STORE/ecommerce_website.html')

def custom_project(request):
    """View for the Custom Project product page."""
    return render(request, 'STORE/custom_project.html')

# Admin functionality
@require_POST
@login_required
@user_passes_test(lambda u: u.is_staff)
def toggle_product_status(request, product_id):
    """
    Toggle the active status of a product.
    This is a simplified implementation that doesn't use a database.
    In a real scenario, you would update a Product model in your database.
    """
    
    return JsonResponse({
        'success': True,
        'product_id': product_id,
        'message': f'Product {product_id} status toggled successfully'
    })