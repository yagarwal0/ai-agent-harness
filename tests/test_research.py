"""Mock-only checks for bounded fresh-context research and its interface."""

from dataclasses import replace
import json
import unittest
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from tutor.config import Config
from tutor.harness import TutorSession
from tutor.schemas import InterviewPlan, ModelReply
from tutor.search import SearchContext
from test_tutor import (ANSWER, APP_PATH, TOPIC, NotesModel, click, make_plan,
                        mock_assessment, pdf_text)


QUERY = "recent supervised learning framework release concepts"
CONTEXT_QUOTE = "This evidence is only in a search snippet."
CONTEXT = SearchContext(
    text=f"Source: Framework documentation\nSearch snippet: {CONTEXT_QUOTE}",
    sources=[{"title": "Framework documentation", "url": "https://example.org/docs"}],
    query=QUERY,
)


def research_request():
    return InterviewPlan(title="Fresh topic", summary="Additional context is needed.",
                         questions=[], research_query=QUERY)


def fake_model(*contents, name="gpt-4.1-mini"):
    model = Mock()
    model.name = name
    model.generate.side_effect = [ModelReply(content, 10, 20) for content in contents]
    return model


def new_session(model, search_client=None, config=None):
    return TutorSession(TOPIC, "Beginner", "", model, config or Config(),
                        search_client=search_client)


