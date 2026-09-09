"""حافظه‌ی بلندمدتِ جارویس — «Memory Kernel».

حقایقِ اتمی، تاریخ‌دار و منبع‌دار در SQLite ذخیره می‌شوند، با آینه‌ی Markdown
سازگار با Obsidian. هیچ حذفِ دائمی‌ای وجود ندارد؛ فقط بایگانی/جایگزینی.
"""

from .store import Fact, MemoryStore, get_store

__all__ = ["Fact", "MemoryStore", "get_store"]
