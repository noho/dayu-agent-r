# WU-CLI-SMOKE-01 Final Closeout

## Gate

- Work unit: WU-CLI-SMOKE-01
- Gate: final closeout
- Date: 2026-07-09
- Draft PR: https://github.com/noho/dayu-agent-r/pull/172
- Branch: `phase/host-issues-control`
- Base: `main`
- Issue: none by user decision
- Status: pass

## What Changed

- Fixed `dayu-cli interactive` idle Ctrl+C behavior to match Codex / Claude Code style: first idle Ctrl+C asks for confirmation, second exits.
- Fixed MANUAL-F01 root cause: Host awaiting snapshot digest is now stable and accepted by the entrypoint awaiting path.
- Aligned `dayu-cli prompt` and `dayu-cli interactive` display semantics:
  - `--thinking` / `--no-thinking` are CLI display toggles only.
  - `--detail` / `--no-detail` are available for both prompt and interactive.
  - Both default to `--thinking --detail`.
  - thinking / detail are running-state displays and do not enter final answer, activity, outbox terminal projection, canonical replay, or interactive final transcript.
- Added Host public thinking projection:
  - Engine `REASONING_DELTA`
  - Host `PREVIEW` row / `HostThinkingView`
  - Service `EntrypointThinking` callback
  - CLI stderr renderer
- Corrected context slots, scene tool exposure, FMP-backed ticker context, and tag-only scene tool selection.
- Centralized workspace path handling so `workspace/workspace` is no longer created.
- Fixed Fins awaiting poller / resume behavior for real interactive downloads.
- Hardened interactive cancel / retry behavior for Fins downloads, including SEC/CN/HK cancellation checkpoints and event-loop-safe SEC client reuse.
- Recorded `TOOL_AWAITING` as Host / ToolRuntime governance that is invisible to LLM-facing Conversation Memory.
- Made wait-resolution `TOOL_RESULT_ACCEPTED` carry accepted evidence envelope and raw tool outcome; Conversation Memory now uses the paired request atom and tool result instead of wait governance facts.
- Made Tool Trace hot/cold summaries expose readable request/result material for accepted tool results, including wait-resolution results.
- Made SEC download terminal summaries classify discovered filings into mutually exclusive downloaded / skipped / rejected / failed buckets.
- Fixed public activity projection so canonical `TOOL_CALL_REQUESTED` request atoms no longer emit duplicate "调用工具" lines; only preview tool-call events produce the started activity.
- Recorded full-repository semantic ownership review findings as backlog for the next WU; they were not fixed in WU-CLI-SMOKE-01.
- Updated README, Host / Service / tests README, design truth, tests, and control document where applicable.

## Accepted Commits

- Plan: `c0b79339`
- Slice S1 idle Ctrl+C: `52e4fcd3`
- MANUAL-F01 awaiting fix: `164072b0`
- MANUAL-F01 control record: `78a26006`
- Display semantics implementation: `c1b546ac`
- Display semantics control record: `14442e6f`
- Draft PR record: `23ed37e1`
- PR review fix / accepted PR review: `632c1f34`
- Real-env tool trace / memory follow-up: `aa12dc06`
- Full-repository semantic ownership review record: `f2a9d24f`
- Duplicate tool call activity projection fix: `885faa45`

## Review Artifacts

- Display semantics implementation/fix: `docs/reviews/wu-cli-smoke-01-display-semantics-codex.md`
- Display semantics reviews and re-reviews:
  - `docs/reviews/wu-cli-smoke-01-display-semantics-review-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-review-ds.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-rereview-ds.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-final-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-final-rereview-ds.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-prompt-lifecycle-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-display-semantics-prompt-lifecycle-rereview-ds.md`
- Awaiting / cancel / memory / trace follow-up artifacts:
  - `workspace/tmp/agentcodex-real-env-tool-trace-memory-fix.md`
  - `docs/reviews/wu-cli-smoke-01-tool-evidence-request-memory-controller-adjudication.md`
  - `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-rereview-mimo.md`
  - `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-rereview-ds.md`
  - `docs/reviews/code-review-20260709-113919.md`
  - `docs/reviews/code-review-20260709-115427.md`
  - `docs/reviews/code-review-20260709-121118.md`
- Full-repository semantic ownership backlog artifacts:
  - `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`
  - `docs/reviews/fullrepo-semantic-ownership-review-ds.md`
  - `docs/reviews/fullrepo-semantic-ownership-review-mimo.md`
- PR review and re-review:
  - `docs/reviews/pr-172-review-20260706-210832.md`
  - `docs/reviews/pr-172-review-ds.md`
  - `docs/reviews/pr-172-review-fix-codex.md`
  - `docs/reviews/pr-172-rereview-mimo.md`
  - `docs/reviews/pr-172-rereview-ds.md`

## User Validation

