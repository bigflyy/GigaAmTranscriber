"""pywebview spike for plan 02 A1: bridge both ways, drop with real paths, timings.

    python spike.py RESULT_JSON [--close-after SECONDS]
"""

import json
import platform
import sys
import threading
import time
from pathlib import Path

import webview
from webview.dom import DOMEventHandler

started = time.perf_counter()
result_path = Path(sys.argv[1])
close_after = float(sys.argv[sys.argv.index("--close-after") + 1]) if "--close-after" in sys.argv else 0
result = {"platform": platform.platform(), "python": platform.python_version(), "pywebview": webview.__version__ if hasattr(webview, "__version__") else "?"}
PAGE = (Path(__file__).parent / "page.html").read_text(encoding="utf-8")


def mark(name):
    result[name] = round(time.perf_counter() - started, 3)
    result_path.write_text(json.dumps(result, indent=1), encoding="utf-8")


class Api:
    """Methods the page can call as pywebview.api.<name>()."""

    def info(self):
        mark("bridge_called")
        return {"platform": platform.system(), "renderer": webview.renderer if hasattr(webview, "renderer") else "?"}

    def pick_files(self):
        return window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True) or []

    def report(self, text):
        result["page_report"] = text
        mark("page_reported")


def on_drop(event):
    files = event.get("dataTransfer", {}).get("files", [])
    paths = [f.get("pywebviewFullPath") for f in files]
    result["dropped"] = paths
    mark("dropped_at")
    window.evaluate_js(f"addFiles({json.dumps(paths)})")


def on_loaded():
    mark("page_loaded")
    window.dom.document.events.dragover += DOMEventHandler(lambda e: None, True, True)
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)
    mark("drop_registered")

    def push():
        lines = ["Добрый день, коллеги.", "Сначала аудио режется на фрагменты по паузам.",
                 "Декодер превращает выход кодировщика в текст."]
        for index, line in enumerate(lines):
            time.sleep(0.3)
            mark(f"push_{index}")
            window.evaluate_js(f"addLine({json.dumps(f'00:{index * 9:02d}')}, {json.dumps(line)})")
        mark("lines_pushed")
        if close_after:
            time.sleep(close_after)
            window.destroy()

    threading.Thread(target=push, daemon=True).start()


window = webview.create_window("GigaAM spike", html=PAGE, js_api=Api(), width=960, height=640, min_size=(720, 520),
                               **({"x": -6000, "y": -6000, "focus": False} if "--offscreen" in sys.argv else {}))
window.events.shown += lambda: mark("window_shown")
window.events.loaded += on_loaded
mark("before_start")
webview.start(gui="edgechromium" if sys.platform == "win32" else "gtk")
mark("closed")
