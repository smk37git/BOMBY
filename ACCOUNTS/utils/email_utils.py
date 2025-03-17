from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.sites.shortcuts import get_current_site

class CustomPasswordResetForm(PasswordResetForm):
    def send_mail(self, subject_template_name, email_template_name, 
                  context, from_email, to_email, html_email_template_name=None):
        """Override the default send_mail to use our custom HTML template."""
        
        # Get the site from context
        if 'domain' not in context:
            current_site = context.get('site')
            context.update({
                'domain': current_site.domain,
                'protocol': 'https' if settings.USE_HTTPS else 'http',
            })
        
        # Render the custom HTML template
        html_email = render_to_string('ACCOUNTS/emails/password_reset_email.html', context)
        subject = "Password Reset Request - BOMBY"
        
        # Send the email with HTML content
        email_message = EmailMultiAlternatives(subject, '', from_email, [to_email])
        email_message.attach_alternative(html_email, 'text/html')
        email_message.send()
        
    def save(self, domain_override=None,
             subject_template_name='registration/password_reset_subject.txt',
             email_template_name='registration/password_reset_email.html',
             use_https=False, token_generator=default_token_generator,
             from_email=None, request=None, html_email_template_name=None,
             extra_email_context=None):
        """
        Override the save method to use our custom email template
        """
        email = self.cleaned_data["email"]
        if not domain_override:
            current_site = get_current_site(request)
            site_name = current_site.name
            domain = current_site.domain
        else:
            site_name = domain = domain_override
            
        context = {
            'email': email,
            'domain': domain,
            'site_name': site_name,
            'uid': urlsafe_base64_encode(force_bytes(self.get_users(email)[0].pk)),
            'user': self.get_users(email)[0],
            'token': token_generator.make_token(self.get_users(email)[0]),
            'protocol': 'https' if use_https else 'http',
            **(extra_email_context or {}),
        }
        
        self.send_mail(
            subject_template_name, email_template_name, context, from_email,
            email, html_email_template_name=html_email_template_name,
        )