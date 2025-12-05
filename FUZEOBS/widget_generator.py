import json

def generate_widget_html(widget):
    """Generate HTML for widget object"""
    user_id = widget.user.id
    widget_type = widget.widget_type
    platform = widget.platform
    config = widget.config
    
    # Get user's connected platforms
    from .models import PlatformConnection
    connected_platforms = list(
        PlatformConnection.objects.filter(user_id=user_id).values_list('platform', flat=True)
    )
    
    if widget_type == 'alert_box':
        return generate_alert_box_html(user_id, platform, config)
    elif widget_type == 'chat_box':
        return generate_chat_box_html(user_id, config)
    elif widget_type == 'event_list':
        return generate_event_list_html(user_id, config, connected_platforms)
    elif widget_type == 'goal_bar':
        return generate_goal_bar_html(user_id, config, connected_platforms)
    elif widget_type == 'labels':
        return generate_labels_html(user_id, config, connected_platforms)
    elif widget_type == 'viewer_count':
        return generate_viewer_count_html(user_id, config, connected_platforms)
    elif widget_type == 'sponsor_banner':
        return generate_sponsor_banner_html(user_id, config)
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

if (platform === 'tiktok') {{
    fetch(`https://bomby.us/fuzeobs/tiktok/start/${{userId}}`)
        .then(r => r.json())
        .then(data => {{
            if (data.started) {{
                console.log('[TIKTOK] Listener started');
            }} else {{
                console.log('[TIKTOK] Not live or already running');
            }}
        }})
        .catch(err => console.log('[TIKTOK] Start failed:', err));
    
    // Re-check every 5 minutes
    setInterval(() => {{
        fetch(`https://bomby.us/fuzeobs/tiktok/start/${{userId}}`)
            .catch(() => {{}});
    }}, 300000);
}}

let ws;
function connectWS() {{
    ws = new WebSocket(`wss://bomby.us/ws/fuzeobs-alerts/${{userId}}/${{platform}}/`);
    ws.onmessage = handleMessage;
    ws.onclose = () => setTimeout(connectWS, 3000);
    ws.onerror = () => ws.close();
}}
connectWS();

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
        
        // Inject custom CSS
        let allCustomCss = '';
        for (const key in data.configs) {{
            const cfg = data.configs[key];
            if (cfg.custom_css_enabled && cfg.custom_css) {{
                allCustomCss += `/* ${{key}} */\\n${{cfg.custom_css}}\\n`;
            }}
        }}
        if (allCustomCss) {{
            const styleEl = document.createElement('style');
            styleEl.id = 'custom-css';
            styleEl.textContent = allCustomCss;
            document.head.appendChild(styleEl);
        }}
    }})
    .catch(err => {{
        configsLoaded = true;
    }});

