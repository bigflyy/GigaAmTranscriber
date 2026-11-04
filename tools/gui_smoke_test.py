"""Run GigaAmTranscriber.exe on a separate, invisible Windows desktop and check it.

Nothing appears on the screen and the mouse and keyboard are not used: the app
runs on its own desktop, the test reads its windows with EnumDesktopWindows,
captures the main window with PrintWindow and closes it by posting WM_CLOSE.

    python tools/gui_smoke_test.py APP_FOLDER                  start, wait for the model, close
    python tools/gui_smoke_test.py APP_FOLDER --audio FILE     also transcribe FILE (passed as the
                                                               argument, which starts transcription)
    --png PATH saves a picture of the window at the end.

Only the standard library is needed (numpy, if present, speeds up the PNG).
"""

import argparse
import ctypes
from ctypes import wintypes
from pathlib import Path
import struct
import sys
import time
import zlib

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

GENERIC_ALL = 0x10000000
WM_CLOSE, WM_GETTEXT, WM_GETTEXTLENGTH = 0x0010, 0x000D, 0x000E
STILL_ACTIVE = 259


class STARTUPINFO(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


user32.CreateDesktopW.restype = wintypes.HANDLE
user32.CreateDesktopW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD,
                                  wintypes.DWORD, ctypes.c_void_p]
user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumDesktopWindows.argtypes = [wintypes.HANDLE, EnumProc, wintypes.LPARAM]
user32.EnumChildWindows.argtypes = [wintypes.HWND, EnumProc, wintypes.LPARAM]


def window_text(hwnd):
    length = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.SendMessageW(hwnd, WM_GETTEXT, length + 1, ctypes.cast(buffer, ctypes.c_void_p).value)
    return buffer.value


def top_windows(desktop, pid):
    """[(hwnd, title, visible)] of one process on one desktop."""
    found = []

    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            found.append((hwnd, window_text(hwnd), bool(user32.IsWindowVisible(hwnd))))
        return True

    user32.EnumDesktopWindows(desktop, EnumProc(callback), 0)
    return found


def child_texts(parent):
    texts = []

    def callback(hwnd, _):
        text = window_text(hwnd)
        if text:
            texts.append(text)
        return True

    user32.EnumChildWindows(parent, EnumProc(callback), 0)
    return texts


def crash_report(desktop, pid):
    """Text of a PyInstaller 'Unhandled exception' dialog or a Tk error box, if one is open."""
    for hwnd, title, _ in top_windows(desktop, pid):
        if "exception" in title.lower() or title == "Ошибка":
            return f"{title}: " + "\n".join(child_texts(hwnd))
    return None


def save_png(hwnd, path):
    """PrintWindow into a bitmap and write it as PNG; works on a desktop nobody looks at."""
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    width, height = rect.right - rect.left, rect.bottom - rect.top
    window_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    gdi32.SelectObject(memory_dc, bitmap)
    user32.PrintWindow(hwnd, memory_dc, 2)  # PW_RENDERFULLCONTENT
    header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    buffer = ctypes.create_string_buffer(width * height * 4)
    gdi32.GetDIBits(memory_dc, bitmap, 0, height, buffer, header, 0)
    gdi32.DeleteObject(bitmap)
    gdi32.DeleteDC(memory_dc)
    user32.ReleaseDC(hwnd, window_dc)
    raw, stride = buffer.raw, width * 4
    try:
        import numpy as np
        pixels = np.frombuffer(raw, np.uint8).reshape(height, width, 4)[:, :, 2::-1]  # BGRA -> RGB
        rows = b"".join(b"\x00" + row.tobytes() for row in pixels)
    except ImportError:
        rows = b"".join(b"\x00" + bytes(value for x in range(0, stride, 4)
                                        for value in raw[y * stride + x:y * stride + x + 3][::-1])
                        for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b""))


