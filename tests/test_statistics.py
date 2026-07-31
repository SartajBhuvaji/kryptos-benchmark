"""Verification for the index of coincidence and quadgram fitness.

These two metrics need no answer to compute, which is what makes them usable where CER
cannot go. The tests are correspondingly about *discrimination*: a metric that returns a
number for every input is worthless unless the numbers separate the cases it claims to
separate. So the assertions are mostly comparative -- transposition against substitution,
real plaintext against shuffled -- rather than checks against magic constants.

Where an absolute value is asserted it is one that follows from the definition (a
transposition cannot change the IoC, because it does not change the letters) rather than
one measured and pinned.
"""

from __future__ import annotations

import json
import pathlib
import random

import pytest

from kryptos.algorithms.baseline import build
from kryptos.scoring import (
    ENGLISH_IOC,
    RANDOM_IOC,
    index_of_coincidence,
    letter_frequencies,
    letters_only,
)
from kryptos.scoring import ngram


@pytest.fixture(scope="module")
def rows() -> dict[str, dict]:
    with pathlib.Path(build.OUTPUT).open(encoding="utf-8") as fh:
        return {r["passage"]: r for r in map(json.loads, fh)}


@pytest.fixture(scope="module")
def model():
    return ngram.load()


# --- index of coincidence ---------------------------------------------------------


def test_ioc_of_uniform_text_is_one():
    """Every pair matches, so the probability of a match is 1."""
    assert index_of_coincidence("AAAAA") == 1.0


def test_ioc_of_all_distinct_letters_is_zero():
    assert index_of_coincidence("ABCDEFG") == 0.0


def test_ioc_is_undefined_below_two_characters():
    """There is no pair to draw. 0.0 is a floor, not a measurement."""
    assert index_of_coincidence("") == 0.0
    assert index_of_coincidence("A") == 0.0


def test_ioc_ignores_order():
    """It is a property of the letter multiset alone -- which is exactly why it survives
    a transposition and why it identifies the cipher family."""
    text = "SLOWLYDESPARATLYSLOWLY"
    shuffled = list(text)
    random.Random(7).shuffle(shuffled)
    assert index_of_coincidence("".join(shuffled)) == index_of_coincidence(text)


def test_random_letters_sit_near_the_uniform_value():
    rng = random.Random(3)
    text = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(5000))
    assert index_of_coincidence(text) == pytest.approx(RANDOM_IOC, abs=0.003)


# --- the tier-3 discriminator, on real data ---------------------------------------


def test_k3_transposition_preserves_the_ioc_exactly(rows):
    """The plan's headline check. A route transposition permutes positions and touches
    no letter identities, so plaintext and ciphertext must agree to the last bit."""
    k3 = rows["K3"]
    plaintext = letters_only(k3["answer"])
    ciphertext = letters_only(k3["problem"])
    assert index_of_coincidence(ciphertext) == index_of_coincidence(plaintext)


def test_k3_ciphertext_ioc_is_english(rows):
    ioc = index_of_coincidence(letters_only(rows["K3"]["problem"]))
    assert ioc == pytest.approx(ENGLISH_IOC, abs=0.005)


@pytest.mark.parametrize("passage", ["K1", "K2"])
def test_quagmire_ciphertext_ioc_is_measurably_lower(rows, passage):
    """A polyalphabetic substitution flattens the distribution. If this did not separate
    from K3, the metric would not be a family discriminator at all."""
    substitution = index_of_coincidence(letters_only(rows[passage]["problem"]))
    transposition = index_of_coincidence(letters_only(rows["K3"]["problem"]))
    assert substitution < transposition - 0.015
    assert substitution < ENGLISH_IOC


def test_solved_plaintexts_all_sit_near_the_english_norm(rows):
    for passage in ("K1", "K2", "K3"):
        ioc = index_of_coincidence(letters_only(rows[passage]["answer"]))
        assert ioc == pytest.approx(ENGLISH_IOC, abs=0.006), passage


def test_letter_frequencies_sum_to_one_and_rank_descending():
    freqs = letter_frequencies(letters_only("THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG"))
    assert sum(freqs.values()) == pytest.approx(1.0)
    assert list(freqs.values()) == sorted(freqs.values(), reverse=True)


def test_letter_frequencies_of_empty_text_is_empty():
    assert letter_frequencies("") == {}


# --- quadgram fitness -------------------------------------------------------------


def test_committed_table_matches_its_recorded_checksum():
    """Every fitness score in the benchmark moves with this file, so it is pinned. No
    network: this checks the artifact in the repository, not the upstream URL."""
    import gzip
    import hashlib

    from kryptos.scoring.data import build as table_build

    table = gzip.decompress(table_build.OUTPUT.read_bytes())
    assert hashlib.sha256(table).hexdigest() == table_build.TABLE_SHA256


