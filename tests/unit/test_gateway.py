from uuid import uuid4

import pytest

from services.gateway.rate_limit import (
    RateLimitExceededError,
    check_rate_limits,
    reset_rate_limit_state,
)
from services.gateway.router import route_chat_completion


@pytest.fixture(autouse=True)
def clear_rate_limits():
    reset_rate_limit_state()
    yield
    reset_rate_limit_state()


def test_route_chat_completion_uses_mock_provider():
    routed = route_chat_completion(
        "gpt-4o-mini",
        [{"role": "user", "content": "ping"}],
    )
    assert routed.provider == "mock"
    assert routed.completion.model == "gpt-4o-mini"
    assert "ping" in routed.completion.content


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
