from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from allauth.socialaccount.models import SocialAccount
from django.db.models import Count

User = get_user_model()

class Command(BaseCommand):
    help = 'Merge duplicate user accounts with same email'

    def handle(self, *args, **options):
        # Find duplicate emails
        duplicates = User.objects.values('email').annotate(count=Count('id')).filter(count__gt=1)
        
        if not duplicates:
            self.stdout.write(self.style.SUCCESS('No duplicate emails found'))
            return
        
        for dup in duplicates:
            email = dup['email']
            users = User.objects.filter(email=email).order_by('date_joined')
            
            # Keep oldest user
            correct_user = users.first()
            duplicate_users = users.exclude(id=correct_user.id)
            
            self.stdout.write(f"\nEmail: {email}")
            self.stdout.write(f"  Keeping: {correct_user.username} (ID: {correct_user.id})")
            
            for dup_user in duplicate_users:
                self.stdout.write(f"  Deleting: {dup_user.username} (ID: {dup_user.id})")
                
                # Move social accounts
                social_accounts = SocialAccount.objects.filter(user=dup_user)
                for sa in social_accounts:
                    sa.user = correct_user
                    sa.save()
                    self.stdout.write(f"    Moved social account: {sa.provider}")
                
                dup_user.delete()
        
        self.stdout.write(self.style.SUCCESS('\nMerge complete!'))