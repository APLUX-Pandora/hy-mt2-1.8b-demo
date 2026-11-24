# Python API

`pandora_hy_mt2_1_8b` loads local Hy-MT2-1.8B models for text translation.

## Quick start

Complete [SDK installation](README.md) and [model preparation](../docs/MODEL_SETUP.md). From the Demo repository root, activate the same environment with `source .venv/bin/activate`.

**Chinese-related translation — use this template when either language is Chinese.**
Fill `target_language` with a Chinese name from the language table, such as `英语`.

The examples explicitly pass this Demo's translation preset. Omitted sampling options use the loaded model package defaults. The SDK defaults to a 256-token output limit. The Demo uses an explicit 4096-token ceiling to preserve its EOS/context-bounded behavior; the total context and input limits still apply.

```python
from pandora_hy_mt2_1_8b import LanguageModel

target_language = "英语"
source_text = "会议明天上午九点半开始，请提前十分钟到达。"
prompt = (
    f"将以下文本翻译为{target_language}，"
    f"注意只需要输出翻译后的结果，不要额外解释：\n\n{source_text}"
)
messages = [{"role": "user", "content": prompt}]

with LanguageModel.from_pretrained("models") as model:
    result = model.generate(
        messages,
        max_new_tokens=4096,
        do_sample=True,
        temperature=0.7,
        top_p=0.6,
        top_k=20,
        repetition_penalty=1.05,
    )
    print(result.text)
```

**Translation between non-Chinese languages — use the English template.**
Fill `target_language` with an English name from the language table, such as `French`.
Use the same activated environment.

```python
from pandora_hy_mt2_1_8b import LanguageModel

target_language = "French"
source_text = "The meeting starts at nine thirty tomorrow morning. Please arrive ten minutes early."
prompt = (
    f"Translate the following text into {target_language}. "
    "Note that you should only output the translated result "
    f"without any additional explanation:\n\n{source_text}"
)
messages = [{"role": "user", "content": prompt}]

with LanguageModel.from_pretrained("models") as model:
    result = model.generate(
        messages,
        max_new_tokens=4096,
        do_sample=True,
        temperature=0.7,
        top_p=0.6,
        top_k=20,
        repetition_penalty=1.05,
    )
    print(result.text)
```

