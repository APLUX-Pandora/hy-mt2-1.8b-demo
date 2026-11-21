"""Translate English to French using English instructions."""
from pathlib import Path

from pandora_hy_mt2_1_8b import LanguageModel

MODEL_DIR = Path("models")
if not (MODEL_DIR / "models.json").is_file():
    MODEL_DIR = MODEL_DIR / "hy-mt2"

TARGET_LANGUAGE = "French"
SOURCE_TEXT = (
    "The meeting starts at nine thirty tomorrow morning. Please arrive ten minutes early. "
    "We will send the discussion results to all colleagues afterward."
)

prompt = (
    f"Translate the following text into {TARGET_LANGUAGE}. "
    "Note that you should only output the translated result "
    f"without any additional explanation:\n\n{SOURCE_TEXT}"
)
messages = [{"role": "user", "content": prompt}]

with LanguageModel.from_pretrained(MODEL_DIR) as model:
    result = model.generate(
        messages,
        max_new_tokens=4096,
        do_sample=True,
        temperature=0.7,
        top_p=0.6,
        top_k=20,
        repetition_penalty=1.05,
    )
    print(result.text)
