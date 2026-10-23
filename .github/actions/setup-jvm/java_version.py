"""Resolve the JDK major version for a build.

Order: the explicit `java-version` input, then `javaVersion` in the checked-out
repo's gradle.properties (the same property the build-conventions plugin uses for
the Gradle toolchain and the Paketo JRE), then DEFAULT_JAVA_VERSION. One source of
truth means a JDK upgrade is a one-line change in the service, not two.

Environment:
  JAVA_VERSION       explicit input; may be empty
  GITHUB_WORKSPACE   checkout root holding gradle.properties
  GITHUB_OUTPUT      file receiving the `java-version` output
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

DEFAULT_JAVA_VERSION = "21"
PROPERTY_NAME = "javaVersion"
MAJOR_VERSION = re.compile(r"[0-9]+")
PROPERTY_LINE = re.compile(rf"^\s*{PROPERTY_NAME}\s*=\s*(.*?)\s*$")


def read_property(properties_file: Path) -> str | None:
    """The value of `javaVersion` in `properties_file`, or None if absent."""
    if not properties_file.is_file():
        return None
    for line in properties_file.read_text(encoding="utf-8").splitlines():
        match = PROPERTY_LINE.match(line)
        if match:
            return match.group(1)
    return None


def main() -> int:
    explicit = os.environ.get("JAVA_VERSION", "").strip()
    if explicit:
        source, value = "the java-version input", explicit
    else:
        from_properties = read_property(Path(os.environ["GITHUB_WORKSPACE"]) / "gradle.properties")
        if from_properties is None:
            source, value = "the default", DEFAULT_JAVA_VERSION
        else:
            source, value = f"{PROPERTY_NAME} in gradle.properties", from_properties

    if not MAJOR_VERSION.fullmatch(value):
        print(f"::error title=Bad JDK version::'{value}' from {source} is not a major version like 21.")
        return 1

    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"java-version={value}\n")
    print(f"JDK {value} (from {source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
