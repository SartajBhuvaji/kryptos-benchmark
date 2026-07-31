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


# --- publish path ----------------------------------------------------------------


def test_preflight_passes_on_the_committed_dataset():
    """The publish path refuses to upload a stale artifact or an invalid card, so a
    green preflight is what makes `python -m kryptos.huggingface.push` safe to run."""
    from kryptos.huggingface import push

    checks = push.preflight()
    assert any("matches builder output" in c for c in checks)
    assert any("metadata validates" in c for c in checks)
    assert any("loads as 4 rows" in c for c in checks)


def test_publishable_files_are_the_card_the_data_and_the_example():
    from kryptos.huggingface import push

    assert push.publishable_files() == ["README.md", "baseline/test.jsonl", "example.py"]


def test_build_residue_is_never_published(tmp_path, monkeypatch):
    """`upload_folder` walks the filesystem, not the git index, so a __pycache__ that
    git happily ignores would otherwise be uploaded -- and importing example.py in the
    test suite is enough to create one."""
    from kryptos.huggingface import push

    staged = tmp_path / "dataset"
    (staged / "baseline").mkdir(parents=True)
    (staged / "README.md").write_text("card", encoding="utf-8")
    (staged / "baseline" / "test.jsonl").write_text("{}\n", encoding="utf-8")
    (staged / "__pycache__").mkdir()
    (staged / "__pycache__" / "example.cpython-313.pyc").write_bytes(b"\x00")
    (staged / ".DS_Store").write_bytes(b"\x00")

    monkeypatch.setattr(push, "DATASET_DIR", staged)
    assert push.publishable_files() == ["README.md", "baseline/test.jsonl"]


def test_preflight_rejects_an_unrecognised_file(tmp_path, monkeypatch):
    """The folder is uploaded wholesale, so an unreviewed file heading for a public URL
    should stop the push rather than ride along with it."""
    from kryptos.huggingface import push

    staged = tmp_path / "dataset"
    staged.mkdir()
    (staged / "notes.txt").write_text("private working notes", encoding="utf-8")

    monkeypatch.setattr(push, "DATASET_DIR", staged)
    with pytest.raises(push.PreflightError, match="unexpected file"):
        push.preflight()


def test_preflight_rejects_a_stale_artifact(tmp_path, monkeypatch):
    """Guards the check above against passing vacuously."""
    from kryptos.huggingface import push

    stale = tmp_path / "test.jsonl"
    stale.write_text('{"id": "not-the-real-thing"}\n', encoding="utf-8")
    monkeypatch.setattr(push.build, "OUTPUT", stale)

    with pytest.raises(push.PreflightError, match="stale"):
        push.preflight()
