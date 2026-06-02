# WU-TOOL-01 Aggregate Review — MiMo

- **Date**: 2026-06-01
- **Branch**: `fix/wu-tool-01-attempt-scoped-duplicate-governance`
- **Base**: `07cf34d397fe076979146163f34238b5c460ca7d`
- **Scope**: 完整 review 当前分支相对 base 的 WU-TOOL-01 diff（slice1–slice4 全量）

---

## Findings

### F-01 [PASS] duplicate key 真正 attempt-scoped，跨 Attempt 不继承

`duplicate_governance_key` 的 sha256 输入包含 `scope.attempt_id`，不同 Attempt 的相同工具+参数自然产生不同 key。`InMemoryAttemptDuplicateGovernance` 是 ToolRuntime executor 实例私有状态，不跨 Attempt、Run 或进程共享。

- `dayu/host/tool_duplicate_governance.py:465-483` — key 计算包含 `attempt_id`
- `dayu/host/tool_runtime.py:2076-2082` — executor 构造 request 时从 `execution_scope.attempt_id` 取值
- 测试 `test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs` 验证跨 Attempt 执行 fresh request

### F-02 [PASS] same Attempt in-flight owner/waiter 治理正确

`InMemoryAttemptDuplicateGovernance.decide_duplicate` 使用 `asyncio.Condition` 实现 owner/waiter 串行化：
- owner 首次调用注册 in-flight 记录，返回 ALLOW
- waiter 发现 in-flight 状态为 OWNER_RUNNING 时 `await condition.wait()`
- owner 完成后 `record_accepted` 或 `record_durable_missing` 唤醒所有 waiter

waiter 在 owner terminal 后根据 in-flight state 路径：
- ACCEPTED → 按 policy 决策复用或拒绝
- DURABLE_MISSING → 返回 `DuplicateDecisionKind.DURABLE_MISSING`，不二次执行

### F-03 [PASS] allow/reuse/hint/require_justification/hard_stop 语义无互相污染

- `ALLOW` + 无 prior refs → 注册 in-flight，真实执行
- `ALLOW` + 有 prior refs → 真实执行（不复用），`_record_duplicate_accepted` 写入新 accepted entry
- `REUSE` → 直接返回 prior outcome，`_record_duplicate_accepted` 返回 False（不重复写入）
- `HINT` / `REQUIRE_JUSTIFICATION` / `HARD_STOP` → governed error，不执行
- `DURABLE_MISSING` → governed error，不执行，不写入 index

每种决策的 `duplicate_decision_message` 和 `diagnostic_message` 由 `DuplicateGovernancePolicy.messages` 配置驱动，不再硬编码。

### F-04 [PASS] owner cancellation / tool exception / accept rejected / accept timeout / durable-missing waiter 行为测试充分

| 场景 | 测试 | 验证 |
|------|------|------|
| owner accept rejected | `test_same_attempt_concurrent_rejected_accept_reports_durable_missing` | waiter → `duplicate_prior_accept_missing`，后续 fresh re-execute 也 failed |
| owner accept timeout | `test_same_attempt_concurrent_timed_out_accept_reports_durable_missing` | 同上 |
| owner tool exception | `test_same_attempt_concurrent_tool_exception_reports_durable_missing` | waiter → `duplicate_prior_accept_missing`，后续 fresh re-execute 可重试 |
| owner cancellation | `test_same_attempt_concurrent_owner_cancellation_reports_durable_missing` | waiter → `duplicate_prior_accept_missing`，后续 fresh re-execute 成功 |
| allow policy concurrent | `test_allow_policy_concurrent_waits_for_owner_before_second_execution` | waiter 等 owner 完成后真实执行 |
| allow policy post-completion | `test_allow_policy_post_owner_completion_executes_again` | 后续调用真实执行 |

### F-05 [PASS] dispatch / HostToolingOptions policy wiring 生产路径生效，无 run-scoped registry 残留

