# Web Demo

Follow [Install](../README.md#install) for device prerequisites, the LMS precheck and Demo installation; then [download one model target](../docs/MODEL_SETUP.md). From the repository root, keep that same .venv activated (`source .venv/bin/activate`):

```bash
bash demo/run.sh --models models --port 51106
```

Open `http://<board-ip>:51106`, replacing `<board-ip>` with the IP address of the device running the Demo. Select source/target languages, edit text, and Translate. Output streams; Stop cancels and retains incomplete output. Copy/download exports completed or explicitly marked incomplete text. Short mode accepts up to2000 characters; long mode accepts20000 and plans independent segments against the SDK token budget. Every request and segment is independent, without conversation memory or cross-turn KV cache.

Language selection, translation instructions, document segmentation, HTTP jobs and UI state belong to the business layer. Both short and long translation use Chinese instructions with Chinese target-language names when the source or target is zh; other directions use English instructions and English language names. Inference uses the installed pandora_hy_mt2_1_8b.LanguageModel through the same public messages API as examples. Internal diagnostics support token budgets and statistics; they are not alternative inference paths.

The model serves one request at a time. Busy requests are rejected. Stop/disconnect requests cancellation; completion is only reported after a terminal event. Failed native inference requires Reload model. Shutdown stops admission, joins in-flight jobs and handlers, then closes the model.

--host defaults0.0.0.0; --port defaults51106; --timeout defaults120seconds per segment (long requests also have a600second total deadline). No authentication/TLS is provided; use a trusted LAN.

## Recording

Recording placeholder; finished presentation media is maintained after publication.

## Languages

Choose two different language codes. Source and target are both required; None/auto is unavailable in the Demo selection.

| Code | Language |
| --- | --- |
| zh | Chinese |
| en | English |
| ja | Japanese |
| ko | Korean |
| fr | French |
| de | German |
| es | Spanish |
| ar | Arabic |
| th | Thai |

The SDK accepts text messages and translation instructions; this language selector belongs to the Demo. Translations can contain errors in names, facts or intent; review output for your use.

## Generation defaults and Demo preset

The examples explicitly pass this Demo's translation preset. Omitted sampling options use the loaded model package defaults. The SDK defaults to a 256-token output limit. The Demo uses an explicit 4096-token ceiling to preserve its EOS/context-bounded behavior; the total context and input limits still apply.
Python examples pass the confirmed values as individual keyword arguments; Web maps each application setting to its named SDK parameter; C examples explicitly set the same six JSON fields. Omitted or null C sampling fields use the model package defaults for each request. A top-k of zero disables candidate count filtering. Request token limits report length. Existing C struct sizes and function signatures are unchanged.
