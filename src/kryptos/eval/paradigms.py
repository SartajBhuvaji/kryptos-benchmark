"""The two evaluation paradigms: chain of thought, and tool use.

Same instance, same tier, same prompt, same output schema — the only difference is
whether the model may run code. That is the point: the gap between the two is a result in
its own right, and it is only a result if nothing else varies. Both paradigms therefore
return the same :class:`~kryptos.eval.providers.Attempt`, which the scoring path consumes
without knowing which produced it.

Chain of thought
----------------
One request. The model reasons in its thinking blocks and returns a JSON answer. Whatever
arithmetic a Quagmire decryption needs, it does in its head. Runs on any provider.

Tool use
--------
The same request plus a server-side code execution sandbox. The model writes Python, it
runs in an isolated container with no network egress, the model reads stdout and iterates.
Server-side was chosen over a local container so the benchmark has no Docker prerequisite
(plan gate 4.1); the cost is that this paradigm is Claude-only until a container backend
lands behind the same interface — :mod:`kryptos.eval.providers` raises rather than
quietly downgrading it to chain of thought.

This module owns what a paradigm *is*: the shared answer schema, the one extra paragraph
of guidance tool use adds, and the single entry point both go through. Carrying the
prompt to an actual API is :mod:`kryptos.eval.providers`, and how the answer is scored is
:mod:`kryptos.eval.results`. Neither of those asks which paradigm it is handling.
"""

from __future__ import annotations

from kryptos.eval import providers, tiers
from kryptos.eval.providers import (  # re-exported: the shape callers already import
    CODE_EXECUTION_TOOL,
    MAX_RESUMES,
    Attempt,
)

__all__ = [
    "ANSWER_SCHEMA",
    "Attempt",
    "CODE_EXECUTION_TOOL",
    "MAX_RESUMES",
    "PARADIGMS",
    "TOOL_USE_GUIDANCE",
    "solve",
]

PARADIGMS = ("cot", "tool_use")

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "cipher": {
            "type": "string",
            "description": "The cipher you identified, or 'unknown' if you could not.",
        },
        "key": {
            "type": "string",
            "description": "Keys or parameters recovered, or 'unknown'.",
        },
        "method": {
            "type": "string",
            "description": "How you got from ciphertext to plaintext, in a few sentences.",
        },
        "plaintext": {
            "type": "string",
            "description": "Recovered plaintext, uppercase A-Z only, no spaces. "
            "Your best attempt even if you are unsure.",
        },
    },
    "required": ["cipher", "key", "method", "plaintext"],
    "additionalProperties": False,
}

TOOL_USE_GUIDANCE = """You have a Python sandbox. Use it.

Write and run code to do the mechanical work -- building keyed alphabets, stepping the
key, permuting grids, computing the index of coincidence and letter frequencies. Print
intermediate results, read them, and iterate. Doing the arithmetic in your head is what
this tool exists to avoid.

The sandbox has no network access. Everything you need is in the prompt."""


def solve(
    client,
    row: dict,
    *,
    model: str,
    tier: int,
    paradigm: str = "cot",
    provider: str = "anthropic",
    effort: str = "high",
    delimited: bool = False,
    few_shot: bool = True,
    max_tokens: int = 32000,
    **backend_options,
) -> Attempt:
    """Run one instance through one paradigm at one tier.

    The single entry point, so a caller cannot accidentally give the two paradigms
    different prompts, schemas or effort levels and then compare their scores. ``client``
    may be a raw SDK client or an already-built
    :class:`~kryptos.eval.providers.Backend`; the latter is how the runner reuses one
    connection across a run.
    """
    if paradigm not in PARADIGMS:
        raise ValueError(f"unknown paradigm {paradigm!r}; choose from {list(PARADIGMS)}")

    backend = (
        client
        if isinstance(client, providers.Backend)
        else providers.backend_for(provider, client)
    )
    if not backend.supports(paradigm):
        raise ValueError(
            f"the {paradigm!r} paradigm is not available on {backend.name!r}; "
            f"it supports {list(providers.SUPPORTED_PARADIGMS[backend.name])}"
        )

    # Built once, here, and handed to the backend untouched. Everything downstream of
    # this line is transport.
    system = tiers.system_prompt(tier, few_shot=few_shot)
    if paradigm == "tool_use":
        system = f"{system}\n\n{TOOL_USE_GUIDANCE}"
    user = tiers.build_prompt(row, tier, delimited=delimited)

    attempt = Attempt(
        instance_id=row["id"],
        tier=tier,
        paradigm=paradigm,
        model=model,
        requested_model=model,
        provider=backend.name,
    )
    return backend.solve(
        attempt,
        system=system,
        user=user,
        model=model,
        schema=ANSWER_SCHEMA,
        effort=effort,
        max_tokens=max_tokens,
        tool_use=paradigm == "tool_use",
        **backend_options,
    )
