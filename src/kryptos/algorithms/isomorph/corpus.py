"""Plaintexts for the isomorph generators.

Kryptos-sized passages of English that have never existed, assembled by drawing clauses
from public-domain prose and concatenating them. The point is to hold two properties at
once that the obvious alternatives each give up one of:

*novel*, so no model can complete the passage from memory once a few characters resolve
-- which is what a verbatim excerpt of a known book would allow, and which would stop the
score measuring cryptanalysis at exactly the moment it started to;

*statistically real*, so the index of coincidence, letter frequencies and quadgram
fitness behave as they would against a genuine target. LLM-written prose is novel but
unusually predictable, and both n-gram hill-climbing and a model's own priors do better on
it than on real English, which inflates scores relative to the cipher's true difficulty.

Everything here is deterministic given a :class:`random.Random`. The caller owns the seed;
see :mod:`kryptos.algorithms.isomorph` for how it threads through the generators.

The corpus itself is committed, checksummed and documented in ``data/PROVENANCE.md``.
"""

from __future__ import annotations

import functools
import gzip
import json
import pathlib
import random
from dataclasses import dataclass, field

CORPUS = pathlib.Path(__file__).resolve().parent / "data" / "clauses.jsonl.gz"

#: The span of the four carved passages, and so the range a generated instance should sit
#: in to be a fair isomorph. K1 is 63 characters and K2 is 372.
KRYPTOS_MIN_LENGTH = 63
KRYPTOS_MAX_LENGTH = 372


def normalize(readable: str) -> str:
    """Reduce readable prose to the carved form: uppercase A-Z, nothing else.

    Matches how the sculpture presents text -- no spacing, no punctuation, no case. The
    isomorphs have to arrive in the same shape as the baseline or the two are not
    comparable, which is the entire measurement the project is built around.

    >>> normalize("I almost wish I had never heard it.")
    'IALMOSTWISHIHADNEVERHEARDIT'
    """
    return "".join(ch for ch in readable.upper() if "A" <= ch <= "Z")


@dataclass(frozen=True)
class Plaintext:
    """A generated passage, with enough provenance to audit where it came from."""

    #: Carved form: uppercase A-Z, exactly the requested length.
    text: str
    #: The same content with clause boundaries kept as spaces, for reading and debugging.
    readable: str
    #: Source work ids contributing to this passage, sorted and deduplicated.
    works: tuple[str, ...]
    #: How many clauses were drawn. One clause would be a verbatim excerpt.
    clause_count: int
    #: Whether the final clause was cut short to hit the requested length exactly.
    truncated: bool = False

    def __post_init__(self) -> None:
        if self.text != normalize(self.readable):
            raise ValueError("text and readable disagree; they must be the same content")

    def __len__(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class Clause:
    work: str
    text: str
    letters: str = field(compare=False, default="")


class Corpus:
    """Clauses of public-domain prose, tagged with the work each came from."""

    def __init__(self, clauses: tuple[Clause, ...]) -> None:
        if not clauses:
            raise ValueError("corpus is empty")
        self.clauses = clauses

    @property
    def works(self) -> tuple[str, ...]:
        return tuple(sorted({clause.work for clause in self.clauses}))

    def sample(self, length: int, rng: random.Random) -> Plaintext:
        """Draw clauses and concatenate them into exactly ``length`` letters.

        Clauses are drawn without replacement within a passage, so no fragment repeats
        inside one instance. The last clause is cut to make the length exact -- possibly
        mid-word, which is unremarkable in a form that has no spaces anyway, and is
        recorded on the result either way.

        Exactness matters more than it looks: a route transposition needs a grid width
        that divides the text length, so a generator that could only ask for
        "about 300 characters" would have its geometry chosen for it by the corpus.
        """
        if not isinstance(length, int) or isinstance(length, bool) or length < 1:
            raise ValueError(f"length must be a positive integer, got {length!r}")
        if length > self.total_letters:
            raise ValueError(
                f"asked for {length} letters; the corpus holds {self.total_letters}"
            )

        picked: list[Clause] = []
        seen: set[int] = set()
        letters = 0

        while letters < length:
            index = rng.randrange(len(self.clauses))
            if index in seen:
                continue
            seen.add(index)
            clause = self.clauses[index]
            picked.append(clause)
            letters += len(clause.letters)

        # Trim the final clause back to land on the requested length exactly.
        overshoot = letters - length
        truncated = overshoot > 0
        if truncated:
            last = picked[-1]
            keep = len(last.letters) - overshoot
            picked[-1] = Clause(last.work, _cut_to_letters(last.text, keep),
                                last.letters[:keep])

        text = "".join(clause.letters for clause in picked)
        assert len(text) == length, "length control is off"

        return Plaintext(
            text=text,
            readable=" ".join(clause.text for clause in picked),
            works=tuple(sorted({clause.work for clause in picked})),
            clause_count=len(picked),
            truncated=truncated,
        )

    @functools.cached_property
    def total_letters(self) -> int:
        return sum(len(clause.letters) for clause in self.clauses)


def _cut_to_letters(readable: str, keep: int) -> str:
    """Trim readable text so it normalises to exactly ``keep`` letters."""
    if keep <= 0:
        return ""
    seen = 0
    for position, ch in enumerate(readable):
        if "A" <= ch.upper() <= "Z":
            seen += 1
            if seen == keep:
                return readable[: position + 1]
    return readable


def parse(payload: str) -> tuple[Clause, ...]:
    rows = (json.loads(line) for line in payload.splitlines() if line.strip())
    return tuple(
        Clause(work=row["work"], text=row["text"], letters=normalize(row["text"]))
        for row in rows
    )


@functools.lru_cache(maxsize=1)
def load() -> Corpus:
    """The committed corpus. Cached -- every generator wants the same object."""
    if not CORPUS.exists():
        raise FileNotFoundError(
            f"missing clause corpus at {CORPUS}. Run: "
            "python -m kryptos.algorithms.isomorph.data.build"
        )
    return Corpus(parse(gzip.decompress(CORPUS.read_bytes()).decode("utf-8")))


def plaintext(length: int, rng: random.Random) -> Plaintext:
    """Draw one passage of ``length`` letters from the committed corpus."""
    return load().sample(length, rng)
