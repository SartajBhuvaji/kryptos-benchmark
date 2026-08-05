"""Unicity distance -- how much ciphertext an instance needs before its answer is unique.

This is the suite's **validity gate**, and it is deliberately not its difficulty measure.
The two get conflated constantly and the conflation is the failure mode Phase 7 exists to
avoid: if an instance is published below its unicity distance, more than one plaintext
decrypts it consistently, no scoring metric can distinguish the intended answer from the
alternatives, and every model scores zero. That row then looks exactly like a legitimately
brutal one. Gating on unicity is what makes "no solver cracked this" mean something other
than "this has no answer".

Shannon's result: with ``H(K)`` bits of key and a plaintext language carrying ``D`` bits of
redundancy per character, the expected number of spurious keys falls below one at

    U = H(K) / D

characters. Above ``U`` the answer is unique in principle; below it, it is not.

**The gate is a low floor, and that is the point.** Simple substitution is log2(26!) = 88.4
bits, so U = 27.6 characters; Playfair is log2(25!) = 83.7 bits, so U = 26.1. Every
realistic instance in this suite clears both by an order of magnitude. The gate rejects
pathological draws -- a short rail fence, an over-long Vigenere key against a stub of
ciphertext -- and it ranks nothing. :mod:`kryptos.algorithms.suite.difficulty` does the
ranking, by measuring what a solver actually recovers.

**Entropy here is theoretical keyspace, not effective keyspace, and that is the
conservative choice.** The generators draw keywords from the corpus vocabulary rather than
from random letters, exactly as Kryptos keys on real words, so an attacker who knows that
searches far fewer keys than log2(26!) suggests. Effective entropy is *lower*, which makes
the true unicity distance *shorter*, which means a row clearing the theoretical gate
clears the real one too. Reversing that -- gating on vocabulary-sized entropy -- would
admit instances this module is here to reject.
"""

from __future__ import annotations

import math

#: Bits per character of a uniform 26-letter alphabet: the ceiling on what one character
#: can carry before English spends most of it on redundancy.
LOG2_ALPHABET = math.log2(26)

#: Entropy rate of English in bits per character. Shannon's 1951 guessing experiments put
#: it between 0.6 and 1.3; the upper end of the range usually quoted is 1.5, and that is
#: what is used here. Higher assumed entropy means lower redundancy, a larger unicity
#: distance and a stricter gate, so erring upward errs toward rejecting instances.
ENGLISH_ENTROPY_RATE = 1.5

#: Redundancy of English over the 26-letter alphabet, ``log2(26) - H``. Works out to 3.200,
#: which is the value the cryptographic literature quotes -- it is not independently
#: assumed here, it falls out of the two constants above.
REDUNDANCY = LOG2_ALPHABET - ENGLISH_ENTROPY_RATE


def _log2_factorial(n: int) -> float:
    """``log2(n!)`` without building ``n!``. Exact enough at these sizes, and 36! is large.

    >>> round(_log2_factorial(26), 3)
    88.382
    """
    return math.lgamma(n + 1) / math.log(2)


def general_linear_order(n: int, modulus: int = 26) -> int:
    """Number of invertible ``n``x``n`` matrices over ``Z/modulus`` -- the Hill keyspace.

    ``Z/26`` is not a field, so the usual prime-power formula does not apply directly.
    Since 26 = 2 x 13, the Chinese remainder theorem splits the ring and a matrix is
    invertible mod 26 exactly when it is invertible mod 2 *and* mod 13, giving the product
    of the two prime-field orders. Counting instead over all 26**(n*n) matrices would
    overstate the key by including the singular ones, which no valid instance can use.

    >>> general_linear_order(2)
    157248
    >>> general_linear_order(3)
    1634038189056
    """
    if modulus != 26:
        raise ValueError(f"only Z/26 is factored here, got Z/{modulus}")

    def order_over_prime(p: int) -> int:
        total = 1
        for i in range(n):
            total *= p**n - p**i
        return total

    return order_over_prime(2) * order_over_prime(13)


