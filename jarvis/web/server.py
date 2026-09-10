"""سرورِ FastAPI برای داشبوردِ محلیِ جارویس."""

from __future__ import annotations

import datetime

from ..config import Config
from ..logging_setup import get_logger
from ..state import STATE

log = get_logger("web")

_cfg: Config | None = None


def available() -> bool:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        return True
    except Exception:
        return False


def _status_payload() -> dict:
    with STATE.lock:
        s = STATE
        data = {
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "cpu": round(s.cpu_percent, 1),
            "ram": round(s.ram_percent, 1),
            "battery": s.battery_percent,
            "camera": s.camera_enabled,
            "voice": s.voice_enabled,
            "telegram": s.telegram_enabled,
            "conversation": s.conversation_active,
            "speaking": s.speaking,
            "subtitle": s.current_subtitle,
            "last_heard": s.last_heard_text,
            "weather_temp": s.weather_temp,
            "location": s.location_name,
            "secondary_temp": s.secondary_temp,
            "secondary_name": s.secondary_name,
            "events": [f"[{t}] {x}" for t, x in list(s.event_log)[-8:]],
        }
    try:
        from ..memory.store import get_store
        data["memory"] = get_store().stats()
    except Exception:
        data["memory"] = {"active": 0, "by_category": {}}
    if _cfg is not None:
        try:
            from ..integrations import registry
            data["integrations"] = registry.status(_cfg)
        except Exception:
            data["integrations"] = {}
    return data


def _build_app():
    from fastapi import Body, FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="J.A.R.V.I.S.", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _PAGE

    @app.get("/api/status")
    def status():
        return JSONResponse(_status_payload())

    @app.get("/api/memory")
    def memory(limit: int = 20):
        try:
            from ..memory.store import get_store
            return [{"text": f.text, "category": f.category, "date": f.short_date(),
                     "source": f.source} for f in get_store().recent(limit)]
        except Exception as exc:
            return {"error": str(exc)}

    @app.get("/api/missions")
    def missions():
        try:
            from ..missions.store import get_store
            st = get_store()
            rows = st._c.execute(
                "SELECT id, request, status, created_at FROM missions "
                "ORDER BY id DESC LIMIT 20").fetchall()
            return [dict(r) for r in rows]
        except Exception as exc:
            return {"error": str(exc)}

    @app.post("/api/chat")
    def chat(text: str = Body("", embed=True)):
        text = (text or "").strip()
        if not text:
            return {"reply": ""}
        from .. import brain
        try:
            return {"reply": brain.respond(text)}
        except Exception as exc:
            log.warning("chat: %s", exc)
            return {"reply": "خطایی پیش اومد."}

    return app


def run_server(cfg: Config) -> None:
    global _cfg
    _cfg = cfg
    if not available():
        return
    import uvicorn
    try:
        log.info("داشبورد وب: http://%s:%d", cfg.web_dashboard_host, cfg.web_dashboard_port)
        uvicorn.run(_build_app(), host=cfg.web_dashboard_host,
                    port=cfg.web_dashboard_port, log_level="warning")
    except Exception as exc:  # pragma: no cover
        log.warning("سرورِ وب اجرا نشد: %s", exc)


