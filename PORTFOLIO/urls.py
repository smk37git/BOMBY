from django.urls import path
from .views import *
from . import views

app_name = 'PORTFOLIO'

urlpatterns = [
    path('', views.portfolio, name='portfolio'),
    path('bomby-project/', views.bomby_project, name='bomby_project'),
    path('api/github-commit/<str:username>/<str:repo>/', views.github_latest_commit, name='github_commit'),
]