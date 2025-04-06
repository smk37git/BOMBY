from django.utils.deprecation import MiddlewareMixin
from .models import PageView, Product, ProductInteraction
import re

class AnalyticsMiddleware(MiddlewareMixin):
    """Middleware to track page views and product interactions"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.async_mode = False
        # Compile URL patterns to match
        self.product_patterns = [
            re.compile(r'^/store/basic-package/$'),
            re.compile(r'^/store/standard-package/$'),
            re.compile(r'^/store/premium-package/$'),
            re.compile(r'^/store/stream-asset/(\d+)/$'),
            re.compile(r'^/store/basic-website/$'),
            re.compile(r'^/store/ecommerce-website/$'),
            re.compile(r'^/store/custom-project/$'),
        ]
        
    def process_request(self, request):
        """Process incoming request before it reaches the view"""
        # Only track GET requests
        if request.method != 'GET':
            return None
            
        # Skip admin pages and static files
        if request.path.startswith('/admin/') or request.path.startswith('/static/'):
            return None
            
        # Skip AJAX requests
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return None
        
        try:
            # Get user or session ID
            user = request.user if request.user.is_authenticated else None
            session_id = request.session.session_key
            
            # If no session key exists yet, create one
            if not session_id:
                request.session.create()
                session_id = request.session.session_key
                
            # Get referrer
            referrer = request.META.get('HTTP_REFERER', '')
            
            # Check if this is a product page
            product = None
            for pattern in self.product_patterns:
                match = pattern.match(request.path)
                if match:
                    # Try to identify the product
                    if 'basic-package' in request.path:
                        product = Product.objects.filter(id=1).first()
                    elif 'standard-package' in request.path:
                        product = Product.objects.filter(id=2).first()
                    elif 'premium-package' in request.path:
                        product = Product.objects.filter(id=3).first()
                    elif 'basic-website' in request.path:
                        product = Product.objects.filter(id=5).first()
                    elif 'ecommerce-website' in request.path:
                        product = Product.objects.filter(id=6).first()
                    elif 'custom-project' in request.path:
                        product = Product.objects.filter(id=7).first()
                    elif 'stream-asset' in request.path and len(match.groups()) > 0:
                        asset_id = match.group(1)
                        # For stream assets, we'd need a different approach
                        # This is just a placeholder
                        continue
                    
                    if product:
                        # Track the product view
                        PageView.objects.create(
                            product=product,
                            user=user,
                            session_id=session_id,
                            referrer=referrer
                        )
                        
                        # Also log a product interaction
                        ProductInteraction.objects.create(
                            product=product,
                            user=user,
                            session_id=session_id,
                            interaction_type='view'
                        )
                        break
            
            # If not a product page, log a general page view
            if not product:
                PageView.objects.create(
                    url=request.path,
                    user=user,
                    session_id=session_id,
                    referrer=referrer
                )
        except Exception as e:
            # Don't break the site if analytics tracking fails
            print(f"Analytics tracking error: {e}")
            
        return None