_PAGE = """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>J.A.R.V.I.S.</title><style>
:root{--bg:#02060b;--panel:#0a1a24;--cyan:#00c8ff;--dim:#4a7a8c;--ok:#50ffbe;--warn:#ff964a}
*{box-sizing:border-box;font-family:Tahoma,system-ui,sans-serif}
body{margin:0;background:var(--bg);color:#dff;padding:16px}
h1{color:var(--cyan);letter-spacing:.3em;font-size:20px;margin:0 0 12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.card{background:var(--panel);border:1px solid #12303f;border-radius:10px;padding:12px}
.card h2{margin:0 0 8px;font-size:13px;color:var(--dim);font-weight:normal}
.big{font-size:26px;color:var(--cyan)}
.row{display:flex;gap:14px;flex-wrap:wrap}
.chip{padding:2px 8px;border-radius:10px;border:1px solid #1c4152;font-size:12px}
.on{color:var(--ok);border-color:var(--ok)}.off{color:var(--dim)}
#log div,#mem div{font-size:12px;color:var(--dim);padding:2px 0;border-bottom:1px solid #0e2531}
#chat{height:230px;overflow:auto;background:#03101a;border-radius:8px;padding:8px;font-size:13px}
#chat .u{color:#cfe}#chat .j{color:var(--cyan)}
form{display:flex;gap:8px;margin-top:8px}
input{flex:1;background:#03101a;border:1px solid #1c4152;color:#dff;padding:8px;border-radius:8px}
button{background:var(--cyan);border:0;color:#012;padding:8px 14px;border-radius:8px;cursor:pointer}
</style></head><body>
<h1>J.A.R.V.I.S.</h1>
<div class="grid">
  <div class="card"><h2>سیستم</h2>
    <div class="row"><span>CPU <b id="cpu" class="big">–</b></span>
    <span>RAM <b id="ram" class="big">–</b></span>
    <span>باتری <b id="bat" class="big">–</b></span></div>
    <div id="clock" style="margin-top:6px;color:var(--dim)"></div></div>
  <div class="card"><h2>وضعیت</h2><div id="chips" class="row"></div>
    <div id="weather" style="margin-top:8px;color:var(--dim)"></div></div>
  <div class="card"><h2>حافظه (<span id="memc">0</span>)</h2><div id="mem"></div></div>
  <div class="card"><h2>رویدادها</h2><div id="log"></div></div>
</div>
<div class="card" style="margin-top:12px"><h2>گفت‌وگو با جارویس</h2>
  <div id="chat"></div>
  <form onsubmit="send(event)"><input id="msg" placeholder="بنویس…" autocomplete="off">
  <button>ارسال</button></form></div>
<script>
const $=id=>document.getElementById(id);
async function tick(){try{
  const s=await (await fetch('/api/status')).json();
  $('cpu').textContent=s.cpu+'%';$('ram').textContent=s.ram+'%';
  $('bat').textContent=s.battery==null?'—':s.battery+'%';
  $('clock').textContent=s.time+(s.conversation?'  · حالت مکالمه':'');
  const I=s.integrations||{};const base={'دوربین':s.camera,'صدا':s.voice,'تلگرام':s.telegram};
  const all=Object.assign(base,{'وب':I.web,'جیمیل':I.google,'اسپاتیفای':I.spotify,'نوشن':I.notion,'بینایی':I.vision,'چهره':I.face_id});
  $('chips').innerHTML=Object.entries(all).map(([k,v])=>`<span class="chip ${v?'on':'off'}">${k}</span>`).join('');
  let w=s.weather_temp!=null?`${s.location||''} ${Math.round(s.weather_temp)}°`:'';
  if(s.secondary_temp!=null)w+=`  ·  ${s.secondary_name} ${Math.round(s.secondary_temp)}°`;
  $('weather').textContent=w;
  $('memc').textContent=(s.memory&&s.memory.active)||0;
  $('log').innerHTML=(s.events||[]).map(e=>`<div>${e}</div>`).join('');
}catch(e){}}
async function loadMem(){try{const m=await (await fetch('/api/memory?limit=12')).json();
  if(Array.isArray(m))$('mem').innerHTML=m.map(f=>`<div>• ${f.text} <span style="opacity:.6">(${f.date})</span></div>`).join('');
}catch(e){}}
async function send(e){e.preventDefault();const t=$('msg').value.trim();if(!t)return;
  $('msg').value='';$('chat').innerHTML+=`<div class="u">▸ ${t}</div>`;
  $('chat').scrollTop=1e9;
  const r=await (await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({text:t})})).json();
  $('chat').innerHTML+=`<div class="j">◂ ${r.reply||'…'}</div>`;$('chat').scrollTop=1e9;loadMem();}
tick();loadMem();setInterval(tick,2000);setInterval(loadMem,15000);
</script></body></html>"""
