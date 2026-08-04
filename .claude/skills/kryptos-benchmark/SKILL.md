---
name: kryptos-benchmark
description: Run the Kryptos cryptanalysis benchmark against a model and report scores and cost. Use when asked to benchmark, evaluate, or score a model on Kryptos, to run a cryptanalysis eval, to compare models on this benchmark, or to re-report an existing runs/*.jsonl file. Handles any Claude model or any OpenAI-compatible endpoint (OpenAI, vLLM, OpenRouter, Together, a local runtime).
---

# Running the Kryptos benchmark

This benchmark measures whether a model can actually break classical ciphers or is
reciting Kryptos from memory. K1–K4 and their solutions are all over the internet; the
isomorph configs are synthetic ciphers with the same structure and novel plaintexts, so
they cannot have been memorised. **The gap between a model's baseline score and its
isomorph score is the result.** A run that reports only one of those two numbers has not
measured anything.

Work through the four steps below in order. Do not skip step 3 — it is the one that stops
someone spending real money on a misconfigured sweep.

---

## Step 1 — Establish provider, model, and key

Ask for these together if they were not given. Never accept an API key as a command-line
argument or write one into a file: it would land in shell history and be visible to
anything that can list processes. Keys are read from the environment only.

| Provider | Flag | Key env var | Install |
|---|---|---|---|
| Claude | *(default)* | `ANTHROPIC_API_KEY` | `pip install -e ".[eval]"` |
| OpenAI-compatible | `--provider openai` | `OPENAI_API_KEY` | `pip install -e ".[openai]"` |

For anything that is not OpenAI itself, add `--base-url` (vLLM, OpenRouter, Together, a
local runtime). Use `--api-key-env VAR` when the key lives under a different name.

Tell the user to set the key themselves rather than asking them to paste it:

```
export ANTHROPIC_API_KEY=sk-ant-...        # or OPENAI_API_KEY
```

**Two constraints to state up front, before they pick a model:**

- **`--paradigm tool_use` is Claude-only.** It needs a server-side sandbox the OpenAI wire
  format has no equivalent for. The runner refuses rather than silently running
  chain-of-thought and labelling it tool use.
- **Haiku 4.5 will not run.** It rejects `output_config.effort` and adaptive thinking. Any
  Claude 4.6-or-newer model works.

---

## Step 2 — Interview for the run parameters

Offer these as menus with the default marked. Do not ask open-endedly; most people do not
know the axes yet. If the user says "just run it", take every default.

**1. Which data?** (`--config`)

| Option | What it measures |
|---|---|
| `baseline` | The four real Kryptos passages. Memorisation control |
| `isomorph_quagmire` | Synthetic Quagmire III — the K1/K2 cipher, novel plaintext |
| `isomorph_transposition` | Synthetic route transposition — the K3 cipher |
| `isomorph_composite` | Vigenère→Hill, a multi-layer K4 proxy |
| `isomorph_nulls` | Quagmire with positional nulls inserted |
| **all five** *(default)* | The headline comparison needs baseline **and** at least one isomorph |

**2. How many instances each?** (`--limit`)

| Option | Use when |
|---|---|
| **5** *(default)* | Sizing a run. Enough for cost-per-instance, not for a quotable score |
| 20 | A real signal per config |
| omit (all 50) | The full published set |

**3. Task framing?** (`--tier`) Default: omit, and each row is posed at its natural tier.

| Tier | Given to the model | Tests |
|---|---|---|
| 1 | Ciphertext **and the keys** | Can it execute the algorithm |
| 2 | Ciphertext and cipher type | Can it recover the key |
| 3 | Ciphertext only | Can it identify and break |
| 4 | K4 — unsolved, no answer exists | Scored on crib placement + English-likeness |

**4. Reasoning paradigm?** (`--paradigm`) Default `cot`. `tool_use` gives Claude a Python
sandbox; the gap between them is itself a publishable result.

**5. Effort?** (`--effort`) Default `high`. `low`/`medium` cut cost substantially. On
OpenAI, `xhigh` and `max` both collapse to `high` — the recorded value says what was sent.

**6. Anything else worth offering:**
- `--delimited` — space out ciphertext characters, testing the tokenization hypothesis
- `--concurrency 4` — recommend this whenever `--limit` is above ~5
- `--no-few-shot` — drop the worked format example

---

## Step 3 — Price it before running it

**Always do this, and always show the number before spending anything.**

Non-Claude models have no rates on file. Without `--price` the cost table reports
`unpriced` and `--max-spend` refuses to run rather than guess — that is deliberate, not a
bug. Ask the user for the model's published rates and pass them:

```
--price gpt-5=1.25/10          # USD per million tokens, input/output
```

Then run one config at `--limit 2` first, read the actual cost per instance out of the
report, multiply by the planned instance count, and show the user that figure. Prompts are
~1,600 characters, so input cost is negligible; **output tokens dominate and vary by an
order of magnitude with effort**, which is exactly why extrapolating from a real 2-instance
probe beats estimating.

Always pass a ceiling on the real run:

```
--max-spend 5.00
```

It is soft by up to `--concurrency` instances, because work already in flight finishes.
Set it below what the user is actually willing to spend.

---

## Step 4 — Run, then report

```bash
python -m kryptos.eval.run_benchmark \
    --model MODEL --config CONFIG --limit 5 \
    --concurrency 4 --max-spend 5.00 --resume \
    --out runs/MODEL.jsonl
```

Run once per config, all writing to the **same** `--out` file so the report can compare
them. Always pass `--resume`: it skips instances already answered and retries refusals and
errors, so an interrupted run continues instead of restarting. Interrupting with Ctrl-C is
safe — completed work is written.

Then aggregate:

```bash
python -m kryptos.eval.report runs/MODEL.jsonl
python -m kryptos.eval.report runs/*.jsonl --by requested_model config   # several models
```

### Presenting the results

Report these five things, in this order. This mirrors how established LLM benchmarks
present scores, with one addition this benchmark needs — the memorisation gap.

1. **Headline: baseline vs isomorph CER, per model.** The whole point. Quote both.
2. **Per-config breakdown** with n, mean CER, and the 95% CI.
3. **Solve rate** — instances at CER 0.0. A partial decryption is not a break.
4. **Refusals and errors, stated separately and excluded from every mean.** They are
   harness outcomes, never wrong answers.
5. **Cost and tokens**, with cost per instance.

A usable shape:

```markdown
| Config                 |  n | mean CER | 95% CI | solved | refused |
|------------------------|---:|---------:|-------:|-------:|--------:|
| baseline               |  4 |    12.0% | ±8.1%  |    2/4 |       0 |
| isomorph_quagmire      |  5 |    94.2% | ±3.4%  |    0/5 |       0 |

**Memorisation gap: 82.2 points.** Solves 2 of 4 published passages, 0 of 5
structurally identical synthetic ones. Cost: $1.24 ($0.14/instance).
```

### Four things not to say

**Do not call a low baseline score cryptanalysis.** K1–K3 and their plaintexts are
published. A model scoring well there and badly on isomorphs has demonstrated recall, and
that is the finding — say so.

**Do not quote a gap whose confidence intervals overlap.** The report prints
`intervals overlap -- not a distinguishable gap` when they do. At `--limit 5` they usually
will. Report it as "no measurable difference at this sample size", not as a result.

**Do not average across metric families.** Tiers 1–3 score by character error rate; tier 4
(K4) scores by crib placement and quadgram fitness. Different scales, no common zero. The
report keeps them apart; keep them apart in prose too.

**Do not count a refusal as a wrong answer.** Report it as a harness outcome.

### If something looks wrong

| Symptom | Cause |
|---|---|
| `unpriced` in the cost table | Non-Claude model with no `--price` |
| Ceiling reached immediately | Same — an unpriced model halts rather than running uncapped |
| `results version [N] != M` | The file predates a schema change; re-run, don't reinterpret |
| Every instance `refused` | A safety classifier; Claude runs retry via server-side fallback |
| `api_error_400` on OpenAI | The server rejected a field — try `--no-reasoning-effort`, or `--provider-param max_completion_tokens=32000` for reasoning models |
| Effort reads `unset` | `--no-reasoning-effort` was passed; the record is truthful about it |

---

## Portability

This file is plain Markdown with YAML frontmatter. Claude Code discovers it here
automatically. For Cursor or another harness, point the agent at this path or copy it to
that tool's rules directory — nothing in it depends on a particular runtime.
