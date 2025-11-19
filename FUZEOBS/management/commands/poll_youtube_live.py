from django.core.management.base import BaseCommand
from FUZEOBS.models import PlatformConnection
from FUZEOBS.youtube_pubsub import poll_super_chats
from django.utils import timezone
import time

class Command(BaseCommand):
    help = 'Poll YouTube super chats for LIVE users only'

    def handle(self, *args, **options):
        self.stdout.write('YouTube live polling started')
        
        while True:
            # Get all YouTube connections (removed activity filter)
            connections = PlatformConnection.objects.filter(platform='youtube')
            
            live_count = 0
            for conn in connections:
                if poll_super_chats(conn.access_token, conn.user.id):
                    live_count += 1
            
            self.stdout.write(f'Checked {connections.count()} users, {live_count} live')
            time.sleep(60)