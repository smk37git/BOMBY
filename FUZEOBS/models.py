from django.db import models
from django.conf import settings
from django.utils import timezone
import secrets

class ActiveSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    session_id = models.CharField(max_length=100, unique=True)
    ip_address = models.GenericIPAddressField(null=True)
    started_at = models.DateTimeField(auto_now_add=True)
    last_ping = models.DateTimeField(auto_now=True)
    is_anonymous = models.BooleanField(default=False)
    
    class Meta:
        indexes = [models.Index(fields=['last_ping', 'is_anonymous'])]

class AIUsage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    user_tier = models.CharField(max_length=20, default='free')
    is_anonymous = models.BooleanField(default=False)
    message_count = models.IntegerField(default=1)
    tokens_used = models.IntegerField(default=0)
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    estimated_cost = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    request_type = models.CharField(max_length=50, choices=[
        ('chat', 'Chat'),
        ('benchmark', 'Benchmark Analysis'),
    ], default='chat')
    timestamp = models.DateTimeField(auto_now_add=True)
    response_time = models.FloatField(null=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['request_type']),
            models.Index(fields=['success']),
            models.Index(fields=['is_anonymous']),
        ]

class UserActivity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    activity_type = models.CharField(max_length=50, choices=[
        ('signup', 'Signup'),
        ('login', 'Login'),
        ('template_use', 'Template Use'),
        ('profile_create', 'Profile Create'),
        ('benchmark', 'Benchmark'),
    ])
    details = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=20, choices=[
        ('web', 'Web'),
        ('app', 'Desktop App'),
    ], default='app')
    
    class Meta:
        indexes = [
            models.Index(fields=['user', 'activity_type']),
            models.Index(fields=['timestamp']),
            models.Index(fields=['source']),
        ]

class TierChange(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    from_tier = models.CharField(max_length=20)
    to_tier = models.CharField(max_length=20)
    reason = models.CharField(max_length=100, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]

class FuzeOBSProfile(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    config = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']

class FuzeOBSChat(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    messages = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']

class FuzeOBSQuickstart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    dismissed = models.BooleanField(default=False)
    dismissed_at = models.DateTimeField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if self.dismissed and not self.dismissed_at:
            self.dismissed_at = timezone.now()
        super().save(*args, **kwargs)

class DownloadTracking(models.Model):
    platform = models.CharField(max_length=20, choices=[
        ('windows', 'Windows'),
        ('mac', 'Mac'),
        ('linux', 'Linux')
    ])
    version = models.CharField(max_length=20)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['platform', 'timestamp']),
            models.Index(fields=['timestamp']),
        ]

class WidgetConfig(models.Model):
    WIDGET_TYPES = [
        ('alert_box', 'Alert Box'),
        ('chat_box', 'Chat Box'),
        ('event_list', 'Event List'),
        ('goal_bar', 'Goal Bar'),
    ]
    
    PLATFORMS = [
        ('twitch', 'Twitch'),
        ('youtube', 'YouTube'),
        ('kick', 'Kick'),
        ('facebook', 'Facebook'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES)
    platform = models.CharField(max_length=20, choices=PLATFORMS)
    name = models.CharField(max_length=100)
    config = models.JSONField(default=dict)
    token = models.CharField(max_length=128, unique=True, blank=True)
    gcs_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(64)
        super().save(*args, **kwargs)
    
    class Meta:
        ordering = ['-updated_at']
        unique_together = ['user', 'widget_type', 'platform']
        indexes = [
            models.Index(fields=['token']),
        ]

class MediaLibrary(models.Model):
    MEDIA_TYPES = [
        ('image', 'Image'),
        ('sound', 'Sound'),
        ('video', 'Video'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    media_type = models.CharField(max_length=10, choices=MEDIA_TYPES)
    file_url = models.URLField()
    file_size = models.IntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']

class PlatformConnection(models.Model):
    PLATFORMS = [
        ('twitch', 'Twitch'),
        ('youtube', 'YouTube'),
        ('kick', 'Kick'),
        ('facebook', 'Facebook'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    platform = models.CharField(max_length=20, choices=PLATFORMS)
    platform_username = models.CharField(max_length=100)
    access_token = models.TextField()
    refresh_token = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True)
    connected_at = models.DateTimeField(auto_now_add=True)
    platform_user_id = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        unique_together = ['user', 'platform']

class WidgetEvent(models.Model):
    widget = models.ForeignKey('WidgetConfig', on_delete=models.CASCADE)
    event_type = models.CharField(max_length=50)
    platform = models.CharField(max_length=20)
    enabled = models.BooleanField(default=True)
    config = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['widget', 'event_type', 'platform']