function handleMessage(e) {{
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
</script>
</body>
</html>"""

def generate_chat_box_html(user_id, config):
    """Generate chat box HTML - matches preview exactly"""
    font_size = config.get('font_size', 24)
    font_color = config.get('font_color', '#FFFFFF')
    style = config.get('style', 'clean')
    hide_bots = config.get('hide_bots', True)
    hide_commands = config.get('hide_commands', False)
    muted_users = config.get('muted_users', [])
    bad_words = config.get('bad_words', [])
    show_platform_icon = config.get('show_platform_icon', True)
    chat_notification_enabled = config.get('chat_notification_enabled', False)
    notification_sound = config.get('notification_sound', '')
    notification_volume = config.get('notification_volume', 50)
    notification_threshold = config.get('notification_threshold', 0)
    chat_delay = config.get('chat_delay', 0)
    hide_after = config.get('hide_after', 30)
    always_show = config.get('always_show', False)
    custom_css = config.get('custom_css', '')
    show_twitch = config.get('show_twitch', True)
    show_youtube = config.get('show_youtube', True)
    show_kick = config.get('show_kick', True)
    show_facebook = config.get('show_facebook', True)
    show_tiktok = config.get('show_tiktok', True)
    
    # Badge/icon size scales with font (matches preview: Math.max(16, Math.floor(font_size * 0.85)))
    badge_size = max(16, int(font_size * 0.85))
    
    # Style-specific CSS - matches preview exactly
    style_css = {
        'clean': f'''
            .message {{
                background: transparent;
                padding: 4px 0;
                margin-bottom: 4px;
                text-shadow: 1px 1px 2px rgba(0,0,0,0.8), -1px -1px 2px rgba(0,0,0,0.8);
            }}
        ''',
        'boxed': f'''
            .message {{
                background: rgba(0,0,0,0.6);
                padding: 8px 12px;
                margin-bottom: 4px;
                border-radius: 4px;
            }}
        ''',
        'chunky': f'''
            .message {{
                background: rgba(0,0,0,0.85);
                padding: 8px 12px;
                margin-bottom: 4px;
                border-radius: 8px;
                border-left: 4px solid var(--user-color, #9146FF);
            }}
        ''',
        'old_school': f'''
            .message {{
                background: linear-gradient(180deg, rgba(60,60,60,0.9) 0%, rgba(40,40,40,0.9) 100%);
                padding: 4px 8px;
                margin-bottom: 4px;
                border: 1px solid rgba(255,255,255,0.2);
            }}
        ''',
        'twitch': f'''
            .message {{
                background: rgba(24,24,27,0.9);
                padding: 8px 12px;
                margin-bottom: 4px;
                border-radius: 4px;
            }}
        '''
    }
    
    current_style = style_css.get(style, style_css['clean'])
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
body {{
    background: transparent;
    margin: 0;
    overflow: hidden;
    font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
}}
.chat-container {{
    position: absolute;
    bottom: 0;
    left: 0;
    max-width: 75%;
    padding: 8px;
    overflow: hidden;
}}
.message {{
    font-size: {font_size}px;
    line-height: 1.4;
    color: {font_color};
    animation: slideIn 0.5s ease-out;
    word-break: break-word;
    overflow-wrap: break-word;
}}
{current_style}
@keyframes slideIn {{
    from {{ transform: translateX(30px); opacity: 0; }}
    to {{ transform: translateX(0); opacity: 1; }}
}}
.badge, .platform-icon {{
    display: inline-block;
    width: {badge_size}px;
    height: {badge_size}px;
    vertical-align: middle;
    margin-right: 6px;
    margin-bottom: 4px;
    object-fit: contain;
}}
.username {{
    font-weight: bold;
    margin-right: 6px;
    display: inline-block;
    white-space: nowrap;
}}
.emote {{
    display: inline-block;
    height: 1.5em;
    vertical-align: middle;
    margin: 0 2px;
}}
{custom_css}
</style>
</head>
<body>
<div class="chat-container" id="chat"></div>
<audio id="notificationSound"></audio>
<script>
const userId = '{user_id}';
const config = {{
    hide_bots: {str(hide_bots).lower()},
    hide_commands: {str(hide_commands).lower()},
    bad_words: {json.dumps(bad_words)},
    muted_users: {json.dumps(muted_users)},
    show_platform_icon: {str(show_platform_icon).lower()},
    show_twitch: {str(show_twitch).lower()},
    show_youtube: {str(show_youtube).lower()},
    show_kick: {str(show_kick).lower()},
    show_facebook: {str(show_facebook).lower()},
    show_tiktok: {str(show_tiktok).lower()},
    notification_enabled: {str(chat_notification_enabled).lower()},
    notification_sound: '{notification_sound}',
    notification_volume: {notification_volume},
    notification_threshold: {notification_threshold},
    chat_delay: {chat_delay},
    hide_after: {hide_after},
    always_show: {str(always_show).lower()}
}};

fetch(`https://bomby.us/fuzeobs/twitch-chat/start/${{userId}}`).catch(() => {{}});
fetch(`https://bomby.us/fuzeobs/kick-chat/start/${{userId}}`).catch(() => {{}});

let ws;
function connectWS() {{
    ws = new WebSocket('wss://bomby.us/ws/fuzeobs-chat/' + userId + '/');
    ws.onmessage = handleMessage;
    ws.onclose = () => setTimeout(connectWS, 3000);
    ws.onerror = () => ws.close();
}}
connectWS();

let lastActivity = Date.now();

const BOT_NAMES = ['nightbot', 'streamelements', 'streamlabs', 'moobot', 'fossabot'];

PLATFORM_ICONS = {{
    'twitch': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-platform.png',
    'youtube': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/youtube-platform.png',
    'kick': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-platform.png',
    'facebook': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/facebook-platform.png',
    'tiktok': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/tiktok-platform.png',
}}

const BADGE_URLS = {{
    twitch: {{
        'broadcaster': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-broadcaster.png',
        'moderator': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-moderator.png',
        'subscriber': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-subscriber.png',
        'vip': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-vip.png',
        'prime': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-prime.png',
        'turbo': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-turbo.png',
        'bits': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-bits.png',
        'sub_gifter': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-sub-gifter.png',
        'partner': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-partner.png',
        'ambassador': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-ambassador.png',
        'artist': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-artist.png',
        'staff': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-staff.png',
    }},
    youtube: {{
        'moderator': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/youtube-moderator.png',
        'member': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/youtube-member.png',
        'coin': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/youtube-coin.png',
        'verified': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/youtube-verified.png',
        'owner': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/youtube-owner.png',
    }},
    kick: {{
        'broadcaster': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-broadcaster.png',
        'moderator': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-moderator.png',
        'vip': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-vip.png',
        'og': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-og.png',
        'founder': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-founder.png',
        'subscriber': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-subscriber.png',
        'sub_gifter': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-sub-gifter.png',
        'staff': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-staff.png',
        'verified': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-verified.png',
    }},
    facebook: {{
        'moderator': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/facebook-moderator.png',
        'subscriber': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/facebook-subscriber.png',
        'top_fan': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/facebook-top-fan.png',
        'verified': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/facebook-verified.png',
    }},
    tiktok: {{
        'moderator': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/tiktok-moderator.png',
        'subscriber': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/tiktok-subscriber.png',
        'gifter': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/tiktok-gifter.png',
        'top_gifter': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/tiktok-top-gifter.png',
    }},
}};

function handleMessage(e) {{
    const data = JSON.parse(e.data);
    
    if (data.type === 'refresh') {{
        window.location.reload();
        return;
    }}
    
    const platformKey = 'show_' + data.platform;
    if (config[platformKey] === false) return;
    
    if (config.hide_bots && BOT_NAMES.includes(data.username.toLowerCase())) return;
    if (config.hide_commands && data.message.startsWith('!')) return;
    if (config.muted_users.includes(data.username.toLowerCase())) return;
    
    // Filter bad words
    if (config.bad_words.length > 0) {{
        const lowerMessage = data.message.toLowerCase();
        for (let word of config.bad_words) {{
            if (lowerMessage.includes(word.toLowerCase())) return;
        }}
    }}
    
    setTimeout(() => displayMessage(data), config.chat_delay * 1000);
}};

function renderMessageWithEmotes(message, emotes, platform) {{
    if (!emotes || emotes.length === 0) return message;
    
    // Sort emotes by position (reverse order for replacement)
    emotes.sort((a, b) => b.start - a.start);
    
    let result = message;
    for (let emote of emotes) {{
        let emoteHtml = '';
        
        if (platform === 'twitch') {{
            // Twitch emotes
            emoteHtml = `<img src="https://static-cdn.jtvnw.net/emoticons/v2/${{emote.id}}/default/dark/1.0" class="emote" alt="emote" />`;
            result = result.substring(0, emote.start) + emoteHtml + result.substring(emote.end);
        }} else if (platform === 'kick') {{
            // Kick emotes [emote:ID:name]
            emoteHtml = `<img src="https://files.kick.com/emotes/${{emote.id}}/fullsize" class="emote" alt="${{emote.name}}" />`;
            result = result.substring(0, emote.start) + emoteHtml + result.substring(emote.end);
        }}
        // YouTube, Facebook, TikTok will go here when implemented
    }}
    
    return result;
}}

function displayMessage(data) {{
    const msg = document.createElement('div');
    msg.className = 'message';

    // Set dynamic border color for chunky style
    if (data.color) {{
        msg.style.setProperty('--user-color', data.color);
    }}
    
    let html = '';
    
    if (config.show_platform_icon && data.platform && PLATFORM_ICONS[data.platform]) {{
        html += `<img src="${{PLATFORM_ICONS[data.platform]}}" class="platform-icon" />`;
    }}
    
    if (data.badges && data.platform) {{
        const platformBadges = BADGE_URLS[data.platform] || {{}};
        data.badges.forEach(badge => {{
            if (platformBadges[badge]) {{
                html += `<img src="${{platformBadges[badge]}}" class="badge" />`;
            }}
        }});
    }}
    
    html += `<span class="username" style="color: ${{data.color || '{font_color}'}}">${{data.username}}:</span>`;
    html += `<span>${{renderMessageWithEmotes(data.message, data.emotes, data.platform)}}</span>`;
    
    msg.innerHTML = html;
    
    const chat = document.getElementById('chat');
    chat.appendChild(msg);
    
    // Keep only last 50 messages
    while (chat.children.length > 50) {{
        chat.removeChild(chat.firstChild);
    }}
    
    const timeSinceActivity = (Date.now() - lastActivity) / 1000;
    if (config.notification_enabled && timeSinceActivity >= config.notification_threshold && config.notification_sound) {{
        const audio = document.getElementById('notificationSound');
        audio.src = config.notification_sound;
        audio.volume = config.notification_volume / 100;
        audio.play().catch(() => {{}});
    }}
    
    lastActivity = Date.now();
    
    if (!config.always_show && config.hide_after > 0) {{
        setTimeout(() => {{
            msg.style.transition = 'opacity 0.3s';
            msg.style.opacity = '0';
            setTimeout(() => msg.remove(), 300);
        }}, config.hide_after * 1000);
    }}
}}
</script>
</body>
</html>"""

def generate_event_list_html(user_id, config, connected_platforms):
    """Generate event list HTML"""
    style = config.get('style', 'clean')
    theme_color = config.get('theme_color', '#9146FF')
    text_color = config.get('text_color', '#FFFFFF')
    font_size = config.get('font_size', 18)
    animation = config.get('animation', 'slide')
    animation_speed = config.get('animation_speed', 500)
    fade_time = config.get('fade_time', 300)
    max_events = config.get('max_events', 5)
    keep_history = config.get('keep_history', False)
    flip_x = config.get('flip_x', False)
    flip_y = config.get('flip_y', False)
    custom_css = config.get('custom_css', '') if config.get('custom_css_enabled', False) else ''
    
    show_twitch = config.get('show_twitch', True)
    show_youtube = config.get('show_youtube', True)
    show_kick = config.get('show_kick', True)
    show_facebook = config.get('show_facebook', True)
    show_tiktok = config.get('show_tiktok', True)
    
    min_bits = config.get('min_bits', 1)
    min_stars = config.get('min_stars', 1)
    min_raiders = config.get('min_raiders', 1)
    
    # Message templates
    message_templates = {
        'twitch_follow': config.get('twitch_follow_msg', '{name} just followed!'),
        'twitch_subscribe': config.get('twitch_sub_msg', '{name} subscribed!'),
        'twitch_resub': config.get('twitch_resub_msg', '{name} resubbed for {months} months!'),
        'twitch_gift_sub': config.get('twitch_gift_msg', '{name} gifted {count} subs!'),
        'twitch_bits': config.get('twitch_bits_msg', '{name} cheered {amount} bits!'),
        'twitch_raid': config.get('twitch_raid_msg', '{name} raided with {viewers} viewers!'),
        'youtube_subscribe': config.get('youtube_subscribe_msg', '{name} just subscribed!'),
        'youtube_member': config.get('youtube_member_msg', '{name} became a member!'),
        'youtube_superchat': config.get('youtube_superchat_msg', '{name} sent {amount}!'),
        'facebook_follow': config.get('facebook_follow_msg', '{name} just followed!'),
        'facebook_stars': config.get('facebook_stars_msg', '{name} sent {amount} stars!'),
        'kick_follow': config.get('kick_follow_msg', '{name} just followed!'),
        'kick_subscribe': config.get('kick_sub_msg', '{name} subscribed!'),
        'kick_gift_sub': config.get('kick_gift_msg', '{name} gifted {count} subs!'),
        'tiktok_follow': config.get('tiktok_follow_msg', '{name} just followed!'),
        'tiktok_gift': config.get('tiktok_gift_msg', '{name} sent {gift}!'),
    }
    
    event_filters = {
        'twitch_follow': config.get('twitch_follow', True),
        'twitch_subscribe': config.get('twitch_subscribe', True),
        'twitch_resub': config.get('twitch_resub', True),
        'twitch_gift_sub': config.get('twitch_gift_sub', True),
        'twitch_bits': config.get('twitch_bits', True),
        'twitch_raid': config.get('twitch_raid', True),
        'youtube_subscribe': config.get('youtube_subscribe', True),
        'youtube_member': config.get('youtube_member', True),
        'youtube_superchat': config.get('youtube_superchat', True),
        'facebook_follow': config.get('facebook_follow', True),
        'facebook_stars': config.get('facebook_stars', True),
        'kick_follow': config.get('kick_follow', True),
        'kick_subscribe': config.get('kick_subscribe', True),
        'kick_gift_sub': config.get('kick_gift_sub', True),
        'tiktok_follow': config.get('tiktok_follow', True),
        'tiktok_gift': config.get('tiktok_gift', True),
    }
    
    # Flip changes alignment, not mirroring
    align_right = 'right: 0;' if flip_x else 'left: 0;'
    align_bottom = 'bottom: 0;' if flip_y else 'top: 0;'
    flex_direction = 'row-reverse' if flip_x else 'row'
    margin_dir = 'margin-top' if flip_y else 'margin-bottom'
    icon_margin = 'margin-left: 8px;' if flip_x else 'margin-right: 8px;'
    badge_margin = 'margin-left: 6px;' if flip_x else 'margin-right: 6px;'
    
    # Fuze style direction based on flip
    grad_dir = '270deg' if flip_x else '90deg'
    border_side = 'border-right' if flip_x else 'border-left'
    
    # Fuze style uses platform color via CSS class
    style_css = {
        'clean': f'''
            .event {{ padding: 8px 12px; {margin_dir}: 6px; background: transparent; }}
        ''',
        'boxed': f'''
            .event {{ padding: 10px 14px; {margin_dir}: 8px; background: rgba(0,0,0,0.7); border-radius: 6px; }}
        ''',
        'compact': f'''
            .event {{ padding: 4px 8px; {margin_dir}: 4px; background: transparent; }}
        ''',
        'fuze': f'''
            .event {{ padding: 10px 14px; {margin_dir}: 8px; {border_side}: 3px solid var(--platform-color); }}
            .event.twitch {{ background: linear-gradient({grad_dir}, rgba(145,70,255,0.5) 0%, rgba(145,70,255,0.2) 60%, transparent 100%); --platform-color: #9146FF; }}
            .event.youtube {{ background: linear-gradient({grad_dir}, rgba(255,0,0,0.5) 0%, rgba(255,0,0,0.2) 60%, transparent 100%); --platform-color: #FF0000; }}
            .event.kick {{ background: linear-gradient({grad_dir}, rgba(83,252,24,0.5) 0%, rgba(83,252,24,0.2) 60%, transparent 100%); --platform-color: #53FC18; }}
            .event.facebook {{ background: linear-gradient({grad_dir}, rgba(24,119,242,0.5) 0%, rgba(24,119,242,0.2) 60%, transparent 100%); --platform-color: #1877F2; }}
            .event.tiktok {{ background: linear-gradient({grad_dir}, rgba(254,40,88,0.5) 0%, rgba(254,40,88,0.2) 60%, transparent 100%); --platform-color: #FE2858; }}
        ''',
        'bomby': f'''
            .event {{ padding: 10px 14px; {margin_dir}: 8px; background: rgba(0,0,0,0.8); border: 2px solid {theme_color}; border-radius: 6px; }}
        '''
    }
    
    animation_css = {
        'slide': '''
            @keyframes eventIn { from { transform: translateX(-20px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
            @keyframes eventOut { from { opacity: 1; } to { opacity: 0; } }
        ''',
        'fade': '''
            @keyframes eventIn { from { opacity: 0; } to { opacity: 1; } }
            @keyframes eventOut { from { opacity: 1; } to { opacity: 0; } }
        ''',
        'bounce': '''
            @keyframes eventIn { 0% { transform: scale(0); opacity: 0; } 50% { transform: scale(1.05); } 100% { transform: scale(1); opacity: 1; } }
            @keyframes eventOut { from { opacity: 1; } to { opacity: 0; } }
        ''',
        'zoom': '''
            @keyframes eventIn { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
            @keyframes eventOut { from { opacity: 1; } to { opacity: 0; } }
        '''
    }
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ box-sizing: border-box; }}
html, body {{
    background: transparent;
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    font-family: 'Inter', 'Segoe UI', Arial, sans-serif;
    overflow: hidden;
}}
#events-container {{
    padding: 10px;
    position: absolute;
    width: 100%;
    {align_right}
    {align_bottom}
}}
.event {{
    color: {text_color};
    font-size: {font_size}px;
    display: flex;
    flex-direction: {flex_direction};
    align-items: center;
    animation: eventIn {animation_speed}ms ease-out forwards;
    width: 100%;
}}
{style_css.get(style, style_css['clean'])}
{animation_css.get(animation, animation_css['slide'])}
.event.removing {{ animation: eventOut {fade_time}ms ease-out forwards; }}
.event-icon {{
    width: {font_size}px;
    height: {font_size}px;
    {icon_margin}
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
}}
.event-icon svg {{
    width: 100%;
    height: 100%;
}}
.event-text {{
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.platform-badge {{
    width: {font_size + 4}px;
    height: {font_size + 4}px;
    {badge_margin}
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
}}
.platform-badge svg {{
    width: 100%;
    height: 100%;
}}
{custom_css}
</style>
</head>
<body>
<div id="events-container"></div>
<script>
const config = {{
    max_events: {max_events},
    keep_history: {str(keep_history).lower()},
    show_twitch: {str(show_twitch).lower()},
    show_youtube: {str(show_youtube).lower()},
    show_kick: {str(show_kick).lower()},
    show_facebook: {str(show_facebook).lower()},
    show_tiktok: {str(show_tiktok).lower()},
    event_filters: {json.dumps(event_filters)},
    min_bits: {min_bits},
    min_stars: {min_stars},
    min_raiders: {min_raiders},
    fade_time: {fade_time},
    flip_y: {str(flip_y).lower()},
    message_templates: {json.dumps(message_templates)}
}};

const PLATFORM_ICONS = {{
    'twitch': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M11.571 4.714h1.715v5.143H11.57zm4.715 0H18v5.143h-1.714zM6 0L1.714 4.286v15.428h5.143V24l4.286-4.286h3.428L22.286 12V0zm14.571 11.143l-3.428 3.428h-3.429l-3 3v-3H6.857V1.714h13.714Z"/></svg>',
    'youtube': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>',
    'kick': '<svg viewBox="0 0 512 512" fill="currentColor"><path d="M37 .036h164.448v113.621h54.71v-56.82h54.731V.036h164.448v170.777h-54.73v56.82h-54.711v56.8h54.71v56.82h54.73V512.03H310.89v-56.82h-54.73v-56.8h-54.711v113.62H37V.036z"/></svg>',
    'facebook': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z"/></svg>',
    'tiktok': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/></svg>'
}};

const PLATFORM_COLORS = {{
    'twitch': '#9146FF',
    'youtube': '#FF0000',
    'kick': '#53FC18',
    'facebook': '#1877F2',
    'tiktok': '#FE2858'
}};

const EVENT_ICONS = {{
    'follow': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>',
    'subscribe': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>',
    'bits': '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 2h10l6 8-11 12L1 10l6-8z"/><path d="M1 10h22"/><path d="M12 22l-5-12 2-8"/><path d="M12 22l5-12-2-8"/><path d="M12 2v20"/></svg>',
    'raid': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
    'superchat': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 16.09V20h-2.67v-1.93c-1.71-.36-3.16-1.46-3.27-3.4h1.96c.1 1.05.82 1.87 2.65 1.87 1.96 0 2.4-.98 2.4-1.59 0-.83-.44-1.61-2.67-2.14-2.48-.6-4.18-1.62-4.18-3.67 0-1.72 1.39-2.84 3.11-3.21V4h2.67v1.95c1.86.45 2.79 1.86 2.85 3.39H14.3c-.05-1.11-.64-1.87-2.22-1.87-1.5 0-2.4.68-2.4 1.64 0 .84.65 1.39 2.67 1.91s4.18 1.39 4.18 3.91c-.01 1.83-1.38 2.83-3.12 3.16z"/></svg>',
    'member': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>',
    'stars': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>',
    'gift': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 6h-2.18c.11-.31.18-.65.18-1 0-1.66-1.34-3-3-3-1.05 0-1.96.54-2.5 1.35l-.5.67-.5-.68C10.96 2.54 10.05 2 9 2 7.34 2 6 3.34 6 5c0 .35.07.69.18 1H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-5-2c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zM9 4c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm11 15H4v-2h16v2zm0-5H4V8h5.08L7 10.83 8.62 12 11 8.76l1-1.36 1 1.36L15.38 12 17 10.83 14.92 8H20v6z"/></svg>',
    'gift_sub': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 6h-2.18c.11-.31.18-.65.18-1 0-1.66-1.34-3-3-3-1.05 0-1.96.54-2.5 1.35l-.5.67-.5-.68C10.96 2.54 10.05 2 9 2 7.34 2 6 3.34 6 5c0 .35.07.69.18 1H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-5-2c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zM9 4c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm11 15H4v-2h16v2zm0-5H4V8h5.08L7 10.83 8.62 12 11 8.76l1-1.36 1 1.36L15.38 12 17 10.83 14.92 8H20v6z"/></svg>',
}};

const connectedPlatforms = {json.dumps(connected_platforms)};
const connections = [];

function createWS(url) {{
    const ws = new WebSocket(url);
    ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
    ws.onclose = () => setTimeout(() => {{
        const idx = connections.indexOf(ws);
        if (idx > -1) connections.splice(idx, 1);
        const newWs = createWS(url);
        connections.push(newWs);
    }}, 3000);
    ws.onerror = () => ws.close();
    return ws;
}}

function connectWS() {{
    if (config.show_twitch && connectedPlatforms.includes('twitch')) {{
        connections.push(createWS('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/twitch/'));
    }}
    if (config.show_youtube && connectedPlatforms.includes('youtube')) {{
        connections.push(createWS('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/youtube/'));
    }}
    if (config.show_kick && connectedPlatforms.includes('kick')) {{
        connections.push(createWS('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/kick/'));
    }}
    if (config.show_facebook && connectedPlatforms.includes('facebook')) {{
        connections.push(createWS('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/facebook/'));
    }}
    if (config.show_tiktok && connectedPlatforms.includes('tiktok')) {{
        connections.push(createWS('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/tiktok/'));
    }}
}}

connectWS();

function handleMessage(data) {{
    if (data.type === 'refresh') {{
        window.location.reload();
        return;
    }}
    addEvent(data);
}}

function addEvent(data) {{
    const {{ event_type, platform, event_data }} = data;
    
    if (!config[`show_${{platform}}`]) return;
    
    const filterKey = `${{platform}}_${{event_type}}`;
    if (config.event_filters[filterKey] === false) return;
    
    if (event_type === 'bits' && event_data.amount < config.min_bits) return;
    if (event_type === 'stars' && event_data.amount < config.min_stars) return;
    if (event_type === 'raid' && event_data.viewers < config.min_raiders) return;
    
    const container = document.getElementById('events-container');
    const eventEl = document.createElement('div');
    eventEl.className = `event ${{platform}}`;
    
    const icon = EVENT_ICONS[event_type] || EVENT_ICONS['follow'];
    const username = event_data.username || 'Someone';
    const platformColor = PLATFORM_COLORS[platform] || '#FFFFFF';
    const platformIcon = PLATFORM_ICONS[platform] || '';
    
    // Get message template and replace variables
    const templateKey = `${{platform}}_${{event_type}}`;
    let template = config.message_templates[templateKey] || `${{username}} ${{event_type}}`;
    
    let text = template
        .replace(/\\{{name\\}}/g, username)
        .replace(/\\{{amount\\}}/g, event_data.amount || '')
        .replace(/\\{{count\\}}/g, event_data.count || event_data.amount || '')
        .replace(/\\{{months\\}}/g, event_data.months || '')
        .replace(/\\{{tier\\}}/g, event_data.tier || '')
        .replace(/\\{{viewers\\}}/g, event_data.viewers || '')
        .replace(/\\{{gift\\}}/g, event_data.gift || '');
    
    eventEl.innerHTML = `
        <span class="platform-badge" style="color: ${{platformColor}}">${{platformIcon}}</span>
        <span class="event-icon" style="color: ${{platformColor}}">${{icon}}</span>
        <span class="event-text">${{text}}</span>
    `;
    
    if (config.flip_y) {{
        container.appendChild(eventEl);
    }} else {{
        container.insertBefore(eventEl, container.firstChild);
    }}
    
    if (!config.keep_history) {{
        const activeEvents = Array.from(container.children).filter(el => !el.classList.contains('removing'));
        const excess = activeEvents.length - config.max_events;
        if (excess > 0) {{
            const toRemoveList = config.flip_y 
                ? activeEvents.slice(0, excess)
                : activeEvents.slice(-excess);
            toRemoveList.forEach(el => {{
                el.classList.add('removing');
                setTimeout(() => el.remove(), config.fade_time);
            }});
        }}
    }}
}}
</script>
</body>
</html>"""

def generate_goal_bar_html(user_id, config, connected_platforms):
    """Generate goal bar HTML with multiple styles"""
    custom_css = config.get('custom_css', '') if config.get('custom_css_enabled', False) else ''
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    background: transparent;
    font-family: Arial, sans-serif;
}}
.goal-container {{
    padding: 10px;
}}
.goal-container.condensed {{
    padding: 5px;
}}
.goal-title {{
    text-align: center;
    margin-bottom: 8px;
    font-weight: bold;
}}
.goal-container.condensed .goal-title {{
    margin-bottom: 4px;
    font-size: 0.9em;
}}
.progress-wrapper {{
    position: relative;
    width: 100%;
    overflow: hidden;
}}
.progress-bar {{
    width: 100%;
    position: relative;
}}
.progress-fill {{
    height: 100%;
    transition: width 0.5s ease;
    display: flex;
    align-items: center;
    justify-content: center;
}}
.progress-text {{
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    font-weight: bold;
    text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
    white-space: nowrap;
}}

/* Style: Standard - Clean flat design */
.style-standard .progress-bar {{ border-radius: 4px; }}
.style-standard .progress-fill {{ border-radius: 4px; }}

/* Style: Neon - Cyberpunk glow */
.style-neon .goal-container {{ filter: drop-shadow(0 0 10px var(--bar-color)); }}
.style-neon .goal-title {{ 
    text-shadow: 0 0 10px var(--bar-color), 0 0 20px var(--bar-color), 0 0 30px var(--bar-color);
    letter-spacing: 2px;
}}
.style-neon .progress-bar {{
    border-radius: 4px;
    border: 2px solid var(--bar-color);
    box-shadow: inset 0 0 15px rgba(0,0,0,0.8), 0 0 10px var(--bar-color);
}}
.style-neon .progress-fill {{
    border-radius: 2px;
    box-shadow: 0 0 20px var(--bar-color), 0 0 40px var(--bar-color), inset 0 0 10px rgba(255,255,255,0.3);
    animation: neon-pulse 2s ease-in-out infinite;
}}
.style-neon .bar-text {{
    text-shadow: 0 0 10px var(--bar-color);
}}
@keyframes neon-pulse {{
    0%, 100% {{ filter: brightness(1); }}
    50% {{ filter: brightness(1.3); }}
}}

/* Style: Glass - Frosted glassmorphism */
.style-glass .progress-bar {{
    border-radius: 12px;
    background: linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.02)) !important;
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.25);
    box-shadow: 0 8px 32px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.2);
    padding: 3px;
    overflow: hidden;
}}
.style-glass .progress-fill {{
    border-radius: 9px;
    background: linear-gradient(180deg, 
        rgba(255,255,255,0.3) 0%, 
        var(--bar-color) 30%, 
        var(--bar-color) 70%,
        rgba(0,0,0,0.2) 100%
    ) !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.4);
}}
.style-glass .progress-text {{
    text-shadow: 0 1px 3px rgba(0,0,0,0.5);
}}

/* Style: Retro - 8-bit pixel gaming */
.style-retro * {{ image-rendering: pixelated; }}
.style-retro .goal-title {{
    font-family: 'Courier New', monospace !important;
    text-transform: uppercase;
    letter-spacing: 3px;
    text-shadow: 3px 3px 0 #000;
}}
.style-retro .progress-bar {{
    border-radius: 0;
    border: 4px solid #fff;
    box-shadow: 4px 4px 0 #000;
    background: repeating-linear-gradient(
        90deg,
        var(--bar-bg-color) 0px,
        var(--bar-bg-color) 10px,
        rgba(0,0,0,0.3) 10px,
        rgba(0,0,0,0.3) 12px
    ) !important;
}}
.style-retro .progress-fill {{
    border-radius: 0;
    background: repeating-linear-gradient(
        90deg,
        var(--bar-color) 0px,
        var(--bar-color) 10px,
        var(--bar-color-light) 10px,
        var(--bar-color-light) 12px
    ) !important;
}}
.style-retro .bar-text {{
    font-family: 'Courier New', monospace !important;
    text-shadow: 2px 2px 0 #000;
}}

/* Style: Gradient - Animated flowing gradient */
.style-gradient .progress-bar {{
    border-radius: 999px;
    overflow: hidden;
}}
.style-gradient .progress-fill {{
    border-radius: 999px;
    background: linear-gradient(90deg, 
        var(--bar-color), 
        var(--bar-color-light), 
        var(--bar-color), 
        var(--bar-color-light)
    ) !important;
    background-size: 300% 100%;
    animation: gradient-flow 3s ease infinite;
}}
@keyframes gradient-flow {{
    0% {{ background-position: 0% 50%; }}
    50% {{ background-position: 100% 50%; }}
    100% {{ background-position: 0% 50%; }}
}}

@keyframes pulse {{
    0%, 100% {{ opacity: 1; transform: scale(1); }}
    50% {{ opacity: 0.9; transform: scale(1.02); }}
}}
.goal-complete .progress-fill {{
    animation: pulse 1.5s infinite;
}}
{custom_css}
</style>
</head>
<body>
<div id="goal-container" class="goal-container"></div>
<script>
const userId = '{user_id}';
const config = {json.dumps(config)};
const connectedPlatforms = {json.dumps(connected_platforms)};

const urlParams = new URLSearchParams(window.location.search);
const goalType = urlParams.get('goal_type') || 'follower';

const container = document.getElementById('goal-container');

let currentAmount = config.starting_amount || 0;
const goalAmount = config.goal_amount || 100;

function getBarColorLight(color) {{
    const hex = color.replace('#', '');
    const r = Math.min(255, parseInt(hex.substr(0,2), 16) + 50);
    const g = Math.min(255, parseInt(hex.substr(2,2), 16) + 50);
    const b = Math.min(255, parseInt(hex.substr(4,2), 16) + 50);
    return `rgb(${{r}},${{g}},${{b}})`;
}}

function render() {{
    const percentage = Math.min(100, (currentAmount / goalAmount) * 100);
    const style = config.style || 'standard';
    const layout = config.layout || 'standard';
    const barColor = config.bar_color || '#00FF00';
    const barBgColor = config.bar_bg_color || '#333333';
    const barThickness = config.bar_thickness || 30;
    const textColor = config.text_color || '#FFFFFF';
    const barTextColor = config.bar_text_color || '#FFFFFF';
    const fontFamily = config.font_family || 'Arial';
    const title = config.title || 'Goal';
    const showPercentage = config.show_percentage !== false;
    const showNumbers = config.show_numbers !== false;
    const isComplete = currentAmount >= goalAmount;
    
    container.className = `goal-container style-${{style}} ${{layout === 'condensed' ? 'condensed' : ''}} ${{isComplete ? 'goal-complete' : ''}}`;
    container.style.setProperty('--bar-color', barColor);
    container.style.setProperty('--bar-color-light', getBarColorLight(barColor));
    
    let progressText = '';
    if (showNumbers && showPercentage) {{
        progressText = `${{currentAmount}} / ${{goalAmount}} (${{Math.round(percentage)}}%)`;
    }} else if (showNumbers) {{
        progressText = `${{currentAmount}} / ${{goalAmount}}`;
    }} else if (showPercentage) {{
        progressText = `${{Math.round(percentage)}}%`;
    }}
    
    container.innerHTML = `
        ${{title ? `<div class="goal-title" style="color: ${{textColor}}; font-family: ${{fontFamily}}">${{title}}</div>` : ''}}
        <div class="progress-wrapper">
            <div class="progress-bar" style="background: ${{barBgColor}}; height: ${{barThickness}}px">
                <div class="progress-fill" style="width: ${{percentage}}%; background: ${{barColor}}"></div>
                <div class="progress-text" style="color: ${{barTextColor}}; font-family: ${{fontFamily}}">${{progressText}}</div>
            </div>
        </div>
    `;
}}

const GOAL_EVENT_MAP = {{
    'tip': ['tip', 'donation'],
    'follower': ['follow'],
    'subscriber': ['subscribe', 'resub', 'gift_sub'],
    'bit': ['bits'],
    'superchat': ['superchat'],
    'member': ['member'],
    'stars': ['stars']
}};

const GOAL_PLATFORMS = {{
    'tip': ['all'],
    'follower': ['twitch', 'youtube', 'kick', 'facebook', 'tiktok'],
    'subscriber': ['twitch', 'youtube', 'kick'],
    'bit': ['twitch'],
    'superchat': ['youtube'],
    'member': ['youtube'],
    'stars': ['facebook']
}};

function connectWebSocket(url, handler) {{
    const ws = new WebSocket(url);
    ws.onmessage = handler;
    ws.onclose = () => setTimeout(() => connectWebSocket(url, handler), 3000);
    ws.onerror = () => ws.close();
    return ws;
}}

function connectGoalWebSockets() {{
    // Always connect to goals channel for refresh signals
    connectWebSocket(`wss://bomby.us/ws/fuzeobs-goals/${{userId}}/`, (e) => {{
        const data = JSON.parse(e.data);
        if (data.type === 'refresh') {{
            window.location.reload();
            return;
        }}
        if (data.type === 'goal_update') {{
            currentAmount = data.current || currentAmount;
            render();
        }}
    }});
    
    // Connect to platform alerts for events
    const platforms = GOAL_PLATFORMS[goalType] || [];
    platforms.forEach(platform => {{
        if (platform === 'all') return; // Already handled above
        if (connectedPlatforms.includes(platform)) {{
            connectWebSocket(`wss://bomby.us/ws/fuzeobs-alerts/${{userId}}/${{platform}}/`, (e) => {{
                const data = JSON.parse(e.data);
                handleAlertForGoal(data);
            }});
        }}
    }});
}}

function handleAlertForGoal(data) {{
    if (data.type === 'refresh') {{
        window.location.reload();
        return;
    }}
    
    const eventTypes = GOAL_EVENT_MAP[goalType] || [];
    if (!eventTypes.includes(data.event_type)) return;
    
    let increment = 1;
    
    if (data.event_type === 'bits') {{
        increment = data.event_data?.amount || 1;
    }} else if (data.event_type === 'superchat') {{
        const amountStr = data.event_data?.amount || '0';
        increment = parseFloat(amountStr.replace(/[^0-9.]/g, '')) || 1;
    }} else if (data.event_type === 'stars') {{
        increment = data.event_data?.amount || 1;
    }} else if (data.event_type === 'gift_sub') {{
        increment = data.event_data?.amount || data.event_data?.count || 1;
    }}
    
    currentAmount += increment;
    render();
}}

function startPlatformListeners() {{
    const platforms = GOAL_PLATFORMS[goalType] || [];
    
    if (platforms.includes('youtube') && connectedPlatforms.includes('youtube')) {{
        fetch(`https://bomby.us/fuzeobs/youtube/start/${{userId}}`).catch(() => {{}});
    }}
    if (platforms.includes('facebook') && connectedPlatforms.includes('facebook')) {{
        fetch(`https://bomby.us/fuzeobs/facebook/start/${{userId}}`).catch(() => {{}});
    }}
    if (platforms.includes('tiktok') && connectedPlatforms.includes('tiktok')) {{
        fetch(`https://bomby.us/fuzeobs/tiktok/start/${{userId}}`).catch(() => {{}});
    }}
}}

render();
startPlatformListeners();
connectGoalWebSockets();
</script>
</body>
</html>"""

def generate_labels_html(user_id, config, connected_platforms):
    """Generate labels widget HTML with WebSocket reconnection and data persistence"""
    custom_css = config.get('custom_css', '')
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&family=Montserrat:wght@400;700&family=Open+Sans:wght@400;700&family=Oswald:wght@400;700&family=Bebas+Neue&display=swap" rel="stylesheet">
<style>
body {{
    background: transparent;
    margin: 0;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
}}
#label-container {{
    display: inline-flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
}}
.label-text {{
    transition: all 0.3s ease;
    overflow: hidden;
    text-overflow: ellipsis;
    display: inline-block;
}}
.platform-icon {{
    width: 24px;
    height: 24px;
    margin-right: 6px;
    flex-shrink: 0;
}}
@keyframes fadeIn {{
    from {{ opacity: 0; }}
    to {{ opacity: 1; }}
}}
@keyframes slideIn {{
    from {{ transform: translateX(-20px); opacity: 0; }}
    to {{ transform: translateX(0); opacity: 1; }}
}}
@keyframes bounceIn {{
    0% {{ transform: scale(0); opacity: 0; }}
    50% {{ transform: scale(1.1); }}
    100% {{ transform: scale(1); opacity: 1; }}
}}
@keyframes pulse {{
    0%, 100% {{ transform: scale(1); }}
    50% {{ transform: scale(1.05); }}
}}
.anim-fade {{ animation: fadeIn 0.5s ease; }}
.anim-slide {{ animation: slideIn 0.5s ease; }}
.anim-bounce {{ animation: bounceIn 0.5s ease; }}
.anim-pulse {{ animation: pulse 1s ease infinite; }}
{custom_css}
</style>
</head>
<body>
<div id="label-container"></div>
<script>
const userId = '{user_id}';
const config = {json.dumps(config)};
const connectedPlatforms = {json.dumps(connected_platforms)};

