"""Verification for the two evaluation paradigms and the shared scoring path.

No API calls. A fake client returns canned messages, which is enough to exercise
everything that actually goes wrong in this layer: refusals, paused turns, unparsable
responses, and transcript capture.

The tests that matter most are the ones pinning **sameness**. The chain-of-thought vs
tool-use gap is a headline result of this project, and it only means something if the two
paradigms differ in exactly one respect. So: same prompt, same schema, same effort, same
scoring function -- with the tool declaration and its guidance as the only difference.
A divergence anywhere else would turn a harness artifact into a reported finding.
"""

from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

import pytest

from kryptos.algorithms.baseline import build as baseline_build
from kryptos.algorithms.isomorph import build as isomorph_build
from kryptos.algorithms.isomorph import schema as isomorph_schema
from kryptos.eval import paradigms, results, tiers


# --- a fake client ----------------------------------------------------------------


def block(**kwargs):
    return SimpleNamespace(**kwargs)


def answer_block(plaintext="THEANSWER", cipher="Quagmire III", key="K", method="m"):
    payload = {"cipher": cipher, "key": key, "method": method, "plaintext": plaintext}
    return block(type="text", text=json.dumps(payload))


def message(content, *, stop_reason="end_turn", stop_details=None, model="claude-opus-5"):
    return SimpleNamespace(
        content=content,
        stop_reason=stop_reason,
        stop_details=stop_details,
        model=model,
        usage=SimpleNamespace(input_tokens=100, output_tokens=50),
    )


class FakeClient:
    """Returns queued messages and records every request it was given."""

    def __init__(self, *messages):
        self._queue = list(messages)
        self.requests: list[dict] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **request):
        self.requests.append(request)
        queued = self._queue.pop(0) if self._queue else message([answer_block()])

        class _Stream:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *exc):
                return False

            def get_final_message(self_inner):
                return queued

        return _Stream()


@pytest.fixture(scope="module")
def rows() -> dict[str, dict]:
    loaded = {}
    with pathlib.Path(baseline_build.OUTPUT).open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            loaded[row["passage"]] = row
    for config in isomorph_schema.CONFIGS:
        with pathlib.Path(isomorph_build.output_for(config)).open(encoding="utf-8") as fh:
            loaded[config.name] = json.loads(fh.readline())
    return loaded


@pytest.fixture
def quagmire(rows) -> dict:
    return rows["isomorph_quagmire"]


# --- the sameness contract --------------------------------------------------------


def test_both_paradigms_send_the_same_prompt(quagmire):
    cot, tool = FakeClient(), FakeClient()
    paradigms.solve(cot, quagmire, model="m", tier=2, paradigm="cot")
    paradigms.solve(tool, quagmire, model="m", tier=2, paradigm="tool_use")

    assert cot.requests[0]["messages"] == tool.requests[0]["messages"]


def test_both_paradigms_send_the_same_schema_and_effort(quagmire):
    cot, tool = FakeClient(), FakeClient()
    paradigms.solve(cot, quagmire, model="m", tier=2, paradigm="cot", effort="max")
    paradigms.solve(tool, quagmire, model="m", tier=2, paradigm="tool_use", effort="max")

    assert cot.requests[0]["output_config"] == tool.requests[0]["output_config"]
    assert cot.requests[0]["max_tokens"] == tool.requests[0]["max_tokens"]
    assert cot.requests[0]["thinking"] == tool.requests[0]["thinking"]


def test_the_only_difference_is_the_tool_and_its_guidance(quagmire):
    """Stated as an exhaustive diff, so a future edit that touches one paradigm and not
    the other fails here rather than surfacing as a spurious paradigm gap."""
    cot, tool = FakeClient(), FakeClient()
    paradigms.solve(cot, quagmire, model="m", tier=2, paradigm="cot")
    paradigms.solve(tool, quagmire, model="m", tier=2, paradigm="tool_use")

    a, b = cot.requests[0], tool.requests[0]
    differing = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    assert differing == {"tools", "system"}
    assert "tools" not in a
    assert b["tools"] == [paradigms.CODE_EXECUTION_TOOL]
    assert b["system"] == f"{a['system']}\n\n{paradigms.TOOL_USE_GUIDANCE}"


