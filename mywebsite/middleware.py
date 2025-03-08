# mywebsite/middleware.py
from django.conf import settings
from django.http import HttpResponse
import os
import mimetypes
import logging

logger = logging.getLogger(__name__)

class StaticFilesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Precompute full paths to static directories
        self.static_dirs = [settings.STATIC_ROOT]
        if hasattr(settings, 'STATICFILES_DIRS'):
            self.static_dirs.extend(settings.STATICFILES_DIRS)

    def __call__(self, request):
        if request.path.startswith(settings.STATIC_URL):
            relative_path = request.path[len(settings.STATIC_URL):]
            
            # Try all possible static file locations
            for static_dir in self.static_dirs:
                file_path = os.path.join(static_dir, relative_path)
                logger.info(f"Looking for: {file_path}")
                
                if os.path.exists(file_path) and os.path.isfile(file_path):
                    content_type, encoding = mimetypes.guess_type(file_path)
                    if content_type:
                        with open(file_path, 'rb') as f:
                            response = HttpResponse(f.read(), content_type=content_type)
                        return response
            
            # Log if file wasn't found anywhere
            logger.error(f"Static file not found: {relative_path}")
                
        return self.get_response(request)