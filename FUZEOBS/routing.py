from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/fuzeobs-alerts/<str:widget_token>/', consumers.AlertConsumer.as_asgi()),
]