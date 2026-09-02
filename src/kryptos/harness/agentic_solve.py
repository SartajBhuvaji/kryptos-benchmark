#!/usr/bin/env python3
"""Agentic tool-use arm for kryptos-bench: reason, write code, iterate, submit.

The repo's own ``tool_use`` paradigm is Anthropic-only -- :mod:`kryptos.eval.providers`
raises rather than quietly downgrading it, because "running chain of thought while the
results file says tool_use" would fake the paradigm gap. This is a prototype of the
container backend that docstring anticipates, kept deliberately outside ``providers.py``
until the loop is proven on real rows.

Why the tool calls are parsed here rather than through the OpenAI ``tools`` field
---------------------------------------------------------------------------------
Two reasons, both load-bearing:

1. **Structured output suppresses thinking.** A strict ``json_schema`` constrains
   generation from token 0, so the model cannot emit its ``<think>`` block at all. That
   is exactly why the chain-of-thought arm produced ~150 tokens of confabulation. This
   loop therefore runs *unconstrained* and takes the answer from a fenced block instead.
2. **No parser-name dependency.** vLLM 0.28 ships GLM-4.7-MoE reasoning/tool adapters;
   this model is GLM-4.6, whose tool-call format may differ. Parsing here works whatever
   the server ships.

Isolation, per the run's contamination rules
--------------------------------------------
* **No network egress.** Every code block runs in a fresh network namespace with no
  interfaces, so the sandbox cannot look up a Kryptos solution. Ubuntu 24.04 blocks
  *unprivileged* user namespaces via AppArmor, so ``unshare -rn`` alone does not work;
  the namespace is created with ``sudo unshare -n`` and privileges are then dropped back
  to uid 1000 with ``setpriv`` before the code runs. Chosen over relaxing
  ``kernel.apparmor_restrict_unprivileged_userns``, which would weaken the whole host.
  :func:`check_sandbox_isolation` asserts *both* halves -- that code runs AND that the
  network is unreachable -- and aborts the run otherwise. Checking only that a network
  probe failed would pass trivially on a sandbox that cannot execute anything at all.
* **No shared history.** Each instance builds its message list from scratch.
* **No shared workspace.** Each instance gets its own temp directory, removed afterwards.
  Files persist *within* an instance (so the model can build helper modules) but never
  across instances.

Stopping criteria
-----------------
There is no single convention; the practice is several simultaneous caps with the
protocol reported alongside the score (SWE-Bench Pro caps turns at 50-250;
Terminal-Bench caps wall clock at 10min-3.3h). "How Inference Compute Shapes Frontier
LLM Evaluation" (arXiv 2606.17930) argues a single fixed-budget number understates
capability and that results should be reported *as a function* of inference compute --
hence ``--token-budget`` is a parameter, recorded per instance, meant to be swept.

The agent stops on the first of: it submits an answer; generated tokens exceed the
budget; turns exceed the cap; wall clock exceeds the cap; the conversation outgrows the
context window. Which one fired is recorded in ``stop_reason`` -- a score is not
comparable across different budgets, so the budget travels with it.

Usage (runs ON the GPU instance, talking to vLLM over localhost)::

    python agentic_solve.py --config baseline --instance kryptos-baseline-k1
    python agentic_solve.py --config isomorph_quagmire --limit 1 --token-budget 32000
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

# This module lives at src/kryptos/harness/, so `src` -- the directory that has to
# be importable for `kryptos` to resolve -- is parents[2]. Needed only when the file
# is run as a script from a source checkout; a `pip install -e .` makes it a no-op.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from kryptos.eval import tiers
from kryptos.eval.results import RESULTS_VERSION
from kryptos.scoring import (character_error_rate, index_of_coincidence,
                             letters_only, quadgram_fitness, similarity_ratio)
from kryptos.scoring import tier as tier_lookup

DEFAULT_BASE_URL = "http://localhost:8000/v1"
DEFAULT_MODEL = "GLM-4.6-Flash-text"
DATASET = "sartajbhuvaji/kryptos-bench"

#: Wall-clock cap on a single code block. Long enough for a hill-climb, short enough that
#: an accidental infinite loop costs one turn rather than the whole instance budget.
EXEC_TIMEOUT = 120

#: Generated tokens held back from the budget so the run can always ask for an answer.
#: Without this, exhausting the budget ends the instance with an empty plaintext scored
#: CER 1.0 -- which is indistinguishable from a model that produced pure garbage, and
#: strictly worse than the partial recovery its code had already printed. Real agentic
#: harnesses submit on timeout for the same reason.
FORCE_ANSWER_RESERVE = 4000

#: Address-space cap per code block, in KB. Stops a runaway allocation from swapping the
#: box rather than failing the turn.
EXEC_MEMORY_KB = 4_000_000

CODE_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
ANSWER_RE = re.compile(r"```answer\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)

#: Version of the agentic scaffold, recorded on every result. Agentic scores are
#: scaffold-dependent -- the same model and budget give different numbers under a
#: different loop -- so a score that does not name its scaffold is not reproducible.
SCAFFOLD_VERSION = 4

#: A worked example of the *loop*, replacing the benchmark's own ``FORMAT_EXAMPLE``.
#:
#: This arm calls ``system_prompt(..., few_shot=False)``. The built-in example shows a
#: toy problem going straight to a JSON answer -- right for a single-shot request, and
#: exactly the wrong demonstration here: scaffold v1 reasoned for 10,202 tokens, ran no
#: code at all and submitted on turn one, which is the shape that example teaches.
#:
#: Built on a Caesar shift for the same reason the benchmark's is: every instance in this
#: dataset is Quagmire, transposition, nulls or a composite, so a Caesar demonstration
#: cannot hint at any of them.
AGENT_EXAMPLE = """Here is the shape of one working session, on an unrelated toy problem.

