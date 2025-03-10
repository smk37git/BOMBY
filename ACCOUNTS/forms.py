from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import URLValidator, RegexValidator
from django.core.exceptions import ValidationError
from .models import User
from .validators import validate_clean_username
from .validators import BANNED_WORDS

class CustomUserCreationForm(UserCreationForm):
    username = forms.CharField(
        validators=[validate_clean_username],
        help_text="Required. 20 characters or fewer. No inappropriate words allowed."
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

class ProfileEditForm(forms.ModelForm):
    # Social media fields remain unchanged
    youtube_link_1 = forms.URLField(required=False, validators=[URLValidator()])
    youtube_link_2 = forms.URLField(required=False, validators=[URLValidator()])
    twitch_link = forms.URLField(required=False, validators=[URLValidator()])
    github_link = forms.URLField(required=False, validators=[URLValidator()])
    twitter_link = forms.URLField(required=False, validators=[URLValidator()])
    kick_link = forms.URLField(required=False, validators=[URLValidator()])
    instagram_link = forms.URLField(required=False, validators=[URLValidator()])

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
            print(f"Processing bio: length={len(bio)}")
        return bio
        
    def clean_profile_picture(self):
        image = self.cleaned_data.get('profile_picture')
        if image:
            print(f"Processing profile picture: name={image.name}, size={image.size}")
        return image
    
    def save(self, commit=True):
        print("ProfileEditForm save called")
        user = super().save(commit=False)
        print(f"Form cleaned data: {self.cleaned_data}")
        
        if commit:
            try:
                user.save()
                print(f"User saved successfully, profile_picture={user.profile_picture}")
            except Exception as e:
                print(f"Error saving user: {str(e)}")
                import traceback
                print(traceback.format_exc())
        
        return user

class UsernameEditForm(forms.ModelForm):
    username = forms.CharField(max_length=20, validators=[validate_clean_username])
    
    class Meta:
        model = User
        fields = ['username']