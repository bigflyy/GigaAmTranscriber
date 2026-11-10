"""Drive the real window off screen and check what the page shows (plan 02 B3-B7, plan 03).

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

--fast-whisper FOLDER names a downloaded faster-whisper model folder (plan 08 C2, with its
model.json); it is linked in as faster_whisper_large_v3_turbo_int8, chosen in Настройки, and
the suggestion search reads the short file with it on the CPU. Without it the choice asks
the download question and "Не сейчас" is checked.
"""

import argparse
import functools
import hashlib
import json
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

from gigaam_app import catalog, controller as controller_module, outputs, window as window_module  # noqa: E402
from build_windows import link_model_folder  # noqa: E402  (tools/, beside this script)

results = []
confirmed_close = []   # the controller, once the scenario has confirmed closing


def clock_text(seconds):
    """The page's timecode (app.js clock): 00:09, 12:04, 1:02:03."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f": {detail}" if detail else ""), flush=True)


def settings_text():
    """The test's settings file. On Windows a read can meet the moment the app replaces the
    file (PermissionError); try again for up to a second, then give up with ""."""
    for _ in range(10):
        try:
            return Path(os.environ["GIGAAM_CONFIG"]).read_text("utf-8")
        except PermissionError:
            time.sleep(0.1)
    return ""


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
    saved = lambda: '"language": "ru"' in settings_text()  # noqa: E731
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
    model_line = js("$('file-model').hidden ? '' : $('file-model').textContent")
    check("Whisper file names its model", "Whisper large-v3-turbo" in model_line, model_line)
    shoot("08b-whisper-file")
    js("$('open-settings').click()")
    js("document.querySelector('#models input[value=RNNT]').click()")
    wait(lambda: js("$('language-box').hidden"), 10, "language choice hidden again")


def fix_steps(js, control, item, short_audio, shoot):
    """Plan 03 Stage A on the finished short file: select words, the bar shows; listen
    (muted); recognise again (a reading per installed model); save text typed by hand,
    which reaches the page, the saved txt and the history."""
    js("document.querySelectorAll('#files li')[1].click()")
    wait(lambda: js("$('text').querySelectorAll('.w').length") > 4, 10, "words of the short file")
    # Select words 1..3 of the first line the way a mouse drag would, then release.
    js("(() => { const p = $('text').querySelector('.seg[data-seg=\"0\"]'); const r = document.createRange();"
       " r.setStart(p.querySelector('[data-w=\"1\"]').firstChild, 0);"
       " r.setEnd(p.querySelector('[data-w=\"3\"]').firstChild, 1);"
       " const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);"
       " document.dispatchEvent(new PointerEvent('pointerup')); })()")
    wait(lambda: not js("$('sel-bar').hidden"), 5, "selection bar")
    check("selection bar shows", not js("$('sel-bar').hidden"))
    check("selection maps to words", js("selection && selection.first.join() + '-' + selection.last.join()") == "0,1-0,3",
          js("selection && selection.first.join() + '-' + selection.last.join()"))
    shoot("04a-selection-bar")
    js("filePlayer.muted = true; player.muted = true; $('sel-play').click()")  # never sound during a test
    wait(lambda: js("!filePlayer.paused && filePlayer.currentTime > 0"), 10, "selection playing")
    check("listen plays the file from the local server", js("filePlayer.src.startsWith('http://127.0.0.1:')"))
    end = js("wordOf(selection.fileId, selection.last)[1]")
    wait(lambda: js("filePlayer.paused"), 10, "selection played to its end")
    stopped = js("filePlayer.currentTime")
    check("the selection stops at its end", js("filePlayer.paused") and end - 0.05 <= stopped <= end + 0.5,
          f"stopped at {stopped:.2f}, ends at {end:.2f}")
    # G7: "Otsyuda" plays from the selection's start and goes on past its end.
    begin = js("wordOf(selection.fileId, selection.first)[0]")
    js("$('sel-from').click()")
    wait(lambda: js("!filePlayer.paused && filePlayer.currentTime > " + str(end + 0.6)), 10, "playing on from the selection")
    check("Otsyuda starts at the selection and keeps going", js("!filePlayer.paused") and js("audio.stopAt") is None
          and js("filePlayer.currentTime") > end + 0.6,
          f"at {js('filePlayer.currentTime'):.2f}, selection {begin:.2f}-{end:.2f}")
    js("filePlayer.pause()")
    current = js("wordsBetween(selection.fileId, selection.first, selection.last).join(' ')")
    js("$('sel-reread').click()")
    wait(lambda: js("$('fix').open"), 5, "fix dialog")
    models = [key for key in controller_module.REREAD_MODELS if control._model_installed(key)]
    wait(lambda: js("$('fix-readings').querySelectorAll('.reading').length") == len(models) + 1
         and not js("$('fix-reread').disabled"), 120, "readings")
    readings = js("[...$('fix-readings').querySelectorAll('.reading')].map(li => li.textContent)")
    check("a reading per installed model", len(readings) == len(models) + 1
          and all("Распознаю" not in text and "Загрузка" not in text for text in readings), readings)
    check("dialog shows the selected text", js("$('fix-text').value") == current, js("$('fix-text').value"))
    js("$('fix-play').click()")
    wait(lambda: js("player.src.startsWith('data:audio/wav')"), 10, "clip")
    check("the dialog plays its own WAV clip", js("player.src.startsWith('data:audio/wav') && player.src.length > 1000"))
    js("stopPlaying()")
    shoot("04b-fix-dialog")
    # A click on the backdrop closes the dialog; with the text changed by hand it does not.
    press_outside = "$('fix').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, clientX: 2, clientY: 2}));"
    click_outside = press_outside + "$('fix').dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: 2, clientY: 2}))"
    js("$('fix-text').value = 'check fix words'; " + click_outside)
    check("click outside keeps an edited dialog", js("$('fix').open"))
    # Selecting in the text field and letting go outside: the press was inside (owner 2026-11-10).
    js("$('fix-text').value = fix.current;"
       " $('fix-text').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true, clientX: 300, clientY: 300}));"
       " $('fix').dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: 2, clientY: 2}))")
    check("a selection that ends outside keeps the dialog", js("$('fix').open"))
    js(click_outside)
    check("click outside closes the dialog", not js("$('fix').open"))
    js("$('fix').showModal()")
    js("$('fix-text').value = 'check fix words'; $('fix-save').click()")
    wait(lambda: not js("$('fix').open"), 10, "dialog closes")
    wait(lambda: "check fix words" in js("$('text').textContent"), 10, "fixed text on the page")
    check("fixed text on the page", "check fix words" in js("$('text').textContent"))
    check("fixed text in the transcript", "check fix words" in item.segments[0].text, item.segments[0].text)
    txt = Path(short_audio).with_name(Path(short_audio).stem + "-transcript.txt")
    check("saved txt written again", "check fix words" in txt.read_text(encoding="utf-8"))
    remembered = Path(os.environ["GIGAAM_HISTORY"]) / f"{item.saved_as}.json"
    check("history updated", "check fix words" in remembered.read_text(encoding="utf-8"))
    shoot("04c-fixed")


def doubt_steps(js, control, item, shoot):
    """Plan 03 B2 on the finished short file: words carry the model's confidence, doubtful
    ones are underlined, the switch hides the marks, Settings switches to colouring all words."""
    js("document.querySelectorAll('#files li')[1].click()")
    wait(lambda: js("$('text').querySelectorAll('.w').length") > 4, 10, "words of the short file")
    words = [word for segment in item.segments for word in segment.words]
    known = [word for word in words if word.confidence is not None]
    check("words have a confidence", len(known) >= len(words) - 3 and known, f"{len(known)} of {len(words)}")
    check("page words carry it", js("$('text').querySelectorAll('.w[data-c]').length") == len(known))
    doubtful = sum(1 for word in known if word.confidence < 0.97)
    check("doubtful words are marked", js("$('text').querySelectorAll('.w.d1, .w.d2').length") == doubtful,
          f"{doubtful} below 0.97: " + ", ".join(f"{w.text} {w.confidence}" for w in known if w.confidence < 0.97))
    check("marks on by default", js("$('doubts').checked && $('text').classList.contains('doubts-underline')"))
    # The look of each mark, on the first word given each class for a moment.
    looks = js("(() => { const w = $('text').querySelector('.w'); const had = w.className; const out = [];"
               " for (const c of ['d1', 'd2']) { w.className = 'w ' + c; const s = getComputedStyle(w);"
               " out.push(s.textDecorationLine + ' ' + s.textDecorationStyle); }"
               " w.className = had; return out; })()")
    check("dotted and wavy underlines", looks == ["underline dotted", "underline wavy"], looks)
    title = js("(() => { const w = $('text').querySelector('.w.d1, .w.d2'); if (!w) return 'none';"
               " w.dispatchEvent(new MouseEvent('mouseover', {bubbles: true})); return w.title; })()")
    # The suggestion search may have finished by now: then a second line names the offer.
    first_line = title.split("\n")[0]
    check("hover names the confidence", title == "none" or ("ошибка: уверенность модели" in title
                                                             and first_line.endswith("%")), title)
    # A higher dotted threshold in Settings marks more words at once.
    js("$('doubt-light').value = 99; $('doubt-light').dispatchEvent(new Event('change'))")
    more = sum(1 for word in known if word.confidence < 0.99)
    wait(lambda: js("$('text').querySelectorAll('.w.d1, .w.d2').length") == more, 5, "threshold 99 %")
    wait(lambda: '"doubt_light": 0.99' in settings_text(), 5, "threshold saved")
    check("threshold from Settings", js("$('text').querySelectorAll('.w.d1, .w.d2').length") == more
          and '"doubt_light": 0.99' in settings_text(), more)
    js("$('doubt-light').value = 97; $('doubt-light').dispatchEvent(new Event('change'))")
    js("$('doubt-strong').value = 98; $('doubt-strong').dispatchEvent(new Event('change'))")
    check("wavy threshold above dotted is refused", js("$('doubt-strong').value") == "80")
    shoot("04d-doubts")
    js("$('doubts').click()")
    check("switch hides the marks", not js("$('text').classList.contains('doubts-underline')"))
    wait(lambda: '"doubt_marks": false' in settings_text(), 5, "switch saved")
    js("$('doubts').click()")
    js("document.querySelector('input[name=doubt-style][value=colors]').click()")
    wait(lambda: js("$('text').classList.contains('doubts-colors')"), 5, "colour style")
    colours = js("(() => { const w = $('text').querySelector('.w.c0'); return w ? [getComputedStyle(w).color,"
                 " getComputedStyle($('text')).color] : null; })()")
    check("colour style paints the words", colours is not None and colours[0] != colours[1], colours)
    # The gradient: a word between two steps gets a colour between theirs.
    blend = js("(() => { const w = $('text').querySelector('.w'); const had = w.dataset.c; const out = [];"
               " for (const c of ['0.98', '0.95', '0.92']) { w.dataset.c = c; markWord(w); out.push(getComputedStyle(w).color); }"
               " w.dataset.c = had; markWord(w); return out; })()")
    check("colours slide between the steps", len(set(blend)) == 3, blend)
    wait(lambda: '"doubt_style": "colors"' in settings_text(), 5, "colour style saved")
    check("colour style saved", '"doubt_style": "colors"' in settings_text())
    shoot("04e-doubt-colours")
    js("document.querySelector('input[name=doubt-style][value=underline]').click()")
    wait(lambda: js("$('text').classList.contains('doubts-underline')"), 5, "underline style again")


def follow_steps(js, item, shoot):
    """Plan 07 H1: new lines never pull the text down by themselves.

    The page gets made-up lines through its own onSegment (a real file is too short to fill
    the window), then the shown file is fetched again, so later steps see its real text."""
    fid = json.dumps(item.id)
    js(f"select({fid}, true)")
    wait(lambda: js("$('text').querySelectorAll('.para').length") > 0, 10, "text for the follow steps")

    def feed(count):
        # Each made-up line ends a sentence, so it is a paragraph of its own (ASCII only).
        js(f"""(() => {{ const lines = state.lines.get({fid});
            for (let k = 0; k < {count}; k += 1) {{ const at = lines.length;
              onSegment({{id: {fid}, index: at, start: 100 + at * 4, end: 103 + at * 4,
                          text: 'Made-up line ' + at + ' that arrives while the file is read.', words: []}}); }}
          }})()""")

    def at_end():
        return js("textAtEnd($('text'))")

    js("$('text').scrollTop = 0")
    feed(40)
    time.sleep(0.3)
    check("new lines do not pull the text down", js("$('text').scrollTop") == 0 and not at_end(),
          js("[$('text').scrollTop, $('text').scrollHeight, $('text').clientHeight]"))
    check("a 'Novyi tekst' button shows when text came below", not js("$('new-text').hidden"))
    shoot("02c-new-text")
    js("$('new-text').click()")
    time.sleep(0.3)
    check("the button takes the reader to the end and hides", at_end() and js("$('new-text').hidden"))
    feed(3)
    time.sleep(0.3)
    check("at the end the text follows new lines", at_end() and js("$('new-text').hidden"))
    js("$('text').scrollTop = 0")
    wait(lambda: not js("followText"), 5, "scrolling up stops following")
    feed(3)
    time.sleep(0.3)
    check("after scrolling up new lines leave the text where it is",
          js("$('text').scrollTop") == 0 and not js("$('new-text').hidden"))
    js("$('text').scrollTop = $('text').scrollHeight")
    wait(lambda: js("followText"), 5, "scrolling to the end starts following")
    feed(2)
    time.sleep(0.3)
    check("scrolling to the end by hand follows again", at_end() and js("$('new-text').hidden"))
    js(f"refreshLines({fid})")
    wait(lambda: js(f"(state.lines.get({fid}) || []).length") == len(item.segments), 10, "real text again")


def speech_steps(js, shoot):
    """Plan 07 H2: the folded speech search settings save at once and go back to the default."""
    check("the advanced part starts folded", js("$('advanced').open") is False)
    js("$('advanced').open = true; $('advanced').scrollIntoView()")
    shown = js("[$('vad-pause').value, $('vad-threshold').value, $('max-line').value]")
    check("speech settings show the defaults", shown == ["2", "50", "25"], shown)
    check("at the default a note, no link", not js("$('vad-pause-note').hidden") and js("$('vad-pause-default').hidden"))

    def put(field, value):
        js(f"$('{field}').value = '{value}'; $('{field}').dispatchEvent(new Event('change'))")

    put("vad-pause", "0.8")
    wait(lambda: '"vad_min_silence_ms": 800' in settings_text(), 10, "pause saved")
    wait(lambda: not js("$('vad-pause-default').hidden"), 10, "default link")
    link = js("$('vad-pause-default').textContent")
    check("a changed pause offers its default", "2 с" in link and js("$('vad-pause-note').hidden"), link)
    put("vad-threshold", "35")
    wait(lambda: '"vad_threshold": 0.35' in settings_text(), 10, "threshold saved")
    put("max-line", "40")
    wait(lambda: '"vad_max_speech_s": 25.0' in settings_text() and js("$('max-line').value") == "25", 10,
         "longest line kept at 25 s")
    put("max-line", "15")
    wait(lambda: '"max_duration": 15.0' in settings_text(), 10, "longest line saved")
    check("the longest line sets both keys", '"vad_max_speech_s": 15.0' in settings_text())
    shoot("05a-advanced")
    js("$('vad-pause-default').click()")
    wait(lambda: '"vad_min_silence_ms": 2000' in settings_text(), 10, "pause back to the default")
    check("the default link puts the default back", js("$('vad-pause').value") == "2" and js("$('vad-pause-default').hidden"))


def whisper_cpu_steps(js, control, shoot, fast):
    """Plan 08 C2: "Whisper на процессоре" in Настройки (layout B, two cards). Without a
    faster-whisper model, choosing it asks the download question and "Не сейчас" goes back
    to whisper.cpp. With --fast-whisper (a downloaded model linked in) it is chosen at once,
    and with the device "Процессор" the search reads the shown file with it."""
    keys = js("[...document.querySelectorAll('#whisper-cpu input')].map((input) => input.value)")
    check("two Whisper engines are offered", keys == ["whisper.cpp", "faster-whisper"], keys)
    check("whisper.cpp is the default", js("document.querySelector('#whisper-cpu input[value=\"whisper.cpp\"]').checked"))
    note = js("$('whisper-cpu').querySelectorAll('.choice-note')[1].textContent")
    js("$('whisper-cpu').scrollIntoView()")
    if not fast:
        check("faster-whisper says it is downloaded separately", "Скачивается отдельно, 780 МБ" in note, note)
        js("document.querySelector('#whisper-cpu input[value=\"faster-whisper\"]').click()")
        wait(lambda: js("$('download').open"), 10, "faster-whisper download question")
        check("the question names faster-whisper", js("$('download-title').textContent") == "Скачать модель faster-whisper"
              and "780 МБ" in js("$('download-text').textContent"), js("$('download-text').textContent"))
        shoot("05b-whisper-cpu-ask")
        js("$('download-no').click()")
        wait(lambda: js("document.querySelector('#whisper-cpu input[value=\"whisper.cpp\"]').checked"), 10,
             "whisper.cpp again")
        check("\"Не сейчас\" goes back to whisper.cpp", '"whisper_cpu": "whisper.cpp"' in settings_text()
              and control.engine["state"] == "ready")
        return
    check("faster-whisper is downloaded", note.endswith("Скачана."), note)
    js("document.querySelector('#whisper-cpu input[value=\"faster-whisper\"]').click()")
    wait(lambda: '"whisper_cpu": "faster-whisper"' in settings_text(), 10, "faster-whisper saved")
    check("no question for a downloaded model", not js("$('download').open"))
    shoot("05b-whisper-cpu")
    js("document.querySelector('#devices input[value=CPU]').click()")
    wait(lambda: control.engine["state"] == "ready" and "процессор" in js("$('engine-text').textContent"), 60, "CPU model")
    item = control.files[0]
    check("the search would use faster-whisper", control._suggest_models(item) == [catalog.FAST_WHISPER_MODEL.key],
          control._suggest_models(item))
    began = time.perf_counter()
    errors, notice = [], control._notice
    control._notice = lambda text: (errors.append(text), notice(text))  # a failed search says so here
    control.find_suggestions(item.id)
    wait(lambda: item.result.suggestions_searched and control.suggesting is None, 600, "faster-whisper search")
    control._notice = notice
    offered = [(word.text, offer["models"], [row[2] for row in offer["words"]])
               for segment in item.segments for word in segment.words for offer in word.suggestions or []]
    check("faster-whisper searched the file without an error", item.result.suggestions_searched and not errors,
          f"{time.perf_counter() - began:.1f} s; offers {offered}; notices {errors}")


def add_steps(js, control, long_audio, short_audio, shoot):
    """Plan 07 H3: the first added file shows at once (also from Настройки); when the next
    file starts, the window moves to it only if the reader has not touched the shown file."""
    folder = Path(tempfile.mkdtemp(prefix="gigaam-added-"))
    copies = {}
    for name, source in (("added-short", short_audio), ("added-short2", short_audio),
                         ("added-long", long_audio), ("added-short3", short_audio)):
        copies[name] = folder / (name + Path(source).suffix)
        shutil.copy2(source, copies[name])

    def shown():
        return js("(fileById(state.selected) || {}).name")

    def finished(*names):
        states = {item.path.stem: item.state for item in control.files}
        return all(states.get(name) in ("done", "failed") for name in names)

    js("document.querySelectorAll('#files li')[0].click()")  # reading a file picked by hand
    reading = shown()
    js("$('open-settings').click()")
    control.add_files([str(copies["added-short"]), str(copies["added-short2"])])
    check("adding shows the first added file at once, also from the settings",
          wait(lambda: shown() == copies["added-short"].name and js("state.view") == "file", 10,
               "first added file shown"), f"{reading} -> {shown()}")
    wait(lambda: finished("added-short", "added-short2"), 120, "two added files recognised")
    check("untouched, the window follows the queue to the next file",
          wait(lambda: shown() == copies["added-short2"].name, 10, "next file shown"), shown())
    control.add_files([str(copies["added-long"]), str(copies["added-short3"])])
    wait(lambda: shown() == copies["added-long"].name, 10, "long added file shown")
    js("$('text').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}))")  # the reader clicks
    wait(lambda: finished("added-long", "added-short3"), 180, "long and short added files recognised")
    time.sleep(0.5)
    check("a file the reader touched stays on screen when the next one starts",
          shown() == copies["added-long"].name, shown())
    shoot("02d-added-stays")


def open_menu(js, anchor):
    """Open the popup menu of a button (plan 07 G: "...", "Файлы", the copy arrow, a speaker
    chip or name) given as a page expression; returns [[data-item, text]] of its items."""
    js(f"closeMenu(); {anchor}.click()")
    wait(lambda: not js("$('menu').hidden"), 5, f"menu of {anchor}")
    return js("[...$('menu').querySelectorAll('.menu-item')].map(b => [b.dataset.item || '', b.textContent])")


def menu_texts(js, anchor):
    """The items of a menu as {data-item: text}; the menu is closed again."""
    items = dict(open_menu(js, anchor))
    js("closeMenu()")
    return items


def choose(js, anchor, item):
    """Open a menu and click the item with this data-item (ASCII, so no quotes needed)."""
    items = open_menu(js, anchor)
    js(f"$('menu').querySelector('[data-item={item}]').click()")
    return items


def suggest_steps(js, control, item, shoot):
    """Plan 06 on the finished short file: after it was recognised, its doubtful words were
    read again by the other models in the background. The status line reports the search; a
    word with an offer has a blue underline and a hover text; a click opens the card, and
    "Vzyat" puts the offer into the text. If the real models offered nothing on this clip,
    one test offer is added so the page is still checked."""
    from gigaam_app import fix
    from gigaam_app.engine import Word
    js("document.querySelectorAll('#files li')[1].click()")
    wait(lambda: js("$('text').querySelectorAll('.w').length") > 4, 10, "words of the short file")
    if not control._suggest_by_itself(item):
        # Recognised on the CPU (WSL, a PC without a GPU): by default only the button
        # searches (plan 06 B5), so nothing ran by itself; the button starts it.
        time.sleep(1)
        check("on the CPU no search by itself", not item.result.suggestions_searched and control.suggesting is None
              and item.id not in control.suggest_queue)
        offered_item = menu_texts(js, "$('more-button')").get("find-suggest", "")
        check("on the CPU the menu offers the search", offered_item.startswith("Найти варианты"), offered_item)
        choose(js, "$('more-button')", "find-suggest")
    wait(lambda: item.result.suggestions_searched and control.suggesting is None, 240, "suggestion search")
    status = menu_texts(js, "$('more-button')").get("find-suggest", "")
    offered = [word for segment in item.segments for word in segment.words if word.suggestions]
    check("search ran after the file", item.result.suggestions_searched,
          f"{status!r}; offers: " + "; ".join(f"{w.text} -> {[(o['models'], o['words']) for o in w.suggestions]}"
                                              for w in offered))
    check("the menu item reports it", status.startswith("Искать варианты заново")
          and ("Другие модели" in status if offered else True) and js("$('task-line').hidden"), status)
    if not offered:
        with control.lock:
            first = item.segments[0].words[1]
            fix.add_suggestion(item.segments, (0, 1), 1, [Word(first.start, first.end, "проверка", 0.9)], "CTC")
            control._emit("line", {"id": item.id, **control._segment_view(0, item.segments[0])})
    wait(lambda: js("$('text').querySelectorAll('.w.sg').length") > 0, 10, "blue underline")
    check("offered words are marked", js("$('text').querySelectorAll('.w.sg').length") > 0)
    colour = js("(() => { const w = $('text').querySelector('.w.sg'); const probe = document.createElement('span');"
                " probe.style.color = 'var(--accent)'; document.body.appendChild(probe);"
                " const out = [getComputedStyle(w).textDecorationColor, getComputedStyle(probe).color];"
                " probe.remove(); return out; })()")
    check("the mark is blue (the accent colour)", colour[0] == colour[1], colour)
    title = js("(() => { const w = $('text').querySelector('.w.sg');"
               " w.dispatchEvent(new MouseEvent('mouseover', {bubbles: true})); return w.title; })()")
    check("hover names the offer", "Другие модели слышат" in title, title)
    js("window.getSelection().removeAllRanges(); $('text').querySelector('.w.sg')"
       ".dispatchEvent(new MouseEvent('click', {bubbles: true}))")
    wait(lambda: not js("$('sg-card').hidden"), 5, "offer card")
    rows = js("[...$('sg-list').querySelectorAll('.sg-item')].map(li => li.textContent)")
    check("card lists the offers", len(rows) >= 1 and all("Взять" in row for row in rows), rows)
    shoot("04g-suggestion-card")
    # The search may add an offer while the card is open: the line is drawn again, and the card
    # must stay open on its word (owner 2026-11-09: it closed at every new offer).
    line = js("spanPosition(card.span)[0]")
    control._emit("line", {"id": item.id, **control._segment_view(line, item.segments[line])})
    time.sleep(0.5)
    check("the card stays open when its line is drawn again", not js("$('sg-card').hidden") and js("!!card"))
    js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape'}))")
    check("Esc closes the card", js("$('sg-card').hidden"))
    js("$('text').querySelector('.w.sg').dispatchEvent(new MouseEvent('click', {bubbles: true}))")
    wait(lambda: not js("$('sg-card').hidden"), 5, "offer card again")
    offer_text = js("$('sg-list').querySelector('.sg-text strong').textContent")
    js("$('sg-list').querySelector('button.primary').click()")
    wait(lambda: offer_text in " ".join(segment.text for segment in item.segments), 10, "offer taken")
    wait(lambda: offer_text in js("$('text').textContent"), 10, "offer on the page")
    check("Vzyat puts the offer into the text", offer_text in js("$('text').textContent")
          and js("$('sg-card').hidden"), offer_text)
    check("the taken words are not doubtful", all(word.confidence is None for segment in item.segments
                                                  for word in segment.words if word.text in offer_text.split()))
    # Search again. The flag is cleared first, so the wait below cannot pass before the
    # click has reached Python (it did, and the player steps then ran during the search).
    item.result.suggestions_searched = False
    choose(js, "$('more-button')", "find-suggest")
    wait(lambda: control.suggesting is not None or item.result.suggestions_searched, 10, "search starts")
    # The player works while the search reports its progress (each report replaced the
    # file's object in the page, and play silently did nothing).
    js("filePlayer.muted = true; $('audio-play').click()")
    wait(lambda: js("!filePlayer.paused && filePlayer.currentTime > 0.3"), 15, "playing during the search")
    check("play works during a search", js("!filePlayer.paused"))
    js("filePlayer.pause(); filePlayer.currentTime = 0")
    wait(lambda: control.suggesting is None and item.result.suggestions_searched, 240, "search again")
    wait(lambda: js("$('task-line').hidden"), 10, "status line gone after the search")
    check("the menu searches again", item.result.suggestions_searched and js("$('task-line').hidden"))
    # Owner 2026-11-09: the search can be cancelled from the status line; the line on the
    # worker ends, the file does not count as searched ("Найти варианты" stays offered).
    item.result.suggestions_searched = False
    choose(js, "$('more-button')", "find-suggest")
    wait(lambda: not js("$('task-suggest-cancel').hidden") or item.result.suggestions_searched, 15, "cancel button")
    shoot("04g2-search-cancel")
    js("$('task-suggest-cancel').click()")
    wait(lambda: control.suggesting is None, 60, "search stopped")
    wait(lambda: js("$('task-line').hidden"), 10, "status line gone after the cancel")
    offered_item = menu_texts(js, "$('more-button')").get("find-suggest", "")
    check("Otmenit stops the search, which is not counted as done", not item.result.suggestions_searched
          and js("$('task-line').hidden") and offered_item.startswith("Найти варианты"), offered_item)
    # "Исправить...": the fix dialog for the offer's words, filled with the offer; the user's
    # own text goes in. If the search found nothing left, one test offer is added.
    if not js("$('text').querySelectorAll('.w.sg').length"):
        with control.lock:
            last = item.segments[0].words[-1]
            fix.add_suggestion(item.segments, (0, len(item.segments[0].words) - 1), 1,
                               [Word(last.start, last.end, "проверка", 0.9)], "Whisper")
            control._emit("line", {"id": item.id, **control._segment_view(0, item.segments[0])})
        wait(lambda: js("$('text').querySelectorAll('.w.sg').length") > 0, 10, "a mark for the edit step")
    js("window.getSelection().removeAllRanges(); $('text').querySelector('.w.sg')"
       ".dispatchEvent(new MouseEvent('click', {bubbles: true}))")
    wait(lambda: not js("$('sg-card').hidden"), 5, "offer card for editing")
    offer_text = js("$('sg-list').querySelector('.sg-text strong').textContent")
    js("$('sg-edit').click()")
    wait(lambda: js("$('fix').open"), 5, "fix dialog from the card")
    check("Ispravit opens the fix dialog with the offer", js("$('fix').open") and js("$('sg-card').hidden")
          and js("$('fix-text').value") == offer_text, js("$('fix-text').value"))
    shoot("04h-edit-from-card")
    own = "своя правка"
    js(f"$('fix-text').value = '{own}'; $('fix-save').click()")
    wait(lambda: own in js("$('text').textContent"), 10, "own text on the page")
    check("the own text goes in, not doubtful", own in js("$('text').textContent")
          and all(word.confidence is None for segment in item.segments for word in segment.words
                  if word.text in own.split()))


def speaker_steps(js, control, item, shoot):
    """Plan 07 on the finished short file. The "Govoryashchie" switch on a file without
    speakers asks for the count; with 2 it downloads the speaker models from the models-1
    release (the temporary download folder starts empty) and finds the speakers. The text
    shows coloured labels and the line of speaker chips. A name's menu renames and gives its
    turn to a new speaker, a chip's menu merges, selected words go to a new speaker, and the
    switch hides and shows the names. Then the Settings checkbox."""
    js("document.querySelectorAll('#files li')[1].click()")
    wait(lambda: js("$('text').querySelectorAll('.w').length") > 4, 10, "words of the short file")
    check("speaker switch is off and usable", not js("$('show-speakers').checked")
          and not js("$('show-speakers').disabled") and js("$('speaker-line').hidden"))
    more = menu_texts(js, "$('more-button')")
    check("the more menu offers a speaker search", more.get("find-speakers") == "Определить говорящих...", more)
    js("$('show-speakers').click()")
    wait(lambda: js("$('speaker-search').open"), 5, "count dialog")
    check("the switch asks for the count first", not js("$('show-speakers').checked"))
    check("count choice: auto and 1..20", js("$('speaker-count').options.length") == 21
          and js("$('speaker-count').value") == "0")
    shoot("04i-speaker-count")
    js("$('speaker-count').value = '2'; $('speaker-search-go').click()")
    wait(lambda: control.speaker_download is not None or control.diarizing is not None, 10, "speaker search starts")
    seen = set()

    def finished():
        if not js("$('task-line').hidden"):
            seen.add(js("$('task-text').textContent").split(":")[0])
        return control.diarizing is None and control.speaker_download is None and not control.speaker_queue
    started = time.perf_counter()
    wait(finished, 300, "speakers found")
    seconds = time.perf_counter() - started
    names = item.result.speakers or []
    check("speakers found", names and item.result.speakers_found, f"{names}, found {item.result.speakers_found}, "
          f"{seconds:.1f} s, seen {seen}")
    check("the status line showed the search", any(text.startswith(("Определяю", "Скачиваю")) for text in seen), seen)
    check("models were downloaded", catalog.installed_folder(catalog.SPEAKER_MODEL) is not None)
    wait(lambda: js("$('text').querySelectorAll('.spk').length") > 0, 10, "speaker labels")
    wait(lambda: js("$('task-line').hidden"), 10, "status line gone")
    labels = js("[...$('text').querySelectorAll('.spk')].map(b => b.textContent)")
    check("labels start the turns", labels and labels[0] == "Говорящий 1"
          and js("$('text').firstElementChild.matches('.turn-head') && !!$('text').firstElementChild.querySelector('.spk')"),
          labels[:6])
    colour = js("(() => { const b = $('text').querySelector('.spk'); const probe = document.createElement('span');"
                " probe.style.color = 'var(--spk-0)'; document.body.appendChild(probe);"
                " const out = [getComputedStyle(b).color, getComputedStyle(probe).color];"
                " probe.remove(); return out; })()")
    check("the first speaker has its colour", colour[0] == colour[1], colour)
    words_shown = js("$('text').querySelectorAll('.w').length")
    check("every word still shown once", words_shown == sum(len(s.words) for s in item.segments), words_shown)
    chips = js("[...$('speaker-chips').querySelectorAll('.spk-chip')].map(c => c.textContent)")
    check("the speaker line shows each speaker with a share", not js("$('speaker-line').hidden") and chips
          and chips[0].startswith("Говорящий 1") and chips[0].endswith("%"), chips)
    check("the switch is on now", js("$('show-speakers').checked"))
    more = menu_texts(js, "$('more-button')")
    check("the more menu searches again", more.get("find-speakers") == "Определить говорящих заново...", more)
    shoot("04j-speakers")
    choose(js, "$('text').querySelector('.spk')", "rename")
    wait(lambda: js("$('speaker').open"), 5, "rename dialog")
    check("rename dialog has the name", js("$('speaker-name').value") == "Говорящий 1", js("$('speaker-name').value"))
    js("$('speaker-name').value = 'Anna'; $('speaker-save').click()")
    wait(lambda: item.result.speakers[0] == "Anna", 10, "renamed in Python")
    wait(lambda: js("$('text').querySelector('.spk').textContent") == "Anna", 10, "renamed on the page")
    first_labels = js("[...$('text').querySelectorAll('.spk[data-speaker=\"0\"]')].map(b => b.textContent)")
    check("rename reaches every label of that speaker", first_labels and set(first_labels) == {"Anna"},
          first_labels[:4])
    wait(lambda: js("$('speaker-chips').textContent").startswith("Anna"), 10, "renamed chip")
    check("rename closes the dialog and reaches the chip", not js("$('speaker').open")
          and js("$('speaker-chips').textContent").startswith("Anna"))
    # G6 join rule, run by the page on lines made up for it (the clip has one line): Sonya, then
    # Anna inside the same line, her sentence cut into the next line by a breath, then a new one.
    made = ("[{index: 0, start: 29.9, text: '', words: [[30, 30.5, 'Меня', null, null, 0],"
            " [30.6, 31, 'Соня.', null, null, 0], [47, 47.5, 'Мы', null, null, 1], [48, 48.6, 'могут', null, null, 1]]},"
            " {index: 1, start: 54.9, text: '', words: [[55, 55.5, 'Решить', null, null, 1],"
            " [55.6, 56, 'проблемы.', null, null, 1]]},"
            " {index: 2, start: 57.9, text: '', words: [[58, 58.5, 'Подкаст', null, null, 1],"
            " [58.6, 59, 'выходит.', null, null, 1]]}]")
    shape = js("(() => { const f = document.createDocumentFragment(); appendParagraphs(f, " + made + ", ['Соня', 'Анна']);"
               " return [...f.children].map(n => n.matches('.turn-head') ? 'name ' + n.textContent"
               " : n.querySelector('time').textContent + ' ' + n.querySelector('p').textContent); })()")
    check("a line cut mid-sentence joins the paragraph before it; a turn inside a line has its word's time",
          shape == ["name Соня", "00:29 Меня Соня.", "name Анна", "00:47 Мы могут Решить проблемы.",
                    "00:57 Подкаст выходит."], shape)
    plain = js("(() => { const f = document.createDocumentFragment(); appendParagraphs(f, " + made + ", null);"
               " return [...f.children].map(n => n.querySelector('time').textContent + ' ' + n.querySelector('p').textContent); })()")
    check("without speakers a line cut mid-sentence joins too", plain == [
        "00:29 Меня Соня. Мы могут Решить проблемы.", "00:57 Подкаст выходит."], plain)
    # The clip has one voice: give the second half of its first line to a second speaker, as a
    # search would, to see a line drawn in two parts (one time, two labels, every word once).
    with control.lock:
        words = item.segments[0].words
        for word in words[len(words) // 2:]:
            word.speaker = 1
        item.result.speakers = ["Anna", "Говорящий 2"]
    control._write_again(item)
    wait(lambda: js("$('text').querySelectorAll('.spk').length") >= 2, 10, "second speaker drawn")
    labels = js("[...$('text').querySelectorAll('.spk')].map(b => b.textContent)")
    # G6 layout D: the name on its own line above the turn, the time in the left column; a turn
    # that starts inside a line has its first word's time.
    second_time = clock_text(item.segments[0].words[len(item.segments[0].words) // 2].start)
    times = js("[...$('text').querySelectorAll('.para time')].map(t => t.textContent)")
    heads = js("[...$('text').children].filter(n => n.matches('.turn-head')).length")
    check("a change of speaker inside a line starts a turn with its name above", labels[:2] == ["Anna", "Говорящий 2"]
          and heads >= 2 and js("$('text').querySelectorAll('.seg[data-seg=\"0\"]').length") == 2
          and len(times) >= 2 and times[1] == second_time, f"{labels}, times {times[:3]}, expected {second_time}")
    check("every word still shown once with two speakers",
          js("$('text').querySelectorAll('.w').length") == sum(len(s.words) for s in item.segments))
    check("the page has the saved files' paragraphs", js("$('text').querySelectorAll('.para').length")
          == len(outputs.paragraphs(item.result)), js("$('text').querySelectorAll('.para').length"))
    js("$('times').checked || $('times').click()")
    columns = js("(() => { const rows = $('text').querySelectorAll('.para'); const head = $('text').querySelector('.turn-head .spk');"
                 " return [...rows].map(r => Math.round(r.querySelector('p').getBoundingClientRect().left))"
                 ".concat([Math.round(head.getBoundingClientRect().left + 3)]); })()")
    check("text and names line up in one column next to the times", max(columns) - min(columns) <= 1, columns)
    shoot("04k-two-speakers-times")
    js("$('times').click()")
    shoot("04k-two-speakers")
    # G4: the name's menu gives the turn of speaker 2 to a new speaker.
    second_label = "$('text').querySelectorAll('.spk')[1]"
    ids = [key for key, _ in open_menu(js, second_label)]
    check("name menu: rename, give the turn to Anna or a new speaker, merge", ids == ["rename", "give-0", "give-new",
                                                                                     "merge-0"], ids)
    shoot("04l-speaker-menu")
    js("$('menu').querySelector('[data-item=give-new]').click()")
    half = len(item.segments[0].words) // 2
    wait(lambda: item.segments[0].words[-1].speaker == 2, 10, "turn given to a new speaker")
    check("the turn goes to a new speaker", [w.speaker for w in item.segments[0].words[half:]] == [2] * (
        len(item.segments[0].words) - half) and item.result.speakers[2] == "Говорящий 3", item.result.speakers)
    wait(lambda: js("[...$('text').querySelectorAll('.spk')].map(b => b.textContent).join('|')").startswith(
        "Anna|Говорящий 3"), 10, "new speaker on the page")
    wait(lambda: js("$('speaker-chips').querySelectorAll('.spk-chip').length") == 2, 10, "chips follow")
    # A chip's menu merges the new speaker into Anna.
    choose(js, "$('speaker-chips').querySelectorAll('.spk-chip')[1]", "merge-0")
    wait(lambda: all(w.speaker == 0 for s in item.segments for w in s.words), 10, "merged")
    wait(lambda: js("$('text').querySelectorAll('.spk').length") == 1, 10, "one label after the merge")
    check("merge leaves one speaker", js("$('speaker-chips').querySelectorAll('.spk-chip').length") == 1
          and "Говорящий 3" not in item.written["txt"].read_text(encoding="utf-8")
          if "txt" in item.written else True)
    # Selected words (the last two of the first line) go to a new speaker from the selection bar.
    js("(() => { const spans = $('text').querySelectorAll('.seg[data-seg=\"0\"] .w'); const r = document.createRange();"
       " r.setStart(spans[spans.length - 2].firstChild, 0);"
       " r.setEnd(spans[spans.length - 1].firstChild, 1);"
       " const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);"
       " document.dispatchEvent(new PointerEvent('pointerup')); })()")
    wait(lambda: not js("$('sel-bar').hidden"), 5, "selection bar for speakers")
    check("the selection bar offers the speaker", not js("$('sel-speaker').hidden"))
    ids = [key for key, _ in open_menu(js, "$('sel-speaker')")]
    check("selected words: only a new speaker (all are Anna's)", ids == ["give-new"], ids)
    shoot("04m-words-speaker")
    js("$('menu').querySelector('[data-item=give-new]').click()")
    wait(lambda: [w.speaker for w in item.segments[0].words[-2:]] == [1, 1], 10, "words given")
    check("selected words go to a new speaker", item.segments[0].words[-3].speaker == 0
          and item.result.speakers[1] == "Говорящий 2", [w.speaker for w in item.segments[0].words])
    wait(lambda: js("$('text').querySelectorAll('.spk').length") >= 2, 10, "words split on the page")
    # The switch hides the names and chips; the copy then has no names; on again brings them back.
    js("$('show-speakers').click()")
    wait(lambda: js("$('text').querySelectorAll('.spk').length") == 0, 5, "names hidden")
    wait(lambda: control.settings.show_speakers is False, 5, "switch saved")
    check("the switch hides names and chips", js("$('speaker-line').hidden")
          and js("$('text').querySelectorAll('.w').length") == sum(len(s.words) for s in item.segments)
          and "Говорящий" not in control.copy_text(item.id, False, False, False))
    check("saved files keep the names", "txt" not in item.written
          or "Говорящий 2:" in item.written["txt"].read_text(encoding="utf-8"))
    shoot("04n-speakers-hidden")
    js("$('show-speakers').click()")
    wait(lambda: js("$('text').querySelectorAll('.spk').length") >= 2, 5, "names shown again")
    check("the switch shows them again", not js("$('speaker-line').hidden") and control.settings.show_speakers)
    # The Settings checkbox is saved at once; switched off again so later steps run as before.
    js("$('open-settings').click()")
    check("speakers checkbox off by default", not js("$('speakers').checked"))
    js("$('speakers').click()")
    wait(lambda: '"speakers": true' in settings_text(), 10, "speakers setting saved")
    check("speakers checkbox saved", control.settings.speakers is True)
    js("$('speakers').click()")
    wait(lambda: '"speakers": false' in settings_text(), 10, "speakers setting off")
    js("$('close-settings').click()")


def player_steps(js, control, item, shoot):
    """Plan 05 on the finished short file (muted): play, pause, seek, the spoken word is
    highlighted, a timecode plays from its line."""
    js("document.querySelectorAll('#files li')[1].click()")
    wait(lambda: js("$('text').querySelectorAll('.w').length") > 4, 10, "words of the short file")
    check("player bar under a finished file", not js("$('audio-bar').hidden"))
    js("filePlayer.muted = true; $('audio-play').click()")
    wait(lambda: js("!filePlayer.paused && filePlayer.currentTime > 1.2"), 15, "playing")
    check("play button plays the file", js("!filePlayer.paused") and js("filePlayer.src.startsWith('http://127.0.0.1:')"))
    check("time runs in the bar", js("$('audio-time').textContent").startswith("00:01"),
          js("$('audio-time').textContent"))
    check("the spoken word is highlighted", js("$('text').querySelectorAll('.w.now').length") == 1)
    shoot("04f-player")
    js("$('audio-play').click()")
    wait(lambda: js("filePlayer.paused"), 5, "pause")
    check("pause", js("filePlayer.paused"))
    space = ("$('audio-seek').focus(); $('audio-seek').dispatchEvent("
             "new KeyboardEvent('keydown', {code: 'Space', bubbles: true}))")
    js(space)
    wait(lambda: js("!filePlayer.paused"), 5, "Space on the seek bar")
    check("Space on the seek bar plays", js("!filePlayer.paused"))
    js(space)
    wait(lambda: js("filePlayer.paused"), 5, "Space pauses")
    js("$('audio-volume').value = 40; $('audio-volume').dispatchEvent(new Event('input'));"
       " $('audio-volume').dispatchEvent(new Event('change'))")
    check("volume slider", abs(js("filePlayer.volume") - 0.4) < 0.01, js("filePlayer.volume"))
    wait(lambda: '"player_volume": 0.4' in settings_text(), 5, "volume saved")
    js("$('audio-mute').click()")
    check("mute button", js("filePlayer.muted"))
    js("$('audio-mute').click(); filePlayer.muted = true")  # back on, and silent for the rest of the test
    js("$('audio-seek').value = 500; $('audio-seek').dispatchEvent(new Event('change'))")
    wait(lambda: abs(js("filePlayer.currentTime - filePlayer.duration / 2")) < 0.3, 5, "seek")
    check("seek bar moves the position", abs(js("filePlayer.currentTime - filePlayer.duration / 2")) < 0.3,
          js("[filePlayer.currentTime, filePlayer.duration]"))
    js("$('text').querySelector('.para time').click()")
    wait(lambda: js("!filePlayer.paused"), 10, "timecode plays")
    first = item.segments[0].words[0].start
    check("a timecode plays from its line", js("!filePlayer.paused") and js("filePlayer.currentTime") < first + 1.5,
          js("filePlayer.currentTime"))
    js("filePlayer.pause()")


def scenario(window, control, long_audio, short_audio, shoot, whisper=False, fast=False):
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
        model_line = js("$('file-model').hidden ? '' : $('file-model').textContent")
        check("running file names its model", model_line.endswith("GigaAM v3 RNNT"), model_line)
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
        files_menu = open_menu(js, "$('files-button')")
        ids = [key for key, _ in files_menu]
        check("the Files menu lists the formats", ids[:2] == ["out-txt", "out-timestamps"] and ids[-1] == "show-folder"
              and files_menu[0][1].startswith("\u2713Текст"), files_menu)
        shoot("04-files-menu")
        # Scripts sent to the page stay ASCII: pywebview on GTK cuts non-ASCII scripts short.
        js("$('menu').querySelector('[data-item=out-srt]').click()")
        srt = Path(short_audio).with_name(Path(short_audio).stem + "-transcript.srt")
        wait(lambda: srt.is_file(), 10, "SRT written")
        check("SRT created from the page", srt.is_file() and srt.stat().st_size > 0)
        choose(js, "$('files-button')", "out-md")
        markdown = Path(short_audio).with_name(Path(short_audio).stem + "-transcript.md")
        wait(lambda: markdown.is_file(), 10, "Markdown written")
        check("Markdown created from the page",
              markdown.is_file() and markdown.read_text(encoding="utf-8").startswith("# " + Path(short_audio).name))
        choose(js, "$('files-button')", "out-llm")
        for_llm = Path(short_audio).with_name(Path(short_audio).stem + "-transcript-llm.txt")
        wait(lambda: for_llm.is_file(), 10, "text for an LLM written")
        check("text for an LLM created from the page",
              for_llm.is_file() and "[?" in for_llm.read_text(encoding="utf-8"))
        copy_menu = menu_texts(js, "$('copy-more')")
        check("copy for an LLM in the copy menu", list(copy_menu) == ["copy-llm"], copy_menu)
        shoot("04-done")
        follow_steps(js, control.files[1], shoot)
        doubt_steps(js, control, control.files[1], shoot)
        suggest_steps(js, control, control.files[1], shoot)
        speaker_steps(js, control, control.files[1], shoot)
        player_steps(js, control, control.files[1], shoot)
        fix_steps(js, control, control.files[1], short_audio, shoot)

        # Retry the short file, remove the cancelled one.
        choose(js, "$('more-button')", "retry")
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
        speech_steps(js, shoot)
        whisper_cpu_steps(js, control, shoot, fast)
        js("document.querySelector('#devices input[value=CPU]').click()")
        # Wait for the page, not only the controller: its message can arrive a moment later.
        wait(lambda: "процессор" in js("$('engine-text').textContent"), 60, "CPU model")
        check("device CPU", "процессор" in js("$('engine-text').textContent"), js("$('engine-text').textContent"))
        # Settings are saved at once; "Sbrosit" goes back to the defaults (device Auto).
        check("settings saved at once", '"device": "CPU"' in settings_text())
        js("$('reset-settings').click()")
        wait(lambda: js("$('reset-note').textContent") != "", 10, "reset note")
        check("reset to defaults", js("document.querySelector('#devices input[value=Auto]').checked")
              and '"device": "Auto"' in settings_text())
        check("reset puts the speech settings back",
              wait(lambda: '"vad_threshold": 0.5' in settings_text() and '"max_duration": 25.0' in settings_text()
                   and js("$('max-line').value") == "25", 10, "speech settings reset"))
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
        add_steps(js, control, long_audio, short_audio, shoot)

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
        files = [entry for entry in files if not entry[0].startswith(("whisper-", "added-"))]
        check("files come back in the next session",
              files[:2] == [[Path(short_audio).name, "done"], [Path(long_audio).name, "cancelled"]], files)
        check("the newest is selected with its text",
              js("state.selected") == js("state.files[state.files.length - 1].id")
              and js("$('text').querySelectorAll('p:not(.placeholder)').length") > 0)
        js("document.querySelectorAll('#files li')[0].click()")
        wait(lambda: js("$('text').querySelectorAll('p:not(.placeholder)').length") > 0, 10, "restored text")
        ids = list(menu_texts(js, "$('files-button')"))
        check("restored file offers its saved files", ids[:4] == ["out-txt", "out-timestamps", "out-md", "out-srt"], ids)
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
    parser.add_argument("--fast-whisper", type=Path,
                        help="a downloaded faster-whisper model folder (faster_whisper_large_v3_turbo_int8) to search with")
    args = parser.parse_args()
    # The log is usually redirected to a file, whose default encoding (cp1251 here) has no
    # arrow and other page symbols: write UTF-8 so a check line never stops the scenario.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
            # Linked, not copied (574 MB): hard links, or symbolic ones across drives (WSL).
            link_model_folder(args.whisper.resolve(), downloads)
        if args.fast_whisper:
            link_model_folder(args.fast_whisper.resolve(), downloads, catalog.FAST_WHISPER_MODEL.folder)
        shoot_again = screenshot_function(args.out)
        run = functools.partial(scenario, long_audio=args.long_audio.resolve(),
                                short_audio=args.short_audio.resolve(), shoot=shoot_again,
                                whisper=args.whisper is not None, fast=args.fast_whisper is not None)
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
