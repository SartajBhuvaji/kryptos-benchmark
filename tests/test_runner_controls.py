"""Verification for the pilot controls: resume, spend ceiling, and concurrency.

These three exist so a long run can be sized, stopped, and continued. Each has a way of
failing that costs money rather than raising an error, and that is what these tests are
aimed at:

* **resume** silently re-running everything (or worse, silently skipping an axis it
  should have run) because its notion of "already done" drifted from the one the
  reporting layer dedupes by;
* **the spend ceiling** quietly ceasing to apply because a model had no price on file
  and was treated as free;
* **concurrency** changing what gets measured rather than only how fast.

No test here makes an API call. The client is a fake that records its calls.
"""

from __future__ import annotations

import json
import pathlib
import threading
from dataclasses import asdict

import pytest

from kryptos.eval import report as reporting
from kryptos.eval import results, run_benchmark


# --- fakes ------------------------------------------------------------------------


class FakeMessage:
    def __init__(self, text, *, input_tokens=1000, output_tokens=500):
        self.content = [type("Text", (), {"type": "text", "text": text})()]
        self.stop_reason = "end_turn"
        self.stop_details = None
        self.usage = type(
            "Usage", (), {"input_tokens": input_tokens, "output_tokens": output_tokens}
        )()
        self.model = "claude-sonnet-5"


class FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


class FakeClient:
    """Records every request, and can be told how long each call takes."""

    def __init__(self, *, plaintext="ANSWER", delay=0.0, tokens=(1000, 500)):
        self.requests: list[dict] = []
        self.concurrent = 0
        self.peak = 0
        self._lock = threading.Lock()
        self._delay = delay
        self._plaintext = plaintext
        self._tokens = tokens
        self.beta = type("Beta", (), {"messages": self})()

    def stream(self, **request):
        with self._lock:
            self.requests.append(request)
            self.concurrent += 1
            self.peak = max(self.peak, self.concurrent)
        if self._delay:
            import time

            time.sleep(self._delay)
        with self._lock:
            self.concurrent -= 1
        body = json.dumps(
            {
                "cipher": "Quagmire III",
                "key": "K",
                "method": "m",
                "plaintext": self._plaintext,
            }
        )
        return FakeStream(
            FakeMessage(body, input_tokens=self._tokens[0], output_tokens=self._tokens[1])
        )


class Args:
    """The subset of parsed arguments the runner reads."""

    def __init__(self, **kwargs):
        defaults = dict(
            model=["claude-sonnet-5"],
            config="baseline",
            tier=2,
            paradigm="cot",
            effort="high",
            delimited=False,
            no_few_shot=False,
            no_transcript=True,
            concurrency=1,
            resume=False,
            max_spend=None,
        )
        defaults.update(kwargs)
        for key, value in defaults.items():
            setattr(self, key, value)


@pytest.fixture
def rows() -> list[dict]:
    return [
        {
            "id": f"inst-{n}",
            "problem": "ABCDEFGHIJ" * 3,
            "problem_letters_only": "ABCDEFGHIJ" * 3,
            "problem_length": 30,
            "cribs": [],
            "answer": "ANSWER",
            "config": "baseline",
            "scoring_metric": "character_error_rate",
        }
        for n in range(6)
    ]


# --- the resume contract ----------------------------------------------------------


def test_a_scored_result_lands_on_the_identity_resume_looks_for(rows):
    """The load-bearing invariant. ``--resume`` skips a job when its planned identity is
    already on disk, so the identity computed *before* the run must equal the one
    computed *from the record* afterwards. If these drift, resume either re-runs
    everything (merely expensive) or skips work it never did (silently wrong)."""
    args = Args()
    job = run_benchmark.plan(rows, args)[0]
    result = run_benchmark.execute(FakeClient(), job, args)

    assert run_benchmark.identity(job, args) == reporting.identity(asdict(result))


