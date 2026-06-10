# WU-TOOLS-01-F03 Slice 1 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F03 Web CI Smoke Generation`
- Gate: Slice 1 code review adjudication
- Implementation artifact: `docs/reviews/wu-tools-01-f03-implementation-slice1-codex.md`
- Review artifacts:
  - `docs/reviews/wu-tools-01-f03-code-review-slice1-mimo.md`
  - `docs/reviews/wu-tools-01-f03-code-review-slice1-ds.md`
- Date: 2026-06-10

## Decision Summary

Slice 1 implementation is directionally accepted, but must pass a small fix gate before re-review.

The required fix is DS Finding 1: `_DIAGNOSTIC_SCHEMA_REVISION` is a newly introduced diagnostic revision marker and should start at `1`, not `2`. Starting at `2` implies an undocumented revision 1 and weakens the schema validation signal that Slice 2 will consume.

## Finding Adjudication

| Finding | Source | Decision | Required action |
|---|---|---|---|
| `_DIAGNOSTIC_SCHEMA_REVISION = 2` has no revision 1 | DS Finding 1 | accepted | Change `_DIAGNOSTIC_SCHEMA_REVISION` to `1` and update deterministic tests/assertions. |
| `_DOCLING_DEPENDENCY_EXCEPTION_TYPES` string matching does not catch subclasses | DS Finding 2 | deferred-with-owner | Defer unless later Slice 2/3 evidence shows real Docling dependency exceptions are missed. Current narrow wrapper path already handles the expected concrete exceptions. |
| `_observed_failing_path_from_payload` may return comparison bucket as failing path | MiMo Finding 1 / DS Finding 3 | accepted-low | Add a clarifying comment if cheap, or leave for Slice 2 consumer handling. Do not block Slice 1 acceptance. |
| `_DoclingInvocationEvidence` dataclass docstring convention | MiMo Finding 2 | accepted-low | Fix only if cheap; not blocking. |
| `schema_version` and `diagnostic_schema_version` share the same value | DS Finding 4 | accepted-low | Add a short comment near schema constants if cheap, explaining legacy artifact schema vs smoke validation marker. |
| Other info findings | MiMo Findings 3/4/6 | accepted | No required fix. |

## Required Next Gate

Dispatch AgentCodex for fix gate only.

Expected result:

- update `utils/diagnose_web_access.py`;
- update `tests/tools/web/test_diagnose_web_access.py`;
- optionally add comments for low-risk accepted-low items if doing so is localized;
- write `docs/reviews/wu-tools-01-f03-fix-slice1-codex.md`;
- rerun focused pytest, full pyright, and `git diff --check`;
- do not commit, push, or create PR.

