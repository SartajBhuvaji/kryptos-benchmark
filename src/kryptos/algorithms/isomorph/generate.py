"""Isomorph generators -- the contamination-resistance mechanism.

Each generator produces an instance structurally identical to a Kryptos passage but with a
plaintext that has never existed and keys drawn at random. A model that solves K1 and
fails every Quagmire isomorph has told you something specific, and that gap is the
quantity the whole project exists to measure.

Everything is deterministic given a :class:`random.Random`. The caller owns the seed:
:func:`generate` takes one and builds the generator, so a published snapshot and an
on-demand fresh run are the same code path differing only in whether a seed was passed.

Screening is not optional
-------------------------
Random keys produce degenerate ciphers at a rate that matters. A Quagmire indicator can
contain a letter that sits at position 0 of the keyed alphabet, and that column copies its
plaintext through in clear -- one position in every period, legible in the ciphertext. A
two-stage route can compose to the identity, shipping a "ciphertext" equal to its
plaintext. A random matrix over Z/26 is non-invertible about half the time, since 26 is
not prime. Phase 1 anticipated all three and exposes :func:`~kryptos.algorithms.ciphers.
quagmire.degenerate_columns`, :func:`~kryptos.algorithms.ciphers.transposition.is_identity`
and :func:`~kryptos.algorithms.ciphers.hill.is_invertible` for exactly this; the generators
reject and redraw rather than shipping a broken instance.

Ground truth is generated, never written
----------------------------------------
Every instance carries its full parameter set, and its ``solution`` prose is rendered from
those parameters. Hand-writing a solution for a randomly generated key is how a dataset
ends up asserting something its own data contradicts -- which is precisely the defect
Phase 1.5 had to correct in the baseline.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, replace
from typing import Any, Callable

from kryptos.algorithms.ciphers import hill, quagmire, transposition, vigenere
from kryptos.algorithms.isomorph import corpus
from kryptos.algorithms.isomorph.corpus import Plaintext

#: How many times to redraw before admitting the parameters cannot be satisfied. Failures
#: are common enough to need retries and rare enough that hitting this bound means a bug
#: or an impossible request, not bad luck.
MAX_ATTEMPTS = 200

#: The null letter for the Quagmire-with-nulls proxy. ``W`` follows the design document,
#: which takes it from K2's plaintext ``ONLY WW``.
NULL_LETTER = "W"

#: Hill block size for the composite proxy. 3x3 over Z/26: large enough that recovering
#: the matrix needs several independent blocks, small enough that a length divisible by it
#: is easy to find inside the Kryptos span.
HILL_BLOCK_SIZE = 3


@dataclass(frozen=True)
class Instance:
    """One generated cipher problem, with everything needed to score or audit it."""

    id: str
    kind: str
    cipher_family: str
    cipher_name: str
    #: What a solver is given.
    ciphertext: str
    #: What a solver should return -- the recovered message.
    answer: str
    #: Machine-generated from :attr:`parameters`; never hand-written.
    solution: str
    #: The full key set. Every value is JSON-serialisable, so an instance can be written
    #: to a dataset row without a custom encoder.
    parameters: dict[str, Any]
    #: Where the plaintext came from.
    source_works: tuple[str, ...]
    clause_count: int
    #: Readable form of the message, spacing preserved, for human inspection.
    answer_readable: str = ""
    seed: int | None = None

    def __len__(self) -> int:
        return len(self.ciphertext)


# --- keyword and parameter drawing -------------------------------------------------


def _keyword(rng: random.Random) -> str:
    return rng.choice(corpus.vocabulary())


def _draw(rng: random.Random, build: Callable[[], Any | None], what: str) -> Any:
    """Redraw ``build`` until it returns something other than ``None``.

    Screening is expressed as "return None and try again" so each generator states its own
    degeneracy conditions inline rather than duplicating a retry loop.
    """
    for _ in range(MAX_ATTEMPTS):
        candidate = build()
        if candidate is not None:
            return candidate
    raise RuntimeError(
        f"could not draw {what} in {MAX_ATTEMPTS} attempts; the constraints are "
        "probably unsatisfiable rather than unlucky"
    )


def quagmire_keys(rng: random.Random) -> tuple[str, str]:
    """An (alphabet, indicator) keyword pair that yields a non-degenerate cipher."""

    def attempt() -> tuple[str, str] | None:
        alphabet_keyword = _keyword(rng)
        indicator_keyword = _keyword(rng)

        # A keyword whose letters are already in alphabetical order from A leaves the
        # alphabet unmixed, reducing Quagmire III to an ordinary Vigenere.
        if quagmire.keyed_alphabet(alphabet_keyword) == quagmire.ALPHABET:
            return None
        # A shift-zero column copies its plaintext through in clear.
        if quagmire.degenerate_columns(indicator_keyword, alphabet_keyword):
            return None
        # Both Kryptos indicators step through every position, so their period equals
        # their length. A repeating indicator like ABAB is a shorter cipher wearing a
        # longer key, and stating the length as the period would be a lie.
        if quagmire.period(indicator_keyword, alphabet_keyword) != len(indicator_keyword):
            return None
        return alphabet_keyword, indicator_keyword

    return _draw(rng, attempt, "Quagmire keys")


def _divisors(n: int) -> list[int]:
    """Proper divisors, excluding 1 and ``n`` -- both make a stage the identity."""
    return [d for d in range(2, n) if n % d == 0]


def transposition_route(length: int, rng: random.Random) -> tuple[transposition.Stage, ...]:
    """A two-stage route over ``length`` characters that is not the identity."""
    widths = _divisors(length)
    if len(widths) < 2:
        raise ValueError(
            f"length {length} has {len(widths)} usable grid width(s); a two-stage route "
            "needs at least two. Choose a length with more divisors."
        )

    def attempt() -> tuple[transposition.Stage, ...] | None:
        first, second = rng.sample(widths, 2)
        # Zero quarter turns would make a stage a no-op, collapsing this to one stage.
        route = ((first, rng.randint(1, 3)), (second, rng.randint(1, 3)))
        if transposition.is_identity(length, route):
            return None
        return route

    return _draw(rng, attempt, f"a non-identity route over {length} characters")


def hill_matrix(size: int, rng: random.Random) -> hill.Matrix:
    """A random ``size x size`` matrix invertible mod 26.

    About half of all random matrices are not, because 26 = 2 x 13 and a determinant
    sharing either factor has no inverse.
    """

    def attempt() -> hill.Matrix | None:
        matrix = tuple(
            tuple(rng.randrange(26) for _ in range(size)) for _ in range(size)
        )
        return matrix if hill.is_invertible(matrix) else None

    return _draw(rng, attempt, f"an invertible {size}x{size} matrix mod 26")


def transposable_length(rng: random.Random, minimum: int, maximum: int) -> int:
    """A length in range with at least two usable grid widths.

    Route transposition needs the width to divide the text exactly, so the length has to
    be chosen with the geometry in mind rather than the other way round. Primes and
    semiprimes in the range are simply unusable.
    """
    candidates = [n for n in range(minimum, maximum + 1) if len(_divisors(n)) >= 2]
    if not candidates:
        raise ValueError(f"no length between {minimum} and {maximum} admits a two-stage route")
    return rng.choice(candidates)


# --- solution rendering ------------------------------------------------------------

QUAGMIRE_SOLUTION = (
    "Quagmire III polyalphabetic substitution. Build the mixed alphabet by writing "
    "{alphabet_keyword}, dropping repeated letters, then appending the unused letters of "
    "the alphabet in order, giving {keyed_alphabet}. The indicator keyword "
    "{indicator_keyword} gives a period of {period}: the message is enciphered with "
    "{period} shifted copies of that alphabet, selected by position modulo {period}. "
    "Decrypt each position with its own shifted alphabet."
)

TRANSPOSITION_SOLUTION = (
    "Route transposition. The letters are permuted rather than substituted, so letter "
    "frequencies and the index of coincidence are unchanged from ordinary English and the "
    "ciphertext is an exact anagram of the plaintext. Recover it in two stages: write the "
    "ciphertext row-major into a grid {solver_first_width} columns wide, rotate it "
    "{solver_first_turns} quarter turn(s) clockwise, and read it back row-major; then do "
    "the same again with a grid {solver_second_width} columns wide and "
    "{solver_second_turns} quarter turn(s). Enciphering is the route {route} in "
    "width:quarter_turns form -- widths {enc_first_width} then {enc_second_width}, at "
    "{enc_first_turns} and {enc_second_turns} quarter turns -- which is what the 'route' "
    "parameter records."
)

COMPOSITE_SOLUTION = (
    "Two enciphering layers, applied in this order. First a Vigenere with key {key} over "
    "the plain A-Z alphabet. Then a Hill cipher over Z/26 on blocks of {block_size} "
    "letters with key matrix {matrix}. Undo them in reverse: multiply each block of "
    "{block_size} ciphertext letters by the inverse matrix mod 26, then subtract the "
    "Vigenere key. This is a multi-layer capability probe, not a model of K4 -- K4's "
    "method is unknown, and solving this says nothing about it."
)

NULLS_SOLUTION = (
    "Quagmire III polyalphabetic substitution with nulls. Build the mixed alphabet by "
    "writing {alphabet_keyword}, dropping repeated letters, then appending the unused "
    "letters of the alphabet in order, giving {keyed_alphabet}. The indicator keyword "
    "{indicator_keyword} gives a period of {period}. Decrypting yields the message with "
    "{null_count} nulls interleaved: it runs in groups of {group} message letters, each "
    "group followed by a single null. Discard every {stride}th character -- 1-indexed "
    "positions {stride}, {stride2}, {stride3} and so on -- to recover the message. "
    "Discard by position, not by letter: the null is always {null}, but {null} also "
    "occurs naturally in the message and those occurrences must be kept. The nulls are "
    "enciphered along with everything else, so the period runs over their positions too. "
    "This is a multi-layer capability probe, not a model of K4 -- K4's method is unknown, "
    "and solving this says nothing about it."
)


# --- generators ---------------------------------------------------------------------


def quagmire_instance(rng: random.Random, length: int, index: int = 0) -> Instance:
    """A Quagmire III isomorph -- K1 and K2's cipher with new keys and a new plaintext."""
    alphabet_keyword, indicator_keyword = quagmire_keys(rng)
    passage = corpus.plaintext(length, rng)
    ciphertext = quagmire.encrypt(passage.text, alphabet_keyword, indicator_keyword)

    keyed = quagmire.keyed_alphabet(alphabet_keyword)
    period = quagmire.period(indicator_keyword, alphabet_keyword)

    return _instance(
        index=index,
        kind="quagmire",
        cipher_family="polyalphabetic_substitution",
        cipher_name="Quagmire III",
        ciphertext=ciphertext,
        passage=passage,
        answer=passage.text,
        parameters={
            "alphabet_keyword": alphabet_keyword,
            "keyed_alphabet": keyed,
            "indicator_keyword": indicator_keyword,
            "period": period,
        },
        solution=QUAGMIRE_SOLUTION.format(
            alphabet_keyword=alphabet_keyword,
            keyed_alphabet=keyed,
            indicator_keyword=indicator_keyword,
            period=period,
        ),
    )


