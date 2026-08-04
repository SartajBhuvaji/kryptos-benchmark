# Kryptos Benchmark

Evaluating large language models on classical cryptanalysis and character-level reasoning,
modelled on the Kryptos sculpture at CIA headquarters.

Testing a model directly on Kryptos measures memorisation, not cryptanalysis: K1–K3 and
their solutions are extensively documented and are certainly in every frontier model's
pre-training data. The project's answer is to generate **Kryptos-isomorphic** challenges —
the same algorithms, matrix transformations and constraints applied to novel plaintexts
under randomised keys — and to use the authentic passages as a memorisation control rather
than as the measurement.

**The gap between a model's baseline score and its isomorph score is the result.** A model
that solves K1 and fails every Quagmire isomorph has told you something specific.

Dataset: [`sartajbhuvaji/kryptos-bench`](https://huggingface.co/datasets/sartajbhuvaji/kryptos-bench)
· 204 instances across five configs, `test` split.

## Status

The benchmark is complete and runnable end to end — 676 tests, five published configs, both
paradigms, two providers, and every comparison available from one command.

**No model has been run against it yet.** The harness measures; it has not yet measured.
That is the remaining work, and two things stay open until it happens: the tier pass marks
are asserted rather than calibrated against an observed score distribution, and the cost of
the full matrix is an estimate rather than a receipt. Nothing in this repository reports a
model's score, and no leaderboard exists.

| component | state |
|---|---|
| baseline dataset | four authentic passages, verified five ways and round-tripped |
| cipher implementations | Quagmire III, route transposition, Vigenère, Hill |
| isomorph generators | four, one per cipher — 200 published instances |
| scoring | CER, similarity, crib placement, quadgram fitness, IoC |
| tier framings | four, from executing a given algorithm to K4 |
| evaluation paradigms | chain of thought and server-side code execution |
| providers | Claude, plus any OpenAI-compatible endpoint |
| reporting | breakdowns, 95% CIs, paired comparisons, cost accounting |

## Quickstart

Python 3.11+. The package itself has no runtime dependencies; running a model needs one of
the two provider extras.

```bash
git clone https://github.com/SartajBhuvaji/kryptos-benchmark
cd kryptos-benchmark
pip install -e ".[eval]"                # Claude
pip install -e ".[openai]"              # OpenAI-compatible endpoints
```

Keys are read from the environment and are never accepted as a command-line argument — an
argument lands in shell history and is visible to anything that can list processes.

```bash
export ANTHROPIC_API_KEY=sk-ant-...     # or OPENAI_API_KEY
```

**Benchmark a Claude model:**

```bash
python -m kryptos.eval.run_benchmark --model claude-sonnet-5 \
    --config isomorph_quagmire --limit 5
```

**Benchmark anything speaking the OpenAI wire format** — OpenAI itself, vLLM, OpenRouter,
Together, a local runtime:

```bash
python -m kryptos.eval.run_benchmark --provider openai --model gpt-5 \
    --base-url https://openrouter.ai/api/v1 --api-key-env OPENROUTER_KEY \
    --price gpt-5=1.25/10 \
    --config isomorph_quagmire --limit 5
```

`--base-url` is optional for OpenAI itself. `--price MODEL=IN/OUT` gives USD per million
tokens; only Anthropic's published rates are on file, and a model with no rate is reported
as `unpriced` rather than as free.

Both then aggregate the same way:

```bash
python -m kryptos.eval.report runs/*.jsonl
```

### What comes back

Per-instance results append to `runs/<config>.jsonl`, so a run can be re-analysed without
paying for it again. `kryptos.eval.report` turns those records into the comparisons the
benchmark exists to make:

```
                    the numbers below are illustrative, not measured — see Status

BY CONFIG / TIER
==============================================================================
group                       n      CER     95% CI  solved  passed   cribs     fit
------------------------------------------------------------------------------
K1 2                        1     0.0%         --     1/1       1      --      --
K3 3                        1    19.0%         --     0/1       0      --      --
K4 4                        1       --         --      --      --   1.0/4   -4.91
isomorph_quagmire 2         5    90.5%    +/-2.8%     0/5       0      --      --
isomorph_transposition 3    5    79.0%    +/-4.8%     0/5       0      --      --

BASELINE VS ISOMORPH, PER MODEL
==============================================================================
The memorisation control. K1-K3 and their solutions are widely published, so a
low baseline CER does not distinguish cryptanalysis from recall. The isomorphs
cannot have been memorised. The gap between them is the result.

claude-sonnet-5
  baseline vs isomorph
    unpaired -- different instances by construction
    mean CER      6.3%  vs   84.7%   gap -78.4%
    95% CI     +/-12.4%  vs +/- 4.6%   intervals separate
    solved           2  vs       0   output tokens 39,200 vs 151,500

COST AND TOKENS
==============================================================================
model                             input       output        USD
------------------------------------------------------------------------------
claude-sonnet-5-20260115          7,280      190,700      $2.88
```

Every mean carries a 95% confidence interval, and every comparison states in words whether
the two intervals overlap. That matters more here than in most benchmarks because the
headline result *is* a difference between two means: at `--limit 5` a few points of gap is
almost always noise. A bare `+4.2%` gets quoted; `intervals overlap -- not a
distinguishable gap` does not.

## Benchmarking your own model

### Size the run before committing to it

The full matrix is 5 configs × 4 tiers × 2 paradigms × 2 presentations at 50 instances per
isomorph config — real API spend. Prompts are small (~1,600 characters), so **output tokens
dominate and vary by an order of magnitude with reasoning effort.** Run two instances
first, read the actual cost per instance out of the report, and multiply:

```bash
python -m kryptos.eval.run_benchmark --model MODEL --config isomorph_quagmire --limit 2
```

### Then run it for real

```bash
python -m kryptos.eval.run_benchmark \
    --model MODEL --config isomorph_quagmire --limit 20 \
    --concurrency 4 --max-spend 5.00 --resume \
    --out runs/MODEL.jsonl
```

Run once per config, all writing to the **same** `--out` file, so the report can compare
them.

| flag | why |
|---|---|
| `--resume` | Skips instances already answered; **retries refusals and errors** rather than cementing them. An interrupted run continues instead of restarting |
| `--concurrency N` | Instances in flight at once. Worth setting above ~5 instances |
| `--max-spend USD` | Stops dispatching at the ceiling. Soft by up to `--concurrency` instances, because work in flight finishes — set it below what you are willing to spend |
| `--price M=IN/OUT` | USD per million tokens for a model with no published rate on file |
| `--limit N` | First N instances |

Ctrl-C is safe: completed work is written, and `--resume` picks it up.

**Runs are bounded by instance count, not by a clock.** Stopping on a timer cuts each
config at an arbitrary point, so the baseline and isomorph means would cover
different-sized samples — the exact comparison the reporting layer refuses to make
everywhere else. This follows what eval harnesses standardise on: a fixed instance set plus
resumability.

### Two limits, enforced rather than papered over

**`--paradigm tool_use` is Claude-only.** It needs a server-side sandbox the OpenAI wire
format has no equivalent for, so the runner refuses instead of quietly running
chain-of-thought and labelling it tool use — a mislabelled run would land as a headline
finding that the tool-use gap had closed.

**Effort recorded is effort sent.** The OpenAI ladder collapses `xhigh`/`max` to `high`,
and `--no-reasoning-effort` drops the field entirely for servers that reject it; the record
then reads `unset` rather than echoing back a level nothing was told about.

Anything else a particular server needs goes through `--provider-param k=v`, repeatable and
JSON-decoded — `max_completion_tokens=32000` for OpenAI's own reasoning models, for
instance.

**Haiku 4.5 will not run.** It rejects `output_config.effort` and adaptive thinking; any
Claude 4.6-or-newer model works.

## The dataset

| config | instances | what it is |
|---|---|---|
| `baseline` | 4 | K1–K4 exactly as carved. The memorisation control |
| `isomorph_quagmire` | 50 | Quagmire III on novel plaintexts under random keys |
| `isomorph_transposition` | 50 | K3's route geometry, novel plaintexts |
| `isomorph_composite` | 50 | Vigenère → Hill, a multi-layer K4 proxy |
| `isomorph_nulls` | 50 | Quagmire III with positional null characters |

Field naming follows established benchmarks — `problem` / `solution` / `answer`, as in
MATH-500 — and problem is separated from ground truth by field grouping rather than by
separate files, which is what every major benchmark does. `INPUT_FIELDS` and
`GROUND_TRUTH_FIELDS` in `schema.py` make that split machine-readable, so a harness never
has to hardcode column names.

Every isomorph instance round-trips through the Phase 1 ciphers on its own published
parameters, so a published key that does not decrypt its own ciphertext fails the build.
Plaintexts are recombined from public-domain prose into passages that have never existed,
statistically indistinguishable from contiguous English.

See [`src/kryptos/dataset/README.md`](src/kryptos/dataset/README.md) for the schema,
scoring rules, per-config provenance, and the transcription-verification argument.

## The four axes

Config, tier, paradigm and presentation are independent by design. Holding three fixed and
varying the fourth is what makes each comparison a result rather than a coincidence.

```bash
--config isomorph_quagmire     # which data
--tier 2                       # how the problem is framed
--paradigm tool_use            # whether the model may run code
--delimited                    # how the ciphertext is rendered
```

**Tiers are framings over one dataset, not separate datasets.** The same instance posed
four ways measures four different things:

| tier | capability | metric | pass |
|---|---|---|---|
| 1 | executing a specified algorithm without arithmetic slips | CER | 0% |
| 2 | single-layer cryptanalysis — IoC, frequency analysis, hill-climbing | CER | ≤ 5% |
| 3 | geometric transposition — spatial reasoning, anagramming | CER | ≤ 10% |
| 4 | K4: hypothesis generation against an unsolved cipher | cribs + fitness | none |

Tier 1 hands the model the keys on purpose — it tests execution, not discovery. Tier 4 has
no pass mark: nobody has solved K4, so there is no distribution to calibrate one against,
and an invented number would licence unsupported claims. Omit `--tier` and each row is
posed at its natural tier.

**Two paradigms** run through one entry point: chain of thought, and the same prompt plus a
Python sandbox. Nothing else differs between them — a test asserts the request diff is
exactly `{tools, system}` — because the gap between them is only a result if nothing else
varies.

**Two providers, one prompt.** `tiers` builds both prompts, `paradigms` decides what a
paradigm means, and `providers` does nothing but carry two strings to an API. A test
asserts both backends receive byte-identical system and user text, and both share one
answer parser — a per-provider parser could be more forgiving of one vendor's output, and
that difference would read as a capability gap.

Only the dataset's input columns are ever sent to the model, and which columns count as
input depends on the tier; a test asserts no ground-truth field appears in any generated
prompt, at any tier, in any config.

## Reading the results

Four rules are enforced in code rather than left to the reader:

- **CER and frontier scores never enter the same mean.** Different scales, no common zero.
- **The paradigm and presentation comparisons are paired** on instances measured on both
  sides. Comparing group means would let a refusal that dropped a hard instance from one
  arm improve that arm's mean for free — and it would read as a paradigm effect.
- **Baseline vs isomorph is unpaired, and says so.** The two sides are different instances
  by construction; that is the experiment.
- **Refusals and transport errors are harness outcomes, never wrong answers.** Scoring a
  safety-classifier hit as CER 1.0 would fold the harness's failures into the model's
  score. They are excluded from every mean and reported separately.

Records carry a schema version and an unknown one is refused rather than reinterpreted: a
field that changed meaning would otherwise produce a plausible number from incompatible
data.

```bash
python -m kryptos.eval.report runs/*.jsonl
python -m kryptos.eval.report runs/*.jsonl --by requested_model config   # several models
python -m kryptos.eval.report runs/*.jsonl --by family                   # the headline
```

When quoting a result: a low baseline score is recall, not cryptanalysis, and a gap whose
confidence intervals overlap is not a finding.

## Driving it from an agent

[`.claude/skills/kryptos-benchmark/SKILL.md`](.claude/skills/kryptos-benchmark/SKILL.md)
drives the whole flow — establish provider and key, interview for the run parameters with
option menus, price a two-instance probe **before** committing to a sweep, run, then
report. It also carries the things not to say when presenting the numbers.

It is plain Markdown with YAML frontmatter. Claude Code discovers it automatically; for
Cursor or another harness, point the agent at the path or copy it into that tool's rules
directory. Nothing in it depends on a particular runtime.

## Repository layout

`src/kryptos/dataset/` is the HuggingFace dataset repository root: the card plus one
directory per config. It holds no code.

```
src/kryptos/dataset/README.md          HuggingFace dataset card
src/kryptos/dataset/<config>/          published artifacts: test.jsonl
src/kryptos/dataset/example.py         standalone runner shipped with the dataset
src/kryptos/algorithms/ciphers/        Quagmire III, transposition, Vigenère, Hill
src/kryptos/algorithms/baseline/       source text, schema and builder for K1–K4
src/kryptos/algorithms/isomorph/       corpus, generators, schema and builder
src/kryptos/scoring/                   CER, cribs, IoC, quadgram fitness, tier table
src/kryptos/eval/                      tiers, paradigms, providers, runner, report
src/kryptos/huggingface/               Hub publishing, with preflight checks
tests/                                 verification — 676 tests
docs/                                  design documents
```

The runner has two roles and they are deliberately separate: `src/kryptos/eval/` is the
project's own harness and grows with the project, while `src/kryptos/dataset/example.py`
ships with the dataset, imports nothing from this repository, and is meant to stay small.

```bash
pip install anthropic datasets rapidfuzz
python src/kryptos/dataset/example.py --passages K1 K3
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest                                          # 676 tests, none call an API

python -m kryptos.algorithms.baseline.build --check       # artifact matches source
python -m kryptos.algorithms.isomorph.build --check
python -m kryptos.algorithms.isomorph.build               # regenerate the snapshot

python -m kryptos.huggingface.push --dry-run              # check, upload nothing
python -m kryptos.huggingface.push                        # publish (private)
```

The test suite makes no network calls and passes with neither provider SDK installed, which
is what the lazy imports exist for.

Builders are deterministic and their artifacts are committed, so consumers need not run
anything. `--check` rebuilds in memory and compares, so a stale artifact fails rather than
being silently republished.

The published instances come from a fixed snapshot seed. Generating *fresh* instances —
for a contamination re-check once these have been public a while, or simply for more of
them — goes through the same code path with a different seed:

```python
from kryptos.algorithms.isomorph import generate
instances = generate.generate("quagmire", 50, seed=20270101)
```

One code path for both is deliberate: instances generated later are comparable with the
published snapshot because nothing differs but the seed.

Publishing runs preflight first and refuses to upload if a committed artifact is stale, the
card's declared config paths do not resolve, the card metadata fails the Hub's validation,
the data does not load against its declared features, or an unrecognised file type would be
swept into the upload. `--public` is never the default: visibility is hard to walk back
once anything has crawled or mirrored it.

See [`plan.md`](plan.md) for the build history and the reasoning behind each decision, and
`docs/` for the original design.

## Limitations

- **The tier pass marks are asserted, not calibrated.** 0% / 5% / 10% come from the design
  document, not from an observed distribution of scores. Treat CER as the measurement and
  the pass column as provisional.
- **The composite configs are proxies for K4, not models of it.** Nobody knows K4's method;
  a Vigenère→Hill composite is a guess about difficulty. They are multi-layer capability
  probes and should be reported as such.
- **The baseline is four instances.** It is a control, not a ranking. There is no
  leaderboard.
- **The isomorph snapshot is published**, and is therefore contaminated like any other
  benchmark once it has been through a training cycle. The fresh-seed path exists for that.
- **The OpenAI backend has not been exercised against a live endpoint.** Its wire format is
  covered by stubbed tests only. Probe two instances before a real sweep.

## Citation

```bibtex
@misc{bhuvaji2026kryptosbench,
  title        = {Kryptos Benchmark: Evaluating Language Models on Classical Cryptanalysis},
  author       = {Bhuvaji, Sartaj},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/datasets/sartajbhuvaji/kryptos-bench}}
}
```

MIT licensed. The *Kryptos* sculpture is a copyrighted work by Jim Sanborn; the ciphertexts
and their published solutions are reproduced as factual data for research and commentary.
Not affiliated with or endorsed by Jim Sanborn or the Central Intelligence Agency.
