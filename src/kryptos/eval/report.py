"""Aggregating persisted runs into the comparisons the benchmark exists to make.

This module adds no capability. Every number it prints was already written to disk by
:mod:`kryptos.eval.results`, one record per instance. What it adds is the arithmetic that
turns those records into results -- and the discipline about *which* records may be
averaged together, which is the only part of reporting that can quietly lie.

Three rules the code enforces rather than documents
---------------------------------------------------
**Never average across metric families.** A row with a reference answer is scored by
character error rate; a row without one (K4) is scored by crib placement and quadgram
fitness. They are different scales with no common zero. :class:`Summary` therefore keeps
two disjoint populations and reports both, and no code path mixes them.

**Paired comparisons are paired.** The chain-of-thought vs tool-use gap and the
raw vs delimited gap are differences *on the same instances*. Comparing group means would
let an unequal set of instances masquerade as a paradigm effect -- if a refusal drops one
hard instance from the tool-use arm, its mean improves for free. :func:`compare` matches
records on every axis except the one under test and discards anything unpaired, reporting
how many pairs survived.

**Baseline vs isomorph cannot be paired, and says so.** They are different instances by
construction -- that is the whole design. :func:`headline` reports it as an unpaired
difference of means and labels it as such, because the alternative is a paired comparison
that silently invents correspondences between K1 and a synthetic Quagmire.

Duplicate records
-----------------
:func:`kryptos.eval.results.write` appends, so re-running a config appends a second record
for the same instance. For aggregation the most recent record wins, and the number
superseded is reported rather than absorbed.

    python -m kryptos.eval.report runs/*.jsonl
    python -m kryptos.eval.report runs/*.jsonl --by model tier
"""

from __future__ import annotations

import argparse
import glob
import pathlib
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

if __package__ in (None, ""):  # allow running the file directly
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from kryptos.eval.results import RESULTS_VERSION

#: The axes that identify one measurement. Two records agreeing on all of these are the
#: same experiment run twice, not two data points.
#:
#: The model axis is the *requested* model, not the one that answered. Grouping by the
#: answering model would file a fallback's answer under the substitute, so a model that
#: refused everything would appear to have no results rather than to have refused.
IDENTITY = ("instance_id", "tier", "paradigm", "requested_model", "delimited", "effort")

#: What each comparison varies, and what it must hold fixed to be a fair pair.
COMPARABLE = {
    "paradigm": tuple(k for k in IDENTITY if k != "paradigm"),
    "delimited": tuple(k for k in IDENTITY if k != "delimited"),
    "effort": tuple(k for k in IDENTITY if k != "effort"),
    "tier": tuple(k for k in IDENTITY if k != "tier"),
    "requested_model": tuple(k for k in IDENTITY if k != "requested_model"),
}

#: Anthropic list prices, USD per million tokens, as of 2026-08-01. Sonnet 5 also has an
#: introductory rate of $2.00/$10.00 running through 2026-08-31; the list price is used
#: here so a cost figure does not silently change meaning when the promotion ends. A run
#: billed during the promotion costs less than this reports -- it never costs more.
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

PER_MILLION = 1_000_000


# --- loading ----------------------------------------------------------------------


def load(paths: Iterable[str | pathlib.Path]) -> list[dict]:
    """Read one or more results files, newest record per experiment.

    Unknown schema versions are refused rather than reinterpreted: a field that changed
    meaning would produce a plausible number from incompatible data.
    """
    import json

    records: list[dict] = []
    for path in paths:
        with pathlib.Path(path).open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    records.append(json.loads(line))

    unknown = {r.get("version") for r in records} - {RESULTS_VERSION}
    if unknown:
        raise SystemExit(
            f"results version {sorted(unknown)} != {RESULTS_VERSION}; "
            "these records were written by a different schema"
        )
    return records


def deduplicate(records: Sequence[dict]) -> tuple[list[dict], int]:
    """Keep the most recent record per experiment. Returns the records and how many
    earlier ones it superseded."""
    latest: dict[tuple, dict] = {}
    for record in records:
        key = identity(record)
        seen = latest.get(key)
        if seen is None or record.get("timestamp", "") >= seen.get("timestamp", ""):
            latest[key] = record
    return list(latest.values()), len(records) - len(latest)


