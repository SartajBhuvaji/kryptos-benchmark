"""Caesar, affine and general substitution -- the suite's monoalphabetic chain.

Three named ciphers over one substitution step: Caesar delegates to affine, affine builds
its alphabet arithmetically and delegates to substitution. The tests below check each layer
on its own terms and then check that the delegation is real rather than three
implementations that happen to agree today.
"""

from __future__ import annotations

import math
import random
import string

import pytest

from kryptos.algorithms.ciphers import affine, caesar, substitution

ALPHABET = string.ascii_uppercase
MESSAGE = "THEQUICKBROWNFOXJUMPSOVERTHELAZYDOG"


def alphabets(seed: int, count: int = 40):
    """Random permutations of A-Z, seeded so a failure is reproducible."""
    rng = random.Random(seed)
    for _ in range(count):
        letters = list(ALPHABET)
        rng.shuffle(letters)
        yield "".join(letters)


# --- substitution ------------------------------------------------------------------


@pytest.mark.parametrize("alphabet", list(alphabets(20260804)))
def test_substitution_round_trips(alphabet):
    assert substitution.decrypt(substitution.encrypt(MESSAGE, alphabet), alphabet) == MESSAGE


@pytest.mark.parametrize("alphabet", list(alphabets(11, count=10)))
def test_substitution_preserves_length_and_letter_multiset_shape(alphabet):
    """A monoalphabetic cipher relabels letters without moving or adding any, so the
    *sorted counts* survive even though the letters do not. That is the property the index
    of coincidence detects, and it is what separates this family from a transposition."""
    ciphertext = substitution.encrypt(MESSAGE, alphabet)
    assert len(ciphertext) == len(MESSAGE)
    counts = lambda text: sorted(text.count(c) for c in set(text))  # noqa: E731
    assert counts(ciphertext) == counts(MESSAGE)


def test_substitution_rejects_a_non_permutation():
    """The failure this guards is silent: a repeated letter still enciphers, and still
    round-trips wherever it does not collide, so rows would decrypt wrongly at scattered
    positions rather than failing."""
    with pytest.raises(ValueError, match="repeated A"):
        substitution.encrypt(MESSAGE, "A" + ALPHABET[1:25] + "A")
    with pytest.raises(ValueError, match="missing Z"):
        substitution.encrypt(MESSAGE, ALPHABET[:25] + "A")
    with pytest.raises(ValueError, match="permutation of A-Z"):
        substitution.encrypt(MESSAGE, "ABC")


def test_substitution_admits_no_passthrough():
    """Unlike the Kryptos ciphers, which carry a carved '?' through untouched."""
    with pytest.raises(ValueError, match="not a letter"):
        substitution.encrypt("ATTACK?AT?DAWN", substitution.from_keyword("KRYPTOS"))


def test_substitution_folds_case_without_changing_length():
    assert substitution.encrypt("attack", ALPHABET) == "ATTACK"


def test_substitution_identity_and_fixed_points_are_screens():
    assert substitution.is_identity(ALPHABET)
    assert not substitution.is_identity(substitution.from_keyword("KRYPTOS"))
    # A keyword whose letters are already in place fixes the whole alphabet: the draw is
    # the identity wearing a keyword, which is exactly what the generator must reject.
    assert substitution.from_keyword("AB") == ALPHABET
    assert len(substitution.fixed_points(substitution.from_keyword("AB"))) == 26
    assert substitution.fixed_points(ALPHABET) == list(ALPHABET)


# --- affine ------------------------------------------------------------------------


def test_affine_multipliers_are_exactly_the_units_of_z26():
    assert affine.MULTIPLIERS == tuple(a for a in range(1, 26) if math.gcd(a, 26) == 1)
    assert len(affine.MULTIPLIERS) == 12
    assert 13 not in affine.MULTIPLIERS  # shares 13
    assert 2 not in affine.MULTIPLIERS  # shares 2


@pytest.mark.parametrize("a", affine.MULTIPLIERS)
@pytest.mark.parametrize("b", [0, 1, 7, 25])
def test_affine_round_trips_over_every_valid_key(a, b):
    assert affine.decrypt(affine.encrypt(MESSAGE, a, b), a, b) == MESSAGE


@pytest.mark.parametrize("a", [2, 4, 13, 26, 0])
def test_affine_rejects_a_multiplier_sharing_a_factor_with_26(a):
    """Not a style preference: with gcd(a, 26) > 1 the map is not injective. a=2 sends both
    A and N to A, so 26 letters collapse onto 13 and no decryption exists."""
    with pytest.raises(ValueError, match="shares a factor with 26"):
        affine.encrypt(MESSAGE, a, 3)


def test_the_rejected_multipliers_really_do_collide():
    """The claim behind the guard, checked rather than asserted in prose."""
    for a in (2, 4, 13):
        images = {(a * i + 3) % 26 for i in range(26)}
        assert len(images) < 26


@pytest.mark.parametrize("a", affine.MULTIPLIERS)
@pytest.mark.parametrize("b", [0, 5, 20])
def test_every_affine_key_induces_a_valid_substitution_alphabet(a, b):
    assert sorted(affine.alphabet(a, b)) == list(ALPHABET)


