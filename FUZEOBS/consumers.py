from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from .models import WidgetConfig

class AlertConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.widget_token = self.scope['url_route']['kwargs']['widget_token']
        
        # Get widget and verify it exists
        widget = await self.get_widget(self.widget_token)
        if not widget:
            await self.close()
            return
        
        self.user_id = widget.user_id
        self.platform = widget.platform
        self.group_name = f'alerts_{self.user_id}_{self.platform}'
        
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
    
    async def alert_event(self, event):
        await self.send_json(event['data'])
    
    @database_sync_to_async
    def get_widget(self, token):
        try:
            return WidgetConfig.objects.get(token=token)
        except WidgetConfig.DoesNotExist:
            return None