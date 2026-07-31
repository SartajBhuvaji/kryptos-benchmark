"""Verification for the scoring module.

These metrics moved out of the benchmark runner unchanged, so the arithmetic tests came
with them. What is new is the last section: the dataset ships a standalone ``example.py``
that carries its own copy of the scoring code, and a copy that silently disagrees with
the canonical implementation would make published numbers incomparable. The differential
test runs both over the same inputs and requires identical answers.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import pathlib

import pytest

from kryptos.algorithms.baseline import build
from kryptos.algorithms.baseline.schema import GROUND_TRUTH_FIELDS, INPUT_FIELDS
from kryptos.scoring import character_error_rate, crib_score, letters_only, levenshtein


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    with pathlib.Path(build.OUTPUT).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


# --- edit distance ----------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b,expected",
    [("kitten", "sitting", 3), ("", "abc", 3), ("abc", "", 3), ("same", "same", 0)],
)
def test_levenshtein(a, b, expected):
    assert levenshtein(a, b) == expected


def test_levenshtein_pure_python_matches_rapidfuzz(monkeypatch):
    """The fallback runs when rapidfuzz is absent, so it must agree with it."""
    pytest.importorskip("rapidfuzz")
    import builtins

    real_import = builtins.__import__

    def no_rapidfuzz(name, *args, **kwargs):
        if name.startswith("rapidfuzz"):
            raise ImportError("blocked for this test")
        return real_import(name, *args, **kwargs)

    pairs = [("BETWEENSUBTLE", "BETWENSUBTLE"), ("ABCDEF", "FEDCBA"), ("X" * 40, "Y" * 40)]
    fast = [levenshtein(a, b) for a, b in pairs]
    monkeypatch.setattr(builtins, "__import__", no_rapidfuzz)
    assert [levenshtein(a, b) for a, b in pairs] == fast


def test_character_error_rate():
    assert character_error_rate("ABCDE", "ABCDE") == 0.0
    assert character_error_rate("ABCDE", "ABXDE") == pytest.approx(0.2)
    assert character_error_rate("ABCDE", "") == 1.0


def test_cer_is_not_clamped():
    """An over-long hypothesis should score above 1.0 rather than silently cap."""
    assert character_error_rate("AB", "ABCDEFGH") > 1.0


def test_perfect_decryption_scores_zero(rows):
    """The end-to-end scoring contract: the stored answer scores 0.0 CER."""
    for row in rows:
        if row["scoring_metric"] == "cer":
            assert character_error_rate(row["answer"], row["answer"]) == 0.0


# --- normalisation ----------------------------------------------------------------


def test_letters_only_normalizes():
    assert letters_only("be tween!") == "BETWEEN"
    assert letters_only("a?b") == "AB"


def test_letters_only_drops_non_ascii_letters():
    """A model may return accented characters; they must not survive into a distance,
    where they would silently count as ordinary mismatches."""
    assert letters_only("café") == "CAF"
    assert letters_only("ΑΒΓ") == ""


# --- cribs ------------------------------------------------------------------------


def test_crib_score_placement(rows):
    k4 = next(r for r in rows if r["passage"] == "K4")
    cribs = k4["cribs"]

    perfect = ["?"] * 97
    for c in cribs:
        perfect[c["start"] - 1 : c["end"]] = list(c["plaintext"])
    assert crib_score(cribs, "".join(perfect)) == (4, 4)


def test_crib_score_separates_placed_from_merely_present(rows):
    """The two figures must differ when a crib appears at the wrong offset -- otherwise
    the placement signal is not measuring anything the presence signal does not."""
    k4 = next(r for r in rows if r["passage"] == "K4")
    displaced = "BERLIN" + "?" * 91
    assert crib_score(k4["cribs"], displaced) == (0, 1)


# --- the shipped example --------------------------------------------------------
#
# It carries its own copy of the scoring code and its own prompt builder, and it is the
# file most people will actually run, so both properties are pinned here: it must agree
# with the module numerically, and it must not leak the answer.


@pytest.fixture(scope="module")
def example():
    """Load ``dataset/example.py`` as a module without importing the package."""
    path = build.DATASET_DIR / "example.py"
    spec = importlib.util.spec_from_file_location("kryptos_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_ships_with_the_dataset(example):
    """It lives inside the Hub repo root, so `push` uploads it with the data."""
    assert (build.DATASET_DIR / "example.py").exists()


def test_example_imports_nothing_from_this_repository():
    """Its whole reason to exist is running as a single file wherever it is dropped.

    Checked on the parsed AST rather than by string search, so a name like
    ``kryptos-bench`` appearing in a docstring or a dataset id cannot trip it, and an
    import cannot hide behind unusual formatting.
    """
    source = (build.DATASET_DIR / "example.py").read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level:
            pytest.fail(f"relative import in a file meant to stand alone: {ast.dump(node)}")
    assert "kryptos" not in imported
    assert imported <= {"__future__", "argparse", "json", "sys", "anthropic", "datasets",
                        "rapidfuzz"}


def test_example_prompts_never_contain_ground_truth(example, rows):
    """The same property the harness is held to. This file ships to the Hub, so a leak
    here would be a leak in the code most users copy."""
    for row in rows:
        prompt = example.build_prompt(row)
        for field in GROUND_TRUTH_FIELDS:
            value = row[field]
            if isinstance(value, str) and len(value) > 3:
                assert value not in prompt, f"{row['passage']}.{field} leaked"


def test_example_input_fields_match_the_schema(example):
    """If the schema grows an input field, the example must be updated with it."""
    assert example.INPUT_FIELDS == INPUT_FIELDS


@pytest.mark.parametrize(
    "reference,hypothesis",
    [
        ("ABCDE", "ABCDE"),
        ("ABCDE", "ABXDE"),
        ("ABCDE", ""),
        ("", "ABC"),
        ("AB", "ABCDEFGH"),
        ("BETWEENSUBTLESHADING", "BETWENSUBTLESHADNG"),
    ],
)
def test_example_cer_matches_the_module(example, reference, hypothesis):
    assert example.character_error_rate(reference, hypothesis) == character_error_rate(
        reference, hypothesis
    )


@pytest.mark.parametrize(
    "text", ["be tween!", "a?b", "café", "ΑΒΓ", "", "ALREADYCLEAN", "mIxEd 123 cAsE"]
)
def test_example_letters_only_matches_the_module(example, text):
    assert example.letters_only(text) == letters_only(text)


def test_example_crib_score_matches_the_module(example, rows):
    k4 = next(r for r in rows if r["passage"] == "K4")
    for hypothesis in ("BERLIN" + "?" * 91, "?" * 97, k4["problem"]):
        assert example.crib_score(k4["cribs"], hypothesis) == crib_score(
            k4["cribs"], hypothesis
        )
