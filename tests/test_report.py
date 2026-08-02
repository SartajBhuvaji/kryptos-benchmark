"""Verification for the reporting layer.

Reporting is where a benchmark most easily lies, because every number it prints looks
equally authoritative. The tests that matter here are the ones asserting what must *not*
be averaged together:

* a CER and a frontier score never enter the same mean;
* a paired comparison drops instances measured on only one side;
* a refusal is never scored as a wrong answer;
* an unpriced model reports no cost rather than a free one.

Each of those is a way to produce a plausible, publishable, wrong number.
"""

from __future__ import annotations

import json

import pytest

from kryptos.eval import report
from kryptos.eval.results import RESULTS_VERSION, Result, write


def record(**overrides) -> dict:
    """A scored result, with the fields a test cares about overridden."""
    base = {
        "instance_id": "kryptos-isomorph-quagmire-0000",
        "config": "isomorph_quagmire",
        "tier": 2,
        "paradigm": "cot",
        "model": "claude-opus-5",
        "requested_model": "claude-opus-5",
        "delimited": False,
        "effort": "high",
        "seed": 20260731,
        "cipher": "Quagmire III",
        "key": "PALIMPSEST",
        "plaintext": "SOMETHING",
        "refused": False,
        "refusal_category": None,
        "error": None,
        "input_tokens": 1000,
        "output_tokens": 2000,
        "code_executions": 0,
        "resumes": 0,
        "metric": "cer",
        "cer": 0.2,
        "similarity": 80.0,
        "passed": False,
        "cribs_placed": None,
        "cribs_present": None,
        "cribs_total": None,
        "fitness": None,
        "ioc": None,
        "version": RESULTS_VERSION,
        "timestamp": "2026-08-01T00:00:00+00:00",
        "transcript": [],
    }
    return {**base, **overrides}


def frontier_record(**overrides) -> dict:
    """A tier-4 result: no reference answer, so no CER."""
    return record(
        **{
            "instance_id": "kryptos-baseline-k4",
            "config": "K4",
            "tier": 4,
            "metric": "frontier_score",
            "cer": None,
            "similarity": None,
            "passed": None,
            "cribs_placed": 2,
            "cribs_present": 3,
            "cribs_total": 4,
            "fitness": -5.1,
            "ioc": 0.045,
            **overrides,
        }
    )


# --- the metric-family rule -------------------------------------------------------


def test_cer_and_frontier_results_are_summarised_separately():
    """The load-bearing rule. CER is an error rate on [0,1]; a frontier score is a crib
    count beside a log-probability. A mean over both would be arithmetic on two scales."""
    summary = report.summarise([record(cer=0.4), frontier_record()])

    assert summary.instances == 2
    assert summary.scored == 1                 # only the CER row
    assert summary.mean_cer == 0.4             # not averaged with anything from tier 4
    assert summary.frontier == 1
    assert summary.mean_cribs_placed == 2


def test_a_frontier_only_population_reports_no_cer():
    summary = report.summarise([frontier_record(), frontier_record(cribs_placed=4)])
    assert summary.mean_cer is None
    assert summary.scored == 0
    assert summary.mean_cribs_placed == 3


def test_tier_4_is_never_counted_as_a_failure():
    """`passed` is None at tier 4 because there is no pass mark, and None is not False."""
    summary = report.summarise([frontier_record(), record(passed=True)])
    assert summary.passed == 1


# --- harness outcomes are not scores ----------------------------------------------


def test_refusals_and_errors_are_excluded_from_the_mean():
    records = [
        record(cer=0.1),
        record(instance_id="b", refused=True, refusal_category="cyber", cer=None),
        record(instance_id="c", error="api_error_500", cer=None),
    ]
    summary = report.summarise(records)

    assert summary.instances == 3
    assert summary.refused == 1 and summary.errored == 1
    assert summary.scored == 1
    assert summary.mean_cer == 0.1        # not 0.1/3, and not dragged toward 1.0


