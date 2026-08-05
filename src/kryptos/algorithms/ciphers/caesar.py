"""Caesar shift -- ``c = (p + n) mod 26``.

The suite's floor, and its purpose is to be trivial. A benchmark whose easiest instance is
already hard cannot tell "this model has no cryptanalytic ability" from "this model failed
today"; a mechanism with 26 keys, one of which is the identity, separates those two.

Affine with the multiplier fixed at one, so it delegates to
:mod:`~kryptos.algorithms.ciphers.affine` rather than restating the shift -- which in turn
delegates to :mod:`~kryptos.algorithms.ciphers.substitution`. The chain is deliberate: one
substitution step exists in the codebase, and the three named ciphers are three ways of
choosing its alphabet.

Distinct from :mod:`~kryptos.algorithms.ciphers.vigenere` at period one only in framing --
the arithmetic is identical. Both are carried because the framings differ in what they ask:
a Vigenère instance invites a search for the period first, and a solver that finds period
one has learned something a Caesar instance never asked.
"""

from __future__ import annotations

from kryptos.algorithms.ciphers import affine

#: The shift leaving every letter untouched. ROT13 is ``13`` and is its own inverse; the
#: generator screens both, the first as useless and the second as recognisable on sight.
IDENTITY = 0


def encrypt(plaintext: str, shift: int) -> str:
    """Shift each letter forward by ``shift``.

    >>> encrypt("ATTACK", 3)
    'DWWDFN'
    """
    return affine.encrypt(plaintext, 1, _validate(shift))


def decrypt(ciphertext: str, shift: int) -> str:
    """Inverse of :func:`encrypt`.

    >>> decrypt("DWWDFN", 3)
    'ATTACK'
    """
    return affine.decrypt(ciphertext, 1, _validate(shift))


def is_identity(shift: int) -> bool:
    """Whether the shift leaves the text unchanged -- the generator's screen.

    >>> is_identity(0), is_identity(26), is_identity(3)
    (True, True, False)
    """
    return _validate(shift) % 26 == IDENTITY


def is_involution(shift: int) -> bool:
    """Whether enciphering twice returns the plaintext, i.e. ROT13.

    Screened not because it is weak -- every Caesar is weak -- but because ROT13 appears
    verbatim throughout the training corpora of every model this benchmark scores, so an
    instance drawn on it measures recall rather than cryptanalysis. That is the distinction
    the whole project exists to preserve.

    >>> is_involution(13), is_involution(3)
    (True, False)
    """
    return _validate(shift) % 26 == 13


def _validate(shift: int) -> int:
    if isinstance(shift, bool) or not isinstance(shift, int):
        raise ValueError(f"shift must be an integer, got {shift!r}")
    return shift
