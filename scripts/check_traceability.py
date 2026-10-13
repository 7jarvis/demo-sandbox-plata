"""Keeps test cases and automated tests linked in both directions.

Fails when:
- a test is tagged with @case("TC-...") that has no anchor in docs/test-cases;
- a test case names an automated test that does not exist;
- a test case without automation does not say why ("Автотест: нет — <reason>").

Run: python scripts/check_traceability.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "docs" / "test-cases"
TESTS = ROOT / "tests"

CASE_TAG = re.compile(r'case\("(TC-[A-Z]+-\d+)"\)')
ANCHOR = re.compile(r'<a id="(tc-[a-z]+-\d+)"></a>')
AUTOTEST_LINE = re.compile(r"^\*\*Автотесты?:\*\*\s*(.*)$")


def main() -> int:
    errors: list[str] = []

    tagged = {m for p in TESTS.rglob("*.py") for m in CASE_TAG.findall(p.read_text(encoding="utf-8"))}
    documented: set[str] = set()

    for doc in sorted(CASES.glob("*.md")):
        text = doc.read_text(encoding="utf-8")
        documented |= {a.upper() for a in ANCHOR.findall(text)}
        for line in text.splitlines():
            m = AUTOTEST_LINE.match(line)
            if not m:
                continue
            value = m.group(1)
            if value.startswith("нет"):
                if "—" not in value:
                    errors.append(f"{doc.name}: manual case without a reason: {line}")
                continue
            base: Path | None = None
            for ref in re.findall(r"`([^`]+)`", value):
                if "::" in ref:
                    path, _, rest = ref.partition("::")
                    base = ROOT / path
                    names = rest.split("::")
                else:
                    names = [ref]
                if base is None or not base.exists():
                    errors.append(f"{doc.name}: test file not found for {ref}")
                    continue
                source = base.read_text(encoding="utf-8")
                for name in names:
                    if not re.search(rf"(def|class) {re.escape(name)}\b", source):
                        errors.append(f"{doc.name}: {base.relative_to(ROOT)} has no {name}")

    for case_id in sorted(tagged - documented):
        errors.append(f"tests reference {case_id}, but docs/test-cases has no such case")

    manual = sorted(documented - tagged)
    print(f"{len(documented)} test cases, {len(tagged)} automated, manual: {', '.join(manual) or 'none'}")
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
