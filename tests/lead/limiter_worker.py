"""Child-process body for the two-process limiter test (importable by spawned processes)."""

import time

from twdata.clients.limiter import HostLimiter


def worker(lock_path, state_path, log_path, interval, n):
    lim = HostLimiter("t", interval, lock_path, state_path)
    for _ in range(n):
        with lim.slot():
            start = time.time()
            time.sleep(0.03)
            end = time.time()
        with open(log_path, "a") as f:
            f.write(f"{start} {end}\n")