Ciphertext (11 characters): WKHTXLFNIRA

Assistant:

```python
ct = "WKHTXLFNIRA"
for s in range(26):
    print(s, "".join(chr((ord(c) - 65 - s) % 26 + 65) for c in ct))
```

stdout:
    0 WKHTXLFNIRA
    1 VJGSWKEMHQZ
    2 UIFRVJDLGPY
    3 THEQUICKFOX
    ...

Assistant:

```answer
{"cipher": "Caesar shift", "key": "shift 3", "method": "Brute-forced all 26 shifts and printed each; shift 3 was the only one that read as English.", "plaintext": "THEQUICKFOX"}
```

Note what happened: the plaintext was *read out of program output*, not guessed. The
answer block came only after the decryption had actually been run."""


AGENT_GUIDANCE = """
You are working in a loop with a Python 3 sandbox, and you will be asked for an answer
only after you have used it.

## How to act

Every message you send must contain exactly one fenced block:

- To run code:

```python
print("your code here")
```

  Its stdout and stderr come back to you in the next message.

- To finish:

```answer
{"cipher": "...", "key": "...", "method": "...", "plaintext": "..."}
```

## Rules

1. **Your first message must be a ```python``` block.** Not a plan, not an answer. Start
   by measuring the ciphertext: length, letter frequencies, index of coincidence.
2. **Never submit a plaintext you did not read out of program output.** If you find
   yourself typing English your code did not print, stop -- that is a guess, and a fluent
   guess scores worse than a partial real decryption.
3. **Verify before finishing.** Decrypt with your candidate key, print the result, and
   read it. If it does not read as English, something is wrong: go back and rework it.
4. **Round-trip your implementation before you trust it.** Write the *encrypt* direction
   as well, encrypt your candidate plaintext with it, and check you get the original
   ciphertext back character for character. An implementation that does not round-trip is
   wrong no matter how reasonable it looks, and this catches the mistakes that reading the
   code does not -- an off-by-one, a wrong modulus, a lookup and an output that disagree.
   If your decryption is gibberish, suspect your implementation before you suspect the
   key.
5. Do not copy text from the worked example above. It is a different problem.
6. If you run out of ideas, submit the best output your code actually produced. An honest
   partial recovery is worth more than an invented sentence.

## The sandbox

- **No network access.** Nothing can be looked up; everything is derived from the
  ciphertext in front of you.
- Standard library plus numpy.
- Each block is a fresh process, but the working directory persists across your blocks --
  write helper modules to disk and import them if that helps.
- A block is killed after 120 seconds, so keep searches bounded and print progress.