const urlParams = new URLSearchParams(window.location.search);
const labelType = urlParams.get('label_type') || 'latest_follower';

const container = document.getElementById('label-container');

let sessionData = {{
    latest_follower: {{ name: '', platform: '' }},
    latest_subscriber: {{ name: '', platform: '' }},
    latest_donation: {{ name: '', amount: '' }},
    latest_cheerer: {{ name: '', amount: 0 }},
    latest_raider: {{ name: '', viewers: 0 }},
    latest_gifter: {{ name: '', amount: 0 }},
    latest_member: {{ name: '' }},
    latest_superchat: {{ name: '', amount: '' }},
    latest_stars: {{ name: '', amount: 0 }},
    latest_sharer: {{ name: '' }},
    top_donation_session: {{ name: '', amount: 0 }},
    top_cheerer_session: {{ name: '', amount: 0 }},
    top_gifter_session: {{ name: '', amount: 0 }},
    top_superchat_session: {{ name: '', amount: 0 }},
    top_stars_session: {{ name: '', amount: 0 }},
    session_followers: 0,
    session_subscribers: 0,
    session_members: 0,
    total_donations_session: 0,
}};

PLATFORM_ICONS = {{
    'twitch': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/twitch-platform.png',
    'youtube': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/youtube-platform.png',
    'kick': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/kick-platform.png',
    'facebook': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/facebook-platform.png',
    'tiktok': 'https://storage.googleapis.com/fuzeobs-public/widget-icons/tiktok-platform.png',
}}

