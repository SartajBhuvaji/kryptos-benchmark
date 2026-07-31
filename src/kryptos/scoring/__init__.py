"""Scoring for the Kryptos benchmark.

Every metric the harness and the tier definitions need, in one place. These started
inside the benchmark runner, where they were fine for a single CER report but could not
be shared with the tier thresholds, the isomorph verification, or the reports in Phase 5.

The split by file is by *what is being measured*, not by caller:

``text``        normalisation every other metric assumes has already happened
``distance``    edit distance and the error rates built on it
``cribs``       partial-credit matching for a passage with no reference plaintext
``statistics``  properties of a ciphertext, independent of any answer
``ngram``       how English-like a candidate is, also independent of any answer
``thresholds``  the tier table, so pass marks are data rather than scattered literals

The last two are the ones that reach where CER cannot. CER needs the answer; index of
coincidence and quadgram fitness need only the text, which is what makes them usable on
a partial break, on a hill-climbing candidate, and on K4.

Import from the package, not the submodules -- the layout below is free to change.
``ngram`` is the exception worth knowing about: it reads a 1.3 MB table off disk on first
use, so it is imported lazily here rather than at package import.
"""

from __future__ import annotations

from kryptos.scoring.cribs import crib_score
from kryptos.scoring.distance import character_error_rate, levenshtein, similarity_ratio
from kryptos.scoring.statistics import (
    ENGLISH_IOC,
    RANDOM_IOC,
    index_of_coincidence,
    letter_frequencies,
)
from kryptos.scoring.text import letters_only
from kryptos.scoring.thresholds import TIERS, Tier, tier

__all__ = [
    "ENGLISH_IOC",
    "RANDOM_IOC",
    "TIERS",
    "Tier",
    "character_error_rate",
    "crib_score",
    "index_of_coincidence",
    "letter_frequencies",
    "letters_only",
    "levenshtein",
    "quadgram_fitness",
    "similarity_ratio",
    "tier",
]


def quadgram_fitness(text: str) -> float:
    """Mean log10 quadgram probability -- how English-like ``text`` reads.

    Thin wrapper so the package's public surface is complete without every import paying
    for the table. See :mod:`kryptos.scoring.ngram`.
    """
    from kryptos.scoring.ngram import fitness

    return fitness(text)
