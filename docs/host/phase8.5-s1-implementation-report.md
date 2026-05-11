# P8.5 Slice 1 Implementation Report

## Work Gate

- work gate: implementation
- work-unit: P8.5 Slice 1 — Generic Tool-Calling EventLog + RuntimeTruncateManager
- approved plan: `docs/host/phase8.5-plan.md`
- implementation agent: Dayu Host P8.5 Slice 1 implementation agent

## Scope Implemented

本次只实施 Slice 1。核心动机成立：旧实现把截断、cursor 与 fetch_more 补读建模为 Host public contract
与专用 EventLog fact，使 Engine-visible tool calling 与 Host 私有运行时治理边界混在一起。Slice 1 的 root
cause 是边界错误，而不是单个事件名或 serializer 映射错误，因此本次按计划收缩 public surface，并把
补读状态迁移到 Host 私有 manager。

已完成：

- EventLog 只保留普通 `TOOL_CALL_REQUESTED` / `TOOL_RESULT_ACCEPTED` 工具事实；删除截断、cursor、
  fetch_more 专用 RunEvent 类型、data class、union 成员、Host package exports 与 serializer mapping。
- 删除 Host public cursor / fetch_more contract；内部需要的 cursor handle 由 Host 私有
  `RuntimeTruncateManager` 持有。
- 新增 Host 私有 `RuntimeTruncateManager`，负责 cursor map、TTL、scope / binding 校验、limit clamp、
  chunk building、single-use consume 与 next cursor issue。
- 新增 Host 私有 framework `fetch_more` 工具定义，callable 通过闭包调用 manager，返回普通
  `ToolCompletedOutcome` / `ToolFailedOutcome`。
- `HostToolRuntime` 收敛为普通 dispatch + 可选截断，不再追加截断 / cursor / fetch_more 专用 RunEvent。
- Host runtime assembly 自动把私有 `fetch_more` schema 投影到 Engine-visible schemas；调用方仍只传业务
  schema，`RunOptions` 不被 in-place 污染，Engine 不接收 `ToolDefinition`、callable、manager 或 cursor type。
