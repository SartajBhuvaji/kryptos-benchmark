"""Transports. One prompt, several APIs.

The benchmark's whole claim rests on holding everything fixed except the axis under test,
and adding a second vendor is the easiest way to break that without noticing. So the
split is deliberate and narrow: :mod:`kryptos.eval.tiers` builds the system prompt and the
user prompt, :mod:`kryptos.eval.paradigms` decides what a paradigm means, and this module
does nothing but carry those two strings to an API and bring an answer back.

**Both backends receive byte-identical prompts.** Nothing here edits, reformats or
re-wraps them, and a test asserts it in both directions. If a cross-model number is ever
quoted, that property is what makes it a comparison rather than a coincidence.

What genuinely differs between the two is confined to :meth:`Backend.solve`:

===================  ===============================  ==============================
                     Anthropic                        OpenAI-compatible
===================  ===============================  ==============================
system prompt        top-level ``system``             a ``role: "system"`` message
JSON output          ``output_config.format``         ``response_format``
reasoning depth      ``thinking`` + ``effort``        ``reasoning_effort``
token counts         ``input_tokens``/``output_``     ``prompt_``/``completion_``
refusal              ``stop_reason == "refusal"``     ``message.refusal`` / filter
===================  ===============================  ==============================

OpenAI-compatible means any server speaking that wire format -- OpenAI itself, vLLM,
OpenRouter, Together, a local runtime -- selected with ``--base-url``. That breadth is the
point, and it is also why this backend sends a deliberately small request: every field is
one more thing a given server might reject. Anything else goes through
``--provider-param``.

Two limits are enforced rather than papered over
------------------------------------------------
**Tool use is Anthropic-only.** It relies on a server-side sandbox that the OpenAI wire
format has no equivalent for. Asking for it elsewhere raises, because the alternative is
running chain-of-thought while the results file says ``tool_use`` -- which would land as a
headline finding that the tool-use gap had vanished.

**Effort recorded is effort sent.** Some servers reject ``reasoning_effort``, so
``--no-reasoning-effort`` drops it -- and then the attempt reports its effort as
``unset`` rather than echoing back a level nothing was told about.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

PROVIDERS = ("anthropic", "openai")

#: Where each provider's key is read from when no environment variable is named.
DEFAULT_KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}

#: Which paradigms each transport can actually run. Enforced, not advisory.
SUPPORTED_PARADIGMS = {"anthropic": ("cot", "tool_use"), "openai": ("cot",)}

#: Server-side sandbox. Isolated, no network egress, Python 3.11 with numpy and pandas
#: already present -- enough for any classical cipher without a package install.
CODE_EXECUTION_TOOL = {"type": "code_execution_20260521", "name": "code_execution"}

#: How many times to resume a paused turn before giving up. A tool-use trace that has
#: paused this many times is looping rather than progressing.
MAX_RESUMES = 8

#: This project's effort ladder onto the three levels the OpenAI field accepts. The two
#: top rungs collapse, and :attr:`Attempt.effort` records what was *sent*, so a run at
#: ``xhigh`` is never later read as though the endpoint was told something it was not.
OPENAI_EFFORT = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}


@dataclass
class Attempt:
    """One model attempt, in the shape every backend produces and scoring consumes."""

    instance_id: str
    tier: int
    paradigm: str
    cipher: str = ""
    key: str = ""
    method: str = ""
    plaintext: str = ""
    #: Set when the request was declined by a safety classifier or content filter.
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
    #: The model that answered. Differs from ``requested_model`` when a fallback served.
    model: str = ""
    #: The model that was asked for -- the experimental axis.
    requested_model: str = ""
    #: Which transport ran this.
    provider: str = "anthropic"
    #: The reasoning effort actually sent, or ``"unset"`` if none was.
    effort: str = ""

    @property
    def usable(self) -> bool:
        """Whether this produced an answer to score, as opposed to a failure to report."""
        return not self.refused and self.error is None

    @property
    def fell_back(self) -> bool:
        return substituted(self.model, self.requested_model)


#: A dated snapshot of an alias -- ``claude-sonnet-5`` served as
#: ``claude-sonnet-5-20260115``. Exactly eight digits, deliberately: a version bump
#: carries one or two, and ``claude-sonnet-5-1`` would be a *different* model rather than
#: the same one dated. Matching loosely there would hide the substitution this exists to
#: catch.
SNAPSHOT_SUFFIX = re.compile(r"-\d{8}$")


def substituted(served: str, asked: str) -> bool:
    """Whether a model other than the one requested answered.

    Not a string comparison, because the API resolves an alias to the snapshot behind it
    and reports *that* back: ask for ``claude-sonnet-5`` and the answer says
    ``claude-sonnet-5-20260115``. Comparing those directly would flag a fallback on every
    record of every ordinary run, and a warning that fires on all of them is one nobody
    reads -- which is exactly when a real fallback goes past unnoticed.

    The suffix is stripped only from the served side. Asking for a specific snapshot and
    being given a different one *is* a substitution: the caller named a set of weights and
    did not get them.
    """
    if not served or served == asked:
        return False
    return SNAPSHOT_SUFFIX.sub("", served) != asked


def client_for(provider: str, *, base_url: str | None = None, api_key: str | None = None):
    """Construct a client. SDKs are imported lazily -- neither is a hard dependency."""
    if provider == "anthropic":
        import anthropic

        return anthropic.Anthropic(
            **{k: v for k, v in (("base_url", base_url), ("api_key", api_key)) if v}
        )
    if provider == "openai":
        import openai

        return openai.OpenAI(
            **{k: v for k, v in (("base_url", base_url), ("api_key", api_key)) if v}
        )
    raise ValueError(f"unknown provider {provider!r}; choose from {list(PROVIDERS)}")


def key_from_env(provider: str, variable: str | None = None) -> str | None:
    """Read the key from the environment.

    A key is never taken as a command-line argument: it would sit in shell history and be
    visible to anything that can list processes.
    """
    return os.environ.get(variable or DEFAULT_KEY_ENV[provider])


# --- backends ---------------------------------------------------------------------


class Backend:
    """Carries one prompt to one API. Subclasses differ only in wire format."""

    name = ""

    def __init__(self, client, *, extra: dict | None = None) -> None:
        self.client = client
        #: Raw request fields from ``--provider-param``, merged last so they win.
        self.extra = dict(extra or {})

    def supports(self, paradigm: str) -> bool:
        return paradigm in SUPPORTED_PARADIGMS[self.name]

    def solve(self, attempt: Attempt, *, system: str, user: str, **options) -> Attempt:
        raise NotImplementedError

    def _failure(self, exc: BaseException) -> str | None:
        """Label a transport failure, or ``None`` if unrecognised.

        ``None`` means re-raise. Swallowing an arbitrary exception into ``error`` would
        file a bug in this harness as a failure of the model under test.
        """
        raise NotImplementedError


class AnthropicBackend(Backend):
    """The Claude Messages API, with server-side code execution for the tool paradigm."""

    name = "anthropic"

    def solve(
        self,
        attempt: Attempt,
        *,
        system: str,
        user: str,
        model: str,
        schema: dict,
        effort: str = "high",
        max_tokens: int = 32000,
        tool_use: bool = False,
    ) -> Attempt:
        request: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            # Cryptanalysis sits close enough to the cyber policy boundary that a benign
            # request is occasionally declined. Server-side fallback re-runs it on the
            # recommended model rather than returning a refusal, so one classifier hit
            # does not void a benchmark run.
            "betas": ["server-side-fallback-2026-07-01"],
            "fallbacks": "default",
            **self.extra,
        }
        if tool_use:
            request["tools"] = [CODE_EXECUTION_TOOL]

        attempt.effort = effort
        return self._run(request, [{"role": "user", "content": user}], attempt)

    def _run(self, request: dict, messages: list, attempt: Attempt) -> Attempt:
        """Drive the request to completion, resuming paused turns."""
        message = None
        for _ in range(MAX_RESUMES + 1):
            try:
                with self.client.beta.messages.stream(
                    **request, messages=messages
                ) as stream:
                    message = stream.get_final_message()
            except Exception as exc:
                label = self._failure(exc)
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

            self._record(attempt, message)

            if message.stop_reason != "pause_turn":
                break

            # The server-side tool loop hit its iteration limit. Re-send with the paused
            # assistant turn appended and no extra user message -- the server resumes
            # from the trailing tool-use block. A "continue" here would corrupt that.
            messages = [*messages, {"role": "assistant", "content": message.content}]
            attempt.resumes += 1
        else:
            attempt.error = "pause_limit_exceeded"
            return attempt

        return _text_into(attempt, _first_text(message.content))

    @staticmethod
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

    def _failure(self, exc: BaseException) -> str | None:
        try:
            import anthropic
        except ImportError:  # pragma: no cover -- present wherever runs happen
            return None
        if isinstance(exc, anthropic.APIStatusError):
            return f"api_error_{exc.status_code}"
        if isinstance(exc, anthropic.APIConnectionError):
            return "connection_error"
        return None


class OpenAIBackend(Backend):
    """Chat Completions, against OpenAI or anything else speaking that wire format.

    Deliberately minimal. Every optional field is one more thing a given server can
    reject, and this backend's value is breadth -- so the request carries the model, the
    two messages, a token cap, a JSON schema, and nothing else unless asked.
    """

    name = "openai"

    def solve(
        self,
        attempt: Attempt,
        *,
        system: str,
        user: str,
        model: str,
        schema: dict,
        effort: str = "high",
        max_tokens: int = 32000,
        tool_use: bool = False,
        reasoning_effort: bool = True,
    ) -> Attempt:
        if tool_use:
            raise ValueError(
                "the tool_use paradigm needs a server-side sandbox, which the OpenAI "
                "wire format has no equivalent for. Running chain of thought here while "
                "recording it as tool use would fake the paradigm gap."
            )

        request: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "answer", "strict": True, "schema": schema},
            },
        }
        if reasoning_effort:
            request["reasoning_effort"] = OPENAI_EFFORT.get(effort, "high")
        request.update(self.extra)

        # Recorded from the request, not from the caller's intent: with the field
        # dropped, nothing was told anything about effort, and the results file must not
        # imply otherwise.
        attempt.effort = str(request.get("reasoning_effort", "unset"))

        try:
            completion = self.client.chat.completions.create(**request)
        except Exception as exc:
            label = self._failure(exc)
            if label is None:
                raise
            attempt.error = label
            return attempt

        usage = getattr(completion, "usage", None)
        attempt.input_tokens += getattr(usage, "prompt_tokens", 0) or 0
        attempt.output_tokens += getattr(usage, "completion_tokens", 0) or 0
        attempt.model = getattr(completion, "model", attempt.model)

        choices = getattr(completion, "choices", None) or []
        if not choices:
            attempt.error = "empty_response"
            return attempt
        choice = choices[0]

        # Two different refusal shapes. Structured outputs put a sentence in `refusal`
        # and leave `content` null; a moderation hit sets finish_reason instead. Both
        # are checked before content is read, because in both cases there is none.
        message = getattr(choice, "message", None)
        refusal = getattr(message, "refusal", None)
        if refusal:
            attempt.refused = True
            attempt.refusal_category = "refusal"
            return attempt
        if getattr(choice, "finish_reason", None) == "content_filter":
            attempt.refused = True
            attempt.refusal_category = "content_filter"
            return attempt

        return _text_into(attempt, getattr(message, "content", "") or "")

    def _failure(self, exc: BaseException) -> str | None:
        try:
            import openai
        except ImportError:  # pragma: no cover -- present wherever runs happen
            return None
        if isinstance(exc, openai.APIStatusError):
            return f"api_error_{exc.status_code}"
        if isinstance(exc, openai.APIConnectionError):
            return "connection_error"
        return None


BACKENDS = {"anthropic": AnthropicBackend, "openai": OpenAIBackend}


def backend_for(provider: str, client, *, extra: dict | None = None) -> Backend:
    if provider not in BACKENDS:
        raise ValueError(f"unknown provider {provider!r}; choose from {list(PROVIDERS)}")
    return BACKENDS[provider](client, extra=extra)


# --- shared response handling -----------------------------------------------------


def _first_text(content) -> str:
    return next((b.text for b in content if getattr(b, "type", None) == "text"), "")


def _text_into(attempt: Attempt, text: str) -> Attempt:
    """Parse one JSON answer into an attempt.

    Shared by every backend on purpose: a per-provider parser could normalise one
    vendor's output more forgivingly than another's, and that difference would show up
    as a capability gap between models.
    """
    from kryptos.scoring import letters_only

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        attempt.error = "unparsed_response"
        return attempt
    if not isinstance(parsed, dict):
        attempt.error = "unparsed_response"
        return attempt

    attempt.cipher = str(parsed.get("cipher", ""))
    attempt.key = str(parsed.get("key", ""))
    attempt.method = str(parsed.get("method", ""))
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


def parse_params(pairs: list[str] | None) -> dict:
    """Turn ``--provider-param k=v`` into request fields, JSON-decoding values.

    The escape hatch for whatever a given server needs and this code does not know
    about -- ``max_completion_tokens`` for OpenAI's reasoning models, a vendor's sampling
    knob, a beta flag. Values parse as JSON where possible so numbers and booleans do
    not arrive as strings.
    """
    params: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"--provider-param needs key=value, got {pair!r}")
        key, _, raw = pair.partition("=")
        try:
            params[key.strip()] = json.loads(raw)
        except json.JSONDecodeError:
            params[key.strip()] = raw
    return params
