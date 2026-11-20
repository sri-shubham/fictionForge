"""Generate the Promptfoo world-evaluation test list from fixtures."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES_DIR = REPO_ROOT / "evals" / "fixtures" / "world"
MANIFEST = FIXTURES_DIR / "manifest.json"
OUTPUT = REPO_ROOT / "evals" / "world_tests.json"


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    tests = []
    for case in manifest:
        rel = case["path"]
        tests.append(
            {
                "vars": {
                    "STORY_BRIEF_JSON": f"file://{rel.removeprefix('evals/')}",
                    "EXPECTED": case["expected"],
                },
                "options": {
                    "suffix": f" {case['name']}",
                },
            }
        )
    OUTPUT.write_text(
        json.dumps(tests, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT} with {len(tests)} test cases")


if __name__ == "__main__":
    main()
