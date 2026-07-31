"""Record schema for the isomorph configs.

Follows the baseline's conventions rather than inventing new ones: ``problem`` /
``solution`` / ``answer`` field naming, problem and ground truth separated by field
grouping, every field present in every row, list fields ``[]`` rather than null, split
named ``test``, and an HLE-style contamination canary on every record.

One config per cipher
---------------------
Each config carries one cipher and therefore one coherent parameter shape. Folding the two
K4 proxies together would publish ``hill_matrix`` as null on every nulls row and
``null_positions`` as null on every Vigenere-Hill row -- legal under the flat-schema rule,
but columns that are meaningless for half the table. HuggingFace configs are for exactly
this, the way GSM8K splits ``main`` from ``socratic``.

The common fields are identical across all four, so a harness can read any config without
knowing which cipher it holds; the per-cipher fields are additive.

No tier threshold is baked in
-----------------------------
``scoring_threshold`` is 0.0 everywhere, meaning "exact recovery is what correct means".
Tiers are *framings* applied at evaluation time -- the same instance can be posed with its
keys supplied or withheld -- so the pass marks in :mod:`kryptos.scoring.thresholds` belong
to the harness, not to the data. Writing a tier's threshold into a row would fix a
Phase 4 decision inside a Phase 3 artifact.
"""

from __future__ import annotations

from typing import Any

from kryptos.algorithms.baseline.schema import CANARY, SPLIT

__all__ = ["CANARY", "SPLIT", "CONFIGS", "config_for", "fields_for", "hf_features"]

#: Identity, provenance and bookkeeping -- identical in every config.
META_FIELDS: tuple[str, ...] = ("id", "config", "kind", "canary", "seed")

#: What a solver is given.
INPUT_FIELDS: tuple[str, ...] = ("problem", "problem_letters_only", "problem_length")

#: The answer and the method. Never shown to the model under evaluation.
COMMON_GROUND_TRUTH: tuple[str, ...] = (
    "solution",
    "answer",
    "answer_readable",
    "cipher_family",
    "cipher_name",
)

#: How a submission is scored.
SCORING_FIELDS: tuple[str, ...] = (
    "scoring_metric",
    "scoring_reference",
    "scoring_threshold",
)

#: Where the plaintext came from.
PROVENANCE_FIELDS: tuple[str, ...] = ("source_works", "clause_count")

#: Per-cipher key material, appended to the common ground-truth block.
QUAGMIRE_KEYS: tuple[str, ...] = (
    "alphabet_keyword",
    "keyed_alphabet",
    "indicator_keyword",
    "period",
)

TRANSPOSITION_KEYS: tuple[str, ...] = ("route", "solver_route")

COMPOSITE_KEYS: tuple[str, ...] = (
    "layers",
    "vigenere_key",
    "hill_block_size",
    "hill_matrix",
)

NULLS_KEYS: tuple[str, ...] = (
    "layers",
    *QUAGMIRE_KEYS,
    "null",
    "null_group",
    "null_stride",
    "null_positions",
    "null_count",
    "deciphered",
)


class Config:
    """One published config: its Hub name, the generator kind behind it, its fields."""

    def __init__(self, name: str, kind: str, keys: tuple[str, ...], summary: str) -> None:
        self.name = name
        self.kind = kind
        self.keys = keys
        self.summary = summary

    @property
    def fields(self) -> tuple[str, ...]:
        return (
            *META_FIELDS,
            *INPUT_FIELDS,
            *COMMON_GROUND_TRUTH,
            *self.keys,
            *SCORING_FIELDS,
            *PROVENANCE_FIELDS,
        )

    @property
    def path(self) -> str:
        return f"{self.name}/{SPLIT}.jsonl"

    def __repr__(self) -> str:  # pragma: no cover -- debugging aid
        return f"Config({self.name!r})"


CONFIGS: tuple[Config, ...] = (
    Config(
        "isomorph_quagmire",
        "quagmire",
        QUAGMIRE_KEYS,
        "K1 and K2's cipher with a novel plaintext and randomly drawn keys.",
    ),
    Config(
        "isomorph_transposition",
        "transposition",
        TRANSPOSITION_KEYS,
        "K3's cipher with a novel plaintext and randomised grid geometry.",
    ),
    Config(
        "isomorph_composite",
        "composite",
        COMPOSITE_KEYS,
        "A Vigenere layer followed by a Hill layer. A multi-layer probe, not a model of K4.",
    ),
    Config(
        "isomorph_nulls",
        "nulls",
        NULLS_KEYS,
        "Quagmire III over a message salted with positional nulls. Also a proxy, not K4.",
    ),
)

BY_NAME = {config.name: config for config in CONFIGS}
BY_KIND = {config.kind: config for config in CONFIGS}


def config_for(name: str) -> Config:
    try:
        return BY_NAME[name]
    except KeyError:
        raise ValueError(
            f"no config {name!r}; the isomorph configs are {sorted(BY_NAME)}"
        ) from None


def fields_for(name: str) -> tuple[str, ...]:
    return config_for(name).fields


def hf_features(name: str) -> Any:
    """The authoritative ``datasets.Features`` for one config.

    Imported lazily -- ``datasets`` verifies HuggingFace compatibility and is not needed
    to consume the JSONL.
    """
    from datasets import Features, Value

    config = config_for(name)

    common = {
        "id": Value("string"),
        "config": Value("string"),
        "kind": Value("string"),
        "canary": Value("string"),
        "seed": Value("int64"),
        "problem": Value("string"),
        "problem_letters_only": Value("string"),
        "problem_length": Value("int32"),
        "solution": Value("string"),
        "answer": Value("string"),
        "answer_readable": Value("string"),
        "cipher_family": Value("string"),
        "cipher_name": Value("string"),
    }

    # Hill's key is published row-major and flat, with the block size beside it, rather
    # than as a list of lists. Arrow handles nested lists, but the flat form removes any
    # question of orientation and matches how every other key here is stored.
    per_cipher: dict[str, Any] = {
        "alphabet_keyword": Value("string"),
        "keyed_alphabet": Value("string"),
        "indicator_keyword": Value("string"),
        "period": Value("int32"),
        "route": Value("string"),
        "solver_route": Value("string"),
        "layers": [Value("string")],
        "vigenere_key": Value("string"),
        "hill_block_size": Value("int32"),
        "hill_matrix": [Value("int32")],
        "null": Value("string"),
        "null_group": Value("int32"),
        "null_stride": Value("int32"),
        "null_positions": [Value("int32")],
        "null_count": Value("int32"),
        "deciphered": Value("string"),
    }

    tail = {
        "scoring_metric": Value("string"),
        "scoring_reference": Value("string"),
        "scoring_threshold": Value("float32"),
        "source_works": [Value("string")],
        "clause_count": Value("int32"),
    }

    features = dict(common)
    features.update({key: per_cipher[key] for key in config.keys})
    features.update(tail)

    ordered = {key: features[key] for key in config.fields}
    return Features(ordered)
