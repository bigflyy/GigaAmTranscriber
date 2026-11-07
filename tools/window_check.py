"""Drive the real window off screen and check what the page shows (plan 02, B3-B7).

On Windows the window opens at (-6000, -6000) without focus; on Linux it must
run under Xvfb (WAYLAND_DISPLAY unset, GDK_BACKEND=x11). So nothing appears on
the screen and the mouse and keyboard are not used. The page is clicked through
evaluate_js; the clipboard is never touched (copy is covered by the tests).

    python tools/window_check.py LONG_AUDIO SHORT_AUDIO --out FOLDER

LONG_AUDIO should take several seconds to transcribe (it is cancelled midway),
SHORT_AUDIO is transcribed twice. Transcripts are written beside both files, so
pass copies. A downloadable test model is served from a local HTTP server to
show the download dialog; its download folder is a temporary folder.
On Windows each step also saves a PNG of the window (PrintWindow).
Set GIGAAM_THEME=light or dark to fix the theme.

--whisper FOLDER names a downloaded Whisper model folder (whisper_large_v3_turbo_q5_0);
it is linked into the temporary download folder, and SHORT_AUDIO is transcribed with
Whisper and a chosen language too. Without it only the language choice is checked.
"""

import argparse
import functools
import hashlib
import shutil
import http.server
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gigaam_app import catalog, controller as controller_module, window as window_module  # noqa: E402

results = []
confirmed_close = []   # the controller, once the scenario has confirmed closing


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail else ""), flush=True)


def wait(condition, timeout, what):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        try:
            if condition():
                return True
        except Exception:  # the page may still be loading
            pass
        time.sleep(0.1)
    check(f"wait: {what}", False, f"not within {timeout:.0f} s")
    return False


class SlowFile(http.server.BaseHTTPRequestHandler):
    """Serves one file in small pieces, so the download dialog shows progress."""

    data = b""

    def do_GET(self):  # noqa: N802 - http.server's name
        self.send_response(200)
        self.send_header("Content-Length", str(len(self.data)))
        self.end_headers()
        for start in range(0, len(self.data), 65536):
            self.wfile.write(self.data[start:start + 65536])
            time.sleep(0.03)

    def log_message(self, *args):
        pass


def add_whisper(source, downloads):
    """Put a downloaded Whisper model folder into the temporary download folder: the
    ggml file as a hard link (no copy of 574 MB) when the drive allows it."""
    target = Path(downloads) / source.name
    target.mkdir()
    for item in source.iterdir():
        try:
            os.link(item, target / item.name)
        except OSError:
            shutil.copy2(item, target / item.name)


def add_test_model(folder):
    """Register a downloadable model "Test" whose only file is 2 MB of zeros (not a real model)."""
    SlowFile.data = bytes(2 * 1024 * 1024)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SlowFile)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    info = catalog.ModelInfo("Test", "test_model", "A test model that is not a real model",
                             files=(catalog.RemoteFile("model.json", len(SlowFile.data),
                                                       hashlib.sha256(SlowFile.data).hexdigest()),),
                             base_url=f"http://127.0.0.1:{server.server_port}")
    catalog.BY_KEY["Test"] = info
    controller_module.MODELS["Test"] = info.folder
    os.environ["GIGAAM_DOWNLOADS"] = str(folder)


