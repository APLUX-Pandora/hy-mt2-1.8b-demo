# Python SDK installation

Follow the [SDK installation](README.md#install) from the Demo root in a dedicated Python environment. This installs pandora-hy-mt2-1-8b, imported as pandora_hy_mt2_1_8b. The Linux AArch64 wheel includes the prebuilt libhy_mt2.so, its QNN user-space runtime libraries and license files. It does not compile at installation or download weights. Compatible device BSP, FastRPC/DSP firmware and LMS remain required. No separate QNN installation or QNN path configuration is required. The installation uses the bundled Pandora Runtime wheel for hardware settings.

After installation, use the [public Python API](PYTHON_API.md) from your own project without PYTHONPATH or repository imports. Pass a local single-target model directory. Python3.10/3.11/3.12 are the supported interpreter versions.