- `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 记录 enhanced schemas，保持 trace 与 Engine 实际输入同源。
- EventLog / trace 保留普通 payload，只 scrub 显式 API key / credential；cursor、scope token、工具参数和
  普通工具结果不是 scrub 触发条件。
- durable `HostToolRuntime.execute_tool_call()` 在真实执行入口先解析 `ToolRuntimeOwnerScope` 并调用
  owner-active verification；校验发生在业务 executor、framework `fetch_more` 和
  `RuntimeTruncateManager.apply_truncation()` / `fetch_more()` mutation 之前。
- Conversation Memory / RunInput 按 ingestion policy 只渲染不可复用摘要，不写 raw cursor、raw scope token
  或可复用 `truncation.fetch_more_args`。

## Review Fix Addendum

本次 fix agent 只处理 Slice 1 code review 与 OLD/NEW review findings：

- Finding 01：新增 Host 私有 credential-only scrub helper，Engine→Host 翻译、RunEvent serializer 与
  ToolTrace projection 共用同一规则；`API_KEY` / `api_key` / `Authorization` / password / client secret 等明确
  凭证被替换为 `***`，cursor、`scope_token` 与普通 `token` 保留。
- Finding 02 / OLD-NEW Finding 01：扩展 ToolRuntime appender port，`AttemptScopedRunEventAppender` 在短事务内执行
  `verify_owner`；durable `ToolRuntimeToolExecutor.execute()` / `HostToolRuntime.execute_tool_call()` 无
  `ToolRuntimeOwnerScope` 时 fail fast，且测试覆盖业务工具截断和 framework `fetch_more` 真实路径。
- Finding 03：Slice 1 validation command 已改为当前真实存在的
  `tests/contracts/test_tool_result_envelope.py`。

未实施：

- Slice 2+ 的 trace analyzer 语义重写、raw side store、ToolRegistry / governance、远程 / 多进程补读均未实施。
- 未创建旧 cursor / fetch_more EventLog rows compatibility reader；本 slice 按全新 schema 起库处理。
- 未 commit、未开 PR、未做 Gateflow closeout。

## Changed Files

Production / contracts:

- `dayu/contracts/__init__.py`
- `dayu/contracts/tool_declaration.py`
- `dayu/contracts/tool_result.py`
- `dayu/host/__init__.py`
- `dayu/host/contracts.py`
- `dayu/host/_credential_scrub.py`
- `dayu/host/_run_event_serializer.py`
- `dayu/host/_tool_runtime.py`
- `dayu/host/_runtime_truncate_manager.py`
- `dayu/host/_framework_tools.py`
- `dayu/host/_engine_tool_schema_provider.py`
- `dayu/host/_worker.py`
- `dayu/host/_run_harness.py`
- `dayu/host/_durable_harness.py`
- `dayu/host/_conversation_memory.py`
- `dayu/host/_event_translation.py`
- `dayu/host/_tool_trace_projection.py`
- `dayu/host/_attempt_supervisor.py`

Tests / smoke / docs:

- `tests/contracts/test_package_exports.py`
- `tests/contracts/test_tool_declaration.py`
- `tests/host/test_host_public_api_surface.py`
- `tests/host/test_phase1_public_boundary.py`
- `tests/host/test_phase2_tool_runtime_boundary.py`
- `tests/host/test_phase2_tool_runtime_eventlog.py`
- `tests/host/test_phase2_tool_runtime_truncation.py`
- `tests/host/test_phase6_run_event_serializer.py`
- `tests/host/test_phase4_context_compaction.py`
- `tests/host/test_phase4_overflow_retry.py`
- `tests/host/test_phase5_multiturn_no_governance_smoke.py`
- `tests/host/test_phase7_tool_trace_projection.py`
- `tests/host/test_phase8_tool_runtime_fencing.py`
- `utils/smoke_host_multiturn_no_governance.py`
- `utils/smoke_host_tool_runtime.py`
- `utils/smoke_host_p7_tool_trace.py`
- `dayu/host/README.md`
- `tests/README.md`
- `docs/host/phase8.5-s1-implementation-report.md`

## Test And Validation Results

Required validation:

```bash
source .venv/bin/activate
python -m pyright dayu/host/ dayu/contracts/ tests/host/ tests/contracts/
```

Result: passed, `0 errors, 0 warnings, 0 informations`.

```bash
source .venv/bin/activate
pytest tests/contracts/test_tool_declaration.py tests/contracts/test_tool_result_envelope.py tests/contracts/test_package_exports.py -q
```

Result: passed, `9 passed`.

```bash
source .venv/bin/activate
pytest tests/host/test_phase1_public_boundary.py tests/host/test_host_public_api_surface.py -q
```

Result: passed, `7 passed`.

```bash
source .venv/bin/activate
pytest tests/host/test_phase2_tool_runtime_boundary.py tests/host/test_phase2_tool_runtime_truncation.py tests/host/test_phase2_tool_runtime_eventlog.py -q
```

Result: passed, `28 passed`.

```bash
source .venv/bin/activate
pytest tests/host/test_phase3_conversation_memory_projection.py tests/host/test_phase5_multiturn_no_governance_smoke.py tests/host/test_phase8_tool_runtime_fencing.py tests/host/test_phase7_tool_trace_projection.py -q
```

Result: passed, `43 passed`.

Additional grep checks:

```bash
rg -n "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolRuntimeCursor|ToolResultTruncatedData|ToolCursor|framework_fetch_more" dayu/host/README.md tests/README.md utils/smoke_host_p7_tool_trace.py
rg -n "TOOL_FETCH_MORE|TOOL_CURSOR_|TOOL_RESULT_TRUNCATED|ToolFetchMore|ToolCursor.*Data|ToolResultTruncatedData|framework_fetch_more" dayu/contracts dayu/host utils/smoke_host_p7_tool_trace.py
```

Result: no matches. Tests still intentionally contain old names in negative public-surface assertions, and runtime / tests use
Host private `FRAMEWORK_FETCH_MORE_NAME` as an internal implementation constant.

## README Decision

Updated:

- `dayu/host/README.md`: removed old public fetch_more / cursor contract wording, removed dedicated truncation / cursor /
  fetch_more EventLog fact model, documented private `RuntimeTruncateManager`, ordinary tool-call EventLog, schema
  auto projection, payload retention, and Memory / RunInput ingestion policy.
- `tests/README.md`: updated ToolRuntime, P5 smoke, P8-S5 fencing, and public boundary descriptions to match ordinary
  tool event semantics and negative public-surface lock.

Not updated:

- Root `README.md`: no CLI, project usage, render, config entry, or user workflow change.
- `dayu/README.md`: no UI / Service / Host / Engine layering change beyond Host-internal boundary already covered by
  Host README.
- `docs/host/design.md` and `docs/host/migration-plan.md`: treated as architecture / migration sources for the approved
  plan; this implementation artifact records the slice outcome without rewriting those higher-level design docs.

## Residual Risks And Uncovered Items

- Slice 1 code review Finding 01 / 02 / 03 and OLD-NEW Finding 01 / 02 / 03 are resolved by this fix pass.
- Private `fetch_more` currently uses a reserved tool name collision policy: caller-provided schema named `fetch_more`
  must match the private schema or runtime raises `ValueError`. This is intentional for Slice 1 but should be considered
  by future ToolRegistry work.
- Slice 1 keeps ordinary cursor / scope token payload in EventLog / trace by design; leakage prevention now relies on
  Memory / RunInput ingestion policy and explicit credential scrub. Future slices should keep analyzer / cold-storage
  policy aligned with this boundary.
- Trace analyzer semantics for truncation / fetch_more are only minimally migrated to ordinary accepted outcome payload;
  deeper analyzer policy remains Slice 2+ scope.

## Stop Condition Status

No stop condition triggered:

- Did not expose `ToolDefinition`, callable, manager, cursor type, or fetch_more public contract to Engine,
  `StartRunRequest`, `RunOptions`, or Host public API.
- Did not require full P10 ToolRegistry.
- Did not require old cursor / fetch_more EventLog rows compatibility reader.

## Completion Signal

Slice 1 implementation is complete within the assigned boundary. Code, tests, README updates, and this durable artifact are
present; remaining work belongs to later P8.5 slices or controller-level follow-up.
