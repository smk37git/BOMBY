from channels.generic.websocket import AsyncJsonWebsocketConsumer

class AlertConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.platform = self.scope['url_route']['kwargs']['platform']
        self.group_name = f'alerts_{self.user_id}_{self.platform}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
    
    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
    
    async def alert_event(self, event):
        await self.send_json(event['data'])