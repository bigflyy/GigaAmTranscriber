"""Command line: gigaam-cli FILE [FILE ...]. The model loads once for all files.

gigaam-cli --list-models shows every model and whether it is installed;
gigaam-cli --download MODEL fetches an extra model (resumes if interrupted);
gigaam-cli --devices shows the GPUs and CPU each recognition engine can use;
gigaam-cli --speakers FILE also finds who speaks when (plan 07): the saved files name the
speakers ("Говорящий 1: ..."); --speakers 3 when the number of speakers is known.
"""

import argparse
from dataclasses import fields
import glob
from pathlib import Path
import sys
import time

from . import __version__, catalog, config, download
from .audio import decode_audio
from .engine import MODELS, ModelNotInstalled, Transcriber
from .outputs import FORMATS, write_outputs
from .vad import VadOptions

MAX_SPEAKERS = 20  # the window's limit too (controller.MAX_SPEAKERS)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="gigaam-cli",
        description="Transcribe speech in audio or video files with GigaAM (Russian) or Whisper.")
    parser.add_argument("files", nargs="*", type=Path, help="audio or video files")
    parser.add_argument("-o", "--out-dir", type=Path, help="output folder (default: beside each file)")
    parser.add_argument("--model", choices=tuple(MODELS), help="recognition model (default: RNNT)")
    parser.add_argument("--language", metavar="CODE",
                        help='Whisper only: speech language such as "en" or "ru", or "auto" to detect it '
                             "(default: the settings file, else auto)")
    parser.add_argument("--device", choices=("auto", "gpu", "cpu"), help="default: auto")
    parser.add_argument("--threads", type=int, help="CPU threads for recognition (default: automatic)")
    parser.add_argument("--formats", help=f"comma-separated list from {','.join(FORMATS)} "
                                          "(default: txt,timestamps)")
    parser.add_argument("--speakers", nargs="?", const="auto", metavar="COUNT",
                        help="find who speaks when and name the speakers in the files: alone or "
                             "'auto' to find their number, a number when it is known, 'off' to skip "
                             "(default: the settings file, else off). The speaker models "
                             f"({size_text(catalog.SPEAKER_MODEL.download_size)}) are downloaded the first time")
    parser.add_argument("--config", type=Path, help="settings file (default: gigaam-config.json beside the app)")
    parser.add_argument("--quiet", action="store_true", help="print only errors")
    parser.add_argument("--list-models", action="store_true", help="show the models and where they are installed")
    parser.add_argument("--devices", action="store_true",
                        help="show the GPUs and CPU that GigaAM (ONNX Runtime) and Whisper (whisper.cpp) can use")
    parser.add_argument("--download", metavar="MODEL", choices=tuple(MODELS) + (catalog.SPEAKER_MODEL.key,),
                        help="download an extra model (or Speakers, the speaker models), "
                             "then transcribe FILES if any are given")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    tuning = parser.add_argument_group("segmentation (override the settings file)")
    for item in fields(VadOptions):
        tuning.add_argument("--" + item.name.replace("_", "-"), type=item.type, dest=item.name)
    return parser


def expand_wildcards(paths):
    """cmd.exe and PowerShell pass *.mp3 through unexpanded; expand it here, keeping the order."""
    expanded = []
    for path in paths:
        text = str(path)
        matches = sorted(glob.glob(text)) if glob.has_magic(text) else []
        expanded += [Path(match) for match in matches if Path(match).is_file()] or [path]
    return expanded


def safe_console():
    """A redirected console uses the ANSI code page, which lacks many characters of
    file names; print those as escapes instead of failing after the work is done."""
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")


def size_text(size):
    return f"{size / 1024 ** 3:.1f} GB" if size >= 1024 ** 3 else f"{size / 1024 ** 2:.0f} MB"


def speaker_count(value):
    """--speakers: None (off), 0 (find the number) or the known number; ValueError otherwise."""
    text = str(value).strip().lower()
    if text == "off":
        return None
    if text == "auto":
        return 0
    if not text.isdigit() or not 1 <= int(text) <= MAX_SPEAKERS:
        raise ValueError(f"--speakers: expected auto, off or a number from 1 to {MAX_SPEAKERS}")
    return int(text)


