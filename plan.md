# Roadmap

Step-by-step plan for building out the benchmark described in
`docs/Kryptos LLM Benchmark Creation Plan.pdf`. The design document sets the destination;
this file is the route, with what is standing already and the decisions still open.

The baseline is the memorisation control. Everything below exists to produce the thing it
is a control *for*: synthetic ciphers structurally identical to Kryptos that cannot have
been memorised, so the gap between a model's baseline score and its isomorph score becomes
measurable.

**Decision gates** (🚩) block the phase they sit in. Answer them before writing that code,
not during.

---

## Status

| Phase | Done | Notes |
|---|---|---|
| 0 — Baseline | 7 / 7 ✅ | Published as `sartajbhuvaji/kryptos-bench`, config `baseline` |
| 1 — Cipher implementations | 14 / 21 | 1.1, 1.2, 1.4 complete (PR #1, #2). 1.3 and 1.5 remain |
| 2 — Scoring module | 0 / 9 | CER and crib-match currently live inside the runner |
| 3 — Isomorph generation | 0 / 18 | Blocked on two decision gates in 3.1 |
| 4 — Tiers and paradigms | 1 / 13 | Blocked on two decision gates in 4.1 |
| 5 — Reporting | 0 / 7 | |
| **Total** | **22 / 75** | |

**Landed so far:** the baseline dataset and its card, the Hub publishing path with
preflight checks, the benchmark runner with CER/crib scoring and the `--delimited`
tokenization switch, and the two Kryptos ciphers with K3's geometry derived rather than
taken on faith. 171 tests.

**Open decision gates —** four, all recorded inline in the phase they block:

| Gate | Phase | Blocks |
|---|---|---|
| Where isomorph plaintexts come from | 3.1 | all generator work |
| Seeded snapshot vs. fresh per run | 3.1 | generator API shape |
| What Tier 4 actually scores | 4.1 | the K4 tier |
| Sandbox for the tool-use paradigm | 4.1 | the second evaluation paradigm |

A fifth gate — deriving K3's route geometry — was resolved in 1.2: the design document's
stated width of 86 is an error, and the real route was recovered by exhaustive search.

---

## Phase 0 — Baseline ✅ complete

- [x] Transcribe K1–K4 exactly as carved, verified five ways (length checksums, length
      preservation, K3 anagram identity, Quagmire periodic consistency, crib positions)
- [x] Flat HF-compatible schema with `problem` / `solution` / `answer` field naming
- [x] Deterministic builder + committed artifact — `src/kryptos/algorithms/baseline/`
- [x] Dataset card following the standard benchmark template
- [x] Publish to the Hub with preflight checks — `sartajbhuvaji/kryptos-bench`, config `baseline`
- [x] Benchmark runner: loads dataset, calls a model, scores, prints — `src/kryptos/eval/`
- [x] Test suite including the no-ground-truth-leak property

---

## Phase 1 — Cipher implementations

**Mostly done.** Both Kryptos ciphers are implemented and the baseline's five indirect
checks have been upgraded to an actual round-trip proof — all three solved passages now
decrypt exactly. What remains is Vigenère and Hill (needed only by the Phase 3 K4 proxies,
not by the baseline) and republishing K3's corrected `solution` field.

Target: `src/kryptos/algorithms/ciphers/`

### 1.1 Quagmire III ✅

- [x] `keyed_alphabet(keyword)` — dedupe keyword letters, append unused A–Z in order
- [x] `encrypt(plaintext, alphabet_keyword, indicator_keyword)`
- [x] `decrypt(ciphertext, alphabet_keyword, indicator_keyword)`
- [x] `?` passes through unenciphered **and does not advance the key** (the alternative
      convention decrypts K2 wrongly at 282 of 369 enciphered positions; this one at none)
- [x] Unit tests on small hand-computed vectors, independent of the Kryptos data

### 1.2 Route transposition ✅

**Gate resolved.** The design document's width-86 → reslice-8 route does not reproduce K3:
86 divides neither 336 nor a padding of it, and sweeping that shape over every rotation
matches nothing. An exhaustive search of two-stage routes over widths dividing 336 found
twelve matches, all inducing one permutation — the width pairs multiplying to 588, both
stages a quarter turn. `K3_ROUTE = ((7, 1), (84, 1))`; the solver's inverse is
`((8, 1), (24, 1))`, which is where the document's "segments of 8" belongs.

- [x] 🚩 **Derive K3's actual geometry.** *Resolved — see below.* The design doc states width-86 → rotate →
      reslice to width-8 → rotate → read columns, without derivation. Treat as a
      hypothesis to test, not a spec to implement.
- [x] `encrypt(plaintext, width, rotations, reslice_width)`
- [x] `decrypt(...)` — exact inverse
- [x] Property test: `decrypt(encrypt(x)) == x` over randomised dimensions
- [x] Property test: ciphertext is always an exact anagram of plaintext

### 1.3 Vigenère and Hill

Needed for the Phase 3 K4 proxies, not for the baseline.

- [ ] Vigenère encrypt/decrypt over a keyed alphabet
- [ ] Hill cipher mod 26: matrix multiply, adjugate inverse, invertibility check
      (`gcd(det, 26) == 1`)
- [ ] Known-plaintext attack: recover the key matrix from enough crib pairs
- [ ] Unit tests including a deliberately non-invertible matrix

### 1.4 Round-trip validation of the baseline ✅

The payoff. Each of these either passes or tells us the published data is wrong.

- [x] K1: `decrypt(ciphertext, "KRYPTOS", "PALIMPSEST")` == stored `answer`
- [x] K2: `decrypt(ciphertext, "KRYPTOS", "ABSCISSA")` == stored `answer`
      (ending `...WESTIDBYROWS`, not the widely quoted `X LAYER TWO`)
- [x] K3: `decrypt(ciphertext, <derived geometry>)` == stored `answer`
- [x] Round-trips live in `tests/test_quagmire.py` and `tests/test_transposition.py`,
      beside each cipher, with the indirect checks still in `tests/test_baseline.py`

### 1.5 Correct and republish the baseline

- [ ] Replace K3's `solution` text, which currently says the geometry "is not asserted
      here", with the verified route
- [ ] Rebuild the artifact, re-run preflight, push to the Hub
- [ ] Note the correction in the dataset card

---

## Phase 2 — Scoring module

Target: `src/kryptos/scoring/`

### 2.1 Extract what exists

- [ ] Move `character_error_rate`, `levenshtein`, `crib_score`, `letters_only` out of
      `run_benchmark.py` into the module (move, don't rewrite — they're tested)
- [ ] Point the runner at the new module; tests must stay green

### 2.2 Add what the tiers need

- [ ] Normalized Levenshtein ratio (0–100) so scores compare across passages of very
      different length — 97 characters vs 869
- [ ] Index of coincidence — the tier-3 discriminator between substitution and
      transposition, and a useful report diagnostic
- [ ] N-gram fitness (quadgram log-probability) to judge whether a partial break is real
      or noise
- [ ] Source and commit an English quadgram frequency table
- [ ] Tier thresholds as data, not scattered constants: T1 = 0%, T2 < 5%, T3 < 10%

### 2.3 Verify

- [ ] IoC ≈ 0.066 on the K3 plaintext and K3 ciphertext (transposition preserves it);
      measurably lower on K1/K2 ciphertext
- [ ] N-gram fitness ranks real plaintext above shuffled text of the same letters

---

## Phase 3 — Isomorph generation

Target: `src/kryptos/algorithms/isomorph/`

The actual contamination-resistance mechanism.

### 3.1 Decision gates — settle before writing generators

- [ ] 🚩 **Where do plaintexts come from?** The design doc says generate them with a
      secondary LLM. Subtle problem: LLM prose is close to the most predictable English
      there is, and both n-gram hill-climbing and a model's own priors do measurably
      better on typical text than idiosyncratic text — scores could be inflated relative
      to the cipher's real difficulty. Alternatives: public-domain text published after a
      stated cutoff, procedurally recombined corpora, or a private held-out set.
- [ ] 🚩 **Seeded snapshot or fresh per run?** Contamination resistance wants new data
      every run; comparing two models wants identical data. Usual resolution is both — a
      seeded published snapshot per release, plus on-demand generation with a fresh seed.
      Decide now: it determines whether seeding threads through the generator API or gets
      bolted on later.

### 3.2 Plaintext corpus

- [ ] Implement the sourcing decided above
- [ ] Normalise: uppercase, strip punctuation and spacing, matching the carved form
- [ ] Length control so generated instances match Kryptos-like sizes (63–372 characters)
- [ ] Corpus provenance recorded per instance

### 3.3 Generators

- [ ] Quagmire III isomorphs — random alphabet keyword, random indicator keyword, period
      derived from the indicator
- [ ] Transposition isomorphs — randomised grid width, rotation sequence, reslice width
- [ ] Composite K4 proxies — Vigenère→Hill, and Quagmire with `W` null separators
- [ ] Every instance ships its full parameter set as ground truth, so `solution` is
      machine-generated rather than hand-written
- [ ] Deterministic given a seed

### 3.4 Verify

- [ ] Every generated instance round-trips through the Phase 1 ciphers
- [ ] Same seed produces byte-identical output
- [ ] Different seeds produce disjoint keys and plaintexts
- [ ] Generated Quagmire instances pass the same periodic-consistency check the baseline does

### 3.5 Publish

- [ ] New sibling configs in the existing Hub repo: `isomorph_quagmire`,
      `isomorph_transposition`, `isomorph_composite`
- [ ] Card sections per config — including that the composites are **proxies**, and
      solving one is not evidence about K4
- [ ] Reuse `kryptos.huggingface.push` preflight; extend it to validate every config

---

## Phase 4 — Tiers and evaluation paradigms

The design document's four tiers are *task framings* over the datasets above, not new data.

| Tier | Input | Capability under test | Threshold |
|---|---|---|---|
| 1 Algorithmic identification | synthetic ciphertext + cipher name + exact keys | executing a specified algorithm without arithmetic slips | 0% CER |
| 2 Single-layer cryptanalysis | synthetic Quagmire III, no keys | IoC, frequency analysis, hill-climbing | CER < 5% |
| 3 Geometric transposition | synthetic transposition | spatial reasoning, anagramming, n-gram optimisation | CER < 10% |
| 4 K4 frontier | authentic K4 + cribs | hypothesis generation, matrix algebra | see gate below |

### 4.1 Decision gates

- [ ] 🚩 **What does Tier 4 score?** The doc says "Normalized Levenshtein > 30%", but K4
      has no known plaintext — there is no reference string to measure against, so the
      metric cannot be computed as written. Options: crib characters only; a hypothesis
      rubric (is the mechanism internally consistent, does it reproduce the cribs, does
      the code run); or report Tier 4 qualitatively with no numeric threshold.
- [ ] 🚩 **Sandbox for tool-use.** Running model-written Python needs isolation. Anthropic's
      server-side code execution tool, or a local container? Affects cost, portability,
      and third-party reproducibility.

### 4.2 Tier prompts

- [ ] Tier 1 — cipher name and keys supplied; tests execution, not discovery
- [ ] Tier 2 — ciphertext only
- [ ] Tier 3 — ciphertext only, transposition family
- [ ] Tier 4 — K4 plus cribs, per the gate above
- [ ] Few-shot format demonstrations, since the design doc notes strict output schemas can
      degrade reasoning without them

### 4.3 Tool-use paradigm

- [ ] Sandbox integration
- [ ] Model writes, executes, and iterates on Python; transcript captured
- [ ] Same scoring path as CoT so the two are directly comparable

### 4.4 Runner extensions

- [ ] `--tier`, `--paradigm`, `--config` flags
- [x] Presentation stays a render-time axis — `--delimited` shipped with the runner
- [ ] Per-instance results persisted, not just printed

---

## Phase 5 — Reporting

- [ ] Multi-model runs from one command
- [ ] Results persisted (JSONL per run, with model, tier, paradigm, seed, timestamp)
- [ ] Per-tier and per-paradigm breakdowns
- [ ] **The headline comparison: baseline score vs. isomorph score, per model.** A model
      that solves K1 and fails every Quagmire isomorph has told you something specific
- [ ] CoT vs tool-use gap per tier — the design doc predicts a large one, and measuring it
      is a result in itself
- [ ] Raw vs character-delimited comparison, testing the doc's tokenization claim
- [ ] Cost and token accounting per run

---

## Risks

- **K3's route geometry may not be as documented.** The width-86 → rotate → width-8 →
  rotate chain is asserted without derivation, which is why Phase 0 stopped short of
  publishing it. If it does not round-trip in 1.4, the real geometry must be derived
  before the K3 isomorph generator can be written.
- **Composite K4 proxies test something we cannot name.** Nobody knows K4's method, so a
  Vigenère→Hill composite is a guess about difficulty, not a model of the real problem.
  Worth building as a multi-layer capability probe; the framing must not imply otherwise.
- **Tier thresholds are asserted, not calibrated.** 0% / 5% / 10% come from the design
  document with no supporting data. Revisit against observed score distributions after
  the first real runs.
- **Cost.** Tier 4 at high effort × several models × two paradigms × two presentations is
  real API spend. Size it before running the matrix, not after.
