"""Verification for the isomorph generators.

The round-trip tests are the ones that matter. A generator that produces a plausible
ciphertext and a parameter set that does not actually decrypt it would be worse than no
generator at all: the dataset would look right and score everything wrong. So every kind
is decrypted back with the Phase 1 ciphers, driven *only* by the parameters the instance
publishes -- not by anything retained from generation.

The screening tests come second in importance and are easy to under-weight. Random keys
produce degenerate ciphers often enough that an unscreened generator ships them: a
shift-zero Quagmire column copies plaintext through in clear, a two-stage route can
compose to the identity, and roughly half of random matrices over Z/26 have no inverse.
Each is checked over enough instances to catch a screen that silently stopped working.
"""

from __future__ import annotations

import random

import pytest

from kryptos.algorithms.ciphers import hill, quagmire, transposition, vigenere
from kryptos.algorithms.isomorph import corpus
from kryptos.algorithms.isomorph import generate as gen
from kryptos.scoring import ENGLISH_IOC, index_of_coincidence, quadgram_fitness

# The baseline's own periodic-consistency check, reused rather than reimplemented so
# "the same check the baseline passes" is literally true.
from test_baseline import periodic_violations

SEED = 20260731
KINDS = ("quagmire", "transposition", "composite", "nulls")


@pytest.fixture(scope="module")
def batches() -> dict[str, list[gen.Instance]]:
    return {kind: gen.generate(kind, 20, seed=SEED) for kind in KINDS}


def route_of(encoded: str) -> tuple[transposition.Stage, ...]:
    return tuple(tuple(int(part) for part in stage.split(":")) for stage in encoded.split(","))


# --- round trips, driven only by published parameters -----------------------------


def test_quagmire_instances_round_trip(batches):
    for instance in batches["quagmire"]:
        p = instance.parameters
        assert quagmire.decrypt(
            instance.ciphertext, p["alphabet_keyword"], p["indicator_keyword"]
        ) == instance.answer


def test_transposition_instances_round_trip(batches):
    for instance in batches["transposition"]:
        route = route_of(instance.parameters["route"])
        assert transposition.decrypt(instance.ciphertext, route) == instance.answer


def test_transposition_solver_route_runs_forward_on_the_ciphertext(batches):
    """When a two-stage inverse exists the solution states it, so it must be correct."""
    for instance in batches["transposition"]:
        encoded = instance.parameters["solver_route"]
        if encoded is None:
            continue
        assert transposition.encrypt(instance.ciphertext, route_of(encoded)) == instance.answer


def test_composite_instances_round_trip(batches):
    """Layers must be undone in reverse: Hill first, then Vigenere."""
    for instance in batches["composite"]:
        p = instance.parameters
        matrix = tuple(tuple(row) for row in p["hill_matrix"])
        recovered = vigenere.decrypt(hill.decrypt(instance.ciphertext, matrix), p["vigenere_key"])
        assert recovered == instance.answer


def test_nulls_instances_round_trip(batches):
    for instance in batches["nulls"]:
        p = instance.parameters
        deciphered = quagmire.decrypt(
            instance.ciphertext, p["alphabet_keyword"], p["indicator_keyword"]
        )
        assert deciphered == p["deciphered"]
        positions = set(p["null_positions"])
        stripped = "".join(ch for i, ch in enumerate(deciphered) if i not in positions)
        assert stripped == instance.answer


def test_nulls_are_discarded_by_position_not_by_letter(batches):
    """W occurs naturally in English, so a "delete every W" rule would delete real
    letters. At least one instance must actually exhibit that, or the distinction is
    untested."""
    natural = [i for i in batches["nulls"] if gen.NULL_LETTER in i.answer]
    assert natural, "no generated message contained a natural W; the risk is untested"
    for instance in natural:
        p = instance.parameters
        deciphered = p["deciphered"]
        by_letter = deciphered.replace(gen.NULL_LETTER, "")
        assert by_letter != instance.answer
        assert len(deciphered) - len(p["null_positions"]) == len(instance.answer)


def test_nulls_sit_exactly_where_the_solution_says(batches):
    for instance in batches["nulls"]:
        p = instance.parameters
        assert all(p["deciphered"][i] == gen.NULL_LETTER for i in p["null_positions"])
        # "groups of N letters, each followed by one null"
        stride = p["null_stride"]
        assert p["null_positions"] == list(range(p["null_group"], len(instance.ciphertext), stride))


# --- screening --------------------------------------------------------------------


def test_no_quagmire_instance_has_a_degenerate_column(batches):
    """A shift-zero column copies its plaintext through in clear, one position in every
    period, legible in the ciphertext."""
    for instance in batches["quagmire"] + batches["nulls"]:
        p = instance.parameters
        assert quagmire.degenerate_columns(p["indicator_keyword"], p["alphabet_keyword"]) == []


def test_quagmire_alphabets_are_actually_mixed(batches):
    """An unmixed alphabet reduces Quagmire III to an ordinary Vigenere."""
    for instance in batches["quagmire"] + batches["nulls"]:
        assert instance.parameters["keyed_alphabet"] != quagmire.ALPHABET


