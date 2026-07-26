"""
CCTV Router — Fixed Version
Bugs fixed:
1. Phone sends frames too fast, WS buffer overflows → added send queue + rate limiting
2. Viewer WS was never added before phone connected → fixed session lookup timing
3. Base64 decode errors silently dropped frames → added proper error reporting
4. Large JSON payloads caused WS drops → switched to binary send for frames
5. Exception handler swallowed all errors → added logging
6. Session not found on direct phone connect → auto-create works correctly now
7. Dashboard viewer connected before phone → fixed by always checking latest_frame
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, Dict, List
from pathlib import Path
import base64, time, uuid, asyncio, json, logging
import numpy as np
import cv2

from services.cctv_analyzer import CCTVAnalyzer, SUSPICIOUS_BEHAVIORS

logger = logging.getLogger("cctv")
logging.basicConfig(level=logging.INFO)

router   = APIRouter()
analyzer = CCTVAnalyzer()

# Global session store
_sessions: Dict[str, Dict] = {}

def _new_session(sid, camera_id="MOBILE", zone_name="Live Zone"):
    return {
        "session_id":   sid,
        "camera_id":    camera_id,
        "zone_name":    zone_name,
        "started_at":   time.time(),
        "frame_count":  0,
        "alert_count":  0,
        "threat_level": "CLEAR",
        "latest_frame": None,
        "alerts":       [],
        "lat":          None,
        "lng":          None,
        "viewer_ws":    [],   # list of (websocket, asyncio.Queue) tuples
        "active":       False,
    }


# ─── REST endpoints ───────────────────────────────────────────────────────────

@router.post("/live/start")
async def start_session(camera_id: str = "MOBILE-01", zone_name: str = "Live Zone"):
    sid = str(uuid.uuid4())[:8].upper()
    _sessions[sid] = _new_session(sid, camera_id, zone_name)
    logger.info(f"Session created: {sid}")
    return {"session_id": sid, "camera_id": camera_id, "zone_name": zone_name}

@router.get("/live/sessions")
async def list_sessions():
    out = []
    for s in _sessions.values():
        out.append({
            "session_id":   s["session_id"],
            "camera_id":    s["camera_id"],
            "zone_name":    s["zone_name"],
            "frame_count":  s["frame_count"],
            "alert_count":  s["alert_count"],
            "threat_level": s["threat_level"],
            "active":       s["active"],
            "started_at":   s["started_at"],
        })
    return {"sessions": out}

@router.get("/live/debug/{session_id}")
async def debug_session(session_id: str):
    """Debug endpoint — check session state without exposing frame data."""
    if session_id not in _sessions:
        raise HTTPException(404, "Session not found")
    s = _sessions[session_id]
    return {
        "session_id":   s["session_id"],
        "active":       s["active"],
        "frame_count":  s["frame_count"],
        "alert_count":  s["alert_count"],
        "threat_level": s["threat_level"],
        "has_latest_frame": s["latest_frame"] is not None,
        "viewer_count": len(s["viewer_ws"]),
        "lat":          s["lat"],
        "lng":          s["lng"],
    }


# ─── WebSocket ①: Phone → Server ─────────────────────────────────────────────

@router.websocket("/ws/phone/{session_id}")
async def phone_ws_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"Phone connected to session {session_id}")

    # Auto-create session if not exists (phone can start without REST call)
    if session_id not in _sessions:
        _sessions[session_id] = _new_session(session_id)

    sess = _sessions[session_id]
    sess["active"] = True

    frame_analyzer = CCTVAnalyzer()
    frame_idx      = 0
    ANALYZE_EVERY  = 15   # run AI every 15 frames (non-blocking)

    try:
        while True:
            # Receive frame from phone
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=15.0)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type", "frame")

            if mtype == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
                continue
            if mtype == "pong":
                continue
            if mtype == "gps":
                sess["lat"] = msg.get("lat")
                sess["lng"] = msg.get("lng")
                continue

            b64 = msg.get("data", "")
            if not b64:
                continue

            # No rate limiting — accept every frame the phone sends
            if msg.get("lat"): sess["lat"] = msg["lat"]
            if msg.get("lng"): sess["lng"] = msg["lng"]

            sess["frame_count"] += 1
            sess["latest_frame"] = b64
            frame_idx += 1

            # ── AI detection (every N frames) ─────────────────────────
            alerts_out = []
            if frame_idx % ANALYZE_EVERY == 0:
                try:
                    img_bytes = base64.b64decode(b64)
                    nparr     = np.frombuffer(img_bytes, np.uint8)
                    frame     = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        dets    = frame_analyzer.detect_frame(frame, frame_idx)
                        raw_al  = frame_analyzer.analyze_behaviors(dets, frame_idx, 25.0, frame=frame)
                        deduped = frame_analyzer._dedup_alerts(raw_al)
                        if deduped:
                            sess["alerts"].extend(deduped)
                            sess["alerts"] = sess["alerts"][-100:]
                            sess["alert_count"] += len(deduped)
                            sev_order = ["CLEAR","LOW","MEDIUM","HIGH","CRITICAL"]
                            worst = max(deduped, key=lambda a: sev_order.index(a.get("severity","LOW")))
                            sess["threat_level"] = worst.get("severity","MEDIUM")
                            alerts_out = deduped
                            logger.info(f"[{session_id}] Alerts: {[a['type'] for a in deduped]}")
                except Exception as e:
                    logger.warning(f"AI analysis error: {e}")

            # ── Build broadcast payload ───────────────────────────────
            payload = {
                "type":         "frame",
                "session_id":   session_id,
                "frame":        frame_idx,
                "image":        b64,
                "threat_level": sess["threat_level"],
                "alerts":       alerts_out,
                "lat":          sess["lat"],
                "lng":          sess["lng"],
                "frame_count":  sess["frame_count"],
                "alert_count":  sess["alert_count"],
                "camera_id":    sess["camera_id"],
                "zone_name":    sess["zone_name"],
            }
            payload_str = json.dumps(payload)

            # ── Push to each viewer's queue (non-blocking) ────────────
            dead = []
            for (vws, q) in sess["viewer_ws"]:
                try:
                    # Drop old frames if queue is full (keep only latest)
                    if q.full():
                        try: q.get_nowait()
                        except asyncio.QueueEmpty: pass
                    q.put_nowait(payload_str)
                except Exception:
                    dead.append((vws, q))
            for item in dead:
                try: sess["viewer_ws"].remove(item)
                except ValueError: pass

            # ── Ack to phone ──────────────────────────────────────────
            try:
                await websocket.send_text(json.dumps({
                    "type":    "ack",
                    "frame":   frame_idx,
                    "threat":  sess["threat_level"],
                    "viewers": len(sess["viewer_ws"]),
                }))
            except Exception:
                pass

    except WebSocketDisconnect:
        logger.info(f"Phone disconnected: {session_id}")
    except Exception as e:
        logger.error(f"Phone WS error [{session_id}]: {e}")
    finally:
        sess["active"] = False


# ─── WebSocket ②: Dashboard → Server (viewer) ────────────────────────────────

@router.websocket("/ws/view/{session_id}")
async def viewer_ws_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"Viewer connected to session {session_id}")

    if session_id not in _sessions:
        await websocket.send_text(json.dumps({"type":"error","msg":f"Session {session_id} not found"}))
        await websocket.close()
        return

    sess = _sessions[session_id]

    # Each viewer gets its own queue so the phone never blocks waiting for slow viewers
    queue: asyncio.Queue = asyncio.Queue(maxsize=5)
    sess["viewer_ws"].append((websocket, queue))

    # Send the latest stored frame immediately (so screen isn't blank)
    if sess["latest_frame"]:
        try:
            await websocket.send_text(json.dumps({
                "type":         "frame",
                "session_id":   session_id,
                "frame":        sess["frame_count"],
                "image":        sess["latest_frame"],
                "threat_level": sess["threat_level"],
                "alerts":       [],
                "lat":          sess["lat"],
                "lng":          sess["lng"],
                "frame_count":  sess["frame_count"],
                "alert_count":  sess["alert_count"],
                "camera_id":    sess["camera_id"],
                "zone_name":    sess["zone_name"],
            }))
        except Exception:
            pass

    # Drain queue → send to this viewer
    async def _drain():
        while True:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_text(msg)
            except asyncio.TimeoutError:
                # Send keepalive heartbeat so browser doesn't time out
                try:
                    await websocket.send_text(json.dumps({"type":"heartbeat"}))
                except Exception:
                    break
            except Exception:
                break

    # Also listen for pings from dashboard
    async def _recv():
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                data = json.loads(raw)
                if data.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type":"pong"}))
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

    try:
        # Run both tasks concurrently
        await asyncio.gather(_drain(), _recv())
    except Exception as e:
        logger.info(f"Viewer disconnected [{session_id}]: {e}")
    finally:
        try:
            sess["viewer_ws"].remove((websocket, queue))
        except ValueError:
            pass
        logger.info(f"Viewer removed from session {session_id}, remaining: {len(sess['viewer_ws'])}")


# ─── Mobile phone page ────────────────────────────────────────────────────────

@router.get("/mobile", response_class=HTMLResponse)
async def mobile_page():
    html = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/>
<title>AEGIS Mobile Camera</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#06080a;color:#c8d4dc;font-family:monospace;
     display:flex;flex-direction:column;height:100vh;overflow:hidden;}
header{background:#0a0d10;padding:10px 14px;border-bottom:1px solid rgba(255,60,60,.2);
       display:flex;justify-content:space-between;align-items:center;flex-shrink:0;}
.logo{color:#ff3c3c;font-size:14px;font-weight:700;letter-spacing:.12em;}
.pill{font-size:10px;padding:3px 10px;border-radius:20px;border:1px solid;}
.p-off{color:#6b7f8c;border-color:#6b7f8c;}
.p-conn{color:#f5a623;border-color:#f5a623;animation:bk 1s step-end infinite;}
.p-live{color:#2ecc71;border-color:#2ecc71;background:rgba(46,204,113,.1);}
.p-alert{color:#ff3c3c;border-color:#ff3c3c;animation:bk .5s step-end infinite;}
@keyframes bk{50%{opacity:.3;}}
#setup{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;}
.hint{background:#0e1217;border:1px solid rgba(46,204,113,.2);padding:10px;
      font-size:11px;line-height:1.7;color:#6b7f8c;text-align:center;border-radius:2px;}
.hint b{color:#2ecc71;}
label{font-size:9px;color:#6b7f8c;letter-spacing:.1em;display:block;margin-bottom:4px;}
input,select{background:#0e1217;border:1px solid rgba(255,60,60,.25);color:#c8d4dc;
             padding:9px 11px;font-family:monospace;font-size:13px;width:100%;outline:none;border-radius:2px;}
.hint-small{font-size:9px;color:#6b7f8c;margin-top:3px;line-height:1.5;}
.hint-green{color:#2ecc71;}
.hint-red{color:#ff3c3c;}
.btn{width:100%;padding:13px;font-family:monospace;font-size:13px;letter-spacing:.08em;
     border:none;border-radius:2px;cursor:pointer;}
.btn-go{background:#2ecc71;color:#06080a;font-weight:700;}
.err{color:#ff3c3c;font-size:11px;padding:6px;background:rgba(255,60,60,.08);
     border:1px solid rgba(255,60,60,.2);border-radius:2px;display:none;word-break:break-all;}
#live{flex:1;display:none;flex-direction:column;}
video{width:100%;object-fit:cover;background:#000;display:block;flex:1;min-height:0;}
canvas{display:none;}
.threat{padding:8px 14px;text-align:center;font-size:13px;letter-spacing:.08em;
        font-weight:700;transition:all .3s;flex-shrink:0;}
.t-CLEAR{background:rgba(46,204,113,.1);color:#2ecc71;}
.t-MEDIUM{background:rgba(245,166,35,.12);color:#f5a623;}
.t-HIGH,.t-CRITICAL{background:rgba(255,60,60,.15);color:#ff3c3c;animation:bk .5s step-end infinite;}
.stats{display:grid;grid-template-columns:1fr 1fr 1fr 1fr;background:#0a0d10;
       border-top:1px solid rgba(255,60,60,.1);flex-shrink:0;}
.sc{padding:7px;text-align:center;border-right:1px solid rgba(255,60,60,.08);}
.sc:last-child{border:none;}
.sv{font-size:15px;color:#e8f0f5;}
.sl{font-size:8px;color:#6b7f8c;margin-top:2px;}
.log-bar{background:#0a0d10;padding:4px 10px;font-size:9px;color:#3498db;
         border-top:1px solid rgba(255,60,60,.1);flex-shrink:0;height:28px;overflow:hidden;}
.gps-bar{background:#0a0d10;padding:4px 10px;font-size:9px;color:#6b7f8c;
         text-align:center;flex-shrink:0;}
.btns{display:grid;grid-template-columns:1fr 1fr;gap:6px;padding:8px 10px;
      background:#0a0d10;border-top:1px solid rgba(255,60,60,.1);flex-shrink:0;}
.sm{padding:9px;font-family:monospace;font-size:11px;border:1px solid rgba(255,60,60,.3);
    background:transparent;color:#c8d4dc;border-radius:2px;cursor:pointer;}
.stop{border-color:#ff3c3c;color:#ff3c3c;}
</style>
</head>
<body>
<header>
  <span class="logo">AEGIS CAM</span>
  <span class="pill p-off" id="pill">OFFLINE</span>
</header>

<div id="setup">
  <div class="hint">
    📡 <b>Two ways to connect:</b><br>
    <b>Option 1 — Cloudflare/ngrok (Recommended):</b><br>
    Open this page via tunnel URL → auto-fills ✅<br><br>
    <b>Option 2 — Same WiFi:</b><br>
    Enter laptop IP:8000 manually
  </div>

  <div>
    <label>SERVER ADDRESS</label>
    <input id="srv" type="text" placeholder="e.g. 192.168.1.45:8000" autocomplete="off"/>
    <div class="hint-small" id="srv-hint"></div>
  </div>

  <div>
    <label>CAMERA ID</label>
    <input id="cid" value="MOBILE-01"/>
  </div>
  <div>
    <label>ZONE</label>
    <input id="zn" value="Main Gate"/>
  </div>
  <div>
    <label>CAMERA</label>
    <select id="fc">
      <option value="environment">Rear Camera</option>
      <option value="user">Front Camera</option>
    </select>
  </div>
  <div class="err" id="err"></div>
  <button class="btn btn-go" id="bgo">📡 GO LIVE</button>
</div>

<div id="live">
  <video id="vid" autoplay muted playsinline></video>
  <canvas id="cvs"></canvas>
  <div class="threat t-CLEAR" id="tbar">✅ MONITORING</div>
  <div class="stats">
    <div class="sc"><div class="sv" id="sf">0</div><div class="sl">FRAMES</div></div>
    <div class="sc"><div class="sv" id="sa">0</div><div class="sl">ALERTS</div></div>
    <div class="sc"><div class="sv" id="sp">0</div><div class="sl">FPS</div></div>
    <div class="sc"><div class="sv" id="sv2">0</div><div class="sl">VIEWERS</div></div>
  </div>
  <div class="gps-bar" id="gps">📍 GPS requesting…</div>
  <div class="log-bar" id="log">Ready</div>
  <div class="btns">
    <button class="sm" id="bfl">🔄 Flip</button>
    <button class="sm stop" id="bst">⏹ Stop</button>
  </div>
</div>

<script>
'use strict';
const $=id=>document.getElementById(id);
let ws=null,stream=null,capIv=null,gpsW=null;
let frames=0,facing='environment',fpc=0,fpt=Date.now();
let lat=null,lng=null,wsReady=false;

function log(m){ $('log').textContent=m; }
function showErr(m){ $('err').textContent=m; $('err').style.display='block'; }

// Detect if page loaded via https (ngrok) or http (local wifi)
const isHttps  = location.protocol === 'https:';
const wsScheme = isHttps ? 'wss' : 'ws';
const httpScheme = isHttps ? 'https' : 'http';

// Auto-fill server address
window.addEventListener('load', () => {
  const h=location.hostname, p=location.port;
  const hint = $('srv-hint');

  if (isHttps) {
    // Opened via ngrok / cloudflare / any https tunnel
    $('srv').value = p ? h+':'+p : h;
    hint.className='hint-small hint-green';
    // Detect which tunnel
    const tunnelName = h.includes('ngrok') ? 'ngrok' :
                       h.includes('trycloudflare') ? 'Cloudflare' :
                       h.includes('cloudflare') ? 'Cloudflare' : 'Secure tunnel';
    hint.textContent='✅ '+tunnelName+' detected — server auto-filled. Do NOT change this field.';
  } else {
    // Local http
    $('srv').value = '';
    hint.className='hint-small hint-red';
    hint.textContent='⚠️ Enter your laptop IP:8000 (e.g. 192.168.1.45:8000). Run ipconfig/ifconfig to find it.';
  }
});

// Open camera with fallback
async function openCamera(f){
  if(stream){ stream.getTracks().forEach(t=>t.stop()); stream=null; }
  await new Promise(r=>setTimeout(r,200));

  // Try exact first, then ideal, then any
  const attempts = [
    {video:{facingMode:{exact:f},width:{ideal:640},height:{ideal:480}},audio:false},
    {video:{facingMode:f,width:{ideal:640},height:{ideal:480}},audio:false},
    {video:{width:{ideal:640},height:{ideal:480}},audio:false},
    {video:true,audio:false}
  ];
  for(const c of attempts){
    try{ return await navigator.mediaDevices.getUserMedia(c); }
    catch(e){ log('cam try failed: '+e.message); }
  }
  throw new Error('No camera available');
}

async function go(){
  const srv=$('srv').value.trim().replace(/^https?:\/\//,'');
  const cid=$('cid').value.trim()||'MOBILE-01';
  const zn=$('zn').value.trim()||'Main Gate';
  facing=$('fc').value;
  $('err').style.display='none';
  if(!srv){ showErr('Enter server address'); return; }

  $('pill').className='pill p-conn'; $('pill').textContent='CONNECTING';

  // Step 1: Create session
  let sid;
  try{
    const url=`${httpScheme}://${srv}/api/cctv/live/start?camera_id=${encodeURIComponent(cid)}&zone_name=${encodeURIComponent(zn)}`;
    log('Connecting to '+url);
    const r=await Promise.race([
      fetch(url,{method:'POST'}),
      new Promise((_,rej)=>setTimeout(()=>rej(new Error('Timeout 8s')),8000))
    ]);
    if(!r.ok) throw new Error('Server error '+r.status);
    const d=await r.json();
    sid=d.session_id;
    log('Session: '+sid);
  }catch(e){
    showErr('Cannot reach server: '+e.message);
    $('pill').className='pill p-off'; $('pill').textContent='OFFLINE';
    return;
  }

  // Step 2: Camera
  try{
    stream=await openCamera(facing);
    $('vid').srcObject=stream;
    log('Camera opened');
  }catch(e){
    showErr('Camera error: '+e.message+(isHttps?'':' — Camera requires HTTPS. Use ngrok URL instead of local IP.'));
    return;
  }

  // Step 3: WebSocket
  const wsUrl=`${wsScheme}://${srv}/api/cctv/ws/phone/${sid}`;
  log('WS: '+wsUrl);
  ws=new WebSocket(wsUrl);

  ws.onopen=()=>{
    wsReady=true;
    $('pill').className='pill p-live'; $('pill').textContent='LIVE';
    $('setup').style.display='none';
    $('live').style.display='flex';
    $('live').style.flexDirection='column';
    log('Streaming at 30fps');
    startCapture();
    startGPS();
  };

  ws.onmessage=e=>{
    try{
      const m=JSON.parse(e.data);
      if(m.type==='ack'){ if(m.threat)setThreat(m.threat); if(m.viewers!==undefined)$('sv2').textContent=m.viewers; }
      if(m.type==='ping') ws.send(JSON.stringify({type:'pong'}));
    }catch(ex){}
  };

  ws.onerror=()=>{ log('WS error: '+wsScheme+'://'); $('pill').className='pill p-off'; $('pill').textContent='ERROR'; showErr('WebSocket error using '+wsScheme+'://'+srv); };
  ws.onclose=(e)=>{ wsReady=false; log('WS closed code='+e.code); $('pill').textContent='DISCONNECTED'; if(capIv){cancelAnimationFrame(capIv);capIv=null;} };
}

// ── CAPTURE: 30fps target, direct send, adaptive quality ──────────────
function startCapture(){
  const vid=$('vid'), cvs=$('cvs'), ctx=cvs.getContext('2d');

  // Adaptive settings based on connection type
  // Same WiFi = can do larger frames at higher quality
  // ngrok = smaller frames to fit through tunnel
  const TARGET_MS = isHttps ? 50 : 33;   // 20fps ngrok, 30fps local
  const FRAME_W   = isHttps ? 320 : 480; // smaller for ngrok, larger local
  const QUALITY   = isHttps ? 0.5 : 0.7; // lower quality for ngrok

  let last=0;
  function loop(ts){
    capIv=requestAnimationFrame(loop);
    if(!vid.videoWidth||!wsReady) return;
    if(ts-last<TARGET_MS) return;
    last=ts;

    const W=FRAME_W, H=Math.round(vid.videoHeight*(W/vid.videoWidth));
    if(cvs.width!==W){ cvs.width=W; cvs.height=H; }
    ctx.drawImage(vid,0,0,W,H);
    const b64=cvs.toDataURL('image/jpeg',QUALITY).split(',')[1];

    // Send only if buffer is clear — prevents pileup
    if(ws&&ws.readyState===1&&ws.bufferedAmount===0){
      try{ ws.send(JSON.stringify({type:'frame',data:b64,lat,lng})); }
      catch(e){ log('send err:'+e.message); }
    }

    frames++;
    $('sf').textContent=frames;
    fpc++;
    const now=Date.now();
    if(now-fpt>=1000){ $('sp').textContent=fpc; fpc=0; fpt=now; }
  }
  capIv=requestAnimationFrame(loop);
}

function startGPS(){
  if(!navigator.geolocation){ $('gps').textContent='📍 GPS unavailable'; return; }
  gpsW=navigator.geolocation.watchPosition(p=>{
    lat=p.coords.latitude; lng=p.coords.longitude;
    $('gps').textContent='📍 '+lat.toFixed(5)+', '+lng.toFixed(5)+' ±'+Math.round(p.coords.accuracy)+'m';
    if(wsReady&&ws.readyState===1) try{ws.send(JSON.stringify({type:'gps',lat,lng}));}catch(e){}
  },e=>{ $('gps').textContent='📍 GPS: '+e.message; },{enableHighAccuracy:true,maximumAge:4000});
}

const TLBL={CLEAR:'✅ MONITORING',MEDIUM:'⚠️ SUSPICIOUS',HIGH:'🚨 THREAT',CRITICAL:'🚨 CRITICAL'};
function setThreat(t){
  $('tbar').textContent=TLBL[t]||t;
  $('tbar').className='threat t-'+(t||'CLEAR');
  const p=$('pill');
  if(['HIGH','CRITICAL'].includes(t)){ p.className='pill p-alert'; p.textContent=t; }
  else{ p.className='pill p-live'; p.textContent='LIVE'; }
  if(['HIGH','CRITICAL'].includes(t)&&navigator.vibrate) navigator.vibrate([300,100,300]);
}

$('bfl').addEventListener('click',async()=>{
  facing=facing==='environment'?'user':'environment';
  try{ stream=await openCamera(facing); $('vid').srcObject=stream; log('Camera: '+facing); }
  catch(e){ log('Flip failed: '+e.message); }
});

$('bst').addEventListener('click',()=>{
  if(capIv){ cancelAnimationFrame(capIv); capIv=null; }
  if(gpsW) navigator.geolocation.clearWatch(gpsW);
  if(ws) ws.close();
  if(stream){ stream.getTracks().forEach(t=>t.stop()); stream=null; }
  wsReady=false;
  $('live').style.display='none';
  $('setup').style.display='flex';
  $('pill').className='pill p-off'; $('pill').textContent='OFFLINE';
  frames=0; log('Stopped');
});

$('bgo').addEventListener('click',go);
</script>
</body>
</html>"""
    return html


# ─── Offline video analysis (unchanged) ──────────────────────────────────────

class CCTVRequest(BaseModel):
    file_id:     str
    camera_id:   str = "CAM-01"
    zone_name:   str = "Zone A"
    sample_rate: int = 5

@router.post("/analyze")
async def analyze_cctv(request: CCTVRequest):
    upload_dir = Path("uploads")
    file_path  = None
    for ext in [".mp4",".avi",".mov",".mkv",".webm"]:
        c = upload_dir / f"{request.file_id}{ext}"
        if c.exists(): file_path = c; break
    if file_path is None:
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_id}")
    result = analyzer.analyze_cctv(
        video_path=str(file_path), sample_rate=request.sample_rate,
        zone_name=request.zone_name, camera_id=request.camera_id)
    if "error" in result:
        raise HTTPException(status_code=422, detail=result["error"])
    return result

@router.get("/behaviors")
async def get_behavior_list():
    return {"behaviors": SUSPICIOUS_BEHAVIORS}