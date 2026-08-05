"""The suite's validity gate: enough ciphertext that the answer is unique."""

from __future__ import annotations

import inspect
import math
from math import gcd

import pytest

from kryptos.algorithms.suite import unicity


def test_redundancy_is_derived_rather_than_asserted():
    """3.2 bits per character is the figure the literature quotes for English.

    It is not typed in here as a constant of its own -- it falls out of log2(26) minus the
    assumed entropy rate. If someone revises the entropy rate, redundancy moves with it and
    every unicity distance in the suite moves too, which is the intended coupling.
    """
    assert unicity.REDUNDANCY == pytest.approx(3.2, abs=0.005)
    assert unicity.REDUNDANCY == unicity.LOG2_ALPHABET - unicity.ENGLISH_ENTROPY_RATE


@pytest.mark.parametrize(
    "n, expected",
    [
        (1, 12),  # the units of Z/26, i.e. Euler's totient of 26
        (2, 157248),
        (3, 1634038189056),
    ],
)
def test_hill_keyspace_counts_invertible_matrices(n, expected):
    assert unicity.general_linear_order(n) == expected


def test_hill_keyspace_matches_an_exhaustive_count():
    """The CRT formula, checked against brute force rather than trusted.

    Z/26 is not a field, so the textbook prime-power formula does not apply and the split
    into mod 2 and mod 13 is the part that could be wrong. Counting all 26**4 two-by-two
    matrices settles it: a matrix over Z/26 is invertible exactly when its determinant is
    a unit, i.e. coprime to 26.
    """
    invertible = sum(
        1
        for a in range(26)
        for b in range(26)
        for c in range(26)
        for d in range(26)
        if gcd((a * d - b * c) % 26, 26) == 1
    )
    assert invertible == unicity.general_linear_order(2)


def test_only_z26_is_factored():
    """The CRT split is hardcoded to 26 = 2 x 13. Another modulus must raise, not answer."""
    with pytest.raises(ValueError, match="only Z/26"):
        unicity.general_linear_order(2, modulus=25)


@pytest.mark.parametrize(
    "mechanism, parameters, expected",
    [
        ("simple_substitution", {}, 27.62),
        ("playfair", {}, 26.15),
        ("caesar", {}, 1.47),
        ("affine", {}, 2.59),
        ("four_square", {}, 52.29),
        ("vigenere", {"period": 8}, 11.75),
    ],
)
def test_published_unicity_distances(mechanism, parameters, expected):
    """The numbers the module docstring and the plan both quote. If these move, the prose
    describing the gate as a low floor has to move with them."""
    assert unicity.unicity_distance(mechanism, **parameters) == pytest.approx(
        expected, abs=0.01
    )


def test_the_gate_is_a_low_floor_at_kryptos_sizes():
    """Every mechanism clears unicity at the lengths this benchmark actually publishes.

    Asserted because it is the module's central claim: the gate exists to reject
    pathological draws, not to rank instances. A gate that started rejecting ordinary
    300-character rows would be silently narrowing the suite.
    """
    for mechanism, parameters in _EVERY_MECHANISM:
        distance = unicity.unicity_distance(mechanism, **parameters)
        assert distance < 372, f"{mechanism} needs {distance:.0f} chars, above Kryptos sizes"


#: One representative parameter set per published mechanism, so the sweeps below cover the
#: registry rather than a convenient subset of it.
_EVERY_MECHANISM = [
    ("caesar", {}),
    ("affine", {}),
    ("simple_substitution", {}),
    ("homophonic", {"symbols": 40}),
    ("vigenere", {"period": 8}),
    ("quagmire_iii", {"period": 10}),
    ("autokey", {"primer_length": 6}),
    ("running_key", {"key_length": 300}),
    ("playfair", {}),
    ("four_square", {}),
    ("hill", {"block_size": 3}),
    ("bifid", {"period": 7}),
    ("trifid", {"period": 7}),
    ("adfgvx", {"columnar_width": 8}),
    ("rail_fence", {}),
    ("columnar", {"width": 8}),
    ("route", {"width_choices": 8}),
]


