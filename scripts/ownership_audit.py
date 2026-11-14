"""Post-hoc ownership audit (docs/specs/m0_specs.md section 9).

    python scripts/ownership_audit.py --agent A --base <rev> --head <rev>

Lists `git diff --name-only --no-renames <base>...<head>`, reads config/ownership.yaml from
`git show <base>:config/ownership.yaml` (so a branch cannot grant itself paths) and exits 1,
listing every changed path outside the agent's globs. `*` matches within a path segment and
`**` across segments. Audits committed changes only.
"""

import argparse
import re
import subprocess
import sys

import yaml


def glob_to_regex(glob: str) -> re.Pattern:
    out = ""
    i = 0
    while i < len(glob):
        c = glob[i]
        if glob.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif glob.startswith("**", i):
            out += ".*"
            i += 2
        elif c == "*":
            out += "[^/]*"
            i += 1
        elif c == "?":
            out += "[^/]"
            i += 1
        else:
            out += re.escape(c)
            i += 1
    return re.compile("^" + out + "$")


def allowed(path: str, globs: list[str]) -> bool:
    return any(glob_to_regex(g).match(path) for g in globs)


def git(*args: str, cwd: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, cwd=cwd
    ).stdout


def audit(agent: str, base: str, head: str, cwd: str | None = None) -> list[str]:
    cfg = yaml.safe_load(git("show", f"{base}:config/ownership.yaml", cwd=cwd))
    if agent not in cfg:
        raise SystemExit(f"unknown agent {agent!r}; known: {sorted(cfg)}")
    changed = git("diff", "--name-only", "--no-renames", f"{base}...{head}", cwd=cwd).split("\n")
    return [p for p in changed if p and not allowed(p, cfg[agent])]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    a = ap.parse_args()
    bad = audit(a.agent, a.base, a.head)
    if bad:
        print("OUT OF SCOPE for", a.agent)
        for p in bad:
            print("  ", p)
        return 1
    print("ok: all changed paths are within", a.agent, "globs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
