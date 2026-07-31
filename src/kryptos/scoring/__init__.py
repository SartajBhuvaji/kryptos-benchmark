"""Scoring for the Kryptos benchmark.

Every metric the harness and the tier definitions need, in one place. These started
inside the benchmark runner, where they were fine for a single CER report but could not
be shared with the tier thresholds, the isomorph verification, or the reports in Phase 5.

The split by file is by *what is being measured*, not by caller:

``text``      normalisation every other metric assumes has already happened
``distance``  edit distance and the error rates built on it
``cribs``     partial-credit matching for a passage with no reference plaintext

Import from the package, not the submodules -- the layout below is free to change.
"""

from __future__ import annotations

from kryptos.scoring.cribs import crib_score
from kryptos.scoring.distance import character_error_rate, levenshtein
from kryptos.scoring.text import letters_only

__all__ = [
    "character_error_rate",
    "crib_score",
    "letters_only",
    "levenshtein",
]
