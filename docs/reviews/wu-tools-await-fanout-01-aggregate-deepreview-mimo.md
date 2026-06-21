# WU-TOOLS-AWAIT-FANOUT-01 Aggregate Deepreview — AgentMiMo

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-await-fanout-01`
- Base: `main`
- Timestamp: 2026-06-21T15:23:13
- Output file: `docs/reviews/wu-tools-await-fanout-01-aggregate-deepreview-mimo.md`
- Included scope: branch 上相对 main 的完整变更，包括计划、实现、测试、README、控制文档与 review artifacts
- Excluded scope: 无
- Parallel review coverage: 无

## 验证记录

本次 deepreview 自行重跑验证命令：

```bash
source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_executor.py tests/host/test_run_input_builder.py tests/host/test_wait_awaiting_accept.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_public_resolve_wait_resume.py -q
```

结果：`184 passed in 1.27s`

```bash
source .venv/bin/activate && pyright
```

结果：`0 errors, 0 warnings, 0 informations`

## Findings

### 01-未修复-低-issues-implementation-control 当前状态表 WU 条目状态未同步

- **入口/函数**: `docs/host/issues-implementation-control.md` 当前状态表
- **文件(行号)**: `docs/host/issues-implementation-control.md`（WU 表格行）
- **输入场景**: 审查控制文档当前状态表与详细 WU section 状态一致性
- **实际分支**: 当前状态表 `implementation status` 字段正确记录 `accepted-slice`；但 WU 表格中 `WU-TOOLS-AWAIT-FANOUT-01` 行的 `状态` 列仍为 `discussion-ready`
- **预期行为**: WU 表格状态应与详细 section 和当前状态表一致，更新为 `accepted-slice` 或 `review`
- **实际行为**: WU 表格状态为 `discussion-ready`，滞后于实际 gate 进度
- **直接证据**: `issues-implementation-control.md` 当前状态表 `implementation status` 记录 "accepted slice commit `2e5791c9` created ... awaiting aggregate deepreview"，但 WU 表格行仍显示 `discussion-ready`
- **影响**: 仅文档一致性；不阻塞实现正确性、测试覆盖或 gate 流程
- **建议改法和验证点**: 将 WU 表格行状态更新为 `accepted-slice`，与详细 section 和当前状态表对齐
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 逐维度审查

### 1. 轻量 await 约束 ✅ 满足

**直接证据**：

- 无 `durable follower ledger`：`dayu/host/durable/schema.py` 和 `dayu/host/durable/state.py` 无变更（`git diff main...HEAD -- dayu/host/durable/` 无输出）
- 无 `wait alias schema`：`host_wait_records` 表结构未变，无 follower / alias 列
- 无 `cross-Attempt duplicate table`：`InMemoryAttemptDuplicateGovernance` 仍是 attempt-local in-memory，无 durable 写入
- 无 `public await lifecycle contract`：`DuplicateGovernancePort.record_awaiting_accepted(...)` 是 Host internal protocol，不在 public API 导出
- 无 `issue-129 two-phase activation`：无 `engine_ingest.py` 变更（`git diff main...HEAD -- dayu/host/engine_ingest.py` 无输出），无 wait adapter activation 变更
- 无 `engine_ingest.py` 变更：确认 `git diff --name-only` 不含该文件

### 2. 核心行为 ✅ 满足

#### 2a. accepted awaiting ack 后不误记 durable-missing

**直接证据**：

- `_execute_one.finally`（`tool_runtime.py:2453-2458`）：`if duplicate_owner_needs_terminal and not duplicate_terminal_recorded` — 当 accepted ack 成功后，`_record_duplicate_awaiting_accepted` 返回 `True`，`duplicate_terminal_recorded=True`，finally 不调用 `record_durable_missing`
- `_accept_awaiting` accepted ack 路径（`tool_runtime.py:2752-2771`）：构造 `_AwaitingAcceptExecution(duplicate_terminal_recorded=True, durable_missing_reason=None)`
- `InMemoryAttemptDuplicateGovernance.record_durable_missing`（`tool_duplicate_governance.py:558-567`）：`AWAITING_ACCEPTED` guard — pop 后检查状态，若为 `AWAITING_ACCEPTED` 则 put 回并 return，不覆盖为 `DURABLE_MISSING`
- marker 写入失败 best-effort：`_record_duplicate_awaiting_accepted`（`tool_runtime.py:2981-3003`）try/except 包裹，异常时仍返回 `True`，不传播
- 测试：`test_awaiting_outcome_returns_only_after_awaiting_accepted_ack` 断言 `recorded_reasons == []`
- 测试：`test_awaiting_marker_failure_keeps_owner_outcome_and_suppresses_cleanup` 断言 marker 失败后 `recorded_reasons == []` 且 owner outcome 仍为 `ToolAwaitingOutcome`
- 测试：`test_durable_missing_preserves_awaiting_accepted_marker` 断言 guard 后 decision 仍为 `AWAITING_FANOUT`

#### 2b. rejected/timeout 仍 durable-missing

**直接证据**：

- `_accept_awaiting` rejected 路径（`tool_runtime.py:2773-2781`）：`durable_missing_reason = HOST_ACCEPT_REJECTED`，`duplicate_terminal_recorded=False`
- `_accept_awaiting` timeout 路径：`durable_missing_reason = HOST_ACCEPT_TIMEOUT`，`duplicate_terminal_recorded=False`
- finally 条件 `True and not False` → 调用 `record_durable_missing`
- 测试：`test_awaiting_accept_rejected_returns_governed_error` 断言 `recorded_reasons == [HOST_ACCEPT_REJECTED]`
- 测试：`test_awaiting_accept_timeout_returns_governed_error` 断言 `recorded_reasons == [HOST_ACCEPT_TIMEOUT]`

#### 2c. batch 后续 calls 仍 run_suspended_by_tool_awaiting

**直接证据**：

- `ToolRuntimeExecutor.execute`（`tool_runtime.py:2257-2273`）：`run_suspended_by_awaiting` 标志在首个 `ToolAwaitingOutcome` 后设为 `True`，后续 calls 直接返回 `run_suspended_by_tool_awaiting` governed failure
- 测试：`test_awaiting_outcome_stops_remaining_batch_calls` 断言 `callable_.call_count == 1`，second outcome 为 `ToolFailedOutcome` with `hint == "run_suspended_by_tool_awaiting"`

#### 2d. defensive AWAITING_FANOUT 不走 ordinary accepted result index

**直接证据**：

- `_execute_one`（`tool_runtime.py:2334-2338`）：`AWAITING_FANOUT` decision 在 `duplicate_governed` 之前 early return，不进入 `_accept_reuse` 或普通 accepted index 路径
- `_awaiting_fanout_record`（`tool_runtime.py:2784-2800`）：直接返回 `BatchToolExecutionRecord(outcome=duplicate_decision.prior_awaiting_outcome)`，不调用 accept port
- `DuplicateDecision` 互斥语义：`AWAITING_FANOUT` 设置 `prior_outcome=None`、`prior_awaiting_outcome` 有值；普通 accepted 设置 `prior_outcome` 有值、`prior_awaiting_outcome=None`
- 测试：`test_record_awaiting_accepted_marks_terminal_without_ordinary_reuse` 断言 `decision.prior_outcome is None`
- 测试：`test_concurrent_duplicate_awaiting_fanout_does_not_start_second_job` 断言 `callable_.call_count == 1`（waiter 不调用业务 callable）

### 3. Resume Material ✅ 满足

**直接证据**：

- `run_input.py:4028-4034`：在现有 `tool_name` / `resolution_kind` / `tool_fact_kind` / `result` 投影之后追加 shared duplicate result guidance
- guidance 文本："This wait result is the accepted result for the interrupted tool request. If the interrupted step made duplicate requests for the same tool with the same arguments, treat this same result as covering those duplicate requests. Do not call the same tool again only to obtain the same result."
- 不泄漏 `wait_id`：测试断言 `"wait-resume-private" not in message.content`
- 不泄漏 `tool_call_id`：测试断言 `"tool-call-private" not in message.content`
- 不泄漏 EventLog id：测试断言 `"event-tool-result-resume" not in message.content`
- 不泄漏 payload ref：测试断言 `"payload-ref-private" not in message.content`
- 不泄漏 digest：测试断言 `"sha256:" not in message.content`
- 不泄漏 attempt/execution：测试断言 `"attempt-current" not in message.content` 和 `"execution-current" not in message.content`
- 测试：`test_resume_wait_message_appends_shared_duplicate_result_guidance` 完整覆盖

### 4. Tests / README / Pyright ✅ 满足

#### Tests

验证矩阵覆盖：

| 测试文件 | 新增/更新测试 | 覆盖行为 |
|---|---|---|
| `test_toolruntime_duplicate_governance.py` | `test_record_awaiting_accepted_marks_terminal_without_ordinary_reuse` | awaiting marker 不污染普通 accepted index |
| | `test_record_awaiting_accepted_fans_out_multiple_waiters` | 多 waiter 共享同一 owner wait |
| | `test_durable_missing_preserves_awaiting_accepted_marker` | AWAITING_ACCEPTED guard 保留 marker |
| | `test_durable_missing_still_reopens_owner_competition` | 非 awaiting 的 durable-missing 仍释放竞争 |
| `test_toolruntime_executor.py` | `test_awaiting_outcome_returns_only_after_awaiting_accepted_ack`（更新） | accepted 后不调用 record_durable_missing |
| | `test_awaiting_marker_failure_keeps_owner_outcome_and_suppresses_cleanup` | marker 失败不覆盖 owner 返回 |
| | `test_awaiting_accept_rejected_returns_governed_error`（更新） | rejected 仍记 durable-missing |
| | `test_awaiting_accept_timeout_returns_governed_error`（更新） | timeout 仍记 durable-missing |
| | `test_concurrent_duplicate_awaiting_fanout_does_not_start_second_job` | 防御性 fanout 不启动第二个 job |
| | `test_awaiting_outcome_stops_remaining_batch_calls`（更新） | batch 截断 + 单一 accept candidate |
| `test_run_input_builder.py` | `test_resume_wait_message_appends_shared_duplicate_result_guidance` | resume material shared guidance + 不泄漏内部 ref |

#### README

- `dayu/host/README.md` 新增 `AWAITING_FANOUT` 决策描述，说明其为 Host internal 防御分支
- 更新 duplicate governance 段落描述，说明 accepted awaiting terminal marker 抑制 durable-missing cleanup
- 未写入 work unit 过程、测试清单、未来计划或 issue 状态
- 符合 `Agent更新约束`：duplicate governance section 已有完整决策枚举，新增实现行为说明是稳定开发者文档

#### Pyright

- 自行重跑：`0 errors, 0 warnings, 0 informations`

### 5. Aggregate 风险 ✅ 一致

#### 跨文档状态一致性

- `docs/host/wu-tools-await-fanout-01-plan.md`：plan 定义的状态机、行为边界、非目标和验收信号与实现一致
- `docs/host/issues-implementation-control.md`：详细 WU section 正确记录所有 gate artifacts 和验证结果；当前状态表 `implementation status` 正确。WU 表格行状态有轻微滞后（Finding 01）
- `docs/host/design.md`：未触及；当前设计真源已支持轻量方案
- `docs/engine/design.md`：未触及；Engine 不涉及
- `docs/reviews/wu-tools-await-fanout-01-code-rereview-controller-adjudication.md`：PASS，DS-F01/F03 closed，DS-F02 deferred
- `docs/reviews/wu-tools-await-fanout-01-fix-codex.md`：fix 正确处理 DS-F01 和 DS-F03
- `docs/reviews/wu-tools-await-fanout-01-code-rereview-mimo.md`：PASS，0 findings
- `docs/reviews/wu-tools-await-fanout-01-code-rereview-ds.md`：PASS，0 findings
- `docs/reviews/wu-tools-await-fanout-01-implementation-codex.md`：S1 完成，stop conditions 无触发

#### Residual Risks

| 风险 | 严重程度 | 状态 | Owner |
|---|---|---|---|
| `AWAITING_FANOUT` 仍为防御性 Host-internal state，当前 batch 截断后不触发 | Low | Accepted residual | 未来并发 WU 若使 fanout 成为 production reachable 路径，必须重访 diagnostic visibility 和 Engine ingest alias semantics |
| marker 写入失败后 attempt-local marker 可能缺失 | Low | Accepted residual | Host durable truth 已成立；跨并发 waiter 强可观测恢复应另起独立 WU |
| DS-F02（diagnostic refs 丢弃）未处理 | Low | Deferred | 不阻塞本 WU core correctness |
| `asyncio.CancelledError` 在 marker 写入 await 点传播后 finally 执行 cleanup | Low | Accepted residual | CancelledError 是任务生命周期事件，cleanup 行为合理 |

## Open Questions

无。

## Conclusion

**PASS** — 0 blocking findings。

本次 deepreview 自行重跑 focused tests `184 passed` 和 pyright `0 errors`，结果与 controller 已有验证一致。

所有五个审查维度均满足：

1. **轻量 await 约束**：未重新引入 durable follower ledger、wait alias schema、cross-Attempt duplicate table、public await lifecycle contract 或 issue-129 two-phase activation。
2. **核心行为**：accepted awaiting ack 后不误记 durable-missing；rejected/timeout 仍 durable-missing；batch 后续 calls 仍 run_suspended_by_tool_awaiting；defensive AWAITING_FANOUT 不走 ordinary accepted result index。
3. **Resume material**：shared duplicate result guidance 自解释，不泄漏 wait id / tool call id / event id / payload ref / digest / attempt / execution。
4. **Tests / README / Pyright**：验证矩阵充分，README 更新边界合理，类型 / docstring / LLM-facing 文本约束满足。
5. **Aggregate 风险**：跨文档状态一致（仅 WU 表格行状态轻微滞后），residual risks 已记录且均有 owner。

唯一 finding 为 `issues-implementation-control.md` WU 表格行状态未同步到 `accepted-slice`，严重程度低，不阻塞 gate。
