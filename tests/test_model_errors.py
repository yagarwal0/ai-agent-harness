"""Synthetic OpenAI failures; no credentials, network or paid model calls."""

import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import httpx2
from openai import (APIConnectionError, APITimeoutError, AuthenticationError,
                    BadRequestError, InternalServerError, NotFoundError,
                    OpenAI as SDKOpenAI, PermissionDeniedError, RateLimitError)
from streamlit.testing.v1 import AppTest

from tutor.config import Config
from tutor.harness import TutorSession
from tutor.openai_model import OpenAIModel
from tutor.schemas import (CriterionScore, InterviewAssessment, InterviewPlan,
                           ModelRequestError, StudyNotes)
from test_tutor import make_plan


FAKE_KEY = "synthetic-openai-secret-for-local-tests"
TOPIC = "Supervised learning"
APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


def plan_data():
    return make_plan().model_dump()


def notes_data():
    return dict(summary="Learning from labeled training examples.", assumptions=[],
                key_concepts=["Use validation data to compare models."], approaches=[],
                feedback="Explain the distinction between training and validation.",
                common_mistakes=[], assessment=None,
                follow_ups=[{"question": question, "sketch": "Explain the trade-off."}
                            for question in ("What if labels are missing?",
                                             "How would streaming input change this?",
                                             "Which validation metric is appropriate?")])


def completed(data=None, *, status="completed", output_text=None, output=None,
              reason=None, usage=True):
    return SimpleNamespace(
        status=status,
        output_text=json.dumps(data if data is not None else plan_data())
                    if output_text is None else output_text,
        output=[] if output is None else output,
        incomplete_details=SimpleNamespace(reason=reason) if reason else None,
        usage=SimpleNamespace(input_tokens=123, output_tokens=45) if usage else None,
    )


def adapter():
    # Patch both runtime key loading and the SDK constructor. The only client is a Mock.
    with patch("tutor.openai_model.load_key", return_value=FAKE_KEY) as loader, \
         patch("tutor.openai_model.OpenAI") as factory:
        model = OpenAIModel("gpt-4.1-mini")
        loader.assert_called_once()
        factory.assert_called_once()
        assert factory.call_args.kwargs["max_retries"] == 0
        return model, factory.return_value


def api_error(error_type, status, code=None):
    request = httpx2.Request("POST", "https://api.example.invalid/v1/responses")
    response = httpx2.Response(status, request=request)
    body = {"code": code, "message": FAKE_KEY, "param": FAKE_KEY}
    return error_type(f"Unsafe provider details: {FAKE_KEY}",
                      response=response, body=body)


