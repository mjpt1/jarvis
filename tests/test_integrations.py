from jarvis.config import Config
from jarvis.integrations import filesystem, shell, registry, web


def test_registry_setup_no_keys():
    cfg = Config()
    cfg.telegram_bot_token = ""
    cfg.spotify_client_id = ""
    cfg.notion_token = ""
    registry.setup(cfg)
    st = registry.status(cfg)
    assert st["web"] is True
    assert st["filesystem"] is True
    assert st["cli"] is False          # پیش‌فرض خاموش
    assert st["telegram"] is False
    assert st["spotify"] is False
    assert st["notion"] is False


def test_filesystem_whitelist(tmp_path):
    allowed = tmp_path / "ok"
    allowed.mkdir()
    (allowed / "a.txt").write_text("سلام", encoding="utf-8")
    filesystem.configure([str(allowed)], allow_write=True)

    assert "a.txt" in filesystem.list_dir(str(allowed))
    assert filesystem.read_file(str(allowed / "a.txt")) == "سلام"
    # خارج از فهرست سفید
    outside = tmp_path / "secret.txt"
    outside.write_text("محرمانه", encoding="utf-8")
    assert "مجاز نیست" in filesystem.read_file(str(outside))


def test_filesystem_write_toggle(tmp_path):
    root = tmp_path / "w"
    root.mkdir()
    filesystem.configure([str(root)], allow_write=False)
    assert "غیرفعال" in filesystem.write_file(str(root / "x.txt"), "y")
    filesystem.configure([str(root)], allow_write=True)
    assert "ذخیره شد" in filesystem.write_file(str(root / "x.txt"), "y")


def test_shell_whitelist():
    shell.configure(enabled=True, whitelist=["echo"])
    out = shell.run("echo hello")
    assert "hello" in out
    assert "مجاز نیست" in shell.run("rm -rf /")


def test_shell_disabled_by_default():
    shell.configure(enabled=False, whitelist=["echo"])
    assert "غیرفعال" in shell.run("echo hi")


def test_web_search_parsing(monkeypatch):
    html = '''
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fp">
      <b>عنوان</b> نمونه</a>
    '''
    monkeypatch.setattr(web, "_get", lambda url, timeout=12: html)
    res = web.search("چیزی")
    assert res and res[0]["url"] == "https://example.com/p"
    assert "عنوان" in res[0]["title"]
