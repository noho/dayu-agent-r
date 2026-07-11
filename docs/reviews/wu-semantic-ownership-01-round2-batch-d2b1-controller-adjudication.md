# WU-SEMANTIC-OWNERSHIP-01 Round2 Batch D2b1 Controller Adjudication

## Scope

- Batch: Round2 Batch D2b1
- Accepted finding: `144159-05`
- Owner boundary: Host accepted tool outcome canonical atom / wait resolution envelope / RunInput resume consumer
- Baseline: D2a accepted commit `4f4d23db`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b1-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round2-batch-d2b1-code-review-ds.md`

## Decision

`144159-05` is closed.

## Owner Correction

- Added `dayu.host.accepted_tool_outcome` as the single Host owner for completed / failed / cancelled accepted tool outcome canonical JSON atom, digest, and inline byte estimation.
- Ordinary ToolRuntime accepted outcome paths now use this owner for `raw_tool_outcome`, `outcome_digest`, and inline-size logic.
- Wait resolution payload planning now uses the same owner for completed / failed / cancelled outcomes. Wait-specific `payload_ref`, `payload_digest`, and provider/wait metadata remain outside the accepted outcome atom.
- `resolve_wait_outcome_json` now records the accepted atom under `tool_outcome`, making digest material distinguish the wait envelope from the tool business outcome atom.
- RunInput resume consumption reads canonical `raw_tool_outcome` and no longer parses the old wait-only nested `result.result` shape.

## Review Result

- AgentMiMo: pass, no material findings.
- AgentDS: pass, no material findings.
- Both reviewers verified:
  - ordinary and wait producers share identical atom/digest;
  - wait envelope metadata does not reshape the atom;
  - completed / failed / cancelled all use the shared codec coherently;
  - RunInput has no old-shape fallback;
  - tests assert owner-level behavior.

## Controller Validation

- `source .venv/bin/activate && pytest -q tests/host/test_accepted_tool_outcome_codec.py tests/host/test_toolruntime_executor.py tests/host/test_resolve_wait_command.py tests/host/test_run_input_builder.py`
  - Result: `179 passed`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: pass.
- Source scan:
  - no `resolve_wait_completed_result_json`, `resolve_wait_failed_result_json`, `resolve_wait_cancelled_result_json`, `_tool_cancelled_json`, `_tool_success_json`, or `_tool_failure_json` residuals;
  - no wait-only `result.result` resume consumer residual.

## README Decision

No README update required. D2b1 changes Host internal accepted outcome codec ownership and test coverage, but do not change Host public API, developer manual responsibilities, test directory hierarchy, test command policy, or user-visible workflow.

## Residual Risk

- Full pytest was not run; affected Host tests, pyright, diff check, and source scans passed.
- Digest envelope shape changed from wait-local `result` to `tool_outcome`. This is intentional under the project rule to treat schema changes as fresh schema unless compatibility is explicitly requested.
- D2b2 remains open for compaction evidence kind, memory projection, and reactive compact budget findings.

## Stop Status

D2b1 is accepted with no fix gate.