class ModelErrorTests(unittest.TestCase):
    def assert_safe_error(self, model, expected, *, report=False, known_usage=False):
        with self.assertRaises(ModelRequestError) as caught:
            model.generate([], report=report, max_output_tokens=1_800)
        error = caught.exception
        self.assertIsInstance(error, ValueError)
        self.assertEqual(error.kind, expected)
        self.assertNotIn(FAKE_KEY, str(error))
        self.assertNotIn("Unsafe provider details", str(error))
        self.assertEqual((error.input_tokens, error.output_tokens),
                         (123, 45) if known_usage else (None, None))
        return error

    def test_http_failures_are_classified_without_provider_messages(self):
        cases = [
            (AuthenticationError, 401, "invalid_api_key", "authentication"),
            (RateLimitError, 429, "insufficient_quota", "quota"),
            (RateLimitError, 429, "credit_balance_exhausted", "quota"),
            (RateLimitError, 429, "organization_spend_limit_exceeded", "quota"),
            (RateLimitError, 429, "project_spend_limit_exceeded", "quota"),
            (RateLimitError, 429, "rate_limit_exceeded", "rate_limit"),
            (PermissionDeniedError, 403, None, "permission"),
            (NotFoundError, 404, "model_not_found", "model_unavailable"),
            (BadRequestError, 400, "invalid_json_schema", "invalid_schema"),
            (BadRequestError, 400, "invalid_request_error", "invalid_request"),
            (InternalServerError, 503, "server_error", "provider_unavailable"),
        ]
        for error_type, status, code, expected in cases:
            with self.subTest(kind=expected):
                model, client = adapter()
                client.responses.create.side_effect = api_error(error_type, status, code)
                self.assert_safe_error(model, expected)
                client.responses.create.assert_called_once()
                client.responses.parse.assert_not_called()

    def test_sdk_mock_http_response_retains_truncated_output_usage(self):
        """Exercise real SDK serialization/parsing through an in-memory transport."""
        requests = []

        def respond(request):
            requests.append(request)
            return httpx2.Response(200, json={
                "id": "resp_synthetic_incomplete", "object": "response",
                "created_at": 1_700_000_000, "model": "gpt-4.1-mini",
                "status": "incomplete", "error": None,
                "incomplete_details": {"reason": "max_output_tokens"},
                "output": [{"id": "msg_synthetic_incomplete", "type": "message",
                            "role": "assistant", "status": "incomplete",
                            "content": [{"type": "output_text", "annotations": [],
                                         "text": '{"title":"unfinished'}]}],
                "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
                "usage": {"input_tokens": 123, "output_tokens": 45,
                          "total_tokens": 168,
                          "input_tokens_details": {"cached_tokens": 0,
                                                   "cache_write_tokens": 0},
                          "output_tokens_details": {"reasoning_tokens": 0}},
            })

        # MockTransport handles every request in memory; trust_env=False avoids proxies.
        with httpx2.Client(transport=httpx2.MockTransport(respond), trust_env=False) as client:
            with SDKOpenAI(api_key=FAKE_KEY, base_url="https://api.example.invalid/v1",
                           http_client=client, max_retries=0) as sdk:
                with patch("tutor.openai_model.load_key", return_value=FAKE_KEY), \
                     patch("tutor.openai_model.OpenAI", return_value=sdk), \
                     patch("socket.create_connection", side_effect=AssertionError("No sockets allowed")):
                    model = OpenAIModel("gpt-4.1-mini")
                    self.assert_safe_error(model, "output_limit", known_usage=True)

        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].method, "POST")
        self.assertEqual(requests[0].url.path, "/v1/responses")
        body = json.loads(requests[0].content)
        self.assertEqual(body["max_output_tokens"], 1_800)
        self.assertEqual(body["model"], "gpt-4.1-mini")
        self.assertFalse(body["store"])
        self.assertNotIn(FAKE_KEY, requests[0].content.decode())
        format_data = body["text"]["format"]
        self.assertEqual(format_data["type"], "json_schema")
        self.assertIs(format_data["strict"], True)
        schema = format_data["schema"]
        self.assertIs(schema["additionalProperties"], False)
        self.assertEqual(set(schema["required"]), set(schema["properties"]))

    def test_network_failures_and_unknown_errors_are_sanitized(self):
        request = httpx2.Request("POST", "https://api.example.invalid/v1/responses")
        cases = [(APIConnectionError(message=FAKE_KEY, request=request), "connection"),
                 (APITimeoutError(request), "timeout"),
                 (RuntimeError(FAKE_KEY), "unknown")]
        for failure, expected in cases:
            with self.subTest(kind=expected):
                model, client = adapter()
                client.responses.create.side_effect = failure
                self.assert_safe_error(model, expected)
                client.responses.create.assert_called_once()

    def test_incomplete_response_is_checked_before_json_parsing(self):
        for reason, expected in (("max_output_tokens", "output_limit"),
                                 ("unknown_future_reason", "incomplete")):
            with self.subTest(reason=reason):
                model, client = adapter()
                client.responses.create.return_value = completed(
                    status="incomplete", output_text="{broken " + FAKE_KEY,
                    reason=reason)
                self.assert_safe_error(model, expected, known_usage=True)

    def test_refusal_is_distinct_and_retains_usage(self):
        model, client = adapter()
        refusal = SimpleNamespace(type="message", content=[
            SimpleNamespace(type="refusal", refusal=FAKE_KEY)])
        client.responses.create.return_value = completed(output=[refusal])
        self.assert_safe_error(model, "refusal", known_usage=True)

    def test_invalid_json_retains_usage_without_leaking_output(self):
        model, client = adapter()
        client.responses.create.return_value = completed(output_text="{ " + FAKE_KEY)
        self.assert_safe_error(model, "invalid_response", known_usage=True)

    def test_semantic_plan_validation_remains_enforced(self):
        for change in ("missing category", "duplicate", "incomplete", "mixed research"):
            with self.subTest(change=change):
                data = plan_data()
                if change == "missing category":
                    for question in data["questions"]:
                        question["category"] = "preparedness"
                elif change == "duplicate":
                    data["questions"][1]["text"] = data["questions"][0]["text"]
                elif change == "incomplete":
                    data["questions"] = data["questions"][:9]
                else:
                    data["research_query"] = "Find recent supervised learning context"
                model, client = adapter()
                client.responses.create.return_value = completed(data)
                self.assert_safe_error(model, "invalid_response", known_usage=True)

    def test_successful_plan_and_report_keep_usage_and_output_limits(self):
        for report, data, expected, limit in ((False, plan_data(), InterviewPlan, 1_800),
                                              (True, notes_data(), StudyNotes, 3_500)):
            with self.subTest(report=report):
                model, client = adapter()
                client.responses.create.return_value = completed(data)
                reply = model.generate([], report=report, max_output_tokens=limit)
                self.assertIsInstance(reply.content, expected)
                self.assertEqual((reply.input_tokens, reply.output_tokens), (123, 45))
                options = client.responses.create.call_args.kwargs
                self.assertEqual(options["model"], "gpt-4.1-mini")
                self.assertEqual(options["max_output_tokens"], limit)
                self.assertFalse(options["store"])
                client.responses.parse.assert_not_called()

    def test_strict_schema_format_keeps_nullable_fields_and_object_rules(self):
        def visit(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(set(node.get("required", [])),
                                     set(node.get("properties", {})))
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        for report, data, nullable in ((False, plan_data(), "research_query"),
                                      (True, notes_data(), "assessment")):
            with self.subTest(report=report):
                model, client = adapter()
                client.responses.create.return_value = completed(data)
                model.generate([], report=report, max_output_tokens=1_800)
                format_data = client.responses.create.call_args.kwargs["text"]["format"]
                self.assertEqual(format_data["type"], "json_schema")
                self.assertIs(format_data["strict"], True)
                schema = format_data["schema"]
                self.assertIn(nullable, schema["required"])
                variants = schema["properties"][nullable]["anyOf"]
                self.assertTrue(any(item.get("type") == "null" for item in variants))
                visit(schema)

    def test_credential_echo_is_redacted_in_valid_output(self):
        data = plan_data()
        data["summary"] = f"A model output accidentally echoed {FAKE_KEY}."
        model, client = adapter()
        client.responses.create.return_value = completed(data)
        reply = model.generate([], report=False, max_output_tokens=1_800)
        self.assertNotIn(FAKE_KEY, reply.content.model_dump_json())
        self.assertIn("[REDACTED]", reply.content.summary)

    def test_local_assessment_bounds_and_single_answer_evidence_are_unchanged(self):
        score = lambda marks, quote: CriterionScore(
            marks=marks, reason="Synthetic test reasoning.", evidence=quote)
        assessment = InterviewAssessment(
            preparedness=score(1, "learner answer"),
            concept_knowledge=score(1, "learner answer"),
            application=score(1, "learner answer"),
            reasoning=score(1, "learner answer"),
            improvements=["Explain a scenario.", "Explain the assumptions."],
        )
        assessment.validate_evidence(["The learner answer explains training data."])
        with self.assertRaises(ValueError):
            assessment.validate_evidence(["The learner", "answer explains training data."])
        data = assessment.model_dump()
        data["application"]["marks"] = 3
        with self.assertRaises(ValueError):
            InterviewAssessment.model_validate(data)

    def test_harness_accounts_known_failure_usage_once_and_never_retries(self):
        model = Mock(name="synthetic_model")
        model.name = "gpt-4.1-mini"
        failure = ModelRequestError("output_limit", input_tokens=123, output_tokens=45)
        model.generate.side_effect = failure
        session = TutorSession(TOPIC, "Beginner", "", model, Config())
        with self.assertRaises(ValueError) as caught:
            session.start()
        self.assertEqual(str(caught.exception), str(failure))
        self.assertEqual((session.calls, session.input_tokens, session.output_tokens),
                         (1, 123, 45))
        self.assertAlmostEqual(session.estimated_cost, Config().cost(123, 45))
        self.assertFalse(session.usage_unknown)
        self.assertIn("Partial", session.status)
        session.finish()
        session.finish()
        model.generate.assert_called_once()

    def test_headless_app_displays_safe_categorized_warning_and_no_marks(self):
        model = Mock(name="synthetic_model")
        model.name = "gpt-4.1-mini"
        failure = ModelRequestError("quota")
        model.generate.side_effect = failure
        with patch("tutor.openai_model.OpenAIModel", return_value=model), \
             patch("tutor.search.BraveSearch") as search_factory:
            app = AppTest.from_file(APP_PATH, default_timeout=20).run()
            self.assertEqual(len(app.checkbox), 0)
            app.text_input(key="topic").input(TOPIC)
            next(button for button in app.button if button.label == "Start interview").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any(warning.value == str(failure) for warning in app.warning))
            self.assertTrue(any("Not assessed" in item.value for item in app.info))
            self.assertNotIn(FAKE_KEY, " ".join(warning.value for warning in app.warning))
            model.generate.assert_called_once()
            search_factory.assert_called_once_with()
            search_factory.return_value.search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
