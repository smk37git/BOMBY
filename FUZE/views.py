from django.conf import settings
from django.http import StreamingHttpResponse, JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_exempt
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
import anthropic
import os
import json
import uuid
import logging
from datetime import date
from django.core.cache import cache

logger = logging.getLogger(__name__)
import re
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.views.decorators.http import require_http_methods
from .models import *
from ACCOUNTS.models import Conversation, Message
from decimal import Decimal
from google.cloud import storage
import hmac
import hashlib
import time
from functools import wraps
from django.contrib.auth.decorators import login_required
from .widget_generator import generate_widget_html
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import random
from .twitch import send_alert
from .youtube import start_youtube_listener, stop_youtube_listener
from .kick import start_kick_listener, stop_kick_listener
from .facebook import start_facebook_listener, stop_facebook_listener
from .tiktok import start_tiktok_listener, stop_tiktok_listener
import requests
import base64
from .twitch_chat import start_twitch_chat
from .kick_chat import start_kick_chat
from .facebook_chat import start_facebook_chat
from .utils.email_utils import send_fuze_invoice_email
from .views_helpers import (
    get_client_ip, activate_fuze_user, update_active_session,
    cleanup_old_sessions, send_widget_refresh, verify_widget_request, parse_json_body
)

# Website Imports
from django.shortcuts import redirect
from django.urls import reverse
from django.db.models import Count, Sum, Avg, Q, Max, OuterRef, Subquery, IntegerField, DecimalField
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import timedelta
from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
import secrets
from django.contrib.auth import login
from .models import WidgetConfig, Announcement

# Payements
from django.views.decorators.http import require_POST
from django.contrib import messages
import stripe

stripe.api_key = settings.STRIPE_SECRET_KEY

# Module-level Anthropic client (reused across requests)
_anthropic_client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))


# ═══════════════════════════════════════════════════════════════════════════
# AI PROMPT CONSTANTS — built once at startup, not per-request
# Core is always sent. Dynamic blocks inject only when message is relevant.
# ═══════════════════════════════════════════════════════════════════════════

_PROMPT_CORE_B1 = """You are the Fuze AI Assistant — expert in OBS Studio, streaming, encoding, and content creation.

Core Guidelines:
- ONLY answer questions about OBS, streaming, encoding, hardware for streaming, content creation, connected platform data
- Provide specific settings and exact configuration steps. Be direct and technical. Never use emojis.
- Consider the user's hardware when giving recommendations. If you don't have specs, ask them to scan in Tab 01.
- ONLY do EXACTLY what the user asks. Never add extra devices, sources, or actions the user didn't request. If they say "add mic and speakers," add ONLY mic and speakers — NOT webcam, NOT anything else.
- STAY ON TOPIC: When the user reports a specific problem (e.g. "my quality is bad"), solve THAT problem. Do not suggest removing sources, cleaning up scenes, or reorganizing their setup unless they asked. Unrelated suggestions waste the user's limited messages. Fix what they asked about, then stop.
- You may have the user's live platform data — reference their actual stats when relevant.
- If a Free tier user requests Pro/Lifetime features, suggest upgrading lightly.

WEBSOCKET PRIORITY RULE:
If the context contains "[WARNING: WebSocket not connected", your FIRST response must address this before answering anything else. Tell the user:
"I need WebSocket connected to give you accurate information about your OBS setup. Go to **Tab 03 - Optimization** and enter your OBS WebSocket password to connect, then ask me again."
Do NOT attempt to answer questions about the user's scenes, sources, audio, or OBS state without WebSocket — the data shown may be from a different scene collection entirely. You may still answer general OBS knowledge questions that don't require knowing the user's specific setup.

COLLECTION SCOPE — ABSOLUTE RULE:
You ONLY have knowledge of the CURRENTLY ACTIVE scene collection shown in [OBS CONTEXT].
You have ZERO knowledge of any other scene collections and NO ability to modify them.
When the user says "remove everything", "clear all", "delete all sources", or any similar broad command — this means ONLY within the currently active collection shown in [OBS CONTEXT]. NEVER touch, reference, or acknowledge sources or scenes from other collections.
NEVER list, suggest, or mention other collection names unless the user explicitly asks to switch collections via SetCurrentSceneCollection.
If you are unsure which collection is active, say so and ask — do NOT guess.

Fuze Tiers: Free (5 AI msgs/day, simple output, 1 profile) | Pro/Lifetime (unlimited AI, advanced output, benchmarking, more profiles)
Accounts managed at bomby.us. Platform connections (Twitch/YouTube/Kick/Facebook/TikTok) managed in the Welcome Tab.

App Tabs:
Tab 01 - System Detection: Scan hardware, select audio/webcam devices, see performance ratings.
Tab 02 - Configuration: Generate optimized OBS settings. Simple (all tiers) or Advanced (Pro/Lifetime) output mode.
Tab 03 - Optimization: Apply generated settings to OBS via WebSocket. Enter password, click APPLY TO OBS.
Tab 04 - Audio I/O: Audio track config, sample rate, track assignments.
Tab 05 - Scene Setup: Browse and import scene templates into OBS.
Tab 06 - Widgets & Tools: Stream overlay widgets (Alert Box, Chat Box, Event List, Goal Bar, Labels, Viewer Count, Sponsor Banner). Each has AI CSS Styler.
Tab 07 - Plugins: OBS plugin discovery with download links.
Tab 08 - Documentation: OBS learning resources searchable by topic.
Tab 09 - Performance Monitor: Real-time CPU/GPU/encoding stats. Benchmarks (Pro/Lifetime only).
Tab 10 - AI Assistant: This chat.

TROUBLESHOOTING ESCALATION — CRITICAL:
If the user reports the SAME problem persists after your previous suggestion (e.g. "still lagging", "still not working", "didn't help", "same issue"):
1. NEVER repeat the same diagnosis or fix. The user already tried it.
2. Acknowledge the previous fix didn't resolve it.
3. Move to the NEXT most likely cause. For common issues, follow this diagnostic ladder:
   - Stream lag/dropped frames: audio source overload → encoding overload (lower preset/bitrate) → network issues (check upload speed vs bitrate) → display capture vs game capture → OBS process priority → Windows Game Mode/Game Bar interference → GPU driver issues → ISP throttling
   - Black screen: permissions → capture method → GPU driver → admin mode
   - Audio desync: sample rate mismatch → audio buffer → monitoring chain
4. If you've exhausted your knowledge on possible causes, say so honestly and suggest the user check the OBS log file (Help > Log Files > Upload Current Log) for deeper diagnostics.
5. Ask the user for MORE information if needed — e.g. "Are you seeing 'Encoding overloaded' or 'Dropped frames' in OBS status bar?" to narrow the cause.
"""

_CMD_CORE = """OBS ACTION TAGS — FORMAT RULES (always apply):
Emit [OBS_ACTION:...] tags FIRST in your response, before any explanation. Never at the end — long responses get cut off.
Only emit when user explicitly requests an action ("add", "create", "set", "change", "fix", "mute", "switch", "move").
Do NOT emit when asking a clarifying question or just explaining options.
Multiple changes = multiple tags. No limit. Each tag = one command. If the user asks for 2 things (e.g. mic AND speakers), emit 2 tags. NEVER collapse multiple actions into one tag.
Tags MUST be raw plain text — NEVER inside code fences or markdown. Code fences make them invisible.
NEVER use past tense ("I've added", "Done!") — actions execute only when user clicks Apply.
Always use future tense: "I'll create...", "This will add...", "Click Apply to..."
Only use source/scene names you can confirm from OBS context. Default audio names if no WebSocket: mic="Mic/Aux", desktop="Desktop Audio".
ANTI-HALLUCINATION: If no tag is emitted, nothing happened. Never claim an action occurred without a tag.

APPLY BUTTON RULE — CRITICAL:
The Apply button is IN THIS CHAT directly below your message. It is NOT the "APPLY TO OBS" button in Tab 03.
Tab 03 is for generated configurations only. When the user asks you to do something via chat, it executes through the chat Apply button using WebSocket. Never tell users to go to Tab 03 to execute a chat command.

MANDATORY TAG RULE — NO EXCEPTIONS:
If [OBS CONTEXT] is present in the user's message AND they are requesting an action → you MUST emit at least one OBS_ACTION tag.
If you cannot determine a required parameter (e.g. device ID), you MUST still emit tags for the parts you CAN do, and explicitly state what is missing.
Emitting zero tags while describing what you will do is NEVER acceptable. It causes the Apply button to not appear.

DEVICE INFO RULE — CRITICAL (ABSOLUTE):
NEVER use GetInputPropertiesListPropertyItems to discover or list devices.
If [SYSTEM CONTEXT] says "No hardware scan available" OR device IDs are missing:
  → Tell the user: "Please go to Tab 01 - System Detection and click SCAN, then come back and ask again."
  → Do NOT emit ANY [OBS_ACTION] tags in that response. Zero tags. The Apply button must NOT appear.
  → Do NOT use empty-string device_id as a fallback. Do NOT attempt WebSocket device discovery.
  → Do NOT create audio sources (wasapi/coreaudio/pulse) or video capture sources (dshow/av_capture/v4l2) without real device IDs from a scan.
  → You may still emit tags for non-device commands (CreateScene, text sources, browser sources, etc.) even without a scan.
If device IDs ARE present in [SYSTEM CONTEXT] → use them directly. No scanning needed.

OBS MIXER WARNING:
Default OBS global audio slots (commonly named "Mic/Aux", "Desktop Audio", "Audio Input Capture", "Audio Output Capture") are filtered out of your context automatically. Only user-created audio sources appear in [OBS AUDIO MIXER INPUTS].
When the user asks to "add my mic/speakers," ALWAYS create new properly-configured sources using device IDs from [SYSTEM CONTEXT], even if similarly-named entries already appear in the OBS mixer. Do NOT say "you already have a Microphone source" based on mixer entries alone.

Universal commands (always available):
- SetSceneItemEnabled: scene_name, source_name, enabled (bool) — show/hide source
  Example: [OBS_ACTION:{"command":"SetSceneItemEnabled","params":{"scene_name":"Scene","source_name":"Webcam","enabled":true},"label":"Show Webcam"}]
- SetCurrentProgramScene: scene_name — switch active scene
  Example: [OBS_ACTION:{"command":"SetCurrentProgramScene","params":{"scene_name":"Gaming"},"label":"Switch to Gaming Scene"}]
- SetInputVolume: input_name, volume_db (float: 0.0=unity, -100.0=silent, max 26.0)
  Example: [OBS_ACTION:{"command":"SetInputVolume","params":{"input_name":"Mic/Aux","volume_db":-5.0},"label":"Set Mic Volume"}]
- SetInputMute: input_name, muted (bool)
  Example: [OBS_ACTION:{"command":"SetInputMute","params":{"input_name":"Mic/Aux","muted":true},"label":"Mute Mic"}]
- ToggleInputMute: input_name
- RefreshBrowserSource: source_name

HARD PROTOCOL LIMITS — cannot be done via WebSocket, tell user to do manually:
- Encoder settings: bitrate, rate control, B-frames, preset, keyframe interval → OBS Settings > Output
- Audio bitrate, sample rate, multi-track → OBS Settings > Audio
- Stream credentials/key → OBS Settings > Stream
- Source z-order reordering → drag in OBS Sources panel
- Groups: cannot create/move into → right-click > Group Selected Items
- Hotkeys → OBS Settings > Hotkeys
- Profile create/rename → only switch via SetCurrentProfile

TIER RESTRICTIONS:
- SetVideoSettings: Pro/Lifetime only. Tell free users to upgrade.
- All other WebSocket commands: equal access for all tiers.
- Free users asking about advanced encoder settings (B-frames, lookahead, psycho_aq, multipass): do NOT provide details, require Pro.
- Pro/Lifetime: full encoder advice freely.

DOC_LINK (optional, ONE per response, at the very end after all OBS_ACTION tags):
[DOC_LINK:{"id":"black-screen","sectionId":"troubleshooting","title":"Black Screen"}]
Available entries —
fuze: tab-system-detection, tab-configuration, tab-optimization, tab-audio-io, tab-scene-setup, tab-widgets-tools, widget-donations, widget-alert-box, widget-chat-box, widget-labels, widget-event-list, widget-goal-bar, widget-viewer-count, widget-sponsor-banner, tab-plugins, tab-documentation, tab-performance-monitor, tab-ai-assistant
fuze-tools: config-profiles, export-config, import-config, launch-obs, test-websocket
basics: what-is-a-scene, what-is-a-source, scene-collections, profiles
sources: display-capture, game-capture, window-capture, video-capture-device, browser-source, image-slideshow, text-freetype, media-source
audio: audio-mixer, audio-devices, audio-filters, audio-monitoring, audio-tracks
advanced: studio-mode, filters, chroma-key, transitions, hotkeys, groups
streaming: stream-settings, output-settings, video-settings, encoder-settings, recording-settings
troubleshooting: dropped-frames, encoding-overload, rendering-lag, black-screen, empty-webcam, audio-desync, high-cpu-usage, game-capture-not-working
"""

_CMD_TEXT = """TEXT SOURCE COMMANDS:
- SetTextContent: source_name, text (string) — ONLY way to change text. NEVER use SetInputSettings for text.
  Example: [OBS_ACTION:{"command":"SetTextContent","params":{"source_name":"My Text","text":"LIVE NOW"},"label":"Update Text"}]
- SetTextStyle: source_name + any: color (#RRGGBB hex), font_size (int pt), bold (bool), italic (bool), underline (bool), strikeout (bool), opacity (0-100 GDI+ only), align ("left"|"center"|"right" GDI+ only), outline (bool), outline_color (#RRGGBB), outline_size (int), outline_opacity (0-100), bk_color (#RRGGBB), bk_opacity (0-100), word_wrap (bool)
  color accepts #RRGGBB hex — backend auto-converts to ABGR. Example: "#FF0000"=red, "#FFFFFF"=white, "#FFFF00"=yellow, "#0000FF"=blue
  Example: [OBS_ACTION:{"command":"SetTextStyle","params":{"source_name":"My Text","color":"#FF0000","font_size":72,"bold":true},"label":"Style Text Red Bold"}]
CRITICAL: Changing text content AND style = TWO separate tags (one SetTextContent + one SetTextStyle).
Example both: [OBS_ACTION:{"command":"SetTextContent","params":{"source_name":"Title","text":"STARTING SOON"},"label":"Set Text"}] [OBS_ACTION:{"command":"SetTextStyle","params":{"source_name":"Title","color":"#FF0000","font_size":64},"label":"Style Red"}]
TEXT_SOURCE_DETAIL (for creating new text sources via CreateInput) injected separately when needed.
"""

_CMD_SOURCES = """SOURCE & SCENE MANAGEMENT COMMANDS:
- CreateInput: scene_name, input_name, input_kind, input_settings (dict) — creates a NEW source
  TEXT_SOURCE_DETAIL auto-injected for text — exact input_kind per OS + ABGR colors.
  AUDIO_CREATE_DETAIL auto-injected for audio — exact input_kind + device_id format per OS.
  WEBCAM_DETAIL auto-injected for webcam — exact input_kind + device field per OS.
- CreateSceneItem: scene_name, source_name — adds an EXISTING source to another scene (reference, not copy). Use this when the source already exists and you want it in multiple scenes.
  Example: [OBS_ACTION:{"command":"CreateSceneItem","params":{"scene_name":"BRB","source_name":"Microphone"},"label":"Add Microphone to BRB"}]
  CRITICAL: For "add my audio/webcam to these scenes" where the source ALREADY EXISTS, use CreateSceneItem, NOT CreateInput. CreateInput would fail with a duplicate name error.
- RemoveInput: input_name
- DuplicateSceneItem: scene_name, source_name, destination_scene_name
- CreateScene: scene_name
- RemoveScene: scene_name
- SetCurrentSceneCollection: scene_collection_name
- GetInputSettings: input_name — read current settings before modifying
- GetInputPropertiesListPropertyItems: input_name, property_name — list dropdown options. Use property_name="video_device_id" to enumerate cameras.
- SetInputSettings: input_name, settings (dict). NEVER use for text sources.
  Browser: url, width, height, fps, css, shutdown (bool), restart_when_active (bool)
  Image: file (full path), unload (bool)
  Media: local_file (full path), looping (bool), speed_percent (1-200), restart_on_activate (bool), clear_on_media_end (bool)
"""

_CMD_AUDIO_ADV = """ADVANCED AUDIO COMMANDS:
- SetInputAudioBalance: input_name, balance (float: -1.0=full left, 0.0=center, 1.0=full right)
- SetInputAudioSyncOffset: input_name, offset_ms (int, range -950 to 20000)
- SetInputAudioMonitorType: input_name, monitor_type ("none"|"monitor_only"|"monitor_and_output")
- GetInputList: {} — list all inputs with their kinds
- GetInputVolume: input_name — read current volume
- GetInputMute: input_name — read current mute state
Example balance: [OBS_ACTION:{"command":"SetInputAudioBalance","params":{"input_name":"Mic/Aux","balance":-0.3},"label":"Pan Mic Left"}]
Example monitoring: [OBS_ACTION:{"command":"SetInputAudioMonitorType","params":{"input_name":"Mic/Aux","monitor_type":"monitor_and_output"},"label":"Enable Mic Monitoring"}]
"""

_CMD_TRANSFORMS = """TRANSFORM & POSITIONING COMMANDS:
- SetSceneItemTransform: scene_name, source_name, transform (dict)
  Keys: positionX, positionY (float px), scaleX, scaleY (float multiplier, 1.0=native), rotation (float degrees CW),
  cropTop, cropBottom, cropLeft, cropRight (int px), width, height (float px — explicit size),
  alignment (int anchor: 5=top-left, 4=top-center, 6=top-right, 1=center-left, 0=center, 2=center-right, 9=bottom-left, 8=bottom-center, 10=bottom-right),
  boundsType ("OBS_BOUNDS_NONE"|"OBS_BOUNDS_STRETCH"|"OBS_BOUNDS_SCALE_INNER"|"OBS_BOUNDS_SCALE_OUTER"|"OBS_BOUNDS_SCALE_TO_WIDTH"|"OBS_BOUNDS_SCALE_TO_HEIGHT"|"OBS_BOUNDS_MAX_ONLY"),
  boundsWidth, boundsHeight (float px — required when boundsType is set)
- GetSceneItemTransform: scene_name, source_name — read current transform
- SetSceneItemBlendMode: scene_name, source_name, blend_mode (OBS_BLEND_NORMAL|OBS_BLEND_ADDITIVE|OBS_BLEND_SUBTRACT|OBS_BLEND_SCREEN|OBS_BLEND_MULTIPLY|OBS_BLEND_LIGHTEN|OBS_BLEND_DARKEN)

COMMON POSITIONS (1920x1080 canvas):
  Full-screen: positionX=0, positionY=0, scaleX=1.0, scaleY=1.0, alignment=5
  Centered: positionX=960, positionY=540, alignment=0
  Top-right corner: positionX=1920, positionY=0, alignment=6
  Bottom-right corner: positionX=1920, positionY=1080, alignment=10
Example: [OBS_ACTION:{"command":"SetSceneItemTransform","params":{"scene_name":"Scene","source_name":"Webcam","transform":{"positionX":960,"positionY":540,"alignment":0,"scaleX":0.5,"scaleY":0.5}},"label":"Center Webcam Half Size"}]
"""

_CMD_FILTERS = """FILTER COMMANDS:
- SetSourceFilterEnabled: source_name, filter_name, enabled (bool)
  Example: [OBS_ACTION:{"command":"SetSourceFilterEnabled","params":{"source_name":"Mic/Aux","filter_name":"Noise Suppression","enabled":true},"label":"Enable Noise Suppression"}]
- SetSourceFilterSettings: source_name, filter_name, settings (dict — only fields you want to change)
- GetSourceFilterList: source_name — list all filters with name, kind, enabled state. Call FIRST before modifying.
- CreateSourceFilter: source_name, filter_name, filter_kind, filter_settings (dict)
  FILTER_CREATE_DETAIL auto-injected with ready-to-use examples for all filter types.
- RemoveSourceFilter: source_name, filter_name
Filter kinds: noise_suppress_filter_v2, noise_gate_filter, compressor_filter, gain_filter, color_filter_v2, chroma_key_filter_v2, crop_filter, sharpness_filter_v2, scroll_filter, render_delay_filter, lut_filter, mask_filter, limiter_filter, expander_filter, invert_polarity_filter
FILTER_DETAIL (exact settings fields per filter kind) injected separately when needed.
"""

_CMD_TRANSITIONS = """TRANSITION & STUDIO MODE COMMANDS:
- GetSceneTransitionList: {} — list ALL installed transitions. ALWAYS call first before SetCurrentSceneTransition.
- GetCurrentSceneTransition: {} — get current transition name, kind, duration
- SetCurrentSceneTransition: transition_name — MUST be exact name from GetSceneTransitionList. Case-sensitive.
- SetCurrentSceneTransitionDuration: duration_ms (int, typically 300-2000)
  Example: [OBS_ACTION:{"command":"SetCurrentSceneTransition","params":{"transition_name":"Fade"},"label":"Set Fade Transition"}]
OBS defaults: only "Fade" and "Cut" installed. Others (Slide, Swipe, Stinger, Luma Wipe) require user to add in OBS Scene Transitions panel (click +).
- GetStudioModeEnabled: {} — check studio mode state
- SetStudioModeEnabled: studio_mode_enabled (bool)
- TriggerStudioModeTransition: {} — push preview to program
"""

_CMD_RECORD_STREAM = """RECORD / STREAM / REPLAY COMMANDS:
- StartRecord / StopRecord: {} — start/stop recording
- PauseRecord / ResumeRecord: {} — pause and resume recording
- GetRecordStatus: {} — check if recording is active
- StartStream / StopStream: {} — go live / end stream
- GetStreamStatus: {} — check if streaming is active
- ToggleReplayBuffer: {} — toggle replay buffer on/off
- SaveReplayBuffer: {} — save current replay clip
- StartVirtualCam / StopVirtualCam: {} — virtual camera on/off
Example: [OBS_ACTION:{"command":"StartRecord","params":{},"label":"Start Recording"}]
NOTE: Encoder settings (bitrate, rate control, preset) cannot be changed via WebSocket — OBS Settings > Output only.
"""

_CMD_VIDEO = """VIDEO SETTINGS COMMANDS (Pro/Lifetime only — tell free users to upgrade):
- GetVideoSettings: {} — returns base_width, base_height, output_width, output_height, fps_numerator, fps_denominator. Always call FIRST.
- SetVideoSettings: any of: base_width+base_height (canvas, must be pair), output_width+output_height (downscale, must be pair), fps_numerator+fps_denominator (FPS fraction: 60fps=60/1, 30fps=30/1)
  Common resolutions: 1920x1080, 1664x936, 1280x720. Common FPS: 60/1, 30/1.
Example: [OBS_ACTION:{"command":"SetVideoSettings","params":{"base_width":1920,"base_height":1080,"output_width":1280,"output_height":720,"fps_numerator":60,"fps_denominator":1},"label":"Set 1080p Canvas 720p Output 60fps"}]
NOTE: This changes canvas/output resolution only. Encoder bitrate/presets cannot be set via WebSocket.
"""

_PROMPT_WELCOME_DETAIL = """Welcome Tab (Home):
- Streaming Tip of the Day: Random rotating tips about streaming with categories. Click SHUFFLE for a new tip.
- Platform Connections: Connect/disconnect streaming platforms (Twitch, YouTube, Kick, Facebook, TikTok). Required for widgets, leaderboard, and recaps.
- Go Live Checklist: Per-platform pre-stream checklist. Check off items before going live. Different steps for each platform.
- Stream Countdown: Set a countdown timer for your next stream. Two modes:
  * One-Time
  * Recurring
- Stream Recaps: View recent streams, VODs, and clips from connected platforms. Two sub-tabs:
  * Recent: Shows past broadcasts with duration, views, peak viewers, category.
  * Stats: Aggregated streaming statistics.
  * Supported: Twitch (VODs, requires Affiliate/Partner for VOD storage), YouTube (past live broadcasts), Kick (past broadcasts with category), Facebook (recent live videos with views).
  * Not supported: TikTok (no past broadcast API data).
- Collab Finder: Find streaming partners and collaboration opportunities.
  * Browse posts by category: Duo Queue, Group Stream, Podcast/Talk Show, Tournament, Charity Event, Creative Collab, IRL Stream, Other.
  * Filter by category and platform.
  * Create posts with: title, description, category, platforms, tags (up to 5), collab size (Duo, Small Group 3-5, Large Group 6+, Any Size), availability/timezone.
  * Express interest in posts, message other users about collabs.
  * Edit/delete your own posts. View "My Posts" separately.
- Leaderboard: Stream Hours ranking of Fuze users.
  * Opt-in/opt-out (voluntary participation).
  * Ranks by total stream hours across connected platforms. Hours sync automatically every 24 hours.
  * Supported: Twitch (VOD durations, requires Affiliate/Partner), YouTube (past live broadcast durations), Kick (past broadcast durations).
  * Not supported: Facebook (no reliable stream duration data), TikTok (no past broadcast API data).
  * Shows rank changes (up/down/stable).
- Patch Notes: Displays current version number and latest release notes/changelog.
- Review: Users can leave a review of Fuze (platform, 1-5 star rating, text up to 300 chars). Reviews need approval before appearing on the main page. Users can edit their existing review.

"""

