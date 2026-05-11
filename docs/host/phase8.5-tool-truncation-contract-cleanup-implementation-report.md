# P8.5 Tool Truncation Contract Cleanup Implementation Report

- work gate name: `implementation`
- work-unit name: P8.5 follow-up fix — remove public ToolTruncationInfo contract leakage
- approved plan path: controller handoff in current conversation; no new P8.5 plan/review was created
- assigned scope: remove public `ToolTruncationInfo` / `ToolResultSuccess.truncation`, move LLM-facing truncation hint into ordinary `ToolResultSuccess.value`, keep Engine unaware of Host truncation state
- explicit non-goals: no Gateflow controller actions, no commit, no PR, no public fetch_more/truncation/cursor contract restoration, no dedicated `TOOL_CURSOR_*` / `TOOL_RESULT_TRUNCATED` / `TOOL_FETCH_MORE_*` RunEvent recovery

## Changed Files

- Contracts / Engine: `dayu/contracts/tool_result.py`, `dayu/contracts/__init__.py`, `dayu/engine/__init__.py`, `dayu/engine/agent.py`
- Host runtime / projections: `dayu/host/_tool_result_truncation.py`, `dayu/host/_runtime_truncate_manager.py`, `dayu/host/_run_event_serializer.py`, `dayu/host/_credential_scrub.py`, `dayu/host/_conversation_memory.py`, `dayu/host/_tool_trace_projection.py`
- Tests / smoke scripts: `tests/contracts/*`, `tests/engine/*`, relevant `tests/host/*`, `utils/smoke_*`
- Documentation: `dayu/engine/README.md`, `dayu/host/README.md`, `tests/README.md`, `docs/host/design.md`, `docs/host/migration-plan.md`

## Implementation Decisions

- Deleted `ToolTruncationInfo` from public contracts and package exports.
- Removed `ToolResultSuccess.truncation`; success results now contain only `ok`, `value`, and `meta`.
- Added Host-private `dayu.host._tool_result_truncation` to build and extract ordinary JSON truncation payloads.
- `RuntimeTruncateManager` now injects `truncation.has_more`, `next_action="fetch_more"`, `fetch_more_args`, and optional `ttl_seconds` directly into `ToolResultSuccess.value`.
- Engine no longer imports or branches on truncation; `_project_truncation_for_llm()` was removed and Engine only performs ordinary JSON result projection.
- Serializer now persists ordinary `value` payload only; there is no top-level truncation schema branch.
- Memory and trace parse truncation diagnostics from ordinary value payload. Memory summary strips reusable raw cursor, raw scope token, and `fetch_more_args`, retaining only safe fingerprint / has_more style diagnostics.

## Validation

- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`  
  Result: passed, `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && pytest tests/contracts tests/engine -q`  
  Result: passed, `327 passed`.
- `source .venv/bin/activate && pytest tests/host -q`  
  Result: passed, `376 passed`.
- `source .venv/bin/activate && pytest tests/utils/test_analyze_tool_trace_host.py -q`  
  Result: passed, `17 passed`.
- `rg "ToolTruncationInfo|truncation=" dayu tests`  
  Result: only negative public-surface tests mention `ToolTruncationInfo`; no `truncation=` constructor parameter remains.
- `rg "ToolTruncationInfo" dayu/contracts dayu/engine dayu/host dayu/host/README.md tests/README.md docs/host/design.md docs/host/migration-plan.md`  
  Result: only `docs/host/migration-plan.md` records the fixed residual; no current code/current boundary doc exports or depends on it.

## Docs Decision

- Updated Engine README because `dayu/engine` behavior changed: truncation is now ordinary JSON payload passthrough, not an Engine-specific projection contract.
- Updated Host README and `docs/host/design.md` to describe Host-injected ordinary tool result value hints.
- Updated `tests/README.md` to reflect value-level truncation hints and safe memory ingestion.
- Updated `docs/host/migration-plan.md` with the P8.5 follow-up fixed residual.

## Residual Risks / Uncovered Areas

- No stop condition was hit: Engine did not need to understand a Host-private truncation type, and no public fetch_more/truncation/cursor contract had to be restored.
- Remaining grep hits are intentional: two negative export tests and one migration-plan fixed-residual note.
- This pass did not run non-requested real-provider smoke scripts.

## Stop Condition Status

- Engine private truncation dependency: not present after cleanup.
- Public fetch_more/truncation/cursor contract restoration needed: no.
- Commit / push / PR / closeout: not performed.
