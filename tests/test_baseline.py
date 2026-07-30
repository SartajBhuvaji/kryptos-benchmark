"""Verification for the Kryptos baseline dataset.

Cipher implementations are deliberately out of scope for this stage, so correctness of
the 869 transcribed characters cannot rest on round-tripping them through a solver.
Instead it rests on four checks that need no cipher implementation and that each fail
on a single altered character:

* length checksums (63/372/337/97 = 869)
* plaintext/ciphertext length preservation, and matching ``?`` positions
* the K3 anagram identity -- transposition permutes, so the two letter multisets are equal
* Quagmire III periodic consistency at the stated periods 10 and 8

The periodic check is the strongest of these and deserves a note. In Quagmire III every
position sharing ``index mod period`` is enciphered by one fixed monoalphabetic map, so
bucketing aligned plaintext/ciphertext pairs by residue must yield a consistent injective
mapping per bucket. Control cases at wrong periods are asserted to fail, so the check is
known to discriminate rather than passing vacuously.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

import pytest

from kryptos.algorithms.baseline import build, source as src
from kryptos.algorithms.baseline.schema import ANOMALY_FIELDS, CRIB_FIELDS, FIELDS

DATA = build.OUTPUT


def carved_answer(row: dict) -> str:
    """Answer in carved form: spacing stripped but literal ``?`` kept, so it aligns
    position-for-position with ``problem``. Derived rather than stored -- the dataset
    keeps one canonical answer (letters only) plus a readable form."""
    return build.normalize(row["answer_readable"])

EXPECTED_LENGTHS = {"K1": 63, "K2": 372, "K3": 337, "K4": 97}
LEFT_PANEL_TOTAL = 869


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    with DATA.open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


@pytest.fixture(scope="module")
def by_passage(rows) -> dict[str, dict]:
    return {r["passage"]: r for r in rows}


# --- provenance ------------------------------------------------------------------


def test_carved_lines_reconstruct_the_left_panel():
    flat = "".join(src.CARVED_LINES)
    assert len(flat) == LEFT_PANEL_TOTAL
    assert flat == src.K1_CIPHERTEXT + src.K2_CIPHERTEXT + src.K3_CIPHERTEXT + src.K4_CIPHERTEXT


def test_committed_artifact_matches_source(rows):
    assert build.serialize(build.build()) == DATA.read_text(encoding="utf-8")


# --- checksums -------------------------------------------------------------------


@pytest.mark.parametrize("passage,expected", EXPECTED_LENGTHS.items())
def test_ciphertext_lengths(by_passage, passage, expected):
    assert by_passage[passage]["problem_length"] == expected
    assert len(by_passage[passage]["problem"]) == expected


def test_left_panel_total(rows):
    assert sum(r["problem_length"] for r in rows) == LEFT_PANEL_TOTAL


def test_left_panel_letter_and_question_mark_split(rows):
    """The left panel is documented as 865 letters plus 4 question marks."""
    assert sum(len(r["problem_letters_only"]) for r in rows) == 865
    assert sum(r["problem"].count("?") for r in rows) == 4


# --- plaintext/ciphertext correspondence ------------------------------------------


@pytest.mark.parametrize("passage", ["K1", "K2", "K3"])
def test_length_is_preserved(by_passage, passage):
    """Substitution and transposition both preserve length, so a mismatch means one of
    the two strings is wrong -- this is what caught the K2 ending discrepancy."""
    row = by_passage[passage]
    assert len(carved_answer(row)) == len(row["problem"])


@pytest.mark.parametrize("passage", ["K1", "K2", "K3"])
def test_question_marks_align(by_passage, passage):
    """``?`` is carved literally and passes through unenciphered, so it must sit at
    identical offsets in both strings."""
    row = by_passage[passage]
    positions = lambda s: [i for i, ch in enumerate(s) if ch == "?"]
    assert positions(row["problem"]) == positions(carved_answer(row))


def test_k3_is_an_exact_anagram(by_passage):
    row = by_passage["K3"]
    assert Counter(row["problem_letters_only"]) == Counter(row["answer"])


# --- Quagmire III periodic consistency --------------------------------------------


def periodic_violations(ciphertext: str, plaintext: str, period: int) -> list[tuple]:
    """Return positions where the residue-class mapping is not a consistent bijection.

    The key advances only on enciphered letters: a literal ``?`` is skipped without
    consuming a key position. That convention is not a guess -- under the alternative
    (``?`` consumes a slot) K2 shows 115 violations at its known period of 8, and under
    this one it shows zero.
    """
    buckets: dict[int, dict[str, str]] = defaultdict(dict)
    violations: list[tuple] = []
    key_index = 0
    for i, (c, p) in enumerate(zip(ciphertext, plaintext)):
        if c == "?" or p == "?":
            continue
        mapping = buckets[key_index % period]
        if p in mapping and mapping[p] != c:
            violations.append((i, p, mapping[p], c))
        mapping[p] = c
        key_index += 1
    for residue, mapping in buckets.items():
        values = list(mapping.values())
        if len(values) != len(set(values)):
            violations.append((-1, residue, "not-injective", ""))
    return violations


@pytest.mark.parametrize("passage,period", [("K1", 10), ("K2", 8)])
def test_quagmire_periodic_consistency(by_passage, passage, period):
    row = by_passage[passage]
    assert row["period"] == period
    assert periodic_violations(row["problem"], carved_answer(row), period) == []


@pytest.mark.parametrize("passage,wrong_period", [("K1", 7), ("K1", 9), ("K2", 6), ("K2", 11)])
def test_periodic_check_rejects_wrong_periods(by_passage, passage, wrong_period):
    """Guards the check above against passing vacuously."""
    row = by_passage[passage]
    assert periodic_violations(row["problem"], carved_answer(row), wrong_period) != []


# --- K4 --------------------------------------------------------------------------


def test_k4_is_unsolved(by_passage):
    row = by_passage["K4"]
    assert row["solved"] is False
    assert row["answer"] is None
    assert row["answer_readable"] is None
    assert row["solution"] is None
    assert row["cipher_family"] == "unknown"
    assert row["period"] is None


def test_k4_scoring_does_not_claim_a_reference_plaintext(by_passage):
    """Only 24 of K4's 97 plaintext characters are known, so full-text CER is undefined."""
    row = by_passage["K4"]
    assert row["scoring_metric"] == "crib_match"
    assert row["scoring_reference"] == "cribs"
    assert row["scoring_threshold"] is None


