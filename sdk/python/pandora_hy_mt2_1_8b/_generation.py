"""Text-generation API primitives; no tokenizer or tensor dependency."""
from __future__ import annotations
from dataclasses import dataclass
import math
import os
import threading
from types import MappingProxyType



class GenerationError(RuntimeError):
    def __init__(self, message, *, native_code=None, operation=None):
        super().__init__(message)
        self.native_code = native_code
        self.operation = operation


class InputError(GenerationError, ValueError):
    pass


class UnsupportedFeatureError(GenerationError):
    pass


class BusyError(GenerationError):
    pass


class ClosedError(GenerationError):
    pass


class InferenceError(GenerationError):
    pass


@dataclass(frozen=True)
class GenerationResult:
    text: str
    finish_reason: str
    audio: None = None

    @property
    def is_complete(self):
        return self.finish_reason == "stop"


@dataclass(frozen=True)
class GenerationUpdate:
    text: str
    delta: str
    finish_reason: str | None = None

    @property
    def is_final(self):
        return self.finish_reason is not None


@dataclass(frozen=True)
class GenerationCapabilities:
    input_types: tuple
    message_roles: tuple
    streaming: bool
    generation_parameters: tuple
    output_types: tuple = ("text",)
    audio_output: bool = False
    cross_turn_cache: bool = False
    conversation_history: bool = False
    max_concurrent_requests: int = 1
    max_instances_per_process: int = 1


def prepare_request(prompt, messages, parameters, supported):
    if (prompt is None) == (messages is None):
        raise InputError("Provide exactly one of prompt or messages")
    if prompt is not None:
        messages = [{"role": "user", "content": prompt}]
    if not isinstance(messages, (list, tuple)) or not messages:
        raise InputError("messages must be a nonempty list or tuple")
    if len(messages)>128: raise InputError("At most 128 messages are allowed")
    if len(messages) > 2 or any(isinstance(m, dict) and m.get("role") == "assistant" for m in messages):
        raise UnsupportedFeatureError("Translation accepts one user message with optional system instructions; no conversation history")
    copied, previous, content_bytes = [], None, 0
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise InputError("Each message requires only role and content")
        role, content = message["role"], message["content"]
        if not isinstance(role, str) or len(role)>9:
            raise InputError("Message role must be a string")
        if role not in ("system", "user", "assistant"):
            raise UnsupportedFeatureError(f"Unsupported message role: {role}")
        if isinstance(content, list):
            if len(content) > 128:
                raise InputError("At most 128 ordered text entries are supported")
            values = []
            characters = 0
            for item in content:
                if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                    raise InputError("Each content entry requires a type")
                if item["type"] != "text":
                    raise UnsupportedFeatureError("This translation model supports text only")
                if set(item) != {"type", "text"} or not isinstance(item["text"], str):
                    raise InputError("A text entry requires only type and string text")
                characters += len(item["text"])
                if characters > 65536:
                    raise InputError("Message content exceeds the bounded text budget")
                values.append(item["text"])
            content = "".join(values)
        if not isinstance(content, str) or len(content)>65536:
            raise InputError("Message content exceeds 65536 aggregate UTF-8 bytes")
        if not content.strip() or "\0" in content:
            raise InputError("Message content must be nonempty text without NUL")
        try:
            content_bytes+=len(content.encode("utf-8"))
            if content_bytes>65536: raise InputError("Message content exceeds 65536 aggregate UTF-8 bytes")
        except UnicodeError as exc:
            raise InputError("Message content must be valid UTF-8") from exc
        if "<｜" in content or "<|im_" in content:
            raise InputError("Model control markers must not occur in message content")
        if role == "system":
            valid = index == 0
        elif role == "user":
            valid = previous in (None, "system", "assistant")
        else:
            valid = previous == "user"
        if not valid:
            raise InputError("Expected optional system then alternating user/assistant messages")
        copied.append({"role": role, "content": content})
        previous = role
    if previous != "user":
        raise InputError("Last message must be user")
    explicit = {k: v for k, v in parameters.items() if v is not None}
    for key, value in explicit.items():
        if key == "do_sample":
            valid = isinstance(value, bool)
        elif key in ("max_new_tokens", "top_k"):
            valid = isinstance(value, int) and not isinstance(value, bool) and (1 if key == "max_new_tokens" else 0) <= value <= 2147483647
        else:
            try:
                valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
            except OverflowError:
                valid = False
            if key == "top_p":
                valid = valid and value <= 1
        if not valid:
            raise InputError(f"Invalid {key}")
    # The native request validator also checks the loaded model defaults.
    greedy = explicit.get("do_sample") is False or explicit.get("top_k") == 1
    if greedy and any(k in explicit for k in ("temperature", "top_p", "top_k")):
        raise InputError("Explicit sampling parameters conflict with effective greedy decoding")
    missing = set(explicit) - set(supported)
    if missing:
        raise UnsupportedFeatureError("Runtime cannot override: " + ", ".join(sorted(missing)))
    return {"messages": copied, **explicit}


