# Code Review — WU-TOOLS-AWAIT-FANOUT-01 Implementation

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-await-fanout-01`
- Base: `main`
- Output file: `docs/reviews/wu-tools-await-fanout-01-code-review-mimo.md`
- Included scope: dirty workspace diff of implementation files (`dayu/host/tool_duplicate_governance.py`, `dayu/host/tool_runtime.py`, `dayu/host/run_input.py`, `dayu/host/README.md`) and corresponding tests (`tests/host/test_toolruntime_duplicate_governance.py`, `tests/host/test_toolruntime_executor.py`, `tests/host/test_run_input_builder.py`)
- Excluded scope: controller flow record `docs/host/issues-implementation-control.md`（除非与实现冲突），implementation codex `docs/reviews/wu-tools-await-fanout-01-implementation-codex.md`（仅作实现参考）
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### Detailed Evidence Walkthrough

以下按 5 个重点审查维度展开走读，每个维度给出直接代码证据和结论。

---

#### 1. Accepted awaiting ack 后是否真正抑制 durable-missing cleanup

**走读路径**: `_execute_one` → `_accept_awaiting` → `_record_duplicate_awaiting_accepted` → `record_awaiting_accepted` → `finally`

**核心机制**:

1. `_execute_one` L2316-2321: 当 `duplicate_decision.kind is ALLOW` 且 `prior_event_refs` 为空时，`duplicate_owner_needs_terminal=True`。这是 owner 首次执行时的标准路径。

2. `_accept_awaiting` L2749-2760: 当 `accept_result` 是 `ToolAwaitingAcceptedAck` 时，调用 `_record_duplicate_awaiting_accepted`。该方法 L2960-2964 检查 `policy_decision.kind is ALLOW` 且 `duplicate_decision.kind is ALLOW` 后，调用 `self._duplicate_governance.record_awaiting_accepted(...)` 写入 `DuplicateAwaitingAcceptedEntry`。

3. `_accept_awaiting` 返回 `_AwaitingAcceptExecution(duplicate_terminal_recorded=True, ...)`。

4. `_execute_one` L2388-2395: `duplicate_terminal_recorded = awaiting_result.duplicate_terminal_recorded`（此时为 `True`），然后 `return awaiting_result.record`。

5. `finally` L2451-2455: 条件 `duplicate_owner_needs_terminal and not duplicate_terminal_recorded` → `True and not True` → `False`，跳过 `record_durable_missing`。

6. `InMemoryAttemptDuplicateGovernance.record_awaiting_accepted` L531-543: 把 `_InFlightDuplicateRecord` 状态设为 `AWAITING_ACCEPTED`，写入 `awaiting_entry`，唤醒等待者。

7. `InMemoryAttemptDuplicateGovernance.record_durable_missing` L559-567: 即使被调用，L561-564 检查 `in_flight.state is AWAITING_ACCEPTED` 时 put back 并 return，不覆盖 accepted awaiting 状态。

**结论**: accepted awaiting ack 后，`finally` 确实被抑制；即使 `record_durable_missing` 被意外调用，也有第二道防线。

**Rejected/Timeout 路径**:

- `_accept_awaiting` L2769-2779: 当 `accept_result` 不是 `ToolAwaitingAcceptedAck` 时，返回 `_AwaitingAcceptExecution(duplicate_terminal_recorded=False, durable_missing_reason=...)`。
- `_durable_missing_reason_for_awaiting_accept_result` L5668-5679: `ToolAwaitingRejectedAck` → `HOST_ACCEPT_REJECTED`，`ToolAwaitingAcceptTimedOut` → `HOST_ACCEPT_TIMEOUT`。
- `finally` 条件成立，调用 `record_durable_missing`，waiter 重新竞争 owner。

---

#### 2. AWAITING_FANOUT 是否只是 Host internal / attempt-local 防御分支

**走读路径**: `DuplicateDecisionKind.AWAITING_FANOUT` → `_decision_for_awaiting_entry` → `_awaiting_fanout_record`

1. `DuplicateDecisionKind.AWAITING_FANOUT` 是 `StrEnum` 成员，值为 `"awaiting_fanout"`。`DuplicateGovernanceMessages.awaiting_fanout` 提供中文说明。

2. `InMemoryAttemptDuplicateGovernance._decision_for_awaiting_entry` L604-632: 当 in-flight 状态为 `AWAITING_ACCEPTED` 时，返回 `AWAITING_FANOUT` 决策，`prior_outcome=None`，`prior_awaiting_outcome` 有值，`prior_wait_id` 有值。互斥语义正确。

3. `_awaiting_fanout_record` L2781-2797: 返回 `BatchToolExecutionRecord(outcome=duplicate_decision.prior_awaiting_outcome)`。不 dispatch 业务 callable，不提交 awaiting accept candidate。

4. `_execute_one` L2331-2335: `AWAITING_FANOUT` 在 `duplicate_governed=False` 之前 early return，不进入后续业务执行路径。

5. 无 durable follower ledger、wait alias schema、跨 Attempt duplicate table 或 public await contract 被引入。`DuplicateGovernancePort.record_awaiting_accepted` 是 attempt-scoped Protocol 方法。

6. `ToolAwaitingOutcome` 来自 `dayu.contracts.tool_outcome`，是已有的公共类型，未引入新依赖。

**结论**: `AWAITING_FANOUT` 确实只是 Host internal / attempt-local 防御分支。当前 production path 中同批后续 calls 被 `run_suspended_by_tool_awaiting` 截断，不会命中此分支。

---

#### 3. 当前 batch 行为是否保持

**走读路径**: `ToolRuntimeExecutor.execute` → `run_suspended_by_awaiting` flag

1. `execute` L2254-2278: `run_suspended_by_awaiting` 初始 `False`。循环中 L2274 调用 `_execute_one`，L2276 检查结果是否为 `ToolAwaitingOutcome`，是则 L2277 设 flag 为 `True`。

2. 下次循环 L2256-2273: flag 为 `True`，直接 append `run_suspended_by_tool_awaiting` governed failure，不调用 `_execute_one`。

3. 测试 `test_awaiting_outcome_stops_remaining_batch_calls` L1273-1330: 两个 batch calls，`callable_.call_count == 1`，`awaiting_accept_port.candidates` 只有 1 个，第二个 record 是 `ToolFailedOutcome` 且 `hint == "run_suspended_by_tool_awaiting"`。

4. 并发测试 `test_concurrent_duplicate_awaiting_fanout_does_not_start_second_job` L1144-1176: owner 和 waiter 是独立 execute 调用（不同 batch）。owner 进入 callable 后，waiter 命中 `AWAITING_FANOUT`，`callable_.call_count == 1`，`awaiting_accept_port.candidates` 只有 1 个。

**结论**: batch 行为完全保持。首个 awaiting 后剩余 calls 继续 `run_suspended_by_tool_awaiting`，不启动第二个 business job。

---

#### 4. RunInputBuilder resume wait material 是否自解释、不泄漏内部 ref

**走读路径**: `_resume_wait_message_from_current_start` L4018-4037

1. 现有投影保留：`tool_name=...`、`resolution_kind=...`、`tool_fact_kind=...`、`result=...`。

2. 追加 guidance L4028-4034: `"This wait result is the accepted result for the interrupted tool request. If the interrupted step made duplicate requests for the same tool with the same arguments, treat this same result as covering those duplicate requests. Do not call the same tool again only to obtain the same result."`

3. 测试 `test_resume_wait_message_appends_shared_duplicate_result_guidance` L383-446:
   - 断言 `"duplicate requests for the same tool with the same arguments"` in content
   - 断言 `"Do not call the same tool again only to obtain the same result."` in content
   - 断言以下内部 ref 不出现：`"wait-resume-private"`、`"tool-call-private"`、`"event-tool-result-resume"`、`"payload-ref-private"`、`"sha256:"`、`"attempt-current"`、`"execution-current"`

**结论**: resume material 自解释、足以表达 duplicate result sharing，且不泄漏任何内部 ref。

---

#### 5. 代码结构、状态机、并发等待、exception/finally 路径、Protocol/interface 扩展、README 同步、测试覆盖

**状态机**:

`_InFlightDuplicateState` 从 `OWNER_RUNNING | ACCEPTED | DURABLE_MISSING` 扩展为 `OWNER_RUNNING | ACCEPTED | AWAITING_ACCEPTED | DURABLE_MISSING`。转换路径：

- `OWNER_RUNNING → AWAITING_ACCEPTED`: `record_awaiting_accepted` 被调用时
- `OWNER_RUNNING → ACCEPTED`: `record_accepted` 被调用时（普通完成）
- `OWNER_RUNNING → DURABLE_MISSING`: `record_durable_missing` 被调用时
- `AWAITING_ACCEPTED` 不可被 `record_durable_missing` 覆盖（L561-564 guard）

`decide_duplicate` 中 L471-497: `OWNER_RUNNING` → wait，`ACCEPTED` → 返回 accepted entry 决策，`AWAITING_ACCEPTED` → 返回 fanout 决策，`DURABLE_MISSING` → continue 重新竞争。

**并发**: `asyncio.Condition` 保护所有状态转换。`decide_duplicate` 中 `while in_flight.state is OWNER_RUNNING: await condition.wait()` 确保 waiter 在 owner 完成前阻塞。

**Exception/Finally**: 已在维度 1 中完整走读。callable 异常时 `durable_missing_reason=TOOL_EXCEPTION`，不经过 awaiting accept path。

**Protocol 扩展**: `DuplicateGovernancePort` 新增 `record_awaiting_accepted` 方法，`DuplicateDecision` 新增 `prior_awaiting_outcome` / `prior_wait_id` 可选字段。所有新增都遵循 frozen dataclass + Protocol 模式。

**README 同步**: `dayu/host/README.md` L592 新增 `AWAITING_FANOUT` 枚举说明和 terminal marker 描述。符合 README 更新触发条件（`dayu/host/` 修改）和 `tests/README.md` 无需更新（测试结构未变）。

**测试覆盖**:

| 测试文件 | 新增/更新 | 覆盖行为 |
|---|---|---|
| `test_toolruntime_duplicate_governance.py` | +3 tests | awaiting accepted terminal marker、multiple waiter fanout、durable-missing owner handoff |
| `test_toolruntime_executor.py` | +3 tests, 4 updated | accepted 不调 durable-missing、rejected/timeout 调 durable-missing、concurrent fanout 不启第二 job、batch 停止行为 |
| `test_run_input_builder.py` | +1 test | resume message 追加 guidance 且不泄漏 ref |

## Open Questions

无。

## Tests / Validation Checked

- `pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py`: **160 passed**
- `pytest tests/host/test_wait_awaiting_accept.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_public_resolve_wait_resume.py`: **22 passed**
- Total: **182 passed**
- `pyright`: **0 errors, 0 warnings, 0 informations**
- Implementation artifact claims "182 passed" and "0 errors": **verified**

## Residual Risk

1. **Engine alias confirmation**: 当前 Host ToolRuntime 尚未证明会产生 alias awaiting records 到 Engine ingest。`engine_ingest.py` 的 `tool_call_id` 严格匹配逻辑未被测试触及。如果 future work 让同 batch 多个 calls 都提交 awaiting accept candidate（而非当前 `run_suspended_by_tool_awaiting` 截断），Engine ingest 可能需要处理 alias。当前 WU 正确地不触及此路径。

2. **`record_awaiting_accepted` best-effort**: `_record_duplicate_awaiting_accepted` 失败时（L2960-2964 guard 或 L2965 `record_awaiting_accepted` 抛异常），`duplicate_terminal_recorded` 返回 `False`，`finally` 仍会调用 `record_durable_missing`。但 Host durable truth（wait record、Run WAITING 状态）已成立，attempt-local 内存状态误标 `DURABLE_MISSING` 只影响同 Attempt 后续 waiter——而这些 waiter 已被 `run_suspended_by_tool_awaiting` 截断。实际影响极低。

3. **Cross-Attempt durable duplicate ledger**: 设计真源明确不引入。如果 future recovery / retry 场景需要跨 Attempt 复用 awaiting 结果，需另起 WU。

## Conclusion

**PASS**

0 blocking findings。实现正确对齐 accepted plan `docs/host/wu-tools-await-fanout-01-plan.md` 和 controller adjudication。核心修复（accepted awaiting 后不误记 durable-missing）通过 attempt-local `AWAITING_ACCEPTED` terminal marker 实现，有两道防线（`finally` 抑制 + `record_durable_missing` guard）。`AWAITING_FANOUT` 保持为防御性 Host internal state，未引入 durable schema、public contract 或 Engine ingest 变更。batch 行为、resume material、README 同步、测试覆盖和 pyright 均验证通过。
