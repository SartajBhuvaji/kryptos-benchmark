# Harness

Everything needed to run a self-hosted model against the benchmark and get scored
results back. Written against `sartajbhuvaji/GLM-4.6-Flash-text` on a Lambda A100, but
nothing here is specific to that model beyond the defaults.

There are two arms, and they measure different things:

| Arm | What the model gets | Driver |
|---|---|---|
| **cot** | one request, strict JSON answer, no tools | `run_cot.sh` → `kryptos.eval.run_benchmark` |
| **agentic** | a sandboxed Python interpreter and as many turns as its budget allows | `agentic_solve.py` |

The agentic arm exists because `kryptos.eval.providers` refuses `--paradigm tool_use` on
the OpenAI wire format — it raises rather than quietly running chain of thought and
labelling it tool use. This is a prototype of the container backend that module's
docstring anticipates, kept outside `providers.py` until the loop is proven on real rows.

## Files

```
serve.sh           launch vLLM on the instance
deploy.sh          ship this package to an instance, install deps, verify the sandbox
run_cot.sh         the chain-of-thought arm, every config
agentic_solve.py   the agentic arm, one instance at a time
analyze.py         charts, run_metadata.json and SUMMARY.md from a finished run
compare_arms.py    cot vs tool_use, with a confabulation check and a zero-pair guard
```

## 1. Provision

Use `unfuse/tools/launch_lambda.sh`, which already defaults to `gpu_1x_a100_sxm4`:

```bash
cd ../unfuse
NAME=kryptos-glm bash tools/launch_lambda.sh launch
```

Two things that script exists to protect you from, both silent:

- **`POST /ssh-keys` with a null `public_key` does not error.** Lambda generates its own
  keypair and returns the private half in the response body. Discard that response and
  you have an instance nobody can ever log into — `ssh_key_names` is fixed at launch, so
  the only fix is terminate and relaunch. `verify_key()` compares the stored key against
  your local `.pub`; if it prints FATAL, stop.
- **A `.env` saved on Windows carries CRLF**, which leaves a trailing `\r` on the key and
  makes a perfectly good key fail as `global/invalid-api-key`. Always source it as
  `. <(sed 's/\r$//' .env)`. Applies to `HUGGINGFACE_TOKEN` too.

Capacity is volatile — check `regions_with_capacity_available` from `/instance-types`
before planning anything.

## 2. Deploy and serve

```bash
bash src/kryptos/harness/deploy.sh <INSTANCE_IP>          # from the repo root
ssh -i ~/.ssh/lambda_glm ubuntu@<INSTANCE_IP> \
  'nohup bash ~/kryptos-benchmark/src/kryptos/harness/serve.sh > ~/vllm.log 2>&1 &'
```

`deploy.sh` ships the package, installs `datasets` and `rapidfuzz` into the vLLM venv,
and runs the sandbox self-check. It fails loudly if the sandbox is not usable.

Set `MAX_MODEL_LEN=32768` for the cot arm; the default 131072 is for the agentic arm,
whose multi-turn transcripts outgrow 32k.

**The SSH tunnel is mandatory, not a convenience.** Port 8000 is firewalled from the
public internet on these instances — a direct `curl` to the IP times out. Leave this
open in its own terminal for as long as you are running anything:

```bash
ssh -i ~/.ssh/lambda_glm -N -L 8000:localhost:8000 ubuntu@<INSTANCE_IP>
```

Lambda's hosted Jupyter is not an alternative. Its proxy rejects programmatic access:
`POST /api/kernels` fails XSRF even with the token in both header and query string, and
the contents API refuses hidden paths. Drive the box over SSH.

## 3. Run

**cot arm** — from the repo root, with the tunnel open:

```bash
bash src/kryptos/harness/run_cot.sh GLM-4.6-Flash-text/results
```

Safe to re-run: `--resume` skips instances already answered and retries refusals and
errors, so an interrupted arm continues rather than duplicating work.

**agentic arm** — runs *on* the instance, so the sandbox is local to a disposable VM and
the model call never leaves localhost:

