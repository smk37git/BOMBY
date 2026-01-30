from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/fuzeobs-alerts/<int:user_id>/', consumers.AlertConsumer.as_asgi()),
    path('ws/fuzeobs-alerts/<int:user_id>/<str:platform>/', consumers.AlertConsumer.as_asgi()),
    path('ws/fuzeobs-chat/<int:user_id>/', consumers.ChatConsumer.as_asgi()),
    path('ws/fuzeobs-goals/<int:user_id>/', consumers.GoalConsumer.as_asgi()),
    path('ws/fuzeobs-labels/<int:user_id>/', consumers.LabelsConsumer.as_asgi()),
    path('ws/fuzeobs-viewers/<int:user_id>/', consumers.ViewerCountConsumer.as_asgi()),
    path('ws/fuzeobs-sponsor/<int:user_id>/', consumers.SponsorBannerConsumer.as_asgi()),
    path('ws/fuzeobs-donations/<int:user_id>/', consumers.DonationConsumer.as_asgi()),
]