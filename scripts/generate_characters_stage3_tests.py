"""Generate evals/characters_stage3_tests.json (all 30 Character Design fixtures, tagged by split) for the frozen Stage 3 eval."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "evals" / "fixtures" / "characters" / "manifest.json"
OUTPUT = REPO_ROOT / "evals" / "characters_stage3_tests.json"


def main() -> None:
    tests = []
    for case in json.loads(MANIFEST.read_text(encoding="utf-8")):
        test = {
            "description": case["name"],
            "vars": {
                "STORY_BRIEF_JSON": f"file://{case['brief']}",
                "WORLD_JSON": f"file://{case['world']}",
                "EXPECTED": case["expected"],
            },
            "metadata": {"split": case["split"], "case": case["name"], "expected": case["expected"]},
        }
        if case["name"] == "14_prompt_injection_override" and case["split"] == "dev":
            test["assert"] = [
                {"type": "python", "value": "file://characters_stage3_assert.py:injection_resistance", "metric": "injection_resistance"}
            ]
        tests.append(test)
    OUTPUT.write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(tests)} test cases")


if __name__ == "__main__":
    main()
