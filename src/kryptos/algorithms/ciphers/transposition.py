"""Route transposition — the cipher behind Kryptos K3.

A route transposition permutes character *positions* without substituting anything, so
letter frequencies and the index of coincidence are unchanged from ordinary English and
the ciphertext is an exact anagram of the plaintext. That is what rules out frequency
analysis and identifies the family.

The route here is a sequence of stages. Each stage writes the running text row-major into
a grid of a given width, rotates the grid a quarter turn clockwise some number of times,
and reads it back row-major. Two stages suffice for K3.

K3's geometry, derived rather than assumed
------------------------------------------
The project's design document states a width of 86 with a reslice to segments of 8. That
does not reproduce K3: 86 does not divide K3's 336 enciphered characters, and an
exhaustive sweep of that shape over every rotation combination matches nothing.

The route was instead recovered by searching all two-stage routes whose widths divide 336
(12,800 candidates) for one carrying K3's plaintext to its ciphertext. Twelve parameter
sets match, and applying each to 336 distinct symbols shows all twelve induce **the same
permutation** — they are different descriptions of one transformation, not twelve ciphers.
They are exactly the pairs whose widths multiply to 588:

    (7, 84)  (14, 42)  (21, 28)  (28, 21)  (42, 14)  (84, 7)

each with both stages rotated 90 degrees, or both 270. :data:`K3_ROUTE` picks the first.

How strong is that? Not "uniquely determined by the data": K3's plaintext has repeated
letters, so roughly 10^306 distinct permutations carry it to the ciphertext, and no amount
of staring at one plaintext/ciphertext pair can single one out. The uniqueness is
*relative to the family searched* — two- and three-stage grid-rotation routes over widths
dividing 336. Extending the sweep to three stages found no route inducing a different
permutation, so within that family the answer is stable. A route outside it that happens
to agree on this one pair cannot be ruled out, and would be indistinguishable here.

Inverting it gives the route a solver would run on the ciphertext — width 8 then width 24,
both a quarter turn — which is where the design document's "segments of 8" belongs. Its
stated width of 86 appears to be an error: 86 divides neither 336 nor any padding of it
that preserves the text, and padding to 344 (86 x 4) and sweeping every second stage and
rotation still matches nothing.

The trailing ``?``
------------------
K3 is 337 carved characters: 336 enciphered letters plus a literal ``?`` at the end. The
``?`` is not part of the permutation. Callers strip it before transposing and re-append it
after; :func:`encrypt` and :func:`decrypt` operate on exactly the text they are given.
"""

from __future__ import annotations

#: One stage of a route: grid width, and quarter turns clockwise applied to that grid.
Stage = tuple[int, int]

#: K3's route in the encryption direction, plaintext to ciphertext. Eleven other
#: parameterisations induce the identical permutation — see the module docstring.
K3_ROUTE: tuple[Stage, ...] = ((7, 1), (84, 1))

#: The same permutation inverted: what a solver applies to the ciphertext. Provided for
#: readability; ``decrypt(text, K3_ROUTE)`` is equivalent and is what the tests use.
K3_SOLVER_ROUTE: tuple[Stage, ...] = ((8, 1), (24, 1))


def encrypt(plaintext: str, route: tuple[Stage, ...]) -> str:
    """Permute ``plaintext`` along ``route``.

    >>> encrypt("ABCDEF", ((2, 1),))
    'ECAFDB'
    """
    perm = permutation(len(plaintext), route)
    return "".join(plaintext[i] for i in perm)


def decrypt(ciphertext: str, route: tuple[Stage, ...]) -> str:
    """Undo :func:`encrypt`. Exact inverse for any text and any valid route.

    >>> decrypt("ECAFDB", ((2, 1),))
    'ABCDEF'
    """
    perm = permutation(len(ciphertext), route)
    out = [""] * len(ciphertext)
    for source, target in enumerate(perm):
        out[target] = ciphertext[source]
    return "".join(out)


def permutation(length: int, route: tuple[Stage, ...]) -> list[int]:
    """Positions the route reads from, in output order.

    ``encrypt(text, route)[i] == text[permutation(len(text), route)[i]]``. Computed on
    indices rather than on the text, so it is independent of the characters and can be
    reused to build the inverse.

    >>> permutation(6, ((2, 1),))
    [4, 2, 0, 5, 3, 1]
    """
    _validate(length, route)
    positions = list(range(length))
    for width, quarter_turns in route:
        rows = [positions[i : i + width] for i in range(0, length, width)]
        for _ in range(quarter_turns % 4):
            rows = [list(row) for row in zip(*rows[::-1])]
        positions = [value for row in rows for value in row]
    return positions


def is_identity(length: int, route: tuple[Stage, ...]) -> bool:
    """Whether the route leaves every position where it found it.

    A route of all-zero rotations is the identity regardless of its widths, and so is a
    single stage whose width is 1 or ``length``. Generators should screen for this rather
    than ship a "ciphertext" identical to its plaintext.

    >>> is_identity(336, ((7, 0), (84, 0)))
    True
    >>> is_identity(336, K3_ROUTE)
    False
    """
    return permutation(length, route) == list(range(length))


def _validate(length: int, route: tuple[Stage, ...]) -> None:
    if not isinstance(length, int) or length < 0:
        raise ValueError(f"length must be a non-negative integer, got {length!r}")
    if not route:
        raise ValueError("route must contain at least one stage")

    for index, stage in enumerate(route):
        try:
            width, quarter_turns = stage
        except (TypeError, ValueError):
            raise ValueError(
                f"stage {index} must be a (width, quarter_turns) pair, got {stage!r}"
            ) from None
        # bool is a subclass of int, so True would silently mean width 1.
        if isinstance(width, bool) or not isinstance(width, int) or width < 1:
            raise ValueError(f"stage {index}: width must be a positive integer, got {width!r}")
        if isinstance(quarter_turns, bool) or not isinstance(quarter_turns, int) or quarter_turns < 0:
            raise ValueError(
                f"stage {index}: quarter_turns must be a non-negative integer, "
                f"got {quarter_turns!r}"
            )
        if length and length % width:
            # A ragged final row has no well-defined rotation, and padding it would
            # change the text length. Reject rather than guess.
            raise ValueError(
                f"stage {index}: width {width} does not divide text length {length}"
            )
