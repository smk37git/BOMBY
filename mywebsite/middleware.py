# mywebsite/middleware.py
from django.conf import settings
from django.http import HttpResponse
import os
import mimetypes

import logging
logger = logging.getLogger(__name__)
# In __call__:
logger.info(f"Looking for static file: {file_path}")

class StaticFilesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith(settings.STATIC_URL):
            path = request.path[len(settings.STATIC_URL):]
            file_path = os.path.join(settings.STATIC_ROOT, path)
            
            if os.path.exists(file_path) and os.path.isfile(file_path):
                content_type, encoding = mimetypes.guess_type(file_path)
                if content_type:
                    with open(file_path, 'rb') as f:
                        response = HttpResponse(f.read(), content_type=content_type)
                    return response
                
        return self.get_response(request)