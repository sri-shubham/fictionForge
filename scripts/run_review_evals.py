"""Retired: legacy review-contract measurement harness.

This script measured reviewers against the *legacy* review contract
(``ReviewIssue``/``ReviewVerdict``/``parse_review_response`` with the ``path``
key).  That contract was removed in Stage 4 in favour of the shared contract
in ``fictionforge.guardrails.reviewer_contract``.

Reviewer quality evaluation now lives in the Stage 3 promptfoo harness:

    .venv/bin/python scripts/reviewer_stage3.py --help

See ``evals/reviewers/`` for the selected prompts, test cases and fixtures,
and ``scripts/stage4_review_gate.py`` for single-gate shadow reviews of the
integrated Stage 4 pipeline.  ``evals/review/dataset.json`` is kept for
reference.
"""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "run_review_evals.py was retired: the legacy review contract "
        "(ReviewIssue/parse_review_response) was removed in Stage 4.\n"
        "Stage 3 reviewer evaluation lives in scripts/reviewer_stage3.py; "
        "single-gate shadow reviews live in scripts/stage4_review_gate.py.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