def test_both_paradigms_score_through_the_same_function(quagmire):
    """The comparison is only meaningful if nothing in scoring branches on paradigm."""
    attempts = [
        paradigms.solve(FakeClient(), quagmire, model="m", tier=2, paradigm=p)
        for p in paradigms.PARADIGMS
    ]
    scored = [results.score(quagmire, a) for a in attempts]
    assert {r.paradigm for r in scored} == set(paradigms.PARADIGMS)
    assert len({r.cer for r in scored}) == 1  # identical output, identical score


def test_scoring_source_never_mentions_paradigm():
    """A structural guard on the claim above."""
    source = pathlib.Path(results.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]      # skip the module docstring, which explains it
    assert 'paradigm ==' not in body
    assert '"cot"' not in body
    assert '"tool_use"' not in body


def test_unknown_paradigm_is_rejected(quagmire):
    with pytest.raises(ValueError, match="unknown paradigm"):
        paradigms.solve(FakeClient(), quagmire, model="m", tier=2, paradigm="psychic")


# --- refusals ---------------------------------------------------------------------


def test_a_refusal_is_recorded_without_reading_content(quagmire):
    """On a refusal the content array is empty, so reading content[0] would raise on the
    exact case being recorded."""
    client = FakeClient(
        message([], stop_reason="refusal", stop_details=SimpleNamespace(category="cyber"))
    )
    attempt = paradigms.solve(client, quagmire, model="m", tier=2)

    assert attempt.refused
    assert attempt.refusal_category == "cyber"
    assert not attempt.usable


def test_both_paradigms_request_server_side_fallback(quagmire):
    for paradigm in paradigms.PARADIGMS:
        client = FakeClient()
        paradigms.solve(client, quagmire, model="m", tier=2, paradigm=paradigm)
        assert client.requests[0]["fallbacks"] == "default"
        assert "server-side-fallback-2026-07-01" in client.requests[0]["betas"]


def test_a_refusal_is_not_scored_as_a_wrong_answer(quagmire):
    """Folding a classifier hit into the model's CER would make the harness's failures
    look like the model's."""
    client = FakeClient(message([], stop_reason="refusal"))
    attempt = paradigms.solve(client, quagmire, model="m", tier=2)
    result = results.score(quagmire, attempt)

    assert result.refused
    assert result.cer is None
    assert result.passed is None


def test_the_model_asked_for_is_kept_apart_from_the_one_that_answered(quagmire):
    """Server-side fallback re-runs a declined request on another model. If the answering
    model overwrote the requested one, that answer would be filed under whichever model
    refused -- putting another model's score in its column, in the comparison the whole
    benchmark exists to make."""
    client = FakeClient(message([answer_block()], model="claude-opus-4-8"))
    attempt = paradigms.solve(client, quagmire, model="claude-opus-5", tier=2)

    assert attempt.requested_model == "claude-opus-5"
    assert attempt.model == "claude-opus-4-8"
    assert attempt.fell_back


def test_no_fallback_leaves_the_two_models_equal(quagmire):
    client = FakeClient(message([answer_block()], model="claude-opus-5"))
    attempt = paradigms.solve(client, quagmire, model="claude-opus-5", tier=2)

    assert attempt.model == attempt.requested_model
    assert not attempt.fell_back


def test_both_models_survive_into_the_persisted_result(quagmire):
    client = FakeClient(message([answer_block()], model="claude-opus-4-8"))
    attempt = paradigms.solve(client, quagmire, model="claude-opus-5", tier=2)
    result = results.score(quagmire, attempt)

    assert result.requested_model == "claude-opus-5"
    assert result.model == "claude-opus-4-8"


# --- paused turns -----------------------------------------------------------------


