from datetime import date

from world import World, flat, weekdays

DAYS = weekdays(date(2023, 1, 2), 30)
A, B = "1111", "2222"


def make_world(tmp_path, n=4, with_bench=True):
    days = DAYS[:n]
    w = World(tmp_path, days)
    if with_bench:
        w.add("0050", flat(100.0, days))
    return w
