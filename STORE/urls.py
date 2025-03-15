from django.urls import path
from . import views

app_name = 'STORE'

urlpatterns = [
    # Main store page
    path('', views.store, name='store'),
    
    # Stream setup service pages
    path('basic-package/', views.basic_package, name='basic_package'),
    path('standard-package/', views.standard_package, name='standard_package'),
    path('premium-package/', views.premium_package, name='premium_package'),
    path('stream-setup/', views.stream_setup, name='stream_setup'),
    
    # Website building pages
    path('basic-website/', views.basic_website, name='basic_website'),
    path('ecommerce-website/', views.ecommerce_website, name='ecommerce_website'),
    path('custom-project/', views.custom_project, name='custom_project'),
    
    # Admin functionality
    path('admin/toggle/<int:product_id>/', views.toggle_product_status, name='toggle_product_status'),

    # Debugging
    path('force-inactive/<int:product_id>/', views.force_inactive, name='force_inactive'),
    path('debug-product/<int:product_id>/', views.debug_product, name='debug_product'),
]