# SPDX-License-Identifier: Apache-2.0
"""Application process wrapper; retain optional raw diagnostics outside delivery."""
import argparse
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

PATHS = re.compile(r"(?<![\w:/])/(?:home|Users|data\d*|root|local|tmp|private|mnt|opt|usr|var|etc|run|source|workspace)(?:/[^\s\"'<>:,]*)?")
PRIVATE_IPS = re.compile(r"\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")

LICENSE_IDS = re.compile(r"(?i)(license ID:\s*)aid[a-z0-9]+")


def sanitize(text):
    return LICENSE_IDS.sub(r"\1<device-license>", PRIVATE_IPS.sub("<private-address>", PATHS.sub("<path>", text)))


def run(command):
    raw = None
    raw_path = os.environ.get("HY_MT2_RAW_LOG")
    if raw_path:
        flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(Path(raw_path).expanduser(), flags, 0o600)
        os.fchmod(fd, 0o600)
        raw = os.fdopen(fd, "w", encoding="utf-8")
    child = None
    stopping_signal = signal.SIGINT
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
    interrupted = False
    def stop(signum, _frame):
        nonlocal stopping_signal, interrupted
        stopping_signal = signum
        if not interrupted:
            interrupted = True
            raise KeyboardInterrupt
    for sig in previous:
        signal.signal(sig, stop)
    try:
        child = subprocess.Popen(command, stderr=subprocess.PIPE, text=True,
                                 encoding="utf-8", errors="replace", start_new_session=True,
                                 env={**os.environ, "HY_MT2_FILTER_WORKER": "1"})
        for line in child.stderr:
            if raw:
                raw.write(line); raw.flush()
            sys.stderr.write(sanitize(line)); sys.stderr.flush()
        return child.wait()
    except KeyboardInterrupt:
        if child is not None and child.poll() is None:
            child.send_signal(stopping_signal)
        # The worker may report partial progress while handling cancellation.
        # Drain those final diagnostics after it exits, before closing the pipe.
        if child is not None:
            for line in child.stderr:
                if raw:
                    raw.write(line); raw.flush()
                sys.stderr.write(sanitize(line)); sys.stderr.flush()
            child.wait()
        return child.returncode if child is not None and child.returncode is not None and child.returncode >= 0 else 128 + stopping_signal
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
        if child is not None:
            child.stderr.close()
            if child.poll() is None:
                child.terminate(); child.wait(timeout=5)
        if raw:
            raw.close()



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required")
    raise SystemExit(run(command))
