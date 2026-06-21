# WU-TOOLS-AWAIT-FANOUT-01 Code Review — AgentDS

## Gate

- Work unit: `WU-TOOLS-AWAIT-FANOUT-01` / GitHub Issue #111
- Gate: `code review`
- Accepted plan: `docs/host/wu-tools-await-fanout-01-plan.md` (commit `29b211d7`)
- Implementation artifact: `docs/reviews/wu-tools-await-fanout-01-implementation-codex.md`
- Slice: `S1 轻量 awaiting cleanup terminal marker`

## Scope

- Mode: current changes (dirty workspace on branch `phase/wu-tools-await-fanout-01`)
- Base: `main`
- Included scope: all dirty production files (`dayu/host/tool_duplicate_governance.py`, `dayu/host/tool_runtime.py`, `dayu/host/run_input.py`, `dayu/host/README.md`) and test files (`tests/host/test_toolruntime_duplicate_governance.py`, `tests/host/test_toolruntime_executor.py`, `tests/host/test_run_input_builder.py`)
- Excluded scope: `docs/host/issues-implementation-control.md` gate state changes (controller-expected process record), `docs/reviews/wu-tools-await-fanout-01-implementation-codex.md` (review target, not part of diff)
- Sources of truth consulted:
  - `docs/host/design.md`
  - `docs/engine/design.md`
  - `docs/host/wu-tools-await-fanout-01-plan.md`
  - `docs/reviews/wu-tools-await-fanout-01-plan-rereview-controller-adjudication.md`
  - `dayu/host/README.md` Agent更新约束
  - `tests/README.md`

## Conclusion

**PASS** — 0 blocking findings. 实现符合 accepted plan，轻量约束保持，无重型 durable 设计回流，字段互斥成立。发现 1 个 medium-severity 结构健壮性问题和 2 个 low-severity 问题，均不阻塞 merge。

## Findings

### F-DS-01-未修复-中-`_execute_one` finally 路径中 `durable_missing_reason` 默认值在 awaiting accepted 成功后未显式重置

- **入口/函数**: `ToolRuntimeExecutor._execute_one` (line 2280)，`finally` block (line 2450-2455)
- **文件(行号)**: `dayu/host/tool_runtime.py:2321, 2388-2394, 2450-2455`
- **输入场景**: owner 的 `_accept_awaiting` 返回 `ToolAwaitingAcceptedAck`，`_record_duplicate_awaiting_accepted` 正常返回 True，但随后 `record_awaiting_accepted(...)` 调用在持有 condition 锁时抛出未预期异常（如 asyncio.CancelledError 在 await 点被触发）
- **实际分支**: 
  - line 2321: `durable_missing_reason = DuplicateDurableMissingReason.GOVERNED_BEFORE_ACCEPT`
  - line 2388-2389: `duplicate_terminal_recorded = awaiting_result.duplicate_terminal_recorded` — 若 `_record_duplicate_awaiting_accepted` 本身抛异常，这行不执行
  - line 2391: `if awaiting_result.durable_missing_reason is not None:` — 成功路径的 `awaiting_result.durable_missing_reason` 固定为 None（line 2767），条件不成立
  - `durable_missing_reason` 保持 line 2321 的 `GOVERNED_BEFORE_ACCEPT`
  - finally (line 2451): `duplicate_owner_needs_terminal=True`（line 2316-2319），`duplicate_terminal_recorded=False`（异常跳过）→ 调用 `record_durable_missing(duplicate_request, GOVERENED_BEFORE_ACCEPT)`
- **预期行为**: 若 owner 已被 Host accepted awaiting，duplicate cleanup 不得写入 durable-missing（除非明确的 rejected/timeout）；异常路径的 cleanup reason 应反映实际状态
- **实际行为**: `finally` 使用 `GOVERNED_BEFORE_ACCEPT` 作为 fallback，与"owner 已 accepted awaiting"的事实状态不一致。`record_durable_missing` 内部的 `AWAITING_ACCEPTED` guard（`tool_duplicate_governance.py:561-564`）无法保护此路径，因为 `_record_duplicate_awaiting_accepted` 抛异常时 `record_awaiting_accepted` 尚未被调用，in-flight 状态仍为 `OWNER_RUNNING`
- **直接证据**: 
  - line 2321 初始化 `durable_missing_reason = GOVERNED_BEFORE_ACCEPT`
  - line 2391 的条件 `if awaiting_result.durable_missing_reason is not None` 在成功路径（`durable_missing_reason=None`）不更新变量
  - line 2767 固定写 `durable_missing_reason=None`
  - `_record_duplicate_awaiting_accepted` (line 2941) 无 try/except，异常直接传播
