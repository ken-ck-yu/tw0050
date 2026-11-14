import bisect
import multiprocessing

from limiter_worker import worker as _worker

from twdata.clients.limiter import HostLimiter, QuotaLimiter


def test_two_processes_never_overlap_and_respect_gap(tmp_path):
    lock, state, log = tmp_path / "h.lock", tmp_path / "h.json", tmp_path / "log.txt"
    interval = 0.2
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_worker, args=(lock, state, log, interval, 4)) for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    spans = sorted(tuple(map(float, ln.split())) for ln in log.read_text().splitlines())
    assert len(spans) == 8
    for (_, prev_end), (next_start, _) in zip(spans, spans[1:], strict=False):
        assert next_start >= prev_end  # no overlap
        assert next_start - prev_end >= interval - 0.02  # gap from completion


def test_sleep_is_capped_after_clock_jump(tmp_path):
    clock = [1000.0]
    slept = []
    lim = HostLimiter(
        "t", 5.0, tmp_path / "l.lock", tmp_path / "l.json", now=lambda: clock[0], sleep=slept.append
    )
    with lim.slot():
        pass
    assert slept == []  # first call never waits
    clock[0] = 1000.0 - 7200  # wall clock jumps back two hours
    with lim.slot():
        pass
    assert slept == [5.0]  # capped at the interval, not 7205


def test_sleep_waits_only_the_remainder(tmp_path):
    clock = [100.0]
    slept = []
    lim = HostLimiter(
        "t", 5.0, tmp_path / "l.lock", tmp_path / "l.json", now=lambda: clock[0], sleep=slept.append
    )
    with lim.slot():
        pass
    clock[0] = 102.0
    with lim.slot():
        pass
    clock[0] = 200.0
    with lim.slot():
        pass
    assert slept == [3.0]


def test_completion_time_measured_after_request(tmp_path):
    clock = [0.0]
    slept = []
    lim = HostLimiter(
        "t", 5.0, tmp_path / "l.lock", tmp_path / "l.json", now=lambda: clock[0], sleep=slept.append
    )
    with lim.slot():
        clock[0] = 4.0  # the request itself took 4 s
    with lim.slot():
        pass
    assert slept == [5.0]


def _quota(tmp_path, clock, slept, limit=600):
    def sleep(s):
        slept.append(s)
        clock[0] += s

    return QuotaLimiter(
        limit, 0.85, tmp_path / "q.json", tmp_path / "q.lock", now=lambda: clock[0], sleep=sleep
    )


def test_quota_stays_at_or_under_85_percent_in_any_window(tmp_path):
    clock, slept = [10_000.0], []
    q = _quota(tmp_path, clock, slept)
    stamps = []
    for _ in range(1500):
        with q.slot():
            stamps.append(clock[0])
        clock[0] += 1.0
    assert q.cap == 510
    for i, t in enumerate(stamps):
        lo = bisect.bisect_right(stamps, t - 3600.0)
        assert i + 1 - lo <= 510
    assert slept  # it had to wait for the roll-over
    assert stamps[-1] - stamps[0] > 3600


def test_quota_waits_for_rollover_then_proceeds(tmp_path):
    clock, slept = [0.0], []
    q = _quota(tmp_path, clock, slept, limit=10)  # cap 8
    for _ in range(8):
        with q.slot():
            pass
    assert slept == []
    with q.slot():
        pass
    assert slept == [3600.0]
    assert clock[0] == 3600.0


def test_quota_is_persisted_across_instances(tmp_path):
    clock, slept = [0.0], []
    q1 = _quota(tmp_path, clock, slept, limit=10)
    for _ in range(8):
        with q1.slot():
            pass
    q2 = _quota(tmp_path, clock, slept, limit=10)
    with q2.slot():
        pass
    assert slept == [3600.0]


def test_update_counts_server_usage_and_new_limit(tmp_path):
    clock, slept = [0.0], []
    q = _quota(tmp_path, clock, slept, limit=600)
    q.update(100, 85)  # cap becomes 85 and the server already counted 85
    assert q.cap == 85
    with q.slot():
        pass
    assert slept == [3600.0]
