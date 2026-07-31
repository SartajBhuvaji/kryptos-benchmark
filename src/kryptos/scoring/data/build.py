"""Fetch and commit the English quadgram frequency table.

The table is an input to scoring, not something derived from this repository, so it is
committed as an artifact and this script is how it is reproduced. Same contract as the
dataset builder: deterministic, re-runnable, and ``--check`` verifies the committed file
without writing.

    python -m kryptos.scoring.data.build --check
    python -m kryptos.scoring.data.build

Source
------
Practical Cryptography's ``english_quadgrams.txt``, the table the classical-cryptanalysis
literature has standardised on. Chosen for exactly that reason: a hill-climbing score
computed against it is comparable with published results, which a table counted from some
other corpus would not be.

It carries 389,373 distinct quadgrams over 4.22 billion observations -- 85% of the 26^4
possible four-letter strings. Committed in full rather than truncated to a popular head:
truncating pushes more quadgrams onto the floor probability and would silently shift
scores away from the published baseline the table was chosen for.

Redistribution terms are not stated on the source site. Committed here on the view that
n-gram counts over a corpus are measurements rather than authorship, attributed in
``PROVENANCE.md`` with the retrieval date and checksums so the claim is auditable. It is
not modified, and it is not the thing this project is offering.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import pathlib
import sys
import zipfile

HERE = pathlib.Path(__file__).resolve().parent

SOURCE_URL = (
    "http://practicalcryptography.com/media/cryptanalysis/files/english_quadgrams.txt.zip"
)
RETRIEVED = "2026-07-31"

ARCHIVE_MEMBER = "english_quadgrams.txt"

#: SHA-256 of the extracted table. Pinned on the table rather than on the zip: an archive
#: recompressed at a different level is the same data, whereas a silent change to the
#: counts would reshape every fitness score in the benchmark with nothing to point at.
TABLE_SHA256 = "b461953d6ad3b5e1f0f07c133102b7656a205529cb8697a8ecda8d45311f7a55"

OUTPUT = HERE / "english_quadgrams.txt.gz"


def fetch() -> bytes:
    """Download the archive and return the table bytes, checksum verified."""
    import urllib.request

    with urllib.request.urlopen(SOURCE_URL, timeout=120) as response:
        archive = response.read()

    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        table = zf.read(ARCHIVE_MEMBER)

    digest = hashlib.sha256(table).hexdigest()
    if digest != TABLE_SHA256:
        raise SystemExit(
            f"{ARCHIVE_MEMBER} does not match the recorded checksum.\n"
            f"  expected {TABLE_SHA256}\n  got      {digest}\n"
            "The upstream table has changed. Review the difference before updating the "
            "constant -- every fitness score in the benchmark moves with it."
        )
    return table


def compress(table: bytes) -> bytes:
    """Gzip deterministically: no mtime, no filename, so the artifact is reproducible."""
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", compresslevel=9, mtime=0) as fh:
        fh.write(table)
    return buffer.getvalue()


def summarise(table: bytes) -> str:
    lines = table.decode("ascii").split()
    quadgrams, counts = lines[0::2], [int(c) for c in lines[1::2]]
    return (
        f"{len(quadgrams):,} quadgrams, {sum(counts):,} observations, "
        f"most common {quadgrams[0]} at {counts[0]:,}"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify the committed artifact without network access")
    args = ap.parse_args()

    if args.check:
        if not OUTPUT.exists():
            print(f"missing {OUTPUT}; run without --check to fetch it", file=sys.stderr)
            return 1
        table = gzip.decompress(OUTPUT.read_bytes())
        digest = hashlib.sha256(table).hexdigest()
        if digest != TABLE_SHA256:
            print(f"{OUTPUT} does not match the recorded checksum", file=sys.stderr)
            return 1
        print(f"{OUTPUT.name} matches its checksum -- {summarise(table)}")
        return 0

    table = fetch()
    OUTPUT.write_bytes(compress(table))
    print(f"wrote {OUTPUT} ({OUTPUT.stat().st_size:,} bytes) -- {summarise(table)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
