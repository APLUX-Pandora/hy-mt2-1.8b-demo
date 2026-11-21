#ifndef HY_MT2_H
#define HY_MT2_H
#include <stddef.h>
#include <stdint.h>
#include "pandora_runtime.h"
#if defined(_WIN32)
#define HY_MT2_API __declspec(dllexport)
#else
#define HY_MT2_API __attribute__((visibility("default")))
#endif
#define HY_MT2_VERSION "1.0.0"
#ifdef __cplusplus
extern "C" {
#endif
typedef struct hy_mt2_engine hy_mt2_engine;
enum { HY_MT2_OK = 0, HY_MT2_ARG = -1, HY_MT2_MODEL = -2, HY_MT2_NPU = -3,
       HY_MT2_STATE = -4, HY_MT2_INTERNAL = -5, HY_MT2_CANCELLED = -6,
       HY_MT2_UNSUPPORTED = -7 };
enum { HY_MT2_IDLE = 0, HY_MT2_PREPARED, HY_MT2_RUNNING, HY_MT2_DONE, HY_MT2_STOPPED, HY_MT2_FAILED };
/* Rendered prompt budget, including BOS and template: 32..8191 tokens;
 * default 512. This is the accepted option range. A request within that range
 * must still fit the configured context and satisfy backend constraints. */
typedef struct { uint32_t struct_size; uint32_t max_input_tokens; } hy_mt2_options;
typedef struct {
    uint32_t struct_size;
    uint32_t state;
    uint64_t prompt_tokens;
    uint64_t generated_tokens;
    double init_ms;
    double first_token_ms;
    double generation_ms;
    double tokens_per_second;
} hy_mt2_stats;
typedef void (*hy_mt2_notify)(void *user);
/* Synchronous translation engine with automatic AIDEM model loading.
 * Sequence: create -> start -> generate -> read_text -> get_stats; repeat; destroy.
 * generate blocks and notifies on queued output. read_text may be called from notify.
 * Backend computation runs on a model-owned worker; notifications are relayed on
 * the synchronous generate caller. The application owns timeout and transport. There is one engine per process (vendor restriction).
 * Only abort, read_text and get_stats may run concurrently with generate. Never call
 * abort from notify; request it from a separate application thread. Repeat abort if
 * cancellation races with start-up. destroy requires generate and readers to finish.
 * UTF-8 output is bytes: reads may split a character; decode incrementally.
 * Generation omission/null uses the common LM defaults; get_info reports the effective
 * sampler and resolved generation settings. The Demo passes its preset explicitly. Each start clears conversation history. Repeated output can vary.
 * Strings returned by error functions remain owned by the library.
 */
HY_MT2_API const char *hy_mt2_version(void);
HY_MT2_API hy_mt2_options hy_mt2_default_options(void);
HY_MT2_API hy_mt2_engine *hy_mt2_create(const char *model_dir, const hy_mt2_options *options);
/* NULL runtime selects CPU default, burst, normal and QNN device 0; handles are provider-local.
 * Output slot must be empty; model retains runtime state until destroy. */
HY_MT2_API int hy_mt2_create_with_runtime(const char *model_dir, const hy_mt2_options *options, pandora_runtime_t *runtime, hy_mt2_engine **out);
/* Clears the owned slot only after checked native teardown succeeds.
 * A vendor cleanup failure retains the complete dependency owner and returns NPU;
 * the failed instance cannot be reused. Its error remains available through last_error.
 * Returns STATE for inherited/running models without touching the slot. */
HY_MT2_API int hy_mt2_destroy_owned(hy_mt2_engine **slot);
HY_MT2_API void hy_mt2_destroy(hy_mt2_engine *engine);
HY_MT2_API const char *hy_mt2_create_error(void);
HY_MT2_API int hy_mt2_create_error_code(void);
HY_MT2_API const char *hy_mt2_last_error(hy_mt2_engine *engine);
/* Languages: zh en ja ko fr de es ar th. Source and target must differ.
 * start validates UTF-8, language codes and the actual tokenizer budget.
 */
/* Return exact prompt token count, or a negative error, without preparing generation.
 * This may exceed max_input_tokens. Call only when no translation is prepared/running.
 */
HY_MT2_API int hy_mt2_count_prompt_tokens(hy_mt2_engine *engine, const char *utf8, const char *source, const char *target);
HY_MT2_API int hy_mt2_start(hy_mt2_engine *engine, const char *utf8, const char *source, const char *target);
/* Generic LLM request: JSON object with messages (role/content string array).
 * Omitted/null controls resolve per request: max_new_tokens=256, do_sample=false,
 * temperature=1, top_p=1, top_k=0, repetition_penalty=1.
 * Explicit temperature/top_p/top_k require do_sample=true; top_k=0 disables filtering.
 * The configured context has 8192 total positions for the rendered prompt
 * (including BOS) and generated tokens. The effective output limit is the
 * smaller of the requested new tokens and the remaining configured context.
 * Successful generation reports stop on natural completion or length when it
 * reaches the effective limit. Confirmed cancellation reports cancelled.
 * Oversized input is rejected without truncation. A backend execution failure,
 * including a provider context-limit error, returns a negative status without
 * a successful finish reason.
 * No translation instruction is inserted. Each request starts a fresh session.
 * Input/output JSON buffers use UTF-8. Result query follows get_info sizing rules.
 */
HY_MT2_API int hy_mt2_start_messages(hy_mt2_engine *engine, const char *request_json);
HY_MT2_API int hy_mt2_count_messages(hy_mt2_engine *engine, const char *request_json);
HY_MT2_API int hy_mt2_get_result(hy_mt2_engine *engine, char *output, size_t capacity);
HY_MT2_API int hy_mt2_generate(hy_mt2_engine *engine, hy_mt2_notify notify, void *user);
/* Return bytes copied, zero if queue empty, or a negative error. Does not add NUL. */
HY_MT2_API int hy_mt2_read_text(hy_mt2_engine *engine, char *output, size_t capacity);
HY_MT2_API int hy_mt2_abort(hy_mt2_engine *engine);
HY_MT2_API int hy_mt2_get_stats(hy_mt2_engine *engine, hy_mt2_stats *stats);
/* JSON capabilities and current resolved settings. Returns required bytes including
 * NUL if the buffer is small, or a negative status on error. */
HY_MT2_API int hy_mt2_get_info(hy_mt2_engine *engine, char *output, size_t capacity);
#ifdef __cplusplus
}
#endif
#endif