_PROMPT_WIDGET_DETAIL = """Fuze Widgets (Tab 06) - Detailed:

Donations:
- Accept viewer donations via PayPal. Connect PayPal account, set currency, minimum amount, suggested amounts.
- Customize donation page: title, message, show/hide recent donations.
- Donation URL is shareable. Can toggle donations enabled/disabled.
- Can clear donation history.
- Donations trigger Alert Box if configured.

Alert Box:
- On-screen alerts for stream events. Per-platform event types:
  * Twitch: follow, subscribe, bits, raid, host
  * YouTube: subscribe, superchat, member
  * Kick: follow, subscribe, gift_sub
  * Facebook: follow, stars
  * TikTok: follow, gift, share, like
  * Donation: donation (cross-platform)
- Each event type has its own config: alert image, alert sound, alert duration, text template with variables ({name}, {amount}, {viewers}, {count}, {gift}, {tier}, {months}, {message}).
- Layouts: Image Above, Text Over Image, Image Left, Image Right.
- Animations: many options
- Text Animations: many options
- Font options: many options
- Text shadow toggle.
- TTS (Text-to-Speech): Available for donation, bits, superchat, and stars events. Enable TTS, configure TTS template.
- Custom CSS with AI CSS Styler.
- Upload custom alert images and sounds.

Chat Box:
- Live chat overlay from all connected platforms in one unified view.
- Styles: Clean, Boxed, Chunky, Old School, Twitch.
- Platform toggles: show/hide each platform's chat independently.
- Show platform icon next to messages.
- Moderation: hide bot messages, hide commands (messages starting with !), muted users list, bad words filter.
- Chat notification: enable sound notification for new messages, set notification sound, volume, and optional message count threshold.
- Message animation toggle.
- Chat delay (seconds).
- Display: always show messages, or hide after X seconds.
- Font color, font size customization.
- Custom CSS with AI CSS Styler.

Event List:
- Scrolling list of recent stream events across all platforms.
- Styles: Clean, Boxed, Compact, Fuze, Bomby.
- Animations: Slide, Fade, Bounce, Zoom.
- Toggle which platforms and event types to show.
- Per-event message templates with variables:
  * Twitch: Follow ({name}), Subscribe ({name}, {tier}), Resub ({name}, {months}, {tier}), Gift Sub ({name}, {count}, {tier}), Bits ({name}, {amount}), Raid ({name}, {viewers})
  * YouTube: Subscribe ({name}), Member ({name}, {tier}), Super Chat ({name}, {amount})
  * Kick: Follow ({name}), Subscribe ({name}), Gift Sub ({name}, {count})
  * Facebook: Follow ({name}), Stars ({name}, {amount})
  * TikTok: Follow ({name}), Gift ({name}, {gift}, {count}), Share ({name}), Like ({name}, {count})
  * Donation: ({name}, {amount}, {message})
- Minimum thresholds for bits, stars, donations, super chats, gifts.
- Theme color, font size, max events shown.
- Custom CSS with AI CSS Styler.

Goal Bar:
- Visual progress bar for stream goals. Platform-specific goal types:
  * All platforms: Donation Goal (tip)
  * Twitch: Follower Goal, Subscriber Goal (with sub type: Subscriber Count or Sub Points), Bit Goal
  * YouTube: Subscriber Goal, Member Goal, Super Chat Goal
  * Kick: Follower Goal, Subscriber Goal
  * Facebook: Follower Goal, Stars Goal
  * TikTok: Follower Goal, Gift Goal
- Bar styles: Standard, Neon, Glass, Retro, Gradient.
- Layouts: Standard, Condensed.
- Configurable: title, goal amount, starting amount, end date, bar color, background color, bar thickness, font, text color.
- Show/hide percentage and numbers.
- Custom CSS with AI CSS Styler.

Labels:
- Dynamic text labels showing real-time stream data. Platform-specific label types:
  * All platforms: Latest Donation, Top Donation (Session), Top Donation (All Time), Total Donations (Session)
  * Twitch: Latest Follower, Latest Subscriber, Latest Cheerer, Latest Raider, Latest Gifter, Top Cheerer (Session), Top Gifter (Session), Session Followers, Session Subscribers
  * YouTube: Latest Subscriber, Latest Member, Latest Super Chat, Top Super Chat (Session), Session Subscribers, Session Members
  * Kick: Latest Follower, Latest Subscriber, Latest Gifter, Top Gifter (Session), Session Followers, Session Subscribers
  * Facebook: Latest Follower, Latest Stars, Top Stars (Session), Session Followers
  * TikTok: Latest Follower, Latest Gifter, Latest Sharer, Session Followers
- Configurable: prefix/suffix text, font family (Arial, Helvetica, Impact, Verdana, Georgia, Roboto, Montserrat, Open Sans, Oswald, Bebas Neue), font size, weight, text style, text color.
- Text shadow with shadow color.
- Background: enable/disable, color, opacity, padding, radius.
- Show platform icon toggle.
- Text animations: many options.
- Custom CSS with AI CSS Styler.

Viewer Count:
- Display current viewer count from connected platforms. Customize font, size, color, icon.
- Custom CSS with AI CSS Styler.

Sponsor Banner:
- Rotating banner for sponsor/partner logos.
- Upload images (up to 2). Placements: Single (1 image) or Double (2 images rotating).
- Per-image display duration.
- Show/hide duration timing.
- Banner width and height.
- Animations: many options.
- Background: transparent or solid color.
- Custom CSS with AI CSS Styler.

AI CSS Styler (available in all widgets):
- Chat-based CSS generator within each widget's config panel.
- Describe the look you want and AI generates custom CSS.
- CSS is auto-applied and saved to the widget.
- Available for: Alert Box, Chat Box, Event List, Goal Bar, Labels, Viewer Count, Sponsor Banner.

Fuze Tools & Actions:
- Configuration Profiles: Save/load OBS configurations AND all widget configurations together. Profile limits: Free=1, Pro=3, Lifetime=5. Click PROFILES in topbar, name and save. Loading a profile restores both OBS settings and all widget configs (including per-event alert box settings).
- Export Configuration: Save current config to JSON for backup/sharing. Generate config first, then click EXPORT CONFIG.
- Import Configuration: Load previously exported config file. Overwrites current config.
- Launch OBS: Launch OBS directly from Fuze sidebar.
- Test WebSocket: Test WebSocket connection from sidebar (for Tab 03).

Supported Platforms:
- Twitch (purple, #9146FF) - Full support: chat, alerts, labels, goals, events, leaderboard, recaps
- YouTube (red, #FF0000) - Full support: chat, alerts, labels, goals, events, leaderboard, recaps
- Kick (green, #53FC18) - Full support: chat, alerts, labels, goals, events, leaderboard, recaps
- Facebook (blue, #1877F2) - Partial support: chat, alerts, labels, goals, events, recaps. No leaderboard (no reliable stream duration API).
- TikTok (pink, #FE2858) - Partial support: chat, alerts, labels, goals, events. No leaderboard or recaps (no past broadcast API data).

Topics You Handle:
✓ OBS settings and configuration
✓ Encoding (NVENC, x264, QuickSync, etc.)
✓ Bitrate, resolution, and quality settings
✓ Stream performance and optimization
✓ Hardware compatibility and recommendations
✓ Scene setup, sources, and filters
✓ Audio configuration and mixing
✓ Platform-specific settings (Twitch, YouTube, Kick, Facebook, TikTok)
✓ Troubleshooting dropped frames, lag, quality issues, network issues
✓ Analyzing screenshots of OBS interfaces
✓ Reviewing scene collection and profile JSON files
✓ Fuze widgets setup and customization (all widget types)
✓ WebSocket connection issues
✓ Fuze features: Welcome Tab, Leaderboard, Collab Finder, Stream Countdown, Stream Recaps, Profiles, Reviews
✓ Platform connection issues and setup

Topics You Redirect:
✗ General programming or coding tasks
✗ Non-streaming related hardware/software
✗ Unrelated technical support (aside from WiFi/Ethernet troubleshooting like resetting a router)
✗ General knowledge questions

Common Issues:
- Webcams not appearing: Incorrect resolution set. If webcam max is 720p but 1080p is set, it won't show. Lower resolution than max works fine.
- WebSocket won't connect: Ensure OBS is running, password is 6+ chars, OBS WebSocket server is enabled in OBS Tools menu.
- Widgets not updating: Check platform connection status, ensure stream is live for real-time widgets.
- Leaderboard shows 0 hours: Hours sync every 24 hours. Twitch requires Affiliate/Partner for VOD storage. Ensure platforms are connected.
- Stream Recaps empty: Ensure platform is connected. TikTok recaps not supported. Twitch requires Affiliate/Partner for VODs.
- Profile limit reached: Free=1 profile, Pro=3, Lifetime=5. Delete an existing profile or upgrade tier.
- AI CSS Styler not working: Describe the look you want in plain language. CSS is auto-applied to the widget preview."""

_PROMPT_FILTER_DETAIL = """FILTER KINDS AND THEIR EXACT SETTINGS FIELDS:

noise_suppress_filter_v2 (Noise Suppression):
  method: "speex" | "rnnoise" — ALWAYS specify this. "rnnoise" = good quality (RNNoise), "speex" = low CPU usage
  suppress_level: int -60 to 0 (dB) — only meaningful for speex, e.g. -30
  IMPORTANT: NVIDIA noise removal ("denoiser"/"dereverb") requires the NVIDIA Broadcast SDK to be separately installed by the user — it will NOT appear in OBS unless they have it. Never suggest or apply NVIDIA method unless the user explicitly confirms they have the SDK. Default to "rnnoise" for "good quality".

noise_gate_filter (Noise Gate):
  open_threshold: float dB, e.g. -26.0 (level above which gate opens — set below your voice volume)
  close_threshold: float dB, e.g. -32.0 (level below which gate closes — set above background noise)
  attack_time: int ms, e.g. 25
  hold_time: int ms, e.g. 200
  release_time: int ms, e.g. 150

compressor_filter (Compressor):
  ratio: float e.g. 4.0 (compression ratio, 2:1 to 6:1 for voice)
  threshold: float dB e.g. -18.0
  attack_time: int ms e.g. 6
  release_time: int ms e.g. 60
  output_gain: float dB e.g. 0.0
  sidechain_source: string (source name or empty string)

gain_filter (Gain):
  db: float e.g. 5.0

color_filter_v2 (Color Correction):
  brightness: float -1.0 to 1.0
  contrast: float -4.0 to 4.0
  saturation: float -1.0 to 5.0
  hue_shift: float -180.0 to 180.0
  opacity: float 0.0 to 1.0

chroma_key_filter_v2 (Chroma Key):
  key_color_type: "green" | "blue" | "red" | "magenta" | "custom"
  similarity: int 1-1000 e.g. 400
  smoothness: int 1-1000 e.g. 80
  spill: int 1-1000 e.g. 100

crop_filter (Crop/Pad):
  left: int pixels
  right: int pixels
  top: int pixels
  bottom: int pixels

sharpness_filter_v2 (Sharpness):
  sharpness: float 0.0 to 1.0

scroll_filter (Scroll):
  speed_x: float pixels/sec horizontal (negative = scroll left)
  speed_y: float pixels/sec vertical (negative = scroll up)
  loop: bool (default true)

render_delay_filter (Render Delay):
  delay_ms: int milliseconds, e.g. 200

lut_filter (Apply LUT):
  image_path: string (full path to .cube file)
  clut_amount: float 0.0 to 1.0 (blend amount)

mask_filter (Image Mask/Blend):
  type: "mask_alpha_filter.effect" | "mask_color_filter.effect"
  image_path: string (full path to mask image)
  stretch: bool

limiter_filter (Limiter — audio):
  threshold: float dB e.g. 0.0
  release_time: int ms e.g. 60

expander_filter (Expander/Gate — audio):
  detector: "RMS" | "peak"
  presets: "expander" | "gate"
  ratio: float e.g. 2.0
  threshold: float dB e.g. -40.0
  attack_time: int ms e.g. 10
  release_time: int ms e.g. 50
  output_gain: float dB e.g. 0.0

invert_polarity_filter (Invert Polarity — audio): no settings needed, empty dict {}

NOTE for SetSourceFilterSettings on existing filters: always call GetSourceFilterList first to confirm the filter name, then emit SetSourceFilterSettings with just the fields you want to change — you don't need to re-send all fields.

"""

_PROMPT_WEBCAM_DETAIL = """  Webcam/capture — input_kind AND settings fields differ by OS (current platform shown in OBS INPUT_KIND VALUES above):
- Do not always assume that the OBS Virtual Camera is the only video capture device. If that is the only source remind the user to scan in Tab 01.

  Windows (dshow_input):
    video_device_id: string — use the device ID exactly as shown in [SELECTED DEVICES] or [ALL DETECTED Webcams] context. The backend will sanitize it automatically.
    last_video_device_id: same value as video_device_id
    res_type: 1
    resolution: string — use the device's max_resolution from context, e.g. "1920x1080" or "1280x720"
    last_resolution: same as resolution
    activate: true
    active: true

  macOS (av_capture_input):
    device: string — the AVFoundation uniqueID from Tab 01 context (UUID-like string, NOT the display name)
    preset: "AVCaptureSessionPreset1920x1080" | "AVCaptureSessionPreset1280x720" | "AVCaptureSessionPreset3840x2160"
    use_preset: true
    NOTE: do NOT include video_device_id, resolution, or res_type — these are Windows-only fields that OBS ignores on Mac

  Linux (v4l2_input):
    device_id: string — the device path from Tab 01 context e.g. "/dev/video0"
    resolution: string e.g. "1920x1080" (optional)

  Workflow to get device value:
    1. FIRST choice: use the webcam from [SELECTED DEVICES from Tab 01 scan] or [ALL DETECTED Webcams] in context. Use the id value exactly as given — the backend handles path format automatically.
    2. SECOND choice: if an existing video capture source already exists in OBS, call GetInputSettings on it to read its current video_device_id, then use that same value for CreateInput.
    3. If neither available: tell the user to run a scan in Tab 01 or confirm their device name."""


_PROMPT_AUDIO_DETAIL = """AUDIO SOURCE CREATION — exact CreateInput parameters by OS:

Windows (wasapi_input_capture for mic, wasapi_output_capture for desktop audio):
  CreateInput fields:
    input_kind: "wasapi_input_capture" (microphone) OR "wasapi_output_capture" (desktop/speakers)
    input_settings: {"device_id": "<GUID from context>"}
    Device ID format: "{0.0.1.00000000}.{xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}"
    Input GUID prefix: {0.0.1...} — Output GUID prefix: {0.0.0...}
  Example mic: [OBS_ACTION:{"command":"CreateInput","params":{"scene_name":"Scene","input_name":"Microphone","input_kind":"wasapi_input_capture","input_settings":{"device_id":"{0.0.1.00000000}.{your-guid-here}"}},"label":"Add Microphone"}]
  Example desktop: [OBS_ACTION:{"command":"CreateInput","params":{"scene_name":"Scene","input_name":"Desktop Audio","input_kind":"wasapi_output_capture","input_settings":{"device_id":"{0.0.0.00000000}.{your-guid-here}"}},"label":"Add Desktop Audio"}]

macOS (coreaudio_input_capture for mic, coreaudio_output_capture for desktop):
  input_settings: {"device_uid": "<UID from context>"}
  Example: [OBS_ACTION:{"command":"CreateInput","params":{"scene_name":"Scene","input_name":"Microphone","input_kind":"coreaudio_input_capture","input_settings":{"device_uid":"BuiltInMicrophoneDevice"}},"label":"Add Microphone"}]

Linux (pulse_input_capture for mic, pulse_output_capture for desktop):
  input_settings: {"device_id": "<device from context or empty string for default>"}

CRITICAL RULES FOR AUDIO:
- ALWAYS use the exact device_id/device_uid from the [SYSTEM CONTEXT] provided. Never invent GUIDs.
- If no device IDs are in context (no scan), do NOT emit any audio CreateInput tags. Tell user to scan in Tab 01 first.
- Input (mic) and output (desktop) use DIFFERENT input_kind values. Never mix them.
- When user asks for BOTH mic and speakers/desktop audio, you MUST emit TWO separate [OBS_ACTION:...] tags — one for input, one for output. NEVER combine them into one tag. NEVER stop after just one.
- After creating, you can set volume with SetInputVolume and mute with SetInputMute.
"""


_PROMPT_TEXT_SOURCE_DETAIL = """TEXT SOURCE CREATION — exact CreateInput parameters by OS:

Windows: input_kind = "text_gdiplus"
  input_settings keys: text (string), font (dict with face/size/flags/style), color (ABGR int — use 0xFFFFFFFF for white, 0xFF0000FF for red, 0xFF00FF00 for green, 0xFFFFFF00 for yellow, 0xFF0000FF for blue), color2 (gradient end, same format), gradient (bool), outline (bool), outline_color (ABGR int), outline_size (int), bk_color (ABGR int), bk_opacity (int 0-100), align ("left"|"center"|"right"), valign ("top"|"center"|"bottom"), vertical (bool), word_wrap (bool)
  CRITICAL: color for GDI+ is ABGR int, NOT hex string. White=4294967295, Red=4278190335, Green=4278255360, Yellow=4278255615, Blue=4294901760, Black=4278190080
  Example white bold centered text: [OBS_ACTION:{"command":"CreateInput","params":{"scene_name":"Scene","input_name":"My Text","input_kind":"text_gdiplus","input_settings":{"text":"STARTING SOON","font":{"face":"Arial","size":72,"flags":1,"style":"Bold"},"color":4294967295,"align":"center","valign":"center","word_wrap":true}},"label":"Add Text Source"}]

macOS / Linux: input_kind = "text_ft2_source"
  input_settings keys: text (string), font (dict with face/size/flags/style), color (ABGR int, same as above), color2, outline (bool), drop_shadow (bool), word_wrap (bool), from_file (bool), text_file (path string)
  Example: [OBS_ACTION:{"command":"CreateInput","params":{"scene_name":"Scene","input_name":"My Text","input_kind":"text_ft2_source","input_settings":{"text":"STARTING SOON","font":{"face":"Arial","size":72,"flags":1,"style":"Bold"},"color":4294967295}},"label":"Add Text Source"}]

FONT FLAGS: 0=Normal, 1=Bold, 2=Italic, 3=Bold+Italic, 4=Underline, 8=Strikeout
ABGR COLOR REFERENCE (most common):
  White:  4294967295  |  Black: 4278190080  |  Red:    4278190335
  Green:  4278255360  |  Blue:  4294901760  |  Yellow: 4278255615
  Orange: 4278225407  |  Purple:4286578815  |  Cyan:   4294967040
NOTE: After CreateInput for a text source, use SetTextStyle to change color instead of recreating — SetTextStyle accepts #RRGGBB hex and converts automatically.
"""

_PROMPT_TRANSFORM_DETAIL = """SCENE ITEM TRANSFORM — complete parameter reference:

SetSceneItemTransform keys (all optional — only include what you're changing):
  positionX, positionY: float pixels from top-left of canvas. Canvas center 1920x1080 = 960,540
  scaleX, scaleY: float multiplier. 1.0=native size. 0.5=half. 2.0=double.
  rotation: float degrees clockwise. 0=upright, 90=rotated right, -90=rotated left, 180=upside down
  cropTop, cropBottom, cropLeft, cropRight: int pixels to crop from each edge
  width, height: float — set explicit pixel size (overrides scale if both used)
  
  alignment: int bitmask for the source's ANCHOR POINT relative to positionX/positionY:
    5 = top-left (default), 4 = top-center, 6 = top-right
    1 = center-left,        0 = center,     2 = center-right  
    9 = bottom-left,        8 = bottom-center, 10 = bottom-right

  boundsType: string — how source fits within its bounds box:
    "OBS_BOUNDS_NONE"         — no bounds, use scale
    "OBS_BOUNDS_STRETCH"      — stretch to fill bounds exactly
    "OBS_BOUNDS_SCALE_INNER"  — scale to fit inside bounds (letterbox/pillarbox)
    "OBS_BOUNDS_SCALE_OUTER"  — scale to fill bounds (may crop)
    "OBS_BOUNDS_SCALE_TO_WIDTH"  — scale to match bounds width
    "OBS_BOUNDS_SCALE_TO_HEIGHT" — scale to match bounds height
    "OBS_BOUNDS_MAX_ONLY"     — only shrink, never enlarge
  boundsWidth, boundsHeight: float — size of the bounds box when boundsType is set

COMMON POSITIONING EXAMPLES:
  Full-screen 1920x1080: positionX=0, positionY=0, scaleX=1.0, scaleY=1.0, alignment=5
  Centered on canvas:    positionX=960, positionY=540, alignment=0
  Bottom-right corner:   positionX=1920, positionY=1080, alignment=10
  Top-right corner:      positionX=1920, positionY=0, alignment=6
  Small overlay (300x200 top-right): positionX=1620, positionY=0, width=300, height=200, alignment=5

Example: [OBS_ACTION:{"command":"SetSceneItemTransform","params":{"scene_name":"Scene","source_name":"Webcam","transform":{"positionX":960,"positionY":540,"alignment":0,"scaleX":0.5,"scaleY":0.5}},"label":"Center Webcam at Half Size"}]
"""

_PROMPT_FILTER_CREATE_DETAIL = """FILTER CREATION — exact CreateSourceFilter parameters:

CreateSourceFilter required params: source_name, filter_name (your chosen name), filter_kind (exact string below), filter_settings (dict)

READY-TO-USE EXAMPLES (copy and adapt):

Noise Suppression (RNNoise — best quality):
[OBS_ACTION:{"command":"CreateSourceFilter","params":{"source_name":"Mic/Aux","filter_name":"Noise Suppression","filter_kind":"noise_suppress_filter_v2","filter_settings":{"method":"rnnoise","suppress_level":-30}},"label":"Add Noise Suppression"}]

Noise Gate:
[OBS_ACTION:{"command":"CreateSourceFilter","params":{"source_name":"Mic/Aux","filter_name":"Noise Gate","filter_kind":"noise_gate_filter","filter_settings":{"open_threshold":-26.0,"close_threshold":-32.0,"attack_time":25,"hold_time":200,"release_time":150}},"label":"Add Noise Gate"}]

Compressor (voice):
[OBS_ACTION:{"command":"CreateSourceFilter","params":{"source_name":"Mic/Aux","filter_name":"Compressor","filter_kind":"compressor_filter","filter_settings":{"ratio":4.0,"threshold":-18.0,"attack_time":6,"release_time":60,"output_gain":0.0,"sidechain_source":""}},"label":"Add Compressor"}]

Gain (+5dB boost):
[OBS_ACTION:{"command":"CreateSourceFilter","params":{"source_name":"Mic/Aux","filter_name":"Gain","filter_kind":"gain_filter","filter_settings":{"db":5.0}},"label":"Add Gain"}]

Color Correction (on a video source):
[OBS_ACTION:{"command":"CreateSourceFilter","params":{"source_name":"Webcam","filter_name":"Color Correction","filter_kind":"color_filter_v2","filter_settings":{"brightness":0.0,"contrast":0.0,"saturation":0.0,"hue_shift":0.0,"opacity":1.0}},"label":"Add Color Correction"}]

Chroma Key (green screen):
[OBS_ACTION:{"command":"CreateSourceFilter","params":{"source_name":"Webcam","filter_name":"Green Screen","filter_kind":"chroma_key_filter_v2","filter_settings":{"key_color_type":"green","similarity":400,"smoothness":80,"spill":100}},"label":"Add Chroma Key"}]

Sharpness:
[OBS_ACTION:{"command":"CreateSourceFilter","params":{"source_name":"Webcam","filter_name":"Sharpness","filter_kind":"sharpness_filter_v2","filter_settings":{"sharpness":0.5}},"label":"Add Sharpness"}]

Crop/Pad:
[OBS_ACTION:{"command":"CreateSourceFilter","params":{"source_name":"Game Capture","filter_name":"Crop","filter_kind":"crop_filter","filter_settings":{"left":0,"right":0,"top":0,"bottom":0}},"label":"Add Crop"}]

Render Delay:
[OBS_ACTION:{"command":"CreateSourceFilter","params":{"source_name":"Webcam","filter_name":"Render Delay","filter_kind":"render_delay_filter","filter_settings":{"delay_ms":200}},"label":"Add Render Delay"}]

IMPORTANT WORKFLOW:
1. Always call GetSourceFilterList first to check if a filter already exists before creating a duplicate.
2. Use exact source name from OBS context (Audio Inputs section for audio sources, scene sources for video).
3. For audio filters (noise suppression, gate, compressor, gain) — source_name is the AUDIO SOURCE name (e.g. "Mic/Aux", "Microphone", "Desktop Audio"), NOT the scene name.
4. filter_name is your chosen display name — can be anything descriptive.
"""

_WIDGET_KW       = frozenset(['widget','alert box','alert','chat box','chatbox','event list',
    'goal bar','labels','viewer count','sponsor','donation','css','overlay','styler',
    'browser source','stream overlay','fuze widget'])
_FILTER_KW       = frozenset(['filter','noise','suppress','compressor','gate','gain',
    'chroma','crop','sharpness','scroll','lut','mask','limiter','expander',
    'reverb','color correct','color grading','add filter','create filter',
    'green screen','color correction','render delay'])
_WEBCAM_KW       = frozenset(['webcam','camera','capture device','video capture',
    'dshow','av_capture','v4l2','video device','add camera','add webcam'])
_WELCOME_KW      = frozenset(['collab','leaderboard','recap','checklist','countdown',
    'patch notes','review','tip of the day','stream tip','platform connect',
    'connect twitch','connect youtube','connect kick','connect facebook',
    'connect tiktok','connect platform','disconnect platform'])
_AUDIO_KW        = frozenset(['add audio','add mic','add microphone','add desktop audio','add speaker',
    'wasapi','coreaudio','pulse_input','audio source','audio input','audio output',
    'create audio','microphone source','desktop audio source',
    'my audio','my mic','my microphone','audio to'])
_TEXT_SOURCE_KW  = frozenset(['add text','create text','text source','add label','starting soon',
    'brb','be right back','ending soon','offline screen','title text','stream title',
    'text_gdiplus','text_ft2','gdi','freetype','add a text','create a text',
    'add some text','add words','add caption'])
_TRANSFORM_KW    = frozenset(['move','position','resize','scale','rotate','rotation','crop',
    'place','center','align','layout','fit','stretch','fullscreen','full screen',
    'full-screen','corner','bottom right','top right','top left','bottom left',
    'size','bigger','smaller','larger','shrink','grow','bounds','transform',
    'picture in picture','pip','overlay position','source size'])
