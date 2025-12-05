from django.urls import path
from . import views

app_name = 'FUZEOBS'

urlpatterns = [
    path('check-update', views.fuzeobs_check_update, name='check_update'),
    path('signup', views.fuzeobs_signup, name='signup'),
    path('login', views.fuzeobs_login, name='login'),
    path('google-auth/init', views.fuzeobs_google_auth_init, name='google_auth_init'),
    path('google-callback', views.fuzeobs_google_callback, name='google_callback'),
    path('google-auth/poll', views.fuzeobs_google_auth_poll, name='google_auth_poll'),
    path('verify', views.fuzeobs_verify, name='verify'),
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

    # == Widget URLS ==

    # PLATFORM ALERTS
    path('twitch-webhook', views.fuzeobs_twitch_webhook, name='twitch_webhook'),
    path('youtube/start/<int:user_id>', views.fuzeobs_youtube_start_listener, name='youtube_start_listener'),
    path('facebook/start/<int:user_id>', views.fuzeobs_facebook_start_listener, name='facebook_start_listener'),
    path('kick-webhook', views.fuzeobs_kick_webhook, name='kick_webhook'),
    path('tiktok/start/<int:user_id>', views.fuzeobs_tiktok_start_listener, name='tiktok_start_listener'),

    # PLATFORM CHATS
    path('twitch-chat/start/<int:user_id>', views.fuzeobs_twitch_chat_start, name='twitch_chat_start'),
    path('kick-chat/start/<int:user_id>', views.fuzeobs_kick_chat_start, name='kick_chat_start'),

    # Widget Serving (clean URL)
    path('w/<str:token>', views.fuzeobs_serve_widget, name='serve_widget'),

    # Widget CRUD
    path('widgets', views.fuzeobs_get_widgets, name='get_widgets'),
    path('widgets/save', views.fuzeobs_save_widget, name='save_widget'),
    path('widgets/<str:widget_type>/delete', views.fuzeobs_delete_widget, name='fuzeobs_delete_widget'),
    path('widgets/toggle', views.fuzeobs_toggle_widget, name='toggle_widget'),

    # Platform Management
    path('platforms', views.fuzeobs_get_platforms, name='get_platforms'),
    path('platforms/connect', views.fuzeobs_connect_platform, name='connect_platform'),
    path('platforms/disconnect', views.fuzeobs_disconnect_platform, name='disconnect_platform'),
    path('callback/<str:platform>', views.fuzeobs_platform_callback, name='platform_callback'),

    # Media Library
    path('media', views.fuzeobs_get_media, name='get_media'),
    path('media/upload', views.fuzeobs_upload_media, name='upload_media'),
    path('media/<int:media_id>/delete', views.fuzeobs_delete_media, name='delete_media'),

    # Widget Event Configuration
    path('widgets/<int:widget_id>/events', views.fuzeobs_get_widget_events, name='get_widget_events'),
    path('widgets/events/save', views.fuzeobs_save_widget_event, name='save_widget_event'),
    path('widgets/events/<int:event_id>/delete', views.fuzeobs_delete_widget_event, name='delete_widget_event'),

    # Alert Testing
    path('test-alert', views.fuzeobs_test_alert, name='test_alert'),
    path('widgets/events/config/<int:user_id>/<str:platform>', views.fuzeobs_get_widget_event_configs, name='get_widget_event_configs'),

    # Labels Data Persistence
    path('labels/data/<int:user_id>', views.fuzeobs_get_label_data, name='get_label_data'),
    path('labels/save/<int:user_id>', views.fuzeobs_save_label_data, name='save_label_data'),

    # Viewer Counts Widget
    path('viewers/twitch/<int:user_id>', views.fuzeobs_get_twitch_viewers),
    path('viewers/youtube/<int:user_id>', views.fuzeobs_get_youtube_viewers),
    path('viewers/kick/<int:user_id>', views.fuzeobs_get_kick_viewers),
    path('viewers/facebook/<int:user_id>', views.fuzeobs_get_facebook_viewers),

    # Website URLS
    path('', views.fuzeobs_view, name="fuzeobs"),
    path('download/windows', views.fuzeobs_download_windows, name='download_windows'),
    path('download/mac', views.fuzeobs_download_mac, name='download_mac'),
    path('analytics', views.fuzeobs_analytics_view, name='analytics'),
    path('analytics/all-users', views.fuzeobs_all_users_view, name='all_users'),
    path('analytics/user/<int:user_id>/', views.fuzeobs_user_detail, name='user_detail'),
    path('analytics/user/<int:user_id>/chat/<int:chat_index>/', views.fuzeobs_chat_detail, name='chat_detail'),
]