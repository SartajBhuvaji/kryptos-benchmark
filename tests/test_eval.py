"""Verification for the benchmark runner.

No API calls. The runner imports ``anthropic`` and ``datasets`` lazily inside the
functions that need them, so scoring and prompt construction are testable on their own.

The leak test is the one that matters. Everything else here is arithmetic; that one
guards the property the whole schema exists to enforce -- a solver never sees the answer.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from kryptos.algorithms.baseline import build
from kryptos.algorithms.baseline.schema import GROUND_TRUTH_FIELDS, INPUT_FIELDS
from kryptos.eval.run_benchmark import (
    build_prompt,
    character_error_rate,
    crib_score,
    letters_only,
    levenshtein,
)


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    with pathlib.Path(build.OUTPUT).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


# --- the property that matters ---------------------------------------------------


def test_prompts_never_contain_ground_truth(rows):
    """A solver must not be handed the answer, the method, or the keys."""
    for row in rows:
        for delimited in (False, True):
            prompt = build_prompt(row, delimited=delimited)
            for field in GROUND_TRUTH_FIELDS:
                value = row[field]
                if isinstance(value, str) and len(value) > 3:
                    assert value not in prompt, f"{row['passage']}.{field} leaked"


def test_runner_input_fields_match_the_schema():
    """If the schema grows an input field, the runner must be updated with it."""
    from kryptos.eval import run_benchmark

    assert run_benchmark.INPUT_FIELDS == INPUT_FIELDS


def test_prompt_contains_the_ciphertext(rows):
    for row in rows:
        assert row["problem"] in build_prompt(row, delimited=False)


def test_delimited_mode_separates_every_character(rows):
    row = rows[0]
    prompt = build_prompt(row, delimited=True)
    assert " ".join(row["problem"]) in prompt
    assert row["problem"] not in prompt  # the contiguous form is gone


def test_k4_prompt_carries_the_cribs(rows):
    k4 = next(r for r in rows if r["passage"] == "K4")
    prompt = build_prompt(k4, delimited=False)
    for crib in k4["cribs"]:
        assert crib["plaintext"] in prompt
        assert f"{crib['start']}-{crib['end']}" in prompt


def test_solved_passages_get_no_crib_section(rows):
    for row in rows:
        if row["solved"]:
            assert "Confirmed plaintext fragments" not in build_prompt(row, False)


# --- scoring ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b,expected",
    [("kitten", "sitting", 3), ("", "abc", 3), ("abc", "", 3), ("same", "same", 0)],
)
def test_levenshtein(a, b, expected):
    assert levenshtein(a, b) == expected


def test_levenshtein_pure_python_matches_rapidfuzz(monkeypatch):
    """The fallback runs when rapidfuzz is absent, so it must agree with it."""
    pytest.importorskip("rapidfuzz")
    import builtins

    real_import = builtins.__import__

    def no_rapidfuzz(name, *args, **kwargs):
        if name.startswith("rapidfuzz"):
            raise ImportError("blocked for this test")
        return real_import(name, *args, **kwargs)

    pairs = [("BETWEENSUBTLE", "BETWENSUBTLE"), ("ABCDEF", "FEDCBA"), ("X" * 40, "Y" * 40)]
    fast = [levenshtein(a, b) for a, b in pairs]
    monkeypatch.setattr(builtins, "__import__", no_rapidfuzz)
    assert [levenshtein(a, b) for a, b in pairs] == fast


def test_character_error_rate():
    assert character_error_rate("ABCDE", "ABCDE") == 0.0
    assert character_error_rate("ABCDE", "ABXDE") == pytest.approx(0.2)
    assert character_error_rate("ABCDE", "") == 1.0


def test_cer_is_not_clamped():
    """An over-long hypothesis should score above 1.0 rather than silently cap."""
    assert character_error_rate("AB", "ABCDEFGH") > 1.0


def test_perfect_decryption_scores_zero(rows):
    """The end-to-end scoring contract: the stored answer scores 0.0 CER."""
    for row in rows:
        if row["scoring_metric"] == "cer":
            assert character_error_rate(row["answer"], row["answer"]) == 0.0


def test_letters_only_normalizes():
    assert letters_only("be tween!") == "BETWEEN"
    assert letters_only("a?b") == "AB"


def test_crib_score_placement(rows):
    k4 = next(r for r in rows if r["passage"] == "K4")
    cribs = k4["cribs"]

    perfect = ["?"] * 97
    for c in cribs:
        perfect[c["start"] - 1 : c["end"]] = list(c["plaintext"])
    assert crib_score(cribs, "".join(perfect)) == (4, 4)

    assert crib_score(cribs, "Z" * 97) == (0, 0)

    # Right fragments, wrong offsets: present but not placed -- the distinction the
    # metric exists to draw.
    shifted = "ZZZZZ" + "".join(perfect)
    exact, anywhere = crib_score(cribs, shifted)
    assert anywhere == 4
    assert exact < 4
