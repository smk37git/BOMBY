from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/fuzeobs-alerts/<int:user_id>/', consumers.AlertConsumer.as_asgi()),
]