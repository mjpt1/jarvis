"""کنترلِ پخشِ Spotify — نیاز به spotipy و Client ID/Secret و اشتراکِ Premium."""

from __future__ import annotations

from ..logging_setup import get_logger
from ..paths import CREDENTIALS_DIR, ensure_dirs

log = get_logger("spotify")

_CID = ""
_SECRET = ""
_REDIRECT = "http://localhost:8888/callback"
_SCOPE = "user-modify-playback-state user-read-playback-state user-read-currently-playing"
_client = None


def configure(client_id: str, client_secret: str, redirect_uri: str) -> None:
    global _CID, _SECRET, _REDIRECT
    _CID, _SECRET, _REDIRECT = client_id, client_secret, redirect_uri


def available() -> bool:
    if not (_CID and _SECRET):
        return False
    try:
        import spotipy  # noqa: F401
        return True
    except Exception:
        return False


def _sp():
    global _client
    if _client is None:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        ensure_dirs()
        _client = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=_CID, client_secret=_SECRET, redirect_uri=_REDIRECT,
            scope=_SCOPE, cache_path=str(CREDENTIALS_DIR / "spotify_token.json"),
            open_browser=True))
    return _client


def _safe(fn, ok_msg: str) -> str:
    try:
        fn()
        return ok_msg
    except Exception as exc:
        log.warning("Spotify: %s", exc)
        return "دستورِ Spotify اجرا نشد (پخش‌کننده‌ای فعال است؟)."


def play() -> str:
    return _safe(lambda: _sp().start_playback(), "پخش شد.")


def pause() -> str:
    return _safe(lambda: _sp().pause_playback(), "مکث شد.")


def next_track() -> str:
    return _safe(lambda: _sp().next_track(), "آهنگِ بعدی.")


def prev_track() -> str:
    return _safe(lambda: _sp().previous_track(), "آهنگِ قبلی.")


def play_search(query: str) -> str:
    try:
        sp = _sp()
        res = sp.search(q=query, type="track", limit=1)
        items = res.get("tracks", {}).get("items", [])
        if not items:
            return f"آهنگی برای «{query}» پیدا نشد."
        tr = items[0]
        sp.start_playback(uris=[tr["uri"]])
        return f"در حال پخشِ «{tr['name']}» از {tr['artists'][0]['name']}."
    except Exception as exc:
        log.warning("Spotify search: %s", exc)
        return "پخشِ آهنگ ناموفق بود."


def current() -> str:
    try:
        cur = _sp().current_playback()
        if not cur or not cur.get("item"):
            return "الان چیزی پخش نمی‌شود."
        it = cur["item"]
        return f"«{it['name']}» از {it['artists'][0]['name']}."
    except Exception as exc:
        log.warning("Spotify current: %s", exc)
        return "دریافتِ وضعیتِ پخش ناموفق بود."
