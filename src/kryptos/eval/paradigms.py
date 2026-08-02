"""The two evaluation paradigms: chain of thought, and tool use.

Same instance, same tier, same prompt, same output schema — the only difference is
whether the model may run code. That is the point: the gap between the two is a result in
its own right, and it is only a result if nothing else varies. Both paradigms therefore
return the same :class:`Attempt`, which the scoring path consumes without knowing which
produced it.

Chain of thought
----------------
One request. The model reasons in its thinking blocks and returns a JSON answer. Whatever
arithmetic a Quagmire decryption needs, it does in its head.

Tool use
--------
The same request plus Anthropic's server-side code execution tool. The model writes
Python, it runs in an isolated container with no network egress, the model reads stdout
and iterates. Server-side was chosen over a local container so the benchmark has no
Docker prerequisite (plan gate 4.1); the cost is that this paradigm is Claude-API-only
until a container backend lands behind the same interface.

Two failure modes this file exists to handle correctly
------------------------------------------------------
**Refusals.** Cryptanalysis sits close enough to the cyber policy boundary that a benign
request is occasionally declined. A refusal is an HTTP 200 with ``stop_reason ==
"refusal"`` and an empty or partial ``content`` array, so reading ``content[0]`` blindly
raises on it. Both paradigms check ``stop_reason`` first and both request server-side
fallback, so one classifier hit does not void a run.

**Paused turns.** Server-side tools run their own sampling loop, and hitting its iteration
limit ends the turn with ``stop_reason == "pause_turn"`` — a *success* that is not
finished. Resuming means re-sending the conversation with the paused assistant turn
appended and no extra user message; the server picks up where it left off. Left
unhandled, a long tool-use trace silently returns a truncated answer that scores as a
failed decryption, which would show up as a paradigm gap that is really a harness bug.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from kryptos.eval import tiers
from kryptos.scoring import letters_only

#: Server-side sandbox. Isolated, no network egress, Python 3.11 with numpy and pandas
#: already present -- enough for any classical cipher without a package install.
CODE_EXECUTION_TOOL = {"type": "code_execution_20260521", "name": "code_execution"}

#: How many times to resume a paused turn before giving up. A tool-use trace that has
#: paused this many times is looping rather than progressing.
MAX_RESUMES = 8

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


@dataclass
class Attempt:
    """One model attempt, in the shape both paradigms produce and scoring consumes."""

    instance_id: str
    tier: int
    paradigm: str
    cipher: str = ""
    key: str = ""
    method: str = ""
    plaintext: str = ""
    #: Set when the request was declined by a safety classifier.
    refused: bool = False
    refusal_category: str | None = None
    #: Set when the request failed outright, or the response could not be parsed.
    error: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    #: Tool-use only: what the model ran and what came back.
    transcript: list[dict[str, Any]] = field(default_factory=list)
    code_executions: int = 0
    resumes: int = 0
    #: The model that actually answered. Not necessarily the one asked for: server-side
    #: fallback re-runs a declined request on another model, and reports it here.
    model: str = ""
    #: The model this attempt was requested as -- the experimental axis. Kept apart from
    #: ``model`` so a fallback cannot be silently counted as a result for the model that
    #: refused, which would put another model's score in its column.
    requested_model: str = ""

    @property
    def usable(self) -> bool:
        """Whether this produced an answer to score, as opposed to a failure to report."""
        return not self.refused and self.error is None

    @property
    def fell_back(self) -> bool:
        return bool(self.model) and self.model != self.requested_model


def solve(
    client,
    row: dict,
    *,
    model: str,
    tier: int,
    paradigm: str = "cot",
    effort: str = "high",
    delimited: bool = False,
    few_shot: bool = True,
    max_tokens: int = 32000,
) -> Attempt:
    """Run one instance through one paradigm at one tier.

    The single entry point, so a caller cannot accidentally give the two paradigms
    different prompts, schemas or effort levels and then compare their scores.
    """
    if paradigm not in PARADIGMS:
        raise ValueError(f"unknown paradigm {paradigm!r}; choose from {list(PARADIGMS)}")

    system = tiers.system_prompt(tier, few_shot=few_shot)
    if paradigm == "tool_use":
        system = f"{system}\n\n{TOOL_USE_GUIDANCE}"

    request: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "thinking": {"type": "adaptive"},
        "output_config": {
            "effort": effort,
            "format": {"type": "json_schema", "schema": ANSWER_SCHEMA},
        },
        # Cryptanalysis sits close enough to the cyber policy boundary that a benign
        # request is occasionally declined. Server-side fallback re-runs it on the
        # recommended model rather than returning a refusal, so one classifier hit does
        # not void a benchmark run.
        "betas": ["server-side-fallback-2026-07-01"],
        "fallbacks": "default",
    }
    if paradigm == "tool_use":
        request["tools"] = [CODE_EXECUTION_TOOL]

    messages = [
        {"role": "user", "content": tiers.build_prompt(row, tier, delimited=delimited)}
    ]

    attempt = Attempt(
        instance_id=row["id"],
        tier=tier,
        paradigm=paradigm,
        model=model,
        requested_model=model,
    )
    return _run(client, request, messages, attempt)


def _api_failure(exc: BaseException) -> str | None:
    """Label an SDK transport failure, or ``None`` if this is not one.

    ``anthropic`` is resolved here rather than imported at module scope so that prompt
    construction and scoring stay usable -- and testable -- without the SDK installed.
    An unrecognised exception returns ``None`` and is re-raised: swallowing arbitrary
    errors into an ``error`` field would hide real bugs as model failures.
    """
    try:
        import anthropic
    except ImportError:  # pragma: no cover -- the SDK is present wherever runs happen
        return None

    if isinstance(exc, anthropic.APIStatusError):
        return f"api_error_{exc.status_code}"
    if isinstance(exc, anthropic.APIConnectionError):
        return "connection_error"
    return None


def _run(client, request: dict, messages: list, attempt: Attempt) -> Attempt:
    """Drive the request to completion, resuming paused turns."""
    message = None
    for _ in range(MAX_RESUMES + 1):
        try:
            with client.beta.messages.stream(**request, messages=messages) as stream:
                message = stream.get_final_message()
        except Exception as exc:
            label = _api_failure(exc)
            if label is None:
                raise
            attempt.error = label
            return attempt

        attempt.input_tokens += message.usage.input_tokens
        attempt.output_tokens += message.usage.output_tokens
        attempt.model = getattr(message, "model", attempt.model)

        # stop_reason first: on a refusal the content array is empty or partial, so
        # indexing it would raise on the very case we are trying to record.
        if message.stop_reason == "refusal":
            attempt.refused = True
            attempt.refusal_category = getattr(message.stop_details, "category", None)
            return attempt

        _record(attempt, message)

        if message.stop_reason != "pause_turn":
            break

        # The server-side tool loop hit its iteration limit. Re-send with the paused
        # assistant turn appended and no extra user message -- the server resumes from
        # the trailing tool-use block. Adding a "continue" here would corrupt that.
        messages = [*messages, {"role": "assistant", "content": message.content}]
        attempt.resumes += 1
    else:
        attempt.error = "pause_limit_exceeded"
        return attempt

    return _parse(attempt, message)


def _record(attempt: Attempt, message) -> None:
    """Capture what the model ran and what came back."""
    for block in message.content:
        kind = getattr(block, "type", None)
        if kind == "server_tool_use":
            attempt.code_executions += 1
            attempt.transcript.append(
                {"type": "code", "input": _plain(getattr(block, "input", None))}
            )
        elif kind == "bash_code_execution_tool_result":
            content = getattr(block, "content", None)
            attempt.transcript.append(
                {
                    "type": "result",
                    "stdout": getattr(content, "stdout", None),
                    "stderr": getattr(content, "stderr", None),
                    "return_code": getattr(content, "return_code", None),
                }
            )


def _parse(attempt: Attempt, message) -> Attempt:
    text = next(
        (b.text for b in message.content if getattr(b, "type", None) == "text"), ""
    )
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        attempt.error = "unparsed_response"
        return attempt

    attempt.cipher = str(parsed.get("cipher", ""))
    attempt.key = str(parsed.get("key", ""))
    attempt.method = str(parsed.get("method", ""))
    # Normalised here, once, so both paradigms reach scoring in the same shape.
    attempt.plaintext = letters_only(str(parsed.get("plaintext", "")))
    return attempt


def _plain(value):
    """Reduce a tool input to something JSON-serialisable for the transcript."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return str(value)