def screenshot_function(out):
    if sys.platform != "win32":
        # Under Xvfb: grab the whole X screen with the system Python's GTK.
        grab = ("import sys, gi; gi.require_version('Gdk', '3.0'); from gi.repository import Gdk; "
                "r = Gdk.get_default_root_window(); "
                "Gdk.pixbuf_get_from_window(r, 0, 0, r.get_width(), r.get_height()).savev(sys.argv[1], 'png', [], [])")

        def shoot_x11(name):
            if os.environ.get("DISPLAY"):
                time.sleep(0.3)
                subprocess.run(["python3", "-c", grab, str(Path(out) / f"{name}.png")], timeout=30)
        return shoot_x11
    import ctypes
    import gui_smoke_test as smoke

    def find():
        found = []

        def callback(hwnd, _):
            pid = ctypes.c_ulong()
            smoke.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            buffer = ctypes.create_unicode_buffer(256)
            smoke.user32.GetWindowTextW(hwnd, buffer, 256)
            if pid.value == os.getpid() and buffer.value == window_module.TITLE:
                found.append(hwnd)
            return True
        smoke.user32.EnumWindows(smoke.EnumProc(callback), 0)
        return found[0] if found else None

    def shoot(name):
        hwnd = find()
        if hwnd:
            time.sleep(0.3)  # let the page finish painting
            smoke.save_png(hwnd, str(Path(out) / f"{name}.png"))
    return shoot


def whisper_steps(js, control, short_audio, shoot, real):
    """Settings: the language choice shows only for Whisper and is saved; with the real
    model, SHORT_AUDIO is transcribed by Whisper with the language chosen."""
    check("no language choice for GigaAM", js("$('language-box').hidden"))
    check("Whisper is offered", js("!!document.querySelector('#models input[value=Whisper]')"))
    if not real:
        return
    js("document.querySelector('#models input[value=Whisper]').click()")
    wait(lambda: not js("$('language-box').hidden"), 10, "language choice")
    check("language choice for Whisper", not js("$('language-box').hidden")
          and js("$('language').value") == "auto")
    js("$('language').value = 'ru'; $('language').dispatchEvent(new Event('change'))")
    saved = lambda: '"language": "ru"' in Path(os.environ["GIGAAM_CONFIG"]).read_text("utf-8")  # noqa: E731
    wait(saved, 10, "language saved")
    check("language saved at once", saved())
    wait(lambda: "Whisper" in js("$('engine-text').textContent") and control.engine["state"] == "ready",
         120, "Whisper loaded")
    engine_text = js("$('engine-text').textContent")
    check("Whisper loaded", "Whisper" in engine_text, engine_text)
    shoot("08a-settings-whisper")
    js("$('close-settings').click()")
    # A copy under another name: the list refuses a file it already holds.
    copy = Path(os.environ["GIGAAM_DOWNLOADS"]) / ("whisper-" + Path(short_audio).name)
    shutil.copy2(short_audio, copy)
    before = len(control.files)
    control.add_files([str(copy)])
    wait(lambda: len(control.files) > before and control.files[-1].state in ("done", "failed"), 300,
         "Whisper transcription")
    item = control.files[-1]
    check("Whisper transcribed the file", item.state == "done" and item.segments
          and item.result.model == "Whisper", item.state)
    js("[...document.querySelectorAll('#files li')].find(li => li.textContent.includes('whisper-')).click()")
    time.sleep(0.3)
    shoot("08b-whisper-file")
    js("$('open-settings').click()")
    js("document.querySelector('#models input[value=RNNT]').click()")
    wait(lambda: js("$('language-box').hidden"), 10, "language choice hidden again")


