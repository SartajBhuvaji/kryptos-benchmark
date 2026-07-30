"""Verification for the Quagmire III cipher.

The hand-computed vector below uses `CIPHER`/`KEY` rather than Kryptos keys, so the
implementation is pinned independently of the data it will be used to validate. The K1
and K2 checks then close the loop: they are the round-trip proof the baseline
transcription could not have on its own, since Phase 0 had no cipher to run.
"""

from __future__ import annotations

import json
import pathlib
import random
import string

import pytest

from kryptos.algorithms.baseline import build
from kryptos.algorithms.ciphers import quagmire

KRYPTOS_ALPHABET = "KRYPTOSABCDEFGHIJLMNQUVWXZ"


@pytest.fixture(scope="module")
def rows() -> dict[str, dict]:
    with pathlib.Path(build.OUTPUT).open(encoding="utf-8") as fh:
        return {r["passage"]: r for r in map(json.loads, fh)}


def carved_answer(row: dict) -> str:
    """Answer in carved form — spacing stripped, ``?`` retained — so it aligns with
    ``problem`` position for position."""
    return row["answer_readable"].replace(" ", "")


# --- keyed alphabet ---------------------------------------------------------------


def test_kryptos_keyed_alphabet():
    assert quagmire.keyed_alphabet("KRYPTOS") == KRYPTOS_ALPHABET


def test_keyed_alphabet_deduplicates_the_keyword():
    # ABSCISSA repeats A and S; only first occurrences survive.
    assert quagmire.keyed_alphabet("ABSCISSA").startswith("ABSCI")


@pytest.mark.parametrize("keyword", ["KRYPTOS", "ABSCISSA", "PALIMPSEST", "A", "ZZZZ"])
def test_keyed_alphabet_is_always_a_permutation(keyword):
    alphabet = quagmire.keyed_alphabet(keyword)
    assert len(alphabet) == 26
    assert sorted(alphabet) == list(string.ascii_uppercase)


def test_keyed_alphabet_accepts_lowercase():
    assert quagmire.keyed_alphabet("kryptos") == KRYPTOS_ALPHABET


# --- period and shifts ------------------------------------------------------------


def test_period_counts_letters_not_unique_letters():
    """ABSCISSA repeats letters but still steps through 8 positions."""
    assert quagmire.period("PALIMPSEST") == 10
    assert quagmire.period("ABSCISSA") == 8


def test_shift_schedule_indexes_into_the_keyed_alphabet():
    assert quagmire.shift_schedule("KRY", KRYPTOS_ALPHABET) == [0, 1, 2]


# --- hand-computed vector ---------------------------------------------------------
#
# alphabet keyword CIPHER -> CIPHERABDFGJKLMNOQSTUVWXYZ
#   index:                   C0 I1 P2 H3 E4 R5 A6 B7 D8 F9 G10 J11 K12 L13 ...
# indicator KEY -> shifts [K=12, E=4, Y=24], period 3
#
#   A(6)  + 12 = 18 -> S
#   T(19) +  4 = 23 -> X
#   T(19) + 24 = 43 % 26 = 17 -> Q
#   A(6)  + 12 = 18 -> S
#   C(0)  +  4 =  4 -> E
#   K(12) + 24 = 36 % 26 = 10 -> G


def test_hand_computed_alphabet():
    assert quagmire.keyed_alphabet("CIPHER") == "CIPHERABDFGJKLMNOQSTUVWXYZ"


def test_hand_computed_encryption():
    assert quagmire.encrypt("ATTACK", "CIPHER", "KEY") == "SXQSEG"


def test_hand_computed_decryption():
    assert quagmire.decrypt("SXQSEG", "CIPHER", "KEY") == "ATTACK"


def test_passthrough_does_not_advance_the_key():
    """The '?' is copied through and consumes no key position, so every letter after
    it keeps the shift it would have had without the '?' present."""
    assert quagmire.encrypt("AT?TACK", "CIPHER", "KEY") == "SX?QSEG"


