"""Run the Kryptos benchmark and print the results.

This is the project's harness, and it grows with the project. It scores through
:mod:`kryptos.scoring` so the tier thresholds, the isomorph verification and the Phase 5
reports all measure with the same code.

A deliberately minimal standalone version ships with the dataset itself, at
``src/kryptos/dataset/example.py``. That one imports nothing from this repository and is
meant to stay small; this one is not.

    python -m kryptos.eval.run_benchmark --config baseline
    python -m kryptos.eval.run_benchmark --config isomorph_quagmire --tier 2
    python -m kryptos.eval.run_benchmark --config isomorph_quagmire --paradigm tool_use
    python -m kryptos.eval.run_benchmark --config baseline --delimited --limit 2
    python -m kryptos.eval.run_benchmark --model claude-opus-5 claude-sonnet-5
    python -m kryptos.eval.run_benchmark --config isomorph_transposition --out runs/x.jsonl

The four axes are independent by design. **Config** selects the data, **tier** how the
problem is framed, **paradigm** whether the model may run code, and **delimited** how the
ciphertext is rendered. Holding three fixed and varying the fourth is what makes each
comparison a result rather than a coincidence -- the baseline-vs-isomorph gap, the
chain-of-thought-vs-tool-use gap, and the tokenization claim all come from exactly that.

``--model`` takes several models, run one after another against the same instances in the
same order. Sharing one invocation is what keeps them comparable: the models cannot drift
apart on tier, presentation or instance set, because there is only one of each to drift.

Only the dataset's input fields are ever sent to the model, and which fields count as
input depends on the tier -- tier 1 supplies the keys on purpose. That policy lives in
:mod:`kryptos.eval.tiers` and is enforced there rather than here.

This prints one run. Aggregating several into the comparisons -- baseline vs isomorph,
chain of thought vs tool use, raw vs delimited, cost -- is :mod:`kryptos.eval.report`,
which reads the JSONL this writes.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass

if __package__ in (None, ""):  # allow running the file directly
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from kryptos.eval import paradigms, providers, report as reporting, results, tiers

DATASET = "sartajbhuvaji/kryptos-bench"
SPLIT = "test"
DEFAULT_MODEL = "claude-opus-5"
DEFAULT_CONFIG = "baseline"

#: Every config the dataset publishes. Kept in the order a reader would want them.
CONFIGS = (
    "baseline",
    "isomorph_quagmire",
    "isomorph_transposition",
    "isomorph_composite",
    "isomorph_nulls",
)


def load_rows(config: str, limit: int | None, passages: list[str] | None) -> list[dict]:
    from datasets import load_dataset

    rows = [dict(r) for r in load_dataset(DATASET, config, split=SPLIT)]

    if passages:
        wanted = {p.upper() for p in passages}
        rows = [r for r in rows if str(r.get("passage", "")).upper() in wanted]
        if not rows:
            raise SystemExit(f"no passages matched {sorted(wanted)}")
    if limit is not None:
        rows = rows[:limit]
    return rows


@dataclass(frozen=True)
class Job:
    """One instance, at one tier, for one model -- the unit of work and of resumption."""

    model: str
    tier: int
    row: dict

    def __hash__(self) -> int:  # rows are dicts; identify a job by what names it
        return hash((self.model, self.tier, self.row["id"]))


def identity(job: Job, args) -> tuple:
    """The identity a job's result will be persisted under.

    Built by handing a synthetic record to the reporting module's own
    :func:`~kryptos.eval.report.identity`, rather than assembling the tuple here. The
    resume check is only correct while the two agree, and a field added to one but not
    the other would otherwise make every instance look unfinished -- or worse, make a
    changed axis look already done.
    """
    return reporting.identity(
        {
            "instance_id": job.row["id"],
            "tier": job.tier,
            "paradigm": args.paradigm,
            "requested_model": job.model,
            "delimited": args.delimited,
            "effort": args.effort,
        }
    )


def plan(rows: list[dict], args) -> list[Job]:
    """Every job this invocation would run, models outermost."""
    return [
        Job(model=model, tier=args.tier or tiers.default_tier(row), row=row)
        for model in args.model
        for row in rows
    ]


def finished(path: str | pathlib.Path) -> set[tuple]:
    """Identities already answered in a results file, so ``--resume`` can skip them.

    **Refusals and errors are deliberately not counted as finished.** They are harness
    outcomes, not answers, and a resumed run is usually a response to exactly those --
    a dropped connection, a rate limit, one classifier hit. Skipping them would make
    ``--resume`` cement the failures it exists to recover from. Re-running appends a
    fresh record, and the reporting layer already keeps the newest per identity.
    """
    target = pathlib.Path(path)
    if not target.exists():
        return set()
    return {
        reporting.identity(record)
        for record in results.read(target)
        if not record.get("refused") and not record.get("error")
    }


class Budget:
    """A spend ceiling in USD, checked between dispatches.

    Not a hard cap, and the distinction matters when running in parallel: work already
    in flight when the ceiling is crossed is allowed to finish, so the final figure can
    exceed the limit by up to ``concurrency - 1`` instances. Set the ceiling below what
    you are actually willing to spend.

    An unpriced model is refused outright rather than treated as free. A ceiling that
    silently stops applying is worse than no ceiling, because it is the one you stop
    checking.
    """

    def __init__(self, limit: float | None) -> None:
        self.limit = limit
        self.spent = 0.0
        self.unpriced: set[str] = set()

    def add(self, result: results.Result) -> None:
        amount = reporting.usd(asdict(result))
        if amount is None:
            self.unpriced.add(result.model)
        else:
            self.spent += amount

    @property
    def exhausted(self) -> bool:
        if self.limit is None:
            return False
        if self.unpriced:
            return True          # cannot price the run; stop rather than guess
        return self.spent >= self.limit


def execute(client, job: Job, args) -> results.Result:
    """Run one job and score it. Called on a worker thread; touches no shared state."""
    options = {}
    if args.provider == "openai":
        options["reasoning_effort"] = not args.no_reasoning_effort

    attempt = paradigms.solve(
        client,
        job.row,
        model=job.model,
        tier=job.tier,
        paradigm=args.paradigm,
        effort=args.effort,
        delimited=args.delimited,
        few_shot=not args.no_few_shot,
        **options,
    )
    return results.score(
        job.row,
        attempt,
        delimited=args.delimited,
        effort=args.effort,
        keep_transcript=not args.no_transcript,
    )


def run(client, jobs: list[Job], args, budget: Budget) -> list[results.Result]:
    """Work through the jobs, up to ``--concurrency`` at a time, until the budget stops.

    Dispatch is windowed rather than submitted up front: a budget checked only before
    the first submission is not a budget. Interrupting returns what has been scored so
    far, so a long run can be stopped and resumed rather than lost.
    """
    scored: list[results.Result] = []
    queue = iter(jobs)
    in_flight: set[Future] = set()
    total = len(jobs)

    def fill(pool: ThreadPoolExecutor) -> None:
        while len(in_flight) < args.concurrency and not budget.exhausted:
            job = next(queue, None)
            if job is None:
                return
            label = job.row.get("passage") or job.row["id"]
            print(
                f"[{job.model}] solving {label} ({job.row['problem_length']} chars) "
                f"tier {job.tier} {args.paradigm}...",
                file=sys.stderr,
            )
            in_flight.add(pool.submit(execute, client, job, args))

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        try:
            fill(pool)
            while in_flight:
                done, pending = wait(in_flight, return_when=FIRST_COMPLETED)
                in_flight.clear()
                in_flight.update(pending)
                for future in done:
                    result = future.result()
                    scored.append(result)
                    budget.add(result)
                    print(
                        f"  {len(scored)}/{total} done"
                        + (f", ${budget.spent:.2f} spent" if budget.limit else ""),
                        file=sys.stderr,
                    )
                fill(pool)
        except KeyboardInterrupt:
            print(
                f"\ninterrupted after {len(scored)} instance(s); "
                "writing what completed -- re-run with --resume to continue",
                file=sys.stderr,
            )

    return scored


def report(rows: list[dict], scored: list[results.Result], model: str, args) -> None:
    by_id = {r["id"]: r for r in rows}

    print()
    print(f"Kryptos benchmark -- {DATASET} [{args.config}/{SPLIT}] -- {model}")
    print(
        f"tier {args.tier or 'auto'} | paradigm {args.paradigm} | "
        f"effort {args.effort} | {'delimited' if args.delimited else 'raw'}"
    )
    print("=" * 82)
    print(f"{'instance':<34} {'tier':<5} {'score':<28} {'identified as':<14}")
    print("-" * 82)

    for result in scored:
        row = by_id[result.instance_id]
        label = str(row.get("passage") or result.instance_id)[:32]

        if result.refused:
            score = f"refused ({result.refusal_category or 'uncategorised'})"
        elif result.error:
            score = f"error ({result.error})"
        elif result.cer is not None:
            verdict = "SOLVED" if result.cer == 0.0 else ""
            if result.passed and result.cer > 0.0:
                verdict = "passed"
            score = f"CER {result.cer:6.1%}  sim {result.similarity:5.1f}  {verdict}"
        else:
            score = (
                f"{result.cribs_placed}/{result.cribs_total} cribs, "
                f"fit {result.fitness:.2f}"
            )

        print(f"{label:<34} {result.tier:<5} {score:<28} {result.cipher[:14]:<14}")

    print("-" * 82)
    totals = results.summarise(scored)
    if totals["mean_cer"] is not None:
        print(
            f"mean CER over {totals['scored']} scoreable instance(s): "
            f"{totals['mean_cer']:.1%}  |  solved {totals['solved']}  |  "
            f"passed tier {totals['passed']}"
        )
    if totals["refused"] or totals["errored"]:
        print(
            f"not scored: {totals['refused']} refused, {totals['errored']} errored "
            "-- these are harness outcomes, not wrong answers"
        )
    print(
        f"tokens: {totals['input_tokens']:,} in / {totals['output_tokens']:,} out"
        + (
            f"  |  {totals['code_executions']} code execution(s)"
            if args.paradigm == "tool_use"
            else ""
        )
    )

    if args.config == "baseline":
        print()
        print("K1-K3 and their solutions are widely published, so a low CER here does not")
        print("distinguish cryptanalysis from recall. Read it as a memorisation baseline.")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--model",
        nargs="+",
        default=[DEFAULT_MODEL],
        metavar="MODEL",
        help="one or more models, run against the same instances in the same order",
    )
    ap.add_argument(
        "--config",
        default=DEFAULT_CONFIG,
        choices=CONFIGS,
        help="which published config to evaluate",
    )
    ap.add_argument(
        "--tier",
        type=int,
        choices=[t.number for t in tiers.TIERS],
        help="task framing; defaults to the tier each row is normally posed at",
    )
    ap.add_argument(
        "--paradigm",
        default="cot",
        choices=list(paradigms.PARADIGMS),
        help="cot reasons in-context; tool_use gives the model a Python sandbox",
    )
    ap.add_argument(
        "--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"]
    )
    ap.add_argument(
        "--delimited",
        action="store_true",
        help="space-separate ciphertext characters (tokenization mitigation)",
    )
    ap.add_argument(
        "--no-few-shot",
        action="store_true",
        help="drop the worked format example, so its effect can be measured",
    )
    ap.add_argument("--passages", nargs="+", metavar="K", help="baseline only, e.g. K1 K3")
    ap.add_argument("--limit", type=int, help="evaluate only the first N instances")
    ap.add_argument(
        "--out",
        help="append per-instance results as JSONL (default: runs/<config>.jsonl)",
    )
    ap.add_argument(
        "--no-transcript",
        action="store_true",
        help="omit tool-use transcripts from the persisted results",
    )
    ap.add_argument(
        "--provider",
        default="anthropic",
        choices=list(providers.PROVIDERS),
        help="which API to call; openai covers any server speaking that wire format",
    )
    ap.add_argument(
        "--base-url",
        metavar="URL",
        help="override the API endpoint (vLLM, OpenRouter, Together, a local runtime)",
    )
    ap.add_argument(
        "--api-key-env",
        metavar="VAR",
        help="environment variable holding the key (default ANTHROPIC_API_KEY / "
        "OPENAI_API_KEY). The key itself is never a command-line argument",
    )
    ap.add_argument(
        "--provider-param",
        action="append",
        metavar="K=V",
        help="extra raw request field, repeatable, JSON-decoded "
        "(e.g. max_completion_tokens=32000 for OpenAI reasoning models)",
    )
    ap.add_argument(
        "--no-reasoning-effort",
        action="store_true",
        help="OpenAI only: omit reasoning_effort for servers that reject it; the "
        "recorded effort then reads 'unset' rather than claiming a level",
    )
    ap.add_argument(
        "--price",
        action="append",
        metavar="MODEL=IN/OUT",
        help="USD per million tokens for a model with no published rate on file, "
        "repeatable (e.g. gpt-5=1.25/10). Without it a non-Claude run is unpriced",
    )
    ap.add_argument(
        "--resume",
        action="store_true",
        help="skip instances already answered in the output file; refusals and errors "
        "are retried rather than skipped",
    )
    ap.add_argument(
        "--concurrency",
        type=int,
        default=1,
        metavar="N",
        help="instances in flight at once (default 1; 4-8 is a reasonable range)",
    )
    ap.add_argument(
        "--max-spend",
        type=float,
        metavar="USD",
        help="stop dispatching once this much has been spent; work already in flight "
        "finishes, so the ceiling is soft by up to --concurrency instances",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    sdk = {"anthropic": "anthropic", "openai": "openai"}[args.provider]
    try:
        __import__(sdk)
        import datasets  # noqa: F401
    except ImportError as exc:
        print(
            f"missing dependency: {exc.name}\n  pip install {sdk} datasets rapidfuzz",
            file=sys.stderr,
        )
        return 1

    for spec in args.price or []:
        reporting.register_price(*reporting.parse_price(spec))

    key = providers.key_from_env(args.provider, args.api_key_env)
    if not key:
        named = args.api_key_env or providers.DEFAULT_KEY_ENV[args.provider]
        if args.provider == "anthropic":
            # Not fatal: the SDK also resolves an `ant auth login` profile.
            print(f"note: {named} unset; falling back to a stored auth profile",
                  file=sys.stderr)
        else:
            raise SystemExit(f"{named} is unset, and {args.provider} needs a key")

    if args.concurrency < 1:
        raise SystemExit("--concurrency must be at least 1")

    # Loaded once and shared by every model, so the instance set cannot differ between
    # them -- the comparison depends on it being the same set in the same order.
    rows = load_rows(args.config, args.limit, args.passages)
    out = args.out or f"runs/{args.config}.jsonl"
    jobs = plan(rows, args)

    if args.resume:
        done = finished(out)
        jobs, skipped = [j for j in jobs if identity(j, args) not in done], len(jobs)
        skipped -= len(jobs)
        print(f"resuming: {skipped} already answered, {len(jobs)} to run", file=sys.stderr)
        if not jobs:
            print("nothing left to run", file=sys.stderr)
            return 0

    backend = providers.backend_for(
        args.provider,
        providers.client_for(args.provider, base_url=args.base_url, api_key=key),
        extra=providers.parse_params(args.provider_param),
    )
    if not backend.supports(args.paradigm):
        raise SystemExit(
            f"the {args.paradigm!r} paradigm is not available on {args.provider!r}; "
            f"it supports {list(providers.SUPPORTED_PARADIGMS[args.provider])}"
        )

    budget = Budget(args.max_spend)
    scored = run(backend, jobs, args, budget)

    # Grouped by the model requested, not the one that answered: a fallback belongs in
    # the column of the model it was asked of, or it silently vanishes from the run.
    for model in args.model:
        mine = [r for r in scored if r.requested_model == model]
        if mine:
            report(rows, mine, model, args)

    target = results.write(scored, out)
    print(f"\nwrote {len(scored)} result(s) to {target}", file=sys.stderr)
    if budget.unpriced:
        print(
            f"stopped: no price on file for {', '.join(sorted(budget.unpriced))}, so "
            "--max-spend could not be enforced",
            file=sys.stderr,
        )
    elif budget.exhausted:
        print(
            f"stopped: spend ceiling reached (${budget.spent:.2f} of ${args.max_spend:.2f}); "
            f"{len(jobs) - len(scored)} instance(s) not run -- --resume continues",
            file=sys.stderr,
        )
    elif args.max_spend:
        print(f"spent ${budget.spent:.2f} of ${args.max_spend:.2f}", file=sys.stderr)
    print(f"aggregate with: python -m kryptos.eval.report {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
