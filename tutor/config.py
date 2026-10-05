"""Small, visible limits. Edit the model and its prices together."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    model: str = "gpt-4.1-mini"
    input_price_per_million: float = 0.40
    output_price_per_million: float = 1.60
    max_calls: int = 12
    max_cost_usd: float = 0.05
    max_input_bytes: int = 40_000
    max_problem_chars: int = 8_000
    max_message_chars: int = 1_000
    max_source_chars: int = 4_000
    question_output_tokens: int = 1_800
    report_output_tokens: int = 3_500
    max_search_calls: int = 1
    search_price_usd: float = 0.005
    max_search_context_chars: int = 4_000

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_price_per_million
            + output_tokens * self.output_price_per_million
        ) / 1_000_000
