from twdata.research.evaluator import log


def test_frozen_hash():
    names = [p.name for p in log.evaluator_files()]
    assert names == sorted(names)
    assert {"constants.py", "costs.py", "data.py", "engine.py", "log.py", "metrics.py"} <= set(
        names
    )
    assert log.HASH_PATH.exists(), "research/EVALUATOR_SHA256 is missing"
    recorded = log.HASH_PATH.read_text().strip()
    assert log.evaluator_sha256() == recorded, (
        "evaluator files and research/EVALUATOR_SHA256 differ: the evaluator is frozen, "
        "any change needs the author's approval and a new hash"
    )
