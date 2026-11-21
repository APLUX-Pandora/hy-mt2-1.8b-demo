"""Translate Chinese to English and English to Chinese using Chinese instructions."""
from pathlib import Path

from pandora_hy_mt2_1_8b import LanguageModel

MODEL_DIR = Path("models")
if not (MODEL_DIR / "models.json").is_file():
    MODEL_DIR = MODEL_DIR / "hy-mt2"

TRANSLATIONS = (
    ("英语", "明天上午九点半开会，请提前十分钟到达会议室。会议结束后，我们会把讨论结果发给所有同事。"),
    ("中文", "The meeting starts at nine thirty tomorrow morning. Please arrive ten minutes early. We will send the discussion results to all colleagues afterward."),
)

with LanguageModel.from_pretrained(MODEL_DIR) as model:
    for target_language, source_text in TRANSLATIONS:
        prompt = (
            f"将以下文本翻译为{target_language}，"
            f"注意只需要输出翻译后的结果，不要额外解释：\n\n{source_text}"
        )
        result = model.generate(
            [{"role": "user", "content": prompt}],
            max_new_tokens=4096,
            do_sample=True,
            temperature=0.7,
            top_p=0.6,
            top_k=20,
            repetition_penalty=1.05,
        )
        print(result.text)