def find_model(key):
    """ModelInfo for a --download name: a recognition model, or the speaker models."""
    return catalog.SPEAKER_MODEL if key == catalog.SPEAKER_MODEL.key else catalog.find(key)


def list_models():
    from .paths import downloads_dir, models_dir
    for info in catalog.CATALOG + (catalog.SPEAKER_MODEL,):
        folder = catalog.installed_folder(info)
        if info.bundled:
            state = "bundled" if folder else "missing"
        else:
            state = "installed" if folder else f"download {size_text(info.download_size)}"
        print(f"{info.key:<20} {state:<16} {info.description}")
    print(f"\nBundled models: {models_dir()}\nDownloaded models: {downloads_dir()}")


def list_devices():
    """Print what each engine can run on; exit code 1 if whisper.cpp cannot be loaded."""
    import onnxruntime
    from .asr import GPU_PROVIDERS, PROVIDER_NAMES
    from . import whisper_cpp
    providers = [name for name in onnxruntime.get_available_providers()
                 if name in GPU_PROVIDERS or name == "CPUExecutionProvider"]
    print("GigaAM (ONNX Runtime): " + ", ".join(PROVIDER_NAMES.get(name, name) for name in providers))
    try:
        library = whisper_cpp.Library.get()
    except (OSError, RuntimeError) as error:
        print(f"Whisper (whisper.cpp): cannot be loaded: {error}")
        return 1
    print(f"Whisper (whisper.cpp {library.version}): backends {', '.join(library.backends())}")
    gpus = library.gpus()
    chosen = whisper_cpp.preferred_gpu(gpus)
    for index, (_, _, description, memory) in enumerate(gpus):
        print(f"  GPU {index}: {description}, {memory / 1024 ** 3:.1f} GB" + (" (used)" if index == chosen else ""))
    if not gpus:
        print("  no Vulkan GPU found: Whisper runs on the CPU")
    for kind, _, description, _ in library.devices():
        if kind == whisper_cpp.DEVICE_CPU:
            print(f"  CPU: {description.strip()}")
    return 0


def download_model(key, quiet):
    """Download one catalog model with a progress line; returns an exit code."""
    info = find_model(key)
    folder = catalog.installed_folder(info)
    if folder is not None:
        if not quiet:
            print(f"{info.key} is already installed: {folder}")
        return 0
    last = [0.0]

    def progress(done, total):
        now = time.perf_counter()
        if not quiet and sys.stderr.isatty() and (now - last[0] > 0.2 or done == total):
            last[0] = now
            print(f"\r  {info.key}: {done / 1024 ** 2:,.0f} of {total / 1024 ** 2:,.0f} MB",
                  end="", file=sys.stderr, flush=True)

    if not quiet:
        print(f"Downloading {info.key} ({size_text(info.download_size)})...", flush=True)
    try:
        folder = download.install(info, on_progress=progress)
    except KeyboardInterrupt:
        print("\nDownload stopped; run the same command again to resume.", file=sys.stderr)
        return 1
    except (download.DownloadError, OSError) as error:
        print(f"\nDownload failed: {error}", file=sys.stderr)
        return 1
    if not quiet:
        if sys.stderr.isatty():
            print(file=sys.stderr)
        print(f"{info.key} installed: {folder}")
    return 0