- **影响**: 在极端并发取消或 condition 异常场景下，已 accepted awaiting 的 owner 可能被错误标记为 durable-missing，后续 waiter 重新竞争 owner 并可能启动第二个 external job。当前 production path 中此场景极难触发（需在 holding condition lock 的 await 点收到取消信号），但结构上存在 state inconsistency 窗口
- **建议改法和验证点**: 
  - 在 `_accept_awaiting` 中，`_record_duplicate_awaiting_accepted` 调用应包裹 best-effort catch（类似 `_record_duplicate_durable_missing_best_effort` 的异常处理模式），确保 owner 的 accepted awaiting durable truth 不被内存索引异常回滚
  - 或：将 `durable_missing_reason` 的更新从条件式 `if ... is not None` 改为无条件赋值（当 `awaiting_result` 被成功构造时，它的 `durable_missing_reason` 就是权威值），这消除了"None 表示不更新"的隐式语义
  - 验证点：注入 `record_awaiting_accepted` 调用抛异常的场景，确认 finally 不调用 `record_durable_missing` 或使用正确 reason
- **修复风险（低）**: 只影响异常路径，正常路径行为不变。修改应遵循现有 best-effort cleanup 模式
- **严重程度（中）**: 理论上的 state inconsistency 窗口；当前 production path 极难触发（需在持锁 await 点收到取消），但结构上存在 correctness risk；plan §8 明确要求 "`record_awaiting_accepted` 本身失败，按现有 cleanup 风格处理为 best-effort diagnostic；不得覆盖 owner 已 accepted awaiting 的原始返回"

---

### F-DS-02-未修复-低-`_awaiting_fanout_record` 丢弃 duplicate 诊断引用

- **入口/函数**: `ToolRuntimeExecutor._awaiting_fanout_record` (line 2781)
- **文件(行号)**: `dayu/host/tool_runtime.py:2330-2335, 2781-2797`
- **输入场景**: 并发 `execute()` 调用的第二个 waiter 命中 `AWAITING_FANOUT` 决策
- **实际分支**: 
  - line 2330: `duplicate_refs = self._diagnostic_refs_for_duplicate(duplicate_decision)` — 对 `AWAITING_FANOUT` kind 发出诊断 ref
  - line 2331-2335: 检测到 `AWAITING_FANOUT`，立即调用 `_awaiting_fanout_record` 并返回
  - `_awaiting_fanout_record` (line 2781-2797): 只返回 `BatchToolExecutionRecord`，不接收、不存储、不投影 `duplicate_refs`
- **预期行为**: diagnostic ref 在 Tool Trace 中可查询，或在 batch record 中以某种方式携带
- **实际行为**: diagnostic ref 被 `DeterministicToolTraceDiagnosticEmitter.emit()` 计算但丢弃；`InMemoryToolTraceDiagnosticEmitter` (测试用) 会存储但 production `DeterministicToolTraceDiagnosticEmitter` 不存储
- **直接证据**: line 2330 的 `duplicate_refs` 变量在 line 2332 的 `return` 后不再被引用；`_awaiting_fanout_record` 的签名不接收 diagnostic refs
- **影响**: 防御性 `AWAITING_FANOUT` 路径在 production Tool Trace / diagnostic 中不可见；排查并发 fanout 行为时缺少直接诊断证据
- **建议改法和验证点**: 
  - 将 `duplicate_refs` 传入 `_awaiting_fanout_record` 或由调用方在 return 前完成 diagnostic 记录
  - 或：明确 `AWAITING_FANOUT` 的 diagnostic 已由 Engine waiting event → Host ingest 路径间接覆盖，并将此判断记录为显式决策