def scenario(window, control, long_audio, short_audio, shoot, whisper=False):
    js = window.evaluate_js
    try:
        wait(lambda: js("typeof state !== 'undefined' && state.booted"), 30, "page ready")
        check("page booted", js("state.booted"))
        wait(lambda: control.engine["state"] == "ready", 60, "model loaded")
        # The page gets each change a moment after the controller: wait for it before reading it.
        wait(lambda: js("$('engine').className") == "engine ready", 10, "page shows the model")
        check("engine text", "RNNT" in js("$('engine-text').textContent"), js("$('engine-text').textContent"))
        shoot("01-empty")

        # B3: two files, the first runs, the second waits.
        control.add_files([str(long_audio), str(short_audio)])
        wait(lambda: js("$('text').querySelectorAll('p:not(.placeholder)').length") >= 2, 120, "live text")
        items = js("[...document.querySelectorAll('#files li')].map(li => li.className)")
        check("list shows running and waiting", items == ["file running selected", "file waiting"], items)
        check("running status", js("$('file-status').textContent").startswith(("Распознаю", "Поиск")),
              js("$('file-status').textContent"))
        shoot("02-running")

        # E1: a file without sound (a txt) is not added; a toast names it.
        notes = Path(tempfile.mkdtemp(prefix="gigaam-check-")) / "notes.txt"
        notes.write_text("просто текст", encoding="utf-8")
        count = len(control.files)
        control.add_files([str(notes)])
        wait(lambda: not js("$('toast').hidden"), 10, "toast for the txt")
        toast = js("$('toast').textContent")
        check("a txt is refused with a note", len(control.files) == count and "notes.txt" in toast, toast)
        shoot("02a-txt-refused")

        # Closing while a file runs asks first; "Ne zakryvat" keeps the window and the file.
        window.destroy()
        wait(lambda: js("$('confirm-close').open"), 10, "close question")
        check("close asks while a file runs", "Идёт распознавание" in js("$('confirm-close-text').textContent"),
              js("$('confirm-close-text').textContent"))
        shoot("02b-close-question")
        js("$('confirm-close-no').click()")
        time.sleep(0.3)
        check("not closing keeps the file running",
              control.files[0].state == "running" and not js("$('confirm-close').open"))

        # Cancel the long file: its text so far is kept and saved; the short one starts.
        js("$('file-cancel').click()")
        wait(lambda: control.files[0].state == "cancelled", 60, "cancelled")
        wait(lambda: control.files[1].state == "done", 120, "short file done")
        wait(lambda: js("document.querySelectorAll('#files li')[1].classList.contains('done')"), 10, "page shows done")
        js("document.querySelectorAll('#files li')[0].click()")
        status = js("$('file-status').textContent")
        check("cancelled status", status.startswith(("Отменено на", "Отменено до")), status)
        # The page asks for the file's text after the click; wait for it instead of reading at once.
        check("cancelled text kept",
              wait(lambda: js("$('text').querySelectorAll('p:not(.placeholder)').length") > 0, 10, "cancelled text"))
        shoot("03-cancelled")

        # B4: timecodes switch, saved files, create a missing format.
        before = js("$('text').classList.contains('with-times')")
        js("$('times').click()")
        check("timecodes switch", js("$('text').classList.contains('with-times')") != before)
        js("$('times').click()")
        js("document.querySelectorAll('#files li')[1].click()")
        chips = js("[...document.querySelectorAll('#saved-list .chip')].map(c => c.textContent)")
        check("saved chips", chips[:2] == ["TXTТекст", "TXTС таймкодами"], chips)
        # Scripts sent to the page stay ASCII: pywebview on GTK cuts non-ASCII scripts short.
        js("document.querySelector('#saved-list .chip[data-format=srt]').click()")
        srt = Path(short_audio).with_name(Path(short_audio).stem + "-transcript.srt")
        wait(lambda: srt.is_file(), 10, "SRT written")
        check("SRT created from the page", srt.is_file() and srt.stat().st_size > 0)
        js("document.querySelector('#saved-list .chip[data-format=md]').click()")
        markdown = Path(short_audio).with_name(Path(short_audio).stem + "-transcript.md")
        wait(lambda: markdown.is_file(), 10, "Markdown written")
        check("Markdown created from the page",
              markdown.is_file() and markdown.read_text(encoding="utf-8").startswith("# " + Path(short_audio).name))
        shoot("04-done")

        # Retry the short file, remove the cancelled one.
        js("$('file-retry').click()")
        wait(lambda: control.files[1].state == "running", 10, "retry started")
        wait(lambda: control.files[1].state == "done", 120, "retry done")
        wait(lambda: js("document.querySelectorAll('#files li')[1].classList.contains('done')"), 10, "page shows done")
        check("retry finished", control.files[1].state == "done")
        js("document.querySelectorAll('#files li')[0].querySelector('.remove').click()")
        wait(lambda: js("document.querySelectorAll('#files li').length") == 1, 10, "removed")
        check("remove", js("document.querySelectorAll('#files li').length") == 1)

        # B5: settings view, device change reloads the model.
        js("$('open-settings').click()")
        check("settings view", not js("$('view-settings').hidden"))
        shoot("05-settings")
        js("document.querySelector('#devices input[value=CPU]').click()")
        # Wait for the page, not only the controller: its message can arrive a moment later.
        wait(lambda: "процессор" in js("$('engine-text').textContent"), 60, "CPU model")
        check("device CPU", "процессор" in js("$('engine-text').textContent"), js("$('engine-text').textContent"))
        # Settings are saved at once; "Sbrosit" goes back to the defaults (device Auto).
        check("settings saved at once", '"device": "CPU"' in Path(os.environ["GIGAAM_CONFIG"]).read_text("utf-8"))
        js("$('reset-settings').click()")
        wait(lambda: js("$('reset-note').textContent") != "", 10, "reset note")
        check("reset to defaults", js("document.querySelector('#devices input[value=Auto]').checked")
              and '"device": "Auto"' in Path(os.environ["GIGAAM_CONFIG"]).read_text("utf-8"))
        time.sleep(0.5)
        wait(lambda: control.engine["state"] == "ready", 60, "model with Auto")

        # Download dialog: ask, decline, ask again, download with progress.
        js("document.querySelector('#models input[value=Test]').click()")
        wait(lambda: js("$('download').open"), 10, "download question")
        check("download question", "2 МБ" in js("$('download-text').textContent"))
        shoot("06-download-ask")
        js("$('download-no').click()")
        check("decline closes", not js("$('download').open"))
        js("document.querySelector('#models input[value=RNNT]').click()")
        js("document.querySelector('#models input[value=Test]').click()")
        wait(lambda: js("$('download').open"), 10, "download question again")
        js("$('download-yes').click()")
        wait(lambda: not js("$('download-progress').hidden"), 10, "download progress")
        time.sleep(0.4)
        shoot("07-download-progress")
        wait(lambda: not js("$('download').open"), 60, "download finished")
        check("downloaded", catalog.installed_folder(catalog.BY_KEY["Test"]) is not None)
        # The test model is not a real model, so loading it must fail visibly.
        wait(lambda: js("$('engine').className") == "engine error", 30, "test model fails to load")
        check("load error shown", js("$('engine').className") == "engine error")
        wait(lambda: not js("$('banner').hidden"), 10, "error banner")
        banner = js("$('banner-text').textContent")
        check("banner names the model", banner.startswith("Не удалось загрузить модель Test"), banner)
        js("document.querySelector('#models input[value=RNNT]').click()")
        js("$('close-settings').click()")
        wait(lambda: control.engine["state"] == "ready", 60, "RNNT again")
        time.sleep(0.3)
        check("banner closes once a model loads", js("$('banner').hidden"))
        shoot("08-end")

        # Whisper (plan 04 B4): language choice, and a file transcribed with the real model.
        js("$('open-settings').click()")
        whisper_steps(js, control, short_audio, shoot, whisper)
        js("$('close-settings').click()")
        wait(lambda: control.engine["state"] == "ready" and "RNNT" in js("$('engine-text').textContent"),
             60, "RNNT after Whisper")

        # Closing while a file runs, then "Zakryt": the window closes and the file stops.
        for written in Path(long_audio).parent.glob(Path(long_audio).stem + "-transcript*"):
            written.unlink()  # from the cancelled run above; closing must write it again
        control.add_files([str(long_audio)])
        wait(lambda: control.running is not None and control.running.segments, 120, "long file again")
        window.destroy()
        wait(lambda: js("$('confirm-close').open"), 10, "close question again")
        confirmed_close.append(control)  # main() checks the result once the window is gone
        js("$('confirm-close-yes').click()")
        return
    except Exception as error:
        check("scenario", False, repr(error))
    finally:
        if not confirmed_close:  # else the window is already closing
            control.close_question = lambda: None  # close without asking, whatever still runs
            window.destroy()