def test_a_refusal_is_never_a_solve():
    summary = report.summarise([record(refused=True, cer=None)])
    assert summary.solved == 0
    assert summary.solve_rate is None


# --- pairing ----------------------------------------------------------------------


def test_comparison_pairs_on_the_same_instances():
    records = [
        record(instance_id="a", paradigm="cot", cer=0.5),
        record(instance_id="a", paradigm="tool_use", cer=0.1),
        record(instance_id="b", paradigm="cot", cer=0.5),
        record(instance_id="b", paradigm="tool_use", cer=0.3),
    ]
    result = report.compare(records, "paradigm", "cot", "tool_use")

    assert result.pairs == 2
    assert result.unpaired == 0
    assert result.left_cer == 0.5
    assert result.right_cer == pytest.approx(0.2)
    assert result.cer_gap == pytest.approx(0.3)   # positive: tool use scored better


def test_an_instance_measured_on_one_side_only_is_discarded():
    """The failure this prevents: a refusal removes a hard instance from one arm, and
    that arm's mean improves for free. Comparing group means would report the artefact
    as a paradigm effect."""
    records = [
        record(instance_id="easy", paradigm="cot", cer=0.1),
        record(instance_id="easy", paradigm="tool_use", cer=0.1),
        record(instance_id="hard", paradigm="cot", cer=0.9),
        # tool_use never produced a result for `hard`
    ]
    result = report.compare(records, "paradigm", "cot", "tool_use")

    assert result.pairs == 1
    assert result.unpaired == 1
    assert result.left_cer == 0.1     # the 0.9 is excluded, not averaged in
    assert result.right_cer == 0.1
    assert result.cer_gap == 0.0      # no gap invented from the unequal sets


def test_pairing_holds_every_other_axis_fixed():
    """Two records differing in tier are not a paradigm pair, however tempting."""
    records = [
        record(instance_id="a", tier=2, paradigm="cot"),
        record(instance_id="a", tier=3, paradigm="tool_use"),
    ]
    assert report.compare(records, "paradigm", "cot", "tool_use").pairs == 0


def test_delimited_comparison_pairs_the_same_way():
    records = [
        record(instance_id="a", delimited=False, cer=0.4),
        record(instance_id="a", delimited=True, cer=0.2),
    ]
    result = report.compare(records, "delimited", False, True)
    assert result.pairs == 1
    assert result.cer_gap == pytest.approx(0.2)


def test_an_unpairable_axis_is_rejected():
    with pytest.raises(ValueError, match="cannot pair on 'config'"):
        report.compare([record()], "config", "a", "b")


# --- the headline comparison ------------------------------------------------------


def test_baseline_and_isomorph_are_told_apart_by_config_prefix():
    """Baseline rows carry no `config` field, so their config is the passage name."""
    assert report.family(record(config="K1")) == "baseline"
    assert report.family(record(config="K4")) == "baseline"
    assert report.family(record(config="isomorph_quagmire")) == "isomorph"
    assert report.family(record(config="isomorph_nulls")) == "isomorph"


def test_headline_reports_itself_as_unpaired():
    """It compares different instances on purpose. Claiming otherwise would imply K1
    corresponds to some particular synthetic Quagmire."""
    records = [
        record(config="K1", instance_id="k1", cer=0.0),
        record(config="isomorph_quagmire", instance_id="q0", cer=0.8),
    ]
    result = report.headline(records, "claude-opus-5")

    assert result.paired is False
    assert result.left_cer == 0.0
    assert result.right_cer == 0.8
    assert "unpaired" in report.render_comparison(result)


def test_headline_separates_models():
    records = [
        record(config="K1", model="claude-opus-5", requested_model="claude-opus-5", cer=0.0),
        record(config="K1", model="claude-sonnet-5", requested_model="claude-sonnet-5", cer=0.5),
    ]
    assert report.headline(records, "claude-opus-5").left_cer == 0.0
    assert report.headline(records, "claude-sonnet-5").left_cer == 0.5


