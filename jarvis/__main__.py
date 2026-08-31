"""نقطه‌ی ورود:  python -m jarvis"""

from __future__ import annotations

import argparse
import sys

from .config import Config
from .logging_setup import setup
from .paths import ensure_dirs


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis", description="J.A.R.V.I.S. Companion")
    parser.add_argument("--init-config", action="store_true",
                        help="ساخت فایل config.json نمونه کنار سورس و خروج")
    parser.add_argument("--windowed", action="store_true", help="اجرا در حالت پنجره‌ای")
    parser.add_argument("--no-camera", action="store_true", help="غیرفعال کردن دوربین")
    parser.add_argument("--no-voice", action="store_true", help="غیرفعال کردن تشخیص گفتار")
    parser.add_argument("--debug", action="store_true", help="نمایش HUD دیباگ از ابتدا")
    parser.add_argument("--smoke-frames", type=int, default=None,
                        help="فقط N فریم رندر کن و خارج شو (برای تست)")
    args = parser.parse_args(argv)

    ensure_dirs()
    setup()

    cfg = Config.load()
    if args.init_config:
        path = cfg.write_example()
        print(f"فایل نمونه ساخته شد: {path}")
        return 0

    if args.windowed:
        cfg.fullscreen = False
    if args.no_camera:
        cfg.enable_camera = False
    if args.no_voice:
        cfg.enable_voice = False
    if args.debug:
        cfg.show_debug_on_start = True

    from .app import run
    run(cfg, smoke_frames=args.smoke_frames)
    return 0


if __name__ == "__main__":
    sys.exit(main())
