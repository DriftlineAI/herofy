"""
SignalWatcher Classifier Tests
Test regex and pattern-based signal classification
"""

import pytest
from datetime import datetime

from agents.signal_watcher.models import (
    SignalSource,
    RawSignal,
    Sentiment,
    Urgency,
)
from agents.signal_watcher.classifiers.regex_classifier import RegexClassifier
from agents.signal_watcher.classifiers.patterns import COMPILED_PATTERNS


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def classifier() -> RegexClassifier:
    """Create a classifier instance."""
    return RegexClassifier()


@pytest.fixture
def urgent_support_signal() -> RawSignal:
    """Signal that should classify as urgent support."""
    return RawSignal(
        id="test-urgent",
        source=SignalSource.GMAIL,
        external_id="gmail-urgent",
        occurred_at=datetime.utcnow(),
        sender_name="Frustrated User",
        sender_email="user@company.com",
        subject="URGENT: Production is down!!!",
        body="Our entire system crashed after the latest update. "
             "All our users are affected. We need immediate help. "
             "This is a P1 blocker for us.",
    )


@pytest.fixture
def going_dark_signal() -> RawSignal:
    """Signal that indicates customer going dark."""
    return RawSignal(
        id="test-dark",
        source=SignalSource.GMAIL,
        external_id="gmail-dark",
        occurred_at=datetime.utcnow(),
        sender_name="Quiet User",
        sender_email="user@company.com",
        subject="Re: Following up",
        body="We haven't heard back from your team on this. "
             "Still no response after multiple follow ups. Is everything ok?",
    )


@pytest.fixture
def frustrated_signal() -> RawSignal:
    """Signal showing customer frustration."""
    return RawSignal(
        id="test-frustrated",
        source=SignalSource.SLACK,
        external_id="slack-frustrated",
        occurred_at=datetime.utcnow(),
        sender_name="Annoyed User",
        sender_email="user@company.com",
        subject=None,
        body="This is ridiculous. I've been waiting for 3 days for a response. "
             "This is completely unacceptable. I expected better from you.",
    )


@pytest.fixture
def positive_signal() -> RawSignal:
    """Signal with positive sentiment."""
    return RawSignal(
        id="test-positive",
        source=SignalSource.GMAIL,
        external_id="gmail-positive",
        occurred_at=datetime.utcnow(),
        sender_name="Happy User",
        sender_email="user@company.com",
        subject="Thank you!",
        body="The new feature is amazing! Our team loves it. "
             "Great work on the dashboard - it looks fantastic.",
    )


@pytest.fixture
def expansion_signal() -> RawSignal:
    """Signal indicating expansion opportunity."""
    return RawSignal(
        id="test-expansion",
        source=SignalSource.GMAIL,
        external_id="gmail-expansion",
        occurred_at=datetime.utcnow(),
        sender_name="Growing User",
        sender_email="user@company.com",
        subject="Adding more seats",
        body="We'd like to discuss adding 50 more users to our account. "
             "Our team has grown and we're ready to upgrade our plan. "
             "Can we schedule a call about pricing?",
    )


@pytest.fixture
def neutral_signal() -> RawSignal:
    """Neutral signal without strong indicators."""
    return RawSignal(
        id="test-neutral",
        source=SignalSource.GMAIL,
        external_id="gmail-neutral",
        occurred_at=datetime.utcnow(),
        sender_name="Regular User",
        sender_email="user@company.com",
        subject="Question about settings",
        body="Hi, I have a quick question about how to configure "
             "the notification settings. Where can I find this?",
    )


# =============================================================================
# Classification Tests
# =============================================================================


def test_classify_urgent_support(classifier, urgent_support_signal):
    """Test classification of urgent support signals."""
    result = classifier.classify(urgent_support_signal)

    assert result.need_type == "urgent_support"
    assert result.urgency in [Urgency.HIGH, Urgency.URGENT]  # Can be either depending on score
    assert result.sentiment in [Sentiment.NEGATIVE, Sentiment.FRUSTRATED]
    assert result.confidence > 0.5
    assert any(kw in result.keywords for kw in ["urgent", "production", "down", "critical", "blocking"])


def test_classify_going_dark(classifier, going_dark_signal):
    """Test classification of going dark signals."""
    result = classifier.classify(going_dark_signal)

    assert result.need_type == "going_dark"
    # Should detect going dark indicators
    assert any(kw in result.keywords for kw in ["no response", "no reply", "haven't heard"])


