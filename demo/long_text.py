"""Document segmentation; translation.py builds instructions and the SDK adds chat markers."""
import re
import time
from pandora_hy_mt2_1_8b._native import TranslationError


def split_once(text, limit):
    """Split without dropping or duplicating any source characters."""
    head = text[:limit]
    patterns = ((r"\n[ \t]*\n+", .8), (r"[。！？؟][”’\"\']?\s*|[.!?](?:[”’\"\']?\s+|$)", .5), (r"\s+", .33))
    for pattern, fraction in patterns:
        cuts = [m.end() for m in re.finditer(pattern, head) if m.end() >= max(1, int(limit * fraction))]
        if cuts:
            cut = cuts[-1]
            return text[:cut], text[cut:]
    return text[:limit], text[limit:]


def segments(text, limit=1500):
    result = []
    while len(text) > limit:
        left, text = split_once(text, limit)
        result.append(left)
    if text:
        result.append(text)
    return result


def plan_document(translator, text, source, target, cancel):
    """Resolve every exact prompt budget before emitting the fixed segment total."""
    pending = segments(text)
    planned = []
    budget = min(2048, translator.info["max_input_tokens"])
    while pending and not cancel.is_set():
        piece = pending.pop(0)
        if piece.strip() and translator.count_prompt_tokens(piece.strip(), source, target) > budget:
            if len(piece.strip()) <= 1:
                raise TranslationError(-1, "A source character exceeds the prompt token budget")
            left, right = split_once(piece, max(1, len(piece) // 2))
            pending[:0] = [left, right]
        else:
            planned.append(piece)
    return planned


def translate_document(translator, text, source, target, emit, cancel, before_segment):
    started = time.monotonic()
    pending = plan_document(translator, text, source, target, cancel)
    total, completed = len(pending), 0
    emit("segment", {"completed": 0, "total": total, "current": 0})
    output = []
    source_offset = 0
    first_ms = None
    stats = {"generation_ms": 0, "generated_tokens": 0, "prompt_tokens": 0}
    weighted_decode_rate = 0.0
    finish_reason = "stop"

    def delta(chunk):
        output.append(chunk)
        emit("delta", {"text": chunk})

    while pending and not cancel.is_set():
        piece = pending.pop(0)
        source_start, source_end = source_offset, source_offset + len(piece)
        source_offset = source_end
        if not piece.strip():
            delta(piece)
            completed += 1
            continue
        before_segment()
        emit("segment", {"completed": completed, "total": total, "current": completed + 1,
                         "source_start": source_start, "source_end": source_end})
        leading = piece[:len(piece) - len(piece.lstrip())]
        trailing = piece[len(piece.rstrip()):]
        prefix = leading
        if output and not prefix and not output[-1][-1:].isspace() and target not in ("zh", "ja"):
            prefix = " "
        emitted = False

        def chunk_delta(chunk):
            nonlocal emitted, first_ms
            if not chunk:
                return
            if first_ms is None:
                first_ms = (time.monotonic() - started) * 1000
            if not emitted and prefix:
                delta(prefix)
            emitted = True
            delta(chunk)

        result = translator.translate(piece.strip(), source, target, on_chunk=chunk_delta)
        for key in stats:
            stats[key] += result["stats"][key]
        # Preserve the backend decode rate: its first generated token belongs to prefill.
        weighted_decode_rate += result["stats"]["tokens_per_second"] * result["stats"]["generation_ms"]
        if result["cancelled"]:
            cancel.set()
            break
        if result.get("finish_reason") == "length":
            finish_reason = "length"
            break
        if trailing:
            delta(trailing)
        completed += 1
        emit("segment", {"completed": completed, "total": total, "current": completed,
                         "source_start": source_start, "source_end": source_end})
    stats["first_token_ms"] = first_ms or 0
    stats["tokens_per_second"] = weighted_decode_rate / stats["generation_ms"] if stats["generation_ms"] else 0
    if cancel.is_set() and finish_reason == "stop":
        finish_reason = "cancelled"
    return {"text": "".join(output), "cancelled": finish_reason == "cancelled",
            "finish_reason": finish_reason, "stats": stats,
            "completed_segments": completed, "total_segments": total,
            "elapsed_ms": (time.monotonic() - started) * 1000}