class ResearchHarnessTests(unittest.TestCase):
    def test_stable_topic_does_not_search(self):
        model = fake_model(make_plan())
        search = Mock()
        session = new_session(model, search)
        session.start()
        search.search.assert_not_called()
        self.assertEqual(session.search_calls, 0)
        self.assertEqual(session.calls, 1)
        self.assertEqual(session.status, "Interviewing")
        self.assertEqual(session.research_context, "")

    def test_requested_research_replans_once_and_accounts_for_known_usage(self):
        notes = NotesModel(mock_assessment()).generate([], report=True, max_output_tokens=100).content
        model = fake_model(research_request(), make_plan(), notes)
        search = Mock()
        search.search.return_value = CONTEXT
        session = new_session(model, search)
        session.start()
        search.search.assert_called_once_with(QUERY)
        self.assertEqual((session.calls, session.search_calls), (2, 1))
        self.assertEqual(session.research_context, CONTEXT.text)
        self.assertEqual(session.research_sources, CONTEXT.sources)
        first = json.loads(model.generate.call_args_list[0].args[0][1]["content"])
        second = json.loads(model.generate.call_args_list[1].args[0][1]["content"])
        self.assertTrue(first["research_available"])
        self.assertFalse(second["research_available"])
        self.assertEqual(second["research_context"], CONTEXT.text)
        self.assertEqual(second["research_sources"], CONTEXT.sources)
        self.assertIn("current_date", second)
        session.send(ANSWER)
        session.finish()
        session.finish()
        report = json.loads(model.generate.call_args.args[0][1]["content"])
        self.assertEqual(report["research_sources"], CONTEXT.sources)
        self.assertEqual((session.calls, session.search_calls), (3, 1))
        self.assertEqual((session.input_tokens, session.output_tokens), (30, 60))
        self.assertAlmostEqual(session.estimated_cost,
                               session.config.cost(30, 60) + session.config.search_price_usd)
        self.assertFalse(session.usage_unknown)
        _, text = pdf_text(session)
        self.assertIn("Additional context sources", text)
        self.assertIn("https://example.org/docs", text)

    def test_missing_or_disabled_search_stops_without_inventing_questions(self):
        for use_search, config, message in (
                (False, Config(), "Fresh context is needed"),
                (True, Config(max_search_calls=0), "Context search allowance reached")):
            with self.subTest(search_available=use_search):
                model = fake_model(research_request())
                search = Mock() if use_search else None
                session = new_session(model, search, config)
                with self.assertRaisesRegex(ValueError, message):
                    session.start()
                session.finish()
                self.assertEqual(session.calls, 1)
                self.assertEqual(session.search_calls, 0)
                self.assertIsNone(session.plan)
                self.assertEqual(session.messages, [])
                self.assertIn("Partial", session.status)
                if search is not None:
                    search.search.assert_not_called()

    def test_failed_search_is_counted_sanitized_and_never_retried(self):
        secret_marker = "synthetic-secret-for-failure-test"
        model = fake_model(research_request())
        search = Mock()
        search.search.side_effect = RuntimeError(secret_marker)
        session = new_session(model, search)
        with self.assertRaisesRegex(ValueError, "Context search was unavailable") as error:
            session.start()
        session.finish()
        with self.assertRaisesRegex(ValueError, "already started"):
            session.start()
        self.assertEqual((session.calls, session.search_calls), (1, 1))
        search.search.assert_called_once_with(QUERY)
        self.assertAlmostEqual(session.estimated_cost,
                               session.config.cost(10, 20) + session.config.search_price_usd)
        self.assertEqual(session.research_sources, [])
        _, text = pdf_text(session)
        self.assertNotIn(secret_marker, str(error.exception) + session.notice + text)

    def test_second_research_request_cannot_repeat_the_search(self):
        model = fake_model(research_request(), research_request())
        search = Mock()
        search.search.return_value = CONTEXT
        session = new_session(model, search)
        with self.assertRaisesRegex(ValueError, "context was insufficient"):
            session.start()
        session.finish()
        search.search.assert_called_once_with(QUERY)
        self.assertEqual((session.calls, session.search_calls), (2, 1))
        self.assertIsNone(session.plan)
        self.assertEqual(session.messages, [])

    def test_call_and_cost_limits_prevent_spending_on_search(self):
        base = Config(max_cost_usd=1)
        probe = new_session(fake_model(), Mock(), base)
        first_bound = probe._input_bound(False)
        first_allowance = (base.cost(first_bound, base.question_output_tokens)
                           + base.cost(base.max_input_bytes, base.report_output_tokens))
        replan_bound = min(base.max_input_bytes,
                           first_bound + base.max_search_context_chars * 4 + 2_000)
        research_allowance = (base.cost(10, 20) + base.search_price_usd
                              + base.cost(replan_bound, base.question_output_tokens)
                              + base.cost(base.max_input_bytes, base.report_output_tokens))
        self.assertLess(first_allowance, research_allowance)
        configs = [Config(max_calls=2),
                   replace(base, max_cost_usd=(first_allowance + research_allowance) / 2)]
        for config in configs:
            with self.subTest(config=config):
                model = fake_model(research_request())
                search = Mock()
                session = new_session(model, search, config)
                with self.assertRaisesRegex(ValueError, "budget cannot cover fresh context"):
                    session.start()
                session.finish()
                search.search.assert_not_called()
                self.assertEqual((session.calls, session.search_calls), (1, 0))

    def test_search_snippet_quotes_cannot_earn_learner_marks(self):
        assessment = mock_assessment()
        assessment.preparedness.evidence = CONTEXT_QUOTE
        notes = NotesModel(assessment).generate([], report=True, max_output_tokens=100).content
        model = fake_model(research_request(), make_plan(), notes)
        search = Mock()
        search.search.return_value = CONTEXT
        session = new_session(model, search)
        session.start()
        session.send(ANSWER)
        session.finish()
        self.assertIsNotNone(session.notes)
        self.assertIsNone(session.notes.assessment)
        self.assertIn("evidence did not match", session.assessment_notice)
        self.assertEqual(session.research_sources, CONTEXT.sources)

    def test_ui_hides_planned_totals_and_search_uses_config_automatically(self):
        plan = make_plan()
        announcement = "We will ask 10 questions total."
        plan.summary = announcement
        with patch("tutor.openai_model.OpenAIModel", return_value=fake_model(plan)), \
             patch("tutor.search.BraveSearch"):
            app = AppTest.from_file(APP_PATH, default_timeout=20).run()
            self.assertEqual(len(app.number_input), 0)
            self.assertEqual(len(app.checkbox), 0)
            app.text_input(key="topic").input(TOPIC)
            click(app, "Start interview")
            self.assertFalse(app.exception)
            self.assertEqual(len(app.get("progress")), 0)
            visible = "\n".join(element.value for element in [*app.caption, *app.markdown])
            self.assertNotIn(announcement, visible)
            self.assertNotIn("Question 1/10", visible)
            self.assertIn("Question 1 (", visible)

        for enabled in (True, False):
            with self.subTest(search_enabled=enabled):
                model = fake_model(make_plan())
                search = Mock()
                config = Config(max_search_calls=1 if enabled else 0)
                with patch("tutor.config.Config", return_value=config), \
                     patch("tutor.openai_model.OpenAIModel", return_value=model) as model_factory, \
                     patch("tutor.search.BraveSearch", return_value=search) as search_factory:
                    app = AppTest.from_file(APP_PATH, default_timeout=20).run()
                    self.assertEqual(len(app.radio), 0)
                    self.assertFalse(app.exception)
                    self.assertEqual(len(app.checkbox), 0)
                    self.assertFalse(next(button for button in app.button
                                          if button.label == "Start interview").disabled)
                    model_factory.assert_not_called()
                    search_factory.assert_not_called()
                    app.text_input(key="topic").input(TOPIC)
                    click(app, "Start interview")
                    self.assertFalse(app.exception)
                    model_factory.assert_called_once()
                    if enabled:
                        search_factory.assert_called_once_with()
                        self.assertIs(app.session_state["session"].search_client, search)
                    else:
                        search_factory.assert_not_called()
                        self.assertIsNone(app.session_state["session"].search_client)
                    search.search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