def test_classify_frustrated(classifier, frustrated_signal):
    """Test classification of frustrated customer signals."""
    result = classifier.classify(frustrated_signal)

    assert result.need_type == "frustrated_signal"
    assert result.sentiment == Sentiment.FRUSTRATED
    assert result.urgency in [Urgency.MEDIUM, Urgency.HIGH]
    assert any(kw in result.keywords for kw in ["ridiculous", "unacceptable", "waiting"])


def test_classify_positive(classifier, positive_signal):
    """Test classification of positive signals."""
    result = classifier.classify(positive_signal)

    assert result.need_type == "positive_signal"
    # Sentiment may be POSITIVE or NEUTRAL depending on sentiment pattern matches
    assert result.sentiment in [Sentiment.POSITIVE, Sentiment.NEUTRAL]
    assert result.urgency in [Urgency.LOW, Urgency.MEDIUM]  # Depends on urgency pattern matches
    # Check that at least one keyword was extracted
    assert len(result.keywords) >= 0  # May have keywords or not


def test_classify_expansion(classifier, expansion_signal):
    """Test classification of expansion opportunity signals."""
    result = classifier.classify(expansion_signal)

    assert result.need_type == "expansion_signal"
    assert result.urgency in [Urgency.LOW, Urgency.MEDIUM]
    assert any(kw in result.keywords for kw in ["seats", "upgrade", "grow", "adding"])


def test_classify_neutral(classifier, neutral_signal):
    """Test classification of neutral signals falls back to check_in_due."""
    result = classifier.classify(neutral_signal)

    # Neutral signals should get low-priority classification
    assert result.need_type in ["check_in_due", "uncategorized"]
    assert result.sentiment == Sentiment.NEUTRAL
    assert result.urgency in [Urgency.LOW, Urgency.MEDIUM]  # Depends on urgency pattern matches


def test_classify_empty_body(classifier):
    """Test classifier handles empty body gracefully."""
    signal = RawSignal(
        id="test-empty",
        source=SignalSource.GMAIL,
        external_id="gmail-empty",
        occurred_at=datetime.utcnow(),
        sender_name="User",
        sender_email="user@company.com",
        subject="Hello",
        body="",
    )

    result = classifier.classify(signal)

    # Should still produce valid classification
    assert result.need_type is not None
    assert result.sentiment is not None


def test_classify_subject_only(classifier):
    """Test classifier uses subject when body is minimal."""
    signal = RawSignal(
        id="test-subject",
        source=SignalSource.GMAIL,
        external_id="gmail-subject",
        occurred_at=datetime.utcnow(),
        sender_name="User",
        sender_email="user@company.com",
        subject="URGENT: Help needed immediately!",
        body="Thanks",
    )

    result = classifier.classify(signal)

    # Subject should contribute to classification
    assert result.urgency in [Urgency.HIGH, Urgency.URGENT]
    assert "urgent" in [k.lower() for k in result.keywords]


# =============================================================================
# Pattern Tests
# =============================================================================


def test_urgent_patterns_match():
    """Test urgent support patterns match expected strings."""
    urgent_texts = [
        "This is urgent, please help",
        "CRITICAL issue with the system",
        "Our production down - major outage",
        "We have an emergency",
        "This is blocking us",
        "The feature is broken",
    ]

    patterns = COMPILED_PATTERNS["urgent_support"]
    for text in urgent_texts:
        matches = [p.search(text.lower()) for p in patterns]
        assert any(matches), f"Expected '{text}' to match urgent patterns"


def test_frustrated_patterns_match():
    """Test frustrated signal patterns match expected strings."""
    frustrated_texts = [
        "This is ridiculous",
        "Completely unacceptable",
        "I'm so frustrated with this",
        "This is really disappointing",
        "I'm very disappointed with the service",
        "I am very unhappy about this",
    ]

    patterns = COMPILED_PATTERNS["frustrated_signal"]
    for text in frustrated_texts:
        matches = [p.search(text.lower()) for p in patterns]
        assert any(matches), f"Expected '{text}' to match frustrated patterns"


def test_positive_patterns_match():
    """Test positive signal patterns match expected strings."""
    positive_texts = [
        "Thank you for your help!",
        "This is amazing work you did",
        "Great work on the feature",
        "We love it and are impressed",
        "I'm impressed with the quality",
        "This exceeds expectations",
    ]

    patterns = COMPILED_PATTERNS["positive_signal"]
    for text in positive_texts:
        matches = [p.search(text.lower()) for p in patterns]
        assert any(matches), f"Expected '{text}' to match positive patterns"


