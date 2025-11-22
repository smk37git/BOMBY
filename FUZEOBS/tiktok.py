import threading
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, DisconnectEvent, FollowEvent, GiftEvent, ShareEvent, LikeEvent
from .twitch import send_alert

tiktok_clients = {}
tiktok_client_lock = threading.Lock()

def start_tiktok_listener(user_id, tiktok_username):
    """Start TikTok listener using reverse-engineered library"""
    print(f'[TIKTOK] Starting listener for @{tiktok_username} (user {user_id})')
    
    with tiktok_client_lock:
        if user_id in tiktok_clients:
            print(f'[TIKTOK] Already listening for user {user_id}')
            return True
    
    client = TikTokLiveClient(unique_id=f"@{tiktok_username}")
    
    @client.on("connect")
    async def on_connect(event: ConnectEvent):
        print(f'[TIKTOK] ✓ Connected to @{tiktok_username}')
    
    @client.on("disconnect")
    async def on_disconnect(event: DisconnectEvent):
        print(f'[TIKTOK] Disconnected from @{tiktok_username}')
        with tiktok_client_lock:
            tiktok_clients.pop(user_id, None)
    
    @client.on("follow")
    async def on_follow(event: FollowEvent):
        send_alert(user_id, 'follow', 'tiktok', {'username': event.user.nickname})
        print(f'[TIKTOK] ✓ Follow from {event.user.nickname}')
    
    @client.on("gift")
    async def on_gift(event: GiftEvent):
        if event.gift.streakable and not event.gift.streaking:
            send_alert(user_id, 'gift', 'tiktok', {
                'username': event.user.nickname,
                'gift': event.gift.info.name,
                'count': event.gift.repeat_count
            })
            print(f'[TIKTOK] ✓ Gift from {event.user.nickname}: {event.gift.repeat_count}x {event.gift.info.name}')
    
    @client.on("share")
    async def on_share(event: ShareEvent):
        send_alert(user_id, 'share', 'tiktok', {'username': event.user.nickname})
        print(f'[TIKTOK] ✓ Share from {event.user.nickname}')
    
    @client.on("like")
    async def on_like(event: LikeEvent):
        if event.likeCount >= 10:
            send_alert(user_id, 'like', 'tiktok', {
                'username': event.user.nickname,
                'count': event.likeCount
            })
            print(f'[TIKTOK] ✓ {event.likeCount} likes from {event.user.nickname}')
    
    def run_client():
        try:
            client.run()
        except Exception as e:
            print(f'[TIKTOK] Error: {e}')
            with tiktok_client_lock:
                tiktok_clients.pop(user_id, None)
    
    with tiktok_client_lock:
        tiktok_clients[user_id] = client
    
    thread = threading.Thread(target=run_client, daemon=True, name=f'tiktok-{user_id}')
    thread.start()
    return True

def stop_tiktok_listener(user_id):
    """Stop TikTok listener"""
    print(f'[TIKTOK] Stopping listener for user {user_id}')
    
    with tiktok_client_lock:
        if user_id in tiktok_clients:
            try:
                tiktok_clients[user_id].disconnect()
            except:
                pass
            tiktok_clients.pop(user_id, None)
        else:
            print(f'[TIKTOK] No active listener for user {user_id}')