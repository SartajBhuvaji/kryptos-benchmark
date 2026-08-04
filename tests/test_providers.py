"""Verification for the transport layer.

The benchmark compares models. The moment a second vendor exists, the comparison is only
meaningful if both are asked the same question — so the load-bearing test here is not that
either backend works, but that the two receive **byte-identical prompts**. Everything else
is about the ways a second provider can silently produce a plausible wrong number:

* a paradigm quietly downgrading, so a chain-of-thought run files itself as tool use;
* an effort level recorded that was never sent;
* a refusal or an empty response read as an answer of ``""``;
* a model with no price on file costing ``$0.00`` instead of "unknown".

No API calls. Both SDKs are stubbed, and neither needs to be installed.
"""

from __future__ import annotations

import json

import pytest

from kryptos.eval import paradigms, providers, report as reporting, results, tiers

ANSWER = {"cipher": "Quagmire III", "key": "PALIMPSEST", "method": "m", "plaintext": "abc"}


# --- stubs ------------------------------------------------------------------------


class OpenAIMessage:
    def __init__(self, content, refusal=None):
        self.content = content
        self.refusal = refusal


class OpenAIChoice:
    def __init__(self, content, refusal=None, finish_reason="stop"):
        self.message = OpenAIMessage(content, refusal)
        self.finish_reason = finish_reason


class OpenAICompletion:
    def __init__(self, choices, *, prompt=100, completion=50, model="gpt-5"):
        self.choices = choices
        self.model = model
        self.usage = type(
            "Usage", (), {"prompt_tokens": prompt, "completion_tokens": completion}
        )()


class FakeOpenAI:
    """Records requests to `chat.completions.create` and returns a canned completion."""

    def __init__(self, completion=None, raises=None):
        self.requests: list[dict] = []
        self._completion = completion or OpenAICompletion(
            [OpenAIChoice(json.dumps(ANSWER))]
        )
        self._raises = raises
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **request):
        self.requests.append(request)
        if self._raises:
            raise self._raises
        return self._completion


class AnthropicMessage:
    def __init__(self, text):
        self.content = [type("T", (), {"type": "text", "text": text})()]
        self.stop_reason = "end_turn"
        self.stop_details = None
        self.usage = type("U", (), {"input_tokens": 100, "output_tokens": 50})()
        self.model = "claude-sonnet-5"


class FakeAnthropic:
    def __init__(self):
        self.requests: list[dict] = []
        self.beta = type("Beta", (), {"messages": self})()

    def stream(self, **request):
        self.requests.append(request)
        message = AnthropicMessage(json.dumps(ANSWER))
        return type(
            "S",
            (),
            {
                "__enter__": lambda s: s,
                "__exit__": lambda s, *e: False,
                "get_final_message": lambda s: message,
            },
        )()


@pytest.fixture
def row() -> dict:
    return {
        "id": "iso-1",
        "problem": "QWERTYUIOPASDFGH",
        "problem_letters_only": "QWERTYUIOPASDFGH",
        "problem_length": 16,
        "cribs": [],
        "answer": "ABC",
        "config": "isomorph_quagmire",
        "scoring_metric": "character_error_rate",
    }


# --- the cross-provider contract --------------------------------------------------


def test_both_providers_receive_byte_identical_prompts(row):
    """The load-bearing test. A cross-model number is a comparison only if the two models
    were asked the same thing; any reformatting between the backends would make every
    such number a measurement of this harness instead."""
    claude, gpt = FakeAnthropic(), FakeOpenAI()
    paradigms.solve(claude, row, model="claude-sonnet-5", tier=2)
    paradigms.solve(gpt, row, model="gpt-5", tier=2, provider="openai")

    sent = gpt.requests[0]["messages"]
    assert claude.requests[0]["system"] == sent[0]["content"]
    assert claude.requests[0]["messages"][0]["content"] == sent[1]["content"]


def test_the_prompts_are_the_ones_the_tier_module_built(row):
    """And neither backend is the author of them."""
    gpt = FakeOpenAI()
    paradigms.solve(gpt, row, model="gpt-5", tier=2, provider="openai")
    sent = gpt.requests[0]["messages"]

    assert sent[0]["content"] == tiers.system_prompt(2)
    assert sent[1]["content"] == tiers.build_prompt(row, 2)


def test_both_providers_use_the_same_answer_schema(row):
    claude, gpt = FakeAnthropic(), FakeOpenAI()
    paradigms.solve(claude, row, model="m", tier=2)
    paradigms.solve(gpt, row, model="m", tier=2, provider="openai")

    assert (
        claude.requests[0]["output_config"]["format"]["schema"]
        is paradigms.ANSWER_SCHEMA
        is gpt.requests[0]["response_format"]["json_schema"]["schema"]
    )


