# WU-TOOLS-01-F01-02-R3 Slice 1 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: Slice 1, Doc Native Tools
- Gate: code review
- Implementation artifact: `docs/reviews/wu-tools-01-f01-02-r3-slice1-implementation-codex.md`
- MiMo review: `docs/reviews/wu-tools-01-f01-02-r3-slice1-code-review-mimo.md`
- DS review: `docs/reviews/wu-tools-01-f01-02-r3-slice1-code-review-ds.md`
- Controller verification before adjudication:
  - `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py`: 22 passed
  - `source .venv/bin/activate && pytest tests/tools/test_combined_tools_acceptance.py -k doc`: 1 passed, 7 deselected; edgar deprecation warnings only
  - `source .venv/bin/activate && pyright`: 0 errors
  - `git diff --check`: passed

## Reviewer Conclusions

- MiMo: `pass-with-findings`
- DS: `pass-with-findings`

Both reviewers agree that Slice 1 completes the core Doc native migration: Doc provider no longer depends on the legacy adapter, five Doc tools remain current `ToolDefinition` / async `ToolCallable` definitions, Host cancellation projects to `ToolCancelledOutcome(reason="host_cancelled")`, and the implementation does not modify Web / Fins / adapter deletion scope.

## Accepted Findings For Fix

### S1-CR-01: Path Validation Leaks Existence Outside Allowed Roots

- Source: MiMo finding 001.
- Severity: medium.
- Decision: accepted.
- Evidence: `_project_doc_paths` resolves the candidate path and checks `candidate.exists()` before checking whether the candidate is under `allowed_roots`.
- Required fix: check allowed-root containment before `exists()`. A path outside allowed roots must return `permission_denied` regardless of whether it exists. Add a regression test for an outside, nonexistent path returning `permission_denied`, not `file_not_found`.

### S1-CR-02: Provider Lock Serialization Lacks Direct Test

- Source: MiMo finding 002 and DS residual risk.
- Severity: medium.
- Decision: accepted.
- Evidence: plan requires concurrency equivalence for legacy `SERIAL_PER_PROVIDER`; current tests do not use concurrent Doc callable execution.
- Required fix: add a focused test that invokes two different Doc tool callables from the same provider concurrently and proves their synchronous business bodies do not overlap. The test should avoid relying on sleeps where a deterministic synchronization primitive is practical.

### S1-CR-03: Line Scan Search Loop Lacks Cancellation Checkpoint

- Source: MiMo finding 003 and DS finding 01.
- Severity: medium for plan compliance, low-to-medium runtime impact.
- Decision: accepted.
- Evidence: `_search_via_line_scan` checks cancellation before reading the file but not during the line scan loop.
- Required fix: add cancellation checkpoints inside the line scan loop. Also narrow `cancellation_token` to a required `CancellationToken`, since all production callers pass a token. Add a regression test that cancels during line scanning and verifies `ToolCancelledOutcome(reason="host_cancelled")`.

### S1-CR-04: Markdown Section / Line Count Helpers Have Cancellation Gaps

- Source: MiMo finding 004.
- Severity: low.
- Decision: accepted as a bounded cooperative-cancellation enhancement.
- Evidence: `_extract_markdown_sections` and `_count_file_lines` can traverse large files or large line lists without observing cancellation.
- Required fix: add cooperative cancellation checkpoints in these helper paths without introducing physical cancellation, timeout policy, or Host / Engine changes. A narrow test is sufficient if it covers a representative large Markdown section extraction or line count cancellation path.

## Rejected / Deferred Findings

### S1-CR-05: `_project_doc_paths` Empty `allowed_roots` Branch Is Unreachable In Production

- Source: DS finding 03.
- Decision: rejected for current fix.
- Reason: this defensive branch is harmless, expresses fail-closed behavior for direct helper misuse, and does not conflict with the provider-level empty roots behavior. No code change required.

### S1-CR-06: Processor Search Has No Timeout Protection

- Source: DS residual risk.
- Decision: deferred-with-owner.
- Owner: WU-WAIT-03 / external job and long-running operation cancellation policy, or a future Doc processor performance hardening issue if real evidence appears.
- Reason: Slice 1 is scoped to legacy adapter retirement and cooperative token checks. It must not introduce a new timeout design.

### S1-CR-07: Miscellaneous Signature / Encoding Cleanups

- Source: DS open questions.
- Decision: no current fix except where already covered by S1-CR-03.
- Reason: `_count_file_lines` encoding behavior and `_fallback_single_section` signature are pre-existing behavior / cleanup questions, not correctness findings for this slice.

## Required Fix Gate

AgentCodex should implement S1-CR-01 through S1-CR-04 only, update `docs/reviews/wu-tools-01-f01-02-r3-slice1-fix-codex.md`, and run:

- `source .venv/bin/activate && pytest tests/tools/test_doc_tools_provider.py`
- `source .venv/bin/activate && pytest tests/tools/test_combined_tools_acceptance.py -k doc`
- `source .venv/bin/activate && pyright`
- `git diff --check`
