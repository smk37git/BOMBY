from django.http import HttpResponseForbidden
from django.shortcuts import redirect
import re

class MediaAccessMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_view(self, request, view_func, view_args, view_kwargs):
        # Skip middleware for non-media URLs
        if not request.path.startswith('/media/'):
            return None
            
        # Always allow access to profile pictures
        if request.path.startswith('/media/profile_pictures/'):
            return None
            
        # For all other media, require login
        if not request.user.is_authenticated:
            return redirect('ACCOUNTS:login')
            
        # Order attachments check
        if request.path.startswith('/media/order_attachments/'):
            # Extract order ID from path (assuming format: /media/order_attachments/{order_id}/...)
            match = re.match(r'/media/order_attachments/(\d+)/', request.path)
            if match:
                order_id = match.group(1)
                # Check if user owns this order or is admin
                from STORE.models import Order
                if not (Order.objects.filter(id=order_id, user=request.user).exists() or request.user.is_staff):
                    return HttpResponseForbidden("You don't have permission to access this file")
                    
        # Stream assets check
        if request.path.startswith('/media/stream_assets/'):
            # Check if user can access stream store
            from STORE.views import user_can_access_stream_store
            if not user_can_access_stream_store(request.user):
                return HttpResponseForbidden("You don't have permission to access stream assets")
                
        # Chunk uploads check (admin only)
        if request.path.startswith('/media/chunk_uploads/'):
            if not request.user.is_staff:
                return HttpResponseForbidden("You don't have permission to access this area")
                
        return None