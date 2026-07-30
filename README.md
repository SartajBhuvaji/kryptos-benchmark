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
| baseline dataset | four authentic passages, verified |
| isomorph generators | not started |
| cipher implementations | not started |
| scoring (CER / Levenshtein) | not started |

## Baseline dataset

The four Kryptos passages exactly as carved, one record each. Destined for the
HuggingFace Hub, so it is authored in Hub-compatible form: a single `test` split at
`src/dataset/baseline/data/test.jsonl` with a dataset card alongside it.

See [`src/dataset/baseline/README.md`](src/dataset/baseline/README.md) for the schema,
scoring rules, and the transcription-verification argument.

## Layout

`src/dataset/` holds datasets only — the artifact and its card, nothing else, so a
dataset directory can be uploaded to the Hub as-is. All code lives under
`src/algorithms/`.

```
src/dataset/baseline/     the dataset: data/test.jsonl + HuggingFace card
src/algorithms/baseline/  canonical source text, schema and builder for that dataset
src/algorithms/           cipher implementations (not yet started)
tests/                    verification
docs/                     design documents
```

## Development

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest                                     # verification suite
.venv/bin/python src/algorithms/baseline/build.py --check      # artifact matches its source
.venv/bin/python src/algorithms/baseline/build.py              # regenerate
```

`build.py` is deterministic; the generated artifact is committed so consumers need not run
anything.
