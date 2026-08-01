"""Tier definitions, as data.

The design document states four tiers and three thresholds. Keeping them in one table
rather than scattering literals through prompt builders and report code means the
calibration question stays answerable: these numbers are asserted, not measured, and the
plan says to revisit them against observed score distributions after the first real runs.
When that happens it should be an edit to this file, not a search for stray constants.

Tier 4 deliberately has no threshold, and now that gate 4.1 is settled it still does not
get one. The design document proposes "Normalized Levenshtein > 30%", which cannot be
computed: K4 has 24 known plaintext characters and no reference string, so there is
nothing to measure a ratio against. It is scored instead by crib placement *and* quadgram
fitness reported together -- see :mod:`kryptos.scoring.frontier` for why neither works
alone. No pass mark, because nobody has solved K4 and there is no distribution of
successful attempts to calibrate one against.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tier:
    """One task framing over the benchmark's data.

    Tiers are framings, not datasets -- the same ciphertext can be posed with its keys
    supplied (tier 1) or withheld (tier 2). ``metric`` names a function in this package.
    """

    number: int
    name: str
    capability: str
    metric: str
    #: Pass mark. ``cer`` is an error rate, so lower is better and this is a maximum.
    #: ``None`` means no numeric threshold has been established -- see the module note.
    threshold: float | None
    note: str = ""
    #: Whether the threshold rests on observed score distributions rather than on the
    #: design document's assertion. All four are currently ``False``; the plan lists
    #: recalibrating them after the first real runs as an open risk. A report that prints
    #: thresholds should say which of them have been earned.
    calibrated: bool = False

    def passed(self, score: float) -> bool | None:
        """Whether ``score`` meets this tier's bar, or ``None`` if there is no bar.

        ``None`` is returned rather than ``False`` so a tier that cannot be scored
        numerically is never silently counted as a failure in an aggregate.
        """
        if self.threshold is None:
            return None
        return score <= self.threshold


TIERS: tuple[Tier, ...] = (
    Tier(
        number=1,
        name="Algorithmic identification",
        capability="executing a specified algorithm without arithmetic slips",
        metric="character_error_rate",
        threshold=0.0,
        note="Cipher name and exact keys are supplied. Nothing is being discovered, so "
             "anything short of exact is an execution error.",
    ),
    Tier(
        number=2,
        name="Single-layer cryptanalysis",
        capability="index of coincidence, frequency analysis, hill-climbing",
        metric="character_error_rate",
        threshold=0.05,
        note="Synthetic Quagmire III with no keys given.",
    ),
    Tier(
        number=3,
        name="Geometric transposition",
        capability="spatial reasoning, anagramming, n-gram optimisation",
        metric="character_error_rate",
        threshold=0.10,
        note="Looser than tier 2 because a route error displaces every subsequent "
             "character, so a nearly-right geometry still scores badly under CER.",
    ),
    Tier(
        number=4,
        name="K4 frontier",
        capability="hypothesis generation, matrix algebra",
        metric="frontier_score",
        threshold=None,
        note="No reference plaintext exists, so no CER-style threshold can be computed. "
             "Scored by crib placement and quadgram fitness together: placement alone is "
             "satisfiable by construction, fitness alone says nothing about the cribs. "
             "Reported, never graded -- there is no solved-K4 distribution to calibrate "
             "a pass mark against.",
    ),
)

BY_NUMBER = {tier.number: tier for tier in TIERS}


def tier(number: int) -> Tier:
    """Look up a tier, with a better error than a bare KeyError."""
    try:
        return BY_NUMBER[number]
    except KeyError:
        raise ValueError(
            f"no tier {number}; the benchmark defines {sorted(BY_NUMBER)}"
        ) from None
