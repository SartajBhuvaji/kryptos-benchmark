"""Edit distance and the error rates built on it.

Character error rate is the benchmark's primary metric for every solved passage: the
minimum number of single-character edits taking the model's plaintext to the stored
answer, divided by the answer's length. A perfect break is 0.0.
"""

from __future__ import annotations


def levenshtein(a: str, b: str) -> int:
    """Minimum single-character insertions, deletions and substitutions between two strings.

    >>> levenshtein("kitten", "sitting")
    3
    """
    try:
        from rapidfuzz.distance import Levenshtein
    except ImportError:
        pass
    else:
        return Levenshtein.distance(a, b)

    # Pure-Python fallback so the script runs without rapidfuzz. Two rows only --
    # K2 is 372x372, which is trivial, but there is no reason to hold the full matrix.
    if not a:
        return len(b)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein distance normalised by reference length. 0.0 is a perfect break.

    Not clamped to 1.0: a hypothesis longer than the reference can exceed it, and that
    is worth seeing rather than hiding.

    >>> character_error_rate("ABCDE", "ABXDE")
    0.2
    """
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return levenshtein(reference, hypothesis) / len(reference)
