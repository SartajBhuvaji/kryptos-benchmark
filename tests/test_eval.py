"""Verification for the benchmark runner.

No API calls. The runner imports ``anthropic`` and ``datasets`` lazily inside the
functions that need them, so prompt construction is testable on its own.

The leak test is the one that matters: it guards the property the whole schema exists to
enforce -- a solver never sees the answer. Scoring moved to ``kryptos.scoring`` and is
tested in ``test_scoring.py``.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from kryptos.algorithms.baseline import build
from kryptos.algorithms.baseline.schema import GROUND_TRUTH_FIELDS, INPUT_FIELDS
from kryptos.eval.run_benchmark import build_prompt


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
