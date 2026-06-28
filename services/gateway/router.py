from dataclasses import dataclass

from services.gateway.mock_provider import MockCompletion, mock_chat_completion

# Primary provider per model with mock fallback for sandbox routing.
MODEL_PROVIDERS: dict[str, list[str]] = {
    "gpt-4o-mini": ["openai", "mock"],
    "gpt-4o": ["openai", "mock"],
    "claude-3-5-sonnet": ["anthropic", "mock"],
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


def route_chat_completion(model: str, messages: list[dict]) -> RoutedCompletion:
    """Route to primary provider with simple failover to mock sandbox."""
    prompt = extract_prompt(messages)
    providers = MODEL_PROVIDERS.get(model, ["mock"])
    last_error: Exception | None = None

    for provider in providers:
        try:
            if provider == "mock":
                completion = mock_chat_completion(model, prompt)
                return RoutedCompletion(completion=completion, provider=provider)
            # Live providers are wired in a later task; failover to mock for MVP.
            raise ProviderError(f"provider {provider} not configured")
        except ProviderError as exc:
            last_error = exc
            continue

    raise ProviderError(str(last_error or "no providers available"))