_FILTER_CREATE_KW = frozenset(['add filter','create filter','noise suppression','noise gate',
    'compressor','add compressor','add noise','suppress','green screen','chroma key',
    'color correction','color grading','sharpen','sharpness','crop filter','gain filter',
    'add gain','render delay','apply filter','put a filter','add a filter',
    'remove background','background removal','audio filter','video filter'])
_TEXT_OPS_KW     = frozenset(['text','caption','font','label','gdi','freetype','change text',
    'update text','set text','word','title','subtitle','heading','rename text',
    'color text','bold','italic','font size','text color','text style'])
_SOURCES_KW      = frozenset(['add','create','remove','delete','duplicate','new scene',
    'new source','add scene','delete scene','import','browser source','image source',
    'media source','add source','remove source'])
_AUDIO_ADV_KW    = frozenset(['balance','pan','sync offset','sync delay','monitoring',
    'monitor audio','audio balance','audio pan','left channel','right channel',
    'audio delay','monitor type','get input list'])
_TRANSITIONS_KW  = frozenset(['transition','fade','cut','stinger','studio mode','preview',
    'push to program','scene transition','transition duration','swipe','slide',
    'dissolve','luma wipe'])
_RECORD_STREAM_KW = frozenset(['record','stream','go live','start stream','stop stream',
    'start recording','stop recording','pause record','replay buffer','save replay',
    'virtual camera','virtual cam','virtualcam','go offline','end stream'])
_VIDEO_KW        = frozenset(['resolution','canvas','fps','frame rate','1080p','720p',
    '1440p','4k','downscale','output resolution','canvas resolution',
    'base resolution','set fps','change resolution','set resolution'])


