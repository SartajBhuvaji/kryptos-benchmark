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

Published privately to the Hub as
[`sartajbhuvaji/kryptos-bench`](https://huggingface.co/datasets/sartajbhuvaji/kryptos-bench).

## Baseline dataset

The four Kryptos passages exactly as carved, one record per passage. Published to the
HuggingFace Hub as the `baseline` config of the `kryptos-benchmark` dataset, so it is
authored in Hub-compatible form and `src/kryptos/dataset/` can be uploaded as-is.

Field naming follows established benchmarks — `problem` / `solution` / `answer`, as in
MATH-500 — and problem is separated from ground truth by field grouping rather than by
separate files, which is what every major benchmark does. `INPUT_FIELDS` and
`GROUND_TRUTH_FIELDS` in `schema.py` make that split machine-readable so a harness never
has to hardcode column names.

See [`src/kryptos/dataset/README.md`](src/kryptos/dataset/README.md) for the schema,
scoring rules, and the transcription-verification argument.

## Layout

`src/kryptos/dataset/` is the HuggingFace dataset repository root: the card plus one
directory per config. It holds no code. Everything else lives under
`src/kryptos/algorithms/`.

```
src/kryptos/dataset/README.md          HuggingFace dataset card
src/kryptos/dataset/baseline/          the baseline config: test.jsonl
src/kryptos/algorithms/baseline/       source text, schema and builder for that config
src/kryptos/algorithms/                cipher implementations (not yet started)
src/kryptos/huggingface/               Hub publishing, with preflight checks
tests/                                 verification
docs/                                  design documents
```

## Development

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest                                     # verification suite
.venv/bin/python src/kryptos/algorithms/baseline/build.py --check      # artifact matches its source
.venv/bin/python src/kryptos/algorithms/baseline/build.py              # regenerate

.venv/bin/python -m kryptos.huggingface.push --dry-run          # check, upload nothing
.venv/bin/python -m kryptos.huggingface.push                    # publish (private)
```

Publishing runs preflight first and refuses to upload if the committed artifact is stale,
the card's declared config paths do not resolve, the card metadata fails the Hub's
validation, or the data does not load against its declared features. `--public` is never
the default: visibility is hard to walk back once anything has crawled or mirrored it.

```bash
```

`build.py` is deterministic; the generated artifact is committed so consumers need not run
anything.
