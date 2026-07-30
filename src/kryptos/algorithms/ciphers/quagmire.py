"""Quagmire III polyalphabetic substitution — the cipher behind Kryptos K1 and K2.

A Quagmire III uses one keyed alphabet for both the plaintext and the ciphertext axis,
with the ciphertext alphabet shifted per position. An indicator keyword supplies the
shift schedule and sets the period.

Alignment convention
--------------------
The shift for a position is the index of that position's indicator letter **within the
keyed alphabet**,

    ciphertext = keyed[(keyed.index(plaintext) + keyed.index(indicator_letter)) % 26]

which aligns the indicator letter under the *first* letter of the keyed alphabet (``K``
for ``KRYPTOS``) rather than under ``A``.

Decryption alone cannot justify this choice. The A-aligned convention differs only by the
constant ``keyed.index("A")``, which any indicator keyword can absorb — under it, K1 and
K2 also decrypt exactly, with indicators ``DHXVZDGMGE`` and ``HIGJVGGH``. What settles it
is keyword recoverability: only first-letter alignment yields the pronounceable English
words ``PALIMPSEST`` and ``ABSCISSA``, which is what a solver is searching for and what
Sanborn published.

That the indicator is load-bearing at all is separately confirmed by swapping the two:
K1 under ``ABSCISSA`` mismatches at 56 of 63 positions, K2 under ``PALIMPSEST`` at 323 of
372.

Passthrough characters
----------------------
The literal ``?`` marks carved into K2 and K3 pass through unenciphered and **do not
advance the key**. Verified rather than assumed: under the alternative convention, K2
decrypts differently from its known plaintext at 282 of 369 enciphered positions, while
under this one it matches at every position. ``tests/test_quagmire.py`` pins both numbers.

Generating synthetic ciphers
----------------------------
A shift of zero arises whenever an indicator letter equals the keyed alphabet's first
letter, and such a column copies plaintext straight through. An indicator made entirely
of that letter makes encryption the identity map. Generators should screen indicators
with :func:`degenerate_columns` rather than rediscovering this on inspection of a
suspiciously readable "ciphertext".
"""

from __future__ import annotations

import string

ALPHABET = string.ascii_uppercase

#: Characters copied through unenciphered, consuming no key position.
PASSTHROUGH = frozenset("?")

#: Case folding restricted to ASCII. ``str.upper`` is not length-preserving --
#: ``"ß".upper()`` is ``"SS"`` and ``"ﬁ".upper()`` is ``"FI"`` -- so folding with it
#: before validation would let non-A-Z input expand into extra ciphertext characters
#: instead of being rejected.
_FOLD = str.maketrans(string.ascii_lowercase, ALPHABET)


def keyed_alphabet(keyword: str) -> str:
    """Build a mixed alphabet: keyword letters first (deduplicated), then the rest.

    >>> keyed_alphabet("KRYPTOS")
    'KRYPTOSABCDEFGHIJLMNQUVWXZ'
    >>> keyed_alphabet("ABSCISSA")
    'ABSCIDEFGHJKLMNOPQRTUVWXYZ'
    """
    keyword = _normalize_keyword(keyword, "keyword")

    seen: list[str] = []
    for ch in keyword:
        if ch not in seen:
            seen.append(ch)
    seen.extend(ch for ch in ALPHABET if ch not in seen)
    return "".join(seen)


def key_length(indicator_keyword: str) -> int:
    """Number of letters in the indicator keyword.

    Not the same as :func:`period` — see that function.

    >>> key_length("ABAB")
    4
    """
    return len(_normalize_keyword(indicator_keyword, "indicator_keyword"))


def period(indicator_keyword: str, alphabet_keyword: str) -> int:
    """Length of the shortest repeating cycle in the shift schedule.

    This is neither the keyword's length nor its count of unique letters. ``ABSCISSA``
    repeats letters yet still steps through eight distinct positions, so its period is 8.
    But ``ABAB`` produces the shift sequence ``[s(A), s(B), s(A), s(B)]``, which repeats
    every two positions — its period is 2, and a solver's Kasiski or index-of-coincidence
    analysis will correctly report 2 rather than 4.

    Both Kryptos indicators happen to be aperiodic, so the distinction is invisible there
    and only bites once keywords are randomly generated.

    >>> period("PALIMPSEST", "KRYPTOS"), period("ABSCISSA", "KRYPTOS")
    (10, 8)
    >>> period("ABAB", "KRYPTOS"), period("KKKKK", "KRYPTOS")
    (2, 1)
    """
    shifts = shift_schedule(indicator_keyword, alphabet_keyword)
    n = len(shifts)
    for candidate in range(1, n + 1):
        if n % candidate == 0 and all(shifts[i] == shifts[i % candidate] for i in range(n)):
            return candidate
    return n  # pragma: no cover -- unreachable: candidate == n always satisfies the test


