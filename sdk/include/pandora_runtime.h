/* Pandora runtime configuration ABI v4. Provider-local native Genie/QNN2.48 configuration.
 * Handles are process-local and provider-local. Never pass a handle to another SDK provider.
 * Models retain the runtime; destroying the caller handle does not invalidate attached models.
 * No model handle may be inherited through fork. Defaults: CPU default, burst, normal, device 0; internal active RPC 100 us. */
#ifndef PANDORA_RUNTIME_H
#define PANDORA_RUNTIME_H
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
#if defined(_WIN32)
#define PANDORA_API __declspec(dllexport)
#else
#define PANDORA_API __attribute__((visibility("default")))
#endif
typedef struct pandora_runtime pandora_runtime_t;
enum { PANDORA_OK = 0, PANDORA_ERROR_ARGUMENT = -1, PANDORA_ERROR_BACKEND = -3,
       PANDORA_ERROR_STATE = -4, PANDORA_ERROR_INTERNAL = -5 };
enum { PANDORA_BACKEND_QNN = 1 };
/* Existing candidate values remain stable. These are profile IDs, not voltage values. */
enum { PANDORA_QNN_BURST = 0, PANDORA_QNN_BALANCED = 1, PANDORA_QNN_SYSTEM_SETTINGS = 2,
       PANDORA_QNN_SUSTAINED_HIGH_PERFORMANCE = 3, PANDORA_QNN_HIGH_PERFORMANCE = 4,
       PANDORA_QNN_LOW_BALANCED = 5, PANDORA_QNN_HIGH_POWER_SAVER = 6,
       PANDORA_QNN_POWER_SAVER = 7, PANDORA_QNN_LOW_POWER_SAVER = 8,
       PANDORA_QNN_EXTREME_POWER_SAVER = 9 };
enum { PANDORA_PRIORITY_LOW = 0, PANDORA_PRIORITY_NORMAL = 100,
       PANDORA_PRIORITY_NORMAL_HIGH = 150, PANDORA_PRIORITY_HIGH = 200 };
enum { PANDORA_MEMORY_LOCK_OFF = 0, PANDORA_MEMORY_LOCK_BEST_EFFORT = 1 };
typedef struct { uint32_t performance_mode; int32_t priority; uint32_t device_id; uint32_t reserved; } pandora_qnn_options_t;
#define PANDORA_RUNTIME_ABI_VERSION 4
#define PANDORA_CPU_ABI_VERSION 1
enum { PANDORA_CPU_AFFINITY_INHERIT=0, PANDORA_CPU_AFFINITY_DEFAULT=1, PANDORA_CPU_AFFINITY_EXPLICIT=2 };
typedef struct {
    uint32_t struct_size, abi_version, policy, cpu_count;
    const uint32_t *cpu_ids;
    uint32_t reserved[2];
} pandora_cpu_options_t;
#define PANDORA_CPU_OPTIONS_INIT {sizeof(pandora_cpu_options_t), PANDORA_CPU_ABI_VERSION, PANDORA_CPU_AFFINITY_DEFAULT, 0, 0, {0,0}}


enum { PANDORA_QNN_OVERRIDE_RPC_CONTROL_LATENCY = 1, PANDORA_QNN_OVERRIDE_RPC_POLLING_TIME = 2 };
typedef struct {
    uint32_t struct_size, abi_version, backend, memory_lock;
    pandora_qnn_options_t qnn;
    /* ABI v2 append-only overrides. Flags distinguish explicit zero from preset defaults. */
    uint32_t qnn_override_flags, rpc_control_latency_us, rpc_polling_time_us, reserved;
    pandora_cpu_options_t cpu;
} pandora_runtime_config_t;
#define PANDORA_RUNTIME_CONFIG_INIT {sizeof(pandora_runtime_config_t), PANDORA_RUNTIME_ABI_VERSION, PANDORA_BACKEND_QNN, PANDORA_MEMORY_LOCK_BEST_EFFORT, {PANDORA_QNN_BURST, PANDORA_PRIORITY_NORMAL, 0, 0}, 0, 0, 0, 0, PANDORA_CPU_OPTIONS_INIT}
typedef struct {
    uint32_t struct_size, abi_version, performance_mode;
    int32_t priority;
    uint32_t memory_lock, active_contexts, power_client_created, active_executions;
    /* Monotonic accepted submissions across attached model lifetimes on this Runtime. */
    uint64_t accepted_active_votes, accepted_release_votes;
    uint32_t rpc_control_latency_us, rpc_polling_time_us, process_rpc_polling_time_us, deferred_vote_failures;
} pandora_runtime_status_t;
/* NULL and ABI4 CONFIG_INIT resolve to CPU default, burst, normal and device 0.
 * ABI4 redefines the former QNN reserved bytes as device_id/reserved; this is
 * never interpreted under ABI2/3. ABI3 managed-default callers remain accepted
 * with zero legacy reserved words; explicit legacy hardware requests stay rejected.
 * RPC override fields retain their existing unsupported contract. Native model memory
 * protection is internal best-effort, not a caller security/debug switch.
 * Device existence/availability is checked by the backend at model load.
 * Accepted configuration is not proof of submission or hardware application. */
