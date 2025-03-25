from django.urls import path, include
from . import views
from django.contrib.auth import views as auth_views
from django.contrib import admin
from django.urls import reverse_lazy
from .views import CustomPasswordResetView

app_name = 'ACCOUNTS'

urlpatterns = [
     # Main Account URLS
     path('signup/', views.signup, name='signup'),
     path('login/', auth_views.LoginView.as_view(template_name='ACCOUNTS/login.html'), name='login'),
     path('logout/', auth_views.LogoutView.as_view(next_page=reverse_lazy('home')), name='logout'),
     path('purchase-history/', views.purchase_history, name='purchase_history'),

     # Logged in View
     path('account/', views.account, name='account'),

     # Username Management
     path('profile/change-username/', views.edit_username, {'user_id': None}, name='profile_edit_username'),
     path('account/change-username/', views.edit_username, {'user_id': None}, name='edit_username'),
     path('edit-username/<int:user_id>/', views.edit_username, name='edit_username_admin'),
     
     # Viewing Another Account
     path('profile/<str:username>/', views.profile_view, name='user_profile'),

     # Password Resetting
     path('password-reset/', CustomPasswordResetView.as_view(), name='password_reset'),
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

     # Messaging URLs
     path('messages/', views.inbox, name='inbox'),
     path('messages/search/', views.user_search, name='user_search'),
     path('messages/start/<int:user_id>/', views.start_conversation, name='start_conversation'),
     path('messages/<int:user_id>/', views.conversation, name='conversation'),
     path('messages/send/<int:user_id>/', views.send_message, name='send_message'),
     path('messages/unread-count/', views.get_unread_count, name='get_unread_count'),
     path('messages/order/<int:order_id>/message/<int:message_id>/', views.copy_order_message_to_inbox, name='copy_order_message'),
     path('api/run-check/', views.run_message_check, name='run_message_check'),

     # Message Monitoring
     path('message-monitor/', views.message_monitor, name='message_monitor'),
     path('message-monitor/mark-read/', views.mark_message_read, name='mark_message_read'),
     path('message-monitor/delete/', views.delete_messages, name='delete_messages'),
]