def shift_schedule(indicator_keyword: str, alphabet_keyword: str) -> list[int]:
    """Per-position shifts, one per letter of the indicator keyword.

    Takes the *keyword*, not a prebuilt alphabet: shifts index into the keyed alphabet,
    and passing plain A-Z by mistake would silently yield a different cipher.

    >>> shift_schedule("KRY", "KRYPTOS")
    [0, 1, 2]
    """
    alphabet = keyed_alphabet(alphabet_keyword)
    indicator = _normalize_keyword(indicator_keyword, "indicator_keyword")
    return [alphabet.index(ch) for ch in indicator]


def degenerate_columns(indicator_keyword: str, alphabet_keyword: str) -> list[int]:
    """Indices of shift-zero positions, which copy plaintext through unchanged.

    Screen generated indicators with this: a non-empty result leaks one position in every
    ``period`` verbatim, and a full-length result makes encryption the identity map.

    >>> degenerate_columns("KEY", "KRYPTOS")
    [0]
    >>> degenerate_columns("PALIMPSEST", "KRYPTOS")
    []
    """
    return [i for i, s in enumerate(shift_schedule(indicator_keyword, alphabet_keyword)) if s == 0]


def encrypt(plaintext: str, alphabet_keyword: str, indicator_keyword: str) -> str:
    """Encipher ``plaintext``. Characters in :data:`PASSTHROUGH` are copied unchanged.

    ASCII lowercase is folded to uppercase; any other character is rejected.
    """
    return _apply(plaintext, alphabet_keyword, indicator_keyword, sign=1)


def decrypt(ciphertext: str, alphabet_keyword: str, indicator_keyword: str) -> str:
    """Decipher ``ciphertext``.

    Inverse of :func:`encrypt` for uppercase input; lowercase input round-trips to its
    uppercase form, since case is normalized rather than preserved.
    """
    return _apply(ciphertext, alphabet_keyword, indicator_keyword, sign=-1)


def _apply(text: str, alphabet_keyword: str, indicator_keyword: str, *, sign: int) -> str:
    alphabet = keyed_alphabet(alphabet_keyword)
    shifts = shift_schedule(indicator_keyword, alphabet_keyword)
    size = len(alphabet)
    index_of = {ch: i for i, ch in enumerate(alphabet)}

    out: list[str] = []
    key_index = 0  # advances only on enciphered letters, never on passthrough
    for position, ch in enumerate(_normalize_text(text)):
        if ch in PASSTHROUGH:
            out.append(ch)
            continue
        shift = shifts[key_index % len(shifts)]
        out.append(alphabet[(index_of[ch] + sign * shift) % size])
        key_index += 1
    return "".join(out)


def _normalize_text(text: str) -> str:
    """Fold ASCII case and reject anything that is not a letter or passthrough.

    Length-preserving by construction, so positions in error messages match the caller's
    string and ciphertext length always equals plaintext length.
    """
    if not isinstance(text, str):
        raise TypeError(f"text must be a string, got {type(text).__name__}")

    folded = text.translate(_FOLD)
    for position, ch in enumerate(folded):
        if ch not in ALPHABET and ch not in PASSTHROUGH:
            original = text[position]
            raise ValueError(
                f"character {original!r} at position {position} is neither a letter "
                f"nor a passthrough character ({''.join(sorted(PASSTHROUGH))})"
            )
    return folded


def _normalize_keyword(keyword: str, name: str) -> str:
    if not isinstance(keyword, str):
        raise TypeError(f"{name} must be a string, got {type(keyword).__name__}")
    folded = keyword.translate(_FOLD)
    if not folded:
        raise ValueError(f"{name} must not be empty")
    if not all(ch in ALPHABET for ch in folded):
        raise ValueError(f"{name} must contain only letters A-Z, got {keyword!r}")
    return folded
