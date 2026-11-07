"""whisper.cpp through ctypes: the shared libraries built by tools/build_whisper_cpp.py.

No Python binding package is used. The structures below mirror include/whisper.h of
whisper.cpp WHISPER_CPP_VERSION field by field; check_layout() compares the defaults
the library fills in with the values whisper.cpp's source sets, so a library built
from another version with a changed layout is refused instead of misread.

The libraries are built with GGML_BACKEND_DL: whisper.dll links only ggml and
ggml-base, and the compute backends are separate files loaded at run time from the
library folder: ggml-vulkan (any Vulkan GPU) and one ggml-cpu-<variant> per CPU
generation, of which ggml picks the best one this CPU supports.
"""

from collections import deque
import ctypes
from ctypes import (CFUNCTYPE, POINTER, Structure, c_bool, c_char_p, c_float, c_int, c_int64,
                    c_size_t, c_void_p)
import os
from pathlib import Path
import sys
import threading

WHISPER_CPP_VERSION = "1.9.5"

# enum whisper_sampling_strategy
SAMPLING_GREEDY = 0
# enum ggml_backend_dev_type
DEVICE_CPU, DEVICE_GPU, DEVICE_IGPU = 0, 1, 2
# enum ggml_log_level: NONE, DEBUG, INFO, WARN, ERROR, CONT (continues the previous line)
LOG_ERROR, LOG_CONT = 4, 5
# Token times (whisper_token_data.t0, t1) count in 10 ms steps.
TIME_STEP_SECONDS = 0.01


def platform_tag():
    """Folder name of the build for this system under third_party/whisper.cpp/."""
    return "windows-x64" if sys.platform == "win32" else "linux-x64"


def library_dir():
    """Folder holding whisper and the ggml libraries: GIGAAM_WHISPER_LIB if set, the
    whisper_cpp folder inside a frozen build, else the build in third_party/ (source checkout)."""
    override = os.environ.get("GIGAAM_WHISPER_LIB")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "whisper_cpp"
    return Path(__file__).resolve().parents[1] / "third_party" / "whisper.cpp" / platform_tag()


# ------------------------------------------------------------------ structures (whisper.h)


class WhisperAheads(Structure):
    _fields_ = [("n_heads", c_size_t), ("heads", c_void_p)]


class ContextParams(Structure):
    """struct whisper_context_params"""
    _fields_ = [
        ("use_gpu", c_bool),
        ("flash_attn", c_bool),
        ("gpu_device", c_int),
        ("dtw_token_timestamps", c_bool),
        ("dtw_aheads_preset", c_int),
        ("dtw_n_top", c_int),
        ("dtw_aheads", WhisperAheads),
        ("dtw_mem_size", c_size_t),
    ]


class TokenData(Structure):
    """struct whisper_token_data"""
    _fields_ = [
        ("id", c_int),
        ("tid", c_int),
        ("p", c_float),
        ("plog", c_float),
        ("pt", c_float),
        ("ptsum", c_float),
        ("t0", c_int64),
        ("t1", c_int64),
        ("t_dtw", c_int64),
        ("vlen", c_float),
    ]


class GreedyParams(Structure):
    _fields_ = [("best_of", c_int)]


class BeamSearchParams(Structure):
    _fields_ = [("beam_size", c_int), ("patience", c_float)]


class VadParams(Structure):
    """struct whisper_vad_params (whisper.cpp's own VAD; the app uses Silero instead)."""
    _fields_ = [
        ("threshold", c_float),
        ("min_speech_duration_ms", c_int),
        ("min_silence_duration_ms", c_int),
        ("max_speech_duration_s", c_float),
        ("speech_pad_ms", c_int),
        ("samples_overlap", c_float),
    ]