def test_published_period_is_the_true_period(batches):
    """Not the keyword length: a repeating indicator like ABAB is a period-2 cipher
    wearing a 4-letter key, and publishing 4 would be a false statement."""
    for instance in batches["quagmire"] + batches["nulls"]:
        p = instance.parameters
        assert p["period"] == quagmire.period(p["indicator_keyword"], p["alphabet_keyword"])
        assert p["period"] == len(p["indicator_keyword"])


def test_no_route_is_the_identity(batches):
    for instance in batches["transposition"]:
        route = route_of(instance.parameters["route"])
        assert not transposition.is_identity(len(instance.ciphertext), route)
        assert instance.ciphertext != instance.answer


def test_every_hill_matrix_is_invertible(batches):
    """About half of random matrices over Z/26 are not, since 26 is not prime."""
    for instance in batches["composite"]:
        matrix = tuple(tuple(row) for row in instance.parameters["hill_matrix"])
        assert hill.is_invertible(matrix)


def test_route_widths_divide_the_text(batches):
    for instance in batches["transposition"]:
        for width, turns in route_of(instance.parameters["route"]):
            assert len(instance.ciphertext) % width == 0
            assert 1 <= turns <= 3      # a zero turn would collapse the stage
            assert 1 < width < len(instance.ciphertext)


def test_screening_reports_failure_rather_than_looping_forever():
    """A constraint that cannot be met must raise, not spin."""
    with pytest.raises(ValueError, match="usable grid width"):
        gen.transposition_route(97, random.Random(0))   # 97 is prime


# --- the baseline's own check, applied to generated instances ---------------------


def test_generated_quagmires_pass_the_baseline_periodic_check(batches):
    """The strongest structural check the baseline has. If an isomorph failed it, the
    isomorph would not be structurally identical to K1 and K2, which is the one thing it
    is required to be."""
    for instance in batches["quagmire"]:
        p = instance.parameters
        assert periodic_violations(instance.ciphertext, instance.answer, p["period"]) == []


def test_the_periodic_check_still_rejects_wrong_periods(batches):
    """Guards the test above against passing vacuously."""
    for instance in batches["quagmire"][:5]:
        wrong = instance.parameters["period"] + 1
        assert periodic_violations(instance.ciphertext, instance.answer, wrong) != []


# --- determinism ------------------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_the_same_seed_gives_byte_identical_output(kind):
    first = gen.generate(kind, 5, seed=99)
    second = gen.generate(kind, 5, seed=99)
    assert [i.ciphertext for i in first] == [i.ciphertext for i in second]
    assert [i.parameters for i in first] == [i.parameters for i in second]
    assert [i.solution for i in first] == [i.solution for i in second]


@pytest.mark.parametrize("kind", KINDS)
def test_different_seeds_give_disjoint_plaintexts_and_keys(kind):
    a = gen.generate(kind, 8, seed=1)
    b = gen.generate(kind, 8, seed=2)
    assert not {i.answer for i in a} & {i.answer for i in b}
    assert not {i.ciphertext for i in a} & {i.ciphertext for i in b}


def test_configs_sharing_one_seed_do_not_share_keys_or_text():
    """One published snapshot uses one seed across every config. Without salting, they
    would draw the same keywords and the same clauses."""
    quag = gen.generate("quagmire", 8, seed=SEED)
    nulls = gen.generate("nulls", 8, seed=SEED)
    assert not {i.answer for i in quag} & {i.answer for i in nulls}
    assert not (
        {i.parameters["alphabet_keyword"] for i in quag}
        & {i.parameters["alphabet_keyword"] for i in nulls}
    )


def test_stream_salt_is_stable_across_processes():
    """Salted with SHA-256, not hash() -- which is randomised per process and would make
    a seeded snapshot unreproducible."""
    assert gen.stream("quagmire", 5).random() == gen.stream("quagmire", 5).random()
    assert gen.stream("quagmire", 5).random() != gen.stream("nulls", 5).random()


def test_no_seed_gives_a_fresh_draw():
    """The contamination-resistance path: nothing published, nothing trainable."""
    a = gen.generate("quagmire", 4)
    b = gen.generate("quagmire", 4)
    assert {i.ciphertext for i in a} != {i.ciphertext for i in b}
    assert all(i.seed is None for i in a)


def test_seed_is_recorded_on_seeded_instances():
    assert all(i.seed == 42 for i in gen.generate("quagmire", 3, seed=42))


# --- shape of what is produced -----------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_instances_are_kryptos_sized(kind, batches):
    for instance in batches[kind]:
        assert corpus.KRYPTOS_MIN_LENGTH <= len(instance.ciphertext) <= corpus.KRYPTOS_MAX_LENGTH


@pytest.mark.parametrize("kind", KINDS)
def test_ids_are_unique_within_a_batch(kind, batches):
    ids = [i.id for i in batches[kind]]
    assert len(set(ids)) == len(ids)
    assert all(i.id.startswith(f"kryptos-isomorph-{kind}-") for i in batches[kind])


