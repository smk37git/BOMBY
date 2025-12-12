from django.db import migrations, models
import django.db.models.deletion


def add_related_order_if_not_exists(apps, schema_editor):
    """Only add column if it doesn't exist"""
    connection = schema_editor.connection
    
    if connection.vendor != 'postgresql':
        return  # Skip for SQLite
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'ACCOUNTS_message' AND column_name = 'related_order_id'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE "ACCOUNTS_message" 
                ADD COLUMN "related_order_id" bigint NULL 
                REFERENCES "STORE_order" ("id") DEFERRABLE INITIALLY DEFERRED
            """)
            cursor.execute("""
                CREATE INDEX "ACCOUNTS_message_related_order_id_idx" 
                ON "ACCOUNTS_message" ("related_order_id")
            """)


class Migration(migrations.Migration):
    dependencies = [
        ('ACCOUNTS', '0002_remove_user_fuzeobs_active_and_more'),
        ('STORE', '0006_order_orderform_ordermessage_orderattachment_review'),
    ]

    operations = [
        migrations.RunPython(add_related_order_if_not_exists, migrations.RunPython.noop),
    ]