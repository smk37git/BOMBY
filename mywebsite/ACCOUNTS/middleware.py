from django.utils.deprecation import MiddlewareMixin
from django.conf import settings

class PurchaseTrackingMiddleware(MiddlewareMixin):
    """
    Middleware to track purchases and upgrade users to Client status when needed.
    You'll need to call this from your purchase completion view.
    """
    
    def __call__(self, request):
        response = self.get_response(request)
        return response
    
    @staticmethod
    def upgrade_to_client(user):
        """
        Call this method from your purchase completion view
        to upgrade a user to Client status.
        """
        if user.is_authenticated and user.is_member():
            user.promote_to_client()
            return True
        return False