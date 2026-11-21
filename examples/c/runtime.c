/* SPDX-License-Identifier: Apache-2.0 */
#include "hy_mt2.h"
#include <stdio.h>

int main(int argc, char **argv) {
    pandora_runtime_t *runtime = NULL;
    hy_mt2_engine *model = NULL;
    pandora_runtime_config_t config = PANDORA_RUNTIME_CONFIG_INIT;
    pandora_runtime_capabilities_t caps = {0};
    pandora_runtime_status_t status = {0};
    int rc, result = 1;
    if (argc > 2) {
        fprintf(stderr, "Usage: %s [MODEL_DIR]\n", argv[0]);
        return 2;
    }
    config.qnn.performance_mode = PANDORA_QNN_BURST;
    config.qnn.priority = PANDORA_PRIORITY_NORMAL;
    config.qnn.device_id = 0;
    rc = pandora_runtime_create(&config, &runtime);
    if (rc || !runtime) {
        fprintf(stderr, "Runtime creation failed: %s\n", pandora_runtime_last_error());
        goto cleanup;
    }
    caps.struct_size = sizeof(caps);
    caps.abi_version = PANDORA_RUNTIME_ABI_VERSION;
    rc = pandora_runtime_get_capabilities(runtime, &caps);
    if (rc) {
        fprintf(stderr, "Capability query failed: %s\n", pandora_runtime_last_error());
        goto cleanup;
    }
    if (printf("Runtime provider=%u supported_fields=%u\n", caps.provider, caps.supported_fields) < 0)
        goto output_error;
    if (argc == 2) {
        char text[1024];
        int n;
        rc = hy_mt2_create_with_runtime(argv[1], NULL, runtime, &model);
        if (rc || !model) {
            fprintf(stderr, "Model creation failed: %s\n", hy_mt2_create_error());
            goto cleanup;
        }
        rc = hy_mt2_start_messages(model,
            "{\"max_new_tokens\":4096,\"do_sample\":true,\"temperature\":0.7,\"top_p\":0.6,\"top_k\":20,\"repetition_penalty\":1.05,\"messages\":[{\"role\":\"user\",\"content\":\"Translate into Chinese: Hello.\"}]}");
        if (!rc) rc = hy_mt2_generate(model, NULL, NULL);
        if (rc) {
            fprintf(stderr, "Generation failed: %s\n", hy_mt2_last_error(model));
            goto cleanup;
        }
        while ((n = hy_mt2_read_text(model, text, sizeof(text))) > 0) {
            if (fwrite(text, 1, (size_t)n, stdout) != (size_t)n) goto output_error;
        }
        if (n < 0) {
            fprintf(stderr, "Text read failed: %s\n", hy_mt2_last_error(model));
            goto cleanup;
        }
        if (fputc('\n', stdout) == EOF) goto output_error;
    }
    status.struct_size = sizeof(status);
    status.abi_version = PANDORA_RUNTIME_ABI_VERSION;
    rc = pandora_runtime_get_status(runtime, &status);
    if (rc) {
        fprintf(stderr, "Status query failed: %s\n", pandora_runtime_last_error());
        goto cleanup;
    }
    if (printf("Runtime mode=%u priority=%d active_contexts=%u\n",
               status.performance_mode, status.priority, status.active_contexts) < 0 ||
        fflush(stdout) == EOF)
        goto output_error;
    result = 0;
    goto cleanup;
output_error:
    fputs("Writing to standard output failed\n", stderr);
cleanup:
    rc = hy_mt2_destroy_owned(&model);
    if (rc) {
        fprintf(stderr, "Model destruction failed: %d\n", rc);
        return 1; /* Retain dependent Runtime after failed model destruction. */
    }
    rc = pandora_runtime_destroy(&runtime);
    if (rc) {
        fprintf(stderr, "Runtime destruction failed: %s\n", pandora_runtime_last_error());
        result = 1;
    }
    return result;
}
