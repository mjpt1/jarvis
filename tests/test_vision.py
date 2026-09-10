import types

from jarvis.integrations import vision_tools, face_id


def test_vision_describe_scene_no_ultralytics(monkeypatch):
    monkeypatch.setattr(vision_tools, "available", lambda: True)
    monkeypatch.setattr(vision_tools, "detect",
                        lambda source=None: [("شخص", 2), ("لپ‌تاپ", 1)])
    monkeypatch.setattr("jarvis.claude_client.available", lambda: False)
    out = vision_tools.describe_scene(narrate=True)
    assert "شخص" in out and "لپ‌تاپ" in out


def test_vision_describe_empty(monkeypatch):
    monkeypatch.setattr(vision_tools, "detect", lambda source=None: [])
    assert "نمی‌بینم" in vision_tools.describe_scene()


def test_detect_counts(monkeypatch):
    class Boxes:
        cls = types.SimpleNamespace(tolist=lambda: [0.0, 0.0, 63.0])

    class R:
        names = {0: "person", 63: "laptop"}
        boxes = Boxes()

    fake_model = types.SimpleNamespace(predict=lambda *a, **k: [R()])
    monkeypatch.setattr(vision_tools, "_load", lambda: fake_model)
    monkeypatch.setattr(vision_tools, "_grab_frame", lambda source=None: object())
    res = vision_tools.detect()
    assert ("شخص", 2) in res and ("لپ‌تاپ", 1) in res


def test_face_id_unavailable_without_reference(monkeypatch, tmp_path):
    monkeypatch.setattr(face_id, "OWNER_FACE", tmp_path / "nope.jpg")
    assert face_id.available() is False
