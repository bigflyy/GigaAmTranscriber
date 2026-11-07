"""The local audio server for the window's player (plan 05 A1)."""

from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from gigaam_app.audio_server import AudioServer, content_type


@pytest.fixture
def served(tmp_path):
    path = tmp_path / "talk.mp3"
    path.write_bytes(bytes(range(256)) * 4)  # 1024 bytes
    server = AudioServer()
    url = server.register(path)
    yield server, path, url
    server.stop()


def fetch(url, headers=None, method="GET"):
    with urlopen(Request(url, headers=headers or {}, method=method), timeout=5) as answer:
        return answer.status, dict(answer.headers), answer.read()


def test_whole_file_with_its_type(served):
    _, path, url = served
    assert url.startswith("http://127.0.0.1:") and url.endswith("/talk.mp3")
    status, headers, body = fetch(url)
    assert status == 200 and body == path.read_bytes()
    assert headers["Content-Type"] == "audio/mpeg" and headers["Accept-Ranges"] == "bytes"


@pytest.mark.parametrize("wanted, first, last", [("bytes=100-199", 100, 199), ("bytes=1000-", 1000, 1023),
                                                 ("bytes=-24", 1000, 1023), ("bytes=1000-5000", 1000, 1023)])
def test_byte_ranges(served, wanted, first, last):
    _, path, url = served
    status, headers, body = fetch(url, {"Range": wanted})
    assert status == 206 and body == path.read_bytes()[first:last + 1]
    assert headers["Content-Range"] == f"bytes {first}-{last}/1024"


def test_range_past_the_end_is_refused(served):
    with pytest.raises(HTTPError) as error:
        fetch(served[2], {"Range": "bytes=2000-"})
    assert error.value.code == 416


def test_head_sends_no_body(served):
    status, headers, body = fetch(served[2], method="HEAD")
    assert status == 200 and headers["Content-Length"] == "1024" and body == b""


def test_wrong_token_unknown_file_and_forgotten_file_are_refused(served):
    server, path, url = served
    base, key, name = url.rsplit("/", 2)
    for bad in (url.replace(server.token, "x" * len(server.token)), f"{base}/nokey/{name}",
                url.rsplit("/", 1)[0]):
        with pytest.raises(HTTPError) as error:
            fetch(bad)
        assert error.value.code == 404
    assert server.register(path) == url  # the same file keeps its address
    server.forget(path)
    with pytest.raises(HTTPError):
        fetch(url)


def test_types_the_player_needs():
    assert content_type("a.opus") == "audio/ogg" and content_type("a.M4A") == "audio/mp4"
    assert content_type("a.wav") == "audio/wav"


def test_playable_copy_with_the_real_ffmpeg(tmp_path):
    import wave

    import numpy as np

    from gigaam_app.audio import start_playable_copy

    source = tmp_path / "tone.wav"
    tone = (np.sin(np.arange(16000) * 2 * np.pi * 440 / 16000) * 8000).astype(np.int16)
    with wave.open(str(source), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(tone.tobytes())
    target = tmp_path / "tone.opus"
    process = start_playable_copy(source, target)
    _, stderr = process.communicate(timeout=60)
    assert process.returncode == 0, stderr
    assert target.read_bytes()[:4] == b"OggS"