def _build_system_prompt(msg: str, return_context_flag: bool = False):
    """Core is always cached. CMD slices injected only when keywords match — keeps context lean.
    If return_context_flag=True, returns (blocks, had_action_context) instead of just blocks."""
    ml = msg.lower()

    def _kw(kw_set):
        return any(k in ml for k in kw_set)

    # Core blocks — always injected, stable cache boundary
    blocks = [
        {
            "type": "text",
            "text": _PROMPT_CORE_B1 + _CMD_CORE,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    # Command slices — injected only when relevant
    extras = []
    if _kw(_TEXT_OPS_KW):
        extras.append("[CMD_TEXT]\n" + _CMD_TEXT)
    if _kw(_SOURCES_KW) or _kw(_WEBCAM_KW) or _kw(_AUDIO_KW) or _kw(_TEXT_SOURCE_KW):
        extras.append("[CMD_SOURCES]\n" + _CMD_SOURCES)
    if _kw(_AUDIO_ADV_KW):
        extras.append("[CMD_AUDIO_ADV]\n" + _CMD_AUDIO_ADV)
    if _kw(_TRANSFORM_KW):
        extras.append("[CMD_TRANSFORMS]\n" + _CMD_TRANSFORMS)
    if _kw(_FILTER_KW) or _kw(_FILTER_CREATE_KW):
        extras.append("[CMD_FILTERS]\n" + _CMD_FILTERS)
    if _kw(_TRANSITIONS_KW):
        extras.append("[CMD_TRANSITIONS]\n" + _CMD_TRANSITIONS)
    if _kw(_RECORD_STREAM_KW):
        extras.append("[CMD_RECORD_STREAM]\n" + _CMD_RECORD_STREAM)
    if _kw(_VIDEO_KW):
        extras.append("[CMD_VIDEO]\n" + _CMD_VIDEO)

    # Detail blocks — injected on top of command slices for max specificity
    if _kw(_WELCOME_KW):
        extras.append("[WELCOME TAB DETAIL]\n" + _PROMPT_WELCOME_DETAIL)
    if _kw(_WIDGET_KW):
        extras.append("[WIDGET DETAIL]\n" + _PROMPT_WIDGET_DETAIL)
    if _kw(_FILTER_KW) or _kw(_FILTER_CREATE_KW):
        extras.append("[FILTER_DETAIL]\n" + _PROMPT_FILTER_DETAIL)
    if _kw(_WEBCAM_KW):
        extras.append("[WEBCAM_DETAIL]\n" + _PROMPT_WEBCAM_DETAIL)
    if _kw(_AUDIO_KW):
        extras.append("[AUDIO_CREATE_DETAIL]\n" + _PROMPT_AUDIO_DETAIL)
    if _kw(_TEXT_SOURCE_KW):
        extras.append("[TEXT_SOURCE_DETAIL]\n" + _PROMPT_TEXT_SOURCE_DETAIL)
    if _kw(_TRANSFORM_KW):
        extras.append("[TRANSFORM_DETAIL]\n" + _PROMPT_TRANSFORM_DETAIL)
    if _kw(_FILTER_CREATE_KW):
        extras.append("[FILTER_CREATE_DETAIL]\n" + _PROMPT_FILTER_CREATE_DETAIL)

    had_action_context = bool(extras)
    if extras:
        blocks.append({"type": "text", "text": "\n\n".join(extras)})

    # Final reminder — placed LAST so it's closest to the conversation.
    # Models lose focus on instructions in the middle of long prompts.
    blocks.append({
        "type": "text",
        "text": (
            "[FINAL REMINDER — READ BEFORE EVERY RESPONSE]\n"
            "If the user wants ANY OBS change, you MUST emit [OBS_ACTION:...] tags.\n"
            "Without tags, no Apply button appears and NOTHING happens.\n"
            "Format: [OBS_ACTION:{\"command\":\"...\",\"params\":{...},\"label\":\"...\"}]\n"
            "NEVER say 'Click Apply' without emitting at least one tag.\n"
            "To add an EXISTING source to another scene: use CreateSceneItem (not CreateInput).\n"
            "Example: [OBS_ACTION:{\"command\":\"CreateSceneItem\",\"params\":{\"scene_name\":\"BRB\",\"source_name\":\"Microphone\"},\"label\":\"Add Mic to BRB\"}]\n\n"
            "PRE-EMISSION CHECKLIST (do this mentally before writing):\n"
            "1. Count how many distinct items the user requested (e.g. 'webcam and speakers' = 2 items, 'mic, speakers, and webcam' = 3 items).\n"
            "2. For EACH item, you MUST emit exactly ONE [OBS_ACTION:...] tag. N items = N tags.\n"
            "3. Emit ALL tags FIRST at the top of your response, before any explanation.\n"
            "4. After writing your response, verify: does the number of tags match the number of items? If not, you dropped one — add it.\n"
            "EXAMPLE — user says 'add my webcam and speakers':\n"
            "  Tag 1: [OBS_ACTION:{\"command\":\"CreateInput\",\"params\":{\"scene_name\":\"Scene\",\"input_name\":\"Webcam\",\"input_kind\":\"dshow_input\",\"input_settings\":{\"video_device_id\":\"...\"}},\"label\":\"Add Webcam\"}]\n"
            "  Tag 2: [OBS_ACTION:{\"command\":\"CreateInput\",\"params\":{\"scene_name\":\"Scene\",\"input_name\":\"Desktop Audio\",\"input_kind\":\"wasapi_output_capture\",\"input_settings\":{\"device_id\":\"...\"}},\"label\":\"Add Speakers\"}]\n"
            "  Two items requested → two tags emitted. Never collapse into one."
        ),
    })

    if return_context_flag:
        return blocks, had_action_context
    return blocks

User = get_user_model()

# ====== VERSION / UPDATES ======


# FUZE UPDATES

FUZE_VERSION = '1.1.7'

@require_http_methods(["GET"])
def fuze_check_update(request):
    platform = request.GET.get('platform', 'windows')
    
    urls = {
        'windows': 'https://storage.googleapis.com/fuze-public/fuze-installer/Fuze-Installer.exe',
        'darwin': 'https://storage.googleapis.com/fuze-public/fuze-installer/Fuze-Installer.dmg',
        'linux': 'https://storage.googleapis.com/fuze-public/fuze-installer/Fuze-Installer.deb',
    }
    
    return JsonResponse({
        'version': FUZE_VERSION,
        'download_url': urls.get(platform, urls['windows']),
        'changelog': 'Fuze 1.1.7 | Disclaimer Update',
        'mandatory': True
    })

FUZE_PATCH_NOTES = {
    'version': FUZE_VERSION,
    'changelog': 'FUZE 1.1.7 | Disclaimer Update',
    'notes': [
        '- Fuze Development is now 1.0 after 6 months of work!',
        '- Upgraded Fuze-AI to now use commands to modify OBS!',
        '- Fuze-AI Usage Limits Upgraded to 450K Total token context!',
        '- Changed Fuze-AI Icon to custom Icon!',
        '- In app fixes and improvements (Start page at top / "enter" to send websocket password)!',
    ]
}

@require_http_methods(["GET"])
def fuze_patch_notes(request):
    return JsonResponse(FUZE_PATCH_NOTES)


class SecureAuth:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key.encode()
    
    def create_signed_token(self, user_id: int, tier: str, token_version: int = 0) -> str:
        timestamp = int(time.time())
        message = f"{user_id}:{tier}:{timestamp}:{token_version}"
        signature = hmac.new(self.secret_key, message.encode(), hashlib.sha256).hexdigest()
        return f"{message}:{signature}"
    
    def verify_token(self, token: str) -> dict:
        try:
            parts = token.split(':')
            if len(parts) != 5:
                return {'valid': False}
            user_id, tier, timestamp, token_version, signature = parts
            message = f"{user_id}:{tier}:{timestamp}:{token_version}"
            expected = hmac.new(self.secret_key, message.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return {'valid': False}
            if int(time.time()) - int(timestamp) > 2592000:  # 30 days
                return {'valid': False}
            return {'valid': True, 'user_id': int(user_id), 'tier': tier, 'token_version': int(token_version)}
        except:
            return {'valid': False}

_fuze_key = os.environ.get('FUZE_SECRET_KEY')
if not _fuze_key:
    _fuze_key = os.environ.get('DJANGO_SECRET_KEY')
    if _fuze_key:
        logger.warning("FUZE_SECRET_KEY not set — falling back to DJANGO_SECRET_KEY. Set a dedicated key in production.")
    else:
        raise RuntimeError("FUZE_SECRET_KEY environment variable is required")
auth_manager = SecureAuth(_fuze_key)

def require_tier(min_tier):
    """Decorator enforcing tier requirements SERVER-SIDE"""
    tier_hierarchy = {'free': 0, 'pro': 1, 'lifetime': 2}
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return JsonResponse({'error': 'No token'}, status=401)
            token = auth_header.replace('Bearer ', '')
            verification = auth_manager.verify_token(token)
            if not verification['valid']:
                return JsonResponse({'error': 'Invalid token'}, status=401)
            try:
                user = User.objects.get(id=verification['user_id'])
                if user.fuze_tier != verification['tier']:
                    return JsonResponse({'error': 'Token mismatch'}, status=401)
            except User.DoesNotExist:
                return JsonResponse({'error': 'User not found'}, status=401)
            if tier_hierarchy.get(user.fuze_tier, 0) < tier_hierarchy.get(min_tier, 0):
                return JsonResponse({'error': 'Insufficient tier', 'required': min_tier}, status=403)
            request.fuze_user = user
            return func(request, *args, **kwargs)
        return wrapper
    return decorator

def get_user_from_token(token):
    """Secure token verification - returns user regardless of tier change"""
    verification = auth_manager.verify_token(token)
    if not verification['valid']:
        return None
    try:
        user = User.objects.get(id=verification['user_id'])
        # Reject tokens issued before a password change
        if getattr(user, 'fuze_token_version', 0) != verification.get('token_version', 0):
            return None
        # Store original token tier for checking later
        user._token_tier = verification['tier']
        return user
    except User.DoesNotExist:
        return None

# ===== VALIDATORS =====
def validate_username(username):
    """Validate username matches Django rules"""
    if not username:
        raise ValidationError("Username is required")
    if len(username) > 20:
        raise ValidationError("Username must be 20 characters or fewer")
    if not re.match(r'^[\w.@+-]+$', username):
        raise ValidationError("Username can only contain letters, digits and @/./+/-/_ characters")
    from ACCOUNTS.validators import contains_profanity
    if contains_profanity(username):
        raise ValidationError("Username contains inappropriate language")
    return username

# ===== AUTHENTICATION ENDPOINTS =====

@csrf_exempt
def fuze_signup(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    data = json.loads(request.body)
    email = data.get('email')
    username = data.get('username')
    password = data.get('password')
    
    try:
        validate_username(username)
    except ValidationError as e:
        logger.error(f'Request error: {e}'); return JsonResponse({'success': False, 'error': 'Bad request'}, status=400)
    
    if len(password) < 8:
        return JsonResponse({'success': False, 'error': 'Password must be at least 8 characters'}, status=400)
    
    if User.objects.filter(email=email).exists():
        return JsonResponse({'success': False, 'error': 'Email already registered'}, status=400)
    
    if User.objects.filter(username=username).exists():
        return JsonResponse({'success': False, 'error': 'Username already taken'}, status=400)
    
    user = User.objects.create_user(username=username, email=email, password=password)
    user.fuze_tier = 'free'
    session_id = data.get('session_id')
    activate_fuze_user(user)
    update_active_session(user, session_id, get_client_ip(request))
    user.save()

    # Track signup activity
    UserActivity.objects.create(
        user=user,
        activity_type='signup',
        source='app'
    )

    token = auth_manager.create_signed_token(user.id, 'free', getattr(user, 'fuze_token_version', 0))
    
    return JsonResponse({
        'success': True,
        'token': token,
        'tier': 'free',
        'email': user.email,
        'username': user.username
    })

@csrf_exempt
@require_http_methods(["POST"])
def fuze_login(request):
    try:
        # Rate limiting by IP
        ip = get_client_ip(request)
        attempts_key = f'fuze_login_attempts_{ip}'
        attempts = cache.get(attempts_key, 0)
        
        if attempts >= 5:
            return JsonResponse({
                'success': False, 
                'error': 'Too many login attempts. Please try again in 15 minutes.'
            }, status=429)
        
        data = json.loads(request.body)
        email_or_username = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email_or_username or not password:
            cache.set(attempts_key, attempts + 1, 900)  # 15 min
            return JsonResponse({'success': False, 'error': 'Email/username and password required'})
        
        user = None
        if '@' in email_or_username:
            try:
                user_obj = User.objects.get(email=email_or_username)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        else:
            user = authenticate(username=email_or_username, password=password)
        
        if not user:
            try:
                user_obj = User.objects.get(email=email_or_username)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                pass
        
        if user:
            cache.delete(attempts_key)
            
            # Track login activity
            UserActivity.objects.create(
                user=user,
                activity_type='login',
                source='app'
            )

            session_id = data.get('session_id')
            activate_fuze_user(user)
            update_active_session(user, session_id, get_client_ip(request))
            
            token = auth_manager.create_signed_token(user.id, user.fuze_tier, getattr(user, 'fuze_token_version', 0))
            return JsonResponse({
                'success': True,
                'token': token,
                'email': user.email,
                'username': user.username,
                'tier': user.fuze_tier,
                'profile_picture': f'https://bomby.us{user.profile_picture.url}' if user.profile_picture else None
            })
        else:
            # Failed login - increment attempts
            cache.set(attempts_key, attempts + 1, 900)  # 15 min
            return JsonResponse({'success': False, 'error': 'Invalid credentials'})
            
    except Exception as e:
        logger.error(f'Server error: {e}'); return JsonResponse({'success': False, 'error': 'Internal error'}, status=500)

@csrf_exempt
def fuze_google_auth_init(request):
    """Initiate Google OAuth flow for Fuze"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    data = json.loads(request.body)
    session_id = data.get('session_id')
    
    if not session_id:
        return JsonResponse({'error': 'session_id required'}, status=400)
    
    # Generate state token and store session mapping
    state_token = secrets.token_urlsafe(32)
    cache.set(f'fuze_oauth_state_{state_token}', session_id, timeout=600)  # 10 min
    
    # Build Google OAuth URL
    auth_url = f"https://bomby.us/accounts/google/login/?next=https://bomby.us/fuze/google-callback?state={state_token}"
    
    return JsonResponse({
        'success': True,
        'auth_url': auth_url,
        'state': state_token
    })

@csrf_exempt
def fuze_google_callback(request):
    """Handle Google OAuth callback for Fuze"""
    state = request.GET.get('state')
    
    if not state:
        return HttpResponse("Invalid state", status=400)
    
    session_id = cache.get(f'fuze_oauth_state_{state}')
    if not session_id:
        return HttpResponse("State expired or invalid", status=400)
    
    # User is now authenticated via allauth
    if not request.user.is_authenticated:
        return HttpResponse("Authentication failed", status=401)
    
    user = request.user
    
    token = auth_manager.create_signed_token(user.id, user.fuze_tier, getattr(user, 'fuze_token_version', 0))
    
    # Store token for session retrieval
    cache.set(f'fuze_google_token_{session_id}', {
        'token': token,
        'email': user.email,
        'username': user.username,
        'tier': user.fuze_tier
    }, timeout=120)  # 2 minutes to retrieve
    
    # Update user's Fuze activation
    activate_fuze_user(user)
    update_active_session(user, session_id, get_client_ip(request))
    
    # Track activity
    UserActivity.objects.create(
        user=user,
        activity_type='login',
        source='app'
    )
    
    return render(request, 'FUZE/google_success.html')


@csrf_exempt
def fuze_google_auth_poll(request):
    """Poll for completed Google OAuth"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    data = json.loads(request.body)
    session_id = data.get('session_id')
    
    if not session_id:
        return JsonResponse({'error': 'session_id required'}, status=400)
    
    # Check if auth completed
    auth_data = cache.get(f'fuze_google_token_{session_id}')
    
    if auth_data:
        cache.delete(f'fuze_google_token_{session_id}')
        
        return JsonResponse({
            'success': True,
            'completed': True,
            'token': auth_data['token'],
            'email': auth_data['email'],
            'username': auth_data['username'],
            'tier': auth_data['tier']
        })
    
    return JsonResponse({
        'success': True,
        'completed': False
    })

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def fuze_verify(request):
    if request.method == "OPTIONS":
        return JsonResponse({'status': 'ok'})
    
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'valid': False, 'authenticated': False, 'reachable': True})
    
    token = auth_header.replace('Bearer ', '')
    if token == 'none':
        return JsonResponse({'valid': False, 'authenticated': False, 'reachable': True})
    
    user = get_user_from_token(token)
    if user:
        session_id = request.META.get('HTTP_X_SESSION_ID')
        if session_id:
            update_active_session(user, session_id, get_client_ip(request))
        
        # Check if 3-month plan has expired
        if user.fuze_tier == 'pro':
            try:
                sub = FuzeSubscription.objects.get(user=user, is_active=True)
                if sub.expires_at and sub.expires_at <= timezone.now():
                    user.fuze_tier = 'free'
                    user.save()
                    sub.is_active = False
                    sub.plan_type = 'free'
                    sub.save()
                    TierChange.objects.create(
                        user=user,
                        from_tier='pro',
                        to_tier='free',
                        reason='3month_expired'
                    )
            except FuzeSubscription.DoesNotExist:
                pass
        
        response_data = {
            'valid': True,
            'authenticated': True,
            'tier': user.fuze_tier,
            'email': user.email,
            'username': user.username,
            'profile_picture': f'https://bomby.us{user.profile_picture.url}' if user.profile_picture else None,
            'reachable': True
        }
        
        # Issue new token if tier changed
        token_tier = getattr(user, '_token_tier', None)
        if token_tier and user.fuze_tier != token_tier:
            response_data['new_token'] = auth_manager.create_signed_token(user.id, user.fuze_tier, getattr(user, 'fuze_token_version', 0))
        
        return JsonResponse(response_data)
    
    return JsonResponse({'valid': False, 'authenticated': False, 'reachable': True})

# ===== QUICK START =====

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuze_quickstart_dismiss(request):
    """Dismiss quick-start modal for logged-in user"""
    user = request.fuze_user
    user.quickstart_dismissed = True
    user.save()
    return JsonResponse({'success': True})

@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuze_quickstart_check(request):
    """Check if user has dismissed quick-start modal"""
    user = request.fuze_user
    return JsonResponse({'dismissed': user.quickstart_dismissed})

@require_http_methods(["GET"])
def fuze_announcements(request):
    """Public endpoint - no auth required. Returns active announcements."""
    announcements = Announcement.objects.filter(active=True).values(
        'id', 'message', 'type', 'created_at'
    )
    return JsonResponse({'announcements': list(announcements)})


@staff_member_required
@csrf_exempt
@require_http_methods(["POST"])
def fuze_announcement_create(request):
    try:
        data = json.loads(request.body)
        ann = Announcement.objects.create(
            message=data['message'],
            type=data.get('type', 'info'),
        )
        return JsonResponse({'success': True, 'id': ann.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@staff_member_required
@csrf_exempt
@require_http_methods(["POST"])
def fuze_announcement_toggle(request):
    try:
        data = json.loads(request.body)
        ann = Announcement.objects.get(id=data['id'])
        ann.active = not ann.active
        ann.save()
        return JsonResponse({'success': True, 'active': ann.active})
    except Announcement.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Not found'})


@staff_member_required
@csrf_exempt
@require_http_methods(["POST"])
def fuze_announcement_delete(request):
    try:
        data = json.loads(request.body)
        Announcement.objects.filter(id=data['id']).delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

# ===== TEMPLATES =====

@csrf_exempt
@require_http_methods(["GET"])
def fuze_list_templates(request):
    """List available templates based on user tier"""
    auth_header = request.headers.get('Authorization', '')
    user = None
    
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        user = get_user_from_token(token)
    
    templates = [
        {'id': 'simple', 'name': 'Simple Stream', 'tier': 'free'},
        {'id': 'gaming', 'name': 'Gaming Stream', 'tier': 'free'},
    ]
    
    if user and user.fuze_tier in ['pro', 'lifetime']:
        templates.extend([
            {'id': 'just-chatting', 'name': 'Just Chatting', 'tier': 'premium'},
            {'id': 'tutorial', 'name': 'Desktop Tutorial', 'tier': 'premium'},
            {'id': 'podcast', 'name': 'Podcast', 'tier': 'premium'},
        ])
    
    return JsonResponse({'templates': templates})

@csrf_exempt
@require_http_methods(["GET"])
def fuze_get_template(request, template_id):
    auth_header = request.headers.get('Authorization', '')
    user = None
    
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        user = get_user_from_token(token)
    
    free_templates = ['simple', 'gaming']
    premium_templates = ['just-chatting', 'tutorial', 'podcast']
    
    if template_id in premium_templates:
        if not user or user.fuze_tier not in ['pro', 'lifetime']:
            return JsonResponse({'error': 'Premium required'}, status=403)
    
    if template_id not in free_templates + premium_templates:
        return JsonResponse({'error': 'Template not found'}, status=404)
    
    if not re.match(r'^[a-zA-Z0-9_-]+$', template_id):
        return JsonResponse({'error': 'Invalid template ID'}, status=400)
    
    try:
        client = storage.Client()
        bucket = client.bucket('bomby-user-uploads')
        blob = bucket.blob(f'fuze-templates/{template_id}.json')
        template_data = json.loads(blob.download_as_text())
        return JsonResponse(template_data)
    except:
        return JsonResponse({'error': 'Template not found'}, status=404)

@csrf_exempt
@require_http_methods(["GET"])
def fuze_get_background(request, background_id):
    from django.http import HttpResponse
    if not re.match(r'^[a-zA-Z0-9_-]+$', background_id):
        return JsonResponse({'error': 'Invalid background ID'}, status=400)
    try:
        client = storage.Client()
        bucket = client.bucket('bomby-user-uploads')
        blob = bucket.blob(f'fuze-templates/scene-backgrounds/{background_id}.png')
        image_data = blob.download_as_bytes()
        return HttpResponse(image_data, content_type='image/png')
    except:
        return JsonResponse({'error': 'Background not found'}, status=404)

# ===== AI CHAT =====

@csrf_exempt
def fuze_ai_chat(request):
    """AI chat streaming endpoint with tier-based rate limiting and file upload"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    # Get user from token (allow anonymous)
    auth_header = request.headers.get('Authorization', '')
    user = None
    tier = 'free'
    
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        user = get_user_from_token(token)
        if user:
            tier = user.fuze_tier or 'free'
            user_id = f'user_{user.id}'
        else:
            user_id = f'anon_{get_client_ip(request)}'
    else:
        user_id = f'anon_{get_client_ip(request)}'
    today = date.today().isoformat()
    daily_key = f'fuze_daily_{user_id}_{today}'
    daily_count = cache.get(daily_key, 0)
    
    # Tier limits
    if tier in ['pro', 'lifetime']:
        rate_key = f'fuze_pro_rate_{user_id}'
        rate_count = cache.get(rate_key, 0)
        
        if rate_count >= 100:
            def limit_msg():
                message_data = {'text': '[Rate Limit Reached]\n\nYou\'ve used 100 messages in 5 hours. Please wait before sending more.'}
                yield "data: " + json.dumps(message_data) + "\n\n"
                yield "data: [DONE]\n\n"
            response = StreamingHttpResponse(limit_msg(), content_type='text/event-stream; charset=utf-8')
            response['Cache-Control'] = 'no-cache'            
            return response
        
        cache.set(rate_key, rate_count + 1, 18000)
        model = "claude-sonnet-4-5-20250929"
        
    else:  # free tier
        if daily_count >= 5:
            def limit_msg():
                message_data = {'text': '[Daily Limit Reached]\n\nYou\'ve used your 5 free messages today. Upgrade to Pro / Lifetime for unlimited access.'}
                yield "data: " + json.dumps(message_data) + "\n\n"
                yield "data: [DONE]\n\n"
            response = StreamingHttpResponse(limit_msg(), content_type='text/event-stream; charset=utf-8')
            response['Cache-Control'] = 'no-cache'            
            return response
        
        cache.set(daily_key, daily_count + 1, 86400)
        model = "claude-haiku-4-5-20251001"
    
    # Anti-spam: 10 messages per minute
    spam_key = f'fuze_spam_{user_id}'
    spam_count = cache.get(spam_key, 0)
    if spam_count >= 10:
        def spam_msg():
            message_data = {'text': '[Please wait a moment]\n\nMaximum 10 messages per minute.'}
            yield "data: " + json.dumps(message_data) + "\n\n"
            yield "data: [DONE]\n\n"
        response = StreamingHttpResponse(spam_msg(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache'        
        return response
    cache.set(spam_key, spam_count + 1, 60)
    
    # Handle both JSON and FormData
    import base64
    
    if request.content_type and 'multipart/form-data' in request.content_type:
        files = request.FILES.getlist('files')[:5]
        message = request.POST.get('message', '').strip()
        style = request.POST.get('style', 'normal')
        history = json.loads(request.POST.get('history', '[]'))
    else:
        files = []
        data = json.loads(request.body)
        message = data.get('message', '').strip()
        style = data.get('style', 'normal')
        history = data.get('history', [])
    
    # Sanitize history — validate roles, strip internal retry messages
    # Retry messages (from client retry button or auto-retry) pollute context
    # and cause the AI to confuse old requests with new ones
    history = [
        {"role": h["role"], "content": h["content"]}
        for h in (history or [])[:20]
        if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content")
        and not str(h.get("content", "")).startswith("[RETRY AS OBS COMMAND]")
        and not str(h.get("content", "")).startswith("[AUTO-RETRY:")
    ]
    
    # ── Repeated-complaint detection ──
    # If the user's last 2+ messages show the same unresolved issue,
    # inject a system-level nudge so the AI doesn't loop.
    _STUCK_PHRASES = frozenset([
        'still lagging', 'still lag', 'still dropping', 'still stuttering',
        'still not working', 'still broken', 'still the same', 'same issue',
        'same problem', 'didnt help', "didn't help", 'not fixed', 'still happens',
        'still occurring', 'still there', 'nothing changed', 'no difference',
    ])
    
    repeat_nudge = ""
    if history and message:
        ml = message.lower()
        if any(phrase in ml for phrase in _STUCK_PHRASES):
            recent_user_msgs = [h['content'].lower() for h in history if h['role'] == 'user'][-4:]
            stuck_count = sum(1 for m in recent_user_msgs if any(p in m for p in _STUCK_PHRASES))
            if stuck_count >= 1:
                repeat_nudge = (
                    "\n\n[SYSTEM NOTE: The user has reported this same issue multiple times. "
                    "Your previous suggestions did NOT fix it. Do NOT repeat the same advice. "
                    "Escalate to the next possible cause. Ask diagnostic questions if needed.]"
                )
    
    if not message and not files:
        return JsonResponse({'error': 'Empty message'}, status=400)
    
    if message:
        off_topic_keywords = [
            'homework', 'essay', 'assignment', 'math problem', 'solve for', 
            'write code', 'python script', 'javascript function', 'sql query',
            'history of', 'who was', 'biography', 'recipe', 'medical advice'
        ]
        
        if any(keyword in message.lower() for keyword in off_topic_keywords):
            def off_topic_message():
                message_data = {'text': '**Off-Topic Query Detected**\n\nThis AI assistant is specifically designed for OBS Studio and streaming questions only.'}
                yield "data: " + json.dumps(message_data) + "\n\n"
                yield "data: [DONE]\n\n"
            
            response = StreamingHttpResponse(off_topic_message(), content_type='text/event-stream; charset=utf-8')
            response['Cache-Control'] = 'no-cache'            
            return response
    
    client = _anthropic_client
    
    # Fetch platform data for logged-in users (cached, fast)
    platform_context = ""
    if user:
        try:
            from .recaps import _fetch_all_recaps, FOLLOWER_FETCHERS
            
            connections = PlatformConnection.objects.filter(user=user)
            connected = [c.platform for c in connections]
            
            if connected:
                parts = [f"Connected platforms: {', '.join(connected)}"]
                
                # Follower counts (cached 5 min)
                follower_cache_key = f'followers:{user.id}'
                follower_data = cache.get(follower_cache_key)
                if not follower_data:
                    followers = {}
                    total = 0
                    for conn in connections:
                        fetcher = FOLLOWER_FETCHERS.get(conn.platform)
                        if fetcher:
                            try:
                                count = fetcher(conn)
                                followers[conn.platform] = count
                                total += count
                            except Exception:
                                followers[conn.platform] = 0
                    follower_data = {'total': total, 'platforms': followers}
                    cache.set(follower_cache_key, follower_data, 300)
                
                if follower_data.get('platforms'):
                    follower_parts = [f"{p}: {c}" for p, c in follower_data['platforms'].items() if c > 0]
                    if follower_parts:
                        parts.append(f"Follower counts — {', '.join(follower_parts)} (Total: {follower_data['total']})")
                
                # Recent streams (cached 5 min)
                recap_cache_key = f'recaps:{user.id}'
                recaps = cache.get(recap_cache_key)
                if recaps is None:
                    try:
                        recaps = _fetch_all_recaps(user)
                        cache.set(recap_cache_key, recaps, 300)
                    except Exception:
                        recaps = []
                
                if recaps:
                    parts.append("Recent streams:")
                    for r in recaps[:5]:
                        line = f"  - [{r.get('platform','?').upper()}] \"{r.get('title','Untitled')}\" — {r.get('duration','?')}"
                        if r.get('views'):
                            line += f", {r['views']} views"
                        if r.get('peak_viewers'):
                            line += f", peak {r['peak_viewers']} viewers"
                        if r.get('category'):
                            line += f", category: {r['category']}"
                        if r.get('date'):
                            line += f" ({r['date'][:10]})"
                        parts.append(line)
                
                platform_context = "\n".join(parts)
        except Exception as e:
            print(f"[AI] Platform data fetch error: {e}")
            platform_context = ""
    
    start_time = time.time()
    input_tokens = 0
    output_tokens = 0
    success = True
    error_msg = ""
    
    def _extract_obs_actions(text):
        """Server-side OBS action parser — no reliance on AI formatting order."""
        actions = []
        TAG = '[OBS_ACTION:'
        offset = 0
        while True:
            tag_start = text.find(TAG, offset)
            if tag_start == -1:
                break
            json_start = tag_start + len(TAG)
            depth = 0
            json_end = -1
            for i in range(json_start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        json_end = i + 1
                        break
            if json_end == -1 or json_end >= len(text) or text[json_end] != ']':
                offset = json_start
                continue
            try:
                action = json.loads(text[json_start:json_end])
                if action.get('params') and len(action['params']) > 0 and action.get('command'):
                    actions.append(action)
            except Exception:
                pass
            offset = json_end + 1
        return actions

    def generate():
        nonlocal input_tokens, output_tokens, success, error_msg
        try:
            content = []
            
            for file in files:
                ext = file.name.lower().split('.')[-1]
                if ext in ['jpg', 'jpeg', 'png']:
                    encoded = base64.b64encode(file.read()).decode('utf-8')
                    content.append({
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': f'image/{"jpeg" if ext == "jpg" else ext}',
                            'data': encoded
                        }
                    })
                elif ext == 'json':
                    file_content = file.read().decode('utf-8')
                    content.append({
                        'type': 'text',
                        'text': f"[Uploaded file: {file.name}]\n```json\n{file_content}\n```"
                    })
            
            if message:
                final_message = message + repeat_nudge if repeat_nudge else message
                content.append({'type': 'text', 'text': final_message})
            
            messages_content = content if files else (message + repeat_nudge if repeat_nudge else message)
            
            style_instructions = {
                'normal': '- Start with a direct answer\n- Provide exact settings when applicable',
                'concise': '- Be extremely brief\n- Only essential information',
                'explanatory': '- Detailed step-by-step\n- Include background context',
                'formal': '- Professional technical language\n- Structured format',
                'learning': '- Break down for beginners\n- Use analogies',
                'sassy': '- Be playfully sassy and sarcastic - eye rolls, dramatic sighs, witty comebacks\n- Use phrases like "Oh honey...", "Bless your heart", "Let me spell it out..."\n- Roast common mistakes gently\n- Still provide the correct, helpful answer after the sass'
            }
            
            style_prompt = style_instructions.get(style, style_instructions['normal'])
            
            # Build multi-turn messages from history
            api_messages = []
            for i, h in enumerate(history):
                msg_content = h["content"]
                # Cache breakpoint on last history message for multi-turn caching
                if i == len(history) - 1:
                    msg_content = [{"type": "text", "text": h["content"], "cache_control": {"type": "ephemeral"}}]
                api_messages.append({"role": h["role"], "content": msg_content})
            
            # Add current user message
            api_messages.append({"role": "user", "content": messages_content})
            
            full_response_text = ''
            _sys_prompt, had_action_context = _build_system_prompt(message or "", return_context_flag=True)
            with client.messages.stream(
                model=model,
                max_tokens=8192,
                system=_sys_prompt + ([{
                    "type": "text",
                    "text": f"This user's streaming data (use to personalize advice):\n{platform_context}"
                }] if platform_context else []),
                messages=api_messages
            ) as stream:
                for text in stream.text_stream:
                    full_response_text += text
                    yield f"data: {json.dumps({'text': text})}\n\n"
                
                final_message = stream.get_final_message()
                input_tokens = final_message.usage.input_tokens
                output_tokens = final_message.usage.output_tokens
                cache_read = getattr(final_message.usage, 'cache_read_input_tokens', 0)
                cache_create = getattr(final_message.usage, 'cache_creation_input_tokens', 0)
                logger.info(f"AI Cache: read={cache_read}, create={cache_create}, uncached={input_tokens}")
            
            # Server-side OBS action parsing — reliable regardless of AI tag placement order
            obs_actions = _extract_obs_actions(full_response_text)
            logger.info(f'[AI Chat] Response length={len(full_response_text)}, OBS actions found={len(obs_actions)}, commands={[a.get("command") for a in obs_actions]}')
            if not obs_actions and '[OBS_ACTION' in full_response_text:
                # AI tried to emit tags but parser couldn't extract them — log the raw text around the tag
                tag_start = full_response_text.find('[OBS_ACTION')
                snippet = full_response_text[max(0, tag_start - 20):tag_start + 200]
                logger.warning(f'[AI Chat] OBS_ACTION tag found in text but parser failed to extract! Snippet: {snippet}')
            # Skip retries when user hasn't scanned or has no device data
            # Frontend sends "No hardware scan available" when systemSpecs is null,
            # and "NONE DETECTED" per device type when scan exists but found no devices
            no_scan = 'No hardware scan available' in (message or '') or 'NONE DETECTED' in (message or '')

            # Silent auto-retry: if action keywords were in the message but model emitted no tags,
            # make a second fast non-streaming call with assistant prefill to force tag output.
            # User never sees this - Apply button just appears correctly instead of orange retry.
            if not obs_actions and had_action_context and not no_scan:
                logger.info('[AI Chat] No tags emitted despite action context - running silent tag-extraction retry')
                try:
                    retry_messages = list(api_messages) + [
                        {"role": "assistant", "content": full_response_text},
                        {"role": "user", "content": (
                            "You described the action above but did NOT emit any [OBS_ACTION:...] tags. "
                            "Now emit ONLY the required [OBS_ACTION:...] tags for everything you described - no explanation, just the tags."
                        )},
                        {"role": "assistant", "content": "[OBS_ACTION:"},
                    ]
                    retry_resp = client.messages.create(
                        model=model,
                        max_tokens=1024,
                        system=_sys_prompt,
                        messages=retry_messages,
                    )
                    retry_text = "[OBS_ACTION:" + (retry_resp.content[0].text if retry_resp.content else "")
                    retry_actions = _extract_obs_actions(retry_text)
                    if retry_actions:
                        obs_actions = retry_actions
                        input_tokens += retry_resp.usage.input_tokens
                        output_tokens += retry_resp.usage.output_tokens
                        logger.info(f'[AI Chat] Silent retry succeeded: {[a.get("command") for a in obs_actions]}')
                    else:
                        logger.warning(f'[AI Chat] Silent retry also produced no tags. Text: {retry_text[:200]}')
                except Exception as retry_err:
                    logger.warning(f'[AI Chat] Silent retry failed: {retry_err}')

            if obs_actions:
                # Count-mismatch retry: user asked for N devices but AI only emitted fewer tags
                # This catches the "add webcam and speakers" → only 1 CreateInput tag bug
                # SKIP if user hasn't scanned — no device IDs to work with
                if not no_scan:
                    try:
                        # Extract just the user's actual message (after context blocks)
                        # Context is prepended as [SYSTEM CONTEXT...]\n\n[OBS CONTEXT...]\n\n{user text}
                        raw_parts = (message or '').split('\n\n')
                        user_text = raw_parts[-1].lower() if raw_parts else ''
                        device_mentions = 0
                        if any(w in user_text for w in ('webcam', 'camera', 'cam')):
                            device_mentions += 1
                        if any(w in user_text for w in ('microphone', 'mic ', 'mic,', ' mic')):
                            device_mentions += 1
                        if any(w in user_text for w in ('speaker', 'speakers', 'desktop audio', 'audio output')):
                            device_mentions += 1
                        
                        create_input_count = sum(1 for a in obs_actions if a.get('command') == 'CreateInput')
                        
                        if device_mentions >= 2 and create_input_count < device_mentions:
                            logger.info(f'[AI Chat] Device count mismatch: {device_mentions} requested, {create_input_count} tags. Running mismatch retry.')
                            existing_kinds = [a.get('params', {}).get('input_kind', '') for a in obs_actions if a.get('command') == 'CreateInput']
                            retry_messages = list(api_messages) + [
                                {"role": "assistant", "content": full_response_text},
                                {"role": "user", "content": (
                                    f"You only emitted {create_input_count} CreateInput tag(s) but the user asked for {device_mentions} devices. "
                                    f"Already emitted input_kinds: {existing_kinds}. "
                                    "Now emit ONLY the MISSING [OBS_ACTION:...] CreateInput tags for the devices you forgot — no explanation, just the tags."
                                )},
                                {"role": "assistant", "content": "[OBS_ACTION:"},
                            ]
                            retry_resp = client.messages.create(
                                model=model,
                                max_tokens=1024,
                                system=_sys_prompt,
                                messages=retry_messages,
                            )
                            retry_text = "[OBS_ACTION:" + (retry_resp.content[0].text if retry_resp.content else "")
                            retry_actions = _extract_obs_actions(retry_text)
                            if retry_actions:
                                obs_actions.extend(retry_actions)
                                input_tokens += retry_resp.usage.input_tokens
                                output_tokens += retry_resp.usage.output_tokens
                                logger.info(f'[AI Chat] Device mismatch retry added {len(retry_actions)} tags: {[a.get("command") for a in retry_actions]}')
                    except Exception as count_err:
                        logger.warning(f'[AI Chat] Device count retry failed: {count_err}')

                yield f"data: {json.dumps({'obs_actions': obs_actions})}\n\n"
            
            yield "data: [DONE]\n\n" 
        except Exception as e:
            success = False
            error_msg = str(e)
            print(f"AI Error: {e}")
            yield f"data: {json.dumps({'text': 'Error processing request.'})}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            response_time = time.time() - start_time
            total_tokens = input_tokens + output_tokens
            
            if model == "claude-sonnet-4-20250514":
                cost = (input_tokens / 1_000_000 * 3) + (output_tokens / 1_000_000 * 15)
            else:  # haiku
                cost = (input_tokens / 1_000_000 * 1) + (output_tokens / 1_000_000 * 5)
            
            # Track all AI usage (both logged-in and anonymous)
            AIUsage.objects.create(
                user=user,
                user_tier=tier,
                is_anonymous=(user is None),
                tokens_used=total_tokens,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost=cost,
                request_type='chat',
                response_time=response_time,
                success=success,
                error_message=error_msg
            )
    
    response = StreamingHttpResponse(generate(), content_type='text/event-stream; charset=utf-8')
    response['Cache-Control'] = 'no-cache'    
    return response

# ===== CHAT HISTORY =====

@csrf_exempt
@require_tier('free')
def fuze_save_chat(request):
    """Save chat for logged-in users only"""
    if request.method == 'OPTIONS':
        response = JsonResponse({})
    elif request.method != 'POST':
        response = JsonResponse({'error': 'POST only'}, status=405)
    else:
        user = request.fuze_user
        data = json.loads(request.body)
        chat_data = data.get('chat')
        
        if not chat_data or not isinstance(chat_data, dict):
            response = JsonResponse({'error': 'Invalid chat data'}, status=400)
        else:
            chat_history = list(user.fuze_chat_history)
            
            # Normalize existing chats
            normalized_history = []
            for item in chat_history:
                if isinstance(item, dict):
                    if 'chat' in item and isinstance(item['chat'], dict) and 'id' in item['chat']:
                        normalized_history.append(item['chat'])
                    elif 'id' in item:
                        normalized_history.append(item)
            
            existing_index = next((i for i, c in enumerate(normalized_history) if c.get('id') == chat_data.get('id')), None)
            
            if existing_index is not None:
                normalized_history[existing_index] = chat_data
            else:
                normalized_history.append(chat_data)
            
            user.fuze_chat_history = sorted(
                normalized_history,
                key=lambda x: x.get('updated_at', 0),
                reverse=True
            )[:10]
            
            user.save()
            response = JsonResponse({'success': True})    
            return response

@csrf_exempt
@require_tier('free')
def fuze_get_chats(request):
    """Get all chats for logged-in users only"""
    if request.method != 'GET':
        response = JsonResponse({'error': 'GET only'}, status=405)
    else:
        user = request.fuze_user
        chats = user.fuze_chat_history if user.fuze_chat_history else []
        response = JsonResponse({'chats': chats})    
        return response

@csrf_exempt
@require_tier('free')
def fuze_delete_chat(request):
    """Delete specific chat for logged-in users only"""
    if request.method != 'POST':
        response = JsonResponse({'error': 'POST only'}, status=405)
    else:
        user = request.fuze_user
        data = json.loads(request.body)
        chat_id = data.get('chatId')
        
        if hasattr(user, 'fuze_chat_history'):
            user.fuze_chat_history = [
                c for c in user.fuze_chat_history 
                if c.get("id") != chat_id
            ]
            user.save()
        
        response = JsonResponse({'success': True})    
        return response

@csrf_exempt
@require_tier('free')
def fuze_clear_chats(request):
    """Clear all chats for logged-in users only"""
    if request.method != 'POST':
        response = JsonResponse({'error': 'POST only'}, status=405)
    else:
        user = request.fuze_user
        user.fuze_chat_history = []
        user.save()
        response = JsonResponse({'success': True})    
        return response

# ===== BENCHMARKING (PRO / LIFETIME ONLY) =====

@csrf_exempt
@require_tier('pro')
def fuze_analyze_benchmark(request):
    """Analyze benchmark results with AI - PRO ONLY"""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=405)
    
    user = request.fuze_user
    data = json.loads(request.body)
    benchmark_data = data.get('benchmark_data', '').strip()
    
    if not benchmark_data:
        return JsonResponse({'error': 'No benchmark data'}, status=400)
    
    client = _anthropic_client
    model = "claude-sonnet-4-20250514"
    
    def generate():
        try:
            with client.messages.stream(
                model=model,
                max_tokens=6000,
                system="""You are the Fuze Performance Analysis Expert. Analyze benchmark results and provide:

1. **Performance Summary** - Brief overview
2. **Critical Issues** - Severe problems (if any)
3. **Detailed Analysis** - CPU, GPU, Network, Frame Drops
4. **Recommended Actions** - Numbered priority list with exact settings
5. **Advanced Optimizations** - Fine-tuning for good streams

Always provide EXACT settings (bitrate numbers, preset names). Explain WHY each change helps. Consider their specific hardware.""",
                messages=[{"role": "user", "content": f"Analyze this streaming benchmark:\n\n{benchmark_data}"}]
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            print(f"AI Error: {e}")
            yield "data: [ERROR] Failed to analyze.\n\n"
    
    response = StreamingHttpResponse(generate(), content_type='text/event-stream; charset=utf-8')
    response['Cache-Control'] = 'no-cache'    
    return response

# ===== PROFILES =====

@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuze_get_profiles(request):
    user = request.fuze_user
    profiles = FuzeProfile.objects.filter(user=user)
    return JsonResponse({
        'profiles': [{
            'id': p.id,
            'name': p.name,
            'config': p.config,
            'created_at': p.created_at.isoformat(),
            'updated_at': p.updated_at.isoformat()
        } for p in profiles]
    })

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuze_create_profile(request):
    user = request.fuze_user
    try:
        data = json.loads(request.body)
        profile = FuzeProfile.objects.create(
            user=user,
            name=data['name'],
            config=data['config']
        )
        return JsonResponse({'success': True, 'id': profile.id})
    except Exception as e:
        logger.error(f'Request error: {e}'); return JsonResponse({'success': False, 'error': 'Bad request'}, status=400)

@csrf_exempt
@require_http_methods(["DELETE"])
@require_tier('free')
def fuze_delete_profile(request, profile_id):
    user = request.fuze_user
    try:
        profile = FuzeProfile.objects.get(id=profile_id, user=user)
        profile.delete()
        return JsonResponse({'success': True})
    except FuzeProfile.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

@csrf_exempt
@require_http_methods(["PUT"])
@require_tier('free')
def fuze_update_profile(request, profile_id):
    user = request.fuze_user
    try:
        profile = FuzeProfile.objects.get(id=profile_id, user=user)
        data = json.loads(request.body)
        profile.name = data.get('name', profile.name)
        profile.config = data.get('config', profile.config)
        profile.save()
        return JsonResponse({'success': True})
    except FuzeProfile.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)
    
# ====== WEBSITE VIEWS =======
def fuze_view(request):
    # Track page view
    from .models import FuzePageView, FuzeReview
    try:
        session_id = request.session.session_key or ''
        if not session_id:
            request.session.create()
            session_id = request.session.session_key
        FuzePageView.objects.create(
            page='landing',
            session_id=session_id,
            user=request.user if request.user.is_authenticated else None
        )
    except:
        pass
    
    # Get featured reviews
    featured_reviews = FuzeReview.objects.filter(featured=True).select_related('user')[:20]
    
    return render(request, 'FUZE/fuze.html', {
        'fuze_version': FUZE_VERSION,
        'featured_reviews': featured_reviews,
    })

def fuze_download_windows(request):
    DownloadTracking.objects.create(
        platform='windows',
        version='0.9.4',
        user=request.user if request.user.is_authenticated else None,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    return redirect('https://storage.googleapis.com/fuze-public/fuze-installer/Fuze-Installer.exe')

def fuze_download_mac(request):
    DownloadTracking.objects.create(
        platform='mac',
        version='0.9.4',
        user=request.user if request.user.is_authenticated else None,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    return redirect('https://storage.googleapis.com/fuze-public/fuze-installer/Fuze-Installer.dmg')

def fuze_download_linux(request):
    DownloadTracking.objects.create(
        platform='linux',
        version='0.9.4',
        user=request.user if request.user.is_authenticated else None,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    return redirect('https://storage.googleapis.com/fuze-public/fuze-installer/Fuze-Installer.deb')

def fuze_install_guide(request):
    return render(request, 'FUZE/fuze_installation_guide.html', {
        'fuze_version': FUZE_VERSION,
    })

def fuze_roadmap(request):
    return render(request, 'FUZE/fuze_roadmap.html', {
        'fuze_version': FUZE_VERSION,
        'patch_notes': FUZE_PATCH_NOTES,
    })

# ====== PRICING & PAYMENT VIEWS =======
FUZE_PLANS = {
    'pro': {
        'name': 'Pro',
        'price': '7.50',
        'stripe_price_id': settings.FUZE_STRIPE_PRICE_MONTHLY,
        'mode': 'subscription',
    },
    '3month': {
        'name': 'Pro (3-Month)',
        'price': '20.00',
        'stripe_price_id': settings.FUZE_STRIPE_PRICE_3MONTH,
        'mode': 'payment',
    },
    'lifetime': {
        'name': 'Lifetime',
        'price': '45.00',
        'stripe_price_id': settings.FUZE_STRIPE_PRICE_LIFETIME,
        'mode': 'payment',
    },
}

def fuze_pricing(request):
    # Track page view
    from .models import FuzePageView
    try:
        session_id = request.session.session_key or ''
        if not session_id:
            request.session.create()
            session_id = request.session.session_key
        FuzePageView.objects.create(
            page='pricing',
            session_id=session_id,
            user=request.user if request.user.is_authenticated else None
        )
    except:
        pass
    
    current_plan = 'free'
    if request.user.is_authenticated:
        current_plan = request.user.fuze_tier or 'free'
    return render(request, 'FUZE/fuze_pricing.html', {'current_plan': current_plan})

@login_required
def fuze_payment(request, plan_type):
    if plan_type not in FUZE_PLANS:
        return redirect('FUZE:pricing')
    
    current_plan = request.user.fuze_tier or 'free'
    
    # Block invalid purchases
    if current_plan == 'lifetime':
        messages.info(request, "You already have Lifetime access!")
        return redirect('FUZE:pricing')
    if current_plan == 'pro' and plan_type == 'pro':
        messages.info(request, "You already have Pro! Consider upgrading to Lifetime.")
        return redirect('FUZE:pricing')
    
    plan = FUZE_PLANS[plan_type]
    return render(request, 'FUZE/fuze_payment.html', {
        'plan_type': plan_type,
        'plan_name': plan['name'],
        'price': plan['price'],
        'stripe_publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
    })

@login_required
@require_POST
def fuze_create_checkout_session(request):
    try:
        data = json.loads(request.body)
        plan_type = data.get('plan_type')

        if plan_type not in FUZE_PLANS:
            return JsonResponse({'error': 'Invalid plan'}, status=400)

        plan = FUZE_PLANS[plan_type]
        return_url = request.build_absolute_uri('/fuze/payment/success/') + '?session_id={CHECKOUT_SESSION_ID}'

        # Validate creator code if provided
        creator_code_str = data.get('creator_code', '').strip().upper()
        valid_code = None
        if creator_code_str:
            from .models import CreatorCode
            try:
                valid_code = CreatorCode.objects.get(code=creator_code_str, is_active=True)
            except CreatorCode.DoesNotExist:
                pass

        metadata = {
            'user_id': str(request.user.id),
            'plan_type': plan_type,
            'product': 'fuze',
        }
        if valid_code:
            metadata['creator_code'] = valid_code.code

        session = stripe.checkout.Session.create(
            ui_mode='embedded',
            customer_email=request.user.email,
            line_items=[{'price': plan['stripe_price_id'], 'quantity': 1}],
            mode=plan['mode'],
            return_url=return_url,
            redirect_on_completion='if_required',
            metadata=metadata
        )

        return JsonResponse({'clientSecret': session.client_secret, 'sessionId': session.id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f'Server error: {e}')
        return JsonResponse({'error': 'Internal error'}, status=500)
    
@login_required
def fuze_payment_success(request):
    session_id = request.GET.get('session_id')
    
    if not session_id:
        messages.error(request, "Invalid payment session.")
        return redirect('FUZE:pricing')
    
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        
        is_complete = session.status == 'complete' or session.payment_status == 'paid'
        
        if not is_complete:
            messages.error(request, "Payment not completed.")
            return redirect('FUZE:pricing')
        
        plan_type = session.metadata.get('plan_type', 'pro')
        user_id = session.metadata.get('user_id')
        plan = FUZE_PLANS.get(plan_type, FUZE_PLANS['pro'])
        
        # Verify the logged-in user matches the payment user
        if str(request.user.id) != str(user_id):
            messages.error(request, "Payment session mismatch.")
            return redirect('FUZE:pricing')
        
        # Check if already processed (prevent duplicates)
        existing_purchase = FuzePurchase.objects.filter(payment_id=session_id).first()
        if existing_purchase:
            return render(request, 'FUZE/fuze_payment_success.html', {
                'plan_type': plan_type,
                'plan_name': plan['name'],
                'purchase': existing_purchase
            })
        
        try:
            user = User.objects.get(id=user_id)
            old_tier = user.fuze_tier
            user.fuze_tier = 'lifetime' if plan_type == 'lifetime' else 'pro'
            
            try:
                user.promote_to_supporter()
            except Exception as e:
                print(f"[FUZE] promote_to_supporter failed: {e}")
            
            # Activate as Fuze user (counts in total users)
            activate_fuze_user(user)
            user.save()
            
            # Cancel existing Pro subscription if upgrading to Lifetime
            if plan_type == 'lifetime':
                try:
                    existing_sub = FuzeSubscription.objects.get(user=user, is_active=True)
                    if existing_sub.stripe_subscription_id:
                        stripe.Subscription.cancel(existing_sub.stripe_subscription_id)
                    existing_sub.is_active = False
                    existing_sub.plan_type = 'lifetime'
                    existing_sub.save()
                except FuzeSubscription.DoesNotExist:
                    pass
            
            TierChange.objects.create(
                user=user,
                from_tier=old_tier,
                to_tier=user.fuze_tier,
                reason='stripe_purchase'
            )
            
            purchase = FuzePurchase.objects.create(
                user=user,
                plan_type=plan_type,
                amount=Decimal(plan['price']),
                payment_id=session_id,
                is_paid=True
            )
            
            # Send invoice email
            try:
                send_fuze_invoice_email(request, user, purchase, plan_type)
            except Exception as e:
                print(f"Failed to send invoice email: {e}")
            
            # Save subscription info for Pro plans
            if plan_type == 'pro' and session.subscription:
                FuzeSubscription.objects.update_or_create(
                    user=user,
                    defaults={
                        'plan_type': 'pro',
                        'stripe_customer_id': session.customer,
                        'stripe_subscription_id': session.subscription,
                        'is_active': True
                    }
                )
            
            # Save 3-month plan with expiration
            if plan_type == '3month':
                from datetime import timedelta
                FuzeSubscription.objects.update_or_create(
                    user=user,
                    defaults={
                        'plan_type': 'pro',
                        'stripe_customer_id': session.customer or '',
                        'stripe_subscription_id': '',
                        'is_active': True,
                        'expires_at': timezone.now() + timedelta(days=90),
                    }
                )
        except User.DoesNotExist:
            pass
        
        return render(request, 'FUZE/fuze_payment_success.html', {
            'plan_type': plan_type,
            'plan_name': plan['name'],
            'purchase': {
                'created_at': timezone.now(),
                'amount': plan['price'],
            }
        })
        
    except stripe.error.StripeError:
        messages.error(request, "Payment verification failed.")
        return redirect('FUZE:pricing')

@csrf_exempt
@require_POST
def fuze_stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return JsonResponse({'error': 'Invalid signature'}, status=400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        metadata = session.get('metadata', {})
        payment_id = session.get('payment_intent') or session.get('id')

        # === FUZE PURCHASES ===
        if metadata.get('product') == 'fuze':
            user_id = metadata.get('user_id')
            plan_type = metadata.get('plan_type')

            if FuzePurchase.objects.filter(payment_id=payment_id).exists():
                return JsonResponse({'status': 'already_processed'})

            try:
                user = User.objects.get(id=user_id)
                old_tier = user.fuze_tier
                user.fuze_tier = 'lifetime' if plan_type == 'lifetime' else 'pro'

                try:
                    user.promote_to_supporter()
                except Exception as e:
                    print(f"[FUZE] promote_to_supporter failed: {e}")

                activate_fuze_user(user)
                user.save()

                if plan_type == 'lifetime':
                    try:
                        existing_sub = FuzeSubscription.objects.get(user=user, is_active=True)
                        if existing_sub.stripe_subscription_id:
                            stripe.Subscription.cancel(existing_sub.stripe_subscription_id)
                        existing_sub.is_active = False
                        existing_sub.plan_type = 'lifetime'
                        existing_sub.save()
                    except FuzeSubscription.DoesNotExist:
                        pass

                TierChange.objects.create(
                    user=user,
                    from_tier=old_tier,
                    to_tier=user.fuze_tier,
                    reason='stripe_webhook'
                )

                amount = Decimal(FUZE_PLANS.get(plan_type, {}).get('price', '7.50'))
                purchase = FuzePurchase.objects.create(
                    user=user,
                    plan_type=plan_type,
                    amount=amount,
                    payment_id=payment_id,
                    is_paid=True
                )

                try:
                    send_fuze_invoice_email(request, user, purchase, plan_type)
                except Exception as e:
                    print(f'[FUZE] Invoice email failed: {e}')

                if plan_type == 'pro' and session.get('subscription'):
                    FuzeSubscription.objects.update_or_create(
                        user=user,
                        defaults={
                            'plan_type': 'pro',
                            'stripe_customer_id': session.get('customer'),
                            'stripe_subscription_id': session.get('subscription'),
                            'is_active': True
                        }
                    )

                if plan_type == '3month':
                    from datetime import timedelta
                    FuzeSubscription.objects.update_or_create(
                        user=user,
                        defaults={
                            'plan_type': 'pro',
                            'stripe_customer_id': session.get('customer', ''),
                            'stripe_subscription_id': '',
                            'is_active': True,
                            'expires_at': timezone.now() + timedelta(days=90),
                        }
                    )

                # === CREATOR CODE USAGE ===
                creator_code_str = metadata.get('creator_code', '')
                if creator_code_str:
                    from .models import CreatorCode, CreatorCodeUsage
                    EARNINGS = {
                        'pro':      Decimal('2.50'),
                        '3month':   Decimal('6.00'),
                        'lifetime': Decimal('9.00'),
                    }
                    AMOUNTS = {
                        'pro':      Decimal('7.50'),
                        '3month':   Decimal('20.00'),
                        'lifetime': Decimal('45.00'),
                    }
                    try:
                        code_obj = CreatorCode.objects.get(code=creator_code_str, is_active=True)
                        CreatorCodeUsage.objects.get_or_create(
                            stripe_session_id=session['id'],
                            defaults={
                                'code': code_obj,
                                'user': user,
                                'plan_type': plan_type,
                                'order_amount': AMOUNTS.get(plan_type, Decimal('0')),
                                'creator_earnings': EARNINGS.get(plan_type, Decimal('0')),
                            }
                        )
                    except CreatorCode.DoesNotExist:
                        pass

            except User.DoesNotExist:
                pass

        # === STORE PRODUCT PURCHASES ===
        elif metadata.get('type') == 'product':
            from STORE.models import Order, Product
            product_id = metadata.get('product_id')
            user_id = metadata.get('user_id')

            if product_id and user_id and payment_id:
                if not Order.objects.filter(payment_id=payment_id).exists():
                    try:
                        user = User.objects.get(id=user_id)
                        product = Product.objects.get(id=product_id)

                        status = 'completed' if int(product_id) == 4 else 'pending'
                        Order.objects.create(
                            user=user,
                            product=product,
                            status=status,
                            payment_id=payment_id,
                            is_paid=True
                        )
                    except Exception as e:
                        print(f"[STORE] Webhook order creation error: {e}")

        # === STORE DONATIONS ===
        elif metadata.get('type') == 'donation':
            from STORE.models import Donation
            amount = metadata.get('amount')
            user_id = metadata.get('user_id')

            if amount and payment_id:
                if not Donation.objects.filter(payment_id=payment_id).exists():
                    try:
                        donation = Donation.objects.create(
                            amount=amount,
                            payment_id=payment_id,
                            is_paid=True
                        )
                        if user_id:
                            donation.user = User.objects.get(id=user_id)
                            donation.save()
                    except Exception as e:
                        print(f"[STORE] Donation webhook error: {e}")

    return JsonResponse({'status': 'ok'})

@login_required
def fuze_manage_subscription(request):
    """Subscription management page"""
    try:
        sub = FuzeSubscription.objects.get(user=request.user)
        # Get subscription details from Stripe if active
        stripe_sub = None
        if sub.stripe_subscription_id and sub.is_active:
            try:
                stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
            except:
                pass
        
        return render(request, 'FUZE/fuze_manage_subscription.html', {
            'subscription': sub,
            'stripe_sub': stripe_sub,
            'cancel_at_period_end': stripe_sub.cancel_at_period_end if stripe_sub else False,
            'current_period_end': stripe_sub.current_period_end if stripe_sub else None,
        })
    except FuzeSubscription.DoesNotExist:
        messages.error(request, "No subscription found.")
        return redirect('ACCOUNTS:purchase_history')

@login_required
@require_POST
def fuze_cancel_subscription(request):
    """Cancel user's Pro subscription"""
    try:
        sub = FuzeSubscription.objects.get(user=request.user, is_active=True)
        if sub.stripe_subscription_id:
            # Cancel at period end (user keeps access until billing cycle ends)
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                cancel_at_period_end=True
            )
            messages.success(request, "Your subscription will cancel at the end of your billing period. You'll keep Pro access until then.")
        else:
            messages.error(request, "No active subscription found.")
    except FuzeSubscription.DoesNotExist:
        messages.error(request, "No active subscription found.")
    
    return redirect('FUZE:manage_subscription')

@login_required
@require_POST
def fuze_reactivate_subscription(request):
    """Reactivate a cancelled subscription"""
    try:
        sub = FuzeSubscription.objects.get(user=request.user, is_active=True)
        if sub.stripe_subscription_id:
            stripe.Subscription.modify(
                sub.stripe_subscription_id,
                cancel_at_period_end=False
            )
            messages.success(request, "Your subscription has been reactivated.")
        else:
            messages.error(request, "No subscription found.")
    except FuzeSubscription.DoesNotExist:
        messages.error(request, "No subscription found.")
    
    return redirect('FUZE:manage_subscription')

@staff_member_required
def fuze_user_detail(request, user_id):
    view_user = get_object_or_404(User, id=user_id)
    days = int(request.GET.get('days', 30))
    cutoff = timezone.now() - timedelta(days=days)
    
    # AI usage
    ai_usage_qs = AIUsage.objects.filter(user=view_user, timestamp__gte=cutoff).order_by('-timestamp')
    ai_stats = ai_usage_qs.aggregate(
        total_cost=Sum('estimated_cost'),
        total_tokens=Sum('tokens_used'),
        total_requests=Count('id')
    )

    # Success rate
    success_count = ai_usage_qs.filter(success=True).count()
    total_count = ai_usage_qs.count()
    success_rate = round((success_count / total_count * 100), 1) if total_count > 0 else 0

    # Get sliced for display
    ai_usage = ai_usage_qs
    
    # Chats
    user_chats = view_user.fuze_chat_history if view_user.fuze_chat_history else []
    
    # Activity
    activity = UserActivity.objects.filter(user=view_user, timestamp__gte=cutoff).order_by('-timestamp')
    
    # Widgets
    widgets = WidgetConfig.objects.filter(user=view_user, enabled=True)
    
    # Media library storage
    media_stats = MediaLibrary.objects.filter(user=view_user).aggregate(
        total_files=Count('id'),
        total_size=Sum('file_size')
    )
    media_size_mb = round((media_stats['total_size'] or 0) / (1024 * 1024), 2)
    
    # Donation settings
    try:
        donation_settings = DonationSettings.objects.get(user=view_user)
        donation_url = request.build_absolute_uri(f'/fuze/donate/{donation_settings.donation_token}')
    except DonationSettings.DoesNotExist:
        donation_settings = None
        donation_url = None
    
    context = {
        'view_user': view_user,
        'ai_usage': ai_usage,
        'ai_stats': ai_stats,
        'success_rate': success_rate,
        'user_chats': user_chats,
        'activity': activity,
        'days': days,
        'widgets': widgets,
        'media_files': media_stats['total_files'] or 0,
        'media_size_mb': media_size_mb,
        'donation_settings': donation_settings,
        'donation_url': donation_url,
    }
    
    return render(request, 'FUZE/user_detail.html', context)

@staff_member_required
def fuze_chat_detail(request, user_id, chat_index):
    view_user = get_object_or_404(User, id=user_id)
    user_chats = view_user.fuze_chat_history if view_user.fuze_chat_history else []
    
    if chat_index >= len(user_chats):
        return redirect('FUZE:user_detail', user_id=user_id)
    
    chat = user_chats[chat_index]
    
    context = {
        'view_user': view_user,
        'chat': chat,
        'chat_index': chat_index
    }
    
    return render(request, 'FUZE/chat_detail.html', context)

@staff_member_required
def fuze_analytics_view(request):
    cleanup_old_sessions()
    
    days = int(request.GET.get('days', 30))
    date_from = timezone.now() - timedelta(days=days)
    
    # Query ONLY Fuze users
    fuze_users = User.objects.filter(fuze_activated=True)
    total_users = fuze_users.count()
    new_users = fuze_users.filter(fuze_first_login__gte=date_from).count()
    
    # Active users from sessions
    from .models import ActiveSession
    active_users = ActiveSession.objects.filter(user__isnull=False).values('user').distinct().count()
    
    # Downloads
    downloads = DownloadTracking.objects.filter(timestamp__gte=date_from)
    total_downloads = downloads.count()
    downloads_by_platform = list(downloads.values('platform').annotate(count=Count('id')))
    
    # AI usage
    ai_stats = AIUsage.objects.filter(timestamp__gte=date_from).aggregate(
        total=Count('id'),
        success_count=Count('id', filter=Q(success=True)),
        total_cost=Sum('estimated_cost'),
        avg_tokens=Avg('tokens_used'),
        avg_response_time=Avg('response_time')
    )
    
    total_requests = ai_stats['total'] or 0
    success_rate = round((ai_stats['success_count'] or 0) / total_requests * 100, 1) if total_requests > 0 else 0
    total_cost = round(float(ai_stats['total_cost'] or 0), 2)
    avg_tokens = round(ai_stats['avg_tokens'] or 0)
    avg_response_time = round(ai_stats['avg_response_time'] or 0, 2)
    
    # AI cost by tier (free vs paid)
    free_ai = AIUsage.objects.filter(timestamp__gte=date_from, user_tier='free').aggregate(
        count=Count('id'), cost=Sum('estimated_cost')
    )
    paid_ai = AIUsage.objects.filter(timestamp__gte=date_from).exclude(user_tier='free').aggregate(
        count=Count('id'), cost=Sum('estimated_cost')
    )
    
    free_cost = round(float(free_ai['cost'] or 0), 2)
    paid_cost = round(float(paid_ai['cost'] or 0), 2)
    free_requests = free_ai['count'] or 0
    paid_requests = paid_ai['count'] or 0
    
    # Tier distribution
    tier_distribution = list(fuze_users.values('fuze_tier').annotate(count=Count('id')))
    for tier in tier_distribution:
        tier['tier'] = tier.pop('fuze_tier')
    
    # Upgrades/downgrades
    upgrades = TierChange.objects.filter(timestamp__gte=date_from).exclude(from_tier='free', to_tier='free').exclude(to_tier='free').count()
    downgrades = TierChange.objects.filter(timestamp__gte=date_from, to_tier='free').count()
    
    # Revenue tracking (from actual purchases for accurate amounts)
    purchases_in_range = FuzePurchase.objects.filter(
        created_at__gte=date_from, is_paid=True
    )
    pro_purchases = purchases_in_range.filter(plan_type='pro').count()
    three_month_purchases = purchases_in_range.filter(plan_type='3month').count()
    lifetime_purchases = purchases_in_range.filter(plan_type='lifetime').count()

    pro_revenue = float(purchases_in_range.filter(plan_type='pro').aggregate(t=Sum('amount'))['t'] or 0)
    three_month_revenue = float(purchases_in_range.filter(plan_type='3month').aggregate(t=Sum('amount'))['t'] or 0)
    lifetime_revenue = float(purchases_in_range.filter(plan_type='lifetime').aggregate(t=Sum('amount'))['t'] or 0)
    total_revenue = pro_revenue + three_month_revenue + lifetime_revenue
    
    # Cost by tier (detailed)
    cost_by_tier_raw = AIUsage.objects.filter(timestamp__gte=date_from).values('user_tier').annotate(
        request_count=Count('id'), 
        total_cost=Sum('estimated_cost')
    )
    
    cost_by_tier = []
    for item in cost_by_tier_raw:
        tier = item['user_tier'] or 'unknown'
        cost_by_tier.append({
            'tier_key': tier,
            'tier_display': tier.title(),
            'request_count': item['request_count'],
            'total_cost': round(float(item['total_cost'] or 0), 2)
        })
    
    # Top users by AI usage (exclude anonymous)
    top_users = AIUsage.objects.filter(
        timestamp__gte=date_from,
        user__isnull=False
    ).values(
        'user__id', 'user__username', 'user__fuze_tier'
    ).annotate(
        total_cost=Sum('estimated_cost'),
        total_requests=Count('id')
    ).order_by('-total_cost')[:10]
    
    # Feature usage
    feature_usage = list(UserActivity.objects.filter(timestamp__gte=date_from).values('activity_type').annotate(count=Count('id')).order_by('-count'))
    
    # Recent tier changes
    recent_tier_changes = TierChange.objects.select_related('user').filter(timestamp__gte=date_from)[:20]
    
    # Error tracking
    error_count = AIUsage.objects.filter(timestamp__gte=date_from, success=False).count()
    error_rate = round((error_count / total_requests * 100), 1) if total_requests > 0 else 0
    
    # Template usage
    template_usage = list(UserActivity.objects.filter(
        timestamp__gte=date_from, 
        activity_type='template_use'
    ).values('details__template_id').annotate(count=Count('id')).order_by('-count')[:10])
    
    # Daily active users trend
    dau_data = []
    for i in range(min(days, 30)):
        day = timezone.now() - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0)
        day_end = day.replace(hour=23, minute=59, second=59)
        dau = UserActivity.objects.filter(timestamp__range=[day_start, day_end]).values('user').distinct().count()
        dau_data.append({'date': day.strftime('%m/%d'), 'count': dau})
    dau_data.reverse()
    
    # Page views tracking
    from .models import FuzePageView
    landing_views = FuzePageView.objects.filter(page='landing', timestamp__gte=date_from).values('session_id').distinct().count()
    pricing_views = FuzePageView.objects.filter(page='pricing', timestamp__gte=date_from).values('session_id').distinct().count()
    
    # Review counts
    total_reviews = FuzeReview.objects.count()
    featured_reviews = FuzeReview.objects.filter(featured=True).count()
    
    # Announcements
    announcements = Announcement.objects.all().order_by('-created_at')
    
    context = {
        'days': days,
        'total_users': total_users,
        'new_users': new_users,
        'active_users': active_users,
        'total_downloads': total_downloads,
        'downloads_by_platform': downloads_by_platform,
        'downloads_json': json.dumps(downloads_by_platform),
        'total_requests': total_requests,
        'success_rate': success_rate,
        'error_rate': error_rate,
        'total_cost': total_cost,
        'free_cost': free_cost,
        'paid_cost': paid_cost,
        'free_requests': free_requests,
        'paid_requests': paid_requests,
        'avg_tokens': avg_tokens,
        'avg_response_time': avg_response_time,
        'tier_distribution': tier_distribution,
        'tier_distribution_json': json.dumps(tier_distribution),
        'upgrades': upgrades,
        'downgrades': downgrades,
        'pro_purchases': pro_purchases,
        'three_month_purchases': three_month_purchases,
        'lifetime_purchases': lifetime_purchases,
        'pro_revenue': pro_revenue,
        'three_month_revenue': three_month_revenue,
        'lifetime_revenue': lifetime_revenue,
        'total_revenue': total_revenue,
        'cost_by_tier': cost_by_tier,
        'top_users': top_users,
        'feature_usage': feature_usage,
        'feature_usage_json': json.dumps(feature_usage),
        'recent_tier_changes': recent_tier_changes,
        'template_usage': template_usage,
        'dau_data': dau_data,
        'dau_json': json.dumps(dau_data),
        'landing_views': landing_views,
        'pricing_views': pricing_views,
        'total_reviews': total_reviews,
        'featured_reviews': featured_reviews,
        'announcements': announcements,
    }
    
    return render(request, 'FUZE/fuze_analytics.html', context)

@staff_member_required
def fuze_telemetry_view(request):
    """HTML telemetry dashboard for anonymous app usage data."""
    from .models import TelemetryEvent
    from django.db.models import Count
    from django.db.models.functions import TruncDate

    days = min(int(request.GET.get('days', 7)), 90)
    since = timezone.now() - timedelta(days=days)
    qs = TelemetryEvent.objects.filter(created_at__gte=since)

    unique_devices = qs.values('device_id').distinct().count()
    unique_sessions = qs.values('session_id').distinct().count()
    total_events = qs.count()

    # Sessions per device
    sessions_per_device = round(unique_sessions / max(unique_devices, 1), 1)

    # Avg session duration
    session_durations = list(
        qs.filter(event='session_end')
        .values_list('properties__duration_seconds', flat=True)
    )
    valid_durations = [d for d in session_durations if d and isinstance(d, (int, float))]
    avg_seconds = sum(valid_durations) / max(len(valid_durations), 1)
    if avg_seconds >= 3600:
        avg_session_display = f"{avg_seconds / 3600:.1f}h"
    elif avg_seconds >= 60:
        avg_session_display = f"{avg_seconds / 60:.0f}m"
    else:
        avg_session_display = f"{avg_seconds:.0f}s"

    # Daily active devices
    daily_raw = list(
        qs.annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(devices=Count('device_id', distinct=True))
        .order_by('day')
    )
    max_daily = max((d['devices'] for d in daily_raw), default=1) or 1
    daily_active = [
        {
            'day': d['day'].strftime('%m/%d'),
            'devices': d['devices'],
            'height': max(round(d['devices'] / max_daily * 100), 3),
        }
        for d in daily_raw
    ]

    # Setup funnel
    funnel_events = [
        ('app_launched', 'App Launched'),
        ('system_detected', 'System Detected'),
        ('config_generated', 'Config Generated'),
        ('obs_connected', 'OBS Connected'),
        ('widget_configured', 'Widget Configured'),
        ('platform_connected', 'Platform Connected'),
        ('scene_injected', 'Scene Injected'),
    ]
    funnel_counts = {
        evt: qs.filter(event=evt).values('device_id').distinct().count()
        for evt, _ in funnel_events
    }
    funnel_base = funnel_counts.get('app_launched', 1) or 1
    funnel_steps = [
        {
            'label': label,
            'count': funnel_counts[evt],
            'pct': round(funnel_counts[evt] / funnel_base * 100),
        }
        for evt, label in funnel_events
    ]

    # Login funnel (per session, not per device)
    login_funnel = {
        'shown': qs.filter(event='login_shown').values('session_id').distinct().count(),
        'dismissed': qs.filter(event='login_dismissed').values('session_id').distinct().count(),
        'completed': qs.filter(event='login_completed').values('session_id').distinct().count(),
    }
    login_conversion = round(
        login_funnel['completed'] / max(login_funnel['shown'], 1) * 100
    )

    # Top events
    top_events_raw = list(
        qs.exclude(event__in=['tab_viewed', 'session_end', 'update_checked']).values('event').annotate(count=Count('id')).order_by('-count')[:15]
    )
    top_max = top_events_raw[0]['count'] if top_events_raw else 1
    top_events = [
        {**e, 'pct': round(e['count'] / top_max * 100)}
        for e in top_events_raw
    ]

    # Tab views (fixed order matching app UI)
    TAB_ORDER = ['WELCOME', 'DETECTION', 'CONFIGURATION', 'OPTIMIZATION', 'AUDIO', 'SCENES', 'TOOLS', 'PLUGINS', 'DOCUMENTATION', 'BENCHMARK', 'FUZE-AI']
    tab_counts_raw = {
        t['properties__tab']: t['count']
        for t in qs.filter(event='tab_viewed')
        .values('properties__tab')
        .annotate(count=Count('id'))
    }
    tab_max = max(tab_counts_raw.values(), default=1) or 1
    tab_views = [
        {
            'tab': name,
            'count': tab_counts_raw.get(name, 0),
            'pct': round(tab_counts_raw.get(name, 0) / tab_max * 100) if tab_counts_raw.get(name, 0) else 0,
        }
        for name in TAB_ORDER
    ]

    # OS breakdown
    os_raw = list(
        qs.values('os_name')
        .annotate(count=Count('device_id', distinct=True))
        .order_by('-count')
    )
    os_max = os_raw[0]['count'] if os_raw else 1
    os_breakdown = [{**o, 'pct': round(o['count'] / os_max * 100)} for o in os_raw]

    # Version breakdown
    ver_raw = list(
        qs.values('app_version')
        .annotate(count=Count('device_id', distinct=True))
        .order_by('-count')
    )
    ver_max = ver_raw[0]['count'] if ver_raw else 1
    version_breakdown = [{**v, 'pct': round(v['count'] / ver_max * 100)} for v in ver_raw]

    # Recent errors
    recent_errors = list(
        qs.filter(event='error')
        .order_by('-created_at')
        .values('device_id', 'properties', 'app_version', 'os_name', 'created_at')[:20]
    )
    for err in recent_errors:
        err['created_at'] = err['created_at'].strftime('%m/%d %H:%M')

    context = {
        'days': days,
        'unique_devices': unique_devices,
        'unique_sessions': unique_sessions,
        'total_events': total_events,
        'sessions_per_device': sessions_per_device,
        'avg_session_display': avg_session_display,
        'daily_active': daily_active,
        'last_day': daily_active[-1]['day'] if daily_active else '',
        'funnel_steps': funnel_steps,
        'login_funnel': login_funnel,
        'login_conversion': login_conversion,
        'top_events': top_events,
        'tab_views': tab_views,
        'os_breakdown': os_breakdown,
        'version_breakdown': version_breakdown,
        'recent_errors': recent_errors,
    }

    return render(request, 'FUZE/fuze_telemetry.html', context)

@staff_member_required
def fuze_all_users_view(request):
    from django.core.paginator import Paginator
    from django.db.models import OuterRef, Subquery, IntegerField, DecimalField, Value, Count, Sum
    from django.db.models.functions import Coalesce
    from decimal import Decimal
    
    # Use subqueries
    ai_requests_subq = AIUsage.objects.filter(user=OuterRef('pk')).values('user').annotate(
        cnt=Count('id')
    ).values('cnt')[:1]
    
    ai_cost_subq = AIUsage.objects.filter(user=OuterRef('pk')).values('user').annotate(
        total=Sum('estimated_cost')
    ).values('total')[:1]
    
    last_activity_subq = UserActivity.objects.filter(user=OuterRef('pk')).order_by(
        '-timestamp'
    ).values('timestamp')[:1]
    
    all_users = User.objects.filter(fuze_activated=True).annotate(
        total_ai_requests=Coalesce(Subquery(ai_requests_subq, output_field=IntegerField()), Value(0)),
        total_ai_cost=Coalesce(Subquery(ai_cost_subq, output_field=DecimalField()), Value(Decimal('0'))),
        last_activity=Subquery(last_activity_subq)
    ).order_by('-total_ai_requests')
    
    paginator = Paginator(all_users, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)
    
    context = {
        'all_users': page_obj,
        'page_obj': page_obj,
    }
    return render(request, 'FUZE/fuze_all_users.html', context)

@staff_member_required
@require_http_methods(["GET", "POST"])
def fuze_reset_analytics(request):
    """Admin view to reset analytics data for testing"""
    if request.method == 'POST':
        reset_type = request.POST.getlist('reset_type')
        deleted = {}
        
        if 'tier_changes' in reset_type:
            deleted['tier_changes'] = TierChange.objects.all().delete()[0]
        if 'ai_usage' in reset_type:
            deleted['ai_usage'] = AIUsage.objects.all().delete()[0]
        if 'user_activity' in reset_type:
            deleted['user_activity'] = UserActivity.objects.all().delete()[0]
        if 'downloads' in reset_type:
            deleted['downloads'] = DownloadTracking.objects.all().delete()[0]
        if 'active_sessions' in reset_type:
            deleted['active_sessions'] = ActiveSession.objects.all().delete()[0]
        if 'page_views' in reset_type:
            from .models import FuzePageView
            deleted['page_views'] = FuzePageView.objects.all().delete()[0]
        if 'telemetry' in reset_type:
            from .models import TelemetryEvent
            deleted['telemetry'] = TelemetryEvent.objects.all().delete()[0]
        
        return render(request, 'FUZE/fuze_reset_analytics.html', {
            'deleted': deleted,
            'success': True
        })
    
    # GET — show counts
    from .models import FuzePageView, TelemetryEvent
    counts = {
        'tier_changes': TierChange.objects.count(),
        'ai_usage': AIUsage.objects.count(),
        'user_activity': UserActivity.objects.count(),
        'downloads': DownloadTracking.objects.count(),
        'active_sessions': ActiveSession.objects.count(),
        'page_views': FuzePageView.objects.count(),
        'telemetry': TelemetryEvent.objects.count(),
    }
    return render(request, 'FUZE/fuze_reset_analytics.html', {'counts': counts})

# ===== WIDGETS SYSTEM =====
# Widget HTML generators

@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuze_get_widgets(request):
    """Get all widgets for user - fetch ALL platforms, not filtered"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        user = get_user_from_token(token)
    else:
        user = None
    
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    # Don't filter by platform - return ALL widgets
    widgets = WidgetConfig.objects.filter(user=user).order_by('-updated_at')
    
    return JsonResponse({
        'widgets': [{
            'id': w.id,
            'type': w.widget_type,
            'platform': w.platform,
            'goal_type': w.goal_type,
            'name': w.name,
            'config': w.config,
            'url': f'https://bomby.us/fuze/w/{w.token}',
            'created_at': w.created_at.isoformat(),
            'updated_at': w.updated_at.isoformat(),
            'enabled': w.enabled
        } for w in widgets]
    })

@xframe_options_exempt
@require_http_methods(["GET"])
def fuze_serve_widget(request, token):
    """Serve widget by token - clean URL"""
    try:
        widget = WidgetConfig.objects.get(token=token)
        html = generate_widget_html(widget)
        response = HttpResponse(html, content_type='text/html')
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    except WidgetConfig.DoesNotExist:
        return HttpResponse('Widget not found', status=404)

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuze_save_widget(request):
    """Save widget - handles auth inline"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        user = get_user_from_token(token)
    else:
        user = None
    
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        data = json.loads(request.body)
        widget_type = data['widget_type']
        goal_type = data.get('goal_type', '')
        
        # For goal_bar and labels: use 'all' platform, goal_type determines what it tracks
        # For viewer_count, chat_box, sponsor_banner: always 'all' platform
        # For alert_box, event_list: use specified platform
        if widget_type in ('viewer_count', 'chat_box', 'sponsor_banner'):
            platform = 'all'
        else:
            platform = data.get('platform', 'all')
        
        # Lookup and create logic
        if widget_type in ('goal_bar', 'labels'):
            # Include goal_type in lookup
            widget, created = WidgetConfig.objects.get_or_create(
                user=user,
                widget_type=widget_type,
                platform=platform,
                goal_type=goal_type,
                defaults={
                    'name': data.get('name', f'{widget_type.replace("_", " ").title()} - {goal_type.replace("_", " ").title()}'),
                    'config': data.get('config', {}),
                    'enabled': False
                }
            )
        else:
            # For other widgets: just widget_type + platform (goal_type is always empty)
            widget, created = WidgetConfig.objects.get_or_create(
                user=user,
                widget_type=widget_type,
                platform=platform,
                goal_type='',
                defaults={
                    'name': data.get('name', f'{widget_type.replace("_", " ").title()} - {platform.title()}'),
                    'config': data.get('config', {}),
                    'enabled': False
                }
            )
        
        # Update if not created
        if not created:
            if 'name' in data:
                widget.name = data['name']
            if 'config' in data:
                widget.config = data['config']
            widget.save()
            
            # Send refresh to widget in OBS
            send_widget_refresh(user.id, widget_type, platform)
        else:
            # Auto-create default event configs for alert_box
            if widget_type == 'alert_box':
                EVENT_TEMPLATES = {
                    'twitch': {
                        'follow': '{name} just followed!',
                        'subscribe': '{name} just subscribed!',
                        'bits': '{name} donated {amount} bits!',
                        'raid': '{name} just raided with {viewers} viewers!',
                        'host': '{name} just hosted with {viewers} viewers!',
                    },
                    'youtube': {
                        'subscribe': '{name} just subscribed!',
                        'member': '{name} became a member!',
                        'superchat': '{name} sent {amount} in Super Chat!',
                    },
                    'kick': {
                        'follow': '{name} just followed!',
                        'subscribe': '{name} just subscribed!',
                        'gift_sub': '{name} gifted {amount} subs!',
                    }
                }
                
                # For 'all' platform, create events for every platform; otherwise just the specified one
                if platform == 'all':
                    platforms_to_create = EVENT_TEMPLATES.items()
                else:
                    templates = EVENT_TEMPLATES.get(platform, {})
                    platforms_to_create = [(platform, templates)] if templates else []
                
                for plat, events in platforms_to_create:
                    for event_type, message_template in events.items():
                        WidgetEvent.objects.get_or_create(
                            widget=widget,
                            event_type=event_type,
                            platform=plat,
                            defaults={
                                'enabled': True,
                                'config': {
                                    'message_template': message_template,
                                    'duration': 5,
                                    'alert_animation': 'fade',
                                    'font_size': 32,
                                    'font_weight': 'normal',
                                    'font_family': 'Arial',
                                    'text_color': '#FFFFFF',
                                    'sound_volume': 50,
                                    'layout': 'image_above'
                                }
                            }
                        )
        
        UserActivity.objects.create(
            user=user,
            activity_type='widget_create' if created else 'widget_update',
            source='app',
            details={'widget_type': widget.widget_type, 'platform': platform, 'widget_id': widget.id, 'goal_type': goal_type}
        )
        
        widget_url = f'https://bomby.us/fuze/w/{widget.token}'
        
        return JsonResponse({
            'success': True,
            'id': widget.id,
            'url': widget_url,
            'widget': {
                'id': widget.id,
                'type': widget.widget_type,
                'platform': widget.platform,
                'goal_type': widget.goal_type,
                'name': widget.name,
                'config': widget.config,
                'url': widget_url,
                'enabled': widget.enabled
            }
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f'Request error: {e}'); return JsonResponse({'error': 'Bad request'}, status=400)

@csrf_exempt
@require_http_methods(["DELETE"])
@require_tier('free')
def fuze_delete_widget(request, widget_type):
    """Delete ALL widgets of a type for user - cascades to events via model FK"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        user = get_user_from_token(token)
    else:
        user = None
    
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        # Delete ALL widgets of this type for user
        deleted_count, _ = WidgetConfig.objects.filter(user=user, widget_type=widget_type).delete()
        return JsonResponse({'success': True, 'deleted': deleted_count})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f'Server error: {e}'); return JsonResponse({'error': 'Internal error'}, status=500)
@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuze_toggle_widget(request):
    """Toggle widget enabled/disabled state"""
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.replace('Bearer ', '')
        user = get_user_from_token(token)
    else:
        user = None
    
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)
    
    try:
        data = json.loads(request.body)
        widget_id = data.get('widget_id')
        enabled = data.get('enabled', True)
        
        widget = WidgetConfig.objects.get(id=widget_id, user=user)
        widget.enabled = enabled
        widget.save()
        
        return JsonResponse({'success': True, 'enabled': widget.enabled})
    except WidgetConfig.DoesNotExist:
        return JsonResponse({'error': 'Widget not found'}, status=404)
    except Exception as e:
        logger.error(f'Server error: {e}'); return JsonResponse({'error': 'Internal error'}, status=500)

# ===== PLATFORM CONNECTIONS =====

PLATFORM_OAUTH_CONFIG = {
    'twitch': {
        'auth_url': 'https://id.twitch.tv/oauth2/authorize',
        'token_url': 'https://id.twitch.tv/oauth2/token',
        'client_id': os.environ.get('TWITCH_CLIENT_ID', ''),
        'client_secret': os.environ.get('TWITCH_CLIENT_SECRET', ''),
        'scopes': ['channel:read:subscriptions', 'bits:read', 'channel:read:redemptions', 'moderator:read:followers', 'chat:read']
    },
    'youtube': {
        'auth_url': 'https://accounts.google.com/o/oauth2/v2/auth',
        'token_url': 'https://oauth2.googleapis.com/token',
        'client_id': os.environ.get('YOUTUBE_CLIENT_ID', ''),
        'client_secret': os.environ.get('YOUTUBE_CLIENT_SECRET', ''),
        'scopes': [
            'https://www.googleapis.com/auth/youtube.readonly',
            'https://www.googleapis.com/auth/youtube.force-ssl'
        ]
    },
    'kick': {
        'auth_url': 'https://id.kick.com/oauth/authorize',
        'token_url': 'https://id.kick.com/oauth/token',
        'client_id': os.environ.get('KICK_CLIENT_ID', ''),
        'client_secret': os.environ.get('KICK_CLIENT_SECRET', ''),
        'scopes': ['user:read', 'channel:read', 'events:subscribe']
    },
    'facebook': {
        'auth_url': 'https://www.facebook.com/v18.0/dialog/oauth',
        'token_url': 'https://graph.facebook.com/v18.0/oauth/access_token',
        'client_id': os.environ.get('FACEBOOK_CLIENT_ID', ''),
        'client_secret': os.environ.get('FACEBOOK_CLIENT_SECRET', ''),
        'scopes': ['pages_show_list', 'pages_read_engagement']
    },
    'tiktok': {
        'auth_url': 'https://www.tiktok.com/v2/auth/authorize',
        'token_url': 'https://open.tiktokapis.com/v2/oauth/token/',
        'client_id': os.environ.get('TIKTOK_CLIENT_KEY', ''),
        'client_secret': os.environ.get('TIKTOK_CLIENT_SECRET', ''),
        'scopes': ['user.info.profile', 'user.info.stats']
    }
}

def generate_pkce_pair():
    """Generate PKCE code_verifier and code_challenge"""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge

@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuze_get_platforms(request):
    """Get connected platforms for user"""
    user = request.fuze_user
    platforms = PlatformConnection.objects.filter(user=user)
    
    return JsonResponse({
        'platforms': [{
            'platform': p.platform,
            'username': p.platform_username,
            'connected_at': p.connected_at.isoformat(),
            'expires_at': p.expires_at.isoformat() if p.expires_at else None
        } for p in platforms]
    })

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuze_connect_platform(request):
    user = request.fuze_user
    try:
        data = json.loads(request.body)
        platform = data['platform']
        
        if platform not in PLATFORM_OAUTH_CONFIG:
            return JsonResponse({'error': 'Invalid platform'}, status=400)
        
        config = PLATFORM_OAUTH_CONFIG[platform]
        state = secrets.token_urlsafe(32)
        
        if platform in ('kick', 'tiktok'):
            code_verifier, code_challenge = generate_pkce_pair()
            cache.set(f'oauth_state_{state}', {'user_id': user.id, 'platform': platform, 'code_verifier': code_verifier}, timeout=600)
        else:
            cache.set(f'oauth_state_{state}', {'user_id': user.id, 'platform': platform}, timeout=600)
        
        redirect_uri = f'https://bomby.us/fuze/callback/{platform}'
        scopes = ' '.join(config['scopes']) if platform != 'tiktok' else ','.join(config['scopes'])
        
        if platform == 'tiktok':
            auth_url = f"{config['auth_url']}?client_key={config['client_id']}&redirect_uri={redirect_uri}&response_type=code&scope={scopes}&state={state}&code_challenge={code_challenge}&code_challenge_method=S256"
        else:
            auth_url = f"{config['auth_url']}?client_id={config['client_id']}&redirect_uri={redirect_uri}&response_type=code&scope={scopes}&state={state}"
        
        if platform == 'youtube':
            auth_url += '&access_type=offline&prompt=consent'
        elif platform == 'kick':
            auth_url += f'&code_challenge={code_challenge}&code_challenge_method=S256'
        elif platform == 'twitch':
            auth_url += '&force_verify=true'  

        return JsonResponse({'success': True, 'auth_url': auth_url, 'state': state})
    except Exception as e:
        logger.error(f'Request error: {e}'); return JsonResponse({'error': 'Bad request'}, status=400)

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuze_tiktok_exchange(request):
    """Exchange TikTok auth code for token (desktop localhost flow)"""
    user = request.fuze_user
    try:
        data = json.loads(request.body)
        code = data['code']
        state = data['state']
        
        state_data = cache.get(f'oauth_state_{state}')
        if not state_data or state_data['platform'] != 'tiktok':
            return JsonResponse({'error': 'Invalid state'}, status=400)
        
        config = PLATFORM_OAUTH_CONFIG['tiktok']
        redirect_uri = 'http://localhost:5050/tiktok-callback'
        
        token_data = {
            'client_key': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
            'code_verifier': state_data['code_verifier']
        }
        
        token_response = requests.post(config['token_url'], 
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data=token_data)
        
        if token_response.status_code != 200:
            print(f'[TIKTOK] Token exchange failed: {token_response.text}')
            return JsonResponse({'error': f'Token exchange failed: {token_response.text}'}, status=400)
        
        token_json = token_response.json()
        logger.debug(f'[TIKTOK] Token exchange: status={token_response.status_code}')
        
        if 'error' in token_json or token_json.get('error_code'):
            error_msg = token_json.get('error_description') or token_json.get('message') or str(token_json)
            return JsonResponse({'error': f'TikTok error: {error_msg}'}, status=400)
        
        access_token = token_json.get('access_token') or token_json.get('data', {}).get('access_token')
        refresh_token = token_json.get('refresh_token') or token_json.get('data', {}).get('refresh_token', '')
        expires_in = token_json.get('expires_in') or token_json.get('data', {}).get('expires_in', 86400)
        
        if not access_token:
            return JsonResponse({'error': f'No access token in response: {token_json}'}, status=400)
        
        username, platform_user_id = get_platform_username('tiktok', access_token)
        
        PlatformConnection.objects.update_or_create(
            user=user,
            platform='tiktok',
            defaults={
                'platform_username': username,
                'platform_user_id': platform_user_id,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_at': timezone.now() + timedelta(seconds=expires_in)
            }
        )
        
        try:
            start_tiktok_listener(user.id, username)
            print(f'[TIKTOK] Started listener for user {user.id} (@{username})')
        except Exception as e:
            print(f'[TIKTOK] Error starting listener: {e}')
        
        cache.delete(f'oauth_state_{state}')
        
        return JsonResponse({'success': True, 'username': username})
    except Exception as e:
        print(f'[TIKTOK] Exchange error: {e}')
        logger.error(f'Request error: {e}'); return JsonResponse({'error': 'Bad request'}, status=400)
    
@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuze_disconnect_platform(request):
    """Disconnect platform"""
    user = request.fuze_user
    
    try:
        data = json.loads(request.body)
        platform = data['platform']
        
        # Stop Kick listener if disconnecting Kick
        if platform == 'kick':
            try:
                conn = PlatformConnection.objects.get(user=user, platform=platform)
                stop_kick_listener(conn.platform_username)
            except: pass

        # Stop YouTube listener if disconnecting YouTube
        elif platform == 'youtube':
            try:
                stop_youtube_listener(user.id)
            except:
                pass
        
        # Stop Facebook listener if disconnecting Facebook
        elif platform == 'facebook':
            try:
                conn = PlatformConnection.objects.get(user=user, platform=platform)
                stop_facebook_listener(conn.platform_user_id)
            except:
                pass

        # Stop TikTok listener if disconnecting TikTok
        elif platform == 'tiktok':
            try:
                stop_tiktok_listener(user.id)
            except:
                pass
        
        PlatformConnection.objects.filter(user=user, platform=platform).delete()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f'Request error: {e}'); return JsonResponse({'error': 'Bad request'}, status=400)

@csrf_exempt
def fuze_platform_callback(request, platform):
    """OAuth callback handler"""
    from .twitch import subscribe_twitch_events
    
    code = request.GET.get('code')
    state = request.GET.get('state')
    
    if not code or not state:
        return HttpResponse('Invalid callback', status=400)
    
    state_data = cache.get(f'oauth_state_{state}')
    if not state_data or state_data['platform'] != platform:
        return HttpResponse('Invalid state', status=400)
    
    # Delete state immediately to prevent replay
    cache.delete(f'oauth_state_{state}')
    
    user = User.objects.get(id=state_data['user_id'])
    config = PLATFORM_OAUTH_CONFIG[platform]
    
    redirect_uri = f'https://bomby.us/fuze/callback/{platform}'
    
    # Build token request - TikTok uses client_key instead of client_id
    if platform == 'tiktok':
        token_data = {
            'client_key': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        }
    else:
        token_data = {
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        }
    
    # Add code_verifier for Kick and TikTok (PKCE)
    if platform in ('kick', 'tiktok') and 'code_verifier' in state_data:
        token_data['code_verifier'] = state_data['code_verifier']
    
    token_response = requests.post(config['token_url'], 
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        data=token_data)
    
    if token_response.status_code != 200:
        print(f'[{platform.upper()}] Token exchange failed: {token_response.text}')
        return HttpResponse('Token exchange failed', status=400)
    
    token_json = token_response.json()
    
    # TikTok may nest tokens in 'data' object
    if platform == 'tiktok':
        access_token = token_json.get('access_token') or token_json.get('data', {}).get('access_token')
        refresh_token = token_json.get('refresh_token') or token_json.get('data', {}).get('refresh_token', '')
        expires_in = token_json.get('expires_in') or token_json.get('data', {}).get('expires_in', 86400)
    else:
        access_token = token_json['access_token']
        refresh_token = token_json.get('refresh_token', '')
        expires_in = token_json.get('expires_in', 3600)
    
    # Facebook returns page token as 3rd value
    if platform == 'facebook':
        username, platform_user_id, page_token = get_platform_username(platform, access_token)
        actual_token = page_token
    else:
        username, platform_user_id = get_platform_username(platform, access_token)
        actual_token = access_token
    
    PlatformConnection.objects.update_or_create(
        user=user,
        platform=platform,
        defaults={
            'platform_username': username,
            'platform_user_id': platform_user_id,
            'access_token': actual_token,
            'refresh_token': refresh_token,
            'expires_at': timezone.now() + timedelta(seconds=expires_in)
        }
    )
    
    # Subscribe to platform events
    if platform == 'twitch' and platform_user_id:
        try:
            subscribe_twitch_events(user.id, platform_user_id, access_token)
        except Exception as e:
            print(f'Error subscribing to Twitch events: {e}')
    elif platform == 'youtube':
        try:
            start_youtube_listener(user.id, access_token)
            print(f'[YOUTUBE] Started listener for user {user.id}')
        except Exception as e:
            print(f'[YOUTUBE] Error starting listener: {e}')
    elif platform == 'kick':
        try:
            start_kick_listener(user.id, username)
            print(f'[KICK] Started listener for user {user.id} ({username})')
        except Exception as e:
            print(f'[KICK] Error starting listener: {e}')
    elif platform == 'facebook':
        try:
            start_facebook_listener(user.id, platform_user_id, actual_token)
            print(f'[FACEBOOK] Started listener for user {user.id}, page {platform_user_id}')
        except Exception as e:
            print(f'[FACEBOOK] Error starting listener: {e}')
    elif platform == 'tiktok':
        try:
            start_tiktok_listener(user.id, username)
            print(f'[TIKTOK] Started listener for user {user.id} (@{username})')
        except Exception as e:
            print(f'[TIKTOK] Error starting listener: {e}')
    
    cache.delete(f'oauth_state_{state}')
    
    return render(request, 'FUZE/platform_connected.html', {'platform': platform})

def get_platform_username(platform, access_token):
    """Get username and user ID from platform API"""
    import requests
    
    if platform == 'twitch':
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Client-Id': PLATFORM_OAUTH_CONFIG['twitch']['client_id']
        }
        response = requests.get('https://api.twitch.tv/helix/users', headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data['data'][0]['login'], data['data'][0]['id']
    
    elif platform == 'youtube':
        # First try the channels API
        response = requests.get(
            'https://www.googleapis.com/youtube/v3/channels',
            params={'part': 'snippet', 'mine': 'true'},
            headers={'Authorization': f'Bearer {access_token}'}
        )
        if response.status_code == 200:
            data = response.json()
            if data.get('items'):
                return data['items'][0]['snippet']['title'], data['items'][0]['id']
        
        # Fallback to userinfo (no quota cost)
        userinfo_resp = requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f'Bearer {access_token}'}
        )
        if userinfo_resp.status_code == 200:
            userinfo = userinfo_resp.json()
            return userinfo.get('name', 'YouTube User'), userinfo.get('sub', '')
        
        return 'YouTube User', ''
    
    elif platform == 'kick':
        headers = {'Authorization': f'Bearer {access_token}'}
        
        try:
            response = requests.get('https://api.kick.com/public/v1/users', 
                                   headers=headers, 
                                   timeout=10)
            print(f'[KICK] /users Status: {response.status_code}')
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('data') and len(data['data']) > 0:
                    user = data['data'][0]
                    username = user.get('name', 'Kick User')
                    user_id = str(user.get('user_id', ''))
                    
                    return username, user_id
                else:
                    print('[KICK] No user data in response')
                    return 'Kick User', ''
            else:
                print(f'[KICK] Failed with status {response.status_code}')
                return 'Kick User', ''
                
        except Exception as e:
            print(f'[KICK] Exception: {e}')
            import traceback
            traceback.print_exc()
            return 'Kick User', ''
    
    elif platform == 'facebook':
        response = requests.get(
            'https://graph.facebook.com/v18.0/me/accounts',
            params={'access_token': access_token}
        )
        print(f'[FACEBOOK] /me/accounts: {response.status_code} - {response.text[:500]}')
        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                page = data['data'][0]
                # Return page token as 3rd element
                return page.get('name', 'Facebook Page'), page.get('id', ''), page.get('access_token', access_token)
        return 'Facebook User', '', access_token
    
    if platform == 'tiktok':
        resp = requests.get(
            'https://open.tiktokapis.com/v2/user/info/',
            params={'fields': 'open_id,display_name,avatar_url'},
            headers={'Authorization': f'Bearer {access_token}'}
        )
        print(f'[TIKTOK] User info: {resp.status_code} - {resp.text[:500]}')
        if resp.status_code == 200:
            data = resp.json().get('data', {}).get('user', {})
            return data.get('display_name', 'TikTok User'), data.get('open_id', '')
        return 'TikTok User', ''
    
    return 'Unknown', ''

# ===== MEDIA LIBRARY =====
@csrf_exempt
@xframe_options_exempt
@csrf_exempt
@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuze_get_media(request):
    """Get user's media library"""
    user = request.fuze_user
    media = MediaLibrary.objects.filter(user=user).order_by('-uploaded_at')
    
    total_size = sum(m.file_size for m in media)
    max_size = 25 * 1024 * 1024  # 25MB for free, could increase for pro
    
    if user.fuze_tier in ['pro', 'lifetime']:
        max_size = 100 * 1024 * 1024  # 100MB
    
    DEFAULT_MEDIA = [
        {
            'id': 'default-image',
            'name': 'Default Alert Image',
            'type': 'image',
            'url': 'https://storage.googleapis.com/fuze-public/media/default-alert.gif',
            'size': 0,
            'is_default': True,
        },
        {
            'id': 'default-sound',
            'name': 'Default Alert Sound',
            'type': 'sound',
            'url': 'https://storage.googleapis.com/fuze-public/media/default-alert.mp3',
            'size': 0,
            'is_default': True,
        },
    ]
    
    user_media = [{
        'id': m.id,
        'name': m.name,
        'type': m.media_type,
        'url': m.file_url,
        'size': m.file_size,
        'is_default': False,
        'uploaded_at': m.uploaded_at.isoformat()
    } for m in media]
    
    return JsonResponse({
        'media': DEFAULT_MEDIA + user_media,
        'total_size': total_size,
        'max_size': max_size
    })

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuze_upload_media(request):
    user = request.fuze_user
    file = request.FILES.get('file')
    if not file:
        return JsonResponse({'error': 'No file'}, status=400)
    
    max_size = 100 * 1024 * 1024 if user.fuze_tier in ['pro', 'lifetime'] else 25 * 1024 * 1024
    current = sum(m.file_size for m in MediaLibrary.objects.filter(user=user))
    
    if current + file.size > max_size:
        return JsonResponse({'error': 'Storage limit exceeded'}, status=400)
    
    # Validate actual file content, not just client-provided content_type
    ALLOWED_EXTENSIONS = {
        'image': {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'},
        'sound': {'mp3', 'wav', 'ogg', 'webm'},
        'video': {'mp4', 'webm', 'mov'},
    }
    MAGIC_BYTES = {
        b'\x89PNG': 'image', b'\xff\xd8\xff': 'image', b'GIF8': 'image',
        b'RIFF': 'image',  # webp (RIFF....WEBP)
        b'ID3': 'sound', b'\xff\xfb': 'sound', b'\xff\xf3': 'sound',
        b'OggS': 'sound',
        b'\x00\x00\x00': 'video',  # mp4/mov (ftyp box)
        b'\x1a\x45\xdf\xa3': 'video',  # webm/mkv
    }
    
    ext = file.name.rsplit('.', 1)[-1].lower() if '.' in file.name else ''
    
    # Determine type from extension
    media_type = None
    for mtype, exts in ALLOWED_EXTENSIONS.items():
        if ext in exts:
            media_type = mtype
            break
    
    if not media_type:
        return JsonResponse({'error': 'Invalid file type'}, status=400)
    
    # Verify magic bytes match claimed type
    header = file.read(12)
    file.seek(0)
    magic_match = False
    for magic, mtype in MAGIC_BYTES.items():
        if header.startswith(magic) and mtype == media_type:
            magic_match = True
            break
    # Allow SVG (text-based, no magic bytes) but sanitize
    if ext == 'svg':
        magic_match = True
        content_full = file.read().decode('utf-8', errors='ignore').lower()
        file.seek(0)
        SVG_DANGEROUS = [
            '<script', 'javascript:', 'onerror', 'onload', 'onmouseover',
            'onclick', 'onfocus', 'onblur', 'onanimationend', 'onbegin',
            'data:text/html', 'data:application', '<foreignobject',
            'xlink:href="data:', 'xlink:href="javascript:',
        ]
        if any(pattern in content_full for pattern in SVG_DANGEROUS):
            return JsonResponse({'error': 'Invalid SVG content'}, status=400)
    
    if not magic_match:
        return JsonResponse({'error': 'File content does not match extension'}, status=400)
    
    client = storage.Client()
    bucket = client.bucket('fuze-public')
    ext = file.name.split('.')[-1]
    filename = f'{uuid.uuid4()}.{ext}'
    blob = bucket.blob(f'media/{user.id}/{filename}')
    blob.upload_from_file(
        file, 
        content_type=file.content_type,
        predefined_acl='publicRead'
    )
    blob.cache_control = 'public, max-age=31536000'
    blob.patch()
    
    file_url = blob.public_url
    
    media = MediaLibrary.objects.create(
        user=user,
        name=file.name,
        media_type=media_type,
        file_url=file_url,
        file_size=file.size
    )
    
    return JsonResponse({
        'success': True,
        'media': {
            'id': media.id,
            'name': media.name,
            'type': media.media_type,
            'url': media.file_url,
            'size': media.file_size
        }
    })

@csrf_exempt
@require_http_methods(["DELETE"])
@require_tier('free')
def fuze_delete_media(request, media_id):
    user = request.fuze_user
    try:
        media = MediaLibrary.objects.get(id=media_id, user=user)
        
        try:
            client = storage.Client()
            bucket = client.bucket('fuze-public')
            blob_path = '/'.join(media.file_url.split('/')[-3:])
            blob = bucket.blob(blob_path)
            blob.delete()
        except:
            pass
        
        media.delete()
        return JsonResponse({'success': True})
    except MediaLibrary.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

# ===== WIDGET EVENTS =====

@csrf_exempt
@require_http_methods(["GET"])
@require_tier('free')
def fuze_get_widget_events(request, widget_id):
    """Get event configurations for widget"""
    user = request.fuze_user
    
    try:
        widget = WidgetConfig.objects.get(id=widget_id, user=user)
        
        # Auto-create missing default events if widget is alert_box
        if widget.widget_type == 'alert_box':
            EVENT_TEMPLATES = {
                'twitch': {
                    'follow': '{name} just followed!',
                    'subscribe': '{name} just subscribed!',
                    'bits': '{name} donated {amount} bits!',
                    'raid': '{name} just raided with {viewers} viewers!',
                    'host': '{name} just hosted with {viewers} viewers!',
                },
                'youtube': {
                    'subscribe': '{name} just subscribed!',
                    'superchat': '{name} sent {amount} in Super Chat!',
                    'supersticker': '{name} sent a Super Sticker!',
                    'member': '{name} became a member!',
                    'milestone': '{name} hit {months} month milestone!',
                    'gift': '{name} gifted memberships!',
                },
                'kick': {
                    'follow': '{name} just followed!',
                    'subscribe': '{name} just subscribed!',
                    'gift_sub': '{name} gifted {amount} subs!',
                }
            }
            
            # For 'all' platform, auto-create for every platform; otherwise just the specified one
            if widget.platform == 'all':
                platforms_to_check = EVENT_TEMPLATES.items()
            else:
                templates = EVENT_TEMPLATES.get(widget.platform, {})
                platforms_to_check = [(widget.platform, templates)] if templates else []
            
            for plat, templates in platforms_to_check:
                for event_type, message_template in templates.items():
                    WidgetEvent.objects.get_or_create(
                        widget=widget,
                        event_type=event_type,
                        platform=plat,
                        defaults={
                            'enabled': True,
                            'config': {
                                'message_template': message_template,
                                'duration': 5,
                                'alert_animation': 'fade',
                                'font_size': 32,
                                'font_weight': 'normal',
                                'font_family': 'Arial',
                                'text_color': '#FFFFFF',
                                'sound_volume': 50,
                                'layout': 'image_above'
                            }
                        }
                    )
        events = WidgetEvent.objects.filter(widget=widget)
        
        return JsonResponse({
            'events': [{
                'id': e.id,
                'event_type': e.event_type,
                'platform': e.platform,
                'enabled': e.enabled,
                'config': e.config
            } for e in events]
        })
        
    except WidgetConfig.DoesNotExist:
        return JsonResponse({'error': 'Widget not found'}, status=404)

@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuze_save_widget_event(request):
    user = request.fuze_user
    
    try:
        data = json.loads(request.body)
        widget_id = data['widget_id']
        event_type = data['event_type']
        platform = data['platform']
        config = data.get('config', {})
        
        widget = WidgetConfig.objects.get(id=widget_id, user=user)
        
        event, created = WidgetEvent.objects.update_or_create(
            widget=widget,
            event_type=event_type,
            platform=platform,
            defaults={
                'enabled': True,
                'config': config
            }
        )
        
        # Send refresh message to OBS via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'alerts_{user.id}_{platform}',
            {
                'type': 'alert_event',
                'data': {
                    'type': 'refresh'
                }
            }
        )
        
        return JsonResponse({
            'success': True,
            'event': {
                'id': event.id,
                'event_type': event.event_type,
                'platform': event.platform,
                'enabled': event.enabled,
                'config': event.config
            }
        })
        
    except WidgetConfig.DoesNotExist:
        return JsonResponse({'error': 'Widget not found'}, status=404)
    except Exception as e:
        logger.error(f'Request error: {e}'); return JsonResponse({'error': 'Bad request'}, status=400)

@csrf_exempt
@require_http_methods(["DELETE"])
@require_tier('free')
def fuze_delete_widget_event(request, event_id):
    """Delete event configuration"""
    user = request.fuze_user
    
    try:
        event = WidgetEvent.objects.get(id=event_id, widget__user=user)
        event.delete()
        return JsonResponse({'success': True})
        
    except WidgetEvent.DoesNotExist:
        return JsonResponse({'error': 'Event not found'}, status=404)
    
@csrf_exempt
@require_http_methods(["POST"])
@require_tier('free')
def fuze_test_alert(request):
    try:
        data = json.loads(request.body)
        event_type = data.get('event_type')
        platform = data.get('platform')
        widget_type = data.get('widget_type', 'alert_box')
        
        user = request.fuze_user
        
        # Build event data based on event type
        random_amount = random.randint(1, 100)
        
        # Format amount based on event type
        if event_type == 'bits':
            formatted_amount = str(random.randint(100, 5000))  # bits are just numbers
        elif event_type == 'stars':
            formatted_amount = str(random.randint(10, 500))  # stars are just numbers
        else:
            formatted_amount = f'${random_amount:.2f}'  # donations/superchat use $
        
        event_data = {
            'username': 'Fuze',
            'amount': formatted_amount,
            'raw_amount': random_amount,
            'viewers': random.randint(1, 2000),
            'count': random.randint(1, 100),
            'gift': 'Rose',
            'message': 'Test message!',
            'months': random.randint(1, 24),
        }
        
        channel_layer = get_channel_layer()
        
        # Route to correct channel based on widget_type
        if widget_type == 'labels':
            # Send to labels channel
            async_to_sync(channel_layer.group_send)(
                f'labels_{user.id}',
                {
                    'type': 'label_update',
                    'data': {
                        'type': event_type,
                        'event_type': event_type,
                        'platform': platform,
                        'event_data': event_data,
                    }
                }
            )
        elif widget_type == 'event_list':
            # Send to donations channel for event list (it listens there)
            if platform == 'donation' or event_type == 'donation':
                async_to_sync(channel_layer.group_send)(
                    f'donations_{user.id}',
                    {
                        'type': 'donation_event',
                        'data': {
                            'type': 'donation',
                            'event_type': 'donation',
                            'platform': 'donation',
                            'event_data': event_data,
                        }
                    }
                )
            else:
                # Send to platform-specific alerts channel for event list
                async_to_sync(channel_layer.group_send)(
                    f'alerts_{user.id}_{platform}',
                    {
                        'type': 'alert_event',
                        'data': {
                            'platform': platform,
                            'event_type': event_type,
                            'event_data': event_data,
                        }
                    }
                )
        elif widget_type == 'goal_bar':
            # For donation/tip goals, send to donations channel
            if platform == 'donation' or event_type == 'donation':
                async_to_sync(channel_layer.group_send)(
                    f'donations_{user.id}',
                    {
                        'type': 'donation_event',
                        'data': {
                            'type': 'donation',
                            'event_type': 'donation',
                            'platform': 'donation',
                            'event_data': event_data,
                        }
                    }
                )
            else:
                # For other goals (follower, subscriber, etc.), send to alerts channel
                async_to_sync(channel_layer.group_send)(
                    f'alerts_{user.id}_{platform}',
                    {
                        'type': 'alert_event',
                        'data': {
                            'platform': platform,
                            'event_type': event_type,
                            'event_data': event_data,
                        }
                    }
                )
        else:
            # Default: send to alertbox channel
            # For donations, also send to donations channel
            if platform == 'donation' or event_type == 'donation':
                async_to_sync(channel_layer.group_send)(
                    f'donations_{user.id}',
                    {
                        'type': 'donation_event',
                        'data': {
                            'type': 'donation',
                            'event_type': 'donation',
                            'platform': 'donation',
                            'event_data': event_data,
                        }
                    }
                )
            else:
                async_to_sync(channel_layer.group_send)(
                    f'alerts_{user.id}_{platform}',
                    {
                        'type': 'alert_event',
                        'data': {
                            'platform': platform,
                            'event_type': event_type,
                            'event_data': event_data,
                            'clear_existing': True
                        }
                    }
                )
        
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f'Server error: {e}'); return JsonResponse({'success': False, 'error': 'Internal error'}, status=500)
    
@csrf_exempt
@require_http_methods(["GET"])
def fuze_get_widget_event_configs(request, user_id, platform):
    """Get event configurations for user's widgets - supports 'all' platform"""
    if not verify_widget_request(request, user_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        if platform == 'all':
            # For 'all' platform, get events from all alert_box widgets for this user
            widgets = WidgetConfig.objects.filter(user_id=user_id, widget_type='alert_box')
        else:
            widgets = WidgetConfig.objects.filter(user_id=user_id, platform=platform)
        
        configs = {}
        
        for widget in widgets:
            if platform == 'all':
                # Get events for all platforms
                events = WidgetEvent.objects.filter(widget=widget, enabled=True)
            else:
                events = WidgetEvent.objects.filter(widget=widget, platform=platform, enabled=True)
            
            for event in events:
                key = f"{event.platform}-{event.event_type}"
                configs[key] = event.config
                configs[key]['enabled'] = True
        
        response = JsonResponse({'configs': configs})
        response['Access-Control-Allow-Origin'] = '*'
        response['Cache-Control'] = 'no-cache'
        return response
    except Exception as e:
        response = JsonResponse({'configs': {}})
        response['Access-Control-Allow-Origin'] = '*'
        return response
    
# =========== TWITCH ALERTS ===========
@csrf_exempt
def fuze_twitch_webhook(request):
    """Receive Twitch EventSub webhooks"""
    import hmac
    import hashlib
    
    message_id = request.headers.get('Twitch-Eventsub-Message-Id', '')
    timestamp = request.headers.get('Twitch-Eventsub-Message-Timestamp', '')
    signature = request.headers.get('Twitch-Eventsub-Message-Signature', '')
    
    body = request.body.decode('utf-8')
    message = message_id + timestamp + body
    expected = 'sha256=' + hmac.new(
        settings.TWITCH_WEBHOOK_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected, signature):
        return JsonResponse({'error': 'Invalid signature'}, status=403)
    
    data = json.loads(body)
    msg_type = request.headers.get('Twitch-Eventsub-Message-Type')
    
    # DEBUG: print(f'[WEBHOOK] Type: {msg_type}')
    
    if msg_type == 'webhook_callback_verification':
        return HttpResponse(data['challenge'], content_type='text/plain')
    
    if msg_type == 'notification':
        event = data['event']
        sub_type = data['subscription']['type']
        condition = data['subscription']['condition']
        
        # DEBUG: print(f'[WEBHOOK] Event: {sub_type}')
        # DEBUG: print(f'[WEBHOOK] Event data: {event}')
        
        broadcaster_id = condition.get('broadcaster_user_id') or condition.get('to_broadcaster_user_id')
        try:
            conn = PlatformConnection.objects.get(platform='twitch', platform_user_id=broadcaster_id)
            
            # DEBUG: print(f'[WEBHOOK] Found user: {conn.user.id}')
            
            event_map = {
                'channel.follow': ('follow', {'username': event.get('user_name', event.get('user_login', 'Unknown'))}),
                'channel.subscribe': ('subscribe', {'username': event.get('user_name', 'Unknown')}),
                'channel.subscription.gift': ('subscribe', {'username': event.get('user_name', 'Anonymous'), 'amount': event.get('total', 1)}),
                'channel.cheer': ('bits', {'username': event.get('user_name', 'Unknown'), 'amount': event.get('bits', 0)}),
                'channel.raid': ('raid', {'username': event.get('from_broadcaster_user_name', 'Unknown'), 'viewers': event.get('viewers', 0)}),
            }
            
            if sub_type in event_map:
                event_type, event_data = event_map[sub_type]
                # DEBUG: print(f'[WEBHOOK] Sending alert: {event_type} - {event_data}')
                send_alert(conn.user.id, event_type, 'twitch', event_data)
                # DEBUG: print(f'[WEBHOOK] Alert sent!')
        except Exception as e:
            print(f'[WEBHOOK ERROR] {e}')
    
    return JsonResponse({'status': 'ok'})

# =========== YOUTUBE ALERTS ===========
@csrf_exempt
@require_http_methods(["GET"])
def fuze_youtube_start_listener(request, user_id):
    """Start YouTube listener if user is live"""
    if not verify_widget_request(request, user_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        conn = PlatformConnection.objects.get(user_id=user_id, platform='youtube')
        from .youtube import start_youtube_listener
        started = start_youtube_listener(user_id, conn.access_token)
        
        response = JsonResponse({'started': started})
        response['Access-Control-Allow-Origin'] = '*'
        return response
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'started': False})
    except Exception as e:
        print(f'[YOUTUBE] Error starting listener: {e}')
        return JsonResponse({'started': False})
    
# =========== FACEBOOK ALERTS ===========
@csrf_exempt
@require_http_methods(["GET"])
def fuze_facebook_start_listener(request, user_id):
    """Start Facebook listener"""
    if not verify_widget_request(request, user_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        conn = PlatformConnection.objects.get(user_id=user_id, platform='facebook')
        started = start_facebook_listener(user_id, conn.platform_user_id, conn.access_token)
        
        response = JsonResponse({'started': started})
        response['Access-Control-Allow-Origin'] = '*'
        return response
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'started': False})
    except Exception as e:
        print(f'[FACEBOOK] Error starting listener: {e}')
        return JsonResponse({'started': False})

# =========== KICK ALERTS ===========
@csrf_exempt
@require_http_methods(["GET"])
def fuze_kick_start_listener(request, user_id):
    """Start Kick listener"""
    if not verify_widget_request(request, user_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        conn = PlatformConnection.objects.get(user_id=user_id, platform='kick')
        started = start_kick_listener(user_id, conn.platform_username)
        
        response = JsonResponse({'started': started})
        response['Access-Control-Allow-Origin'] = '*'
        return response
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'started': False})
    except Exception as e:
        print(f'[KICK] Error starting listener: {e}')
        return JsonResponse({'started': False})

