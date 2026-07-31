"""Verification for the Hill cipher over Z/26.

The hand-computed vector is the textbook one, checked here from first principles rather
than by rerunning the implementation:

    K = ((3, 3), (2, 5)),  plaintext HELP
    H=7 E=4  ->  3*7+3*4 = 33 = 7  (mod 26) -> H
                 2*7+5*4 = 34 = 8  (mod 26) -> I
    L=11 P=15 -> 3*11+3*15 = 78 = 0  (mod 26) -> A
                 2*11+5*15 = 97 = 19 (mod 26) -> T
    ciphertext HIAT

Invertibility is the part worth testing hard. 26 = 2 x 13 is composite, so a non-zero
determinant is not sufficient, and generators that only check ``det != 0`` will produce
undecryptable keys.
"""

from __future__ import annotations

import math
import random
import string

import pytest

from kryptos.algorithms.ciphers import hill

TEXTBOOK_KEY = ((3, 3), (2, 5))


# --- hand-computed vector ---------------------------------------------------------


def test_hand_computed_encryption():
    assert hill.encrypt("HELP", TEXTBOOK_KEY) == "HIAT"


def test_hand_computed_decryption():
    assert hill.decrypt("HIAT", TEXTBOOK_KEY) == "HELP"


def test_hand_computed_determinant():
    # 3*5 - 3*2 = 9
    assert hill.determinant(TEXTBOOK_KEY) == 9


def test_hand_computed_inverse():
    # det 9, and 9 * 3 = 27 = 1 (mod 26), so det^-1 = 3.
    # adj = ((5, -3), (-2, 3)) = ((5, 23), (24, 3)) mod 26
    # inv = 3 * adj = ((15, 69), (72, 9)) = ((15, 17), (20, 9)) mod 26
    assert hill.inverse(TEXTBOOK_KEY) == ((15, 17), (20, 9))


def test_inverse_times_matrix_is_the_identity():
    product = hill.multiply(TEXTBOOK_KEY, hill.inverse(TEXTBOOK_KEY))
    assert product == ((1, 0), (0, 1))


# --- invertibility over a composite modulus ---------------------------------------


@pytest.mark.parametrize(
    "matrix,det,reason",
    [
        (((2, 4), (6, 8)), 18, "even determinant shares the factor 2"),
        (((1, 2), (3, 4)), 24, "even determinant"),
        (((1, 0), (0, 13)), 13, "determinant is a multiple of 13"),
        (((2, 0), (0, 1)), 2, "even determinant"),
        (((1, 1), (1, 1)), 0, "singular over the integers too"),
    ],
)
def test_non_invertible_matrices_are_rejected(matrix, det, reason):
    """The plan's 'deliberately non-invertible matrix' case. Note two of these have a
    perfectly non-zero determinant — checking det != 0 is not enough over Z/26."""
    assert hill.determinant(matrix) == det, reason
    assert not hill.is_invertible(matrix)
    with pytest.raises(ValueError, match="not invertible"):
        hill.inverse(matrix)


def test_non_zero_determinant_is_not_sufficient():
    """Stated explicitly because it is the trap: 18 != 0 but gcd(18, 26) == 2."""
    matrix = ((2, 4), (6, 8))
    assert hill.determinant(matrix) != 0
    assert math.gcd(hill.determinant(matrix), 26) != 1
    assert not hill.is_invertible(matrix)


def test_invertibility_matches_gcd_over_every_two_by_two_determinant():
    for det in range(26):
        expected = math.gcd(det, 26) == 1
        matrix = ((1, 0), (0, det))
        assert hill.is_invertible(matrix) is expected


def test_units_mod_26_are_exactly_the_twelve_coprime_residues():
    units = [d for d in range(26) if hill.is_invertible(((1, 0), (0, d)))]
    assert units == [1, 3, 5, 7, 9, 11, 15, 17, 19, 21, 23, 25]
    assert len(units) == 12  # Euler phi(26)


# --- properties -------------------------------------------------------------------


def _random_invertible(rng, size):
    while True:
        matrix = tuple(
            tuple(rng.randrange(26) for _ in range(size)) for _ in range(size)
        )
        if hill.is_invertible(matrix):
            return matrix


def test_round_trip_over_random_invertible_keys():
    rng = random.Random(20260730)
    for _ in range(200):
        size = rng.choice([2, 2, 2, 3])
        matrix = _random_invertible(rng, size)
        text = "".join(rng.choices(string.ascii_uppercase, k=size * rng.randint(1, 8)))
        assert hill.decrypt(hill.encrypt(text, matrix), matrix) == text


