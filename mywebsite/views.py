# mywebsite/views.py
from django.http import HttpResponse
from django.conf import settings
import os

def test_view(request):
    """Simple view that works without database or complex logic"""
    return HttpResponse(
        "<html><body><h1>Test Page</h1><p>This page works!</p></body></html>",
        content_type="text/html"
    )

def static_test(request, path):
    """Direct file server for static files during debugging"""
    filepath = os.path.join(settings.STATIC_ROOT, path)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        with open(filepath, 'rb') as f:
            content = f.read()
        content_type = 'text/css' if path.endswith('.css') else 'application/javascript' if path.endswith('.js') else 'image/jpeg' if path.endswith('.jpg') else 'image/png' if path.endswith('.png') else 'text/plain'
        return HttpResponse(content, content_type=content_type)
    return HttpResponse(f"File not found: {path}", status=404)

def health_check(request):
    """Health check endpoint"""
    try:
        return HttpResponse("OK - Service is running")
    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=500)