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
        "# FuzeOBS API & admin",
        "Disallow: /fuzeobs/check-update",
        "Disallow: /fuzeobs/signup",
        "Disallow: /fuzeobs/login",
        "Disallow: /fuzeobs/verify",
        "Disallow: /fuzeobs/ai-chat",
        "Disallow: /fuzeobs/save-chat",
        "Disallow: /fuzeobs/get-chats",
        "Disallow: /fuzeobs/delete-chat",
        "Disallow: /fuzeobs/clear-chats",
        "Disallow: /fuzeobs/analyze-benchmark",
        "Disallow: /fuzeobs/profiles",
        "Disallow: /fuzeobs/templates",
        "Disallow: /fuzeobs/backgrounds/",
        "Disallow: /fuzeobs/quickstart/",
        "Disallow: /fuzeobs/widgets",
        "Disallow: /fuzeobs/platforms",
        "Disallow: /fuzeobs/callback/",
        "Disallow: /fuzeobs/media",
        "Disallow: /fuzeobs/test-alert",
        "Disallow: /fuzeobs/labels/",
        "Disallow: /fuzeobs/viewers/",
        "Disallow: /fuzeobs/donations/",
        "Disallow: /fuzeobs/w/",
        "Disallow: /fuzeobs/twitch-webhook",
        "Disallow: /fuzeobs/youtube/",
        "Disallow: /fuzeobs/facebook/",
        "Disallow: /fuzeobs/kick/",
        "Disallow: /fuzeobs/tiktok/",
        "Disallow: /fuzeobs/twitch-chat/",
        "Disallow: /fuzeobs/kick-chat/",
        "Disallow: /fuzeobs/facebook-chat/",
        "Disallow: /fuzeobs/analytics",
        "Disallow: /fuzeobs/reviews/",
        "Disallow: /fuzeobs/google-auth/",
        "Disallow: /fuzeobs/google-callback",
        "Disallow: /fuzeobs/stripe-webhook/",
        "Disallow: /fuzeobs/create-checkout-session/",
        "Disallow: /fuzeobs/manage-subscription/",
        "Disallow: /fuzeobs/cancel-subscription/",
        "Disallow: /fuzeobs/reactivate-subscription/",
        "Disallow: /fuzeobs/collab/",
        "Disallow: /fuzeobs/leaderboard/",
        "Disallow: /fuzeobs/recaps",
        "Disallow: /fuzeobs/followers",
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

    # FuzeOBS API
    path('fuzeobs/', include('FUZEOBS.urls', namespace='FUZEOBS')),
]

# Static files only
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

handler500 = 'MAIN.views.custom_500'