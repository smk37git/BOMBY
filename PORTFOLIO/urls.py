from django.urls import path
from .views import *
from . import views

app_name = 'PORTFOLIO'

urlpatterns = [
    path('', views.portfolio, name='portfolio'),
    path('bomby-project/', views.bomby_project, name='bomby_project'),
    path('api/github-commit/<str:username>/<str:repo>/', views.github_latest_bomby_commit, name='github_commit'),
    path('fraternity-project/', views.fraternity_project, name='fraternity_project'),
    path('github-project/', views.github_project, name='github_project'),
    path('college-project/', views.college_project, name='college_project'),
    path('steam-workshop/', views.steam_workshop, name='steam_workshop'),
    path('stream-setup/', views.stream_setup, name='stream_setup'),
    path('api/github-commit/<str:username>/<str:repo>/', views.github_latest_fraternity_commit, name='github_commit'),
]