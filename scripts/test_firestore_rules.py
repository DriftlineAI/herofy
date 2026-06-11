#!/usr/bin/env python3
"""
Firestore security-rules test (runs against the local Firestore emulator).

Pushes the current firestore.rules to the running emulator, then asserts tenant isolation on the
workspace-keyed collections: only a member (whose token carries the workspace id in the `ws` custom
claim) may read; unauthenticated, non-member, and no-claim callers are denied.

The emulator does not verify token signatures, so we mint unsigned JWTs carrying arbitrary claims
to impersonate principals — the same trick the DataConnect harness uses with `impersonate`.

Usage: python3 scripts/test_firestore_rules.py   (Firestore emulator must be running on :8181)
"""
import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROJ = "herofy-496505"
EMU_HOST = "http://localhost:8181"
DOCS = f"{EMU_HOST}/v1/projects/{PROJ}/databases/(default)/documents"
RULES_FILE = Path(__file__).resolve().parent.parent / "firestore.rules"

WS = "11111111-1111-1111-1111-111111111111"          # test workspace (dashed, matches doc-id format)
OTHER = "22222222-2222-2222-2222-222222222222"


def _b64(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def token(claims: dict) -> str:
    header = _b64({"alg": "RS256", "typ": "JWT"})
    payload = _b64({
        "iss": f"https://securetoken.google.com/{PROJ}", "aud": PROJ,
        "sub": claims.get("sub", "u"), "user_id": claims.get("sub", "u"),
        "iat": 1700000000, "exp": 2000000000,
        "firebase": {"sign_in_provider": "password"}, **claims,
    })
    return f"{header}.{payload}.sig"  # emulator skips signature verification


def _send(method: str, path: str, token_str=None, body=None) -> int:
    req = urllib.request.Request(f"{DOCS}/{path}", method=method,
                                 data=json.dumps(body).encode() if body else None)
    req.add_header("Content-Type", "application/json")
    if token_str:
        req.add_header("Authorization", f"Bearer {token_str}")
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def push_rules() -> bool:
    url = f"{EMU_HOST}/emulator/v1/projects/{PROJ}:securityRules"
    body = {"rules": {"files": [{"name": "firestore.rules", "content": RULES_FILE.read_text()}]}}
    req = urllib.request.Request(url, method="PUT", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=6) as r:
            return r.status == 200
    except Exception as e:  # noqa: BLE001
        print("rules push failed:", e)
        return False


def main():
    if not push_rules():
        print("Could not push rules to emulator (is it running on :8181?)")
        sys.exit(2)

    member = token({"sub": "m", "ws": [WS]})
    nonmember = token({"sub": "o", "ws": [OTHER]})
    noclaim = token({"sub": "n"})
    matrix = [("no-auth", None, 403), ("member", member, 200),
              ("non-member", nonmember, 403), ("no-ws-claim", noclaim, 403)]

    fails = 0
    rows = []

    # workspace-keyed collections
    for coll in ("notifications", "setup_progress"):
        _send("PATCH", f"{coll}/{WS}", "owner", {"fields": {"n": {"integerValue": "1"}}})
        for name, tk, want in matrix:
            got = _send("GET", f"{coll}/{WS}", tk)
            ok = got == want
            fails += not ok
            rows.append(f"  [{'ok ' if ok else 'FAIL'}] {coll:<16} {name:<12} want={want} got={got}")

    # agent_status: keyed by runId, carries a workspaceId field; subcollection gated via parent get()
    run_id = "run-test-0001"
    _send("PATCH", f"agent_status/{run_id}", "owner", {"fields": {"workspaceId": {"stringValue": WS}}})
    _send("PATCH", f"agent_status/{run_id}/outputs/o1", "owner", {"fields": {"t": {"stringValue": "x"}}})
    for name, tk, want in matrix:
        for path, label in ((f"agent_status/{run_id}", "agent_status"),
                            (f"agent_status/{run_id}/outputs/o1", "agent_status/out")):
            got = _send("GET", path, tk)
            ok = got == want
            fails += not ok
            rows.append(f"  [{'ok ' if ok else 'FAIL'}] {label:<16} {name:<12} want={want} got={got}")
    print("\n".join(rows))
    print(f"\n{'PASS' if fails == 0 else 'FAIL'}: {fails} mismatch(es)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