def test_a_paused_turn_is_resumed(quagmire):
    """Server-side tools run their own loop; hitting its limit ends the turn with
    pause_turn -- a success that is not finished."""
    paused = message(
        [block(type="server_tool_use", input={"code": "print(1)"})],
        stop_reason="pause_turn",
    )
    client = FakeClient(paused, message([answer_block("RECOVERED")]))
    attempt = paradigms.solve(client, quagmire, model="m", tier=2, paradigm="tool_use")

    assert attempt.resumes == 1
    assert attempt.plaintext == "RECOVERED"
    assert len(client.requests) == 2


def test_resuming_appends_the_paused_turn_and_adds_no_user_message(quagmire):
    """The server resumes from the trailing tool-use block. A 'continue' message here
    would corrupt that."""
    paused = message([block(type="text", text="working")], stop_reason="pause_turn")
    client = FakeClient(paused, message([answer_block()]))
    paradigms.solve(client, quagmire, model="m", tier=2, paradigm="tool_use")

    resumed = client.requests[1]["messages"]
    assert len(resumed) == 2
    assert resumed[0] == client.requests[0]["messages"][0]
    assert resumed[1]["role"] == "assistant"


def test_endless_pausing_gives_up_rather_than_looping(quagmire):
    paused = message([block(type="text", text="...")], stop_reason="pause_turn")
    client = FakeClient(*[paused] * (paradigms.MAX_RESUMES + 2))
    attempt = paradigms.solve(client, quagmire, model="m", tier=2, paradigm="tool_use")

    assert attempt.error == "pause_limit_exceeded"
    assert len(client.requests) == paradigms.MAX_RESUMES + 1


def test_tokens_accumulate_across_resumes(quagmire):
    paused = message([block(type="text", text="x")], stop_reason="pause_turn")
    client = FakeClient(paused, paused, message([answer_block()]))
    attempt = paradigms.solve(client, quagmire, model="m", tier=2, paradigm="tool_use")

    assert attempt.resumes == 2
    assert attempt.input_tokens == 300      # three requests at 100 each
    assert attempt.output_tokens == 150


# --- transcript capture -----------------------------------------------------------


def test_code_and_output_are_captured(quagmire):
    client = FakeClient(
        message(
            [
                block(type="server_tool_use", input={"code": "print('IOC', 0.066)"}),
                block(
                    type="bash_code_execution_tool_result",
                    content=SimpleNamespace(stdout="IOC 0.066", stderr="", return_code=0),
                ),
                answer_block("PLAINTEXT"),
            ]
        )
    )
    attempt = paradigms.solve(client, quagmire, model="m", tier=2, paradigm="tool_use")

    assert attempt.code_executions == 1
    assert attempt.transcript[0]["type"] == "code"
    assert attempt.transcript[0]["input"]["code"] == "print('IOC', 0.066)"
    assert attempt.transcript[1] == {
        "type": "result",
        "stdout": "IOC 0.066",
        "stderr": "",
        "return_code": 0,
    }


def test_transcript_survives_json_serialisation(quagmire):
    client = FakeClient(
        message(
            [
                block(type="server_tool_use", input=SimpleNamespace(weird="object")),
                answer_block(),
            ]
        )
    )
    attempt = paradigms.solve(client, quagmire, model="m", tier=2, paradigm="tool_use")
    assert json.loads(json.dumps(attempt.transcript))


def test_cot_captures_no_transcript(quagmire):
    attempt = paradigms.solve(FakeClient(), quagmire, model="m", tier=2, paradigm="cot")
    assert attempt.transcript == []
    assert attempt.code_executions == 0


# --- parsing ----------------------------------------------------------------------


def test_an_unparsable_response_is_an_error_not_an_empty_answer(quagmire):
    client = FakeClient(message([block(type="text", text="I could not solve this.")]))
    attempt = paradigms.solve(client, quagmire, model="m", tier=2)

    assert attempt.error == "unparsed_response"
    assert not attempt.usable


