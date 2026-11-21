# Hy-MT2-1.8B

<p align="center">
  <a href="https://huggingface.co/APLUX-Pandora/Hy-MT2-1.8B"><img src="https://img.shields.io/badge/Hugging%20Face-HY--MT2--1.8B-E3B800?style=for-the-badge&amp;logo=huggingface&amp;logoColor=FFD21E&amp;labelColor=555555" alt="Hugging Face: Hy-MT2-1.8B"></a>
  <a href="https://github.com/APLUX-Pandora/hy-mt2-1.8b-demo"><img src="https://img.shields.io/badge/GitHub-HY--MT2--1.8B-000000?style=for-the-badge&amp;logo=github&amp;logoColor=white&amp;labelColor=555555" alt="GitHub: Hy-MT2-1.8B"></a>
</p>

Translate short text and documents between nine languages on compatible Qualcomm devices. Each translation request is independent.

Based on [Hy-MT2-1.8B](https://huggingface.co/tencent/Hy-MT2-1.8B).

**Demo recording:** reserved for a post-release recording.

<a id="install"></a>
## 1. Install

Clone the Demo and enter its root directory:

```bash
git clone https://github.com/APLUX-Pandora/hy-mt2-1.8b-demo.git
cd hy-mt2-1.8b-demo
```

### Prepare the device

Use a compatible Linux device with Aidlux LMS and the required drivers, DSP firmware and BSP/FastRPC support. The SDK includes its QNN runtime libraries; no separate QNN installation or path configuration is required.

Check the activation:

```bash
sudo lms check
```

Continue only when it returns true.

See [device prerequisites](sdk/environment.md) for required system libraries.

### Install the Demo and SDK

Use Python 3.10–3.12. Create and activate the Demo environment, then install:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

This installs the SDK, the Web Demo and the Hugging Face CLI. To use only the SDK in your own application, run `python -m pip install ./sdk` in that application's environment.

The checkout includes a prebuilt native library. Installation checks the bundled files, and the SDK checks the native library version and Runtime ABI when loading the model.

<a id="download-one-target"></a>
## 2. Get the model

Download the shared resources and the target for your device. This example uses QCS8625:

```bash
hf download APLUX-Pandora/Hy-MT2-1.8B --local-dir models --exclude "targets/*" --exclude "media/*" --exclude README.md --exclude .gitattributes
hf download APLUX-Pandora/Hy-MT2-1.8B --local-dir models --include "targets/qcs8625_qnn248/*"
```

For a private repository, run `hf auth login` first. Available targets and the folder layout are in [Model setup](docs/MODEL_SETUP.md).

Verify the downloaded model package before use:

```bash
python demo/prepare_models.py models
```

<a id="use"></a>
## 3. Run the Web Demo

```bash
bash demo/run.sh --port 51106
```

Open `http://<device-ip>:51106/` and choose languages, enter text and select **Translate**. Stop it with `Ctrl+C`. Use a trusted LAN. See the [Web Demo guide](demo/README.md).

## 4. Python Usage

In the same environment, from the Demo root:

**Chinese-related translation — use this template when either language is Chinese.**
Fill `target_language` with a Chinese name from the language table, such as `英语`.

The examples explicitly pass this Demo's translation preset. SDK omission/None instead uses max_new_tokens=256, do_sample=False, temperature=1.0, top_p=1.0, top_k=0 and repetition_penalty=1.0. The Demo uses an explicit 4096-token ceiling to preserve its EOS/context-bounded behavior; the total context and input limits still apply.

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

[Translation language names](sdk/PYTHON_API.md#translation-language-values) are used in the prompts. Review translations for names, facts and sentence intent.

More in the [Python API](sdk/PYTHON_API.md) and [examples](examples/README.md).

## Documentation

- [Model setup](docs/MODEL_SETUP.md): device requirements, targets, download and folder layout
- [Python API](sdk/PYTHON_API.md): every public class, method and parameter
- [C ABI](docs/C_ABI.md): native integration
- [Examples](examples/README.md): runnable Python and C examples
- [Python package](sdk/PYTHON_PACKAGE.md): SDK installation for your own projects
- [Runtime](sdk/RUNTIME_API.md): hardware settings and runtime status

## License

See [LICENSING.md](LICENSING.md), [NOTICE](NOTICE) and [LICENSES](LICENSES/).
