# Gateflow Plan Fix: engine-cancel-commit-boundary-and-tool-timeout

## Work Gate

- **Gate**: plan fix
- **Work unit**: `engine-cancel-commit-boundary-and-tool-timeout`
- **Source review artifact**: `docs/reviews/gateflow-plan-review-engine-cancel-commit-boundary-20260511.md`
- **Fixed plan artifact**: `docs/reviews/gateflow-plan-engine-cancel-commit-boundary-20260511.md`

## Controller Decisions

All four plan review findings were accepted.

## Fix Status

### 001: Slice 3 ToolMessage 注入 ownership 错误

- **Status**: fixed
- **Plan changes**:
  - Clarified `_execute_tool_batch` does not own `messages` and must not inject ToolMessages.
  - Moved the implementation instruction to outer `run_messages`: after `_last_tool_batch_result` is read, call `_inject_tool_messages(...)`, then observe cancellation.
  - Preserved `_execute_tool_batch` ownership as “execute tools, emit tool events, return accepted records.”

### 002: runtime timeout helper bounded handshake 语义未收敛

- **Status**: fixed
- **Plan changes**:
  - Added explicit `WaitTimedOut` contract to the plan.
  - Chose no-background-task ownership: helper cancels target and waits for target task completion.
  - Added the required ToolExecutor cooperation contract: `execute` must not swallow `asyncio.CancelledError` and run forever after Engine timeout/cancellation.
  - Added docstring and test expectations for cancellation cooperation.

### 003: late cancel ToolMessage 注入测试诱导私有 monkeypatch

- **Status**: fixed
- **Plan changes**:
  - Removed monkeypatch / private `_last_tool_batch_result` inspection from late-cancel acceptance criteria.
  - Late-cancel tests now assert stable observable contract: `TOOL_RESULT_ACCEPTED` emitted, terminal `RUN_CANCELLED`, no next Runner call.
  - ToolMessage projection content remains covered by existing normal completed/failed next-Runner tests; plan allows adding missing normal-path failed projection assertions if needed.
  - Re-review found one stale residual-risk bullet that still suggested private monkeypatch / `_last_tool_batch_result`; removed it from the plan.

### 004: docs sync 遗漏 AgentPolicy 与早期取消旧口径

- **Status**: fixed
- **Plan changes**:
  - Slice 4 now requires updating `AgentPolicy.tool_execution_timeout_seconds` in design and README contract sections.
  - Slice 4 now requires cleaning or explicitly qualifying old cancellation statements in `docs/engine/design.md`, including final-answer late cancel wording.
  - Added completion checks for old phrases such as “取消优先于挂起、最终回答” and for timeout policy discoverability.

## Validation

- `git diff --check -- docs/reviews/gateflow-plan-engine-cancel-commit-boundary-20260511.md docs/reviews/gateflow-plan-fix-engine-cancel-commit-boundary-20260511.md`: passed.

No pytest or pyright was run for this plan-only fix.

## Residual Risks

- None unresolved at plan level. The timeout helper still has an explicit implementation residual risk: non-cooperative ToolExecutor implementations are protocol violations and cannot be made safe by Engine alone.

## Artifact Path

- `docs/reviews/gateflow-plan-fix-engine-cancel-commit-boundary-20260511.md`
