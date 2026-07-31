# English quadgram frequency table

`english_quadgrams.txt.gz` is committed data, not something this repository derives.
`build.py` reproduces it; this file records where it came from and what it contains.

## Source

| | |
|---|---|
| Origin | Practical Cryptography, *Quadgram Statistics as a Fitness Measure* |
| URL | `http://practicalcryptography.com/media/cryptanalysis/files/english_quadgrams.txt.zip` |
| Retrieved | 2026-07-31 |
| SHA-256 (extracted `english_quadgrams.txt`) | `b461953d6ad3b5e1f0f07c133102b7656a205529cb8697a8ecda8d45311f7a55` |
| Committed as | gzip level 9, `mtime=0` for a reproducible artifact |

## Contents

| | |
|---|---|
| Distinct quadgrams | 389,373 |
| Total observations | 4,224,127,912 |
| Coverage of the 26⁴ space | 85.2% |
| Most frequent | `TION` at 13,168,375 |

Stored verbatim in the upstream format — `QUADGRAM count`, one per line, descending by
count. Not truncated to a popular head: dropping the tail pushes more quadgrams onto the
floor probability, which would shift scores away from the published baseline this table
was chosen to be comparable with.

## Why this table

The classical-cryptanalysis literature has standardised on it. A hill-climbing or
partial-break score computed against it can be compared with published results; the same
score against a table counted from some other corpus cannot. That comparability is the
entire reason for preferring it to a corpus we could have counted ourselves.

Its corpus is undisclosed beyond "English text", so the table carries whatever genre and
period bias that corpus had. This matters for the benchmark in one specific way, recorded
here because it affects interpretation rather than correctness: quadgram fitness rewards
*typical* English, so an idiosyncratic plaintext scores lower than a bland one at equal
correctness. The Phase 3 decision about where isomorph plaintexts come from runs into the
same effect from the other direction.

## Licensing

Redistribution terms are not stated on the source site. It is committed here on the view
that n-gram counts over a corpus are measurements rather than authorship — facts about
English, not expression — and it is reproduced unmodified and attributed above. It is an
input to this project, not part of what the project offers.

If the upstream table changes, `build.py` fails on the checksum rather than silently
adopting new counts. Every fitness score in the benchmark moves with this file, so that
failure is the point.
