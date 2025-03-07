#!/usr/bin/env python
"""
Script to check the database connection.
Run this after deployment to verify that your application can connect to the database.
"""

import os
import sys
import django
from django.db import connections
from django.db.utils import OperationalError

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mywebsite.settings')
django.setup()

def check_connection():
    """Check if the database connection is working."""
    try:
        # Try to get a cursor from the default database connection
        connection = connections['default']
        connection.cursor()
        print("✅ Database connection successful!")
        
        # Get database info
        db_name = connection.settings_dict['NAME']
        db_engine = connection.settings_dict['ENGINE']
        db_host = connection.settings_dict['HOST']
        
        print(f"Database engine: {db_engine}")
        print(f"Database name: {db_name}")
        print(f"Database host: {db_host}")
        
        # Check if tables exist
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            table_count = cursor.fetchone()[0]
            print(f"Number of tables: {table_count}")
            
        return True
    except OperationalError as e:
        print(f"❌ Database connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ An error occurred: {e}")
        return False

if __name__ == "__main__":
    print("Checking database connection...")
    success = check_connection()
    sys.exit(0 if success else 1) 