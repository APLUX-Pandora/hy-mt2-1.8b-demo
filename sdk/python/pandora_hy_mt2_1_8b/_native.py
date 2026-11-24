"""Synchronous ctypes binding with Runtime-controlled native execution ownership."""
import codecs
import ctypes as C
from functools import lru_cache
import json
import os
from pathlib import Path

from pandora_runtime import load_library as load_runtime_library

from . import _runtime

_RUNTIME_ABI = 5


class TranslationError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def resolve_model_dir(model_dir=None, *, default_container=None):
    """Resolve and verify the configured common/selected-target model resources."""
    from ._package import resolve_model_dir as resolve
    try:
        return resolve(model_dir, default_container=default_container)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise TranslationError(-2, "Invalid model package: " + str(exc)) from exc


class Options(C.Structure):
    _fields_ = [("struct_size", C.c_uint32), ("max_input_tokens", C.c_uint32)]


class Stats(C.Structure):
    _fields_ = [("struct_size", C.c_uint32), ("state", C.c_uint32),
                ("prompt_tokens", C.c_uint64), ("generated_tokens", C.c_uint64),
                ("init_ms", C.c_double), ("first_token_ms", C.c_double),
                ("generation_ms", C.c_double), ("tokens_per_second", C.c_double)]


NOTIFY = C.CFUNCTYPE(None, C.c_void_p)


@lru_cache(maxsize=1)
def _matched_library():
    """Load the native library paired with this SDK."""
    selected = Path(__file__).with_name("_runtime") / "libhy_mt2.so"
    if not selected.is_file():
        raise FileNotFoundError("Installed SDK is missing its matched native library")
    try:
        pairing = json.loads(selected.with_name("native-library.json").read_text(encoding="utf-8"))
        expected_version = pairing["sdk_version"]
        expected_abi = pairing["runtime_abi"]
        if not isinstance(expected_version, str) or not expected_version or type(expected_abi) is not int:
            raise ValueError("invalid SDK version or Runtime ABI")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise TranslationError(-5, "Invalid installed native SDK pairing metadata") from exc
    if expected_abi != _RUNTIME_ABI:
        raise TranslationError(-5, f"Native SDK Runtime ABI mismatch (expected {_RUNTIME_ABI}, found {expected_abi})")
    load_runtime_library()
    lib = C.CDLL(str(selected))
    lib.hy_mt2_version.argtypes = []
    lib.hy_mt2_version.restype = C.c_char_p
    raw_version = lib.hy_mt2_version()
    version = raw_version.decode("utf-8", "replace") if raw_version else None
    if version != expected_version:
        raise TranslationError(-5, f"Native SDK version mismatch (expected {expected_version!r}, found {version!r})")
    return lib


library = _matched_library


