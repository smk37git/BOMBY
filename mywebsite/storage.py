from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os
import logging

logger = logging.getLogger(__name__)

class CustomFileSystemStorage(FileSystemStorage):
    def url(self, name):
        # Always allow profile pictures to be public
        if name.startswith('profile_pictures/'):
            return f'/media/{name}'
        
        # Check if this is a stream asset or order attachment
        # These should be accessible only through protected views
        if name.startswith(('stream_assets/', 'order_attachments/')):
            # Return route to protected view
            return f'/protected-media/{name}'
            
        # Default handling for other files
        return super().url(name)