# Key entropy in bits, per mechanism. Each takes the parameters the instance publishes and
# returns the size of the space the key was drawn from. Where a small integer is part of
# the key -- a period, a grid width -- the *range* it was drawn from contributes, not the
# value itself: knowing a period is 7 tells an attacker nothing they did not already have
# by knowing periods run 1 to 12.


def caesar() -> float:
    """26 shifts, one of which is the identity.

    >>> round(caesar(), 3)
    4.7
    """
    return LOG2_ALPHABET


def affine() -> float:
    """``c = a*p + b``, with ``a`` coprime to 26. Twelve valid multipliers, 26 offsets.

    >>> round(affine(), 3)
    8.285
    """
    return math.log2(12 * 26)


def simple_substitution() -> float:
    """An arbitrary permutation of the alphabet.

    >>> round(simple_substitution(), 3)
    88.382
    """
    return _log2_factorial(26)


def homophonic(symbols: int) -> float:
    """Each of ``symbols`` ciphertext symbols maps to one of 26 plaintext letters.

    An upper bound, and knowingly loose: it counts every assignment, while a usable
    homophonic key must be surjective and must allocate symbols roughly in proportion to
    English letter frequency. Both constraints shrink the real space. Loose in the
    conservative direction -- an overstated key means an overstated unicity distance.

    >>> round(homophonic(40), 3)
    188.018
    """
    return symbols * LOG2_ALPHABET


def vigenere(period: int) -> float:
    """A shift per position in the cycle. The *true* period, not the keyword length --
    a keyword that repeats is a shorter cipher wearing a longer key.

    >>> round(vigenere(8), 3)
    37.604
    """
    return period * LOG2_ALPHABET


def quagmire_iii(period: int) -> float:
    """A mixed alphabet plus an indicator that selects a shift per position.

    >>> round(quagmire_iii(10), 3)
    135.386
    """
    return simple_substitution() + vigenere(period)


def autokey(primer_length: int) -> float:
    """Only the primer is secret; the key then extends with the plaintext itself.

    The extension carries no independent entropy -- it is a function of the message -- so
    the key is the primer and nothing more. That makes autokey's unicity distance tiny
    while its practical difficulty is high, which is precisely why the two measures are
    kept apart in this suite.

    >>> round(autokey(6), 3)
    28.203
    """
    return primer_length * LOG2_ALPHABET


def running_key(key_length: int) -> float:
    """The key is itself English text, so it carries the entropy rate of English.

    Not ``key_length * log2(26)``: a running key drawn from a book is as redundant as the
    message it hides. At 1.5 bits per character against 3.2 of redundancy, U is about
    0.47 of the ciphertext length -- always cleared, for any length. The cipher's
    reputation rests on the cost of the search, not on ambiguity of the answer.

    Named ``key_length`` rather than ``length`` even though a running key must match its
    message character for character. The two are numerically equal and conceptually
    distinct, and the short name collided with the ciphertext length that
    :func:`admits_unique_solution` takes -- which surfaced as an argument clash rather
    than a wrong answer, but only because this is the one mechanism where it could.

    >>> round(running_key(200), 3)
    300.0
    """
    return key_length * ENGLISH_ENTROPY_RATE


def playfair() -> float:
    """A 5x5 square of 25 letters, I and J sharing a cell.

    >>> round(playfair(), 3)
    83.682
    """
    return _log2_factorial(25)


def four_square() -> float:
    """Two independent 25-letter squares.

    >>> round(four_square(), 3)
    167.363
    """
    return 2 * _log2_factorial(25)


def hill(block_size: int) -> float:
    """An invertible ``block_size``-square matrix over ``Z/26``.

    >>> round(hill(2), 3), round(hill(3), 3)
    (17.263, 40.572)
    """
    return math.log2(general_linear_order(block_size))


