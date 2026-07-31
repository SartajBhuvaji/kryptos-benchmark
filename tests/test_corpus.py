"""Verification for the isomorph plaintext corpus.

Three properties matter, and they pull against each other, which is why they are all
tested rather than just the easy one:

*exactness* -- a generated passage is exactly the requested length, because a route
transposition needs a grid width dividing the text and a corpus that could only supply
"about 300 characters" would be choosing the geometry itself;

*determinism* -- the same seed gives byte-identical output, which is what makes a
published snapshot possible at all;

*naturalness* -- the recombined text still has the statistics of English, since the whole
argument for recombining rather than generating is that the statistics survive it. That
one is checked against the metrics from Phase 2 rather than asserted.
"""

from __future__ import annotations

import random

import pytest

from kryptos.algorithms.isomorph import corpus
from kryptos.scoring import ENGLISH_IOC, index_of_coincidence, quadgram_fitness


@pytest.fixture(scope="module")
def loaded():
    return corpus.load()


# --- normalisation ----------------------------------------------------------------


def test_normalize_produces_the_carved_form():
    assert corpus.normalize("I almost wish I had never heard it.") == "IALMOSTWISHIHADNEVERHEARDIT"


def test_normalize_drops_everything_that_is_not_a_letter():
    assert corpus.normalize("three-fourths, 1895 — “yes”?") == "THREEFOURTHSYES"


def test_normalize_is_idempotent():
    once = corpus.normalize("The Major he gazed on the wine.")
    assert corpus.normalize(once) == once


# --- the committed corpus ---------------------------------------------------------


def test_corpus_matches_its_recorded_checksum():
    """Generated plaintexts change if this file changes, so it is pinned."""
    import gzip
    import hashlib

    from kryptos.algorithms.isomorph.data import build

    payload = gzip.decompress(build.OUTPUT.read_bytes())
    assert hashlib.sha256(payload).hexdigest() == build.CORPUS_SHA256


def test_corpus_is_stored_deterministically():
    import gzip

    from kryptos.algorithms.isomorph.data import build

    payload = gzip.decompress(build.OUTPUT.read_bytes())
    assert build.compress(payload) == build.OUTPUT.read_bytes()


def test_corpus_draws_on_every_declared_work(loaded):
    from kryptos.algorithms.isomorph.data import build

    assert set(loaded.works) == {w["id"] for w in build.WORKS}


def test_every_clause_is_within_the_declared_length_bounds(loaded):
    from kryptos.algorithms.isomorph.data import build

    for clause in loaded.clauses:
        assert build.MIN_CLAUSE_LETTERS <= len(clause.letters) <= build.MAX_CLAUSE_LETTERS


def test_clauses_carry_no_digits(loaded):
    """They would normalise away silently, turning "1895" into nothing and joining the
    words either side of it."""
    assert not any(ch.isdigit() for clause in loaded.clauses for ch in clause.text)


def test_accented_letters_are_folded_not_dropped():
    """Normalisation alone deletes an accented letter, welding its neighbours into a
    sequence that occurs in no English word. The builder folds first."""
    from kryptos.algorithms.isomorph.data import build

    assert corpus.normalize(build.deaccent("Ma’ame Pélagie")) == "MAAMEPELAGIE"
    assert corpus.normalize("Ma’ame Pélagie") == "MAAMEPLAGIE"  # what folding prevents


def test_no_clause_normalises_to_fewer_letters_than_it_appears_to_have(loaded):
    """The bug the fold fixes: a clause can pass a length filter counted with
    `str.isalpha` and then normalise shorter, because `é` is alpha but is not A-Z."""
    for clause in loaded.clauses:
        assert len(clause.letters) == sum(ch.isalpha() for ch in clause.text)


def test_empty_corpus_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        corpus.Corpus(())


# --- exact length control ---------------------------------------------------------


@pytest.mark.parametrize("length", [1, 20, 63, 97, 200, 337, 372, 869])
def test_sample_is_exactly_the_requested_length(loaded, length):
    assert len(loaded.sample(length, random.Random(1)).text) == length


