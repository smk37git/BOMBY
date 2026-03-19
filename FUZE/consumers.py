import os
import time
import hmac
import hashlib
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

# Config: (group_prefix, event_handler_name, extra_url_kwargs, requires_auth)
# Widget consumers (alerts, chat, goals, etc.) are open — OBS browser sources can't send auth headers.
# They only RECEIVE events, never send sensitive data, so this is acceptable.
CONSUMER_CONFIG = {
    'alert': ('alerts', 'alert_event', ['platform'], False),
    'chat': ('chat', 'chat_message', [], False),
    'goal': ('goals', 'goal_update', [], False),
    'labels': ('labels', 'label_update', [], False),
    'viewer_count': ('viewers', 'viewer_update', [], False),
    'sponsor_banner': ('sponsor', 'sponsor_update', [], False),
    'donation': ('donations', 'donation_event', [], False),
}


class BaseConsumer(AsyncJsonWebsocketConsumer):
    """Base consumer - subclasses just set consumer_type"""
    consumer_type: str = None
    
    async def connect(self):
        config = CONSUMER_CONFIG[self.consumer_type]
        prefix, _, extra_kwargs, requires_auth = config
        
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        
        # Validate user_id exists
        if not await self._user_exists(self.user_id):
            await self.close()
            return
        
        # Build group name with optional extra kwargs (e.g., platform)
        group_parts = [prefix, str(self.user_id)]
        for kwarg in extra_kwargs:
            value = self.scope['url_route']['kwargs'].get(kwarg)
            if value:
                # Sanitize: only allow alphanumeric and underscore
                clean = ''.join(c for c in str(value) if c.isalnum() or c == '_')
                setattr(self, kwarg, clean)
                group_parts.append(clean)
        
        self.group_name = '_'.join(group_parts)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def _user_exists(self, user_id):
        User = get_user_model()
        return User.objects.filter(id=user_id).exists()


def _make_handler(event_name):
    """Create event handler that forwards data to client"""
    async def handler(self, event):
        await self.send_json(event['data'])
    handler.__name__ = event_name
    return handler


def _create_consumer_class(consumer_type: str):
    """Factory to create consumer class from config"""
    config = CONSUMER_CONFIG[consumer_type]
    _, event_name, _, _ = config
    
    return type(
        f'{consumer_type.title().replace("_", "")}Consumer',
        (BaseConsumer,),
        {
            'consumer_type': consumer_type,
            event_name: _make_handler(event_name),
        }
    )


# Generate all consumer classes - maintains same public API
AlertConsumer = _create_consumer_class('alert')
ChatConsumer = _create_consumer_class('chat')
GoalConsumer = _create_consumer_class('goal')
LabelsConsumer = _create_consumer_class('labels')
ViewerCountConsumer = _create_consumer_class('viewer_count')
SponsorBannerConsumer = _create_consumer_class('sponsor_banner')
DonationConsumer = _create_consumer_class('donation')