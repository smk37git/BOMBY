from django.urls import path
from . import views

app_name = 'FUZEOBS'

urlpatterns = [
    path('check-update', views.fuzeobs_check_update, name='check_update'),
    path('signup', views.fuzeobs_signup, name='signup'),
    path('login', views.fuzeobs_login, name='login'),
    path('verify', views.fuzeobs_verify, name='verify'),
    path('check-password/', views.fuzeobs_check_password, name='check_password'),
    path('set-password/', views.fuzeobs_set_password, name='set_password'),
    path('ai-chat', views.fuzeobs_ai_chat, name='ai_chat'),
    path('save-chat', views.fuzeobs_save_chat, name='save_chat'),
    path('get-chats', views.fuzeobs_get_chats, name='get_chats'),
    path('delete-chat', views.fuzeobs_delete_chat, name='delete_chat'),
    path('clear-chats', views.fuzeobs_clear_chats, name='clear_chats'),
    path('analyze-benchmark', views.fuzeobs_analyze_benchmark, name='analyze_benchmark'),
    path('profiles', views.fuzeobs_get_profiles, name='get_profiles'),
    path('profiles/create', views.fuzeobs_create_profile, name='create_profile'),
    path('profiles/<int:profile_id>', views.fuzeobs_update_profile, name='update_profile'),
    path('profiles/<int:profile_id>/delete', views.fuzeobs_delete_profile, name='delete_profile'),
    path('templates', views.fuzeobs_list_templates, name='list_templates'),
    path('templates/<str:template_id>', views.fuzeobs_get_template, name='get_template'),
    path('backgrounds/<str:background_id>', views.fuzeobs_get_background, name='get_background'),
    path('quickstart/dismiss', views.fuzeobs_quickstart_dismiss, name='quickstart_dismiss'),
    path('quickstart/check', views.fuzeobs_quickstart_check, name='quickstart_check'),

    # Website URLS
    path('', views.fuzeobs_view, name="fuzeobs"),
    path('download/windows', views.fuzeobs_download_windows, name='download_windows'),
    path('download/mac', views.fuzeobs_download_mac, name='download_mac'),
    path('analytics', views.fuzeobs_analytics_view, name='analytics'),
    path('analytics/all-users', views.fuzeobs_all_users_view, name='all_users'),
    path('analytics/user/<int:user_id>/', views.fuzeobs_user_detail, name='user_detail'),
    path('analytics/user/<int:user_id>/chat/<int:chat_index>/', views.fuzeobs_chat_detail, name='chat_detail'),
]