def test_resume_skips_only_what_is_answered(tmp_path, rows):
    args = Args()
    jobs = run_benchmark.plan(rows, args)
    path = tmp_path / "run.jsonl"

    results.write([run_benchmark.execute(FakeClient(), jobs[0], args)], path)
    done = run_benchmark.finished(path)

    assert run_benchmark.identity(jobs[0], args) in done
    assert run_benchmark.identity(jobs[1], args) not in done


def test_resume_retries_refusals_and_errors(tmp_path, rows):
    """A refusal is a harness outcome, not an answer. Treating one as finished would
    make --resume cement exactly the failures it exists to recover from."""
    args = Args()
    job = run_benchmark.plan(rows, args)[0]
    good = run_benchmark.execute(FakeClient(), job, args)

    refused = results.Result(**{**asdict(good), "refused": True})
    errored = results.Result(**{**asdict(good), "error": "connection_error"})
    path = tmp_path / "run.jsonl"
    results.write([refused, errored], path)

    assert run_benchmark.finished(path) == set()


def test_resume_distinguishes_axes_not_just_instances(tmp_path, rows):
    """The same instance at a different tier is a different measurement. Skipping on
    instance id alone would silently drop every tier after the first."""
    tier2, tier3 = Args(tier=2), Args(tier=3)
    job2 = run_benchmark.plan(rows, tier2)[0]
    path = tmp_path / "run.jsonl"
    results.write([run_benchmark.execute(FakeClient(), job2, tier2)], path)

    done = run_benchmark.finished(path)
    job3 = run_benchmark.plan(rows, tier3)[0]

    assert run_benchmark.identity(job2, tier2) in done
    assert run_benchmark.identity(job3, tier3) not in done


@pytest.mark.parametrize(
    "changed", [{"paradigm": "tool_use"}, {"delimited": True}, {"effort": "low"}]
)
def test_every_experiment_axis_separates_resume_state(tmp_path, rows, changed):
    base = Args()
    other = Args(**changed)
    path = tmp_path / "run.jsonl"
    results.write(
        [run_benchmark.execute(FakeClient(), run_benchmark.plan(rows, base)[0], base)],
        path,
    )

    done = run_benchmark.finished(path)
    assert run_benchmark.identity(run_benchmark.plan(rows, other)[0], other) not in done


def test_finished_on_a_missing_file_is_empty(tmp_path):
    assert run_benchmark.finished(tmp_path / "nope.jsonl") == set()


# --- the spend ceiling ------------------------------------------------------------


def test_budget_accumulates_priced_spend(rows):
    args = Args()
    budget = run_benchmark.Budget(limit=1.00)
    result = run_benchmark.execute(FakeClient(tokens=(1_000_000, 1_000_000)),
                                   run_benchmark.plan(rows, args)[0], args)
    budget.add(result)

    # Sonnet 5 list: $3.00 in + $15.00 out per million.
    assert budget.spent == pytest.approx(18.00)
    assert budget.exhausted


def test_budget_without_a_limit_never_stops(rows):
    args = Args()
    budget = run_benchmark.Budget(limit=None)
    budget.add(
        run_benchmark.execute(
            FakeClient(tokens=(9_000_000, 9_000_000)), run_benchmark.plan(rows, args)[0], args
        )
    )
    assert not budget.exhausted


def test_an_unpriced_model_stops_the_run_rather_than_running_free(rows):
    """The failure this prevents: a model with no entry in the price table costs $0.00
    by arithmetic, so a ceiling would never be reached and would never be checked
    again. Refusing is the honest response."""
    args = Args()
    budget = run_benchmark.Budget(limit=5.00)
    result = run_benchmark.execute(FakeClient(), run_benchmark.plan(rows, args)[0], args)
    result.model = "some-unreleased-model"
    budget.add(result)

    assert budget.unpriced == {"some-unreleased-model"}
    assert budget.exhausted
    assert budget.spent == 0.0


