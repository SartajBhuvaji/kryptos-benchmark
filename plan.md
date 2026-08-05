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
| 4 — Tiers and paradigms | 13 / 13 ✅ | PR #10, #11. Both paradigms runnable |
| 5 — Reporting | 7 / 7 ✅ | PR #12. Every comparison is one command |
| 6 — Running it | 4 / 7 | Controls, providers and the skill in; the pilot is next |
| 7 — Classical cipher suite | 0 / 18 | Planned. Sibling configs; three gates open |
| **Total** | **81 / 102** | |

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
parameters, the four tier framings that pose them, both evaluation paradigms behind one
runner, the reporting layer that turns runs into comparisons, and the runner controls
that make a long run resumable and cost-bounded. 689 tests.

**The roadmap is complete through Phase 5.** Every measurement the project was built for is runnable with
all four axes independently selectable — baseline vs isomorph, tier by tier,
chain-of-thought vs tool use, raw vs delimited — and reportable from one command over the
persisted results.

**Nothing has been run against a model yet.** The benchmark measures; it has not yet
measured. Phase 6 is that work, and the first real runs are what turn two of the risks
below from open questions into data: the tier thresholds are still asserted rather than
calibrated, and the cost of the full matrix is still an estimate. Size a run with
`--limit` and `--max-spend` before committing to it.

**All five original decision gates are closed**, each recorded in full in the section it
blocked: K3's route geometry (1.2) — the document's stated width of 86 is an error and the
real route was recovered by exhaustive search; plaintext sourcing and seeding (3.1) —
recombined public-domain prose, with both a seeded snapshot and a fresh-seed path sharing
one code path; Tier 4 scoring and the tool-use sandbox (4.1) — cribs plus fitness with no
pass mark, and server-side code execution first. **Phase 7 opens three more** (7.1), all
of them blocking its first line of code and none of them blocking Phase 6.

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

### 4.1 Decision gates ✅ both resolved

- [x] 🚩 **What does Tier 4 score?** *Resolved: crib placement **and** quadgram fitness,
      reported together, no pass mark.* Neither works alone — placement is satisfiable by
      construction (drop the four cribs into noise, score 4/4, having done nothing), and
      fitness alone says nothing about the fragments. Both failure modes are tested. No
      threshold, because there is no distribution of successful K4 attempts to calibrate
      one against and an invented number would licence unsupported claims
- [x] 🚩 **Sandbox for tool-use.** *Resolved: Anthropic's server-side code execution tool
      first, with a local container backend behind the same interface when a non-Claude
      model needs evaluating.* Server-side means no Docker prerequisite, an isolated
      no-egress container, and negligible cost at this scale. Recorded limitation: it is
      Claude-API-only, so the tool-use paradigm does not reach other providers until the
      second backend exists

### 4.2 Tier prompts ✅

- [x] Tier 1 — cipher name and keys supplied; tests execution, not discovery
- [x] Tier 2 — ciphertext only
- [x] Tier 3 — ciphertext only, transposition family
- [x] Tier 4 — K4 plus cribs, per the gate above
- [x] Few-shot format demonstrations, since the design doc notes strict output schemas can
      degrade reasoning without them. Built on a Caesar shift — a cipher no instance uses
      — so it demonstrates the format without hinting at any answer

**The leak invariant is per tier here, not global.** Everywhere else a prompt never
contains ground truth; tier 1 breaks that deliberately. So `answer`, `answer_readable`,
`solution` and the nulls config's `deciphered` are forbidden at *every* tier, while key
material is visible at tier 1 and withheld at 2 and 3 — expressed as a field allowlist
rather than per-branch logic. Tested in **both** directions: a filter erring toward
hiding everything would turn tier 1 into a second tier 2, silently, and the two would
stop measuring different things.

### 4.3 Tool-use paradigm ✅

- [x] Sandbox integration — Anthropic's server-side `code_execution_20260521`, isolated
      with no network egress. **Paused turns are resumed**: a server-side tool loop that
      hits its iteration limit ends with `stop_reason: pause_turn`, a success that is not
      finished. Unhandled, it returns a truncated answer that scores as a failed
      decryption — the exact shape of a fake paradigm gap
- [x] Model writes, executes, and iterates on Python; transcript captured — the code it
      ran and the stdout/stderr/return code it read back