- `HostToolingOptions` 新增 `duplicate_governance_policy: DuplicateGovernancePolicy` 字段（`tooling.py:88`）
- `dispatch.py` 通过 `tooling_options.duplicate_governance_policy` 传入 `ToolRuntimeBuildRequest`（`dispatch.py:2692`）
- `DefaultToolRuntimeFactory` 直接构造 `InMemoryAttemptDuplicateGovernance(request.duplicate_governance_policy)`（`tool_runtime.py:2756`）
- 旧 `InMemoryRunScopedDuplicateGovernanceRegistry`、`RunScopedDuplicateGovernanceRegistry`、`_RunLocalDuplicateGovernanceState`、`InMemoryRunLocalDuplicateGovernance` 全部删除
- dispatch.py 中 `_duplicate_governance_registry` 字段、`clear_run`、`clear_all`、`active_run_count` 调用全部移除
- `threading.RLock` 导入移除，全部改用 `asyncio.Condition`

### F-06 [PASS] TOOL_CALL_GOVERNED payload / trace_summary / diagnostic message 一致性

- `duplicate_scope` JSON 在 `_append_tool_call_governed_if_needed` 中写入 payload（`tool_runtime.py:3695`）
- `tool_trace.py` 新增 `_FIELD_DUPLICATE_SCOPE`，在 `_extract_canonical_trace`、`_trace_summary` 中透传
- `_duplicate_scope_json` 投影 `{kind, attempt_id}` 到所有三个 surface
- 测试 `test_tool_call_chain_projects_hot_rows_and_cold_lines` 验证 hot row 和 cold line 均包含 `duplicate_scope`
- 测试 `test_event_sequence_monotonic_and_reuse_has_canonical_governance_only` 验证 governed payload 中 `duplicate_scope` 和 `reuse_prior_event_refs` 正确

### F-07 [PASS] worker/Host restart non-durable behavior 被测试和 README 清楚表达

- `dayu/host/README.md`："新 Attempt、worker restart 或 Host restart 不继承旧内存索引，也不从 EventLog 重建 duplicate ledger"
- 测试 `test_fresh_toolruntime_handle_same_attempt_is_in_memory_non_durable_restart_behavior` 验证新 handle 同 Attempt 同 key 按 fresh request 处理
- 测试 `test_reactive_recovery_uses_fresh_duplicate_governance_attempt` 验证 reactive recovery 新 Attempt 执行 fresh request

### F-08 [PASS] README 和 tests/README 职责合规

- `dayu/host/README.md` 更新：run-scoped duplicate governance registry → attempt-local duplicate governance state；policy wiring 描述更新
- `tests/README.md` 更新：duplicate governance 测试矩阵新增 attempt-scoped / in-flight / cross-Attempt / worker restart / trace scope 条目；duplicate governance 测试组新增 `test_tool_trace_projection.py`、`test_dispatch_scheduler.py`、`test_tooling_options.py`
- 术语 grep 无 run-scoped/run-local duplicate 残留（仅 `tests/README.md` 中 "run-scoped truncation cursor" 是 truncation 语义，非 duplicate governance）

### F-09 [PASS] 无 durable ledger / EventLog 重建 / schema change / compat wrapper / Any/object/无类型签名 / 分层反向依赖

- 无新增 durable table 或 schema migration
- 无从 EventLog 重建 duplicate refs 的代码
- 旧模块 `DuplicateDecision`、`DuplicateGovernancePolicy`、`DuplicateGovernancePort`、`DuplicateGovernanceRequest` 等从 `tool_runtime.py` 删除，新位置 `tool_duplicate_governance.py` 无兼容 re-export
- 新模块 `__all__` 明确导出，`tool_runtime.py` `__all__` 已清理旧符号
- 新模块无 `Any`、`object`、无类型参数/返回值
- `tool_duplicate_governance.py` 只 import `dayu.contracts.*` 和 `dayu.host.durable.codec`，不反向依赖上层

### F-10 [PASS] DuplicateGovernancePort 协议从 sync 改为 async

旧 `DuplicateGovernancePort.decide_duplicate` 和 `record_accepted` 是同步方法，新版本改为 `async`。`ToolRuntimeExecutor._execute_single_call` 中相应改为 `await` 调用。这是正确的设计选择，因为 `asyncio.Condition.wait()` 需要在 async context 中工作。

`record_accepted` 签名从 `record_accepted(record: DuplicateAcceptedRecord)` 改为 `record_accepted(request, accepted_entry)`，将 request 和 entry 分离，消除旧 `DuplicateAcceptedRecord` 中冗余的 request 嵌套。

### F-11 [PASS] `_execute_single_call` try/finally duplicate terminal 记录逻辑正确

