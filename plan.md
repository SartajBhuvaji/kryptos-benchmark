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
| 1 — Cipher implementations | 22 / 22 ✅ | PR #1–#4. K3's route now published as data |
| 2 — Scoring module | 10 / 10 ✅ | PR #5, #6. Thresholds are asserted, not yet calibrated |
| 3 — Isomorph generation | 18 / 18 ✅ | PR #7–#9. 200 instances live on the Hub |
| 4 — Tiers and paradigms | 1 / 13 | **Next.** Blocked on two decision gates in 4.1 |
| 5 — Reporting | 0 / 7 | |
| **Total** | **58 / 77** | |

**Landed so far:** the baseline dataset and its card, the Hub publishing path with
preflight checks, the benchmark runner with CER/crib scoring and the `--delimited`
tokenization switch, and the two Kryptos ciphers with K3's geometry derived rather than
taken on faith, and Vigenère and Hill for the Phase 3 composites. Every solved passage
round-trips from carved ciphertext to published answer. The scoring module now carries
everything the tiers need — CER, similarity ratio, index of coincidence, quadgram
fitness and the tier table. Phase 3's plaintext corpus is in: 36,653 clauses of
public-domain prose, recombined into passages that have never existed, the four generators
that turn them into cipher instances, and 200 published instances across four sibling
configs — every one round-tripping through the Phase 1 ciphers on its own published
parameters. 476 tests.

**The measurement the project exists for is now runnable end to end:** baseline score
versus isomorph score, per model. What Phase 4 adds is the framing — tiers, prompts, and
the second evaluation paradigm — not the data.

**Open decision gates —** two, both in Phase 4:

| Gate | Phase | Blocks |
|---|---|---|
| What Tier 4 actually scores | 4.1 | the K4 tier |
| Sandbox for the tool-use paradigm | 4.1 | the second evaluation paradigm |

Three gates are closed. K3's route geometry (1.2): the design document's stated width of
86 is an error, and the real route was recovered by exhaustive search. Both 3.1 gates
(recorded in full in that section): plaintexts come from recombined public-domain prose,
and generation supports both a seeded snapshot and a fresh seed, with the seed threaded
through the generator API rather than bolted on.

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

## Phase 1 — Cipher implementations ✅ complete

All four ciphers are implemented, the baseline's five indirect checks have been upgraded
to an actual round-trip proof — every solved passage decrypts exactly — and the published
dataset now states K3's route instead of declining to assert it.

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

### 1.3 Vigenère and Hill ✅

Needed for the Phase 3 K4 proxies, not for the baseline.

- [x] Vigenère encrypt/decrypt over a keyed alphabet
- [x] Hill cipher mod 26: matrix multiply, adjugate inverse, invertibility check
      (`gcd(det, 26) == 1`)
- [x] Known-plaintext attack: recover the key matrix from enough crib pairs
- [x] Unit tests including a deliberately non-invertible matrix

### 1.4 Round-trip validation of the baseline ✅

The payoff. Each of these either passes or tells us the published data is wrong.

- [x] K1: `decrypt(ciphertext, "KRYPTOS", "PALIMPSEST")` == stored `answer`
- [x] K2: `decrypt(ciphertext, "KRYPTOS", "ABSCISSA")` == stored `answer`
      (ending `...WESTIDBYROWS`, not the widely quoted `X LAYER TWO`)
- [x] K3: `decrypt(ciphertext, <derived geometry>)` == stored `answer`
- [x] Round-trips live in `tests/test_quagmire.py` and `tests/test_transposition.py`,
      beside each cipher, with the indirect checks still in `tests/test_baseline.py`

### 1.5 Correct and republish the baseline ✅

- [x] Replace K3's `solution` text, which currently says the geometry "is not asserted
      here", with the verified route — and render it from `K3_ROUTE` /
      `K3_SOLVER_ROUTE` rather than restating them, since hand-restating is what let it
      go stale
- [x] Add a machine-readable `route` field, so the transposition's key is data like the
      Quagmire keywords are, not prose. `"width:quarter_turns"` per stage, encryption
      direction; a string because a list-of-struct column populated in one of four rows
      is the shape Arrow loads least predictably. Phase 3's isomorphs need this field