"plaintext" in your answer must be uppercase A-Z, no spaces or punctuation.
"""


@dataclass
class Turn:
    index: int
    kind: str                      # "code" | "answer" | "prose" | "rejected_answer"
    reasoning_chars: int = 0
    #: What the message actually contained, recorded regardless of which branch ran.
    #: v1 stored `code` only on turns already classified as code, so when an answer was
    #: taken it was impossible to tell afterwards whether a code block had also been
    #: present and silently dropped. That ambiguity is what this exists to remove.
    had_code_block: bool = False
    had_answer_block: bool = False
    visible: str = ""
    code: str = ""
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    output_tokens: int = 0
    prompt_tokens: int = 0
    seconds: float = 0.0
    #: "length" means the generation was cut at the per-turn cap mid-thought. Five
    #: consecutive of these is what a too-small cap looks like in the record.
    finish_reason: str = ""


@dataclass
class AgentResult:
    instance_id: str
    config: str
    tier: int
    paradigm: str = "tool_use"
    model: str = DEFAULT_MODEL
    requested_model: str = DEFAULT_MODEL
    provider: str = "openai"
    delimited: bool = False
    effort: str = "unset"

    cipher: str = ""
    key: str = ""
    method: str = ""
    plaintext: str = ""
    refused: bool = False
    refusal_category: str | None = None
    error: str | None = None

    input_tokens: int = 0
    output_tokens: int = 0
    code_executions: int = 0
    resumes: int = 0

    metric: str = ""
    cer: float | None = None
    similarity: float | None = None
    passed: bool | None = None

    # --- agentic protocol, recorded so a score is never read without its budget ---
    stop_reason: str = ""
    turns_used: int = 0
    token_budget: int = 0
    turn_limit: int = 0
    wallclock_limit: int = 0
    wallclock_seconds: float = 0.0
    reasoning_chars: int = 0
    submitted: bool = False
    verified_by_code: bool = False
    #: Whether the answer came from the forced final turn rather than the
    #: model deciding it was done. A forced answer is a weaker claim.
    forced_answer: bool = False
    #: Which scaffold produced this. Agentic scores are scaffold-dependent.
    scaffold_version: int = 0
    #: Diagnostics on the submitted plaintext, reported beside CER and never folded into
    #: it. CER against an English reference rewards fluent invention: the chain-of-thought
    #: arm scored 0.762 on K1 with `IDONTKNOWWHATTHEHELLISGOINGON`, while a real but
    #: wrong decryption scored 0.905. These two separate the cases -- invented English has
    #: English-like fitness and IoC, a failed decryption does not -- so a confabulated
    #: answer is visible in the record rather than flattering the mean.
    answer_fitness: float | None = None
    answer_ioc: float | None = None

    #: Schema version of the SHARED fields, so these records load through
    #: `kryptos.eval.report.load`, which refuses versions it does not recognise rather
    #: than reinterpreting them. The agentic fields above are additive -- every field this
    #: version defines carries its v3 meaning -- so the records are v3 with extras, not a
    #: fourth schema. Without this they parse as version None and `load()` bails.
    version: int = RESULTS_VERSION
    timestamp: str = ""
    transcript: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


#: Create a network namespace as root, then immediately drop back to the unprivileged
#: user before exec'ing anything the model wrote. Ubuntu 24.04's AppArmor blocks the
#: unprivileged `unshare -rn` form.
SANDBOX = ["sudo", "-n", "unshare", "-n",
           "setpriv", "--reuid=1000", "--regid=1000", "--clear-groups"]


def check_sandbox_isolation() -> None:
    """Assert the sandbox both *runs code* and *has no network*. Never degrade silently.

    Both halves matter. A check that only confirmed the network probe failed would also
    pass on a sandbox so broken it cannot execute anything -- which is exactly the state
    `unshare -rn` lands in on this image, and it would have turned every instance into a
    silent zero rather than an obvious failure.
    """
    try:
        runs = subprocess.run([*SANDBOX, "python3", "-c", "print('SANDBOX_OK')"],
                              capture_output=True, timeout=60, text=True)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise SystemExit(f"sandbox unusable ({exc}); refusing to run") from None
    if "SANDBOX_OK" not in runs.stdout:
        raise SystemExit(
            f"sandbox cannot execute code; refusing to run.\n"
            f"  stdout: {runs.stdout.strip()[:200]}\n  stderr: {runs.stderr.strip()[:300]}")

    probe = subprocess.run(
        [*SANDBOX, "python3", "-c",
         "import socket;socket.create_connection(('1.1.1.1',53),2);print('REACHED')"],
        capture_output=True, timeout=60, text=True)
    if probe.returncode == 0 or "REACHED" in probe.stdout:
        raise SystemExit("sandbox reached the network; refusing to run")

    print("sandbox OK -- executes code, egress blocked", file=sys.stderr)


def run_code(code: str, workspace: pathlib.Path) -> tuple[str, str, int]:
    """Execute one block in the instance's workspace, with no network and a time cap."""
    script = workspace / "_block.py"
    script.write_text(code, encoding="utf-8")
    try:
        proc = subprocess.run(
            [*SANDBOX, "bash", "-c",
             f"ulimit -v {EXEC_MEMORY_KB}; exec python3 _block.py"],
            cwd=workspace, capture_output=True, text=True, timeout=EXEC_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "", f"[killed: exceeded {EXEC_TIMEOUT}s]", -1
    return proc.stdout[-8000:], proc.stderr[-4000:], proc.returncode


def chat(messages: list[dict], *, base_url: str, model: str, max_tokens: int,
         temperature: float, reasoning_effort: str | None = None) -> dict:
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": temperature}
    # Sent so this arm pairs with the canonical cot arm, which ran at `effort: high`.
    # report.compare() holds every IDENTITY axis but the one under test fixed, and
    # `effort` is one of them -- mismatch there yields zero pairs and no error. The
    # alternative, re-running cot without reasoning_effort, also meant dropping its
    # few-shot example, which pushed that arm from 6 unparseable responses to 115 of 204.
    # Comparing tool use against a baseline broken that badly would be worse than useless.
    if reasoning_effort:
        body["reasoning_effort"] = reasoning_effort
    req = urllib.request.Request(f"{base_url}/chat/completions",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as fh:
        return json.load(fh)


def solve(row: dict, args) -> AgentResult:
    """Run one instance to a stop condition. Fresh conversation, fresh workspace."""
    tier = args.tier or tiers.default_tier(row)
    # few_shot=False: the benchmark's worked example demonstrates answering in one
    # shot, which is the behaviour this arm exists to avoid. AGENT_EXAMPLE shows the
    # loop instead. The task framing itself (base prompt + tier guidance) is untouched,
    # so this stays comparable to any other run at the same tier.
    system = "\n\n".join([tiers.system_prompt(tier, few_shot=False),
                           AGENT_EXAMPLE, AGENT_GUIDANCE])
    user = tiers.build_prompt(row, tier, delimited=args.delimited)

    result = AgentResult(
        instance_id=row["id"],
        config=row.get("config") or row.get("passage", ""),
        tier=tier,
        model=args.model, requested_model=args.model,
        metric=row.get("scoring_metric", ""),
        token_budget=args.token_budget, turn_limit=args.turn_limit,
        wallclock_limit=args.wallclock_limit,
        scaffold_version=SCAFFOLD_VERSION,
        # What was SENT, so a record never claims a level nothing was told.
        effort=args.reasoning_effort or "unset",
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]
    workspace = pathlib.Path(tempfile.mkdtemp(prefix=f"kryptos-{row['id']}-"))
    started = time.time()
    turns: list[Turn] = []
    turn_rejected = False   # an answer is pushed back at most once
    forced = False          # the final ask has been issued

    try:
        while True:
            elapsed = time.time() - started
            spent = result.output_tokens
            over_budget = spent >= args.token_budget - FORCE_ANSWER_RESERVE
            out_of_turns = len(turns) >= args.turn_limit - 1
            out_of_time = elapsed >= args.wallclock_limit - 120

            # One last turn, spent asking for the best answer it already has, rather than
            # ending with nothing. `forced` is recorded so a forced answer is never read
            # as a voluntary submission.
            if (over_budget or out_of_turns or out_of_time) and not forced:
                forced = True
                result.forced_answer = True
                messages.append({"role": "user", "content":
                    "Budget nearly exhausted -- this is your final turn. Emit your "
                    "```answer``` block now, using the best plaintext your code has "
                    "actually printed so far. Do not start new analysis. If nothing "
                    "decrypted cleanly, submit your closest real output rather than "
                    "inventing text."})

            if spent >= args.token_budget:
                result.stop_reason = "token_budget"; break
            if len(turns) >= args.turn_limit:
                result.stop_reason = "turn_limit"; break
            if elapsed >= args.wallclock_limit:
                result.stop_reason = "wall_clock"; break

            # Never ask for more than the budget has left, so the cap is exact rather
            # than overshot by up to one full generation.
            remaining = args.token_budget - result.output_tokens
            t0 = time.time()
            try:
                completion = chat(messages, base_url=args.base_url, model=args.model,
                                  max_tokens=min(args.max_tokens_per_turn, remaining),
                                  temperature=args.temperature,
                                  reasoning_effort=args.reasoning_effort)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode()[:300]
                # A context overflow is a stop condition, not a harness bug.
                if exc.code == 400 and ("context" in detail or "maximum" in detail):
                    result.stop_reason = "context_limit"; break
                result.error = f"api_error_{exc.code}"; result.stop_reason = "error"; break
            except Exception as exc:
                result.error = f"transport_{type(exc).__name__}"
                result.stop_reason = "error"; break

            usage = completion.get("usage", {})
            choice = completion["choices"][0]
            text = choice["message"].get("content") or ""
            think = "\n".join(THINK_RE.findall(text))
            visible = THINK_RE.sub("", text)

            turn = Turn(index=len(turns), kind="prose",
                        finish_reason=choice.get("finish_reason", "") or "",
                        reasoning_chars=len(think),
                        output_tokens=usage.get("completion_tokens", 0),
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        seconds=time.time() - t0)
            result.output_tokens += turn.output_tokens
            result.input_tokens += turn.prompt_tokens
            result.reasoning_chars += turn.reasoning_chars

            answer = ANSWER_RE.search(visible)
            code = CODE_RE.search(visible)
            turn.had_code_block = code is not None
            turn.had_answer_block = answer is not None
            turn.visible = visible.strip()[:4000]

            # Order by POSITION, not by type. v1 tested `if answer:` first, so a message
            # containing a python block *followed by* an answer block had its code
            # silently discarded -- the model would look like it never used the sandbox.
            if code and (not answer or code.start() < answer.start()):
                answer = None

            if answer:
                # The tool_use paradigm is defined by working the problem with code. An
                # answer with no execution behind it is a chain-of-thought answer wearing
                # the wrong label, so it is pushed back once rather than accepted. This
                # constrains process only -- it says nothing about what the answer is.
                if result.code_executions == 0 and not turn_rejected and not forced:
                    turn_rejected = True
                    turn.kind = "rejected_answer"
                    turns.append(turn)
                    messages.append({"role": "assistant", "content": visible.strip()})
                    messages.append({"role": "user", "content":
                        "You have not run any code yet, so that plaintext was not read "
                        "out of program output. Run the decryption in a ```python``` "
                        "block, print the result, and check it reads as English. Then "
                        "give your ```answer```."})
                    continue

                turn.kind = "answer"
                turns.append(turn)
                try:
                    parsed = json.loads(answer.group(1))
                except json.JSONDecodeError:
                    result.error = "unparsed_response"; result.stop_reason = "error"; break
                result.cipher = str(parsed.get("cipher", ""))
                result.key = str(parsed.get("key", ""))
                result.method = str(parsed.get("method", ""))
                result.plaintext = letters_only(str(parsed.get("plaintext", "")))
                result.submitted = True
                result.stop_reason = "submitted"
                break

            if code:
                turn.kind = "code"
                turn.code = code.group(1)
                turn.stdout, turn.stderr, turn.returncode = run_code(turn.code, workspace)
                result.code_executions += 1
                turns.append(turn)
                remaining_tok = args.token_budget - result.output_tokens
                messages.append({"role": "assistant", "content": visible.strip()})
                messages.append({"role": "user", "content":
                    f"stdout:\n{turn.stdout or '(empty)'}\n\n"
                    f"stderr:\n{turn.stderr or '(empty)'}\n\n"
                    f"(exit {turn.returncode}) Turn {len(turns)}/{args.turn_limit}, "
                    f"~{remaining_tok} generated tokens left. Continue, or give your "
                    f"```answer``` block."})
                continue

            # Neither a code block nor an answer -- nudge once rather than looping.
            turns.append(turn)
            messages.append({"role": "assistant", "content": visible.strip()})
            messages.append({"role": "user", "content":
                "Emit either a ```python``` block to run, or your final ```answer``` "
                "block. Nothing else advances the task."})
    finally:
        shutil.rmtree(workspace, ignore_errors=True)

    result.turns_used = len(turns)
    result.wallclock_seconds = round(time.time() - started, 1)
    result.verified_by_code = result.code_executions > 0 and result.submitted
    result.transcript = [asdict(t) for t in turns] if not args.no_transcript else []

    # Scored by the row, exactly as kryptos.eval.results does, so these numbers sit in
    # the same units as the chain-of-thought arm.
    if result.plaintext:
        result.answer_fitness = quadgram_fitness(result.plaintext)
        result.answer_ioc = index_of_coincidence(result.plaintext)
    if row.get("answer") is not None and result.error is None:
        result.cer = character_error_rate(row["answer"], result.plaintext)
        result.similarity = similarity_ratio(row["answer"], result.plaintext)
        result.passed = tier_lookup(tier).passed(result.cer)
    return result


def load_rows(config: str, instance: str | None, limit: int | None) -> list[dict]:
    from datasets import load_dataset
    rows = [dict(r) for r in load_dataset(DATASET, config, split="test")]
    if instance:
        rows = [r for r in rows if r["id"] == instance]
        if not rows:
            raise SystemExit(f"no instance {instance!r} in {config}")
    return rows[:limit] if limit else rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="baseline")
    ap.add_argument("--instance", help="a single instance id")
    ap.add_argument("--limit", type=int, help="first N instances of the config")
    ap.add_argument("--tier", type=int, help="override the row's default tier")
    ap.add_argument("--delimited", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--temperature", type=float, default=0.6)
    ap.add_argument("--reasoning-effort", default="high",
                    help="sent on every request and recorded as the `effort` axis; must "
                         "match the cot arm being compared against or compare() finds no "
                         "pairs. Pass an empty string to send nothing (records 'unset')")

    ap.add_argument("--token-budget", type=int, default=64000,
                    help="cumulative GENERATED tokens per instance (primary stop)")
    ap.add_argument("--turn-limit", type=int, default=20,
                    help="tool-call turns per instance; catches tight low-token loops")
    ap.add_argument("--wallclock-limit", type=int, default=1200,
                    help="seconds per instance; catches a hung sandbox")
    # Tuned between two observed failures. At 16000 a single degenerate prose turn ate
    # 65% of a 32k budget before the loop could nudge it. At 6000 this model hit the cap
    # on five consecutive turns -- every generation truncated mid-thought -- and never
    # converged. 8000 leaves room for a long think plus a code block without inviting a
    # runaway, and FORCE_ANSWER_RESERVE guarantees a final turn regardless.
    ap.add_argument("--max-tokens-per-turn", type=int, default=8000)

    ap.add_argument("--out", required=True, help="JSONL to append results to")
    ap.add_argument("--no-transcript", action="store_true")
    args = ap.parse_args(argv)

    check_sandbox_isolation()
    rows = load_rows(args.config, args.instance, args.limit)
    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    print(f"{len(rows)} instance(s) | budget {args.token_budget} gen tokens, "
          f"{args.turn_limit} turns, {args.wallclock_limit}s", file=sys.stderr)

    for row in rows:
        print(f"\n=== {row['id']} ===", file=sys.stderr)
        res = solve(row, args)
        with out.open("a", encoding="utf-8") as fh:
            fh.write(res.to_json() + "\n")
        cer = "n/a" if res.cer is None else f"{res.cer:.3f}"
        print(f"  stop={res.stop_reason} turns={res.turns_used} "
              f"code_runs={res.code_executions} out_tok={res.output_tokens} "
              f"{res.wallclock_seconds}s CER={cer}", file=sys.stderr)
        print(f"  plaintext: {res.plaintext[:70]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
