from django.urls import path
from . import views
from .donations import (
    donation_settings, paypal_connect, paypal_callback, 
    paypal_disconnect, donation_page, create_donation_order, 
    capture_donation, donation_history, validate_donation,
    clear_donation_history
)
from .recaps import fuze_recaps as recaps_view, fuze_recaps_refresh as recaps_refresh_view
from .recaps import fuze_followers as followers_view
from .leaderboard import (
    fuze_leaderboard,
    fuze_leaderboard_optin,
    fuze_leaderboard_optout,
    fuze_leaderboard_sync,
    fuze_leaderboard_cron_sync,
)
from .telemetry_views import fuze_telemetry_ingest, fuze_telemetry_dashboard

app_name = 'FUZE'

urlpatterns = [
    # ── Telemetry (unauthenticated)
    path('telemetry', fuze_telemetry_ingest, name='telemetry_ingest'),
    path('telemetry/dashboard', fuze_telemetry_dashboard, name='telemetry_dashboard'),
    path('telemetry/page', views.fuze_telemetry_view, name='telemetry_page'),

    path('check-update', views.fuze_check_update, name='check_update'),
    path('patch-notes', views.fuze_patch_notes, name='patch_notes'),
    path('signup', views.fuze_signup, name='signup'),
    path('login', views.fuze_login, name='login'),
    path('google-auth/init', views.fuze_google_auth_init, name='google_auth_init'),
    path('google-callback', views.fuze_google_callback, name='google_callback'),
    path('google-auth/poll', views.fuze_google_auth_poll, name='google_auth_poll'),
    path('verify', views.fuze_verify, name='verify'),
    path('ai-chat', views.fuze_ai_chat, name='ai_chat'),
    path('save-chat', views.fuze_save_chat, name='save_chat'),
    path('get-chats', views.fuze_get_chats, name='get_chats'),
    path('delete-chat', views.fuze_delete_chat, name='delete_chat'),
    path('clear-chats', views.fuze_clear_chats, name='clear_chats'),
    path('analyze-benchmark', views.fuze_analyze_benchmark, name='analyze_benchmark'),
    path('profiles', views.fuze_get_profiles, name='get_profiles'),
    path('profiles/create', views.fuze_create_profile, name='create_profile'),
    path('profiles/<int:profile_id>', views.fuze_update_profile, name='update_profile'),
    path('profiles/<int:profile_id>/delete', views.fuze_delete_profile, name='delete_profile'),
    path('templates', views.fuze_list_templates, name='list_templates'),
    path('templates/<str:template_id>', views.fuze_get_template, name='get_template'),
    path('backgrounds/<str:background_id>', views.fuze_get_background, name='get_background'),
    path('quickstart/dismiss', views.fuze_quickstart_dismiss, name='quickstart_dismiss'),
    path('quickstart/check', views.fuze_quickstart_check, name='quickstart_check'),

    # Announcements
    path('announcements', views.fuze_announcements, name='announcements'),
    path('announcements/create', views.fuze_announcement_create, name='announcement_create'),
    path('announcements/toggle', views.fuze_announcement_toggle, name='announcement_toggle'),
    path('announcements/delete', views.fuze_announcement_delete, name='announcement_delete'),

    # == Widget URLS ==

    # PLATFORM ALERTS
    path('twitch-webhook', views.fuze_twitch_webhook, name='twitch_webhook'),
    path('youtube/start/<int:user_id>', views.fuze_youtube_start_listener, name='youtube_start_listener'),
    path('facebook/start/<int:user_id>', views.fuze_facebook_start_listener, name='facebook_start_listener'),
    path('kick/start/<int:user_id>', views.fuze_kick_start_listener, name='kick_start_listener'),
    path('kick-webhook', views.fuze_kick_webhook, name='kick_webhook'),
    path('tiktok/start/<int:user_id>', views.fuze_tiktok_start_listener, name='tiktok_start_listener'),

    # PLATFORM CHATS
    path('twitch-chat/start/<int:user_id>', views.fuze_twitch_chat_start, name='twitch_chat_start'),
    path('kick-chat/start/<int:user_id>', views.fuze_kick_chat_start, name='kick_chat_start'),
    path('facebook-chat/start/<int:user_id>', views.fuze_facebook_chat_start, name='facebook_chat_start'),

    # Widget Serving (clean URL)
    path('w/<str:token>', views.fuze_serve_widget, name='serve_widget'),

    # Widget CRUD
    path('widgets', views.fuze_get_widgets, name='get_widgets'),
    path('widgets/save', views.fuze_save_widget, name='save_widget'),
    path('widgets/<str:widget_type>/delete', views.fuze_delete_widget, name='fuze_delete_widget'),
    path('widgets/toggle', views.fuze_toggle_widget, name='toggle_widget'),

    # Platform Management
    path('platforms', views.fuze_get_platforms, name='get_platforms'),
    path('platforms/connect', views.fuze_connect_platform, name='connect_platform'),
    path('platforms/tiktok-exchange', views.fuze_tiktok_exchange, name='tiktok_exchange'),
    path('platforms/disconnect', views.fuze_disconnect_platform, name='disconnect_platform'),
    path('callback/<str:platform>', views.fuze_platform_callback, name='platform_callback'),

    # Media Library
    path('media', views.fuze_get_media, name='get_media'),
    path('media/upload', views.fuze_upload_media, name='upload_media'),
    path('media/<int:media_id>/delete', views.fuze_delete_media, name='delete_media'),

    # Widget Event Configuration
    path('widgets/<int:widget_id>/events', views.fuze_get_widget_events, name='get_widget_events'),
    path('widgets/events/save', views.fuze_save_widget_event, name='save_widget_event'),
    path('widgets/events/<int:event_id>/delete', views.fuze_delete_widget_event, name='delete_widget_event'),

    # Alert Testing
    path('test-alert', views.fuze_test_alert, name='test_alert'),
    path('widgets/events/config/<int:user_id>/<str:platform>', views.fuze_get_widget_event_configs, name='get_widget_event_configs'),

    # Labels Data Persistence
    path('labels/data/<int:user_id>', views.fuze_get_label_data, name='get_label_data'),
    path('labels/save/<int:user_id>', views.fuze_save_label_data, name='save_label_data'),

    # Viewer Counts Widget
    path('viewers/twitch/<int:user_id>', views.fuze_get_twitch_viewers),
    path('viewers/youtube/<int:user_id>', views.fuze_get_youtube_viewers),
    path('viewers/kick/<int:user_id>', views.fuze_get_kick_viewers),
    path('viewers/facebook/<int:user_id>', views.fuze_get_facebook_viewers),
    path('viewers/tiktok/<int:user_id>', views.fuze_get_tiktok_viewers),

    # Donations
    path('donations/settings', donation_settings, name='donation_settings'),
    path('donations/paypal/connect', paypal_connect, name='paypal_connect'),
    path('donations/paypal/callback', paypal_callback, name='paypal_callback'),
    path('donations/paypal/disconnect', paypal_disconnect, name='paypal_disconnect'),
    path('donations/history', donation_history, name='donation_history'),
    path('donations/clear', clear_donation_history, name='clear_donation_history'),
    path('donate/<str:token>', donation_page, name='donation_page'),
    path('donate/<str:token>/validate', validate_donation, name='validate_donation'),
    path('donate/<str:token>/create', create_donation_order, name='create_donation_order'),
    path('donate/<str:token>/capture', capture_donation, name='capture_donation'),

    # Website URLS
    path('', views.fuze_view, name="fuze"),
    path('download/windows', views.fuze_download_windows, name='download_windows'),
    path('download/mac', views.fuze_download_mac, name='download_mac'),
    path('download/linux', views.fuze_download_linux, name='download_linux'),
    path('install-guide/', views.fuze_install_guide, name='install_guide'),
    path('roadmap/', views.fuze_roadmap, name='roadmap'),
    path('analytics', views.fuze_analytics_view, name='analytics'),
    path('analytics/reset/', views.fuze_reset_analytics, name='reset_analytics'),
    path('analytics/all-users', views.fuze_all_users_view, name='all_users'),
    path('analytics/user/<int:user_id>/', views.fuze_user_detail, name='user_detail'),
    path('analytics/user/<int:user_id>/chat/<int:chat_index>/', views.fuze_chat_detail, name='chat_detail'),

    # Payments
    path('pricing/', views.fuze_pricing, name='pricing'),
    path('payment/success/', views.fuze_payment_success, name='payment_success'),
    path('manage-subscription/', views.fuze_manage_subscription, name='manage_subscription'),
    path('cancel-subscription/', views.fuze_cancel_subscription, name='cancel_subscription'),
    path('reactivate-subscription/', views.fuze_reactivate_subscription, name='reactivate_subscription'),
    path('payment/<str:plan_type>/', views.fuze_payment, name='payment'),
    path('create-checkout-session/', views.fuze_create_checkout_session, name='create_checkout_session'),
    path('stripe-webhook/', views.fuze_stripe_webhook, name='stripe_webhook'),

    # Reviews
    path('reviews/submit', views.fuze_submit_review, name='submit_review'),
    path('reviews/featured', views.fuze_get_featured_reviews, name='featured_reviews'),
    path('reviews/admin', views.fuze_reviews_admin, name='reviews_admin'),
    path('reviews/toggle-featured', views.fuze_toggle_review_featured, name='toggle_review_featured'),
    path('reviews/delete', views.fuze_delete_review, name='delete_review'),
    path('reviews/edit-admin', views.edit_review_admin, name='edit_review_admin'),
    path('reviews/create-admin', views.fuze_create_review_admin, name='create_review_admin'),
    path('reviews/my-review', views.my_review, name='my_review'),

    # Welcome Page
    path('countdown', views.fuze_countdown, name='countdown'),
    path('recaps', recaps_view, name='recaps'),
    path('followers', followers_view, name='followers'),
    path('recaps/refresh', recaps_refresh_view, name='recaps_refresh'),

    # Collab Finder
    path('collab/posts', views.collab_posts, name='collab_posts'),
    path('collab/posts/<int:post_id>', views.collab_post_detail, name='collab_post_detail'),
    path('collab/posts/<int:post_id>/interest', views.collab_interest, name='collab_interest'),
    path('collab/posts/<int:post_id>/renew', views.collab_renew_post, name='collab_renew'),
    path('collab/my-posts', views.collab_my_posts, name='collab_my_posts'),
    path('collab/message', views.collab_send_message, name='collab_send_message'),

    # Leaderboard
    path('leaderboard/opt-in', fuze_leaderboard_optin, name='leaderboard_optin'),
    path('leaderboard/opt-out', fuze_leaderboard_optout, name='leaderboard_optout'),
    path('leaderboard/sync', fuze_leaderboard_sync, name='leaderboard_sync'),
    path('leaderboard/cron-sync', fuze_leaderboard_cron_sync, name='leaderboard_cron_sync'),
    path('leaderboard/<str:period>', fuze_leaderboard, name='leaderboard'),

    # Creator Codes
    path('analytics/creator-codes/', views.fuze_creator_codes_view, name='creator_codes'),
    path('analytics/creator-codes/create', views.fuze_creator_code_create, name='creator_code_create'),
    path('analytics/creator-codes/toggle', views.fuze_creator_code_toggle, name='creator_code_toggle'),
    path('analytics/creator-codes/delete', views.fuze_creator_code_delete, name='creator_code_delete'),
    path('analytics/creator-codes/mark-paid', views.fuze_creator_code_mark_paid, name='creator_code_mark_paid'),
    path('validate-creator-code/', views.fuze_validate_creator_code, name='validate_creator_code'),
    path('creator-portal/', views.fuze_my_creator_code, name='my_creator_code'),
]