def test_the_plaintext_is_normalised_once_for_both_paradigms(quagmire):
    for paradigm in paradigms.PARADIGMS:
        client = FakeClient(message([answer_block("the answer!! 123")]))
        attempt = paradigms.solve(client, quagmire, model="m", tier=2, paradigm=paradigm)
        assert attempt.plaintext == "THEANSWER"


# --- tier wiring ------------------------------------------------------------------


def test_the_tier_selects_the_prompt(quagmire):
    one, two = FakeClient(), FakeClient()
    paradigms.solve(one, quagmire, model="m", tier=1)
    paradigms.solve(two, quagmire, model="m", tier=2)

    assert one.requests[0]["messages"] != two.requests[0]["messages"]
    assert quagmire["indicator_keyword"] in one.requests[0]["messages"][0]["content"]
    assert quagmire["indicator_keyword"] not in two.requests[0]["messages"][0]["content"]


def test_the_few_shot_example_can_be_dropped(quagmire):
    with_it, without = FakeClient(), FakeClient()
    paradigms.solve(with_it, quagmire, model="m", tier=2, few_shot=True)
    paradigms.solve(without, quagmire, model="m", tier=2, few_shot=False)

    assert tiers.FORMAT_EXAMPLE in with_it.requests[0]["system"]
    assert tiers.FORMAT_EXAMPLE not in without.requests[0]["system"]


def test_delimited_is_a_render_time_axis(quagmire):
    plain, spaced = FakeClient(), FakeClient()
    paradigms.solve(plain, quagmire, model="m", tier=2)
    paradigms.solve(spaced, quagmire, model="m", tier=2, delimited=True)

    assert " ".join(quagmire["problem"]) in spaced.requests[0]["messages"][0]["content"]
    assert plain.requests[0]["system"] == spaced.requests[0]["system"]


# --- scoring ----------------------------------------------------------------------


def test_a_perfect_answer_scores_zero_cer(quagmire):
    client = FakeClient(message([answer_block(quagmire["answer"])]))
    attempt = paradigms.solve(client, quagmire, model="m", tier=2)
    result = results.score(quagmire, attempt)

    assert result.cer == 0.0
    assert result.similarity == 100.0
    assert result.passed is True


def test_a_wrong_answer_fails_the_tier_threshold(quagmire):
    client = FakeClient(message([answer_block("X" * len(quagmire["answer"]))]))
    result = results.score(quagmire, paradigms.solve(client, quagmire, model="m", tier=2))

    assert result.cer > 0.05
    assert result.passed is False


def test_an_unsolved_row_is_scored_on_the_frontier_metrics(rows):
    k4 = rows["K4"]
    hypothesis = ["X"] * 97
    for crib in k4["cribs"]:
        hypothesis[crib["start"] - 1 : crib["end"]] = list(crib["plaintext"])

    client = FakeClient(message([answer_block("".join(hypothesis))]))
    result = results.score(k4, paradigms.solve(client, k4, model="m", tier=4))

    assert result.cer is None                  # no reference plaintext exists
    assert result.cribs_placed == 4
    assert result.fitness is not None
    assert result.passed is None               # tier 4 has no pass mark


def test_which_metric_applies_comes_from_the_row_not_the_caller(rows):
    for key in ("K1", "K4"):
        row = rows[key]
        client = FakeClient(message([answer_block("SOMETHING")]))
        result = results.score(row, paradigms.solve(client, row, model="m", tier=2))
        assert (result.cer is None) == (row["answer"] is None)


# --- persistence ------------------------------------------------------------------


def test_results_round_trip_through_jsonl(tmp_path, quagmire):
    client = FakeClient(message([answer_block(quagmire["answer"])]))
    result = results.score(quagmire, paradigms.solve(client, quagmire, model="m", tier=2))

    target = results.write([result], tmp_path / "runs" / "out.jsonl")
    loaded = results.read(target)

    assert len(loaded) == 1
    assert loaded[0]["instance_id"] == result.instance_id
    assert loaded[0]["cer"] == 0.0
    assert loaded[0]["version"] == results.RESULTS_VERSION