def test_an_unpriced_model_is_harmless_without_a_ceiling(rows):
    args = Args()
    budget = run_benchmark.Budget(limit=None)
    result = run_benchmark.execute(FakeClient(), run_benchmark.plan(rows, args)[0], args)
    result.model = "some-unreleased-model"
    budget.add(result)
    assert not budget.exhausted


def test_the_ceiling_stops_dispatch_partway(rows):
    """Serial, so the ceiling is exact: each instance costs $0.0105, and a $0.03 limit
    admits three before the fourth check trips it."""
    args = Args(concurrency=1)
    client = FakeClient()
    budget = run_benchmark.Budget(limit=0.03)
    scored = run_benchmark.run(client, run_benchmark.plan(rows, args), args, budget)

    assert len(scored) == 3
    assert len(client.requests) == 3
    assert budget.exhausted


def test_no_ceiling_runs_everything(rows):
    args = Args()
    client = FakeClient()
    jobs = run_benchmark.plan(rows, args)
    scored = run_benchmark.run(client, jobs, args, run_benchmark.Budget(None))
    assert len(scored) == len(jobs)


# --- concurrency ------------------------------------------------------------------


def test_concurrency_actually_overlaps_requests(rows):
    args = Args(concurrency=4)
    client = FakeClient(delay=0.05)
    run_benchmark.run(client, run_benchmark.plan(rows, args), args, run_benchmark.Budget(None))
    assert client.peak > 1


def test_serial_is_the_default_and_never_overlaps(rows):
    args = Args()
    assert args.concurrency == 1
    client = FakeClient(delay=0.01)
    run_benchmark.run(client, run_benchmark.plan(rows, args), args, run_benchmark.Budget(None))
    assert client.peak == 1


def test_concurrency_changes_speed_not_what_is_measured(rows):
    """The whole point. A parallel run and a serial run over the same jobs must produce
    the same set of measurements -- otherwise --concurrency is an experiment variable."""
    serial_args, parallel_args = Args(concurrency=1), Args(concurrency=4)
    jobs = run_benchmark.plan(rows, serial_args)

    serial = run_benchmark.run(FakeClient(), jobs, serial_args, run_benchmark.Budget(None))
    parallel = run_benchmark.run(FakeClient(), jobs, parallel_args, run_benchmark.Budget(None))

    def measurements(scored):
        return {(r.instance_id, r.tier, r.paradigm, r.cer) for r in scored}

    assert measurements(serial) == measurements(parallel)


def test_every_job_runs_exactly_once_under_concurrency(rows):
    args = Args(concurrency=4)
    jobs = run_benchmark.plan(rows, args)
    scored = run_benchmark.run(FakeClient(), jobs, args, run_benchmark.Budget(None))

    ran = [r.instance_id for r in scored]
    assert sorted(ran) == sorted(j.row["id"] for j in jobs)
    assert len(ran) == len(set(ran))


# --- planning ---------------------------------------------------------------------


def test_plan_covers_every_model_and_row(rows):
    args = Args(model=["claude-sonnet-5", "claude-opus-5"])
    jobs = run_benchmark.plan(rows, args)
    assert len(jobs) == 2 * len(rows)
    assert {j.model for j in jobs} == {"claude-sonnet-5", "claude-opus-5"}


def test_plan_uses_the_rows_own_tier_when_none_is_forced():
    args = Args(tier=None)
    unsolved = {
        "id": "k4",
        "problem": "X" * 97,
        "problem_length": 97,
        "answer": None,
        "cribs": [],
        "passage": "K4",
    }
    assert run_benchmark.plan([unsolved], args)[0].tier == 4


def test_cli_exposes_the_three_controls():
    args = run_benchmark.build_parser().parse_args(
        ["--resume", "--concurrency", "4", "--max-spend", "2.50"]
    )
    assert args.resume is True
    assert args.concurrency == 4
    assert args.max_spend == 2.50


def test_the_controls_default_to_the_previous_behaviour():
    args = run_benchmark.build_parser().parse_args([])
    assert args.resume is False
    assert args.concurrency == 1
    assert args.max_spend is None