- [x] Same scoring path as CoT so the two are directly comparable. One entry point builds
      one prompt, one schema, one effort setting; both paradigms return the same
      `Attempt`. A test states the request diff **exhaustively** — `{tools, system}` and
      nothing else — and another checks structurally that scoring never branches on
      paradigm at all

### 4.4 Runner extensions ✅

- [x] `--tier`, `--paradigm`, `--config` flags — plus `--effort`, `--limit`,
      `--no-few-shot` and `--out`. The axes are independent: holding three fixed and
      varying the fourth is what makes each comparison a result rather than a coincidence
- [x] Presentation stays a render-time axis — `--delimited` shipped with the runner
- [x] Per-instance results persisted, not just printed. Every axis is in the record
      (config, tier, paradigm, delimited, effort, seed, model), because a results file
      that does not say what produced it cannot be interpreted afterwards. Appends rather
      than overwrites — a run is real API spend

A refusal or a transport error is recorded as a **harness outcome, never a wrong answer**.
Scoring a classifier hit as CER 1.0 would fold the harness's failures into the model's
score.

---

## Phase 5 — Reporting ✅ complete

Every comparison the benchmark was built to make is now one command. Reporting added no
capability — it aggregates what the runner already persists per instance — so the work was
almost entirely about **which records may be averaged together**, the only part of
reporting that can quietly produce a plausible, publishable, wrong number.

Target: `src/kryptos/eval/report.py`

- [x] Multi-model runs from one command — `--model A B C`, against one instance set loaded
      once, so the models cannot drift apart on tier, presentation or instance set
- [x] Results persisted (JSONL per run, with model, tier, paradigm, seed, timestamp) —
      delivered by `results.py` in 4.4 and reused unchanged
- [x] Per-tier and per-paradigm breakdowns — `--by`, defaulting to config/tier/paradigm,
      with the model axis added automatically whenever a file holds more than one
- [x] **The headline comparison: baseline score vs. isomorph score, per model.** A model
      that solves K1 and fails every Quagmire isomorph has told you something specific
- [x] CoT vs tool-use gap per tier — the design doc predicts a large one, and measuring it
      is a result in itself
- [x] Raw vs character-delimited comparison, testing the doc's tokenization claim
- [x] Cost and token accounting per run, priced per model against published rates

### The three rules the code enforces rather than documents

**Never average across metric families.** A row with a reference answer is scored by CER;
a row without one is scored by crib placement and quadgram fitness. Different scales, no
common zero. `Summary` keeps two disjoint populations and no code path mixes them.

**Paired comparisons are paired.** The CoT-vs-tool-use and raw-vs-delimited gaps are
differences *on the same instances*. `compare()` matches on every axis except the one
under test, discards anything unpaired and reports how many pairs survived. Comparing
group means instead would let a refusal that dropped a hard instance from one arm improve
that arm's mean for free — and be reported as a paradigm effect.

**Baseline vs isomorph cannot be paired, and says so.** The two sides are different
instances by construction; that is the experiment. Pairing would require pretending K1
corresponds to some particular synthetic Quagmire.

Refusals and errors stay harness outcomes, excluded from every mean. An unpriced model
reports no cost rather than a free one — a run that silently cost nothing is the number
nobody double-checks.

### Requested model vs answering model

Server-side fallback re-runs a declined request on a substitute, and the attempt recorded
only the substitute. A fallback's answer would therefore have been filed under whichever
model refused, putting another model's score in its column — in the headline comparison
specifically. The two are now separate fields: **scores group by the model requested, cost
bills the model that answered**, and any divergence is reported rather than absorbed.
Results schema moved to v2, and an unrecognised version is refused rather than
reinterpreted, since a field that changed meaning yields a plausible number from
incompatible data.

---

## Phase 6 — Running it

The roadmap built a benchmark that measures. This phase is about actually measuring, and
it starts with the two risks below that are still estimates rather than data: the tier
thresholds are uncalibrated, and the cost of the full matrix is a guess.

- [x] Runner controls for a long run — `--resume`, `--max-spend`, `--concurrency`
- [x] A second provider — any OpenAI-compatible endpoint behind `--provider openai`
      and `--base-url`, sharing one prompt builder and one answer parser with Claude
