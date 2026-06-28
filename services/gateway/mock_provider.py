from dataclasses import dataclass


@dataclass(frozen=True)
class MockUsage:
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class MockCompletion:
    model: str
    content: str
    usage: MockUsage
    base_cost_microdollars: int


# Deterministic sandbox pricing — no live provider calls.
MODEL_COSTS = {
    "gpt-4o-mini": {"input_per_m": 150_000, "output_per_m": 600_000},
    "gpt-4o": {"input_per_m": 500_000, "output_per_m": 1_500_000},
    "claude-3-5-sonnet": {"input_per_m": 300_000, "output_per_m": 1_500_000},
}


def estimate_base_cost(model: str, input_tokens: int, output_tokens: int) -> int:
    rates = MODEL_COSTS.get(model, {"input_per_m": 100_000, "output_per_m": 400_000})
    input_cost = (input_tokens * rates["input_per_m"]) // 1_000_000
    output_cost = (output_tokens * rates["output_per_m"]) // 1_000_000
    return input_cost + output_cost


def estimate_prompt_tokens(prompt: str) -> int:
    return max(1, len(prompt.split()))


def estimate_max_hold_microdollars(
    model: str, prompt: str, *, max_tokens: int | None = None
) -> int:
    """Pessimistic upper bound for balance hold before provider call."""
    input_tokens = estimate_prompt_tokens(prompt)
    output_tokens = max_tokens if max_tokens is not None else 256
    return estimate_base_cost(model, input_tokens, output_tokens)


def mock_chat_completion(model: str, prompt: str) -> MockCompletion:
    input_tokens = estimate_prompt_tokens(prompt)
    output_tokens = min(256, max(8, input_tokens * 2))
    content = f"[mock:{model}] echo: {prompt[:120]}"
    base_cost = estimate_base_cost(model, input_tokens, output_tokens)
    return MockCompletion(
        model=model,
        content=content,
        usage=MockUsage(input_tokens=input_tokens, output_tokens=output_tokens),
        base_cost_microdollars=base_cost,
    )
