import os
from dataclasses import dataclass

from services.gateway.mock_provider import (
    MockCompletion,
    MockUsage,
    estimate_base_cost,
    mock_chat_completion,
)

# Primary provider per model with mock fallback for sandbox routing.
# Each model tries its live provider first, then falls back to the in-process
# mock when the provider is not configured (no API key) — so sandbox/dev works
# with zero external keys, while a configured key routes to the real provider.
MODEL_PROVIDERS: dict[str, list[str]] = {
    "gpt-4o-mini": ["openai", "mock"],
    "gpt-4o": ["openai", "mock"],
    "claude-3-5-sonnet": ["anthropic", "mock"],
    "gemini-1.5-flash": ["gemini", "mock"],
    "gemini-2.0-flash": ["gemini", "mock"],
    "gemini-2.5-flash": ["gemini", "mock"],
    "gemini-2.5-flash-lite": ["gemini", "mock"],
}

# Our model slug -> litellm model id. litellm infers the provider from the
# prefix (gemini/*, openai defaults, anthropic claude-*).
LITELLM_MODEL_IDS: dict[str, str] = {
    "gpt-4o-mini": "gpt-4o-mini",
    "gpt-4o": "gpt-4o",
    "claude-3-5-sonnet": "claude-3-5-sonnet",
    "gemini-1.5-flash": "gemini/gemini-1.5-flash",
    "gemini-2.0-flash": "gemini/gemini-2.0-flash",
    "gemini-2.5-flash": "gemini/gemini-2.5-flash",
    "gemini-2.5-flash-lite": "gemini/gemini-2.5-flash-lite",
}

# Provider -> env var holding its API key. Used to decide live-vs-mock routing.
_PROVIDER_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


class ProviderError(Exception):
    pass


@dataclass(frozen=True)
class RoutedCompletion:
    completion: MockCompletion
    provider: str


def extract_prompt(messages: list[dict]) -> str:
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            parts.append(content.strip())
    if not parts:
        raise ValueError("messages must include at least one non-empty user content")
    return "\n".join(parts)


def _provider_configured(provider: str) -> bool:
    env_var = _PROVIDER_KEY_ENV.get(provider)
    return bool(env_var and os.environ.get(env_var))


def _litellm_base_cost_microdollars(response, model: str, input_tokens: int, output_tokens: int) -> int:
    """Prefer litellm's cost map (true provider cost); fall back to our estimates."""
    try:
        import litellm

        cost_usd = float(litellm.completion_cost(completion_response=response))
        if cost_usd >= 0:
            return int(round(cost_usd * 1_000_000))
    except Exception:
        pass
    return estimate_base_cost(model, input_tokens, output_tokens)


def _litellm_completion(model: str, messages: list[dict]) -> MockCompletion:
    """Call the live provider via litellm and normalize to our completion shape."""
    import litellm

    litellm.set_verbose = False
    litellm_model_id = LITELLM_MODEL_IDS.get(model, model)
    response = litellm.completion(model=litellm_model_id, messages=messages)

    content = response["choices"][0]["message"]["content"] or ""
    usage = response.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens", 0) or 0)
    output_tokens = int(usage.get("completion_tokens", 0) or 0)
    base_cost = _litellm_base_cost_microdollars(response, model, input_tokens, output_tokens)

    return MockCompletion(
        model=model,
        content=content,
        usage=MockUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        base_cost_microdollars=base_cost,
    )


def route_chat_completion(model: str, messages: list[dict]) -> RoutedCompletion:
    """Route to the primary live provider, failing over to mock when unconfigured.

    If a provider's API key is set, the call goes to the real provider and any
    error surfaces (we do NOT silently degrade real requests to mock content).
    If no key is set, that provider is skipped and the mock sandbox handles it.
    """
    prompt = extract_prompt(messages)
    providers = MODEL_PROVIDERS.get(model, ["mock"])
    last_error: Exception | None = None

    for provider in providers:
        if provider == "mock":
            try:
                return RoutedCompletion(completion=mock_chat_completion(model, prompt), provider=provider)
            except Exception as exc:
                last_error = exc
                continue

        if not _provider_configured(provider):
            last_error = ProviderError(f"provider {provider} not configured")
            continue

        try:
            completion = _litellm_completion(model, messages)
            return RoutedCompletion(completion=completion, provider=provider)
        except Exception as exc:
            # Live provider is configured but the call failed — surface the real
            # error rather than returning fake mock content for a real request.
            raise ProviderError(f"{provider} call failed: {exc}") from exc

    raise ProviderError(str(last_error or "no providers available"))
