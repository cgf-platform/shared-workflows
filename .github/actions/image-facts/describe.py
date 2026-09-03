#!/usr/bin/env python3
"""Describe a built OCI image in the run summary.

Exists because the pipeline used to *assert* things about its images that were
not true: seven `-PBP_*` flags never reached the buildpack, so releases shipped a
full JDK under a step named "JRE" for months with nothing to contradict it.

Reads the Paketo build metadata label, which is authoritative about the runtime
the buildpack actually installed -- unlike running `java -version`, which depends
on the launcher being on PATH.

Never fails the build. A diagnostic that can break a good release is worse than
no diagnostic.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

BUILD_METADATA_LABEL = "io.buildpacks.build.metadata"
# Paketo installs one of these; which one is the JDK-vs-JRE answer.
RUNTIME_BOM_NAMES = ("jdk", "jre")


def docker(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ("docker", *args), capture_output=True, text=True, timeout=120, check=True
        )
    except (subprocess.SubprocessError, OSError):
        return None
    return out.stdout.strip() or None


def human_bytes(raw: str) -> str:
    try:
        size = int(raw)
    except ValueError:
        return raw
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return raw


def main() -> int:
    image = os.environ.get("IMAGE_REF")
    if not image:
        print("IMAGE_REF not set; nothing to describe", file=sys.stderr)
        return 0

    rows: list[tuple[str, str]] = []

    basics = docker(
        "image", "inspect", image,
        "--format", "{{.Size}}\t{{.Os}}/{{.Architecture}}\t{{.Config.User}}",
    )
    if basics:
        size, platform, user = (basics.split("\t") + ["", "", ""])[:3]
        rows.append(("Size", human_bytes(size)))
        rows.append(("Platform", platform or "unknown"))
        rows.append(("Runs as", user or "root (!)"))

    raw_meta = docker(
        "image", "inspect", image,
        "--format", f'{{{{index .Config.Labels "{BUILD_METADATA_LABEL}"}}}}',
    )
    buildpacks: list[str] = []
    if raw_meta:
        try:
            meta = json.loads(raw_meta)
        except json.JSONDecodeError:
            meta = {}
        for entry in meta.get("bom", []):
            if entry.get("name") in RUNTIME_BOM_NAMES:
                version = entry.get("metadata", {}).get("version", "")
                rows.append(("Java runtime", f"**{entry['name'].upper()}** {version}".strip()))
        buildpacks = [
            f"{bp.get('id', '?')} {bp.get('version', '')}".strip()
            for bp in meta.get("buildpacks", [])
        ]

    lines = ["### Image", "", f"`{image}`", ""]
    if rows:
        lines += ["| Property | Value |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in rows]
        lines.append("")
    else:
        lines += ["_Could not inspect the image._", ""]

    if buildpacks:
        lines += ["<details><summary>Buildpacks</summary>", ""]
        lines += [f"- `{bp}`" for bp in buildpacks]
        lines += ["", "</details>", ""]

    rendered = "\n".join(lines)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
