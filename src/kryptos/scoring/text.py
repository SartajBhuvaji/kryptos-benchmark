"""Text normalisation shared by every metric.

Scoring compares a model's free-form output against a stored answer, so both sides have
to be reduced to the same alphabet first. Everything downstream -- edit distance, index
of coincidence, n-gram fitness -- assumes it is looking at uppercase A-Z and nothing else.
"""

from __future__ import annotations


def letters_only(text: str) -> str:
    """Uppercase A-Z only.

    Deliberately ASCII-restricted rather than ``str.isalpha``: a model may return
    accented or non-Latin characters, and those must be dropped rather than smuggled
    into an edit distance where they would count as ordinary mismatches. The dataset
    builder has a separate, laxer helper of the same name -- it runs over text that is
    already known-clean, where the distinction cannot arise.

    >>> letters_only("be tween!")
    'BETWEEN'
    >>> letters_only("a?b")
    'AB'
    """
    return "".join(ch for ch in text.upper() if "A" <= ch <= "Z")
