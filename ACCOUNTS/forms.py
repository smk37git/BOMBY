from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import URLValidator, RegexValidator
from django.core.exceptions import ValidationError
from .models import User
from .validators import validate_clean_username
from .validators import BANNED_WORDS
from .models import Message
from .validators import validate_clean_content

## Create User Interface
class CustomUserCreationForm(UserCreationForm):
    username = forms.CharField(
        validators=[validate_clean_username],
        help_text="Required. 20 characters or fewer. No inappropriate words allowed."
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

# Edit Profile
class ProfileEditForm(forms.ModelForm):
    youtube_link_1 = forms.URLField(
        required=False,
        validators=[
            URLValidator(message="Enter a valid URL."),
            RegexValidator(
                regex=r'^https?://(www\.)?(youtube\.com/(channel/|c/|@|user/)|youtu\.be/)',
                message="YouTube URL must start with youtube.com/channel/, youtube.com/c/, youtube.com/@, youtube.com/user/, or youtu.be/"
            )
        ],
        widget=forms.URLInput(attrs={
            'placeholder': 'https://youtube.com/@username or https://youtube.com/channel/...',
            'pattern': 'https?://(www\\.)?(youtube\\.com/(channel/|c/|@|user/)|youtu\\.be/).*',
            'title': 'YouTube URL must start with youtube.com/channel/, youtube.com/c/, youtube.com/@, youtube.com/user/, or youtu.be/'
        }),
    )

    youtube_link_2 = forms.URLField(
      required=False,
        validators=[
            URLValidator(message="Enter a valid URL."),
            RegexValidator(
                regex=r'^https?://(www\.)?(youtube\.com/(channel/|c/|@|user/)|youtu\.be/)',
                message="YouTube URL must start with youtube.com/channel/, youtube.com/c/, youtube.com/@, youtube.com/user/, or youtu.be/"
            )
        ],
        widget=forms.URLInput(attrs={
            'placeholder': 'https://youtube.com/@username or https://youtube.com/channel/...',
            'pattern': 'https?://(www\\.)?(youtube\\.com/(channel/|c/|@|user/)|youtu\\.be/).*',
            'title': 'YouTube URL must start with youtube.com/channel/, youtube.com/c/, youtube.com/@, youtube.com/user/, or youtu.be/'
        }),
    )
    
    twitch_link = forms.URLField(
        required=False,
        validators=[
            URLValidator(message="Enter a valid URL."),
            RegexValidator(
                regex=r'^https?://(www\.)?(twitch\.tv/)',
                message="Twitch URL must start with twitch.tv/"
            )
        ],
        widget=forms.URLInput(attrs={
            'placeholder': 'https://twitch.tv/...',
            'pattern': 'https?://(www\\.)?(twitch\\.tv/).*',
            'title': 'Twitch URL must start with twitch.tv/'
        }),
    )
    
    github_link = forms.URLField(
        required=False,
        validators=[
            URLValidator(message="Enter a valid URL."),
            RegexValidator(
                regex=r'^https?://(www\.)?(github\.com/)',
                message="GitHub URL must start with github.com/"
            )
        ],
        widget=forms.URLInput(attrs={
            'placeholder': 'https://github.com/...',
            'pattern': 'https?://(www\\.)?(github\\.com/).*',
            'title': 'GitHub URL must start with github.com/'
        }),
    )
    
    twitter_link = forms.URLField(
        required=False,
        validators=[
            URLValidator(message="Enter a valid URL."),
            RegexValidator(
                regex=r'^https?://(www\.)?(x\.com/|twitter\.com/)',
                message="X/Twitter URL must start with x.com/ or twitter.com/"
            )
        ],
        widget=forms.URLInput(attrs={
            'placeholder': 'https://x.com/...',
            'pattern': 'https?://(www\\.)?(x\\.com/|twitter\\.com/).*',
            'title': 'X/Twitter URL must start with x.com/ or twitter.com/'
        }),
    )
    
    kick_link = forms.URLField(
        required=False,
        validators=[
            URLValidator(message="Enter a valid URL."),
            RegexValidator(
                regex=r'^https?://(www\.)?(kick\.com/)',
                message="Kick URL must start with kick.com/"
            )
        ],
        widget=forms.URLInput(attrs={
            'placeholder': 'https://kick.com/...',
            'pattern': 'https?://(www\\.)?(kick\\.com/).*',
            'title': 'Kick URL must start with kick.com/'
        }),
    )
    
    instagram_link = forms.URLField(
        required=False,
        validators=[
            URLValidator(message="Enter a valid URL."),
            RegexValidator(
                regex=r'^https?://(www\.)?(instagram\.com/)',
                message="Instagram URL must start with instagram.com/"
            )
        ],
        widget=forms.URLInput(attrs={
            'placeholder': 'https://instagram.com/...',
            'pattern': 'https?://(www\\.)?(instagram\\.com/).*',
            'title': 'Instagram URL must start with instagram.com/'
        }),
    )

    class Meta:
        model = User
        fields = [
            'profile_picture', 
            'bio',
            'youtube_link_1', 
            'youtube_link_2',
            'twitch_link',
            'github_link',
            'twitter_link',
            'kick_link',
            'instagram_link'
        ]
    
    def clean_bio(self):
        bio = self.cleaned_data.get('bio')
        if bio:
            bio_lower = bio.lower()
            for word in BANNED_WORDS:
                if word and word in bio_lower:
                    raise forms.ValidationError("Bio contains inappropriate language.")
        return bio
        
    def clean_profile_picture(self):
        image = self.cleaned_data.get('profile_picture')
        if not image:
            return image
            
        # Check file type
        valid_types = ['image/jpeg', 'image/png', 'image/gif']
        if hasattr(image, 'content_type') and image.content_type not in valid_types:
            raise forms.ValidationError("Invalid file type. Please upload a JPEG, PNG, or GIF image.")
            
        return image

# Edit Username
class UsernameEditForm(forms.ModelForm):
    username = forms.CharField(
        max_length=20,
        validators=[validate_clean_username],
        help_text="Required. 20 characters or fewer. Letters, digits and @/./+/-/_ only."
    )
    
    class Meta:
        model = User
        fields = ['username']

# Messaging System
class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Type your message here...'}),
        }
    
    def clean_content(self):
        content = self.cleaned_data.get('content')
        return validate_clean_content(content)