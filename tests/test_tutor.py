"""Mock-only interview checks; no real keys, network, or generated-code execution."""

from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

from tutor.config import Config
from tutor.harness import TutorSession
from tutor.openai_model import OpenAIModel
from tutor.pdf_export import build_pdf
from tutor.schemas import (Approach, CriterionScore, FollowUp, InterviewAssessment,
                           InterviewPlan, InterviewQuestion, ModelReply, StudyNotes)
from tutor.sources import Source


APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")
TOPIC = "Supervised machine learning"
ANSWER = "I train on labeled examples and use a held-out validation set to check generalization."
PROBLEM = "Return the sum of a list nums of small integers. Example: [2, 3] -> 5; [] -> 0."


def mock_assessment():
    """Illustrative marks for exercising the app, not a live learner assessment."""
    return InterviewAssessment(
        preparedness=CriterionScore(marks=3, reason="The answer identifies labeled training examples.",
                                    evidence="I train on labeled examples"),
        concept_knowledge=CriterionScore(marks=3, reason="It connects learning to generalization.",
                                         evidence="check generalization"),
        application=CriterionScore(marks=1, reason="A validation set is mentioned; justify the split strategy too.",
                                   evidence="held-out validation set"),
        reasoning=CriterionScore(marks=1, reason="The goal is stated, but the justification is brief.",
                                 evidence="to check generalization"),
        improvements=["Explain how the validation split avoids information leakage.",
                      "Choose a metric and justify it for a concrete prediction task."],
    )


def make_plan(question_count=10):
    """Independent test data; never loaded by the application or sent to an API."""
    categories = ("preparedness", "concept_knowledge", "application", "reasoning")
    return InterviewPlan(
        title=TOPIC,
        summary="Synthetic plan for deterministic tests only.",
        questions=[InterviewQuestion(category=categories[number % len(categories)],
                                     text=f"Synthetic question {number + 1}: explain a learning concept.")
                   for number in range(question_count)],
    )


class NotesModel:
    """Test-only model stand-in; zero usage means no real API calls were made."""

    name = "gpt-4.1-mini"

    def __init__(self, assessment=None, approaches=None):
        self.assessment = assessment
        self.approaches = approaches or []
        self.report_messages = None

    def generate(self, messages, *, report, max_output_tokens):
        if not report:
            settings = json.loads(messages[1]["content"])
            return ModelReply(make_plan(settings["question_count"]), 0, 0)
        self.report_messages = messages
        return ModelReply(StudyNotes(
            summary="Supervised learning uses labeled examples to learn a prediction rule.",
            assumptions=["The training labels describe the prediction task."],
            key_concepts=["Training examples contain inputs and target labels.",
                          "A held-out validation set helps compare models without training on its examples."],
            approaches=self.approaches,
            feedback="Illustrative mock feedback for PDF and interface checks.",
            common_mistakes=["Using validation examples to fit the model creates leakage."],
            follow_ups=[
                FollowUp(question="What changes if labels are unavailable?",
                         sketch="Consider unsupervised learning and define a useful discovery objective."),
                FollowUp(question="How would temporal data change the validation split?",
                         sketch="Keep future observations out of past training windows."),
                FollowUp(question="How should class imbalance affect metric selection?",
                         sketch="Compare precision, recall, and task-specific costs instead of accuracy alone."),
            ],
            assessment=self.assessment,
        ), 0, 0)


def make_session(model=None, config=None, problem=None, level="Beginner", *,
                 question_count=10, source_url="", source_title=TOPIC, company=""):
    return TutorSession(problem or TOPIC, level, company, model or NotesModel(), config or Config(),
                        question_count=question_count, source_url=source_url, source_title=source_title)


def pdf_text(session):
    data = build_pdf(session.problem, session.level, session.company, session.messages,
                     session.notes, status=session.status, model_name=session.model.name,
                     source_url=session.source_url, source_title=session.source_title,
                     question_count=session.question_count, answered_count=len(session.answers),
                     assessment_notice=session.assessment_notice,
                     research_sources=getattr(session, "research_sources", []))
    return data, "\n".join(page.extract_text() for page in PdfReader(BytesIO(data)).pages)


def click(app, label):
    return next(button for button in app.button if button.label == label).click().run()


