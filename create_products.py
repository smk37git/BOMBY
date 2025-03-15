import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mywebsite.settings')
django.setup()

from STORE.models import Product

products = [
    (1, {'name': 'Basic Package', 'price': 25.00, 'is_active': True}),
    (2, {'name': 'Standard Package', 'price': 45.00, 'is_active': True}),
    (3, {'name': 'Premium Package', 'price': 75.00, 'is_active': True}),
    (5, {'name': 'Basic Website', 'price': 150.00, 'is_active': True}),
    (6, {'name': 'E-Commerce Website', 'price': 350.00, 'is_active': True}),
    (7, {'name': 'Custom Project', 'description': 'Custom', 'is_active': True})
]

for pid, defaults in products:
    obj, created = Product.objects.get_or_create(id=pid, defaults=defaults)
    print(f"{'Created' if created else 'Already exists'}: {obj.name}")