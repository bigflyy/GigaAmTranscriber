"""The desktop window: the page in gigaam_app/web shown by pywebview.

Windows draws it with Edge WebView2, Linux with the system WebKitGTK. Before
the window opens, the app checks that the engine is there and otherwise shows
a native message with what to install: without WebView2, pywebview would fall
back to the old IE engine without a word.

    GIGAAM_THEME=light|dark      force a theme (tests and screenshots)
    GIGAAM_WINDOW_OFFSCREEN=1    open the window off screen and without focus (tests)
"""

import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

from . import __version__
from .controller import FILE_DIALOG_TYPES, Controller
from .history import History
from .paths import history_dir
from .worker import WorkerProcess

WEB_DIR = Path(__file__).resolve().parent / "web"
# Window icon: WinForms (Windows) loads an .ico, GTK (Linux) a .png. tools/make_icon.py draws both.
ICON = Path(__file__).resolve().parent / "icons" / ("gigaam.ico" if sys.platform == "win32" else "gigaam.png")
TITLE = f"GigaAM - Расшифровка речи {__version__}"
# Must match --bg of each theme in web/app.css: the frame shows it before the page paints.
BACKGROUND = {"light": "#f6f7f9", "dark": "#16171b"}
WEBVIEW2_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_CLIENT = r"Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


# ---------------------------------------------------------------------- theme

