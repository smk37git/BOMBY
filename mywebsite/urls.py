from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from django.http import HttpResponse
from STORE.views import qr_redirect


def robots_txt(request):
    lines = [
        "User-agent: *",
        "",
        "# Auth / account pages",
        "Disallow: /accounts/login/",
        "Disallow: /accounts/signup/",
        "Disallow: /accounts/password-reset/",
        "Disallow: /accounts/account/",
        "Disallow: /accounts/edit-profile/",
        "Disallow: /accounts/messages/",
        "Disallow: /accounts/user-management/",
        "Disallow: /accounts/message-monitor/",
        "Disallow: /accounts/purchase-history/",
        "Disallow: /accounts/profile/",
        "",
        "# Store protected pages",
        "Disallow: /store/my-orders/",
        "Disallow: /store/order/",
        "Disallow: /store/payment/",
        "Disallow: /store/purchase/",
        "Disallow: /store/create-checkout-session/",
        "Disallow: /store/apply-discount/",
        "Disallow: /store/admin/",
        "Disallow: /store/upload/",
        "Disallow: /store/message-me/",
        "Disallow: /store/message-general/",
        "",
        "# Main admin",
        "Disallow: /admin-panel/",
        "Disallow: /admin-verify/",
        "Disallow: /admin/",
        "Disallow: /announcements/",
        "Disallow: /generate-discount-code/",
        "",
        "# Portfolio API",
        "Disallow: /portfolio/api/",
        "",
        "# Fuze API & admin",
        "Disallow: /fuze/check-update",
        "Disallow: /fuze/signup",
        "Disallow: /fuze/login",
        "Disallow: /fuze/verify",
        "Disallow: /fuze/ai-chat",
        "Disallow: /fuze/save-chat",
        "Disallow: /fuze/get-chats",
        "Disallow: /fuze/delete-chat",
        "Disallow: /fuze/clear-chats",
        "Disallow: /fuze/analyze-benchmark",
        "Disallow: /fuze/profiles",
        "Disallow: /fuze/templates",
        "Disallow: /fuze/backgrounds/",
        "Disallow: /fuze/quickstart/",
        "Disallow: /fuze/widgets",
        "Disallow: /fuze/platforms",
        "Disallow: /fuze/callback/",
        "Disallow: /fuze/media",
        "Disallow: /fuze/test-alert",
        "Disallow: /fuze/labels/",
        "Disallow: /fuze/viewers/",
        "Disallow: /fuze/donations/",
        "Disallow: /fuze/w/",
        "Disallow: /fuze/twitch-webhook",
        "Disallow: /fuze/youtube/",
        "Disallow: /fuze/facebook/",
        "Disallow: /fuze/kick/",
        "Disallow: /fuze/tiktok/",
        "Disallow: /fuze/twitch-chat/",
        "Disallow: /fuze/kick-chat/",
        "Disallow: /fuze/facebook-chat/",
        "Disallow: /fuze/analytics",
        "Disallow: /fuze/reviews/",
        "Disallow: /fuze/google-auth/",
        "Disallow: /fuze/google-callback",
        "Disallow: /fuze/stripe-webhook/",
        "Disallow: /fuze/create-checkout-session/",
        "Disallow: /fuze/manage-subscription/",
        "Disallow: /fuze/cancel-subscription/",
        "Disallow: /fuze/reactivate-subscription/",
        "Disallow: /fuze/collab/",
        "Disallow: /fuze/leaderboard/",
        "Disallow: /fuze/recaps",
        "Disallow: /fuze/followers",
        "",
        "# Easter egg",
        "Disallow: /easter-egg/",
        "",
        "Sitemap: https://bomby.us/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


urlpatterns = [
    path('robots.txt', robots_txt),
    path('admin/', admin.site.urls),
    path('', include(('MAIN.urls', 'MAIN'), namespace='MAIN')),
    path('accounts/', include('ACCOUNTS.urls', namespace='ACCOUNTS')),
    path('portfolio/', include('PORTFOLIO.urls', namespace='PORTFOLIO')),
    path('store/', include('STORE.urls', namespace='STORE')),

    # For serving media files in all environments
    path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),

    # QR Code redirect at root level for shorter URLs
    path('redirect/<str:code>/', qr_redirect, name='qr_redirect'),

    # Google Auth URL
    path('accounts/', include('allauth.urls')),

    # Fuze API
    path('fuze/', include('FUZE.urls', namespace='FUZE')),
]

# Static files only
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler500 = 'MAIN.views.custom_500'