#!/usr/bin/env bash
# Ship the benchmark package and this harness to a GPU instance, install what the
# agentic arm needs, and prove the sandbox works before anything is run on it.
#
#   bash src/kryptos/harness/deploy.sh <INSTANCE_IP> [SSH_KEY]
#
# Run from the repo root. The instance is expected to be a Lambda Stack box that
# already has a vLLM venv at ~/venvs/vllm (see README for provisioning).

set -euo pipefail

IP="${1:?usage: deploy.sh <INSTANCE_IP> [SSH_KEY]}"
KEY="${2:-$HOME/.ssh/lambda_glm}"
USER="${SSH_USER:-ubuntu}"
REMOTE_DIR="${REMOTE_DIR:-kryptos-benchmark}"
VENV="${VENV:-\$HOME/venvs/vllm}"

SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=no -o BatchMode=yes -o ConnectTimeout=20)

[ -f pyproject.toml ] || { echo "run this from the repo root" >&2; exit 1; }

echo "==> shipping src/kryptos to $USER@$IP:~/$REMOTE_DIR"
# tar over ssh rather than scp -r: it preserves the tree in one round trip and carries
# the committed corpora (quadgram tables, isomorph data) that the scoring code reads.
tar czf - src/kryptos pyproject.toml \
  | "${SSH[@]}" "$USER@$IP" "mkdir -p ~/$REMOTE_DIR && cd ~/$REMOTE_DIR && tar xzf - && \
      echo '    python files:' \$(find src -name '*.py' | wc -l) && \
      echo '    scoring data:' \$(ls src/kryptos/scoring/data/ | tr '\n' ' ')"

echo "==> installing agentic-arm dependencies into the vLLM venv"
# The package itself declares no runtime dependencies; these are what the eval and
# scoring paths need. Installed into the vLLM venv so one interpreter serves and scores.
"${SSH[@]}" "$USER@$IP" "$VENV/bin/pip install -q datasets rapidfuzz 2>&1 | tail -2; \
  $VENV/bin/python -c 'import datasets, rapidfuzz; print(\"    datasets\", datasets.__version__, \"| rapidfuzz\", rapidfuzz.__version__)'"

echo "==> verifying the code sandbox"
# Asserts both halves -- that code runs AND that egress is blocked. Aborts otherwise.
# A check that only confirmed the network probe failed would pass on a sandbox too
# broken to execute anything, turning every instance into a silent zero.
"${SSH[@]}" "$USER@$IP" "cd ~/$REMOTE_DIR && $VENV/bin/python -c '
import sys; sys.path.insert(0, \"src\")
from kryptos.harness.agentic_solve import check_sandbox_isolation, SANDBOX
check_sandbox_isolation()
print(\"    sandbox:\", \" \".join(SANDBOX))
'"

echo
echo "deployed. next:"
echo "  serve:  ssh -i $KEY $USER@$IP 'nohup bash ~/$REMOTE_DIR/src/kryptos/harness/serve.sh > ~/vllm.log 2>&1 &'"
echo "  tunnel: ssh -i $KEY -N -L 8000:localhost:8000 $USER@$IP"
