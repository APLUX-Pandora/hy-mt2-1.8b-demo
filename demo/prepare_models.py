#!/usr/bin/env python3
"""Verify the complete selected download before first use or after an update."""
import argparse
import hashlib
import re
from pathlib import Path
from pandora_hy_mt2_1_8b._package import validate_model_package, _path

def verify_model_installation(directory):
    root = Path(directory).resolve()
    doc = validate_model_package(root)
    checksum = root / "SHA256SUMS"
    if checksum.stat().st_size > 1024 * 1024:
        raise ValueError("SHA256SUMS exceeds size limit")
    checks = {}
    for line in checksum.read_text().splitlines():
        if not line:
            continue
        digest, name = line.split(maxsplit=1)
        path = _path(root, name.removeprefix("*"))
        if path in checks or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid installation checksum entry")
        checks[path] = digest
    required = {_path(root, name) for name in ("models.json", "NOTICE", "LICENSES/Apache-2.0.txt")}
    required.update(_path(root, value if isinstance(value, str) else value["path"])
                    for value in doc["resources"].values())
    complete = []
    for target in doc["targets"]:
        paths = [_path(root, name) for name in target["files"]["language_model"]]
        if all(path.is_file() and path.stat().st_size > 0 for path in paths):
            complete.append(paths)
    if len(complete) != 1:
        raise ValueError("Expected one complete installation target")
    required.update(complete[0])
    for path in sorted(required):
        name = path.relative_to(root).as_posix()
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("Missing or empty installation resource: " + name)
        expected = checks.get(path)
        if expected is None:
            raise ValueError("Required resource has no installation checksum: " + name)
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError("Installation checksum differs: " + str(path))
    return doc

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package")
    args = parser.parse_args()
    try:
        verify_model_installation(args.package)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Model verification failed: {exc}\n"
                    "See docs/MODEL_SETUP.md in the Demo repository for downloads and verification.\n")
    print("Model download closure and required payload checksums verified")
if __name__ == "__main__":
    main()