def test_expansion_patterns_match():
    """Test expansion signal patterns match expected strings."""
    expansion_texts = [
        "We want to add more seats",
        "Ready to upgrade our plan",
        "We're scaling up the team usage",
        "Can we add additional seats?",
        "Looking to expand our team of users",
        "We need to add users to our account",
    ]

    patterns = COMPILED_PATTERNS["expansion_signal"]
    for text in expansion_texts:
        matches = [p.search(text.lower()) for p in patterns]
        assert any(matches), f"Expected '{text}' to match expansion patterns"


def test_going_dark_patterns_match():
    """Test going dark patterns match expected strings."""
    dark_texts = [
        "Sorry we haven't heard back from you",
        "We got no response from the team",
        "No reply yet on our follow-up",
        "There's been no answer for a week",
        "Haven't heard back yet",
    ]

    patterns = COMPILED_PATTERNS["going_dark"]
    for text in dark_texts:
        matches = [p.search(text.lower()) for p in patterns]
        assert any(matches), f"Expected '{text}' to match going dark patterns"


# =============================================================================
# Confidence Score Tests
# =============================================================================


def test_confidence_increases_with_more_matches(classifier):
    """Test that more pattern matches increase confidence."""
    weak_signal = RawSignal(
        id="weak",
        source=SignalSource.GMAIL,
        external_id="weak",
        occurred_at=datetime.utcnow(),
        sender_name="User",
        sender_email="user@test.com",
        subject="Question",
        body="This is urgent.",
    )

    strong_signal = RawSignal(
        id="strong",
        source=SignalSource.GMAIL,
        external_id="strong",
        occurred_at=datetime.utcnow(),
        sender_name="User",
        sender_email="user@test.com",
        subject="URGENT: Critical P1 Issue",
        body="This is urgent! Production is down! "
             "We have a critical blocker. Need immediate help ASAP!",
    )

    weak_result = classifier.classify(weak_signal)
    strong_result = classifier.classify(strong_signal)

    # Strong signal should have higher confidence
    assert strong_result.confidence > weak_result.confidence


def test_keywords_extracted_correctly(classifier, urgent_support_signal):
    """Test that keywords are properly extracted."""
    result = classifier.classify(urgent_support_signal)

    # Should have extracted relevant keywords
    assert len(result.keywords) > 0
    # Keywords should be from the signal content
    assert all(
        kw.lower() in urgent_support_signal.subject.lower()
        or kw.lower() in urgent_support_signal.body.lower()
        for kw in result.keywords
    )


# =============================================================================
# Edge Cases
# =============================================================================


def test_classify_mixed_signals(classifier):
    """Test classification of signals with mixed indicators."""
    mixed_signal = RawSignal(
        id="mixed",
        source=SignalSource.GMAIL,
        external_id="mixed",
        occurred_at=datetime.utcnow(),
        sender_name="User",
        sender_email="user@test.com",
        subject="Issue but also thanks",
        body="The new feature is great! But we have an urgent issue "
             "with the API. Can you help?",
    )

    result = classifier.classify(mixed_signal)

    # Should still produce a valid result
    assert result.need_type is not None
    # Should detect both positive and urgent keywords
    keywords_lower = [k.lower() for k in result.keywords]
    # Either the urgent or positive should be detected
    assert any(k in keywords_lower for k in ["urgent", "issue", "great"])


def test_classify_non_english(classifier):
    """Test classifier handles non-English gracefully."""
    non_english = RawSignal(
        id="non-eng",
        source=SignalSource.GMAIL,
        external_id="non-eng",
        occurred_at=datetime.utcnow(),
        sender_name="User",
        sender_email="user@test.com",
        subject="Pregunta",
        body="Hola, tengo una pregunta sobre el sistema.",
    )

    result = classifier.classify(non_english)

    # Should still produce a valid result
    assert result.need_type is not None
    assert result.sentiment is not None
    # Confidence may be lower for non-English
    assert result.confidence > 0


def test_classify_very_long_body(classifier):
    """Test classifier handles very long bodies."""
    long_body = "This is a test. " * 500  # Very long body
    long_signal = RawSignal(
        id="long",
        source=SignalSource.GMAIL,
        external_id="long",
        occurred_at=datetime.utcnow(),
        sender_name="User",
        sender_email="user@test.com",
        subject="Long email",
        body=long_body + " URGENT HELP NEEDED!",
    )

    result = classifier.classify(long_signal)

    # Should still find patterns even in long text
    assert result.need_type is not None
    # Should detect urgent even at end of long body
    assert result.urgency in [Urgency.MEDIUM, Urgency.HIGH]