class _NativeModel:
    """One instance per process; close only after generation and readers finish.

    translate is blocking. abort is allowed from a separate application thread,
    never from on_chunk. on_chunk receives complete UTF-8 strings. When stopped,
    translate returns the partial result with cancelled=True.
    """
    def __init__(self, model_dir=None, library=None, max_input_tokens=512, *, runtime=None):
        self._pid = os.getpid()
        self._engine_slot = C.c_void_p()
        self._handle = None
        self._translating = False
        if type(max_input_tokens) is not int or not 32 <= max_input_tokens <= 8191:
            raise TranslationError(-1,"max_input_tokens must be an integer in 32..8191")
        if model_dir is not None:
            try:
                path = os.fspath(model_dir)
            except TypeError as exc:
                raise TranslationError(-1, "Model directory must be a path") from exc
            if not isinstance(path,str) or len(path)>4096 or len(os.fsencode(path))>4096 or "\0" in path:
                raise TranslationError(-1,"Model directory must be a path of at most 4096 bytes without NUL")
        self.model_dir = resolve_model_dir(model_dir)
        if library is None:
            self._lib = _matched_library()
        else:
            load_runtime_library()
            self._lib = C.CDLL(str(Path(library).expanduser().resolve(strict=True)))
        signatures = {
            "hy_mt2_create": ([C.c_char_p, C.POINTER(Options)], C.c_void_p),
            "hy_mt2_destroy": ([C.c_void_p], None),
            "hy_mt2_destroy_owned": ([C.POINTER(C.c_void_p)], C.c_int),
            "hy_mt2_create_error": ([], C.c_char_p),
            "hy_mt2_create_error_code": ([], C.c_int),
            "hy_mt2_last_error": ([C.c_void_p], C.c_char_p),
            "hy_mt2_count_prompt_tokens": ([C.c_void_p, C.c_char_p, C.c_char_p, C.c_char_p], C.c_int),
            "hy_mt2_start": ([C.c_void_p, C.c_char_p, C.c_char_p, C.c_char_p], C.c_int),
            "hy_mt2_generate": ([C.c_void_p, NOTIFY, C.c_void_p], C.c_int),
            "hy_mt2_read_text": ([C.c_void_p, C.c_void_p, C.c_size_t], C.c_int),
            "hy_mt2_abort": ([C.c_void_p], C.c_int),
            "hy_mt2_get_stats": ([C.c_void_p, C.POINTER(Stats)], C.c_int),
            "hy_mt2_get_info": ([C.c_void_p, C.c_void_p, C.c_size_t], C.c_int),
        }
        for name, (args, result) in signatures.items():
            f = getattr(self._lib, name)
            f.argtypes, f.restype = args, result
        if runtime is not None and not isinstance(runtime, _runtime.Runtime):
            raise TypeError("runtime must be this provider's Runtime")
        self.runtime = runtime
        create = self._lib.hy_mt2_create_with_runtime
        create.argtypes = [C.c_char_p, C.POINTER(Options), C.c_void_p, C.POINTER(C.c_void_p)]
        create.restype = C.c_int
        options = Options(C.sizeof(Options), max_input_tokens)
        directory = str(self.model_dir).encode()
        try:
            if runtime is None:
                create(directory, C.byref(options), None, C.byref(self._engine_slot))
            else:
                # Check the process before taking a lock that could have been inherited.
                with runtime.borrow_handle() as handle:
                    create(directory, C.byref(options), handle, C.byref(self._engine_slot))
            self._handle = self._engine_slot.value
            if not self._handle:
                raise TranslationError(
                    self._lib.hy_mt2_create_error_code(), self._lib.hy_mt2_create_error().decode("utf-8", "replace")
                )
        except BaseException:
            self._handle = self._engine_slot.value
            if self._handle:
                self.close()
            raise

    def _check_process(self):
        if os.getpid() != self._pid:
            raise TranslationError(-4,"Model inherited through fork; initialize after spawn/exec")

    @staticmethod
    def _translation_bytes(text, source, target):
        values=[]
        for name,value,limit in (("Text",text,16000),("Source",source,9),("Target",target,9)):
            if not isinstance(value,str) or len(value)>limit or "\0" in value:
                raise TranslationError(-1,name+" must be a bounded string without NUL")
            try: encoded=value.encode("utf-8")
            except UnicodeError as exc: raise TranslationError(-1,name+" must be UTF-8") from exc
            if len(encoded)>limit: raise TranslationError(-1,name+" exceeds byte limit")
            values.append(encoded)
        return values

    def _check(self, result):
        self._check_process()
        if result < 0:
            raise TranslationError(result, self._lib.hy_mt2_last_error(self._handle).decode("utf-8", "replace"))
        return result

    @property
    def _info(self):
        self._check_process()
        size = self._check(self._lib.hy_mt2_get_info(self._handle, None, 0))
        buf = C.create_string_buffer(size)
        self._check(self._lib.hy_mt2_get_info(self._handle, buf, size))
        return json.loads(buf.value)

    @property
    def _stats(self):
        self._check_process()
        stats = Stats()
        stats.struct_size = C.sizeof(Stats)
        self._check(self._lib.hy_mt2_get_stats(self._handle, C.byref(stats)))
        return {name: getattr(stats, name) for name, _ in Stats._fields_ if name != "struct_size"}

    def _count_prompt_tokens(self, text, source, target):
        """Count the SDK's full prompt without preparing or running inference."""
        self._check_process()
        if not self._handle or self._translating:
            raise TranslationError(-4, "Translator must be open and idle")
        payload=self._translation_bytes(text,source,target)
        return self._check(self._lib.hy_mt2_count_prompt_tokens(self._handle,*payload))

    def _translate(self, text, source, target, on_chunk=None):
        self._check_process()
        if not self._handle:
            raise TranslationError(-4, "Translator is closed")
        if self._translating:
            raise TranslationError(-4, "Translation already active")
        payload=self._translation_bytes(text,source,target)
        self._translating = True
        try:
            self._check(self._lib.hy_mt2_start(self._handle,*payload))
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            chunks, errors = [], []
            buf = C.create_string_buffer(257)

            def drain(_):
                try:
                    while True:
                        n = self._check(self._lib.hy_mt2_read_text(self._handle, buf, len(buf)))
                        if not n:
                            break
                        chunk = decoder.decode(buf.raw[:n])
                        if chunk:
                            chunks.append(chunk)
                            if on_chunk and not errors:
                                on_chunk(chunk)
                except Exception as exc:
                    errors.append(exc)

            callback = NOTIFY(drain)
            result = self._lib.hy_mt2_generate(self._handle, callback, None)
            drain(None)
            tail = decoder.decode(b"", final=result != -6)
            if tail:
                chunks.append(tail)
                if on_chunk:
                    on_chunk(tail)
            if errors:
                raise errors[0]
            if result != -6:
                self._check(result)
            return {"text": "".join(chunks), "cancelled": result == -6, "stats": self._stats}
        finally:
            self._translating = False

    def _abort(self):
        self._check_process()
        if self._handle:
            self._check(self._lib.hy_mt2_abort(self._handle))

    def close(self):
        self._check_process()
        if self._translating:
            raise TranslationError(-4, "Wait for translate to finish before close")
        try:
            self._check(self._lib.hy_mt2_destroy_owned(C.byref(self._engine_slot)))
        finally:
            # The native slot is authoritative if a Python handler interrupts return.
            self._handle=self._engine_slot.value

    def __enter__(self):
        self._check_process()
        return self

    def __exit__(self, *_):
        self.close()


# Preserve the names previously importable from this module.
from ._generation import (
    GenerationResult as GenerationResult,
    GenerationUpdate as GenerationUpdate,
    GenerationCapabilities as GenerationCapabilities,
    GenerationError as GenerationError,
    InputError as InputError,
    UnsupportedFeatureError as UnsupportedFeatureError,
    BusyError as BusyError,
    ClosedError as ClosedError,
    InferenceError as InferenceError,
)
from ._lm import install_llm_api
LanguageModel = install_llm_api(_NativeModel, NOTIFY)
