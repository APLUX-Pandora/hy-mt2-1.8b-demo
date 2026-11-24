# Model setup

## Device requirements

- A compatible Linux device with Aidlux LMS (`sudo lms check` returns true), drivers, DSP firmware and BSP/FastRPC support.
- Python 3.10–3.12 in the Demo environment (see [Install](../README.md#1-install)).
- The SDK includes its QNN runtime libraries. Do not install QNN separately or set QNN paths.

See [device prerequisites](../sdk/environment.md) for system libraries.

## Targets

Pick the folder for your device's SoC:

| SoC | Target folder |
| --- | --- |
| QCS8550 | `qcs8550_qnn248` |
| QCS9075 / IQ9 | `qcs9075_qnn248` |
| QCS8625 | `qcs8625_qnn248` |
| QCS8275 / IQ8 | `qcs8275_qnn248` |

## Download

Replace `<target-folder>` with a folder from the table.

From the Demo root, in the activated environment, download the shared resources once and then one target:

```bash
hf download APLUX-Pandora/Hy-MT2-1.8B --local-dir models --exclude "targets/*" --exclude "media/*" --exclude README.md --exclude .gitattributes
hf download APLUX-Pandora/Hy-MT2-1.8B --local-dir models --include "targets/<target-folder>/*"
```

Run `hf auth login` first if the repository is private. Keep one target per model folder: to switch devices, move the old `targets/` folder out or download into a new folder.

Verify the downloaded model package before use:

```bash
python demo/prepare_models.py models
```

## Folder layout

After the download, `models/` in a Demo clone looks like this:

```text
models/
├── README.md                      # included in the Demo checkout
├── models.json
├── SHA256SUMS
├── tokenizer.json
├── NOTICE
├── LICENSES/Apache-2.0.txt
├── prefix/kv-cache.primary.qnn-htp
├── embedding/embedding.f32.bin
└── targets/qcs8625_qnn248/
    ├── hy-mt2-1.8b_qnn248_qcs8625_cl8192_1_of_2.serialized.bin.aidem
    └── hy-mt2-1.8b_qnn248_qcs8625_cl8192_2_of_2.serialized.bin.aidem
```

The SDK reads `models.json`, checks that the shared resources and one complete target are present, and reports what is missing. `hf download` verifies each large file's checksum.

The SDK reads the standalone tokenizer from the model directory and the Genie dialog and HTP configuration from the encrypted model package. The package also includes a tokenizer for AidGen. The manifest records the chat template opening in `chat_template.bos` and the cache path and covered token IDs in `resources.prefix`. The SDK renders the full template and rejects a mismatch before inference.

## Troubleshooting

| Message or symptom | What to do |
| --- | --- |
| LMS check returns false | Activate the device before loading the model. |
| No complete target | Download the target listed for your SoC and run the package check again. |
| Multiple complete targets | Keep only the target for the current device in the model folder. |