def transposition_instance(rng: random.Random, length: int, index: int = 0) -> Instance:
    """A route transposition isomorph -- K3's cipher with new geometry and text."""
    route = transposition_route(length, rng)
    passage = corpus.plaintext(length, rng)
    ciphertext = transposition.encrypt(passage.text, route)

    solver = _inverse_route(length, route)

    return _instance(
        index=index,
        kind="transposition",
        cipher_family="transposition",
        cipher_name="Route transposition",
        ciphertext=ciphertext,
        passage=passage,
        answer=passage.text,
        parameters={
            "route": _format_route(route),
            "solver_route": _format_route(solver) if solver else None,
        },
        solution=TRANSPOSITION_SOLUTION.format(
            route=_format_route(route),
            enc_first_width=route[0][0], enc_first_turns=route[0][1],
            enc_second_width=route[1][0], enc_second_turns=route[1][1],
            solver_first_width=solver[0][0] if solver else route[0][0],
            solver_first_turns=solver[0][1] if solver else route[0][1],
            solver_second_width=solver[1][0] if solver else route[1][0],
            solver_second_turns=solver[1][1] if solver else route[1][1],
        ),
    )


def composite_instance(
    rng: random.Random, length: int, index: int = 0, block_size: int = HILL_BLOCK_SIZE
) -> Instance:
    """A Vigenere layer followed by a Hill layer -- a K4 *proxy*, not a K4 model."""
    if length % block_size:
        raise ValueError(
            f"length {length} is not a multiple of Hill block size {block_size}; "
            "the composite cannot pad without changing the message"
        )
    key = _keyword(rng)
    matrix = hill_matrix(block_size, rng)
    passage = corpus.plaintext(length, rng)

    intermediate = vigenere.encrypt(passage.text, key)
    ciphertext = hill.encrypt(intermediate, matrix)

    return _instance(
        index=index,
        kind="composite",
        cipher_family="composite",
        cipher_name="Vigenere then Hill",
        ciphertext=ciphertext,
        passage=passage,
        answer=passage.text,
        parameters={
            "layers": ["vigenere", "hill"],
            "vigenere_key": key,
            "hill_block_size": block_size,
            "hill_matrix": [list(row) for row in matrix],
        },
        solution=COMPOSITE_SOLUTION.format(
            key=key,
            block_size=block_size,
            matrix=[list(row) for row in matrix],
        ),
    )