def bifid(period: int, max_period: int = 12) -> float:
    """A 25-letter Polybius square, plus the period the fractionated pairs are cut on.

    ``period`` is accepted and deliberately unused: what an attacker must search is the
    range periods are drawn from, not the value this instance happened to draw. It stays
    in the signature so a row's published parameters can be splatted in unchanged.

    >>> round(bifid(7), 3)
    87.266
    """
    return _log2_factorial(25) + math.log2(max_period)


def trifid(period: int, max_period: int = 12) -> float:
    """A 27-symbol square -- the alphabet plus one padding symbol -- over three coordinates.

    ``period`` is accepted and unused, for the reason given in :func:`bifid`.

    >>> round(trifid(7), 3)
    96.722
    """
    return _log2_factorial(27) + math.log2(max_period)


def adfgvx(columnar_width: int) -> float:
    """A 6x6 square over letters and digits, then a keyed columnar transposition.

    Two stages, but one key, and both halves must be recovered together -- which is what
    makes it the suite's hardest single-stage entry rather than a multi-stage one.

    >>> round(adfgvx(8), 3)
    153.394
    """
    return _log2_factorial(36) + _log2_factorial(columnar_width)


def rail_fence(max_depth: int = 10) -> float:
    """Depth alone. Two bits of key at a realistic range of depths, which is why this is
    the suite's easy anchor: the ciphertext is longer than its unicity distance always.

    >>> round(rail_fence(), 3)
    3.322
    """
    return math.log2(max_depth)


def columnar(width: int) -> float:
    """A permutation of ``width`` columns.

    >>> round(columnar(8), 3)
    15.299
    """
    return _log2_factorial(width)


#: Every mechanism the suite publishes, mapped to the function computing its key entropy.
#: A generator that adds a cipher without adding it here fails :func:`key_entropy` loudly
#: rather than defaulting to some entropy nobody chose.
MECHANISMS = {
    "caesar": caesar,
    "affine": affine,
    "simple_substitution": simple_substitution,
    "homophonic": homophonic,
    "vigenere": vigenere,
    "quagmire_iii": quagmire_iii,
    "autokey": autokey,
    "running_key": running_key,
    "playfair": playfair,
    "four_square": four_square,
    "hill": hill,
    "bifid": bifid,
    "trifid": trifid,
    "adfgvx": adfgvx,
    "rail_fence": rail_fence,
    "columnar": columnar,
}


def key_entropy(mechanism: str, **parameters: int) -> float:
    """Bits of key for ``mechanism``, given the parameters that instance published.

    >>> round(key_entropy("playfair"), 3)
    83.682
    >>> round(key_entropy("vigenere", period=8), 3)
    37.604
    """
    try:
        compute = MECHANISMS[mechanism]
    except KeyError:
        known = ", ".join(sorted(MECHANISMS))
        raise ValueError(f"unknown mechanism {mechanism!r}; known: {known}") from None
    return compute(**parameters)


def unicity_distance(mechanism: str, **parameters: int) -> float:
    """Characters of ciphertext at which ``mechanism``'s answer becomes unique.

    >>> round(unicity_distance("simple_substitution"), 2)
    27.62
    >>> round(unicity_distance("playfair"), 2)
    26.15
    """
    return key_entropy(mechanism, **parameters) / REDUNDANCY


def admits_unique_solution(
    mechanism: str, ciphertext_length: int, **parameters: int
) -> bool:
    """Whether ``ciphertext_length`` characters give the instance exactly one answer.

    The gate the generator applies before an instance is allowed into the pool. Compared
    against the *ceiling* of the unicity distance, since a fractional character is not
    available to a solver -- 27.62 characters means 28.

    The first parameter is spelled out rather than called ``length`` because ``**parameters``
    carries whatever the mechanism publishes, and a mechanism with a ``length`` of its own
    would bind to this argument instead. :func:`running_key` had exactly that name.

    >>> admits_unique_solution("simple_substitution", 200)
    True
    >>> admits_unique_solution("simple_substitution", 20)
    False
    >>> admits_unique_solution("running_key", 200, key_length=200)
    True
    """
    return ciphertext_length >= math.ceil(unicity_distance(mechanism, **parameters))
