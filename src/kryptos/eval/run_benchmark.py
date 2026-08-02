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
    python -m kryptos.eval.run_benchmark --config isomorph_transposition --out runs/x.jsonl

The four axes are independent by design. **Config** selects the data, **tier** how the
problem is framed, **paradigm** whether the model may run code, and **delimited** how the
ciphertext is rendered. Holding three fixed and varying the fourth is what makes each
comparison a result rather than a coincidence -- the baseline-vs-isomorph gap, the
chain-of-thought-vs-tool-use gap, and the tokenization claim all come from exactly that.

Only the dataset's input fields are ever sent to the model, and which fields count as
input depends on the tier -- tier 1 supplies the keys on purpose. That policy lives in
:mod:`kryptos.eval.tiers` and is enforced there rather than here.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys

if __package__ in (None, ""):  # allow running the file directly
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from kryptos.eval import paradigms, results, tiers

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
    ap.add_argument("--model", default=DEFAULT_MODEL)
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
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        import anthropic  # noqa: F401
        import datasets  # noqa: F401
    except ImportError as exc:
        print(
            f"missing dependency: {exc.name}\n  pip install anthropic datasets rapidfuzz",
            file=sys.stderr,
        )
        return 1

    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        # Not fatal: the SDK also resolves an `ant auth login` profile.
        print(
            "note: ANTHROPIC_API_KEY unset; falling back to a stored auth profile",
            file=sys.stderr,
        )

    rows = load_rows(args.config, args.limit, args.passages)
    client = anthropic.Anthropic()

    scored: list[results.Result] = []
    for row in rows:
        tier = args.tier or tiers.default_tier(row)
        label = row.get("passage") or row["id"]
        print(
            f"solving {label} ({row['problem_length']} chars) "
            f"tier {tier} {args.paradigm}...",
            file=sys.stderr,
        )

        attempt = paradigms.solve(
            client,
            row,
            model=args.model,
            tier=tier,
            paradigm=args.paradigm,
            effort=args.effort,
            delimited=args.delimited,
            few_shot=not args.no_few_shot,
        )
        scored.append(
            results.score(
                row,
                attempt,
                delimited=args.delimited,
                effort=args.effort,
                keep_transcript=not args.no_transcript,
            )
        )

    report(rows, scored, args.model, args)

    target = results.write(scored, args.out or f"runs/{args.config}.jsonl")
    print(f"\nwrote {len(scored)} result(s) to {target}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
