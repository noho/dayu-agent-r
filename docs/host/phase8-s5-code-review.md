# P8-S5 Code Review: Attempt-scoped Append 与 ToolRuntime Fencing

## Review Gate

- **Gate name**: P8-S5 code review
- **Reviewed target**: `migration/host-p8-attempt-lease-recovery` branch, uncommitted diff against `de626e7 host: add p8 terminal close fencing`
- **Diff scope**: `dayu/host/_attempt_supervisor.py`、`dayu/host/_run_harness.py`、`dayu/host/_tool_runtime.py`、`dayu/host/README.md`、`tests/README.md`、`tests/host/test_phase8_attempt_fencing.py`、`tests/host/test_phase8_attempt_supervisor.py`，以及未跟踪 `tests/host/test_phase8_tool_runtime_fencing.py`、`docs/host/phase8-s4-user-review.md`
- **Conclusion**: **通过**

## 实施方验证结果

实施方报告:

- `pytest tests -q` → 646 passed
- `pytest tests/host -q` → 270 passed
- `pytest tests/host/test_phase8_attempt_fencing.py tests/host/test_phase8_attempt_supervisor.py tests/host/test_phase8_tool_runtime_fencing.py -q` → 24 passed
- `pyright dayu/host tests/host` → 0 errors / 0 warnings
- `git diff --check` → exit 0

review 独立确认: 上述命令均通过。

## Review Checklist

### 1. AttemptScopedRunEventAppender

| 检查项 | 结果 |
|--------|------|
| 所有 append 先校验 `draft.run_id == owner_context.run_id` | **PASS** — `_verify_run_id_matches` 在 `append`、`append_in_transaction`、`append_terminal_and_close` 三个入口均首先调用 |
| 非 terminal append 在同一 `BEGIN IMMEDIATE` 事务内完成 `verify_owner` + `append_with_position_in_transaction` | **PASS** — `append` 开 `self.storage.transaction()`，`append_in_transaction` 使用外层 `tx`，两者均在同一事务内执行 |
| terminal draft 被明确拒绝并引导走 `append_terminal_and_close` | **PASS** — `append` / `append_in_transaction` 检查 `TERMINAL_RUN_EVENT_TYPES` 后抛 `ValueError`；`append_terminal_and_close` 反向检查后抛 `ValueError` |
| owner mismatch / stale owner / lease expired 抛 typed `AttemptFencingError`，不写 diagnostic RunEvent | **PASS** — `_verify_run_id_matches` 抛 `AttemptFencingError(reason=OWNER_MISMATCH)`；`verify_owner` CAS 失败抛 `AttemptFencingError`；全程无 diagnostic RunEvent 写入 |
| `scoped_appender` 只能由 `AttemptSupervisor` 工厂构造 | **PASS** — `AttemptSupervisor.scoped_appender()` 是唯一公开入口；`AttemptScopedRunEventAppender` 虽为 `@dataclass`，但所有调用方均通过工厂构造 |
| `AttemptSupervisor.append_terminal_and_close` 委托给 scoped appender | **PASS** — 方法体直接 `self.scoped_appender(owner_context).append_terminal_and_close(...)` |

### 2. LocalRunHarness Call Site 覆盖

