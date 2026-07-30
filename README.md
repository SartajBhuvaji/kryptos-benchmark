# Kryptos Benchmark

Evaluating large language models on classical cryptanalysis and character-level reasoning,
modelled on the Kryptos sculpture at CIA headquarters.

Testing a model directly on Kryptos measures memorisation, not cryptanalysis: K1–K3 and
their solutions are extensively documented and are certainly in every frontier model's
pre-training data. The project's answer is to generate **Kryptos-isomorphic** challenges —
the same algorithms, matrix transformations and constraints applied to novel plaintexts
under randomised keys — and to use the authentic passages as a memorisation control rather
than as the measurement.

See `docs/` for the full design.

## Status

| component | state |
|---|---|
| `src/dataset/baseline` | four authentic passages, verified |
| `src/dataset/*` isomorph generators | not started |
| `src/algorithms` | not started |
| scoring (CER / Levenshtein) | not started |

## Baseline dataset

The four Kryptos passages exactly as carved, one record each. Destined for the
HuggingFace Hub, so it is authored in Hub-compatible form: a single `test` split at
`src/dataset/baseline/data/test.jsonl` with a dataset card alongside it.

See [`src/dataset/baseline/README.md`](src/dataset/baseline/README.md) for the schema,
scoring rules, and the transcription-verification argument.

## Layout

```
src/dataset/baseline/     baseline dataset: source text, schema, builder, artifact, card
src/algorithms/           cipher implementations (not yet started)
tests/                    verification
docs/                     design documents
```

## Development

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest                                  # verification suite
.venv/bin/python src/dataset/baseline/build.py --check      # artifact matches its source
.venv/bin/python src/dataset/baseline/build.py              # regenerate
```

`build.py` is deterministic; the generated artifact is committed so consumers need not run
anything.