@csrf_exempt
@require_http_methods(["POST"])
def fuze_kick_webhook(request):
    """Handle Kick webhook events with Ed25519 signature verification"""
    try:
        # --- Verify Kick webhook signature ---
        message_id = request.headers.get('Kick-Event-Message-Id', '')
        timestamp = request.headers.get('Kick-Event-Message-Timestamp', '')
        signature_b64 = request.headers.get('Kick-Event-Signature', '')
        
        if not all([message_id, timestamp, signature_b64]):
            return JsonResponse({'error': 'Missing signature headers'}, status=401)
        
        # Get Kick's public key (cached for 1 hour)
        from django.core.cache import cache
        kick_public_key = cache.get('kick_webhook_public_key')
        if not kick_public_key:
            import requests as ext_requests
            try:
                resp = ext_requests.get('https://api.kick.com/public/v1/public-key', timeout=5)
                resp.raise_for_status()
                kick_public_key = resp.json().get('data', {}).get('public_key', '')
                if kick_public_key:
                    cache.set('kick_webhook_public_key', kick_public_key, 3600)
            except Exception as e:
                print(f'[KICK] Failed to fetch public key: {e}')
                return JsonResponse({'error': 'Cannot verify signature'}, status=500)
        
        if not kick_public_key:
            return JsonResponse({'error': 'No public key available'}, status=500)
        
        # Verify Ed25519 signature: sign(message_id + timestamp + body)
        import base64
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        from cryptography.exceptions import InvalidSignature
        
        try:
            body_bytes = request.body
            signed_content = (message_id + timestamp).encode('utf-8') + body_bytes
            signature_bytes = base64.b64decode(signature_b64)
            
            # Load the public key (PEM format from Kick API)
            if kick_public_key.startswith('-----'):
                public_key = load_pem_public_key(kick_public_key.encode('utf-8'))
            else:
                # Raw base64-encoded key
                key_bytes = base64.b64decode(kick_public_key)
                public_key = Ed25519PublicKey.from_public_bytes(key_bytes)
            
            public_key.verify(signature_bytes, signed_content)
        except (InvalidSignature, Exception) as e:
            print(f'[KICK] Webhook signature verification failed: {e}')
            return JsonResponse({'error': 'Invalid signature'}, status=403)
        # --- End signature verification ---
        
        event_type = request.headers.get('Kick-Event-Type', '')
        data = json.loads(request.body)
        
        # Follow event
        if event_type == 'channel.followed':
            follower_username = data.get('follower', {}).get('username', 'Someone')
            broadcaster_id = data.get('broadcaster', {}).get('user_id')
            
            try:
                conn = PlatformConnection.objects.get(platform='kick', platform_user_id=str(broadcaster_id))
                send_alert(conn.user_id, 'follow', 'kick', {'username': follower_username})
                print(f'[KICK] Webhook follow: {follower_username}')
            except PlatformConnection.DoesNotExist:
                print(f'[KICK] No connection for broadcaster {broadcaster_id}')
        
        # New subscription event
        elif event_type == 'channel.subscription.new':
            subscriber_username = data.get('subscriber', {}).get('username', 'Someone')
            broadcaster_id = data.get('broadcaster', {}).get('user_id')
            
            try:
                conn = PlatformConnection.objects.get(platform='kick', platform_user_id=str(broadcaster_id))
                send_alert(conn.user_id, 'subscribe', 'kick', {'username': subscriber_username})
                print(f'[KICK] Webhook sub: {subscriber_username}')
            except PlatformConnection.DoesNotExist:
                print(f'[KICK] No connection for broadcaster {broadcaster_id}')
        
        # Gift subscription event
        elif event_type == 'channel.subscription.gifts':
            gifter = data.get('gifter', {})
            gifter_username = gifter.get('username') if not gifter.get('is_anonymous') else 'Anonymous'
            giftees = data.get('giftees', [])
            gift_count = len(giftees)
            broadcaster_id = data.get('broadcaster', {}).get('user_id')
            
            try:
                conn = PlatformConnection.objects.get(platform='kick', platform_user_id=str(broadcaster_id))
                send_alert(conn.user_id, 'gift_sub', 'kick', {
                    'username': gifter_username,
                    'amount': gift_count
                })
                print(f'[KICK] Webhook gift sub: {gifter_username} gifted {gift_count}')
            except PlatformConnection.DoesNotExist:
                print(f'[KICK] No connection for broadcaster {broadcaster_id}')
        
        return JsonResponse({'status': 'ok'}, status=200)
    
    except Exception as e:
        print(f'[KICK] Webhook error: {e}')
        logger.error(f'Server error: {e}'); return JsonResponse({'error': 'Internal error'}, status=500)

