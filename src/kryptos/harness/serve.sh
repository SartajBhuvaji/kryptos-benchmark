#!/usr/bin/env bash
# Serve the model with vLLM. Run this ON the GPU instance.
#
# Both exports below are load-bearing. A bare `vllm serve` starts, accepts a request,
# and then dies on the first generated token:
#
#   vLLM 0.28 pulls in flashinfer, whose sampler JIT-compiles the first time it runs.
#   That compile needs `ninja`, which pip installed *inside* the venv -- not on PATH
#   when the binary is exec'd directly. Fixing PATH alone only moves the failure one
#   step later, into an nvcc build, where the system nvcc (12.8) mismatches the CUDA
#   torch was built against (13.0). Disabling the flashinfer sampler is what actually
#   avoids it.
#
# Restart with this script, never a bare `vllm serve`.

set -euo pipefail

export PATH="$HOME/venvs/vllm/bin:$PATH"
export VLLM_USE_FLASHINFER_SAMPLER=0

MODEL="${MODEL:-sartajbhuvaji/GLM-4.6-Flash-text}"
SERVED_NAME="${SERVED_NAME:-GLM-4.6-Flash-text}"
PORT="${PORT:-8000}"
GPU_UTIL="${GPU_UTIL:-0.92}"

# Context window. Pick by arm:
#
#   32768   the chain-of-thought arm. One request, one short answer; anything larger
#           just reserves KV nothing will use.
#   131072  the agentic arm (default). Multi-turn transcripts carry every code block
#           and its stdout, so they outgrow 32k quickly, and the point of that arm is
#           to let the model reason at length.
#
# The KV arithmetic, measured on a 40 GB A100 at GPU_UTIL=0.92: weights take 18.8 GB,
# leaving 17.31 GiB of cache = 453,728 tokens. This model is GQA with 2 KV heads over
# 40 layers at head_dim 128, so KV costs 40 KB/token and a full-length 131072-token
# sequence costs 5.24 GB -- vLLM reports 3.46x concurrency at that length. The agentic
# arm runs 1-2 at a time, so that is ample. At 32768 the same cache gives ~13.8x.
MAX_MODEL_LEN="${MAX_MODEL_LEN:-131072}"

echo "serving $MODEL as $SERVED_NAME on :$PORT (ctx $MAX_MODEL_LEN, util $GPU_UTIL)"

exec vllm serve "$MODEL" \
  --served-model-name "$SERVED_NAME" \
  --host 0.0.0.0 --port "$PORT" \
  --max-model-len "$MAX_MODEL_LEN" \
  --gpu-memory-utilization "$GPU_UTIL" \
  --dtype bfloat16
