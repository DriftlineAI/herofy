"""
Signal Matching
Logic for matching signals to existing threads and needs
"""

from .signal_matcher import SignalMatcher
from .similarity import calculate_subject_similarity, levenshtein_distance

__all__ = [
    "SignalMatcher",
    "calculate_subject_similarity",
    "levenshtein_distance",
]
