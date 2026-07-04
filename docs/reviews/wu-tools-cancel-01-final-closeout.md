# WU-TOOLS-CANCEL-01 Final Closeout

## Scope

- Work unit: WU-TOOLS-CANCEL-01
- Umbrella issue: #87
- Draft PR: https://github.com/noho/dayu-agent-r/pull/170
- Branch: `phase/wu-tools-cancel-01`
- Accepted S2 aggregate commit: `093f1c22`
- Accepted PR review commit: `10f6ac93`

## What Changed

- Added typed tool execution capability on `ToolDefinition.execution`, with stable discovery digest projection.
- Wired Host ToolRuntime production default to declaration-backed execution capsule selection instead of tool-name branching.
- Added process-backed execution for Doc blocking tools.
- Added process-backed execution for Fins read tools while preserving Fins download / preprocess / upload as awaiting `EXTERNAL_JOB` tools.
- Added process-backed execution for Web `search_web` and `fetch_web_page`.
- Preserved Host-owned cancel / timeout governance: cancel and timeout return governed outcomes, child process late results cannot become accepted tool results, and child envelopes cannot forge Host-governed statuses.
- Kept `tool_execution_timeout_seconds` as the single tool-call deadline truth; interrupt cleanup is bounded cleanup, not a second tool timeout or an extension of the original deadline.

## What Was Verified

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/tools/test_doc_tools_provider.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/web/test_web_tools_provider.py -q`
  - Result: `219 passed`, with 3 existing upstream `edgar` deprecation warnings.
- `source .venv/bin/activate && pytest tests/contracts tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q`
  - Result: `92 passed`.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed with no output.
- `gh pr checks 170`
  - Result: no checks reported on branch `phase/wu-tools-cancel-01`.

## Review Status

- S2A1 contract / declaration / digest: implemented, reviewed, fixed, re-reviewed, and accepted.
- S2A2 Host factory wiring: implemented, reviewed, fixed, re-reviewed, and accepted.
- S2B Doc process-backed: implemented, reviewed, fixed, re-reviewed, and accepted.
- S2C Fins read process-backed: implemented, reviewed, fixed, re-reviewed, and accepted.
- S2D Web sync process-backed: implemented, reviewed, and accepted.
- S2E aggregate validation: passed.
- S2 aggregate deepreview:
  - AgentMiMo: PASS.
  - AgentDS: PASS.
  - Controller adjudication: PASS, with non-blocking hardening risks accepted.
- PR #170 review:
  - AgentMiMo initial review: PASS.
  - AgentDS initial review: implementation PASS, PR body NEEDS_FIX.
  - AgentCodex PR body fix: completed.
  - AgentMiMo targeted re-review: PASS.
  - AgentDS targeted re-review: PASS.
  - Controller adjudication: PASS.

## #87 Closeout Link

PR #170 body uses `Closes #87`, so merging the draft PR is expected to close issue #87 automatically.

The PR body explicitly records the closeout chain:

- WU-WAIT-03 / #92 completed WAITING external job cancel / revoke / abandon.
- WU-LIFE-03 / #91 completed Host active cancel closeout.
- WU-LIFE-04 / #168 fixed the `tool_execution_timeout_seconds` boundary.
- WU-TOOLS-CANCEL-01 completes the remaining tool/provider interrupt boundary.

No external issue closeout comment was published in this gate because the control document requires explicit authorization before external closeout comments, direct issue close, marking PR ready, merge, reviewer requests, or branch deletion.

## Residual Risk Reconciliation

No blocking residual risk remains for WU-TOOLS-CANCEL-01.

Accepted non-blocking follow-up hardening:

- Process envelope structured hints are still folded into message text.
- Web process-backed execution has per-call cold-start cost.
- Playwright nested process cleanup lacks real browser smoke / stress coverage.
- Fins real XBRL spawned-child fixture breadth is limited.
- Process envelope constants are not yet single-sourced across Host / Doc / Fins / Web.
- Process capsule terminate / kill grace values may need production tuning.
- GitHub reports no CI checks for this branch; local validation evidence is recorded above.

## Next Entry Point

WU-TOOLS-CANCEL-01 is at `final-closeout-pass`. PR #170 remains draft/open for maintainer review.

Do not mark PR #170 ready, merge it, close #87 directly, request reviewers, publish external closeout comments, or delete the branch without explicit authorization.

After PR #170 is merged, pull the latest `main` and resume phaseflow from `docs/host/issues-implementation-control.md`. The default next work unit is WU-WAIT-04 production-grade awaiting end-to-end smoke, which can consume the completed #87 immediate-interrupt closeout path.
