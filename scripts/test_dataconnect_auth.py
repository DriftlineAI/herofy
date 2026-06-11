#!/usr/bin/env python3
"""
DataConnect @auth enforcement test (runs against the local emulator).

WHY THIS WORKS LOCALLY: the DataConnect `services:executeGraphql` endpoint bypasses
@auth for the default (admin) context — which is why the Python backend and seeds work
regardless of @auth level. But when the request carries `extensions.impersonate`, the
SAME endpoint ENFORCES @auth (and @check) as that principal. So we can exercise the full
auth matrix — unauthenticated / anonymous / member / non-member / admin — without deploying
and without prod.

Two kinds of operation are tested:

1. LEVEL ops (PUBLIC / USER_ANON / USER / NO_ACCESS) — allow/deny derived purely from the level:
     level                unauth  anon   user   admin
     PUBLIC               allow   allow  allow  allow
     USER_ANON            deny    allow  allow  allow
     USER                 deny    deny   allow  allow
     NO_ACCESS            deny    deny   deny   allow

2. MEMBERSHIP-GATED ops (USER_ANON + a `workspaceMembers ... @check` gate) — these need a real
   (workspace, member) pair, auto-discovered from emulator data. Asserts per-workspace scoping:
     unauth -> deny ;  member of the workspace -> allow ;  non-member -> deny (rolled back).
   Gated mutations are tested on deny paths only (member would actually insert); gated queries
   get the full member/non-member matrix (no side effects).

SAFETY: never executes a mutation as admin, and never executes a gated mutation as the member.

Usage:
  python3 scripts/test_dataconnect_auth.py          # curated representative + all gated ops
  python3 scripts/test_dataconnect_auth.py --all     # every parsable op
"""
import json, re, sys, urllib.request, urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GQL = [REPO / "dataconnect/example/queries.gql", REPO / "dataconnect/example/mutations.gql"]
SCHEMA = REPO / "dataconnect/schema/schema.gql"
# enum name -> first value, so required enum vars can be supplied (else GraphQL rejects the call
# at variable-validation, before @auth runs, which would masquerade as ALLOW).
ENUMS = {m.group(1): m.group(2).split()[0]
         for m in re.finditer(r'enum\s+([A-Za-z0-9_]+)\s*\{([^}]*)\}', SCHEMA.read_text())}
PROJECT, LOCATION, SERVICE = "herofy-496505", "us-central1", "herofy-prod-service"
BASE = f"http://localhost:9399/v1beta/projects/{PROJECT}/locations/{LOCATION}/services/{SERVICE}"

LEVEL_EXPECT = {
    "PUBLIC":    {"unauth": True,  "anon": True,  "user": True,  "admin": True},
    "USER_ANON": {"unauth": False, "anon": True,  "user": True,  "admin": True},
    "USER":      {"unauth": False, "anon": False, "user": True,  "admin": True},
    "NO_ACCESS": {"unauth": False, "anon": False, "user": False, "admin": True},
}
DUMMY = {"UUID": "00000000-0000-0000-0000-000000000000", "String": "t", "Int": "0",
         "Float": "0", "Boolean": "false", "Date": "2026-01-01", "Timestamp": "2026-01-01T00:00:00Z",
         "Int64": "0"}
OP_RE = re.compile(r'\b(query|mutation)\s+([A-Za-z0-9_]+)\s*(\([^)]*\))?\s*@auth\(level:\s*([A-Z_]+)\)', re.DOTALL)


def post(query, variables, impersonate):
    body = {"query": query, "variables": variables}
    if impersonate is not None:
        body["extensions"] = {"impersonate": impersonate}
    req = urllib.request.Request(f"{BASE}:executeGraphql", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode() or "{}")


def verdict(payload):
    blob = json.dumps(payload)
    if "PERMISSION_DENIED" in blob or "@auth rejected" in blob or "aborted" in blob or payload.get("code") in (7, 16):
        return "DENY"
    return "ALLOW"


def extract_block(text, start):
    i = text.index("{", start); depth = 0; j = i
    while j < len(text):
        depth += (text[j] == "{") - (text[j] == "}")
        if depth == 0:
            return text[start:j + 1]
        j += 1
    return None


def parse_params(src):
    out = []
    if src:
        for name, typ in re.findall(r'\$([A-Za-z0-9_]+)\s*:\s*([A-Za-z0-9_\[\]!]+)', src):
            base = typ.strip("[]!")
            out.append((name, base, typ.endswith("!") and "[" not in typ))
    return out


def load_ops():
    ops = {}
    for f in GQL:
        text = f.read_text()
        for m in OP_RE.finditer(text):
            name = m.group(2)
            block = extract_block(text, m.start())
            ops[name] = {"kind": m.group(1), "level": m.group(4), "params": parse_params(m.group(3)),
                         "text": block, "gated": bool(block and "workspaceMembers" in block and "@check" in block)}
    return ops


