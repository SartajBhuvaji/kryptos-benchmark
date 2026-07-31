"""Quadgram fitness -- how English-like a candidate plaintext is.

CER answers "is this the answer", which needs the answer. This answers "is this English",
which does not, and that is what makes it useful where CER cannot go: judging whether a
partial break is a real foothold or a coincidence, ranking hill-climbing candidates, and
saying something quantitative about a K4 hypothesis that has no reference plaintext.

The measure is the log10 probability of the text under a quadgram model. Each overlapping
four-letter window contributes ``log10(count / total)``; the sum is the text's score.
Quadgrams the corpus never saw get a floor of ``log10(0.01 / total)`` -- a value below the
rarest observed quadgram, so unseen sequences are penalised heavily but not infinitely.
Without a floor a single impossible quadgram would send the whole score to negative
infinity and destroy any ordering between two bad candidates.

Fitness scales with length, so :meth:`QuadgramModel.fitness` divides by the number of
windows -- Kryptos passages span 63 to 869 characters, and a raw sum would rank the long
ones worst regardless of content. Measured against this table, the per-quadgram mean runs
about -4.0 to -4.2 for ordinary English prose, -4.1 to -4.4 for the Kryptos plaintexts,
and around -6.2 for uniformly random letters. The gap of roughly two log units is the
signal; the absolute values mean nothing on their own and shift with any other table.

The table itself is documented in ``data/PROVENANCE.md``.
"""

from __future__ import annotations

import functools
import gzip
import math
import pathlib

#: Overlapping window size. Named rather than inlined -- the floor, the minimum text
#: length and the window count all depend on it agreeing with the table.
ORDER = 4

TABLE = pathlib.Path(__file__).resolve().parent / "data" / "english_quadgrams.txt.gz"

#: Weight given to a quadgram the corpus never observed, as a fraction of one observation.
#: The conventional choice for this table; low enough to punish, finite enough to rank.
UNSEEN_WEIGHT = 0.01


class QuadgramModel:
    """Log10 probabilities for every quadgram in a frequency table.

    Construct from :func:`load` rather than directly unless you are testing with a
    deliberately small table.
    """

    def __init__(self, counts: dict[str, int]) -> None:
        if not counts:
            raise ValueError("quadgram model needs a non-empty table")
        total = sum(counts.values())
        self.total = total
        self.log_probability = {
            quadgram: math.log10(count / total) for quadgram, count in counts.items()
        }
        self.floor = math.log10(UNSEEN_WEIGHT / total)

    def score(self, text: str) -> float:
        """Total log10 probability of ``text``. More negative is less English-like.

        Scales with length, so it compares candidates *for the same passage*. To compare
        across passages of different length, use :meth:`fitness`.
        """
        if len(text) < ORDER:
            return 0.0
        return sum(
            self.log_probability.get(text[i : i + ORDER], self.floor)
            for i in range(len(text) - ORDER + 1)
        )

    def fitness(self, text: str) -> float:
        """Mean log10 probability per quadgram -- the length-independent form.

        Returns :attr:`floor` for text shorter than one window, which is the correct
        limit: nothing has been observed, so nothing is better than unseen.
        """
        windows = len(text) - ORDER + 1
        if windows < 1:
            return self.floor
        return self.score(text) / windows


def parse(table: str) -> dict[str, int]:
    """Parse the upstream format: ``QUADGRAM count``, one per line."""
    counts: dict[str, int] = {}
    for line in table.splitlines():
        if not line.strip():
            continue
        quadgram, _, count = line.partition(" ")
        counts[quadgram.strip().upper()] = int(count)
    return counts


@functools.lru_cache(maxsize=1)
def load() -> QuadgramModel:
    """The default model, read from the committed table.

    Cached: parsing 389,373 lines takes a moment and every caller wants the same object.
    """
    if not TABLE.exists():
        raise FileNotFoundError(
            f"missing quadgram table at {TABLE}. Run: "
            "python -m kryptos.scoring.data.build"
        )
    return QuadgramModel(parse(gzip.decompress(TABLE.read_bytes()).decode("ascii")))


def fitness(text: str) -> float:
    """Mean log10 quadgram probability of ``text`` under the default model.

    Expects normalised text -- see :func:`kryptos.scoring.text.letters_only`.
    """
    return load().fitness(text)


def score(text: str) -> float:
    """Total log10 quadgram probability of ``text`` under the default model."""
    return load().score(text)