```bash
ssh -i ~/.ssh/lambda_glm ubuntu@<INSTANCE_IP>
cd ~/kryptos-benchmark
~/venvs/vllm/bin/python src/kryptos/harness/agentic_solve.py \
  --config baseline --instance kryptos-baseline-k1 --tier 1 \
  --token-budget 32000 --turn-limit 12 \
  --out results-agentic/k1-tier1-32k.jsonl
```

## 4. Analyse

```bash
python src/kryptos/harness/analyze.py --results GLM-4.6-Flash-text/results --wall-clock 619
```

This executes the notebook's own analysis cells rather than reimplementing them, so the
committed charts and `SUMMARY.md` are what someone gets by opening the notebook and
running it. Verified: consecutive runs are byte-identical apart from the regenerated
timestamp. Drop `gpu_env.json` in the results directory (from
`unfuse/tools/gpu_env.sh --json`, with `PYTHON=~/venvs/vllm/bin/python`) and the machine
travels with the score.

## Stopping criteria for the agentic arm

There is no single convention. The practice is several simultaneous caps, with the
protocol reported next to the score — SWE-Bench Pro caps turns at 50–250, Terminal-Bench
caps wall clock at 10 min to 3.3 h. "How Inference Compute Shapes Frontier LLM
Evaluation" (arXiv 2606.17930) argues that a single fixed-budget number increasingly
understates capability, and that results should be reported *as a function of* inference
compute. So the budget is a parameter meant to be swept, not a constant.

| Cap | Default | Guards against |
|---|---|---|
| generated tokens per instance | 64,000 | the real budget |
| tool-call turns | 20 | tight loops that burn few tokens |
| wall clock per instance | 1,200 s | a hung sandbox |
| the agent's own `answer` block | — | it decides it is done |

Whichever fires is recorded in `stop_reason`, alongside `token_budget`, `turn_limit` and
`wallclock_limit` on every record. **A score is not comparable across budgets**, so the
budget travels with it. Token budget is the primary criterion because it is
hardware-independent — wall clock would make the same run score differently on a faster
GPU.

## The agentic scaffold

**Agentic scores are scaffold-dependent.** The same model at the same budget scores
differently under a different loop, which is why SWE-bench numbers are quoted per
scaffold. `SCAFFOLD_VERSION` is recorded on every result; a number that does not name its
scaffold is not reproducible. Current version is **2**.

The scaffold is protocol, not task. The benchmark's own task framing —
`tiers.system_prompt()` plus `tiers.build_prompt()` — is passed through untouched, so
these runs stay comparable to any other model at the same tier. Everything below governs
*how the model works*, never what the answer is.

**v2 drops the benchmark's few-shot example** (`system_prompt(tier, few_shot=False)`).
`FORMAT_EXAMPLE` demonstrates a toy problem going straight to a JSON answer — correct for
a single-shot chain-of-thought request, and precisely the wrong demonstration in a tool
loop. Under v1, which kept it, the model reasoned for 10,202 tokens, ran no code at all,
and submitted on turn one: exactly the shape the example teaches. `AGENT_EXAMPLE` replaces
it with a worked *session* — brute-force a Caesar in code, print the shifts, read the
plaintext out of stdout, then answer. Caesar for the same reason the benchmark chose it:
every instance here is Quagmire, transposition, nulls or a composite, so it cannot hint.

**v4 guarantees an answer, and sizes the per-turn cap between two failures.**

`--max-tokens-per-turn` was tuned by getting it wrong twice. At its original 16000, one
degenerate turn -- prose, no code block, no answer -- consumed 65% of a 32k budget before
the loop could nudge it. Dropping it to 6000 produced the opposite failure: five
consecutive turns at *exactly* 6000 tokens, every generation truncated mid-thought, six
code executions, and no convergence. 8000 sits between them. `finish_reason` is now
recorded per turn, so "hit the cap" appears in the data instead of having to be inferred
from suspiciously round token counts.

The worse half of that run was how it ended. Exhausting the budget left `plaintext`
empty, scored **CER 1.0** -- indistinguishable from a model that emitted pure garbage, and
strictly worse than the partial recovery its own code had already printed. So v4 holds
`FORCE_ANSWER_RESERVE` (4000 tokens) back from the budget and spends it on one final turn
asking for the best plaintext the code actually produced, explicitly forbidding new
analysis or invented text. The same reserve guards the turn and wall-clock limits.

