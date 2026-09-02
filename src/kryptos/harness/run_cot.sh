#!/usr/bin/env bash
# The chain-of-thought arm: every config, one invocation each, against an
# OpenAI-compatible endpoint.
#
#   bash src/kryptos/harness/run_cot.sh [RESULTS_DIR]
#
# Run from the repo root, with the endpoint reachable at BASE_URL. If the model is
# served on a remote GPU box, open the tunnel first -- port 8000 is firewalled from the
# public internet there, so it is not optional:
#
#   ssh -i ~/.ssh/lambda_glm -N -L 8000:localhost:8000 ubuntu@<INSTANCE_IP>

set -euo pipefail

MODEL="${MODEL:-GLM-4.6-Flash-text}"
BASE_URL="${BASE_URL:-http://localhost:8000/v1}"
RESULTS="${1:-$MODEL/results}"
CONCURRENCY="${CONCURRENCY:-24}"
PYTHON="${PYTHON:-python3}"

# vLLM does not check the key unless it was started with --api-key, but the benchmark
# refuses to run with no key at all rather than send an empty credential. A key is never
# passed as an argument -- it would sit in shell history and be visible to `ps`.
export VLLM_API_KEY="${VLLM_API_KEY:-EMPTY}"
export PYTHONPATH="${PYTHONPATH:-src}"

# Why --provider-param max_tokens is required here:
#
# kryptos.eval.paradigms.solve() hardcodes max_tokens=32000 and there is no CLI flag for
# it. Against a 32768-token context that is unsatisfiable the moment a prompt is added,
# and vLLM rejects every request. --provider-param merges into the raw request body last
# (providers.OpenAIBackend does `request.update(self.extra)`), so it wins.
#
# 8192 is also just the right size: answers on this model run ~150 tokens, and anything
# past ~1000 is a degenerate generation that gets truncated into `unparsed_response`.
# Lowering it further would cut the long tail that dominates wall clock.
MAX_TOKENS="${MAX_TOKENS:-8192}"

# Effort. vLLM 0.28 genuinely validates `reasoning_effort` -- a bogus value returns 400
# naming the accepted levels -- so it is sent and recorded as `effort: high`. Set
# NO_REASONING_EFFORT=1 for a server that rejects it, or to pair this arm against the
# agentic arm, which sends no effort field and records `effort: unset`. report.compare()
# needs every non-varied IDENTITY axis to match, and effort is one of them.
EFFORT_FLAG=""
[ "${NO_REASONING_EFFORT:-0}" = "1" ] && EFFORT_FLAG="--no-reasoning-effort"

CONFIGS=(baseline isomorph_quagmire isomorph_transposition isomorph_composite isomorph_nulls)

mkdir -p "$RESULTS"
echo "cot arm -> $RESULTS  (model $MODEL, concurrency $CONCURRENCY, max_tokens $MAX_TOKENS)"

for cfg in "${CONFIGS[@]}"; do
  echo
  echo "############ $cfg $(date -u +%H:%M:%S) ############"
  # --resume skips instances already answered and retries refusals and errors, so this
  # script is safe to re-run: an interrupted arm continues instead of duplicating work.
  "$PYTHON" -m kryptos.eval.run_benchmark \
    --config "$cfg" \
    --model "$MODEL" \
    --provider openai \
    --base-url "$BASE_URL" \
    --api-key-env VLLM_API_KEY \
    --paradigm cot \
    --concurrency "$CONCURRENCY" \
    --provider-param "max_tokens=$MAX_TOKENS" \
    --out "$RESULTS/$cfg.jsonl" \
    --resume \
    $EFFORT_FLAG
done

echo
echo "done. analyse with:"
echo "  python src/kryptos/harness/analyze.py --results $RESULTS --wall-clock <seconds>"
