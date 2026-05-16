# Phase 7 Aggregate Exit Review + P7-S5 Code Review

日期：2026-05-16

## Scope

- Mode: current changes (P7-S5) + Phase 7 aggregate exit
- Branch: feat/host-phase7-tool-awaiting-resolve-wait
- Base: main
- Output file: docs/reviews/host-phase7-aggregate-review-s5-mimo-20260516.md
- Included scope: P7-S5 uncommitted changes + Phase 7 S1~S4 accepted commits 全量 exit criteria 验证
- Excluded scope: Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model
- Parallel review coverage: 无

## P7-S5 Findings

未发现实质性问题。

### 1. P7-S5 plan 对齐

P7-S5 目标为 "Integration, Docs, Gate Validation"。实现交付：

- `tests/host/test_phase7_waiting_integration.py`：新增 `test_local_awaiting_tool_manual_resolve_resumes_run`，覆盖本地 awaiting tool → Host wait record → WAITING → manual resolve_wait → resumed Run 集成路径。
- `dayu/host/README.md`：同步 WAITING cancel、resolve_wait request shape、late diagnostic、poller、Engine awaiting diagnostic boundary。

Plan 要求 "local awaiting tool -> WAITING -> manual/poll resolve -> resumed run 的集成证明"。manual resolve 由新增集成测试覆盖；poll resolve 已有 `test_wait_adapter_polling.py::test_poll_adapter_ready_result_resolves_wait` 覆盖。README 只描述当前已实现事实，无 "未来设计" 内容。

### 2. integration test 质量

`test_local_awaiting_tool_manual_resolve_resumes_run` 是真实端到端测试：

1. 创建 active Run（`_seed_active_integration_run`）
2. 构造真实 `DefaultToolRuntimeFactory` + `EffectiveToolBundleBuilder` + `WaitAdapterRegistry`
3. 执行 `_AwaitingBusinessTool`（返回 `ToolAwaitingOutcome`）
4. 验证 ToolRuntime accept path 创建 wait record、Run 进入 WAITING、Attempt 进入 SUSPENDED
5. 调用 public `resolve_wait(source=manual)` 恢复 Run
6. 验证 resume RunInputBuilder 重建 accepted wait/tool fact system message

测试复用 `test_resolve_wait_command.py` 的 helper（`_SeededWaitingRun`、`_build_resume_request`、`_completed_request`、`_options`、`_read_wait`、`_seed_active_run`），这是合理的代码复用，不违反分层规则。所有 import 均为 `dayu.host` 包根或 `dayu.host.durable` 内部模块（集成测试需要验证 durable state），符合项目测试惯例。所有函数和类均有完整中文 docstring。

`test_phase7_resolve_wait_public_entry_is_importable` 是弱 smoke test，仅验证 `resolve_wait` 可从包根导入。价值有限但无害。

### 3. README 一致性

`dayu/host/README.md` 变更：

- `cancel_run` 描述更新：从 "WAITING 取消由 Phase 7 负责" 改为已实现的 WAITING cancel 行为 ✓
- `cancel_session_runs` 描述更新：从 "若存在 WAITING ... 返回 UNSUPPORTED_OPERATION" 改为支持 WAITING ✓
- `resolve_wait` 描述补充 `ResolveWaitRequest` 必须携带 UTC-aware `observed_at`、`source`、`idempotency_key` 与强类型 `outcome` envelope ✓
- 新增 Engine `TOOL_AWAITING` / `RUN_SUSPENDED` diagnostic confirmation 边界说明 ✓
- internal admission 描述更新：移除 "wait cancellation" 未实现标记 ✓

所有描述与当前代码事实一致，无残留旧术语。

`tests/README.md` 未更新，理由为 "本次没有新增测试层级或命令约定"。集成测试文件 `test_phase7_waiting_integration.py` 已在 P7-S3 的验证命令中被覆盖。合理。

### 4. 验证

- `pytest tests/host -q` → 389 passed ✓
- `python -m pyright dayu/ tests/ utils/` → 0 errors ✓
- `git diff --check` → 通过 ✓

---

## Phase 7 Aggregate Exit Review

### Exit Criteria 验证

Phase 7 退出条件（`implementation-control.md:887-891`）：

| 条件 | 状态 | 证据 |
|------|------|------|
| 长事务工具可以让 Run 进入 WAITING | ✅ | P7-S2: `ToolAwaitingOutcome` → wait record → WAITING/SUSPENDED |
| 由统一 `resolve_wait` 创建新 Attempt 继续 | ✅ | P7-S3: completed/cancelled → resume Attempt + dispatch; P7-S5 集成测试验证 |
| `ResolveWaitRequest.outcome_ref` 已被 typed envelope 替代 | ✅ | P7-S1: `ResolveWaitCompletedOutcome` / `FailedOutcome` / `CancelledOutcome` / `LostOutcome` |
| `observed_at` 类型明确 | ✅ | P7-S1: `datetime`，UTC-aware，`__post_init__` 校验 |
| lost outcome 与 wait record lost 状态区别 | ✅ | P7-S1: `ResolveWaitLostOutcome` vs `WaitRecordStatus.LOST` |
| `adapter_key` 来源明确 | ✅ | P7-S1: `WaitAdapterKey` typed ref，来自 `WaitAdapterRegistry` binding |
| `snapshot_ref` / `external_job_id` typed ref 约束 | ✅ | P7-S1: `HostPayloadRef` / `ExternalJobRef` typed dataclass |

### 验证要求验证

Phase 7 验证要求（`implementation-control.md:881-885`）：

