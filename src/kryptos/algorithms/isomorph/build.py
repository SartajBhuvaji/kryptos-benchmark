"""Build the published isomorph snapshot.

Emits one ``<config>/test.jsonl`` per isomorph config under the dataset directory.
Deterministic and re-runnable: ``--check`` rebuilds in memory and compares against the
committed files without writing, so CI can prove the artifacts match their source.

    python -m kryptos.algorithms.isomorph.build --check
    python -m kryptos.algorithms.isomorph.build

The snapshot and the fresh path
-------------------------------
This is the *snapshot* half of decision 3.1b. It exists so two models can be compared on
identical data and so results can be cited. Because it is published, it is contaminated
like any other benchmark the moment it has been public through a training cycle -- which
is why :func:`kryptos.algorithms.isomorph.generate.generate` also runs with no seed at
all, producing instances that have never been published and cannot have been trained on.
The two are the same code path. That equivalence is the whole argument: a fresh run is
comparable with the snapshot because nothing differs but the seed.

:data:`SNAPSHOT_SEED` is therefore load-bearing and must not be changed casually. Changing
it silently replaces every published instance, invalidating any score anyone has reported
against this release.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

if __package__ in (None, ""):  # allow running the file directly
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from kryptos.algorithms.baseline.build import DATASET_DIR
from kryptos.algorithms.isomorph import generate as gen
from kryptos.algorithms.isomorph.schema import CANARY, CONFIGS, SPLIT, Config

#: The published snapshot's seed. Fixed at the date of the first isomorph release.
#: Changing it replaces every published instance -- see the module note.
SNAPSHOT_SEED = 20260731

#: Instances per config. Enough that a per-config score is not dominated by which
#: passages happened to be drawn; small enough that a full Phase 4 matrix -- models x
#: tiers x paradigms x two presentations -- stays affordable. Anyone wanting tighter
#: statistics generates more with a fresh seed rather than needing a bigger snapshot.
INSTANCES_PER_CONFIG = 50


def letters_only(text: str) -> str:
    return "".join(ch for ch in text if ch.isalpha())


def _row(config: Config, instance: gen.Instance) -> dict:
    """Flatten one instance into a published record, in the config's field order."""
    parameters = dict(instance.parameters)

    # Hill's matrix is published row-major and flat, with the block size beside it.
    if "hill_matrix" in parameters:
        parameters["hill_matrix"] = [
            value for row in parameters["hill_matrix"] for value in row
        ]

    row = {
        "id": instance.id,
        "config": config.name,
        "kind": instance.kind,
        "canary": CANARY,
        "seed": SNAPSHOT_SEED,
        "problem": instance.ciphertext,
        "problem_letters_only": letters_only(instance.ciphertext),
        "problem_length": len(instance.ciphertext),
        "solution": instance.solution,
        "answer": instance.answer,
        "answer_readable": instance.answer_readable,
        "cipher_family": instance.cipher_family,
        "cipher_name": instance.cipher_name,
        **{key: parameters[key] for key in config.keys},
        # Exact recovery is what "correct" means. Tier pass marks live in
        # kryptos.scoring.thresholds and are applied by the harness, not baked in here.
        "scoring_metric": "cer",
        "scoring_reference": "answer",
        "scoring_threshold": 0.0,
        "source_works": list(instance.source_works),
        "clause_count": instance.clause_count,
    }

    assert tuple(row) == config.fields, f"{instance.id}: field order drift"
    return row


def build_config(config: Config, count: int = INSTANCES_PER_CONFIG) -> list[dict]:
    instances = gen.generate(config.kind, count, seed=SNAPSHOT_SEED)
    return [_row(config, instance) for instance in instances]


def build() -> dict[str, list[dict]]:
    return {config.name: build_config(config) for config in CONFIGS}


def serialize(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def output_for(config: Config) -> pathlib.Path:
    return DATASET_DIR / config.name / f"{SPLIT}.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="compare against the committed files instead of writing",
    )
    args = ap.parse_args()

    failed = False
    for config in CONFIGS:
        payload = serialize(build_config(config))
        target = output_for(config)

        if args.check:
            if not target.exists():
                print(f"missing {target}", file=sys.stderr)
                failed = True
            elif target.read_text(encoding="utf-8") != payload:
                print(f"{target} is stale; re-run without --check", file=sys.stderr)
                failed = True
            else:
                print(f"  ok  {config.name} matches source")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
        print(f"wrote {target} ({len(payload):,} bytes, {INSTANCES_PER_CONFIG} records)")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
