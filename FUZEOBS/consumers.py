from channels.generic.websocket import AsyncJsonWebsocketConsumer

# Config: (group_prefix, event_handler_name, extra_url_kwargs)
CONSUMER_CONFIG = {
    'alert': ('alerts', 'alert_event', ['platform']),
    'chat': ('chat', 'chat_message', []),
    'goal': ('goals', 'goal_update', []),
    'labels': ('labels', 'label_update', []),
    'viewer_count': ('viewers', 'viewer_update', []),
    'sponsor_banner': ('sponsor', 'sponsor_update', []),
    'donation': ('donations', 'donation_event', []),
}


class BaseConsumer(AsyncJsonWebsocketConsumer):
    """Base consumer - subclasses just set consumer_type"""
    consumer_type: str = None
    
    async def connect(self):
        config = CONSUMER_CONFIG[self.consumer_type]
        prefix, _, extra_kwargs = config
        
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        
        # Build group name with optional extra kwargs (e.g., platform)
        group_parts = [prefix, str(self.user_id)]
        for kwarg in extra_kwargs:
            value = self.scope['url_route']['kwargs'].get(kwarg)
            if value:
                setattr(self, kwarg, value)
                group_parts.append(str(value))
        
        self.group_name = '_'.join(group_parts)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)


def _make_handler(event_name):
    """Create event handler that forwards data to client"""
    async def handler(self, event):
        await self.send_json(event['data'])
    handler.__name__ = event_name
    return handler


def _create_consumer_class(consumer_type: str):
    """Factory to create consumer class from config"""
    config = CONSUMER_CONFIG[consumer_type]
    _, event_name, _ = config
    
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