def identity(record: dict) -> tuple:
    return tuple(_key(record, axis) for axis in IDENTITY)


def requested(record: dict) -> str:
    """The model a record belongs to. Falls back to the answering model, which is the
    same thing whenever no fallback fired."""
    return str(record.get("requested_model") or record.get("model") or "")


def fell_back(record: dict) -> bool:
    """Whether another model answered for the one that was asked."""
    served = str(record.get("model") or "")
    return bool(served) and served != requested(record)


def family(record: dict) -> str:
    """``baseline`` or ``isomorph`` -- the headline comparison's two sides.

    Baseline rows carry no ``config`` field, so their config is the passage name (``K1``);
    isomorph rows carry ``isomorph_<cipher>``. Matching on the prefix handles both, and
    handles a future config named for its cipher rather than its provenance.
    """
    return "isomorph" if str(record.get("config", "")).startswith("isomorph") else "baseline"


# --- aggregation ------------------------------------------------------------------


@dataclass
class Summary:
    """One population of results. The two metric families are kept apart."""

    instances: int = 0
    refused: int = 0
    errored: int = 0
    #: Answered by a different model than the one requested, via server-side fallback.
    #: Reported rather than absorbed: these are somebody else's scores.
    fell_back: int = 0

    # --- rows with a reference answer ---
    scored: int = 0
    solved: int = 0
    passed: int = 0
    mean_cer: float | None = None
    mean_similarity: float | None = None

    # --- rows without one (tier 4) ---
    frontier: int = 0
    mean_cribs_placed: float | None = None
    cribs_total: int = 0
    mean_fitness: float | None = None

    # --- spend ---
    input_tokens: int = 0
    output_tokens: int = 0
    code_executions: int = 0
    resumes: int = 0
    #: Models that answered -- what a cost table bills against.
    models: set[str] = field(default_factory=set)
    #: Models that were asked -- what a per-model score belongs to.
    requested_models: set[str] = field(default_factory=set)

    @property
    def solve_rate(self) -> float | None:
        return self.solved / self.scored if self.scored else None


def summarise(records: Sequence[dict]) -> Summary:
    """Aggregate a population. Only scoreable attempts reach a mean."""
    cers = [r["cer"] for r in records if r.get("cer") is not None]
    sims = [r["similarity"] for r in records if r.get("similarity") is not None]
    placed = [r["cribs_placed"] for r in records if r.get("cribs_placed") is not None]
    fits = [r["fitness"] for r in records if r.get("fitness") is not None]
    totals = [r["cribs_total"] for r in records if r.get("cribs_total") is not None]

    return Summary(
        instances=len(records),
        refused=sum(1 for r in records if r.get("refused")),
        errored=sum(1 for r in records if r.get("error")),
        fell_back=sum(1 for r in records if fell_back(r)),
        scored=len(cers),
        solved=sum(1 for c in cers if c == 0.0),
        passed=sum(1 for r in records if r.get("passed") is True),
        mean_cer=_mean(cers),
        mean_similarity=_mean(sims),
        frontier=len(placed),
        mean_cribs_placed=_mean(placed),
        cribs_total=max(totals) if totals else 0,
        mean_fitness=_mean(fits),
        input_tokens=sum(r.get("input_tokens", 0) for r in records),
        output_tokens=sum(r.get("output_tokens", 0) for r in records),
        code_executions=sum(r.get("code_executions", 0) for r in records),
        resumes=sum(r.get("resumes", 0) for r in records),
        models={str(r.get("model", "")) for r in records if r.get("model")},
        requested_models={
            requested(r) for r in records if requested(r)
        },
    )