def run(app, audio=None, png=None, ready_seconds=12.0, timeout=300.0, log=print):
    """Start the GUI on a hidden desktop; returns a dict of timings. Raises on any failure."""
    app = Path(app)
    outputs = []
    if audio is not None:
        audio = Path(audio).resolve()
        outputs = [audio.with_name(audio.stem + "-transcript.txt"),
                   audio.with_name(audio.stem + "-transcript-timestamps.txt")]
        for path in outputs:
            path.unlink(missing_ok=True)
    name = f"gigaam-smoke-{int(time.time() * 1000)}"
    desktop = user32.CreateDesktopW(name, None, None, 0, GENERIC_ALL, None)
    if not desktop:
        raise OSError(ctypes.get_last_error(), "CreateDesktopW failed")
    info = STARTUPINFO(cb=ctypes.sizeof(STARTUPINFO), lpDesktop=f"winsta0\\{name}")
    process = PROCESS_INFORMATION()
    command = f'"{app / "GigaAmTranscriber.exe"}"' + (f' "{audio}"' if audio else "")
    started = time.perf_counter()
    if not kernel32.CreateProcessW(None, ctypes.create_unicode_buffer(command), None, None, False, 0, None,
                                   str(app), ctypes.byref(info), ctypes.byref(process)):
        user32.CloseDesktop(desktop)
        raise OSError(ctypes.get_last_error(), "CreateProcessW failed")
    pid = process.dwProcessId
    timings = {}

    def alive():
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(process.hProcess, ctypes.byref(code))
        return code.value == STILL_ACTIVE

    def check_crash():
        report = crash_report(desktop, pid)
        if report:
            raise RuntimeError(report)
        if not alive():
            raise RuntimeError("the app exited on its own")

    try:
        main_window = None
        while main_window is None:
            if time.perf_counter() - started > 60:
                raise RuntimeError("no main window within 60 s")
            check_crash()
            main_window = next((hwnd for hwnd, title, visible in top_windows(desktop, pid)
                                if visible and title.startswith("GigaAM")), None)
            time.sleep(0.05)
        timings["window_seconds"] = time.perf_counter() - started
        log(f"window after {timings['window_seconds']:.2f} s")
        if outputs:
            while not all(path.is_file() for path in outputs):
                if time.perf_counter() - started > timeout:
                    raise RuntimeError(f"no transcript within {timeout:.0f} s")
                check_crash()
                time.sleep(0.1)
            timings["transcript_seconds"] = time.perf_counter() - started
            log(f"transcript written after {timings['transcript_seconds']:.2f} s")
            time.sleep(1.0)  # the status line updates after the files are written
        else:
            # The model loads in the background; give it time, then make sure nothing failed.
            deadline = started + ready_seconds
            while time.perf_counter() < deadline:
                check_crash()
                time.sleep(0.2)
        check_crash()
        if png:
            save_png(main_window, png)
        user32.PostMessageW(main_window, WM_CLOSE, 0, 0)
        if kernel32.WaitForSingleObject(process.hProcess, 15000) != 0:
            raise RuntimeError("the app did not close after WM_CLOSE")
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(process.hProcess, ctypes.byref(code))
        if code.value != 0:
            raise RuntimeError(f"exit code {code.value}")
        timings["outputs"] = {path.name: path.stat().st_size for path in outputs}
        return timings
    finally:
        if alive():
            kernel32.TerminateProcess(process.hProcess, 1)
            kernel32.WaitForSingleObject(process.hProcess, 5000)
        kernel32.CloseHandle(process.hProcess)
        kernel32.CloseHandle(process.hThread)
        user32.CloseDesktop(desktop)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("app", type=Path, help="folder with GigaAmTranscriber.exe")
    parser.add_argument("--audio", type=Path, help="file to transcribe; outputs are written beside it")
    parser.add_argument("--png", type=Path, help="save a picture of the window here")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows only")
    timings = run(args.app, args.audio, args.png)
    for name, size in timings.get("outputs", {}).items():
        print(f"{name}: {size} bytes")
    print("GUI smoke test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