- **修复风险（低）**: 仅影响 diagnostic/trace 可见性，不改变执行语义
- **严重程度（低）**: 不影响 correctness；plan 要求的 "bounded diagnostic" 在代码中已发射，只是未被消费

---

### F-DS-03-未修复-低-`record_durable_missing` 的 `AWAITING_ACCEPTED` guard 缺少直接单元测试

- **入口/函数**: `InMemoryAttemptDuplicateGovernance.record_durable_missing` (line 545)
- **文件(行号)**: `dayu/host/tool_duplicate_governance.py:561-564`
- **输入场景**: `record_durable_missing(request, reason)` 在 in-flight 状态为 `AWAITING_ACCEPTED` 时被调用
- **实际分支**: line 561-564: `if in_flight.state is _InFlightDuplicateState.AWAITING_ACCEPTED: self._state.in_flight_by_key[duplicate_key] = in_flight; self._state.condition.notify_all(); return`
- **预期行为**: `AWAITING_ACCEPTED` 记录应被保护，不被 durable-missing 覆盖
- **实际行为**: 代码正确 guard，但无直接测试证明该 guard 在单元级生效
- **直接证据**: 
  - `test_toolruntime_duplicate_governance.py` 无直接测试 `record_durable_missing` 对 `AWAITING_ACCEPTED` 记录的作用
  - `test_durable_missing_still_reopens_owner_competition` (line 1468) 测试的是 `OWNER_RUNNING` → `DURABLE_MISSING` 后 waiter 重新竞争，不涉及 `AWAITING_ACCEPTED`
  - executor 测试通过 monkeypatch 间接触达此 guard，但 monkeypatch 替换了 `record_durable_missing` 本身，不执行 guard 代码
- **影响**: guard 路径未经单元级回归保护；若未来 refactor 改变 state pop/re-insert 逻辑，guard 可能被绕过
- **建议改法和验证点**: 在 `test_toolruntime_duplicate_governance.py` 新增测试：owner → `record_awaiting_accepted` → `record_durable_missing(reason)` → 验证后续 `decide_duplicate` 仍返回 `AWAITING_FANOUT`（而非重新竞争 owner）
- **修复风险（低）**: 纯测试补充，不修改生产代码
- **严重程度（低）**: guard 逻辑简单且 executor 测试间接验证了正确行为（accepted awaiting 后 durable-missing 不被调用）；缺失的是对 guard 本身的防御性单元覆盖

---

## Open Questions

1. `_record_duplicate_awaiting_accepted` 方法（line 2941）构造 `HostEventRef` 时从 `accepted_ack.accepted_event_refs` 逐字段映射（line 2968-2973）。`accepted_ack` 的类型是 `ToolAwaitingAcceptedAck`，其 `accepted_event_refs` 的类型应为 `tuple[ToolAwaitingEventRef, ...]`。当前代码假设 `ToolAwaitingEventRef` 有 `event_id` 和 `event_sequence` 字段。pyright 通过表明类型兼容，但若 `ToolAwaitingEventRef` 未来增加必填字段，此处需要同步更新。是否需要在此处使用 `ToolAwaitingEventRef` 的 `to_host_event_ref()` 方法（如果存在），或用类型保护确保字段完整性？

## Tests / Validation Checked

