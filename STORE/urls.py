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

    # Stream Store pages
    path('stream-store/', views.stream_store, name='stream_store'),
    path('stream-store/purchase/', views.stream_store_purchase, name='stream_store_purchase'),
    path('stream-asset/<int:asset_id>/', views.stream_asset_detail, name='stream_asset_detail'),
    path('stream-asset/<int:asset_id>/download/', views.download_asset, name='download_asset'),
    path('become-supporter/', views.become_supporter, name='become_supporter'),
    
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

    # Stream Asset Management
    path('admin/stream-assets/', views.stream_asset_management, name='stream_asset_management'),
    path('admin/stream-assets/add/', views.add_stream_asset, name='add_stream_asset'),
    path('admin/stream-assets/edit/<int:asset_id>/', views.edit_stream_asset, name='edit_stream_asset'),
    path('admin/stream-assets/bulk-status-change/', views.bulk_change_asset_status, name='bulk_change_asset_status'),
    path('admin/stream-assets/delete/', views.delete_stream_assets, name='delete_stream_assets'),
    path('upload/chunk/', views.handle_chunked_upload, name='handle_chunked_upload'),

    # Order Management
    path('admin/orders/', views.order_management, name='order_management'),
    path('admin/orders/change-status/', views.admin_change_order_status, name='admin_change_order_status'),
    path('admin/orders/delete/', views.admin_delete_orders, name='admin_delete_orders'),
    path('admin/orders/add/', views.admin_add_order, name='admin_add_order'),

    # Review Management
    path('admin/reviews/', views.review_management, name='review_management'),
    path('admin/reviews/view/<int:review_id>/', views.review_details, name='review_details'),
    path('admin/reviews/edit/<int:review_id>/', views.admin_edit_review, name='admin_edit_review'),
    path('admin/reviews/delete/', views.admin_delete_reviews, name='admin_delete_reviews'),
    path('admin/reviews/add/', views.admin_add_review, name='admin_add_review'),
]