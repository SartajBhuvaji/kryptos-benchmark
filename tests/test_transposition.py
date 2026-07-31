"""Verification for the route transposition cipher.

The hand-computed vector uses a 6-character text and a single stage, small enough to
check by eye, so the implementation is pinned independently of K3. The K3 tests then
close the last box in plan item 1.4 — the baseline's third and final round-trip proof.

The geometry tests are the unusual ones here. K3's route was recovered by search rather
than taken from the design document, so the tests pin both the result *and* the reasoning:
that twelve parameterisations induce one permutation, and that the documented width of 86
matches nothing.
"""

from __future__ import annotations

import json
import pathlib
import random

import pytest

from kryptos.algorithms.baseline import build
from kryptos.algorithms.ciphers import transposition as rt

DIVISORS_OF_336 = [d for d in range(1, 337) if 336 % d == 0]


@pytest.fixture(scope="module")
def k3() -> dict[str, str]:
    with pathlib.Path(build.OUTPUT).open(encoding="utf-8") as fh:
        row = {r["passage"]: r for r in map(json.loads, fh)}["K3"]
    ciphertext = row["problem"]
    plaintext = row["answer_readable"].replace(" ", "")
    assert ciphertext.endswith("?") and plaintext.endswith("?")
    # The trailing '?' is carved but not enciphered; the permutation acts on 336 letters.
    return {"ciphertext": ciphertext[:-1], "plaintext": plaintext[:-1]}


# --- hand-computed vector ---------------------------------------------------------
#
# "ABCDEF" written row-major at width 2 is
#     A B
#     C D
#     E F
# A quarter turn clockwise sends column 0 (A, C, E) to the top row reversed, giving
#     E C A
#     F D B
# read row-major -> ECAFDB


def test_hand_computed_single_stage():
    assert rt.encrypt("ABCDEF", ((2, 1),)) == "ECAFDB"


def test_hand_computed_permutation():
    assert rt.permutation(6, ((2, 1),)) == [4, 2, 0, 5, 3, 1]


def test_hand_computed_inverse():
    assert rt.decrypt("ECAFDB", ((2, 1),)) == "ABCDEF"


def test_four_quarter_turns_is_the_identity():
    assert rt.encrypt("ABCDEF", ((2, 4),)) == "ABCDEF"
    assert rt.encrypt("ABCDEF", ((2, 1),)) == rt.encrypt("ABCDEF", ((2, 5),))


# --- properties -------------------------------------------------------------------


def test_round_trip_over_random_routes():
    rng = random.Random(20260730)
    for _ in range(300):
        length = rng.choice([12, 24, 36, 48, 120, 336])
        divisors = [d for d in range(1, length + 1) if length % d == 0]
        route = tuple(
            (rng.choice(divisors), rng.randrange(4)) for _ in range(rng.randint(1, 3))
        )
        text = "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ?", k=length))
        assert rt.decrypt(rt.encrypt(text, route), route) == text


def test_transposition_always_preserves_the_multiset():
    """Defining property of the family: ciphertext is an exact anagram."""
    rng = random.Random(11)
    for _ in range(100):
        text = "".join(rng.choices("ABCDEFGHIJ", k=48))
        route = ((rng.choice([2, 4, 6, 8, 12, 16, 24]), rng.randrange(4)),)
        assert sorted(rt.encrypt(text, route)) == sorted(text)


def test_permutation_is_a_bijection():
    for width in DIVISORS_OF_336:
        for turns in range(4):
            perm = rt.permutation(336, ((width, turns),))
            assert sorted(perm) == list(range(336))


def test_permutation_is_independent_of_the_text():
    """It is computed on indices, so a route moves positions identically whatever
    characters sit in them — including texts with repeated letters."""
    route = ((8, 1), (24, 1))
    perm = rt.permutation(48, route)

    distinct = "".join(chr(ord("a") + i) for i in range(48))
    repeated = "AB" * 24
    assert rt.encrypt(distinct, route) == "".join(distinct[i] for i in perm)
    assert rt.encrypt(repeated, route) == "".join(repeated[i] for i in perm)


