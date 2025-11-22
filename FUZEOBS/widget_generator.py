def generate_widget_html(widget):
    """Generate HTML for widget object"""
    user_id = widget.user.id
    widget_type = widget.widget_type
    platform = widget.platform
    config = widget.config
    
    if widget_type == 'alert_box':
        return generate_alert_box_html(user_id, platform, config)
    elif widget_type == 'chat_box':
        return generate_chat_box_html(user_id, config)
    elif widget_type == 'event_list':
        return generate_event_list_html(user_id, config)
    elif widget_type == 'goal_bar':
        return generate_goal_bar_html(user_id, config)
    else:
        raise ValueError(f"Unknown widget type: {widget_type}")

def generate_alert_box_html(user_id, platform, config):
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
    max-width: 90vw;
    max-height: 90vh;
}}
.alert-image {{
    max-width: min(600px, 70vw);
    max-height: min(600px, 60vh);
    width: auto;
    height: auto;
    object-fit: contain;
}}
.alert-text {{
    font-size: 32px;
    color: #FFFFFF;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
    margin: 10px 0;
    word-wrap: break-word;
    max-width: 90vw;
}}

/* Alert Animations */
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
@keyframes rotateIn {{
    from {{ transform: translate(-50%, -50%) rotate(-180deg) scale(0); opacity: 0; }}
    to {{ transform: translate(-50%, -50%) rotate(0deg) scale(1); opacity: 1; }}
}}

/* Text Animations */
@keyframes wiggle {{
    0%, 100% {{ transform: rotate(0deg); }}
    25% {{ transform: rotate(-5deg); }}
    75% {{ transform: rotate(5deg); }}
}}
@keyframes wave {{
    0%, 100% {{ transform: translateY(0); }}
    50% {{ transform: translateY(-10px); }}
}}
@keyframes bounce {{
    0%, 100% {{ transform: translateY(0); }}
    50% {{ transform: translateY(-15px); }}
}}
@keyframes pulse {{
    0%, 100% {{ transform: scale(1); }}
    50% {{ transform: scale(1.05); }}
}}

@keyframes fadeOut {{
    from {{ opacity: 1; }}
    to {{ opacity: 0; }}
}}
</style>
</head>
<body>
<div id="container"></div>
<audio id="alertSound" preload="auto"></audio>
<script>
const userId = '{user_id}';
const platform = '{platform}';

// Start YouTube listener if platform is YouTube
if (platform === 'youtube') {{
    fetch(`https://bomby.us/fuzeobs/youtube/start/${{userId}}`)
        .then(r => r.json())
        .then(data => {{
            if (data.started) {{
                console.log('[YOUTUBE] Listener started');
            }} else {{
                console.log('[YOUTUBE] Not live or already running');
            }}
        }})
        .catch(err => console.log('[YOUTUBE] Start failed:', err));
    
    // Re-check every 5 minutes in case stream starts later
    setInterval(() => {{
        fetch(`https://bomby.us/fuzeobs/youtube/start/${{userId}}`)
            .catch(() => {{}});
    }}, 300000);
}}

// Start Facebook listener if platform is Facebook
if (platform === 'facebook') {{
    fetch(`https://bomby.us/fuzeobs/facebook/start/${{userId}}`)
        .then(r => r.json())
        .then(data => {{
            if (data.started) {{
                console.log('[FACEBOOK] Listener started');
            }} else {{
                console.log('[FACEBOOK] Not active or already running');
            }}
        }})
        .catch(err => console.log('[FACEBOOK] Start failed:', err));
    
    // Re-check every 5 minutes
    setInterval(() => {{
        fetch(`https://bomby.us/fuzeobs/facebook/start/${{userId}}`)
            .catch(() => {{}});
    }}, 300000);
}}

const ws = new WebSocket(`wss://bomby.us/ws/fuzeobs-alerts/${{userId}}/${{platform}}/`);

const defaultConfig = {{
    enabled: true,
    alert_animation: 'fade',
    font_size: 32,
    font_weight: 'normal',
    font_family: 'Arial',
    text_color: '#FFFFFF',
    message_template: '{{name}} just followed!',
    duration: 5,
    sound_volume: 50,
    layout: 'image_above'
}};