Two details this depends on: the verify-before-submit gate is bypassed during the forced
turn -- otherwise it could reject the last answer and still end empty -- and
`forced_answer` is recorded, because an answer extracted at the budget wall is a weaker
claim than one the model volunteered.

**v3 requires round-tripping the implementation.** On K1 at tier 1 -- cipher name and
complete key supplied, nothing to discover -- v2 wrote a Quagmire III decryptor that
indexed into the keyed alphabet but emitted from the standard one:

    plaintext_chars.append(chr(plaintext_pos + 65))        # what it wrote
    plaintext_chars.append(keyed_alphabet[plaintext_pos])  # CER 0.0000

That single substitution recovers the passage exactly. The model ran its code, saw
gibberish, said so ("Wait, that seems like gibberish. Did I implement the Quagmire III
correctly?"), reasoned for 16,000 tokens, and re-emitted the same bug. So v3 asks for the
encrypt direction as well, and for the candidate plaintext to be re-encrypted back to the
ciphertext before the answer is trusted. This is generic cryptanalytic practice and names
no cipher, no alphabet and no key -- it leaks nothing, it just refuses to trust an
implementation that was never tested.

**v2 requires the sandbox to have been used.** An `answer` block submitted with zero
executions is pushed back once, with a note that the plaintext was not read out of program
output. An answer with no code behind it is a chain-of-thought answer wearing a
`tool_use` label, and recording it as the latter would fake the paradigm gap the benchmark
exists to measure. `verified_by_code` on each record says whether code ran before the
answer.

The other v2 rules all target confabulation, which is this model's dominant failure mode —
fluent English bearing no relation to the ciphertext: first message must be a `python`
block; never submit a plaintext your code did not print; verify by decrypting and reading;
do not copy the worked example; if stuck, submit real partial output rather than an
invented sentence. Each turn also echoes `Turn n/N, ~k generated tokens left` so the model
can pace itself against the budget.

## Gotchas

**An `answer` block can hide a `python` block behind it.** Scaffold v1 dispatched on
whichever block *type* it tested first (`if answer:` before `if code:`), so a message
containing code followed by an answer had its code silently dropped and the answer taken —
making a model that did use the sandbox look like one that never touched it. v2 dispatches
on block *position*. The lesson generalises: when a message can carry two kinds of
instruction, order by where they appear, not by the order you happen to check them. v1 also
stored the raw text only on turns already classified as code, so afterwards there was no
way to tell which had happened; `had_code_block`, `had_answer_block` and `visible` are now
recorded on every turn regardless of branch.

Things that cost real time here. None of them announce themselves.

**A bare `vllm serve` crashes on the first generated token.** vLLM 0.28 pulls in
flashinfer, whose sampler JIT-compiles on first use and dies with
`FileNotFoundError: 'ninja'` — pip put `ninja` inside the venv, which is not on `PATH`
when the binary is exec'd directly. Fixing only `PATH` moves the failure one step later
into an `nvcc` build, where the system nvcc (12.8) mismatches the CUDA torch was built
against (13.0). Both `export PATH=...` and `export VLLM_USE_FLASHINFER_SAMPLER=0` are
required; `serve.sh` carries them.

**`unshare -rn` does not work on Ubuntu 24.04.** AppArmor blocks unprivileged user
namespaces (`kernel.apparmor_restrict_unprivileged_userns=1`), so it fails with
`write failed /proc/self/uid_map: Operation not permitted`. The sandbox instead creates
the namespace with `sudo unshare -n` and drops straight back to uid 1000 with `setpriv`,
which is preferable to relaxing that sysctl and weakening the whole host.

**The isolation check must assert both halves.** Verifying only that a network probe
failed passes trivially on a sandbox so broken it cannot execute anything at all — which
is exactly the state `unshare -rn` lands in here. That version of the check would have
turned every instance into a silent zero attributed to the model. `check_sandbox_isolation()`
requires a sentinel from a real execution *and* an unreachable network, and aborts otherwise.

**Strict `json_schema` suppresses thinking entirely.** The grammar constrains generation
from token 0, so the model never emits its `<think>` block — the chat template has
thinking on by default, and it simply cannot get there. This is why the cot arm produced
~150 tokens of fluent confabulation per instance, including one answer that recycled the
few-shot example's own plaintext. The agentic arm therefore runs completely
unconstrained and parses the answer out of a fenced block client-side, which also avoids
depending on vLLM shipping a tool parser that matches this model's format (0.28 ships
GLM-4.7-MoE adapters; this is GLM-4.6).

