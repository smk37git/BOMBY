from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.contrib import messages

# Create your views here.

## Homepage View
def home(request):
    return render(request, 'MAIN/home.html')

## About View
def about(request):
    return render(request, 'MAIN/about.html')

## Contact View
def contact(request):
    if request.method == 'POST':
        # Extract form data
        name = request.POST.get('name')
        email = request.POST.get('email')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        
        try:
            # Compose email
            email_message = f"""
            From: {name}
            Email: {email}
            Subject: {subject}

            Message:
            {message}
            """
            # Send email
            send_mail(
                f'New Message: {subject}',  # Email subject
                email_message,
                'your-gmail@gmail.com',  # From email
                ['REMOVED_EMAIL'],  # To email
                fail_silently=False,
            )
            
            # Add success message
            messages.success(request, 'Your message was sent successfully!')
        
        except Exception as e:
            # Add error message
            messages.error(request, 'There was an error sending your message. Please try again.')
    
    return render(request, 'MAIN/contact.html')

## Portfolio View
def portfolio(request):
    return render(request, 'PORTFOLIO/portfolio.html')