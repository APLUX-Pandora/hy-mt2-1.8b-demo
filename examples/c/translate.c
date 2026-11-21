/* SPDX-License-Identifier: Apache-2.0 */
#include "hy_mt2.h"
#include <stdio.h>

struct output { hy_mt2_engine *model; int error; };
static void receive(void *opaque) {
    struct output *out = (struct output *)opaque;
    char bytes[1024];
    int size;
    while ((size = hy_mt2_read_text(out->model, bytes, sizeof(bytes))) > 0) {
        if (fwrite(bytes, 1, (size_t)size, stdout) != (size_t)size) out->error = 1;
    }
    if (size < 0) out->error = 1;
}
int main(int argc, char **argv) {
    struct output out = {NULL, 0};
    int code, result = 1;
    const char *request = "{\"max_new_tokens\":4096,\"do_sample\":true,\"temperature\":0.7,\"top_p\":0.6,\"top_k\":20,\"repetition_penalty\":1.05,\"messages\":[{\"role\":\"user\",\"content\":\"Translate into Chinese: Good morning.\"}]}";
    if (argc != 2) { fprintf(stderr, "Usage: %s MODEL_DIR\n", argv[0]); return 2; }
    code = hy_mt2_create_with_runtime(argv[1], NULL, NULL, &out.model);
    if (code || !out.model) { fprintf(stderr, "%s\n", hy_mt2_create_error()); goto cleanup; }
    code = hy_mt2_start_messages(out.model, request);
    if (!code) code = hy_mt2_generate(out.model, receive, &out);
    receive(&out);
    if (code) { fprintf(stderr, "%s\n", hy_mt2_last_error(out.model)); goto cleanup; }
    if (out.error || fputc('\n', stdout) == EOF || fflush(stdout) == EOF || ferror(stdout)) {
        fputs("Could not write the translation to standard output\n", stderr);
        goto cleanup;
    }
    result = 0;
cleanup:
    code = hy_mt2_destroy_owned(&out.model);
    if (code) { fprintf(stderr, "Model destruction failed: %d\n", code); result = 1; }
    return result;
}