def test_k4_does_not_contaminate_the_baseline_mean():
    """K4 is in the baseline config but has no answer, so it scores on the other metric
    and must not enter the baseline CER."""
    records = [record(config="K1", cer=0.0), frontier_record()]
    result = report.headline(records, "claude-opus-5")
    assert result.left_cer == 0.0


# --- requested vs served model ----------------------------------------------------


def test_results_group_by_the_model_that_was_asked():
    """A fallback answer belongs in the column of the model that was asked, or the
    refusing model appears to have no results rather than to have refused."""
    fallback = record(model="claude-opus-4-8", requested_model="claude-opus-5", cer=0.3)
    assert report.requested(fallback) == "claude-opus-5"
    assert report.fell_back(fallback) is True
    assert report.headline([record(config="K1", **{
        "model": "claude-opus-4-8", "requested_model": "claude-opus-5", "cer": 0.3
    })], "claude-opus-5").left_cer == 0.3


def test_a_fallback_is_reported_not_absorbed():
    summary = report.summarise(
        [record(model="claude-opus-4-8", requested_model="claude-opus-5")]
    )
    assert summary.fell_back == 1
    assert summary.models == {"claude-opus-4-8"}          # billed
    assert summary.requested_models == {"claude-opus-5"}  # scored


def test_a_run_with_no_fallback_reports_none():
    assert report.summarise([record()]).fell_back == 0
    assert report.fell_back(record()) is False


def test_the_preamble_warns_when_a_fallback_served_a_result():
    text = report._preamble(
        [record(model="claude-opus-4-8", requested_model="claude-opus-5")], 0
    )
    assert "WARNING" in text
    assert "not that model's" in text


def test_cost_bills_the_model_that_answered():
    """Scores group by the model requested; cost groups by the one that ran, because
    that is what was charged."""
    rows = report.cost(
        [record(model="claude-haiku-4-5", requested_model="claude-opus-5")]
    )
    assert [r.model for r in rows] == ["claude-haiku-4-5"]


# --- cost -------------------------------------------------------------------------


def test_cost_is_computed_from_the_published_rates():
    rows = report.cost([record(input_tokens=1_000_000, output_tokens=1_000_000)])
    assert len(rows) == 1
    assert rows[0].input_usd == pytest.approx(5.00)
    assert rows[0].output_usd == pytest.approx(25.00)
    assert rows[0].total_usd == pytest.approx(30.00)


def test_output_tokens_cost_more_than_input():
    for model in report.PRICES:
        cheap, dear = report.PRICES[model]
        assert dear > cheap, model


def test_an_unpriced_model_reports_no_cost_rather_than_zero():
    """A run that silently cost nothing is the number nobody double-checks."""
    rows = report.cost([record(model="some-other-vendor-model")])
    assert rows[0].total_usd is None
    assert rows[0].priced is False
    assert rows[0].input_tokens == 1000        # tokens are still counted


def test_unpriced_models_are_excluded_from_the_total_and_named():
    records = [record(), record(model="mystery-model", instance_id="b")]
    text = report.render_cost(records)
    assert "unpriced" in text
    assert "mystery-model" in text
    assert "excluded from the total" in text


def test_a_dated_model_variant_resolves_to_its_alias_price():
    """The persisted model is whatever the API returned, which may be a dated variant."""
    assert report.price_for("claude-haiku-4-5-20251001") == report.PRICES["claude-haiku-4-5"]


def test_price_lookup_prefers_the_longest_match():
    assert report.price_for("claude-opus-4-8") == (5.00, 25.00)
    assert report.price_for("claude-fable-5") == (10.00, 50.00)


def test_an_unknown_model_has_no_price():
    assert report.price_for("gpt-does-not-exist") is None
    assert report.price_for("") is None


# --- deduplication ----------------------------------------------------------------


