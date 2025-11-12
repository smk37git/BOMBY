from google.cloud import storage
import hashlib
import json

def generate_alert_box_html(user_id, config):
    return f"""<!DOCTYPE html>
<html>
<head>
<style>
body {{ background: transparent; margin: 0; overflow: hidden; }}
.alert {{
    font-family: {config.get('font', 'Arial')};
    font-size: {config.get('font_size', 32)}px;
    color: {config.get('text_color', '#FFFFFF')};
    text-align: center;
    padding: 20px;
    animation: slideIn 0.5s ease-out;
}}
@keyframes slideIn {{
    from {{ transform: translateY(-100%); opacity: 0; }}
    to {{ transform: translateY(0); opacity: 1; }}
}}
</style>
</head>
<body>
<div id="container"></div>
<script>
const ws = new WebSocket('wss://bomby.us/ws/alerts/{user_id}');
ws.onmessage = (e) => {{
    const data = JSON.parse(e.data);
    const alert = document.createElement('div');
    alert.className = 'alert';
    alert.textContent = data.message;
    document.getElementById('container').appendChild(alert);
    setTimeout(() => alert.remove(), {config.get('duration', 5000)});
}};
</script>
</body>
</html>"""

def generate_chat_box_html(user_id, config):
    return f"""<!DOCTYPE html>
<html>
<head>
<style>
body {{ 
    background: transparent; 
    margin: 0; 
    overflow: hidden;
    font-family: {config.get('font', 'Arial')};
}}
.chat-container {{
    max-height: {config.get('height', 400)}px;
    overflow-y: auto;
}}
.message {{
    padding: 8px;
    margin: 4px;
    background: {config.get('bg_color', 'rgba(0,0,0,0.5)')};
    border-radius: 4px;
    color: {config.get('text_color', '#FFFFFF')};
}}
.username {{ color: {config.get('username_color', '#00FF00')}; font-weight: bold; }}
</style>
</head>
<body>
<div class="chat-container" id="chat"></div>
<script>
const ws = new WebSocket('wss://bomby.us/ws/chat/{user_id}');
ws.onmessage = (e) => {{
    const data = JSON.parse(e.data);
    const msg = document.createElement('div');
    msg.className = 'message';
    msg.innerHTML = `<span class="username">${{data.username}}:</span> ${{data.message}}`;
    document.getElementById('chat').appendChild(msg);
    document.getElementById('chat').scrollTop = document.getElementById('chat').scrollHeight;
}};
</script>
</body>
</html>"""

def upload_to_gcs(html_content, user_id, widget_type):
    client = storage.Client()
    bucket = client.bucket('bomby-user-uploads')
    
    # Generate unique filename
    hash_id = hashlib.md5(f"{user_id}{widget_type}".encode()).hexdigest()[:8]
    blob_name = f'fuzeobs-widgets/{user_id}/{widget_type}_{hash_id}.html'
    
    blob = bucket.blob(blob_name)
    blob.upload_from_string(html_content, content_type='text/html')
    blob.make_public()
    
    return blob.public_url