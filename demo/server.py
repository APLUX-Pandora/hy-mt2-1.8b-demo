"""Local-board translation application. One model, one active request."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import os
from pathlib import Path
import queue
import signal
import sys
import threading
import time
import uuid
from flask import Flask, Response, jsonify, request, send_from_directory
from pandora_hy_mt2_1_8b._native import resolve_model_dir
from pandora_hy_mt2_1_8b._native import TranslationError
from translation import Translator
from pandora_hy_mt2_1_8b import Runtime
from cpu_options import add_cpu_argument
from long_text import translate_document

ROOT = Path(__file__).resolve().parent


def make_app(translator, timeout=120, stopping=None, factory=None):
    app = Flask(__name__, static_folder=str(ROOT / "static"))
    app.config["MAX_CONTENT_LENGTH"] = 262144
    stopping = stopping if stopping is not None else threading.Event()
    busy = threading.Lock()
    jobs_lock = threading.Lock()
    jobs = {}
    info = dict(translator.info)
    model_state = "ready"
    lifecycle = None
    samples = json.loads((ROOT / "samples.json").read_text())

    @app.get("/long")
    @app.get("/")
    def index():
        return send_from_directory(ROOT / "static", "index.html")

    @app.get("/api/info")
    def capabilities():
        return jsonify({**info, "busy": busy.locked(), "model_state": model_state,
                        "reload_available": factory is not None, "request_timeout": timeout,
                        "long_timeout": max(timeout, 600), "max_characters": 2000, "samples": samples,
                        "max_long_characters": 20000, "long_samples": json.loads((ROOT / "long_samples.json").read_text())})

    def replace_model():
        nonlocal translator, info
        # Keep ownership on a close failure; never create a second native owner.
        if translator is not None:
            translator.close()
            translator = None
        if stopping.is_set():
            raise RuntimeError("Service is stopping")
        translator = factory()
        info = dict(translator.info)

    @app.post("/api/model/reload")
    def reload_model():
        nonlocal model_state, lifecycle
        if stopping.is_set():
            return jsonify(error="Service is stopping"), 503
        if factory is None:
            return jsonify(error="Model reload is unavailable; restart the service"), 503
        if not busy.acquire(blocking=False):
            return jsonify(error="Wait for the current translation or reload to finish"), 409
        try:
            if stopping.is_set():
                return jsonify(error="Service is stopping"), 503
            model_state = "reloading"
            if lifecycle is None:
                # Reuse one lifecycle thread instead of retaining a new native allocator
                # arena for each short-lived HTTP request thread.
                lifecycle = ThreadPoolExecutor(max_workers=1, thread_name_prefix="model-lifecycle")
            lifecycle.submit(replace_model).result()
            model_state = "ready"
            return jsonify(ok=True, model_state=model_state)
        except Exception:
            model_state = "failed"
            app.logger.error("Model reload failed")
            app.logger.debug("Model reload diagnostic", exc_info=True)
            return jsonify(error="Model reload failed. Check device resources, then reload again or restart the service.", model_state=model_state), 503
        finally:
            busy.release()

    @app.post("/api/jobs")
    def create_job():
        if stopping.is_set():
            return jsonify(error="Service is stopping"), 503
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="Expected a JSON object"), 400
        text, source, target = data.get("text"), data.get("source"), data.get("target")
        mode = data.get("mode", "short")
        if mode not in ("short", "long"):
            return jsonify(error="Choose short or long translation mode"), 400
        limit = 20000 if mode == "long" else 2000
        if not isinstance(text, str) or not text.strip() or len(text) > limit or "\x00" in text:
            return jsonify(error=f"Enter 1–{limit:,} characters"), 400
        if "<｜" in text or "<|im_" in text:
            return jsonify(error="Model control markers are not accepted in source text"), 400
        if not isinstance(source, str) or not isinstance(target, str) or source not in info["languages"] or target not in info["languages"] or source == target:
            return jsonify(error="Choose two different supported languages"), 400
        if not busy.acquire(blocking=False):
            return jsonify(error="Another translation is running. Please try again when it finishes."), 409
        if model_state != "ready":
            busy.release()
            return jsonify(error="The model needs reloading before another translation.", model_state=model_state), 503
        job = {"id": uuid.uuid4().hex, "events": queue.Queue(), "cancel": threading.Event(),
               "finished": threading.Event(), "deadline": time.monotonic() + timeout,
               "reason": "Stopped", "created": time.monotonic(),
               "subscribe_deadline": time.monotonic() + 15,
               "total_deadline": time.monotonic() + max(timeout, 600) if mode == "long" else time.monotonic() + timeout}
        with jobs_lock:
            if stopping.is_set():
                busy.release()
                return jsonify(error="Service is stopping"), 503
            for key in list(jobs):
                if jobs[key]["finished"].is_set() and (len(jobs) >= 20 or time.monotonic() - jobs[key]["created"] > 600):
                    del jobs[key]
            jobs[job["id"]] = job

        def watchdog():
            while not job["finished"].wait(0.05):
                if not job.get("subscribed") and time.monotonic() > job["subscribe_deadline"]:
                    job["reason"] = "Translation stream was not connected"
                    job["cancel"].set()
                if time.monotonic() > min(job["deadline"], job["total_deadline"]):
                    job["reason"] = "Translation timed out"
                    job["cancel"].set()
                if job["cancel"].is_set():
                    try:
                        translator.abort()
                    except TranslationError:
                        pass

        def worker():
            nonlocal model_state
            monitor = threading.Thread(target=watchdog, daemon=True)
            monitor.start()
            try:
                if mode == "long":
                    def before_segment():
                        job["deadline"] = time.monotonic() + timeout
                    result = translate_document(translator, text, source, target,
                        lambda kind, value: job["events"].put((kind, value)), job["cancel"], before_segment)
                else:
                    if translator.count_prompt_tokens(text, source, target) > 2048:
                        raise TranslationError(-1, "Short text exceeds the 2048 prompt-token budget; use Long text")
                    result = translator.translate(text, source, target,
                        on_chunk=lambda chunk: job["events"].put(("delta", {"text": chunk})))
                if result["cancelled"]:
                    result["message"] = job["reason"]
                job["events"].put(("done", result))
            except Exception as exc:
                code = exc.code if isinstance(exc, TranslationError) else -5
                if code == -1:
                    app.logger.info("Translation request rejected (code %s)", code)
                else:
                    app.logger.error("Translation job failed (code %s)", code)
                    app.logger.debug("Translation diagnostic", exc_info=True)
                if code != -1:
                    model_state = "failed"
                message = str(exc) if code == -1 else "Translation failed. Reload the model before translating again."
                job["events"].put(("error", {"error": message, "code": code, "model_state": model_state}))
            finally:
                job["finished"].set()
                monitor.join()
                busy.release()

        job["worker"] = threading.Thread(target=worker, name="translation-job")
        job["worker"].start()
        return jsonify(id=job["id"]), 202

    @app.get("/api/jobs/<identifier>/events")
    def events(identifier):
        with jobs_lock:
            job = jobs.get(identifier)
        if job is None:
            return jsonify(error="Translation not found"), 404
        # Each stream has one consumer. Reconnection must not consume another stream's events.
        with jobs_lock:
            if job.get("subscribed"):
                return jsonify(error="Translation stream already opened"), 409
            job["subscribed"] = True

        def stream():
            terminal = False
            try:
                yield ": connected\n\n"
                while True:
                    try:
                        kind, data = job["events"].get(timeout=10)
                    except queue.Empty:
                        if job["finished"].is_set():
                            return
                        yield "event: keep-alive\ndata: {}\n\n"
                        continue
                    terminal = kind in ("done", "error")
                    yield "event: " + kind + "\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"
                    if terminal:
                        return
            finally:
                if not terminal and not job["finished"].is_set():
                    job["cancel"].set()
        return Response(stream(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/jobs/<identifier>/cancel")
    def cancel(identifier):
        with jobs_lock:
            job = jobs.get(identifier)
        if job is None:
            return jsonify(error="Translation not found"), 404
        job["cancel"].set()
        return jsonify(ok=True)

    def stop_jobs(wait=False):
        stopping.set()
        with jobs_lock:
            pending = list(jobs.values())
        for job in pending:
            if not job["finished"].is_set():
                job["cancel"].set()
        if wait:
            for job in pending:
                worker = job.get("worker")
                if worker is not None:
                    worker.join()

    def release_owner():
        nonlocal translator
        if translator is not None:
            translator.close()
            translator = None

    def close_model():
        nonlocal lifecycle
        if lifecycle is None:
            release_owner()
        else:
            try:
                lifecycle.submit(release_owner).result()
            finally:
                lifecycle.shutdown(wait=True)
                lifecycle = None

    app.extensions["translation_close"] = close_model
    app.extensions["translation_shutdown"] = stop_jobs
    return app


def serve(factory, host, port, timeout=120, level="WARNING"):
    """Stop admission, join handlers and jobs, then release the native owner."""
    from werkzeug.serving import ThreadedWSGIServer, WSGIRequestHandler

    class RequestHandler(WSGIRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

    class Server(ThreadedWSGIServer):
        daemon_threads = False
        block_on_close = True

    stopping, finished = threading.Event(), threading.Event()
    engine = app = server = watcher = None
    stop_requested = False

    def stop(_signum, _frame):
        nonlocal stop_requested
        stop_requested = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}

    def shutdown():
        while not finished.wait(.05):
            if stop_requested:
                stopping.set()
                app.extensions["translation_shutdown"]()
                server.shutdown()
                return

    try:
        print(json.dumps({"translation_loading": True}), flush=True)
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, previous)
        try:
            engine = factory()
        finally:
            # A pending signal may run only after the returned native handle has an owner.
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        if stop_requested:
            return
        app = make_app(engine, timeout, stopping, factory=factory)
        app.logger.setLevel(getattr(logging, level))
        server = Server(host, port, app, handler=RequestHandler)
        print(json.dumps({"translation_ready": True}), flush=True)
        watcher = threading.Thread(target=shutdown, name="translation-shutdown")
        watcher.start()
        server.serve_forever(poll_interval=.1)
    finally:
        try:
            stopping.set()
            if app is not None:
                app.extensions["translation_shutdown"]()
            if server is not None:
                server.server_close()
            if app is not None:
                app.extensions["translation_shutdown"](wait=True)
            finished.set()
            if watcher is not None:
                watcher.join()
            if app is not None:
                app.extensions["translation_close"]()
                print(json.dumps({"translation_closed": True}), flush=True)
            elif engine is not None:
                engine.close()
                print(json.dumps({"translation_closed": True}), flush=True)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", "--model-dir", dest="model_dir", help="Package root; default: HY_MT2_MODELS or the unique package in this checkout's models/")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=51106)
    parser.add_argument("--timeout", type=float, default=120)
    add_cpu_argument(parser)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    level = os.environ.get("HY_MT2_LOG_LEVEL", "WARNING").upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        parser.error("HY_MT2_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
    try:
        model_dir = resolve_model_dir(args.model_dir, default_container=ROOT.parent / "models")
        print(f"Model package: {model_dir}", file=sys.stderr)
        with Runtime(cpu=args.cpu_affinity) as runtime:
            serve(lambda: Translator(model_dir, max_input_tokens=2048,runtime=runtime), args.host, args.port, args.timeout, level)
    except TranslationError as exc:
        parser.exit(1, f"Model setup failed (code {exc.code}): {exc}\n")