def test_writing_appends_rather_than_overwrites(tmp_path, quagmire):
    """A run is real API spend; silently replacing an earlier one is expensive."""
    client = FakeClient(message([answer_block()]))
    result = results.score(quagmire, paradigms.solve(client, quagmire, model="m", tier=2))

    target = tmp_path / "out.jsonl"
    results.write([result], target)
    results.write([result], target)
    assert len(results.read(target)) == 2


def test_transcripts_can_be_omitted_from_persisted_results(tmp_path, quagmire):
    client = FakeClient(
        message([block(type="server_tool_use", input={"code": "x"}), answer_block()])
    )
    attempt = paradigms.solve(client, quagmire, model="m", tier=2, paradigm="tool_use")

    kept = results.score(quagmire, attempt, keep_transcript=True)
    dropped = results.score(quagmire, attempt, keep_transcript=False)
    assert kept.transcript and dropped.transcript == []


def test_the_run_axes_are_persisted(quagmire):
    """Every axis of the experiment has to be in the record, or a results file cannot be
    interpreted after the fact."""
    client = FakeClient(message([answer_block()]))
    attempt = paradigms.solve(
        client,
        quagmire,
        model="m",
        tier=3,
        paradigm="tool_use",
        delimited=True,
        effort="xhigh",
    )
    # Solved and scored at the same effort deliberately: since v3 the persisted effort is
    # the one the backend *sent*, so passing a different level here would be asserting
    # that the record can disagree with the request.
    result = results.score(quagmire, attempt, delimited=True, effort="xhigh")

    assert (result.tier, result.paradigm, result.delimited, result.effort) == (
        3,
        "tool_use",
        True,
        "xhigh",
    )
    assert result.seed == quagmire["seed"]


def test_summary_counts_only_scoreable_attempts(quagmire):
    good = results.score(
        quagmire,
        paradigms.solve(
            FakeClient(message([answer_block(quagmire["answer"])])),
            quagmire, model="m", tier=2,
        ),
    )
    refused = results.score(
        quagmire,
        paradigms.solve(
            FakeClient(message([], stop_reason="refusal")), quagmire, model="m", tier=2
        ),
    )

    totals = results.summarise([good, refused])
    assert totals["instances"] == 2
    assert totals["scored"] == 1
    assert totals["refused"] == 1
    assert totals["mean_cer"] == 0.0        # the refusal does not drag the mean


# --- runner flags -----------------------------------------------------------------


def test_every_axis_has_a_flag():
    from kryptos.eval import run_benchmark

    parsed = run_benchmark.build_parser().parse_args(
        ["--config", "isomorph_nulls", "--tier", "1", "--paradigm", "tool_use",
         "--delimited", "--effort", "max"]
    )
    assert parsed.config == "isomorph_nulls"
    assert parsed.tier == 1
    assert parsed.paradigm == "tool_use"
    assert parsed.delimited is True
    assert parsed.effort == "max"


def test_flag_defaults_are_the_documented_ones():
    from kryptos.eval import run_benchmark

    parsed = run_benchmark.build_parser().parse_args([])
    assert parsed.config == run_benchmark.DEFAULT_CONFIG
    assert parsed.paradigm == "cot"
    assert parsed.tier is None              # per-row default
    assert parsed.delimited is False


def test_the_runner_offers_every_published_config():
    from kryptos.eval import run_benchmark
    from kryptos.huggingface import push

    assert set(run_benchmark.CONFIGS) == set(push.ALL_CONFIGS)


@pytest.mark.parametrize("bad", [["--tier", "9"], ["--paradigm", "psychic"],
                                ["--config", "isomorph_imaginary"]])
def test_invalid_flag_values_are_rejected(bad):
    from kryptos.eval import run_benchmark

    with pytest.raises(SystemExit):
        run_benchmark.build_parser().parse_args(bad)