The user re-ran real `dayu-cli interactive --log-level debug --log-file workspace/tmp/wu-cli-smoke-01-manual/interactive.log` after clearing `workspace/.dayu`.

Observed real outputs:

- `下载亚朵财报`: final answer reported `discovered=27`, `downloaded=12`, `rejected=15`, `failed=0`, closing the earlier non-closed count issue.
- `下载Meta财报`: final answer reported `discovered=27`, `downloaded=27`, no skipped / rejected / failed.
- `下载芝商所财报`: final answer reported `discovered=26`, `downloaded=26`, no skipped / rejected / failed.

Controller EventLog / durable checks confirmed:

- ATAT, META, and CME counts are mutually exclusive and closed.
- Wait-resolution `TOOL_RESULT_ACCEPTED` rows contain `accepted_evidence_envelope` and `raw_tool_outcome`.
- Canonical `TOOL_CALL_REQUESTED` request atoms contain `semantic_query_text` and safe argument material for `ticker=ATAT`, `ticker=META`, and `ticker=CME`.
- Conversation Memory contains readable tool / query / result evidence and does not contain `原始工具响应不可用`, `TOOL_AWAITING`, `wait_id`, `poll`, or `runtime`.
- Tool Trace hot/cold summaries expose `arguments_summary_text` and `result_details`, including ATAT `discovered=27, downloaded=12, skipped=0, rejected=15, failed=0`.

The user also identified a final small activity projection issue: duplicate `Activity: started 调用工具：Start Fins Download`. Controller traced it to preview and canonical `TOOL_CALL_REQUESTED` rows both being projected as public activity. Commit `885faa45` fixed this at the Host read API projection boundary without changing Tool Trace, because one business tool call should still correspond to one tool trace.

## Validation

Earlier PR validation:

- `source .venv/bin/activate && pytest tests/cli -q`
  - `225 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime.py tests/host/test_engine_ingest_mapping.py tests/host/test_host_activity_event_projection.py -q`
  - `126 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/host/test_host_activity_event_projection.py -q`
  - `17 passed`
- `source .venv/bin/activate && pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed
- `gh pr checks 172`
  - no checks reported on branch `phase/host-issues-control`

Latest focused validation after the final activity projection fix:

- `pytest tests/host/test_host_activity_event_projection.py`
  - `18 passed`
- `pytest tests/cli/test_interactive_run_view.py tests/cli/test_activity_renderer.py`
  - `17 passed`
- `pyright dayu/host/read_api.py tests/host/test_host_activity_event_projection.py`
  - `0 errors`
- `pyright`
  - `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - passed

## Residual Risks

| ID | Status | Owner / Destination | Notes |
|---|---|---|---|
| WU-CLI-SMOKE-01-R1 | deferred-with-owner | WU-RET-03 / GitHub Issue #78 under #43 retention lane | `REASONING_DELTA` thinking text is stored as a `PREVIEW` row for live watcher projection; retention / purge governance should classify PREVIEW cleanup policy. |
| WU-CLI-SMOKE-01-R2 | deferred-with-owner | Future CLI UI enhancement / user decision | CLI thinking remains a single-line 160-character running-state display. |
| CN/HK-DOC-CONVERT-R1 | deferred-with-owner | Future Fins hard-timeout WU / user decision | Docling synchronous third-party conversion cannot be hard-interrupted while running inside `asyncio.to_thread(...)`; future hard-timeout requirements should move conversion to process/subprocess isolation. |
| UPLOAD-EXPOSURE-R1 | deferred-with-owner | Future user decision | Upload tool exposure remains deferred to separate user decision. |
| SEMANTIC-OWNERSHIP-R1 | deferred-with-owner | Next WU semantic ownership backlog | Full-repository semantic ownership review findings are recorded and accepted as backlog, but were intentionally not fixed in WU-CLI-SMOKE-01. |

## Next Work Unit

After PR #172 is merged, return to the target base branch and start the next WU from the semantic ownership backlog recorded in `docs/reviews/fullrepo-semantic-ownership-controller-adjudication.md`.

Initial recommended order:

1. P0-A: Engine runner finish reason and usage authority.
2. P0-B: Fins preprocess/upload typed result contracts.
3. P1-A: Host accepted evidence/query/status typed projection contract.
4. P1-B: Host event type and cancellation durable contract.
5. P1-C: LLM-facing governance leakage cleanup.
6. P2-A: CLI/service boundary consistency.
7. P2-B: Memory/test contract hardening.
8. P2-C: Config fallback prompt source of truth.

The next WU should include multiple deepreview rounds before final closeout.

## Closeout

Final closeout passes. Draft PR #172 is open and remains draft. No issue closeout comment is needed because this work unit intentionally has no GitHub Issue owner. After PR #172 is merged, pull latest `main` and resume phaseflow from `docs/host/issues-implementation-control.md` next entry point to start the semantic ownership backlog WU.
