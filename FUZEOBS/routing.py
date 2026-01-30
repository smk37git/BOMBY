from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/fuzeobs-alerts/(?P<user_id>\d+)/$', consumers.AlertConsumer.as_asgi()),
    re_path(r'ws/fuzeobs-donations/(?P<user_id>\d+)/$', consumers.DonationConsumer.as_asgi()),
    re_path(r'ws/fuzeobs-chat/(?P<user_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/fuzeobs-goals/(?P<user_id>\d+)/$', consumers.GoalConsumer.as_asgi()),
    re_path(r'ws/fuzeobs-labels/(?P<user_id>\d+)/$', consumers.LabelsConsumer.as_asgi()),
    re_path(r'ws/fuzeobs-viewers/(?P<user_id>\d+)/$', consumers.ViewerCountConsumer.as_asgi()),
    re_path(r'ws/fuzeobs-sponsor/(?P<user_id>\d+)/$', consumers.SponsorBannerConsumer.as_asgi()),
]