"""A small local HTTP server that lets the window's page play whole audio files (plan 05).

The page is loaded from a string, so it cannot open files by path, and a data: URL is
far too big for a long recording. This server listens on 127.0.0.1 only, on a free port,
and serves only the files the controller registered, each under a random token, so
other programs on the computer cannot guess the addresses or read other files. It
answers Range requests, which the audio element uses to seek without loading the
whole file.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import mimetypes
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import quote, unquote

CHUNK = 256 * 1024
RANGE = re.compile(r"bytes=(\d*)-(\d*)$")
# Types the audio element needs to hear about; mimetypes knows the rest or guesses wrong.
AUDIO_TYPES = {".opus": "audio/ogg", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".m4a": "audio/mp4",
               ".aac": "audio/aac", ".flac": "audio/flac", ".wav": "audio/wav", ".mp3": "audio/mpeg",
               ".webm": "audio/webm", ".mp4": "video/mp4"}


def content_type(path):
    suffix = Path(path).suffix.lower()
    return AUDIO_TYPES.get(suffix) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"


class AudioServer:
    """Serves registered files at http://127.0.0.1:PORT/TOKEN/KEY/NAME."""

    def __init__(self):
        self.token = secrets.token_urlsafe(18)
        self.files = {}          # key -> Path
        self.lock = threading.Lock()
        self.httpd = None
        self.thread = None

    @property
    def running(self):
        return self.httpd is not None

    def start(self):
        """Listen on a free port in a background thread. Calling it again does nothing."""
        if self.httpd is not None:
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - http.server's name
                server._answer(self, with_body=True)

            def do_HEAD(self):  # noqa: N802
                server._answer(self, with_body=False)

            def log_message(self, *args):  # no console output
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.05},
                                       name="audio-server", daemon=True)
        self.thread.start()

    def stop(self):
        if self.httpd is None:
            return
        self.httpd.shutdown()
        self.httpd.server_close()
        self.httpd = None

    def register(self, path):
        """Serve one file; returns its URL. The same file always gets the same URL."""
        self.start()
        path = Path(path)
        with self.lock:
            for key, known in self.files.items():
                if known == path:
                    break
            else:
                key = secrets.token_urlsafe(9)
                self.files[key] = path
        port = self.httpd.server_address[1]
        return f"http://127.0.0.1:{port}/{self.token}/{key}/{quote(path.name)}"

    def forget(self, path):
        """Stop serving a file (its URL answers 404 from now on)."""
        with self.lock:
            for key in [key for key, known in self.files.items() if known == Path(path)]:
                del self.files[key]

    def _answer(self, request, with_body):
        """Send the file for a request, the whole of it or one byte range."""
        parts = unquote(request.path.split("?", 1)[0]).strip("/").split("/")
        with self.lock:
            path = self.files.get(parts[1]) if len(parts) == 3 else None
        if path is None or not secrets.compare_digest(parts[0], self.token):
            request.send_error(404)
            return
        try:
            stream = open(path, "rb")
        except OSError:
            request.send_error(404)
            return
        with stream:
            size = Path(path).stat().st_size
            first, last = 0, size - 1
            wanted = request.headers.get("Range")
            match = RANGE.match(wanted.strip()) if wanted else None
            if wanted and not match:
                request.send_error(416)
                return
            if match:
                start, end = match.groups()
                if start:
                    first = int(start)
                    last = min(int(end), size - 1) if end else size - 1
                elif end:  # the last N bytes
                    first = max(0, size - int(end))
                if first >= size or first > last:
                    request.send_response(416)
                    request.send_header("Content-Range", f"bytes */{size}")
                    request.end_headers()
                    return
                request.send_response(206)
                request.send_header("Content-Range", f"bytes {first}-{last}/{size}")
            else:
                request.send_response(200)
            request.send_header("Content-Type", content_type(path))
            request.send_header("Content-Length", str(last - first + 1))
            request.send_header("Accept-Ranges", "bytes")
            request.send_header("Cache-Control", "no-store")
            request.end_headers()
            if not with_body:
                return
            stream.seek(first)
            left = last - first + 1
            try:
                while left > 0:
                    data = stream.read(min(CHUNK, left))
                    if not data:
                        break
                    request.wfile.write(data)
                    left -= len(data)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # the player stopped reading (a seek, a pause, the window closed)
