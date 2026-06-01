# WU-TOOL-01 Aggregate Review

- **Review type**: aggregate deepreview (slices 1–4 完整审查)
- **Date**: 2026-06-01
- **Reviewer**: Claude Opus 4.6
- **Repo**: `/Users/leo/workspace/dayu-agent-r`
- **Branch**: `fix/wu-tool-01-attempt-scoped-duplicate-governance`
- **Base**: `07cf34d397fe076979146163f34238b5c460ca7d`
- **Accepted commits**: slice1 `bd782be`, slice2 `5f09506`, slice3 `98ccd7a`, slice4 `660561a`
- **Design source**: `docs/host/design.md`
- **Control doc**: `docs/host/host-core-followup-implementation-control.md`
- **Plan**: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`

## Findings

### 1. Duplicate Key / Scope 是否正确 attempt-scoped

**通过。** `duplicate_governance_key()`（`dayu/host/tool_duplicate_governance.py:553-571`）将 `attempt_id` 纳入 scope hash，与 `tool_name`、`tool_identity_digest`、`normalized_arguments_digest`、`semantic_duplicate_key` 一起构成 stable sha256 duplicate key，排除 `index_in_iteration`。

`DefaultToolRuntimeFactory.create_tool_runtime()`（`tool_runtime.py:2756-2758`）为每个 `ToolRuntimeBuildRequest` 创建新的 `InMemoryAttemptDuplicateGovernance`，自然阻止跨 Attempt 继承。

测试 `test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs`（`test_toolruntime_duplicate_governance.py:759-800`）证明相同 run_id 不同 attempt_id 的同工具同参数 duplicate key 不同，且两个调用各自按 `ALLOW` fresh request 执行。

**无残留隐患。** grep 确认 dayu/host 中无 `RunScoped`、`RunLocal`、`duplicate_governance_for_run`、`duplicate_registry` 残留。

### 2. In-Flight Owner / Waiter 治理正确性

**通过。** `InMemoryAttemptDuplicateGovernance.decide_duplicate()`（`tool_duplicate_governance.py:376-424`）实现完整状态机：

- `decide_duplicate()` 在 `asyncio.Condition` 保护下：
  - 无 accepted entry 且无 in-flight 记录 → 创建 `OWNER_RUNNING` 记录，返回 `ALLOW`（owner 路径）
  - 已有 accepted entry → 立即返回 policy 驱动的决策（`reuse`/`hint`/`require_justification`/`hard_stop`/`allow`）
  - 已有 in-flight 记录 → waiter 等待 `condition.wait()`，owner terminal 后根据 `ACCEPTED` 或 `DURABLE_MISSING` 返回对应决策
- `record_accepted()` 写入 accepted entry，更新 in-flight 状态为 `ACCEPTED`，`notify_all()`
- `record_durable_missing()` 设置 terminal 状态为 `DURABLE_MISSING`，`notify_all()`
- `record_accepted()` 和 `record_durable_missing()` 都 `pop` in-flight map entry

**关键并发契约满足：**
- 工具 callable 执行和 Host accept 不在持有 duplicate governance lock 时运行（lock 只在 `_state.condition` 的 async context manager 内持有）
- waiters 不接收 owner 异常/取消，返回 governed durable-missing decision
- in-flight map entry 释放后，新 caller 看到无 accepted entry 且无 in-flight → 成为新 owner

### 3. Owner 失败路径测试覆盖

**通过。** 4 条 owner 失败路径均有直接并行测试，且每条测试末尾都有 "later" 调用验证 in-flight 释放后新 caller 成为 fresh owner：

| 失败路径 | 测试函数 | 行号 |
|---|---|---|
| owner 取消 | `test_same_attempt_concurrent_owner_cancellation_reports_durable_missing` | 1008 |
| 工具异常 | `test_same_attempt_concurrent_tool_exception_reports_durable_missing` | 968 |
| accept rejected | `test_same_attempt_concurrent_rejected_accept_reports_durable_missing` | 883 |
| accept timeout | `test_same_attempt_concurrent_timed_out_accept_reports_durable_missing` | 926 |

所有路径断言：
- `tool.call_count == 1`（in-flight 窗口内不二次执行）
- waiter outcome 为 `ToolFailedOutcome`，hint = `"duplicate_prior_accept_missing"`
- 后续 caller（"later"）执行新真实工具调用

`_execute_one()` 的 `finally` 块（`tool_runtime.py:2210-2215`）通过 `duplicate_owner_needs_terminal` flag 精确控制：只有 in-flight owner（`ALLOW` 且无 prior refs）才在失败时调用 `record_durable_missing()`。

### 4. Allow / Reuse / Hint / Require_justification / Hard_stop 语义正确

**通过。** `_decision_for_request()`（`tool_duplicate_governance.py:500-524`）正确实现：

- 按工具名覆盖 `decisions_by_tool_name`，fallback 到 `default_duplicate_decision`
- `REQUIRE_JUSTIFICATION` 无配置参数名时降级为 `HINT`
- `REQUIRE_JUSTIFICATION` 有参数名且参数值为非空 str 时返回 `ALLOW`
- `_decision_for_accepted_entry()` 中 `ALLOW` 调用 `_allow_decision()`，传递 prior_refs 但不传 prior_outcome（allow 仍执行真实 tool）
- 非 `ALLOW` 决策传递 prior_outcome 和 prior_event_refs，供 reuse / governed error 消费

**`allow` 并发语义正确：** `test_allow_policy_concurrent_waits_for_owner_before_second_execution`（line 1061）验证 allow 也等待 owner terminal；`test_allow_policy_post_owner_completion_executes_again`（line 1088）验证 owner 完成后再次调用仍真实执行。

**governed error candidate 校验完整：** `_validate_duplicate_governed_candidate()`（`tool_runtime.py:3888-3922`）对 `DURABLE_MISSING`、`HINT`、`REQUIRE_JUSTIFICATION`、`HARD_STOP` 分别验证 reason/message/prior_refs 一致性。

### 5. Dispatch / HostToolingOptions Policy Wiring

**通过。** `HostToolingOptions.duplicate_governance_policy`（`dayu/host/tooling.py:87-88`）类型为 `DuplicateGovernancePolicy`，`__post_init__` 校验类型（line 101-106）。`dispatch.py:2692-2694` 传递 `tooling_options.duplicate_governance_policy` 到 `ToolRuntimeBuildRequest`，由 `DefaultToolRuntimeFactory` 构造 `InMemoryAttemptDuplicateGovernance(request.duplicate_governance_policy)`。

**无 run-scoped registry/clear 生命周期残留：** grep 确认 `dispatch.py` 中无 `_duplicate_governance_registry`、`clear_run()`、`clear_all()` 调用。Scheduler 不再持有或清理 duplicate registry。

### 6. TOOL_CALL_GOVERNED Payload / Tool Trace / Diagnostic 一致性

**通过。** 三个维度一致：

- **EventLog payload**: `_append_tool_call_governed_if_needed()`（`tool_runtime.py:3116-3118`）写入 `"duplicate_scope": {"kind": "attempt", "attempt_id": candidate.scope.attempt_id}`
- **Tool trace projection**: `tool_trace.py:482` 的 `_trace_summary` 读取 `_FIELD_DUPLICATE_SCOPE`；cold trace 也包含 duplicate_scope（`tool_trace.py:391-394` 测试断言）
- **Diagnostic message**: duplicate 决策的 `diagnostic_message` 为 `policy.messages.attempt_scope_diagnostic`（对 non-allow decisions）或 `policy.messages.prior_accept_missing`（对 durable-missing）

**accept barrier 测试验证：** `test_toolruntime_accept_barrier.py:505-508` 断言 `governed_payload["duplicate_scope"]["kind"] == "attempt"` 且 `attempt_id` 与 candidate 一致。

### 7. Worker / Host Restart Non-durable Behavior

**通过。** 测试 `test_fresh_toolruntime_handle_same_attempt_is_in_memory_non_durable_restart_behavior`（`test_toolruntime_duplicate_governance.py:804-837`）验证：新 `ToolRuntimeHandle` 即使 same `attempt_id`，也不继承旧内存 duplicate index；第二次调用执行 fresh request，`duplicate_decision=ALLOW`，`reuse_prior_event_refs=()`。

**README 已明确表达：** `dayu/host/README.md:231` 写清 "新 Attempt、worker restart 或 Host restart 不继承旧内存索引"。

### 8. README 和 Tests/README 职责合规

**通过。**

- `dayu/host/README.md:231-232`：新增 attempt-local in-memory duplicate governance 语义、typed policy 配置说明和 non-durable 行为描述。符合 Host 开发手册职责。
- `tests/README.md:130`：coverage 描述中包含 "attempt-scoped duplicate key / in-flight owner-waiter 串行化 / cross-Attempt fresh request / worker restart in-memory non-durable behavior / trace scope projection"。符合测试手册职责。
- 根 `README.md` 和 `dayu/README.md` 无需更新（未改变用户可见 CLI、分层边界）。

### 9. 术语 grep 结果

**通过。** `run-local`/`run-scoped`/`RunScoped`/`RunLocal`/`同 Run` 在 `dayu/host/` 和 `tests/host/` 中的残留：

- `truncation cursor` 相关（`tool_runtime.py:7,791,1129,1294,1736,2736`）：与 duplicate governance 无关，属于 allowed truncation wording
- `reactive compaction token`（`dayu/host/README.md:278`）：`run-local token` 指 Engine envelope 的取消 token，与 duplicate governance 无关
- `test_local_proxy_engine_ingest.py` 中的 `"run-local"` 是测试数据字符串 id
- `dayu/host/api.py:734` 的 `run-scoped truncation manager` 注释：与 duplicate governance 无关

**无 duplicate governance 的 run-scoped/run-local 术语残留。**

### 10. 未引入项确认

| 检查项 | 结果 |
|---|---|
| durable ledger | 未引入；`InMemoryAttemptDuplicateGovernance` 只维护内存 dict |
| EventLog 重建 duplicate refs | 未引入；prior refs 从内存 accepted entry 获取 |
| schema change | 无 SQLite schema change；`TOOL_CALL_GOVERNED` payload 是 additive 字段 |
| compat wrapper/re-export | 无；旧 `RunScopedDuplicateGovernanceRegistry` 等全部删除 |
| `Any`/`object`/无类型签名 | 无；`tool_duplicate_governance.py` 所有签名明确 |
| 分层反向依赖 | 无；`tool_duplicate_governance.py` 只依赖 `dayu.contracts` 和 `dayu.host.durable.codec` |
| 过度耦合 | 无；duplicate governance 独立 typed module，不依赖 scheduler、accept barrier 或 Engine |

## Open Questions

无。Control doc 中 `RR-TOOL-01`（awaiting fanout 更宽并发治理）已 deferred-with-owner，不在 WU-TOOL-01 scope。`RR-TOOL-02`（tool trace duplicate scope 透传）已在 Slice 3 完成。

## Verification

```bash
# Target tests: 123 passed
source .venv/bin/activate
python -m pytest tests/host/test_toolruntime_duplicate_governance.py \
  tests/host/test_toolruntime_diagnostics.py \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_dispatch_scheduler.py \
  tests/host/test_tooling_options.py -x -q
