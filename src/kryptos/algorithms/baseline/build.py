"""Build the Kryptos baseline dataset.

Emits ``baseline/test.jsonl`` under the dataset directory: four records, one per carved
passage, each posing the same problem -- given this ciphertext, recover the plaintext.
K4 is unsolved, so its record carries a null answer and is scored against Sanborn's four
confirmed cribs instead.

Deterministic and re-runnable. ``--check`` rebuilds in memory and compares against the
committed file without writing, so CI can prove the artifact matches its source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

if __package__ in (None, ""):  # allow running the file directly
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3]))

from kryptos.algorithms.baseline import source as src
from kryptos.algorithms.baseline.schema import CANARY, CONFIG, FIELDS, SPLIT, anomaly, crib

#: Repository root, four levels up from src/kryptos/algorithms/baseline/.
ROOT = pathlib.Path(__file__).resolve().parents[4]

#: The HuggingFace dataset repository root. Holds only the card and the config
#: directories, so it can be uploaded to the Hub as-is.
DATASET_DIR = ROOT / "src" / "kryptos" / "dataset"
OUTPUT = DATASET_DIR / CONFIG / f"{SPLIT}.jsonl"

QUAGMIRE_SOLUTION = (
    "Quagmire III polyalphabetic substitution. Build the mixed alphabet by writing "
    "{alphabet_keyword}, dropping repeated letters, then appending the unused letters of "
    "the alphabet in order, giving {keyed_alphabet}. The indicator keyword "
    "{indicator_keyword} gives a period of {period}: the message is enciphered with "
    "{period} shifted copies of that alphabet, selected by position modulo {period}. "
    "Decrypt each position with its own shifted alphabet. A literal '?' is copied through "
    "unenciphered and does not advance the key."
)

TRANSPOSITION_SOLUTION = (
    "Route transposition. The letters are permuted rather than substituted, so letter "
    "frequencies and the index of coincidence are unchanged from ordinary English and the "
    "ciphertext is an exact anagram of the plaintext -- which is what rules out frequency "
    "analysis and identifies the cipher family. Recovery means inverting a multi-stage "
    "geometric route: the text is written into a rectangular grid, rotated, resliced to a "
    "different width, rotated again, and read off by columns. The exact grid dimensions "
    "and rotation sequence are not asserted here; they are pinned down alongside the "
    "cipher implementations. A literal '?' is copied through."
)


def letters_only(text: str) -> str:
    return "".join(ch for ch in text if ch.isalpha())


def normalize(readable: str) -> str:
    """Strip spacing but keep the literal ``?`` marks, matching the carved form."""
    return readable.replace(" ", "")


def _record(
    passage: str,
    ciphertext: str,
    readable_plaintext: str | None,
    cipher_family: str,
    cipher_name: str,
    solution: str | None,
    *,
    alphabet_keyword: str | None = None,
    indicator_keyword: str | None = None,
    period: int | None = None,
    cribs: list | None = None,
    anomalies: list | None = None,
) -> dict:
    plaintext = normalize(readable_plaintext) if readable_plaintext else None
    solved = readable_plaintext is not None
    return {
        # --- meta ---
        "id": f"kryptos-baseline-{passage.lower()}",
        "passage": passage,
        "solved": solved,
        "canary": CANARY,
        # --- input: what a solver is given ---
        "problem": ciphertext,
        "problem_letters_only": letters_only(ciphertext),
        "problem_length": len(ciphertext),
        "cribs": cribs or [],
        # --- ground truth: never shown to the model under evaluation ---
        "solution": solution,
        "answer": letters_only(plaintext) if plaintext else None,
        "answer_readable": readable_plaintext,
        "cipher_family": cipher_family,
        "cipher_name": cipher_name,
        "alphabet_keyword": alphabet_keyword,
        "keyed_alphabet": src.KEYED_ALPHABET if alphabet_keyword else None,
        "indicator_keyword": indicator_keyword,
        "period": period,
        "anomalies": anomalies or [],
        # --- scoring ---
        # K4 has 24 known plaintext characters and no reference string, so full-text
        # CER is undefined for it. The schema says so rather than implying otherwise.
        "scoring_metric": "cer" if solved else "crib_match",
        "scoring_reference": "answer" if solved else "cribs",
        "scoring_threshold": 0.0 if solved else None,
        # --- provenance ---
        "source_urls": list(src.SOURCE_URLS),
        "retrieved": src.RETRIEVED,
        "sha256_problem": hashlib.sha256(ciphertext.encode()).hexdigest(),
    }


def build() -> list[dict]:
    k4_cribs = [
        crib(c["plaintext"], src.K4_CIPHERTEXT[c["start"] - 1 : c["end"]], c["start"], c["end"])
        for c in src.K4_CRIBS
    ]

    records = [
        _record(
            "K1",
            src.K1_CIPHERTEXT,
            src.K1_PLAINTEXT,
            "polyalphabetic_substitution",
            "Quagmire III",
            QUAGMIRE_SOLUTION.format(
                alphabet_keyword=src.K1_ALPHABET_KEYWORD,
                keyed_alphabet=src.KEYED_ALPHABET,
                indicator_keyword=src.K1_INDICATOR_KEYWORD,
                period=src.K1_PERIOD,
            ),
            alphabet_keyword=src.K1_ALPHABET_KEYWORD,
            indicator_keyword=src.K1_INDICATOR_KEYWORD,
            period=src.K1_PERIOD,
            anomalies=[
                anomaly(
                    "deliberate_misspelling",
                    "IQLUSION",
                    "Sanborn has stated this misspelling of ILLUSION is intentional.",
                    intended="ILLUSION",
                )
            ],
        ),
        _record(
            "K2",
            src.K2_CIPHERTEXT,
            src.K2_PLAINTEXT,
            "polyalphabetic_substitution",
            "Quagmire III",
            QUAGMIRE_SOLUTION.format(
                alphabet_keyword=src.K2_ALPHABET_KEYWORD,
                keyed_alphabet=src.KEYED_ALPHABET,
                indicator_keyword=src.K2_INDICATOR_KEYWORD,
                period=src.K2_PERIOD,
            ),
            alphabet_keyword=src.K2_ALPHABET_KEYWORD,
            indicator_keyword=src.K2_INDICATOR_KEYWORD,
            period=src.K2_PERIOD,
            anomalies=[
                anomaly(
                    "transcription_error",
                    "UNDERGRUUND",
                    "Unlike IQLUSION and DESPARATLY, this one is not established as "
                    "deliberate. The coding charts spell UNDERGROUND correctly and carry "
                    "the keyword ABSCISSA correctly, so the change arose when the "
                    "ciphertext was transcribed onto the sculpture: an E became an R, and "
                    "R against keyword letter S decodes to U. Whether that was intended "
                    "is unknown.",
                    intended="UNDERGROUND",
                ),
                anomaly(
                    "omitted_character",
                    "ID BY ROWS",
                    "The carved 372-character ciphertext decrypts to an ending of "
                    "WEST ID BY ROWS. On 19 April 2006 Sanborn disclosed that he omitted "
                    "an S from the ciphertext (an X in the plaintext) and confirmed the "
                    f"intended reading is {src.K2_INTENDED_ENDING!r} -- one character "
                    "longer than the carved ciphertext can support. Ground truth here is "
                    "what the given ciphertext actually yields, so that a correct "
                    "decryption is not penalised.",
                    intended=src.K2_INTENDED_ENDING,
                ),
            ],
        ),
        _record(
            "K3",
            src.K3_CIPHERTEXT,
            src.K3_PLAINTEXT,
            "transposition",
            "Route transposition",
            TRANSPOSITION_SOLUTION,
            anomalies=[
                anomaly(
                    "deliberate_misspelling",
                    "DESPARATLY",
                    "Misspelling of DESPERATELY. The passage paraphrases Howard Carter's "
                    "1922 account of opening the tomb of Tutankhamun.",
                    intended="DESPERATELY",
                )
            ],
        ),
        _record(
            "K4",
            src.K4_CIPHERTEXT,
            None,
            "unknown",
            "unknown",
            None,  # unsolved: no method is known, so none is asserted
            cribs=k4_cribs,
        ),
    ]

    for rec in records:
        assert tuple(rec) == FIELDS, f"{rec['id']}: field order drift"
    return records


def serialize(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--check",
        action="store_true",
        help="compare against the committed file instead of writing",
    )
    args = ap.parse_args()

    payload = serialize(build())

    if args.check:
        if not OUTPUT.exists():
            print(f"missing {OUTPUT}", file=sys.stderr)
            return 1
        if OUTPUT.read_text(encoding="utf-8") != payload:
            print(f"{OUTPUT} is stale; re-run without --check", file=sys.stderr)
            return 1
        print(f"{OUTPUT} matches source")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(payload, encoding="utf-8")
    print(f"wrote {OUTPUT} ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