class FullParams(Structure):
    """struct whisper_full_params, in the order of whisper.h."""
    _fields_ = [
        ("strategy", c_int),
        ("n_threads", c_int),
        ("n_max_text_ctx", c_int),
        ("offset_ms", c_int),
        ("duration_ms", c_int),
        ("translate", c_bool),
        ("no_context", c_bool),
        ("no_timestamps", c_bool),
        ("single_segment", c_bool),
        ("print_special", c_bool),
        ("print_progress", c_bool),
        ("print_realtime", c_bool),
        ("print_timestamps", c_bool),
        ("token_timestamps", c_bool),
        ("thold_pt", c_float),
        ("thold_ptsum", c_float),
        ("max_len", c_int),
        ("split_on_word", c_bool),
        ("max_tokens", c_int),
        ("debug_mode", c_bool),
        ("audio_ctx", c_int),
        ("tdrz_enable", c_bool),
        ("suppress_regex", c_char_p),
        ("initial_prompt", c_char_p),
        ("carry_initial_prompt", c_bool),
        ("prompt_tokens", POINTER(c_int)),
        ("prompt_n_tokens", c_int),
        ("language", c_char_p),
        ("detect_language", c_bool),
        ("suppress_blank", c_bool),
        ("suppress_nst", c_bool),
        ("temperature", c_float),
        ("max_initial_ts", c_float),
        ("length_penalty", c_float),
        ("temperature_inc", c_float),
        ("entropy_thold", c_float),
        ("logprob_thold", c_float),
        ("no_speech_thold", c_float),
        ("greedy", GreedyParams),
        ("beam_search", BeamSearchParams),
        ("new_segment_callback", c_void_p),
        ("new_segment_callback_user_data", c_void_p),
        ("progress_callback", c_void_p),
        ("progress_callback_user_data", c_void_p),
        ("encoder_begin_callback", c_void_p),
        ("encoder_begin_callback_user_data", c_void_p),
        ("abort_callback", c_void_p),
        ("abort_callback_user_data", c_void_p),
        ("logits_filter_callback", c_void_p),
        ("logits_filter_callback_user_data", c_void_p),
        ("grammar_rules", c_void_p),
        ("n_grammar_rules", c_size_t),
        ("i_start_rule", c_size_t),
        ("grammar_penalty", c_float),
        ("vad", c_bool),
        ("vad_model_path", c_char_p),
        ("vad_params", VadParams),
    ]


# void (*ggml_log_callback)(enum ggml_log_level level, const char * text, void * user_data)
LOG_CALLBACK = CFUNCTYPE(None, c_int, c_char_p, c_void_p)
# bool (*ggml_abort_callback)(void * data)
ABORT_CALLBACK = CFUNCTYPE(c_bool, c_void_p)


def _close(value, expected, tolerance=1e-6):
    return abs(value - expected) <= tolerance


def check_layout(params):
    """True if a FullParams filled by whisper_full_default_params(GREEDY) holds the defaults
    that whisper.cpp 1.9.5 sets (src/whisper.cpp). The checked fields are spread from the
    first to the last member, so a moved, added or removed field shifts at least one."""
    return (params.strategy == SAMPLING_GREEDY and params.n_max_text_ctx == 16384
            and params.no_context and params.print_progress and params.print_timestamps
            and not params.token_timestamps and _close(params.thold_pt, 0.01)
            and _close(params.thold_ptsum, 0.01) and params.language == b"en"
            and params.suppress_blank and not params.suppress_nst
            and _close(params.max_initial_ts, 1.0) and _close(params.length_penalty, -1.0)
            and _close(params.temperature_inc, 0.2) and _close(params.entropy_thold, 2.4)
            and _close(params.logprob_thold, -1.0) and _close(params.no_speech_thold, 0.6)
            and params.greedy.best_of == 5 and params.beam_search.beam_size == -1
            and _close(params.beam_search.patience, -1.0) and _close(params.grammar_penalty, 100.0)
            and not params.vad and _close(params.vad_params.threshold, 0.5)
            and params.vad_params.min_speech_duration_ms == 250
            and params.vad_params.min_silence_duration_ms == 100
            and params.vad_params.speech_pad_ms == 30 and _close(params.vad_params.samples_overlap, 0.1))


# ------------------------------------------------------------------ the libraries