#define PANDORA_VALUE_UNKNOWN UINT32_MAX
#define PANDORA_PRIORITY_UNKNOWN INT32_MIN
enum { PANDORA_ERROR_UNSUPPORTED = -7 };
PANDORA_API const char *pandora_runtime_last_error(void);
PANDORA_API int pandora_runtime_create(const pandora_runtime_config_t *, pandora_runtime_t **out);
PANDORA_API int pandora_runtime_get_status(pandora_runtime_t *, pandora_runtime_status_t *);
PANDORA_API int pandora_runtime_destroy(pandora_runtime_t **);
enum { PANDORA_FIELD_PERFORMANCE_MODE = 1, PANDORA_FIELD_PRIORITY = 2,
       PANDORA_FIELD_RPC_CONTROL_LATENCY = 4, PANDORA_FIELD_RPC_POLLING = 8,
       PANDORA_FIELD_MEMORY_LOCK = 16 };
enum { PANDORA_PROVIDER_AIDGEN_QNN248 = 3, PANDORA_PROVIDER_GENIE_QNN248 = 4, PANDORA_PROVIDER_GENIE_PDM_QNN248 = PANDORA_PROVIDER_GENIE_QNN248 };
typedef struct {
    uint32_t struct_size, abi_version, provider, supported_fields;
    uint32_t supported_performance_modes, reserved[3];
} pandora_runtime_capabilities_t;
typedef struct {
    uint32_t struct_size, abi_version, configured_fields, submitted_fields;
    uint32_t active_contexts, backend_performance_mode, backend_rpc_control_latency_us, reserved;
} pandora_runtime_submission_status_t;
PANDORA_API int pandora_runtime_get_capabilities(pandora_runtime_t *, pandora_runtime_capabilities_t *);
PANDORA_API int pandora_runtime_get_submission_status(pandora_runtime_t *, pandora_runtime_submission_status_t *);
enum { PANDORA_FIELD_DEVICE_ID = 32 };
typedef struct {
    uint32_t struct_size, abi_version, requested_device_id, bound;
    uint32_t execution_device_id, power_device_id, power_core_id, power_client_id;
} pandora_runtime_device_status_t;
/* ABI4 exact-sized status; bound is set only after actual topology/handle and
 * power-client agreement has been verified by this SDK's backend. The binding
 * and its device fields are reported from one snapshot. */
PANDORA_API int pandora_runtime_get_device_status(pandora_runtime_t *, pandora_runtime_device_status_t *);
enum { PANDORA_CPU_IDS_ALLOWED=0, PANDORA_CPU_IDS_RESOLVED=1, PANDORA_CPU_IDS_DEFAULT=2 };
enum { PANDORA_CPU_COVERAGE_MODEL_EXECUTION=2 };
enum { PANDORA_CPU_THREAD_MODEL=3, PANDORA_CPU_THREAD_BACKEND=4 };
enum { PANDORA_CPU_PROFILE_NONE=0, PANDORA_CPU_PROFILE_MODEL_PACKAGE=2 };
typedef struct {
    uint32_t struct_size, abi_version, policy, coverage;
    uint32_t supported_policies, backend_override_supported, active_workers, observed_threads;
    uint32_t verified_threads, profile_id, reserved[2];
    uint64_t affinity_failures;
    uint64_t package_mask, backend_mask;
    uint32_t config_flags, reserved_tail;
} pandora_cpu_status_t;
typedef struct {
    uint32_t struct_size, abi_version;
    uint64_t tid;
    uint32_t scope, cpu_count, verified, reserved;
} pandora_cpu_thread_status_t;
/* CPU query structs use PANDORA_CPU_ABI_VERSION. Array queries accept NULL
 * with *count=0 to report required size. Insufficient capacity updates *count,
 * writes no array elements and returns ARGUMENT. Query each thread by index
 * only while model lifecycles are quiescent; records disappear on model close.
 * Observed masks are freshly read from the kernel, not config echoes. */
PANDORA_API int pandora_runtime_get_cpu_status(pandora_runtime_t *, pandora_cpu_status_t *);
PANDORA_API int pandora_runtime_get_cpu_ids(pandora_runtime_t *, uint32_t kind, uint32_t *ids, uint32_t *count);
PANDORA_API int pandora_runtime_get_cpu_thread(pandora_runtime_t *, uint32_t index, pandora_cpu_thread_status_t *, uint32_t *ids, uint32_t *count);
/* config_flags: 1 package mask known, 2 override submitted and read back,
 * 4 override submitted. backend_mask is valid when 2 or 4 is set.
 * This provider reports submission (4) and has no backend readback (2).
 * default resolves the versioned platform table using Linux soc_id and kernel
 * present CPU count: 603/present=8 -> 0xe0, 603/present=6 -> 0x38,
 * 702 -> 0x8c, unrecognized IDs -> 0xe0. A registered ID with unsupported
 * present count fails. The complete selected mask must be present, online and
 * host-allowed; it is never silently narrowed. It overrides the package mask.
 * Model-owned worker placement is reported separately and cannot escape host
 * permissions. The caller thread is not rebound.
 * inherit uses the model-loading thread's allowed CPUs and submits 0x0.
 * Explicit sets accept CPU IDs 0..63 (Genie uint64 mask).
 * CPU query ABI1 uses exact sizes; masks are backend config, not OS observations.
 * thread query masks are freshly read from the kernel. */
/* JSON profile identity: Linux ID, present count, config version, fallback and mask. */
PANDORA_API int pandora_runtime_get_cpu_profile(pandora_runtime_t*, char*, size_t);
#ifdef __cplusplus
}
#endif
#endif
