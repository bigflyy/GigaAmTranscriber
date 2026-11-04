"""Model downloads against a local HTTP server: checksums, resume, cancel, bad servers."""

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import threading

import pytest

from gigaam_app import catalog, cli, download
from gigaam_app.catalog import ModelInfo, RemoteFile


class Server:
    """Serves files by asset name. Fault switches change what the next replies do."""

    def __init__(self):
        self.files = {}           # asset name -> bytes
        self.requests = []        # (asset name, Range header or None)
        self.ignore_range = False
        self.cut_after = None     # send only this many bytes of a reply, then close
        self.corrupt = False      # flip one byte in every reply
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                name = self.path.rsplit("/", 1)[-1]
                server.requests.append((name, self.headers.get("Range")))
                data = server.files.get(name)
                if data is None:
                    self.send_error(404)
                    return
                start, status = 0, 200
                wanted = self.headers.get("Range")
                if wanted and not server.ignore_range:
                    start = int(wanted.split("=")[1].split("-")[0])
                    if start >= len(data):
                        self.send_error(416)
                        return
                    status = 206
                body = data[start:]
                if server.corrupt and body:
                    body = bytes([body[0] ^ 0xFF]) + body[1:]
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
                self.end_headers()
                if server.cut_after is not None:
                    body = body[:server.cut_after]
                    self.close_connection = True
                self.wfile.write(body)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/models-test"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture
def server():
    running = Server()
    yield running
    running.close()


def make_model(server, sizes=(3000, 2_500_000), with_meta=False):
    """A fake catalog entry whose files the server holds. with_meta adds the
    model.json that marks a folder as installed."""
    files = []
    names = [f"part{number}.bin" for number in range(len(sizes))]
    if with_meta:
        names[0] = "model.json"
    for name, size in zip(names, sizes):
        data = os.urandom(size)
        server.files[f"fake_model.{name}"] = data
        files.append(RemoteFile(name, size, hashlib.sha256(data).hexdigest()))
    return ModelInfo("Fake", "fake_model", "test model", files=tuple(files), base_url=server.url)


def assert_installed(folder, server):
    assert folder.name == "fake_model" and not (folder.parent / "fake_model.partial").exists()
    for name, data in server.files.items():
        assert (folder / name.split(".", 1)[1]).read_bytes() == data


def test_install_verifies_and_renames(server, tmp_path):
    info = make_model(server)
    seen = []
    folder = download.install(info, tmp_path, on_progress=lambda done, total: seen.append((done, total)))
    assert_installed(folder, server)
    assert seen[-1] == (info.download_size, info.download_size)
    assert all(a[0] <= b[0] for a, b in zip(seen, seen[1:]))  # progress never goes back


def test_damaged_file_is_deleted_and_nothing_installed(server, tmp_path):
    info = make_model(server)
    server.corrupt = True
    with pytest.raises(download.DownloadError, match="checksum"):
        download.install(info, tmp_path)
    assert not (tmp_path / "fake_model").exists()
    assert not (tmp_path / "fake_model.partial" / "part0.bin").exists()


def test_cut_connection_retries_with_range(server, tmp_path):
    info = make_model(server, sizes=(2_500_000,))
    server.cut_after = 600_000
    with pytest.raises(download.DownloadError, match="connection closed|network error"):
        download.install(info, tmp_path)
    # Every retry asked only for the missing bytes.
    assert [header for _, header in server.requests] == [None, "bytes=600000-", "bytes=1200000-"]
    partial = tmp_path / "fake_model.partial" / "part0.bin"
    assert partial.stat().st_size == 1_800_000
    server.cut_after = None
    server.requests.clear()
    assert_installed(download.install(info, tmp_path), server)
    assert server.requests == [("fake_model.part0.bin", "bytes=1800000-")]


def test_cancel_keeps_the_part_for_later(server, tmp_path):
    info = make_model(server, sizes=(3_000_000,))
    calls = []

    def cancel_after_first_block():
        calls.append(1)
        return len(calls) > 1

    with pytest.raises(download.DownloadCancelled):
        download.install(info, tmp_path, should_cancel=cancel_after_first_block)
    assert not (tmp_path / "fake_model").exists()
    assert 0 < (tmp_path / "fake_model.partial" / "part0.bin").stat().st_size < 3_000_000
    assert_installed(download.install(info, tmp_path), server)


def test_server_ignoring_range_restarts_the_file(server, tmp_path):
    info = make_model(server, sizes=(2_000_000,))
    staging = tmp_path / "fake_model.partial"
    staging.mkdir()
    (staging / "part0.bin").write_bytes(server.files["fake_model.part0.bin"][:700_000])
    server.ignore_range = True
    assert_installed(download.install(info, tmp_path), server)


def test_wrong_partial_bytes_are_caught(server, tmp_path):
    """A partial file with wrong bytes fails the checksum after resuming and is deleted."""
    info = make_model(server, sizes=(2_000_000,))
    staging = tmp_path / "fake_model.partial"
    staging.mkdir()
    (staging / "part0.bin").write_bytes(b"\0" * 700_000)
    with pytest.raises(download.DownloadError, match="checksum"):
        download.install(info, tmp_path)
    assert not (staging / "part0.bin").exists()
    assert_installed(download.install(info, tmp_path), server)


