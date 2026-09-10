"""داشبورد وبِ جارویس (FastAPI) — چت، وضعیت زنده، حافظه، مأموریت‌ها.

اختیاری: `pip install fastapi uvicorn`. بدونشان خاموش می‌ماند.
"""

from .server import available, run_server

__all__ = ["available", "run_server"]