- [x] Rebuild the artifact, re-run preflight, push to the Hub (PR #4)
- [x] Note the correction in the dataset card — including its stale claim that the text
      "is not validated by round-tripping through a solver", which 1.4 made false

---

## Phase 2 — Scoring module

Target: `src/kryptos/scoring/`

### 2.1 Extract what exists ✅

- [x] Move `character_error_rate`, `levenshtein`, `crib_score`, `letters_only` out of
      `run_benchmark.py` into the module (move, don't rewrite — they're tested).
      Split by what is measured: `text`, `distance`, `cribs`
- [x] Point the runner at the new module; tests must stay green
- [x] Separate the runner's two roles, which this collided with. It claimed to import
      nothing from the repo so it could ship as a usage example, but nothing ever
      shipped — and Phases 4–5 make it too big for that job anyway. The harness now
      imports the module; `dataset/example.py` is standalone, ships with the data, and
      is pinned to the module value-for-value plus held to the no-leak property

### 2.2 Add what the tiers need ✅

- [x] Normalized Levenshtein ratio (0–100) so scores compare across passages of very
      different length — 97 characters vs 869. `similarity_ratio`, symmetric and bounded,
      unlike CER which divides by the reference and is unclamped
- [x] Index of coincidence — the tier-3 discriminator between substitution and
      transposition, and a useful report diagnostic
- [x] N-gram fitness (quadgram log-probability) to judge whether a partial break is real
      or noise. Reported as a per-quadgram mean, since a raw sum ranks long passages worst
      regardless of content
- [x] Source and commit an English quadgram frequency table — the Practical Cryptography
      table, so scores stay comparable with the published cryptanalysis literature that
      uses it. 389,373 quadgrams, committed whole; truncating would push more onto the
      floor and shift scores off that baseline. Checksummed, with provenance and the
      licensing position recorded in `scoring/data/PROVENANCE.md`
- [x] Tier thresholds as data, not scattered constants: T1 = 0%, T2 < 5%, T3 < 10%.
      Tier 4 holds `None` rather than a placeholder, so gate 4.1 stays visible

### 2.3 Verify ✅

- [x] IoC ≈ 0.066 on the K3 plaintext and K3 ciphertext (transposition preserves it);
      measurably lower on K1/K2 ciphertext. Measured: K3 **0.0662 on both, equal to the
      bit**; K1 0.0379 and K2 0.0455 against an English norm of 0.0667
- [x] N-gram fitness ranks real plaintext above shuffled text of the same letters —
      by roughly two log units, on identical letter multisets, which isolates what the
      n-gram model adds over the IoC

---

## Phase 3 — Isomorph generation

Target: `src/kryptos/algorithms/isomorph/`

The actual contamination-resistance mechanism.

### 3.1 Decision gates ✅ both resolved

- [x] 🚩 **Where do plaintexts come from?** *Resolved: procedurally recombined
      public-domain corpora.* Clauses drawn from eight pre-1929 prose works and
      concatenated, so a passage is novel — no memorised completion once a few characters
      resolve — while keeping the statistics of real English. The LLM option in the design
      doc was rejected on the inflation problem stated below; verbatim excerpts on
      recognisability. **Verified, not assumed:** recombined text scores −4.207 quadgram
      fitness against −4.201 for genuine contiguous prose at matched lengths, a gap of
      0.006 against a standard deviation of 0.11
- [x] 🚩 **Seeded snapshot or fresh per run?** *Resolved: both.* A seeded published
      snapshot per release for cross-model comparability, plus on-demand generation with
      a fresh seed for contamination resistance. Seed is a first-class parameter of every
      generator from the start rather than retrofitted

### 3.2 Plaintext corpus ✅

- [x] Implement the sourcing decided above — `isomorph/data/build.py`, same contract as
      the other builders: deterministic, checksummed, `--check` without network.
      Gutenberg's licensed boilerplate stripped by requiring its START/END markers
- [x] Normalise: uppercase, strip punctuation and spacing, matching the carved form.
      Accented letters are folded first (`Pélagie` → `PELAGIE`), not dropped — dropping
      welds neighbours into sequences occurring in no English word
- [x] Length control so generated instances match Kryptos-like sizes (63–372 characters).
      **Exact**, by trimming the final clause: a route transposition needs a grid width
      dividing the text, so approximate lengths would choose the geometry for us
- [x] Corpus provenance recorded per instance — source works, clause count, and whether
      the tail was trimmed

### 3.3 Generators ✅

- [x] Quagmire III isomorphs — random alphabet keyword, random indicator keyword, period
      derived from the indicator. Published period is the **true** period, not the keyword
      length: a repeating indicator is a shorter cipher wearing a longer key
- [x] Transposition isomorphs — randomised grid width, rotation sequence, reslice width.
      Length is chosen from the geometry, not the other way round, since a width must
      divide the text; the solution states the two-stage inverse when one exists
- [x] Composite K4 proxies — Vigenère→Hill, and Quagmire with `W` null separators. Nulls
      are discarded **by position, not by letter** — `W` occurs naturally in English, so
      "delete every W" would delete real letters and leave the instance unsolvable
- [x] Every instance ships its full parameter set as ground truth, so `solution` is
      machine-generated rather than hand-written
- [x] Deterministic given a seed — and the stream is salted per kind with SHA-256, or one
      snapshot ships every config keyed alike, with plaintexts shared between them

Keywords are drawn from the corpus vocabulary rather than made of random letters, matching
how Kryptos keys on real words. Degenerate draws are screened and redrawn using the hooks
Phase 1 left for exactly this — `degenerate_columns`, `is_identity`, `is_invertible`.

### 3.4 Verify ✅

- [x] Every generated instance round-trips through the Phase 1 ciphers — driven only by
      the parameters the instance publishes, not by anything retained from generation
- [x] Same seed produces byte-identical output
- [x] Different seeds produce disjoint keys and plaintexts
- [x] Generated Quagmire instances pass the same periodic-consistency check the baseline
      does — imported from the baseline's test module rather than reimplemented, so the
      claim is literally true rather than approximately

### 3.5 Publish ✅

- [x] New sibling configs in the existing Hub repo: `isomorph_quagmire`,
      `isomorph_transposition`, `isomorph_composite` — **and `isomorph_nulls`, a fourth.**
      The two K4 proxies share no parameters, so folding them into one config would
      publish `hill_matrix` as null on every nulls row and `null_positions` as null on
      every Vigenère–Hill row. One cipher per config, 50 instances each, seed `20260731`
- [x] Card sections per config — including that the composites are **proxies**, and
      solving one is not evidence about K4. Stated in the card *and* in every proxy row's
      published `solution`
- [x] Reuse `kryptos.huggingface.push` preflight; extend it to validate every config —
      in both directions: a built config the card omits uploads as files the Hub never
      surfaces, and a declared config no builder produces resolves only because a stale
      file survived on disk

No tier threshold is baked into the data. Tiers are framings applied at evaluation time,
so `scoring_threshold` is `0.0` — exact recovery — and the pass marks stay in
`kryptos.scoring.thresholds` where Phase 4 can revise them without reissuing the dataset.

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

- ~~**K3's route geometry may not be as documented.**~~ *Realised, then closed.* The
  documented width-86 chain reproduced nothing; the real route was derived by exhaustive
  search in 1.2 and published in 1.5. The residual caveat is narrower: uniqueness holds
  only relative to the family of routes searched, since one plaintext/ciphertext pair
  cannot single out a permutation on its own.
- **Composite K4 proxies test something we cannot name.** Nobody knows K4's method, so a
  Vigenère→Hill composite is a guess about difficulty, not a model of the real problem.
  Worth building as a multi-layer capability probe; the framing must not imply otherwise.
- **Tier thresholds are asserted, not calibrated.** 0% / 5% / 10% come from the design
  document with no supporting data. Revisit against observed score distributions after
  the first real runs.
- **Cost.** Tier 4 at high effort × several models × two paradigms × two presentations is
  real API spend. Size it before running the matrix, not after.
