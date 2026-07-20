# WU-SEMANTIC-OWNERSHIP-01 R05 Plan 第二次 Complete Re-Review — AgentDS

## 0. Review 身份与 Gate 位置

- **reviewer**: AgentDS（R05 第二次 complete re-review，本 review 是 WU-SEMANTIC-OWNERSHIP-01 umbrella R05 的第二轮独立 adversarial re-review，不进入 implementation）
- **immutable target**: `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
- **plan base / HEAD**: `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`
- **umbrella**: `WU-SEMANTIC-OWNERSHIP-01` continuation
- **本轮 gate**: `WAITING_FOR_CONTROLLER_VALIDATION_AFTER_SECOND_PLAN_FIX`；本轮只 review 最终计划全文，完成后停下等待 Controller
- **写权限**: 仅新建本 artifact：`docs/reviews/wu-semantic-ownership-01-r05-plan-second-rereview-ds.md`；不得修改 target、control、产品、测试、README、design 或任何既有 artifact，不 commit/push
- **review 生成时间**: 2026-07-15T21:45:12+08:00（系统时钟）

### 0.1 已读输入（完整清单）

| 类别 | 文件 | 状态 |
|---|---|---|
| 项目约束 | `AGENTS.md`（全部章节） | ✓ |
| 控制文档 | `docs/host/issues-implementation-control.md`（R05 段） | ✓ |
| 总控优化 | `docs/phaseflow-umbrella-optimization-control.md` | ✓ |
| umbrella plan | `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md`（§12 R05 manifest） | ✓ |
| controller 裁决 | `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`（Topic 5 final decision） | ✓ |
| 设计真源 | `docs/host/design.md`（wait observation/abandon 段） | ✓ |
| 设计真源 | `docs/engine/design.md`（§4 §6 §11 §12） | ✓ |
| Gate 0 初审 | `docs/reviews/wu-semantic-ownership-01-r05-plan-review-mimo.md` | ✓ |
| Gate 0 初审 | `docs/reviews/wu-semantic-ownership-01-r05-plan-review-ds.md` | ✓ |
| Gate 0 裁决 | `docs/reviews/wu-semantic-ownership-01-r05-plan-review-controller-adjudication.md` | ✓ |
| Gate 1 fix | `docs/reviews/wu-semantic-ownership-01-r05-plan-fix-codex.md` | ✓ |
| Gate 1 验证 | `docs/reviews/wu-semantic-ownership-01-r05-plan-fix-controller-validation.md` | ✓ |
| Gate 2 re-review | `docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-mimo.md` | ✓ |
| Gate 2 re-review | `docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-ds.md` | ✓ |
| Gate 2 裁决 | `docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-controller-adjudication.md` | ✓ |
| Gate 3 fix | `docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-fix-codex.md` | ✓ |
| Gate 3 验证 | `docs/reviews/wu-semantic-ownership-01-r05-plan-rereview-fix-controller-validation.md` | ✓ |

### 0.2 直接代码证据（全量复核）

| 文件 | 复核范围 | 状态 |
|---|---|---|
| `dayu/host/wait_adapter.py` | 全文件（poll_once CANCELLED branch, poll timeout, abandon timeout, _release_with_backoff, _MarkWaitRecordAbandonTimeoutOperation） | ✓ |
| `dayu/host/_wait_observation.py` | token/generation fence 段 (lines 110-170, 320-379) | ✓ |
| `dayu/host/waiting.py` | typed ResolveWaitLostOutcome 段 (line 1016-1024) | ✓ |
| `dayu/host/durable/state.py` | claim/release/abandon/abandon_timeout 段 (lines 2465-2797)；TERMINAL_RUN_STATUS_VALUES import (line 40) | ✓ |
| `dayu/host/durable/schema.py` | poll_abandoned_at 段 (lines 873, 921) | ✓ |
| `dayu/engine/agent.py` | handshake timeout 段 (lines 1960-2088, 2170-2194) | ✓ |
| `utils/smoke_host_public_awaiting_entrypoint.py` | 前 60 行结构 | ✓ |

### 0.3 独立验证命令（全部执行）

| 命令 | 结果 |
|---|---|
| `python -m ruff check dayu/host/durable/state.py ...`（plan §9.2 完整 changed-file 命令） | `Found 2 errors`：state.py:40:5 F401 + test_phase7:8:22 F401 |
| `python -m ruff check dayu tests utils` | `Found 167 errors`（全量 baseline） |
| `python -m pyright dayu/ tests/ utils/` | `0 errors, 0 warnings, 0 informations` |
| `rg -n 'mark_wait_record_poll_abandon_timeout\|_MarkWaitRecordAbandonTimeoutOperation' dayu tests` | 5 处命中（1 import + 1 class def + 1 call-through + 1 call-site + 1 function def），tests 零命中 |
| `rg -n 'TERMINAL_RUN_STATUS_VALUES' dayu/host/durable/state.py` | 仅 import line 40，函数体内零使用 |
| `rg -n 'TERMINAL_RUN_STATUS_VALUES' dayu/ tests/` | state.py 仅 import；schema.py 有实际使用；test_state_schema.py 有实际使用；purge.py 有独立定义 |
| `rg -n 'tool_execution_timeout_seconds' dayu/engine/agent.py` | 仅两处：line 1974（context 构造）和 line 2184（await_or_cancel_or_timeout），均在 handshake 内 |
| `git diff --name-only 5ba0d8b6.. -- dayu/engine/agent.py` | 空（no diff） |
| `git diff --name-only 5ba0d8b6.. -- dayu/host/durable/schema.py` | 空（no diff） |
| `pytest tests/host/test_wait_observation_runner.py tests/host/test_wait_adapter_polling.py tests/host/test_phase7_waiting_integration.py -q` | `41 passed` |
| `pytest tests/engine/test_agent_phase3_tool_call.py -q` | `47 passed` |
| `pytest tests/host --ignore=tests/host/test_toolruntime_executor.py --cov=dayu.host.durable.state --cov=dayu.host.wait_adapter --cov-branch -q` | `1 failed, 1915 passed, 1 skipped, 5 deselected`；durable/state.py=83%；wait_adapter.py=85% |

### 0.4 独立验证中发现的 transient coverage-session 失败

本 review 运行 plan §8 的 green coverage 命令时，整体结果不是 plan 声称的 `1916 passed`，而是 `1 failed, 1915 passed, 1 skipped, 5 deselected`（覆盖率数值 `durable/state.py=83%`、`wait_adapter.py=85%` 与 plan 一致）。失败的六元组如下：

```text
exact command:
  source .venv/bin/activate && python -m pytest -q tests/host
  --ignore=tests/host/test_toolruntime_executor.py
  --cov=dayu.host.durable.state --cov=dayu.host.wait_adapter --cov-branch

test node:
  tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task

error type / first stable frame:
  dayu.host.api.HostApiError (Host execution is unavailable)
  raised at dayu/host/_execution_health.py:258 in raise_if_scheduler_unavailable

