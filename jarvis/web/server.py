"""سرورِ FastAPI — «مرکز فرمانِ» جارویس (هم‌شکلِ داشبوردِ جارویس‌اواس)."""

from __future__ import annotations

import datetime

from ..config import Config
from ..logging_setup import get_logger
from ..state import STATE

log = get_logger("web")

_cfg: Config | None = None
_APP_START = datetime.datetime.now()


def available() -> bool:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        return True
    except Exception:
        return False


def _fa_digits(s) -> str:
    return str(s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
_MONTHS = ["ژانویه", "فوریه", "مارس", "آوریل", "مه", "ژوئن", "ژوئیه", "اوت",
           "سپتامبر", "اکتبر", "نوامبر", "دسامبر"]


# ============================================================
# جمع‌آوریِ داده‌ی داشبورد
# ============================================================

def _integrations_status() -> dict:
    if _cfg is None:
        return {}
    try:
        from ..integrations import registry
        return registry.status(_cfg)
    except Exception:
        return {}


def _memory_stats() -> dict:
    try:
        from ..memory.store import get_store
        return get_store().stats()
    except Exception:
        return {"active": 0, "by_category": {}}


def _dashboard_payload() -> dict:
    now = datetime.datetime.now()
    with STATE.lock:
        s = STATE
        cpu, ram, disk = s.cpu_percent, s.ram_percent, s.disk_percent
        batt = s.battery_percent
        speaking, subtitle = s.speaking, s.current_subtitle
        convo, awaiting = s.conversation_active, s.awaiting_command
        voice_on, tg_on = s.voice_enabled, s.telegram_enabled
        mic, tts_lvl = s.mic_level, s.tts_level
        last_heard = s.last_heard_text
        wtemp, wloc = s.weather_temp, s.location_name
        sec_temp, sec_name = s.secondary_temp, s.secondary_name
        events = list(s.event_log)[-10:]
        net = list(s.net_history)
        turns = len(s.chat_history) // 2
        tool_calls = s.tool_call_count
        owner_gate, owner_present = s.owner_gate_active, s.owner_present

    ints = _integrations_status()
    mem = _memory_stats()
    llm_connected = sum(1 for k in ("google", "spotify", "notion") if ints.get(k))

    from .. import claude_client
    claude_ok = claude_client.available()

    # --- بودجه / پیش‌کنشی ---
    budget, notifications, autonomy = {}, [], _cfg.autonomy_level if _cfg else 1
    try:
        from ..proactive.budget import BUDGET
        from ..proactive.notifications import autonomy as _au
        from ..proactive.notifications import recent as _rec
        budget = BUDGET.summary()
        notifications = _rec(8)
        autonomy = _au()
    except Exception:
        pass

    # --- AI Core Overview ---
    core = [
        {"name": "هستهٔ هوش", "status": "فعال" if claude_ok else "محلی", "ok": True, "icon": "◈"},
        {"name": "حافظه", "status": f"{_fa_digits(mem['active'])} ذخیره", "ok": True, "icon": "▤"},
        {"name": "صدا", "status": "آنلاین" if voice_on else "خاموش", "ok": voice_on, "icon": "◉"},
        {"name": "عامل‌ها", "status": f"{_fa_digits(sum(1 for a in _agents(ints, speaking, convo) if a['active']))} فعال",
         "ok": True, "icon": "❖"},
        {"name": "LLM‌ها", "status": f"{_fa_digits(1 if claude_ok else 0)} متصل", "ok": claude_ok, "icon": "⛁"},
        {"name": "سیستم", "status": "بهینه" if cpu < 85 and ram < 92 else "پرمصرف",
         "ok": cpu < 85 and ram < 92, "icon": "⛨"},
    ]

    # --- Live Intelligence Feed ---
    feed = []
    for n in notifications:
        tag = {"warn": "هشدار", "urgent": "فوری"}.get(n["level"], "اطلاع")
        feed.append({"icon": "🔔", "title": n["text"], "sub": n["source"], "tag": tag})
    feed.append({"icon": "🖥", "title": f"مصرف پردازنده {_fa_digits(int(cpu))}٪ · رم {_fa_digits(int(ram))}٪",
                 "sub": "بارِ سیستم", "tag": "زنده"})
    if claude_ok and budget:
        feed.append({"icon": "💠", "title": f"امروز {_fa_digits(budget.get('calls', 0))} تماس با Claude "
                     f"— {budget.get('usd', 0):.3f} دلار", "sub": "بودجه", "tag": "اطلاع"})
    if last_heard:
        feed.append({"icon": "🎙", "title": f"آخرین شنیده: «{last_heard}»", "sub": "صدا", "tag": "زنده"})
    if not feed:
        feed.append({"icon": "✓", "title": "همه چیز عادی است قربان", "sub": "سیستم", "tag": "اطلاع"})

    # --- Mission Timeline ---
    timeline = []
    try:
        from ..missions.store import get_store as _ms
        rows = _ms()._c.execute(
            "SELECT request, status, created_at FROM missions ORDER BY id DESC LIMIT 5"
        ).fetchall()
        for r in rows:
            st = {"done": "انجام شد", "failed": "ناموفق", "running": "در حال اجرا",
                  "planning": "برنامه‌ریزی"}.get(r["status"], r["status"])
            timeline.append({"time": (r["created_at"] or "")[11:16] or "—",
                             "title": r["request"][:60], "meta": st})
    except Exception:
        pass
    if ints.get("google"):
        try:
            from ..integrations import google_ws
            svc = google_ws._svc("calendar", "v3")
            tz = datetime.UTC
            res = svc.events().list(calendarId="primary",
                                    timeMin=datetime.datetime.now(tz).isoformat(),
                                    timeMax=(datetime.datetime.now(tz) + datetime.timedelta(days=1)).isoformat(),
                                    singleEvents=True, orderBy="startTime", maxResults=5).execute()
            for ev in res.get("items", []):
                start = ev["start"].get("dateTime", ev["start"].get("date", ""))
                timeline.append({"time": start[11:16] or "—",
                                 "title": ev.get("summary", "رویداد"), "meta": "تقویم"})
        except Exception:
            pass
    if not timeline:
        timeline.append({"time": now.strftime("%H:%M"), "title": "سیستم آماده به کار",
                         "meta": "اکنون"})

    return {
        "clock": now.strftime("%H:%M:%S"),
        "date": f"{_WEEKDAYS[now.weekday()]} {_fa_digits(now.day)} {_MONTHS[now.month - 1]} {_fa_digits(now.year)}",
        "system_status": "بهینه" if cpu < 85 and ram < 92 else "پرمصرف",
        "uptime": _fa_digits(int((now - _APP_START).total_seconds() // 60)) + " دقیقه",
        "core": core,
        "feed": feed[:8],
        "agents": _agents(ints, speaking, convo),
        "timeline": timeline[:6],
        "quick": [
            {"label": "وضعیت سیستم", "cmd": "وضعیت سیستم"},
            {"label": "اخبار", "cmd": "اخبار"},
            {"label": "چه کارهایی دارم", "cmd": "چه کارهایی داری"},
            {"label": "هوا چطوره", "cmd": "هوا چطوره"},
            {"label": "حافظه‌ت رو نشون بده", "cmd": "حافظه‌ت رو نشون بده"},
            {"label": "یه جوک بگو", "cmd": "یه جوک بگو"},
        ],
        "monitor": {"cpu": round(cpu, 1), "ram": round(ram, 1), "disk": round(disk, 1),
                    "battery": batt},
        "memory": {"count": mem["active"], "turns": turns, "tools": tool_calls,
                   "by_category": mem["by_category"]},
        "net": net[-40:],
        "llm": [
            {"name": "Claude", "state": "متصل" if claude_ok else "وصل نیست"},
            {"name": "Gmail", "state": "متصل" if ints.get("google") else "وصل نیست"},
            {"name": "Calendar", "state": "متصل" if ints.get("google") else "وصل نیست"},
            {"name": "Spotify", "state": "متصل" if ints.get("spotify") else "وصل نیست"},
            {"name": "Notion", "state": "متصل" if ints.get("notion") else "وصل نیست"},
            {"name": "Telegram", "state": "متصل" if tg_on else "وصل نیست"},
            {"name": "وب", "state": "متصل" if ints.get("web") else "وصل نیست"},
            {"name": "بینایی", "state": "متصل" if ints.get("vision") else "وصل نیست"},
        ],
        "llm_connected": 1 + llm_connected + (1 if tg_on else 0) + (1 if ints.get("web") else 0),
        "voice": {"listening": awaiting or convo, "conversation": convo,
                  "speaking": speaking, "level": round(max(mic, tts_lvl), 3),
                  "subtitle": subtitle, "last_heard": last_heard,
                  "gate": owner_gate and not owner_present},
        "bottom": {
            "location": wloc or "—",
            "weather": (f"{wtemp:.0f}°" if wtemp is not None else "—")
            + (f" · {sec_name} {sec_temp:.0f}°" if sec_temp is not None else ""),
            "network": _net_quality(net),
        },
        "budget": budget,
        "autonomy": autonomy,
        "events": [f"[{t}] {x}" for t, x in events],
    }


def _agents(ints: dict, speaking: bool, convo: bool) -> list:
    with STATE.lock:
        voice_on, cam_on, tg_on = STATE.voice_enabled, STATE.camera_enabled, STATE.telegram_enabled
    return [
        {"name": "عامل صدا", "active": voice_on,
         "status": "در حال صحبت" if speaking else ("گوش می‌دهد" if (voice_on and convo) else
                   ("آماده" if voice_on else "خاموش"))},
        {"name": "عامل بینایی", "active": cam_on, "status": "فعال" if cam_on else "خاموش"},
        {"name": "عامل حافظه", "active": True, "status": "فعال"},
        {"name": "عامل وب", "active": bool(ints.get("web")), "status": "آماده" if ints.get("web") else "خاموش"},
        {"name": "عامل مأموریت", "active": True, "status": "آماده"},
        {"name": "عامل تلگرام", "active": tg_on, "status": "متصل" if tg_on else "خاموش"},
    ]


def _net_quality(net: list) -> str:
    if not net:
        return "—"
    avg = sum(net[-10:]) / max(1, len(net[-10:]))
    return "عالی" if avg >= 0 else "ضعیف"  # اتصال برقرار است اگر آماری هست


# ============================================================

def _build_app():
    from fastapi import Body, FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    app = FastAPI(title="J.A.R.V.I.S.", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _PAGE

    @app.get("/api/dashboard")
    def dashboard():
        return JSONResponse(_dashboard_payload())

    @app.get("/api/memory")
    def memory(limit: int = 15):
        try:
            from ..memory.store import get_store
            return [{"text": f.text, "category": f.category, "date": f.short_date(),
                     "source": f.source} for f in get_store().recent(limit)]
        except Exception as exc:
            return {"error": str(exc)}

    @app.post("/api/autonomy")
    def set_autonomy(level: int = Body(..., embed=True)):
        from ..proactive.notifications import set_autonomy as _sa
        if _cfg is not None:
            _cfg.autonomy_level = _sa(level)
        return {"autonomy": _sa(level)}

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
        log.info("مرکز فرمانِ وب: http://%s:%d", cfg.web_dashboard_host, cfg.web_dashboard_port)
        uvicorn.run(_build_app(), host=cfg.web_dashboard_host,
                    port=cfg.web_dashboard_port, log_level="warning")
    except Exception as exc:  # pragma: no cover
        log.warning("سرورِ وب اجرا نشد: %s", exc)


_PAGE = r"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>J.A.R.V.I.S. Command Center</title>
<style>
:root{
  --bg:#04090f; --bg2:#060d16; --panel:#0a1622; --panel2:#0c1a28;
  --line:#123047; --line2:#1c4763;
  --cy:#38c6ee; --cy-dim:#2b7fa0; --cy-faint:#183f52;
  --txt:#cfeaf6; --mut:#5f8ba3; --ok:#4ff0c0; --warn:#ffb057; --bad:#ff6b6b;
  --glow:0 0 18px rgba(56,198,238,.18);
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:radial-gradient(1200px 700px at 60% -10%,#0a2233 0%,var(--bg) 60%);
  color:var(--txt);font-family:Vazirmatn,Tahoma,system-ui,sans-serif;overflow:hidden}
::-webkit-scrollbar{width:6px;height:6px}::-webkit-scrollbar-thumb{background:var(--line2);border-radius:3px}
.app{display:grid;grid-template-columns:236px 1fr;grid-template-rows:auto 1fr 44px;height:100vh}

/* ---------- Sidebar ---------- */
.side{grid-column:1;grid-row:1/4;background:linear-gradient(180deg,#081521,#050b12);border-left:1px solid var(--line);
  display:flex;flex-direction:column;padding:16px 14px;gap:14px;overflow:auto}
.brand{display:flex;align-items:center;gap:10px}
.brand .orb-mini{width:34px;height:34px;border-radius:50%;border:2px solid var(--cy);
  box-shadow:var(--glow),inset 0 0 12px rgba(56,198,238,.35);position:relative}
.brand .orb-mini::after{content:"";position:absolute;inset:7px;border-radius:50%;background:var(--cy);
  box-shadow:0 0 12px var(--cy);animation:pulse 2.6s infinite}
.brand b{font-size:15px;letter-spacing:.22em}.brand span{display:block;font-size:9px;color:var(--mut);letter-spacing:.28em}
.nav{display:flex;flex-direction:column;gap:2px;margin-top:4px}
.nav a{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:8px;color:var(--mut);
  font-size:13px;text-decoration:none;cursor:pointer;transition:.15s}
.nav a:hover{background:#0d2232;color:var(--txt)}
.nav a.on{background:linear-gradient(90deg,rgba(56,198,238,.16),transparent);color:var(--cy);
  border-right:2px solid var(--cy)}
.nav a .ic{width:16px;text-align:center;opacity:.85}
.nav a .bdg{margin-inline-start:auto;background:var(--cy-faint);color:var(--cy);font-size:10px;
  border-radius:9px;padding:1px 6px}
.vstat{margin-top:auto;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px;text-align:center}
.vstat h4{font-size:10px;color:var(--mut);letter-spacing:.2em;margin-bottom:8px}
.wave{display:flex;align-items:center;justify-content:center;gap:3px;height:26px;margin-bottom:6px}
.wave i{width:3px;background:var(--cy);border-radius:2px;height:6px;animation:eq 1s infinite ease-in-out}
.wave i:nth-child(2){animation-delay:.1s}.wave i:nth-child(3){animation-delay:.2s}
.wave i:nth-child(4){animation-delay:.3s}.wave i:nth-child(5){animation-delay:.15s}
.wave i:nth-child(6){animation-delay:.25s}.wave i:nth-child(7){animation-delay:.05s}
.vstat .lbl{font-size:11px;color:var(--cy);margin-bottom:8px}
.mic{width:58px;height:58px;border-radius:50%;margin:0 auto;border:2px solid var(--cy);
  display:flex;align-items:center;justify-content:center;font-size:22px;color:var(--cy);
  box-shadow:var(--glow),inset 0 0 16px rgba(56,198,238,.25);cursor:pointer}
.vstat small{display:block;color:var(--mut);font-size:10px;margin-top:6px}
.focus{border:1px solid var(--line2);border-radius:9px;padding:8px;text-align:center;font-size:12px;
  color:var(--mut);cursor:pointer}
.focus:hover{color:var(--cy);border-color:var(--cy)}

/* ---------- Top bar ---------- */
.top{grid-column:2;grid-row:1;display:flex;align-items:center;gap:16px;padding:12px 20px;border-bottom:1px solid var(--line)}
.pill{display:flex;align-items:center;gap:7px;background:var(--panel);border:1px solid var(--line);
  border-radius:20px;padding:5px 12px;font-size:11px;color:var(--mut)}
.pill .dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok)}
.clock{text-align:center;flex:1}
.clock b{font-size:26px;color:var(--cy);letter-spacing:.06em;font-variant-numeric:tabular-nums}
.clock span{display:block;font-size:11px;color:var(--mut);margin-top:2px}
.top .r{display:flex;align-items:center;gap:10px}
.top input{background:var(--panel);border:1px solid var(--line);border-radius:8px;color:var(--txt);
  padding:6px 10px;font-family:inherit;font-size:12px;width:170px}
.icobtn{width:32px;height:32px;border-radius:8px;border:1px solid var(--line);background:var(--panel);
  color:var(--mut);display:flex;align-items:center;justify-content:center;cursor:pointer}
.op{display:flex;align-items:center;gap:8px;background:var(--panel);border:1px solid var(--line);
  border-radius:20px;padding:4px 6px 4px 12px;font-size:11px}
.op .av{width:26px;height:26px;border-radius:50%;background:linear-gradient(135deg,var(--cy),#1b6480)}

/* ---------- Main grid ---------- */
.main{grid-column:2;grid-row:2;overflow:auto;padding:16px 20px 24px;display:grid;gap:14px;
  grid-template-columns:300px 1fr 340px;grid-auto-rows:min-content;align-content:start}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);
  border-radius:14px;padding:14px;box-shadow:var(--glow)}
.card h3{font-size:11px;color:var(--mut);letter-spacing:.18em;margin-bottom:10px;
  display:flex;align-items:center;justify-content:space-between}
.card h3 a{color:var(--cy-dim);font-size:10px;cursor:pointer;text-decoration:none}
.card h3 .live{color:var(--ok);font-size:9px;border:1px solid var(--ok);border-radius:8px;padding:0 5px}

.corelist div{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px solid #0c1e2c;font-size:12px}
.corelist div:last-child{border:0}
.corelist .ic{width:26px;height:26px;border-radius:7px;background:var(--cy-faint);color:var(--cy);
  display:flex;align-items:center;justify-content:center}
.corelist .s{margin-inline-start:auto;color:var(--mut);font-size:11px}
.corelist .s.ok{color:var(--ok)}

.core-center{grid-row:span 2;display:flex;flex-direction:column;align-items:center;justify-content:center;
  min-height:340px;position:relative}
#sphere{width:100%;max-width:420px;aspect-ratio:1/1}
.core-center .lbl{position:absolute;text-align:center;pointer-events:none}
.core-center .lbl b{font-size:30px;letter-spacing:.4em;color:#eaf9ff;text-shadow:0 0 22px var(--cy)}
.core-center .lbl span{display:block;font-size:11px;letter-spacing:.4em;color:var(--cy-dim);margin-top:4px}

.feed{display:flex;flex-direction:column;gap:9px;max-height:340px;overflow:auto}
.feed .it{display:flex;gap:9px;font-size:12px;padding-bottom:8px;border-bottom:1px solid #0c1e2c}
.feed .it .ico{font-size:15px}
.feed .it .tx b{display:block;color:var(--txt);font-weight:normal;line-height:1.5}
.feed .it .tx s{color:var(--mut);font-size:10px;text-decoration:none}
.feed .it .tag{margin-inline-start:auto;font-size:9px;color:var(--cy);border:1px solid var(--cy-faint);
  border-radius:7px;padding:1px 5px;height:fit-content}
.feed .it .tag.هشدار,.feed .it .tag.فوری{color:var(--warn);border-color:var(--warn)}

.agents{grid-column:1/3;display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.agent{background:#08131e;border:1px solid var(--line);border-radius:10px;padding:10px;display:flex;
  align-items:center;gap:9px;font-size:12px}
.agent .d{width:8px;height:8px;border-radius:50%;background:var(--mut)}
.agent.on .d{background:var(--ok);box-shadow:0 0 8px var(--ok)}
.agent .st{margin-inline-start:auto;color:var(--mut);font-size:10px}

.timeline .row{display:flex;gap:10px;font-size:12px;padding:7px 0;border-bottom:1px solid #0c1e2c}
.timeline .row:last-child{border:0}
.timeline .t{color:var(--cy);font-variant-numeric:tabular-nums;min-width:42px}
.timeline .m{margin-inline-start:auto;color:var(--mut);font-size:10px}

.quick{display:flex;flex-direction:column;gap:7px}
.quick button{background:#08131e;border:1px solid var(--line);border-radius:9px;color:var(--txt);
  padding:9px 12px;text-align:right;font-family:inherit;font-size:12px;cursor:pointer;transition:.15s}
.quick button:hover{border-color:var(--cy);color:var(--cy);background:#0b1c2b}

.rings{display:flex;justify-content:space-around;align-items:center}
.ring{text-align:center}
.ring svg{width:82px;height:82px;transform:rotate(-90deg)}
.ring .bg{fill:none;stroke:#0f2636;stroke-width:7}
.ring .fg{fill:none;stroke:var(--cy);stroke-width:7;stroke-linecap:round;transition:stroke-dashoffset .6s}
.ring .v{margin-top:-52px;font-size:16px;color:var(--cy);font-variant-numeric:tabular-nums}
.ring .n{margin-top:34px;font-size:10px;color:var(--mut);letter-spacing:.1em}

.mem-nums{display:flex;justify-content:space-around;margin-top:8px}
.mem-nums div{text-align:center}.mem-nums b{font-size:20px;color:var(--cy)}.mem-nums span{font-size:10px;color:var(--mut)}
#memspark{width:100%;height:60px}

.llm{display:grid;grid-template-columns:repeat(2,1fr);gap:7px}
.llm .p{display:flex;align-items:center;gap:8px;background:#08131e;border:1px solid var(--line);
  border-radius:8px;padding:7px 9px;font-size:11px}
.llm .p .d{width:7px;height:7px;border-radius:50%;background:var(--mut)}
.llm .p.on .d{background:var(--ok);box-shadow:0 0 7px var(--ok)}
.llm .p .s{margin-inline-start:auto;color:var(--mut);font-size:9px}

.chatcard{grid-column:1/4}
#chat{height:170px;overflow:auto;background:#050f18;border:1px solid var(--line);border-radius:10px;
  padding:10px;font-size:13px;line-height:1.9}
#chat .u{color:#bfe6f4}#chat .j{color:var(--cy)}
.chatform{display:flex;gap:8px;margin-top:9px}
.chatform input{flex:1;background:#050f18;border:1px solid var(--line);border-radius:9px;color:var(--txt);
  padding:10px;font-family:inherit}
.chatform button{background:var(--cy);border:0;color:#022;padding:0 18px;border-radius:9px;cursor:pointer;font-family:inherit}

/* ---------- Bottom bar ---------- */
.bottom{grid-column:2;grid-row:3;display:flex;align-items:center;gap:18px;padding:0 20px;border-top:1px solid var(--line);
  background:#050b12;font-size:11px;color:var(--mut)}
.bottom .b{display:flex;align-items:center;gap:6px}
.bottom .talk{flex:1;display:flex;align-items:center;justify-content:center;gap:12px;color:var(--cy)}
.bottom .talk .wave{height:16px}.bottom .talk .wave i{background:var(--cy)}
.brief{border:1px solid var(--cy);border-radius:8px;padding:5px 12px;color:var(--cy);cursor:pointer}

@keyframes pulse{0%,100%{opacity:.5}50%{opacity:1}}
@keyframes eq{0%,100%{height:5px}50%{height:20px}}
@media(max-width:1150px){.main{grid-template-columns:1fr}.agents{grid-column:auto}.core-center{grid-row:auto}}
</style></head><body>
<div class="app">

  <aside class="side">
    <div class="brand"><div class="orb-mini"></div>
      <div><b>JARVIS</b><span>COMMAND CENTER</span></div></div>
    <nav class="nav">
      <a class="on"><span class="ic">▦</span> مرکز فرمان</a>
      <a><span class="ic">◈</span> هستهٔ هوش</a>
      <a><span class="ic">❖</span> عامل‌ها</a>
      <a><span class="ic">✔</span> کارها <span class="bdg" id="nb-tasks">۰</span></a>
      <a><span class="ic">▤</span> حافظه <span class="bdg" id="nb-mem">۰</span></a>
      <a><span class="ic">✎</span> گفت‌وگوها <span class="bdg" id="nb-turns">۰</span></a>
      <a><span class="ic">◵</span> مأموریت‌ها</a>
      <a><span class="ic">⚙</span> ابزارها و مهارت‌ها</a>
      <a><span class="ic">⌘</span> تنظیمات</a>
    </nav>
    <div class="vstat">
      <h4>وضعیت صدا</h4>
      <div class="wave"><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div>
      <div class="lbl" id="v-lbl">در انتظار…</div>
      <div class="mic" onclick="startVoice()">🎙</div>
      <small>برای صحبت بگویید «جارویس»</small>
    </div>
    <div class="focus" onclick="say('تا صبح ساکت باش')">◐ حالت تمرکز</div>
  </aside>

  <header class="top">
    <div class="pill"><span class="dot" id="sys-dot"></span> وضعیت سیستم · <b id="sys-st">—</b></div>
    <div class="clock"><b id="clk">—</b><span id="dte">—</span></div>
    <div class="r">
      <input id="msg2" placeholder="جست‌وجو یا فرمان…" onkeydown="if(event.key==='Enter'){say(this.value);this.value=''}">
      <div class="icobtn">▦</div><div class="icobtn">◔</div><div class="icobtn">⚙</div>
      <div class="op"><span>اپراتور · فرمانده</span><span class="av"></span></div>
    </div>
  </header>

  <main class="main">
    <section class="card">
      <h3>نمای هستهٔ هوش</h3>
      <div class="corelist" id="core"></div>
    </section>

    <section class="card core-center">
      <canvas id="sphere"></canvas>
      <div class="lbl"><b>JARVIS</b><span>AI CORE · v8.0</span></div>
    </section>

    <section class="card">
      <h3>جریان اطلاعاتِ زنده <span class="live">زنده</span></h3>
      <div class="feed" id="feed"></div>
    </section>

    <section class="card agents-wrap" style="grid-column:1/3">
      <h3>عامل‌های فعال</h3>
      <div class="agents" id="agents"></div>
    </section>

    <section class="card">
      <h3>فرمان‌های سریع</h3>
      <div class="quick" id="quick"></div>
    </section>

    <section class="card">
      <h3>خط زمانیِ مأموریت</h3>
      <div class="timeline" id="timeline"></div>
    </section>

    <section class="card">
      <h3>پایشِ سیستم</h3>
      <div class="rings" id="rings"></div>
    </section>

    <section class="card">
      <h3>بینشِ حافظه</h3>
      <canvas id="memspark"></canvas>
      <div class="mem-nums">
        <div><b id="m-count">۰</b><span>حقیقت</span></div>
        <div><b id="m-turns">۰</b><span>دور گفت‌وگو</span></div>
        <div><b id="m-tools">۰</b><span>فرمان</span></div>
      </div>
    </section>

    <section class="card">
      <h3>وضعیت LLM و ادغام‌ها <span id="llm-n" style="color:var(--cy)"></span></h3>
      <div class="llm" id="llm"></div>
    </section>

    <section class="card chatcard">
      <h3>گفت‌وگو با جارویس</h3>
      <div id="chat"></div>
      <div class="chatform">
        <input id="msg" placeholder="بنویس…" autocomplete="off"
               onkeydown="if(event.key==='Enter')send()">
        <button onclick="send()">ارسال</button>
      </div>
    </section>
  </main>

  <footer class="bottom">
    <div class="b">◍ <span id="b-loc">—</span></div>
    <div class="b">☀ <span id="b-wx">—</span></div>
    <div class="b">📶 <span id="b-net">—</span></div>
    <div class="talk"><div class="wave"><i></i><i></i><i></i></div>
      <span id="b-talk">صحبت با جارویس</span>
      <div class="wave"><i></i><i></i><i></i></div></div>
    <div class="brief" onclick="say('چه کارهایی داری')">خلاصهٔ مدیریتی</div>
  </footer>
</div>

<script>
const $=s=>document.querySelector(s), FA=n=>String(n).replace(/[0-9]/g,d=>'۰۱۲۳۴۵۶۷۸۹'[d]);
let LVL=0;

async function tick(){
  let d; try{ d=await (await fetch('/api/dashboard')).json(); }catch(e){ return; }
  $('#clk').textContent=d.clock.replace(/[0-9]/g,x=>'۰۱۲۳۴۵۶۷۸۹'[x]);
  $('#dte').textContent=d.date;
  $('#sys-st').textContent=d.system_status;
  $('#sys-dot').style.background=d.system_status==='بهینه'?'var(--ok)':'var(--warn)';

  $('#core').innerHTML=d.core.map(c=>`<div><span class="ic">${c.icon}</span>${c.name}
    <span class="s ${c.ok?'ok':''}">${c.status}</span></div>`).join('');

  $('#feed').innerHTML=d.feed.map(f=>`<div class="it"><span class="ico">${f.icon}</span>
    <div class="tx"><b>${f.title}</b><s>${f.sub}</s></div>
    <span class="tag ${f.tag}">${f.tag}</span></div>`).join('');

  $('#agents').innerHTML=d.agents.map(a=>`<div class="agent ${a.active?'on':''}">
    <span class="d"></span>${a.name}<span class="st">${a.status}</span></div>`).join('');

  $('#timeline').innerHTML=d.timeline.map(t=>`<div class="row"><span class="t">${FA(t.time)}</span>
    <span>${t.title}</span><span class="m">${t.meta}</span></div>`).join('');

  $('#quick').innerHTML=d.quick.map(q=>`<button onclick="say('${q.cmd}')">${q.label}</button>`).join('');

  const m=d.monitor;
  $('#rings').innerHTML=[['پردازنده',m.cpu],['حافظه',m.ram],['دیسک',m.disk]].map(([n,v])=>{
    const off=289-289*Math.min(100,v)/100;
    return `<div class="ring"><svg viewBox="0 0 100 100"><circle class="bg" cx="50" cy="50" r="46"/>
      <circle class="fg" cx="50" cy="50" r="46" stroke-dasharray="289" stroke-dashoffset="${off}"/></svg>
      <div class="v">${FA(Math.round(v))}٪</div><div class="n">${n}</div></div>`;}).join('');

  $('#m-count').textContent=FA(d.memory.count);
  $('#m-turns').textContent=FA(d.memory.turns);
  $('#m-tools').textContent=FA(d.memory.tools);
  $('#nb-mem').textContent=FA(d.memory.count);
  $('#nb-turns').textContent=FA(d.memory.turns);
  $('#nb-tasks').textContent=FA(d.timeline.length);
  drawSpark(d.net);

  $('#llm').innerHTML=d.llm.map(l=>`<div class="p ${l.state==='متصل'?'on':''}">
    <span class="d"></span>${l.name}<span class="s">${l.state}</span></div>`).join('');
  $('#llm-n').textContent=FA(d.llm_connected)+' متصل';

  const v=d.voice; LVL=v.level;
  $('#v-lbl').textContent=v.speaking?'در حال صحبت…':v.gate?'منتظر دیدن چهره…':
    (v.conversation?'حالت مکالمه':(v.listening?'گوش می‌کنم…':'در انتظار…'));
  $('#b-talk').textContent=v.speaking?(v.subtitle||'…'):(v.last_heard?('«'+v.last_heard+'»'):'صحبت با جارویس');
  $('#b-loc').textContent=d.bottom.location;
  $('#b-wx').textContent=d.bottom.weather;
  $('#b-net').textContent=d.bottom.network;
}

/* ---- particle sphere ---- */
const cv=$('#sphere'), cx=cv.getContext('2d');
let P=[]; (function(){const N=520,ph=Math.PI*(3-Math.sqrt(5));
  for(let i=0;i<N;i++){const y=1-(i/(N-1))*2,r=Math.sqrt(1-y*y),t=ph*i;
    P.push([Math.cos(t)*r,y,Math.sin(t)*r]);}})();
function sphere(ts){
  const w=cv.width=cv.clientWidth*2, h=cv.height=cv.clientHeight*2, R=w*0.36;
  cx.clearRect(0,0,w,h); const a=ts/2200, e=0.25+LVL*0.9;
  const ca=Math.cos(a),sa=Math.sin(a);
  const pts=P.map(([x,y,z])=>{
    let X=x*ca-z*sa, Z=x*sa+z*ca;
    const s=1+e*0.35*Math.abs(Math.sin((X+ts/900)*3));
    X*=s;y*=s;Z*=s;
    const f=1.9/(1.9-Z);
    return [w/2+X*R*f, h/2+y*R*f, Z, f];});
  pts.sort((p,q)=>p[2]-q[2]);
  for(const [px,py,z,f] of pts){
    const b=(z+1)/2, col=LVL>0.12?'255,210,140':'56,198,238';
    cx.beginPath();cx.arc(px,py,Math.max(1,1.6*f+b*2.2),0,7);
    cx.fillStyle=`rgba(${col},${0.25+b*0.6})`;cx.fill();}
  cx.beginPath();cx.arc(w/2,h/2,R*0.07*(1+e*0.4),0,7);cx.fillStyle='#eaffff';cx.fill();
  requestAnimationFrame(sphere);
}
requestAnimationFrame(sphere);

function drawSpark(net){
  const c=$('#memspark'), g=c.getContext('2d'), w=c.width=c.clientWidth*2, h=c.height=c.clientHeight*2;
  g.clearRect(0,0,w,h); if(!net||net.length<2)return;
  const mx=Math.max(...net,1); g.beginPath();
  net.forEach((v,i)=>{const x=i/(net.length-1)*w, y=h-Math.min(1,v/mx)*h*0.9-4;
    i?g.lineTo(x,y):g.moveTo(x,y);});
  g.strokeStyle='#38c6ee';g.lineWidth=2;g.stroke();
  net.forEach((v,i)=>{const x=i/(net.length-1)*w,y=h-Math.min(1,v/mx)*h*0.9-4;
    g.beginPath();g.arc(x,y,2.5,0,7);g.fillStyle='#38c6ee';g.fill();});
}

async function send(){const t=$('#msg').value.trim();if(!t)return;$('#msg').value='';
  $('#chat').innerHTML+=`<div class="u">▸ ${t}</div>`;$('#chat').scrollTop=1e9;
  const r=await (await fetch('/api/chat',{method:'POST',headers:{'content-type':'application/json'},
    body:JSON.stringify({text:t})})).json();
  $('#chat').innerHTML+=`<div class="j">◂ ${r.reply||'…'}</div>`;$('#chat').scrollTop=1e9;}
function say(t){ $('#msg').value=t; send(); }
function startVoice(){ say('جارویس'); }

tick(); setInterval(tick,2000);
</script></body></html>"""
