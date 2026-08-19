#!/usr/bin/env python3
"""Print a readable summary of an offline-clone diagnostic report.

Usage: python summarize-diagnostic-report.py <report.json>

Companion to run-live-diagnostic.sh, which produces the report inside the Linux
container where the live section can execute.
"""
from __future__ import annotations

import json
import sys


def main() -> int:
    report = json.load(open(sys.argv[1]))
    print("overall:", report.get("diagnostic_status"))
    for name, section in report["sections"].items():
        execution = section.get("execution", {})
        findings = section.get("findings", [])
        print(f"{name}: complete={execution.get('complete')} findings={len(findings)}")
        for reason in execution.get("incomplete_reasons") or ():
            print("   incomplete:", str(reason)[:240])
        coverage = section.get("coverage") or {}
        if coverage:
            print("   coverage:", json.dumps(coverage, sort_keys=True)[:400])
        for finding in findings[:15]:
            print(
                "   -",
                finding.get("check"),
                "|",
                str(finding.get("subject", ""))[:46],
                "|",
                str(finding.get("message", ""))[:110],
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