const LABEL_PLATFORMS = {{
    'latest_donation': ['all'],
    'top_donation_session': ['all'],
    'top_donation_alltime': ['all'],
    'total_donations_session': ['all'],
    'latest_follower': ['twitch', 'youtube', 'kick', 'facebook', 'tiktok'],
    'latest_subscriber': ['twitch', 'youtube', 'kick'],
    'latest_cheerer': ['twitch'],
    'latest_raider': ['twitch'],
    'latest_gifter': ['twitch', 'kick', 'tiktok'],
    'latest_member': ['youtube'],
    'latest_superchat': ['youtube'],
    'latest_stars': ['facebook'],
    'latest_sharer': ['tiktok'],
    'top_cheerer_session': ['twitch'],
    'top_gifter_session': ['twitch', 'kick'],
    'top_superchat_session': ['youtube'],
    'top_stars_session': ['facebook'],
    'session_followers': ['twitch', 'youtube', 'kick', 'facebook', 'tiktok'],
    'session_subscribers': ['twitch', 'youtube', 'kick'],
    'session_members': ['youtube'],
}};

function getStyleString() {{
    let style = `font-family: '${{config.font_family || 'Arial'}}', sans-serif;`;
    style += `font-size: ${{config.font_size || 32}}px;`;
    style += `color: ${{config.text_color || '#FFFFFF'}};`;
    if (config.label_width && config.label_width > 0) {{
        style += `max-width: ${{config.label_width}}px;`;
    }}
    if (config.text_style === 'bold') style += 'font-weight: bold;';
    if (config.text_style === 'italic') style += 'font-style: italic;';
    if (config.text_style === 'uppercase') style += 'text-transform: uppercase;';
    if (config.text_shadow) {{
        style += `text-shadow: 2px 2px 4px ${{config.shadow_color || '#000000'}};`;
    }}
    if (config.background_enabled) {{
        const bgColor = config.background_color || '#000000';
        const opacity = (config.background_opacity || 50) / 100;
        const r = parseInt(bgColor.slice(1,3), 16);
        const g = parseInt(bgColor.slice(3,5), 16);
        const b = parseInt(bgColor.slice(5,7), 16);
        style += `background: rgba(${{r}},${{g}},${{b}},${{opacity}});`;
        style += `padding: ${{config.background_padding || 10}}px;`;
        style += `border-radius: ${{config.background_radius || 5}}px;`;
    }}
    return style;
}}