const eventConfigs = {{}};
let configsLoaded = false;

fetch(`https://bomby.us/fuzeobs/widgets/events/config/${{userId}}/${{platform}}?t=${{Date.now()}}`)
    .then(r => r.json())
    .then(data => {{
        Object.assign(eventConfigs, data.configs);
        configsLoaded = true;
    }})
    .catch(err => {{
        configsLoaded = true;
    }});

ws.onmessage = (e) => {{
    const data = JSON.parse(e.data);
    
    if (data.type === 'refresh') {{
        window.location.reload();
        return;
    }}
    
    if (data.clear_existing) {{
        document.getElementById('container').innerHTML = '';
    }}
    
    const configKey = `${{data.platform}}-${{data.event_type}}`;
    const config = eventConfigs[configKey] || defaultConfig;
    
    if (!config.enabled) return;
    
    const alert = document.createElement('div');
    alert.className = 'alert';
    
    const layout = config.layout || 'image_above';
    
    if (layout === 'image_above') {{
        alert.style.display = 'flex';
        alert.style.flexDirection = 'column';
        alert.style.alignItems = 'center';
        alert.style.gap = '15px';
    }} else if (layout === 'image_left') {{
        alert.style.display = 'flex';
        alert.style.flexDirection = 'row';
        alert.style.alignItems = 'center';
        alert.style.gap = '20px';
    }} else if (layout === 'image_right') {{
        alert.style.display = 'flex';
        alert.style.flexDirection = 'row-reverse';
        alert.style.alignItems = 'center';
        alert.style.gap = '20px';
    }} else if (layout === 'text_over_image') {{
        alert.style.display = 'inline-block';
    }}
    
    const animation = config.alert_animation || 'fade';
    alert.style.animation = `${{animation}}In 0.5s ease-out forwards`;
    
    if (config.image_url) {{
        const imgContainer = document.createElement('div');
        if (layout === 'text_over_image') {{
            imgContainer.style.position = 'relative';
            imgContainer.style.display = 'inline-block';
        }}
        
        const img = document.createElement('img');
        img.src = config.image_url;
        img.className = 'alert-image';
        img.style.display = 'block';
        imgContainer.appendChild(img);
        alert.appendChild(imgContainer);
    }}
    
    const text = document.createElement('div');
    text.className = 'alert-text';
    text.style.fontSize = (config.font_size || 32) + 'px';
    text.style.fontWeight = config.font_weight || 'normal';
    text.style.fontFamily = config.font_family || 'Arial';
    text.style.color = config.text_color || '#FFFFFF';
    
    if (config.text_shadow) {{
        text.style.textShadow = '2px 2px 4px rgba(0,0,0,0.8)';
    }}
    
    const eventData = data.event_data || {{}};
    let message = config.message_template || '{{name}} just followed!';
    message = message.replace(/{{name}}/g, eventData.username || "Someone");
    message = message.replace(/{{amount}}/g, eventData.amount || '');
    message = message.replace(/{{viewers}}/g, eventData.viewers || '');
    message = message.replace(/{{months}}/g, eventData.months || '');
    message = message.replace(/{{count}}/g, eventData.count || '');
    text.textContent = message;
    
    if (config.text_animation && config.text_animation !== 'none') {{
        text.style.animation = `${{config.text_animation}} 1s ease-in-out infinite`;
    }}
    
    if (layout === 'text_over_image' && config.image_url) {{
        const textWrapper = document.createElement('div');
        textWrapper.style.position = 'absolute';
        textWrapper.style.top = '50%';
        textWrapper.style.left = '50%';
        textWrapper.style.transform = 'translate(-50%, -50%)';
        textWrapper.style.zIndex = '10';
        textWrapper.style.margin = '0';
        textWrapper.style.width = '100%';
        textWrapper.style.padding = '0 10px';
        textWrapper.style.boxSizing = 'border-box';
        textWrapper.appendChild(text);
        alert.firstChild.appendChild(textWrapper);
    }} else {{
        alert.appendChild(text);
    }}
    
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
        'raid': '🔥',
        'superchat': '💵',
        'member': '🌟',
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