def dummy_vars(params, overrides):
    v = {}
    for n, t, req in params:
        if n in overrides:
            v[n] = overrides[n]
        elif req and t in DUMMY:
            v[n] = {"Boolean": False, "Int": 0, "Int64": 0, "Float": 0.0}.get(t, DUMMY[t])
        elif req and t in ENUMS:
            v[n] = ENUMS[t]
    return v


def _dash(h):
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}" if "-" not in h and len(h) == 32 else h


def member_fixture():
    """Discover a coherent (workspace, member, customer) triple from emulator data — a customer
    whose workspace has a member — so member-allow works for ops that also gate on $customerId."""
    pl = post("query { customers(limit: 1) { id workspaceId "
              "workspace { workspaceMembers_on_workspace(limit: 1) { userId } } } }", {}, None)
    rows = pl.get("data", {}).get("customers") or []
    for c in rows:
        members = (c.get("workspace") or {}).get("workspaceMembers_on_workspace") or []
        if members:
            return {"workspaceId": _dash(c["workspaceId"]), "member": members[0]["userId"],
                    "customerId": _dash(c["id"])}
    # Fallback: membership only (no customer in any accessible workspace).
    pl = post("query { workspaceMembers(limit: 1) { workspaceId userId } }", {}, None)
    rows = pl.get("data", {}).get("workspaceMembers") or []
    if not rows:
        return None
    return {"workspaceId": _dash(rows[0]["workspaceId"]), "member": rows[0]["userId"], "customerId": None}


def claims(uid):
    return {"authClaims": {"sub": uid, "user_id": uid, "firebase": {"sign_in_provider": "password"}}}


def main():
    ops = load_ops()
    fix = member_fixture()
    print(f"emulator: {BASE}")
    print(f"membership fixture: {fix}\n" if fix else "membership fixture: NONE (gated tests skipped)\n")

    if "--all" in sys.argv:
        names = sorted(ops)
    else:
        names = []
        for lvl in ["PUBLIC", "USER", "NO_ACCESS"]:
            names += [n for n, o in ops.items() if o["level"] == lvl and o["kind"] == "query"
                      and not o["gated"] and all(t in DUMMY for _, t, r in o["params"] if r)][:2]
        names.append("DeleteWorkspacePublic")
        names += [n for n, o in ops.items() if o["gated"]]  # all migrated membership-gated ops

    rows, fails = [], 0

    def check(name, principal, impersonate, want, ov=None):
        nonlocal fails
        op = ops[name]
        got = verdict(post(op["text"], dummy_vars(op["params"], ov or {}), impersonate))
        ok = (got == ("ALLOW" if want else "DENY"))
        fails += (not ok)
        rows.append(f"  [{'ok ' if ok else 'FAIL'}] {op['level']:<10}{'*GATE' if op['gated'] else '':<5} "
                    f"{name:<26} {principal:<10} want={'ALLOW' if want else 'DENY':<5} got={got}")

    for name in dict.fromkeys(names):
        if name not in ops:
            continue
        op = ops[name]
        if op["gated"]:
            if not fix:
                continue
            has_ws = any(n == "workspaceId" for n, _, _ in op["params"])
            has_cust = any(n == "customerId" for n, _, _ in op["params"])
            ov = {}
            if has_ws:
                ov["workspaceId"] = fix["workspaceId"]
            if has_cust and fix.get("customerId"):  # real in-workspace customer for the @check
                ov["customerId"] = fix["customerId"]
            check(name, "unauth", {"unauthenticated": True}, False, ov)              # USER_ANON -> deny
            check(name, "nonmember", claims("zzz-not-a-member"), False, ov)          # @check -> deny
            # member-allow only for direct ($workspaceId) reads; derive-from-parent member-allow
            # needs a real parent id and is validated by the manual probes in this PR.
            if op["kind"] == "query" and has_ws:
                check(name, "member", claims(fix["member"]), True, ov)
        else:
            exp = LEVEL_EXPECT[op["level"]]
            check(name, "unauth", {"unauthenticated": True}, exp["unauth"])
            check(name, "anon", {"authClaims": {"sub": "t-anon", "firebase": {"sign_in_provider": "anonymous"}}}, exp["anon"])
            check(name, "user", claims("t-user"), exp["user"])
            if op["kind"] == "query":                                                # never run mutations as admin
                check(name, "admin", None, exp["admin"])

    print("\n".join(rows))
    print(f"\n{'PASS' if fails == 0 else 'FAIL'}: {fails} mismatch(es)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