function getLabelValue() {{
    const prefix = config.prefix_text || '';
    const suffix = config.suffix_text || '';
    let value = '';
    switch(labelType) {{
        case 'latest_follower': value = sessionData.latest_follower.name || '{{name}}'; break;
        case 'latest_subscriber': value = sessionData.latest_subscriber.name || '{{name}}'; break;
        case 'latest_donation': value = sessionData.latest_donation.name ? `${{sessionData.latest_donation.name}} (${{sessionData.latest_donation.amount}})` : '{{name}}'; break;
        case 'latest_cheerer': value = sessionData.latest_cheerer.name ? `${{sessionData.latest_cheerer.name}} (${{sessionData.latest_cheerer.amount}} bits)` : '{{name}}'; break;
        case 'latest_raider': value = sessionData.latest_raider.name ? `${{sessionData.latest_raider.name}} (${{sessionData.latest_raider.viewers}} viewers)` : '{{name}}'; break;
        case 'latest_gifter': value = sessionData.latest_gifter.name ? `${{sessionData.latest_gifter.name}} (${{sessionData.latest_gifter.amount}} subs)` : '{{name}}'; break;
        case 'latest_member': value = sessionData.latest_member.name || '{{name}}'; break;
        case 'latest_superchat': value = sessionData.latest_superchat.name ? `${{sessionData.latest_superchat.name}} (${{sessionData.latest_superchat.amount}})` : '{{name}}'; break;
        case 'latest_stars': value = sessionData.latest_stars.name ? `${{sessionData.latest_stars.name}} (${{sessionData.latest_stars.amount}} stars)` : '{{name}}'; break;
        case 'latest_sharer': value = sessionData.latest_sharer.name || '{{name}}'; break;
        case 'top_donation_session': value = sessionData.top_donation_session.name ? `${{sessionData.top_donation_session.name}} ($${{sessionData.top_donation_session.amount}})` : '{{name}}'; break;
        case 'top_cheerer_session': value = sessionData.top_cheerer_session.name ? `${{sessionData.top_cheerer_session.name}} (${{sessionData.top_cheerer_session.amount}} bits)` : '{{name}}'; break;
        case 'top_gifter_session': value = sessionData.top_gifter_session.name ? `${{sessionData.top_gifter_session.name}} (${{sessionData.top_gifter_session.amount}} subs)` : '{{name}}'; break;
        case 'top_superchat_session': value = sessionData.top_superchat_session.name ? `${{sessionData.top_superchat_session.name}} (${{sessionData.top_superchat_session.amount}})` : '{{name}}'; break;
        case 'top_stars_session': value = sessionData.top_stars_session.name ? `${{sessionData.top_stars_session.name}} (${{sessionData.top_stars_session.amount}} stars)` : '{{name}}'; break;
        case 'session_followers': value = sessionData.session_followers.toString(); break;
        case 'session_subscribers': value = sessionData.session_subscribers.toString(); break;
        case 'session_members': value = sessionData.session_members.toString(); break;
        case 'total_donations_session': value = `$${{sessionData.total_donations_session.toFixed(2)}}`; break;
        default: value = '{{name}}';
    }}
    return `${{prefix}}${{value}}${{suffix}}`;
}}

