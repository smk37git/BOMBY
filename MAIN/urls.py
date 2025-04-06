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
]