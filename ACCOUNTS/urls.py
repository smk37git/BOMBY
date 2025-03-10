from django.urls import path, include
from . import views
from django.contrib.auth import views as auth_views
from django.contrib import admin
from django.urls import reverse_lazy

app_name = 'ACCOUNTS'

urlpatterns = [
     # Add Firebase authentication URLs
     path('firebase-login/', views.firebase_login, name='firebase_login'),
     path('firebase-config/', views.firebase_config, name='firebase_config'),
     
     # Main Account URLS
     path('signup/', views.signup, name='signup'),
     path('login/', auth_views.LoginView.as_view(template_name='ACCOUNTS/login.html'), name='login'),
     path('logout/', auth_views.LogoutView.as_view(next_page=reverse_lazy('home')), name='logout'),

     # Logged in View
     path('account/', views.account, name='account'),

     # Username Management - Fixed paths with specific routes first
     path('profile/change-username/', views.edit_username, {'user_id': None}, name='profile_edit_username'),
     path('account/change-username/', views.edit_username, {'user_id': None}, name='edit_username'),
     path('edit-username/<int:user_id>/', views.edit_username, name='edit_username_admin'),
     
     # Viewing Another Account - More general route after specific ones
     path('profile/<str:username>/', views.profile_view, name='user_profile'),

     # Password Resetting
     path('password-reset/', 
     auth_views.PasswordResetView.as_view(
          template_name='ACCOUNTS/password_reset.html',
          email_template_name='ACCOUNTS/password_reset_email.html',
          success_url=reverse_lazy('ACCOUNTS:password_reset_done'),
        ),
     name='password_reset'),
     path('password-reset/done/', 
          auth_views.PasswordResetDoneView.as_view(template_name='ACCOUNTS/password_reset_done.html'), 
          name='password_reset_done'),
     path('password-reset-confirm/<uidb64>/<token>/', 
          auth_views.PasswordResetConfirmView.as_view(template_name='ACCOUNTS/password_reset_confirm.html', 
          success_url=reverse_lazy('ACCOUNTS:password_reset_complete')), 
          name='password_reset_confirm'),
     path('password-reset-complete/', 
          auth_views.PasswordResetCompleteView.as_view(template_name='ACCOUNTS/password_reset_complete.html'), 
          name='password_reset_complete'),

     # Edit Profile
     path('edit-profile/', views.edit_profile, name='edit_profile'),

     # Promotional Wall
     path('users/', views.promotional_wall, name='promotional_wall'),
     path('update-promo-links/', views.update_promo_links, name='update_promo_links'),

     # User Management
     path('user-management/', views.user_management, name='user_management'),
     path('bulk-change-user-type/', views.bulk_change_user_type, name='bulk_change_user_type'),
     path('bulk-delete-users/', views.bulk_delete_users, name='bulk_delete_users'),
     path('test-upload/', views.test_file_upload, name='test_file_upload'),
     path('debug-gcs/', views.debug_gcs_direct, name='debug_gcs_direct'),
     path('debug-django-storage/', views.debug_django_storage, name='debug_django_storage'),
]