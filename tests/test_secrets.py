"""Credential parsing checks use temporary synthetic files, never workspace keys."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tutor.secrets import load_key


class SecretTests(unittest.TestCase):
    def read(self, text, provider):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "synthetic-keys.txt"
            path.write_text(text, encoding="utf-8")
            return load_key(provider, path)

    def test_named_keys_are_kept_separate(self):
        text = '# Local credentials\nOPENAI_API_KEY="synthetic-openai"\nBRAVE_API_KEY=synthetic-brave\n'
        self.assertEqual(self.read(text, "openai"), "synthetic-openai")
        self.assertEqual(self.read(text, "brave"), "synthetic-brave")

    def test_json_keys_and_aliases(self):
        text = json.dumps({"openai_api_key": "synthetic-openai", "BRAVE_SEARCH_API_KEY": "synthetic-brave"})
        self.assertEqual(self.read(text, "openai"), "synthetic-openai")
        self.assertEqual(self.read(text, "brave"), "synthetic-brave")

    def test_single_legacy_key_is_only_assigned_to_openai(self):
        self.assertEqual(self.read("synthetic-original-key", "openai"), "synthetic-original-key")
        with self.assertRaises(ValueError):
            self.read("synthetic-original-key", "brave")

    def test_ambiguous_missing_duplicate_and_invalid_keys_fail_safely(self):
        for text in ("synthetic-openai\nsynthetic-brave", "OPENAI_API_KEY=synthetic-openai",
                     "BRAVE_API_KEY=synthetic-brave\nbrave=another-secret",
                     "BRAVE_API_KEY=", "BRAVE_API_KEY=synthetic secret", "{invalid-secret-json"):
            with self.subTest(format=text.splitlines()[0].split("=")[0]), self.assertRaises(ValueError) as error:
                self.read(text, "brave")
            self.assertNotIn("synthetic-brave", str(error.exception))
            self.assertNotIn("another-secret", str(error.exception))

    def test_environment_lookup_does_not_open_a_file(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "synthetic-openai", "BRAVE_API_KEY": "synthetic-brave"}, clear=True), \
             patch("tutor.secrets.Path.read_text", side_effect=AssertionError("No file read")):
            self.assertEqual(load_key("openai"), "synthetic-openai")
            self.assertEqual(load_key("brave"), "synthetic-brave")

    def test_missing_or_oversize_files_fail_without_values(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "missing.txt"
            with self.assertRaisesRegex(ValueError, "Cannot read"):
                load_key("brave", path)
            path.write_text("synthetic-secret" * 2000, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "too large"):
                load_key("brave", path)


if __name__ == "__main__":
    unittest.main()
