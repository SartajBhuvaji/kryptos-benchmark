"""Verification for the tier prompts and the tier-4 frontier score.

The leak tests are the ones that matter, and here they run in **both** directions. Every
other prompt test in this project asserts that ground truth never appears; tier 1 breaks
that rule on purpose, by handing the model the keys to see whether it can execute the
algorithm. So two things have to hold at once:

* the answer never appears, at any tier, in any config;
* tier 1 really does show the keys.

The second is not a formality. A filter that erred toward hiding everything would turn
tier 1 into a second tier 2 — no error, no failing assertion elsewhere, and the two tiers
would quietly stop measuring different things.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from kryptos.algorithms.baseline import build as baseline_build
from kryptos.algorithms.isomorph import build as isomorph_build
from kryptos.algorithms.isomorph import schema as isomorph_schema
from kryptos.eval import tiers
from kryptos.scoring import frontier

TIER_NUMBERS = (1, 2, 3, 4)


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    """One row from every config, so per-config key shapes are all exercised."""
    collected = []
    with pathlib.Path(baseline_build.OUTPUT).open(encoding="utf-8") as fh:
        collected += [json.loads(line) for line in fh]
    for config in isomorph_schema.CONFIGS:
        with pathlib.Path(isomorph_build.output_for(config)).open(encoding="utf-8") as fh:
            collected += [json.loads(line) for line in fh][:3]
    return collected


# --- the leak rule, forbidden direction -------------------------------------------


@pytest.mark.parametrize("number", TIER_NUMBERS)
def test_the_answer_never_appears_at_any_tier(rows, number):
    for row in rows:
        prompt = tiers.build_prompt(row, number)
        for field in tiers.FORBIDDEN_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and len(value) > 3:
                assert value not in prompt, f"{row['id']} tier {number}: {field} leaked"


@pytest.mark.parametrize("number", TIER_NUMBERS)
def test_the_answer_never_appears_in_the_delimited_form(rows, number):
    """The delimited render spaces out every character, so a substring check on the raw
    answer would pass vacuously. Compare against the spaced form too."""
    for row in rows:
        prompt = tiers.build_prompt(row, number, delimited=True)
        for field in tiers.FORBIDDEN_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and len(value) > 3:
                assert value not in prompt
                assert " ".join(value) not in prompt


def test_forbidden_and_visible_fields_are_disjoint():
    """A field cannot be both showable and forbidden."""
    for number, allowed in tiers.VISIBLE_FIELDS.items():
        assert not set(allowed) & set(tiers.FORBIDDEN_FIELDS), number


def test_visible_projects_away_everything_else(rows):
    for row in rows:
        for number in TIER_NUMBERS:
            assert set(tiers.visible(row, number)) <= set(tiers.VISIBLE_FIELDS[number])


def test_nulls_deciphered_intermediate_is_forbidden(rows):
    """It is the plaintext with nulls still in it — one deletion away from the answer."""
    assert "deciphered" in tiers.FORBIDDEN_FIELDS
    nulls = [r for r in rows if r.get("config") == "isomorph_nulls"]
    assert nulls, "expected nulls rows in the fixture"
    for row in nulls:
        for number in TIER_NUMBERS:
            assert row["deciphered"] not in tiers.build_prompt(row, number)


# --- the leak rule, required direction --------------------------------------------


def test_tier_1_actually_supplies_the_keys(rows):
    """Tier 1 tests execution, not discovery. If the keys are missing it is tier 2 with
    extra steps, and the two tiers stop measuring different things."""
    for row in rows:
        if row.get("answer") is None:
            continue                              # K4 has no keys to supply
        prompt = tiers.build_prompt(row, 1)
        shown = [
            key for key in tiers.KEY_FIELDS
            if isinstance(row.get(key), str) and row[key] and str(row[key]) in prompt
        ]
        assert shown, f"{row['id']}: tier 1 showed no key material"


@pytest.mark.parametrize(
    "config,key",
    [
        ("isomorph_quagmire", "indicator_keyword"),
        ("isomorph_transposition", "route"),
        ("isomorph_composite", "vigenere_key"),
        ("isomorph_nulls", "indicator_keyword"),
    ],
)
def test_each_config_shows_its_own_key_at_tier_1(rows, config, key):
    """Per config, so a new key shape cannot be silently unhandled."""
    row = next(r for r in rows if r.get("config") == config)
    assert str(row[key]) in tiers.build_prompt(row, 1)


def test_tier_2_and_3_withhold_the_keys(rows):
    for row in rows:
        for number in (2, 3):
            prompt = tiers.build_prompt(row, number)
            for key in tiers.KEY_FIELDS:
                value = row.get(key)
                if isinstance(value, str) and len(value) > 3:
                    assert value not in prompt, f"{row['id']} tier {number}: {key} leaked"


def test_the_same_row_gives_different_prompts_at_tier_1_and_2(rows):
    """The core claim about tiers: framings over one dataset, not separate datasets."""
    row = next(r for r in rows if r.get("config") == "isomorph_quagmire")
    assert tiers.build_prompt(row, 1) != tiers.build_prompt(row, 2)
    assert len(tiers.build_prompt(row, 1)) > len(tiers.build_prompt(row, 2))


# --- prompt content ---------------------------------------------------------------


@pytest.mark.parametrize("number", TIER_NUMBERS)
def test_prompt_contains_the_ciphertext(rows, number):
    for row in rows:
        assert row["problem"] in tiers.build_prompt(row, number)


def test_delimited_mode_separates_every_character(rows):
    row = rows[0]
    prompt = tiers.build_prompt(row, 2, delimited=True)
    assert " ".join(row["problem"]) in prompt
    assert row["problem"] not in prompt


def test_cribs_appear_only_where_they_exist(rows):
    for row in rows:
        prompt = tiers.build_prompt(row, tiers.default_tier(row))
        if row.get("cribs"):
            for crib in row["cribs"]:
                assert crib["plaintext"] in prompt
                assert f"{crib['start']}-{crib['end']}" in prompt
        else:
            assert "Confirmed plaintext fragments" not in prompt


@pytest.mark.parametrize("number", TIER_NUMBERS)
def test_system_prompt_states_what_the_tier_tests(number):
    prompt = tiers.system_prompt(number)
    assert tiers.TIER_GUIDANCE[number] in prompt
    assert "expert cryptanalyst" in prompt


def test_tier_4_prompt_does_not_promise_a_solution():
    """Nobody has solved K4. A prompt implying otherwise would be dishonest framing."""
    assert "unsolved" in tiers.TIER_GUIDANCE[4]
    assert "best hypothesis" in tiers.TIER_GUIDANCE[4]


def test_unknown_tier_is_rejected(rows):
    with pytest.raises(ValueError, match="no tier 9"):
        tiers.build_prompt(rows[0], 9)


# --- few-shot demonstration -------------------------------------------------------


def test_format_example_is_included_by_default_and_removable():
    with_example = tiers.system_prompt(2)
    without = tiers.system_prompt(2, few_shot=False)
    assert tiers.FORMAT_EXAMPLE in with_example
    assert tiers.FORMAT_EXAMPLE not in without
    assert len(with_example) > len(without)


def test_format_example_uses_a_cipher_no_instance_uses(rows):
    """It must demonstrate the format without hinting at any answer. A Caesar shift
    appears nowhere in this benchmark."""
    assert "Caesar" in tiers.FORMAT_EXAMPLE
    for row in rows:
        assert row.get("cipher_name") != "Caesar shift"


def test_format_example_contains_no_benchmark_text(rows):
    for row in rows:
        for field in ("problem", "answer"):
            value = row.get(field)
            if isinstance(value, str) and len(value) > 8:
                assert value not in tiers.FORMAT_EXAMPLE


def test_format_example_demonstrates_a_filled_in_answer():
    """The point is showing a completed response, not describing the schema."""
    for field in ("cipher", "key", "method", "plaintext"):
        assert f'"{field}"' in tiers.FORMAT_EXAMPLE
    assert "THEQUICKFOX" in tiers.FORMAT_EXAMPLE


# --- default tier -----------------------------------------------------------------


def test_default_tier_is_derived_per_row_not_per_config(rows):
    baseline = [r for r in rows if r.get("passage")]
    by_passage = {r["passage"]: tiers.default_tier(r) for r in baseline}
    assert by_passage == {"K1": 2, "K2": 2, "K3": 3, "K4": 4}


def test_default_tier_sends_transpositions_to_tier_3(rows):
    row = next(r for r in rows if r.get("config") == "isomorph_transposition")
    assert tiers.default_tier(row) == 3


def test_default_tier_sends_unsolved_passages_to_tier_4(rows):
    for row in rows:
        if row.get("answer") is None:
            assert tiers.default_tier(row) == 4


# --- the tier-4 frontier score ----------------------------------------------------


@pytest.fixture(scope="module")
def k4(rows) -> dict:
    return next(r for r in rows if r.get("passage") == "K4")


def test_perfect_crib_placement_is_recognised(k4):
    hypothesis = ["X"] * 97
    for crib in k4["cribs"]:
        hypothesis[crib["start"] - 1 : crib["end"]] = list(crib["plaintext"])
    result = frontier.score(k4["cribs"], "".join(hypothesis))
    assert result.cribs_placed == 4
    assert result.cribs_present == 4


def test_cribs_alone_do_not_look_like_a_break(k4):
    """The reason fitness is reported beside placement. A hypothesis built by dropping
    the cribs into noise scores 4/4 on placement and must not read as English."""
    hypothesis = ["X"] * 97
    for crib in k4["cribs"]:
        hypothesis[crib["start"] - 1 : crib["end"]] = list(crib["plaintext"])
    result = frontier.score(k4["cribs"], "".join(hypothesis))
    assert result.cribs_placed == 4
    assert not result.reads_as_english


def test_english_without_cribs_does_not_look_like_a_break(k4):
    """And the converse: fluent text that ignores the fragments scores zero placement."""
    english = "ITWASTOTALLYINVISIBLEHOWSTHATPOSSIBLETHEYUSEDTHEEARTHSMAGNETICFIELDX" * 2
    result = frontier.score(k4["cribs"], english[:97])
    assert result.cribs_placed == 0
    assert result.reads_as_english


def test_displaced_cribs_are_present_but_not_placed(k4):
    result = frontier.score(k4["cribs"], "BERLINCLOCK" + "X" * 86)
    assert result.cribs_placed == 0
    assert result.cribs_present == 2


def test_score_normalises_free_form_model_output(k4):
    """This scores model output, not project data, so it cannot assume clean input."""
    result = frontier.score(k4["cribs"], "  berlin clock!!  ")
    assert result.length == 11
    assert result.cribs_present == 2


def test_summary_reports_both_numbers_and_their_scale(k4):
    summary = frontier.score(k4["cribs"], "X" * 97).summary()
    assert "cribs placed" in summary
    assert "fitness" in summary
    assert "English ~" in summary      # the scale, so the number is interpretable


def test_tier_4_carries_no_threshold():
    """Nobody has solved K4, so there is no distribution to calibrate a pass mark
    against. An invented number would licence unsupported claims."""
    from kryptos.scoring import tier as tier_lookup

    assert tier_lookup(4).threshold is None
    assert tier_lookup(4).passed(0.0) is None
    assert tier_lookup(4).metric == "frontier_score"
