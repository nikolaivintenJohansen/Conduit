from uuid import uuid4

import pytest

from services.gateway.rate_limit import (
    RateLimitExceededError,
    check_rate_limits,
    reset_rate_limit_state,
)
from services.gateway.router import ProviderError, route_chat_completion


@pytest.fixture(autouse=True)
def clear_rate_limits():
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


def _fake_litellm(monkeypatch, *, completion, completion_cost=0.0):
    import sys
    import types

    fake = types.SimpleNamespace(
        completion=completion,
        completion_cost=lambda completion_response: completion_cost,
        set_verbose=False,
    )
    monkeypatch.setitem(sys.modules, "litellm", fake)
    return fake


def test_route_chat_completion_uses_mock_provider():
    routed = route_chat_completion(
        "gpt-4o-mini",
        [{"role": "user", "content": "ping"}],
    )
    assert routed.provider == "mock"
    assert routed.completion.model == "gpt-4o-mini"
    assert "ping" in routed.completion.content


def test_route_chat_completion_uses_live_provider_when_configured(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-live")
    fake_response = {
        "choices": [{"message": {"content": "hello from live provider"}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 34},
    }
    _fake_litellm(monkeypatch, completion=lambda model, messages: fake_response, completion_cost=0.000123)

    routed = route_chat_completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])
    assert routed.provider == "openai"
    assert routed.completion.content == "hello from live provider"
    assert routed.completion.usage.input_tokens == 12
    assert routed.completion.usage.output_tokens == 34
    # 0.000123 USD -> 123 microdollars
    assert routed.completion.base_cost_microdollars == 123


def test_route_chat_completion_surfaces_live_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-live")

    def boom(model, messages):
        raise RuntimeError("auth failed")

    _fake_litellm(monkeypatch, completion=boom)

    with pytest.raises(ProviderError, match="openai call failed"):
        route_chat_completion("gpt-4o-mini", [{"role": "user", "content": "hi"}])


def test_route_chat_completion_falls_back_to_mock_when_key_unset(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    routed = route_chat_completion("gpt-4o-mini", [{"role": "user", "content": "ping"}])
    assert routed.provider == "mock"


def test_route_chat_completion_requires_messages():
    with pytest.raises(ValueError):
        route_chat_completion("gpt-4o-mini", [{"role": "user", "content": "   "}])


def test_rate_limit_rpm():
    key_id = uuid4()
    check_rate_limits(key_id, rpm_limit=2, tpm_limit=10_000, estimated_tokens=10)
    check_rate_limits(key_id, rpm_limit=2, tpm_limit=10_000, estimated_tokens=10)
    with pytest.raises(RateLimitExceededError):
        check_rate_limits(key_id, rpm_limit=2, tpm_limit=10_000, estimated_tokens=10)


def test_rate_limit_tpm():
    key_id = uuid4()
    with pytest.raises(RateLimitExceededError):
        check_rate_limits(key_id, rpm_limit=100, tpm_limit=5, estimated_tokens=10)
