"""Behavioural tests for the JDK-version resolver used by setup-jvm.

Run from the repo root:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / ".github/actions/setup-jvm/java_version.py"
)
_spec = importlib.util.spec_from_file_location("java_version", SCRIPT_PATH)
java_version = importlib.util.module_from_spec(_spec)
sys.modules["java_version"] = java_version
_spec.loader.exec_module(java_version)


def run_main(explicit: str, properties: str | None) -> tuple[int, str, dict[str, str]]:
    """Run main() in a temp workspace holding `properties` as gradle.properties (or none)."""
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        if properties is not None:
            (workspace / "gradle.properties").write_text(properties)
        output_file = workspace / "github_output"
        output_file.touch()
        env = {
            "JAVA_VERSION": explicit,
            "GITHUB_WORKSPACE": str(workspace),
            "GITHUB_OUTPUT": str(output_file),
        }
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out):
            code = java_version.main()
        outputs = dict(
            line.split("=", 1) for line in output_file.read_text().splitlines() if "=" in line
        )
        return code, out.getvalue(), outputs


class ResolveTest(unittest.TestCase):
    def test_explicit_input_wins_over_gradle_properties(self):
        code, _, outputs = run_main("17", "javaVersion=21\n")
        self.assertEqual((code, outputs), (0, {"java-version": "17"}))

    def test_empty_input_reads_java_version_from_gradle_properties(self):
        code, _, outputs = run_main("", "org.gradle.caching=true\njavaVersion=25\n")
        self.assertEqual((code, outputs), (0, {"java-version": "25"}))

    def test_whitespace_around_the_property_is_tolerated(self):
        _, _, outputs = run_main("", "  javaVersion =  21  \n")
        self.assertEqual(outputs, {"java-version": "21"})

    def test_commented_out_property_is_ignored(self):
        _, _, outputs = run_main("", "# javaVersion=17\njavaVersion=21\n")
        self.assertEqual(outputs, {"java-version": "21"})

    def test_missing_gradle_properties_falls_back_to_default(self):
        code, _, outputs = run_main("", None)
        self.assertEqual((code, outputs), (0, {"java-version": "21"}))

    def test_gradle_properties_without_the_property_falls_back_to_default(self):
        _, _, outputs = run_main("", "org.gradle.caching=true\n")
        self.assertEqual(outputs, {"java-version": "21"})

    def test_non_numeric_property_fails_instead_of_silently_falling_back(self):
        code, stdout, outputs = run_main("", "javaVersion=latest\n")
        self.assertEqual(code, 1)
        self.assertIn("::error", stdout)
        self.assertIn("javaVersion", stdout)
        self.assertEqual(outputs, {})

    def test_non_numeric_explicit_input_fails(self):
        code, stdout, _ = run_main("21; rm -rf /", "javaVersion=21\n")
        self.assertEqual(code, 1)
        self.assertIn("::error", stdout)


if __name__ == "__main__":
    unittest.main()
