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
    flip_y: {str(flip_y).lower()}
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
    'bits': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>',
    'raid': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
    'superchat': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1.41 16.09V20h-2.67v-1.93c-1.71-.36-3.16-1.46-3.27-3.4h1.96c.1 1.05.82 1.87 2.65 1.87 1.96 0 2.4-.98 2.4-1.59 0-.83-.44-1.61-2.67-2.14-2.48-.6-4.18-1.62-4.18-3.67 0-1.72 1.39-2.84 3.11-3.21V4h2.67v1.95c1.86.45 2.79 1.86 2.85 3.39H14.3c-.05-1.11-.64-1.87-2.22-1.87-1.5 0-2.4.68-2.4 1.64 0 .84.65 1.39 2.67 1.91s4.18 1.39 4.18 3.91c-.01 1.83-1.38 2.83-3.12 3.16z"/></svg>',
    'member': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>',
    'stars': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z"/></svg>',
    'gift': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 6h-2.18c.11-.31.18-.65.18-1 0-1.66-1.34-3-3-3-1.05 0-1.96.54-2.5 1.35l-.5.67-.5-.68C10.96 2.54 10.05 2 9 2 7.34 2 6 3.34 6 5c0 .35.07.69.18 1H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-5-2c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zM9 4c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm11 15H4v-2h16v2zm0-5H4V8h5.08L7 10.83 8.62 12 11 8.76l1-1.36 1 1.36L15.38 12 17 10.83 14.92 8H20v6z"/></svg>',
    'gift_sub': '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 6h-2.18c.11-.31.18-.65.18-1 0-1.66-1.34-3-3-3-1.05 0-1.96.54-2.5 1.35l-.5.67-.5-.68C10.96 2.54 10.05 2 9 2 7.34 2 6 3.34 6 5c0 .35.07.69.18 1H4c-1.11 0-1.99.89-1.99 2L2 19c0 1.11.89 2 2 2h16c1.11 0 2-.89 2-2V8c0-1.11-.89-2-2-2zm-5-2c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zM9 4c.55 0 1 .45 1 1s-.45 1-1 1-1-.45-1-1 .45-1 1-1zm11 15H4v-2h16v2zm0-5H4V8h5.08L7 10.83 8.62 12 11 8.76l1-1.36 1 1.36L15.38 12 17 10.83 14.92 8H20v6z"/></svg>',
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
        ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
        connections.push(ws);
    }}
    if (config.show_youtube && connectedPlatforms.includes('youtube')) {{
        const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/youtube/');
        ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
        connections.push(ws);
    }}
    if (config.show_kick && connectedPlatforms.includes('kick')) {{
        const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/kick/');
        ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
        connections.push(ws);
    }}
    if (config.show_facebook && connectedPlatforms.includes('facebook')) {{
        const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/facebook/');
        ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
        connections.push(ws);
    }}
    if (config.show_tiktok && connectedPlatforms.includes('tiktok')) {{
        const ws = new WebSocket('wss://bomby.us/ws/fuzeobs-alerts/{user_id}/tiktok/');
        ws.onmessage = (e) => handleMessage(JSON.parse(e.data));
        connections.push(ws);
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
    const action = EVENT_NAMES[event_type] || event_type;
    const username = event_data.username || 'Someone';
    const platformColor = PLATFORM_COLORS[platform] || '#FFFFFF';
    const platformIcon = PLATFORM_ICONS[platform] || '';
    
    let text = `${{username}} ${{action}}`;
    if (event_type === 'bits') text = `${{username}} cheered ${{event_data.amount}} bits`;
    if (event_type === 'raid') text = `${{username}} raided with ${{event_data.viewers}} viewers`;
    if (event_type === 'superchat') text = `${{username}} super chatted ${{event_data.amount}}`;
    if (event_type === 'stars') text = `${{username}} sent ${{event_data.amount}} stars`;
    
    eventEl.innerHTML = `
        <span class="platform-badge" style="color: ${{platformColor}}">${{platformIcon}}</span>
        <span class="event-icon" style="color: ${{platformColor}}">${{icon}}</span>
        <span class="event-text">${{text}}</span>
    `;
    
    // For flip_y, add to bottom; otherwise add to top
    if (config.flip_y) {{
        container.appendChild(eventEl);
    }} else {{
        container.insertBefore(eventEl, container.firstChild);
    }}
    
    if (!config.keep_history) {{
        while (container.children.length > config.max_events) {{
            const toRemove = config.flip_y ? container.firstChild : container.lastChild;
            toRemove.classList.add('removing');
            setTimeout(() => toRemove.remove(), config.fade_time);
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