from google.cloud import storage
import hashlib
import json

def generate_widget_html(user_id, widget_type, config):
    """Generate HTML for different widget types"""
    
    if widget_type == 'alert_box':
        return generate_alert_box_html(user_id, config)
    elif widget_type == 'chat_box':
        return generate_chat_box_html(user_id, config)
    elif widget_type == 'event_list':
        return generate_event_list_html(user_id, config)
    elif widget_type == 'goal_bar':
        return generate_goal_bar_html(user_id, config)
    else:
        raise ValueError(f"Unknown widget type: {widget_type}")

def generate_alert_box_html(user_id, config):
    """Generate alert box HTML with event support"""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{
    background: transparent;
    margin: 0;
    overflow: hidden;
    font-family: 'Arial', sans-serif;
}}
#container {{
    position: relative;
    width: 100%;
    height: 100vh;
}}
.alert {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    text-align: center;
    opacity: 0;
}}
.alert-image {{
    max-width: 300px;
    margin-bottom: 20px;
}}
.alert-text {{
    font-size: 32px;
    color: #FFFFFF;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
    margin: 10px 0;
}}
/* Animations */
@keyframes fadeIn {{
    from {{ opacity: 0; }}
    to {{ opacity: 1; }}
}}
@keyframes slideIn {{
    from {{ transform: translate(-50%, -100%); opacity: 0; }}
    to {{ transform: translate(-50%, -50%); opacity: 1; }}
}}
@keyframes bounceIn {{
    0% {{ transform: translate(-50%, -50%) scale(0); opacity: 0; }}
    50% {{ transform: translate(-50%, -50%) scale(1.1); }}
    100% {{ transform: translate(-50%, -50%) scale(1); opacity: 1; }}
}}
@keyframes zoomIn {{
    from {{ transform: translate(-50%, -50%) scale(0); opacity: 0; }}
    to {{ transform: translate(-50%, -50%) scale(1); opacity: 1; }}
}}
/* Text animations */
@keyframes wiggle {{
    0%, 100% {{ transform: rotate(0deg); }}
    25% {{ transform: rotate(-5deg); }}
    75% {{ transform: rotate(5deg); }}
}}
@keyframes wave {{
    0%, 100% {{ transform: translateY(0); }}
    50% {{ transform: translateY(-10px); }}
}}
</style>
</head>
<body>
<div id="container"></div>
<audio id="alertSound" preload="auto"></audio>
<script>
const userId = '{user_id}';
const ws = new WebSocket(`wss://bomby.us/ws/fuzeobs-alerts/${{userId}}`);

// Default configuration for when no config exists
const defaultConfig = {{
    enabled: true,
    alert_animation: 'fade',
    font_size: 32,
    text_color: '#FFFFFF',
    message_template: '{{{{name}}}} just followed!',
    duration: 5,
    sound_volume: 50
}};

// Event configurations fetched from server
const eventConfigs = {{}};

ws.onmessage = (e) => {{
    const data = JSON.parse(e.data);
    const configKey = `${{data.platform}}-${{data.event_type}}`;
    
    // Use saved config if exists, otherwise use default
    const config = eventConfigs[configKey] || defaultConfig;
    
    if (!config.enabled) return;
    
    const alert = document.createElement('div');
    alert.className = 'alert';
    
    const animation = config.alert_animation || 'fade';
    alert.style.animation = `${{animation}}In 0.5s ease-out forwards`;
    
    if (config.image_url) {{
        const img = document.createElement('img');
        img.src = config.image_url;
        img.className = 'alert-image';
        alert.appendChild(img);
    }}
    
    const text = document.createElement('div');
    text.className = 'alert-text';
    text.style.fontSize = (config.font_size || 32) + 'px';
    text.style.color = config.text_color || '#FFFFFF';
    
    let message = config.message_template || '{{{{name}}}} just followed!';
    message = message.replace(/{{{{name}}}}/g, data.username);
    message = message.replace(/{{{{amount}}}}/g, data.amount || '');
    text.textContent = message;
    
    if (config.text_animation && config.text_animation !== 'none') {{
        text.style.animation = `${{config.text_animation}} 1s ease-in-out infinite`;
    }}
    
    alert.appendChild(text);
    
    if (config.sound_url) {{
        const audio = document.getElementById('alertSound');
        audio.src = config.sound_url;
        audio.volume = (config.sound_volume || 50) / 100;
        audio.play().catch(err => console.log('Audio play failed:', err));
    }}
    
    document.getElementById('container').appendChild(alert);
    
    const duration = (config.duration || 5) * 1000;
    setTimeout(() => {{
        alert.style.animation = 'fadeOut 0.5s ease-out forwards';
        setTimeout(() => alert.remove(), 500);
    }}, duration);
}};

ws.onerror = (error) => {{
    console.error('WebSocket error:', error);
}};

// Fetch event configurations (optional - falls back to defaults)
fetch(`/fuzeobs/widgets/events/config/${{userId}}`)
    .then(r => r.json())
    .then(data => {{
        Object.assign(eventConfigs, data.configs);
        console.log('Loaded configs:', eventConfigs);
    }})
    .catch(err => console.log('Using default config:', err));
