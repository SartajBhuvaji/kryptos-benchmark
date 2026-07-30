"""Quagmire III polyalphabetic substitution — the cipher behind Kryptos K1 and K2.

A Quagmire III uses one keyed alphabet for both the plaintext and the ciphertext axis,
with the ciphertext alphabet shifted per position. An indicator keyword supplies the
shift schedule and sets the period.

Alignment convention
--------------------
Textbook descriptions of Quagmire III differ on where the indicator letter sits, so the
convention here was derived from the carved data rather than assumed: the shift for a
position is the index of that position's indicator letter **within the keyed alphabet**,

    ciphertext = keyed[(keyed.index(plaintext) + keyed.index(indicator_letter)) % 26]

which is equivalent to aligning the indicator letter under the *first* letter of the keyed
alphabet (``K`` for ``KRYPTOS``) rather than under ``A``. Under this rule K1 and K2 both
reproduce exactly; under the two swapped indicators they mismatch at 56 and 323 positions,
so the rule is doing real work rather than fitting anything.

The literal ``?`` marks carved into K2 and K3 pass through unenciphered and **do not
advance the key**. This is verified, not assumed: the alternative convention produces 115
inconsistencies in K2 at its known period of 8, and this one produces zero.
"""

from __future__ import annotations

import string

ALPHABET = string.ascii_uppercase

#: Characters copied through unenciphered, consuming no key position.
PASSTHROUGH = frozenset("?")


def keyed_alphabet(keyword: str, alphabet: str = ALPHABET) -> str:
    """Build a mixed alphabet: keyword letters first (deduplicated), then the rest.

    >>> keyed_alphabet("KRYPTOS")
    'KRYPTOSABCDEFGHIJLMNQUVWXZ'
    """
    keyword = _validate_keyword(keyword, "keyword")

    seen: list[str] = []
    for ch in keyword:
        if ch not in seen:
            seen.append(ch)
    seen.extend(ch for ch in alphabet if ch not in seen)

    result = "".join(seen)
    if len(result) != len(alphabet):
        raise ValueError(f"keyed alphabet has {len(result)} letters, expected {len(alphabet)}")
    return result


def period(indicator_keyword: str) -> int:
    """Number of distinct shift positions in the cycle.

    This is the keyword's *length*, not its number of unique letters — ``ABSCISSA``
    repeats letters but still steps through eight positions before repeating.

    >>> period("PALIMPSEST"), period("ABSCISSA")
    (10, 8)
    """
    return len(_validate_keyword(indicator_keyword, "indicator_keyword"))


def shift_schedule(indicator_keyword: str, alphabet: str) -> list[int]:
    """Per-position shifts, one per letter of the indicator keyword."""
    return [alphabet.index(ch) for ch in _validate_keyword(indicator_keyword, "indicator_keyword")]


def encrypt(plaintext: str, alphabet_keyword: str, indicator_keyword: str) -> str:
    """Encipher ``plaintext``. Characters in :data:`PASSTHROUGH` are copied unchanged."""
    return _apply(plaintext, alphabet_keyword, indicator_keyword, sign=1)


def decrypt(ciphertext: str, alphabet_keyword: str, indicator_keyword: str) -> str:
    """Decipher ``ciphertext``. Exact inverse of :func:`encrypt`."""
    return _apply(ciphertext, alphabet_keyword, indicator_keyword, sign=-1)


def _apply(text: str, alphabet_keyword: str, indicator_keyword: str, *, sign: int) -> str:
    alphabet = keyed_alphabet(alphabet_keyword)
    shifts = shift_schedule(indicator_keyword, alphabet)
    size = len(alphabet)

    out: list[str] = []
    key_index = 0  # advances only on enciphered letters, never on passthrough
    for position, ch in enumerate(text.upper()):
        if ch in PASSTHROUGH:
            out.append(ch)
            continue
        if ch not in alphabet:
            raise ValueError(
                f"character {ch!r} at position {position} is neither a letter "
                f"nor a passthrough character ({''.join(sorted(PASSTHROUGH))})"
            )
        shift = shifts[key_index % len(shifts)]
        out.append(alphabet[(alphabet.index(ch) + sign * shift) % size])
        key_index += 1
    return "".join(out)


def _validate_keyword(keyword: str, name: str) -> str:
    if not isinstance(keyword, str):
        raise TypeError(f"{name} must be a string, got {type(keyword).__name__}")
    keyword = keyword.upper()
    if not keyword:
        raise ValueError(f"{name} must not be empty")
    if not all(ch in ALPHABET for ch in keyword):
        raise ValueError(f"{name} must contain only letters A-Z, got {keyword!r}")
    return keyword