- [x] Confidence intervals on every reported mean, and overlap stated in words
- [x] An agent skill that drives the whole flow — `.claude/skills/kryptos-benchmark/`
- [ ] A sized pilot: one model, `--limit 5`, all five configs, to get real cost per
      instance and a first look at the score distribution
- [ ] Calibrate the tier thresholds against that distribution, replacing the asserted
      0% / 5% / 10%
- [ ] The full matrix, once the pilot says what it costs

### Why the controls are counted rather than clocked

The obvious way to bound a long run is a time limit, and it is wrong here. Stopping on a
clock cuts each config at an arbitrary point, so the baseline and isomorph means would
cover different-sized samples — the exact comparison `report.py` refuses to make
everywhere else. Two runs of "four hours" are not comparable to each other either.

Eval harnesses standardise on item count plus resumability instead, and that is what
landed: a fixed instance set, `--limit` to size it, and an append-only results file that
`--resume` reads to skip what is already answered. A wall-clock cap is legitimate as a
kill switch, not as the definition of a run — and killing a run is now safe, because
interrupting writes what completed.

Two details that are easy to get wrong and are documented in the code rather than left to
be discovered. `--resume` keys on the same identity the reporting layer dedupes by,
computed by handing a synthetic record to `report.identity()` — assembling that tuple
separately would let the two drift, and a drifted resume either re-runs everything or
skips work it never did. And `--max-spend` is soft: dispatch stops when the ceiling is
crossed, but work already in flight finishes, so a parallel run can exceed it by up to
`--concurrency` instances.

### One prompt, two APIs

A second vendor is the easiest way to break the benchmark's central claim without noticing,
because nothing errors when two models are asked subtly different questions. The split is
therefore narrow: `tiers` builds both prompts, `paradigms` decides what a paradigm means,
and `providers` does nothing but carry two strings to an API. A test asserts the two
backends receive **byte-identical** system and user text, and both share one answer parser
— a per-provider parser could be more forgiving of one vendor's output than another's, and
that difference would read as a capability gap.

Two limits are enforced rather than papered over. **Tool use raises on OpenAI** instead of
silently running chain of thought, because a mislabelled run would land as a finding that
the tool-use gap had closed. And **effort recorded is effort sent**: the OpenAI ladder
collapses `xhigh`/`max` to `high` and `--no-reasoning-effort` drops the field entirely, so
the record says `unset` rather than echoing a level nothing was told about. Results schema
moved to v3 for that meaning change.

Non-Claude models are **unpriced**, which makes the cost table say so and `--max-spend`
refuse to run. `--price MODEL=IN/OUT` supplies the missing rate; a rate nobody typed is a
rate nobody checked.

### Reporting what other benchmarks report

Means now carry a 95% confidence interval, and every paired comparison states in words
whether the two intervals overlap. The headline result is a *difference* between two means,
and at pilot sample sizes a few points of gap is almost always noise — a bare `+4.2%` gets
quoted, `intervals overlap -- not a distinguishable gap` does not.

### Haiku 4.5 will not run on this harness

`paradigms.solve` sends `thinking: {"type": "adaptive"}` and `output_config.effort`, and
Haiku 4.5 accepts neither — it is a pre-4.6 model that still takes
`thinking: {"type": "enabled", "budget_tokens": N}`. Running the cheapest model therefore
needs a per-model capability shim in the request builder, not a flag. Deferred: Sonnet 5
runs unmodified and bills at an introductory $2/$10 per MTok through 2026-08-31, which
makes the saving from Haiku small against the cost of building and testing that shim.

Two smaller limits, for whenever the batch path is worth taking: the Batches API halves
token cost but **rejects the `fallbacks` parameter**, and server-side tool use does not
fit it (there is no `pause_turn` resume loop). Batch would serve chain-of-thought only.

---

## Phase 7 — Classical cipher suite

Target: `src/kryptos/algorithms/suite/`

Everything above measures two cipher families through four framings. That answers *can a
model break Quagmire III*, and it answers it as a cliff: a model either has the mechanism
or it does not. What it cannot produce is a **difficulty curve** — the ordering of what a
model breaks, what it half-breaks, and where it stops — because there is nothing between
Quagmire and K4 to stand on.