| 验证项 | 结果 | 证据 |
|---|---|---|
| pytest 182 passed (focused suites) | ✅ | implementation artifact reports 182 passed in 1.35s |
| pyright 0 errors | ✅ | implementation artifact reports 0 errors, 0 warnings, 0 informations |
| `record_awaiting_accepted` 实现/调用方一致 | ✅ | Protocol → `InMemoryAttemptDuplicateGovernance` → `ToolRuntimeExecutor._record_duplicate_awaiting_accepted` 链路一致 |
| `prior_outcome` vs `prior_awaiting_outcome` 字段互斥 | ✅ | `_decision_for_accepted_entry`: prior_outcome set, prior_awaiting_outcome=None; `_decision_for_awaiting_entry`: prior_outcome=None, prior_awaiting_outcome set; `_allow_decision`: both None |
| `AWAITING_ACCEPTED` / `AWAITING_FANOUT` attempt-local, Host internal | ✅ | 存于 `_AttemptDuplicateGovernanceState.in_flight_by_key`（纯内存）；无 durable schema 变更；无 public contract 新增 |
| 无重型 durable 设计回流 | ✅ | 未修改 `engine_ingest.py`、durable schema/state、wait adapter activation contract、public API |
| accepted 不 cleanup | ✅ | `test_awaiting_outcome_returns_only_after_awaiting_accepted_ack` 断言 `recorded_reasons == []` |
| rejected/timeout cleanup | ✅ | 两个测试各自断言 `recorded_reasons == [HOST_ACCEPT_REJECTED]` 和 `[HOST_ACCEPT_TIMEOUT]` |
| 多 waiter defensive fanout | ✅ | governance 级 `test_record_awaiting_accepted_fans_out_multiple_waiters`；executor 级 `test_concurrent_duplicate_awaiting_fanout_does_not_start_second_job` |
| batch truncation behavior | ✅ | `test_awaiting_outcome_stops_remaining_batch_calls` 断言 call_count==1, 1 candidate, second call governed |
| resume material non-leakage | ✅ | 测试检查 7 类内部 ref 不在 message 中 |
| durable-missing 仍释放 waiter 重新竞争 | ✅ | `test_durable_missing_still_reopens_owner_competition` 直接覆盖 |
| README 更新在职责边界内 | ✅ | `dayu/host/README.md` 仅新增 `AWAITING_FANOUT` 决策说明与 terminal marker 一句；无过程/状态泄漏 |
| tests/README.md 不更新合理 | ✅ | 测试结构/约定未变，不触发 README 更新 |
| pyright/typing/docstring 约束 | ✅ | 新增类型均有完整注解；新增函数/类均有中文 docstring |
| LLM-facing 文本约束 | ✅ | resume material 不泄漏 `wait_id`/`tool_call_id`/EventLog id/payload ref/digest/Attempt id；`awaiting_fanout` message 为业务可读中文 |

## Residual Risks

| Risk | Severity | Status | Owner |
|---|---|---|---|
| `_record_duplicate_awaiting_accepted` 异常传播可能导致 `finally` 用错误 reason 清理（F-DS-01） | Medium | Open | WU-TOOLS-AWAIT-FANOUT-01 |
| `AWAITING_FANOUT` 诊断 ref 丢弃导致 production 不可见（F-DS-02） | Low | Open | WU-TOOLS-AWAIT-FANOUT-01 |
| `record_durable_missing` 的 `AWAITING_ACCEPTED` guard 无直接单元覆盖（F-DS-03） | Low | Open | WU-TOOLS-AWAIT-FANOUT-01 |
| Engine ingest alias awaiting confirmation 未修改/未测试 | Info | deferred-with-owner | Future Engine/ToolRuntime concurrency work unit; 当前无 direct evidence 证明 path reachable |
| 未来 Engine/ToolRuntime 并发模型可能使 `AWAITING_FANOUT` 成为 production reachable | Info | deferred-with-owner | Future Engine/ToolRuntime concurrency work unit; 当前 batch behavior (`run_suspended_by_tool_awaiting`) 阻止此路径 |
| Resume material test 用硬编码 ref 字符串检查，若新增 ref 类型需同步更新 | Low | Informational | 测试维护者；当前覆盖充分 |

## 裁决摘要

实现严格对齐 accepted plan (`docs/host/wu-tools-await-fanout-01-plan.md`)。核心修复链路完整：`record_awaiting_accepted` → `AWAITING_ACCEPTED` terminal marker → `finally` cleanup 抑制 → 多 waiter 防御性 fanout。轻量约束保持，无 durable schema/public contract/Engine ingest 扩张。字段互斥 `prior_outcome` vs `prior_awaiting_outcome` 在全部三个决策构造点成立。测试覆盖 accepted/rejected/timeout/多 waiter/batch truncation/resume leakage 六个关键维度。0 blocking findings。

三个非阻塞 findings 均可在后续 fix gate 或 follow-up 中处理：F-DS-01（finally 默认 reason 在异常路径不一致）为最高优先级，建议在进入 draft PR 前修复；F-DS-02（诊断 ref 丢弃）和 F-DS-03（guard 单元覆盖缺失）为 low severity，可作为 deferred 或 quick fix。