def nulls_instance(
    rng: random.Random, length: int, index: int = 0, group: int | None = None
) -> Instance:
    """Quagmire III over a message salted with ``W`` nulls -- the second K4 proxy.

    ``length`` is the length of the *ciphertext*, so the recoverable message is shorter by
    the number of nulls inserted. Sizing it the other way would make instances of a
    requested length unpredictable, and the ciphertext is the thing a solver is handed.

    Nulls go at regular positions -- ``group`` message letters, then one null, repeating.
    That regularity is what makes the instance solvable: ``W`` occurs naturally in English,
    so a rule of "discard every W" would be ambiguous and would delete real letters from
    the message. The rule is positional, and the null letter is incidental.
    """
    alphabet_keyword, indicator_keyword = quagmire_keys(rng)
    spacing = group if group is not None else rng.randint(6, 12)
    if not isinstance(spacing, int) or isinstance(spacing, bool) or spacing < 1:
        raise ValueError(f"group must be a positive integer, got {spacing!r}")

    # A null lands at every index congruent to `spacing` modulo `spacing + 1`, which is
    # exactly "group letters then a null", repeated.
    null_positions = list(range(spacing, length, spacing + 1))
    message_length = length - len(null_positions)
    if message_length < 1:
        raise ValueError(f"group {spacing} leaves no message at length {length}")
    passage = corpus.plaintext(message_length, rng)

    salted = _insert_nulls(passage.text, null_positions)
    assert len(salted) == length, "null insertion changed the requested length"
    assert all(salted[p] == NULL_LETTER for p in null_positions), "nulls are misplaced"

    ciphertext = quagmire.encrypt(salted, alphabet_keyword, indicator_keyword)
    keyed = quagmire.keyed_alphabet(alphabet_keyword)
    period = quagmire.period(indicator_keyword, alphabet_keyword)

    return _instance(
        index=index,
        kind="nulls",
        cipher_family="composite",
        cipher_name="Quagmire III with nulls",
        ciphertext=ciphertext,
        passage=passage,
        # The message, not the enciphered text: the nulls carry no meaning and the task
        # is to identify and discard them. `deciphered` below records the intermediate,
        # so a tier that wants to score the substitution alone still can.
        answer=passage.text,
        parameters={
            "layers": ["quagmire_iii", "nulls"],
            "alphabet_keyword": alphabet_keyword,
            "keyed_alphabet": keyed,
            "indicator_keyword": indicator_keyword,
            "period": period,
            "null": NULL_LETTER,
            "null_group": spacing,
            "null_stride": spacing + 1,
            "null_positions": null_positions,
            "null_count": len(null_positions),
            "deciphered": salted,
        },
        solution=NULLS_SOLUTION.format(
            alphabet_keyword=alphabet_keyword,
            keyed_alphabet=keyed,
            indicator_keyword=indicator_keyword,
            period=period,
            null=NULL_LETTER,
            null_count=len(null_positions),
            group=spacing,
            stride=spacing + 1,
            stride2=2 * (spacing + 1),
            stride3=3 * (spacing + 1),
        ),
    )