def test_empty_text():
    assert rt.encrypt("", ((1, 1),)) == ""


# --- identity screening -----------------------------------------------------------


def test_is_identity_flags_zero_rotation_routes():
    assert rt.is_identity(336, ((7, 0), (84, 0)))
    assert rt.is_identity(336, ((8, 4),))
    assert not rt.is_identity(336, rt.K3_ROUTE)


def test_width_one_and_full_width_only_reverse_or_do_nothing():
    """A single stage at width 1 or width == length is a strip, so a quarter turn can
    only reverse it — never mix positions. Generators get no diffusion from these."""
    assert rt.encrypt("ABCDEF", ((1, 1),)) == "FEDCBA"  # column strip, reversed
    assert rt.encrypt("ABCDEF", ((6, 1),)) == "ABCDEF"  # row strip, unchanged
    assert rt.is_identity(6, ((6, 1),))


@pytest.mark.parametrize("width", [1, 2, 3, 4, 6, 12])
def test_two_quarter_turns_reverse_the_text_at_any_width(width):
    """A 180-degree turn reverses row-major reading order regardless of grid shape —
    a route of a single doubled turn is therefore never a useful cipher."""
    text = "ABCDEFGHIJKL"
    assert rt.encrypt(text, ((width, 2),)) == text[::-1]


@pytest.mark.parametrize("width", [1, 2, 3, 4, 6, 12])
def test_four_quarter_turns_restore_at_any_width(width):
    text = "ABCDEFGHIJKL"
    assert rt.encrypt(text, ((width, 4),)) == text


# --- K3: the derived geometry -----------------------------------------------------


def test_k3_encrypts_exactly(k3):
    assert rt.encrypt(k3["plaintext"], rt.K3_ROUTE) == k3["ciphertext"]


def test_k3_decrypts_exactly(k3):
    assert rt.decrypt(k3["ciphertext"], rt.K3_ROUTE) == k3["plaintext"]


def test_k3_solver_route_is_the_inverse(k3):
    """The route a solver runs forward on the ciphertext, per the module docstring."""
    assert rt.encrypt(k3["ciphertext"], rt.K3_SOLVER_ROUTE) == k3["plaintext"]


def test_k3_ciphertext_is_an_anagram_of_its_plaintext(k3):
    assert sorted(k3["ciphertext"]) == sorted(k3["plaintext"])


@pytest.mark.parametrize(
    "route",
    [
        ((7, 1), (84, 1)),
        ((14, 1), (42, 1)),
        ((21, 1), (28, 1)),
        ((28, 1), (21, 1)),
        ((42, 1), (14, 1)),
        ((84, 1), (7, 1)),
        ((7, 3), (84, 3)),
        ((14, 3), (42, 3)),
        ((21, 3), (28, 3)),
        ((28, 3), (21, 3)),
        ((42, 3), (14, 3)),
        ((84, 3), (7, 3)),
    ],
)
def test_all_twelve_parameterisations_induce_the_same_permutation(route, k3):
    """Pins the search result: the geometry is uniquely determined, and these twelve
    are descriptions of one permutation rather than twelve different ciphers."""
    assert rt.permutation(336, route) == rt.permutation(336, rt.K3_ROUTE)
    assert rt.encrypt(k3["plaintext"], route) == k3["ciphertext"]


def test_documented_width_86_does_not_divide_k3():
    """The design document's stated width. It cannot tile 336 characters at all."""
    assert 336 % 86 != 0
    with pytest.raises(ValueError, match="does not divide"):
        rt.encrypt("A" * 336, ((86, 1),))


def test_no_single_stage_route_reproduces_k3(k3):
    """K3 is genuinely two-stage — worth pinning, since a one-stage route would be a
    much simpler description and its absence is what justifies the extra stage."""
    for width in DIVISORS_OF_336:
        for turns in range(4):
            assert rt.encrypt(k3["plaintext"], ((width, turns),)) != k3["ciphertext"]


