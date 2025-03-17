from django.db import models
from django.conf import settings
from django.utils import timezone
import os

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
    
    def save(self, *args, **kwargs):
        # Set due date when status changes to in_progress (3 days from now)
        if self.status == 'in_progress' and not self.due_date:
            self.due_date = timezone.now() + timezone.timedelta(days=3)
        
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
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    def save(self, *args, **kwargs):
        if not self.id:
            # Get user's timezone if available, otherwise use server's timezone
            user_timezone = getattr(self.sender, 'timezone', None)
            if user_timezone:
                from django.utils import timezone
                # Apply user's timezone to created_at
                self.created_at = timezone.now().astimezone(pytz.timezone(user_timezone))
        
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