#: The generator for each kind, by name.
GENERATORS: dict[str, Callable[..., Instance]] = {
    "quagmire": quagmire_instance,
    "transposition": transposition_instance,
    "composite": composite_instance,
    "nulls": nulls_instance,
}


def generate(
    kind: str,
    count: int,
    *,
    seed: int | None = None,
    min_length: int = corpus.KRYPTOS_MIN_LENGTH,
    max_length: int = corpus.KRYPTOS_MAX_LENGTH,
) -> list[Instance]:
    """Generate ``count`` instances of ``kind``.

    Pass ``seed`` for a reproducible snapshot; omit it for a fresh draw that has never
    been published and cannot have been trained on. Both are the same code path -- that
    equivalence is what makes a published snapshot and an on-demand run comparable.
    """
    if kind not in GENERATORS:
        raise ValueError(f"unknown kind {kind!r}; choose from {sorted(GENERATORS)}")
    if not isinstance(count, int) or isinstance(count, bool) or count < 1:
        raise ValueError(f"count must be a positive integer, got {count!r}")
    if min_length > max_length:
        raise ValueError(f"min_length {min_length} exceeds max_length {max_length}")

    rng = stream(kind, seed)
    generator = GENERATORS[kind]

    instances = []
    for index in range(count):
        length = _length_for(kind, rng, min_length, max_length)
        instance = generator(rng, length, index)
        instances.append(
            instance if seed is None else _with_seed(instance, seed)
        )
    return instances


