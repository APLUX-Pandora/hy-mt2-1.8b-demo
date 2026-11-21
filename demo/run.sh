#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
python="${PYTHON:-$PWD/.venv/bin/python}"
if [[ ! -x "$python" ]]; then
    echo 'Project environment missing. Run: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt' >&2
    exit 1
fi
if ! "$python" -c 'import sys; raise SystemExit(sys.prefix == sys.base_prefix)'; then
    echo 'Use a dedicated project virtual environment; PYTHON must not select system Python.' >&2
    exit 1
fi
exec "$python" demo/runtime_logging.py -- "$python" demo/server.py "$@"
