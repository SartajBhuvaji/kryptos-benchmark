"""Tier prompts -- the four task framings the benchmark poses.

Tiers are framings over the existing data, not new datasets. The same generated Quagmire
instance is a tier 1 problem when its keys are supplied and a tier 2 problem when they
are withheld; nothing about the row changes, only what the prompt shows.

The leak rule is per tier, not global
-------------------------------------
Elsewhere in this project the rule is simple: a prompt never contains ground truth. Here
it cannot be, because tier 1 exists precisely to hand the model the keys and see whether
it can execute the algorithm without arithmetic slips. So the invariant splits in two:

* **Always forbidden, at every tier** -- ``answer``, ``answer_readable``, ``solution``,
  and the nulls config's ``deciphered`` intermediate. These are the answer in one form or
  another, and showing any of them makes the score meaningless.
* **Tier-dependent** -- key material. Visible at tier 1, withheld at tiers 2 and 3.

:data:`VISIBLE_FIELDS` states this per tier and :func:`build_prompt` reads it, so the
policy is data rather than something re-derived inside each branch. Tests assert both
halves: that forbidden fields never appear anywhere, and that tier 1 actually does
include the keys -- an over-zealous filter that hid them would silently turn tier 1 into
a second tier 2 and the two would stop measuring different things.
"""

from __future__ import annotations

from kryptos.scoring.thresholds import TIERS, tier

#: Fields every tier may show. These are the input columns and nothing else.
INPUT_FIELDS: tuple[str, ...] = (
    "problem",
    "problem_letters_only",
    "problem_length",
    "cribs",
)

#: Never shown at any tier, in any config. Each is the answer or trivially yields it.
FORBIDDEN_FIELDS: tuple[str, ...] = (
    "answer",
    "answer_readable",
    "solution",
    "deciphered",
)

#: Key material, by config. Shown at tier 1 only.
KEY_FIELDS: tuple[str, ...] = (
    "cipher_name",
    "alphabet_keyword",
    "keyed_alphabet",
    "indicator_keyword",
    "period",
    "route",
    "solver_route",
    "layers",
    "vigenere_key",
    "hill_block_size",
    "hill_matrix",
    "null",
    "null_group",
    "null_stride",
    "null_count",
)

#: What each tier may put in front of the model.
VISIBLE_FIELDS: dict[int, tuple[str, ...]] = {
    1: (*INPUT_FIELDS, *KEY_FIELDS),
    2: INPUT_FIELDS,
    3: INPUT_FIELDS,
    4: INPUT_FIELDS,
}

SYSTEM_PROMPT = """You are an expert cryptanalyst working on classical ciphers.

Work the problem rather than recalling it. If you recognise the ciphertext, still derive
the answer from the text itself -- state the cipher, the key, and the steps that take the
ciphertext to your plaintext.

Report the plaintext as uppercase A-Z with no spaces or punctuation."""

#: Tier-specific guidance appended to the system prompt. Each says what is being tested,
#: because a model that misreads the task fails for the wrong reason.
TIER_GUIDANCE: dict[int, str] = {
    1: "The cipher and its complete key are given to you. Nothing needs to be "
       "discovered. What is being tested is whether you can execute the algorithm "
       "exactly -- index into the right alphabet, step the key correctly, and make no "
       "arithmetic slips across the whole message.",
    2: "You are given ciphertext and nothing else. Useful starting points: the index of "
       "coincidence distinguishes substitution from transposition (a transposition "
       "leaves it at the English norm of about 0.066 and preserves letter frequencies "
       "exactly). For a periodic polyalphabetic cipher, find the period first, then "
       "solve each residue class as a separate monoalphabetic substitution.",
    3: "You are given ciphertext and nothing else. Check the letter frequencies before "
       "assuming a substitution: if they match ordinary English and the index of "
       "coincidence sits near 0.066, the letters have been rearranged rather than "
       "replaced, and the problem is geometric rather than one of frequency analysis.",
    4: "This ciphertext is unsolved. Nobody knows its method, and a complete solution is "
       "not the expectation. Produce your best hypothesis: propose a mechanism "
       "consistent with the confirmed fragments below and apply it to the full text. "
       "Your answer is judged on whether the fragments land at their stated positions "
       "and whether the rest reads as English -- so do not pad around the fragments "
       "with filler, and do not omit the parts you are unsure of.",
}