def second_session(window, control, short_audio, long_audio):
    """The window opened again: files from the first session are back, with their text."""
    js = window.evaluate_js
    try:
        wait(lambda: js("typeof state !== 'undefined' && state.booted"), 30, "page ready again")
        files = js("state.files.map(f => [f.name, f.state])")
        # The Whisper steps add a third file; it does not change these two.
        files = [entry for entry in files if not entry[0].startswith("whisper-")]
        check("files come back in the next session",
              files[:2] == [[Path(short_audio).name, "done"], [Path(long_audio).name, "cancelled"]], files)
        check("the newest is selected with its text",
              js("state.selected") == js("state.files[state.files.length - 1].id")
              and js("$('text').querySelectorAll('p:not(.placeholder)').length") > 0)
        js("document.querySelectorAll('#files li')[0].click()")
        wait(lambda: js("$('text').querySelectorAll('p:not(.placeholder)').length") > 0, 10, "restored text")
        chips = js("[...document.querySelectorAll('#saved-list .chip')].map(c => c.dataset.format)")
        check("restored file offers its saved files", chips[:4] == ["txt", "timestamps", "md", "srt"], chips)
        shoot_again("09-next-session")
    except Exception as error:
        check("second session", False, repr(error))
    finally:
        window.destroy()


shoot_again = lambda name: None  # noqa: E731 - set in main()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("long_audio", type=Path)
    parser.add_argument("short_audio", type=Path)
    parser.add_argument("--out", type=Path, default=Path("."), help="folder for the PNGs")
    parser.add_argument("--whisper", type=Path, help="a downloaded Whisper model folder to transcribe with")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.environ["GIGAAM_WINDOW_OFFSCREEN"] = "1"
    elif os.environ.get("WAYLAND_DISPLAY") or os.environ.get("GDK_BACKEND") != "x11":
        # Under WSLg the window would show on the real screen: run under Xvfb instead.
        raise SystemExit("Run under Xvfb: unset WAYLAND_DISPLAY, set GDK_BACKEND=x11, use xvfb-run.")
    global shoot_again
    with tempfile.TemporaryDirectory(prefix="gigaam-check-") as downloads,             tempfile.TemporaryDirectory(prefix="gigaam-history-") as history:
        os.environ["GIGAAM_HISTORY"] = history  # never the user's own list
        os.environ["GIGAAM_CONFIG"] = str(Path(history) / "settings.json")  # nor the user's settings
        add_test_model(downloads)
        if args.whisper:
            add_whisper(args.whisper.resolve(), downloads)
        shoot_again = screenshot_function(args.out)
        run = functools.partial(scenario, long_audio=args.long_audio.resolve(),
                                short_audio=args.short_audio.resolve(), shoot=shoot_again,
                                whisper=args.whisper is not None)
        window_module.main([], scenario=run)
        if confirmed_close:
            window_module.main([], scenario=functools.partial(second_session, short_audio=args.short_audio.resolve(),
                                                                   long_audio=args.long_audio.resolve()))
    if confirmed_close:
        control = confirmed_close[0]
        check("closing after the question stops the file", control.worker.cancel.is_set())
        # The window waits for the worker, so the text found before closing is on disk.
        check("text found before closing is saved",
              args.long_audio.with_name(args.long_audio.stem + "-transcript.txt").is_file())
    failed = [name for name, ok in results if not ok]
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed or not results else 0


if __name__ == "__main__":
    raise SystemExit(main())
