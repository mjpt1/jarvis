"""رندر متن فارسی با شکل‌دهی حروف (reshape + bidi) و کش رندر."""

from __future__ import annotations

import functools

import pygame

try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS_SHAPING = True
except Exception:  # pragma: no cover
    _HAS_SHAPING = False


def shape(text: str) -> str:
    if not _HAS_SHAPING or not text:
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


@functools.lru_cache(maxsize=512)
def _render_cached(font_id: int, text: str, color: tuple, shaped: bool):
    # این تابع فقط از طریق render() صدا زده می‌شود؛ font از رجیستری گرفته می‌شود.
    font = _FONT_REGISTRY[font_id]
    disp = shape(text) if shaped else text
    return font.render(disp, True, color)


_FONT_REGISTRY: dict[int, pygame.font.Font] = {}


def render(font, text: str, color, *, shaped: bool = True):
    fid = id(font)
    _FONT_REGISTRY.setdefault(fid, font)
    return _render_cached(fid, text, tuple(color), shaped)


def blit(surface, font, text, color, pos, *, anchor="topleft", shaped=True):
    label = render(font, text, color, shaped=shaped)
    rect = label.get_rect(**{anchor: pos})
    surface.blit(label, rect)
    return rect
