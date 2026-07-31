"""Fetch the public-domain source texts and commit the clause corpus.

Same contract as the other builders in this repository: deterministic, re-runnable, and
``--check`` verifies the committed artifact without touching the network.

    python -m kryptos.algorithms.isomorph.data.build --check
    python -m kryptos.algorithms.isomorph.data.build

What is committed is not the books. It is a list of *clauses* -- the fragments between
punctuation marks -- each tagged with the work it came from. Generation draws clauses at
random and concatenates them, which is the whole point: the resulting plaintext has never
existed, so no model can complete it from memory, while its letter and n-gram statistics
remain those of real English rather than of anything synthesised.

Why not the alternatives
------------------------
Verbatim passages carry natural statistics but are recognisable: recover eight characters
of a known sentence and a model can recall the rest, which stops the score measuring
cryptanalysis at exactly the point it was starting to. LLM-written prose is novel but sits
near the most predictable English there is, so hill-climbing and a model's own priors both
do better on it than on real text and scores drift up relative to the cipher's true
difficulty. Recombination is the option that gives up neither.

The cost is that clause junctions are not natural English -- three quadgrams per join read
as nonsense. That is measured rather than assumed; see ``PROVENANCE.md`` for the size of
the effect on quadgram fitness.

Selection of works
------------------
Narrative prose, varied authors, all published before 1929 and therefore public domain in
the United States. Poetry and drama are excluded: their line structure survives clause
splitting and produces fragments that do not read as continuous prose.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import pathlib
import re
import sys
import unicodedata

if __package__ in (None, ""):  # allow running the file directly
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[4]))

from kryptos.algorithms.isomorph.corpus import normalize

HERE = pathlib.Path(__file__).resolve().parent
OUTPUT = HERE / "clauses.jsonl.gz"

RETRIEVED = "2026-07-31"

#: Project Gutenberg ebook numbers, with the metadata recorded per instance.
WORKS: tuple[dict, ...] = (
    {"id": "wells-time-machine", "gutenberg": 35,
     "title": "The Time Machine", "author": "H. G. Wells", "year": 1895},
    {"id": "conrad-heart-of-darkness", "gutenberg": 219,
     "title": "Heart of Darkness", "author": "Joseph Conrad", "year": 1899},
    {"id": "grahame-wind-in-the-willows", "gutenberg": 289,
     "title": "The Wind in the Willows", "author": "Kenneth Grahame", "year": 1908},
    {"id": "wharton-age-of-innocence", "gutenberg": 541,
     "title": "The Age of Innocence", "author": "Edith Wharton", "year": 1920},
    {"id": "london-call-of-the-wild", "gutenberg": 215,
     "title": "The Call of the Wild", "author": "Jack London", "year": 1903},
    {"id": "hudson-green-mansions", "gutenberg": 12197,
     "title": "Green Mansions", "author": "W. H. Hudson", "year": 1904},
    {"id": "forster-room-with-a-view", "gutenberg": 2641,
     "title": "A Room with a View", "author": "E. M. Forster", "year": 1908},
    {"id": "chopin-awakening", "gutenberg": 160,
     "title": "The Awakening", "author": "Kate Chopin", "year": 1899},
)

SOURCE_URL = "https://www.gutenberg.org/cache/epub/{n}/pg{n}.txt"

#: Project Gutenberg wraps each public-domain work in its own licensed boilerplate. The
#: text between these markers is the work itself, which is what is in the public domain --
#: the surrounding header, footer and trademark terms are not, and are discarded here.
START_MARKER = re.compile(r"^\*\*\*\s*START OF (THE|THIS) PROJECT GUTENBERG EBOOK.*$", re.M)
END_MARKER = re.compile(r"^\*\*\*\s*END OF (THE|THIS) PROJECT GUTENBERG EBOOK.*$", re.M)

#: Clause boundaries: sentence-ending punctuation, and the internal marks that separate
#: grammatically complete fragments. Splitting finer than this yields pieces too short to
#: carry n-gram structure; splitting only on sentences yields pieces so long that a single
#: draw is a recognisable quotation.
CLAUSE_SPLIT = re.compile(r"[.!?;:,()\"“”—]+|--+")

#: A clause must be long enough to contribute real n-gram structure and short enough that
#: several fit inside a Kryptos-sized passage of 63 to 372 characters. Measured on the
#: *normalised* form, since that is what a generated plaintext is made of -- counting
#: ``str.isalpha`` instead would count an accented letter that normalisation later drops.
MIN_CLAUSE_LETTERS = 20
MAX_CLAUSE_LETTERS = 90


#: SHA-256 of the serialised corpus, pinned so a changed upstream text or a changed
#: filtering rule shows up as a failure rather than as silently different plaintexts.
CORPUS_SHA256 = "98d5b2b998fc5a2582589db56b135de8ab879388c09d5028ac6bdb76e196084a"


def deaccent(text: str) -> str:
    """Fold accented Latin letters onto their base letters: ``Pélagie`` -> ``Pelagie``.

    The carved alphabet is A-Z, so an accented letter has to become *something*. Dropping
    it silently -- which is what normalisation alone would do -- welds the surrounding
    letters together and invents a sequence that occurs in no English word: ``Pelagie``
    would arrive as ``PLAGIE``. Folding keeps the word intact, which is what the n-gram
    statistics are supposed to reflect.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def strip_boilerplate(raw: str, work_id: str) -> str:
    start = START_MARKER.search(raw)
    end = END_MARKER.search(raw)
    if not start or not end:
        raise SystemExit(
            f"{work_id}: Project Gutenberg markers not found. The file layout has "
            "changed; do not guess at the boundaries, since the boilerplate is the part "
            "that is not public domain."
        )
    return raw[start.end() : end.start()]


