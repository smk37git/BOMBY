class StaticFilesMiddleware:
    """
    Middleware to help with static files in production.
    This middleware adds appropriate headers for static files.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add Cache-Control headers for static and media files
        if request.path.startswith('/static/') or request.path.startswith('/media/'):
            response['Cache-Control'] = 'public, max-age=31536000'
            response['X-Content-Type-Options'] = 'nosniff'
        
        return response 