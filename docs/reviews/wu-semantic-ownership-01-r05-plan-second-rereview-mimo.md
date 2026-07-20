# WU-SEMANTIC-OWNERSHIP-01 R05 Plan Second Complete Re-Review — AgentMiMo

## 0. Review 身份与范围

- **reviewer**: AgentMiMo（第二次完整 re-review，第一路）
- **immutable target**: `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
- **plan base / HEAD**: `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`
- **review scope**: 最终修订计划全文 constructively adversarial review，不只检查 R05-PRR-F01 局部 diff
- **已读输入**:
  - `AGENTS.md`
  - `docs/host/issues-implementation-control.md`（R05 段）
  - `docs/phaseflow-umbrella-optimization-control.md`
  - `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`（R05 manifest §12）
  - `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`（Topic 5 final decision）
  - `docs/host/design.md`（wait observation/abandon 段）
  - `docs/engine/design.md`（§11 §12 handshake 段）
  - 全部 R05 artifact 链：初审 MiMo/DS → Controller adjudication → plan-fix → fix validation → re-review MiMo/DS → re-review controller adjudication → second plan-fix → second fix controller validation
  - 当前 production 代码：`wait_adapter.py`、`_wait_observation.py`、`durable/state.py`、`durable/schema.py`、`agent.py`
  - 当前测试：`test_wait_observation_runner.py`、`test_wait_adapter_polling.py`、`test_phase7_waiting_integration.py`、`test_wait_record_state.py`、`test_agent_phase3_tool_call.py`
- **直接代码验证**:
  - directed Ruff 8-path 命令确认 2 条 F401
  - symbol scan 确认 `mark_wait_record_poll_abandon_timeout` 5 处命中（tests 零）
  - source scan 确认 timeout 传播模式
  - `git diff --name-only 5ba0d8b6...` 确认 dayu/tests/utils/design 无 diff
  - pyright 确认 0 errors
  - full Ruff 确认 167 errors
  - `wait_adapter.py:1021-1029` 确认 CANCELLED 先走 abandon path 并 `continue`
  - `wait_adapter.py:1102-1128` 确认 poll timeout 当前构造 `WaitPollLost(ResolveWaitLostOutcome(...))`
  - `wait_adapter.py:1363-1382` 确认 abandon timeout 当前调用 `_MarkWaitRecordAbandonTimeoutOperation`
  - `durable/state.py:2728-2797` 确认 `mark_wait_record_poll_abandon_timeout` 完整定义与语义
  - `durable/schema.py:873` 确认 `poll_abandoned_at TEXT NULL` 字段存在
- **review 生成时间**: 2026-07-15T21:41:57+08:00（系统时钟）

---

## 1. R05-PRR-F01 与 R05-PF-01..04 关闭状态逐项复核

### 1.1 R05-PRR-F01 — changed-file Ruff 基线两条 F401

**裁决：CLOSED ✅**

直接复核：

- §2.3 已用完整 8-path 命令登记两条 F401 六元组（`state.py:40:5` 和 `test_phase7_waiting_integration.py:8:22`）。
- §5.1 atomic completion 要求 "两条 touched-file F401 均须在同一 S1 归零"。
- §9.2 全量 Ruff residual 预期 `167 - 2 = 165`，逐六元组核对。
- §0、§5.1 atomic completion、§6.2、§13、§14 均已同源收窄，明确 import hygiene 合法但不授权其它 lint cleanup。

独立 probe 验证：使用完整 8-path 命令（含 `test_wait_record_state.py`），精确返回 2 条 F401，与 plan 登记一致。`test_wait_record_state.py` 本身无 Ruff 问题。

### 1.2 R05-PF-01 — cancelled abandon timeout 长期 capped retry residual

**裁决：CLOSED ✅**

- `wait_adapter.py:1021-1029` 确认：`record.status is CANCELLED` → `_abandon_cancelled_wait` → `continue`，跳过 `_handle_time_boundary`。
- §2.1、§4、§15 三处明确记录该 call order。
- 当前安全边界（claim CAS、`max_outstanding_adapter_calls=8`、finite single-call timeout、late-publication fencing、backoff cap `300s`）正确列出。
- future owner 正确分离为 Host cancel/abandon durable evidence policy（≠ Issue 175 的 Fins Docling 物理 containment）。
- 禁止 R05 发明 max retry / abandon deadline / timeout terminal marker 已显式声明。

### 1.3 R05-PF-02 — public smoke timing 可执行性

**裁决：CLOSED ✅**

- §5.2 和 §11 要求 event/condition/durable-state polling 驱动所有 phase。
- 唯一 `time.monotonic()` overall deadline。
- 具名 constants 与三段带 margin 严格不等式（`margin >= 5 * state-poll quantum`）。
- phase 失败输出 phase ledger、monotonic elapsed、runner dropped count、Run/Wait snapshot。
- timing 可行性：`handshake(5s) + margin(2.5s) < observation_timeout(30s) < operation_duration(45s) < 60s`。总耗时 ~65s，在合理 CI cap 内。

### 1.4 R05-PF-03 — Host design `close marker` 真源纠错

**裁决：CLOSED ✅**

- `docs/host/design.md` 已加入 R05-S1 write allowlist。
- §5.1 精确改写：transient diagnostic + release/backoff + keep CANCELLED + no `poll_abandoned_at`，保留 explicit lifecycle terminal outcome。
- 不新增 retry 上限 / deadline / policy / schema；超出即 stop。

### 1.5 R05-PF-04 — durable invalid timeout-only primitive 删除

**裁决：CLOSED ✅**

- `dayu/host/durable/state.py` 已加入 R05-S1 production allowlist。
- §5.1 要求删除 `mark_wait_record_poll_abandon_timeout(...)` 完整定义，禁止 deprecated/compat/dead surface。
- zero-symbol scan 确认：5 处命中（1 import + 1 class def + 1 call-through + 1 call-site + 1 function def），tests 零命中。
- `mark_wait_record_poll_abandoned(...)`（explicit lifecycle terminal）独立保留。
- `durable/schema.py` no-diff 要求明确。
- `tests/host/test_wait_record_state.py` 加入 test allowlist，新增 durable owner preservation test。
- per-file coverage 门禁 `durable/state.py >= 80%`、`wait_adapter.py >= 80%`。

---

## 2. State Machine Owner / Root Cause 挑战

**挑战：root cause 是否真的在 `WaitPoller` 而非 runner fencing 或 durable store？**

验证路径：

1. **poll timeout**：`wait_adapter.py:1102-1114` → `WaitObservationTimedOut` → 构造 `WaitPollLost(ResolveWaitLostOutcome(reason_code="wait_observation_timeout"))` → `self._resolve_claimed_wait(record, timeout_result)`。这是 `WaitPoller` 的 decision——把 observation uncertainty 提升为 business LOST。

2. **abandon timeout**：`wait_adapter.py:1363-1376` → `WaitObservationTimedOut` → `_MarkWaitRecordAbandonTimeoutOperation(abandoned_at=now)` 写 `poll_abandoned_at` terminal marker。这是 `WaitPoller` 的 decision——把 observation uncertainty 提升为 terminal abandon。

3. **runner fence**：`_wait_observation.py:123-137`（invalidate）+ `_wait_observation.py:336-361`（`_publish` 检查 token identity/state/closed/generation）。fence 正确撤销 publication authority，late result 被拒绝。runner fence 不做业务分类。

4. **typed terminal**：`waiting.py:1016-1024` 只接受显式 `ResolveWaitLostOutcome`。该 owner 正确——只有 provider authoritative typed lost 才 terminalize。

**结论：root cause 定位正确。** runner fence 只负责 fencing，durable store 只负责 persistence，业务分类（timeout → LOST / terminal abandon）是 `WaitPoller` 的 decision。R05 在正确 owner 修复。✅

---

## 3. CANCELLED 长期 Retry Residual 精确性

**挑战：plan 是否准确描述了 CANCELLED 长期 retry 的行为边界，且不误称既有 deadline 收口？**

验证：

1. **Call order**（`wait_adapter.py:1021-1036`）：
   ```
   poll_once():
     if record.status is CANCELLED:        # line 1021
       _abandon_cancelled_wait(...)         # line 1022-1024
       continue                             # line 1029
     _handle_time_boundary(...)             # line 1030 ← 不可达 for CANCELLED
   ```

2. **R05 后 retry 通路**：abandon timeout → `_release_with_backoff` → 清 claim、设 `next_observe_at`、递增 attempt、不写 `poll_abandoned_at` → claim query `poll_abandoned_at IS NULL` 可通过 → backoff 到期后可再次 claim。

3. **DS Challenge 3.3 已纠正**：DS 初审称 "deadline expiry 是独立 terminal 路径"，但代码证据确认 `_handle_time_boundary` 对 CANCELLED **永不执行**。plan §2.1、§4、§15 三处明确记录，不误称 deadline 收口。

4. **resource boundary**：claim CAS + `max_outstanding_adapter_calls=8` + finite single-call timeout + late-publication fencing + `backoff_max_delay_seconds=300`。这些限制单轮/并发资源，但不提供终止证据。

5. **future owner 分离**：Host cancel/abandon durable evidence policy ≠ Issue 175 process isolation。前者定义 durable stop evidence，后者处理 Fins Docling 物理 containment。

**结论：描述准确，不误称 deadline 收口。✅**

---

## 4. Durable Invalid Primitive 删除正确性

**挑战：删除 `mark_wait_record_poll_abandon_timeout` 是否真的是 owner-boundary root fix？**

验证：

1. **语义分析**（`durable/state.py:2728-2797`）：该函数的唯一语义是 UPDATE 设置 `poll_abandoned_at`（terminal marker）、清 claim fields、reset `poll_backoff_attempt=0`、set `poll_next_observe_at=NULL`。与 `release_wait_record_poll_claim` 对比，后者设 `next_observe_at`（backoff）、递增 attempt、不写 `poll_abandoned_at`。

2. **Caller 链**：`state.py:2728`（definition）→ `wait_adapter.py:51`（import）→ `wait_adapter.py:706-731`（`_MarkWaitRecordAbandonTimeoutOperation` wrapper）→ `wait_adapter.py:1368`（call-site）。唯一 consumer。

3. **Schema 不变**：`poll_abandoned_at` 字段同时服务于 `mark_wait_record_poll_abandoned`（explicit lifecycle terminal）和待删除的 timeout primitive。删除后者，前者继续工作。`schema.py` no-diff。

4. **Tests 零引用**：`rg` 确认 tests 中无任何对该 function 的引用。

5. **为什么不能保留 dead code**：(a) 语义已被否定；(b) 保留会在 durable boundary 留下可误用的 invalid operation；(c) 项目禁止兼容/dead shim。

**结论：owner-boundary root fix 正确。✅**

---

## 5. Design Writeback 精确性

**挑战：writeback 是否只纠正已裁决句子，不引入新 policy/schema？**

验证：

- **Target**：`docs/host/design.md:2429-2430` 的 "cancelled wait 的 abandon 超时只写 `wait_abandon_timeout` diagnostic/close marker"。
- **Planned replacement**：transient `wait_abandon_timeout` diagnostic + release claim + Host policy backoff + keep `CANCELLED` + no terminal `poll_abandoned_at`；保留 explicit lifecycle terminal outcome。
- **Boundary**：§5.1 明确 "不新增 retry 上限、deadline、policy/schema"，§13 stop condition 11 要求超出即 stop。
- **Lines 2425-2427 保留**：poll timeout 行为已正确描述（transient diagnostic + release + backoff + no LOST），R05 不修改。

**结论：writeback 精确且受限。✅**

---

## 6. Smoke Event/Condition/Monotonic 可执行性

**挑战：smoke 的 5 个 phase 是否真正可由 event/condition/durable-state polling 驱动，不依赖固定 sleep 推断状态？**

| Phase | 驱动方式 | 可实现性 |
|---|---|---|
| 1. handshake accepted + operation started | `asyncio.Event` / `threading.Event` | ✅ |
| 2. first observation entered + timeout state | event gate 阻塞 adapter 首次调用 + durable state polling 确认 diagnostic | ✅ |
| 3. operation finish + late result released + dropped count | signal + durable state polling | ✅ |
| 4. second observation entered | state-poll quantum 查询 due/claim state | ✅ |
| 5. SUCCEEDED + terminal event + outbox | public result/state condition | ✅ |

Timing 不等式可行性（packaged values）：

```
handshake_budget(5s) + margin(2.5s) = 7.5 < adapter_timeout(30s) < operation_duration(45s) < 60s
margin = 2.5s >= 5 * quantum(0.5s) ✓
total ≈ 65s < CI_cap(120s) ✓
```

Phase 失败证据：phase ledger + monotonic elapsed + runner dropped count + Run/Wait snapshot（claim/status/next-observe/diagnostic/`poll_abandoned_at`/terminal outbox）。

**结论：5 个 phase 均可实现，timing 有界。✅**

---

## 7. 两 Slice / 依赖 / 回滚

**挑战：PF-03（design writeback）和 PF-04（durable primitive 删除）是否破坏了原始两 slice 原子边界？**

| Slice | 性质 | Production 变更 | 回滚边界 |
|---|---|---|---|
| R05-S1 | 唯一 production semantic transaction | `wait_adapter.py` + `durable/state.py` + `design.md` | 单独可回滚 |
| R05-S2 | 跨层 contract evidence | 无 production 变更（`agent.py` no diff） | 不改 production |

- PF-03 归属 S1：design truth correction 与 adapter decision 修正同属一个 semantic transaction。
- PF-04 归属 S1：durable primitive 删除是 storage owner boundary 修正，与 adapter 不再调用该 primitive 同属一个语义闭环。
- S2 的 Engine regression 预期在 base 上直接通过（当前 production 已正确）；public smoke 需要 S1 的 Host behavior 变更。

**结论：两 slice 原子边界保持。✅**

---

## 8. Engine `agent.py` No-Diff

**挑战：`agent.py` 是否真的不需要修改？**

直接代码证据：

- `agent.py:1974`：`timeout_seconds` 只设置在 `BatchToolExecutionContext` 上。
- `agent.py:2184`：`await_or_cancel_or_timeout` 使用同一 timeout 包裹 `_call_tool_executor`。
- `agent.py:2055-2088`：接受 `ToolAwaitingOutcome` 后 emit `RUN_SUSPENDED` 并 return，**无 timeout 再读取**。
- `docs/engine/design.md:398`：明确 "Host durable accepted 之后继续运行的外部长事务不受 `tool_execution_timeout_seconds` 限制"。

§5.2 regression test `test_accepted_awaiting_external_operation_outlives_handshake_timeout` 预期在 base 上直接通过。若失败则 stop（§13 stop condition 4）。

**结论：no-diff 判定有直接代码证据支撑。✅**

---

## 9. Test-First / Coverage / Ruff Six-Tuple 与 Residual 165

### 9.1 Test-First Red → Green

两条新 owner tests 在未改 production 的 base 上预期精确失败：

- `test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve`：当前 timeout → LOST，R05 后应保持 WAITING。
- `test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal`：当前 timeout 写 `poll_abandoned_at`，R05 后应保持 NULL。

两条 preservation green nodes 在 base 和 implementation 后均应为绿：

- `test_cancelled_poll_timeout_release_preserves_claimability_after_due`：`release_wait_record_poll_claim` 已支持 CANCELLED。
- `test_poll_abandon_success_marks_row_and_clears_claim`：explicit terminal 不变。

### 9.2 Coverage 门禁

| Changed Production File | Coverage Target | 当前实测 | Verdict |
|---|---|---|---|
| `dayu/host/durable/state.py` | >= 80% | 83% | PASS |
| `dayu/host/wait_adapter.py` | >= 80% | 86% | PASS |

Coverage 命令：`tests/host --ignore=tests/host/test_toolruntime_executor.py`，排除有充分理由（无关 process-backed ToolRuntime），不掩盖 R05 propagation。

### 9.3 Ruff Six-Tuple 与 Residual 165

Six-tuple A（`state.py` F401）：

```text
exact command: python -m ruff check dayu/host/durable/state.py dayu/host/wait_adapter.py tests/host/test_wait_observation_runner.py tests/host/test_wait_adapter_polling.py tests/host/test_phase7_waiting_integration.py tests/host/test_wait_record_state.py tests/engine/test_agent_phase3_tool_call.py utils/smoke_host_public_awaiting_entrypoint.py
node/path: dayu/host/durable/state.py
error type: F401
first stable location: dayu/host/durable/state.py:40:5
text fingerprint: `dayu.host.durable._row_rules.TERMINAL_RUN_STATUS_VALUES imported but unused`
baseline SHA: 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
```

Six-tuple B（test F401）：

```text
exact command: [同上]
node/path: tests/host/test_phase7_waiting_integration.py
error type: F401
first stable location: tests/host/test_phase7_waiting_integration.py:8:22
text fingerprint: `datetime.UTC imported but unused`
baseline SHA: 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
```

独立 probe 确认：完整 8-path 命令精确返回 2 条 F401，与 plan 登记一致。full Ruff base = 167 errors，residual 预期 = 167 - 2 = 165。逐六元组核对规则已明确。

---

## 10. Source / Propagation / Security Scans

| Scan | 命令 | 预期 | Verdict |
|---|---|---|---|
| invalid symbol 零匹配 | `rg 'mark_wait_record_poll_abandon_timeout\|_MarkWaitRecordAbandonTimeoutOperation' dayu tests` | guard 返回零（exit 1） | ✅ 当前 5 处命中，implementation 后应为零 |
| schema no-diff | `git diff --exit-code 5ba0d8b6... -- dayu/host/durable/schema.py` | exit 0 | ✅ |
| timeout 不传播成 terminal | source scan | `wait_observation_timeout` 只作 diagnostic code；不在 `ResolveWaitLostOutcome` 构造中 | ✅ |
| late token 唯一路径 | source scan | runner 仍是唯一 publication authority | ✅ |
| claim/backoff 唯一真源 | source scan | timeout branches 只调用 `_release_with_backoff` | ✅ |
| Engine no-diff | `git diff --exit-code 5ba0d8b6... -- dayu/engine/agent.py` | exit 0 | ✅ |
| R04 ownership | `rg 'awaiting_resolution_mode\|wait_poller_policy'` | 只从 owner 路径投影 | ✅ |
| security/deferred scope | `git diff --unified=0 ... \| rg 'authorization\|...'` | 零命中 | ✅ |

---

## 11. README Decision

| README | 决策 | 证据 |
|---|---|---|
| `dayu/host/README.md` | 需要更新 | observation timeout 是 poll-local diagnostic + claim release/backoff，poll 保持 WAITING，abandon timeout 保持 retryable CANCELLED |
| `tests/README.md` | 需要更新 | R05 owner regression 与 public awaiting smoke 覆盖的 contract |
| `dayu/engine/README.md` | `agent.py` no diff 时不改 | 当前已说明 timeout 只限制 handshake |
| 根 README / `dayu/README.md` | 不触发 | 无入口/工作流/分层变化 |

---

## 12. Security / Deferred Boundaries

| 边界 | plan 声明 | Verdict |
|---|---|---|
| 不实施 unified authorization | §1.3 非目标 | ✅ |
| 不实施 callback transport | §1.3 非目标 | ✅ |
| 不实施 Issue 175 process isolation | §1.3 非目标 + §15 residual | ✅ |
| 不实施 R06+ | §1.3 非目标 | ✅ |
| 保留 token/fence/CAS/capacity/close-drain | §1.3 + §4 branch matrix | ✅ |
| 不写 LOST / terminal abandon marker for timeout | §5.1 production 变更 | ✅ |

---

## 13. Branch Matrix 完整覆盖

plan §4 分支矩阵 14 行，逐行验证 owner assertion：

| # | 路径 | Assertion | Verdict |
|---|---|---|---|
| 1 | poll Ready | `test_poll_adapter_ready_result_resolves_wait` | ✅ |
| 2 | poll NotReady | `test_poll_adapter_not_ready_leaves_wait_active` | ✅ |
| 3 | poll authoritative Lost | `test_poll_adapter_lost_result_closes_run` | ✅ |
| 4 | poll observation timeout | **新增** test-first red→green | ✅ |
| 5 | poll adapter exception | `test_abandon_adapter_snapshot_projection_failure_releases_with_backoff` | ✅ |
| 6 | poll capacity | `test_active_poll_claim_suppresses_second_poller_adapter_call` | ✅ |
| 7-9 | cancelled explicit applied/unsupported/noop | `test_cancelled_poll_wait_is_abandoned_once_without_resolve` | ✅ |
| 10 | cancelled observation timeout | **新增** test-first red→green | ✅ |
| 11 | cancelled exception | `test_failed_cancelled_wait_abandon_is_retried_next_poll` | ✅ |
| 12 | cancelled capacity | 既有 release/cadence test | ✅ |
| 13 | close/drain | `test_supervisor_close_uses_one_shared_deadline_and_stays_closing` | ✅ |
| 14 | wait deadline (non-CANCELLED) | `test_invalid_poll_deadline_fails_closed_without_business_lost` | ✅ |

**14/14 路径均有 owner assertion。**

---

## 14. Open Questions

**无 blocking open question。**

---

## 15. Findings

**零 finding。**

原 Finding 001（§5.1 production changes 未显式列出 F401 import hygiene）已撤回——与 immutable target 直接矛盾。

直接证据：最终 plan §5.1 `dayu/host/durable/state.py` production changes 段第 241 行已逐字写明：

> 同时删除当前 base 在 `dayu/host/durable/state.py:40:5` 已证明未使用的 `TERMINAL_RUN_STATUS_VALUES` import；这只是 planned changed owner file 的唯一 lint hygiene，不改变 durable semantic contract，也不授权清理其它 import、Ruff 项或代码。

该句正是原 Finding 001 建议补入的文本。reviewer 初次阅读时遗漏了第 241 行，属于 reviewer 错误，不是 plan 缺陷。对此失误表示修正。

---

## 16. Residual Risks

| # | Risk | 分类 | Owner / Destination | 当前边界 |
|---|---|---|---|---|
| R1 | cancelled abandon observation 可能长期 capped-backoff retry 并间歇占用有限 capacity | `requiring new issue or explicit user decision` | future Host cancel/abandon durable evidence policy | CAS/cap/timeout/fence/backoff cap 限制单轮/并发资源，非终止证据 |
| R2 | Fins Docling 物理终止/containment | `tracked by existing issue` | Issue 175 | 不与 Host durable stop evidence 混同 |
| R3 | public smoke 执行时间 ~65s | `fixed in current slice` | R05-S2 | event/condition/state-poll + monotonic deadline + CI cap |
| R4 | `mark_wait_record_poll_abandon_timeout` 在 state.py 中留有定义（implementation 后删除） | `fixed in current slice` | R05-S1 | owner-boundary deletion + zero-symbol scan |
| R5 | callback / unified authorization / R06+ | `assigned to later work unit` | 既有 umbrella later WU / issue | 本 plan 无变更 |
| R6 | future explicit Host LOST durable evidence policy | `requiring new issue or explicit user decision` | future Host policy | R05 不预留 heuristic branch |

---

## 17. Final Plan Review Conclusion

**PASS**

该最终修订计划经过第二次完整 constructively adversarial re-review，所有维度均通过：

- **R05-PRR-F01 + R05-PF-01..04**：全部关闭，每个都有独立代码证据验证。
- **State machine owner/root cause**：`WaitPoller` 是 timeout policy 解释的正确 owner；runner fence 和 typed terminal resolver 保持 read-only。
- **CANCELLED 长期 retry**：call order 确认绕过 `_handle_time_boundary`；resource boundary 和 future owner 准确；不误称 deadline 收口。
- **Durable invalid primitive deletion**：owner-boundary root fix；单一 consumer 删除后 primitive 无合法 caller；schema/compat 无扩域。
- **Design writeback**：精确一句话纠错，不引入新 policy/schema。
- **Smoke event/condition/monotonic**：5 个 phase 均可实现，timing 有界（~65s < CI cap）。
- **两 slice**：原子边界保持；PF-03/PF-04 自然归入 S1。
- **Engine agent.py no-diff**：直接代码证据 + 设计真源 + regression test 三重验证。
- **Test-first / coverage / Ruff**：两条 red→green + 两条 preservation green + 逐文件 >=80% + 两条 F401 基线 + residual 165。
- **Source/propagation/security scans**：五组 scan 命令 + 人工核对均可执行。
- **R04 12 fields/modes**：显式保留，回归命令覆盖。
- **Security/deferred boundaries**：全部边界 hold；stop conditions 覆盖所有扩域路径。

**零 finding、零 blocker、零 blocking question、零 owner/allowlist 修改建议。plan 达到 code-generation-ready 标准。**

下一 gate：AgentDS 完成第二路完整 re-review，随后 Controller 最终 adjudication。
