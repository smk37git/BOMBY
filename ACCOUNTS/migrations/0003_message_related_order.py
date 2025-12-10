from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [
        ('ACCOUNTS', '0002_remove_user_fuzeobs_active_and_more'),
        ('STORE', '0006_order_orderform_ordermessage_orderattachment_review'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='related_order',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='STORE.order'),
        ),
    ]