"""Vigenère cipher, optionally over a keyed alphabet.

Vigenère is exactly :mod:`~kryptos.algorithms.ciphers.quagmire` over the *unkeyed*
alphabet: with ``A B C ... Z`` on both axes, "shift by the index of the key letter in the
alphabet" reduces to the familiar ``c = (p + k) mod 26``. Verified against the textbook
vector ``ATTACKATDAWN`` + ``LEMON`` -> ``LXFOPVEFRNHR``.

So this module delegates rather than restating the shift arithmetic. A second copy would
be a second thing to keep correct, and the two would drift the first time either changed.
What lives here is the naming and the default: callers writing a Vigenère stage of a
composite cipher should not have to know it is a Quagmire underneath, or remember that
``"A"`` is the keyword that yields an unkeyed alphabet.

Passing ``alphabet_keyword`` recovers the general keyed case, which is what the Phase 3
K4-proxy composites use. It is keyword-only on purpose: this module's second positional
argument is the *key* while :mod:`quagmire`'s is the *alphabet keyword*, so a positional
call written against the wrong module would silently produce a different cipher rather
than an error — and a mislabelled ground-truth row in the dataset.

Composing with :mod:`~kryptos.algorithms.ciphers.hill`: this cipher carries ``?`` through
and preserves length, while Hill admits no passthrough and needs a length that is a
multiple of its block size. A caller chaining the two strips and pads between the stages;
neither module does it silently.
"""

from __future__ import annotations

from kryptos.algorithms.ciphers import quagmire

#: Keyword whose keyed alphabet is the plain alphabet, i.e. no mixing at all.
UNKEYED = "A"

#: Re-exported so callers need not reach into :mod:`quagmire` for it.
PASSTHROUGH = quagmire.PASSTHROUGH


def encrypt(plaintext: str, key: str, *, alphabet_keyword: str = UNKEYED) -> str:
    """Encipher ``plaintext`` with a repeating ``key``.

    >>> encrypt("ATTACKATDAWN", "LEMON")
    'LXFOPVEFRNHR'
    """
    return quagmire.encrypt(plaintext, alphabet_keyword, key)


def decrypt(ciphertext: str, key: str, *, alphabet_keyword: str = UNKEYED) -> str:
    """Decipher ``ciphertext``. Inverse of :func:`encrypt` for uppercase input.

    >>> decrypt("LXFOPVEFRNHR", "LEMON")
    'ATTACKATDAWN'
    """
    return quagmire.decrypt(ciphertext, alphabet_keyword, key)


def period(key: str, *, alphabet_keyword: str = UNKEYED) -> int:
    """Length of the shortest repeating cycle in the shift schedule.

    Not the key's length: ``ABAB`` repeats every two positions. See
    :func:`kryptos.algorithms.ciphers.quagmire.period`.

    >>> period("LEMON"), period("ABAB")
    (5, 2)
    """
    return quagmire.period(key, alphabet_keyword)
