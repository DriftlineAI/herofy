#!/usr/bin/env python3
"""
Static @auth classification guard (no emulator, no network — pure static analysis).

Enforces the invariant that keeps the security lockdown from breaking the app:

  * HARD FAIL — no `@auth(level: NO_ACCESS)` operation may be referenced anywhere in the
    deployed browser bundle (`frontend/src`). A NO_ACCESS op is admin-only; if the browser
    calls it, the app breaks on deploy. This is the exact regression class that a naive
    single-line / case-sensitive classifier misses (multi-line signatures + camelCase
    callables), so the check parses with a DOTALL signature regex and tests BOTH the
    PascalCase hook name (`use<Name>`) and the camelCase callable (`<name>`).

  * INFO — PUBLIC operations that ARE browser-referenced. These are the Phase C/D backlog
    (to become USER_ANON + membership @check, or route through the backend). Printed, not failed.

Run:  python3 scripts/check_auth_classification.py
Exit: non-zero if any NO_ACCESS op is browser-referenced.
"""
import re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GQL = [REPO / "dataconnect/example/queries.gql", REPO / "dataconnect/example/mutations.gql"]
FRONTEND_SRC = REPO / "frontend/src"

OP_RE = re.compile(r'\b(query|mutation)\s+([A-Za-z0-9_]+)\s*(?:\([^)]*\))?\s*@auth\(level:\s*([A-Z_]+)\)', re.DOTALL)


def load_levels():
    levels = {}
    for f in GQL:
        for m in OP_RE.finditer(f.read_text()):
            levels[m.group(2)] = m.group(3)
    return levels


def frontend_blob():
    parts = []
    for p in FRONTEND_SRC.rglob("*"):
        if p.suffix in (".ts", ".tsx") and "dataconnect-generated" not in p.parts:
            parts.append(p.read_text(errors="ignore"))
    return "\n".join(parts)


def camel(n):
    return n[0].lower() + n[1:]


def main():
    levels = load_levels()
    blob = frontend_blob()
    referenced = {n for n in levels if (n in blob) or (camel(n) in blob)}

    from collections import Counter
    dist = dict(Counter(levels.values()))

    violations = sorted(n for n, l in levels.items() if l == "NO_ACCESS" and n in referenced)
    backlog = sorted(n for n, l in levels.items() if l == "PUBLIC" and n in referenced)

    print(f"operations: {len(levels)}  distribution: {dist}")
    print(f"browser-referenced: {len(referenced)}")
    print(f"PUBLIC & browser-referenced (Phase C/D backlog): {len(backlog)}")
    for n in backlog:
        print(f"    info  {n}")

    if violations:
        print(f"\nFAIL: {len(violations)} NO_ACCESS op(s) referenced by frontend/src (would break the app):")
        for n in violations:
            print(f"    !! {n}")
        sys.exit(1)
    print("\nPASS: 0 NO_ACCESS ops are browser-referenced.")


if __name__ == "__main__":
    main()