def stream(kind: str, seed: int | None) -> random.Random:
    """The random stream for one config, salted by ``kind``.

    Seeding every config from the same integer makes them draw the *same* keywords and the
    same clauses -- one published snapshot would ship three configs keyed alike, and a
    plaintext appearing in the transposition config would appear again inside the nulls
    config. Salting separates the streams while keeping one seed per release.

    Salted with SHA-256 rather than :func:`hash`, which is randomised per process and would
    make "seeded" mean nothing across runs.
    """
    if seed is None:
        return random.Random()
    digest = hashlib.sha256(f"{kind}:{seed}".encode()).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _length_for(kind: str, rng: random.Random, minimum: int, maximum: int) -> int:
    """Pick a length the cipher can actually accept.

    Each family constrains this differently, and getting it wrong surfaces as an
    exception from deep inside a cipher rather than as a clear refusal here.
    """
    if kind == "transposition":
        return transposable_length(rng, minimum, maximum)
    if kind == "composite":
        block = HILL_BLOCK_SIZE
        lowest = -(-minimum // block) * block
        if lowest > maximum:
            raise ValueError(f"no multiple of {block} between {minimum} and {maximum}")
        return rng.randrange(lowest, maximum + 1, block)
    return rng.randint(minimum, maximum)


# --- helpers -------------------------------------------------------------------------


def _instance(
    *,
    index: int,
    kind: str,
    cipher_family: str,
    cipher_name: str,
    ciphertext: str,
    passage: Plaintext,
    answer: str,
    parameters: dict[str, Any],
    solution: str,
) -> Instance:
    return Instance(
        id=f"kryptos-isomorph-{kind}-{index:04d}",
        kind=kind,
        cipher_family=cipher_family,
        cipher_name=cipher_name,
        ciphertext=ciphertext,
        answer=answer,
        answer_readable=passage.readable,
        solution=solution,
        parameters=parameters,
        source_works=passage.works,
        clause_count=passage.clause_count,
    )


def _with_seed(instance: Instance, seed: int) -> Instance:
    return replace(instance, seed=seed)


def _insert_nulls(message: str, positions: list[int]) -> str:
    """Insert :data:`NULL_LETTER` so it lands at each index of the *result*."""
    out = list(message)
    for position in positions:
        out.insert(position, NULL_LETTER)
    return "".join(out)


def _format_route(route: tuple[transposition.Stage, ...]) -> str:
    """Same encoding the baseline uses for K3 -- ``width:turns`` per stage."""
    return ",".join(f"{width}:{turns}" for width, turns in route)


def _inverse_route(
    length: int, route: tuple[transposition.Stage, ...]
) -> tuple[transposition.Stage, ...] | None:
    """A two-stage route running forward on the ciphertext, if one exists.

    K3's inverse happens to be expressible as another two-stage grid route, which is why
    its solution can be stated that way. That is not guaranteed for an arbitrary route, so
    this searches and returns ``None`` when there is none -- the caller then describes the
    route in the encryption direction and leaves inverting it to the solver.
    """
    target = transposition.permutation(length, route)
    inverse = [0] * length
    for source, destination in enumerate(target):
        inverse[destination] = source

    for first in _divisors(length):
        for first_turns in range(1, 4):
            for second in _divisors(length):
                for second_turns in range(1, 4):
                    candidate = ((first, first_turns), (second, second_turns))
                    if transposition.permutation(length, candidate) == inverse:
                        return candidate
    return None
