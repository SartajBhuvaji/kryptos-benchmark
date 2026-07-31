"""Statistics that describe a ciphertext rather than score an answer.

The index of coincidence is the tier-3 discriminator. A transposition permutes positions
without touching letter identities, so it leaves the letter distribution -- and therefore
the IoC -- exactly where English put it. A polyalphabetic substitution flattens the
distribution toward uniform and drags the IoC down with it. Measuring it is how a solver
decides which family it is looking at before trying anything expensive.
"""

from __future__ import annotations

from collections import Counter

#: IoC of ordinary English text over the 26-letter alphabet.
ENGLISH_IOC = 0.0667

#: IoC of text drawn uniformly at random from 26 letters, i.e. 1/26. A polyalphabetic
#: cipher with a long key approaches this; a monoalphabetic one never does.
RANDOM_IOC = 1 / 26


def index_of_coincidence(text: str) -> float:
    """Probability that two letters drawn without replacement from ``text`` match.

    Expects normalised text -- see :func:`kryptos.scoring.text.letters_only`. Anything
    else is counted as-is, which would quietly include spaces in the denominator.

    Returns 0.0 for fewer than two characters, where the quantity is undefined: there is
    no pair to draw. That is a floor rather than a meaningful value, and callers
    comparing against :data:`ENGLISH_IOC` should have enough text for the comparison to
    mean anything -- a few dozen characters is noisy, and K1's 63 are already marginal.

    >>> round(index_of_coincidence("AAAA"), 4)
    1.0
    >>> index_of_coincidence("ABCD")
    0.0
    """
    n = len(text)
    if n < 2:
        return 0.0
    return sum(c * (c - 1) for c in Counter(text).values()) / (n * (n - 1))


def letter_frequencies(text: str) -> dict[str, float]:
    """Relative frequency of each letter present, descending. Diagnostic, not a score."""
    n = len(text)
    if not n:
        return {}
    counts = Counter(text)
    return {ch: c / n for ch, c in counts.most_common()}
