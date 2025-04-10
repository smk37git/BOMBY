from django.db import models
from django.utils import timezone

# Create your models here.
class Announcement(models.Model):
    message = models.CharField(max_length=255)
    link = models.URLField(blank=True, null=True)
    link_text = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    bg_color = models.CharField(max_length=50, default='#7b00fe', help_text="Use color name or hex code")
    text_color = models.CharField(max_length=50, default='white', help_text="Use color name or hex code")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.message[:50]
    
    class Meta:
        ordering = ['-created_at']