def test_encryption_preserves_length():
    rng = random.Random(3)
    matrix = _random_invertible(rng, 2)
    for length in (2, 4, 20, 100):
        text = "A" * length
        assert len(hill.encrypt(text, matrix)) == length


def test_identity_matrix_is_the_identity_cipher():
    identity = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
    assert hill.encrypt("KRYPTO", identity) == "KRYPTO"  # 6 letters = 2 blocks of 3


def test_three_by_three_round_trip():
    matrix = ((6, 24, 1), (13, 16, 10), (20, 17, 15))  # classic invertible 3x3
    assert hill.is_invertible(matrix)
    assert hill.decrypt(hill.encrypt("ACTNOW", matrix), matrix) == "ACTNOW"


def test_one_by_one_is_a_multiplicative_shift():
    """Degenerate but legal: a 1x1 key multiplies each letter by a unit."""
    assert hill.is_invertible(((3,),))
    assert hill.encrypt("B", ((3,),)) == "D"  # B=1 -> 3 -> D
    assert hill.decrypt("D", ((3,),)) == "B"


# --- known-plaintext attack -------------------------------------------------------


def test_recover_key_from_the_textbook_pair():
    assert hill.recover_key("HELP", "HIAT", 2) == TEXTBOOK_KEY


def test_recover_key_over_random_keys():
    rng = random.Random(99)
    for _ in range(60):
        size = rng.choice([2, 3])
        matrix = _random_invertible(rng, size)
        # Enough blocks that some selection is invertible. A random 3x3 over Z/26 is
        # invertible only ~37% of the time (it must invert mod 2 AND mod 13), so a bare
        # `size` blocks is often not enough — the attack needs slack, not just parity.
        plain = "".join(rng.choices(string.ascii_uppercase, k=size * (size + 8)))
        cipher = hill.encrypt(plain, matrix)
        assert hill.recover_key(plain, cipher, size) == matrix


def test_recover_key_searches_past_singular_blocks():
    """The first blocks may form a singular matrix; extra known text should rescue it."""
    matrix = TEXTBOOK_KEY
    # AAAA gives two identical blocks -> singular; append blocks that are not.
    plain = "AAAAHELP"
    cipher = hill.encrypt(plain, matrix)
    assert hill.recover_key(plain, cipher, 2) == matrix


def test_recover_key_needs_enough_blocks():
    with pytest.raises(ValueError, match="at least 2 blocks"):
        hill.recover_key("HE", "HI", 2)


def test_recover_key_reports_when_no_blocks_are_invertible():
    matrix = TEXTBOOK_KEY
    plain = "AAAAAA"  # every block identical -> no invertible selection
    cipher = hill.encrypt(plain, matrix)
    with pytest.raises(ValueError, match="invertible"):
        hill.recover_key(plain, cipher, 2)


def test_recover_key_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="lengths differ"):
        hill.recover_key("HELP", "HIA", 2)


# --- input validation -------------------------------------------------------------


def test_block_misalignment_is_rejected_not_padded():
    with pytest.raises(ValueError, match="not a multiple of block size"):
        hill.encrypt("HEL", TEXTBOOK_KEY)


def test_passthrough_character_is_rejected():
    """Unlike Quagmire and the route cipher, a '?' would shift every later letter into
    a different block, so it cannot be carried through."""
    with pytest.raises(ValueError, match="no passthrough"):
        hill.encrypt("HE?P", TEXTBOOK_KEY)


def test_lowercase_is_folded():
    assert hill.encrypt("help", TEXTBOOK_KEY) == "HIAT"


def test_length_changing_unicode_is_rejected():
    with pytest.raises(ValueError, match="not a letter"):
        hill.encrypt("HßLP", TEXTBOOK_KEY)


def test_non_string_text_rejected():
    with pytest.raises(TypeError):
        hill.encrypt(None, TEXTBOOK_KEY)


@pytest.mark.parametrize("bad", [(), ((),), ((1, 2), (3,)), ((1, "x"),), (((True, 1),))])
def test_malformed_matrix_is_rejected(bad):
    with pytest.raises(ValueError):
        hill.determinant(bad)


def test_bool_block_size_rejected():
    with pytest.raises(ValueError, match="block_size"):
        hill.recover_key("HELP", "HIAT", True)


def test_multiply_shape_mismatch():
    with pytest.raises(ValueError, match="shape mismatch"):
        hill.multiply(((1, 2), (3, 4)), ((1, 2, 3),))
