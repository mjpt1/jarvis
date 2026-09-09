"""آینه‌ی Markdown از حافظه — یک فایل به‌ازای هر دسته، سازگار با Obsidian.

منبعِ حقیقت همیشه SQLite است؛ این فقط یک بازتابِ خواندنی برای مرور انسانی است.
"""

from __future__ import annotations

from datetime import datetime

from ..logging_setup import get_logger
from ..paths import MEMORY_VAULT, ensure_dirs
from .store import MemoryStore

log = get_logger("memory")


def _safe(name: str) -> str:
    return "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "general"


def rebuild(store: MemoryStore) -> int:
    """کلِ vault را از پایگاه‌داده بازسازی می‌کند. تعداد فایل‌های نوشته‌شده را برمی‌گرداند."""
    ensure_dirs()
    facts = store.all_active()
    by_cat: dict[str, list] = {}
    for f in facts:
        by_cat.setdefault(f.category, []).append(f)

    # فایل‌های قدیمی که دیگر دسته‌ای ندارند پاک شوند
    existing = {p.stem for p in MEMORY_VAULT.glob("*.md")}
    keep = {_safe(c) for c in by_cat} | {"_index"}
    for stale in existing - keep:
        (MEMORY_VAULT / f"{stale}.md").unlink(missing_ok=True)

    written = 0
    for cat, items in sorted(by_cat.items()):
        lines = [f"---", f"category: {cat}", f"updated: {datetime.now().isoformat(timespec='seconds')}",
                 f"count: {len(items)}", "---", "", f"# {cat}", ""]
        for f in sorted(items, key=lambda x: x.created_at):
            tags = " ".join(f"#{t}" for t in f.tags)
            meta = f"  <sub>{f.short_date()} · منبع: {f.source} · اطمینان {f.confidence:.2f}"
            if f.reinforcement:
                meta += f" · ×{f.reinforcement + 1}"
            meta += f" {tags}</sub>"
            lines.append(f"- {f.text}{meta}")
        (MEMORY_VAULT / f"{_safe(cat)}.md").write_text("\n".join(lines) + "\n",
                                                       encoding="utf-8")
        written += 1

    st = store.stats()
    idx = ["---", "type: index", f"updated: {datetime.now().isoformat(timespec='seconds')}",
           "---", "", "# فهرست حافظه‌ی جارویس", "",
           f"مجموع حقایق فعال: **{st['active']}**", ""]
    for cat, n in sorted(st["by_category"].items()):
        idx.append(f"- [[{_safe(cat)}]] — {n}")
    (MEMORY_VAULT / "_index.md").write_text("\n".join(idx) + "\n", encoding="utf-8")
    log.info("آینه‌ی Markdown بازسازی شد (%d فایل، %d حقیقت).", written, len(facts))
    return written