def test_passthrough_survives_a_round_trip():
    text = "AT?TAC?K"
    assert quagmire.decrypt(quagmire.encrypt(text, "CIPHER", "KEY"), "CIPHER", "KEY") == text


def test_case_is_normalized():
    assert quagmire.encrypt("attack", "cipher", "key") == "SXQSEG"


# --- properties -------------------------------------------------------------------


def test_round_trip_over_random_keys_and_texts():
    rng = random.Random(20260730)
    for _ in range(200):
        alphabet_kw = "".join(rng.choices(string.ascii_uppercase, k=rng.randint(1, 12)))
        indicator_kw = "".join(rng.choices(string.ascii_uppercase, k=rng.randint(1, 12)))
        text = "".join(rng.choices(string.ascii_uppercase + "?", k=rng.randint(0, 80)))
        encrypted = quagmire.encrypt(text, alphabet_kw, indicator_kw)
        assert quagmire.decrypt(encrypted, alphabet_kw, indicator_kw) == text


def test_encryption_preserves_length_and_passthrough_positions():
    rng = random.Random(7)
    for _ in range(50):
        text = "".join(rng.choices(string.ascii_uppercase + "?", k=60))
        out = quagmire.encrypt(text, "KRYPTOS", "PALIMPSEST")
        assert len(out) == len(text)
        assert [i for i, c in enumerate(out) if c == "?"] == [
            i for i, c in enumerate(text) if c == "?"
        ]


def test_a_single_period_is_a_plain_shift():
    """With a one-letter indicator the cipher degenerates to a monoalphabetic shift of
    the keyed alphabet — a useful sanity anchor on the shift arithmetic."""
    alphabet = quagmire.keyed_alphabet("KRYPTOS")
    shift = alphabet.index("R")
    for ch in string.ascii_uppercase:
        expected = alphabet[(alphabet.index(ch) + shift) % 26]
        assert quagmire.encrypt(ch, "KRYPTOS", "R") == expected


# --- the real proof: K1 and K2 ----------------------------------------------------


@pytest.mark.parametrize("passage,indicator", [("K1", "PALIMPSEST"), ("K2", "ABSCISSA")])
def test_baseline_passage_decrypts_exactly(rows, passage, indicator):
    row = rows[passage]
    assert quagmire.decrypt(row["problem"], "KRYPTOS", indicator) == carved_answer(row)


@pytest.mark.parametrize("passage,indicator", [("K1", "PALIMPSEST"), ("K2", "ABSCISSA")])
def test_baseline_passage_re_encrypts_exactly(rows, passage, indicator):
    row = rows[passage]
    assert quagmire.encrypt(carved_answer(row), "KRYPTOS", indicator) == row["problem"]


@pytest.mark.parametrize(
    "passage,wrong_indicator", [("K1", "ABSCISSA"), ("K2", "PALIMPSEST")]
)
def test_wrong_indicator_does_not_decrypt(rows, passage, wrong_indicator):
    """Guards the two tests above against passing for a trivial reason."""
    row = rows[passage]
    assert quagmire.decrypt(row["problem"], "KRYPTOS", wrong_indicator) != carved_answer(row)


def test_stored_period_matches_the_indicator(rows):
    for passage, indicator in (("K1", "PALIMPSEST"), ("K2", "ABSCISSA")):
        assert rows[passage]["period"] == quagmire.period(indicator)


# --- input validation -------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", "AB1", "AB-C", "AB C"])
def test_invalid_keyword_is_rejected(bad):
    with pytest.raises(ValueError):
        quagmire.keyed_alphabet(bad)


def test_non_string_keyword_is_rejected():
    with pytest.raises(TypeError):
        quagmire.keyed_alphabet(None)


def test_invalid_character_in_text_is_rejected():
    with pytest.raises(ValueError, match="position 3"):
        quagmire.encrypt("ABC!DEF", "KRYPTOS", "PALIMPSEST")


def test_spaces_are_rejected_rather_than_silently_dropped():
    """Callers normalize before encrypting; silently stripping would hide a bug."""
    with pytest.raises(ValueError):
        quagmire.encrypt("HELLO WORLD", "KRYPTOS", "PALIMPSEST")