def test_every_registered_mechanism_is_covered_here():
    """A mechanism added to the registry without a parameter set would slip past the
    sweeps above while appearing to be tested."""
    assert sorted(name for name, _ in _EVERY_MECHANISM) == sorted(unicity.MECHANISMS)


@pytest.mark.parametrize("mechanism, parameters", _EVERY_MECHANISM)
def test_every_mechanism_yields_positive_entropy(mechanism, parameters):
    assert unicity.key_entropy(mechanism, **parameters) > 0


def test_an_unregistered_mechanism_raises_and_says_what_is_known():
    """A generator adding a cipher and forgetting the registry gets an error naming the
    alternatives, not a default entropy nobody chose."""
    with pytest.raises(ValueError, match="unknown mechanism 'enigma'") as caught:
        unicity.key_entropy("enigma")
    assert "playfair" in str(caught.value)


def test_the_gate_compares_against_the_ceiling():
    """27.62 characters means 28, because a solver cannot have 0.62 of a character."""
    exact = unicity.unicity_distance("simple_substitution")
    assert 27 < exact < 28
    assert not unicity.admits_unique_solution("simple_substitution", 27)
    assert unicity.admits_unique_solution("simple_substitution", 28)


def test_a_longer_vigenere_period_demands_more_ciphertext():
    """Monotone in the key, which is the whole shape of the Shannon bound."""
    distances = [unicity.unicity_distance("vigenere", period=p) for p in range(1, 13)]
    assert distances == sorted(distances)
    assert len(set(distances)) == len(distances)


def test_autokey_needs_little_ciphertext_despite_being_hard():
    """The case that proves unicity is not a difficulty measure.

    Only the primer is secret -- the key then extends with the plaintext, which carries no
    independent entropy -- so an autokey instance becomes unique after a couple of dozen
    characters while remaining genuinely hard to break. Any attempt to reuse this module
    for ranking would put autokey next to Caesar.
    """
    autokey = unicity.unicity_distance("autokey", primer_length=6)
    substitution = unicity.unicity_distance("simple_substitution")
    assert autokey < substitution
    assert unicity.admits_unique_solution("autokey", 100, primer_length=6)


def test_a_running_key_always_clears_its_own_length():
    """The key is English, so it is as redundant as the message. U works out near 0.47 of
    the ciphertext length, so the instance is always above its own gate -- the cipher is
    hard because the search is expensive, not because the answer is ambiguous."""
    for length in (100, 200, 400, 800):
        assert unicity.admits_unique_solution("running_key", length, key_length=length)
        assert unicity.unicity_distance("running_key", key_length=length) < length


def test_a_period_does_not_change_a_fractionating_key():
    """bifid and trifid accept the drawn period and ignore it on purpose: what must be
    searched is the range periods come from, not the value one instance landed on."""
    assert unicity.key_entropy("bifid", period=3) == unicity.key_entropy("bifid", period=11)
    assert unicity.key_entropy("trifid", period=3) == unicity.key_entropy("trifid", period=11)
    wider = unicity.key_entropy("bifid", period=7, max_period=24)
    assert wider > unicity.key_entropy("bifid", period=7, max_period=12)


def test_no_mechanism_parameter_shadows_the_gates_own_argument():
    """``admits_unique_solution`` takes a ciphertext length positionally and everything else
    through ``**parameters``, so a mechanism parameter sharing that name binds to the wrong
    argument and raises. ``running_key`` shipped with ``length`` and did exactly that.

    Caught here rather than at the call site because the clash only appears for the one
    mechanism that owns the name -- the other fifteen pass, and the gap reads as a bug in
    running key rather than in the signature.
    """
    reserved = {"mechanism", "ciphertext_length"}
    for name, compute in unicity.MECHANISMS.items():
        taken = set(inspect.signature(compute).parameters)
        assert not (taken & reserved), f"{name} takes {taken & reserved}, which the gate owns"


def test_log2_factorial_agrees_with_the_exact_value():
    """lgamma is used to keep 36! out of memory; it has to agree with the real thing."""
    for n in (5, 12, 25, 26, 27, 36):
        assert unicity._log2_factorial(n) == pytest.approx(
            math.log2(math.factorial(n)), rel=1e-12
        )
