"""Unit tests for the deterministic OOO pre-filter (services/ooo_detection.py)."""

from services.ooo_detection import detect_ooo


def test_plain_reply_is_not_ooo():
    r = detect_ooo("Re: pricing", "Thanks, this looks good — let's proceed next week.")
    assert r.is_ooo is False


def test_classic_ooo_detected():
    r = detect_ooo(
        "Automatic reply: Re: pricing",
        "I am out of the office until March 15 with limited access to email.",
    )
    assert r.is_ooo is True
    assert r.until and "March 15" in r.until


def test_ooo_with_delegate_and_email():
    body = (
        "I'm on vacation and will be back on 03/20. "
        "In my absence, please contact Sarah Chen (sarah.chen@acme.com)."
    )
    r = detect_ooo("Out of Office", body)
    assert r.is_ooo is True
    assert r.delegate_name == "Sarah Chen"
    assert r.delegate_email == "sarah.chen@acme.com"


def test_ooo_covering_phrasing():
    r = detect_ooo("OOO", "I'm away from my desk this week. Bob Tanaka is covering for me.")
    assert r.is_ooo is True
    assert r.delegate_name == "Bob Tanaka"


def test_ooo_without_date_or_delegate():
    r = detect_ooo("Re: check-in", "Currently away and unavailable. Will respond when I return.")
    assert r.is_ooo is True
    assert r.until is None
    assert r.delegate_name is None