[Nine language values](#translation-language-values). Language codes identify the pair; put the corresponding full name into the translation instruction.

Each call uses only its supplied input. Translation can contain errors in names, facts or sentence intent; review the result for your use.

## API overview

| Entry / signature | Purpose | Return | Example |
| --- | --- | --- | --- |
| `LanguageModel.from_pretrained(model_dir, *, runtime=None)` | Load one local model package; also available as `LanguageModel(model_dir, *, runtime=None)` | Owned `LanguageModel` | [Chinese-related translation](../examples/python/translate_with_chinese.py) |
| `model.generate(messages, *, max_new_tokens=None, do_sample=None, temperature=None, top_p=None, top_k=None, repetition_penalty=None, return_audio=False)` | Generate text to completion | `GenerationResult` | Quick start |
| `model.generate_stream(messages, *, max_new_tokens=None, do_sample=None, temperature=None, top_p=None, top_k=None, repetition_penalty=None, return_audio=False)` | Create a lazy, owned text stream; generation starts on iteration | `GenerationStream` iterator/context manager | Streaming below |
| `model.capabilities` | Read supported inputs, outputs and generation controls | Frozen `GenerationCapabilities` | `print(model.capabilities)` after loading |
| `model.generation_config` | Read the loaded package sampler defaults and the SDK output token limit | Read-only mapping | `print(dict(model.generation_config))` after loading |
| `model.close()` | Close an idle model; also called by model context-manager exit | `None` | Quick start |
| `iter(stream)` / `next(stream)` | Receive Unicode updates, including one terminal update | `GenerationUpdate`; then StopIteration | Streaming below |
| `stream.result` | Read the final result after completion or cancellation of a started stream | `GenerationResult` | Streaming below |
| `stream.close()` | Cancel started work if necessary, join it and release the request owner; context-manager exit does the same | `None` | Early exit below |

Unknown generation keywords, including past_key_values, raise TypeError. No DynamicCache or cross-turn cache parameter is exported. No general parameter dictionary, seed argument, public tokenizer or raw prefix/cache API is provided.

## Parameters

### Loading

| Parameter | Type | Required / default | Values and restrictions | Unit |
| --- | --- | --- | --- | --- |
| `model_dir` | str, path-like or None | Required argument; None reads HY_MT2_MODELS | Explicit package root containing models.json, common files and exactly one complete target. None fails when HY_MT2_MODELS is unset. Empty/NUL paths or paths above 4096 UTF-8 bytes fail. | Path |
| `runtime` | this SDK's Runtime or None | Optional, None | None uses CPU default, burst, normal and device 0. An external Runtime is borrowed and must outlive its models. | None |

See [Runtime](RUNTIME_API.md) for hardware configuration and [model setup](../docs/MODEL_SETUP.md) for target names.

### Messages: both generation functions

| Parameter / field | Type | Required / default | Values and restrictions | Unit |
| --- | --- | --- | --- | --- |
| `messages` | list or tuple of dict | Required | Exactly one user message, optionally preceded by one system message. No assistant history, multiple user turns or media. | Ordered messages |
| `role` | str | Required per message | `system`: optional first instruction; `user`: final translation request. Neither None nor auto is supported. | None |
| `content` | str or list of text dict | Required per message | Nonblank UTF-8 text without NUL or model control markers. Text-list entries are concatenated in order without inserted separators. | Text |
| text-entry `type` | str | Required in a content list | `text` only | None |
| text-entry `text` | str | Required in a content list | Same content restrictions; at most 128 entries per list | Text |

Messages accept only role/content fields; text entries accept only type/text fields. Aggregate content is limited to 65536 UTF-8 bytes. The Python loader uses a fixed budget of 2048 rendered prompt tokens, including the BOS and template. It exposes no `max_input_tokens` argument. A rendered prompt above 2048 tokens raises `InputError` without truncation. The separate C API supports a configurable input budget through [`hy_mt2_options`](../docs/C_ABI.md). The configured model context has 8192 total positions for the rendered prompt (including BOS) and generated tokens. The effective output limit is the smaller of the requested new tokens and the remaining configured context. Successfully reaching that limit returns `length`. A backend rejection, including a provider context-limit error, raises `InferenceError`.

There is no SDK language enum or source/target argument: specify the target language in the user instruction. The [Web Demo](../demo/README.md) provides its own nine-language selection; it does not change the SDK signature. No system prompt is inserted automatically. Chinese-related directions use a Chinese translation instruction and Chinese language names; other directions use an English instruction and English language names. The two complete [translation examples](../examples/README.md) show both cases. Pass the instruction as user content; the SDK adds the HY chat delimiters, so do not insert model control tokens yourself.

### Translation language values

This Demo provides nine translation languages. The following values fill `target_language`
in the Usage templates and example scripts. Choose different source and target languages.
If either language is `zh`, use the Chinese template and the Chinese-template value;
otherwise use the English template and the English-template value. These full names are
instruction text, not an additional SDK enum or `language` keyword. Do not substitute the
short code for the full name. No `None` or `auto` language selection is provided.

| Code | Chinese-template value | English-template value |
| --- | --- | --- |
| `zh` | `中文` | `Chinese` |
| `en` | `英语` | `English` |
| `ja` | `日语` | `Japanese` |
| `ko` | `韩语` | `Korean` |
| `fr` | `法语` | `French` |
| `de` | `德语` | `German` |
| `es` | `西班牙语` | `Spanish` |
| `ar` | `阿拉伯语` | `Arabic` |
| `th` | `泰语` | `Thai` |

### Generation: shared by generate and generate_stream

| Parameter | Type | Required / omitted or None resolution | Legal values and restrictions | Unit |
| --- | --- | --- | --- | --- |
| max_new_tokens | int or None | Optional; **256** | 1..2147483647; upper bound on new output tokens. The native engine may apply a lower limit based on the remaining context. | Output tokens |
| do_sample | bool or None | Optional, package sampler | False selects greedy decoding. True enables sampling. | None |
| temperature | int/float or None | Optional, package sampler | Positive finite value, bool rejected; sampling only. | Dimensionless |
| top_p | int/float or None | Optional, package sampler | Finite (0,1]; 1 disables nucleus filtering; bool rejected. | Probability mass |
| top_k | int or None | Optional, package sampler | 0 disables filtering; 2..2147483647 selects candidates. Explicit 1 conflicts with the backend greedy strategy; use do_sample=False without sampling fields. | Candidate count |
| repetition_penalty | int/float or None | Optional, package sampler | Positive finite value; 1 disables penalty; bool rejected. | Dimensionless |
| `return_audio` | bool | Optional; **False** | False only. True raises UnsupportedFeatureError; None/non-bool raises InputError. | None |

Omitted values and `None` use the loaded package defaults on every request. Explicit options override those defaults for the current request. Temperature, top-p and top-k overrides require sampling to be enabled. Explicit greedy decoding selects one candidate. Explicit sampling with a packed top-k of 1 disables the candidate count filter when top-k is omitted. The Demo explicitly passes `max_new_tokens=4096`, `do_sample=True`, `temperature=0.7`, `top_p=0.6`, `top_k=20` and `repetition_penalty=1.05`. The sampler uses the model package seed. The model defines BOS, EOS, template, prefix, context and RoPE.

## Results and cleanup

| Object / field | Type / values | Meaning |
| --- | --- | --- |
| `GenerationResult.text` | str | Newly generated text |
| `GenerationResult.audio` | None | Text-only output |
| `GenerationResult.finish_reason` | `stop`, `length` or `cancelled` | Normal completion, reaching the effective output limit, or confirmed cancellation; backend/context failures raise errors rather than report success |
| `GenerationResult.is_complete` | bool | True only for stop |
| `GenerationUpdate.delta` | str | New Unicode text since the previous update; terminal delta can be empty |
| `GenerationUpdate.text` | str | Accumulated text |
| `GenerationUpdate.finish_reason` | None, stop, length or cancelled | None while running; one terminal update ends iteration |
| `GenerationUpdate.is_final` | bool | Whether finish_reason is present |

### Errors

| Exception | Meaning / action |
| --- | --- |
| `GenerationError` | Common base; native_code and operation preserve available native context, with Python exception chaining for causes |
| `InputError` | Invalid input, encoding, conflicting parameter or budget; correct input and retry |
| `UnsupportedFeatureError` | Requested capability or valid setting is unavailable |
| `BusyError` | A stream is owned/being iterated or result is not yet final; finish/close the relevant work first |
| `ClosedError` | Model or stream is closed |
| `InferenceError` | Loading/backend/generation failure; close the model and recreate it after resolving the cause |
| `RuntimeNativeError` | Runtime native failure with `code` (a PANDORA_RUNTIME_ERROR_* value); see Runtime reference |

These classes are exported from pandora_hy_mt2_1_8b. File-system/type errors can also propagate from model preparation. Models, streams and Runtime objects are process-local; do not inherit live objects through fork, use spawn/exec.

### Lifecycle

Reaching the effective output limit successfully returns `length`. Read `stream.result` after consuming the terminal update or closing a started stream. Closing requests cancellation if work is still in progress and waits for the native worker to finish. The result retains the text received through the actual terminal state, including a normal result that was already available at close. Closing before the first iteration produces no result. If inference fails during close, close propagates the error and `stream.result` raises `InferenceError`. Cached results remain readable after close.

```python
with model.generate_stream(
    messages,
    max_new_tokens=4096,
    do_sample=True,
    temperature=0.7,
    top_p=0.6,
    top_k=20,
    repetition_penalty=1.05,
) as stream:
    for update in stream:
        print(update.delta, end="", flush=True)
    result = stream.result
```

For early exit:
```python
with model.generate_stream(
    messages,
    max_new_tokens=4096,
    do_sample=True,
    temperature=0.7,
    top_p=0.6,
    top_k=20,
    repetition_penalty=1.05,
) as stream:
    for update in stream:
        print(update.delta, end="", flush=True)
        if len(update.text) >= 40:
            break
# A started stream has stopped before this point.
result = stream.result
```

Both fragments assume an already loaded model and messages prepared as above. Close completed streams too, before starting another request or closing the model. Only one model per process and one owned stream per model are supported. Do not concurrently iterate and close a stream: wait for the active iteration to return. Model.close raises BusyError while a stream is owned. Close streams, then models, then caller-owned Runtime. Close is idempotent after success; a native teardown error is not successful release or permission to reuse the model.

GenerationCapabilities exposes input_types=(text,), message_roles=(system,user), streaming=True, output_types=(text,), audio_output=False, cross_turn_cache=False, conversation_history=False, max_concurrent_requests=1 and max_instances_per_process=1. generation_parameters lists the six supported generation controls in the table above.

## Advanced

[Runtime](RUNTIME_API.md) documents CpuOptions, QnnOptions and status queries. [Examples](../examples/README.md) lists all runnable Python/C entry points. [C ABI](../docs/C_ABI.md) documents native integration. Internal underscore modules, Web helpers and diagnostics are outside the public model SDK API.
