"""HY adapter for the Pandora simplified LLM API."""
import codecs
import ctypes as C
import json
import queue
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from time import monotonic

from ._generation import (GenerationModelMixin, GenerationCapabilities,
    GenerationUpdate, InputError, UnsupportedFeatureError, BusyError,
    InferenceError)


def install_llm_api(native_class, notify_type):
    class LanguageModel(GenerationModelMixin, native_class):
        def __init__(self, model_dir, *, runtime=None):
            max_input_tokens = 2048
            if isinstance(max_input_tokens, bool) or not isinstance(max_input_tokens, int) or not 32 <= max_input_tokens <= 8191:
                raise InputError("max_input_tokens must be an integer in 32..8191")
            try:
                super().__init__(model_dir, max_input_tokens=max_input_tokens, runtime=runtime)
            except (InputError, UnsupportedFeatureError):
                raise
            except (OSError, RuntimeError) as exc:
                code = getattr(exc, "code", None)
                kind = {-1: InputError, -7: UnsupportedFeatureError}.get(code, InferenceError)
                raise kind(str(exc), native_code=code, operation="from_pretrained") from exc
            try:
                for name in ("start_messages", "count_messages"):
                    fn = getattr(self._lib, "hy_mt2_" + name)
                    fn.argtypes, fn.restype = [C.c_void_p, C.c_char_p], C.c_int
                self._lib.hy_mt2_get_result.argtypes = [C.c_void_p, C.c_void_p, C.c_size_t]
                self._lib.hy_mt2_get_result.restype = C.c_int
                info = self._info
                defaults = info.get("generation_defaults")
                parameters = tuple(info["supported_generation_parameters"])
                if not isinstance(defaults, dict) or defaults.keys() != set(parameters):
                    raise UnsupportedFeatureError("Native library did not report model generation defaults")
                self._max_input_tokens = info["max_input_tokens"]
                self._initialize_generation(GenerationCapabilities(
                    ("text",), ("system", "user"), True,
                    parameters), defaults)
            except BaseException as exc:
                native_class.close(self)
                if isinstance(exc, AttributeError):
                    raise UnsupportedFeatureError('LanguageModel requires the candidate0.3 native API', operation='from_pretrained') from exc
                raise

        def _native_check(self, code, operation):
            if code >= 0:
                return code
            message = self._lib.hy_mt2_last_error(self._handle).decode("utf-8", "replace")
            kind = {-1: InputError, -4: BusyError, -7: UnsupportedFeatureError}.get(code, InferenceError)
            raise kind(message, native_code=code, operation=operation)

        def _validate_request(self, request):
            payload = json.dumps(request, ensure_ascii=False).encode()
            if len(payload)>524288: raise InputError("Request JSON exceeds 524288 bytes")
            count = self._native_check(self._lib.hy_mt2_count_messages(self._handle, payload), "count_messages")
            if count > self._max_input_tokens:
                raise InputError("Request exceeds model input token budget")

        def _count_messages(self, messages):
            self._check_process()
            from ._generation import prepare_request
            with self._request_lock:
                self._check_idle()
                request = prepare_request(None, messages, {}, ())
                return self._native_check(self._lib.hy_mt2_count_messages(
                    self._handle, json.dumps(request, ensure_ascii=False).encode()), "count_messages")

        def _iterate(self, request, cancel):
            output, errors, done = queue.Queue(maxsize=16), [], threading.Event()
            decoder = codecs.getincrementaldecoder("utf-8")("strict")
            abandoned, entered = threading.Event(), threading.Event()
            text = ""

            def publish(chunk):
                while not abandoned.is_set():
                    try:
                        output.put(chunk, timeout=0.05)
                        return
                    except queue.Full:
                        pass

            def drain(_):
                try:
                    buffer = C.create_string_buffer(4096)
                    while True:
                        count = self._native_check(self._lib.hy_mt2_read_text(self._handle, buffer, len(buffer)), "read_text")
                        if not count:
                            break
                        chunk = decoder.decode(buffer.raw[:count])
                        if chunk:
                            publish(chunk)
                except BaseException as exc:
                    errors.append(exc)
                    cancel.set()

            def terminal_reason():
                size = self._native_check(self._lib.hy_mt2_get_result(self._handle, None, 0), "get_result")
                buf = C.create_string_buffer(size)
                self._native_check(self._lib.hy_mt2_get_result(self._handle, buf, size), "get_result")
                return json.loads(buf.value)["finish_reason"]

            def work():
                try:
                    entered.set()
                    if abandoned.is_set():
                        return
                    callback = notify_type(drain)
                    code = self._lib.hy_mt2_generate(self._handle, callback, None)
                    drain(None)
                    # Older native builds return STATE if abort won before generate.
                    cancelled = code == -6 or (code == -4 and terminal_reason() == "cancelled")
                    if not cancelled:
                        self._native_check(code, "generate")
                    tail = decoder.decode(b"", final=not cancelled)
                    if tail:
                        publish(tail)
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    done.set()
                    # Wake a reader waiting for more text as soon as the worker exits.
                    publish(None)

            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="hy-mt2-generation") as executor:
                # Complete thread startup before native request ownership can pass to it.
                executor.submit(lambda: None).result()
                try:
                    self._native_check(self._lib.hy_mt2_start_messages(
                        self._handle, json.dumps(request, ensure_ascii=False).encode()), "start_messages")
                    executor.submit(work)
                    next_abort = 0.0
                    while True:
                        if cancel.is_set() and not done.is_set() and monotonic() >= next_abort:
                            self._native_check(self._lib.hy_mt2_abort(self._handle), "abort")
                            next_abort = monotonic() + 0.05
                        try:
                            delta = output.get(timeout=0.05)
                        except queue.Empty:
                            continue
                        if delta is None:
                            break
                        text += delta
                        yield GenerationUpdate(text, delta)
                    if errors:
                        self._failed = True
                        if isinstance(errors[0], (InputError, UnsupportedFeatureError, BusyError, InferenceError)):
                            raise errors[0]
                        raise InferenceError(str(errors[0]), operation='generate') from errors[0]
                    reason = terminal_reason()
                    if reason not in ("stop", "length", "cancelled"):
                        raise InferenceError("Runtime did not provide a terminal state")
                    yield GenerationUpdate(text, "", reason)
                finally:
                    original = sys.exc_info()[1]
                    abandoned.set()
                    cleanup_error = None
                    while not done.is_set():
                        try:
                            # Abort even when submission was interrupted before work entered.
                            self._native_check(self._lib.hy_mt2_abort(self._handle), "abort")
                        except BaseException as exc:
                            if cleanup_error is None:
                                cleanup_error = exc
                        if not entered.is_set():
                            break
                        try:
                            done.wait(0.05)
                        except KeyboardInterrupt as exc:
                            if cleanup_error is None:
                                cleanup_error = exc
                    if original is None and cleanup_error is not None:
                        raise cleanup_error

        def close(self):
            self._check_process()
            lock = getattr(self, "_request_lock", None)
            if lock is None:
                return native_class.close(self)
            with lock:
                if self._active is not None:
                    raise BusyError("Close the active generation stream before model.close()")
                native_class.close(self)

    LanguageModel.__name__ = "LanguageModel"
    LanguageModel.__qualname__ = "LanguageModel"
    LanguageModel.__module__ = "pandora_hy_mt2_1_8b"
    return LanguageModel
