from django.http import HttpResponse

# Paths that legitimately need open CORS (OBS browser sources, public donation pages, webhooks)
OPEN_CORS_PREFIXES = (
    '/fuzeobs/ws/',
    '/fuzeobs/widget/',
    '/fuzeobs/widgets/',
    '/fuzeobs/donate/',
    '/fuzeobs/donations/validate/',
    '/fuzeobs/donations/capture/',
    '/fuzeobs/donations/paypal/callback',
    '/fuzeobs/kick-webhook',
    '/fuzeobs/twitch-webhook',
)

# Trusted origins for authenticated API calls
TRUSTED_ORIGINS = (
    'https://bomby.us',
    'https://www.bomby.us',
)


class CorsOptionsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith('/fuzeobs/'):
            return self.get_response(request)

        is_open = any(request.path.startswith(p) for p in OPEN_CORS_PREFIXES)

        if is_open:
            cors_origin = '*'
        else:
            origin = request.META.get('HTTP_ORIGIN', '')
            cors_origin = origin if origin in TRUSTED_ORIGINS else TRUSTED_ORIGINS[0]

        # Handle OPTIONS preflight
        if request.method == 'OPTIONS':
            response = HttpResponse()
            response['Access-Control-Allow-Origin'] = cors_origin
            response['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, X-Session-ID'
            response['Access-Control-Max-Age'] = '86400'
            if cors_origin != '*':
                response['Vary'] = 'Origin'
            return response

        response = self.get_response(request)
        response['Access-Control-Allow-Origin'] = cors_origin
        if cors_origin != '*':
            response['Vary'] = 'Origin'

        return response