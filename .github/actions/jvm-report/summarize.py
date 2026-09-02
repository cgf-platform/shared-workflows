#!/usr/bin/env python3
"""Render JUnit and JaCoCo results into a GitHub step summary.

Replaces a pair of embedded sed/awk pipelines. Two reasons this is a file and
not a `run:` block: XML is parsed with a real parser rather than line-matched,
and the JaCoCo column indices are named constants instead of positional magic.

Reads nothing but the working tree; writes only to $GITHUB_STEP_SUMMARY.
Never fails the build -- a reporting problem must not mask, or manufacture, a
test result.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

# JaCoCo CSV columns. The previous awk summed INSTRUCTION_{MISSED,COVERED} and
# labelled the result "Lines", which contradicted the `counter = "LINE"` gate in
# every build file. Naming them stops that recurring.
COL_BRANCH_MISSED, COL_BRANCH_COVERED = 5, 6
COL_LINE_MISSED, COL_LINE_COVERED = 7, 8


@dataclass
class Totals:
    tests: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0

    @property
    def passed(self) -> int:
        return self.tests - self.failures - self.errors - self.skipped

    @property
    def ok(self) -> bool:
        return self.failures == 0 and self.errors == 0


def collect_junit(root: Path) -> tuple[Totals, list[str]]:
    totals, failed_cases = Totals(), []
    for report in root.glob("**/build/test-results/**/TEST-*.xml"):
        try:
            suite = ET.parse(report).getroot()
        except ET.ParseError:
            continue  # a truncated report is not a reason to fail reporting
        totals.tests += int(suite.get("tests", 0))
        totals.failures += int(suite.get("failures", 0))
        totals.errors += int(suite.get("errors", 0))
        totals.skipped += int(suite.get("skipped", 0))
        for case in suite.iter("testcase"):
            if case.find("failure") is not None or case.find("error") is not None:
                failed_cases.append(f"{case.get('classname', '?')}.{case.get('name', '?')}")
    return totals, failed_cases


def collect_coverage(root: Path) -> tuple[float, float] | None:
    """Return (line %, branch %) from the first JaCoCo CSV found, if any."""
    for csv in root.glob("**/build/reports/jacoco/**/*.csv"):
        line_missed = line_covered = branch_missed = branch_covered = 0
        with csv.open() as fh:
            next(fh, None)  # header
            for row in fh:
                cells = row.rstrip("\n").split(",")
                if len(cells) <= COL_LINE_COVERED:
                    continue
                try:
                    branch_missed += int(cells[COL_BRANCH_MISSED])
                    branch_covered += int(cells[COL_BRANCH_COVERED])
                    line_missed += int(cells[COL_LINE_MISSED])
                    line_covered += int(cells[COL_LINE_COVERED])
                except ValueError:
                    continue
        lines = line_missed + line_covered
        branches = branch_missed + branch_covered
        return (
            line_covered / lines * 100 if lines else 0.0,
            branch_covered / branches * 100 if branches else 0.0,
        )
    return None


def main() -> int:
    service = os.environ.get("SERVICE_NAME", "service")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    root = Path.cwd()

    totals, failed_cases = collect_junit(root)
    coverage = collect_coverage(root)

    out: list[str] = [f"## {service}", ""]

    if totals.tests == 0:
        out.append("> No test results found. If this service has tests, the build "
                   "failed before they ran.")
    else:
        verdict = "passed" if totals.ok else "failed"
        out += [
            f"**Tests {verdict}** — {totals.passed} passed, {totals.failures} failed, "
            f"{totals.errors} errored, {totals.skipped} skipped, {totals.tests} total.",
            "",
        ]

    if coverage:
        line_pct, branch_pct = coverage
        out += [
            "| Metric | Covered |",
            "|---|---:|",
            f"| Lines | {line_pct:.1f}% |",
            f"| Branches | {branch_pct:.1f}% |",
            "",
        ]
    else:
        out += ["_No JaCoCo CSV report. Enable `csv.required` in the build to see "
                "coverage here._", ""]

    if failed_cases:
        shown = failed_cases[:20]
        out += ["<details><summary>Failed tests</summary>", ""]
        out += [f"- `{case}`" for case in shown]
        if len(failed_cases) > len(shown):
            out.append(f"- …and {len(failed_cases) - len(shown)} more")
        out += ["", "</details>", ""]

    rendered = "\n".join(out)
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
