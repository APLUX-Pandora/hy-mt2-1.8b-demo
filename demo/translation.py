"""Translation application policy over the general LLM interface."""
import threading
from pandora_hy_mt2_1_8b import LanguageModel, GenerationError
from pandora_hy_mt2_1_8b._native import TranslationError

DEMO_GENERATION = {'max_new_tokens': 4096, 'do_sample': True, 'temperature': 0.7, 'top_p': 0.6, 'top_k': 20, 'repetition_penalty': 1.05}

LANGUAGES = {"zh": "Chinese", "en": "English", "ja": "Japanese", "ko": "Korean",
             "fr": "French", "de": "German", "es": "Spanish", "ar": "Arabic", "th": "Thai"}


LANGUAGES_ZH = {"zh": "中文", "en": "英语", "ja": "日语", "ko": "韩语",
                "fr": "法语", "de": "德语", "es": "西班牙语", "ar": "阿拉伯语", "th": "泰语"}

def translation_prompt(text, source, target):
    if source not in LANGUAGES or target not in LANGUAGES or source == target:
        raise TranslationError(-1, "Choose two different supported languages")
    if not isinstance(text, str) or not text.strip():
        raise TranslationError(-1, "Provide nonempty text")
    if "zh" in (source, target):
        return (f"将以下文本翻译为{LANGUAGES_ZH[target]}，"
                f"注意只需要输出翻译后的结果，不要额外解释：\n\n{text}")
    return (f"Translate the following text into {LANGUAGES[target]}. Note that you should only "
            f"output the translated result without any additional explanation:\n\n{text}")


class Translator:
    """Demo adapter; language selection and translation instructions live here."""
    def __init__(self, model_dir=None, *, max_input_tokens=2048, runtime=None):
        if max_input_tokens != 2048:
            raise ValueError("This LM SDK uses a 2048-token prompt budget")
        self.model = LanguageModel.from_pretrained(model_dir, runtime=runtime)
        self._cancel = threading.Event()

    @property
    def info(self):
        return self.model._info

    @property
    def stats(self):
        return self.model._stats

    def count_prompt_tokens(self, text, source, target):
        try:
            return self.model._count_messages([{"role": "user", "content": translation_prompt(text, source, target)}])
        except GenerationError as exc:
            raise TranslationError(exc.native_code or -1, str(exc)) from exc

    def translate(self, text, source, target, on_chunk=None):
        self._cancel.clear()
        try:
            with self.model.generate_stream(
                [{ "role": "user", "content": translation_prompt(text, source, target)}],
                max_new_tokens=DEMO_GENERATION['max_new_tokens'],
                do_sample=DEMO_GENERATION['do_sample'],
                temperature=DEMO_GENERATION['temperature'],
                top_p=DEMO_GENERATION['top_p'],
                top_k=DEMO_GENERATION['top_k'],
                repetition_penalty=DEMO_GENERATION['repetition_penalty'],
            ) as stream:
                for update in stream:
                    if on_chunk and update.delta:
                        on_chunk(update.delta)
                    if self._cancel.is_set():
                        break
            reason = stream.result.finish_reason
            return {"text": stream.result.text, "finish_reason": reason,
                    "cancelled": reason == "cancelled", "stats": self.model._stats}
        except GenerationError as exc:
            raise TranslationError(exc.native_code or -3, str(exc)) from exc

    def abort(self):
        self._cancel.set()
        self.model._abort()

    def close(self):
        self.model.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