class TutorTests(unittest.TestCase):
    def test_default_ten_and_hard_cap_twelve(self):
        for count in (10, 12):
            with self.subTest(count=count):
                session = make_session(question_count=count)
                session.start()
                self.assertEqual(len(session.plan.questions), count)
                self.assertEqual(len({q.category for q in session.plan.questions}), 4)
                for number in range(count):
                    self.assertIn(f"Question {number + 1} (", session.messages[-1]["content"])
                    self.assertNotIn(f"/{count}", session.messages[-1]["content"])
                    session.send(ANSWER)
                self.assertIsNone(session.current_question)
                self.assertEqual(len(session.answers), count)
                self.assertEqual(sum(m["role"] == "assistant" for m in session.messages), count)
                self.assertEqual(session.calls, 2)
                self.assertEqual(session.estimated_cost, 0)
                self.assertIsNotNone(session.notes)
                self.assertEqual(session.status, "Finished - unverified")
                self.assertIn("did not provide an interview review", session.assessment_notice)
                with self.assertRaisesRegex(ValueError, "finished"):
                    session.send("A thirteenth answer cannot change the plan.")

    def test_invalid_session_settings_are_rejected_before_calls(self):
        for count in (9, 13, True, 10.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                make_session(question_count=count)
        for options in ({"problem": "x" * 8_001}, {"level": "Expert"},
                        {"company": "x" * 101}, {"config": Config(max_calls=1)}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                make_session(**options)

    def test_plan_contract_rejects_duplicates_categories_and_counts(self):
        plan = make_plan().model_dump()
        for change in ("duplicate", "category", "coverage", "too few", "too many", "blank"):
            data = json.loads(json.dumps(plan))
            if change == "duplicate":
                data["questions"][1]["text"] = "  " + data["questions"][0]["text"].upper() + "  "
            elif change == "category":
                data["questions"][0]["category"] = "unrelated"
            elif change == "coverage":
                for item in data["questions"]:
                    item["category"] = "preparedness"
            elif change == "too few":
                data["questions"] = data["questions"][:9]
            elif change == "too many":
                data["questions"] += data["questions"][:3]
            else:
                data["questions"][0]["text"] = "     "
            with self.subTest(change=change), self.assertRaises(ValueError):
                InterviewPlan.model_validate(data)
        for content in (make_plan(11), "unstructured questions"):
            model = Mock()
            model.name = "gpt-4.1-mini"
            model.generate.return_value = ModelReply(content, 0, 0)
            session = make_session(model)
            with self.assertRaises(ValueError):
                session.start()
            self.assertIsNone(session.plan)
            self.assertIn("Partial", session.status)
            session.finish()
            self.assertEqual(session.calls, 1)

    def test_answers_use_no_model_calls_and_finish_runs_once(self):
        model = NotesModel(mock_assessment())
        session = make_session(model, Config(max_calls=2), question_count=12)
        session.start()
        for number in range(12):
            session.send(ANSWER)
            self.assertEqual(session.calls, 2 if number == 11 else 1)
        session.finish()
        self.assertEqual(session.calls, 2)
        self.assertEqual(session.status, "Finished - unverified")
        self.assertEqual(session.notes.assessment.total, 8)
        payload = json.loads(model.report_messages[1]["content"])
        self.assertEqual(payload["question_count"], 12)
        self.assertEqual([item["answer"] for item in payload["interview"]], [ANSWER] * 12)
        self.assertEqual([item["number"] for item in payload["interview"]], list(range(1, 13)))
        with self.assertRaisesRegex(ValueError, "already started"):
            session.start()

    def test_early_finish_preserves_coverage_and_no_answers_are_unscored(self):
        empty = make_session(NotesModel(mock_assessment()))
        empty.start()
        empty.finish()
        empty.finish()
        self.assertEqual(empty.calls, 1)
        self.assertIsNone(empty.notes)
        self.assertIn("no interview answers", empty.assessment_notice)
        _, text = pdf_text(empty)
        self.assertIn("Answers recorded: 0.", text)
        self.assertNotIn("Total:", text)
        model = NotesModel(mock_assessment())
        session = make_session(model)
        session.start()
        session.send(ANSWER)
        session.finish()
        self.assertEqual(session.calls, 2)
        self.assertIn("Partial", session.status)
        payload = json.loads(model.report_messages[1]["content"])["interview"]
        self.assertEqual(payload[0]["answer"], ANSWER)
        self.assertTrue(all(item["answer"] is None for item in payload[1:]))

    def test_default_context_accepts_twelve_max_ascii_answers_and_source(self):
        model = NotesModel()
        session = make_session(model, problem="S" * 4_000, question_count=12)
        session.start()
        answer = "A" * session.config.max_message_chars
        for _ in range(12):
            session.send(answer)
        self.assertEqual(session.answers, [answer] * 12)
        self.assertEqual(session.calls, 2)
        self.assertEqual(session.status, "Finished - unverified")
        self.assertLessEqual(session._input_bound(True), session.config.max_input_bytes)
        self.assertEqual(json.loads(model.report_messages[1]["content"])["source_material"], "S" * 4_000)

    def test_context_failure_preserves_full_latest_answer_and_stops(self):
        session = make_session(NotesModel())
        session.start()
        session.config = replace(session.config, max_input_bytes=session._input_bound(True) + 10)
        answer = "preserved answer " * 50
        session.send(answer)
        self.assertEqual(session.answers, [answer.strip()])
        self.assertEqual(session.messages[-1]["content"], answer.strip())
        self.assertIn("preserved", session.notice)
        self.assertIn("Partial", session.status)
        session.finish()
        self.assertEqual(session.calls, 1)
        _, text = pdf_text(session)
        self.assertIn(" ".join(answer.split()), " ".join(text.split()))

    def test_budget_and_input_bounds_prevent_model_call(self):
        for config in (Config(max_cost_usd=0.00001), Config(max_input_bytes=100)):
            model = Mock()
            model.name = "gpt-4.1-mini"
            session = make_session(model, config)
            with self.assertRaises(ValueError):
                session.start()
            session.finish()
            model.generate.assert_not_called()
            self.assertEqual(session.calls, 0)
            self.assertIn("Partial", session.status)

    def test_provider_failure_is_counted_and_error_secrets_are_not_retained(self):
        model = Mock()
        model.name = "gpt-4.1-mini"
        marker = "synthetic-secret-never-log"
        model.generate.side_effect = RuntimeError(marker)
        session = make_session(model)
        with self.assertRaisesRegex(ValueError, "Model request failed") as result:
            session.start()
        session.finish()
        self.assertEqual(session.calls, 1)
        self.assertEqual(model.generate.call_count, 1)
        self.assertTrue(session.usage_unknown)
        self.assertGreater(session.estimated_cost, 0)
        _, text = pdf_text(session)
        self.assertNotIn(marker, str(result.exception) + session.notice + text)
        self.assertIn("PARTIAL", text)

    def test_malformed_final_report_exports_answers_without_retry(self):
        model = Mock()
        model.name = "gpt-4.1-mini"
        model.generate.side_effect = [ModelReply(make_plan(), 0, 0), ModelReply("not structured notes", 0, 0)]
        session = make_session(model)
        session.start()
        session.send(ANSWER)
        session.finish()
        session.finish()
        self.assertEqual(session.calls, 2)
        self.assertIsNone(session.notes)
        self.assertIn("Invalid structured response", session.notice)
        _, text = pdf_text(session)
        self.assertIn(ANSWER, " ".join(text.split()))
        self.assertIn("PARTIAL", text)

    def test_usage_and_cost_are_accounted_from_mocked_live_responses(self):
        notes_model = NotesModel()
        notes = notes_model.generate([], report=True, max_output_tokens=100).content
        model = Mock()
        model.name = "gpt-4.1-mini"
        model.generate.side_effect = [ModelReply(make_plan(), 10, 20), ModelReply(notes, 30, 40)]
        session = make_session(model, Config(max_calls=2))
        session.start()
        session.send(ANSWER)
        session.finish()
        self.assertEqual((session.input_tokens, session.output_tokens), (40, 60))
        self.assertAlmostEqual(session.estimated_cost, session.config.cost(40, 60))
        self.assertFalse(session.usage_unknown)

    def test_answer_limits_reject_invalid_input_without_recording_it(self):
        session = make_session()
        session.start()
        for text in (" ", "x" * 1_001):
            with self.assertRaises(ValueError):
                session.send(text)
        self.assertEqual(session.answers, [])
        self.assertEqual(session.calls, 1)
        session.finish()
        with self.assertRaisesRegex(ValueError, "finished"):
            session.send(ANSWER)

    def test_rubric_bounds_strict_numbers_and_partial_review(self):
        assessment = mock_assessment()
        self.assertEqual(assessment.total, 8)
        for field, marks in (("preparedness", 4), ("concept_knowledge", -1),
                             ("application", 3), ("reasoning", True), ("reasoning", 1.5)):
            data = assessment.model_dump()
            data[field]["marks"] = marks
            with self.subTest(field=field, marks=marks), self.assertRaises(ValueError):
                InterviewAssessment.model_validate(data)
        data = assessment.model_dump()
        data["total"] = 10
        with self.assertRaises(ValueError):
            InterviewAssessment.model_validate(data)
        data.pop("total")
        data["reasoning"] = {"marks": None, "reason": "A justification is missing.", "evidence": ""}
        partial = InterviewAssessment.model_validate(data)
        self.assertIsNone(partial.total)
        session = make_session(NotesModel(partial))
        session.start()
        session.send(ANSWER)
        session.finish()
        _, text = pdf_text(session)
        self.assertIn("Not assessed", text)
        self.assertIn("no overall score", text)
        self.assertNotIn("Total:", text)

    def test_evidence_from_source_questions_or_settings_cannot_earn_marks(self):
        quote = "Evidence exists only outside the learner answer."
        for origin in ("invented", "source", "question", "settings"):
            with self.subTest(origin=origin):
                assessment = mock_assessment()
                assessment.preparedness.evidence = quote
                session = make_session(NotesModel(assessment),
                                       problem=TOPIC + (" " + quote if origin == "source" else ""),
                                       company=quote if origin == "settings" else "")
                session.start()
                if origin == "question":
                    session.plan.questions[0].text = quote
                session.send(ANSWER)
                session.finish()
                self.assertIsNotNone(session.notes)
                self.assertIsNone(session.notes.assessment)
                self.assertIn("evidence did not match", session.assessment_notice)

    def test_general_pdf_uses_same_marks_concepts_and_no_forced_code(self):
        session = make_session(NotesModel(mock_assessment()),
                               source_url="https://en.wikipedia.org/wiki/Supervised_learning")
        session.start()
        session.send(ANSWER)
        session.finish()
        data, text = pdf_text(session)
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertIn("Total: 8/10", text)
        self.assertIn("AI review of your interview answers", text)
        self.assertIn("Key concepts", text)
        self.assertIn("Source URL: https://en.wikipedia.org/wiki/Supervised_learning", text)
        self.assertIn("Answers recorded: 1.", text)
        self.assertNotIn("Python code (untested)", text)
        self.assertEqual(session.notes.approaches, [])
        self.assertIn("not additional interview questions", text)
        for question in session.notes.follow_ups:
            self.assertIn(question.question, text)

    def test_evidence_must_appear_in_one_answer_without_splicing(self):
        assessment = mock_assessment()
        for field in ("preparedness", "concept_knowledge", "application", "reasoning"):
            getattr(assessment, field).evidence = "generalization.\nSecond recorded answer."
        session = make_session(NotesModel(assessment))
        session.start()
        session.send(ANSWER)
        session.send("Second recorded answer.")
        session.finish()
        self.assertIsNone(session.notes.assessment)
        self.assertIn("evidence did not match", session.assessment_notice)

    def test_pdf_shows_recorded_answers_without_announcing_planned_total(self):
        for count in (10, 12):
            with self.subTest(count=count):
                session = make_session(question_count=count)
                session.start()
                session.send(ANSWER)
                session.finish()
                _, text = pdf_text(session)
                self.assertIn("Answers recorded: 1.", text)
                self.assertIn("PARTIAL INTERVIEW", text)
                self.assertNotIn(f"1/{count}", text)
                self.assertNotIn(f"{count} questions", text)
                self.assertNotIn("planned questions", text)
                self.assertEqual(len(session.plan.questions), count)

    def test_pdf_records_search_provenance_without_claiming_verification(self):
        session = make_session()
        session.start()
        session.finish()
        session.research_sources = [
            {"title": "New concept <b>reference</b>",
             "url": "https://example.com/concept?version=1&view=full"},
            {"title": "", "url": "https://example.org/details"},
        ]
        _, text = pdf_text(session)
        self.assertIn("Additional context sources", text)
        self.assertIn("Search snippets have not been independently verified.",
                      " ".join(text.split()))
        self.assertIn("New concept <b>reference</b>", text)
        self.assertIn("https://example.com/concept?version=1&view=full", text)
        self.assertIn("Search result", text)
        session.research_sources = []
        _, text = pdf_text(session)
        self.assertNotIn("Additional context sources", text)

    def test_coding_pdf_preserves_exact_code_and_unexecuted_label(self):
        approach = Approach(name="Single pass (already optimal)",
                            intuition="Read each value once and accumulate the total.",
                            code="def total(nums):\n    return sum(nums)",
                            correctness="Every value contributes exactly once, starting at zero.",
                            time_complexity="O(n) for small constant-size integers.",
                            space_complexity="O(1) auxiliary space for these small values.",
                            worked_example="[2, 3]: start at 0, add 2, add 3, return 5.")
        session = make_session(NotesModel(approaches=[approach]), problem=PROBLEM,
                               source_title="Sum a list")
        session.start()
        session.send("I would sum every value once, with an empty list returning zero.")
        session.finish()
        _, text = pdf_text(session)
        self.assertIn("UNTESTED", text)
        self.assertIn("def total(nums):", text)
        self.assertIn("return sum(nums)", text)
        self.assertIn("Approach comparison", text)
        self.assertEqual(len(session.notes.follow_ups), 3)

    def test_adapter_parses_both_contracts_with_only_synthetic_key_and_redacts(self):
        marker = "synthetic-key-for-unit-test"
        plan = make_plan()
        plan.summary = f"This mock includes {marker} only to verify redaction."
        notes = NotesModel().generate([], report=True, max_output_tokens=100).content
        notes.summary = f"This mock report includes {marker} only to verify redaction."
        client = Mock()
        client.responses.create.side_effect = [
            SimpleNamespace(status="completed", output_text=plan.model_dump_json(), output=[],
                            usage=SimpleNamespace(input_tokens=10, output_tokens=20)),
            SimpleNamespace(status="completed", output_text=notes.model_dump_json(), output=[],
                            usage=SimpleNamespace(input_tokens=30, output_tokens=40)),
            SimpleNamespace(status="incomplete", output_text="", output=[], usage=None),
        ]
        with TemporaryDirectory() as directory:
            key_path = Path(directory) / "fake-key.txt"
            key_path.write_text(marker, encoding="utf-8")
            with patch("tutor.openai_model.OpenAI", return_value=client) as factory:
                model = OpenAIModel("gpt-4.1-mini", key_path=key_path)
                plan_reply = model.generate([{"role": "user", "content": "mock topic"}],
                                            report=False, max_output_tokens=100)
                notes_reply = model.generate([{"role": "user", "content": "mock answers"}],
                                             report=True, max_output_tokens=100)
                with self.assertRaisesRegex(ValueError, "complete, valid"):
                    model.generate([], report=True, max_output_tokens=100)
                self.assertEqual(factory.call_args.kwargs["max_retries"], 0)
        self.assertNotIn(marker, plan_reply.content.model_dump_json())
        self.assertNotIn(marker, notes_reply.content.model_dump_json())
        self.assertEqual(plan_reply.input_tokens, 10)
        calls = client.responses.create.call_args_list
        self.assertEqual(calls[0].kwargs["text"]["format"]["name"], "InterviewPlan")
        self.assertEqual(calls[1].kwargs["text"]["format"]["name"], "StudyNotes")
        self.assertTrue(all(call.kwargs["store"] is False for call in calls))
        self.assertNotIn(marker, str(calls))

    def test_app_topic_early_finish_download_and_reset(self):
        with patch("tutor.openai_model.OpenAIModel", return_value=NotesModel()), \
             patch("tutor.search.BraveSearch"):
            app = AppTest.from_file(APP_PATH, default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.selectbox), 1)
            self.assertEqual(len(app.number_input), 0)
            self.assertEqual(len(app.radio), 0)
            click(app, "Start interview")
            self.assertTrue(app.error)
            self.assertNotIn("session", app.session_state)
            app.text_input(key="topic").input(TOPIC)
            click(app, "Start interview")
            self.assertFalse(app.exception)
            self.assertIn(TOPIC, app.session_state["session"].problem)
            app.chat_input[0].set_value(ANSWER).run()
            self.assertEqual(app.session_state["session"].calls, 1)
            self.assertEqual(len(app.session_state["session"].answers), 1)
            click(app, "Finish & prepare PDF")
            self.assertFalse(app.exception)
            self.assertTrue(app.session_state["pdf_bytes"].startswith(b"%PDF"))
            self.assertIsNotNone(app.session_state["session"].notes)
            app.run()
            self.assertEqual(app.session_state["session"].calls, 2)
            click(app, "New session")
            self.assertFalse(app.exception)
            self.assertNotIn("session", app.session_state)

    def test_app_url_uses_mocked_source_without_network(self):
        url = "https://en.wikipedia.org/wiki/Unsupervised_learning"
        source = Source("Unsupervised learning", "A mock page about learning patterns without labels.", url)
        with patch("tutor.sources.load_source", return_value=source) as loader, \
             patch("tutor.openai_model.OpenAIModel", return_value=NotesModel()), \
             patch("tutor.search.BraveSearch"):
            app = AppTest.from_file(APP_PATH, default_timeout=20).run()
            app.text_input(key="source_url").input(url)
            click(app, "Start interview")
            self.assertFalse(app.exception)
            self.assertEqual(loader.call_args.args[0], url)
            self.assertEqual(app.session_state["session"].source_url, url)
            self.assertEqual(len(app.session_state["session"].plan.questions), 10)

    def test_app_completes_ten_answers_and_displays_mock_scorecard(self):
        with patch("tutor.openai_model.OpenAIModel", return_value=NotesModel(mock_assessment())), \
             patch("tutor.search.BraveSearch"):
            app = AppTest.from_file(APP_PATH, default_timeout=20).run()
            app.text_input(key="topic").input(TOPIC)
            click(app, "Start interview")
            for _ in range(10):
                app.chat_input[0].set_value(ANSWER).run()
                self.assertFalse(app.exception)
            self.assertEqual(app.metric[0].value, "8/10")
            self.assertEqual(len(app.chat_input), 0)
            self.assertEqual(app.session_state["session"].calls, 2)
            text = "\n".join(page.extract_text() for page in
                             PdfReader(BytesIO(app.session_state["pdf_bytes"])).pages)
            self.assertIn("Total: 8/10", text)
            self.assertIn("Answers recorded: 10.", text)
            app.run()
            self.assertEqual(app.session_state["session"].calls, 2)

    def test_app_has_clean_start_and_defers_clients_until_valid_submission(self):
        with patch("tutor.openai_model.OpenAIModel") as model_factory, \
             patch("tutor.search.BraveSearch") as search_factory:
            app = AppTest.from_file(APP_PATH, default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.radio), 0)
            self.assertEqual(len(app.checkbox), 0)
            self.assertFalse(next(button for button in app.button if button.label == "Start interview").disabled)
            visible = "\n".join(item.value for item in [*app.caption, *app.markdown])
            for removed in ("Enter a page URL or topic", "gpt-4.1-mini", "million input tokens",
                            "I approve", "estimated spending", "Fresh-context research"):
                self.assertNotIn(removed, visible)
            model_factory.assert_not_called()
            search_factory.assert_not_called()
            click(app, "Start interview")
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertNotIn("session", app.session_state)
            model_factory.assert_not_called()
            search_factory.assert_not_called()

    def test_app_previous_chat_session_can_reset_after_format_change(self):
        with patch("tutor.openai_model.OpenAIModel") as model_factory, \
             patch("tutor.search.BraveSearch") as search_factory:
            app = AppTest.from_file(APP_PATH, default_timeout=20).run()
            app.session_state["session"] = SimpleNamespace(status="Chatting", messages=[])
            app.run()
            self.assertFalse(app.exception)
            self.assertIn("format has changed", app.info[0].value)
            click(app, "New session")
            self.assertFalse(app.exception)
            self.assertNotIn("session", app.session_state)
            self.assertTrue(any(button.label == "Start interview" for button in app.button))
            model_factory.assert_not_called()
            search_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
