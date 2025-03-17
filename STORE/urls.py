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
    path('stream-store/', views.stream_store, name='stream_store'),
    
    # Website building pages
    path('basic-website/', views.basic_website, name='basic_website'),
    path('ecommerce-website/', views.ecommerce_website, name='ecommerce_website'),
    path('custom-project/', views.custom_project, name='custom_project'),

    # Order pages
    path('purchase/<int:product_id>/', views.purchase_product, name='purchase_product'),
    path('order/<int:order_id>/form/', views.order_form, name='order_form'),
    path('order/<int:order_id>/', views.order_details, name='order_details'),
    path('order/<int:order_id>/complete/', views.mark_completed, name='mark_completed'),
    path('order/<int:order_id>/review/', views.submit_review, name='submit_review'),
    path('my-orders/', views.my_orders, name='my_orders'),
    
    # Admin functionality
    path('admin/toggle/<int:product_id>/', views.toggle_product_status, name='toggle_product_status'),
    path('force-active/<int:product_id>/', views.force_active, name='force_active'),
    path('force-inactive/<int:product_id>/', views.force_inactive, name='force_inactive'),

    # Product Management
    path('admin/products/', views.product_management, name='product_management'),
    path('admin/products/edit/<int:product_id>/', views.edit_product, name='edit_product'),
    path('admin/products/bulk-status-change/', views.bulk_change_product_status, name='bulk_change_product_status'),
    path('products/create/', views.create_product, name='create_product'),
    path('products/delete/', views.delete_products, name='delete_products'),

    # Order Management
    path('admin/orders/', views.order_management, name='order_management'),
    path('admin/orders/change-status/', views.admin_change_order_status, name='admin_change_order_status'),
    path('admin/orders/delete/', views.admin_delete_orders, name='admin_delete_orders'),
    path('admin/orders/add/', views.admin_add_order, name='admin_add_order'),
]