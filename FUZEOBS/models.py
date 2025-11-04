# FUZEOBS/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone

class FuzeOBSUser(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    tier = models.CharField(max_length=20, choices=[
        ('free', 'Free'),
        ('pro', 'Pro'),
        ('lifetime', 'Lifetime')
    ], default='free')
    registration_source = models.CharField(max_length=20, default='fuzeobs')
    app_version = models.CharField(max_length=20, blank=True)
    last_app_login = models.DateTimeField(null=True, blank=True)
    total_app_sessions = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['tier']),
            models.Index(fields=['registration_source']),
            models.Index(fields=['last_app_login']),
        ]

class AIUsage(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
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