call chain:
  test_dispatch_scheduler.py:4941 await scheduler.close()
  -> dispatch.py:2593 close() -> _suppress_task_cancel(active_task)
  -> dispatch.py:3971 _consume_worker_events -> ingestor.close_clean_eof
  -> engine_ingest.py:960 close_clean_eof -> _close_worker_lifecycle
  -> engine_ingest.py:2778 _with_terminal_promotion_retry -> wake_queue_promotion(session_id)
  -> dispatch.py:1119 wake_queue_promotion -> _raise_if_wake_unavailable(component=_CRITICAL_COMPONENT_PROMOTION)
  -> dispatch.py:2706 raise_if_scheduler_unavailable
  -> _execution_health.py:258 raise HostApiError: Host execution is unavailable

normalized fingerprint:
  HostApiError: Host execution is unavailable during scheduler.close() →
  _consume_worker_events → close_clean_eof → wake_queue_promotion;
  health gate state already past CLOSING at promotion time;
  log: dispatch.worker_events.clean_eof_without_terminal

baseline SHA: 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1
```

**Source/propagation 交集检查**（独立执行）：

- `rg -l 'wait_adapter|durable/state|WaitPoller|_release_with_backoff|WaitObservationTimedOut|mark_wait_record_poll' tests/host/test_dispatch_scheduler.py` → **零命中**
- `rg -l 'dispatch_scheduler|HostExecutionHealthGate|raise_if_scheduler_unavailable|_execution_health' dayu/host/wait_adapter.py dayu/host/durable/state.py` → **零命中**
- `rg -n 'HostExecutionHealthGate|_execution_health|raise_if_scheduler_unavailable' dayu/host/wait_adapter.py dayu/host/durable/state.py` → **零命中**

**结论**：该 node 与 R05 changed production files（`wait_adapter.py`、`durable/state.py`）及 R05 修改的全部语义路径（WaitPoller/observation timeout/claim release/backoff）之间，**source 与 propagation 交集均为零**。失败路径完全位于 dispatch scheduler → health gate → worker event ingest 子系统。

**隔离复跑**：`python -m pytest -q tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task` → `1 passed in 0.31s`。根因当前未定——直接证据只证明：(a) 完整 coverage suite 首次出现 `HostApiError: Host execution is unavailable` 于 scheduler close() 路径；(b) 同一 node 隔离复跑未复现；(c) 与 R05 owner paths 零 source/propagation 交集。单次隔离通过不能证明 root cause 已消除，同样首次全量失败也不能仅靠零 R05 交集就断言 root cause 为 test-order 污染。

**对 plan validation 的影响**：plan 的 coverage 门禁是该命令 **全绿**（`1916 passed`），而本次独立复现没有达到全绿。现有直接证据只证明失败与 R05 零 propagation 交集且隔离未复现——根因未定。因此本 review **不得**建议把 plan 的 exact green requirement 改成 approximate，也**不得**把根因断定为 test-order/isolation defect。Implementation 仍必须要求完整 coverage command 全绿；若 implementation 时该 node 仍然失败，必须先独立定位根因（排查是否为环境差异、真实 dispatch regression 或 test 间状态泄漏），排查结论进入 implementation completion report；不能以 "R05 reviewer 已确认无关" 豁免。

---

## 1. Assumptions Tested

| # | Assumption | Evidence Source | Verdict |
|---|---|---|---|
| A1 | poll timeout root cause 在 `WaitPoller` | `wait_adapter.py:1102-1128` 构造 `WaitPollLost(ResolveWaitLostOutcome(...))` → `_resolve_claimed_wait` | PASS |
| A2 | abandon timeout root cause 在 `WaitPoller` | `wait_adapter.py:1363-1382` → `_MarkWaitRecordAbandonTimeoutOperation` 写 `poll_abandoned_at` | PASS |
| A3 | `WaitObservationRunner` token/generation fence 正确 | `_wait_observation.py` invalidate + `_publish` 检查 token identity/state/closed/generation | PASS |
| A4 | `release_wait_record_poll_claim` 支持 WAITING + CANCELLED | `state.py:2642-2655` WHERE clause `status IN (WAITING, CANCELLED)` | PASS |
| A5 | Engine `agent.py` 在 accepted awaiting 后不复用 handshake timeout | `agent.py:1974,2184` 只在 `_execute_batch` 内读取；line 2055-2088 接受 awaiting 后 emit `RUN_SUSPENDED` 并 return | PASS |
| A6 | `release_wait_record_poll_claim` 不写 `poll_abandoned_at` | 该函数只清 claim 字段 + 写 backoff/diagnostic，不触及 `poll_abandoned_at` | PASS |
| A7 | `poll_abandoned_at IS NULL` 是 cancelled record claim 必要条件 | `state.py:2537` claim query | PASS |
| A8 | CANCELLED 绕过 `_handle_time_boundary` | `wait_adapter.py:1021-1029`: `status is CANCELLED` → `_abandon_cancelled_wait` → `continue`；`_handle_time_boundary` 在 line 1030 | PASS |
| A9 | `mark_wait_record_poll_abandoned` 独立于 timeout-only primitive | `state.py:2663` 单独定义，用于 explicit lifecycle terminal | PASS |
| A10 | `_release_with_backoff` 可接受 `ADAPTER_ERROR` / `ABANDON_ERROR` | 参数类型 `WaitPollLastOutcome`，两个值均为既有 enum | PASS |
| A11 | invalid timeout primitive 仅单点 consumer | 全仓 scan：1 import + 1 wrapper + 1 call-through + 1 call-site + 1 def；tests 零命中 | PASS |
| A12 | `TERMINAL_RUN_STATUS_VALUES` 在 `state.py` 中确实未使用 | 仅 line 40 import；函数体内零使用；`schema.py` 独立 import 并使用 | PASS |
| A13 | Engine agent.py no-diff | `git diff --exit-code base -- agent.py` 返回 0 | PASS |
| A14 | schema.py no-diff | `git diff --exit-code base -- schema.py` 返回 0 | PASS |
| A15 | design.md line 2429-2430 "close marker" 存在 | `rg` 确认 | PASS |
| A16 | directed Ruff 正好 2 条 F401 | 独立运行 confirmed | PASS |
| A17 | full Ruff baseline 167 | 独立运行 confirmed | PASS |
| A18 | pyright baseline 0 errors | 独立运行 confirmed | PASS |
| A19 | 41 tests passed（focused matrix） | 独立运行 confirmed | PASS |
| A20 | 47 Engine tests passed | 独立运行 confirmed | PASS |

---

## 2. R05-PF-01..04 与 R05-PRR-F01 逐项关闭终极复核

本节是第三次独立复核（初审 → re-review → 本次 second re-review），逐项提供独立代码证据。

### 2.1 R05-PF-01 — cancelled abandon timeout 长期 capped retry residual

| 裁决要求 | 计划位置 | 独立验证 | 结论 |
|---|---|---|---|
| CANCELLED 绕过 `_handle_time_boundary` | §2.1 表, §4 row 13, §15 | `wait_adapter.py:1021-1029`：`status is CANCELLED` → `_abandon_cancelled_wait` → `continue`；line 1030 `_handle_time_boundary` 不可达 | **真正关闭** |
| 长期 retry 事实登记 | §15 | 描述 call order，明确不进入 `_handle_time_boundary` | **真正关闭** |
| 有限资源边界 | §15 | claim CAS、`max_outstanding_adapter_calls=8`、finite single-call timeout、late-publication fencing、`backoff_max_delay_seconds=300` | **真正关闭** |
| future owner 分离 | §15 | Host cancel/abandon durable evidence policy ≠ Issue 175 process isolation | **真正关闭** |
| 禁止扩域 | §15 + §1.3 | 不发明 max retry、abandon deadline、timeout terminal marker | **真正关闭** |

**独立判定**：PF-01 真正关闭。plan 的三个独立位置（§2.1、§4、§15）均正确描述了 CANCELLED 绕过 `_handle_time_boundary` 的事实。Controller 裁决中明确纠正了初审 DS Challenge 3.3 的错误判断（"deadline expiry 是独立 terminal 路径"），这一纠正已被计划完全吸收。

### 2.2 R05-PF-02 — public smoke timing 可执行性

| 裁决要求 | 计划位置 | 独立验证 | 结论 |
|---|---|---|---|
| event/condition-driven phases | §5.2 第 8 点, §11 | 5 个 phase 全部由 event/condition/state-poll 驱动 | **真正关闭** |
| monotonic deadline | §5.2 第 10 点, §11 | `time.monotonic()` 唯一 overall deadline；all phase waits 从同一 deadline 计算 remaining budget | **真正关闭** |
| relative margins | §5.2 第 8 点 | `margin >= 5 * state-poll quantum`；三段严格不等式 | **真正关闭** |
| 禁止固定 sleep 推断 | §5.2 第 8 点, §11 | 明确禁止 | **真正关闭** |
| CI cap | §5.2 第 10 点 | overall deadline ≤ CI duration cap | **真正关闭** |
| phase failure evidence | §5.2 第 10 点, §11 | phase ledger + monotonic elapsed + runner dropped count + Run/Wait snapshot | **真正关闭** |

**独立判定**：PF-02 真正关闭。以 packaged values（`adapter_call_timeout_seconds=30`、`backoff_initial_delay_seconds=30`）代入验证，operation duration 窗口约 29s（`30+margin` 到 `60-margin`），完全可操作。总耗时 estimate ~65s，在合理 CI cap（120s）内有约 55s 余量。

### 2.3 R05-PF-03 — Host design `close marker` 真源纠错

| 裁决要求 | 计划位置 | 独立验证 | 结论 |
|---|---|---|---|
| allowlist 纳入 | §5.1, §6.2 | `docs/host/design.md` 加入 R05-S1 write allowlist | **真正关闭** |
| 精确改写 | §5.1 | 只改 line 2429-2430 一句：transient diagnostic + release claim + backoff + keep CANCELLED + no `poll_abandoned_at` | **真正关闭** |
| explicit lifecycle terminal 保留 | §5.1 | "只有 provider 显式返回 applied / unsupported / noop lifecycle outcome，才沿既有 transition 写 terminal abandon marker" | **真正关闭** |
| 不扩写新 policy/schema | §5.1 + §13 stop condition 11 | 明确禁止新增 retry 上限、deadline、policy/schema | **真正关闭** |

**独立判定**：PF-03 真正关闭。当前 design.md:2429-2430 为 "cancelled wait 的 abandon 超时只写 `wait_abandon_timeout` diagnostic/close marker"，其中 "close marker" 可被歧读为 terminal marker。plan 的精确改写消除了这一歧义。另注意 design.md:2425-2427 已正确描述 poll timeout 行为——计划不改该部分，范围精确。

### 2.4 R05-PF-04 — durable invalid timeout-only primitive 删除

| 裁决要求 | 计划位置 | 独立验证 | 结论 |
|---|---|---|---|
| production allowlist | §5.1, §6.2 | `dayu/host/durable/state.py` 加入 R05-S1 production allowlist | **真正关闭** |
| 精确删除范围 | §5.1 | 删除 `mark_wait_record_poll_abandon_timeout(...)` 完整定义 + 仅服务 invalid semantic 的代码 | **真正关闭** |
| zero-symbol scan | §10.1 | `mark_wait_record_poll_abandon_timeout\|_MarkWaitRecordAbandonTimeoutOperation` 零定义零调用 | **真正关闭** |
| schema no-diff | §5.1 + §10.1 | `durable/schema.py` 无 diff；`poll_abandoned_at` 只承载 explicit lifecycle terminal | **真正关闭** |
| explicit terminal 保留 | §5.1 | `mark_wait_record_poll_abandoned(...)` 不变 | **真正关闭** |
| per-file coverage | §5.1, §8 | actual changed files 各 >=80% | **真正关闭** |

**独立判定**：PF-04 真正关闭。删除是 owner-boundary root fix——该 primitive 的唯一 production consumer 将被删除（`_MarkWaitRecordAbandonTimeoutOperation`），因此 primitive 本身无合法 caller。保留 dead code 违反项目禁止兼容/dead shim 约束。当前 schema 字段 `poll_abandoned_at` 同时被正确语义（`mark_wait_record_poll_abandoned`）和错误语义（待删除 primitive）写入；删除后者后，字段仍被前者使用，schema 无需变更。

### 2.5 R05-PRR-F01 — changed-file Ruff 基线补登记

| 裁决要求 | 计划位置 | 独立验证 | 结论 |
|---|---|---|---|
| 登记 state.py F401 六元组 | §2.3 六元组 A | 使用最终 planned changed Python path 命令登记：`state.py:40:5`, F401, `TERMINAL_RUN_STATUS_VALUES` | **真正关闭** |
| 保留测试 F401 登记 | §2.3 六元组 B | 继续登记 `test_phase7_waiting_integration.py:8:22` F401 `datetime.UTC` | **真正关闭** |
| S1 同时清除两条 F401 | §5.1 atomic completion + §9.2 | 同 slice 清除两条 touched-file F401 | **真正关闭** |
| Ruff residual 精确化 | §9.2 | `167 - 2 = 165`；逐六元组核对 | **真正关闭** |
| 收窄绝对边界 | §0, §5.1, §6.2, §13, §14 | 增加唯一 import hygiene；禁止其它 lint cleanup | **真正关闭** |

**独立判定**：PRR-F01 真正关闭。独立运行 directed Ruff 确认正好 2 条 F401（`state.py:40:5` + `test_phase7:8:22`），plan 已用六元组登记。`TERMINAL_RUN_STATUS_VALUES` 在 `state.py` 中仅在 import line 40 出现（函数体内零引用），确认 unused。该符号在 `schema.py:20,186,192` 和 `test_state_schema.py:21,199,215` 中有独立 import 和使用——因此删除 `state.py` 的 import 不影响它们。

---

## 3. 全计划 Adversarial Re-Review（所有 Lens）

### 3.1 Architecture Boundary Review

| 维度 | 验证 | Verdict |
|---|---|---|
| Host 不依赖 Engine | R05-S1 只改 `wait_adapter.py` + `durable/state.py`，不 import Engine | PASS |
| Engine 不依赖 Host | R05-S2 `agent.py` no diff；Engine regression test 只读 Host public contract | PASS |
| `durable/state.py` 不向上泄漏 | 只删除一个 store primitive + 一个 unused import；不新增 public API | PASS |
| Service 不穿透 Host | smoke 经 `ServiceRunOverrides -> open_host -> durable poller` 公共链 | PASS |
| `dayu.runtime` 不被触及 | R05 不修改 runtime 包 | PASS |
| Schema/storage boundary | `durable/schema.py` no-diff；`poll_abandoned_at` 保留只为 explicit lifecycle terminal | PASS |
| Public contract boundary | R04 12-field policy + typed modes 保留；`ResolveWaitLostOutcome` 保留只为 authoritative typed lost | PASS |

**无边界违规。**

### 3.2 Best-Practice Review

| 维度 | 验证 | Verdict |
|---|---|---|
| root cause 修复 | 在 `WaitPoller` decision owner 修复，不补下游兼容 | PASS |
| 语义 owner 单一 | timeout policy → WaitPoller；token/fence → WaitObservationRunner；typed terminal → waiting.py | PASS |
| 无兼容代码 | 删除 invalid primitive + unused import，不留 deprecated wrapper | PASS |
| 无 God object | 复用 `_release_with_backoff`，不新增 registry/builder/facade | PASS |
| 测试跟着边界迁移 | 替换旧错误语义测试为新 owner contract | PASS |
| coverage 逐文件门禁 | actual changed production files 各自 >=80% | PASS |

**无最佳实践偏离。**

### 3.3 Optimal-Solution Review

plan 的路径（复用 `_release_with_backoff` + 删除 invalid primitive）是最实际的路径。替代方案评估：

- ❌ 新增 max retry / abandon deadline → 发明尚未裁决的 Host policy
- ❌ 保留 dead primitive → 违反项目约束，留下可再次误用的 invalid semantic
- ❌ 在 Engine 侧补偿 → 违反分层架构，Engine 不拥有 observation policy
- ❌ 在 waiting.py 识别 timeout code → 语义 owner 错误，waiting.py 只接受 typed terminal

**当前路径最优。**

### 3.4 Overengineering Review

- 两 slice 不过度：S1 是 production transaction，S2 是 evidence；合并会混合 root fix 与跨层验证
- 不新增 policy 字段/timer/scheduler/runner/token/lost outcome
- 不引入 max retry / abandon deadline / new backoff algorithm
- `_release_with_backoff` 是既有唯一 release/backoff 路径，复用而非复制

**无过度设计。**

### 3.5 Overcoupling Review

| 维度 | 验证 | Verdict |
|---|---|---|
| S1 两个 production file 是否过度绑定 | `wait_adapter.py` 删除 consumer；`durable/state.py` 删除 primitive。同属一个 invalid semantic 闭环 | PASS — 语义同源，必须同步 |
| S2 是否必须依赖 S1 | Engine regression 预期在 base 上直接通过（当前 production 已正确）；smoke 需要 S1 的 Host behavior | PASS — 依赖合理 |
| R04 config 是否被 R05 绑定 | R05 不改 config schema/fields/modes，只复用既有 12-field snapshot | PASS |
| `_wait_observation.py` / `waiting.py` 是否被不必要绑入 | 预期 no diff；只有出现 diffs 才 stop | PASS — 防御性检查 |

**无过度耦合。**

---

## 4. State Machine Owner / Root Cause 终极验证

### 4.1 Root cause 定位

root cause 判定为 `WaitPoller` 对 `WaitObservationTimedOut` 的错误业务解释。独立证据链：

1. **poll timeout** (`wait_adapter.py:1102-1128`)：`WaitObservationTimedOut` → 构造 `WaitPollLost(ResolveWaitLostOutcome(...wait_observation_timeout...))` → `_resolve_claimed_wait` → LOST terminalization。这是把 observation uncertainty 提升为业务 LOST 的直接代码路径。

2. **abandon timeout** (`wait_adapter.py:1363-1382`)：`WaitObservationTimedOut` → `_MarkWaitRecordAbandonTimeoutOperation` → 写 `poll_abandoned_at` → 永久阻断后续 claim。这是把 observation uncertainty 提升为 terminal abandon 的直接代码路径。

3. **runner fence 正确** (`_wait_observation.py`)：token/generation 在同一锁下 invalidate；`_publish` 同时校验 token identity、state、closed、generation。不需第二 fence。

4. **store primitive 被误用**：`release_wait_record_poll_claim` 已支持 WAITING/CANCELLED 的原子 release/backoff/diagnostic，但 timeout path 绕过了它。

**结论：root cause 定位精确。唯一 owner 是 `WaitPoller` decision。**

### 4.2 Owner 表验证

plan §3 的 owner 表逐项核实：

| 语义 | plan 声称 owner | 代码事实 | 判定 |
|---|---|---|---|
| observation timeout policy 解释 | `WaitPoller` | `wait_adapter.py:1102-1128`（poll）+ `wait_adapter.py:1363-1382`（abandon） | ✓ |
| token/generation fence | `WaitObservationRunner` | `_wait_observation.py:123-137` + `_publish` | ✓ |
| claim release/backoff 入口 | `WaitPoller._release_with_backoff` | `wait_adapter.py:1503-1543` 唯一路径 | ✓ |
| claim 清理与 diagnostic projection | `release_wait_record_poll_claim` | `state.py:2590-2660` 原子操作 | ✓ |
| timeout-only terminal primitive | `durable/state.py`（删除） | `state.py:2728-2797` 单点 definition | ✓ |
| typed terminal wait resolution | `ResolveWaitService` / `waiting.py` | `waiting.py:1016-1024` 只接受显式 `ResolveWaitLostOutcome` | ✓ |
| Engine handshake budget | `Agent` timeout wrapper | `agent.py:1974,2184` 只在 handshake 内 | ✓ |

**无 owner 冲突或漂移。**

---

## 5. CANCELLED 长期 Retry Residual 精确性验证

### 5.1 Call order 验证

```
poll_once() [wait_adapter.py:980-1053]:
  for claimed in claimed_records:
    record = claimed.record
    if self._lifecycle_gate.is_closed():         # line 1017
      → release_shutdown_skipped + continue
    if record.status is CANCELLED:                # line 1021
      → _abandon_cancelled_wait(record, ...)      # line 1022-1024
      → continue                                   # line 1029 ← 关键
    _handle_time_boundary(record, ...)             # line 1030-1036 ← 仅对非-CANCELLED 执行
