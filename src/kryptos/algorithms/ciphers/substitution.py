"""Monoalphabetic substitution -- one fixed alphabet, applied to every position.

The suite's most general single-alphabet cipher, and the base the other two monoalphabetic
mechanisms delegate to: :mod:`~kryptos.algorithms.ciphers.affine` is this cipher over an
alphabet generated arithmetically, and :mod:`~kryptos.algorithms.ciphers.caesar` is affine
with the multiplier fixed at one. Three names, one substitution step, one implementation --
the same relationship :mod:`~kryptos.algorithms.ciphers.vigenere` already has to
:mod:`~kryptos.algorithms.ciphers.quagmire`, and for the same reason: a second copy of the
mapping is a second thing to keep correct.

Where it sits in the suite: this is the canonical hill-climbing target. Its keyspace is
log2(26!) = 88.4 bits, far too large to enumerate, and yet frequency analysis breaks it on
a few hundred characters -- which is exactly the gap Phase 7 sets out to measure, since a
model reciting "use frequency analysis" and a model actually recovering the alphabet score
very differently and are easy to confuse in prose.

**No passthrough.** Unlike the Kryptos ciphers, which copy a carved ``?`` through
unenciphered, this admits only A-Z and raises otherwise. The suite's plaintexts come from
the Phase 3 corpus already normalised, so a stray character means a generator bug, and
carrying it silently would publish a row whose ciphertext does not match its stated key.
"""

from __future__ import annotations

import string

from kryptos.algorithms.ciphers.quagmire import keyed_alphabet

#: The plaintext alphabet, in order. A key is a permutation of this.
ALPHABET = string.ascii_uppercase

#: ASCII-only case folding, matching :mod:`~kryptos.algorithms.ciphers.quagmire`.
#: ``str.upper`` is not length-preserving -- ``"ß".upper()`` is ``"SS"`` -- so folding
#: with it before validation would let non-A-Z input expand into extra ciphertext.
_FOLD = str.maketrans(string.ascii_lowercase, string.ascii_uppercase)


def from_keyword(keyword: str) -> str:
    """A mixed alphabet built from ``keyword``, then the unused letters in order.

    Re-exported from :mod:`~kryptos.algorithms.ciphers.quagmire` so a caller building a
    substitution key need not reach into the Kryptos cipher for it. The suite draws
    keywords from the corpus vocabulary, as Kryptos keys on real words.

    >>> from_keyword("KRYPTOS")
    'KRYPTOSABCDEFGHIJLMNQUVWXZ'
    """
    return keyed_alphabet(keyword)


def encrypt(plaintext: str, alphabet: str) -> str:
    """Replace each letter with the one at its position in ``alphabet``.

    >>> encrypt("ATTACK", "KRYPTOSABCDEFGHIJLMNQUVWXZ")
    'KNNKYD'
    """
    return _apply(plaintext, _validate_alphabet(alphabet), encipher=True)


def decrypt(ciphertext: str, alphabet: str) -> str:
    """Inverse of :func:`encrypt`.

    >>> decrypt("KNNKYD", "KRYPTOSABCDEFGHIJLMNQUVWXZ")
    'ATTACK'
    """
    return _apply(ciphertext, _validate_alphabet(alphabet), encipher=False)


def is_identity(alphabet: str) -> bool:
    """Whether the key leaves every letter where it found it.

    A generator screen, matching the hooks Phase 1 left on the other ciphers. The identity
    permutation is a valid draw and a worthless instance: the ciphertext is the plaintext,
    so the row would be solved by reading it.

    >>> is_identity(ALPHABET)
    True
    >>> is_identity(from_keyword("KRYPTOS"))
    False
    """
    return _validate_alphabet(alphabet) == ALPHABET


def fixed_points(alphabet: str) -> list[str]:
    """Letters the key maps to themselves.

    The weaker screen behind :func:`is_identity`. A draw fixing most of the alphabet is not
    the identity but is nearly as easy, and a keyword-built alphabet fixes the tail by
    construction -- ``from_keyword("AB")`` moves nothing at all. The generator rejects on a
    count, not on this list, but the list is what makes a rejection legible.

    >>> fixed_points(from_keyword("KRYPTOS"))
    ['Z']
    >>> len(fixed_points(from_keyword("AB")))
    26
    """
    alphabet = _validate_alphabet(alphabet)
    return [plain for plain, cipher in zip(ALPHABET, alphabet) if plain == cipher]


def _apply(text: str, alphabet: str, *, encipher: bool) -> str:
    source, target = (ALPHABET, alphabet) if encipher else (alphabet, ALPHABET)
    return _normalize(text).translate(str.maketrans(source, target))


def _validate_alphabet(alphabet: str) -> str:
    """A key must be a permutation of A-Z -- every letter present, exactly once.

    Checked rather than assumed because the failure is silent in the wrong direction: an
    alphabet with a repeated letter still enciphers, and still round-trips for the letters
    it happens not to collide on, so a generator would publish rows that decrypt to the
    wrong plaintext at scattered positions rather than failing outright.
    """
    if not isinstance(alphabet, str):
        raise TypeError(f"alphabet must be a string, got {type(alphabet).__name__}")
    folded = alphabet.translate(_FOLD)
    if sorted(folded) != sorted(ALPHABET):
        missing = "".join(sorted(set(ALPHABET) - set(folded)))
        repeated = "".join(sorted({c for c in folded if folded.count(c) > 1}))
        detail = []
        if missing:
            detail.append(f"missing {missing}")
        if repeated:
            detail.append(f"repeated {repeated}")
        if not detail:
            detail.append(f"length {len(folded)}, expected 26")
        raise ValueError(
            f"alphabet must be a permutation of A-Z: {', '.join(detail)}"
        )
    return folded


def _normalize(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError(f"text must be a string, got {type(text).__name__}")
    folded = text.translate(_FOLD)
    for position, ch in enumerate(folded):
        if ch not in ALPHABET:
            raise ValueError(
                f"character {text[position]!r} at position {position} is not a letter; "
                f"the suite's substitution ciphers admit no passthrough characters"
            )
    return folded