class GenerationStream:
    """An owned request. Use with, especially when leaving iteration early."""
    def __init__(self, model, request):
        self._pid=os.getpid()
        self._model, self._request = model, request
        self._iterator = None
        self._cancel = threading.Event()
        self._closed = False
        self._result = None
        self._error = None
        self._iterating = threading.Lock()

    def _check_process(self):
        if self._pid!=os.getpid(): raise InferenceError("Stream inherited through fork; use spawn/exec",native_code=-4)

    def __enter__(self):
        self._check_process()
        if self._closed:
            raise ClosedError("Generation stream is closed")
        return self

    def __exit__(self, *_):
        self.close()

    def __iter__(self):
        return self

    def _advance(self):
        try:
            update = next(self._iterator)
        except StopIteration as exc:
            self._error = InferenceError("Generation ended without a final update")
            raise self._error from exc
        except BaseException as exc:
            self._error = exc
            raise
        if update.is_final:
            self._result = GenerationResult(update.text, update.finish_reason)
        return update

    def __next__(self):
        self._check_process()
        if not self._iterating.acquire(blocking=False):
            raise BusyError("Stream iteration is already active")
        try:
            if self._closed or self._result is not None or self._error is not None:
                raise StopIteration
            if self._iterator is None:
                self._iterator = self._model._iterate(self._request, self._cancel)
            return self._advance()
        finally:
            self._iterating.release()

    @property
    def result(self):
        self._check_process()
        if self._error is not None:
            raise InferenceError("Generation failed; no final result") from self._error
        if self._result is None:
            raise BusyError("Generation has no final result")
        return self._result

    def close(self):
        self._check_process()
        if not self._iterating.acquire(blocking=False):
            raise BusyError("Wait for active stream iteration before close")
        try:
            if self._closed:
                return
            iterator = self._iterator
            try:
                if iterator is not None:
                    self._cancel.set()
                    # Keep reading queued text and let the native terminal state decide
                    # whether the cancellation request arrived in time.
                    while self._result is None and self._error is None:
                        self._advance()
            finally:
                try:
                    if iterator is not None:
                        iterator.close()
                finally:
                    self._closed = True
                    with self._model._request_lock:
                        self._model._active = None
                    self._iterator = None
                    self._request = None
                    self._model = None
        finally:
            self._iterating.release()


class GenerationModelMixin:
    @classmethod
    def from_pretrained(cls, model_dir, *, runtime=None):
        return cls(model_dir, runtime=runtime)

    def _check_process(self):
        if self._pid!=os.getpid(): raise InferenceError("Model inherited through fork; use spawn/exec",native_code=-4)

    def _initialize_generation(self, capabilities, defaults):
        self._pid=os.getpid()
        self._active = None
        self._request_lock = threading.Lock()
        self._failed = False
        self._capabilities = capabilities
        self._generation_config = MappingProxyType(dict(defaults))

    @property
    def capabilities(self):
        self._check_process()
        return self._capabilities

    @property
    def generation_config(self):
        self._check_process()
        return self._generation_config

    def _check_idle(self):
        if not self._handle:
            raise ClosedError("Model is closed")
        if self._failed:
            raise InferenceError("Model failed; close and recreate it")
        if self._active is not None:
            raise BusyError("Close the active request before starting another")

    def generate_stream(self, messages, *, max_new_tokens=None,
                        do_sample=None, temperature=None, top_p=None, top_k=None,
                        repetition_penalty=None, return_audio=False):
        self._check_process()
        if type(return_audio) is not bool:
            raise InputError("return_audio must be boolean")
        if return_audio:
            raise UnsupportedFeatureError("Translation supports text only, without audio output")
        parameters = dict(max_new_tokens=max_new_tokens, do_sample=do_sample,
                          temperature=temperature, top_p=top_p, top_k=top_k,
                          repetition_penalty=repetition_penalty)
        with self._request_lock:
            self._check_idle()
            request = prepare_request(None, messages, parameters, self.capabilities.generation_parameters)
            self._validate_request(request)
            stream = GenerationStream(self, request)
            self._active = stream
            return stream

    def generate(self, messages, *, max_new_tokens=None,
                 do_sample=None, temperature=None, top_p=None, top_k=None,
                 repetition_penalty=None, return_audio=False):
        with self.generate_stream(messages, max_new_tokens=max_new_tokens,
                                 do_sample=do_sample, temperature=temperature, top_p=top_p,
                                 top_k=top_k, repetition_penalty=repetition_penalty, return_audio=return_audio) as stream:
            for _ in stream:
                pass
            return stream.result
