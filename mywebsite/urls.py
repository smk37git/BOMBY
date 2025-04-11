from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include(('MAIN.urls', 'MAIN'), namespace='MAIN')),
    path('accounts/', include('ACCOUNTS.urls', namespace='ACCOUNTS')),
    path('portfolio/', include('PORTFOLIO.urls', namespace='PORTFOLIO')),
    path('store/', include('STORE.urls', namespace='STORE')),
    
    # Add this line for serving media files in all environments
    path('media/<path:path>', serve, {'document_root': settings.MEDIA_ROOT}),
]

# Static files only
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)