# Plaintext clause corpus

`clauses.jsonl.gz` is committed data. `build.py` reproduces it; this file records where it
came from, what is in it, and what the recombination costs.

## Source

Eight works of narrative prose from Project Gutenberg, all first published before 1929 and
therefore public domain in the United States. Poetry and drama are excluded — their line
structure survives clause splitting and yields fragments that do not read as prose.

| work | author | year | PG # | clauses |
|---|---|---|---|---|
| The Time Machine | H. G. Wells | 1895 | 35 | 2,955 |
| Heart of Darkness | Joseph Conrad | 1899 | 219 | 3,256 |
| The Awakening | Kate Chopin | 1899 | 160 | 5,610 |
| The Call of the Wild | Jack London | 1903 | 215 | 2,877 |
| Green Mansions | W. H. Hudson | 1904 | 12197 | 2,352 |
| The Wind in the Willows | Kenneth Grahame | 1908 | 289 | 5,128 |
| A Room with a View | E. M. Forster | 1908 | 2641 | 6,245 |
| The Age of Innocence | Edith Wharton | 1920 | 541 | 8,230 |

| | |
|---|---|
| Retrieved | 2026-07-31 |
| Total clauses | 36,653 |
| Total letters | 1,412,069 |
| Clause length | 20–90 letters, median 34, mean 38.5 |
| SHA-256 (uncompressed JSONL) | `98d5b2b998fc5a2582589db56b135de8ab879388c09d5028ac6bdb76e196084a` |
| Committed as | gzip level 9, `mtime=0`, rows sorted by (work, text) |

Clause lengths are counted on the **normalised** form — what a generated plaintext is
actually made of. Counting `str.isalpha` instead would count an accented letter that
normalisation later drops, so a clause could pass a 20-letter floor and arrive as 19.
Accented letters are folded to their base letter before splitting (`Pélagie` → `Pelagie`)
rather than left to vanish, which would weld the neighbours into `PLAGIE` — a sequence
occurring in no English word, quietly corrupting the statistics the corpus exists to
preserve.

Sorted on write so that re-fetching diffs only on real change rather than on iteration
order. This also means adjacent rows in the file are alphabetical neighbours, not
consecutive prose — anything measuring "natural contiguous text" must go back to an
original work rather than slicing this file.

## What recombination costs

A generated passage concatenates whole clauses, so the three quadgrams straddling each
join are not English. With clauses averaging 38.5 letters those joins are about 2.6% of
quadgram positions, and the measured effect is smaller than the spread between passages:

| | quadgram fitness | index of coincidence |
|---|---|---|
| Recombined clauses (200 samples, 63–372 letters) | **−4.207** ± 0.106 | 0.0646 |
| Genuine contiguous prose, same lengths | **−4.201** ± 0.111 | 0.0649 |
| Kryptos K1–K3 plaintexts | −4.288 | 0.0655 |

The gap between the first two rows is 0.006, against a standard deviation of 0.11 — two
orders of magnitude smaller than the spread between individual passages. Recombined text
is indistinguishable from continuous prose at the scale these metrics work at, and nothing
here needs the benchmark to compensate for the recombination.

The control matters: it is contiguous text taken from an original work, not a slice of
this file. Rows here are sorted alphabetically, so adjacent lines are neighbours in the
sort order rather than consecutive prose, and slicing them would measure recombination
against recombination.

The comparison that matters is the last row: generated plaintexts sit on the same side of
the Kryptos passages as real prose does, so an isomorph is not quietly easier or harder
than the baseline on account of its plaintext.

## Licensing

The works are public domain in the United States. Project Gutenberg wraps each one in its
own licensed header, footer and trademark terms; `build.py` requires the
`*** START/END OF THE PROJECT GUTENBERG EBOOK ***` markers and keeps only what lies
between them, discarding the boilerplate, which is the part that is not public domain. If
those markers are ever absent the build fails rather than guessing at the boundary.

Readers outside the United States should check their own term of copyright: 1920s works
are public domain in the US but a few of these authors died recently enough that
life-plus-70 jurisdictions may differ.

## Bias worth naming

Eight works of literary fiction from 1895–1920 is a narrow slice of English. Generated
plaintexts inherit that register: period vocabulary, long sentences, no technical or
contemporary idiom. This does not bias the *cipher* — a transposition does not care what
it permutes — but it does mean quadgram fitness and a model's priors are being exercised
on early-twentieth-century literary prose specifically, not on English in general. The
Kryptos plaintexts happen to sit in a similar register, which is why this is recorded as a
property rather than corrected for.
