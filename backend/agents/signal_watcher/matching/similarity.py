"""
Similarity Functions
Text similarity algorithms for fuzzy matching
"""

import re
from typing import List


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate the Levenshtein (edit) distance between two strings.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Number of edits needed to transform s1 into s2
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)

    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 otherwise
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def calculate_subject_similarity(subject1: str | None, subject2: str | None) -> float:
    """
    Calculate similarity score between two email subjects.

    Handles common variations:
    - Re:/Fwd: prefixes
    - Case differences
    - Minor word order changes

    Args:
        subject1: First subject line
        subject2: Second subject line

    Returns:
        Similarity score from 0.0 (no match) to 1.0 (exact match)
    """
    if not subject1 or not subject2:
        return 0.0

    # Normalize subjects
    norm1 = _normalize_subject(subject1)
    norm2 = _normalize_subject(subject2)

    if not norm1 or not norm2:
        return 0.0

    # Exact match after normalization
    if norm1 == norm2:
        return 1.0

    # Calculate Levenshtein-based similarity
    distance = levenshtein_distance(norm1, norm2)
    max_len = max(len(norm1), len(norm2))

    # Convert distance to similarity score
    similarity = 1.0 - (distance / max_len)

    # Boost score if key words overlap
    words1 = set(norm1.split())
    words2 = set(norm2.split())

    if len(words1) > 0 and len(words2) > 0:
        word_overlap = len(words1 & words2) / min(len(words1), len(words2))
        # Blend Levenshtein similarity with word overlap
        similarity = (similarity * 0.6) + (word_overlap * 0.4)

    return min(1.0, max(0.0, similarity))


def _normalize_subject(subject: str) -> str:
    """
    Normalize an email subject for comparison.

    Removes:
    - Re:/Fwd: prefixes
    - Extra whitespace
    - Ticket numbers (e.g., [TICKET-123])
    - Case differences
    """
    normalized = subject.lower().strip()

    # Remove Re:/Fwd: prefixes (handles multiple)
    re_fwd_pattern = r"^(re:|fwd:|fw:|\s)+"
    normalized = re.sub(re_fwd_pattern, "", normalized, flags=re.IGNORECASE)

    # Remove ticket numbers like [TICKET-123] or (TKT-456)
    ticket_pattern = r"[\[\(][A-Z]+-\d+[\]\)]"
    normalized = re.sub(ticket_pattern, "", normalized, flags=re.IGNORECASE)

    # Collapse whitespace
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


def extract_key_terms(text: str, min_length: int = 4) -> list[str]:
    """
    Extract key terms from text for matching.

    Filters out common words and short terms.

    Args:
        text: Input text
        min_length: Minimum word length to include

    Returns:
        List of key terms (lowercase)
    """
    # Common stop words to filter
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "over", "after",
        "is", "are", "was", "were", "be", "been", "being", "have", "has",
        "had", "do", "does", "did", "will", "would", "could", "should",
        "this", "that", "these", "those", "it", "its", "they", "them",
        "we", "us", "our", "you", "your", "i", "my", "me", "he", "she",
        "can", "just", "also", "very", "more", "some", "any", "all",
        "please", "thanks", "thank", "hi", "hello", "hey", "regards",
    }

    # Extract words
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())

    # Filter by length and stop words
    key_terms = [
        word for word in words
        if len(word) >= min_length and word not in stop_words
    ]

    # Remove duplicates while preserving order
    seen = set()
    unique_terms = []
    for term in key_terms:
        if term not in seen:
            seen.add(term)
            unique_terms.append(term)

    return unique_terms


def calculate_term_overlap(text1: str, text2: str) -> float:
    """
    Calculate term overlap score between two texts.

    Args:
        text1: First text
        text2: Second text

    Returns:
        Overlap score from 0.0 to 1.0
    """
    terms1 = set(extract_key_terms(text1))
    terms2 = set(extract_key_terms(text2))

    if not terms1 or not terms2:
        return 0.0

    intersection = terms1 & terms2
    union = terms1 | terms2

    # Jaccard similarity
    return len(intersection) / len(union)
