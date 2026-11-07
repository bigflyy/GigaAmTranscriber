"""Download an extra model into the per-user model folder, checking every byte.

Files are written to "<downloads>/<folder>.partial/" first. Each one must have
the size and SHA-256 written in catalog.py. Only when every file passes is the
folder renamed to its final name, so the app never sees a half-installed model.

An interrupted download (network error, cancel, closed window) keeps what it
has; the next attempt asks the server only for the missing bytes (HTTP Range)
after re-hashing the part already on disk.

A file is fetched from the release first; when that fails (missing asset, network
trouble, wrong bytes), its mirrors are tried in order. The bytes already on disk
are kept between them: every address serves the same file, and the SHA-256 at the
end decides. A model with a model_type gets its model.json written from the catalog.
"""

import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import socket
import urllib.error
import urllib.request

from . import __version__, catalog
from .paths import downloads_dir

BLOCK = 1024 * 1024
ATTEMPTS = 3                     # per file, for network errors; each retry resumes
TIMEOUT_SECONDS = 30             # per network read
SPACE_MARGIN = 64 * 1024 ** 2    # keep this much free beyond the download itself


class DownloadError(RuntimeError):
    pass


class DownloadCancelled(DownloadError):
    pass


class _NetworkError(DownloadError):
    """A failure that a retry may fix; the bytes received so far are kept."""


def install(info, root=None, on_progress=None, should_cancel=None, opener=None):
    """Download every file of a catalog model and return the installed folder.

    on_progress(done_bytes, total_bytes) is called from this thread.
    should_cancel() is checked between blocks; a cancel raises DownloadCancelled.
    opener(request, timeout) defaults to urllib.request.urlopen (tests replace it).
    """
    if info.bundled:
        raise ValueError(f"{info.key} is bundled with the app, nothing to download")
    root = Path(root) if root else downloads_dir()
    final = root / info.folder
    staging = root / (info.folder + ".partial")
    staging.mkdir(parents=True, exist_ok=True)
    opener = opener or urllib.request.urlopen
    total = info.download_size
    on_disk = sum(min((staging / f.name).stat().st_size, f.size) for f in info.files if (staging / f.name).is_file())
    free = shutil.disk_usage(staging).free
    if free < total - on_disk + SPACE_MARGIN:
        raise DownloadError(f"Not enough disk space in {root}: the model needs "
                            f"{(total - on_disk) / 1024 ** 3:.1f} GB more, {free / 1024 ** 3:.1f} GB is free")
    done = 0
    for file in info.files:
        _fetch_from_any(info.urls(file), staging / file.name, file, done, total, on_progress, should_cancel, opener)
        done += file.size
    if info.model_type:
        (staging / "model.json").write_text(json.dumps(catalog.manifest(info), indent=2) + "\n", encoding="utf-8")
    if final.exists():
        shutil.rmtree(final)  # an older copy of the same model in our own folder
    os.replace(staging, final)
    return final


def _fetch_from_any(urls, path, file, done_before, total, on_progress, should_cancel, opener):
    """Try each address in turn, each with ATTEMPTS tries for network errors.
    A cancel stops at once; when every address fails, the error names each of them."""
    errors = []
    for url in urls:
        for attempt in range(1, ATTEMPTS + 1):
            try:
                _fetch(url, path, file, done_before, total, on_progress, should_cancel, opener)
                return
            except DownloadCancelled:
                raise
            except _NetworkError as error:
                if attempt == ATTEMPTS:
                    errors.append(error)
            except DownloadError as error:
                errors.append(error)
                break
    if len(errors) == 1:
        raise errors[0]
    raise DownloadError("; ".join(str(error) for error in errors)) from errors[-1]


def _hash_existing(path, digest):
    with open(path, "rb") as stream:
        while block := stream.read(BLOCK):
            digest.update(block)


def _fetch(url, path, file, done_before, total, on_progress, should_cancel, opener):
    """Make 'path' the verified file, downloading only what is missing."""
    have = path.stat().st_size if path.is_file() else 0
    if have > file.size:
        path.unlink()
        have = 0
    digest = hashlib.sha256()
    if have:
        _hash_existing(path, digest)
    if have == file.size:
        if digest.hexdigest() == file.sha256:
            if on_progress:
                on_progress(done_before + have, total)
            return
        path.unlink()  # complete but wrong: download it again
        have, digest = 0, hashlib.sha256()

    headers = {"User-Agent": f"GigaAmTranscriber/{__version__}"}
    if have:
        headers["Range"] = f"bytes={have}-"
    try:
        with opener(urllib.request.Request(url, headers=headers), timeout=TIMEOUT_SECONDS) as response:
            status = response.getcode()
            if have and (status != 206 or not _range_starts_at(response, have)):
                have, digest = 0, hashlib.sha256()  # the server sent the whole file again
            with open(path, "ab" if have else "wb") as output:
                while True:
                    if should_cancel is not None and should_cancel():
                        raise DownloadCancelled("Download cancelled; it resumes next time")
                    block = response.read(BLOCK)
                    if not block:
                        break
                    if have + len(block) > file.size:
                        raise DownloadError(f"{file.name}: the server sent more data than expected")
                    output.write(block)
                    digest.update(block)
                    have += len(block)
                    if on_progress:
                        on_progress(done_before + have, total)
    except urllib.error.HTTPError as error:
        if error.code == 416:  # Range not satisfiable: start this file again
            path.unlink(missing_ok=True)
            raise _NetworkError(f"{file.name}: the server refused to resume") from error
        raise DownloadError(f"{file.name}: HTTP {error.code} {error.reason} from {url}") from error
    except (urllib.error.URLError, http.client.HTTPException, socket.timeout, ConnectionError,
            TimeoutError) as error:
        reason = getattr(error, "reason", error)
        raise _NetworkError(f"{file.name}: network error ({reason}); the download resumes next time") from error
    if have != file.size:
        raise _NetworkError(f"{file.name}: connection closed at {have} of {file.size} bytes")
    if digest.hexdigest() != file.sha256:
        path.unlink()
        raise DownloadError(f"{file.name}: checksum does not match the catalog; the file was deleted")


def _range_starts_at(response, offset):
    """True when a 206 reply's Content-Range starts at the requested offset."""
    content_range = response.headers.get("Content-Range", "")
    return content_range.startswith(f"bytes {offset}-")
