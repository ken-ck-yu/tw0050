"""Command line (docs/specs/m0_specs.md section 9). No command deletes data."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import sys
from datetime import date

from twdata.common import config, paths, state
from twdata.common.errors import exit_code_for

EXIT_OK, EXIT_VERIFY, EXIT_USAGE, EXIT_BLOCKED, EXIT_DRIFT, EXIT_INTERNAL = 0, 1, 2, 3, 4, 5


def discover(package: str = "twdata.ingest") -> tuple[dict, dict]:
    """Return ({dataset: callable}, {module: error}). A module that fails to import is skipped."""
    pkg = importlib.import_module(package)
    errors: dict[str, str] = dict(getattr(pkg, "IMPORT_ERRORS", {}))
    found: dict = {}
    owner: dict[str, str] = {}
    for m in pkgutil.iter_modules(pkg.__path__):
        try:
            mod = importlib.import_module(f"{package}.{m.name}")
        except Exception as e:
            errors[m.name] = f"{type(e).__name__}: {e}"
            continue
        for name, fn in getattr(mod, "DATASETS", {}).items():
            if name in found:
                errors[m.name] = f"duplicate dataset name {name!r} (also in {owner[name]})"
                continue
            found[name] = fn
            owner[name] = m.name
    return found, errors


def _date(text: str) -> date:
    return date.fromisoformat(text)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="twdata")
    ap.add_argument("--data-dir", default=None)
    sub = ap.add_subparsers(dest="command", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--dataset", required=True)
    f.add_argument("--start", required=True, type=_date)
    f.add_argument("--end", required=True, type=_date)
    st = sub.add_parser("status")
    st.add_argument("--dataset")
    st.add_argument("--verify", action="store_true")
    sub.add_parser("limiter-check")
    sub.add_parser("snapshot")
    ru = sub.add_parser("rebuild-universe")
    ru.add_argument("--from", dest="start", required=True, type=_date)
    ru.add_argument("--to", dest="end", required=True, type=_date)
    return ap


def _context(settings, finmind: bool):
    from twdata.clients.context import build_context

    return build_context(settings, finmind=finmind)


def cmd_fetch(a, settings) -> int:
    datasets, errors = discover()
    for mod, err in errors.items():
        print(f"warning: module {mod} skipped: {err}", file=sys.stderr)
    if a.dataset not in datasets:
        if errors:
            print(f"dataset {a.dataset!r} not available; broken modules above", file=sys.stderr)
            return EXIT_INTERNAL
        print(f"unknown dataset {a.dataset!r}; known: {sorted(datasets)}", file=sys.stderr)
        return EXIT_USAGE
    need_finmind = bool(os.environ.get("FINMIND_TOKEN"))
    ctx = _context(settings, need_finmind)
    datasets[a.dataset](ctx, a.start, a.end)
    ctx.cache.flush()
    return EXIT_OK


def _manifest_pairs(settings):
    base = settings.data_dir / "state" / "manifest"
    out = []
    if base.exists():
        for p in sorted(base.rglob("*.jsonl")):
            rel = p.relative_to(base).parts
            if rel[0] == "qa":
                out.append(("qa", rel[1], p.stem))
            else:
                out.append(("raw", rel[0], p.stem))
    return out


def cmd_status(a, settings) -> int:
    entries = state.entries(settings)
    for e in entries:
        if a.dataset and e["dataset"] != a.dataset:
            continue
        if "completed" not in e:
            continue  # side files such as stock_info_duplicates are not progress state
        done = e["completed"]
        text = (
            f"{len(done)} ranges, last {done[-1]}"
            if e["key_type"] == "date" and done
            else (f"{len(done)} stocks" if done else "empty")
        )
        print(f"{e['dataset']}: {text} (updated {e.get('updated_at')})")
    ledger = paths.calendar_ledger(settings)
    if ledger.exists():
        lines = ledger.read_text(encoding="utf-8").splitlines()
        print(f"calendar discrepancies: {len(lines)}")
        for ln in lines[-5:]:
            print("  ", ln)
    manifest = paths.snapshot_dir(settings) / "manifest.jsonl"
    if manifest.exists():
        last = json.loads(manifest.read_text(encoding="utf-8").splitlines()[-1])["fetched_at"]
        age = (date.today() - date.fromisoformat(last[:10])).days
        print(f"last snapshot: {last} ({age} calendar days ago)")
        if age > 3:
            print("warning: last snapshot is more than one trading day old", file=sys.stderr)
    if a.verify:
        from twdata.clients.rawcache import RawCache

        problems = []
        for area, source, dataset in _manifest_pairs(settings):
            cache = RawCache(settings, area=area)
            problems += [(area, source, dataset, p) for p in cache.verify(source, dataset)]
        for e in entries:
            for shard in e.get("shards", []):
                if not list((settings.data_dir / "raw").rglob(shard)):
                    problems.append(("state", e["dataset"], shard, "shard file missing"))
        for p in problems:
            print("PROBLEM", p)
        return EXIT_VERIFY if problems else EXIT_OK
    return EXIT_OK


def cmd_limiter_check(a, settings) -> int:
    ctx = _context(settings, True)
    info = ctx.finmind.user_info()
    rate = info.limit * settings.finmind.target_fraction
    print(
        f"finmind: level={info.level} limit={info.limit}/h used={info.user_count} "
        f"target={rate:.0f}/h"
    )
    print(f"twse spacing {settings.spacing_s.twse}s, tpex spacing {settings.spacing_s.tpex}s")
    return EXIT_OK


def cmd_agent_module(modname: str, func: str, *args) -> int:
    try:
        mod = importlib.import_module(modname)
        fn = getattr(mod, func)
    except (ImportError, AttributeError):
        print("not built yet (milestone M1)", file=sys.stderr)
        return EXIT_INTERNAL
    fn(*args)
    return EXIT_OK


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    try:
        config.load_env()
        settings = config.load_settings(data_dir_override=a.data_dir)
        if a.command == "fetch":
            return cmd_fetch(a, settings)
        if a.command == "status":
            return cmd_status(a, settings)
        if a.command == "limiter-check":
            return cmd_limiter_check(a, settings)
        ctx = _context(settings, False)
        if a.command == "snapshot":
            return cmd_agent_module("twdata.ingest.snapshots", "run", ctx)
        if a.command == "rebuild-universe":
            return cmd_agent_module("twdata.universe.build", "rebuild", ctx, a.start, a.end)
        return EXIT_USAGE
    except SystemExit:
        raise
    except Exception as e:  # map every project exception to its exit code
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return exit_code_for(e)


if __name__ == "__main__":
    raise SystemExit(main())
