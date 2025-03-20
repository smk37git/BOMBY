from django.core.management.base import BaseCommand
from STORE.models import Product

class Command(BaseCommand):
    help = 'Adds Stream Store product'

    def handle(self, *args, **options):
        product, created = Product.objects.get_or_create(
            id=4,
            defaults={
                'name': 'Stream Store',
                'price': 10.00,
                'description': 'Access to streaming assets',
                'is_active': True
            }
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Successfully created Stream Store product'))
        else:
            self.stdout.write(self.style.WARNING('Stream Store product already exists'))