#!/usr/bin/env python
"""
Script to help debug static file issues.
This script will print detailed information about your static files configuration.
"""
import os
import sys
import django
from pathlib import Path

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mywebsite.settings')
django.setup()

from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management.commands.findstatic import Command as FindStaticCommand

def debug_static_files():
    """Print detailed information about static files configuration."""
    print("\n=== Django Static Files Configuration ===")
    print(f"STATIC_URL: {settings.STATIC_URL}")
    print(f"STATIC_ROOT: {settings.STATIC_ROOT}")
    print(f"STATICFILES_DIRS: {settings.STATICFILES_DIRS}")
    print(f"STATICFILES_FINDERS: {settings.STATICFILES_FINDERS}")
    print(f"DEBUG: {settings.DEBUG}")
    
    print("\n=== Static Files Directory Structure ===")
    static_root = Path(settings.STATIC_ROOT)
    if static_root.exists():
        print(f"STATIC_ROOT exists: {static_root}")
        # Count files by extension
        extensions = {}
        total_files = 0
        for root, _, files in os.walk(static_root):
            for file in files:
                total_files += 1
                ext = os.path.splitext(file)[1].lower()
                extensions[ext] = extensions.get(ext, 0) + 1
        
        print(f"Total files in STATIC_ROOT: {total_files}")
        print("Files by extension:")
        for ext, count in sorted(extensions.items(), key=lambda x: x[1], reverse=True):
            print(f"  {ext}: {count}")
        
        # List CSS files specifically
        print("\nCSS files:")
        css_files = []
        for root, _, files in os.walk(static_root):
            for file in files:
                if file.endswith('.css'):
                    rel_path = os.path.relpath(os.path.join(root, file), static_root)
                    css_files.append(rel_path)
        
        for css_file in sorted(css_files)[:10]:  # Show first 10 CSS files
            print(f"  {css_file}")
        
        if len(css_files) > 10:
            print(f"  ... and {len(css_files) - 10} more CSS files")
    else:
        print(f"STATIC_ROOT does not exist: {static_root}")
    
    print("\n=== Static Files Finder Test ===")
    # Try to find a few common static files
    find_static = FindStaticCommand()
    test_files = ['admin/css/base.css', 'css/style.css', 'js/main.js']
    for file in test_files:
        try:
            result = find_static.find_location(file)
            print(f"Finding '{file}': {result}")
        except Exception as e:
            print(f"Finding '{file}': Not found ({e})")
    
    return True

if __name__ == '__main__':
    success = debug_static_files()
    sys.exit(0 if success else 1) 