def test_both_providers_normalise_the_plaintext_identically(row):
    """One shared parser. A per-provider one could be more forgiving of one vendor's
    output than another's, which would read as a capability gap."""
    claude, gpt = FakeAnthropic(), FakeOpenAI()
    a = paradigms.solve(claude, row, model="m", tier=2)
    b = paradigms.solve(gpt, row, model="m", tier=2, provider="openai")

    assert a.plaintext == b.plaintext == "ABC"


def test_the_answer_never_leaks_through_either_backend(row):
    gpt = FakeOpenAI()
    paradigms.solve(gpt, row, model="m", tier=2, provider="openai")
    body = json.dumps(gpt.requests[0])
    assert row["answer"] not in body


# --- paradigm availability --------------------------------------------------------


def test_tool_use_is_refused_on_openai_rather_than_downgraded(row):
    """Silently running chain of thought here would land as a headline finding that the
    tool-use gap had closed."""
    with pytest.raises(ValueError, match="not available on 'openai'"):
        paradigms.solve(
            FakeOpenAI(), row, model="m", tier=2, paradigm="tool_use", provider="openai"
        )


def test_tool_use_is_available_on_anthropic(row):
    attempt = paradigms.solve(
        FakeAnthropic(), row, model="m", tier=2, paradigm="tool_use"
    )
    assert attempt.paradigm == "tool_use"


def test_the_backend_itself_also_refuses_tool_use(row):
    """Belt and braces: the guard is on the backend too, not only in solve()."""
    backend = providers.backend_for("openai", FakeOpenAI())
    with pytest.raises(ValueError, match="server-side sandbox"):
        backend.solve(
            providers.Attempt(instance_id="x", tier=2, paradigm="tool_use"),
            system="s",
            user="u",
            model="m",
            schema={},
            tool_use=True,
        )


def test_supported_paradigms_are_declared_per_provider():
    assert providers.SUPPORTED_PARADIGMS["openai"] == ("cot",)
    assert set(providers.SUPPORTED_PARADIGMS["anthropic"]) == set(paradigms.PARADIGMS)


# --- effort recorded is effort sent -----------------------------------------------


@pytest.mark.parametrize(
    "asked,sent", [("low", "low"), ("medium", "medium"), ("high", "high"),
                   ("xhigh", "high"), ("max", "high")]
)
def test_openai_effort_ladder_collapses_and_records_what_it_sent(row, asked, sent):
    gpt = FakeOpenAI()
    attempt = paradigms.solve(
        gpt, row, model="m", tier=2, provider="openai", effort=asked
    )
    assert gpt.requests[0]["reasoning_effort"] == sent
    assert attempt.effort == sent


def test_dropping_reasoning_effort_records_unset_not_a_level(row):
    """The failure this prevents: a results file saying every run was at 'high' when the
    endpoint was never told anything about effort at all."""
    gpt = FakeOpenAI()
    attempt = paradigms.solve(
        gpt, row, model="m", tier=2, provider="openai", effort="high",
        reasoning_effort=False,
    )
    assert "reasoning_effort" not in gpt.requests[0]
    assert attempt.effort == "unset"


def test_the_persisted_effort_is_the_one_that_was_sent(row):
    gpt = FakeOpenAI()
    attempt = paradigms.solve(
        gpt, row, model="m", tier=2, provider="openai", effort="max",
    )
    # The caller asks score() for `max`; the record must still say what went on the wire.
    assert results.score(row, attempt, effort="max").effort == "high"


def test_anthropic_effort_passes_through_unchanged(row):
    claude = FakeAnthropic()
    attempt = paradigms.solve(claude, row, model="m", tier=2, effort="xhigh")
    assert claude.requests[0]["output_config"]["effort"] == "xhigh"
    assert attempt.effort == "xhigh"


# --- openai response handling -----------------------------------------------------


def test_usage_is_read_from_the_openai_field_names(row):
    attempt = paradigms.solve(FakeOpenAI(), row, model="m", tier=2, provider="openai")
    assert (attempt.input_tokens, attempt.output_tokens) == (100, 50)


def test_a_structured_output_refusal_is_recorded_not_scored(row):
    gpt = FakeOpenAI(OpenAICompletion([OpenAIChoice(None, refusal="I can't help")]))
    attempt = paradigms.solve(gpt, row, model="m", tier=2, provider="openai")

    assert attempt.refused and not attempt.usable
    assert attempt.refusal_category == "refusal"
    assert results.score(row, attempt).cer is None


def test_a_content_filter_hit_is_a_refusal(row):
    gpt = FakeOpenAI(
        OpenAICompletion([OpenAIChoice(None, finish_reason="content_filter")])
    )
    attempt = paradigms.solve(gpt, row, model="m", tier=2, provider="openai")
    assert attempt.refused and attempt.refusal_category == "content_filter"


def test_an_empty_choice_list_is_an_error_not_an_empty_answer(row):
    gpt = FakeOpenAI(OpenAICompletion([]))
    attempt = paradigms.solve(gpt, row, model="m", tier=2, provider="openai")
    assert attempt.error == "empty_response"
    assert not attempt.usable


