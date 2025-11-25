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
    animation: slideIn 0.3s ease-out;
    word-break: break-word;
    overflow-wrap: break-word;
}}
{current_style}
@keyframes slideIn {{
    from {{ transform: translateX(-20px); opacity: 0; }}
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

const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-chat/' + userId + '/');
let lastActivity = Date.now();

const BOT_NAMES = ['nightbot', 'streamelements', 'streamlabs', 'moobot', 'fossabot'];

const PLATFORM_ICONS = {{
    'twitch': 'https://www.iconninja.com/files/830/856/929/logo-brand-social-network-twitch-icon.png',
    'youtube': 'https://www.gstatic.com/images/icons/material/product/2x/youtube_64dp.png',
    'kick': 'https://cdn.streamlabs.com/static/kick/image/logo.png',
    'facebook': 'https://cdn.streamlabs.com/static/facebook/image/FB29.png',
    'tiktok': 'https://sf16-website-login.neutral.ttwstatic.com/obj/tiktok_web_login_static/tiktok/webapp/main/webapp-desktop/8152caf0c8e8bc67ae0d.png'
}};

const BADGE_URLS = {{
    'broadcaster': 'https://static-cdn.jtvnw.net/badges/v1/5527c58c-fb7d-422d-b71b-f309dcb85cc1/2',
    'moderator': 'https://static-cdn.jtvnw.net/badges/v1/3267646d-33f0-4b17-b3df-f923a41db1d0/2',
    'subscriber': 'https://static-cdn.jtvnw.net/badges/v1/5d9f2208-5dd8-11e7-8513-2ff4adfae661/2',
    'vip': 'https://static-cdn.jtvnw.net/badges/v1/b817aba4-fad8-49e2-b88a-7cc744571f1e/2',
    'prime': 'https://static-cdn.jtvnw.net/badges/v1/bbbe0db0-a598-423e-86d0-f9fb98ca1933/2',
    'turbo': 'https://static-cdn.jtvnw.net/badges/v1/bd444ec6-8f34-4bf9-91f4-af1e3428d80f/2',
    'bits': 'https://static-cdn.jtvnw.net/badges/v1/73b5c3fb-24f9-4a82-a852-2f475b59411c/2',
    'sub_gifter': 'https://static-cdn.jtvnw.net/badges/v1/a5ef6c17-2e5b-4d8f-9b80-2779fd722414/2',
    'partner': 'https://static-cdn.jtvnw.net/badges/v1/d12a2e27-16f6-41d0-ab77-b780518f00a3/2'
}};

ws.onmessage = (e) => {{
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
    
    if (data.badges) {{
        data.badges.forEach(badge => {{
            if (BADGE_URLS[badge]) {{
                html += `<img src="${{BADGE_URLS[badge]}}" class="badge" />`;
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
    
    show_twitch = config.get('show_twitch', True)
    show_youtube = config.get('show_youtube', True)
    show_kick = config.get('show_kick', True)
    show_facebook = config.get('show_facebook', True)
    show_tiktok = config.get('show_tiktok', True)
    
    min_bits = config.get('min_bits', 1)
    min_stars = config.get('min_stars', 1)
    min_raiders = config.get('min_raiders', 1)
    
    event_filters = {
        'twitch_follow': config.get('twitch_follow', True),
        'twitch_subscribe': config.get('twitch_subscribe', True),
        'twitch_resub': config.get('twitch_resub', True),
        'twitch_gift_sub': config.get('twitch_gift_sub', True),
        'twitch_bits': config.get('twitch_bits', True),
        'twitch_raid': config.get('twitch_raid', True),
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
    
    style_css = {
        'clean': '''
            .event { padding: 8px 12px; margin-bottom: 6px; background: transparent; }
        ''',
        'boxed': '''
            .event { padding: 10px 14px; margin-bottom: 8px; background: rgba(0,0,0,0.7); border-radius: 6px; }
        ''',
        'compact': '''
            .event { padding: 4px 8px; margin-bottom: 4px; background: transparent; }
        ''',
        'fuze': f'''
            .event {{ padding: 10px 14px; margin-bottom: 8px; background: linear-gradient(90deg, {theme_color}40, transparent); border-left: 3px solid {theme_color}; }}
        ''',
        'bomby': f'''
            .event {{ padding: 10px 14px; margin-bottom: 8px; background: rgba(0,0,0,0.8); border: 2px solid {theme_color}; border-radius: 6px; }}
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
    
    transform = ''
    if flip_x and flip_y:
        transform = 'transform: scale(-1, -1);'
    elif flip_x:
        transform = 'transform: scaleX(-1);'
    elif flip_y:
        transform = 'transform: scaleY(-1);'
    
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
    {transform}
}}
.event {{
    color: {text_color};
    font-size: {font_size}px;
    display: flex;
    align-items: center;
    animation: eventIn {animation_speed}ms ease-out forwards;
}}
{style_css.get(style, style_css['clean'])}
{animation_css.get(animation, animation_css['slide'])}
.event.removing {{ animation: eventOut {fade_time}ms ease-out forwards; }}
.event-icon {{
    font-size: {font_size + 2}px;
    margin-right: 8px;
    flex-shrink: 0;
}}
.event-text {{
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
.platform-badge {{
    width: {font_size + 2}px;
    height: {font_size + 2}px;
    margin-right: 6px;
    border-radius: 50%;
    object-fit: contain;
    flex-shrink: 0;
}}
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
    fade_time: {fade_time}
}};

const PLATFORM_ICONS = {{
    'twitch': 'https://www.iconninja.com/files/830/856/929/logo-brand-social-network-twitch-icon.png',
    'youtube': 'https://www.gstatic.com/images/icons/material/product/2x/youtube_64dp.png',
    'kick': 'https://cdn.streamlabs.com/static/kick/image/logo.png',
    'facebook': 'https://cdn.streamlabs.com/static/facebook/image/FB29.png',
    'tiktok': 'https://sf16-website-login.neutral.ttwstatic.com/obj/tiktok_web_login_static/tiktok/webapp/main/webapp-desktop/8152caf0c8e8bc67ae0d.png'
}};

const EVENT_ICONS = {{
    'follow': '❤️',
    'subscribe': '⭐',
    'bits': '💎',
    'raid': '🔥',
    'superchat': '💵',
    'member': '🌟',
    'stars': '⭐',
    'gift': '🎁',
    'gift_sub': '🎁',
}};

const EVENT_NAMES = {{
    'follow': 'followed',
    'subscribe': 'subscribed',
    'bits': 'cheered',
    'raid': 'raided',
    'superchat': 'super chatted',
    'member': 'became a member',
    'stars': 'sent stars',
    'gift': 'sent a gift',
    'gift_sub': 'gifted a sub',
}};

const connectedPlatforms = {json.dumps(connected_platforms)};
const connections = [];

function connectWS() {{
    if (config.show_twitch && connectedPlatforms.includes('twitch')) {{
        const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/twitch/');
        ws.onmessage = (e) => addEvent(JSON.parse(e.data));
        connections.push(ws);
    }}
    if (config.show_youtube && connectedPlatforms.includes('youtube')) {{
        const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/youtube/');
        ws.onmessage = (e) => addEvent(JSON.parse(e.data));
        connections.push(ws);
    }}
    if (config.show_kick && connectedPlatforms.includes('kick')) {{
        const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/kick/');
        ws.onmessage = (e) => addEvent(JSON.parse(e.data));
        connections.push(ws);
    }}
    if (config.show_facebook && connectedPlatforms.includes('facebook')) {{
        const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/facebook/');
        ws.onmessage = (e) => addEvent(JSON.parse(e.data));
        connections.push(ws);
    }}
    if (config.show_tiktok && connectedPlatforms.includes('tiktok')) {{
        const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/tiktok/');
        ws.onmessage = (e) => addEvent(JSON.parse(e.data));
        connections.push(ws);
    }}
}}

connectWS();

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
    eventEl.className = 'event';
    
    const icon = EVENT_ICONS[event_type] || '🎉';
    const action = EVENT_NAMES[event_type] || event_type;
    const username = event_data.username || 'Someone';
    
    let text = `${{username}} ${{action}}`;
    if (event_type === 'bits') text = `${{username}} cheered ${{event_data.amount}} bits`;
    if (event_type === 'raid') text = `${{username}} raided with ${{event_data.viewers}} viewers`;
    if (event_type === 'superchat') text = `${{username}} super chatted ${{event_data.amount}}`;
    if (event_type === 'stars') text = `${{username}} sent ${{event_data.amount}} stars`;
    
    const platformIcon = PLATFORM_ICONS[platform] ? `<img src="${{PLATFORM_ICONS[platform]}}" class="platform-badge" alt="${{platform}}">` : '';
    
    eventEl.innerHTML = `
        ${{platformIcon}}
        <span class="event-icon">${{icon}}</span>
        <span class="event-text">${{text}}</span>
    `;
    
    container.insertBefore(eventEl, container.firstChild);
    
    if (!config.keep_history) {{
        while (container.children.length > config.max_events) {{
            const last = container.lastChild;
            last.classList.add('removing');
            setTimeout(() => last.remove(), config.fade_time);
        }}
    }}
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