def test_affine_screens_report_degenerate_and_duplicate_draws():
    assert affine.is_identity(1, 0)
    assert not affine.is_identity(1, 3)
    assert not affine.is_identity(5, 0)
    assert affine.is_shift(1) and not affine.is_shift(5)
    assert affine.is_invertible(5) and not affine.is_invertible(2)


# --- caesar ------------------------------------------------------------------------


@pytest.mark.parametrize("shift", range(26))
def test_caesar_round_trips_over_every_shift(shift):
    assert caesar.decrypt(caesar.encrypt(MESSAGE, shift), shift) == MESSAGE


def test_caesar_matches_the_textbook_vector():
    assert caesar.encrypt("ATTACKATDAWN", 3) == "DWWDFNDWGDZQ"


def test_rot13_is_its_own_inverse_and_is_screened():
    """Screened because ROT13 appears verbatim in every training corpus this benchmark
    scores against, so an instance drawn on it measures recall rather than cryptanalysis."""
    assert caesar.encrypt(caesar.encrypt(MESSAGE, 13), 13) == MESSAGE
    assert caesar.is_involution(13)
    assert not caesar.is_involution(3)


@pytest.mark.parametrize("shift", [0, 26, 52, -26])
def test_caesar_identity_screen_is_modular(shift):
    assert caesar.is_identity(shift)
    assert caesar.encrypt(MESSAGE, shift) == MESSAGE


# --- the delegation itself ---------------------------------------------------------


@pytest.mark.parametrize("shift", range(26))
def test_caesar_is_affine_with_multiplier_one(shift):
    """The delegation, asserted. If Caesar ever grows its own shift arithmetic, this is
    what notices -- the two would agree at first and drift on the first change to either."""
    assert caesar.encrypt(MESSAGE, shift) == affine.encrypt(MESSAGE, 1, shift)


@pytest.mark.parametrize("a", affine.MULTIPLIERS)
def test_affine_is_substitution_over_its_generated_alphabet(a):
    assert affine.encrypt(MESSAGE, a, 9) == substitution.encrypt(MESSAGE, affine.alphabet(a, 9))


@pytest.mark.parametrize("shift", [1, 3, 7, 25])
def test_caesar_agrees_with_vigenere_at_period_one(shift):
    """Caesar and a one-letter Vigenere key are the same arithmetic reached by two routes.
    Both are carried because the framings ask different things of a solver, but they must
    not disagree about the ciphertext."""
    from kryptos.algorithms.ciphers import vigenere

    assert caesar.encrypt(MESSAGE, shift) == vigenere.encrypt(MESSAGE, ALPHABET[shift])


@pytest.mark.parametrize("indicator", ALPHABET)
def test_quagmire_at_period_one_is_a_rotation_within_its_keyed_alphabet(indicator):
    """A single-letter indicator makes Quagmire III monoalphabetic -- but not a substitution
    over the keyed alphabet, which is the natural guess and is wrong.

    Quagmire III carries the *same* mixed alphabet on both axes, so a zero shift maps every
    letter to itself: ``encrypt(text, "KRYPTOS", "K")`` returns the plaintext untouched. All
    of the substitution comes from the shift, and the induced alphabet is the keyed alphabet
    rotated by it -- indexed by position *within the keyed alphabet*, not within A-Z.

    Asserted across all 26 indicators because it pins the convention. A change to Quagmire's
    axis handling would still round-trip against itself and would silently stop agreeing
    here, which is the only place the two families are compared.
    """
    from kryptos.algorithms.ciphers import quagmire

    keyed = quagmire.keyed_alphabet("KRYPTOS")
    shift = quagmire.shift_schedule(indicator, "KRYPTOS")[0]
    induced = "".join(keyed[(keyed.index(p) + shift) % 26] for p in ALPHABET)
    assert quagmire.encrypt(MESSAGE, "KRYPTOS", indicator) == substitution.encrypt(
        MESSAGE, induced
    )


def test_quagmire_is_the_identity_at_zero_shift():
    """The corollary that makes the test above necessary, and a screen the isomorph
    generator already relies on: an indicator whose shift is zero enciphers nothing."""
    from kryptos.algorithms.ciphers import quagmire

    assert quagmire.shift_schedule("K", "KRYPTOS") == [0]
    assert quagmire.encrypt(MESSAGE, "KRYPTOS", "K") == MESSAGE


# --- what the suite will draw on ---------------------------------------------------


def test_the_three_mechanisms_have_the_keyspaces_unicity_assumes():
    """The entropy figures in suite/unicity.py are counts of these keyspaces. If a cipher's
    key set changes without that module changing, every unicity distance built on it is
    quietly wrong."""
    from kryptos.algorithms.suite import unicity

    assert unicity.key_entropy("caesar") == pytest.approx(math.log2(26))
    assert unicity.key_entropy("affine") == pytest.approx(
        math.log2(len(affine.MULTIPLIERS) * 26)
    )
    assert unicity.key_entropy("simple_substitution") == pytest.approx(
        math.log2(math.factorial(26))
    )