# =========== TIKTOK ALERTS ===========
@csrf_exempt
def fuze_tiktok_start_listener(request, user_id):
    """Start TikTok listener - needs username only"""
    if not verify_widget_request(request, user_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        conn = PlatformConnection.objects.get(user_id=user_id, platform='tiktok')
        tiktok_username = conn.platform_username  # Store @username when connecting
        started = start_tiktok_listener(user_id, tiktok_username)
        return JsonResponse({'started': started})
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'error': 'Not connected'}, status=404)
    except Exception as e:
        logger.error(f'Server error: {e}'); return JsonResponse({'error': 'Internal error'}, status=500)
    
# =========== CHATBOX ===========  
@csrf_exempt
@require_http_methods(["GET"])
def fuze_twitch_chat_start(request, user_id):
    """Start Twitch chat IRC using user's OAuth token"""
    if not verify_widget_request(request, user_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        user = User.objects.get(id=user_id)
        conn = PlatformConnection.objects.get(user=user, platform='twitch')
        
        # Refresh token if expired
        if conn.expires_at and conn.expires_at < timezone.now():
            # Twitch token refresh
            resp = requests.post('https://id.twitch.tv/oauth2/token', data={
                'client_id': settings.TWITCH_CLIENT_ID,
                'client_secret': settings.TWITCH_CLIENT_SECRET,
                'grant_type': 'refresh_token',
                'refresh_token': conn.refresh_token
            })
            if resp.status_code == 200:
                data = resp.json()
                conn.access_token = data['access_token']
                conn.refresh_token = data.get('refresh_token', conn.refresh_token)
                conn.expires_at = timezone.now() + timedelta(seconds=data['expires_in'])
                conn.save()

        started = start_twitch_chat(conn.platform_username, user_id, conn.access_token)
        
        return JsonResponse({'started': started})
    except Exception as e:
        logger.error(f'Request error: {e}'); return JsonResponse({'error': 'Bad request'}, status=400)
    
@csrf_exempt
def fuze_kick_chat_start(request, user_id):
    """Start Kick chat listener"""
    if not verify_widget_request(request, user_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        user = User.objects.get(id=user_id)
        conn = PlatformConnection.objects.get(user=user, platform='kick')
        started = start_kick_chat(conn.platform_username, user_id, conn.access_token)
        return JsonResponse({'started': started})
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'started': False, 'error': 'Not connected'})
    except Exception as e:
        print(f'[KICK CHAT] Error: {e}')
        logger.error(f'Request error: {e}'); return JsonResponse({'error': 'Bad request'}, status=400)

