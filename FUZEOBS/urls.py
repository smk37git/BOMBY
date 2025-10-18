from django.urls import path
from . import views

app_name = 'FUZEOBS'

urlpatterns = [
    path('login', views.fuzeobs_login, name='login'),
    path('verify', views.fuzeobs_verify, name='verify'),
    path('ai-chat', views.fuzeobs_ai_chat, name='ai_chat'),
]