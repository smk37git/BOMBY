from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/fuze-alerts/<int:user_id>/<str:platform>/', consumers.AlertConsumer.as_asgi()),
    path('ws/fuze-chat/<int:user_id>/', consumers.ChatConsumer.as_asgi()),
    path('ws/fuze-goals/<int:user_id>/', consumers.GoalConsumer.as_asgi()),
    path('ws/fuze-labels/<int:user_id>/', consumers.LabelsConsumer.as_asgi()),
    path('ws/fuze-viewers/<int:user_id>/', consumers.ViewerCountConsumer.as_asgi()),
    path('ws/fuze-sponsor/<int:user_id>/', consumers.SponsorBannerConsumer.as_asgi()),
    path('ws/fuze-donations/<int:user_id>/', consumers.DonationConsumer.as_asgi()),
]