@csrf_exempt
def fuze_facebook_chat_start(request, user_id):
    """Start Facebook chat polling"""
    if not verify_widget_request(request, user_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    try:
        user = User.objects.get(id=user_id)
        conn = PlatformConnection.objects.get(user=user, platform='facebook')
        started = start_facebook_chat(user_id, conn.platform_user_id, conn.access_token)
        return JsonResponse({'started': started})
    except PlatformConnection.DoesNotExist:
        return JsonResponse({'started': False, 'error': 'Not connected'})
    except Exception as e:
        print(f'[FB CHAT] Error: {e}')
        logger.error(f'Request error: {e}'); return JsonResponse({'error': 'Bad request'}, status=400)
    
# =========== LABELS ===========    
@csrf_exempt
def fuze_get_label_data(request, user_id):
    """Get persisted label session data for widget reload"""
    if not verify_widget_request(request, user_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    from .models import LabelSessionData
    
    data = {}
    for item in LabelSessionData.objects.filter(user_id=user_id):
        data[item.label_type] = item.data
    return JsonResponse({'data': data})


@csrf_exempt
def fuze_save_label_data(request, user_id):
    """Save label data when events occur - called from widget JS"""
    if not verify_widget_request(request, user_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)
    from .models import LabelSessionData
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    
    try:
        body = json.loads(request.body)
        label_type = body.get('label_type')
        data = body.get('data', {})
        
        if not label_type:
            return JsonResponse({'error': 'label_type required'}, status=400)
        
        LabelSessionData.objects.update_or_create(
            user_id=user_id,
            label_type=label_type,
            defaults={'data': data}
        )
        return JsonResponse({'saved': True})
    except Exception as e:
        logger.error(f'Server error: {e}'); return JsonResponse({'error': 'Internal error'}, status=500)
    
# =========== VIEWER COUNT ===========
# Factory pattern - replaces 5 identical functions
def _viewer_endpoint(platform: str):
    """Factory for viewer count endpoints"""
    from .views_helpers import get_platform_viewer_count
    
    @csrf_exempt
    @require_http_methods(["GET"])
    def endpoint(request, user_id):
        if not verify_widget_request(request, user_id):
            return JsonResponse({'error': 'Unauthorized'}, status=403)
        return JsonResponse({'viewers': get_platform_viewer_count(user_id, platform)})
    return endpoint

fuze_get_twitch_viewers = _viewer_endpoint('twitch')
fuze_get_youtube_viewers = _viewer_endpoint('youtube')
fuze_get_kick_viewers = _viewer_endpoint('kick')
fuze_get_facebook_viewers = _viewer_endpoint('facebook')
fuze_get_tiktok_viewers = _viewer_endpoint('tiktok')

# ====== REVIEWS ======

@csrf_exempt
@require_http_methods(["POST"])
def fuze_submit_review(request):
    """Submit a review (requires auth)"""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return JsonResponse({'success': False, 'error': 'Authentication required'}, status=401)
    
    token = auth_header.split(' ')[1]
    result = auth_manager.verify_token(token)
    
    if not result.get('valid'):
        return JsonResponse({'success': False, 'error': 'Invalid token'}, status=401)
    
    try:
        user = User.objects.get(id=result['user_id'])
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    platform = data.get('platform', '').lower()
    rating = data.get('rating')
    review_text = data.get('review', '').strip()
    
    # Validation
    if platform not in ['twitch', 'youtube', 'kick', 'tiktok', 'facebook', 'other']:
        return JsonResponse({'success': False, 'error': 'Invalid platform'}, status=400)
    
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        return JsonResponse({'success': False, 'error': 'Rating must be 1-5'}, status=400)
    
    if not review_text or len(review_text) > 300:
        return JsonResponse({'success': False, 'error': 'Review must be 1-300 characters'}, status=400)
    
    # Profanity check
    from ACCOUNTS.validators import contains_profanity
    if contains_profanity(review_text):
        return JsonResponse({'success': False, 'error': 'Review contains inappropriate language'}, status=400)
    
    # Check if user already has a review
    from .models import FuzeReview
    existing = FuzeReview.objects.filter(user=user).first()
    if existing:
        # Update existing review
        existing.platform = platform
        existing.rating = rating
        existing.review = review_text
        existing.save()
        return JsonResponse({'success': True, 'message': 'Review updated'})
    
    # Create new review
    FuzeReview.objects.create(
        user=user,
        platform=platform,
        rating=rating,
        review=review_text
    )
    
    return JsonResponse({'success': True, 'message': 'Review submitted'})


@require_http_methods(["GET"])
def fuze_get_featured_reviews(request):
    """Get featured reviews for landing page (public)"""
    from .models import FuzeReview
    
    reviews = FuzeReview.objects.filter(featured=True).select_related('user')[:20]
    
    return JsonResponse({
        'success': True,
        'reviews': [{
            'username': r.user.username,
            'platform': r.platform,
            'rating': r.rating,
            'review': r.review,
            'profile_picture': r.user.profile_picture.url if r.user.profile_picture else None,
            'created_at': r.created_at.isoformat()
        } for r in reviews]
    })


# ====== REVIEWS ADMIN ======

@staff_member_required
def fuze_reviews_admin(request):
    """Admin page for managing reviews"""
    from .models import FuzeReview
    
    reviews = FuzeReview.objects.select_related('user').all()
    featured_count = reviews.filter(featured=True).count()
    
    return render(request, 'FUZE/fuze_reviews.html', {
        'reviews': reviews,
        'total_reviews': reviews.count(),
        'featured_count': featured_count,
        'avg_rating': reviews.aggregate(Avg('rating'))['rating__avg'] or 0,
    })

@csrf_exempt 
@staff_member_required
@require_http_methods(["POST"])
def fuze_toggle_review_featured(request):
    """Toggle featured status of a review"""
    from .models import FuzeReview
    
    try:
        data = json.loads(request.body)
        review_id = data.get('review_id')
        featured = data.get('featured', False)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    try:
        review = FuzeReview.objects.get(id=review_id)
        review.featured = featured
        review.save()
        return JsonResponse({'success': True})
    except FuzeReview.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Review not found'}, status=404)

@csrf_exempt 
@staff_member_required
@require_http_methods(["POST"])
def fuze_delete_review(request):
    """Delete a review"""
    from .models import FuzeReview
    
    try:
        data = json.loads(request.body)
        review_id = data.get('review_id')
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    try:
        review = FuzeReview.objects.get(id=review_id)
        review.delete()
        return JsonResponse({'success': True})
    except FuzeReview.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Review not found'}, status=404)

@csrf_exempt 
@staff_member_required
@require_http_methods(["POST"])
def fuze_create_review_admin(request):
    """Admin: Create a review manually"""
    from .models import FuzeReview
    
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    
    username = data.get('username')
    platform = data.get('platform', '').lower()
    rating = data.get('rating')
    review_text = data.get('review', '').strip()
    featured = data.get('featured', False)
    
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    
    # Check for existing review
    if FuzeReview.objects.filter(user=user).exists():
        return JsonResponse({'success': False, 'error': 'User already has a review'}, status=400)
    
    FuzeReview.objects.create(
        user=user,
        platform=platform,
        rating=rating,
        review=review_text,
        featured=featured
    )
    
    return JsonResponse({'success': True})

@csrf_exempt
@require_http_methods(["POST"])
@staff_member_required
def edit_review_admin(request):
    data = json.loads(request.body)
    try:
        review = FuzeReview.objects.get(id=data['review_id'])
        review.platform = data.get('platform', review.platform)
        review.rating = data.get('rating', review.rating)
        review.review = data.get('review', review.review)
        review.featured = data.get('featured', review.featured)
        review.save()
        return JsonResponse({'success': True})
    except FuzeReview.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Review not found'}, status=404)

@csrf_exempt
@require_http_methods(["GET"])
def my_review(request):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return JsonResponse({'success': False, 'error': 'Not authenticated'}, status=401)
    
    result = auth_manager.verify_token(token)
    if not result.get('valid'):
        return JsonResponse({'success': False, 'error': 'Invalid token'}, status=401)
    
    try:
        user = User.objects.get(id=result['user_id'])
        review = FuzeReview.objects.filter(user=user).first()
        if review:
            return JsonResponse({
                'success': True,
                'review': {
                    'platform': review.platform,
                    'rating': review.rating,
                    'review': review.review,
                    'featured': review.featured,
                }
            })
        else:
            return JsonResponse({'success': True, 'review': None})
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)

@csrf_exempt
@require_tier('free')
def fuze_countdown(request):
    user = request.fuze_user

    if request.method == 'GET':
        try:
            c = StreamCountdown.objects.get(user=user)
            result = {'success': True, 'countdown': None, 'schedule': None}
            if c.scheduled_at:
                result['countdown'] = {
                    'title': c.title,
                    'scheduled_at': c.scheduled_at.isoformat(),
                    'platforms': c.platforms,
                }
            if c.schedule_days:
                result['schedule'] = {
                    'title': c.title,
                    'days': c.schedule_days,
                    'time': c.schedule_time,
                    'platforms': c.platforms,
                }
            return JsonResponse(result)
        except StreamCountdown.DoesNotExist:
            return JsonResponse({'success': True, 'countdown': None, 'schedule': None})

    elif request.method == 'POST':
        data = json.loads(request.body)
        defaults = {
            'title': data.get('title', ''),
            'platforms': data.get('platforms', []),
        }

        # Recurring schedule
        if data.get('schedule_days'):
            defaults['schedule_days'] = data['schedule_days']
            defaults['schedule_time'] = data.get('schedule_time', '')
            defaults['scheduled_at'] = None
        # One-time countdown
        elif data.get('scheduled_at'):
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(data['scheduled_at'])
            if not dt:
                return JsonResponse({'error': 'Invalid datetime'}, status=400)
            defaults['scheduled_at'] = dt
            defaults['schedule_days'] = []
            defaults['schedule_time'] = ''
        else:
            return JsonResponse({'error': 'scheduled_at or schedule_days required'}, status=400)

        c, _ = StreamCountdown.objects.update_or_create(user=user, defaults=defaults)

        result = {'success': True, 'countdown': None, 'schedule': None}
        if c.scheduled_at:
            result['countdown'] = {
                'title': c.title,
                'scheduled_at': c.scheduled_at.isoformat(),
                'platforms': c.platforms,
            }
        if c.schedule_days:
            result['schedule'] = {
                'title': c.title,
                'days': c.schedule_days,
                'time': c.schedule_time,
                'platforms': c.platforms,
            }
        return JsonResponse(result)

    elif request.method == 'DELETE':
        StreamCountdown.objects.filter(user=user).delete()
        return JsonResponse({'success': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)


# ============ COLLAB FINDER ============
def _get_profile_pic_url(user):
    """Get full profile picture URL"""
    if hasattr(user, 'profile_picture') and user.profile_picture:
        return f'https://bomby.us{user.profile_picture.url}'
    return None

@csrf_exempt
def collab_posts(request):
    """List collab posts (GET, anonymous OK) or create one (POST, auth required)"""
    
    if request.method == 'GET':
        # Optional auth for is_interested/is_owner
        user = None
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            user = get_user_from_token(auth_header[7:])
        
        status_filter = request.GET.get('status', 'open')
        posts = CollabPost.objects.select_related('user').filter(status=status_filter)
        
        # Exclude expired posts from public listing
        posts = posts.filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())
        )
        
        user_interests = set()
        if user:
            user_interests = set(
                CollabInterest.objects.filter(user=user).values_list('post_id', flat=True)
            )
        
        results = []
        for post in posts[:50]:
            results.append({
                'id': post.id,
                'title': post.title,
                'description': post.description[:150] + ('...' if len(post.description) > 150 else ''),
                'full_description': post.description,
                'category': post.category,
                'platforms': post.platforms,
                'tags': post.tags,
                'collab_size': post.collab_size,
                'availability': post.availability,
                'status': post.status,
                'interested_count': post.interested_count,
                'is_interested': post.id in user_interests,
                'is_owner': (user is not None and post.user_id == user.id),
                'username': post.user.username,
                'profile_picture': _get_profile_pic_url(post.user),
                'created_at': post.created_at.isoformat(),
                'expires_at': post.expires_at.isoformat() if post.expires_at else None,
            })
        
        return JsonResponse({'success': True, 'posts': results})
    
    elif request.method == 'POST':
        # POST requires auth
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return JsonResponse({'error': 'Login required'}, status=401)
        user = get_user_from_token(auth_header[7:])
        if not user:
            return JsonResponse({'error': 'Invalid token'}, status=401)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        
        title = data.get('title', '').strip()
        description = data.get('description', '').strip()
        category = data.get('category', '')
        platforms = data.get('platforms', [])
        tags = data.get('tags', [])
        collab_size = data.get('collab_size', 'duo')
        availability = data.get('availability', '').strip()
        
        if not title or len(title) > 50:
            return JsonResponse({'success': False, 'error': 'Title required (max 50 chars)'}, status=400)
        if not description or len(description) > 200:
            return JsonResponse({'success': False, 'error': 'Description required (max 200 chars)'}, status=400)
        
        valid_categories = [c[0] for c in CollabPost.CATEGORY_CHOICES]
        if category not in valid_categories:
            return JsonResponse({'success': False, 'error': 'Invalid category'}, status=400)
        
        valid_platforms = ['twitch', 'youtube', 'kick', 'facebook', 'tiktok']
        platforms = [p for p in platforms if p in valid_platforms]
        if not platforms:
            return JsonResponse({'success': False, 'error': 'At least one platform required'}, status=400)
        
        valid_sizes = [s[0] for s in CollabPost.SIZE_CHOICES]
        if collab_size not in valid_sizes:
            collab_size = 'duo'
        
        tags = [t.strip()[:30] for t in tags[:5] if t.strip()]
        
        from ACCOUNTS.validators import contains_profanity
        for field_name, field_val in [('Title', title), ('Description', description), ('Availability', availability)]:
            if field_val and contains_profanity(field_val):
                return JsonResponse({'success': False, 'error': f'{field_name} contains inappropriate language'}, status=400)
        for tag in tags:
            if contains_profanity(tag):
                return JsonResponse({'success': False, 'error': 'Tags contain inappropriate language'}, status=400)
        
        active_count = CollabPost.objects.filter(user=user, status='open').count()
        if active_count >= 3:
            return JsonResponse({'success': False, 'error': 'Max 3 active posts allowed'}, status=400)
        
        post = CollabPost.objects.create(
            user=user,
            title=title,
            description=description,
            category=category,
            platforms=platforms,
            tags=tags,
            collab_size=collab_size,
            availability=availability,
            expires_at=timezone.now() + timedelta(days=30),
        )
        
        return JsonResponse({'success': True, 'post_id': post.id})
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
@require_tier('free')
def collab_post_detail(request, post_id):
    """Update post (PUT) or delete (DELETE) own post"""
    user = request.fuze_user
    
    try:
        post = CollabPost.objects.get(id=post_id)
    except CollabPost.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)
    
    if post.user_id != user.id:
        return JsonResponse({'success': False, 'error': 'Not your post'}, status=403)
    
    if request.method == 'PUT':
        data = json.loads(request.body)
        
        new_status = data.get('status')
        if new_status and new_status in ['open', 'filled', 'closed']:
            post.status = new_status
        
        if 'title' in data:
            title = data['title'].strip()
            if title and len(title) <= 50:
                post.title = title
        if 'description' in data:
            desc = data['description'].strip()
            if desc and len(desc) <= 200:
                post.description = desc
        if 'category' in data:
            valid_categories = [c[0] for c in CollabPost.CATEGORY_CHOICES]
            if data['category'] in valid_categories:
                post.category = data['category']
        if 'platforms' in data:
            valid_platforms = ['twitch', 'youtube', 'kick', 'facebook', 'tiktok']
            platforms = [p for p in data['platforms'] if p in valid_platforms]
            if platforms:
                post.platforms = platforms
        if 'tags' in data:
            post.tags = [t.strip()[:30] for t in data['tags'][:5] if t.strip()]
        if 'collab_size' in data:
            valid_sizes = [s[0] for s in CollabPost.SIZE_CHOICES]
            if data['collab_size'] in valid_sizes:
                post.collab_size = data['collab_size']
        if 'availability' in data:
            post.availability = data['availability'].strip()[:200]
        
        # Profanity check on all text fields
        from ACCOUNTS.validators import contains_profanity
        for field_name, field_val in [('Title', post.title), ('Description', post.description), ('Availability', post.availability)]:
            if field_val and contains_profanity(field_val):
                return JsonResponse({'success': False, 'error': f'{field_name} contains inappropriate language'}, status=400)
        for tag in post.tags:
            if contains_profanity(tag):
                return JsonResponse({'success': False, 'error': 'Tags contain inappropriate language'}, status=400)
        
        post.save()
        return JsonResponse({'success': True})
    
    elif request.method == 'DELETE':
        post.delete()
        return JsonResponse({'success': True})
    
    return JsonResponse({'error': 'Method not allowed'}, status=405)

