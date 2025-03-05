from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from .validators import validate_clean_content
from PIL import Image
import io
import json

def validate_image_size(file):
    # 10MB limit
    max_size = 10 * 1024 * 1024
    if file.size > max_size:
        raise ValidationError(f"Image size cannot exceed 10MB. Your file is {file.size/(1024*1024):.2f}MB")

def validate_image_dimensions(file):
    # Open the image
    img = Image.open(file)
    
    # Check dimensions
    max_width = 800
    max_height = 800
    
    if img.width > max_width or img.height > max_height:
        raise ValidationError(f"Image dimensions cannot exceed 800x800 pixels. Your image is {img.width}x{img.height} pixels.")

# User Model
class User(AbstractUser):
    class UserType(models.TextChoices):
        MEMBER = 'MEMBER', 'Member'
        SUPPORTER = 'SUPPORTER', 'Supporter'
        CLIENT = 'CLIENT', 'Client'
        ADMIN = 'ADMIN', 'Admin'

    user_type = models.CharField(
        max_length=10,
        choices=UserType.choices,
        default=UserType.MEMBER,
    )

    # Profile picture with validation
    profile_picture = models.ImageField(
        upload_to='profile_pictures/', 
        blank=True, 
        null=True,
        validators=[validate_image_size, validate_image_dimensions]
    )
    
    # Bio
    bio = models.TextField(max_length = 500, blank=True, null=True, validators=[validate_clean_content])
    
    # Social links
    youtube_link_1 = models.URLField(max_length=255, blank=True, null=True)
    youtube_link_2 = models.URLField(max_length=255, blank=True, null=True)
    twitch_link = models.URLField(max_length=255, blank=True, null=True)
    github_link = models.URLField(max_length=255, blank=True, null=True)
    twitter_link = models.URLField(max_length=255, blank=True, null=True)
    kick_link = models.URLField(max_length=255, blank=True, null=True)
    instagram_link = models.URLField(max_length=255, blank=True, null=True)

    # Promo links storage
    _promo_links = models.TextField(blank=True, null=True)

    def set_promo_links(self, links):
        """Store promo links as JSON"""
        self._promo_links = json.dumps(links) if links else None

    def get_promo_links(self):
        """Retrieve promo links from JSON"""
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
        if self.user_type == self.UserType.MEMBER:
            self.user_type = self.UserType.CLIENT
            self.save()
            
    def save(self, *args, **kwargs):
        # If this is a new instance or the profile picture has changed
        if self.pk is not None:
            try:
                old_instance = User.objects.get(pk=self.pk)
                if old_instance.profile_picture != self.profile_picture and self.profile_picture:
                    # Resize image if needed
                    img = Image.open(self.profile_picture)
                    
                    # Check if resize is needed
                    max_width, max_height = 800, 800
                    if img.width > max_width or img.height > max_height:
                        # Calculate new dimensions while maintaining aspect ratio
                        if img.width > img.height:
                            new_width = max_width
                            new_height = int(img.height * (max_width / img.width))
                        else:
                            new_height = max_height
                            new_width = int(img.width * (max_height / img.height))
                        
                        # Resize image
                        img = img.resize((new_width, new_height), Image.LANCZOS)
                        
                        # Save the resized image back to the field
                        buffer = io.BytesIO()
                        img_format = self.profile_picture.name.split('.')[-1].upper()
                        if img_format == 'JPG':
                            img_format = 'JPEG'
                        img.save(buffer, format=img_format)
                        
                        # Replace the file content
                        from django.core.files.base import ContentFile
                        self.profile_picture.save(
                            self.profile_picture.name,
                            ContentFile(buffer.getvalue()),
                            save=False
                        )
            except User.DoesNotExist:
                pass
            
        super().save(*args, **kwargs)