This phase adds that curve as **sibling configs, not a replacement**. The Kryptos configs
carry the contamination-resistance claim, which rests on isomorphs of a famous artifact;
the suite is contamination-free by a different and weaker mechanism, namely that a
randomly-keyed Playfair over recombined prose has never existed before. Two different
claims. They are reported separately and never averaged into one number — a blended score
would inherit the weaker of the two guarantees while wearing the name of the stronger.

Phase 3's corpus, Phase 2's scoring and Phase 4–6's harness are reused unchanged. None of
`kryptos.scoring` knows what Kryptos is, and `results.score(row, attempt)` is already
row-driven, so this phase adds ciphers and a difficulty pipeline, not a second harness.

### 7.1 Decision gates 🚩 three open

- [ ] 🚩 **How do 15 ciphers share one schema?** The rule that split `isomorph_composite`
      from `isomorph_nulls` — no config may publish a column that is null on most of its
      rows — does not survive fifteen ciphers in four difficulty configs. A Playfair
      square, a Hill matrix and a rail-fence depth have no common shape.
      *Proposed:* one `parameters` list-of-struct field, `[{name, value}]`, both strings,
      uniform across every cipher and empty for none. Declared as a plain Python list, not
      `Sequence({...})`, which inverts a struct into a struct-of-lists and fails the cast.
      `solution` prose stays machine-generated from those parameters, so the readable path
      is unchanged
- [ ] 🚩 **What defines a difficulty band?** *Proposed:* solver crack rate at a fixed
      compute budget, measured per instance, with unicity distance as a separate validity
      gate. See below — the two do different jobs and conflating them is the failure mode
- [ ] 🚩 **Which 15 mechanisms, and how many instances each?** *Proposed inventory below.*
      The count that matters is instances per band per mechanism, since that is what sets
      the width of a per-cipher confidence interval

### Difficulty is measured, not declared

A hand-labelled `brutal` row is indistinguishable from a broken one: both score 0 on every
model. The band therefore has to come from something computable before any model runs.

**Unicity distance gates validity.** Below `H(K) / D` characters — key entropy over
English redundancy at roughly 3.2 bits per letter — more than one plaintext decrypts the
instance consistently, and there is no unique answer to score against. This is a low
floor, and saying so is the point: simple substitution is log₂(26!) ≈ 88 bits, so
U ≈ 28 characters; Playfair is log₂(25!) ≈ 84 bits, so U ≈ 26. Every realistic instance
clears it. It rejects the pathological short ones and ranks nothing.

**Solver crack rate assigns the band.** Run a classical attack against the instance with a
fixed budget and record whether it recovers the plaintext, over N seeded restarts:

| Band | Criterion |
|---|---|
| easy | small enough keyspace to brute-force, or cracked on every restart in under a second |
| medium | a known statistical attack applies (Kasiski, IC, frequency) and cracks ≥ 90% of restarts |
| hard | cracks between 10% and 90% of restarts |
| brutal | cracks < 10%, **and** the instance clears unicity and round-trips |

The `brutal` band is defined so that it can only contain instances that are known to be
solvable in principle. That is the whole reason for the unicity gate: without it, "no
solver cracked this" and "this has no answer" are the same observation.

Hill-climbing against the quadgram model in `kryptos.scoring.ngram` is the workhorse
attack and already exists. What this phase adds is the restart harness around it and the
per-mechanism attacks — Kasiski and IC for periodic polyalphabetics, brute force where the
keyspace admits it.

**Difficulty is a property of the instance, not the cipher.** `(mechanism, length, key)`
determines it jointly: Playfair at 500 characters is a different problem from Playfair at
90, and a Vigenère whose keyword repeats has a shorter true period than its length
suggests. A mechanism therefore appears in **several bands**, with length as the primary
lever. Stamping each cipher with one difficulty would throw away the most informative axis
in the set.

**What the bands do and do not claim.** They measure *classical cryptanalytic* difficulty.
Whether that ordering predicts *model* difficulty is an open empirical question, and one
this suite exists to answer rather than assume — a model may find a rail fence hard for
tokenization reasons that have nothing to do with its keyspace. The card must say so.

### 7.2 Mechanism inventory

Fifteen classes chosen for mechanistic distinctness, not headcount. Vigenère, Beaufort,
Variant Beaufort and Gronsfeld are one mechanism reparameterized — a model that breaks one
breaks all four — so only Vigenère is carried, and the near-variants are worth at most a
single recognition probe later. Four already exist from Phases 1 and 3 and are reused.

