# Stage 4 contract migration: legacy review contract -> shared reviewer contract

The Stage 3 reviewer evaluations were judged against
`fictionforge.guardrails.reviewer_contract`; the pre-Stage-4 workflow gates
used a separate, older contract embedded in `guardrails/review.py`.  Stage 4
deleted the local contract entirely.  There is exactly one contract now.

## Removed symbols (no longer exist anywhere in src/)

| Removed | Replaced by |
|---|---|
| `ReviewIssue` | `ReviewerIssue` (`reviewer_contract`) |
| `ReviewVerdict` | `ReviewerVerdict` |
| `parse_review_response` | `parse_reviewer_response` |
| `ReviewParseError` | `ReviewerContractError` |
| `locate_path`, `evidence_grounded` | `ground_issue` (strict path resolution + verbatim evidence) |
| `POLICY_PUNCH_OUT_CODES`, local `BLOCKING_SEVERITIES` | `POLICY_CODES`, `BLOCKING_SEVERITIES` from the contract |
| local `_SELF_APPROVAL_PATTERNS` | contract `_AUTHORITY_CLAIMS` validator |
| `Decision` | `ReviewDecision` (adds `reviewer_verdict`, `punch_out_confirmed`, `notes`) |

## Field mapping (issue objects)

| Legacy | Shared contract |
|---|---|
| `path` (`$.a[0]`, nullable) | `artifact_path` (required `DocPath`, optionally `doc::` prefixed: `brief`/`world`/`characters`/`storyboard`) |
| — | `reference_path` (nullable `DocPath`) |
| `code`, `severity`, `evidence`, `explanation`, `suggested_correction` | same names, same roles (strict lengths/patterns) |
| gate-record extras `path_resolves`, `evidence_grounded` | `grounded`, `grounding_reasons`, `in_taxonomy` |

## Behaviour changes

* **Bare JSON only.**  A single Markdown code fence used to be accepted;
  it is now rejected (`ReviewerContractError`).  So are duplicate keys,
  non-finite numbers, and any unknown/extra keys.
* **Stricter verdict consistency.**  `REVISE` must carry a blocking issue
  and may not carry a `POLICY_*` code; `PUNCH_OUT` requires a critical
  `POLICY_*` issue (previously any blocking issue allowed it).
* **Invalid responses are never re-asked.**  Previously a malformed
  response consumed `review.max_attempts` like a timeout; now it fails
  closed immediately.  Only `REVIEWER_TIMEOUT` / `REVIEWER_PROVIDER_ERROR`
  retry (bounded by `review.max_attempts`, fresh prompt + nonce per attempt).
* **Evidence grounding is strict.**  The old `locate_path`/`evidence_grounded`
  helpers were loose; `ground_issue` requires every `||`-separated evidence
  fragment (>= 8 chars) to appear verbatim (normalized) in the documents and
  under the cited paths.  Ungrounded findings are recorded, never silently
  dropped.
* **PUNCH_OUT needs trusted confirmation.**  Previously any critical
  allow-listed code was enough; now the policy issue's evidence must also be
  grounded *and* corroborated (for every policy code) by the deterministic
  injection scan or punch-out phrase scan, else the verdict downgrades to
  REVISE.
* **Prompts switched to the Stage 3-selected files**
  (`prompts/reviewers/{world,characters,storyboard}.md`; context/artifact
  block titles match the Stage 3 renderer exactly, incl. `doc::` namespaces).
  The legacy `*_reviewer.md` files remain on disk but are unreferenced.
* **Gate record schema 2.0.0**: `review_mode`,
  `adversarial_guardrails_enforced`, `prompt_version`,
  `reviewer.reviewed_artifact_sha256`, `policy.punch_out_confirmed`,
  `repeated_findings`, `false_positive_candidates`, `label_comparison`,
  `shadow.enforced_equivalent_decision`; approvals also carry `enforcement`,
  `reviewer_verdict`, `reviewer_prompt_sha256` and require a matching
  `review_mode` keeper.
