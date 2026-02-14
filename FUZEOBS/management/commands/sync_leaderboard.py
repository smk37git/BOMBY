"""
Management command to sync leaderboard hours for all opted-in users.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from FUZEOBS.models import LeaderboardEntry
from FUZEOBS.leaderboard import _sync_user_hours


class Command(BaseCommand):
    help = 'Sync stream hours for all opted-in leaderboard users'

    def handle(self, *args, **options):
        entries = LeaderboardEntry.objects.filter(opted_in=True).select_related('user')
        count = entries.count()
        self.stdout.write(f'[LEADERBOARD] Syncing {count} users...')

        for i, entry in enumerate(entries, 1):
            try:
                # Save current rank as previous
                current_rank = (
                    LeaderboardEntry.objects
                    .filter(opted_in=True, total_stream_minutes__gt=entry.total_stream_minutes)
                    .count() + 1
                )
                entry.previous_rank = current_rank

                # Fetch fresh hours
                total, weekly, monthly = _sync_user_hours(entry.user)
                entry.total_stream_minutes = total
                entry.weekly_stream_minutes = weekly
                entry.monthly_stream_minutes = monthly
                entry.last_synced = timezone.now()
                entry.save()

                self.stdout.write(f'  [{i}/{count}] {entry.user.username}: {total}min total, {weekly}min week, {monthly}min month')
            except Exception as e:
                self.stderr.write(f'  [{i}/{count}] {entry.user.username}: ERROR - {e}')

        self.stdout.write(self.style.SUCCESS(f'[LEADERBOARD] Done. Synced {count} users.'))