| Class | Mechanism | Expected band(s) |
|---|---|---|
| Monoalphabetic | Caesar, Affine, simple substitution, homophonic | easy → brutal |
| Polyalphabetic | Vigenère ✅, Quagmire III ✅, autokey, running key | medium → brutal |
| Polygraphic | Playfair, four-square, Hill ✅ | hard |
| Fractionating | Bifid, trifid, ADFGVX | hard → brutal |
| Transposition | Rail fence, keyed columnar, route ✅ | easy → hard |

Expected bands are a prior, not an assignment; 7.4 overwrites them with what the solver
actually measured. Homophonic and running key are the two most likely to land in `brutal`
for the reason that makes them interesting — both flatten the statistics the standard
attacks depend on.

### 7.3 Solvability instrumentation

- [ ] `suite/unicity.py` — key entropy per mechanism and the redundancy constant, with the
      derivation in the docstring rather than a bare number
- [ ] `suite/solvers/` — hill-climb and simulated-annealing drivers over the existing
      quadgram model, plus per-mechanism attacks and brute force where the keyspace admits
- [ ] `suite/difficulty.py` — the restart harness that turns an instance into a crack
      rate and a band, deterministic given a seed
- [ ] Solver budget fixed and recorded per instance, not per run. A band measured against
      a budget nobody wrote down is a band nobody can reproduce

### 7.4 Generators and selection

- [ ] Eleven new ciphers under `algorithms/ciphers/`, same contract as the existing four:
      `encrypt`/`decrypt` inverse over uppercase, degeneracy hooks for the generator to
      screen against
- [ ] Generate a **pool** larger than the published set, sweeping length per mechanism, so
      the bands are filled by selection rather than by hoping the draw lands evenly
- [ ] Measure every pooled instance, then select a balanced sample per band
- [ ] Keys drawn from the corpus vocabulary, as in 3.3 — Kryptos keys on real words, and
      random letter strings would make the keyword-guessing sub-problem disappear

### 7.5 Verify

- [ ] Every published instance round-trips on its own published `parameters` — the same
      standard as 3.4, driven by nothing retained from generation
- [ ] Every instance clears its mechanism's unicity distance
- [ ] Same seed, byte-identical output, bands included
- [ ] Band assignment reproduces from the recorded solver budget

### 7.6 Publish

- [ ] Four sibling configs — `suite_easy`, `suite_medium`, `suite_hard`, `suite_brutal` —
      in the existing Hub repo, reusing `kryptos.huggingface.push` and its two-way
      preflight
- [ ] Card sections stating the weaker contamination claim, the solver-measured provenance
      of every band, and that the ordering is classical rather than model difficulty
- [ ] Per-row `cipher_name`, `cipher_family`, `difficulty`, `unicity_distance`,
      `solver_crack_rate`, `solver_budget` — so a reader can re-derive the band

### Sizing this before it is built

The four axes already multiply: 204 instances × 4 tiers × 2 paradigms × 2 presentations is
roughly 3,300 calls for a full sweep. Adding ~240 suite instances takes that past 7,000,
and at Sonnet 5's introductory $2/$10 per MTok — assuming 5k in and 3k out per call, both
**assumptions and not measurements** — a full sweep lands in the low hundreds of dollars.
Chain of thought with adaptive thinking will exceed 3k output tokens on the hard bands.

So the suite ships with a **default slice**: one tier, one paradigm, raw presentation. The
full cross stays opt-in and stays behind `--max-spend`. The pilot in Phase 6 still has to
run first — it is what replaces the two assumptions above with token counts, and no part
of this phase should be sized against a guess when a measurement is one run away.

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
- **The suite's difficulty bands may not order model difficulty.** They are measured
  against classical attacks, and a model is not a hill-climber. If observed scores come out
  uncorrelated with the bands, that is a finding worth publishing, not a bug to tune away —
  but the card has to have promised only what was measured, or the finding reads as a
  broken dataset instead.
- **The suite has a weaker contamination guarantee than the isomorphs.** Novel-by-generation
  is not the same claim as isomorph-of-a-famous-artifact, and a blended headline score would
  quietly inherit the weaker one. Reported separately, never averaged.
