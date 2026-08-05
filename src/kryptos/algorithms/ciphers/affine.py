"""Affine cipher -- ``c = (a*p + b) mod 26``, with ``a`` coprime to 26.

A monoalphabetic substitution whose alphabet is generated arithmetically instead of drawn
freely, so it delegates to :mod:`~kryptos.algorithms.ciphers.substitution` rather than
restating the mapping. What lives here is the arithmetic that builds the alphabet, and the
coprimality constraint that makes the cipher invertible at all.

**Why ``a`` must be coprime to 26.** Enciphering multiplies by ``a`` mod 26, and that map
is a bijection exactly when ``a`` has a multiplicative inverse, i.e. when ``gcd(a, 26) = 1``.
Take ``a = 2``: A and N both encipher to A, the map collapses 26 letters onto 13, and no
decryption exists. Twelve of the 25 non-zero multipliers survive, giving 12 x 26 = 312 keys
and log2(312) = 8.3 bits -- small enough to brute-force, which is why the suite expects
this in the `easy` band and why it is worth carrying alongside Caesar: both are trivial to
search, but affine punishes a solver that assumes shift-only and never tries a multiplier.

The same ``gcd(det, 26) = 1`` condition governs :mod:`~kryptos.algorithms.ciphers.hill`,
of which this is the one-by-one case.
"""

from __future__ import annotations

import math

from kryptos.algorithms.ciphers import substitution
from kryptos.algorithms.ciphers.substitution import ALPHABET

#: Multipliers coprime to 26, the only ones admitting an inverse. Derived rather than
#: typed out, so the list cannot drift from the condition it is supposed to satisfy.
MULTIPLIERS = tuple(a for a in range(1, 26) if math.gcd(a, 26) == 1)


def alphabet(a: int, b: int) -> str:
    """The substitution alphabet induced by ``(a, b)``.

    >>> alphabet(5, 8)
    'INSXCHMRWBGLQVAFKPUZEJOTYD'
    >>> alphabet(1, 0) == ALPHABET
    True
    """
    _validate(a, b)
    return "".join(ALPHABET[(a * i + b) % 26] for i in range(26))


def encrypt(plaintext: str, a: int, b: int) -> str:
    """Encipher with ``c = (a*p + b) mod 26``.

    >>> encrypt("ATTACK", 5, 8)
    'IZZISG'
    """
    return substitution.encrypt(plaintext, alphabet(a, b))


def decrypt(ciphertext: str, a: int, b: int) -> str:
    """Inverse of :func:`encrypt`.

    >>> decrypt("IZZISG", 5, 8)
    'ATTACK'
    """
    return substitution.decrypt(ciphertext, alphabet(a, b))


def is_invertible(a: int) -> bool:
    """Whether ``a`` admits a multiplicative inverse mod 26 -- the generator's screen.

    >>> is_invertible(5), is_invertible(2)
    (True, False)
    """
    return math.gcd(a, 26) == 1


def is_identity(a: int, b: int) -> bool:
    """Whether ``(a, b)`` leaves the alphabet untouched.

    >>> is_identity(1, 0), is_identity(1, 3)
    (True, False)
    """
    return a % 26 == 1 and b % 26 == 0


def is_shift(a: int) -> bool:
    """Whether the key reduces to a Caesar shift, which the suite carries separately.

    Not degenerate -- a shift is a perfectly good cipher -- but a generator drawing affine
    keys uniformly lands on ``a = 1`` one time in twelve, and those instances duplicate the
    Caesar rows rather than testing anything affine adds.

    >>> is_shift(1), is_shift(5)
    (True, False)
    """
    return a % 26 == 1


def _validate(a: int, b: int) -> None:
    for name, value in (("a", a), ("b", b)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer, got {value!r}")
    if not is_invertible(a):
        raise ValueError(
            f"multiplier a={a} shares a factor with 26, so the map is not a bijection "
            f"and has no inverse; valid multipliers are {list(MULTIPLIERS)}"
        )
