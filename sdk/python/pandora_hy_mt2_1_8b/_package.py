"""Bounded resource selection for startup; full hashes are installation-only."""
import json
import os
from pathlib import Path

_SUPPORTED_TARGETS = {
    ("qcs8550", "2.48"),
    ("qcs9075", "2.48"),
    ("qcs8625", "2.48"),
    ("qcs8275", "2.48"),
}

def _path(root, name):
    if not isinstance(name, str) or not name or "\\" in name or "\0" in name:
        raise ValueError("Invalid model resource path")
    relative = Path(name)
    if relative.is_absolute() or any(x in (".", "..") for x in name.split("/")):
        raise ValueError("Model resource traversal is forbidden")
    value = (root / relative).resolve()
    if value == root or root not in value.parents:
        raise ValueError("Model resource escapes the package root")
    return value

def _file(path):
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Missing or empty model resource: " + str(path))

def validate_model_package(directory):
    root = Path(directory).resolve()
    manifest = _path(root, "models.json")
    if manifest.stat().st_size > 1024 * 1024:
        raise ValueError("models.json exceeds size limit")
    doc = json.loads(manifest.read_text())
    if type(doc.get("format_version")) is not int or doc["format_version"] != 2 or doc.get("model") != "Hy-MT2-1.8B":
        raise ValueError("Unsupported models.json format/model")
    resources = doc["resources"]
    prefix = _path(root, resources["prefix"])
    tokenizer = _path(root, resources["tokenizer"])
    lut = resources["embedding"]
    if lut["dtype"] != "float32-le" or lut["layout"] != "row-major" or lut["shape"] != [120818, 2048]:
        raise ValueError("Invalid embedding layout")
    embedding = _path(root, lut["path"])
    for path in (prefix, tokenizer, embedding):
        _file(path)
    if prefix.suffix != ".qnn-htp" or prefix.stat().st_size != 32784:
        raise ValueError("Invalid original prefix")
    if tokenizer.stat().st_size > 32 * 1024 * 1024 or embedding.stat().st_size != 989741056:
        raise ValueError("Invalid tokenizer or embedding size")
    identities, matches, incomplete = set(), [], []
    targets = doc["targets"]
    if not isinstance(targets, list) or not 1 <= len(targets) <= 32:
        raise ValueError("Invalid model targets")
    for target in targets:
        identity = (target["soc"], target["qnn_version"])
        if identity not in _SUPPORTED_TARGETS or identity in identities:
            raise ValueError("Unsupported or duplicate HY Multi-CL target")
        identities.add(identity)
        folder = _path(root, target["directory"])
        files = target["files"]
        if set(files) != {"language_model"}:
            raise ValueError("Unexpected protected resource role")
        shards = files["language_model"]
        if not isinstance(shards, list) or len(shards) != 2:
            raise ValueError("Expected two ordered language-model shards")
        paths = [_path(root, value) for value in shards]
        if len(set(paths + [prefix, tokenizer, embedding])) != 5 or any(folder != p.parent or p.suffix != ".aidem" for p in paths):
            raise ValueError("Duplicate resource or non-flat AIDEM graph")
        missing = [p.relative_to(root).as_posix() for p in paths
                   if not p.is_file() or p.stat().st_size == 0]
        if missing:
            incomplete.append(f"{identity[0]}: {', '.join(missing)}")
        else:
            matches.append(paths)
    if not matches:
        raise ValueError("No complete local target. Missing or empty resources: " + "; ".join(incomplete))
    if len(matches) > 1:
        raise ValueError("Use exactly one complete local target; found " + str(len(matches)))
    return doc

def resolve_model_dir(model_dir=None, *, default_container=None):
    explicit = model_dir if model_dir is not None else os.environ.get("HY_MT2_MODELS")
    if explicit is None and default_container is None:
        raise ValueError("Installed SDK requires an explicit model package root")
    if explicit is not None and not os.fspath(explicit).strip():
        raise ValueError("Explicit model path is empty")
    base = Path(explicit if explicit is not None else default_container).expanduser().resolve()
    if (base / "models.json").is_file(): root = base
    elif explicit is not None:
        raise ValueError("Explicit model root must contain models.json")
    else:
        candidates = sorted(p for p in base.glob("*") if p.is_dir() and (p / "models.json").is_file())
        if len(candidates) != 1:
            raise ValueError("Choose one model package explicitly; found " + str(len(candidates)))
        root = candidates[0].resolve()
    validate_model_package(root)
    return root
