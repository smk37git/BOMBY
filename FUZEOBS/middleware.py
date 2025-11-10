class CorsOptionsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        # Add CORS headers to all /fuzeobs/ responses
        if request.path.startswith('/fuzeobs/'):
            response['Access-Control-Allow-Origin'] = '*'
            if request.method == "OPTIONS":
                response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, X-Session-ID'
                response['Access-Control-Max-Age'] = '86400'
        
        return response