def _find_library(folder, stem):
    """Path of one library in the folder: 'whisper.dll' on Windows; on Linux
    'libwhisper.so' or a versioned name such as 'libwhisper.so.1'."""
    if sys.platform == "win32":
        path = folder / f"{stem}.dll"
        return path if path.is_file() else None
    exact = folder / f"lib{stem}.so"
    if exact.is_file():
        return exact
    versioned = sorted(folder.glob(f"lib{stem}.so.*"))
    return versioned[0] if versioned else None


class _Functions:
    """C functions looked up by name in the first of several libraries that exports them."""

    def __init__(self, *libraries):
        self._libraries = libraries

    def bind(self, name, argtypes, restype):
        for library in self._libraries:
            try:
                function = getattr(library, name)
            except AttributeError:
                continue
            function.argtypes, function.restype = argtypes, restype
            setattr(self, name, function)
            return
        raise AttributeError(f"{name} is not exported by the ggml libraries")


class Library:
    """whisper and ggml loaded once per process, with every backend from the library folder.

    Log lines from whisper.cpp and ggml are kept (the last few hundred) for error
    messages instead of going to stderr; GIGAAM_WHISPER_LOG=1 also prints them.
    """

    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get(cls, folder=None):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(Path(folder) if folder else library_dir())
            return cls._instance

    def __init__(self, folder):
        self.folder = folder
        self.log = deque(maxlen=400)
        self._print_log = os.environ.get("GIGAAM_WHISPER_LOG") == "1"
        paths = {stem: _find_library(folder, stem) for stem in ("ggml-base", "ggml", "whisper")}
        missing = [stem for stem, path in paths.items() if path is None]
        if missing:
            raise FileNotFoundError(f"whisper.cpp libraries not found in {folder} (missing: {', '.join(missing)})")
        if sys.platform == "win32":
            # Lets the backends that ggml loads later find ggml-base.dll beside them.
            self._dll_directory = os.add_dll_directory(str(folder))
            mode = 0
        else:
            mode = ctypes.RTLD_GLOBAL
        self.ggml_base = ctypes.CDLL(str(paths["ggml-base"]), mode=mode)
        self.ggml = ctypes.CDLL(str(paths["ggml"]), mode=mode)
        self.whisper = ctypes.CDLL(str(paths["whisper"]), mode=mode)
        # ggml's functions are split between ggml-base (tensors, devices) and ggml (backend registry).
        self.g = _Functions(self.ggml, self.ggml_base)
        self._declare()
        # Kept referenced for as long as the libraries may call it.
        self._log_callback = LOG_CALLBACK(self._on_log)
        self.whisper.whisper_log_set(self._log_callback, None)
        self.g.ggml_log_set(self._log_callback, None)
        self.g.ggml_backend_load_all_from_path(str(folder).encode("utf-8"))
        defaults = self.whisper.whisper_full_default_params(SAMPLING_GREEDY)
        if not check_layout(defaults):
            raise RuntimeError(f"whisper.cpp in {folder} does not match the structures of version "
                               f"{WHISPER_CPP_VERSION} this app was written for")

    def _declare(self):
        """Argument and result types of every function the app calls."""
        g = self.g
        g.bind("ggml_log_set", [LOG_CALLBACK, c_void_p], None)
        g.bind("ggml_backend_load_all_from_path", [c_char_p], None)
        g.bind("ggml_backend_dev_count", [], c_size_t)
        g.bind("ggml_backend_dev_get", [c_size_t], c_void_p)
        g.bind("ggml_backend_dev_name", [c_void_p], c_char_p)
        g.bind("ggml_backend_dev_description", [c_void_p], c_char_p)
        g.bind("ggml_backend_dev_type", [c_void_p], c_int)
        g.bind("ggml_backend_dev_memory", [c_void_p, POINTER(c_size_t), POINTER(c_size_t)], None)
        g.bind("ggml_backend_reg_count", [], c_size_t)
        g.bind("ggml_backend_reg_get", [c_size_t], c_void_p)
        g.bind("ggml_backend_reg_name", [c_void_p], c_char_p)

        w = self.whisper
        w.whisper_log_set.argtypes = [LOG_CALLBACK, c_void_p]
        w.whisper_log_set.restype = None
        w.whisper_version.argtypes = []
        w.whisper_version.restype = c_char_p
        w.whisper_print_system_info.argtypes = []
        w.whisper_print_system_info.restype = c_char_p
        w.whisper_context_default_params.argtypes = []
        w.whisper_context_default_params.restype = ContextParams
        w.whisper_full_default_params.argtypes = [c_int]
        w.whisper_full_default_params.restype = FullParams
        w.whisper_init_from_file_with_params.argtypes = [c_char_p, ContextParams]
        w.whisper_init_from_file_with_params.restype = c_void_p
        w.whisper_free.argtypes = [c_void_p]
        w.whisper_free.restype = None
        w.whisper_full.argtypes = [c_void_p, FullParams, POINTER(c_float), c_int]
        w.whisper_full.restype = c_int
        w.whisper_full_n_segments.argtypes = [c_void_p]
        w.whisper_full_n_segments.restype = c_int
        w.whisper_full_lang_id.argtypes = [c_void_p]
        w.whisper_full_lang_id.restype = c_int
        w.whisper_lang_str.argtypes = [c_int]
        w.whisper_lang_str.restype = c_char_p
        w.whisper_lang_id.argtypes = [c_char_p]
        w.whisper_lang_id.restype = c_int
        w.whisper_full_n_tokens.argtypes = [c_void_p, c_int]
        w.whisper_full_n_tokens.restype = c_int
        w.whisper_full_get_token_text.argtypes = [c_void_p, c_int, c_int]
        w.whisper_full_get_token_text.restype = c_char_p
        w.whisper_full_get_token_data.argtypes = [c_void_p, c_int, c_int]
        w.whisper_full_get_token_data.restype = TokenData
        w.whisper_token_eot.argtypes = [c_void_p]
        w.whisper_token_eot.restype = c_int
        w.whisper_is_multilingual.argtypes = [c_void_p]
        w.whisper_is_multilingual.restype = c_int

    def _on_log(self, level, text, user_data):
        line = (text or b"").decode("utf-8", "replace")
        if level == LOG_CONT and self.log:
            self.log[-1] = (self.log[-1][0], self.log[-1][1] + line)
        else:
            self.log.append((level, line))
        if self._print_log:
            sys.stderr.write(line)

    def recent_errors(self, count=5):
        lines = [text.strip() for level, text in self.log if level == LOG_ERROR and text.strip()]
        return lines[-count:]

    @property
    def version(self):
        return self.whisper.whisper_version().decode()

    @property
    def system_info(self):
        return self.whisper.whisper_print_system_info().decode()

    def backends(self):
        """Names of the registered backends, for example ['Vulkan', 'CPU']."""
        g = self.g
        return [g.ggml_backend_reg_name(g.ggml_backend_reg_get(i)).decode()
                for i in range(g.ggml_backend_reg_count())]

    def devices(self):
        """[(type, name, description, total memory bytes)] for every ggml device."""
        g = self.g
        found = []
        for index in range(g.ggml_backend_dev_count()):
            device = g.ggml_backend_dev_get(index)
            free, total = c_size_t(0), c_size_t(0)
            g.ggml_backend_dev_memory(device, ctypes.byref(free), ctypes.byref(total))
            found.append((g.ggml_backend_dev_type(device), g.ggml_backend_dev_name(device).decode(),
                          (g.ggml_backend_dev_description(device) or b"").decode("utf-8", "replace"),
                          total.value))
        return found

    def gpus(self):
        """GPU devices in whisper.cpp's gpu_device numbering (GPU and IGPU types, in ggml's order)."""
        return [device for device in self.devices() if device[0] in (DEVICE_GPU, DEVICE_IGPU)]


