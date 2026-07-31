"""Crib matching -- the only honest metric for an unsolved passage.

K4 has 24 known plaintext characters and no reference string, so character error rate is
undefined for it. What can be measured is whether a proposed plaintext puts Sanborn's
released fragments where he says they go.
"""

from __future__ import annotations


def crib_score(cribs: list[dict], hypothesis: str) -> tuple[int, int]:
    """Return (cribs placed at their exact position, cribs present anywhere).

    K4's only ground truth is 24 characters at known offsets, so this is what can
    honestly be measured. Positions are 1-indexed and inclusive.

    The second figure is the weaker signal and is reported alongside rather than instead:
    a hypothesis containing BERLIN somewhere is doing something, but a hypothesis with
    BERLIN at 64-69 is doing the thing that matters.
    """
    exact = sum(
        1 for c in cribs if hypothesis[c["start"] - 1 : c["end"]] == c["plaintext"]
    )
    anywhere = sum(1 for c in cribs if c["plaintext"] in hypothesis)
    return exact, anywhere
