from jarvis.memory.store import MemoryStore
from jarvis.memory import markdown_mirror


def _store(tmp_path):
    return MemoryStore(tmp_path / "m.db")


def test_add_and_search(tmp_path):
    s = _store(tmp_path)
    s.add_fact("کاربر قهوه‌ی تلخ دوست دارد", category="preference")
    s.add_fact("اسم همکار کاربر رضا است", category="people")
    hits = s.search("قهوه")
    assert hits and "قهوه" in hits[0].text


def test_dedupe_reinforces(tmp_path):
    s = _store(tmp_path)
    a = s.add_fact("کاربر ساعت ۷ صبح بیدار می‌شود")
    b = s.add_fact("کاربر ساعت ۷ صبح بیدار می‌شود")   # تقریباً یکسان
    assert a.id == b.id
    assert b.reinforcement == 1


def test_supersede_keeps_history(tmp_path):
    s = _store(tmp_path)
    old = s.add_fact("کاربر در تهران زندگی می‌کند", category="home")
    new = s.supersede(old.id, "کاربر در مونکتون زندگی می‌کند", category="home")
    assert s.get(old.id).status == "superseded"
    assert s.get(old.id).superseded_by == new.id
    assert old.id in [t[1] for t in s.relations_of(new.id)]
    # هیچ چیز پاک نشده
    assert s.get(old.id) is not None


def test_no_hard_delete_archive_only(tmp_path):
    s = _store(tmp_path)
    f = s.add_fact("یک نکته‌ی موقت")
    s.archive(f.id)
    assert s.get(f.id).status == "archived"
    assert f.id not in [x.id for x in s.all_active()]


def test_markdown_mirror(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    monkeypatch.setattr(markdown_mirror, "MEMORY_VAULT", vault)
    monkeypatch.setattr(markdown_mirror, "ensure_dirs", lambda: vault.mkdir(exist_ok=True))
    s = _store(tmp_path)
    s.add_fact("کاربر گربه دارد", category="home")
    markdown_mirror.rebuild(s)
    assert (vault / "home.md").exists()
    assert "گربه" in (vault / "home.md").read_text(encoding="utf-8")
    assert (vault / "_index.md").exists()