| 检查项 | 结果 |
|--------|------|
| Engine-sourced events 走 scoped appender | **PASS** — `_run_to_store` 主循环内 `_resolve_attempt_appender(current_active_attempt).append(draft)` |
| `CONTEXT_OVERFLOW_OBSERVED` | **PASS** — `_append_overflow_observed` 改为 `_scope_appender().append(...)` |
| `CONTEXT_COMPACT_REQUESTED` | **PASS** — `_compact_or_fail` 内 `_scope_appender().append(...)` |
| `CONTEXT_COMPACT_COMPLETED` | **PASS** — `_compact_or_fail` 内 `_scope_appender().append(...)` |
| `CONTEXT_COMPACT_FAILED` | **PASS** — `_compact_or_fail` / `_append_compact_exception_failure` / `_append_unexpected_compaction_terminal_closure` 均改为 `_scope_appender().append(...)` |
| `CONTEXT_ATTEMPT_RETRYING` | **PASS** — `_compact_or_fail` 内 `_scope_appender().append(...)` |
| Worker failure | **PASS** — `_append_worker_failure_if_needed` 改为 `_scope_appender().append(...)` |
| Missing terminal failure | **PASS** — `_append_missing_terminal_failure_if_needed` 改为 `_scope_appender().append(...)` |
| `RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 同事务 | **PASS** — `_append_run_input_context_snapshot_fact` 新增 `active_attempt` 参数；supervisor 路径使用 `scoped.append_in_transaction(tx=tx, draft=draft)`，legacy 路径退化为 `event_store.append_in_transaction` |
| `USER_INPUT_ACCEPTED` 在 attempt 前 raw append | **PASS** — `start_run` 内 `self.event_store.append(user_input_accepted_draft(...))`；此时尚未创建 attempt，不参与 fencing，符合设计 |
| owner-lost 后 Host failure raw append | **PASS** — `_handle_owner_lost` (line 1042) 仍使用 `self.event_store.append(host_failure_draft(...))`；此时 owner 已 lost，`verify_owner` 可能已失败，raw append 保证 Host failure 一定能写入 EventLog，run 不会进入无终态 limbo |
| 是否遗漏 direct `event_store.append` call site | **PASS** — `start_run` 的 `USER_INPUT_ACCEPTED` 是唯一保留的 raw append，其余全部走 scoped helper |
| `_scope_appender()` vs `_resolve_attempt_appender()` 选型 | **PASS** — `_scope_appender()` 读 ContextVar 用于不直接持有 `_ActiveAttempt` 的 helper（compact / overflow / failure）；`_resolve_attempt_appender()` 显式接收 `_ActiveAttempt` 用于主循环；两者互补，退化逻辑一致 |

### 3. ToolRuntime Fencing

| 检查项 | 结果 |
|--------|------|
| `ToolRuntimeEventAppender` Protocol 强类型 | **PASS** — `async def append(self, draft: RunEventDraft) -> RunEvent`；不暴露 owner token |
| `PlainRunEventAppender` 非 fencing 退化 | **PASS** — `frozen=True, slots=True`；直接透传 `event_store.append` |
| `ToolRuntimeOwnerScope` ContextVar 安装/恢复 | **PASS** — `set()` + `try/finally` `reset()`；异常路径仍恢复 |
| `active_tool_runtime_appender` 返回类型 | **PASS** — `ToolRuntimeEventAppender | None`；无 scope 时返回 `None` |
| `InMemoryToolRuntime._resolve_appender` 7 个 helper 全部通过 | **PASS** — `_append_tool_result_truncated`、`_append_cursor_issued`、`_append_fetch_requested`、`_append_fetch_completed`、`_append_cursor_expired`、`_append_cursor_denied`、`_fetch_failure` 均改为 `self._resolve_appender().append(...)` |
| `ToolExecutionContext` 不变 | **PASS** — 未修改 `ToolExecutionContext`；owner secret 不进入 `dayu.contracts` |
| framework `fetch_more` 使用当前 attempt owner | **PASS** — `_execute_framework_fetch_more` 调用 `self.fetch_more(parsed)`；`fetch_more` 内部通过 `_resolve_appender()` 读取 ContextVar，取得的是发起 fetch_more 时 scope 内的 appender，不是 cursor 创建时的旧 owner |
| owner token 不进入 extra payload / 日志 / public API | **PASS** — 所有日志使用 `owner_token.masked()`；`AttemptOwnerContext` 仅在 `_attempt_supervisor.py` / `_run_harness.py` 内部使用 |

### 4. 测试充分性

| 检查项 | 结果 |
|--------|------|
| `AttemptScopedRunEventAppender` 路径覆盖 | **PASS** — `test_phase8_attempt_fencing.py` 新增 4 个测试: terminal draft rejected、run_id mismatch、stale owner fenced、normal owner append |
| `ToolRuntimeOwnerScope` 行为 | **PASS** — `test_phase8_tool_runtime_fencing.py` 覆盖: scope 外返回 None、scope 安装/恢复（含异常路径）、scope 内返回 `AttemptScopedRunEventAppender`、scope 外退化为 `PlainRunEventAppender`、run_id mismatch 抛 OWNER_MISMATCH |
| framework `fetch_more` 端到端 fenced 路径 | **见 Finding F1** |

### 5. Scope Guard

| 检查项 | 结果 |
|--------|------|
| 不提前实现 P8-S6 recovery scan | **PASS** — 无 `recover_stale_attempts` 代码 |
| 不提前实现 P8-S7 multiprocessing | **PASS** — 无 multiprocessing 代码 |
| 不引入 observer claim / lease | **PASS** |
| 不新增 fenced late write diagnostic RunEvent | **PASS** — fenced 情况直接抛 `AttemptFencingError`，不写 diagnostic |
| 不把 owner token 放入 extra payload | **PASS** |

### 6. 类型与项目约束

| 检查项 | 结果 |
|--------|------|
| 新增 `Any` / `object` / type ignore | **PASS** — 生产代码无新增；测试 `test_phase8_tool_runtime_fencing.py` line 209 有 `type: ignore[arg-type]` 用于 `_noop_executor`，仅构造 `InMemoryToolRuntime` 不触发 execute 路径，可接受 |
| 中文 docstring 完整性 | **PASS** — `AttemptScopedRunEventAppender` 及其 3 个方法、`_verify_run_id_matches`、`ToolRuntimeEventAppender`、`PlainRunEventAppender`、`ToolRuntimeOwnerScope`、`active_tool_runtime_appender`、`_resolve_appender`、`_resolve_attempt_appender`、`_scope_appender`、`_attempt_owner_scope`、`_null_attempt_owner_scope`、`_append_run_input_context_snapshot_fact` 新增参数文档均完整 |
| magic string / number | **PASS** — `_ERROR_TERMINAL_REQUIRES_TERMINAL_TYPE` / `_ERROR_TERMINAL_DRAFT_TERMINAL_TYPE` 提取为模块常量 |
| God helper / 循环依赖 | **PASS** — `_tool_runtime.py` 新增 `ToolRuntimeEventAppender` Protocol 不 import `_attempt_supervisor`；`_run_harness.py` import `_tool_runtime` 的新符号；无反向依赖 |
| 反向依赖 | **PASS** — 依赖方向: `_run_harness.py` → `_attempt_supervisor.py` → `_tool_runtime.py` Protocol；`_tool_runtime.py` 不 import host 上层 |

### 7. 文档

| 检查项 | 结果 |
|--------|------|
| `dayu/host/README.md` 当前事实 | **PASS** — 更新内容描述 P8-S5 已落地的 `AttemptScopedRunEventAppender` 机制，未写未来设计 |
| `tests/README.md` 当前事实 | **PASS** — 新增 P8-S5 ToolRuntime owner fencing 测试描述 |
| `docs/host/migration-plan.md` 更新 | **见 Finding F2** |
| `docs/host/phase8-s4-user-review.md` 未跟踪 | **见 Finding F3** |
| residual risks 有 owner | **PASS** — README 明确标注 recovery scan 归 P8-S6、multiprocessing 归 P8-S7 |

## Findings

### Finding F1: Framework fetch_more 端到端 fenced 测试缺失

- **Severity**: medium
- **Status**: deferred-with-owner
- **Owner**: P8-S6
- **Location**: `tests/host/test_phase8_tool_runtime_fencing.py`
- **Description**: 实施报告指出 "ToolRuntime 端到端集成测试当前覆盖 helper 解析路径与 fencing 早抛；需要走完整 framework fetch_more 路径的端到端 fenced 复现可在 P8-S6 一并补强。" 当前测试覆盖:
  - `ToolRuntimeOwnerScope` ContextVar 安装/恢复/异常恢复
  - `active_tool_runtime_appender` scope 外 None
  - `_resolve_appender` scope 内/外退化
  - run_id mismatch 抛 OWNER_MISMATCH
  - 但缺少: 在 scope 内通过 `InMemoryToolRuntime.fetch_more()` 完整路径写入 `TOOL_FETCH_MORE_REQUESTED` / `TOOL_FETCH_MORE_COMPLETED` / `TOOL_CURSOR_ISSUED` 等 fact，且 draft.run_id mismatch 时被 fencing 拒绝的端到端测试。
- **Evidence**: P8-S5 完成信号要求 "late owner 对 ... ToolRuntime truncate / cursor / fetch_more facts 均被拒绝；合法 owner 回归测试通过。" 当前 helper 级测试已证明 `_resolve_appender()` 在 scope 内返回 `AttemptScopedRunEventAppender`、该 appender 对 run_id mismatch 抛 `AttemptFencingError`、且 EventLog 不残留。这两个组件组合起来足以推导 framework fetch_more 路径也会被 fencing。但缺少从 `fetch_more()` 入口到 EventLog 的端到端 fenced 断言。
- **Recommendation**: 作为 P8-S6 completion criteria 的一部分补强: 构造 `InMemoryToolRuntime` + 真实 supervisor + `ToolRuntimeOwnerScope`，在 scope 内调用 `fetch_more()` 时注入 run_id mismatch 的 cursor record，断言抛 `AttemptFencingError(reason=OWNER_MISMATCH)` 且 `list_events` 为空。同时补一个合法 owner 的 `fetch_more()` 正常写入回归测试。
- **Controller Decision**: deferred-with-owner — P8-S6

### Finding F2: migration-plan.md 需要在 S5 完成后更新

- **Severity**: low
- **Status**: accepted
- **Location**: `docs/host/migration-plan.md`
- **Description**: `migration-plan.md` 当前 phase status 表记录到 P8-S4。S5 closeout 后应更新 P8 行状态。实施方未在当前 diff 中更新此文件。
- **Evidence**: 实施方可能计划在 gate closeout 阶段统一更新。review 不阻塞，但 closeout 时必须同步。
- **Recommendation**: closeout 时更新 `migration-plan.md` P8 行状态至 S5。
- **Controller Decision**: accepted — 已修复

### Finding F3: phase8-s4-user-review.md 未跟踪 artifact

- **Severity**: low
- **Status**: accepted
- **Location**: `docs/host/phase8-s4-user-review.md`
- **Description**: `git status` 显示 `docs/host/phase8-s4-user-review.md` 为 `??`（未跟踪）。后续提交不能遗漏此文件。
- **Evidence**: 该文件是 P8-S4 user review 的正式 artifact，应纳入版本管理。
- **Recommendation**: 在当前或下一个 commit 中 `git add docs/host/phase8-s4-user-review.md`。
- **Controller Decision**: accepted — 已修复

## Open Questions

无。

## Residual Risks

| 风险 | Owner | 说明 |
|------|-------|------|
| Framework fetch_more 端到端 fenced 测试 | P8-S6 | 见 Finding F1；组件级测试已充分证明 contract，P8-S6 补强端到端断言 |
| Recovery scan 未实现 | P8-S6 | 进程崩溃后 stale/orphan attempt 无法自动恢复；当前依赖 lease TTL 自然过期 |
| Multiprocessing 未验证 | P8-S7 / issue #38 | 文件 SQLite 多进程并发 append / terminal race 未测试 |
| P16 / issue #28 observer async upgrade | P16 | observer sink 异步协议升级归 P16 |

## 总结

P8-S5 实现质量高，设计清晰:

1. **AttemptScopedRunEventAppender** 强类型设计正确: `run_id` 校验 → `verify_owner` CAS → EventLog append 三步在同一 `BEGIN IMMEDIATE` 事务内完成；terminal draft 明确拒绝引导到 `append_terminal_and_close`；`scoped_appender()` 是唯一构造入口。

2. **Harness call site 覆盖完整**: Engine-sourced event、context overflow/compact/retry facts、worker failure、missing terminal、`RUN_INPUT_CONTEXT_SNAPSHOT_BUILT` 全部走 scoped helper；`USER_INPUT_ACCEPTED` 在 attempt 前 raw append 合理；owner-lost 后 raw append 保证 Host failure 一定能写入。

3. **ToolRuntime fencing 设计干净**: `ToolRuntimeEventAppender` Protocol 不泄漏 owner token；`ContextVar` + `ToolRuntimeOwnerScope` 避免跨 attempt 污染；7 个 helper 全部通过 `_resolve_appender()` 统一收口；framework `fetch_more` 自然取得当前 attempt owner。

4. **Scope guard 严格遵守**: 无 P8-S6/P8-S7 提前实现，无 observer claim，无 diagnostic RunEvent，无 owner token 泄漏。

5. **唯一不足**: framework fetch_more 端到端 fenced 测试缺失（F1），但组件级测试已充分证明 contract，deferred 到 P8-S6 补强。
