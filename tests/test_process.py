import os
import threading
import time

import psutil

from browserbout.metrics.process import sample


def test_sample_measures_cpu_with_fresh_process_objects() -> None:
    # Return new Process objects on every call, like Process.children() does.
    def get_procs() -> list[psutil.Process]:
        return [psutil.Process(os.getpid())]

    stop = threading.Event()

    def burn() -> None:
        while not stop.is_set():
            sum(range(10_000))

    worker = threading.Thread(target=burn)
    worker.start()
    try:
        time.sleep(0.05)
        result = sample(get_procs, 0.5)
    finally:
        stop.set()
        worker.join()
    assert result.cpu_percent > 10
    assert result.memory_mb > 0
    assert result.process_count == 1
