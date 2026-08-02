"""Scoring an attempt, and persisting the result.

**One scoring path, both paradigms.** :func:`score` takes an :class:`~kryptos.eval.
paradigms.Attempt` and never asks which paradigm produced it. That is what makes the
chain-of-thought vs tool-use comparison mean anything: if the two were scored by separate
code, any gap between them could be a difference in the scorer rather than in the model.

What gets scored is chosen by the *row*, not the caller — a row with an answer is scored
by character error rate against it, and a row without one is scored by crib placement and
quadgram fitness together (see :mod:`kryptos.scoring.frontier`). The dataset already
states which applies, in ``scoring_metric``.

Results are persisted per instance rather than printed and discarded. A run is a real
API spend; being unable to re-analyse it without paying again is a bad trade.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from kryptos.eval.paradigms import Attempt
from kryptos.scoring import character_error_rate, similarity_ratio, tier as tier_lookup

#: Schema version for the persisted records. Bumped when a field changes meaning, so an
#: analysis script reading an old file can tell.
RESULTS_VERSION = 1


@dataclass
class Result:
    """One scored attempt, in the shape written to disk."""

    # --- what was run ---
    instance_id: str
    config: str
    tier: int
    paradigm: str
    model: str
    delimited: bool
    effort: str
    seed: int | None = None

    # --- what came back ---
    cipher: str = ""
    key: str = ""
    plaintext: str = ""
    refused: bool = False
    refusal_category: str | None = None
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    code_executions: int = 0
    resumes: int = 0

    # --- how it scored ---
    metric: str = ""
    #: Character error rate, for rows with a reference answer. ``None`` otherwise.
    cer: float | None = None
    #: Symmetric 0-100 similarity, comparable across passages of different length.
    similarity: float | None = None
    #: Whether the tier's pass mark was met. ``None`` when the tier has no pass mark
    #: (tier 4) or when there was nothing to score.
    passed: bool | None = None
    #: Frontier scoring, for rows with no reference answer.
    cribs_placed: int | None = None
    cribs_present: int | None = None
    cribs_total: int | None = None
    fitness: float | None = None
    ioc: float | None = None

    # --- bookkeeping ---
    version: int = RESULTS_VERSION
    timestamp: str = ""
    transcript: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


def score(
    row: dict,
    attempt: Attempt,
    *,
    delimited: bool = False,
    effort: str = "high",
    keep_transcript: bool = True,
) -> Result:
    """Score one attempt against its row. Paradigm-agnostic by construction."""
    result = Result(
        instance_id=attempt.instance_id,
        config=row.get("config") or row.get("passage", ""),
        tier=attempt.tier,
        paradigm=attempt.paradigm,
        model=attempt.model,
        delimited=delimited,
        effort=effort,
        seed=row.get("seed"),
        cipher=attempt.cipher,
        key=attempt.key,
        plaintext=attempt.plaintext,
        refused=attempt.refused,
        refusal_category=attempt.refusal_category,
        error=attempt.error,
        input_tokens=attempt.input_tokens,
        output_tokens=attempt.output_tokens,
        code_executions=attempt.code_executions,
        resumes=attempt.resumes,
        metric=row.get("scoring_metric", ""),
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        transcript=list(attempt.transcript) if keep_transcript else [],
    )

    if not attempt.usable:
        # A refusal or an error is not a wrong answer, and scoring it as CER 1.0 would
        # quietly fold harness failures into the model's score.
        return result

    if row.get("answer") is not None:
        result.cer = character_error_rate(row["answer"], attempt.plaintext)
        result.similarity = similarity_ratio(row["answer"], attempt.plaintext)
        result.passed = tier_lookup(attempt.tier).passed(result.cer)
    else:
        from kryptos.scoring import frontier_score

        frontier = frontier_score(row.get("cribs") or [], attempt.plaintext)
        result.cribs_placed = frontier.cribs_placed
        result.cribs_present = frontier.cribs_present
        result.cribs_total = frontier.cribs_total
        result.fitness = frontier.fitness
        result.ioc = frontier.ioc
        # Tier 4 has no pass mark; `passed` stays None rather than becoming False, so an
        # unscoreable tier is never counted as a failure in an aggregate.
        result.passed = tier_lookup(attempt.tier).passed(0.0)

    return result


def write(results: list[Result], path: str | pathlib.Path) -> pathlib.Path:
    """Append results as JSONL, creating the file and its parent if needed.

    Append rather than overwrite: a run is real API spend, and silently replacing an
    earlier run's records would be an expensive mistake to make twice.
    """
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        for result in results:
            fh.write(result.to_json() + "\n")
    return target


def read(path: str | pathlib.Path) -> list[dict]:
    """Read persisted results back."""
    with pathlib.Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def summarise(results: list[Result]) -> dict[str, Any]:
    """Aggregate a run. Only scoreable attempts count toward the mean."""
    scored = [r for r in results if r.cer is not None]
    refused = [r for r in results if r.refused]
    errored = [r for r in results if r.error]

    return {
        "instances": len(results),
        "scored": len(scored),
        "refused": len(refused),
        "errored": len(errored),
        "solved": sum(1 for r in scored if r.cer == 0.0),
        "passed": sum(1 for r in results if r.passed is True),
        "mean_cer": sum(r.cer for r in scored) / len(scored) if scored else None,
        "mean_similarity": (
            sum(r.similarity for r in scored) / len(scored) if scored else None
        ),
        "input_tokens": sum(r.input_tokens for r in results),
        "output_tokens": sum(r.output_tokens for r in results),
        "code_executions": sum(r.code_executions for r in results),
    }
