"""Brave Search transport checks using synthetic keys and responses only."""

import http.client
import json
import socket
import unittest
from unittest.mock import Mock, patch

from tutor.search import (
    BraveSearch, MAX_CONTEXT_CHARS, MAX_RESPONSE_BYTES, SearchError,
)


SYNTHETIC_KEY = "synthetic-brave-token-for-tests"


def result(title="Learning concepts", url="https://example.com/lesson", description="Use labeled training examples to learn a mapping from features to outputs."):
    return {"title": title, "url": url, "description": description}


def response_for(data, *, status=200, headers=None):
    response = Mock(status=status)
    response.getheaders.return_value = headers or [("Content-Type", "application/json")]
    body = json.dumps(data).encode("utf-8")
    response.read1.side_effect = [body, b""]
    return response


class SearchTests(unittest.TestCase):
    def invoke(self, response, query="supervised machine learning", **kwargs):
        connection = Mock()
        connection.getresponse.return_value = response
        with patch("tutor.secrets.load_key", return_value=SYNTHETIC_KEY) as credentials, patch("tutor.search.http.client.HTTPSConnection", return_value=connection) as transport:
            context = BraveSearch().search(query, **kwargs)
        return context, connection, credentials, transport

    def test_fixed_endpoint_one_request_and_no_credentials_in_context(self):
        response = response_for({"web": {"results": [result(description=f"Labeled examples. {SYNTHETIC_KEY}")]}})
        context, connection, credentials, transport = self.invoke(response)
        transport.assert_called_once_with("api.search.brave.com", timeout=8)
        credentials.assert_called_once_with("brave", None)
        args, kwargs = connection.request.call_args
        self.assertEqual(args[0], "GET")
        self.assertTrue(args[1].startswith("/res/v1/web/search?q=supervised+machine+learning&count=3&"))
        self.assertEqual(kwargs["headers"]["X-Subscription-Token"], SYNTHETIC_KEY)
        self.assertIn("[REDACTED]", context.text)
        self.assertNotIn(SYNTHETIC_KEY, repr(context))
        self.assertEqual(context.sources, [{"title": "Learning concepts", "url": "https://example.com/lesson"}])
        connection.request.assert_called_once()
        connection.close.assert_called_once()

    def test_query_and_count_limits_stop_before_credentials_or_network(self):
        for query in ("", " ", "x" * 301, "a " * 76):
            with self.subTest(query=query), patch("tutor.search.http.client.HTTPSConnection") as network, patch("tutor.secrets.load_key") as key:
                with self.assertRaises(SearchError):
                    BraveSearch().search(query)
                network.assert_not_called()
                key.assert_not_called()
        for count in (0, 4, True, 1.5):
            with self.subTest(count=count), self.assertRaises(SearchError):
                BraveSearch().search("learning", max_results=count)

    def test_result_count_text_and_total_context_are_bounded(self):
        results = [result(title="<b>" + "t" * 200 + "</b>", url=f"https://example.com/{number}", description="d" * 2_000) for number in range(9)]
        context, connection, _, _ = self.invoke(response_for({"web": {"results": results}}))
        self.assertEqual(len(context.sources), 3)
        self.assertLessEqual(len(context.text), MAX_CONTEXT_CHARS)
        self.assertNotIn("<b>", context.text)
        self.assertEqual(len(context.sources[0]["title"]), 160)
        self.assertNotIn("d" * 801, context.text)
        connection.request.assert_called_once()

    def test_unsafe_duplicate_and_empty_sources_are_skipped(self):
        invalid = ["javascript:alert(1)", "file:///secret", "https://user:pass@example.com/a", "http://127.0.0.1/", "https://localhost/", "http://10.0.0.1/", "http://[::1]/", "https://private.local/", "https://example.com:8443/", f"https://example.com/?token={SYNTHETIC_KEY}", "https://example.com/a\nHeader: secret"]
        results = [result(url=url) for url in invalid] + [result(description=""), result(), result(), result(url="https://other.example/lesson#part")]
        context, _, _, _ = self.invoke(response_for({"web": {"results": results}}))
        self.assertEqual([source["url"] for source in context.sources], ["https://example.com/lesson", "https://other.example/lesson"])

    def test_error_statuses_redirects_and_transport_errors_are_sanitized_without_retry(self):
        for status in (301, 401, 403, 429, 500):
            response = response_for({"secret": SYNTHETIC_KEY}, status=status)
            connection = Mock()
            connection.getresponse.return_value = response
            with self.subTest(status=status), patch("tutor.secrets.load_key", return_value=SYNTHETIC_KEY), patch("tutor.search.http.client.HTTPSConnection", return_value=connection):
                with self.assertRaises(SearchError) as error:
                    BraveSearch().search("learning")
                self.assertNotIn(SYNTHETIC_KEY, str(error.exception))
                response.read1.assert_not_called()
                connection.request.assert_called_once()
                connection.close.assert_called_once()
        for failure in (socket.timeout(SYNTHETIC_KEY), http.client.HTTPException(SYNTHETIC_KEY)):
            connection = Mock()
            connection.request.side_effect = failure
            with patch("tutor.secrets.load_key", return_value=SYNTHETIC_KEY), patch("tutor.search.http.client.HTTPSConnection", return_value=connection):
                with self.assertRaises(SearchError) as error:
                    BraveSearch().search("learning")
                self.assertNotIn(SYNTHETIC_KEY, str(error.exception))
                connection.request.assert_called_once()
                connection.close.assert_called_once()

    def test_malformed_empty_and_oversize_responses_are_rejected(self):
        for data in ([], {}, {"web": []}, {"web": {"results": []}}, {"web": {"results": [None, result(url="file:///secret")]}}):
            with self.subTest(data=data), self.assertRaises(SearchError):
                self.invoke(response_for(data))
        cases = [
            response_for({}, headers=[("Content-Length", str(MAX_RESPONSE_BYTES + 1))]),
            response_for({}, headers=[("Content-Encoding", "gzip")]),
        ]
        invalid_json = response_for({})
        invalid_json.read1.side_effect = [b"{malformed", b""]
        cases.append(invalid_json)
        streaming = response_for({})
        streaming.read1.side_effect = [b"x" * 65_536] * 16
        cases.append(streaming)
        for response in cases:
            with self.assertRaises(SearchError):
                self.invoke(response)

    def test_credentials_are_lazy_and_failures_do_not_expose_loader_errors(self):
        with patch("tutor.secrets.load_key", side_effect=ValueError(SYNTHETIC_KEY)) as load, patch("tutor.search.http.client.HTTPSConnection") as network:
            client = BraveSearch("synthetic-path.txt")
            load.assert_not_called()
            with self.assertRaises(SearchError) as error:
                client.search("learning")
            self.assertNotIn(SYNTHETIC_KEY, str(error.exception))
            load.assert_called_once_with("brave", "synthetic-path.txt")
            network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
