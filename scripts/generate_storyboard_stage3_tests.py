"""Generate evals/storyboard_stage3_tests.json from the existing 35-case storyboard suite, tagged by split.

The cases, fixtures and EXPECTED values are taken unchanged from evals/storyboard_tests.json; the split
(dev/holdout) is read from each brief's path. Only metadata is added.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "evals" / "storyboard_tests.json"
OUTPUT = REPO_ROOT / "evals" / "storyboard_stage3_tests.json"


def main() -> None:
    tests = []
    for case in json.loads(SOURCE.read_text(encoding="utf-8")):
        brief = case["vars"]["STORY_BRIEF_JSON"]
        split = "dev" if "/storyboard/dev/" in brief else "holdout" if "/storyboard/holdout/" in brief else None
        if split is None:
            raise SystemExit(f"cannot determine split for {brief}")
        name = Path(brief).stem
        tests.append(
            {
                "description": f"{split}/{name}",
                "vars": case["vars"],
                "metadata": {"split": split, "case": name, "expected": case["vars"]["EXPECTED"]},
            }
        )
    OUTPUT.write_text(json.dumps(tests, indent=2) + "\n", encoding="utf-8")
    counts = {s: sum(t["metadata"]["split"] == s for t in tests) for s in ("dev", "holdout")}
    print(f"Wrote {OUTPUT} with {len(tests)} cases {counts}")


if __name__ == "__main__":
    main()
