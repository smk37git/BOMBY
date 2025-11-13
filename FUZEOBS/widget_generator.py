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

@keyframes fadeIn {{
    0% {{ opacity: 0; }}
    100% {{ opacity: 1; }}
}}
@keyframes slideIn {{
    0% {{ opacity: 0; transform: translateY(-100px); }}
    100% {{ opacity: 1; transform: translateY(0); }}
}}
@keyframes bounceIn {{
    0% {{ opacity: 0; transform: scale(0.3); }}
    50% {{ opacity: 1; transform: scale(1.05); }}
    70% {{ transform: scale(0.9); }}
    100% {{ opacity: 1; transform: scale(1); }}
}}
@keyframes zoomIn {{
    0% {{ opacity: 0; transform: scale(0); }}
    100% {{ opacity: 1; transform: scale(1); }}
}}

@keyframes textWiggle {{
    0%, 100% {{ transform: rotate(0deg); }}
    25% {{ transform: rotate(-3deg); }}
    75% {{ transform: rotate(3deg); }}
}}
@keyframes textWave {{
    0%, 100% {{ transform: translateY(0); }}
    50% {{ transform: translateY(-8px); }}
}}
@keyframes textBounce {{
    0%, 100% {{ transform: translateY(0); }}
    50% {{ transform: translateY(-12px); }}
}}
@keyframes textPulse {{
    0%, 100% {{ transform: scale(1); }}
    50% {{ transform: scale(1.08); }}
}}

@keyframes fadeOut {{
    0% {{ opacity: 1; }}
    100% {{ opacity: 0; }}
}}
</style>
</head>
<body>
<div id="container"></div>
<audio id="alertSound" preload="auto"></audio>
<script>
const userId = '{user_id}';
const ws = new WebSocket(`wss://bomby.us/ws/fuzeobs-alerts/${{userId}}`);
const eventConfigs = {{}};

// Load configs and auto-reload when changed
function loadConfigs() {{
    fetch(`/fuzeobs/widgets/events/config/${{userId}}?t=${{Date.now()}}`)
        .then(r => r.json())
        .then(data => {{
            const newVersion = JSON.stringify(data.configs);
            if (newVersion !== JSON.stringify(eventConfigs)) {{
                Object.keys(eventConfigs).forEach(k => delete eventConfigs[k]);
                Object.assign(eventConfigs, data.configs);
                console.log('Configs updated:', eventConfigs);
            }}
        }})
        .catch(err => console.log('Config error:', err));
}}

loadConfigs();
setInterval(loadConfigs, 3000); // Auto-poll like StreamLabs

ws.onmessage = (e) => {{
    const data = JSON.parse(e.data);
    const configKey = `${{data.platform}}-${{data.event_type}}`;
    const config = eventConfigs[configKey];
    
    if (!config || !config.enabled) return;
    
    const eventData = data.event_data || {{}};
    let message = config.message_template || '{{{{name}}}} just followed!';
    message = message.replace(/{{{{name}}}}/g, eventData.username || "Someone");
    message = message.replace(/{{{{amount}}}}/g, eventData.amount || '');
    
    const layout = config.layout || 'standard';
    const alertAnim = config.alert_animation || 'fade';
    
    // Create container
    const alertWrap = document.createElement('div');
    alertWrap.style.position = 'absolute';
    alertWrap.style.top = '50%';
    alertWrap.style.left = '50%';
    alertWrap.style.transform = 'translate(-50%, -50%)';
    
    if (layout === 'standard' || layout === 'image_above') {{
        alertWrap.style.display = 'flex';
        alertWrap.style.flexDirection = 'column';
        alertWrap.style.alignItems = 'center';
        alertWrap.style.textAlign = 'center';
        
        if (config.image_url) {{
            const img = document.createElement('img');
            img.src = config.image_url;
            img.style.maxWidth = '300px';
            img.style.marginBottom = '20px';
            img.style.display = 'block';
            alertWrap.appendChild(img);
        }}
        
        const text = document.createElement('div');
        text.textContent = message;
        applyTextStyles(text, config);
        alertWrap.appendChild(text);
        
    }} else if (layout === 'image_left') {{
        alertWrap.style.display = 'flex';
        alertWrap.style.flexDirection = 'row';
        alertWrap.style.alignItems = 'center';
        alertWrap.style.gap = '20px';
        
        if (config.image_url) {{
            const img = document.createElement('img');
            img.src = config.image_url;
            img.style.maxWidth = '200px';
            img.style.display = 'block';
            alertWrap.appendChild(img);
        }}
        
        const text = document.createElement('div');
        text.textContent = message;
        applyTextStyles(text, config);
        alertWrap.appendChild(text);
        
    }} else if (layout === 'text_over_image') {{
        if (config.image_url) {{
            const imgWrap = document.createElement('div');
            imgWrap.style.position = 'relative';
            imgWrap.style.display = 'inline-block';
            
            const img = document.createElement('img');
            img.src = config.image_url;
            img.style.maxWidth = '400px';
            img.style.display = 'block';
            imgWrap.appendChild(img);
            
            const text = document.createElement('div');
            text.textContent = message;
            text.style.position = 'absolute';
            text.style.top = '50%';
            text.style.left = '50%';
            text.style.transform = 'translate(-50%, -50%)';
            text.style.width = '90%';
            text.style.textAlign = 'center';
            applyTextStyles(text, config);
            imgWrap.appendChild(text);
            
            alertWrap.appendChild(imgWrap);
        }} else {{
            const text = document.createElement('div');
            text.textContent = message;
            text.style.textAlign = 'center';
            applyTextStyles(text, config);
            alertWrap.appendChild(text);
        }}
    }}
    
    // Apply animation
    alertWrap.style.animation = `${{alertAnim}}In 0.5s ease-out forwards`;
    alertWrap.style.opacity = '0';
    
    // Sound
    if (config.sound_url) {{
        const audio = document.getElementById('alertSound');
        audio.src = config.sound_url;
        audio.volume = (config.sound_volume || 50) / 100;
        audio.play().catch(e => {{}});
    }}
    
    document.getElementById('container').appendChild(alertWrap);
    
    // Remove
    const duration = (config.duration || 5) * 1000;
    setTimeout(() => {{
        alertWrap.style.animation = 'fadeOut 0.5s ease-out forwards';
        setTimeout(() => alertWrap.remove(), 500);
    }}, duration);
}};