@pytest.mark.parametrize("kind", KINDS)
def test_ciphertext_is_never_the_plaintext(kind, batches):
    for instance in batches[kind]:
        assert instance.ciphertext != instance.answer


@pytest.mark.parametrize("kind", KINDS)
def test_everything_is_carved_form(kind, batches):
    for instance in batches[kind]:
        assert instance.ciphertext.isalpha() and instance.ciphertext.isupper()
        assert instance.answer.isalpha() and instance.answer.isupper()


@pytest.mark.parametrize("kind", KINDS)
def test_provenance_is_recorded(kind, batches):
    for instance in batches[kind]:
        assert instance.source_works
        assert instance.clause_count >= 1
        assert corpus.normalize(instance.answer_readable) == instance.answer


def test_substitution_preserves_length_and_transposition_anagrams(batches):
    for instance in batches["quagmire"]:
        assert len(instance.ciphertext) == len(instance.answer)
    for instance in batches["transposition"]:
        assert sorted(instance.ciphertext) == sorted(instance.answer)


def test_nulls_answer_is_shorter_than_its_ciphertext(batches):
    for instance in batches["nulls"]:
        assert len(instance.answer) == len(instance.ciphertext) - instance.parameters["null_count"]


# --- generated ground truth --------------------------------------------------------


@pytest.mark.parametrize("kind", KINDS)
def test_solution_states_the_instance_s_own_parameters(kind, batches):
    """Solutions are rendered from parameters, never hand-written -- the defect Phase 1.5
    had to correct in the baseline was a hand-written solution going stale."""
    for instance in batches[kind]:
        for key in ("alphabet_keyword", "indicator_keyword", "vigenere_key", "route"):
            value = instance.parameters.get(key)
            if isinstance(value, str):
                assert value in instance.solution, f"{instance.id}: {key} missing"


def test_solutions_differ_between_instances(batches):
    """A template that ignored its parameters would produce identical prose."""
    for kind in KINDS:
        solutions = {i.solution for i in batches[kind]}
        assert len(solutions) > 1


def test_parameters_are_json_serialisable(batches):
    import json

    for kind in KINDS:
        for instance in batches[kind]:
            assert json.loads(json.dumps(instance.parameters)) == instance.parameters


def test_proxies_disclaim_being_models_of_k4(batches):
    """Nobody knows K4's method, so the framing must not imply solving these says
    anything about it."""
    for instance in batches["composite"] + batches["nulls"]:
        assert "not a model of K4" in instance.solution


# --- statistical behaviour, using the Phase 2 metrics -----------------------------


def test_generated_transpositions_preserve_the_ioc_exactly(batches):
    """The family discriminator has to work on isomorphs exactly as it does on K3, or
    they are not isomorphs. Exact equality is the real property: a permutation cannot
    change a letter multiset."""
    for instance in batches["transposition"]:
        assert index_of_coincidence(instance.ciphertext) == index_of_coincidence(instance.answer)


def test_generated_transposition_ioc_sits_at_the_english_norm_on_average(batches):
    """Per instance it cannot: at 63 characters the IoC is far too noisy to pin, and
    asserting a tight bound on a single short passage would be measuring luck. The batch
    mean is the honest form of this check."""
    instances = batches["transposition"]
    mean = sum(index_of_coincidence(i.ciphertext) for i in instances) / len(instances)
    assert mean == pytest.approx(ENGLISH_IOC, abs=0.008)


def test_generated_substitutions_flatten_the_ioc(batches):
    """Averaged over the batch: a single short passage is noisy, but a polyalphabetic
    cipher must pull the distribution toward uniform overall."""
    for kind in ("quagmire", "composite"):
        mean = sum(index_of_coincidence(i.ciphertext) for i in batches[kind]) / len(batches[kind])
        assert mean < ENGLISH_IOC - 0.012, kind


@pytest.mark.parametrize("kind", KINDS)
def test_plaintexts_read_as_english_and_ciphertexts_do_not(kind, batches):
    for instance in batches[kind]:
        assert quadgram_fitness(instance.answer) > quadgram_fitness(instance.ciphertext)


# --- input validation --------------------------------------------------------------


def test_unknown_kind_is_rejected():
    with pytest.raises(ValueError, match="unknown kind"):
        gen.generate("enigma", 1, seed=1)


@pytest.mark.parametrize("count", [0, -1, 1.5, True])
def test_bad_count_is_rejected(count):
    with pytest.raises(ValueError, match="positive integer"):
        gen.generate("quagmire", count, seed=1)


def test_inverted_length_range_is_rejected():
    with pytest.raises(ValueError, match="exceeds"):
        gen.generate("quagmire", 1, seed=1, min_length=200, max_length=100)


def test_composite_refuses_a_length_it_cannot_block():
    with pytest.raises(ValueError, match="not a multiple"):
        gen.composite_instance(random.Random(0), 100)