def test_complete_files_are_not_fetched_again(server, tmp_path):
    info = make_model(server)
    staging = tmp_path / "fake_model.partial"
    staging.mkdir()
    (staging / "part0.bin").write_bytes(server.files["fake_model.part0.bin"])
    assert_installed(download.install(info, tmp_path), server)
    assert [name for name, _ in server.requests] == ["fake_model.part1.bin"]


def test_too_long_reply_is_rejected(server, tmp_path):
    info = make_model(server, sizes=(5000,))
    server.files["fake_model.part0.bin"] += b"extra"
    with pytest.raises(download.DownloadError, match="more data"):
        download.install(info, tmp_path)


def test_missing_asset_reports_http_status(server, tmp_path):
    info = make_model(server, sizes=(5000,))
    server.files.clear()
    with pytest.raises(download.DownloadError, match="HTTP 404"):
        download.install(info, tmp_path)


def test_not_enough_space(server, tmp_path, monkeypatch):
    info = make_model(server)
    monkeypatch.setattr(download.shutil, "disk_usage", lambda path: type("Usage", (), {"free": 1000})())
    with pytest.raises(download.DownloadError, match="disk space"):
        download.install(info, tmp_path)
    assert server.requests == []


def test_old_copy_is_replaced(server, tmp_path):
    info = make_model(server)
    old = tmp_path / "fake_model"
    old.mkdir()
    (old / "stale.txt").write_text("old")
    folder = download.install(info, tmp_path)
    assert_installed(folder, server)
    assert not (folder / "stale.txt").exists()


def test_bundled_models_cannot_be_downloaded(tmp_path):
    with pytest.raises(ValueError):
        download.install(catalog.find("RNNT"), tmp_path)


# ---------------------------------------------------------------- catalog and CLI

def test_catalog_entries_are_well_formed():
    assert len(catalog.BY_KEY) == len(catalog.CATALOG)
    for info in catalog.CATALOG:
        names = [file.name for file in info.files]
        assert len(names) == len(set(names))
        for file in info.files:
            assert file.size > 0 and len(file.sha256) == 64 and int(file.sha256, 16) >= 0
            assert info.url(file).startswith("https://github.com/")
        if not info.bundled:
            assert "model.json" in names and "encoder.onnx" in names
            # GitHub release assets are limited to 2 GiB each.
            assert max(file.size for file in info.files) < 2 * 1024 ** 3


def test_old_names_and_unknown_names():
    assert catalog.find("Multilingual CTC (220M)").key == "Multilingual"
    with pytest.raises(ValueError):
        catalog.find("Whisper")


def test_installed_folder_looks_in_both_places(tmp_path, monkeypatch):
    monkeypatch.setenv("GIGAAM_MODELS", str(tmp_path / "bundled"))
    monkeypatch.setenv("GIGAAM_DOWNLOADS", str(tmp_path / "downloads"))
    info = catalog.find("Multilingual")
    assert catalog.installed_folder(info) is None
    (tmp_path / "downloads" / "multilingual_ctc").mkdir(parents=True)
    (tmp_path / "downloads" / "multilingual_ctc" / "model.json").write_text("{}")
    assert catalog.installed_folder(info) == tmp_path / "downloads" / "multilingual_ctc"
    # A bundled model is never taken from the downloads folder.
    (tmp_path / "downloads" / "v3_e2e_rnnt").mkdir()
    (tmp_path / "downloads" / "v3_e2e_rnnt" / "model.json").write_text("{}")
    assert catalog.installed_folder(catalog.find("RNNT")) is None


def test_cli_download_and_list(server, tmp_path, monkeypatch, capsys):
    fake = make_model(server, with_meta=True)
    monkeypatch.setenv("GIGAAM_DOWNLOADS", str(tmp_path))
    monkeypatch.setattr(catalog, "CATALOG", catalog.CATALOG + (fake,))
    monkeypatch.setitem(catalog.BY_KEY, "Fake", fake)
    assert cli.main(["--list-models"]) == 0
    assert "download 2 MB" in capsys.readouterr().out
    assert cli.download_model("Fake", quiet=True) == 0
    assert_installed(tmp_path / "fake_model", server)
    assert cli.download_model("Fake", quiet=False) == 0
    assert "already installed" in capsys.readouterr().out
    server.files.clear()
    (tmp_path / "fake_model").rename(tmp_path / "moved")
    assert cli.download_model("Fake", quiet=True) == 1
    assert "HTTP 404" in capsys.readouterr().err


def test_cli_reports_model_not_downloaded(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("GIGAAM_DOWNLOADS", str(tmp_path / "empty"))
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    assert cli.main([str(audio), "--model", "Multilingual", "--config", str(tmp_path / "none.json")]) == 2
    assert "--download Multilingual" in capsys.readouterr().err