def main(argv=None):
    safe_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list_models:
        list_models()
        return 0
    if args.devices:
        return list_devices()
    if args.download:
        code = download_model(args.download, args.quiet)
        if code or not args.files:
            return code
    if not args.files:
        parser.error("no input files")
    args.files = expand_wildcards(args.files)
    try:
        settings = config.load(args.config)
    except (OSError, ValueError) as error:
        print(f"Settings error: {error}", file=sys.stderr)
        return 2
    model = args.model or settings.model
    language = args.language or settings.language
    device = args.device or settings.engine_device
    threads = args.threads if args.threads is not None else (settings.cpu_threads or None)
    formats = args.formats.split(",") if args.formats else settings.outputs
    unknown = [fmt for fmt in formats if fmt not in FORMATS]
    if unknown:
        print(f"Unknown format: {', '.join(unknown)}", file=sys.stderr)
        return 2
    try:
        speakers = speaker_count(args.speakers if args.speakers is not None
                                 else ("auto" if settings.speakers else "off"))
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    options = settings.vad
    for item in fields(VadOptions):
        value = getattr(args, item.name)
        if value is not None:
            setattr(options, item.name, value)

    def say(message):
        if not args.quiet:
            print(message, flush=True)

    missing = [str(path) for path in args.files if not path.is_file()]
    if missing:
        print("File not found: " + ", ".join(missing), file=sys.stderr)
        return 2
    try:
        transcriber = Transcriber(model, device=device, cpu_threads=threads, language=language)
    except (ModelNotInstalled, ValueError) as error:  # ValueError: a language Whisper does not know
        print(error, file=sys.stderr)
        return 2
    if args.language and not transcriber.uses_language:
        print(f"Note: --language is for Whisper; {model} recognises Russian only.", file=sys.stderr)
    say(f"{model} on {transcriber.device_label}, loaded in {transcriber.load_seconds:.1f} s")
    speaker_model = None
    if speakers is not None:
        speaker_model = load_speaker_model(device, threads, args.quiet)
        if speaker_model is None:
            return 1
    failures = 0
    for path in args.files:
        try:
            last = [0.0]

            def progress(searched, recognised):
                now = time.perf_counter()
                if not args.quiet and sys.stderr.isatty() and now - last[0] > 0.2:
                    last[0] = now
                    print(f"\r  searched {searched * 100:5.1f}%  recognised {recognised * 100:5.1f}%",
                          end="", file=sys.stderr, flush=True)

            result = transcriber.transcribe(path, options, on_progress=progress)
            if not args.quiet and sys.stderr.isatty():
                print("\r" + " " * 40 + "\r", end="", file=sys.stderr)
            if not result.segments:
                say(f"{path.name}: no speech found, nothing written")
                continue
            if speaker_model is not None:
                found, seconds = find_speakers(speaker_model, path, result, speakers or None)
                say(f"{path.name}: {found} speaker(s) found in {seconds:.1f} s")
            written = write_outputs(result, formats, args.out_dir, doubt_below=settings.doubt_light)
            speed = result.audio_seconds / result.elapsed_seconds if result.elapsed_seconds else 0
            say(f"{path.name}: {result.audio_seconds:.0f} s of audio in {result.elapsed_seconds:.1f} s "
                f"({speed:.0f}x realtime)")
            for item in written:
                say(f"  {item}")
        except Exception as error:  # report and continue with the next file
            failures += 1
            print(f"{path}: {error}", file=sys.stderr)
    return 1 if failures else 0


def load_speaker_model(device, threads, quiet):
    """The speaker models, downloaded first if needed; None (after a message) when that fails."""
    from .diarize import SpeakerModel
    if catalog.installed_folder(catalog.SPEAKER_MODEL) is None:
        if download_model(catalog.SPEAKER_MODEL.key, quiet):
            return None
    try:
        return SpeakerModel(catalog.installed_folder(catalog.SPEAKER_MODEL), device=device, cpu_threads=threads)
    except Exception as error:  # a damaged download, a provider that fails to start
        print(f"Speaker models could not be loaded: {error}", file=sys.stderr)
        return None


def find_speakers(model, path, result, count):
    """Give the words of result their speakers (count: the known number, or None to find it).
    Returns (speakers with words, seconds it took)."""
    from .diarize import assign_speakers
    started = time.perf_counter()
    found = model.diarize(decode_audio(path), num_speakers=count)
    result.speakers = assign_speakers(result.segments, found.exclusive_turns)
    return len(result.speakers), time.perf_counter() - started


if __name__ == "__main__":
    raise SystemExit(main())