def test_re_running_an_instance_supersedes_the_earlier_record():
    """`results.write` appends, so a second run of the same config adds a second record
    for every instance. Counting both would double the instance count and average a
    stale score with a fresh one."""
    old = record(cer=0.9, timestamp="2026-08-01T00:00:00+00:00")
    new = record(cer=0.1, timestamp="2026-08-02T00:00:00+00:00")

    kept, superseded = report.deduplicate([old, new])

    assert superseded == 1
    assert len(kept) == 1
    assert kept[0]["cer"] == 0.1


def test_records_differing_on_any_axis_are_not_duplicates():
    for axis, value in [
        ("tier", 3),
        ("paradigm", "tool_use"),
        ("requested_model", "claude-sonnet-5"),
        ("delimited", True),
        ("effort", "max"),
        ("instance_id", "other"),
    ]:
        kept, superseded = report.deduplicate([record(), record(**{axis: value})])
        assert superseded == 0, axis
        assert len(kept) == 2, axis


# --- reading --------------------------------------------------------------------


def test_load_reads_what_write_produced(tmp_path):
    """The two halves of persistence, checked against each other rather than against a
    hand-written fixture that could drift from the dataclass."""
    path = tmp_path / "run.jsonl"
    write([Result(**{
        "instance_id": "x", "config": "isomorph_nulls", "tier": 3, "paradigm": "cot",
        "model": "claude-opus-5", "delimited": False, "effort": "high",
        "requested_model": "claude-opus-5", "cer": 0.25, "similarity": 75.0,
    })], path)

    records = report.load([path])
    assert len(records) == 1
    assert records[0]["cer"] == 0.25
    assert records[0]["version"] == RESULTS_VERSION
    assert report.summarise(records).mean_cer == 0.25


def test_a_foreign_schema_version_is_refused(tmp_path):
    """A field that changed meaning would produce a plausible number from incompatible
    data. Refusing is the only safe reading."""
    path = tmp_path / "old.jsonl"
    path.write_text(json.dumps(record(version=RESULTS_VERSION - 1)) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="different schema"):
        report.load([path])


def test_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "run.jsonl"
    path.write_text(json.dumps(record()) + "\n\n", encoding="utf-8")
    assert len(report.load([path])) == 1


def test_several_files_are_read_as_one_population(tmp_path):
    for name, instance in [("a.jsonl", "a"), ("b.jsonl", "b")]:
        (tmp_path / name).write_text(
            json.dumps(record(instance_id=instance)) + "\n", encoding="utf-8"
        )
    records = report.load([tmp_path / "a.jsonl", tmp_path / "b.jsonl"])
    assert len(records) == 2


# --- breakdown --------------------------------------------------------------------


def test_breakdown_groups_by_the_requested_fields():
    records = [
        record(tier=2, paradigm="cot", cer=0.2),
        record(tier=2, paradigm="tool_use", cer=0.4),
        record(tier=3, paradigm="cot", cer=0.6),
    ]
    rows = dict(report.breakdown(records, "tier", "paradigm"))

    assert rows[(2, "cot")].mean_cer == 0.2
    assert rows[(2, "tool_use")].mean_cer == 0.4
    assert rows[(3, "cot")].mean_cer == 0.6


def test_breakdown_by_family_is_the_headline_split():
    records = [record(config="K1"), record(config="isomorph_quagmire")]
    rows = dict(report.breakdown(records, "family"))
    assert set(rows) == {("baseline",), ("isomorph",)}


def test_a_multi_model_file_never_pools_models_in_one_row():
    """Pooling two models into a single row is worse than printing no breakdown."""
    records = [
        record(requested_model="claude-opus-5", cer=0.0),
        record(requested_model="claude-sonnet-5", instance_id="b", cer=1.0),
    ]
    text = report.render(records, 0, ["config", "tier"])
    assert "claude-opus-5" in text
    assert "claude-sonnet-5" in text


# --- rendering --------------------------------------------------------------------


