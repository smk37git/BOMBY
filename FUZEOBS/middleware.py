from django.http import HttpResponse

class CorsOptionsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/fuzeobs/'):
            # Handle OPTIONS preflight
            if request.method == "OPTIONS":
                response = HttpResponse()
                response['Access-Control-Allow-Origin'] = '*'
                response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, X-Session-ID'
                response['Access-Control-Max-Age'] = '86400'
                return response
        
        response = self.get_response(request)
        
        # Add CORS to actual responses
        if request.path.startswith('/fuzeobs/'):
            response['Access-Control-Allow-Origin'] = '*'
        
        return response