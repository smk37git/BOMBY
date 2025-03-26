from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from .validators import validate_clean_content
from PIL import Image
import io
import json
from django.conf import settings

# Keep validate_image_size and validate_image_dimensions functions
def validate_image_size(file):
    max_size = 5 * 1024 * 1024
    if file.size > max_size:
        raise ValidationError(f"Image size cannot exceed 10MB. Your file is {file.size/(1024*1024):.2f}MB")

def validate_image_dimensions(file):
    img = Image.open(file)
    
    max_width = 800
    max_height = 800
    
    if img.width > max_width or img.height > max_height:
        raise ValidationError(f"Image dimensions cannot exceed 800x800 pixels. Your image is {img.width}x{img.height} pixels.")

class User(AbstractUser):
    
    class UserType(models.TextChoices):
        MEMBER = 'MEMBER', 'Member'
        SUPPORTER = 'SUPPORTER', 'Supporter'
        CLIENT = 'CLIENT', 'Client'
        ADMIN = 'ADMIN', 'Admin'

    class Meta:
        db_table = 'ACCOUNTS_user'

    # Rest of model stays the same
    user_type = models.CharField(
        max_length=10,
        choices=UserType.choices,
        default=UserType.MEMBER,
    )
    
    # All existing fields and methods remain unchanged
    profile_picture = models.ImageField(
        upload_to='profile_pictures/', 
        blank=True, 
        null=True,
        validators=[validate_image_size, validate_image_dimensions]
    )
    
    bio = models.TextField(max_length = 500, blank=True, null=True, validators=[validate_clean_content])
    youtube_link_1 = models.URLField(max_length=255, blank=True, null=True)
    youtube_link_2 = models.URLField(max_length=255, blank=True, null=True)
    twitch_link = models.URLField(max_length=255, blank=True, null=True)
    github_link = models.URLField(max_length=255, blank=True, null=True)
    twitter_link = models.URLField(max_length=255, blank=True, null=True)
    kick_link = models.URLField(max_length=255, blank=True, null=True)
    instagram_link = models.URLField(max_length=255, blank=True, null=True)
    _promo_links = models.TextField(blank=True, null=True)
    
    # Existing Methods
    def set_promo_links(self, links):
        self._promo_links = json.dumps(links) if links else None

    def get_promo_links(self):
        return json.loads(self._promo_links) if self._promo_links else []

    promo_links = property(get_promo_links, set_promo_links)

    @property
    def is_member(self):
        return self.user_type == self.UserType.MEMBER

    @property
    def is_supporter(self):
        return self.user_type == self.UserType.SUPPORTER

    @property
    def is_client(self):
        return self.user_type == self.UserType.CLIENT

    @property
    def is_admin_user(self):
        return self.user_type == self.UserType.ADMIN

    def promote_to_supporter(self):
        if self.user_type == self.UserType.MEMBER:
            self.user_type = self.UserType.SUPPORTER
            self.save()

    def promote_to_client(self):
        if self.user_type in [self.UserType.MEMBER, self.UserType.SUPPORTER]:
            self.user_type = self.UserType.CLIENT
            self.save()
            
    def save(self, *args, **kwargs):
        # Existing save method remains unchanged
        if self.pk is not None:
            try:
                old_instance = User.objects.get(pk=self.pk)
                if old_instance.profile_picture != self.profile_picture and self.profile_picture:
                    img = Image.open(self.profile_picture)
                    
                    max_width, max_height = 800, 800
                    if img.width > max_width or img.height > max_height:
                        if img.width > img.height:
                            new_width = max_width
                            new_height = int(img.height * (max_width / img.width))
                        else:
                            new_height = max_height
                            new_width = int(img.width * (max_height / img.height))
                        
                        img = img.resize((new_width, new_height), Image.LANCZOS)
                        
                        buffer = io.BytesIO()
                        img_format = self.profile_picture.name.split('.')[-1].upper()
                        if img_format == 'JPG':
                            img_format = 'JPEG'
                        img.save(buffer, format=img_format)
                        
                        from django.core.files.base import ContentFile
                        self.profile_picture.save(
                            self.profile_picture.name,
                            ContentFile(buffer.getvalue()),
                            save=False
                        )
            except User.DoesNotExist:
                pass
            
        super().save(*args, **kwargs)

# Messaging System
class Message(models.Model):
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    recipient = models.ForeignKey(User, related_name='received_messages', on_delete=models.CASCADE)
    content = models.TextField(validators=[validate_clean_content])
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    related_order = models.ForeignKey('STORE.Order', null=True, blank=True, on_delete=models.CASCADE)
    conversation = models.ForeignKey('Conversation', related_name='messages', on_delete=models.CASCADE, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Message from {self.sender} to {self.recipient} at {self.created_at}"

class Conversation(models.Model):
    participants = models.ManyToManyField(User, related_name='conversations')
    last_message = models.ForeignKey(Message, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
    
    def __str__(self):
        return f"Conversation {self.id}"
    
    def other_participant(self, user):
        return self.participants.exclude(id=user.id).first()

# Email for unread messages
class MessageNotification(models.Model):
    """
    Tracks when unread message notifications were last sent to users
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='message_notification')
    last_notified = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return f"Message notification for {self.user.username}"