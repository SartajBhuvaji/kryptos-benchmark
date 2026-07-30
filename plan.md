# Roadmap

Working plan for building out the benchmark described in
`docs/Kryptos LLM Benchmark Creation Plan.pdf`. The design document sets the destination;
this file tracks the route, what is already standing, and the decisions still open.

## Where we are

| Component | State |
|---|---|
| Baseline dataset (K1–K4 as carved) | **done** — published as `sartajbhuvaji/kryptos-bench`, config `baseline` |
| Dataset schema, builder, HF publishing | **done** — `src/kryptos/algorithms/baseline/`, `src/kryptos/huggingface/` |
| Benchmark runner (single-model, CoT) | **done** — `src/kryptos/eval/run_benchmark.py` |
| Cipher implementations | not started |
| Scoring as a reusable module | partial — CER and crib-match live inside the runner |
| Isomorph generators | not started |
| Tier structure (1–4) | not started |
| Tool-use / code-execution paradigm | not started |

The baseline is the memorisation control. Everything below exists to produce the thing it
is a control *for*: synthetic ciphers that are structurally identical to Kryptos but
cannot have been memorised, so that the gap between a model's baseline score and its
isomorph score becomes measurable.

---

## Phase 1 — Cipher implementations

**Why first.** Everything downstream depends on it. The isomorph generators need to
*encrypt*; the baseline's transcription is currently validated five indirect ways rather
than by round-tripping through a solver; and K3's `solution` field in the published
dataset deliberately declines to assert the route geometry because we have not verified
it. One phase closes all three.

`src/kryptos/algorithms/ciphers/`

- **Quagmire III** — encrypt and decrypt. Keyed alphabet from a keyword, indicator
  keyword setting the period, `?` as a pass-through that does not advance the key
  (verified in the baseline work: the alternative convention yields 115 inconsistencies
  in K2 at period 8, this one yields zero).
- **Route transposition** — encrypt and decrypt. The design document describes width-86
  → rotate → reslice to width 8 → rotate → read columns. **This is unverified.** Pinning
  it down is a deliverable of this phase, not an assumption of it.
- **Vigenère** and **Hill (mod 26)** — needed for the K4-proxy composites in Phase 3.
  Hill needs matrix inversion mod 26 via the adjugate, plus a known-plaintext attack path.

**Verification.** Round-trip every baseline passage: `decrypt(K1_ciphertext, KRYPTOS,
PALIMPSEST, 10)` must equal the stored answer exactly, and likewise K2 and K3. That
upgrades the baseline from "five checks that would each catch a single altered character"
to a proof. If K3 does not round-trip, the published route geometry is wrong and the
dataset's `solution` field gets corrected.

**Follow-on.** Once K3 round-trips, update the `solution` field in the baseline and
re-publish — it currently says the geometry "is not asserted here."

---

## Phase 2 — Scoring module

`src/kryptos/scoring/`

Lift CER and crib-match out of the runner and add what the tiers need:

