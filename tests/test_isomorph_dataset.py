"""Verification for the published isomorph configs.

The generators are tested in ``test_generate.py``. This file tests the *artifacts* — the
committed JSONL that people will actually download. The distinction matters: a correct
generator can still be published wrong, by flattening a matrix in the wrong order,
dropping a field, or shipping a row whose stated keys no longer decrypt its ciphertext.

So the round trips here are re-run against the committed files, reading only what the row
publishes.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from kryptos.algorithms.ciphers import hill, quagmire, transposition, vigenere
from kryptos.algorithms.isomorph import build as isomorph_build
from kryptos.algorithms.isomorph import schema as isomorph_schema
from kryptos.algorithms.isomorph.schema import CANARY, CONFIGS

CONFIG_NAMES = [config.name for config in CONFIGS]


@pytest.fixture(scope="module")
def rows() -> dict[str, list[dict]]:
    loaded = {}
    for config in CONFIGS:
        path = isomorph_build.output_for(config)
        with pathlib.Path(path).open(encoding="utf-8") as fh:
            loaded[config.name] = [json.loads(line) for line in fh]
    return loaded


def route_of(encoded: str):
    return tuple(tuple(int(p) for p in stage.split(":")) for stage in encoded.split(","))


# --- the artifacts exist and match their builder ----------------------------------


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_committed_artifact_matches_the_builder(name, rows):
    config = isomorph_schema.config_for(name)
    expected = isomorph_build.serialize(isomorph_build.build_config(config))
    assert isomorph_build.output_for(config).read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_each_config_has_the_declared_record_count(name, rows):
    assert len(rows[name]) == isomorph_build.INSTANCES_PER_CONFIG


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_every_row_carries_every_field_in_order(name, rows):
    fields = isomorph_schema.fields_for(name)
    for row in rows[name]:
        assert tuple(row) == fields


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_no_row_carries_another_ciphers_fields(name, rows):
    """The reason for one config per cipher. A nulls row must not carry hill_matrix."""
    others = set()
    for config in CONFIGS:
        if config.name != name:
            others |= set(config.keys)
    mine = set(isomorph_schema.config_for(name).keys)
    for row in rows[name]:
        assert not (set(row) & (others - mine))


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_no_list_field_is_null(name, rows):
    for row in rows[name]:
        for field in ("source_works", "layers", "null_positions", "hill_matrix"):
            if field in row:
                assert isinstance(row[field], list)


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_every_row_carries_the_canary_and_the_seed(name, rows):
    for row in rows[name]:
        assert row["canary"] == CANARY
        assert row["seed"] == isomorph_build.SNAPSHOT_SEED


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_ids_are_unique(name, rows):
    ids = [row["id"] for row in rows[name]]
    assert len(set(ids)) == len(ids)


def test_ids_are_unique_across_configs(rows):
    everything = [row["id"] for name in CONFIG_NAMES for row in rows[name]]
    assert len(set(everything)) == len(everything)


# --- round trips against the committed rows ---------------------------------------


def test_published_quagmire_rows_decrypt(rows):
    for row in rows["isomorph_quagmire"]:
        assert quagmire.decrypt(
            row["problem"], row["alphabet_keyword"], row["indicator_keyword"]
        ) == row["answer"]


def test_published_transposition_rows_decrypt(rows):
    for row in rows["isomorph_transposition"]:
        assert transposition.decrypt(row["problem"], route_of(row["route"])) == row["answer"]
        if row["solver_route"]:
            assert transposition.encrypt(
                row["problem"], route_of(row["solver_route"])
            ) == row["answer"]


def test_published_composite_rows_decrypt(rows):
    """Also pins the flattening: a matrix stored column-major would fail here."""
    for row in rows["isomorph_composite"]:
        size = row["hill_block_size"]
        flat = row["hill_matrix"]
        assert len(flat) == size * size
        matrix = tuple(
            tuple(flat[i * size : (i + 1) * size]) for i in range(size)
        )
        recovered = vigenere.decrypt(hill.decrypt(row["problem"], matrix), row["vigenere_key"])
        assert recovered == row["answer"]


def test_published_nulls_rows_decrypt(rows):
    for row in rows["isomorph_nulls"]:
        deciphered = quagmire.decrypt(
            row["problem"], row["alphabet_keyword"], row["indicator_keyword"]
        )
        assert deciphered == row["deciphered"]
        positions = set(row["null_positions"])
        assert "".join(
            ch for i, ch in enumerate(deciphered) if i not in positions
        ) == row["answer"]


# --- published ground truth --------------------------------------------------------


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_solution_is_present_and_specific(name, rows):
    solutions = {row["solution"] for row in rows[name]}
    assert len(solutions) > 1, "a template ignoring its parameters would be identical"
    for row in rows[name]:
        assert row["solution"]


def test_published_period_is_the_true_period(rows):
    for name in ("isomorph_quagmire", "isomorph_nulls"):
        for row in rows[name]:
            assert row["period"] == quagmire.period(
                row["indicator_keyword"], row["alphabet_keyword"]
            )


def test_proxy_configs_disclaim_being_models_of_k4(rows):
    """Nobody knows K4's method. Solving a proxy is not evidence about it, and the
    published text has to say so."""
    for name in ("isomorph_composite", "isomorph_nulls"):
        for row in rows[name]:
            assert "not a model of K4" in row["solution"]


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_scoring_is_declared_without_a_baked_in_tier(name, rows):
    """Tiers are framings applied at evaluation time -- the same instance can be posed
    with keys supplied or withheld -- so a tier threshold does not belong in the data."""
    for row in rows[name]:
        assert row["scoring_metric"] == "cer"
        assert row["scoring_reference"] == "answer"
        assert row["scoring_threshold"] == 0.0


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_provenance_is_published(name, rows):
    for row in rows[name]:
        assert row["source_works"]
        assert row["clause_count"] >= 1


# --- the leak property, on the published rows -------------------------------------


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_the_problem_never_contains_the_answer(name, rows):
    """The input fields are what a harness sends. None may reveal the plaintext."""
    for row in rows[name]:
        assert row["answer"] not in row["problem"]
        assert row["answer"] not in row["problem_letters_only"]


@pytest.mark.parametrize("name", CONFIG_NAMES)
def test_input_fields_are_free_of_key_material(name, rows):
    keys = ("alphabet_keyword", "indicator_keyword", "vigenere_key", "route", "deciphered")
    for row in rows[name]:
        for key in keys:
            value = row.get(key)
            if isinstance(value, str) and len(value) > 3:
                assert value not in row["problem"]


# --- publish path ------------------------------------------------------------------


def test_preflight_covers_every_config():
    from kryptos.huggingface import push

    checks = push.preflight()
    for name in ("baseline", *CONFIG_NAMES):
        assert any(f"{name} loads as" in c for c in checks), name
        assert any(f"builder output ({name})" in c for c in checks), name


def test_preflight_rejects_a_card_missing_a_config(tmp_path, monkeypatch):
    """Guards the check above: a config built but not declared uploads as files the Hub
    will never surface."""
    from kryptos.huggingface import push

    card = tmp_path / "README.md"
    card.write_text(
        "---\nconfigs:\n  - config_name: baseline\n    data_files:\n"
        "      - split: test\n        path: baseline/test.jsonl\n---\n# card\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(push, "CARD", card)

    with pytest.raises(push.PreflightError, match="does not declare config"):
        push.preflight()


def test_preflight_rejects_a_card_declaring_an_unbuilt_config(tmp_path, monkeypatch):
    from kryptos.huggingface import push

    declared = "\n".join(
        f"  - config_name: {name}\n    data_files:\n      - split: test\n"
        f"        path: {name}/test.jsonl"
        for name in ("baseline", *CONFIG_NAMES, "isomorph_imaginary")
    )
    card = tmp_path / "README.md"
    card.write_text(f"---\nconfigs:\n{declared}\n---\n# card\n", encoding="utf-8")
    monkeypatch.setattr(push, "CARD", card)

    with pytest.raises(push.PreflightError, match="no builder produces"):
        push.preflight()