`_execute_single_call` 中：
1. `duplicate_owner_needs_terminal` = `ALLOW` and 无 prior refs（即 owner 首次执行）
2. `duplicate_terminal_recorded` 初始 False
3. `durable_missing_reason` 初始 `GOVERNED_BEFORE_ACCEPT`，按执行路径更新：
   - callable exception → `TOOL_EXCEPTION`
   - bounded policy cancel → `OWNER_CANCELLED`
   - accept rejected → `HOST_ACCEPT_REJECTED`
   - accept timeout → `HOST_ACCEPT_TIMEOUT`
4. `finally` 块：`if duplicate_owner_needs_terminal and not duplicate_terminal_recorded: record_durable_missing`

关键路径验证：
- 正常 accepted → `_record_duplicate_accepted` 返回 True，finally 跳过
- policy reject（非 ALLOW）→ `duplicate_owner_needs_terminal` True，`duplicate_terminal_recorded` False，finally 记录 `GOVERNED_BEFORE_ACCEPT`
- callable exception → 直接 return raw_outcome，finally 记录 `TOOL_EXCEPTION`
- accept rejected → `durable_missing_reason` 更新为 `HOST_ACCEPT_REJECTED`，finally 记录

对于 REUSE 路径，`_accept_reuse` 提前 return，`duplicate_owner_needs_terminal` 为 False（有 prior refs），finally 跳过——正确，REUSE 不需要注册 in-flight。

### F-12 [INFO] DuplicateGovernanceMessages 可配置化

旧实现中 duplicate governance 消息硬编码在 `_duplicate_message` 函数中。新实现通过 `DuplicateGovernanceMessages` dataclass 配置化，支持每种决策独立消息、`attempt_scope_diagnostic` 和 `prior_accept_missing` 消息。`DuplicateGovernancePolicy.__post_init__` 校验所有消息非空。测试覆盖零配置默认消息、自定义消息和空消息拒绝。

### F-13 [INFO] HostToolingOptions 类型校验新增

`HostToolingOptions.__post_init__` 新增 `isinstance(duplicate_governance_policy, DuplicateGovernancePolicy)` 校验，拒绝非 typed policy 对象。测试 `test_host_tooling_options_rejects_invalid_duplicate_policy_type` 覆盖。

---

## Open Questions

无。

---

## Verification

| 验证项 | 结果 |
|--------|------|
| `pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py tests/host/test_dispatch_scheduler.py tests/host/test_tooling_options.py` | **123 passed** (1.31s) |
| `pyright dayu/host/tool_duplicate_governance.py dayu/host/tool_runtime.py dayu/host/dispatch.py dayu/host/tooling.py dayu/host/tool_trace.py` | **0 errors, 0 warnings, 0 informations** |
| 术语 grep run-scoped/run-local duplicate 残留 | **无残留**（仅 truncation 语义的 "run-scoped truncation cursor"） |

---

## Residual Risks

1. **无 residual blocking risk。** 所有 duplicate governance 语义正确、测试覆盖充分、分层合规、术语一致。

2. **低风险观察项：** `DuplicateGovernancePort` 从 sync 改为 async 是 breaking change，但该端口是 Host 内部协议，无外部实现方，影响可控。

---

## Conclusion

**Remaining blocking findings: 0**

WU-TOOL-01 将 duplicate governance 从 run-scoped in-memory（`InMemoryRunScopedDuplicateGovernanceRegistry` + `RLock`）重构为 attempt-scoped in-memory（`InMemoryAttemptDuplicateGovernance` + `asyncio.Condition`），核心变更包括：

1. **新增 `tool_duplicate_governance.py`**：承载所有 duplicate governance typed contracts（policy、scope、request、decision、port protocol、in-memory implementation），与 `tool_runtime.py` 解耦
2. **消除 run-scoped registry 生命周期**：dispatch scheduler 不再持有 `_duplicate_governance_registry`，不再需要 `clear_run`/`clear_all` 清理
3. **in-flight owner/waiter 串行化**：`asyncio.Condition` 实现同一 Attempt 内并发重复调用的正确等待和唤醒
4. **configurable messages**：`DuplicateGovernanceMessages` 消除硬编码消息，支持调用方自定义治理文案
5. **trace consistency**：`duplicate_scope` 在 payload、trace_summary、diagnostic 三 surface 一致投影

代码质量、测试覆盖、分层合规、README/术语同步均达标。
