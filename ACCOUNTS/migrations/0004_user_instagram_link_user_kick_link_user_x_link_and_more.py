# Generated by Django 5.1.5 on 2025-02-27 22:18

import ACCOUNTS.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ACCOUNTS', '0003_alter_user_user_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='instagram_link',
            field=models.URLField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='kick_link',
            field=models.URLField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='user',
            name='x_link',
            field=models.URLField(blank=True, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name='user',
            name='profile_picture',
            field=models.ImageField(blank=True, null=True, upload_to='profile_pictures/', validators=[ACCOUNTS.models.validate_image_size, ACCOUNTS.models.validate_image_dimensions]),
        ),
    ]