def test_the_full_report_renders_for_a_realistic_mixed_run():
    """Every metric family, both paradigms, both presentations, two models."""
    records = [
        record(config="K1", instance_id="k1", cer=0.0),
        frontier_record(),
        record(instance_id="q0", paradigm="cot", cer=0.7),
        record(instance_id="q0", paradigm="tool_use", cer=0.2),
        record(instance_id="q1", delimited=False, cer=0.6),
        record(instance_id="q1", delimited=True, cer=0.5),
        record(instance_id="q2", requested_model="claude-sonnet-5",
               model="claude-sonnet-5", cer=0.9),
        record(instance_id="q3", refused=True, cer=None),
    ]
    text = report.render(records, 0, ["config", "tier", "paradigm"])

    assert "BASELINE VS ISOMORPH" in text
    assert "CHAIN OF THOUGHT VS TOOL USE" in text
    assert "RAW VS CHARACTER-DELIMITED" in text
    assert "COST AND TOKENS" in text
    assert "refused" in text


def test_rendering_survives_a_run_with_nothing_scoreable():
    """A run that refused everything must still produce a report saying so, rather than
    dividing by zero."""
    records = [record(refused=True, cer=None, similarity=None)]
    text = report.render(records, 0, ["config"])
    assert "not enough scoreable results" in text or "refused" in text


def test_comparison_with_one_empty_side_says_so_rather_than_guessing():
    result = report.compare([record(paradigm="cot")], "paradigm", "cot", "tool_use")
    assert result.pairs == 0
    assert "not enough scoreable results" in report.render_comparison(result)


def test_the_cost_note_records_the_price_basis():
    """A dollar figure with no date is unauditable."""
    text = report.render_cost([record()])
    assert "2026-08-01" in text
    assert "per million tokens" in text


def test_no_two_breakdown_rows_render_identically():
    """Truncating group labels to a fixed width once produced two visibly identical rows
    carrying different numbers -- a table that reads wrong, not merely one that reads
    badly. The column is sized to its content instead."""
    records = [
        record(requested_model="claude-opus-5", paradigm="cot", cer=0.1),
        record(requested_model="claude-opus-5", paradigm="tool_use", cer=0.9),
    ]
    body = report.render_breakdown(records, "requested_model", "config", "paradigm")
    rows = [ln for ln in body.splitlines() if ln.startswith("claude")]

    assert len(rows) == 2
    assert rows[0] != rows[1]
    assert "tool_use" in body and "chain of thought" in body


def test_tier_1_is_not_relabelled_as_delimited():
    """`1 == True` in Python, so a value-label map keyed on booleans would rename tier 1.
    Booleans are matched by type for exactly this reason."""
    assert report._label(1) == "1"
    assert report._label(True) == "delimited"
    assert report._label(0) == "0"
    assert report._label(False) == "raw"

    body = report.render_breakdown([record(tier=1)], "tier")
    assert "delimited" not in body


def test_the_presentation_axis_names_what_it_varies():
    """`False vs True` leaves the reader to guess which arm is which."""
    records = [record(delimited=False, cer=0.4), record(delimited=True, cer=0.2)]
    text = report.render_comparison(report.compare(records, "delimited", False, True))
    assert "raw vs delimited" in text


def test_the_headline_states_the_memorisation_caveat():
    """The baseline number is meaningless without it, and it is the one people quote."""
    text = report.render_headline([record(config="K1")])
    assert "memoris" in text.lower()
    assert "recall" in text


# --- cli --------------------------------------------------------------------------


def test_cli_reports_a_written_run(tmp_path, capsys):
    path = tmp_path / "run.jsonl"
    path.write_text(
        "\n".join(json.dumps(r) for r in [record(config="K1"), record()]) + "\n",
        encoding="utf-8",
    )

    assert report.main([str(path)]) == 0
    assert "BASELINE VS ISOMORPH" in capsys.readouterr().out


def test_cli_rejects_a_missing_file(tmp_path):
    with pytest.raises(SystemExit, match="no such results file"):
        report.main([str(tmp_path / "absent.jsonl")])


def test_cli_rejects_an_empty_file(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="no results found"):
        report.main([str(path)])
