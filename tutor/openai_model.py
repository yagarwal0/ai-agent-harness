"""The OpenAI adapter: runtime credentials and structured model responses."""

from pathlib import Path

from openai import (APIConnectionError, APIStatusError, APITimeoutError,
                    AuthenticationError, BadRequestError, NotFoundError, OpenAI,
                    PermissionDeniedError, RateLimitError)
from pydantic import ValidationError

from tutor.schemas import InterviewPlan, ModelReply, ModelRequestError, StudyNotes
from tutor.secrets import load_key


def _response_format(schema):
    """Apply strict API object rules to the same Pydantic response contract."""
    value = schema.model_json_schema()

    def make_strict(node):
        if isinstance(node, dict):
            node.pop("default", None)
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node["required"] = list(node.get("properties", {}))
            for child in node.values():
                make_strict(child)
        elif isinstance(node, list):
            for child in node:
                make_strict(child)

    make_strict(value)
    return {"type": "json_schema", "name": schema.__name__, "schema": value, "strict": True}


def _failure_kind(error):
    """Inspect types and known codes only; never show raw error bodies/messages."""
    if isinstance(error, APITimeoutError):
        return "timeout"
    if isinstance(error, APIConnectionError):
        return "connection"
    if isinstance(error, AuthenticationError):
        return "authentication"
    if isinstance(error, PermissionDeniedError):
        return "permission"
    if isinstance(error, NotFoundError):
        return "model_unavailable"
    if isinstance(error, RateLimitError):
        return ("quota" if error.code in (
            "insufficient_quota", "billing_hard_limit_reached", "billing_not_active",
            "organization_usage_limit_exceeded", "project_usage_limit_exceeded",
            "credit_balance_exhausted", "organization_spend_limit_exceeded",
            "project_spend_limit_exceeded",
        ) else "rate_limit")
    if isinstance(error, BadRequestError):
        return "invalid_schema" if error.code == "invalid_json_schema" else "invalid_request"
    if isinstance(error, APIStatusError) and error.status_code >= 500:
        return "provider_unavailable"
    return "unknown"


class OpenAIModel:
    def __init__(self, model: str, key_path: Path | None = None):
        key = load_key("openai", key_path)
        self.name = model
        self._key = key
        self._client = OpenAI(
            api_key=key, base_url="https://api.openai.com/v1", timeout=30, max_retries=0
        )

    def generate(self, messages, *, report: bool, max_output_tokens: int) -> ModelReply:
        schema = StudyNotes if report else InterviewPlan
        try:
            # Parse locally AFTER inspecting status and retaining usage. SDK parse()
            # can raise on truncated/invalid JSON before returning that metadata.
            response = self._client.responses.create(
                model=self.name, input=messages, max_output_tokens=max_output_tokens,
                store=False, text={"format": _response_format(schema)},
            )
        except Exception as error:
            raise ModelRequestError(_failure_kind(error)) from None

        usage = response.usage
        input_tokens = usage.input_tokens if usage else None
        output_tokens = usage.output_tokens if usage else None

        def fail(kind):
            raise ModelRequestError(kind, input_tokens=input_tokens,
                                    output_tokens=output_tokens) from None

        if response.status == "incomplete":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            fail("output_limit" if reason == "max_output_tokens" else "incomplete")
        if response.status != "completed":
            fail("incomplete")
        for item in getattr(response, "output", []):
            if any(getattr(part, "type", None) == "refusal"
                   for part in getattr(item, "content", [])):
                fail("refusal")
        if not response.output_text:
            fail("invalid_response")
        try:
            content = schema.model_validate_json(response.output_text)
            # Never let a credential echoed in an output reach the UI/PDF.
            content = schema.model_validate_json(
                content.model_dump_json().replace(self._key, "[REDACTED]")
            )
        except (ValidationError, ValueError, TypeError):
            fail("invalid_response")
        return ModelReply(content, input_tokens, output_tokens)
