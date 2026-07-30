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
    """ABSCISSA repeats letters but still steps through 8 distinct positions."""
    assert quagmire.period("PALIMPSEST", "KRYPTOS") == 10
    assert quagmire.period("ABSCISSA", "KRYPTOS") == 8


@pytest.mark.parametrize(
    "indicator,expected",
    [("ABAB", 2), ("ABCABCABC", 3), ("XYXYXY", 2), ("KKKKK", 1), ("ABCD", 4)],
)
def test_period_is_the_minimal_repeat_not_the_keyword_length(indicator, expected):
    """Both Kryptos indicators are aperiodic, so this only bites on generated keys:
    a solver analysing ABAB correctly reports period 2, and ground truth claiming 4
    would mark that correct answer wrong."""
    assert quagmire.period(indicator, "KRYPTOS") == expected
    assert quagmire.key_length(indicator) == len(indicator)


def test_period_depends_on_the_keyed_alphabet():
    """Shifts index into the keyed alphabet, so the period is not alphabet-free."""
    assert quagmire.period("KA", "KRYPTOS") != 0  # K and A differ under KRYPTOS
    assert quagmire.key_length("KA") == 2


def test_shift_schedule_indexes_into_the_keyed_alphabet():
    assert quagmire.shift_schedule("KRY", "KRYPTOS") == [0, 1, 2]


def test_shift_schedule_uses_the_keyed_alphabet_not_plain_az():
    """Indexing into A-Z instead would silently produce a different cipher."""
    assert quagmire.shift_schedule("KRY", "KRYPTOS") != [
        string.ascii_uppercase.index(c) for c in "KRY"
    ]


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
    """Shows the indicator is load-bearing. Note this does NOT establish the alignment
    convention -- see test_a_aligned_convention_also_decrypts below."""
    row = rows[passage]
    assert quagmire.decrypt(row["problem"], "KRYPTOS", wrong_indicator) != carved_answer(row)


@pytest.mark.parametrize(
    "passage,wrong_indicator,expected_mismatches",
    [("K1", "ABSCISSA", 56), ("K2", "PALIMPSEST", 323)],
)
def test_swapped_indicator_mismatch_counts(rows, passage, wrong_indicator, expected_mismatches):
    """Pins the figures cited in the module docstring."""
    row = rows[passage]
    got = quagmire.decrypt(row["problem"], "KRYPTOS", wrong_indicator)
    assert sum(a != b for a, b in zip(got, carved_answer(row))) == expected_mismatches


def test_a_aligned_convention_also_decrypts(rows):
    """The honest counterweight: decryption alone does not pick the alignment.

    The A-aligned convention differs by the constant keyed.index("A"), which the
    indicator absorbs -- so it reproduces both passages exactly too, just with
    unpronounceable indicators. Keyword recoverability is what settles the choice, and
    this test exists so the docstring's argument cannot quietly rot into the wrong one.
    """
    alphabet = quagmire.keyed_alphabet("KRYPTOS")
    offset = alphabet.index("A")
    for passage, indicator, expected in (
        ("K1", "PALIMPSEST", "DHXVZDGMGE"),
        ("K2", "ABSCISSA", "HIGJVGGH"),
    ):
        rotated = "".join(alphabet[(alphabet.index(c) + offset) % 26] for c in indicator)
        assert rotated == expected, "A-aligned equivalent indicator changed"
        assert not rotated.isalpha() or rotated not in ("PALIMPSEST", "ABSCISSA")

        shifts = [(alphabet.index(c) - offset) % 26 for c in rotated]
        row, key_index, out = rows[passage], 0, []
        for ch in row["problem"]:
            if ch == "?":
                out.append(ch)
                continue
            out.append(alphabet[(alphabet.index(ch) - shifts[key_index % len(shifts)]) % 26])
            key_index += 1
        assert "".join(out) == carved_answer(row)


def test_passthrough_convention_is_pinned_by_k2(rows):
    """The alternative convention -- '?' advancing the key -- is wrong by 282 of 369
    enciphered positions. Pins the figure cited in the module docstring."""
    row, alphabet = rows["K2"], quagmire.keyed_alphabet("KRYPTOS")
    shifts = quagmire.shift_schedule("ABSCISSA", "KRYPTOS")
    plaintext = carved_answer(row)

    mismatches = enciphered = 0
    for i, (c, p) in enumerate(zip(row["problem"], plaintext)):
        if c == "?":
            continue
        enciphered += 1
        if alphabet[(alphabet.index(p) + shifts[i % len(shifts)]) % 26] != c:
            mismatches += 1
    assert (mismatches, enciphered) == (282, 369)


def test_stored_period_matches_the_indicator(rows):
    for passage, indicator in (("K1", "PALIMPSEST"), ("K2", "ABSCISSA")):
        assert rows[passage]["period"] == quagmire.period(indicator, "KRYPTOS")


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


# --- findings from adversarial review ---------------------------------------------


@pytest.mark.parametrize("text", ["\u00df", "A\u00dfB", "\ufb01", "\u0131"])
def test_length_changing_unicode_is_rejected_not_expanded(text):
    """str.upper() is not length-preserving -- "\u00df".upper() is "SS" -- so folding case
    before validation would let non-A-Z input expand into extra ciphertext characters
    instead of being rejected."""
    with pytest.raises(ValueError):
        quagmire.encrypt(text, "KRYPTOS", "PALIMPSEST")


def test_error_position_matches_the_callers_string():
    """Position must index the original text, not a case-folded expansion of it."""
    with pytest.raises(ValueError, match="position 3"):
        quagmire.encrypt("ABC!DEF", "KRYPTOS", "PALIMPSEST")


def test_non_string_text_raises_type_error():
    for bad in (None, 42, b"ABC"):
        with pytest.raises(TypeError):
            quagmire.encrypt(bad, "KRYPTOS", "PALIMPSEST")


def test_degenerate_columns_flags_shift_zero():
    assert quagmire.degenerate_columns("PALIMPSEST", "KRYPTOS") == []
    assert quagmire.degenerate_columns("KEY", "KRYPTOS") == [0]
    assert quagmire.degenerate_columns("KKK", "KRYPTOS") == [0, 1, 2]


def test_all_degenerate_indicator_is_the_identity_map():
    """What degenerate_columns exists to prevent a generator from shipping."""
    assert quagmire.encrypt("HELLOWORLD", "KRYPTOS", "KKK") == "HELLOWORLD"


def test_empty_and_passthrough_only_inputs():
    assert quagmire.encrypt("", "KRYPTOS", "PALIMPSEST") == ""
    assert quagmire.encrypt("???", "KRYPTOS", "PALIMPSEST") == "???"


def test_keyword_covering_the_whole_alphabet():
    kw = string.ascii_uppercase
    assert quagmire.keyed_alphabet(kw) == kw
    assert quagmire.decrypt(quagmire.encrypt("KRYPTOS", kw, kw), kw, kw) == "KRYPTOS"


def test_module_doctests_run():
    """pytest does not collect doctests by default; run them explicitly so the
    docstring examples cannot drift."""
    import doctest

    result = doctest.testmod(quagmire, verbose=False)
    assert result.failed == 0
    assert result.attempted > 0
