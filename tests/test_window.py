"""Helpers of the pywebview window (gigaam_app/window.py) that run without opening it."""

import json
import re
import sys

import pytest

from gigaam_app import window


def test_page_is_self_contained():
    html = window.page_html()
    assert "<style>" in html and "<script>" in html
    assert 'href="app.css"' not in html and 'src="app.js"' not in html
    # No network: nothing is loaded from outside the page.
    assert not re.search(r"""(src|href)=["']?(https?:)?//""", html)
    assert "@import" not in html


def test_forced_theme_reaches_page_and_background(monkeypatch):
    monkeypatch.setenv("GIGAAM_THEME", "dark")
    assert window.system_theme() == "dark"
    assert '<html lang="ru" data-theme="dark">' in window.page_html()
    monkeypatch.setenv("GIGAAM_THEME", "light")
    assert window.system_theme() == "light"


def test_background_colours_match_the_css():
    css = (window.WEB_DIR / "app.css").read_text(encoding="utf-8")
    light = re.search(r":root \{[^}]*--bg: (#[0-9a-f]{6})", css).group(1)
    dark = re.search(r':root\[data-theme="dark"\] \{[^}]*--bg: (#[0-9a-f]{6})', css).group(1)
    assert window.BACKGROUND == {"light": light, "dark": dark}


def test_missing_runtime_message(monkeypatch):
    monkeypatch.setenv("GIGAAM_PRETEND_NO_WEBVIEW", "1")
    text, link = window.missing_runtime()
    if sys.platform == "win32":
        assert "WebView2" in text and link == window.WEBVIEW2_URL
    else:
        assert "WebKitGTK" in text and "gir1.2-webkit2-4.1" in text and link is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry")
def test_webview2_is_found_on_this_machine():
    # The development and test machines have WebView2; a missing one is covered above.
    assert window.webview2_version()
    assert window.missing_runtime() is None


def test_pushed_messages_are_ascii():
    """pywebview on GTK cuts non-ASCII scripts short, so the sender must escape them."""
    sent = []

    class FakeWindow:
        def evaluate_js(self, script):
            sent.append(script)

    import queue
    outbox = queue.Queue()
    sender = window.Sender(FakeWindow(), outbox)
    outbox.put({"seq": 1, "kind": "notice", "data": {"text": "Текст скопирован"}})
    outbox.put(None)
    sender.run()
    assert sent and sent[0].isascii()
    payload = sent[0][sent[0].index("receive(") + len("receive("):-1]
    assert json.loads(payload)["data"]["text"] == "Текст скопирован"


def test_api_exposes_only_page_methods():
    """pywebview exposes every public attribute of js_api to the page."""
    public = {name for name in dir(window.Api) if not name.startswith("_")}
    assert public == {"ready", "pick_files", "add_files", "remove", "cancel", "retry", "segments", "copy_text",
                      "open_output", "create_output", "show_folder", "set_settings", "reset_settings",
                      "download", "decline_download", "cancel_download", "close_anyway", "clip", "reread", "apply_fix"}
    api = window.Api(controller=object())
    assert all(name.startswith("_") for name in vars(api))


def test_page_calls_only_existing_api_methods():
    script = (window.WEB_DIR / "app.js").read_text(encoding="utf-8")
    called = set(re.findall(r"call\('(\w+)'", script))
    assert called and called <= {name for name in dir(window.Api) if not name.startswith("_")}


def test_window_icon_files():
    """The icon the window loads exists, and the .ico holds every size Windows asks for
    (tools/make_icon.py writes them; the 16-32 px ones are hand-drawn)."""
    import struct

    assert window.ICON.is_file()
    icons = window.ICON.parent
    assert (icons / "gigaam.png").is_file() and (icons / "gigaam.svg").is_file()
    data = (icons / "gigaam.ico").read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data, 0)
    assert (reserved, kind) == (0, 1)
    # Each directory entry starts with width and height bytes; 0 means 256.
    sizes = sorted((data[6 + 16 * i] or 256) for i in range(count))
    assert sizes == [16, 20, 24, 32, 40, 48, 64, 128, 256]
