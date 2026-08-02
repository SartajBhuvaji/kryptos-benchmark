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

See [`plan.md`](plan.md) for the build history and the reasoning behind each decision, and
`docs/` for the original design.

## Status

The roadmap is complete: 77/77, 600 tests. **Nothing has been run against a model yet** —
the benchmark measures, but it has not yet measured.

| component | state |
|---|---|
| baseline dataset | four authentic passages, verified five ways and round-tripped |
| cipher implementations | Quagmire III, route transposition, Vigenère, Hill |
| isomorph generators | four, one per cipher — 200 published instances |
| scoring | CER, similarity, crib placement, quadgram fitness, IoC |
| tier framings | four, from executing a given algorithm to K4 |
| evaluation paradigms | chain of thought and server-side code execution |
| reporting | breakdowns, paired comparisons, cost accounting |

Published to the Hub as
[`sartajbhuvaji/kryptos-bench`](https://huggingface.co/datasets/sartajbhuvaji/kryptos-bench),
five configs, `test` split.

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

## Tiers and paradigms

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
and an invented number would licence unsupported claims.

**Two paradigms** run through one entry point: chain of thought, and the same prompt plus a
Python sandbox. Nothing else differs between them — a test asserts the request diff is
exactly `{tools, system}` — because the gap between them is only a result if nothing else
varies.

## Running it

```bash
.venv/bin/python -m pip install -e ".[eval]"
.venv/bin/python -m kryptos.eval.run_benchmark --help

# one config, default framing
.venv/bin/python -m kryptos.eval.run_benchmark --config baseline

# the axes are independent: config, tier, paradigm, presentation
.venv/bin/python -m kryptos.eval.run_benchmark --config isomorph_quagmire --tier 2
.venv/bin/python -m kryptos.eval.run_benchmark --config isomorph_quagmire --paradigm tool_use
.venv/bin/python -m kryptos.eval.run_benchmark --config isomorph_quagmire --delimited

# several models against one instance set, so they cannot drift apart
.venv/bin/python -m kryptos.eval.run_benchmark --model claude-opus-5 claude-sonnet-5

# aggregate the persisted runs into comparisons
.venv/bin/python -m kryptos.eval.report runs/*.jsonl
```

Needs the `eval` extra and Anthropic credentials. Only the dataset's input columns are ever
sent to the model, and which columns count as input depends on the tier; a test asserts no
ground-truth field appears in any generated prompt, at any tier, in any config.

**Size a run before committing to it.** The full matrix is 5 configs × 4 tiers × 2
paradigms × 2 presentations at 50 instances per isomorph config — real API spend. `--limit`
exists for exactly this.

## Reading the results

Runs append to `runs/*.jsonl`, one record per instance, so a run can be re-analysed without
paying for it again. `kryptos.eval.report` turns those records into the comparisons the
benchmark exists to make: per-tier and per-paradigm breakdowns, baseline vs isomorph per
model, the chain-of-thought vs tool-use gap, the raw vs character-delimited test of the
tokenization claim, and cost.

Three rules are enforced in code rather than left to the reader:

- **CER and frontier scores never enter the same mean.** Different scales, no common zero.
- **The paradigm and presentation comparisons are paired** on instances measured on both
  sides. Comparing group means would let a refusal that dropped a hard instance from one
  arm improve that arm's mean for free — and it would read as a paradigm effect.
- **Baseline vs isomorph is unpaired, and says so.** The two sides are different instances
  by construction; that is the experiment.

Refusals and transport errors are recorded as harness outcomes, never as wrong answers.
Scoring a safety-classifier hit as CER 1.0 would fold the harness's failures into the
model's score.

## Layout

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
src/kryptos/eval/                      tiers, paradigms, runner, results, report
src/kryptos/huggingface/               Hub publishing, with preflight checks
tests/                                 verification — 600 tests
docs/                                  design documents
```

The runner has two roles and they are deliberately separate: `src/kryptos/eval/` is the
project's own harness and grows with the project, while `src/kryptos/dataset/example.py`
ships with the dataset, imports nothing from this repository, and is meant to stay small.

## Development

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest                                          # verification suite

.venv/bin/python -m kryptos.algorithms.baseline.build --check       # artifact matches source
.venv/bin/python -m kryptos.algorithms.isomorph.build --check
.venv/bin/python -m kryptos.algorithms.isomorph.build              # regenerate the snapshot

.venv/bin/python -m kryptos.huggingface.push --dry-run              # check, upload nothing
.venv/bin/python -m kryptos.huggingface.push                        # publish (private)
```

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
