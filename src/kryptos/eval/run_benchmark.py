"""Run the Kryptos benchmark against a Claude model and print the results.

Self-contained on purpose: it imports nothing from this repository, so the file can be
dropped into the dataset's HuggingFace repo as a usage example without modification.

    pip install anthropic datasets rapidfuzz
    export ANTHROPIC_API_KEY=...        # or: ant auth login

    python run_benchmark.py                     # all four passages
    python run_benchmark.py --passages K1 K3    # a subset
    python run_benchmark.py --delimited         # space-separate ciphertext characters
    python run_benchmark.py --effort max        # deeper reasoning, more tokens

Only the dataset's input fields are ever sent to the model. The ground-truth columns
(`solution`, `answer`, `answer_readable`, cipher keys) stay on this side of the wall --
that separation is the whole point of the field grouping in the schema, and it is
enforced here in `build_prompt` rather than left to convention.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass

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
        "cipher": {
            "type": "string",
            "description": "The cipher you identified, or 'unknown' if you could not.",
        },
        "key": {
            "type": "string",
            "description": "Keys or parameters recovered, or 'unknown'.",
        },
        "method": {
            "type": "string",
            "description": "How you got from ciphertext to plaintext, in a few sentences.",
        },
        "plaintext": {
            "type": "string",
            "description": "Recovered plaintext, uppercase A-Z only, no spaces. "
            "Your best attempt even if you are unsure.",
        },
    },
    "required": ["cipher", "key", "method", "plaintext"],
    "additionalProperties": False,
}


# --- scoring ---------------------------------------------------------------------


def letters_only(text: str) -> str:
    return "".join(ch for ch in text.upper() if "A" <= ch <= "Z")


def levenshtein(a: str, b: str) -> int:
    try:
        from rapidfuzz.distance import Levenshtein
    except ImportError:
        pass
    else:
        return Levenshtein.distance(a, b)

    # Pure-Python fallback so the script runs without rapidfuzz. Two rows only --
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
    exact = sum(
        1 for c in cribs if hypothesis[c["start"] - 1 : c["end"]] == c["plaintext"]
    )
    anywhere = sum(1 for c in cribs if c["plaintext"] in hypothesis)
    return exact, anywhere


# --- model call ------------------------------------------------------------------


@dataclass
class Attempt:
    passage: str
    cipher: str
    key: str
    plaintext: str
    refused: bool = False
    refusal_category: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0


def build_prompt(row: dict, delimited: bool) -> str:
    """Render a solver-visible prompt. Reads only INPUT_FIELDS -- never ground truth."""
    visible = {k: row[k] for k in INPUT_FIELDS}

    ciphertext = visible["problem"]
    if delimited:
        # The design doc's tokenization mitigation: one token per character, so the
        # model can address individual letters by position instead of guessing at
        # subword boundaries.
        ciphertext = " ".join(ciphertext)

    parts = [
        f"Ciphertext ({visible['problem_length']} characters):",
        "",
        ciphertext,
        "",
    ]

    if visible["cribs"]:
        parts += [
            "Confirmed plaintext fragments, at these 1-indexed positions in the "
            "plaintext:",
            "",
        ]
        parts += [
            f"  {c['plaintext']} at {c['start']}-{c['end']}" for c in visible["cribs"]
        ]
        parts += [
            "",
            "This ciphertext is unsolved. Produce your best hypothesis: propose a "
            "mechanism consistent with the fragments and apply it to the full text.",
            "",
        ]

    parts.append("Recover the plaintext.")
    return "\n".join(parts)


def solve(client, model: str, effort: str, row: dict, delimited: bool) -> Attempt:
    import anthropic

    try:
        with client.beta.messages.stream(
            model=model,
            max_tokens=32000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(row, delimited)}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
            },
            # Cryptanalysis sits close enough to the cyber policy boundary that a
            # benign request is occasionally declined. Server-side fallback re-runs
            # the request on Anthropic's recommended model rather than returning a
            # refusal, so one classifier hit does not void a benchmark run.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            message = stream.get_final_message()
    except anthropic.APIStatusError as exc:
        print(f"  {row['passage']}: API error {exc.status_code} -- {exc.message}",
              file=sys.stderr)
        return Attempt(row["passage"], "error", "error", "")

    usage = message.usage

    # Check stop_reason before reading content: on a refusal the content array is
    # empty (pre-output) or partial (mid-stream), so indexing it blindly breaks.
    if message.stop_reason == "refusal":
        category = getattr(message.stop_details, "category", None)
        return Attempt(
            row["passage"], "refused", "refused", "",
            refused=True, refusal_category=category,
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
        )

    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return Attempt(row["passage"], "unparsed", "unparsed", "",
                       input_tokens=usage.input_tokens,
                       output_tokens=usage.output_tokens)

    return Attempt(
        passage=row["passage"],
        cipher=parsed.get("cipher", ""),
        key=parsed.get("key", ""),
        plaintext=letters_only(parsed.get("plaintext", "")),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )


# --- reporting -------------------------------------------------------------------


def report(rows: list[dict], attempts: list[Attempt], model: str) -> None:
    by_passage = {r["passage"]: r for r in rows}

    print()
    print(f"Kryptos benchmark -- {DATASET} [{CONFIG}/{SPLIT}] -- {model}")
    print("=" * 78)
    print(f"{'passage':<8} {'metric':<11} {'score':<22} {'cipher identified':<24}")
    print("-" * 78)

    scored, total_cer = 0, 0.0
    for a in attempts:
        row = by_passage[a.passage]

        if a.refused:
            score = f"refused ({a.refusal_category or 'uncategorised'})"
        elif row["scoring_metric"] == "cer":
            cer = character_error_rate(row["answer"], a.plaintext)
            scored += 1
            total_cer += cer
            verdict = "SOLVED" if cer == 0.0 else ("close" if cer < 0.15 else "")
            score = f"CER {cer:6.1%}  {verdict}"
        else:
            exact, anywhere = crib_score(row["cribs"], a.plaintext)
            score = f"{exact}/{len(row['cribs'])} placed, {anywhere} present"

        print(f"{a.passage:<8} {row['scoring_metric']:<11} {score:<22} {a.cipher[:24]:<24}")

    print("-" * 78)
    if scored:
        print(f"mean CER over {scored} scoreable passage(s): {total_cer / scored:.1%}")
    tokens_in = sum(a.input_tokens for a in attempts)
    tokens_out = sum(a.output_tokens for a in attempts)
    print(f"tokens: {tokens_in:,} in / {tokens_out:,} out")

    print()
    print("K1-K3 and their solutions are widely published, so a low CER here does not")
    print("distinguish cryptanalysis from recall. Read it as a memorisation baseline.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--effort", default="high",
                    choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--passages", nargs="+", metavar="K",
                    help="subset to run, e.g. --passages K1 K3")
    ap.add_argument("--delimited", action="store_true",
                    help="space-separate ciphertext characters (tokenization mitigation)")
    args = ap.parse_args()

    try:
        import anthropic  # noqa: F401
        from datasets import load_dataset
    except ImportError as exc:
        print(f"missing dependency: {exc.name}\n"
              f"  pip install anthropic datasets rapidfuzz", file=sys.stderr)
        return 1

    import anthropic

    if not os.environ.get("ANTHROPIC_API_KEY"):
        # Not fatal: the SDK also resolves an `ant auth login` profile.
        print("note: ANTHROPIC_API_KEY unset; falling back to a stored auth profile",
              file=sys.stderr)

    ds = load_dataset(DATASET, CONFIG, split=SPLIT)
    rows = [dict(r) for r in ds]
    if args.passages:
        wanted = {p.upper() for p in args.passages}
        rows = [r for r in rows if r["passage"] in wanted]
        if not rows:
            print(f"no passages matched {sorted(wanted)}", file=sys.stderr)
            return 1

    client = anthropic.Anthropic()

    attempts = []
    for row in rows:
        print(f"solving {row['passage']} ({row['problem_length']} chars)...",
              file=sys.stderr)
        attempts.append(solve(client, args.model, args.effort, row, args.delimited))

    report(rows, attempts, args.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
