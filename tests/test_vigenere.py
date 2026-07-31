"""Verification for the Vigenère cipher.

The module delegates to Quagmire III, so these tests do two jobs: pin Vigenère's own
behaviour against textbook vectors computed independently, and pin the *equivalence* that
justifies delegating at all. If the two ever diverge, the second group fails and the
delegation stops being safe to keep.
"""

from __future__ import annotations

import random
import string

import pytest

from kryptos.algorithms.ciphers import quagmire, vigenere


def reference_vigenere(plaintext: str, key: str) -> str:
    """Textbook Vigenère written from the definition, sharing no code with the module."""
    return "".join(
        chr((ord(p) - 65 + ord(key[i % len(key)]) - 65) % 26 + 65)
        for i, p in enumerate(plaintext)
    )


# --- textbook vectors -------------------------------------------------------------


def test_canonical_vector():
    assert vigenere.encrypt("ATTACKATDAWN", "LEMON") == "LXFOPVEFRNHR"


def test_canonical_vector_decrypts():
    assert vigenere.decrypt("LXFOPVEFRNHR", "LEMON") == "ATTACKATDAWN"


def test_matches_an_independent_reference_implementation():
    rng = random.Random(20260730)
    for _ in range(200):
        text = "".join(rng.choices(string.ascii_uppercase, k=rng.randint(1, 60)))
        key = "".join(rng.choices(string.ascii_uppercase, k=rng.randint(1, 10)))
        assert vigenere.encrypt(text, key) == reference_vigenere(text, key)


def test_single_letter_key_is_a_caesar_shift():
    assert vigenere.encrypt("ABC", "C") == "CDE"
    assert vigenere.encrypt("XYZ", "B") == "YZA"  # wraps


def test_key_a_is_the_identity():
    assert vigenere.encrypt("KRYPTOS", "A") == "KRYPTOS"


# --- the equivalence that justifies delegating ------------------------------------


def test_unkeyed_alphabet_is_the_plain_alphabet():
    assert quagmire.keyed_alphabet(vigenere.UNKEYED) == string.ascii_uppercase


def test_vigenere_equals_quagmire_over_the_unkeyed_alphabet():
    rng = random.Random(4242)
    for _ in range(150):
        text = "".join(rng.choices(string.ascii_uppercase + "?", k=rng.randint(0, 50)))
        key = "".join(rng.choices(string.ascii_uppercase, k=rng.randint(1, 10)))
        assert vigenere.encrypt(text, key) == quagmire.encrypt(text, vigenere.UNKEYED, key)


def test_keyed_alphabet_case_matches_quagmire_directly():
    """With an alphabet keyword supplied, Vigenère *is* Quagmire III — the K4-proxy case."""
    rng = random.Random(7)
    for _ in range(100):
        text = "".join(rng.choices(string.ascii_uppercase, k=rng.randint(1, 40)))
        key = "".join(rng.choices(string.ascii_uppercase, k=rng.randint(1, 8)))
        alphabet_kw = "".join(rng.choices(string.ascii_uppercase, k=rng.randint(1, 8)))
        assert vigenere.encrypt(text, key, alphabet_kw) == quagmire.encrypt(
            text, alphabet_kw, key
        )


def test_keyed_alphabet_actually_changes_the_output():
    """Guards the delegation tests against passing because everything is identical."""
    assert vigenere.encrypt("ATTACK", "LEMON", "KRYPTOS") != vigenere.encrypt(
        "ATTACK", "LEMON"
    )


# --- properties -------------------------------------------------------------------


def test_round_trip():
    rng = random.Random(11)
    for _ in range(200):
        text = "".join(rng.choices(string.ascii_uppercase + "?", k=rng.randint(0, 60)))
        key = "".join(rng.choices(string.ascii_uppercase, k=rng.randint(1, 12)))
        alphabet_kw = rng.choice(["A", "KRYPTOS", "CIPHER"])
        assert vigenere.decrypt(vigenere.encrypt(text, key, alphabet_kw), key, alphabet_kw) == text


def test_passthrough_is_carried_and_does_not_advance_the_key():
    assert vigenere.encrypt("AT?TACK", "KEY") == vigenere.encrypt(
        "ATTACK", "KEY"
    )[:2] + "?" + vigenere.encrypt("ATTACK", "KEY")[2:]


def test_period_is_the_minimal_repeat():
    assert vigenere.period("LEMON") == 5
    assert vigenere.period("ABAB") == 2


# --- input validation -------------------------------------------------------------


def test_empty_key_rejected():
    with pytest.raises(ValueError):
        vigenere.encrypt("ABC", "")


def test_non_letter_in_text_rejected():
    with pytest.raises(ValueError):
        vigenere.encrypt("AB!C", "KEY")
