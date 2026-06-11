"""
Out-of-office (OOO) detection — a deterministic pre-filter.

An OOO auto-reply to our outbound is one of the few things regex is genuinely good
at, and treating it as a real reply would falsely reset the responsiveness/silence
clock (docs/plans/ENGAGEMENT_HEALTH_MODEL.md). So we detect it deterministically —
never an LLM call — and:
  1. do NOT pair it as a genuine response (the human hasn't engaged),
  2. surface the stated return date and any delegate ("Sarah is covering") so the
     contact graph can be improved opportunistically.

detect_ooo() is pure (no DB / network) and returns an OOOResult.
"""

import re
from dataclasses import dataclass

# Phrases that reliably indicate an auto-reply, not a human response.
_OOO_PATTERNS = [
    r"out of (the )?office",
    r"out-of-office",
    r"\bOOO\b",
    r"on (vacation|holiday|leave|annual leave|parental leave|medical leave)",
    r"away from (my|the) (desk|office)",
    r"(currently|presently) (away|unavailable)",
    r"limited access to (my )?email",
    r"automatic(ally)? repl(y|ies)",
    r"auto[- ]?reply",
    r"will be back (on|in)",
    r"returning (on|to the office)",
    r"back in the office",
]
_OOO_RE = re.compile("|".join(_OOO_PATTERNS), re.IGNORECASE)

# "until <date>" / "back on <date>" / "returning <date>" — capture a coarse date phrase.
_UNTIL_RE = re.compile(
    r"(?:until|through|back(?:\s+in\s+the\s+office)?(?:\s+on)?|returning(?:\s+on)?|return\s+on)\s+"
    r"([A-Z][a-z]+ \d{1,2}(?:,? \d{4})?|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)

# Delegate: "contact <Name>", "reach out to <Name>", "<Name> is covering/handling",
# "in my absence, <Name>", plus an optional email nearby.
_DELEGATE_NAME_RE = re.compile(
    r"(?:please\s+)?(?:contact|reach out to|email|reach)\s+([A-Z][a-z]+(?: [A-Z][a-z]+)?)"
    r"|([A-Z][a-z]+(?: [A-Z][a-z]+)?)\s+(?:is|will be)\s+(?:covering|handling|assisting|the point of contact)"
    r"|in my absence,?\s+(?:please\s+)?(?:contact\s+)?([A-Z][a-z]+(?: [A-Z][a-z]+)?)",
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


@dataclass
class OOOResult:
    """Outcome of detect_ooo()."""

    is_ooo: bool
    until: str | None = None            # raw return-date phrase, if stated
    delegate_name: str | None = None    # covering contact, if named
    delegate_email: str | None = None   # delegate email, if present in the body


def detect_ooo(subject: str | None, body: str | None) -> OOOResult:
    """Detect an OOO auto-reply from an inbound message's subject + body.

    Pure and cheap. Returns is_ooo=False for ordinary replies. When OOO is detected,
    best-effort extracts the return date and a delegate (name + email if present).
    """
    text = f"{subject or ''}\n{body or ''}".strip()
    if not text or not _OOO_RE.search(text):
        return OOOResult(is_ooo=False)

    until = None
    m = _UNTIL_RE.search(text)
    if m:
        until = m.group(1).strip()

    delegate_name = None
    dm = _DELEGATE_NAME_RE.search(text)
    if dm:
        delegate_name = next((g for g in dm.groups() if g), None)

    delegate_email = None
    # Prefer an email that sits near the delegate mention; else the first email present.
    emails = _EMAIL_RE.findall(text)
    if emails:
        delegate_email = emails[0]

    return OOOResult(
        is_ooo=True,
        until=until,
        delegate_name=delegate_name,
        delegate_email=delegate_email,
    )
