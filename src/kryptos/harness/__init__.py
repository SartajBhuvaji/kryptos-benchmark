"""Operational harness for running a served model against the benchmark.

Two arms live here. The chain-of-thought arm is `kryptos.eval.run_benchmark` driven by
`run_cot.sh` against an OpenAI-compatible endpoint; the agentic arm is
:mod:`kryptos.harness.agentic_solve`, which gives the model a sandboxed Python
interpreter and lets it iterate. The shell scripts alongside provision and serve the
model. See README.md for the operator guide.
"""