| 要求 | 测试覆盖 |
|------|----------|
| wait record state machine | `test_wait_record_state.py` — schema / row codec / DDL CHECK / CAS helper |
| resolve_wait idempotency | `test_resolve_wait_command.py` — 同 key 同 digest 重放、同 key 不同 digest 冲突 |
| late result rejection | `test_wait_cancel_late_result.py` — CANCELLED/LOST late diagnostic、RESOLVED/FAILED 不同 key 不写 diagnostic |
| cancel-vs-resolve first-committer-wins | `test_wait_cancel_late_result.py` — cancel 后 resolve 写 late diagnostic |
| poll adapter observes cancelled wait and stops | `test_wait_adapter_polling.py` — cancelled wait → abandon，不调用 resolve_wait |
| late result writes diagnostic EventLog event | `test_wait_cancel_late_result.py` — WAIT_LATE_RESULT_REJECTED 事件验证 |
| integration: awaiting -> resumed local run | `test_phase7_waiting_integration.py` — 端到端 manual resolve |
| pyright: wait adapter modules | `python -m pyright dayu/ tests/ utils/` → 0 errors |
| docs: Host README wait/resume 语义同步 | README 已更新 WAITING cancel、resolve_wait、late diagnostic、poller、Engine diagnostic |

### Design Alignment 验证

`docs/host/design.md` §20 要求与实现对照：

| 设计要求 | 实现位置 | 状态 |
|----------|----------|------|
| ToolRuntime Host accept path 是 awaiting canonical owner | `waiting.py` `DefaultHostToolAwaitingAcceptPort` | ✅ |
| Engine tool_awaiting/run_suspended 不能创建 wait record | `engine_ingest.py` `_confirm_waiting_engine_event` — 只 diagnostic | ✅ |
| wait record 是 Host durable state index | `durable/state.py` host_wait_records schema + CAS helper | ✅ |
| resolve_wait 是短事务 command | `waiting.py` `resolve_wait` — single write transaction | ✅ |
| 幂等范围 (wait_id, idempotency_key) | `waiting.py` `_wait_resolution_scope` | ✅ |
| 同 key 同 outcome 重放，不同 outcome 冲突 | `waiting.py` `_resolve_in_transaction` + `_replay_terminal_resolution_or_none` | ✅ |
| cancelled/lost late result → WAIT_LATE_RESULT_REJECTED diagnostic | `waiting.py` `_reject_late_result` | ✅ |
| WAITING cancel → cancelled wait records + CANCELLED Run | `run_transition.py` `cancel_waiting_run_in_transaction` | ✅ |
| resume 是同一 Run 内新 Attempt | `run_transition.py` `resume_run_from_waiting_in_transaction` | ✅ |
| RunInputBuilder 从 EventLog canonical facts 重建 messages | `run_input.py` `_resume_wait_message_from_current_start` | ✅ |
| poll/callback/manual 都走同一 resolve_wait pipeline | `wait_adapter.py` `WaitPoller.poll_once` → `resolve_wait` | ✅ |

### 边界验证

Phase 7 范围（`implementation-control.md:849-850`）：

- 允许修改：wait record table/store ✅、wait adapter durable refs ✅、ToolAwaitingOutcome accept path ✅、resolve_wait command ✅、wait poller background adapter ✅、WAITING cancel/steer/resume ✅
- 禁止修改：外部系统专属 callback 服务 ✅（未实现）、复杂 job reconcile ✅（未实现）、强制外部 job cancel ✅（未实现）

未越界修改 Engine、contracts、fins、service、ui、recovery、outbox、audit、tool trace read-model。

### Non-goals 验证

Phase 7 non-goals（`phase7-plan.md:27-36`）：

| Non-goal | 状态 |
|----------|------|
| 不实现 HTTP callback endpoint | ✅ 未实现 |
| 不保证外部 job physical cancel | ✅ 未实现 |
| 不实现 RemoteProxy / remote worker 自治 resume | ✅ 未实现 |
| 不实现 retry / replay / steer / recovery dispatch | ✅ 未实现 |
| 不实现完整 tool trace projection / audit / read model | ✅ 未实现 |
| 不修改 Engine contract | ✅ 未修改 |
| 不把 adapter object / callable 放进 durable wait record | ✅ 只存 typed refs |
| 不做旧库兼容 | ✅ 全新 schema |

### Residual Risks

以下为 Phase 7 已知非目标，有明确 owner 或属于后续 phase：

1. **callback endpoint / auth / replay**：Phase 7 只预留 `callback` source 和 `resolve_wait` pipeline contract。Owner: 后续 phase。
2. **外部 job physical cancel / revoke**：adapter 只能 best-effort。Owner: 后续 adapter hardening。
3. **Engine contract 不携带 Host accepted wait refs**：P7 只能做 diagnostic confirmation，不能做强 matching-ref 校验。Owner: 后续 Engine contract 扩展。
4. **poller 后台调度循环 / 退避 / in-flight fencing**：当前只有 `poll_once()` 单轮。Owner: 后续 runtime hardening。
5. **recovery scan 对 WAITING Run 处理**：design §20 明确 "Host recovery scan 遇到 WAITING Run 时不得创建新 Attempt"。Owner: Phase 11。
6. **tool trace projection / late diagnostic 可观测性**：WAIT_LATE_RESULT_REJECTED diagnostic 已写入 EventLog，但无 read model 投影。Owner: Phase 8+ projection。

所有 residual risk 均有明确 owner 或属于已确认 non-goal，无无主风险。

---

## 结论

**P7-S5 PASS，Phase 7 Aggregate Exit PASS。**

P7-S5 集成测试提供了 local awaiting tool → WAITING → manual resolve → resumed run 的端到端证明。README 只描述当前事实。Phase 7 全部退出条件、验证要求和 design alignment 均已满足。未发现 blocking finding。Residual risks 均有明确 owner。