#: A worked example of the response format, appended to the system prompt.
#:
#: The design document notes that imposing a strict output schema can degrade reasoning
#: when the model has not been shown what a filled-in answer looks like -- it spends
#: attention satisfying the schema instead of solving the problem. The demonstration
#: costs a few hundred tokens and removes that failure mode.
#:
#: Deliberately built on a *different* cipher (Caesar) and a throwaway plaintext, so it
#: cannot serve as a hint for any benchmark instance. Every passage in this benchmark is
#: Quagmire, transposition, or a composite; none is a Caesar shift.
FORMAT_EXAMPLE = """Here is the response format, worked on an unrelated toy problem.

Ciphertext (11 characters):

WKHTXLFNIRA

A correct response:

{
  "cipher": "Caesar shift",
  "key": "shift 3",
  "method": "Letter frequencies matched English with a uniform offset. Testing shift 3 \
gave readable text: W->T, K->H, H->E.",
  "plaintext": "THEQUICKFOX"
}

Note that "plaintext" is uppercase A-Z with no spaces, and that "method" states how the \
key was found rather than merely naming the cipher. Give your best attempt in \
"plaintext" even when you are unsure -- a partial recovery scores better than an empty \
string."""


def system_prompt(number: int, *, few_shot: bool = True) -> str:
    """The system prompt for a tier: base, that tier's framing, and a format example.

    ``few_shot=False`` drops the worked example, so its effect can be measured rather
    than assumed.
    """
    parts = [SYSTEM_PROMPT, TIER_GUIDANCE[tier(number).number]]
    if few_shot:
        parts.append(FORMAT_EXAMPLE)
    return "\n\n".join(parts)


def visible(row: dict, number: int) -> dict:
    """Project a row down to what ``number`` may show. The enforcement point.

    Filtering here rather than at each render site means a new tier, or a new config with
    new key fields, cannot leak by being handled in one branch and forgotten in another.
    """
    allowed = VISIBLE_FIELDS[tier(number).number]
    return {key: row[key] for key in allowed if key in row}


def build_prompt(row: dict, number: int, *, delimited: bool = False) -> str:
    """Render the user-facing prompt for one instance at one tier."""
    fields = visible(row, number)

    ciphertext = fields["problem"]
    if delimited:
        # The design doc's tokenization mitigation: one token per character, so the model
        # can address individual letters by position instead of guessing at subword
        # boundaries. A render-time axis, orthogonal to the tier.
        ciphertext = " ".join(ciphertext)

    parts = [
        f"Ciphertext ({fields['problem_length']} characters):",
        "",
        ciphertext,
        "",
    ]

    keys = _key_lines(fields)
    if keys:
        parts += ["The cipher and its key:", "", *keys, ""]

    if fields.get("cribs"):
        parts += [
            "Confirmed plaintext fragments, at these 1-indexed positions in the "
            "plaintext:",
            "",
            *(f"  {c['plaintext']} at {c['start']}-{c['end']}" for c in fields["cribs"]),
            "",
        ]

    parts.append("Recover the plaintext.")
    return "\n".join(parts)


def _key_lines(fields: dict) -> list[str]:
    """Render whichever key fields this config actually carries.

    Driven by what is present rather than by cipher name, so a new config with a new key
    shape needs only an entry in :data:`KEY_FIELDS`.
    """
    labels = {
        "cipher_name": "cipher",
        "alphabet_keyword": "alphabet keyword",
        "keyed_alphabet": "keyed alphabet",
        "indicator_keyword": "indicator keyword",
        "period": "period",
        "route": "route (width:quarter_turns per stage, encryption direction)",
        "solver_route": "solver route (run forward on the ciphertext)",
        "layers": "layers, in application order",
        "vigenere_key": "Vigenere key",
        "hill_block_size": "Hill block size",
        "hill_matrix": "Hill key matrix (row-major)",
        "null": "null letter",
        "null_group": "message letters between nulls",
        "null_stride": "null every Nth character",
        "null_count": "number of nulls",
    }

    lines = []
    for key in KEY_FIELDS:
        value = fields.get(key)
        if value is None or value == [] or value == "":
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        lines.append(f"  {labels[key]}: {value}")
    return lines


def default_tier(row: dict) -> int:
    """The tier a row is normally posed at, derived from the row itself.

    Per row rather than per config, because the baseline holds both kinds: K1-K3 have
    answers and K4 does not, so a config-level default would be wrong for one of them
    whichever way it went.

    A default, not a constraint -- any instance can be posed at any tier, which is what
    makes tiers framings rather than datasets.
    """
    if row.get("answer") is None:
        return 4                      # unsolved: nothing to score CER against
    if row.get("cipher_family") == "transposition":
        return 3
    return 2


__all__ = [
    "FORBIDDEN_FIELDS",
    "FORMAT_EXAMPLE",
    "INPUT_FIELDS",
    "KEY_FIELDS",
    "TIERS",
    "TIER_GUIDANCE",
    "VISIBLE_FIELDS",
    "build_prompt",
    "default_tier",
    "system_prompt",
    "visible",
]
