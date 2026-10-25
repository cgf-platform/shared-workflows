"""Validate and normalise a human-supplied release version.

Replaces three copies of the same shell snippet. The version arrives through the
environment (never interpolated into a script), is checked against strict
MAJOR.MINOR.PATCH, and optionally must not already be a GitHub Release.

Inputs (environment):
  VERSION            the raw version the caller supplied
  VERSION_PREFIX     forbid | allow   whether a leading "v" is accepted
  EXISTING_RELEASE   forbid | ignore  whether an existing release for the tag fails
  GITHUB_REPOSITORY  owner/repo, used for the existing-release lookup
  GH_TOKEN           token for `gh` (only needed when EXISTING_RELEASE=forbid)
  GITHUB_OUTPUT      file receiving the `version` and `tag` outputs
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
PREFIX_MODES = ("forbid", "allow")
EXISTING_RELEASE_MODES = ("forbid", "ignore")


def normalize(raw: str, prefix_mode: str) -> tuple[str, str]:
    """Return (bare version, v-tag) for `raw`, or raise ValueError explaining why not."""
    if prefix_mode not in PREFIX_MODES:
        raise ValueError(f"VERSION_PREFIX must be one of {PREFIX_MODES}, got '{prefix_mode}'")
    bare = raw
    if raw.startswith("v"):
        if prefix_mode == "forbid":
            raise ValueError(f"'{raw}' is not MAJOR.MINOR.PATCH (no leading v).")
        bare = raw[1:]
    if not SEMVER.fullmatch(bare):
        expected = "1.2.3 or v1.2.3" if prefix_mode == "allow" else "MAJOR.MINOR.PATCH (no leading v)"
        raise ValueError(f"'{raw}' is not {expected}.")
    return bare, f"v{bare}"


def release_exists(tag: str, repository: str) -> bool:
    """True if `repository` already has a GitHub Release for `tag`."""
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repository],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def fail(title: str, message: str) -> int:
    print(f"::error title={title}::{message}")
    return 1


def main() -> int:
    raw = os.environ.get("VERSION")
    if raw is None:
        return fail("Missing version", "VERSION was not provided to the validator.")
    prefix_mode = os.environ.get("VERSION_PREFIX", "forbid")
    existing_mode = os.environ.get("EXISTING_RELEASE", "forbid")
    if existing_mode not in EXISTING_RELEASE_MODES:
        return fail(
            "Bad configuration",
            f"EXISTING_RELEASE must be one of {EXISTING_RELEASE_MODES}, got '{existing_mode}'.",
        )

    try:
        version, tag = normalize(raw, prefix_mode)
    except ValueError as error:
        return fail("Bad version", str(error))

    if existing_mode == "forbid" and release_exists(tag, os.environ["GITHUB_REPOSITORY"]):
        return fail("Version exists", f"Release {tag} already exists. Pick a new version.")

    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"version={version}\ntag={tag}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
