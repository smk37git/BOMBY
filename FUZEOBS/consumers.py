from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from .models import WidgetEvent

class AlertConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.group_name = f'alerts_{self.user_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
    
    async def alert_event(self, event):
        # Config can come from message (testing) or DB (real events)
        config = event['data'].get('config')
        
        # If no config in message, fetch from DB
        if not config:
            config = await self.get_event_config(
                event['data']['platform'],
                event['data']['event_type']
            )
        
        # Skip if no config found and not enabled
        if not config or not config.get('enabled', True):
            return
        
        # Send complete package
        await self.send_json({
            'platform': event['data']['platform'],
            'event_type': event['data']['event_type'],
            'event_data': event['data'].get('event_data', {}),
            'config': config
        })
    
    @database_sync_to_async
    def get_event_config(self, platform, event_type):
        try:
            from .models import WidgetConfig
            widget = WidgetConfig.objects.filter(
                user_id=self.user_id,
                widget_type='alert_box'
            ).first()
            
            if not widget:
                return None
            
            event = WidgetEvent.objects.filter(
                widget=widget,
                platform=platform,
                event_type=event_type
            ).first()
            
            return event.config if event else None
        except:
            return None