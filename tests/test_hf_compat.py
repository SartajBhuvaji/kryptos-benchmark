"""Prove the baseline dataset loads under HuggingFace ``datasets`` as authored.

The dataset is destined for the Hub, so compatibility is verified here rather than
discovered at upload time. The load is done *with* the declared Features, which is the
part that matters: passing under inference alone would not prove the declared schema is
correct, and four rows full of nulls give inference very little to work with.
"""

from __future__ import annotations

import pathlib

import pytest

from kryptos.algorithms.baseline import build
from kryptos.algorithms.baseline.schema import CANARY, CONFIG, SPLIT, hf_features

datasets = pytest.importorskip("datasets", reason="datasets is a dev dependency")

DATA = build.OUTPUT


@pytest.fixture(scope="module")
def loaded():
    return datasets.load_dataset(
        "json", data_files={SPLIT: str(DATA)}, features=hf_features()
    )


def test_loads_into_a_single_test_split(loaded):
    assert list(loaded) == [SPLIT]
    assert loaded[SPLIT].num_rows == 4


def test_declared_features_match_what_is_stored(loaded):
    assert loaded[SPLIT].features == hf_features()


def test_inference_alone_agrees_on_column_names():
    """Loading without explicit features must not fail or drop columns."""
    inferred = datasets.load_dataset("json", data_files={SPLIT: str(DATA)})
    assert set(inferred[SPLIT].column_names) == set(hf_features())


def test_values_survive_the_round_trip(loaded):
    rows = {r["passage"]: r for r in loaded[SPLIT]}
    assert rows["K1"]["problem"].startswith("EMUFPHZLRFA")
    assert rows["K1"]["answer_readable"].startswith("BETWEEN SUBTLE SHADING")
    assert rows["K4"]["answer"] is None
    assert [c["plaintext"] for c in rows["K4"]["cribs"]] == [
        "EAST",
        "NORTHEAST",
        "BERLIN",
        "CLOCK",
    ]
    assert rows["K3"]["cribs"] == []


def test_every_record_carries_the_contamination_canary(loaded):
    """Following cais/hle: lets crawlers and dedup pipelines exclude this data."""
    assert all(r["canary"] == CANARY for r in loaded[SPLIT])


def test_dataset_card_is_present_and_declares_the_config():
    """The folder is uploaded to the Hub as-is, so the card must travel with it."""
    card = build.DATASET_DIR / "README.md"
    text = card.read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "configs:" in text
    assert f"split: {SPLIT}" in text
    assert f"config_name: {CONFIG}" in text