def test_search_finds_exactly_the_twelve(k3):
    """Re-runs the derivation: an exhaustive two-stage sweep over widths dividing 336
    yields twelve matches and no others."""
    matches = [
        (w1, r1, w2, r2)
        for w1 in DIVISORS_OF_336
        for r1 in range(4)
        for w2 in DIVISORS_OF_336
        for r2 in range(4)
        if rt.encrypt(k3["plaintext"], ((w1, r1), (w2, r2))) == k3["ciphertext"]
    ]
    assert len(matches) == 12
    assert {(w1, w2) for w1, _, w2, _ in matches} == {
        (7, 84), (14, 42), (21, 28), (28, 21), (42, 14), (84, 7)
    }
    assert all(w1 * w2 == 588 for w1, _, w2, _ in matches)


# --- input validation -------------------------------------------------------------


def test_empty_route_is_rejected():
    with pytest.raises(ValueError, match="at least one stage"):
        rt.permutation(12, ())


@pytest.mark.parametrize("width", [0, -1, 2.5, "4"])
def test_invalid_width_is_rejected(width):
    with pytest.raises(ValueError):
        rt.permutation(12, ((width, 1),))


def test_non_dividing_width_is_rejected():
    with pytest.raises(ValueError, match="does not divide"):
        rt.permutation(10, ((3, 1),))


def test_malformed_stage_is_rejected():
    with pytest.raises(ValueError, match="pair"):
        rt.permutation(12, (4,))


def test_negative_quarter_turns_rejected():
    with pytest.raises(ValueError, match="quarter_turns"):
        rt.permutation(12, ((4, -1),))


# --- findings from adversarial probing --------------------------------------------


@pytest.mark.parametrize("stage", [(True, 1), (1, True), (False, 1)])
def test_bool_is_not_accepted_as_an_integer(stage):
    """bool subclasses int, so True would silently mean width 1 rather than error."""
    with pytest.raises(ValueError):
        rt.permutation(6, (stage,))


def test_quarter_turns_are_taken_modulo_four():
    assert rt.encrypt("ABCDEF", ((2, 1001),)) == rt.encrypt("ABCDEF", ((2, 1),))


@pytest.mark.parametrize("length", [0, 1, 7])
def test_degenerate_lengths(length):
    text = "ABCDEFG"[:length]
    route = ((max(length, 1), 1),)
    assert rt.decrypt(rt.encrypt(text, route), route) == text


def test_every_entry_point_validates():
    """A non-dividing width must be rejected regardless of which function is called."""
    for call in (
        lambda: rt.encrypt("ABCDEFG", ((3, 1),)),
        lambda: rt.decrypt("ABCDEFG", ((3, 1),)),
        lambda: rt.is_identity(7, ((3, 1),)),
    ):
        with pytest.raises(ValueError, match="does not divide"):
            call()


def test_the_data_alone_cannot_pin_a_permutation(k3):
    """Guards the docstring against overclaiming. K3's plaintext has repeated letters,
    so astronomically many permutations carry it to the ciphertext -- uniqueness is
    relative to the family searched, never established by the pair itself."""
    import math
    from collections import Counter

    counts = Counter(k3["plaintext"])
    consistent = math.prod(math.factorial(n) for n in counts.values())
    assert consistent > 10**300
    assert max(counts.values()) > 1


def test_padded_width_86_still_matches_nothing(k3):
    """Being generous to the design document: pad 336 to 344 so 86 tiles it, then sweep
    every second stage and rotation. Still nothing."""
    padded = k3["plaintext"] + "X" * ((-336) % 86)
    assert len(padded) == 344
    for r1 in range(4):
        for w2 in (d for d in range(1, 345) if 344 % d == 0):
            for r2 in range(4):
                out = rt.encrypt(padded, ((86, r1), (w2, r2)))
                assert out[:336] != k3["ciphertext"]
