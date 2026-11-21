# C ABI

The public headers are [hy_mt2.h](../sdk/include/hy_mt2.h) and [pandora_runtime.h](../sdk/include/pandora_runtime.h). C and Python use the same `libhy_mt2.so`.

## Build and link

From the Demo root, compile against the shipped header and library; the library carries its QNN runtime:

```bash
cc -std=c99 -Wall -Wextra -Werror -I sdk/include examples/c/translate.c -L sdk/lib -lhy_mt2 -Wl,-rpath,'$ORIGIN/sdk/lib' -o translate_c
./translate_c models
```

## Lifecycle

```text
create_with_runtime → start_messages → generate → read_text / get_result → destroy_owned
```

Each start creates a fresh translation request. Pass one user message with an optional preceding system message, plus the generation fields documented in the [Python API](../sdk/PYTHON_API.md). Fix input errors before retrying. A model that fails native teardown retains its owned handle and cannot be reused.

### Generation defaults and Demo preset

Omitted or null generation fields resolve per request to `max_new_tokens=256`, `do_sample=false`, `temperature=1.0`, `top_p=1.0`, `top_k=0` and `repetition_penalty=1.0`. Explicit sampling fields require `do_sample=true`. The Demo preset supplies all six fields explicitly, including a 4096-token ceiling.

`hy_mt2_options.max_input_tokens` defaults to 512 and accepts 32–8191 rendered prompt tokens, including BOS and the prompt template. Python uses a fixed budget of 2048. Input over the budget is rejected without truncation. The total configured context is 8192 positions. The effective output limit is the smaller of the requested new tokens and the remaining context. The terminal result reports `stop`, `length` or `cancelled`. A backend error returns a negative status.

## Functions

| Function | Purpose | Returns |
| --- | --- | --- |
| `hy_mt2_version`, `hy_mt2_default_options` | Query the library version and default model options | Borrowed string or options value |
| `hy_mt2_create`, `hy_mt2_create_with_runtime` | Load a local model, optionally with a caller-owned Runtime | Handle or NULL for `create`. Status and output handle for `create_with_runtime` |
| `hy_mt2_destroy_owned`, `hy_mt2_destroy` | Release the model. Prefer `destroy_owned` to receive teardown status and clear the slot on success | Status or void |
| `hy_mt2_create_error`, `hy_mt2_create_error_code`, `hy_mt2_last_error` | Read creation errors or the latest model error | Borrowed string or error code |
| `hy_mt2_start_messages`, `hy_mt2_count_messages` | Prepare a message JSON request or count its rendered prompt tokens | Status or token count. Negative on error |
| `hy_mt2_start`, `hy_mt2_count_prompt_tokens` | Compatibility entry points for text and language codes | Status or token count. Negative on error |
| `hy_mt2_generate`, `hy_mt2_abort` | Generate synchronously or request cancellation | Status |
| `hy_mt2_read_text` | Copy queued UTF-8 bytes into a caller buffer | Bytes read, zero if empty, or negative on error |
| `hy_mt2_get_result`, `hy_mt2_get_info` | Query terminal result or model and generation information as JSON | Status or required capacity including NUL when the buffer is too small |
| `hy_mt2_get_stats` | Read request state and counters | Status |
| `pandora_runtime_create`, `pandora_runtime_destroy` | Create or release a Runtime | Status |
| `pandora_runtime_last_error` | Read the latest Runtime error | Borrowed string |
| `pandora_runtime_get_status`, `pandora_runtime_get_capabilities`, `pandora_runtime_get_submission_status`, `pandora_runtime_get_device_status` | Query Runtime availability, capabilities, submission and device status | Status |
| `pandora_runtime_get_cpu_status`, `pandora_runtime_get_cpu_ids`, `pandora_runtime_get_cpu_thread`, `pandora_runtime_get_cpu_profile` | Query CPU status, IDs, thread affinity or profile | Status. Supply capacity for array or JSON output |

A null Runtime uses CPU default, burst performance, normal priority and device 0. Explicit CPU arrays are copied. Requested CPU IDs must be online and allowed. See the [Runtime reference](../sdk/RUNTIME_API.md) and the public header for configuration and query buffer sizes.

For `pandora_runtime_get_cpu_profile`, supply a writable buffer and its capacity in bytes, including room for the terminating NUL. The function returns 0 and writes a NUL-terminated JSON string on success. A null buffer, zero capacity or insufficient space returns `HY_MT2_ARG` (-1), with no output written. Use `pandora_runtime_last_error` for the error message. The function has no size-query mode.

## Error codes

| Code | Meaning | What the caller should do |
| --- | --- | --- |
| `HY_MT2_OK` (0) | Success | Continue |
| `HY_MT2_ARG` (-1) | Invalid argument | Check input, options, structure sizes and buffer capacities |
| `HY_MT2_MODEL` (-2) | Invalid or incomplete model resources | Check [model setup](MODEL_SETUP.md) |
| `HY_MT2_NPU` (-3) | Backend failure | Read the error for the failing operation before retrying |
| `HY_MT2_STATE` (-4) | Invalid model or request state | Check call order and wait for active work to finish |
| `HY_MT2_INTERNAL` (-5) | SDK failure | Read the error for the failing operation |
| `HY_MT2_CANCELLED` (-6) | Cancellation confirmed | End the request |
| `HY_MT2_UNSUPPORTED` (-7) | Unsupported setting or feature | Choose a supported setting |

## Threads and ownership

Use one model per process and one active request per model. Only `hy_mt2_abort`, `hy_mt2_read_text` and `hy_mt2_get_stats` may overlap generation. The synchronous generation caller runs notifications. Request cancellation from a separate thread, outside the callback. Wait for generation and readers before destroying the model. Release caller-owned Runtime handles after their models. Create fresh model and Runtime objects in child processes.

Input strings are borrowed for the call and copied before any later use. Output bytes are copied into caller-owned buffers and can end mid-character. Decode incrementally. Error strings are borrowed until the next relevant call. Initialize structures with the exact size and ABI fields declared in the headers.

## Example

A complete program is in [examples/c/translate.c](../examples/c/translate.c). It loads a model, submits a message, writes UTF-8 output and releases the handle.
