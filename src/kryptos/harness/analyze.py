#!/usr/bin/env python3
"""Aggregate a finished run into charts, a metadata block and SUMMARY.md.

**This executes the notebook's own analysis cells rather than reimplementing them.**
That property is the point and is worth preserving: if this script grew its own copy of
the charting and summary logic, the artifacts committed next to a run could drift from
what someone gets by opening the notebook and running it, and the divergence would show
up as two different numbers for the same run with no way to tell which was current.
Cells are selected by their leading `# --- <name>` comment, so the notebook stays the
single source of truth for how a result is presented.

    python src/kryptos/harness/analyze.py --results GLM-4.6-Flash-text/results \\
                                          --wall-clock 619

Writes into the results directory: cer_by_config.png, outcome_mix.png,
run_metadata.json, SUMMARY.md. Reads gpu_env.json from there if present, so the machine
the run happened on travels with the score.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from collections import Counter

DEFAULT_NOTEBOOK = "notebooks/glm-4.6-flash-text/kryptos_bench_glm46_flash_text.ipynb"

#: Cells to run, in order, matched on the leading comment of each. Anything not listed
#: here (configuration, the endpoint check, the run itself) is skipped -- this script
#: analyses an existing run and never issues a request.
CELL_PREFIXES = (
    "# --- the headline",
    "# --- chart setup",
    "# --- chart 1",
    "# --- chart 2",
    "# --- failure audit",
    "# --- provenance",
    "# --- SUMMARY.md",
)


def find_repo_root(start: pathlib.Path) -> pathlib.Path:
    """Walk up for pyproject.toml.

    Counting `.parent` hops would break the moment this file moves -- which it already
    has once, from notebooks/ into the package.
    """
    here = start.resolve()
    for candidate in (here, *here.parents):
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise SystemExit(f"no pyproject.toml above {start}; run from inside the repo")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--results", required=True,
                    help="directory of per-config .jsonl files to aggregate")
    ap.add_argument("--wall-clock", type=float, default=0.0,
                    help="seconds the run took, for the throughput and cost figures")
    ap.add_argument("--model", default="GLM-4.6-Flash-text", help="served model name")
    ap.add_argument("--hf-model", default="sartajbhuvaji/GLM-4.6-Flash-text")
    ap.add_argument("--notebook", help=f"override the notebook path (default {DEFAULT_NOTEBOOK})")
    ap.add_argument("--concurrency", type=int, default=24,
                    help="recorded in the metadata block, not used to compute anything")
    ap.add_argument("--max-tokens", type=int, default=8192)
    ap.add_argument("--usd-per-hour", type=float, default=1.99)
    ap.add_argument("--no-reasoning-effort", action="store_true",
                    help="record that no reasoning_effort was sent on this run")
    args = ap.parse_args(argv)

    repo = find_repo_root(pathlib.Path(__file__))
    sys.path.insert(0, str(repo / "src"))

    results = pathlib.Path(args.results)
    if not results.is_absolute():
        results = (repo / results).resolve()
    if not results.is_dir():
        raise SystemExit(f"no such results directory: {results}")

    notebook = pathlib.Path(args.notebook) if args.notebook else repo / DEFAULT_NOTEBOOK
    if not notebook.is_file():
        raise SystemExit(f"no notebook at {notebook}")

    import matplotlib
    matplotlib.use("Agg")          # no display on a headless box

    from kryptos.eval import report as reporting, results as results_mod

    cells = json.loads(notebook.read_text(encoding="utf-8"))["cells"]
    sources = ["".join(c["source"]) for c in cells if c["cell_type"] == "code"]

    paths = sorted(results.glob("*.jsonl"))
    if not paths:
        raise SystemExit(f"no .jsonl files in {results}")
    records = reporting.load(paths)
    records, duplicates = reporting.deduplicate(records)
    summary = reporting.summarise(records)
    print(f"loaded {len(records)} records from {len(paths)} file(s)"
          + (f" ({duplicates} duplicate(s) dropped)" if duplicates else ""))

    # The namespace the notebook's cells expect. Assembled explicitly rather than by
    # running the notebook's own configuration cell, because that one also resolves the
    # endpoint and installs dependencies.
    namespace = {
        "__name__": "__analysis__",
        "json": json, "pathlib": pathlib, "sys": sys, "Counter": Counter,
        "reporting": reporting, "results_mod": results_mod,
        "MODEL": args.model, "HF_MODEL": args.hf_model,
        "REPO": repo, "RESULTS": results,
        "CONFIGS": ["baseline", "isomorph_quagmire", "isomorph_transposition",
                    "isomorph_composite", "isomorph_nulls"],
        "MAX_TOKENS": args.max_tokens,
        "CONCURRENCY": args.concurrency,
        "REASONING_EFFORT": not args.no_reasoning_effort,
        "A100_USD_PER_HOUR": args.usd_per_hour,
        "WALL_CLOCK": args.wall_clock,
        "timings": {},
        "records": records, "summary": summary,
    }

    ran = 0
    for source in sources:
        stripped = source.lstrip()
        if not stripped.startswith(CELL_PREFIXES):
            continue
        label = stripped.splitlines()[0][:60]
        try:
            exec(compile(source, label, "exec"), namespace)
        except Exception as exc:
            print(f"\nFAILED in cell {label!r}: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            raise
        ran += 1

    if ran != len(CELL_PREFIXES):
        print(f"\nwarning: ran {ran} of {len(CELL_PREFIXES)} expected cells -- the "
              f"notebook's cell comments may have been renamed", file=sys.stderr)

    print(f"\nwrote into {results}:")
    for name in ("cer_by_config.png", "outcome_mix.png", "run_metadata.json", "SUMMARY.md"):
        target = results / name
        if target.exists():
            print(f"  {name:<22}{target.stat().st_size:>9,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
