from django import forms
from .models import OrderForm, OrderMessage, OrderAttachment, Review
from django.core.exceptions import ValidationError
from ACCOUNTS.validators import validate_clean_content

class OrderQuestionsForm(forms.ModelForm):
    # Add structured fields for specific questions
    download_speed = forms.CharField(max_length=10, required=False, 
                                    widget=forms.TextInput(attrs={'placeholder': 'Enter speed'}))
    upload_speed = forms.CharField(max_length=10, required=False,
                                  widget=forms.TextInput(attrs={'placeholder': 'Enter speed'}))
    
    DISCORD_CHOICES = [
        ('joined', 'I have joined the Discord Server'),
        ('not_joined', 'I have not joined the Discord Server')
    ]
    discord_status = forms.ChoiceField(choices=DISCORD_CHOICES, widget=forms.RadioSelect)
    discord_username = forms.CharField(max_length=100, required=False)
    
    TEAMVIEWER_CHOICES = [
        ('downloaded', 'I have downloaded TeamViewer'),
        ('not_downloaded', 'I have not downloaded TeamViewer')
    ]
    teamviewer_status = forms.ChoiceField(choices=TEAMVIEWER_CHOICES, widget=forms.RadioSelect)
    
    class Meta:
        model = OrderForm
        fields = ['question1', 'download_speed', 'upload_speed', 'discord_status', 'discord_username', 
                  'teamviewer_status', 'question5']
        labels = {
            'question1': 'Please list your computer Specifications (GPU, CPU, RAM) so that I can configure the best settings for you.',
            'question5': 'Now that the business questions are out of the way, please share some information about yourself! What are you wanting to achieve? What will you stream? Be as creative as you want!',
        }
        widgets = {
            'question5': forms.Textarea(attrs={'rows': 4}),
        }
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Format question2 with download and upload speeds
        instance.question2 = f"Download: {self.cleaned_data.get('download_speed')} Mbps, Upload: {self.cleaned_data.get('upload_speed')} Mbps"
        
        # Format question3 with Discord status and username if applicable
        if self.cleaned_data.get('discord_status') == 'joined':
            instance.question3 = f"I have joined the Discord Server. My username is: {self.cleaned_data.get('discord_username')}"
        else:
            instance.question3 = "I have not joined the Discord Server"
        
        # Format question4 with TeamViewer status
        if self.cleaned_data.get('teamviewer_status') == 'downloaded':
            instance.question4 = "I have downloaded TeamViewer"
        else:
            instance.question4 = "I have not downloaded TeamViewer"
        
        if commit:
            instance.save()
        return instance

class MessageForm(forms.ModelForm):
    class Meta:
        model = OrderMessage
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Type your message here...'}),
        }
    
    def clean_message(self):
        message = self.cleaned_data.get('message')
        from ACCOUNTS.validators import validate_clean_content
        return validate_clean_content(message)

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Share your experience...'}),
        }
    
    def clean_comment(self):
        comment = self.cleaned_data.get('comment')
        try:
            return validate_clean_content(comment)
        except ValidationError as e:
            raise forms.ValidationError(e.message)