- **CER** via Levenshtein (already written — move, don't rewrite).
- **Normalized Levenshtein ratio** 0–100, which the design document calls for so scores
  compare across passages of very different length (97 vs 869 characters).
- **Index of coincidence** — the tier-3 discriminator between substitution and
  transposition, and useful as a diagnostic in reports.
- **N-gram fitness** (quadgram log-probability) — needed to score hill-climbing output
  and to judge whether a model's partial break is real or noise.
- **Tier thresholds** as data, not scattered constants: T1 = 0% CER, T2 < 5%, T3 < 10%.

---

## Phase 3 — Isomorph generation

`src/kryptos/algorithms/isomorph/`

The core contamination-resistance mechanism: same algorithms and constraints, novel
plaintexts, randomised keys.

- **K1/K2 isomorphs** — random alphabet keyword + random indicator keyword, period
  derived from the indicator, encrypted through a freshly generated Quagmire III tableau.
- **K3 isomorphs** — randomised grid dimensions, rotation sequence, and reslice width.
- **K4 proxies** — composite ciphers standing in for the unknown method: Vigenère
  followed by Hill multiplication, and Quagmire interspersed with null separators on the
  `W` hypothesis. These are *proxies*, and the dataset card must say so — solving one is
  not evidence about K4.

Each generated instance ships with its full parameter set as ground truth, so the
`solution` field is machine-generated rather than hand-written.

**Publishing.** New configs alongside `baseline` in the same Hub repo —
`isomorph_quagmire`, `isomorph_transposition`, `isomorph_composite` — which is the shape
the config layer was chosen for.

---

## Phase 4 — Tiers and evaluation paradigms

The design document's four tiers, which are *task framings* over the datasets above rather
than new data:

| Tier | Input | Capability under test | Threshold |
|---|---|---|---|
| 1 Algorithmic identification | synthetic ciphertext + cipher name + exact keys | can it execute a specified algorithm without arithmetic slips | 0% CER |
| 2 Single-layer cryptanalysis | synthetic Quagmire III, no keys | IoC, frequency analysis, hill-climbing | CER < 5% |
| 3 Geometric transposition | synthetic transposition | spatial reasoning, anagramming, n-gram optimisation | CER < 10% |
| 4 K4 frontier | authentic K4 + cribs | hypothesis generation, matrix algebra | see open question below |

Two paradigms, per the design document:

- **Autoregressive CoT** — what the runner does today.
- **Programmatic tool-use** — the model writes and executes Python in a sandbox. The
  design document argues, plausibly, that transformers cannot reliably carry mod-26
  arithmetic across hundreds of characters in-context, and that the honest measurement is
  whether a model can *write the solver*. Expect a large gap between the two paradigms;
  measuring that gap is a result in itself.

Presentation stays a render-time axis: raw vs. character-delimited ciphertext, already
implemented as `--delimited` in the runner.

---

## Phase 5 — Reporting

Multi-model runs, results persisted rather than printed, per-tier and per-paradigm
breakdowns, and the comparison the whole project is for: **baseline score vs. isomorph
score, per model.** A model that solves K1 and fails every Quagmire isomorph has told you
something specific.

---

## Open decisions

These need answers before the phase they belong to, and I'd rather raise them now than
guess.

**1. Where do isomorph plaintexts come from?** (Phase 3, blocking.) The design document
suggests generating them with a secondary LLM. That has a subtle problem: LLM-generated
prose is close to the most predictable English there is, and both n-gram hill-climbing
and a model's own priors do measurably better on typical text than on idiosyncratic text.
Scores could be inflated relative to what the cipher's difficulty warrants. Alternatives:
public-domain text published after a stated cutoff, procedurally recombined corpora, or a
private held-out set. Worth deciding deliberately.

**2. Reproducible or fresh-every-run?** (Phase 3, blocking.) Contamination resistance
wants a new dataset each run; comparing two models wants the identical dataset. These
pull against each other. The usual resolution is both: a seeded, published snapshot per
release for comparability, plus on-demand generation with a fresh seed for anyone who
suspects the snapshot has leaked. Needs deciding before generators are written, because
it determines whether seeding is threaded through the API or bolted on.

**3. What does Tier 4 actually score?** (Phase 4.) The design document says "Normalized
Levenshtein > 30%" — but K4 has no known plaintext, so there is no reference string to
compute a distance against. The metric as written cannot be computed. Realistic options:
score against the 24 crib characters only; score the *hypothesis* against a rubric
(is the proposed mechanism internally consistent, does it reproduce the cribs, does the
code run); or drop the numeric threshold and report Tier 4 qualitatively. This is
currently the weakest-specified part of the design.

**4. Sandbox for the tool-use paradigm.** (Phase 4.) Running model-written Python needs
an isolated environment. Options range from Anthropic's server-side code execution tool
to a local container. Affects cost, portability, and what a third party can reproduce.

---

## Risks

**K3's route geometry may not be as documented.** The design document's width-86 →
rotate → width-8 → rotate chain is stated without derivation, and my baseline work
deliberately stopped short of asserting it. If it does not round-trip in Phase 1, the K3
isomorph generator needs the real geometry first.

**Composite K4 proxies test something we cannot name.** Since nobody knows K4's method, a
Vigenère→Hill composite is a guess about difficulty, not a model of the real problem. It
is still worth building — multi-layer ciphers are a real capability probe — but the
framing must not imply that solving the proxy bears on K4.

**Tier thresholds are asserted, not calibrated.** 0% / 5% / 10% come from the design
document without supporting data. After the first real runs they should be revisited
against observed score distributions rather than treated as fixed.

**Cost.** Tier 4 at high effort across several models, times paradigms, times
presentation variants, is a real API spend. Worth sizing before the matrix is run rather
than after.