</script>
</body>
</html>"""

def generate_chat_box_html(user_id, config):
    """Generate chat box HTML"""
    height = config.get('height', 400)
    bg_color = config.get('bg_color', 'rgba(0,0,0,0.5)')
    text_color = config.get('text_color', '#FFFFFF')
    username_color = config.get('username_color', '#00FF00')
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{
    background: transparent;
    margin: 0;
    overflow: hidden;
    font-family: 'Arial', sans-serif;
}}
.chat-container {{
    max-height: {height}px;
    overflow-y: auto;
    padding: 10px;
}}
.chat-container::-webkit-scrollbar {{
    width: 8px;
}}
.chat-container::-webkit-scrollbar-track {{
    background: rgba(0,0,0,0.3);
}}
.chat-container::-webkit-scrollbar-thumb {{
    background: rgba(255,255,255,0.3);
    border-radius: 4px;
}}
.message {{
    padding: 8px;
    margin: 4px 0;
    background: {bg_color};
    border-radius: 4px;
    color: {text_color};
    word-wrap: break-word;
}}
.username {{
    color: {username_color};
    font-weight: bold;
    margin-right: 5px;
}}
</style>
</head>
<body>
<div class="chat-container" id="chat"></div>
<script>
const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-chat/{user_id}');

ws.onmessage = (e) => {{
    const data = JSON.parse(e.data);
    const msg = document.createElement('div');
    msg.className = 'message';
    msg.innerHTML = `<span class="username">${{data.username}}:</span>${{data.message}}`;
    
    const chat = document.getElementById('chat');
    chat.appendChild(msg);
    chat.scrollTop = chat.scrollHeight;
    
    // Keep only last 50 messages
    while (chat.children.length > 50) {{
        chat.removeChild(chat.firstChild);
    }}
}};
</script>
</body>
</html>"""

def generate_event_list_html(user_id, config):
    """Generate event list HTML"""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{
    background: transparent;
    margin: 0;
    padding: 10px;
    font-family: 'Arial', sans-serif;
    color: white;
}}
.event {{
    background: rgba(0,0,0,0.7);
    padding: 10px;
    margin: 5px 0;
    border-radius: 5px;
    display: flex;
    align-items: center;
    animation: slideInLeft 0.3s ease-out;
}}
@keyframes slideInLeft {{
    from {{ transform: translateX(-100%); opacity: 0; }}
    to {{ transform: translateX(0); opacity: 1; }}
}}
.event-icon {{ font-size: 24px; margin-right: 10px; }}
.event-text {{ flex: 1; }}
</style>
</head>
<body>
<div id="events"></div>
<script>
const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-events/{user_id}');
ws.onmessage = (e) => {{
    const data = JSON.parse(e.data);
    const event = document.createElement('div');
    event.className = 'event';
    event.innerHTML = `
        <div class="event-icon">${{getEventIcon(data.type)}}</div>
        <div class="event-text">${{data.username}} ${{data.action}}</div>
    `;
    
    const container = document.getElementById('events');
    container.insertBefore(event, container.firstChild);
    
    // Keep only last 10 events
    while (container.children.length > 10) {{
        container.removeChild(container.lastChild);
    }}
}};

function getEventIcon(type) {{
    const icons = {{
        'follow': '❤️',
        'subscribe': '⭐',
        'bits': '💎',
        'donation': '💰',
        'raid': '👥'
    }};
    return icons[type] || '🎉';
}}
</script>
</body>
</html>"""

def generate_goal_bar_html(user_id, config):
    """Generate goal bar HTML"""
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{
    background: transparent;
    margin: 0;
    padding: 20px;
    font-family: 'Arial', sans-serif;
}}
.goal-container {{
    background: rgba(0,0,0,0.8);
    padding: 15px;
    border-radius: 10px;
}}
.goal-title {{
    color: white;
    font-size: 18px;
    margin-bottom: 10px;
    text-align: center;
}}
.progress-bar {{
    background: rgba(255,255,255,0.2);
    height: 30px;
    border-radius: 15px;
    overflow: hidden;
}}
.progress-fill {{
    background: linear-gradient(90deg, #00ff00, #00cc00);
    height: 100%;
    transition: width 0.5s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: bold;
}}
</style>
</head>
<body>
<div class="goal-container">
    <div class="goal-title" id="title">Loading...</div>
    <div class="progress-bar">
        <div class="progress-fill" id="progress" style="width: 0%">
            <span id="progressText">0%</span>
        </div>
    </div>
</div>
<script>
const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-goals/{user_id}');
ws.onmessage = (e) => {{
    const data = JSON.parse(e.data);
    document.getElementById('title').textContent = data.title;
    const percentage = (data.current / data.goal) * 100;
    document.getElementById('progress').style.width = percentage + '%';
    document.getElementById('progressText').textContent = 
        `${{data.current}} / ${{data.goal}} (${{Math.round(percentage)}}%)`;
}};
</script>
</body>
</html>"""

def upload_to_gcs(html_content, user_id, widget_type):
    """Upload widget HTML to Google Cloud Storage"""
    client = storage.Client()
    bucket = client.bucket('bomby-user-uploads')
    
    # Generate unique filename
    hash_id = hashlib.md5(f"{user_id}{widget_type}{html_content[:100]}".encode()).hexdigest()[:8]
    blob_name = f'fuzeobs-widgets/{user_id}/{widget_type}_{hash_id}.html'
    
    blob = bucket.blob(blob_name)
    blob.upload_from_string(html_content, content_type='text/html')
    blob.make_public()
    
    return blob.public_url