from django.urls import path
from . import views

app_name = 'MAIN'

urlpatterns = [
    path('', views.home, name='home'),
    path('home', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('contact/', views.contact, name='contact'),
    path('admin-panel/', views.admin_panel, name='admin_panel'),
    path('coming-soon/', views.coming_soon, name='coming_soon'),

    # Announcement URLs
    path('announcements/', views.manage_announcements, name='manage_announcements'),
    path('announcements/edit/<int:announcement_id>/', views.edit_announcement, name='edit_announcement'),
    path('announcements/toggle/<int:announcement_id>/', views.toggle_announcement, name='toggle_announcement'),
    path('announcements/delete/<int:announcement_id>/', views.delete_announcement, name='delete_announcement'),
]