function render(animate = false) {{
    const animClass = animate && config.animation && config.animation !== 'none' ? `anim-${{config.animation}}` : '';
    let iconHtml = '';
    if (config.show_platform_icon && sessionData.latest_follower.platform) {{
        const platform = sessionData.latest_follower.platform;
        if (PLATFORM_ICONS[platform]) {{
            iconHtml = `<img class="platform-icon" src="${{PLATFORM_ICONS[platform]}}" alt="${{platform}}" />`;
        }}
    }}
    container.innerHTML = `${{iconHtml}}<span class="label-text ${{animClass}}" style="${{getStyleString()}}">${{getLabelValue()}}</span>`;
}}

function saveData() {{
    fetch(`https://bomby.us/fuzeobs/labels/save/${{userId}}`, {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{label_type: labelType, data: sessionData}})
    }}).catch(() => {{}});
}}

function handleEvent(data) {{
    if (data.type === 'refresh') {{ window.location.reload(); return; }}
    const eventType = data.event_type;
    const eventData = data.event_data || {{}};
    const platform = data.platform;
    switch(eventType) {{
        case 'follow':
            sessionData.latest_follower = {{ name: eventData.username, platform }};
            sessionData.session_followers++;
            break;
        case 'subscribe':
        case 'member':
            sessionData.latest_subscriber = {{ name: eventData.username, platform }};
            sessionData.session_subscribers++;
            if (eventType === 'member') {{
                sessionData.latest_member = {{ name: eventData.username }};
                sessionData.session_members++;
            }}
            break;
        case 'bits':
            const bits = eventData.amount || 0;
            sessionData.latest_cheerer = {{ name: eventData.username, amount: bits }};
            if (bits > sessionData.top_cheerer_session.amount) {{
                sessionData.top_cheerer_session = {{ name: eventData.username, amount: bits }};
            }}
            break;
        case 'raid':
            sessionData.latest_raider = {{ name: eventData.username, viewers: eventData.viewers || 0 }};
            break;
        case 'gift_sub':
        case 'gift':
            const giftAmount = eventData.amount || eventData.count || 1;
            sessionData.latest_gifter = {{ name: eventData.username, amount: giftAmount }};
            if (giftAmount > sessionData.top_gifter_session.amount) {{
                sessionData.top_gifter_session = {{ name: eventData.username, amount: giftAmount }};
            }}
            break;
        case 'superchat':
            sessionData.latest_superchat = {{ name: eventData.username, amount: eventData.amount }};
            const scAmount = parseFloat((eventData.amount || '0').replace(/[^0-9.]/g, '')) || 0;
            if (scAmount > sessionData.top_superchat_session.amount) {{
                sessionData.top_superchat_session = {{ name: eventData.username, amount: scAmount }};
            }}
            break;
        case 'stars':
            const stars = eventData.amount || 0;
            sessionData.latest_stars = {{ name: eventData.username, amount: stars }};
            if (stars > sessionData.top_stars_session.amount) {{
                sessionData.top_stars_session = {{ name: eventData.username, amount: stars }};
            }}
            break;
        case 'share':
            sessionData.latest_sharer = {{ name: eventData.username }};
            break;
        case 'donation':
        case 'tip':
            const donationAmount = parseFloat(eventData.amount) || 0;
            sessionData.latest_donation = {{ name: eventData.username, amount: `$${{donationAmount.toFixed(2)}}` }};
            sessionData.total_donations_session += donationAmount;
            if (donationAmount > sessionData.top_donation_session.amount) {{
                sessionData.top_donation_session = {{ name: eventData.username, amount: donationAmount }};
            }}
            break;
    }}
    render(true);
    saveData();
}}

