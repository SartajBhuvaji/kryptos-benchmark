#!/usr/bin/env python3
"""Compare the chain-of-thought and tool-use arms, and flag confabulated answers.

Two things this exists to get right, both of which are easy to get silently wrong.

**Pairing.** :func:`kryptos.eval.report.compare` pairs instances that appear on *both*
sides of the axis under test, holding every other IDENTITY axis fixed -- and ``effort`` is
one of those axes. The canonical cot arm ran at ``effort: high``; the agentic arm sends no
``reasoning_effort`` at all and honestly records ``unset``. Pointing this at those two
directories yields **zero pairs and no error**, which reads exactly like "no difference".
So the default cot directory here is the *matched* one, and a zero-pair result is reported
as a failure rather than printed as a finding.

**Confabulation.** CER is computed against an English reference, so fluent invented
English scores better than a real but wrong decryption -- on K1 the cot arm's
``IDONTKNOWWHATTHEHELLISGOINGON`` scored 0.762 while a genuine failed decryption scored
0.905. Ranking arms on CER alone would therefore reward bluffing. Quadgram fitness
separates the two cleanly, so it is reported alongside and never folded in.

    python -m kryptos.harness.compare_arms \\
        --cot GLM-4.6-Flash-text/results-cot-nofewshot \\
        --agentic GLM-4.6-Flash-text/results-agentic
"""

from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from kryptos.eval import report as reporting
from kryptos.scoring import quadgram_fitness

#: Above this, a submitted plaintext reads like English. A correct decryption and an
#: invented English sentence both sit near -4; a failed decryption sits near -7.5. So this
#: does not separate right from wrong -- it separates *English* from *not English*, which
#: is what makes a high-fitness wrong answer worth flagging.
ENGLISH_FITNESS = -6.0


def load_dir(path: pathlib.Path) -> list[dict]:
    files = sorted(path.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"no .jsonl files in {path}")
    records, dropped = reporting.deduplicate(reporting.load(files))
    if dropped:
        print(f"  {path.name}: {dropped} superseded record(s) dropped", file=sys.stderr)
    return records


def describe(label: str, records: list[dict]) -> None:
    s = reporting.summarise(records)
    cer = "n/a" if s.mean_cer is None else f"{s.mean_cer:.4f}"
    ci = "" if s.cer_ci95 is None else f" +/-{s.cer_ci95:.4f}"
    print(f"{label:<28} n={s.instances:<4} scored={s.scored:<4} "
          f"CER {cer}{ci}  solved={s.solved} passed={s.passed} "
          f"refused={s.refused} errored={s.errored}")


def confabulation_report(records: list[dict]) -> None:
    """Answers that read as English but are wrong -- the cases CER flatters."""
    rows = []
    for r in records:
        text = r.get("plaintext") or ""
        if not text or r.get("cer") is None:
            continue
        fitness = r.get("answer_fitness")
        if fitness is None:                      # cot records carry no diagnostic
            fitness = quadgram_fitness(text)
        rows.append((r, fitness))
    if not rows:
        return

    fluent_wrong = [(r, f) for r, f in rows if f > ENGLISH_FITNESS and r["cer"] > 0.3]
    mean_fit = sum(f for _, f in rows) / len(rows)
    print(f"  mean quadgram fitness {mean_fit:+.2f} over {len(rows)} answer(s)")
    print(f"  reads as English but wrong (fitness > {ENGLISH_FITNESS}, CER > 0.3): "
          f"{len(fluent_wrong)}/{len(rows)}")
    for r, f in sorted(fluent_wrong, key=lambda x: -x[1])[:5]:
        print(f"    {r['instance_id']:<34} CER {r['cer']:.3f}  fitness {f:+.2f}  "
              f"{r['plaintext'][:40]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cot", type=pathlib.Path, required=True,
                    help="the MATCHED cot results dir (no few-shot, effort unset)")
    ap.add_argument("--agentic", type=pathlib.Path, required=True)
    ap.add_argument("--model", default="GLM-4.6-Flash-text")
    args = ap.parse_args(argv)

    cot, agentic = load_dir(args.cot), load_dir(args.agentic)

    print("\n=== arms ===")
    describe("cot (matched)", cot)
    describe("tool_use (agentic)", agentic)

    print("\n=== agentic protocol ===")
    if agentic:
        stops: dict[str, int] = {}
        for r in agentic:
            stops[r.get("stop_reason", "?")] = stops.get(r.get("stop_reason", "?"), 0) + 1
        print("  stop reasons:", ", ".join(f"{k}={v}" for k, v in sorted(stops.items())))
        used = [r for r in agentic if r.get("code_executions", 0) > 0]
        verified = [r for r in agentic if r.get("verified_by_code")]
        budgets = {r.get("token_budget") for r in agentic}
        scaffolds = {r.get("scaffold_version") for r in agentic}
        print(f"  ran code: {len(used)}/{len(agentic)}   "
              f"answered after running code: {len(verified)}/{len(agentic)}")
        print(f"  token budget(s): {sorted(b for b in budgets if b)}   "
              f"scaffold version(s): {sorted(v for v in scaffolds if v)}")
        if len(budgets) > 1:
            print("  NOTE: mixed budgets -- a score is not comparable across them; "
                  "group before quoting a mean")

    print("\n=== confabulation check ===")
    print(" cot:")
    confabulation_report(cot)
    print(" agentic:")
    confabulation_report(agentic)

    print("\n=== paradigm comparison ===")
    both = cot + agentic
    comparison = reporting.compare(both, "paradigm", "cot", "tool_use")
    if comparison.pairs == 0:
        print("  ZERO PAIRS -- these arms do not pair, so there is no comparison to make.")
        print("  compare() holds every IDENTITY axis but 'paradigm' fixed, so check that")
        print("  tier, delimited and effort agree across the two directories. The usual")
        print("  cause is pointing --cot at the canonical arm (effort 'high') instead of")
        print("  the matched one (effort 'unset').")
        for label, recs in (("cot", cot), ("agentic", agentic)):
            print(f"    {label:<9} effort={sorted({r.get('effort') for r in recs})} "
                  f"tiers={sorted({r.get('tier') for r in recs})} "
                  f"delimited={sorted({r.get('delimited') for r in recs})}")
        return 1

    left = "n/a" if comparison.left_cer is None else f"{comparison.left_cer:.4f}"
    right = "n/a" if comparison.right_cer is None else f"{comparison.right_cer:.4f}"
    print(f"  paired on {comparison.pairs} instance(s); {comparison.unpaired} unpaired")
    print(f"  cot      CER {left}   solved {comparison.left_solved}   "
          f"{comparison.left_output_tokens:,} output tokens")
    print(f"  tool_use CER {right}   solved {comparison.right_solved}   "
          f"{comparison.right_output_tokens:,} output tokens")
    if comparison.cer_gap is not None:
        print(f"  gap {comparison.cer_gap:+.4f}  (negative => cot scored lower error)")
        print("  Read this next to the confabulation check above: a cot arm can win on CER")
        print("  by inventing fluent English, which is not the same as solving more.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