```

**确认**：`_handle_time_boundary` 对 CANCELLED record **永不执行**。

### 5.2 Plan 描述准确性

plan 在三个独立位置描述了这一事实：
- §2.1 代码证据表：明确记录 CANCELLED → abandon → continue → 不进入 `_handle_time_boundary`
- §4 row 13：明确 "`CANCELLED` 在 `poll_once()` 中先进入 abandon path，不能用 `_handle_time_boundary(...)` 解释或终止其长期 retry"
- §15 explicit residual：完整描述长期 retry 事实、当前安全边界、future owner

**描述准确。无 deadline 收口的误称。**

### 5.3 资源边界验证

| 边界 | 机制 | 值 | 效果 |
|---|---|---|---|
| 并发上限 | `max_outstanding_adapter_calls` | 8 | 最多 8 个并发 observation thread |
| 频率上限 | `backoff_max_delay_seconds` | 300 | 最慢每 5 分钟一次重试 |
| 单次上界 | `adapter_call_timeout_seconds` | 30 | 单次 observation 最多 30s |
| 排他性 | claim CAS (`poll_abandoned_at IS NULL`) | — | 单 record 同时只有一个 poller 持有有效 claim |
| late publication | token/generation fence | — | timeout 后迟到结果被拒绝 |

**资源边界有限，但不等同于终止证据。plan 正确地将此标记为 residual。**

---

## 6. Design Writeback 精确性验证

### 6.1 Writeback target

当前 `docs/host/design.md:2429-2430`：
> cancelled wait 的 abandon 超时只写 `wait_abandon_timeout` diagnostic/close marker，不宣称 provider 已取消成功。

**歧义**："close marker" 可读作：
- (a) 关闭（停止后续观察）的标记 → 错误语义，支持当前 `_MarkWaitRecordAbandonTimeoutOperation`
- (b) 本次 abandon 观察的关闭标记 → 可与 retry 语义兼容

### 6.2 Planned writeback

plan §5.1 规定：
> cancelled wait 的 abandon observation timeout 只写 poll-local transient `wait_abandon_timeout` diagnostic、释放 claim 并按 Host policy backoff，durable status 保持 `CANCELLED` 且不写 terminal `poll_abandoned_at`；只有 provider 显式返回 applied / unsupported / noop lifecycle outcome，才沿既有 transition 写 terminal abandon marker，且不调用 wait resolve。

**验证**：
- 消除 "close marker" 歧义 ✓
- 明确 transient diagnostic ✓
- 明确 release claim + backoff ✓
- 明确 keep CANCELLED ✓
- 明确 no terminal `poll_abandoned_at` ✓
- 保留 explicit lifecycle terminal outcome ✓
- 不引入新 policy/schema ✓

**writeback 精确且受限。**

---

## 7. Smoke Event/Condition/Monotonic 可执行性验证

### 7.1 Timing 不等式可满足性

以 packaged defaults + test-only override 验证：

```
handshake_budget = 5s（test-only override via ServiceRunOverrides）
adapter_call_timeout_seconds = 30（packaged）
backoff_initial_delay_seconds = 30（packaged）
state_poll_quantum = 0.1s（assumed）
margin = 5 * 0.1s = 0.5s