function connectWebSocket(url) {{
    const ws = new WebSocket(url);
    ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
    ws.onclose = () => setTimeout(() => connectWebSocket(url), 3000);
    ws.onerror = () => ws.close();
    return ws;
}}

function connectWebSockets() {{
    // Always connect to labels channel for refresh signals
    connectWebSocket(`wss://bomby.us/ws/fuzeobs-labels/${{userId}}/`);
    
    // Connect to platform alerts for events (unless already using 'all')
    const platforms = LABEL_PLATFORMS[labelType] || [];
    if (!platforms.includes('all')) {{
        platforms.forEach(platform => {{
            if (connectedPlatforms.includes(platform)) {{
                connectWebSocket(`wss://bomby.us/ws/fuzeobs-alerts/${{userId}}/${{platform}}/`);
            }}
        }});
    }}
}}

function startPlatformListeners() {{
    const platforms = LABEL_PLATFORMS[labelType] || [];
    if (platforms.includes('youtube') && connectedPlatforms.includes('youtube')) {{
        fetch(`https://bomby.us/fuzeobs/youtube/start/${{userId}}`).catch(() => {{}});
    }}
    if (platforms.includes('facebook') && connectedPlatforms.includes('facebook')) {{
        fetch(`https://bomby.us/fuzeobs/facebook/start/${{userId}}`).catch(() => {{}});
    }}
    if (platforms.includes('tiktok') && connectedPlatforms.includes('tiktok')) {{
        fetch(`https://bomby.us/fuzeobs/tiktok/start/${{userId}}`).catch(() => {{}});
    }}
}}

// Load persisted data on startup
fetch(`https://bomby.us/fuzeobs/labels/data/${{userId}}`)
    .then(r => r.json())
    .then(res => {{
        if (res.data && res.data[labelType]) {{
            Object.assign(sessionData, res.data[labelType]);
        }}
        render();
    }})
    .catch(() => render());