def test_table_is_stored_deterministically():
    """gzip with mtime=0, so rebuilding it produces a byte-identical artifact and a
    re-fetch shows up as a real diff rather than a timestamp change."""
    import gzip

    from kryptos.scoring.data import build as table_build

    table = gzip.decompress(table_build.OUTPUT.read_bytes())
    assert table_build.compress(table) == table_build.OUTPUT.read_bytes()


def test_table_loads_with_the_expected_shape(model):
    """Pinned to the checksummed artifact -- see data/PROVENANCE.md."""
    assert len(model.log_probability) == 389_373
    assert model.total == 4_224_127_912


def test_most_frequent_quadgram_has_the_highest_log_probability(model):
    assert max(model.log_probability, key=model.log_probability.get) == "TION"


def test_every_log_probability_is_negative(model):
    """They are log10 of probabilities below 1, so none may be positive."""
    assert max(model.log_probability.values()) < 0


def test_floor_is_below_every_observed_quadgram(model):
    """An unseen quadgram must be worse than the rarest seen one, or the penalty is not
    a penalty."""
    assert model.floor < min(model.log_probability.values())


def test_unseen_quadgrams_get_the_floor(model):
    absent = "JQXZ"
    assert absent not in model.log_probability
    assert model.score(absent) == model.floor


def test_fitness_ranks_real_plaintext_above_shuffled(rows):
    """The plan's second verification. Same letters, same IoC, same length -- only the
    order differs, so this isolates what the n-gram model contributes over the IoC."""
    for passage in ("K1", "K2", "K3"):
        plaintext = letters_only(rows[passage]["answer"])
        shuffled = list(plaintext)
        random.Random(11).shuffle(shuffled)
        assert ngram.fitness(plaintext) > ngram.fitness("".join(shuffled)) + 1.0, passage


def test_fitness_ranks_plaintext_above_its_own_ciphertext(rows):
    """What a solver would actually watch while hill-climbing."""
    for passage in ("K1", "K2", "K3"):
        assert ngram.fitness(letters_only(rows[passage]["answer"])) > ngram.fitness(
            letters_only(rows[passage]["problem"])
        ), passage


def test_fitness_is_length_independent_where_score_is_not(rows):
    """Doubling the text roughly doubles the total but leaves the mean where it was --
    which is the whole reason the mean exists, given passages of 63 and 869 characters.

    Only roughly: doubling an n-character text gives 2n-3 windows rather than 2(n-3),
    and the three windows straddling the join are nonsense English. Both effects shrink
    as n grows, so this uses K3 rather than the 61-letter K1.
    """
    text = letters_only(rows["K3"]["answer"])
    assert ngram.score(text * 2) == pytest.approx(2 * ngram.score(text), rel=0.02)
    assert ngram.fitness(text * 2) == pytest.approx(ngram.fitness(text), rel=0.02)


def test_score_grows_with_length_so_it_cannot_compare_passages(rows):
    """Guards the test above against passing vacuously: if score were already
    length-independent, the mean would not be adding anything."""
    k1 = letters_only(rows["K1"]["answer"])
    k3 = letters_only(rows["K3"]["answer"])
    assert ngram.score(k3) < ngram.score(k1) * 3      # K3 is the more English of the two
    assert ngram.fitness(k3) > ngram.fitness(k1)      # yet ranks higher per quadgram


def test_short_text_returns_the_floor_rather_than_a_flattering_zero(model):
    """Below one window there is nothing to observe. Returning 0.0 -- the value a perfect
    match would have -- would rank an empty answer above every real attempt."""
    assert model.fitness("ABC") == model.floor
    assert model.fitness("") == model.floor


def test_score_of_too_short_text_is_zero(model):
    """The sum over zero windows. Distinct from fitness, which must not report 0.0."""
    assert model.score("ABC") == 0.0


def test_model_rejects_an_empty_table():
    with pytest.raises(ValueError, match="non-empty"):
        ngram.QuadgramModel({})


def test_parse_reads_the_upstream_format():
    counts = ngram.parse("TION 13168375\nNTHE 11234972\n\n")
    assert counts == {"TION": 13168375, "NTHE": 11234972}


def test_a_hand_built_model_computes_the_documented_arithmetic():
    """Pins the formula independently of the 1.3 MB table."""
    import math

    model = ngram.QuadgramModel({"ABCD": 3, "BCDE": 1})
    assert model.total == 4
    assert model.log_probability["ABCD"] == pytest.approx(math.log10(0.75))
    assert model.floor == pytest.approx(math.log10(0.01 / 4))
    # "ABCDE" holds exactly the two windows ABCD and BCDE.
    assert model.score("ABCDE") == pytest.approx(math.log10(0.75) + math.log10(0.25))
    assert model.fitness("ABCDE") == pytest.approx(model.score("ABCDE") / 2)
