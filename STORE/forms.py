from django import forms
from .models import OrderForm, OrderMessage, OrderAttachment, Review

class OrderQuestionsForm(forms.ModelForm):
    class Meta:
        model = OrderForm
        fields = ['question1', 'question2', 'question3', 'question4', 'question5']
        labels = {
            'question1': 'Please list your computer Specifications (GPU, CPU, RAM) so that I can configure the best settings for you.',
            'question2': 'Please run a Broadband Speed Test (Internet Speed Test) and share the Download and Upload Speeds (Mbps). You can do this safely by using Speedtest by Ookla: https://www.speedtest.net',
            'question3': 'You are HIGHLY recommended to join the Discord Server to get the best experience with clear communication about your stream setup. Join here: https://discord.gg/bdqAXc4',
            'question4': 'The way that I like to support you is by remotely connecting to your PC via TeamViewer. Please download TeamViewer QuickSupporthere: https://www.teamviewer.com/en-us/download/windows/?utm_source=google&utm_medium=cpc&utm_campaign=us%7Cb%7Cpr%7C22%7Caug%7Ctv-core-download-sn%7Cnew%7Ct0%7C0&utm_content=Download&utm_term=teamviewer+download',
            'question5': 'Now that the business questions are out of the way, please share some information about yourself! What are you wanting to achieve? What will you stream? Be as creative as you want!',
        }
        widgets = {
            'question5': forms.Textarea(attrs={'rows': 4}),
        }

class MessageForm(forms.ModelForm):
    class Meta:
        model = OrderMessage
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Type your message here...'}),
        }

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Share your experience...'}),
        }