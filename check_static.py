#!/usr/bin/env python
"""
Script to check if static files are being collected correctly.
Run this script after building the Docker image to verify static files.
"""
import os
import sys
from pathlib import Path

def check_static_files():
    """Check if static files are being collected correctly."""
    # Get the base directory
    base_dir = Path(__file__).resolve().parent
    
    # Check if staticfiles directory exists
    staticfiles_dir = os.path.join(base_dir, 'staticfiles')
    if not os.path.exists(staticfiles_dir):
        print(f"ERROR: Static files directory '{staticfiles_dir}' does not exist!")
        return False
    
    # Count the number of files in the staticfiles directory
    file_count = sum(len(files) for _, _, files in os.walk(staticfiles_dir))
    print(f"Found {file_count} static files in '{staticfiles_dir}'")
    
    # Check for CSS files specifically
    css_files = []
    for root, _, files in os.walk(staticfiles_dir):
        for file in files:
            if file.endswith('.css'):
                css_files.append(os.path.join(root, file))
    
    print(f"Found {len(css_files)} CSS files:")
    for css_file in css_files:
        print(f"  - {os.path.relpath(css_file, staticfiles_dir)}")
    
    return True

if __name__ == '__main__':
    success = check_static_files()
    sys.exit(0 if success else 1) 