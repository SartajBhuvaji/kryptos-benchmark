"""Minimal worked example: evaluate a model on the Kryptos benchmark.

Self-contained by design. It imports nothing from the kryptos-benchmark repository, so
it runs as a single file wherever you drop it, and it ships alongside the data on the
Hub. Keeping it small is the point -- the project's real harness has tiers, evaluation
paradigms and persisted results, and none of that belongs in an example.

    pip install anthropic datasets rapidfuzz
    export ANTHROPIC_API_KEY=...        # or: ant auth login

    python example.py                     # all four passages
    python example.py --passages K1 K3    # a subset

Only the dataset's input fields are ever sent to the model. The ground-truth columns
(`solution`, `answer`, `answer_readable`, and the cipher keys) stay on this side of the
wall -- that separation is what the schema's field grouping is for, and `build_prompt`
enforces it rather than trusting the caller to remember.

Scoring here is intentionally the same arithmetic the project uses, so numbers from this
file are comparable with numbers from the harness. `tests/test_scoring.py` in the
repository pins that agreement.
"""

from __future__ import annotations

import argparse
import json
import sys

DATASET = "sartajbhuvaji/kryptos-bench"
CONFIG = "baseline"
SPLIT = "test"

DEFAULT_MODEL = "claude-opus-5"

#: The only columns a solver may see. Mirrors INPUT_FIELDS in the dataset schema.
INPUT_FIELDS = ("problem", "problem_letters_only", "problem_length", "cribs")

SYSTEM_PROMPT = """You are an expert cryptanalyst working on classical ciphers.

You will be given a ciphertext. Recover the plaintext.

Work the problem rather than recalling it. If you recognise the ciphertext, still derive
the answer from the text itself -- state the cipher, the key, and the steps that take the
ciphertext to your plaintext.

Useful starting points: the index of coincidence distinguishes substitution from
transposition (a transposition leaves it at the English norm of about 0.066 and preserves
letter frequencies exactly). For a periodic polyalphabetic cipher, find the period first,
then solve each residue class as a separate monoalphabetic substitution.

Report the plaintext as uppercase A-Z with no spaces or punctuation."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "cipher": {"type": "string", "description": "The cipher you identified, or 'unknown'."},
        "key": {"type": "string", "description": "Keys or parameters recovered, or 'unknown'."},
        "plaintext": {
            "type": "string",
            "description": "Recovered plaintext, uppercase A-Z only, no spaces. "
            "Your best attempt even if you are unsure.",
        },
    },
    "required": ["cipher", "key", "plaintext"],
    "additionalProperties": False,
}


# --- scoring ---------------------------------------------------------------------


def letters_only(text: str) -> str:
    """Uppercase A-Z only. A model may return anything; the metric needs one alphabet."""
    return "".join(ch for ch in text.upper() if "A" <= ch <= "Z")


def levenshtein(a: str, b: str) -> int:
    try:
        from rapidfuzz.distance import Levenshtein
    except ImportError:
        pass
    else:
        return Levenshtein.distance(a, b)

    # Pure-Python fallback so the file runs without rapidfuzz. Two rows only --
    # K2 is 372x372, which is trivial, but there is no reason to hold the full matrix.
    if not a:
        return len(b)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb))
            )
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    """Levenshtein distance normalised by reference length. 0.0 is a perfect break.

    Not clamped to 1.0: a hypothesis longer than the reference can exceed it, and that
    is worth seeing rather than hiding.
    """
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return levenshtein(reference, hypothesis) / len(reference)


def crib_score(cribs: list[dict], hypothesis: str) -> tuple[int, int]:
    """Return (cribs placed at their exact position, cribs present anywhere).

    K4's only ground truth is 24 characters at known offsets, so this is what can
    honestly be measured. Positions are 1-indexed and inclusive.
    """
    exact = sum(1 for c in cribs if hypothesis[c["start"] - 1 : c["end"]] == c["plaintext"])
    anywhere = sum(1 for c in cribs if c["plaintext"] in hypothesis)
    return exact, anywhere


# --- prompt and model call -------------------------------------------------------


def build_prompt(row: dict) -> str:
    """Render a solver-visible prompt. Reads only INPUT_FIELDS -- never ground truth."""
    visible = {k: row[k] for k in INPUT_FIELDS}

    parts = [f"Ciphertext ({visible['problem_length']} characters):", "", visible["problem"], ""]

    if visible["cribs"]:
        parts += ["Confirmed plaintext fragments, at these 1-indexed positions:", ""]
        parts += [f"  {c['plaintext']} at {c['start']}-{c['end']}" for c in visible["cribs"]]
        parts += [
            "",
            "This ciphertext is unsolved. Produce your best hypothesis: propose a "
            "mechanism consistent with the fragments and apply it to the full text.",
            "",
        ]

    parts.append("Recover the plaintext.")
    return "\n".join(parts)


def solve(client, model: str, row: dict) -> dict:
    message = client.messages.create(
        model=model,
        max_tokens=32000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(row)}],
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": ANSWER_SCHEMA}},
    )

    # Check stop_reason before reading content: on a refusal the content array is empty,
    # so indexing it blindly breaks. Cryptanalysis sits close enough to the cyber policy
    # boundary that a benign request is occasionally declined.
    if message.stop_reason == "refusal":
        return {"cipher": "refused", "key": "refused", "plaintext": ""}

    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"cipher": "unparsed", "key": "unparsed", "plaintext": ""}

    parsed["plaintext"] = letters_only(parsed.get("plaintext", ""))
    return parsed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--passages", nargs="+", metavar="K", help="subset, e.g. --passages K1 K3")
    args = ap.parse_args()

    try:
        import anthropic
        from datasets import load_dataset
    except ImportError as exc:
        print(f"missing dependency: {exc.name}\n  pip install anthropic datasets rapidfuzz",
              file=sys.stderr)
        return 1

    rows = [dict(r) for r in load_dataset(DATASET, CONFIG, split=SPLIT)]
    if args.passages:
        wanted = {p.upper() for p in args.passages}
        rows = [r for r in rows if r["passage"] in wanted]
        if not rows:
            print(f"no passages matched {sorted(wanted)}", file=sys.stderr)
            return 1

    client = anthropic.Anthropic()

    print(f"\nKryptos benchmark -- {DATASET} [{CONFIG}/{SPLIT}] -- {args.model}")
    print("=" * 66)

    for row in rows:
        print(f"solving {row['passage']} ({row['problem_length']} chars)...", file=sys.stderr)
        attempt = solve(client, args.model, row)

        if row["scoring_metric"] == "cer":
            cer = character_error_rate(row["answer"], attempt["plaintext"])
            score = f"CER {cer:6.1%}" + ("  SOLVED" if cer == 0.0 else "")
        else:
            exact, anywhere = crib_score(row["cribs"], attempt["plaintext"])
            score = f"{exact}/{len(row['cribs'])} cribs placed, {anywhere} present"

        print(f"{row['passage']:<5} {score:<26} identified as: {attempt['cipher'][:22]}")

    print("=" * 66)
    print("K1-K3 and their solutions are widely published, so a low CER here does not")
    print("distinguish cryptanalysis from recall. Read it as a memorisation baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
