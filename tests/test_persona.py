from jarvis import persona
from jarvis.config import Config
from jarvis.state import STATE


class _Eng:
    class music:
        @staticmethod
        def pause():
            _Eng.paused = True
    paused = False


def _allow(monkeypatch):
    monkeypatch.setattr(persona, "_allowed", lambda: True)
    with STATE.lock:
        STATE.speaking = False
        STATE.now_playing = ""


def test_gesture_speaks(monkeypatch):
    _allow(monkeypatch)
    said = []
    monkeypatch.setattr(persona, "_speak", lambda t: said.append(t))
    persona._last_react = 0
    persona._last_gesture = {"name": "", "at": 0}
    persona.on_gesture("Thumb_Up", Config(), _Eng())
    assert said and "ممنون" in said[0] or said


def test_gesture_fist_pauses_music(monkeypatch):
    _allow(monkeypatch)
    monkeypatch.setattr(persona, "_speak", lambda t: None)
    persona._last_react = 0
    persona._last_gesture = {"name": "", "at": 0}
    with STATE.lock:
        STATE.now_playing = "x"
    persona.on_gesture("Closed_Fist", Config(), _Eng())
    assert _Eng.paused


def test_gesture_debounced(monkeypatch):
    _allow(monkeypatch)
    said = []
    monkeypatch.setattr(persona, "_speak", lambda t: said.append(t))
    persona._last_react = 0
    persona._last_gesture = {"name": "", "at": 0}
    persona.on_gesture("Open_Palm", Config(), _Eng())
    persona.on_gesture("Open_Palm", Config(), _Eng())   # همان حرکت بلافاصله
    assert len(said) == 1


def test_time_bucket():
    assert persona._time_bucket() in ("morning", "noon", "evening", "late")
