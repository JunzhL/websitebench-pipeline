#!/usr/bin/env python3
"""Print the parts of an offline-clone diagnostic report a human reads first."""

from __future__ import annotations

import json
import pathlib
import sys


def main() -> int:
    report = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(f"diagnostic_status: {report.get('diagnostic_status')}")
    for name, section in (report.get("sections") or {}).items():
        execution = section.get("execution") or {}
        findings = section.get("findings") or []
        print(f"\n[{name}] complete={execution.get('complete')} findings={len(findings)}")
        for reason in execution.get("incomplete_reasons") or []:
            print(f"  incomplete: {reason}")
        print(f"  coverage: {json.dumps(section.get('coverage'), sort_keys=True)}")
        for finding in findings[:15]:
            check = str(finding.get("check"))
            subject = str(finding.get("subject"))[:46]
            message = str(finding.get("message"))[:110]
            print(f"  {check} | {subject} | {message}")
        if len(findings) > 15:
            print(f"  ... {len(findings) - 15} more findings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
