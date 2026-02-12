from django.db import migrations


def fix_leftover_columns(apps, schema_editor):
    connection = schema_editor.connection
    columns_to_remove = [
        'fuzeobs_active', 'fuzeobs_lifetime',
        'fuzeobs_subscription_end', 'fuzeobs_subscription_id',
        'stripe_customer_id',
    ]

    if connection.vendor == 'sqlite':
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA table_info('ACCOUNTS_user')")
            existing = {row[1] for row in cursor.fetchall()}
        for col in columns_to_remove:
            if col in existing:
                with connection.cursor() as cursor:
                    cursor.execute(f'ALTER TABLE "ACCOUNTS_user" DROP COLUMN "{col}"')

    elif connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'ACCOUNTS_user'
            """)
            existing = {row[0] for row in cursor.fetchall()}
        for col in columns_to_remove:
            if col in existing:
                with connection.cursor() as cursor:
                    cursor.execute(f'ALTER TABLE "ACCOUNTS_user" DROP COLUMN "{col}"')


class Migration(migrations.Migration):
    dependencies = [
        ('ACCOUNTS', '0003_message_related_order'),
    ]

    operations = [
        migrations.RunPython(fix_leftover_columns, migrations.RunPython.noop),
    ]