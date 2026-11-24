# Hy-MT2-1.8B SDK

Load a local Hy-MT2-1.8B model and translate text from Python or C.

## What's included

The Python package path is relative to the installed environment. `SHA256SUMS` covers the bundled native library, QNN runtime files and shared Runtime interfaces.

| Path | Content |
| --- | --- |
| `pandora_hy_mt2_1_8b/` | Python package (`from pandora_hy_mt2_1_8b import LanguageModel`) |
| `include/` | C header |
| `lib/` | Prebuilt native library with its QNN runtime |
| `SHA256SUMS` | Checksums of the shipped files |

## Install

In your application's activated Python 3.10–3.12 environment, from the Demo root:

```bash
python -m pip install sdk/wheels/pandora_runtime-*.whl
python -m pip install ./sdk
```

The device must pass `sudo lms check`. The SDK does not install LMS or drivers and does not download models; see [Get the model](../README.md#2-get-the-model).

## Usage

After [model setup](../docs/MODEL_SETUP.md), run from the Demo root in the same environment.

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

## Documentation

- [Python API](PYTHON_API.md)
- [C ABI](../docs/C_ABI.md)
- [Examples](../examples/README.md)
- [Runtime](RUNTIME_API.md)
- [Python package](PYTHON_PACKAGE.md)
- [Licensing](../LICENSING.md)
