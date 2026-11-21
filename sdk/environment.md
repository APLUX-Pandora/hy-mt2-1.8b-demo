# Runtime environment

The SDK requires Linux AArch64, Python 3.10–3.12, compatible device BSP/drivers, FastRPC and DSP firmware, LMS and basic C/C++ libraries. Its Genie engine and QNN runtime libraries are included. No separate QNN installation or QNN path configuration is required.

The device must provide libaidlms.so, its supported activation, libcdsprpc and the firmware/basic ABI required by the device BSP. The SDK does not install or replace the BSP, drivers, firmware or LMS. Do not remove shared system libraries.

[SDK installation](README.md) provides the LMS precheck and ordinary pip installation. [Model setup](../docs/MODEL_SETUP.md) maps compatible SoC resources. The venv does not isolate NPU devices or ports. From the repository root, ldd sdk/lib/libhy_mt2.so checks ordinary linker dependencies; successful model loading additionally checks the package-local runtime and device compatibility.

Model files use the AIDEM format and are loaded automatically by the matching SDK. Keep the ordinary tokenizer, embedding and prefix resources with the selected target.

Close streams before models, and models before external Runtime objects. A reported teardown failure is not successful release; resolve it before reuse. Hardware configuration and observable status limits are described in [Runtime](RUNTIME_API.md).