def system_theme():
    """'dark' or 'light': GIGAAM_THEME, else the system's app theme, else light."""
    forced = os.environ.get("GIGAAM_THEME", "").lower()
    if forced in BACKGROUND:
        return forced
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
        except OSError:
            return "light"
    try:
        answer = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                                capture_output=True, text=True, timeout=2).stdout
        if "dark" in answer:
            return "dark"
        answer = subprocess.run(["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                                capture_output=True, text=True, timeout=2).stdout
        return "dark" if "dark" in answer.lower() else "light"
    except (OSError, subprocess.SubprocessError):
        return "dark" if "dark" in os.environ.get("GTK_THEME", "").lower() else "light"


def page_html():
    """index.html with app.css and app.js inlined: no server, no file URLs, no network.
    With GIGAAM_THEME set the page keeps that theme instead of following the system."""
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
    css = (WEB_DIR / "app.css").read_text(encoding="utf-8")
    script = (WEB_DIR / "app.js").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="app.css">', f"<style>\n{css}</style>")
    html = html.replace('<script src="app.js"></script>', f"<script>\n{script}</script>")
    forced = os.environ.get("GIGAAM_THEME", "").lower()
    if forced in BACKGROUND:
        html = html.replace('<html lang="ru">', f'<html lang="ru" data-theme="{forced}">')
    return html


# ---------------------------------------------------------------------- runtime check

def webview2_version():
    """Installed WebView2 Runtime version, or None (Microsoft's documented registry check)."""
    import winreg
    places = [(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\\" + WEBVIEW2_CLIENT),
              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\" + WEBVIEW2_CLIENT),
              (winreg.HKEY_CURRENT_USER, r"Software\\" + WEBVIEW2_CLIENT)]
    for root, path in places:
        try:
            with winreg.OpenKey(root, path) as key:
                version = winreg.QueryValueEx(key, "pv")[0]
        except OSError:
            continue
        if version and version != "0.0.0.0":
            return version
    return None


def webkitgtk_available():
    """True when PyGObject can load GTK 3 and WebKit2 (the same versions pywebview tries)."""
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        for version in ("4.1", "4.0"):
            try:
                gi.require_version("WebKit2", version)
                break
            except ValueError:
                continue
        else:
            return False
        from gi.repository import Gtk, WebKit2  # noqa: F401
        return True
    except (ImportError, ValueError):
        return False


def missing_runtime():
    """(message, link) when the web engine is missing, else None."""
    if os.environ.get("GIGAAM_PRETEND_NO_WEBVIEW"):  # lets tests see the message path
        found = False
    elif sys.platform == "win32":
        found = webview2_version() is not None
    else:
        found = webkitgtk_available()
    if found:
        return None
    if sys.platform == "win32":
        return ("Для окна программы нужен Microsoft Edge WebView2 Runtime, а он не установлен.\n\n"
                "Установите его с сайта Microsoft (бесплатно, загрузчик около 2 МБ) и запустите программу снова.\n\n"
                "Открыть страницу загрузки?", WEBVIEW2_URL)
    # The frozen build carries PyGObject itself; from source it comes from the system too.
    python_gi = "" if getattr(sys, "frozen", False) else " python3-gi"
    python_gobject = "" if getattr(sys, "frozen", False) else " python3-gobject"
    return ("Для окна программы нужна библиотека WebKitGTK, а она не найдена.\n\n"
            "Установите её и запустите программу снова:\n"
            f"  Ubuntu, Debian: sudo apt install gir1.2-webkit2-4.1{python_gi}\n"
            f"  Fedora: sudo dnf install webkit2gtk4.1 gobject-introspection{python_gobject}\n\n"
            "Командная строка (gigaam-cli) работает и без неё.", None)


def show_native_message(text, link):
    """Show the message without the web engine: MessageBox on Windows, zenity or stderr on Linux."""
    if sys.platform == "win32":
        import ctypes
        MB_YESNO, MB_ICONWARNING, IDYES = 0x4, 0x30, 6
        answer = ctypes.windll.user32.MessageBoxW(None, text, TITLE, (MB_YESNO if link else 0) | MB_ICONWARNING)
        if link and answer == IDYES:
            os.startfile(link)
        return
    print(text, file=sys.stderr)
    for command in (["zenity", "--warning", "--no-wrap", "--title", TITLE, "--text", text],
                    ["kdialog", "--title", TITLE, "--sorry", text],
                    ["xmessage", "-center", text]):
        try:
            subprocess.run(command, timeout=600)
            return
        except (OSError, subprocess.SubprocessError):
            continue


# ---------------------------------------------------------------------- bridge

class Api:
    """Methods the page calls as pywebview.api.<name>(...). Names starting with
    an underscore are not exposed to the page."""

    def __init__(self, controller):
        self._controller = controller
        self._window = None
        self._close_confirmed = False

    def ready(self):
        return self._controller.ready()

    def pick_files(self):
        import webview
        paths = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=True,
                                                file_types=FILE_DIALOG_TYPES)
        return self._controller.add_files(list(paths or []))

    def add_files(self, paths):
        return self._controller.add_files(paths)

    def remove(self, file_id):
        return self._controller.remove(file_id)

    def cancel(self, file_id):
        return self._controller.cancel(file_id)

    def retry(self, file_id):
        return self._controller.retry(file_id)

    def segments(self, file_id):
        return self._controller.segments(file_id)

    def copy_text(self, file_id, with_times, for_llm=False):
        return self._controller.copy_text(file_id, with_times, for_llm)

    def open_output(self, file_id, fmt):
        return self._controller.open_output(file_id, fmt)

    def create_output(self, file_id, fmt):
        return self._controller.create_output(file_id, fmt)

    def show_folder(self, file_id):
        return self._controller.show_folder(file_id)

    def clip(self, file_id, first, last):
        return self._controller.clip(file_id, first, last)

    def audio(self, file_id, convert=False):
        return self._controller.audio(file_id, convert)

    def reread(self, file_id, first, last, terms):
        return self._controller.reread(file_id, first, last, terms)

    def apply_fix(self, file_id, first, last, text, model):
        return self._controller.apply_fix(file_id, first, last, text, model)

    def find_suggestions(self, file_id):
        return self._controller.find_suggestions(file_id)

    def take_suggestion(self, file_id, position, index):
        return self._controller.take_suggestion(file_id, position, index)

    def leave_suggestion(self, file_id, position, index):
        return self._controller.leave_suggestion(file_id, position, index)

    def set_settings(self, change):
        return self._controller.set_settings(change)

    def reset_settings(self):
        return self._controller.reset_settings()

    def download(self):
        return self._controller.download()

    def decline_download(self):
        return self._controller.decline_download()

    def cancel_download(self):
        return self._controller.cancel_download()

    def close_anyway(self):
        """The user confirmed closing although a file or a download runs."""
        self._close_confirmed = True
        self._window.destroy()
        return True


class Sender(threading.Thread):
    """Delivers the controller's messages to the page, in order, from one thread."""

    def __init__(self, window, outbox):
        super().__init__(name="gigaam-sender", daemon=True)
        self.window = window
        self.outbox = outbox

    def run(self):
        while True:
            message = self.outbox.get()
            if message is None:
                return
            # ASCII only: pywebview's GTK backend passes the script's length in characters
            # where WebKit expects bytes, so Cyrillic text would cut the script short.
            payload = json.dumps(message, ensure_ascii=True)
            try:
                self.window.evaluate_js(f"window.gigaam && window.gigaam.receive({payload})")
            except Exception:  # the window is closing; nothing left to draw on
                return


# ---------------------------------------------------------------------- main

def main(argv=None, scenario=None):
    """Open the window with the files in argv. scenario(window, controller), if given,
    runs on its own thread once the window has started (tools/window_check.py)."""
    argv = sys.argv[1:] if argv is None else argv
    problem = missing_runtime()
    if problem:
        show_native_message(*problem)
        return 1
    import webview
    from webview.dom import DOMEventHandler

    theme = system_theme()
    events = queue.Queue()
    worker = WorkerProcess(events)  # the models run in their own process, so loading never freezes the window
    outbox = queue.Queue()
    controller = Controller(worker, events, send=outbox.put, initial_files=argv,
                            history=History(history_dir()))
    api = Api(controller)
    offscreen = os.environ.get("GIGAAM_WINDOW_OFFSCREEN") == "1"
    window = webview.create_window(
        TITLE, html=page_html(), js_api=api, width=1040, height=680, min_size=(720, 480),
        background_color=BACKGROUND[theme], text_select=True,
        **({"x": -6000, "y": -6000, "focus": False} if offscreen else {}))
    api._window = window
    sender = Sender(window, outbox)

    def on_drop(event):
        files = event.get("dataTransfer", {}).get("files", [])
        controller.add_files([item.get("pywebviewFullPath") for item in files])

    def on_loaded():
        # Python receives drops itself: only it gets the real paths of dropped files.
        window.dom.document.events.dragover += DOMEventHandler(lambda event: None, True, True)
        window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)

    def on_closing():
        # While a file or a download runs, ask first: the page shows the question and
        # calls close_anyway() if the user agrees. Returning False keeps the window open.
        if not api._close_confirmed and controller.ask_close():
            return False
        controller.close()
        outbox.put(None)
        return None

    window.events.loaded += on_loaded
    window.events.closing += on_closing
    worker.start()
    controller.start()
    sender.start()
    gui = "edgechromium" if sys.platform == "win32" else "gtk"
    if scenario:
        webview.start(scenario, (window, controller), gui=gui, private_mode=True, icon=str(ICON))
    else:
        webview.start(gui=gui, private_mode=True, icon=str(ICON))
    worker.stop()
    controller.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
