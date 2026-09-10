import subprocess
import sys
from pathlib import Path

from jarvis.errors import JarvisError, REGISTRY, describe, is_registered


def test_registry_shape():
    for code in REGISTRY:
        assert code.startswith("JRV-") and code.count("-") == 2
        assert code.split("-")[2].isdigit()


def test_jarvis_error_message():
    e = JarvisError("JRV-MEM-001", "خالی")
    assert "JRV-MEM-001" in str(e) and "خالی" in str(e)
    assert is_registered("JRV-MEM-001")
    assert not is_registered("JRV-XXX-999")
    assert describe("JRV-MEM-001")


def test_check_registry_script_passes():
    root = Path(__file__).resolve().parent.parent
    r = subprocess.run([sys.executable, str(root / "scripts" / "check_registry.py")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
