"""Scoring for a passage with no reference plaintext -- in practice, K4.

Character error rate needs an answer. K4 has 24 known plaintext characters out of 97 and
no reference string, so the design document's proposed "Normalized Levenshtein > 30%"
cannot be computed at all: there is nothing to measure a ratio against.

What replaces it is two numbers reported side by side, and no pass mark.

Why not cribs alone
-------------------
Crib placement is objective and already implemented, but on its own it is trivially
gameable. A hypothesis can place ``EAST`` at 22-25, ``NORTHEAST`` at 26-34, ``BERLIN`` at
64-69 and ``CLOCK`` at 70-74 by construction, fill the remaining 73 characters with
noise, and score a perfect 4/4 having done no cryptanalysis whatsoever. A metric that
cannot separate that from a real partial break is not measuring the thing tier 4 exists
to measure.

Quadgram fitness closes the hole from the other side: it asks whether the *rest* of the
proposed plaintext reads as English, which construction-by-crib does not achieve. Neither
number is sufficient alone; together they are hard to satisfy without having actually
recovered something.

Why no threshold
----------------
Any pass mark here would be invented. Nobody has solved K4, so there is no distribution
of successful attempts to calibrate against, and a made-up number would licence
"passed tier 4" claims that the data cannot support. The report states both figures and
leaves the judgement to a reader.
"""

from __future__ import annotations

from dataclasses import dataclass

from kryptos.scoring.cribs import crib_score
from kryptos.scoring.statistics import ENGLISH_IOC, index_of_coincidence
from kryptos.scoring.text import letters_only

#: Mean quadgram fitness of ordinary English under the committed table, and of uniformly
#: random letters. Reported alongside a score so the number is interpretable without
#: having to remember the scale. Measured -- see ``scoring/data/PROVENANCE.md``.
ENGLISH_FITNESS = -4.2
RANDOM_FITNESS = -6.2


@dataclass(frozen=True)
class FrontierScore:
    """What can honestly be said about an attempt at an unsolved passage."""

    #: Cribs whose plaintext sits at exactly its stated offset.
    cribs_placed: int
    #: Cribs appearing anywhere in the hypothesis. The weaker signal, reported alongside.
    cribs_present: int
    cribs_total: int
    #: Mean log10 quadgram probability of the whole hypothesis.
    fitness: float
    #: Index of coincidence of the hypothesis, as a sanity check on its letter mix.
    ioc: float
    length: int

    @property
    def reads_as_english(self) -> bool:
        """Whether the hypothesis is closer to English than to noise on fitness.

        A convenience for reports, not a pass mark. Midpoint of the two reference
        values, which is a coarse split and is described as such wherever it is shown.
        """
        return self.fitness > (ENGLISH_FITNESS + RANDOM_FITNESS) / 2

    def summary(self) -> str:
        return (
            f"{self.cribs_placed}/{self.cribs_total} cribs placed, "
            f"{self.cribs_present} present; fitness {self.fitness:.2f} "
            f"(English ~{ENGLISH_FITNESS}, random ~{RANDOM_FITNESS}); "
            f"IoC {self.ioc:.4f} (English ~{ENGLISH_IOC})"
        )


def score(cribs: list[dict], hypothesis: str) -> FrontierScore:
    """Score a proposed plaintext for a passage with no reference answer.

    ``hypothesis`` is normalised here rather than assumed clean, because this is scoring
    free-form model output rather than data the project generated.
    """
    from kryptos.scoring.ngram import fitness as quadgram_fitness

    text = letters_only(hypothesis)
    placed, present = crib_score(cribs, text)

    return FrontierScore(
        cribs_placed=placed,
        cribs_present=present,
        cribs_total=len(cribs),
        fitness=quadgram_fitness(text),
        ioc=index_of_coincidence(text),
        length=len(text),
    )
