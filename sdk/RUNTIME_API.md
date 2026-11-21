# Pandora Runtime Python API v1

Runtime configures CPU affinity, QNN performance mode, QNN priority and the NPU device. Import `Runtime`, `CpuOptions`, and `QnnOptions` from the model SDK. Pass the configuration as `runtime=` when loading the model. Omit the argument or pass `None` to let the SDK create and manage the default Runtime, using CPU affinity `"default"`, burst performance, normal priority and device 0. `Runtime()` and `CpuOptions()` also select `"default"`; select `"inherit"` explicitly to follow host placement. Backend configuration is managed by the SDK; users do not prepare Genie or HTP configuration files.

## Configuration

| Option | Default | Values |
| --- | --- | --- |
| `CpuOptions.affinity` | `"default"` | `"inherit"` follows the allowed CPUs of the thread that loads the model. `"default"` selects the SDK's recommended placement for the platform. You can also pass a nonempty collection of CPU IDs, such as `[3, 4]`, from the process's allowed set. |
| `QnnOptions.performance_mode` | `"burst"` | See the performance modes below. |
| `QnnOptions.priority` | `"normal"` | `"low"`, `"normal"`, `"normal_high"`, and `"high"`, in ascending order. |
| `QnnOptions.device_id` | `0` | An NPU device ID from 0 to 2³²−1. The ID must be available on the target device. Unavailable IDs return an error. |

Active RPC control latency defaults internally to 100 microseconds. RPC polling and low-level voltage/DCVS/sleep settings are SDK-managed backend presets, not additional required user parameters. The common baseline is burst; adding power-saving modes is not required. Any additional supported modes and legacy overrides depend on the actual SDK version and platform.

| Performance mode | Values |
| --- | --- |
| Performance | `"burst"`, `"sustained_high_performance"`, `"high_performance"` |
| Balanced | `"balanced"`, `"low_balanced"` |
| Power saving | `"high_power_saver"`, `"power_saver"`, `"low_power_saver"`, `"extreme_power_saver"` |
| System managed | `"system_settings"` lets the system manage performance settings. |

Available QNN settings depend on the model and platform. See [Runtime support](#runtime-support) for this SDK's supported values. By default, the SDK raises an error when you request an unsupported setting.

### Runtime support

Hy-MT2 supports these Runtime settings:

- `QnnOptions.performance_mode`: `"burst"` only.
- `QnnOptions.priority`: `"normal"` only.
- `QnnOptions.device_id`: an explicit NPU device ID available on the target. The default is `0`.
- `CpuOptions.affinity`: `"default"`, `"inherit"`, or a nonempty list of allowed CPU IDs.
- RPC control latency and polling use SDK-managed settings. User overrides are unsupported.

## Python usage

Create the Runtime, pass it to the model loader, and release both objects explicitly. For packages with SoC/QNN variants, follow the model's download instructions to select the resources for your device. Pass the local model directory and the Runtime to the loader. The model loader and inference call depend on the SDK.

<!-- BEGIN PANDORA RUNTIME USAGE -->
After [SDK/model preparation](README.md), from the repository root in the same activated .venv:
```python
from pandora_hy_mt2_1_8b import LanguageModel, Runtime, CpuOptions, QnnOptions

runtime = Runtime(cpu=CpuOptions(affinity="default"), qnn=QnnOptions(device_id=0))
try:
    with LanguageModel.from_pretrained("models", runtime=runtime) as model:
        print(model.generate(
            [{"role": "user", "content": "将以下文本翻译为中文，注意只需要输出翻译后的结果，不要额外解释：\n\nHello."}],
            max_new_tokens=4096,
            do_sample=True,
            temperature=0.7,
            top_p=0.6,
            top_k=20,
            repetition_penalty=1.05,
        ).text)
        print(runtime.status())
finally:
    runtime.close()
```

See [model-specific Runtime settings](#runtime-support) for supported settings.
<!-- END PANDORA RUNTIME USAGE -->

Configuration is fixed for the lifetime of a Runtime. Create a new Runtime to use different settings. When your application creates the Runtime, finish any in-flight inference and close streams or caches first, then close the attached models and finally the Runtime. Runtime and model objects also support context managers. Each process creates its own Runtime from the model SDK it uses.

Choose another available NPU with `QnnOptions(device_id=1)` inside `Runtime(qnn=...)`; device_id is not a top-level Runtime argument. Parameter type/range checks happen at construction, while device availability may be checked at first model load for lazy initialization. A bool, float, negative or out-of-range value is invalid. Changing devices requires a new Runtime and model; there is no live context migration. The execution device and its power client must match. CPU placement and model SoC/QNN resource selection remain separate. Unsupported fields or mismatched native libraries must not be silently ignored; use the model SDK's stated supported interface/version.


The native Runtime selects default CPU placement from the detected platform and its hardware CPU count. The full configured set must be present, online and allowed by the process affinity. An unreadable hardware profile or an unsupported CPU count for a known platform returns an error. Python, C and Web use the same defaults. Explicit inherit and CPU collections
retain their semantics. Configuration identity, detected hardware count, selected
mask and observed thread masks are distinct state fields. In CPU status,
`backend_cpu_mask` is the value submitted in the backend configuration.
`backend_cpu_mask_read_back` indicates whether the backend confirmed the value.