# Result: 123 passed in 1.22s

# Pyright: 0 errors, 0 warnings, 0 informations
# Result: clean

# Terminology grep: run-local/run-scoped/同 Run
# Result: allowed truncation cursor / reactive compaction / test data id only
```

## Residual Risks

| ID | 描述 | 状态 |
|---|---|---|
| RR-TOOL-01 | awaiting fanout 更宽并发治理 | deferred-with-owner（control doc 已有条目） |

无新增 residual risk。

## Conclusion

**Remaining blocking findings: 0.**

WU-TOOL-01 全部 4 个 slice 的实现正确地将 duplicate governance 从 run-scoped 改造为 attempt-scoped。关键属性：

1. duplicate key 包含 `attempt_id`；跨 Attempt 不继承，新 handle 不跨内存边界共享
2. in-flight owner/waiter 状态机在 `asyncio.Condition` 保护下正确实现，包括 owner 取消/异常/accept rejection/accept timeout 四种失败路径的 durable-missing 通知
3. `allow`/`reuse`/`hint`/`require_justification`/`hard_stop` 五类决策语义通过 typed `DuplicateGovernancePolicy` 配置，无硬编码消息、无决策语义污染
4. `HostToolingOptions.duplicate_governance_policy` 作为 construction-time typed input 正确接入 dispatch 生产路径；scheduler 无 run-scoped registry 残留
5. `TOOL_CALL_GOVERNED` payload、tool trace `duplicate_scope` 和 diagnostic message 三处一致使用 `DuplicateGovernanceScope(kind="attempt")`
6. worker/Host restart non-durable behavior 有明确测试和 README 文档
7. 无 durable ledger、EventLog 重建、schema change、compat wrapper、`Any`/`object` 类型、分层反向依赖或过度耦合引入
8. 123 tests passed，pyright 0 errors，terminology grep 干净
