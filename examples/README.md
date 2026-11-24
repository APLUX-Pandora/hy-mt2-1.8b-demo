# Examples

## Overview

| Example | What it shows |
| --- | --- |
| [python/translate_with_chinese.py](python/translate_with_chinese.py) | Chinese → English and English → Chinese using Chinese instructions |
| [python/translate_without_chinese.py](python/translate_without_chinese.py) | English → French using an English instruction |
| [c/translate.c](c/translate.c) | C translation using an output callback |

## Before you run

Complete [Install](../README.md#1-install) and [Get the model](../README.md#2-get-the-model). Run every command from the Demo root in the activated environment. Stop the Web Demo first; examples and the Web Demo share the NPU.

The Python scripts use the prepared `models` directory and source text in each script. They also accept the earlier `models/hy-mt2` layout when `models` does not contain a manifest.

## Python examples

### translate_with_chinese.py

Translate a short meeting announcement in both directions. Use a Chinese instruction if either language is Chinese.

```bash
python examples/python/translate_with_chinese.py
```

Output:

```text
There will be a meeting at 9:30 am tomorrow. Please arrive at the meeting room ten minutes in advance. After the meeting, we will send the discussion results to all colleagues.
会议明天上午九点半开始。请提前十分钟到达。我们会之后把讨论结果发送给所有同事。
```

### translate_without_chinese.py

Translate the same announcement from English to French. Use an English instruction for non-Chinese language pairs.

```bash
python examples/python/translate_without_chinese.py
```

Output:

```text
La réunion commence à neuf heures trente demain matin. Veuillez arriver dix minutes en avance. Nous transmettrons les résultats de la discussion à tous les collègues plus tard.
```

## C example

A C compiler is required.

Build against the headers and prebuilt library in `sdk/`:

### translate.c

```bash
runtime_dir=$(python -c "import pathlib,pandora_runtime; print(pathlib.Path(pandora_runtime.__file__).parent)")
cc -std=c99 -Wall -Wextra -Werror -I sdk/include examples/c/translate.c -L sdk/lib -L"$runtime_dir" -Wl,--no-as-needed -l:libpandora_runtime.so.5 -Wl,--as-needed -Wl,-rpath,"$runtime_dir" -lhy_mt2 -Wl,-rpath,'$ORIGIN/sdk/lib' -o translate_c
./translate_c models
```

Output:

```text
早上好。
```

## Reference

Use these nine language names in the scripts. In `translate_with_chinese.py`,
`TRANSLATIONS` pairs each Chinese target name with its source text. In
`translate_without_chinese.py`, fill `TARGET_LANGUAGE` with an English target name.
Source and target must differ. When either is `zh`, use the Chinese template;
otherwise use the English template. The names are prompt text, not SDK parameters.
No `None` or `auto` selection is provided.

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

The examples pass the Demo translation preset explicitly. See the [Python API](../sdk/PYTHON_API.md) for SDK defaults and the supported generation settings.