function applyTextStyles(text, config) {{
    text.style.fontSize = (config.font_size || 32) + 'px';
    text.style.fontWeight = config.font_weight || 'normal';
    text.style.color = config.text_color || '#FFFFFF';
    text.style.textShadow = config.text_shadow !== false ? '2px 2px 4px rgba(0,0,0,0.8)' : 'none';
    
    const textAnim = config.text_animation || 'none';
    if (textAnim !== 'none') {{
        text.style.animation = `text${{textAnim.charAt(0).toUpperCase() + textAnim.slice(1)}} 1s ease-in-out infinite`;
    }}
}}

ws.onerror = (error) => console.error('WebSocket error:', error);
</script>
</body>
</html>"""

def generate_chat_box_html(user_id, config):
    height = config.get('height', 400)
    bg_color = config.get('bg_color', 'rgba(0,0,0,0.5)')
    text_color = config.get('text_color', '#FFFFFF')
    username_color = config.get('username_color', '#00FF00')
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ background: transparent; margin: 0; overflow: hidden; font-family: 'Arial', sans-serif; }}
.chat-container {{ max-height: {height}px; overflow-y: auto; padding: 10px; }}
.chat-container::-webkit-scrollbar {{ width: 8px; }}
.chat-container::-webkit-scrollbar-track {{ background: rgba(0,0,0,0.3); }}
.chat-container::-webkit-scrollbar-thumb {{ background: rgba(255,255,255,0.3); border-radius: 4px; }}
.message {{ padding: 8px; margin: 4px 0; background: {bg_color}; border-radius: 4px; color: {text_color}; word-wrap: break-word; }}
.username {{ color: {username_color}; font-weight: bold; margin-right: 5px; }}
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
    while (chat.children.length > 50) chat.removeChild(chat.firstChild);
}};
</script>
</body>
</html>"""

def generate_event_list_html(user_id, config):
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ background: transparent; margin: 0; padding: 10px; font-family: 'Arial', sans-serif; color: white; }}
.event {{ background: rgba(0,0,0,0.7); padding: 10px; margin: 5px 0; border-radius: 5px; display: flex; align-items: center; animation: slideInLeft 0.3s ease-out; }}
@keyframes slideInLeft {{ from {{ transform: translateX(-100%); opacity: 0; }} to {{ transform: translateX(0); opacity: 1; }} }}
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
    event.innerHTML = `<div class="event-icon">${{getEventIcon(data.type)}}</div><div class="event-text">${{data.username}} ${{data.action}}</div>`;
    const container = document.getElementById('events');
    container.insertBefore(event, container.firstChild);
    while (container.children.length > 10) container.removeChild(container.lastChild);
}};
function getEventIcon(type) {{ const icons = {{'follow': 'â¤ï¸', 'subscribe': 'â­', 'bits': 'ðŸ'Ž', 'donation': 'ðŸ'°', 'raid': 'ðŸ'¥'}}; return icons[type] || 'ðŸŽ‰'; }}
</script>
</body>
</html>"""

def generate_goal_bar_html(user_id, config):
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{ background: transparent; margin: 0; padding: 20px; font-family: 'Arial', sans-serif; }}
.goal-container {{ background: rgba(0,0,0,0.8); padding: 15px; border-radius: 10px; }}
.goal-title {{ color: white; font-size: 18px; margin-bottom: 10px; text-align: center; }}
.progress-bar {{ background: rgba(255,255,255,0.2); height: 30px; border-radius: 15px; overflow: hidden; }}
.progress-fill {{ background: linear-gradient(90deg, #00ff00, #00cc00); height: 100%; transition: width 0.5s ease; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; }}
</style>
</head>
<body>
<div class="goal-container">
    <div class="goal-title" id="title">Loading...</div>
    <div class="progress-bar"><div class="progress-fill" id="progress" style="width: 0%"><span id="progressText">0%</span></div></div>
</div>
<script>
const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-goals/{user_id}');
ws.onmessage = (e) => {{ const data = JSON.parse(e.data); document.getElementById('title').textContent = data.title; const percentage = (data.current / data.goal) * 100; document.getElementById('progress').style.width = percentage + '%'; document.getElementById('progressText').textContent = `${{data.current}} / ${{data.goal}} (${{Math.round(percentage)}}%)`; }};
</script>
</body>
</html>"""

def upload_to_gcs(html_content, user_id, widget_type):
    client = storage.Client()
    bucket = client.bucket('bomby-user-uploads')
    hash_id = hashlib.md5(f"{user_id}{widget_type}{html_content[:100]}".encode()).hexdigest()[:8]
    blob_name = f'fuzeobs-widgets/{user_id}/{widget_type}_{hash_id}.html'
    blob = bucket.blob(blob_name)
    blob.upload_from_string(html_content, content_type='text/html')
    blob.make_public()
    return blob.public_url