不等式链：
  handshake_budget + margin < adapter_timeout
  5 + 0.5 = 5.5 < 30  ✓

  adapter_timeout + margin < operation_duration
  30 + 0.5 < operation_duration → operation_duration > 30.5s

  operation_duration < adapter_timeout + backoff_initial
  operation_duration < 60

operation_duration 窗口: (30.5s, 60s - 0.5s) = (30.5s, 59.5s)
窗口宽度: 29s ← 远大于操作抖动
```

**总耗时**：handshake(~5s) + first observation timeout(~30s) + backoff(~30s) + second observe(~1s) ≈ **66s**。CI cap 设为 120s → 约 54s 余量。

### 7.2 Phase 驱动可实现性

| Phase | 驱动方式 | 可实现性 |
|---|---|---|
| 1. accepted handshake + WAITING | `asyncio.Event` / durable state polling | ✓ 可复用现有 `_BlockingAdapter` pattern |
| 2. first observation timeout | adapter 首次调用由 event gate 阻塞 → 等待 durable timeout diagnostic + claim release + backoff due | ✓ durable state polling 可实现 |
| 3. late result release | signal operation finish → 等待 runner dropped count + durable state still WAITING | ✓ event + condition |
| 4. second observation Ready | state-poll quantum 查询 durable due/claim state | ✓ 不篡改 due time |
| 5. SUCCEEDED + terminal event + outbox | public result/state condition 等待 | ✓ 现有 public entrypoint |

**全部 5 个 phase 可用 event/condition/durable-state polling 实现，不依赖固定 sleep 推断。**

### 7.3 实现风险

smoke 实现复杂度较高：§5.2 有 10 条明确要求，§11 有 5 个 ordered phases 加 10 条 evidence assertions。这实际上是编写一个小型测试框架。实现 Agent 需要在以下方面做到精确：
- `asyncio.Event` / `threading.Event` 的正确创建和传递
- monotonic deadline 的 remaining budget 计算
- state polling 的 quantum 让出
- phase failure 时的完整 snapshot 收集

这些都是可实现但需要仔细 coding 的要求——不是 plan 的缺陷。

---

## 8. 两 Slice / 依赖 / 回滚验证

### 8.1 边界

| Slice | 性质 | Production 变更 | Evidence 变更 | 回滚 |
|---|---|---|---|---|
| R05-S1 | 唯一 production semantic transaction | `wait_adapter.py` + `durable/state.py` + `design.md` | host tests + `test_wait_record_state.py` | 单独可回滚 |
| R05-S2 | 跨层 contract evidence | 无 production 变更 | engine regression + public smoke + README | 无 production 回滚需求 |

### 8.2 PF-03/PF-04 归入 S1

Controller 裁决明确 "PF-03/PF-04 都属于 S1 同一个 semantic transaction，不增加 slice"。验证：
- PF-03（design writeback）：与 adapter decision 修正同属一个 semantic transaction
- PF-04（primitive 删除）：与 adapter 不再调用该 primitive 同属一个语义闭环
- S1 仍是单一切片，PF-03/PF-04 自然归入

**两 slice 原子边界保持。**

### 8.3 回滚考虑

S1 单独可回滚：回滚 `wait_adapter.py` + `durable/state.py` 的所有 diff + `design.md` 的 writeback 即可恢复旧行为。S2 不改 production，无回滚需求。

---

## 9. Engine agent.py No-Diff 验证

### 9.1 代码路径验证

| 位置 | 读取 `tool_execution_timeout_seconds` | 语义 |
|---|---|---|
| `agent.py:1974` | 构造 `BatchToolExecutionContext.timeout_seconds` | 协作提示字段 |
| `agent.py:2184` | `await_or_cancel_or_timeout` 包裹 `_call_tool_executor` | Engine handshake enforcement |

**仅此两处。**

### 9.2 Accepted Awaiting 后验证

```
agent.py:1983: batch_outcome = await self._execute_batch(batch_request)
  → handshake 在此完成