@csrf_exempt
@require_tier('free')
def collab_interest(request, post_id):
    """Toggle interest on a collab post (POST)"""
    user = request.fuze_user
    
    try:
        post = CollabPost.objects.get(id=post_id)
    except CollabPost.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)
    
    if post.user_id == user.id:
        return JsonResponse({'success': False, 'error': 'Cannot express interest in your own post'}, status=400)
    
    existing = CollabInterest.objects.filter(post=post, user=user).first()
    if existing:
        existing.delete()
        post.interested_count = max(0, post.interested_count - 1)
        post.save()
        return JsonResponse({'success': True, 'interested': False, 'count': post.interested_count})
    else:
        CollabInterest.objects.create(post=post, user=user)
        post.interested_count += 1
        post.save()
        return JsonResponse({'success': True, 'interested': True, 'count': post.interested_count})

@csrf_exempt
@require_tier('free')
def collab_my_posts(request):
    """Get current user's collab posts"""
    user = request.fuze_user
    
    posts = CollabPost.objects.filter(user=user)
    results = []
    for post in posts:
        interested_users = []
        for interest in CollabInterest.objects.select_related('user').filter(post=post):
            interested_users.append({
                'user_id': interest.user.id,
                'username': interest.user.username,
                'profile_picture': _get_profile_pic_url(interest.user),
                'created_at': interest.created_at.isoformat(),
            })
        
        results.append({
            'id': post.id,
            'title': post.title,
            'description': post.description,
            'category': post.category,
            'platforms': post.platforms,
            'tags': post.tags,
            'collab_size': post.collab_size,
            'availability': post.availability,
            'status': post.status,
            'interested_count': post.interested_count,
            'interested_users': interested_users,
            'created_at': post.created_at.isoformat(),
            'expires_at': post.expires_at.isoformat() if post.expires_at else None,
        })
    
    return JsonResponse({'success': True, 'posts': results})

@csrf_exempt
@require_tier('free')
def collab_send_message(request):
    """Send a message to a user from collab finder"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    user = request.fuze_user
    data = json.loads(request.body)
    target_username = data.get('username', '').strip()
    content = data.get('message', '').strip()
    
    if not target_username or not content:
        return JsonResponse({'success': False, 'error': 'Username and message required'}, status=400)
    
    if len(content) > 500:
        return JsonResponse({'success': False, 'error': 'Message too long (max 500 chars)'}, status=400)
    
    from ACCOUNTS.validators import contains_profanity
    if contains_profanity(content):
        return JsonResponse({'success': False, 'error': 'Message contains inappropriate language'}, status=400)
    
    try:
        recipient = User.objects.get(username=target_username)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found'}, status=404)
    
    if recipient.id == user.id:
        return JsonResponse({'success': False, 'error': 'Cannot message yourself'}, status=400)
    
    # Find or create conversation
    conversation = Conversation.objects.filter(
        participants=user
    ).filter(
        participants=recipient
    ).first()
    
    if not conversation:
        conversation = Conversation.objects.create()
        conversation.participants.add(user, recipient)
    
    # Create message
    message = Message.objects.create(
        sender=user,
        recipient=recipient,
        content=content,
        conversation=conversation
    )
    
    conversation.last_message = message
    conversation.save()
    
    return JsonResponse({'success': True, 'message_id': message.id})

@csrf_exempt
@require_tier('free')
def collab_renew_post(request, post_id):
    """Renew a collab post for another 30 days"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    user = request.fuze_user
    
    try:
        post = CollabPost.objects.get(id=post_id)
    except CollabPost.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Post not found'}, status=404)
    
    if post.user_id != user.id:
        return JsonResponse({'success': False, 'error': 'Not your post'}, status=403)
    
    post.expires_at = timezone.now() + timedelta(days=30)
    post.status = 'open'
    post.save()
    
    return JsonResponse({'success': True, 'expires_at': post.expires_at.isoformat()})

# ============================ CREATOR CODES ============================
@staff_member_required
def fuze_creator_codes_view(request):
    from .models import CreatorCode, CreatorCodeUsage
    from django.db.models import Sum, Count

    codes = CreatorCode.objects.annotate(
        total_uses=Count('usages'),
        total_earned=Sum('usages__creator_earnings'),
        pending=Sum('usages__creator_earnings', filter=Q(usages__paid_out=False))
    ).order_by('-created_at')

    # Monthly breakdown for current month
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly = CreatorCodeUsage.objects.filter(created_at__gte=month_start).values(
        'code__code', 'code__creator_name'
    ).annotate(
        uses=Count('id'),
        earned=Sum('creator_earnings')
    ).order_by('-earned')

    return render(request, 'FUZE/fuze_creator_codes.html', {
        'codes': codes,
        'monthly': monthly,
        'month_name': now.strftime('%B %Y'),
    })

@staff_member_required
@require_http_methods(["POST"])
def fuze_creator_code_create(request):
    from .models import CreatorCode
    from django.contrib.auth import get_user_model
    data = parse_json_body(request)
    code = data.get('code', '').strip().upper()
    name = data.get('creator_name', '').strip()
    email = data.get('creator_email', '').strip()
    username = data.get('username', '').strip()

    if not code or not name:
        return JsonResponse({'success': False, 'error': 'Code and name required'})
    if CreatorCode.objects.filter(code=code).exists():
        return JsonResponse({'success': False, 'error': 'Code already exists'})

    user = None
    if username:
        try:
            user = get_user_model().objects.get(username=username)
        except get_user_model().DoesNotExist:
            return JsonResponse({'success': False, 'error': f'No user found with username "{username}"'})

    obj = CreatorCode.objects.create(code=code, creator_name=name, creator_email=email, user=user)
    return JsonResponse({
        'success': True,
        'id': obj.id,
        'code': obj.code,
        'creator_name': obj.creator_name,
        'linked_username': user.username if user else None
    })

@staff_member_required
@require_http_methods(["POST"])
def fuze_creator_code_toggle(request):
    from .models import CreatorCode
    data = parse_json_body(request)
    obj = CreatorCode.objects.get(id=data['id'])
    obj.is_active = not obj.is_active
    obj.save()
    return JsonResponse({'success': True, 'is_active': obj.is_active})

@staff_member_required
@require_http_methods(["POST"])
def fuze_creator_code_delete(request):
    from .models import CreatorCode
    data = parse_json_body(request)
    CreatorCode.objects.filter(id=data['id']).delete()
    return JsonResponse({'success': True})

@staff_member_required
@require_http_methods(["POST"])
def fuze_creator_code_mark_paid(request):
    from .models import CreatorCode, CreatorCodeUsage
    from django.db.models import Sum
    data = parse_json_body(request)
    
    pending = CreatorCodeUsage.objects.filter(
        code_id=data['id'], paid_out=False
    ).aggregate(total=Sum('creator_earnings'))['total'] or 0
    
    if pending < 10:
        return JsonResponse({'success': False, 'error': f'Pending amount ${pending:.2f} is below the $10 minimum payout threshold.'})
    
    CreatorCodeUsage.objects.filter(code_id=data['id'], paid_out=False).update(paid_out=True)
    return JsonResponse({'success': True})

@require_http_methods(["GET"])
def fuze_validate_creator_code(request):
    from .models import CreatorCode
    code = request.GET.get('code', '').strip().upper()
    try:
        obj = CreatorCode.objects.get(code=code, is_active=True)
        return JsonResponse({'valid': True, 'creator_name': obj.creator_name})
    except CreatorCode.DoesNotExist:
        return JsonResponse({'valid': False})

@login_required
def fuze_my_creator_code(request):
    from .models import CreatorCode, CreatorCodeUsage
    from django.db.models import Sum, Count

    if request.user.is_staff:
        return redirect('FUZE:creator_codes')

    try:
        code = CreatorCode.objects.get(user=request.user)
    except CreatorCode.DoesNotExist:
        return render(request, 'FUZE/fuze_my_creator_code.html', {'no_code': True})

    monthly = CreatorCodeUsage.objects.filter(code=code).extra(
        select={'month': "DATE_TRUNC('month', created_at)"}
    ).values('month').annotate(uses=Count('id'), earned=Sum('creator_earnings')).order_by('-month')

    pending = code.pending_payout()
    total = code.total_earned()

    return render(request, 'FUZE/fuze_my_creator_code.html', {
        'code': code,
        'monthly': monthly,
        'pending': pending,
        'total': total,
    })