def test_sample_length_holds_across_many_seeds(loaded):
    """The final clause is trimmed to land exactly, so this exercises the trim rather
    than getting lucky on clause boundaries."""
    for seed in range(50):
        assert len(loaded.sample(337, random.Random(seed)).text) == 337


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, "63"])
def test_sample_rejects_a_bad_length(loaded, bad):
    with pytest.raises(ValueError, match="positive integer"):
        loaded.sample(bad, random.Random(0))


def test_sample_refuses_to_exceed_the_corpus(loaded):
    with pytest.raises(ValueError, match="corpus holds"):
        loaded.sample(loaded.total_letters + 1, random.Random(0))


def test_text_and_readable_always_agree(loaded):
    """Enforced in __post_init__, so this checks the trim keeps them in step -- cutting
    the readable form and the letters separately is exactly where they could diverge."""
    for seed in range(30):
        sample = loaded.sample(150, random.Random(seed))
        assert sample.text == corpus.normalize(sample.readable)


def test_cut_to_letters_counts_letters_not_characters():
    assert corpus._cut_to_letters("three-fourths of", 6) == "three-f"
    assert corpus._cut_to_letters("abc", 0) == ""


# --- determinism ------------------------------------------------------------------


def test_the_same_seed_gives_identical_output(loaded):
    a = loaded.sample(200, random.Random(20260731))
    b = loaded.sample(200, random.Random(20260731))
    assert a == b


def test_different_seeds_give_different_passages(loaded):
    texts = {loaded.sample(200, random.Random(seed)).text for seed in range(25)}
    assert len(texts) == 25


def test_sequential_draws_from_one_rng_differ(loaded):
    """A generator producing 50 instances from one seeded rng must not emit 50 copies."""
    rng = random.Random(99)
    texts = {loaded.sample(120, rng).text for _ in range(25)}
    assert len(texts) == 25


# --- provenance -------------------------------------------------------------------


def test_provenance_names_only_real_works(loaded):
    sample = loaded.sample(372, random.Random(5))
    assert set(sample.works) <= set(loaded.works)
    assert list(sample.works) == sorted(set(sample.works))


def test_a_passage_is_built_from_several_clauses(loaded):
    """One clause would be a verbatim excerpt of a published book, which is the thing
    recombination exists to avoid."""
    for seed in range(20):
        assert loaded.sample(200, random.Random(seed)).clause_count >= 2


def test_truncation_is_reported_honestly(loaded):
    """`truncated` must describe what happened, not what usually happens."""
    seen = set()
    for seed in range(60):
        sample = loaded.sample(200, random.Random(seed))
        seen.add(sample.truncated)
        rebuilt = corpus.normalize(sample.readable)
        assert rebuilt == sample.text
    assert True in seen, "expected trimming to occur at least once in 60 draws"


def test_plaintext_rejects_inconsistent_content():
    with pytest.raises(ValueError, match="disagree"):
        corpus.Plaintext(text="ABC", readable="XYZ", works=("w",), clause_count=1)


# --- naturalness, measured with the Phase 2 metrics -------------------------------


def test_recombined_text_has_english_statistics(loaded):
    """The argument for recombining rather than generating is that the statistics
    survive it. Checked, not assumed."""
    rng = random.Random(20260731)
    samples = [loaded.sample(length, rng).text for length in (63, 97, 200, 337, 372) * 8]

    mean_ioc = sum(map(index_of_coincidence, samples)) / len(samples)
    assert mean_ioc == pytest.approx(ENGLISH_IOC, abs=0.004)

    mean_fitness = sum(map(quadgram_fitness, samples)) / len(samples)
    assert -4.6 < mean_fitness < -3.8


def test_recombined_text_reads_as_english_not_as_noise(loaded):
    """The discriminating version of the test above: a shuffle of the same letters has
    an identical IoC, so only the n-gram model separates them."""
    rng = random.Random(4)
    for _ in range(10):
        sample = loaded.sample(300, rng).text
        shuffled = list(sample)
        rng.shuffle(shuffled)
        assert quadgram_fitness(sample) > quadgram_fitness("".join(shuffled)) + 1.0


def test_kryptos_sized_lengths_are_all_available(loaded):
    """The generators need the carved span, 63 to 372 characters."""
    rng = random.Random(0)
    for length in range(corpus.KRYPTOS_MIN_LENGTH, corpus.KRYPTOS_MAX_LENGTH + 1, 20):
        assert len(loaded.sample(length, rng).text) == length
