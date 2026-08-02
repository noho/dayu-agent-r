# Controller Adjudication — S7/F07 Code Re-Review

## Inputs

- Entry HEAD: `b8f87e3b`
- Fix artifact: `docs/reviews/wu-cli-conformance-f01-f07-s7-code-review-fix-codex.md`
- Independent re-reviews:
  - `docs/reviews/wu-cli-conformance-f01-f07-s7-code-rereview-mimo.md`
  - `docs/reviews/wu-cli-conformance-f01-f07-s7-code-rereview-ds.md`

## Independent controller adjudication

| Finding | Final status | Controller evidence |
|---|---|---|
| C-001 duplicate-key/repair-feedback secret leak | `closed` | `_strict_object_pairs` still rejects before JSON overwrite; duplicate-key reports now use stable path `$` rather than echoing the raw key. `_single_parser_issue_report` sanitizes parser path/message, while `_bounded_issue_message` independently sanitizes and bounds path/message/source labels. `build_compact_repair_feedback_v2` reduces issue count and, for a single oversized issue, removes labels until serialized feedback is at most 8192 characters. Malicious API-key/token/Bearer/password tests prove the report, feedback, and rendered repair prompt contain no probe secret. |
| C-002 policy-cap documentation mismatch | `closed` | Design and implementation artifact now describe the actual `MemoryProjectionPolicy`: session-summary char cap plus per-section item-count and aggregate-size caps for facts, anchors, intents, and references. They explicitly exclude diagnostics from Memory policy caps. Production policy and validator were not expanded. |
| M-R1 / DS-1 defensive owner-test gap | `closed` | Fresh-v2 tests cover cancellation after attempt-one failure and before attempt-two prepare, accepted-result missing manifest/response identity fail-closed guards, later reactive pass failure with no accepted/partial truth, and secret-safe semantic repair. Existing multi-pass root duplicate tests continue to prove whole-pass rerouting. No v1 fake or compatibility reader was restored. |
| Previously rejected/closed findings | `remain closed` | The fix did not change `intent_type`/`reason`, answer-anchor shape, material enums, exception types, single-attempt convenience API, compatibility policy, or utils migration boundary. No new evidence revives those findings. |
| Fix-introduced findings | `none` | Both independent reviewers report none. Controller additionally inspected single-issue/many-label total-cap behavior, operation result guards, and later-pass isolation and found no unowned path or downstream compensation. |

## Verification accepted

- Focused owner tests: `43 passed`.
- Accepted-plan S7 matrix: `711 passed, 1 skipped`; skip is the existing real-provider environment gate.
- Full repository pyright: `0 errors, 0 warnings, 0 informations`.
- Ruff on changed Python files: pass.
- Modified production file coverage: each `82%–93%`, aggregate `87%`.
- Active fresh-v2 old-symbol scan: zero; reactive multi-pass owner/consumer/tests remain present.
- `python -m json.tool` for both registries: pass.
- `git diff --check`: pass; index empty before accepted-slice staging.
- Frozen digests remain:
  - oracle: `f9972d943ac8ae8d79ebbe7114c1305b7af2933729575d1407fcb6d4d05b07f4`
  - scenarios: `7f283b039dc02ce686bb134c748e5c98039af2029eb090dbdaf6dcf4fe5e8cef`

## Gate decision

S7/F07 code re-review is `PASS`. The S7 atomic closure may be staged as one exact accepted-slice commit. No README, frozen registry, old evidence, Engine production, CLI/Service production, branch, push, or PR-state operation belongs in that commit.