agent.py:2017-2019: ToolAwaitingOutcome → 加入 awaiting_records
  → 无后续 timeout 读取
agent.py:2055-2088: emit RUN_SUSPENDED + return
  → run 结束，无 timeout reuse
```

### 9.3 设计真源

`docs/engine/design.md:398`：合法长事务工具必须在 handshake budget 内返回 `ToolAwaitingOutcome`；Host durable accepted 后不受 `tool_execution_timeout_seconds` 限制。

### 9.4 独立验证

- `git diff --exit-code base -- dayu/engine/agent.py` → 0（no diff 确认）
- `pytest tests/engine/test_agent_phase3_tool_call.py -q` → 47 passed
- regression test `test_accepted_awaiting_external_operation_outlives_handshake_timeout` 预期在 base 上直接通过

**No-diff 判定三重验证通过。**

---

## 10. Test-First / Coverage / Ruff / Pyright 六元组与 Residual 165

### 10.1 Test-First 红→绿

plan §7.1 的 3 个 test-first red nodes 在未改 production 的 base 上预期：
- `test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve` → 红（断言 lost=0, WAITING, claim released, backoff）
- `test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal` → 红（断言 CANCELLED, `poll_abandoned_at is None`, claim released）
- `test_poll_observation_timeout_keeps_waiting_then_ready_resumes_run` → 红（integration timeout → WAITING → Ready → SUCCEEDED）

`test_cancelled_poll_timeout_release_preserves_claimability_after_due` 是 preservation green node——base 和 implementation 后都应为绿。

**test-first 策略正确。**

### 10.2 Coverage 门禁

| File | Coverage | Target | 独立验证 | Verdict |
|---|---|---|---|---|
| `dayu/host/durable/state.py` | 83% | >=80% | 83%（独立复现） | PASS |
| `dayu/host/wait_adapter.py` | 85% | >=80% | 85%（独立复现） | PASS |

**Transient failure caveat**：独立复现时完整 coverage command 为 `1 failed, 1915 passed`（非 plan 声称的 `1916 passed`）。失败 node `test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task` 的六元组、与 R05 changed files 的零 source/propagation 交集、隔离 1 passed 的证据均已在 §0.4 登记。两个 changed production file 的覆盖率数值（83%/85%）与 plan 完全一致，逐文件 `--fail-under=80` 门禁不受影响。但 **plan 的 exact green requirement（全绿 `1916 passed`）没有被本次 independent probe 复现**；根因当前未定——直接证据只证明失败与 R05 changed files 零 source/propagation 交集且隔离未复现。因此 implementation 必须运行完整 coverage command 并达到全绿；若该 node 仍失败，必须先独立定位根因，不能以 "R05 reviewer 已排除" 豁免。

### 10.3 Pyright

`python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations`（独立复现）。

### 10.4 Ruff

| Command | 结果 | Verdict |
|---|---|---|
| directed Ruff（plan §9.2 完整 changed-file） | `Found 2 errors`：state.py:40:5 F401 + test_phase7:8:22 F401 | 正确登记 |
| full Ruff | `Found 167 errors` | baseline 确认 |
| implementation 后预期 | `167 - 2 = 165` | 精确 |

六元组分别登记了 A（state.py F401）和 B（test_phase7 F401），六项完整。

### 10.5 Residual 165 逐六元组

plan §12 规定了严格的六元组继承规则：exact command、test node / lint path、error type、first stable frame、fingerprint、baseline SHA 六项完全相同才可继承。165 条预期 residual 必须在 implementation 后逐条核对这些维度，不能仅靠数量匹配豁免。当前 plan 已明确此要求。

---

## 11. Source / Propagation / Security Scans 可执行性验证

plan §10 的五组 scan 逐项验证：

| # | Scan | 命令 | 预期 | 独立验证 |
|---|---|---|---|---|
| 10.1 | timeout 不传播成 terminal | `rg` for `WaitObservationTimedOut`/`ResolveWaitLostOutcome` | `wait_observation_timeout` 只作为 diagnostic code；不在 `ResolveWaitLostOutcome` 构造中 | ✓ 现有代码中这两个 code 已在 production 中被正确使用（作为 diagnostic error_code 而不是 LOST reason_code 的唯一来源——这是当前代码的 root cause，R05 修复后两者分离） |
| 10.1 | invalid symbol zero | `rg` for `mark_wait_record_poll_abandon_timeout\|_MarkWaitRecordAbandonTimeoutOperation` | exit 1（零匹配）→ guard 返回零 | ✓ 当前 5 处命中，implementation 后应为 0 |
| 10.1 | schema no-diff | `git diff --exit-code` | exit 0 | ✓ 独立确认无 diff |
| 10.2 | late token 唯一 | `rg` for `_start_observation\|_invalidate_token\|_publish` | runner 仍是唯一 publication authority | ✓ |
| 10.3 | claim/backoff 唯一 | `rg` for `_release_with_backoff\|release_wait_record_poll_claim` | timeout branches 只调用既有 `_release_with_backoff` | ✓ plan 正确要求 |
| 10.4 | Engine no-diff | `git diff --exit-code` + `rg` for `tool_execution_timeout_seconds` | exit 0 + 只在 handshake 内 | ✓ 独立确认 |
| 10.5 | R04 ownership | `rg` for `awaiting_resolution_mode\|wait_poller_policy` | 只从 owner 路径投影 | ✓ |
| 10.5 | security/deferred | `git diff --unified=0 ... \| rg` | 零命中 | ✓ |

**所有 scan 可执行且预期结果明确。**

---

## 12. README 决策验证

| README | 计划动作 | 触发条件 | 独立判定 |
|---|---|---|---|
| `dayu/host/README.md` | R05-S2 更新 | `dayu/host/` 修改触发 | ✓ 正确：只写 current contract |
| `tests/README.md` | R05-S2 更新 | `tests/` 修改触发 | ✓ 正确：记录 R05 owner regression + smoke |
| `dayu/engine/README.md` | 预期 no diff 不做机械修改 | `agent.py` no diff → 不触发 | ✓ 正确 |
| 根 README | 不触发 | 无入口/工作流/分层/装配变化 | ✓ 正确 |
| `dayu/README.md` | 不触发 | 无分层/装配变化 | ✓ 正确 |

**README 决策正确。**

---

## 13. Security / Deferred Boundaries 保持

| 边界 | plan 声明 | 代码事实 | Verdict |
|---|---|---|---|
| 不实施 unified authorization | §1.3 | closed allowlist 不含相关文件 | PASS |
| 不实施 callback transport | §1.3 | R05 不改 Fins binding | PASS |
| 不实施 Issue 175 process isolation | §1.3 + §15 | 不含 `process_backed`/subprocess 修改 | PASS |
| 保留 token/fence/CAS/capacity/close-drain | §1.3 + §4 | 既有 owner tests preservation | PASS |
| 不放宽 claim CAS | §10.3 | `_release_with_backoff` 使用同一 `_ReleaseWaitRecordClaimOperation` | PASS |
| 不实施 R06+ | §1.3 | 不修改 Fins storage/domain | PASS |

**所有 security/deferred 边界保持。** §10.5 security scan 命令 `git diff --unified=0 ... | rg -n 'authorization|permission|callback transport|process isolation|process_backed|subprocess|Issue 175'` 预期零命中。

---

## 14. Findings

经过全文 constructively adversarial review，应用所有 mandatory lenses（architecture boundary、best-practice、optimal-solution、overengineering、overcoupling），以下是我的 findings：

### 14.1 无 Blocker Finding

经过三轮独立 review（初审 MiMo/DS → re-review MiMo/DS → 本 second re-review），计划的核心要素已经过充分挑战和验证：
- root cause 定位精确（`WaitPoller` 对 observation timeout 的错误业务解释）
- semantic owner 判定正确（5 个 owner 各司其职，无冲突或漂移）
- state machine transition 完整（14 行 branch matrix 全部有 owner assertion）
- 两 slice 原子边界保持
- Engine no-diff 有代码证据 + 设计真源 + regression test 三重验证
- closed allowlist 足以阻止扩域
- stop conditions 覆盖所有已知扩域路径

### 14.2 一条 Transient Validation Risk（低严重度，非 plan defect）

#### 001-未修复-低-Coverage 全绿基线未在独立验证中复现（首次失败、隔离未复现、与 R05 零 propagation 交集，根因未定）

- **位置**: plan §8 声称 green coverage 集为 `1916 passed, 1 skipped, 5 deselected`（全绿）
- **问题类型**: 独立验证观察（非 plan semantic defect）
- **当前写法**: plan §8 把该命令列为 required green gate，声称在 base 上已实测全绿
- **反例/失败场景**: 本 review 两次独立运行相同 coverage 命令（不同时间、不同 test order seed），结果均为 `1 failed, 1915 passed, 1 skipped, 5 deselected`。失败 node：`tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task`。详见 §0.4 的完整六元组登记。
- **为什么不是 plan defect 且不能用于弱化 plan gate**: 该 failure 的 call chain 为 scheduler.close() → wake_queue_promotion → health gate 抛出 `HostApiError: Host execution is unavailable at _execution_health.py:258`。与 R05 changed production files（`wait_adapter.py`、`durable/state.py`）及 R05 修改的全部语义路径（WaitPoller/observation timeout/claim release/backoff）**source 与 propagation 交集均为零**（双向 `rg` 零命中，见 §0.4）。隔离运行该 node 单独通过（`1 passed in 0.31s`）。根因当前未定——直接证据只证明：(a) 完整 coverage suite 首次出现该 `HostApiError`；(b) 同一 node 隔离复跑未复现；(c) 与 R05 owner paths 零 source/propagation 交集。单次隔离通过不能证明 root cause 已消除；零 R05 交集也不能替代根因定位。
- **为什么之前的 review artifact 没有登记**: plan §8 的 probe 时间和运行环境与本 review 不同。plan-fix artifact 已登记了无关 `test_toolruntime_executor.py` 的 15 个 `PicklingError` 并正确排除。该 `test_dispatch_scheduler` failure 未被之前任何一轮 review 的 coverage probe 触发。
- **直接证据**:
  - §0.4 的完整六元组（exact command、test node、error type、first stable stack frame `_execution_health.py:258`、call chain fingerprint、base SHA）
  - 双向 source/propagation `rg` 零命中（`wait_adapter`/`durable/state` ↔ `dispatch_scheduler`/`_execution_health` 无任何 import 关系）
  - 隔离 `pytest ...::test_wake_queue_promotion_uses_tracked_async_promotion_task` → `1 passed in 0.31s`
  - plan §8 的 claim：`1916 passed`（全绿）
  - 本 review 的两次独立复现：`1 failed, 1915 passed`（均非全绿）
- **影响**: 若 implementation Agent 严格运行 plan §8 的 coverage 命令且同一 node 再次失败，gate 会失败。这**不是授权弱化 plan 的 exact green requirement**。Implementation 仍必须要求完整 coverage command 全绿。若全量 suite 中该 node 再次失败，implementation Agent 必须先独立定位根因，排查结论需进入 implementation completion report；不能以 "R05 second re-review 已确认无关" 跳过。
- **建议改法和验证点**: **不修改 plan**。Implementation completion report 必须如实报告 coverage command 的 exact pass/fail count。若全绿则正常通过。若非全绿且失败 node 与 §0.4 六元组完全匹配（同 node、同 error type、同 stable frame、同 fingerprint），可引用本 artifact 的 propagation 证据说明与 R05 语义无关，但仍需记录 root cause 排查结论。若失败 node/error 不同，视为新增 failure，按 §13 stop condition 停回 Controller。
- **修复风险（低/中/高）**: N/A — 非 plan 修改项，属于 implementation 时的 validation risk。
- **严重程度（低/中/高/严重）**: 低 — 不影响 plan 语义正确性或 code-generation 判定；与 R05 changed files 零 source/propagation 交集；不阻断 code generation。根因未定，**明确不授权弱化 plan gate**。

---

## 15. Open Questions

**无 blocking open question。**

以下为已自行验证的设计级确认：

1. **Q**: `TERMINAL_RUN_STATUS_VALUES` 删除是否安全？
   **A**: 已确认。该符号在 `state.py` 中仅在 import line 40 出现（函数体内零引用）。`schema.py:20,186,192` 和 `test_state_schema.py:21,199,215` 有独立 import 路径。删除 `state.py` 的 import 不影响它们。

2. **Q**: `_release_with_backoff` 对 CANCELLED + ABANDON_ERROR 的 CAS 安全性？
   **A**: `release_wait_record_poll_claim` 的 WHERE 子句接受 `status IN (WAITING, CANCELLED)`，且要求 `poll_claim_id = ?`。CAS 语义与 WAITING 路径完全一致。无新增 race condition。

3. **Q**: design.md lines 2425-2427 已描述正确 poll timeout 行为但代码仍走 LOST，是否算 plan scope gap？
   **A**: 不算。plan §5.1 production 变更明确覆盖 poll `WaitObservationTimedOut` 分支（从 `WaitPollLost(ResolveWaitLostOutcome(...))` 改为 `_release_with_backoff`）。design 文本先行于代码是正常的——R05-S1 的代码修改将使两者一致。

---

## 16. Residual Risks

| # | Risk | 严重程度 | 分类 | Owner | 追踪 |
|---|---|---|---|---|---|
| RR-1 | cancelled abandon observation 可能长期 capped-backoff retry（每 300s）并间歇占用有限 observation capacity（max 8 concurrent） | 中 | `requiring new issue or explicit user decision` | future Host cancel/abandon durable evidence policy | R05 completion report；不与 Issue 175 混同 |
| RR-2 | Fins Docling 物理终止/containment | 中 | `tracked by existing issue` | Issue 175 | 不进入 R05 |
| RR-3 | public smoke 执行时间 ~65s，实现复杂度高（10 条要求 + 5 个 phases + 10 条 assertions） | 低 | `fixed in current slice` | R05-S2 implementation | event/condition/monotonic/margin 保障有界性 |
| RR-4 | plan §8 green coverage command 全绿 baseline 未在本次独立验证中复现（`test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task` 首次 `HostApiError`、隔离未复现、六元组见 §0.4）；与 R05 changed files 零 source/propagation 交集；根因未定 | 低 | `transient validation risk — not authorization to weaken plan gate` | R05 implementation completion report | Implementation 仍必须要求 coverage command 全绿；若同一 node 再现，先独立定位根因再报告 |
| RR-5 | callback transport / unified authorization / R06+ | 低 | `assigned to later work unit` | 既有 umbrella later WU/issue | 本 plan 无变更 |
| RR-6 | future explicit Host LOST durable evidence policy | 低 | `requiring new issue or explicit user decision` | future Host policy | R05 不预留 heuristic branch |
| RR-7 | full Ruff residual 165 条必须以六元组逐条验证，不能仅靠数量匹配豁免 | 低 | `implementation verification` | R05 implementation | plan §9.2 和 §12 已明确要求 |

---

## 17. 已关闭 Finding 最终状态

| Finding | 来源 | 轮次 | 最终状态 |
|---|---|---|---|
| MiMo 001（中）cancelled abandon 长期 retry | initial MiMo | 第一轮 | → PF-01 accepted narrowed → CLOSED |
| MiMo 002（低）smoke timing 敏感性 | initial MiMo | 第一轮 | → PF-02 accepted narrowed → CLOSED |
| DS RR-1（低）design.md "close marker" | initial DS | 第一轮 | → PF-03 accepted → CLOSED |
| DS RR-2（低）primitive dead code | initial DS | 第一轮 | → PF-04 accepted → CLOSED |
| DS RR-3（低）smoke 执行时间 | initial DS | 第一轮 | → 合并入 PF-02 → CLOSED |
| DS RR-4（无）backoff attempt 连续性 | initial DS | 第一轮 | → CLOSED_NO_ACTION |
| DS RR-5（低）smoke 覆盖缺口 | initial DS | 第一轮 | → CLOSED_BY_PLAN_SCOPE |
| MiMo 001（低）Ruff 基线遗漏 | re-review MiMo | 第二轮 | → PRR-F01 accepted narrowed → CLOSED |
| MiMo 子结论（test_wait_record_state 路径遗漏） | re-review MiMo | 第二轮 | → REJECTED（immutable plan 已包含该路径） |
| DS changed-file Ruff PASS | re-review DS | 第二轮 | → SUPERSEDED（实际为 2 条 F401） |

**全部 4 个 accepted plan findings（PF-01..04）+ 1 个 accepted re-review finding（PRR-F01）= 5 个已关闭。零 open finding。**

---

## 18. 与初审 / Re-Review / Controller 裁决的一致性检查

| Controller 核心判断 | 本 review 独立验证 | 结论 |
|---|---|---|
| root cause 在 `WaitPoller` decision owner | `wait_adapter.py:1102-1128` + `wait_adapter.py:1363-1382` 直接代码路径 | **一致** |
| `_wait_observation.py` token/fence 正确 | `_publish` 在同一锁下校验 token identity/state/closed/generation | **一致** |
| `waiting.py` typed terminal 正确 | `waiting.py:1016-1024` 只接受显式 `ResolveWaitLostOutcome` | **一致** |
| `durable/state.py` 足够且不需扩域 | `release_wait_record_poll_claim` 已支持 WAITING/CANCELLED | **一致** |
| `agent.py` no-diff | `agent.py:1974,2184` 只在 handshake 内读取 timeout | **一致** |
| CANCELLED 绕过 `_handle_time_boundary` | `wait_adapter.py:1021-1029` continue 跳过 line 1030 | **一致** |
| `poll_abandoned_at` 阻断机制 | `state.py:2537` claim query + `state.py:2777` timeout write | **一致** |
| PF-01..04 全部关闭 | 逐项复核 4 个 PF | **一致** |
| PRR-F01 关闭 | 逐项复核 changed-file Ruff 2 F401 + `165` residual | **一致** |
| 两 slice 原子边界 | S1 production transaction + S2 evidence | **一致** |
| closed allowlist 完整 | §6.2 精确列出所有可写路径 | **一致** |
| stop conditions 足够 | §13 的 11 条 stop conditions 覆盖全部扩域路径 | **一致** |

**无矛盾。所有 Controller 核心判断均被本 review 的独立代码证据确认。**

---

## 19. Final Plan Review Conclusion

**PASS**

该最终计划经过三轮独立 adversarial review（初审 MiMo/DS → re-review MiMo/DS → 本 second re-review），所有 mandatory lenses（architecture boundary、best-practice、optimal-solution、overengineering、overcoupling）均未发现 blocker。具体：

- **R05-PF-01..04 与 R05-PRR-F01**：全部真正关闭，每个都有独立代码证据验证
- **State machine owner / root cause**：精确（`WaitPoller` 对 `WaitObservationTimedOut` 的错误业务解释），无 owner 冲突或漂移
- **CANCELLED 长期 retry residual**：准确描述了 call order（绕过 `_handle_time_boundary`）、资源边界、future owner；不误称 deadline 收口
- **Durable invalid primitive 删除**：owner-boundary root fix；单点 consumer 删除 → primitive 无合法 caller；schema/compat 无扩域；`TERMINAL_RUN_STATUS_VALUES` import 仅 unused hygiene
- **Design writeback**：精确一句话纠错，消除 "close marker" 歧义，不引入新 policy/schema
- **Smoke event/condition/monotonic**：packaged values 下 operation window ~29s、总耗时 ~66s，CI cap 内完全有界；5 个 phase 全部可用 event/condition/state-poll 实现
- **两 slice**：S1 生产语义 transaction + S2 跨层 evidence；PF-03/PF-04 自然归入 S1；独立可回滚
- **Engine no-diff**：代码路径 + 设计真源 + git diff + regression test 四重验证
- **Test-first/coverage**：test-first 红→绿 策略正确；changed production file 逐文件 `>=80%`
- **Ruff**：changed-file 2 F401 已登记六元组；full Ruff `167→165` 预期精确
- **Pyright**：0 errors baseline 保持
- **Source/propagation/security scans**：全部可执行且预期明确
- **README**：决策正确
- **Security/deferred boundaries**：全部保持；Issue 175/callback/R06+/unified authorization 不进入本 WU

- **Coverage transient risk**：plan §8 green coverage 全绿 baseline 未在本次独立验证中复现（`test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task` 首次 `HostApiError`、隔离未复现，与 R05 changed files 零 source/propagation 交集，根因未定）。Implementation 仍必须要求 coverage command 全绿；若同一 node 再现，必须先独立定位根因，不能以 "reviewer 已排除" 豁免。

**计划已达到 code-generation-ready 标准。零 blocker、零 high/medium finding、零 blocking question。一条 low-severity transient validation risk（001）——非 plan semantic defect，不授权弱化 plan gate。下一 gate：Controller 裁决是否接受本次 second re-review 结论，并决定是否进入 implementation。**

---

*本 review 只写入了 `docs/reviews/wu-semantic-ownership-01-r05-plan-second-rereview-ds.md`。未修改 target plan、control、产品、测试、README、design 或任何既有 artifact。未 commit/push。*