**`reasoning_effort` is accepted, not ignored.** vLLM 0.28 genuinely validates it — a
bogus value returns HTTP 400 naming the accepted levels, whereas an unknown field would
be silently dropped with a 200. It appears inert for this model regardless (~150-token
answers either way), but it is sent and recorded as `effort: high`, which is honest about
the request.

**The two arms do not pair for a paradigm comparison as run.** `report.compare()` pairs
on `IDENTITY` minus the varied axis, so `cot` vs `tool_use` requires `instance_id`,
`tier`, `requested_model`, `delimited` **and `effort`** to match. The cot arm recorded
`effort: high`; the agentic loop sends no effort field and honestly records
`effort: unset`. Those do not match, so `compare()` returns **zero pairs and reports
nothing** rather than erroring. To get a clean comparison, run the cot arm with
`NO_REASONING_EFFORT=1` so both sit at `effort: unset`, and pose the agentic arm at each
row's default tier rather than an overridden one.

## CER alone rewards confabulation

Worth knowing before any of these numbers are quoted. On K1 the scores ran *backwards*
against the quality of the work:

| arm | submitted plaintext | CER | quadgram fitness |
|---|---|---|---|
| ground truth | `BETWEENSUBTLESHADING…` | 0.000 | -4.42 |
| cot | `IDONTKNOWWHATTHEHELLISGOINGON` | **0.762** | -4.02 |
| agentic v1 (no code run) | gibberish | 0.873 | -7.92 |
| agentic v2 (real decryption) | 63 real chars | **0.905** | -7.43 |

The chain-of-thought arm invented a fluent English sentence and *beat* a genuine failed
decryption, because English letter distributions overlap the English reference regardless
of whether the answer is right. A model that bluffs will out-score one that shows real
work and fails.

Quadgram fitness separates the two cleanly -- invented English sits near -4, a failed
decryption near -7.5 -- so `answer_fitness` and `answer_ioc` are recorded on every agentic
record **beside** CER and never folded into it. Changing the benchmark's scoring metric is
a design decision for the dataset owner, not something the harness should do quietly; this
just makes the failure mode visible in the data.

## Results layout

| directory | arm | few-shot | effort |
|---|---|---|---|
| `results/` | chain of thought, canonical | on | `high` |
| `results-cot-nofewshot/` | chain of thought, matched to the agentic arm | off | `unset` |
| `results-agentic/` | tool use | off (scaffold example instead) | `unset` |

`report.compare(records, "paradigm", "cot", "tool_use")` pairs on every IDENTITY axis
except the one under test, and `effort` is one of them -- so it pairs the *second* cot
directory against the agentic one. Pairing against `results/` returns zero pairs, silently,
because that arm ran at `effort: high`. Note also that few-shot is **not** an IDENTITY
axis, so mixing the two cot arms in one directory would hide a real difference rather than
record it; that is why they are separate directories.

## Measured, so nobody re-measures it

On `gpu_1x_a100_sxm4` (A100-SXM4-40GB, $1.99/hr), vLLM 0.28, bf16:

- **61.8 tok/s** single-stream decode — about 75% of the memory-bandwidth roof
  (18.8 GB of weights over 1555 GB/s ≈ 82 tok/s), so the serving path is healthy.
- **684 tok/s** peak at 23-way concurrency — roughly **11×** the single-stream rate.
  Batching is nearly free until KV runs out.
- KV cache is **453,728 tokens (17.31 GiB)**; this model is GQA with 2 KV heads over 40
  layers at head_dim 128, so **40 KB/token**. That is 3.46× concurrency at 131072
  context, ~13.8× at 32768.
- The full cot arm — **204 instances in 10.3 min for $0.34**, 87,774 in / 78,778 out.

Wall clock on the cot arm is dominated by a long tail, not the bulk: most instances
finish in seconds, then one or two stragglers generate alone toward the token cap. The
lever there is a lower `max_tokens`, not more concurrency.