def breakdown(records: Sequence[dict], *keys: str) -> list[tuple[tuple, Summary]]:
    """Group by the given fields and summarise each group, in sorted key order."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for record in records:
        groups[tuple(_key(record, k) for k in keys)].append(record)
    return [(key, summarise(groups[key])) for key in sorted(groups, key=_sortable)]


DERIVED = {"family": family, "requested_model": requested}


def _key(record: dict, field_name: str):
    derive = DERIVED.get(field_name)
    return derive(record) if derive else record.get(field_name)


def _sortable(key: tuple) -> tuple:
    return tuple((v is None, str(v)) for v in key)


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


# --- comparisons ------------------------------------------------------------------


@dataclass
class Comparison:
    """One axis varied with everything else held fixed."""

    axis: str
    left: Any
    right: Any
    pairs: int
    unpaired: int
    paired: bool = True
    #: Mean CER on each side, over the paired instances only.
    left_cer: float | None = None
    right_cer: float | None = None
    #: Instances solved outright on each side.
    left_solved: int = 0
    right_solved: int = 0
    left_output_tokens: int = 0
    right_output_tokens: int = 0

    @property
    def cer_gap(self) -> float | None:
        """Left minus right. Negative means the left arm scored *better* (lower error)."""
        if self.left_cer is None or self.right_cer is None:
            return None
        return self.left_cer - self.right_cer


def compare(records: Sequence[dict], axis: str, left, right) -> Comparison:
    """Compare two values of one axis over instances measured on *both* sides.

    Records that appear on only one side are discarded and counted, so a refusal that
    removed a hard instance from one arm cannot flatter that arm's mean.
    """
    if axis not in COMPARABLE:
        raise ValueError(f"cannot pair on {axis!r}; choose from {sorted(COMPARABLE)}")

    held = COMPARABLE[axis]
    sides: dict[Any, dict[tuple, dict]] = {left: {}, right: {}}
    for record in records:
        value = _key(record, axis)
        if value in sides:
            sides[value][tuple(_key(record, k) for k in held)] = record

    shared = set(sides[left]) & set(sides[right])
    unpaired = (len(sides[left]) - len(shared)) + (len(sides[right]) - len(shared))

    lefts = [sides[left][k] for k in shared]
    rights = [sides[right][k] for k in shared]
    a, b = summarise(lefts), summarise(rights)

    return Comparison(
        axis=axis,
        left=left,
        right=right,
        pairs=len(shared),
        unpaired=unpaired,
        left_cer=a.mean_cer,
        right_cer=b.mean_cer,
        left_solved=a.solved,
        right_solved=b.solved,
        left_output_tokens=a.output_tokens,
        right_output_tokens=b.output_tokens,
    )


def headline(records: Sequence[dict], model: str) -> Comparison:
    """Baseline score vs isomorph score, for one model.

    **Deliberately unpaired.** The two sides are different instances -- that is the
    experiment, not a defect in it. Pairing would require pretending K1 corresponds to
    some particular synthetic Quagmire.
    """
    mine = [r for r in records if requested(r) == model]
    base = [r for r in mine if family(r) == "baseline"]
    iso = [r for r in mine if family(r) == "isomorph"]
    a, b = summarise(base), summarise(iso)

    return Comparison(
        axis="family",
        left="baseline",
        right="isomorph",
        pairs=0,
        unpaired=0,
        paired=False,
        left_cer=a.mean_cer,
        right_cer=b.mean_cer,
        left_solved=a.solved,
        right_solved=b.solved,
        left_output_tokens=a.output_tokens,
        right_output_tokens=b.output_tokens,
    )


# --- cost -------------------------------------------------------------------------


@dataclass
class Cost:
    model: str
    input_tokens: int
    output_tokens: int
    input_usd: float | None
    output_usd: float | None

    @property
    def total_usd(self) -> float | None:
        if self.input_usd is None or self.output_usd is None:
            return None
        return self.input_usd + self.output_usd

    @property
    def priced(self) -> bool:
        return self.total_usd is not None


def price_for(model: str) -> tuple[float, float] | None:
    """Rates for a model, or ``None`` if it is not in the table.

    An unpriced model must report ``None``, never zero -- a run that silently costs
    nothing is the one number nobody double-checks. The prefix match exists because the
    persisted model is whatever the API returned, which may be a dated variant of the
    alias that was requested, or a fallback model.
    """
    if model in PRICES:
        return PRICES[model]
    candidates = [name for name in PRICES if model.startswith(name)]
    return PRICES[max(candidates, key=len)] if candidates else None


def cost(records: Sequence[dict]) -> list[Cost]:
    """Token and dollar accounting, by the model that *answered*.

    Deliberately the served model, not the requested one: a fallback bills at the rate of
    whichever model actually ran. Scores group the other way -- see :data:`IDENTITY`.
    """
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for record in records:
        entry = totals[str(record.get("model", ""))]
        entry[0] += record.get("input_tokens", 0)
        entry[1] += record.get("output_tokens", 0)

    rows = []
    for model, (tokens_in, tokens_out) in sorted(totals.items()):
        rate = price_for(model)
        rows.append(
            Cost(
                model=model,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                input_usd=tokens_in * rate[0] / PER_MILLION if rate else None,
                output_usd=tokens_out * rate[1] / PER_MILLION if rate else None,
            )
        )
    return rows


# --- rendering --------------------------------------------------------------------

WIDTH = 78


def render_breakdown(records: Sequence[dict], *keys: str) -> str:
    rows = breakdown(records, *keys)
    labels = {key: " ".join(_label(k) for k in key) for key, _ in rows}

    # Sized to the longest label rather than truncated to a fixed width. Truncation once
    # produced two visibly identical rows carrying different numbers, which is a worse
    # failure than a wide table.
    pad = max([len(v) for v in labels.values()] + [len("group")])
    rule = "-" * (pad + 43)

    lines = [_heading("by " + " / ".join(keys))]
    lines.append(
        f"{'group':<{pad}} {'n':>4} {'CER':>8} {'solved':>7} {'passed':>7} "
        f"{'cribs':>7} {'fit':>7}"
    )
    lines.append(rule)
    for key, s in rows:
        label = labels[key]
        cer = f"{s.mean_cer:.1%}" if s.mean_cer is not None else "--"
        solved = f"{s.solved}/{s.scored}" if s.scored else "--"
        passed = str(s.passed) if s.scored else "--"
        cribs = (
            f"{s.mean_cribs_placed:.1f}/{s.cribs_total}"
            if s.mean_cribs_placed is not None
            else "--"
        )
        fit = f"{s.mean_fitness:.2f}" if s.mean_fitness is not None else "--"
        lines.append(
            f"{label:<{pad}} {s.instances:>4} {cer:>8} {solved:>7} {passed:>7} "
            f"{cribs:>7} {fit:>7}"
        )
        if s.refused or s.errored:
            lines.append(
                f"{'':<{pad}} {s.refused} refused, {s.errored} errored "
                "(harness outcomes, excluded from the mean)"
            )
        if s.fell_back:
            lines.append(f"{'':<{pad}} {s.fell_back} answered by a fallback model")
    return "\n".join(lines)


#: How a string axis value reads in a heading.
VALUE_LABELS = {"cot": "chain of thought"}


def _label(value) -> str:
    """Render an axis value for a human.

    Booleans are matched by type, not by dict lookup: ``1 == True`` in Python, so a
    ``{True: "delimited"}`` entry would silently relabel tier 1 as "delimited".
    """
    if isinstance(value, bool):
        return "delimited" if value else "raw"
    if isinstance(value, str):
        return VALUE_LABELS.get(value, value)
    return str(value)


def render_comparison(c: Comparison) -> str:
    lines = [f"  {_label(c.left)} vs {_label(c.right)}"]
    if c.paired:
        lines.append(f"    paired instances: {c.pairs}   discarded unpaired: {c.unpaired}")
    else:
        lines.append("    unpaired -- different instances by construction")

    if c.left_cer is None or c.right_cer is None:
        lines.append("    not enough scoreable results on both sides")
        return "\n".join(lines)

    lines.append(
        f"    mean CER   {c.left_cer:>7.1%}  vs {c.right_cer:>7.1%}   "
        f"gap {c.cer_gap:+.1%}"
    )
    lines.append(
        f"    solved     {c.left_solved:>7}  vs {c.right_solved:>7}   "
        f"output tokens {c.left_output_tokens:,} vs {c.right_output_tokens:,}"
    )
    return "\n".join(lines)


def render_headline(records: Sequence[dict]) -> str:
    lines = [_heading("baseline vs isomorph, per model")]
    lines.append(
        "The memorisation control. K1-K3 and their solutions are widely published, so a"
    )
    lines.append(
        "low baseline CER does not distinguish cryptanalysis from recall. The isomorphs"
    )
    lines.append("cannot have been memorised. The gap between them is the result.")
    lines.append("")
    for model in sorted(summarise(records).requested_models):
        lines.append(f"{model}")
        lines.append(render_comparison(headline(records, model)))
        lines.append("")
    return "\n".join(lines).rstrip()


def render_axis(records: Sequence[dict], axis: str, left, right, title: str) -> str:
    lines = [_heading(title)]
    tiers = sorted({r.get("tier") for r in records if r.get("tier") is not None})
    for tier in tiers:
        subset = [r for r in records if r.get("tier") == tier]
        comparison = compare(subset, axis, left, right)
        if comparison.pairs == 0:
            continue
        lines.append(f"tier {tier}")
        lines.append(render_comparison(comparison))
        lines.append("")
    if len(lines) == 1:
        lines.append("  no paired results on this axis")
    return "\n".join(lines).rstrip()


def render_cost(records: Sequence[dict]) -> str:
    lines = [_heading("cost and tokens")]
    lines.append(f"{'model':<26} {'input':>12} {'output':>12} {'USD':>10}")
    lines.append("-" * WIDTH)
    rows = cost(records)
    for row in rows:
        usd = f"${row.total_usd:,.2f}" if row.priced else "unpriced"
        lines.append(
            f"{row.model[:26]:<26} {row.input_tokens:>12,} "
            f"{row.output_tokens:>12,} {usd:>10}"
        )
    lines.append("-" * WIDTH)

    priced = [r for r in rows if r.priced]
    total = sum(r.total_usd for r in priced)
    lines.append(f"{'total (priced models)':<26} {'':>12} {'':>12} {f'${total:,.2f}':>10}")
    if len(priced) < len(rows):
        missing = [r.model for r in rows if not r.priced]
        lines.append(f"no price on file for: {', '.join(missing)} -- excluded from the total")
    lines.append("")
    lines.append("List prices as of 2026-08-01, USD per million tokens. Sonnet 5 bills at an")
    lines.append("introductory $2.00/$10.00 through 2026-08-31, so a run made during the")
    lines.append("promotion cost less than shown here; no run costs more.")
    return "\n".join(lines)


def _heading(title: str) -> str:
    return f"\n{title.upper()}\n{'=' * WIDTH}"


def render(records: Sequence[dict], superseded: int, by: Sequence[str]) -> str:
    # A breakdown that pools two models into one row is worse than no breakdown, so the
    # model axis is added whenever the file holds more than one and the caller did not
    # already ask for it.
    keys = list(by)
    if len(summarise(records).requested_models) > 1 and "requested_model" not in keys:
        keys.insert(0, "requested_model")

    sections = [
        _preamble(records, superseded),
        render_breakdown(records, *keys),
        render_headline(records),
        render_axis(
            records, "paradigm", "cot", "tool_use", "chain of thought vs tool use"
        ),
        render_axis(
            records, "delimited", False, True, "raw vs character-delimited ciphertext"
        ),
        render_cost(records),
    ]
    return "\n".join(sections) + "\n"


def _preamble(records: Sequence[dict], superseded: int) -> str:
    totals = summarise(records)
    lines = [
        f"Kryptos benchmark -- {totals.instances} result(s), "
        f"{len(totals.requested_models)} model(s)"
    ]
    if superseded:
        lines.append(
            f"{superseded} earlier record(s) superseded by a later run of the same "
            "instance"
        )
    if totals.refused or totals.errored:
        lines.append(
            f"{totals.refused} refused, {totals.errored} errored -- harness outcomes, "
            "never counted as wrong answers"
        )
    if totals.fell_back:
        lines.append(
            f"WARNING: {totals.fell_back} result(s) were answered by a different model "
            "than the one requested,"
        )
        lines.append(
            "via server-side fallback. They are counted under the model that was asked, "
            "so those"
        )
        lines.append(
            "scores are not that model's. Re-run them before quoting a per-model number."
        )
    return "\n".join(lines)


# --- cli --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("paths", nargs="+", help="results JSONL files (globs accepted)")
    ap.add_argument(
        "--by",
        nargs="+",
        default=["config", "tier", "paradigm"],
        help="fields to break down by; 'family' means baseline vs isomorph",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # Globs are expanded here as well as by the shell, so the same command works on a
    # shell that does not expand them.
    paths: list[str] = []
    for pattern in args.paths:
        paths.extend(sorted(glob.glob(pattern)) or [pattern])

    missing = [p for p in paths if not pathlib.Path(p).exists()]
    if missing:
        raise SystemExit(f"no such results file(s): {', '.join(missing)}")

    records, superseded = deduplicate(load(paths))
    if not records:
        raise SystemExit("no results found")

    print(render(records, superseded, args.by))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