def test_unparseable_content_is_an_error(row):
    gpt = FakeOpenAI(OpenAICompletion([OpenAIChoice("not json at all")]))
    attempt = paradigms.solve(gpt, row, model="m", tier=2, provider="openai")
    assert attempt.error == "unparsed_response"


def test_a_bare_json_scalar_is_an_error_not_an_answer(row):
    gpt = FakeOpenAI(OpenAICompletion([OpenAIChoice('"just a string"')]))
    attempt = paradigms.solve(gpt, row, model="m", tier=2, provider="openai")
    assert attempt.error == "unparsed_response"


def test_an_unrecognised_exception_is_re_raised_not_swallowed(row):
    """Filing a bug in this harness as a model failure is how a broken run looks like a
    weak model."""
    gpt = FakeOpenAI(raises=RuntimeError("something local broke"))
    with pytest.raises(RuntimeError):
        paradigms.solve(gpt, row, model="m", tier=2, provider="openai")


def test_the_openai_request_carries_only_the_fields_we_chose(row):
    """Every optional field is one more thing some compatible server can reject."""
    gpt = FakeOpenAI()
    paradigms.solve(gpt, row, model="m", tier=2, provider="openai")
    assert set(gpt.requests[0]) == {
        "model", "messages", "max_tokens", "response_format", "reasoning_effort",
    }


# --- provider params --------------------------------------------------------------


def test_provider_params_reach_the_request_and_win(row):
    backend = providers.backend_for(
        "openai", FakeOpenAI(), extra={"max_completion_tokens": 4096, "max_tokens": 1}
    )
    paradigms.solve(backend, row, model="m", tier=2, provider="openai")
    sent = backend.client.requests[0]
    assert sent["max_completion_tokens"] == 4096
    assert sent["max_tokens"] == 1


@pytest.mark.parametrize(
    "pairs,expected",
    [
        (["top_p=0.9"], {"top_p": 0.9}),
        (["seed=7"], {"seed": 7}),
        (["stream=false"], {"stream": False}),
        (["service_tier=flex"], {"service_tier": "flex"}),
        ([], {}),
    ],
)
def test_provider_params_json_decode(pairs, expected):
    assert providers.parse_params(pairs) == expected


def test_a_malformed_provider_param_is_rejected():
    with pytest.raises(ValueError, match="key=value"):
        providers.parse_params(["nonsense"])


# --- keys and clients -------------------------------------------------------------


def test_the_key_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-default")
    monkeypatch.setenv("MY_KEY", "sk-named")
    assert providers.key_from_env("openai") == "sk-default"
    assert providers.key_from_env("openai", "MY_KEY") == "sk-named"


def test_a_missing_key_is_none_not_an_empty_string(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert providers.key_from_env("openai") is None


def test_unknown_providers_are_rejected():
    with pytest.raises(ValueError, match="unknown provider"):
        providers.backend_for("gemini", object())
    with pytest.raises(ValueError, match="unknown provider"):
        providers.client_for("gemini")


def test_provider_is_persisted_on_the_result(row):
    attempt = paradigms.solve(FakeOpenAI(), row, model="m", tier=2, provider="openai")
    assert results.score(row, attempt).provider == "openai"


# --- pricing ----------------------------------------------------------------------


@pytest.fixture
def prices():
    """Restore the table -- register_price mutates module state."""
    original = dict(reporting.PRICES)
    yield
    reporting.PRICES.clear()
    reporting.PRICES.update(original)


def test_an_unknown_model_is_unpriced_rather_than_free():
    assert reporting.price_for("some-local-llama") is None
    assert reporting.usd({"model": "some-local-llama", "output_tokens": 10**6}) is None


def test_registering_a_price_makes_a_model_billable(prices):
    reporting.register_price("gpt-5", 1.25, 10.00)
    assert reporting.usd(
        {"model": "gpt-5", "input_tokens": 1_000_000, "output_tokens": 1_000_000}
    ) == pytest.approx(11.25)


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("gpt-5=1.25/10", ("gpt-5", 1.25, 10.0)),
        ("llama-3.3-70b=0.59/0.79", ("llama-3.3-70b", 0.59, 0.79)),
        ("free-local=0/0", ("free-local", 0.0, 0.0)),
    ],
)
def test_price_specs_parse(spec, expected):
    assert reporting.parse_price(spec) == expected


@pytest.mark.parametrize("spec", ["gpt-5", "gpt-5=1.25", "=1/2", "gpt-5=a/b"])
def test_malformed_price_specs_are_rejected(spec):
    with pytest.raises(ValueError):
        reporting.parse_price(spec)


def test_negative_prices_are_rejected(prices):
    with pytest.raises(ValueError, match="negative"):
        reporting.register_price("weird", -1, 2)
