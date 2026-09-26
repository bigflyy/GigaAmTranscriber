"""Focused release regressions; run with python -m unittest discover -s tests -p test_desktop.py."""

import tempfile
import io
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import torch

import app_config
import gui
import gigaam
import transcribe
from model_catalog import MODEL_CHOICES, model_files
from gigaam import vad_utils
from transcribe import format_audio_stats, format_segments, save_transcripts, transcript_paths


class ConfigTests(unittest.TestCase):
    def test_multilingual_config_roundtrip_and_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for label, model in MODEL_CHOICES.items():
                with self.subTest(model=model):
                    config = app_config.validate_config({"model": label})
                    app_config.write_config(path, config)
                    self.assertEqual(app_config.read_config(path)["model"], label)
                    self.assertEqual(transcribe.parser().parse_args(["--model", model]).model, model)

    def test_defaults_and_legacy_config(self):
        config = app_config.validate_config({"min_duration": 15})
        self.assertNotIn("min_duration", config)
        self.assertFalse(config["include_timestamps"])
        for key in ("max_duration", "vad_max_speech_s", "strict_limit_duration"):
            self.assertEqual(config[key], 25)
        self.assertEqual(app_config.read_config("gigaam-config.example.json"), config)

    def test_invalid_values(self):
        for config in ({"cpu_threads": 0}, {"cpu_threads": True}, {"vad_threshold": float("nan")},
                       {"vad_min_speech_ms": 1.5}, {"model": "unknown"}, {"version": 2},
                       {"typo": 1}, {"include_timestamps": "false"}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                app_config.validate_config(config)

    def test_roundtrip_and_failed_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = app_config.validate_config({"cpu_threads": 8, "model": "CTC"})
            app_config.write_config(path, config)
            self.assertEqual(app_config.read_config(path), config)
            with patch.object(app_config.os, "replace", side_effect=PermissionError), self.assertRaises(PermissionError):
                app_config.write_config(path, app_config.defaults())
            self.assertEqual(app_config.read_config(path), config)
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    def test_frozen_config_path(self):
        with patch.object(app_config.sys, "frozen", True, create=True), \
             patch.object(app_config.sys, "executable", str(Path.cwd() / "App.exe")):
            self.assertEqual(app_config.default_config_path(), Path.cwd() / "gigaam-config.json")


class ChunkTests(unittest.TestCase):
    def test_vad_progress_is_bounded_and_completes_without_speech(self):
        events = []
        def scan(*args, **kwargs):
            for percent in (0.1, 0.9, 1, 50, 50.2, 99.9, 100):
                kwargs["progress_tracking_callback"](percent)
            return []
        with patch.object(vad_utils, "load_audio", return_value=torch.zeros(16000)), \
             patch.object(vad_utils, "get_pipeline"), \
             patch.object(vad_utils, "get_speech_timestamps", side_effect=scan):
            chunks, bounds = vad_utils.segment_audio_file("fixture", 16000, vad_progress_callback=events.append)
        self.assertEqual(events, [0, 1, 50, 99, 100])
        self.assertEqual((chunks, bounds), ([], []))

    def chunks(self, regions, **kwargs):
        wave = torch.zeros(120 * 16000)
        stats = []
        with patch.object(vad_utils, "load_audio", return_value=wave), \
             patch.object(vad_utils, "get_pipeline"), \
             patch.object(vad_utils, "get_speech_timestamps", return_value=[dict(start=a, end=b) for a, b in regions]):
            chunks, bounds = vad_utils.segment_audio_file("fixture", 16000, stats_callback=stats.append, **kwargs)
        self.assertTrue(all(chunk.numel() <= 400000 for chunk in chunks))
        return bounds, stats[0]

    def test_merge_without_preferred_min(self):
        self.assertEqual(self.chunks([(0, 16), (16, 20)], min_duration=1)[0], [(0, 20)])
        self.assertEqual(self.chunks([(0, 20), (20, 25)])[0], [(0, 25)])

    def test_gap_counts_toward_maximum(self):
        self.assertEqual(self.chunks([(0, 10), (13, 23)])[0], [(0, 23)])
        self.assertEqual(self.chunks([(0, 10), (16, 26)])[0], [(0, 10), (16, 26)])

    def test_hard_limit(self):
        self.assertEqual(self.chunks([(0, 40)])[0], [(0, 20), (20, 40)])

    def test_leading_silence_is_excluded(self):
        bounds, stats = self.chunks([(100, 110)])
        self.assertEqual(bounds, [(100, 110)])
        self.assertEqual(stats["speech_seconds"], 10)
        self.assertEqual(stats["retained_seconds"], 10)
        self.assertEqual(stats["filtered_seconds"], 110)

    def test_empty_and_tiny_tail(self):
        self.assertEqual(self.chunks([])[0], [])
        self.assertEqual(self.chunks([(0, 25), (30, 30.1)])[0], [(0, 25)])

    def test_stats_include_retained_pauses(self):
        _, stats = self.chunks([(1, 3), (5, 6)])
        self.assertEqual(stats["speech_seconds"], 3)
        self.assertEqual(stats["retained_seconds"], 5)
        self.assertNotIn("VAD", format_audio_stats(stats))


class ModelFilesTests(unittest.TestCase):
    def test_bundle_requirements_and_no_multilingual_tokenizer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "models").mkdir()
            with patch.object(transcribe, "__file__", str(root / "transcribe.py")):
                for model in MODEL_CHOICES.values():
                    with self.subTest(model=model):
                        self.assertIsNone(transcribe.bundled_model_root(model))
                        (root / "models" / f"{model}.ckpt").touch()
                        if model.startswith("multilingual"):
                            self.assertEqual(transcribe.bundled_model_root(model), root / "models")
                            with patch.object(gigaam, "_download_file") as download:
                                self.assertIsNone(gigaam._download_tokenizer(model, directory))
                                download.assert_not_called()
                        else:
                            self.assertIsNone(transcribe.bundled_model_root(model))
                            (root / "models" / model_files(model)[1]).touch()
                            self.assertEqual(transcribe.bundled_model_root(model), root / "models")

    def test_download_completion_and_interruption(self):
        class Response(io.BytesIO):
            def info(self):
                return {"Content-Length": "6"}

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.ckpt"
            with patch.object(gigaam.urllib.request, "urlopen", return_value=Response(b"abc")):
                with self.assertRaises(OSError):
                    gigaam._download_file("https://example.invalid/model", str(path))
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])
            with patch.object(gigaam.urllib.request, "urlopen", return_value=Response(b"abcdef")):
                gigaam._download_file("https://example.invalid/model", str(path))
            self.assertEqual(path.read_bytes(), b"abcdef")
            self.assertEqual(gigaam.hash_path(str(path)), "e80b5017098950fc58aad83c8c14978e")
            with patch.object(gigaam.urllib.request, "urlopen") as download:
                gigaam._download_file("https://example.invalid/model", str(path))
                download.assert_not_called()


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.root = tk.Tk()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args[1])
        self.config_patch = patch.object(gui, "default_config_path", return_value=self.folder / "gigaam-config.json")
        self.config_patch.start()
        self.app = gui.TranscriberApp(self.root)
        self.root.update()

    def tearDown(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()
        self.config_patch.stop()
        self.temp.cleanup()

    def wait_for(self, condition):
        deadline = time.monotonic() + 5
        while not condition():
            self.root.update()
            self.assertFalse(self.errors, self.errors)
            self.assertLess(time.monotonic(), deadline)
            time.sleep(.01)

    def test_controls_config_and_help(self):
        app = self.app
        self.assertFalse(app.include_timestamps.get())
        self.assertFalse(app.advanced.winfo_ismapped())
        self.assertNotIn("min_duration", app.values)
        app.toggle_advanced()
        app.cpu_threads.set("8")
        app.save_default_config()
        app.reset_defaults()
        app.load_config(self.folder / "gigaam-config.json")
        self.assertEqual(app.cpu_threads.get(), "8")
        for key in app.values:
            self.assertIn(key, gui.HELP)
        app.show_help()
        self.assertTrue(app.help_window.winfo_exists())

    def test_model_selection_reaches_worker(self):
        audio = self.folder / "sample.wav"
        audio.touch()
        self.app.file.set(str(audio))
        for label, expected in MODEL_CHOICES.items():
            with self.subTest(model=label), patch.object(gui, "run_transcription") as worker:
                self.app.model.set(label)
                self.app.save_default_config()
                self.app.reset_defaults()
                self.app.load_config(self.folder / "gigaam-config.json")
                self.app.start()
                self.wait_for(lambda: not self.app.running)
                self.assertEqual(worker.call_args.args[2], expected)

    def test_streaming_keeps_scroll_and_selection(self):
        app = self.app
        app.segments = [dict(transcription=f"Line {i} " * 20, boundaries=(i, i+1)) for i in range(100)]
        app.render_segments()
        self.root.update()
        app.text.yview("45.0")
        app.text.tag_add("sel", "46.1", "46.8")
        self.root.update()
        top = app.text.index("@0,0")
        selection = app.text.tag_ranges("sel")
        item = dict(transcription="Next chunk", boundaries=(100, 101))
        app.segments.append(item)
        app.append_segment(item)
        self.root.update()
        self.assertEqual(app.text.index("@0,0"), top)
        self.assertEqual(app.text.tag_ranges("sel"), selection)

    def test_vad_progress_transitions_to_recognition_and_respects_cancel(self):
        app = self.app
        app.events.put(("vad_progress", 37))
        app.poll()
        self.assertEqual(str(app.bar["mode"]), "determinate")
        self.assertEqual(float(app.bar["value"]), 37)
        self.assertEqual(app.status.get(), "Поиск речи: 37%")
        app.events.put(("vad_progress", 100))
        app.events.put(("progress", (0, 3, time.monotonic())))
        app.poll()
        self.assertEqual(float(app.bar["value"]), 0)
        self.assertIn("0 из 3", app.status.get())
        app.cancel_event.set()
        app.status.set("Cancelling")
        app.events.put(("vad_progress", 50))
        app.poll()
        self.assertEqual(app.status.get(), "Cancelling")
        self.assertEqual(float(app.bar["value"]), 0)

    def test_cancel_preserves_both_outputs_and_restart_clears(self):
        app = self.app
        audio = self.folder / "sample.wav"
        audio.touch()
        app.file.set(str(audio))
        emit = [True]
        item = dict(transcription="Partial result", boundaries=(1, 2))
        def worker(*args, **kwargs):
            if emit[0]:
                kwargs["result_callback"](item)
                kwargs["progress_callback"](1, 3)
            deadline = time.monotonic() + 5
            while not kwargs["cancel_callback"]():
                if time.monotonic() > deadline:
                    raise TimeoutError("Cancellation not received")
                time.sleep(.01)
            return [item] if emit[0] else []
        with patch.object(gui, "run_transcription", side_effect=worker):
            app.start()
            self.wait_for(lambda: len(app.segments) == 1)
            app.cancel_button.invoke()
            self.wait_for(lambda: not app.running)
            self.assertIn("Затрачено времени:", app.eta.get())
            paths = transcript_paths(app.saved_output)
            for path, timestamps in zip(paths, (False, True)):
                self.assertEqual(path.read_text(encoding="utf-8"), format_segments([item], timestamps))
            before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
            app.include_timestamps.set(True)
            app.timestamps_changed()
            self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths])
            emit[0] = False
            app.start()
            self.assertEqual(app.segments, [])
            self.assertEqual(app.text.get("1.0", "end-1c"), "")
            app.cancel()
            self.wait_for(lambda: not app.running)
            self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths])

    def test_completed_run_and_export(self):
        app = self.app
        audio = self.folder / "sample.wav"
        audio.touch()
        app.file.set(str(audio))
        item = dict(transcription="Finished result", boundaries=(0, 2))
        def worker(*args, **kwargs):
            kwargs["result_callback"](item)
            return [item]
        with patch.object(gui, "run_transcription", side_effect=worker):
            app.start()
            self.wait_for(lambda: not app.running)
        self.assertEqual(float(app.bar["value"]), 100)
        self.assertIn("Затрачено времени:", app.eta.get())
        for path in transcript_paths(app.saved_output):
            self.assertTrue(path.is_file())


if __name__ == "__main__":
    unittest.main()
