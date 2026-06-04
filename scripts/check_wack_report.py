from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PASS_MARKERS = {"PASS", "PASSED"}
FAIL_MARKERS = {"FAIL", "FAILED", "ERROR"}


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalized(value: str | None) -> str:
    return (value or "").strip().upper()


def report_passed(report_path: Path) -> tuple[bool, str]:
    if not report_path.exists():
        return False, f"WACK report not found: {report_path}"

    try:
        root = ET.parse(report_path).getroot()
    except ET.ParseError as exc:
        return False, f"WACK report parse error: {exc}"

    root_overall = _normalized(root.attrib.get("OVERALL_RESULT"))
    test_results = [
        _normalized(element.text) for element in root.iter() if _local_name(element.tag) == "RESULT"
    ]
    overall_results = [
        _normalized(element.text)
        for element in root.iter()
        if _local_name(element.tag) == "OverallResult"
    ]
    explicit_results = [
        result for result in [root_overall, *overall_results, *test_results] if result
    ]

    if not explicit_results:
        return False, "WACK report schema unknown: missing explicit result fields"
    if any(result in FAIL_MARKERS for result in explicit_results):
        failed_tests = _failed_test_names(root)
        if failed_tests:
            return False, "WACK report contains failed tests: " + "; ".join(failed_tests[:5])
        return False, "WACK report contains fail/error markers"
    if root_overall and root_overall not in PASS_MARKERS:
        return False, f"WACK report overall result: {root_overall}"
    if overall_results and any(result not in PASS_MARKERS for result in overall_results):
        return False, f"WACK report result: {', '.join(overall_results)}"
    if test_results and any(result not in PASS_MARKERS for result in test_results):
        return False, "WACK report contains non-pass test results"

    for element in root.iter():
        values = [
            _normalized(element.text),
            *(_normalized(value) for value in element.attrib.values()),
        ]
        if any(value in FAIL_MARKERS for value in values):
            return False, "WACK report contains fail/error markers"

    return True, "WACK report PASS"


def _failed_test_names(root: ET.Element) -> list[str]:
    failed: list[str] = []
    for element in root.iter():
        if _local_name(element.tag) != "TEST":
            continue
        result = ""
        for child in element:
            if _local_name(child.tag) == "RESULT":
                result = _normalized(child.text)
                break
        if result in FAIL_MARKERS:
            name = element.attrib.get("NAME") or element.attrib.get("TITLE") or "unnamed test"
            failed.append(name)
    return failed


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: check_wack_report.py <report.xml>", file=sys.stderr)
        return 2

    passed, message = report_passed(Path(argv[1]))
    print(message)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