def clauses_of(text: str) -> list[str]:
    """Split a work into clause-sized fragments of readable text.

    Returns fragments with their original spacing and casing. Normalisation to the carved
    A-Z form happens at generation time, not here, so the corpus stays readable and its
    provenance stays auditable.
    """
    # Paragraph structure is irrelevant once clauses are drawn at random, but line breaks
    # inside a sentence must not become word boundaries that were never there.
    flat = re.sub(r"\s+", " ", deaccent(text))

    found = []
    for piece in CLAUSE_SPLIT.split(flat):
        clause = piece.strip()
        if not clause:
            continue
        # Counted the way a generated plaintext will be built, so the bounds recorded
        # here are the bounds that actually hold downstream.
        letters = len(normalize(clause))
        if not MIN_CLAUSE_LETTERS <= letters <= MAX_CLAUSE_LETTERS:
            continue
        # Chapter headings, page furniture and anything carrying digits or markup would
        # normalise into letter sequences that are not English prose.
        if any(ch.isdigit() for ch in clause):
            continue
        if letters / len(clause) < 0.75:
            continue
        if clause.isupper():
            continue
        # Any letter that survived deaccenting but is still outside A-Z would vanish in
        # normalisation and weld its neighbours together. Drop the clause rather than
        # ship a word that no longer spells anything.
        if any(ch.isalpha() and not ("A" <= ch.upper() <= "Z") for ch in clause):
            continue
        found.append(clause)
    return found


def fetch() -> list[dict]:
    import urllib.request

    corpus: list[dict] = []
    for work in WORKS:
        url = SOURCE_URL.format(n=work["gutenberg"])
        with urllib.request.urlopen(url, timeout=120) as response:
            raw = response.read().decode("utf-8-sig", errors="replace")

        body = strip_boilerplate(raw, work["id"])
        found = clauses_of(body)
        if len(found) < 500:
            raise SystemExit(
                f"{work['id']}: only {len(found)} usable clauses, which suggests the "
                "text or the filters are wrong rather than that the book is short."
            )
        corpus.extend({"work": work["id"], "text": clause} for clause in found)
        print(f"  {work['id']:<32} {len(found):>6,} clauses", file=sys.stderr)

    return corpus


def serialize(corpus: list[dict]) -> bytes:
    """Deterministic: sorted by work then text, so a re-fetch diffs only on real change."""
    ordered = sorted(corpus, key=lambda c: (c["work"], c["text"]))
    payload = "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in ordered)
    return payload.encode("utf-8")


def compress(payload: bytes) -> bytes:
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as fh:
        fh.write(payload)
    return buffer.getvalue()


def summarise(payload: bytes) -> str:
    rows = [json.loads(line) for line in payload.decode("utf-8").splitlines()]
    works = {r["work"] for r in rows}
    letters = sum(sum(ch.isalpha() for ch in r["text"]) for r in rows)
    return f"{len(rows):,} clauses from {len(works)} works, {letters:,} letters"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify the committed artifact without network access")
    args = ap.parse_args()

    if args.check:
        if not OUTPUT.exists():
            print(f"missing {OUTPUT}; run without --check to fetch it", file=sys.stderr)
            return 1
        payload = gzip.decompress(OUTPUT.read_bytes())
        digest = hashlib.sha256(payload).hexdigest()
        if CORPUS_SHA256 and digest != CORPUS_SHA256:
            print(f"{OUTPUT} does not match the recorded checksum:\n"
                  f"  expected {CORPUS_SHA256}\n  got      {digest}", file=sys.stderr)
            return 1
        print(f"{OUTPUT.name} matches its checksum -- {summarise(payload)}")
        return 0

    payload = serialize(fetch())
    OUTPUT.write_bytes(compress(payload))
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes) -- {summarise(payload)}")
    print(f"CORPUS_SHA256 = {hashlib.sha256(payload).hexdigest()!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
