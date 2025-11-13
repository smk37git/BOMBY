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
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{
    background: transparent;
    margin: 0;
    overflow: hidden;
    font-family: Arial, sans-serif;
}}
#alert-container {{
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    display: none;
}}

/* Layout variants */
.layout-standard, .layout-image-above {{
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
}}
.layout-image-left {{
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 20px;
}}
.layout-text-over-image {{
    position: relative;
    display: inline-block;
}}
.layout-text-over-image .alert-text {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 90%;
}}

.alert-image {{ max-width: 300px; display: block; }}
.layout-image-left .alert-image {{ max-width: 200px; }}
.layout-text-over-image .alert-image {{ max-width: 400px; }}

/* Animations */
.anim-fade {{ animation: fadeIn 0.5s forwards; }}
.anim-slide {{ animation: slideIn 0.5s forwards; }}
.anim-bounce {{ animation: bounceIn 0.5s forwards; }}
.anim-zoom {{ animation: zoomIn 0.5s forwards; }}

.anim-fade.out {{ animation: fadeOut 0.5s forwards; }}
.anim-slide.out {{ animation: fadeOut 0.5s forwards; }}
.anim-bounce.out {{ animation: fadeOut 0.5s forwards; }}
.anim-zoom.out {{ animation: fadeOut 0.5s forwards; }}

@keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
@keyframes slideIn {{ from {{ opacity: 0; transform: translateY(-100px); }} to {{ opacity: 1; transform: translateY(0); }} }}
@keyframes bounceIn {{
    0% {{ opacity: 0; transform: scale(0.3); }}
    50% {{ opacity: 1; transform: scale(1.05); }}
    70% {{ transform: scale(0.9); }}
    100% {{ opacity: 1; transform: scale(1); }}
}}
@keyframes zoomIn {{ from {{ opacity: 0; transform: scale(0); }} to {{ opacity: 1; transform: scale(1); }} }}
@keyframes fadeOut {{ from {{ opacity: 1; }} to {{ opacity: 0; }} }}

/* Text animations */
.text-wiggle {{ animation: textWiggle 1s infinite; }}
.text-wave {{ animation: textWave 1s infinite; }}
.text-bounce {{ animation: textBounce 1s infinite; }}
.text-pulse {{ animation: textPulse 1s infinite; }}

@keyframes textWiggle {{ 0%, 100% {{ transform: rotate(0deg); }} 25% {{ transform: rotate(-3deg); }} 75% {{ transform: rotate(3deg); }} }}
@keyframes textWave {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-8px); }} }}
@keyframes textBounce {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-12px); }} }}
@keyframes textPulse {{ 0%, 100% {{ transform: scale(1); }} 50% {{ transform: scale(1.08); }} }}
</style>
</head>
<body>
<div id="alert-container">
    <img class="alert-image" id="alert-img" style="display:none">
    <div class="alert-text" id="alert-text"></div>
</div>
<audio id="alertSound" preload="auto"></audio>
<script>
const ws = new WebSocket(`wss://bomby.us/ws/fuzeobs-alerts/{user_id}`);
const eventConfigs = {{}};
let currentTimeout;

function loadConfigs() {{
    fetch(`/fuzeobs/widgets/events/config/{user_id}?t=${{Date.now()}}`)
        .then(r => r.json())
        .then(data => {{
            Object.keys(eventConfigs).forEach(k => delete eventConfigs[k]);
            Object.assign(eventConfigs, data.configs);
        }})
        .catch(() => {{}});
}}

loadConfigs();
setInterval(loadConfigs, 3000);

ws.onmessage = (e) => {{
    const data = JSON.parse(e.data);
    const configKey = `${{data.platform}}-${{data.event_type}}`;
    const cfg = eventConfigs[configKey];
    
    if (!cfg || !cfg.enabled) return;
    if (currentTimeout) clearTimeout(currentTimeout);
    
    const eventData = data.event_data || {{}};
    let message = (cfg.message_template || '{{{{name}}}} just followed!')
        .replace(/{{{{name}}}}/g, eventData.username || "Someone")
        .replace(/{{{{amount}}}}/g, eventData.amount || '');
    
    const container = document.getElementById('alert-container');
    const img = document.getElementById('alert-img');
    const text = document.getElementById('alert-text');
    
    // Reset
    container.className = '';
    container.style.display = 'none';
    img.style.display = 'none';
    text.className = 'alert-text';
    
    // Apply layout
    const layout = cfg.layout || 'standard';
    container.className = `layout-${{layout}}`;
    
    // Image
    if (cfg.image_url) {{
        img.src = cfg.image_url;
        img.style.display = 'block';
    }}
    
    // Text styling
    text.textContent = message;
    text.style.fontSize = (cfg.font_size || 32) + 'px';
    text.style.fontWeight = cfg.font_weight || 'normal';
    text.style.color = cfg.text_color || '#FFFFFF';
    text.style.textShadow = cfg.text_shadow !== false ? '2px 2px 4px rgba(0,0,0,0.8)' : 'none';
    
    const textAnim = cfg.text_animation || 'none';
    if (textAnim !== 'none') text.classList.add(`text-${{textAnim}}`);
    
    // Show with animation
    const alertAnim = cfg.alert_animation || 'fade';
    container.classList.add(`anim-${{alertAnim}}`);
    container.style.display = layout === 'text-over-image' ? 'inline-block' : 'flex';
    
    // Sound
    if (cfg.sound_url) {{
        const audio = document.getElementById('alertSound');
        audio.src = cfg.sound_url;
        audio.volume = (cfg.sound_volume || 50) / 100;
        audio.play().catch(() => {{}});
    }}
    
    // Hide after duration
    const duration = (cfg.duration || 5) * 1000;
    currentTimeout = setTimeout(() => {{
        container.classList.add('out');
        setTimeout(() => {{ container.style.display = 'none'; }}, 500);
    }}, duration);
}};
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