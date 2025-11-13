from google.cloud import storage
import hashlib

def generate_widget_html(user_id, widget_type, config):
    if widget_type == 'alert_box':
        return generate_alert_box_html(user_id, config)
    elif widget_type == 'chat_box':
        return generate_chat_box_html(user_id, config)
    elif widget_type == 'event_list':
        return generate_event_list_html(user_id, config)
    elif widget_type == 'goal_bar':
        return generate_goal_bar_html(user_id, config)
    raise ValueError(f"Unknown widget type: {widget_type}")

def generate_alert_box_html(user_id, config):
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
body{{margin:0;overflow:hidden;background:transparent;font-family:Arial}}
#c{{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);visibility:hidden;opacity:0}}
.s,.a{{display:flex;flex-direction:column;align-items:center;text-align:center;gap:20px}}
.l{{display:flex;flex-direction:row;align-items:center;gap:20px}}
.o{{position:relative;display:inline-block}}
.o .t{{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);width:90%;text-align:center}}
.i{{max-width:300px;display:block}}
.l .i{{max-width:200px}}
.o .i{{max-width:400px}}
@keyframes fadeIn{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes slideIn{{from{{opacity:0;transform:translateY(-100px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes bounceIn{{0%{{opacity:0;transform:scale(.3)}}50%{{transform:scale(1.05)}}70%{{transform:scale(.9)}}100%{{opacity:1;transform:scale(1)}}}}
@keyframes zoomIn{{from{{opacity:0;transform:scale(0)}}to{{opacity:1;transform:scale(1)}}}}
@keyframes fadeOut{{to{{opacity:0;visibility:hidden}}}}
@keyframes wiggle{{0%,100%{{transform:rotate(0)}}25%{{transform:rotate(-3deg)}}75%{{transform:rotate(3deg)}}}}
@keyframes wave{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-8px)}}}}
@keyframes bounce{{0%,100%{{transform:translateY(0)}}50%{{transform:translateY(-12px)}}}}
@keyframes pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.08)}}}}
</style></head><body>
<div id="c"></div><audio id="s"></audio>
<script>
console.log('🟢 NEW WIDGET v4.0 - NO POLLING');
const ws=new WebSocket('wss://bomby.us/ws/fuzeobs-alerts/{user_id}');
let to;
ws.onmessage=e=>{{
  const a=JSON.parse(e.data);
  if(!a.config||!a.config.enabled)return;
  const c=a.config,d=a.event_data||{{}};
  let m=(c.message_template||'{{{{name}}}} just followed!').replace(/{{{{name}}}}/g,d.username||'Someone').replace(/{{{{amount}}}}/g,d.amount||'');
  const ly=c.layout||'standard';
  let h='';
  if(ly==='text_over_image'&&c.image_url){{
    h=`<div class="o"><img class="i" src="${{c.image_url}}"><div class="t">${{m}}</div></div>`;
  }}else{{
    const cls=ly==='standard'?'s':ly==='image_above'?'a':ly==='image_left'?'l':'s';
    h=`<div class="${{cls}}">`;
    if(c.image_url)h+=`<img class="i" src="${{c.image_url}}">`;
    h+=`<div class="t">${{m}}</div></div>`;
  }}
  const ct=document.getElementById('c');
  ct.innerHTML=h;
  const tx=ct.querySelector('.t');
  tx.style.fontSize=(c.font_size||32)+'px';
  tx.style.fontWeight=c.font_weight||'normal';
  tx.style.color=c.text_color||'#FFF';
  tx.style.textShadow=c.text_shadow!==false?'2px 2px 4px rgba(0,0,0,0.8)':'none';
  const ta=c.text_animation||'none';
  if(ta!=='none')tx.style.animation=ta+' 1s infinite';
  const aa=c.alert_animation||'fade';
  ct.style.cssText='animation:'+aa+'In 0.5s forwards;visibility:visible';
  if(c.sound_url){{
    const au=document.getElementById('s');
    au.src=c.sound_url;
    au.volume=(c.sound_volume||50)/100;
    au.play().catch(()=>{{}});
  }}
  if(to)clearTimeout(to);
  to=setTimeout(()=>{{ct.style.animation='fadeOut 0.5s forwards'}},(c.duration||5)*1000);
}};
ws.onerror=e=>console.error('WS Error:',e);
ws.onopen=()=>console.log('WS Connected');
</script></body></html>"""

def generate_chat_box_html(user_id, config):
    h=config.get('height',400)
    bg=config.get('bg_color','rgba(0,0,0,0.5)')
    tc=config.get('text_color','#FFFFFF')
    uc=config.get('username_color','#00FF00')
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
body{{background:transparent;margin:0;overflow:hidden;font-family:Arial}}
.cc{{max-height:{h}px;overflow-y:auto;padding:10px}}
.cc::-webkit-scrollbar{{width:8px}}
.cc::-webkit-scrollbar-track{{background:rgba(0,0,0,0.3)}}
.cc::-webkit-scrollbar-thumb{{background:rgba(255,255,255,0.3);border-radius:4px}}
.m{{padding:8px;margin:4px 0;background:{bg};border-radius:4px;color:{tc};word-wrap:break-word}}
.u{{color:{uc};font-weight:bold;margin-right:5px}}
</style></head><body>
<div class="cc" id="ch"></div>
<script>
const ws=new WebSocket('wss://bomby.us/ws/fuzeobs-chat/{user_id}');
ws.onmessage=e=>{{
  const d=JSON.parse(e.data);
  const m=document.createElement('div');
  m.className='m';
  m.innerHTML=`<span class="u">${{d.username}}:</span>${{d.message}}`;
  const ch=document.getElementById('ch');
  ch.appendChild(m);
  ch.scrollTop=ch.scrollHeight;
  while(ch.children.length>50)ch.removeChild(ch.firstChild);
}};
</script></body></html>"""

