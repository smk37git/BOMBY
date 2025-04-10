from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
import os
import re
from google.cloud import storage
import logging

logger = logging.getLogger(__name__)

class GCSMediaMiddleware(MiddlewareMixin):
    """Middleware to handle media file serving, especially for GCS files in development"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.media_url = settings.MEDIA_URL
        self.is_cloud_run = bool(os.environ.get('K_SERVICE'))
        
    def process_response(self, request, response):
        """Process response to intercept GCS media requests in development"""
        
        # Skip if in Cloud Run (mounted bucket)
        if self.is_cloud_run:
            return response
            
        # Skip if not a media URL or if response is already successful
        if not request.path.startswith(self.media_url) or response.status_code < 400:
            return response
            
        # For 404 errors on media URLs, try to serve from GCS
        try:
            path = request.path[len(self.media_url):]  # Remove media prefix
            
            # Skip if not a stream asset path
            if not path.startswith('stream_assets/'):
                return response
                
            # Initialize the GCS client
            client = storage.Client()
            bucket = client.bucket('bomby-user-uploads')
            
            # Get the blob
            blob = bucket.blob(path)
            
            if not blob.exists():
                return response  # Keep the 404 if not in GCS either
            
            # Download the content
            content = blob.download_as_bytes()
            
            # Set the content type based on file extension
            content_type = 'application/octet-stream'  # Default
            if path.endswith('.mp4'):
                content_type = 'video/mp4'
            elif path.endswith('.jpg') or path.endswith('.jpeg'):
                content_type = 'image/jpeg'
            elif path.endswith('.png'):
                content_type = 'image/png'
            elif path.endswith('.gif'):
                content_type = 'image/gif'
            
            # Return the response
            new_response = HttpResponse(content, content_type=content_type)
            new_response['Content-Disposition'] = f'inline; filename="{os.path.basename(path)}"'
            return new_response
            
        except Exception as e:
            logger.error(f"Error serving GCS media file: {str(e)}")
            return response