def preferred_gpu(gpus):
    """Index (in whisper.cpp's gpu_device numbering) of the GPU to use: the first one
    with its own memory (a discrete card) before integrated ones; None without GPUs."""
    for index, device in enumerate(gpus):
        if device[0] == DEVICE_GPU:
            return index
    return 0 if gpus else None


# ------------------------------------------------------------------ one loaded model


class Token:
    """One text token of a result: raw UTF-8 bytes (a token may hold part of a
    character) and its time in seconds from the start of the audio passed in."""

    __slots__ = ("data", "start", "end", "probability")

    def __init__(self, data, start, end, probability):
        self.data, self.start, self.end, self.probability = data, start, end, probability

    def __repr__(self):
        return f"Token({self.data!r}, {self.start:.2f}, {self.end:.2f})"


class Cancelled(Exception):
    """whisper_full stopped because should_cancel() returned True."""


class Context:
    """A ggml model file loaded by whisper.cpp. One whisper_full at a time (not thread safe)."""

    def __init__(self, model_path, use_gpu=True, gpu_device=0, flash_attn=True, library=None):
        self.lib = library or Library.get()
        params = self.lib.whisper.whisper_context_default_params()
        params.use_gpu = bool(use_gpu)
        params.gpu_device = int(gpu_device or 0)
        params.flash_attn = bool(flash_attn)
        self.handle = self.lib.whisper.whisper_init_from_file_with_params(str(model_path).encode("utf-8"), params)
        if not self.handle:
            details = "; ".join(self.lib.recent_errors()) or "no details"
            raise RuntimeError(f"whisper.cpp could not load {model_path}: {details}")
        self.eot = self.lib.whisper.whisper_token_eot(self.handle)
        self.multilingual = bool(self.lib.whisper.whisper_is_multilingual(self.handle))

    def close(self):
        if self.handle:
            self.lib.whisper.whisper_free(self.handle)
            self.handle = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def is_language(self, code):
        return self.lib.whisper.whisper_lang_id(code.encode()) >= 0

    def transcribe(self, samples, language=None, n_threads=4, should_cancel=None):
        """Recognise one piece of 16 kHz mono float32 audio (up to 30 s: Whisper's window).

        Greedy decoding with whisper.cpp's usual fallback to higher temperatures for a
        failing window. Nothing is carried over from the previous call (no_context).
        language: a code such as 'ru', or None / 'auto' to detect it.
        Returns (language code, [Token]) with special tokens left out.
        """
        w = self.lib.whisper
        params = w.whisper_full_default_params(SAMPLING_GREEDY)
        params.n_threads = int(n_threads)
        params.no_context = True
        params.print_progress = False
        params.print_timestamps = False
        params.print_realtime = False
        params.token_timestamps = True
        params.language = (language or "auto").encode()
        params.suppress_nst = True
        abort = None
        if should_cancel is not None:
            abort = ABORT_CALLBACK(lambda data: bool(should_cancel()))
            params.abort_callback = ctypes.cast(abort, c_void_p)
        samples = _float32_array(samples)
        pointer = samples.ctypes.data_as(POINTER(c_float))
        result = w.whisper_full(self.handle, params, pointer, len(samples))
        if should_cancel is not None and should_cancel():
            raise Cancelled()
        if result != 0:
            details = "; ".join(self.lib.recent_errors()) or "no details"
            raise RuntimeError(f"whisper_full failed ({result}): {details}")
        lang = w.whisper_lang_str(w.whisper_full_lang_id(self.handle))
        tokens = []
        for segment in range(w.whisper_full_n_segments(self.handle)):
            for index in range(w.whisper_full_n_tokens(self.handle, segment)):
                data = w.whisper_full_get_token_data(self.handle, segment, index)
                if data.id >= self.eot:  # special tokens: end of text, language, timestamps, ...
                    continue
                text = w.whisper_full_get_token_text(self.handle, segment, index) or b""
                tokens.append(Token(text, data.t0 * TIME_STEP_SECONDS, data.t1 * TIME_STEP_SECONDS, data.p))
        del abort  # the call has returned; the callback may go
        return (lang.decode() if lang else ""), tokens


def _float32_array(samples):
    import numpy as np
    return np.ascontiguousarray(samples, dtype=np.float32)
