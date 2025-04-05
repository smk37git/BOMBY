from django.db import models
from django.conf import settings
from django.utils import timezone
import os
import pytz

# Store Page Models
class Product(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name

# Order Models
class Order(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    product = models.ForeignKey('Product', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    due_date = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    payment_id = models.CharField(max_length=100, blank=True, null=True)
    is_paid = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        # Set due date when status changes to in_progress based on product type
        if self.status == 'in_progress' and not self.due_date:
            # Default is no due date
            days = None
            
            # Set different timers based on package type
            if self.product_id == 1:  # Basic Package
                days = 3
            elif self.product_id == 2:  # Standard Package
                days = 5
            elif self.product_id == 3:  # Premium Package
                days = 7
                
            # Only set due date if days is specified
            if days is not None:
                self.due_date = timezone.now() + timezone.timedelta(days=days)
        
        # Set completed_at when status changes to completed
        if self.status == 'completed' and not self.completed_at:
            self.completed_at = timezone.now()
            
        super().save(*args, **kwargs)

class OrderForm(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='form')
    question1 = models.TextField()
    question2 = models.TextField()
    question3 = models.TextField()
    question4 = models.TextField()
    question5 = models.TextField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    
class OrderMessage(models.Model):
    order = models.ForeignKey('Order', on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False)  # Add this line
    
    def save(self, *args, **kwargs):
        # Keep existing save logic
        if not self.id:
            # Get user's timezone if available, otherwise use server's timezone
            user_timezone = getattr(self.sender, 'timezone', None)
            if user_timezone:
                try:
                    # Apply user's timezone to created_at
                    self.created_at = timezone.now().astimezone(pytz.timezone(user_timezone))
                except (pytz.exceptions.UnknownTimeZoneError, AttributeError):
                    # Fall back to default behavior if timezone is invalid
                    pass
            
            # Filter message content for inappropriate language
            from ACCOUNTS.validators import validate_clean_content
            self.message = validate_clean_content(self.message)
        
        super().save(*args, **kwargs)
    
class OrderAttachment(models.Model):
    message = models.ForeignKey(OrderMessage, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='order_attachments/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    @property
    def filename(self):
        return os.path.basename(self.file.name)

class Review(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='review')
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

# Stream Store Models
class StreamAsset(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    file_path = models.CharField(max_length=255)  # Path to main file in bucket
    thumbnail = models.ImageField(upload_to='stream_assets/thumbnails/', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class AssetVersion(models.Model):
    VERSION_TYPES = (
        ('static', 'Static'),
        ('animated', 'Animated'),
        ('video', 'Video'),
    )
    
    asset = models.ForeignKey(StreamAsset, on_delete=models.CASCADE, related_name='versions')
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=20, choices=VERSION_TYPES)
    file_path = models.CharField(max_length=255)  # Path in bucket
    
    def __str__(self):
        return f"{self.asset.name} - {self.name}"

class AssetMedia(models.Model):
    MEDIA_TYPES = (
        ('image', 'Image'),
        ('video', 'Video'),
    )
    
    asset = models.ForeignKey(StreamAsset, on_delete=models.CASCADE, related_name='media')
    type = models.CharField(max_length=10, choices=MEDIA_TYPES)
    file = models.ImageField(upload_to='stream_assets/media/', blank=True)  # For locally stored files
    file_path = models.CharField(max_length=255, blank=True)  # For bucket-stored files
    is_thumbnail = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)  # For ordering in gallery
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.asset.name} - Media {self.id}"

class UserAsset(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    asset = models.ForeignKey(StreamAsset, on_delete=models.CASCADE)
    purchased_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'asset')

# Invoices
class Invoice(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='invoice')
    invoice_number = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Invoice #{self.invoice_number} for Order #{self.order.id}"
    
    def generate_invoice_number(self):
        # Format: INV-YEAR-MONTH-ORDERID
        return f"INV-{self.created_at.year}-{self.created_at.month:02d}-{self.order.id}"

class NotificationRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notification_records')
    notification_type = models.CharField(max_length=50)  # 'order_message', 'message', etc.
    last_sent_at = models.DateTimeField()
    
    class Meta:
        unique_together = ('user', 'notification_type')
        
    def __str__(self):
        return f"{self.notification_type} for {self.user.email}"