def test_k4_cribs_sit_at_their_stated_positions(by_passage):
    row = by_passage["K4"]
    assert len(row["cribs"]) == 4
    assert sum(len(c["plaintext"]) for c in row["cribs"]) == 24
    for c in row["cribs"]:
        assert len(c["plaintext"]) == c["end"] - c["start"] + 1
        assert row["problem"][c["start"] - 1 : c["end"]] == c["ciphertext"]


# --- anomalies -------------------------------------------------------------------


def test_k2_records_both_endings(by_passage):
    row = by_passage["K2"]
    assert row["answer"].endswith("WESTIDBYROWS")
    omission = next(a for a in row["anomalies"] if a["kind"] == "omitted_character")
    assert omission["intended"] == "WEST X LAYER TWO"


def test_undergruund_is_recorded_as_a_carving_error(by_passage):
    """It is widely repeated as a deliberate misspelling; the coding charts show it is not."""
    row = by_passage["K2"]
    entry = next(a for a in row["anomalies"] if a["text"] == "UNDERGRUUND")
    assert entry["kind"] == "transcription_error"
    assert entry["intended"] == "UNDERGROUND"


@pytest.mark.parametrize("passage,text", [("K1", "IQLUSION"), ("K3", "DESPARATLY")])
def test_deliberate_misspellings_survive_into_the_plaintext(by_passage, passage, text):
    row = by_passage[passage]
    assert text in row["answer"]
    assert any(a["text"] == text and a["kind"] == "deliberate_misspelling" for a in row["anomalies"])


# --- schema uniformity ------------------------------------------------------------


def test_every_record_carries_every_field(rows):
    assert len(rows) == 4
    for row in rows:
        assert tuple(row) == FIELDS


def test_list_fields_are_never_null(rows):
    for row in rows:
        for field in ("cribs", "anomalies", "source_urls"):
            assert isinstance(row[field], list)


def test_nested_structs_are_uniformly_keyed(rows):
    for row in rows:
        for c in row["cribs"]:
            assert tuple(c) == CRIB_FIELDS
        for a in row["anomalies"]:
            assert tuple(a) == ANOMALY_FIELDS


def test_ids_are_unique_and_derived_from_passage(rows):
    assert len({r["id"] for r in rows}) == 4
    for row in rows:
        assert row["id"] == f"kryptos-baseline-{row['passage'].lower()}"
