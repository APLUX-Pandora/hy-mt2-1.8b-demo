# SPDX-License-Identifier: Apache-2.0
"""Application-owned signal cancellation for synchronous CLI examples."""
from contextlib import contextmanager
import signal
import threading


class StopRequest:
    """Keep the first shutdown signal and expose a document cancellation event."""
    def __init__(self):
        self.cancel = threading.Event()
        self.signum = None

    def request(self, signum, _frame):
        if self.signum is None:
            self.signum = signum
            # Repeated/nested signals must not reenter Event.set's lock.
            self.cancel.set()

    @property
    def exit_code(self):
        return 128 + self.signum if self.signum is not None else 0


@contextmanager
def managed_translator(factory):
    """Own loading, cancellation and close; never abort from a signal callback.

    The caller performs blocking inference in the context's main thread. Signals
    are deferred across native loading/destruction; the watcher inherits the
    blocked mask and repeats abort to cover the SDK start/generate handoff.
    """
    signals = {signal.SIGTERM, signal.SIGINT}
    stop, finished = StopRequest(), threading.Event()
    engine = watcher = None
    synchronous_signals = hasattr(signal, "sigtimedwait")
    mask = signal.pthread_sigmask(signal.SIG_BLOCK, signals)
    previous = {sig: signal.signal(sig, stop.request) for sig in signals}
    try:
        engine = factory()

        def monitor():
            while not finished.is_set():
                if synchronous_signals:
                    pending = signal.sigtimedwait(signals, .05)
                    if pending is not None:
                        stop.request(pending.si_signo, None)
                elif finished.wait(.05):
                    break
                if stop.cancel.is_set():
                    # Keep cancellation retryable; the foreground call reports
                    # native errors and remains the owner until it has returned.
                    try:
                        engine.abort()
                    except RuntimeError:
                        pass

        watcher = threading.Thread(target=monitor, name="translation-cli-cancel")
        watcher.start()
        # Linux vendor callbacks need not run on Python's main thread. Keep
        # signals blocked in inference threads and consume them synchronously
        # in the watcher, without interrupting native RPC or waiting for Python's
        # main-thread signal dispatch. Other hosts only run SDK-double tests.
        if not synchronous_signals:
            signal.pthread_sigmask(signal.SIG_SETMASK, mask)
        yield engine, stop
    finally:
        signal.pthread_sigmask(signal.SIG_BLOCK, signals)
        try:
            finished.set()
            if watcher is not None and watcher.ident is not None:
                watcher.join()
            if engine is not None:
                engine.close()
        finally:
            # This helper is for a CLI that exits after a stop. Retain the
            # blocked stop mask through interpreter shutdown: CPython may reset
            # handlers before exiting, and a late repeated signal must not
            # replace the first signal's exit status after native cleanup.
            if stop.signum is None:
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