startPlatformListeners();
connectWebSockets();
</script>
</body>
</html>"""

def generate_viewer_count_html(user_id, config, connected_platforms):
    """Generate viewer count widget HTML"""
    import json
    
    config_json = json.dumps(config)
    platforms_json = json.dumps(connected_platforms)
    custom_css = config.get('custom_css', '') if config.get('custom_css_enabled', False) else ''
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Open+Sans:wght@400;500;600;700;800&family=Roboto:wght@400;500;700;900&display=swap" rel="stylesheet">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: transparent;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
}}
#viewer-container {{
    display: flex;
    align-items: center;
    transition: all 0.3s ease;
}}
#viewer-count {{
    transition: transform 0.2s ease;
}}
#viewer-count.bump {{
    transform: scale(1.1);
}}
.eye-icon {{
    display: flex;
    align-items: center;
    justify-content: center;
}}
.eye-icon svg {{
    fill: none;
    stroke: currentColor;
    stroke-width: 2;
    stroke-linecap: round;
    stroke-linejoin: round;
}}
{custom_css}
</style>
</head>
<body>
<div id="viewer-container">
    <div class="eye-icon" id="eye-icon"></div>
    <span id="viewer-count">0</span>
</div>

<script>
const userId = {user_id};
const config = {config_json};
const connectedPlatforms = {platforms_json};

const viewers = {{
    twitch: 0,
    youtube: 0,
    kick: 0,
    facebook: 0
}};

const POLL_INTERVALS = {{
    twitch: 30000,
    youtube: 60000,
    kick: 15000,
    facebook: 30000
}};

function applyStyles() {{
    const container = document.getElementById('viewer-container');
    const count = document.getElementById('viewer-count');
    const icon = document.getElementById('eye-icon');
    
    container.style.fontFamily = config.font_family || 'Open Sans';
    container.style.fontSize = (config.font_size || 36) + 'px';
    container.style.fontWeight = config.font_weight || '800';
    container.style.color = config.font_color || '#FFFFFF';
    container.style.gap = (config.spacing || 10) + 'px';
    container.style.padding = (config.padding || 20) + 'px';
    container.style.borderRadius = (config.border_radius || 8) + 'px';
    
    if (config.transparent_background !== false) {{
        container.style.backgroundColor = 'transparent';
    }} else {{
        container.style.backgroundColor = config.background_color || '#5CA05C';
    }}
    
    if (config.text_shadow) {{
        container.style.textShadow = `2px 2px 4px ${{config.shadow_color || '#000000'}}`;
    }}
    
    if (config.show_icon !== false) {{
        const iconSize = config.icon_size || 32;
        const iconColor = config.icon_color || '#FFFFFF';
        icon.innerHTML = `
            <svg width="${{iconSize}}" height="${{iconSize}}" viewBox="0 0 24 24" style="color: ${{iconColor}}">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
            </svg>
        `;
        icon.style.display = 'flex';
    }} else {{
        icon.style.display = 'none';
    }}
}}

function updateDisplay() {{
    let total = 0;
    if (config.show_twitch !== false && connectedPlatforms.includes('twitch')) total += viewers.twitch;
    if (config.show_youtube !== false && connectedPlatforms.includes('youtube')) total += viewers.youtube;
    if (config.show_kick !== false && connectedPlatforms.includes('kick')) total += viewers.kick;
    if (config.show_facebook !== false && connectedPlatforms.includes('facebook')) total += viewers.facebook;
    
    const countEl = document.getElementById('viewer-count');
    const oldValue = parseInt(countEl.textContent.replace(/,/g, '')) || 0;
    
    if (total !== oldValue) {{
        countEl.textContent = total.toLocaleString();
        if (config.animate_changes !== false) {{
            countEl.classList.add('bump');
            setTimeout(() => countEl.classList.remove('bump'), 200);
        }}
    }}
}}

async function pollTwitch() {{
    if (!config.show_twitch || !connectedPlatforms.includes('twitch')) return;
    try {{
        const resp = await fetch(`https://bomby.us/fuzeobs/viewers/twitch/${{userId}}`);
        if (resp.ok) {{
            const data = await resp.json();
            viewers.twitch = data.viewers || 0;
            updateDisplay();
        }}
    }} catch (e) {{}}
}}

async function pollYouTube() {{
    if (!config.show_youtube || !connectedPlatforms.includes('youtube')) return;
    try {{
        const resp = await fetch(`https://bomby.us/fuzeobs/viewers/youtube/${{userId}}`);
        if (resp.ok) {{
            const data = await resp.json();
            viewers.youtube = data.viewers || 0;
            updateDisplay();
        }}
    }} catch (e) {{}}
}}

async function pollKick() {{
    if (!config.show_kick || !connectedPlatforms.includes('kick')) return;
    try {{
        const resp = await fetch(`https://bomby.us/fuzeobs/viewers/kick/${{userId}}`);
        if (resp.ok) {{
            const data = await resp.json();
            viewers.kick = data.viewers || 0;
            updateDisplay();
        }}
    }} catch (e) {{}}
}}

async function pollFacebook() {{
    if (!config.show_facebook || !connectedPlatforms.includes('facebook')) return;
    try {{
        const resp = await fetch(`https://bomby.us/fuzeobs/viewers/facebook/${{userId}}`);
        if (resp.ok) {{
            const data = await resp.json();
            viewers.facebook = data.viewers || 0;
            updateDisplay();
        }}
    }} catch (e) {{}}
}}

function connectWS() {{
    const ws = new WebSocket(`wss://bomby.us/ws/fuzeobs-viewers/${{userId}}/`);
    
    ws.onmessage = (e) => {{
        const data = JSON.parse(e.data);
        if (data.type === 'refresh') {{
            window.location.reload();
            return;
        }}
        if (data.platform && typeof data.viewers === 'number') {{
            viewers[data.platform] = data.viewers;
            updateDisplay();
        }}
    }};
    
    ws.onclose = () => setTimeout(connectWS, 3000);
    ws.onerror = () => ws.close();
}}

applyStyles();
updateDisplay();
connectWS();

if (config.show_twitch !== false && connectedPlatforms.includes('twitch')) {{
    pollTwitch();
    setInterval(pollTwitch, POLL_INTERVALS.twitch);
}}
if (config.show_youtube !== false && connectedPlatforms.includes('youtube')) {{
    pollYouTube();
    setInterval(pollYouTube, POLL_INTERVALS.youtube);
}}
if (config.show_kick !== false && connectedPlatforms.includes('kick')) {{
    pollKick();
    setInterval(pollKick, POLL_INTERVALS.kick);
}}
if (config.show_facebook !== false && connectedPlatforms.includes('facebook')) {{
    pollFacebook();
    setInterval(pollFacebook, POLL_INTERVALS.facebook);
}}
</script>
</body>
</html>"""

def generate_sponsor_banner_html(user_id, config):
    """Generate sponsor banner widget HTML"""
    import json
    config_json = json.dumps(config)
    custom_css = config.get('custom_css', '') if config.get('custom_css_enabled', False) else ''
    
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: transparent;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
}}
#banner-container {{
    display: inline-block;
    overflow: hidden;
    transition: opacity 0.5s ease;
    background: transparent;
}}
#banner-container.hidden {{
    opacity: 0;
    pointer-events: none;
}}
.banner-image {{
    object-fit: cover;
    display: block;
}}

@keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
@keyframes bounce {{ 0%, 100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-10px); }} }}
@keyframes pulse {{ 0%, 100% {{ transform: scale(1); }} 50% {{ transform: scale(1.05); }} }}
@keyframes rotate {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
@keyframes slideIn {{ from {{ transform: translateX(-100%); opacity: 0; }} to {{ transform: translateX(0); opacity: 1; }} }}
@keyframes zoomIn {{ from {{ transform: scale(0); opacity: 0; }} to {{ transform: scale(1); opacity: 1; }} }}

.anim-fade {{ animation: fadeIn 0.5s ease forwards; }}
.anim-bounce {{ animation: bounce 1s ease infinite; }}
.anim-pulse {{ animation: pulse 2s ease infinite; }}
.anim-rotate {{ animation: rotate 3s linear infinite; }}
.anim-slide {{ animation: slideIn 0.5s ease forwards; }}
.anim-zoom {{ animation: zoomIn 0.5s ease forwards; }}
{custom_css}
</style>
</head>
<body>
<div id="banner-container">
    <img id="banner-image" class="banner-image" />
</div>

<script>
const userId = {user_id};
const config = {config_json};

const container = document.getElementById('banner-container');
const image = document.getElementById('banner-image');

let currentImageIndex = 0;
let images = [];
let isVisible = true;

function init() {{
    const bannerWidth = config.banner_width || 400;
    const bannerHeight = config.banner_height || 200;
    
    container.style.width = bannerWidth + 'px';
    container.style.height = bannerHeight + 'px';
    image.style.width = '100%';
    image.style.height = '100%';
    
    if (config.background_transparent !== false) {{
        container.style.backgroundColor = 'transparent';
    }} else {{
        container.style.backgroundColor = config.background_color || '#000000';
    }}
    
    images = [];
    if (config.image_1) images.push(config.image_1);
    if (config.placement === 'double' && config.image_2) images.push(config.image_2);
    
    if (images.length === 0) {{
        container.classList.add('hidden');
        return;
    }}
    
    showImage(0);
    startVisibilityCycle();
    
    if (config.placement === 'double' && images.length > 1) {{
        startImageCycle();
    }}
}}

function showImage(index) {{
    currentImageIndex = index;
    image.src = images[index];
    image.className = 'banner-image anim-' + (config.animation || 'fade');
}}

function startImageCycle() {{
    let durations = [
        (config.image_1_duration || 5) * 1000,
        (config.image_2_duration || 5) * 1000
    ];
    
    function cycleImage() {{
        if (!isVisible) {{
            setTimeout(cycleImage, 500);
            return;
        }}
        let currentDuration = durations[currentImageIndex];
        currentImageIndex = (currentImageIndex + 1) % images.length;
        showImage(currentImageIndex);
        setTimeout(cycleImage, currentDuration);
    }}
    
    setTimeout(cycleImage, durations[0]);
}}

function startVisibilityCycle() {{
    const hideMins = config.hide_duration_mins || 0;
    const hideSecs = config.hide_duration_secs || 0;
    const showMins = config.show_duration_mins || 0;
    const showSecs = config.show_duration_secs || 0;
    
    const hideMs = (hideMins * 60 + hideSecs) * 1000;
    const showMs = (showMins * 60 + showSecs) * 1000;
    
    if (hideMs === 0 && showMs === 0) {{
        container.classList.remove('hidden');
        isVisible = true;
        return;
    }}
    
    function cycle() {{
        container.classList.remove('hidden');
        isVisible = true;
        
        // Re-trigger animation by removing and re-adding class
        const animClass = 'anim-' + (config.animation || 'fade');
        image.classList.remove(animClass);
        void image.offsetWidth; // Force reflow
        image.classList.add(animClass);
        
        if (showMs > 0) {{
            setTimeout(() => {{
                container.classList.add('hidden');
                isVisible = false;
                if (hideMs > 0) setTimeout(cycle, hideMs);
            }}, showMs);
        }}
    }}
    cycle();
}}

function connectWS() {{
    const ws = new WebSocket(`wss://bomby.us/ws/fuzeobs-sponsor/${{userId}}/`);
    ws.onmessage = (e) => {{
        const data = JSON.parse(e.data);
        if (data.type === 'refresh') window.location.reload();
    }};
    ws.onclose = () => setTimeout(connectWS, 3000);
    ws.onerror = () => ws.close();
}}

connectWS();
init();
</script>
</body>
</html>"""