def generate_event_list_html(user_id, config):
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
body{{background:transparent;margin:0;padding:10px;font-family:Arial;color:white}}
.e{{background:rgba(0,0,0,0.7);padding:10px;margin:5px 0;border-radius:5px;display:flex;align-items:center;animation:slideInLeft 0.3s ease-out}}
@keyframes slideInLeft{{from{{transform:translateX(-100%);opacity:0}}to{{transform:translateX(0);opacity:1}}}}
.ei{{font-size:24px;margin-right:10px}}
.et{{flex:1}}
</style></head><body>
<div id="ev"></div>
<script>
const ws=new WebSocket('wss://bomby.us/ws/fuzeobs-events/{user_id}');
ws.onmessage=e=>{{
  const d=JSON.parse(e.data);
  const ev=document.createElement('div');
  ev.className='e';
  ev.innerHTML=`<div class="ei">${{getIcon(d.type)}}</div><div class="et">${{d.username}} ${{d.action}}</div>`;
  const ct=document.getElementById('ev');
  ct.insertBefore(ev,ct.firstChild);
  while(ct.children.length>10)ct.removeChild(ct.lastChild);
}};
function getIcon(t){{const i={{'follow':'❤️','subscribe':'⭐','bits':'💎','donation':'💰','raid':'💥'}};return i[t]||'🎉'}}
</script></body></html>"""

def generate_goal_bar_html(user_id, config):
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
body{{background:transparent;margin:0;padding:20px;font-family:Arial}}
.gc{{background:rgba(0,0,0,0.8);padding:15px;border-radius:10px}}
.gt{{color:white;font-size:18px;margin-bottom:10px;text-align:center}}
.pb{{background:rgba(255,255,255,0.2);height:30px;border-radius:15px;overflow:hidden}}
.pf{{background:linear-gradient(90deg,#00ff00,#00cc00);height:100%;transition:width 0.5s ease;display:flex;align-items:center;justify-content:center;color:white;font-weight:bold}}
</style></head><body>
<div class="gc">
  <div class="gt" id="ti">Loading...</div>
  <div class="pb"><div class="pf" id="pr" style="width:0%"><span id="pt">0%</span></div></div>
</div>
<script>
const ws=new WebSocket('wss://bomby.us/ws/fuzeobs-goals/{user_id}');
ws.onmessage=e=>{{
  const d=JSON.parse(e.data);
  document.getElementById('ti').textContent=d.title;
  const p=(d.current/d.goal)*100;
  document.getElementById('pr').style.width=p+'%';
  document.getElementById('pt').textContent=`${{d.current}}/${{d.goal}} (${{Math.round(p)}}%)`;
}};
</script></body></html>"""

def upload_to_gcs(html_content, user_id, widget_type):
    client=storage.Client()
    bucket=client.bucket('fuzeobs-public')
    hash_id=hashlib.md5(f"{user_id}{widget_type}{html_content[:100]}".encode()).hexdigest()[:8]
    blob_name=f'fuzeobs-widgets/{user_id}/{widget_type}_{hash_id}.html'
    blob=bucket.blob(blob_name)
    blob.upload_from_string(html_content,content_type='text/html')
    blob.make_public()
    return blob.public_url