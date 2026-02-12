from django.db import migrations


def remove_old_fields_sqlite(apps, schema_editor):
    """Remove leftover columns that 0002 skipped on SQLite"""
    connection = schema_editor.connection
    if connection.vendor == 'sqlite3':
        # SQLite doesn't support DROP COLUMN before 3.35.0,
        # but Django 4.2+ handles it via table rebuild.
        # We use schema_editor to do it properly.
        User = apps.get_model('ACCOUNTS', 'User')
        columns_to_check = [
            'fuzeobs_active', 'fuzeobs_lifetime',
            'fuzeobs_subscription_end', 'fuzeobs_subscription_id',
            'stripe_customer_id',
        ]
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info('ACCOUNTS_user')")
            existing = {row[1] for row in cursor.fetchall()}

        for col in columns_to_check:
            if col in existing:
                with connection.cursor() as cursor:
                    # Django 4.1+ SQLite supports DROP COLUMN
                    cursor.execute(f'ALTER TABLE "ACCOUNTS_user" DROP COLUMN "{col}"')


class Migration(migrations.Migration):
    dependencies = [
        ('ACCOUNTS', '0003_message_related_order'),
    ]

    operations = [
        migrations.RunPython(remove_old_fields_sqlite, migrations.RunPython.noop),
    ]