# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Adversarial Code Review — AgentDS

## 1. Verdict

**PASS — zero material finding, two observations**

七路径 product/test/design diff 在正确的 semantic owner boundary 内实现了 R05 的 poll/abandon observation timeout 非终态 release/backoff transaction。durable state 完整删除了 invalid timeout-only terminal primitive，WaitPoller 在两条 timeout 路径统一复用既有 `_release_with_backoff` 与 `release_wait_record_poll_claim`。late publication token/generation fence、authoritative typed LOST、explicit lifecycle terminal outcome、claim CAS、backoff policy、capacity、close gate 与 R04 config ownership 全部保留。测试断言了 owner contract 行为，没有自我实现 fake 或固化偶然行为。

两条 observation 已在下方详细说明，均不阻断 PASS。

## 2. Reviewed Evidence

| 类别 | 证据 | 验证方式 |
|---|---|---|
| Product | `dayu/host/durable/state.py` full diff | 逐行阅读，确认 `mark_wait_record_poll_abandon_timeout` 及 `TERMINAL_RUN_STATUS_VALUES` import 已删除，`release_wait_record_poll_claim` / `claim_wait_record_for_poll` / `mark_wait_record_poll_abandoned` 保留 |
| Product | `dayu/host/wait_adapter.py` full diff | 逐行阅读，确认 poll timeout → `_release_with_backoff(ADAPTER_ERROR/wait_observation_timeout)`，abandon timeout → `_release_with_backoff(ABANDON_ERROR/wait_abandon_timeout)`，无 `ResolveWaitLostOutcome` 构造，无 `_MarkWaitRecordAbandonTimeoutOperation` |
| Design | `docs/host/design.md` R05 句 | 确认第 2429-2432 行精确改写：timeout 是 poll-local transient diagnostic，保持 CANCELLED 且不写 `poll_abandoned_at` |
| Tests | `test_wait_observation_runner.py` | 两条新 owner tests + token invalidation + shared close deadline，共 4 条 |
| Tests | `test_wait_adapter_polling.py` | Ready/NotReady/LOST/adapter error/claim CAS/expired/abandon lifecycle/boundary tests |
| Tests | `test_phase7_waiting_integration.py` | poll timeout → WAITING → next round Ready → RESOLVED → RUNNING |
| Tests | `test_wait_record_state.py` | CANCELLED timeout release claimability + parameterized explicit terminal marker |
| No-diff | `_wait_observation.py` | `git diff --exit-code` PASS |
| No-diff | `waiting.py` | `git diff --exit-code` PASS |
| No-diff | `durable/schema.py` | `git diff --exit-code` PASS |
| No-diff | `agent.py` | `git diff --exit-code` PASS |
| No-diff | `dispatch.py`, `engine_ingest.py` | `git diff --exit-code` PASS |
| Controller | `wu-semantic-ownership-01-r05-s1-controller-validation.md` | PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW |
| Codex impl | `wu-semantic-ownership-01-r05-s1-implementation-codex.md` | 已读，与当前 diff 一致 |
| Codex continuation | `wu-semantic-ownership-01-r05-s1-validation-continuation-codex.md` | 已读，validation 证据可复现 |
| Plan | `wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md` | 已读，实现与 plan §3 owner 表精确对齐 |
| Issues control | `docs/host/issues-implementation-control.md` R05 gates | 已读，当前 gate 为 dual complete code review |

### 2.1 独立验证复跑

```text
# 核心 owner contract 节点
$ pytest -q tests/host/test_wait_observation_runner.py::test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve \
  tests/host/test_wait_observation_runner.py::test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal \
  tests/host/test_phase7_waiting_integration.py::test_poll_observation_timeout_keeps_waiting_then_ready_resumes_run \
  tests/host/test_wait_record_state.py::test_cancelled_poll_timeout_release_preserves_claimability_after_due \
  tests/host/test_wait_record_state.py::test_poll_abandon_success_marks_row_and_clears_claim
7 passed in 0.40s

# 四文件 full focused suite
$ pytest -q tests/host/test_wait_observation_runner.py tests/host/test_wait_adapter_polling.py \
  tests/host/test_phase7_waiting_integration.py tests/host/test_wait_record_state.py
69 passed in 0.91s

# pyright on changed production files
$ pyright dayu/host/durable/state.py dayu/host/wait_adapter.py
0 errors, 0 warnings, 0 informations

# git diff --check
PASS

# deleted symbol guard
$ rg 'mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation' dayu tests
ZERO HITS

# deleted import guard
$ rg 'TERMINAL_RUN_STATUS_VALUES' dayu/host/durable/state.py
ZERO HITS

# deleted UTC import
$ rg 'datetime.UTC' tests/host/test_phase7_waiting_integration.py
ZERO HITS

# deleted old wrong tests
$ rg 'test_stuck_poll_times_out_to_lost|test_stuck_abandon_writes_timeout_marker' tests
ZERO HITS
```

## 3. Finding Ledger

### Current Accepted: 0

### Observations: 2

---

### DS-OBS-01 — CANCELLED wait 的 deadline expiry 不在 poller 路径内处理

**严重度**: 观察（非阻断，plan 已登记为 deferred）

**位置**: `dayu/host/wait_adapter.py:991`（`record.status is WaitRecordStatus.CANCELLED` 先 `continue`，跳过 `_handle_time_boundary`）

**直接证据**:

```python
# wait_adapter.py:991-999
if record.status is WaitRecordStatus.CANCELLED:
    abandoned_delta, adapter_error_delta, conflict_delta, shutdown_delta = (
        self._abandon_cancelled_wait(record, claim_id)
    )
    ...
    continue
# _handle_time_boundary 只在后续非 CANCELLED 路径执行
boundary_release = self._handle_time_boundary(record, claim_id)
```

**语义分析**: 若 CANCELLED wait 的 `deadline_at` 已过期，poller 仍会尝试 `abandon_wait`（经 `_abandon_cancelled_wait`），仅当 provider 显式返回 applied/unsupported/noop 或 adapter 异常时才停止重试。expired deadline 不会被 `expire_wait` 路径拦截，因为 `_handle_time_boundary` 对 CANCELLED 不可达。

**为什么不是 finding**: plan §1.3 与 Controller validation §4 已将其登记为 RETAINED RESIDUAL，owner 为 future Host durable evidence policy。当前 claim CAS、capacity、finite timeout、late-result fence 与 capped backoff 限制资源但不创造 terminal evidence。本 observation 不改变该分类，仅确认代码路径与 plan 记录一致。

**建议**: 在 R05-S2 或后续 WU 中，由 Host durable evidence policy owner 决定 expired CANCELLED wait 是否应自动 fail closed（如复用 `expire_wait`），而不是永远重试 abandon。当前行为在 provider 永久不可达时会导致无限 backoff-capped retry。

---

### DS-OBS-02 — poll timeout 使用 `ADAPTER_ERROR` 而非专用 outcome

**严重度**: 观察（非阻断，受 plan §3.1 "不新增 enum" 约束）

**位置**: `dayu/host/wait_adapter.py:1077-1085`

**直接证据**:

```python
# wait_adapter.py:1077-1085
adapter_errors += 1
claim_conflicts += self._release_with_backoff(
    record,
    claim_id,
    outcome=WaitPollLastOutcome.ADAPTER_ERROR,
    error_code=_POLL_ERROR_CODE_OBSERVATION_TIMEOUT,
    error_message="wait adapter observation exceeded Host time budget",
)
```

**语义分析**: poll observation timeout 不是 adapter 错误——adapter 没有返回任何值。当前使用 `WaitPollLastOutcome.ADAPTER_ERROR` 使得 supervisor diagnostics 无法区分 "adapter 抛异常" 与 "Host 超时"。`error_code=wait_observation_timeout` 在 durable row 层面提供了区分，但 diagnostics snapshot 的 `adapter_errors` 计数混合了两种不同根因。

**为什么不是 finding**: plan §3.1 明确约束 "不得新增 schema/enum/default"。在既有 enum 中，`ADAPTER_ERROR` 是最接近的归类。两个场景的真实区分已经通过 `poll_last_error_code` 字段完成，audit 可精确识别。若未来需要 diagnostics-level 区分，应在独立 WU 中新增 `WaitPollLastOutcome` 值（如 `OBSERVATION_TIMEOUT`），并同步更新 diagnostics snapshot 字段。

**建议**: 若后续 WU 放开 enum 新增约束，考虑新增 `WaitPollLastOutcome.OBSERVATION_TIMEOUT` 并对应拆分 diagnostics 计数，使 operator 能从 supervisor diagnostics 直接区分超时与真正 adapter 异常。

---

## 4. Owner Contract 逐项确认

| 语义 | owner | 验证结果 |
|---|---|---|
| observation token/generation fence | `WaitObservationRunner` | PASS — `_publish` 校验 token identity、state、closed、generation；`dropped_count` 正确递增 |
| poll timeout → release + backoff, keep WAITING | `WaitPoller` | PASS — `_release_with_backoff(ADAPTER_ERROR/wait_observation_timeout)`，不构造 `WaitPollLost`，不调 `resolve_wait` |
| abandon timeout → release + backoff, keep CANCELLED | `WaitPoller` | PASS — `_release_with_backoff(ABANDON_ERROR/wait_abandon_timeout)`，不写 `poll_abandoned_at` |
| authoritative typed LOST | `WaitPoller` → `resolve_wait(ResolveWaitLostOutcome)` | PASS — `WaitPollLost` 仍完整保留，经 `_resolve_claimed_wait` → `resolver.resolve_wait` → `mark_run_lost_from_waiting_in_transaction` |
| explicit lifecycle terminal (applied/unsupported/noop) | `WaitPoller._abandon_cancelled_wait` → `mark_wait_record_poll_abandoned` | PASS — adapter success 后调用 `_MarkWaitRecordAbandonedOperation`，写 `poll_abandoned_at` + claim release，不调 `resolve_wait` |
| claim CAS | `claim_wait_record_for_poll` / `release_wait_record_poll_claim` | PASS — 两个函数均保留，CAS WHERE 条件完整 |
| backoff policy 唯一真源 | `_backoff_delay_seconds` + `_release_with_backoff` | PASS — poll/abandon timeout 统一使用 `_release_with_backoff`，公式不重复 |
| capacity / shared close deadline | `WaitObservationRunner` / `WaitPollerSupervisor` | PASS — `max_outstanding_adapter_calls` 限制不变，`close_drain_timeout_seconds` 单次 shared deadline 不变 |
| R04 config ownership | `awaiting_resolution_mode` / `host_runtime.json` | PASS — 三个 packaged provider mode 仍为 `poll`，12 字段 snapshot 无变化 |
| deleted symbol: `mark_wait_record_poll_abandon_timeout` | `dayu/host/durable/state.py` | PASS — production/tests 零定义、零调用 |
| deleted import: `TERMINAL_RUN_STATUS_VALUES` | `dayu/host/durable/state.py` | PASS — 已删除，`TERMINAL_RUN_STATUSES`（public alias）仍在使用 |
| deleted import: `datetime.UTC` | `tests/host/test_phase7_waiting_integration.py` | PASS — 已删除 |
| deleted old wrong tests | `test_stuck_poll_times_out_to_lost...` / `test_stuck_abandon_writes_timeout_marker...` | PASS — 已删除，由新 owner contract tests 替代 |
| Engine handshake no-diff | `dayu/engine/agent.py` | PASS — `git diff --exit-code` 确认空 diff |
| schema no-diff | `dayu/host/durable/schema.py` | PASS — `git diff --exit-code` 确认空 diff |
| scheduler/dispatch no-diff | `dayu/host/dispatch.py` / `engine_ingest.py` | PASS — `git diff --exit-code` 确认空 diff |

## 5. Retained Safety

以下安全机制经逐项确认未被弱化或删除：

- **Late publication token/generation fence**: `WaitObservationRunner._publish` 的四条件 guard（token identity、ACTIVE state、!closed、generation match）全部保留；`dropped_count` 单调递增。
- **Outstanding capacity**: `max_outstanding_adapter_calls` 限制不变；`WaitObservationCapacityExceeded` 在 cap 满时正确返回。
- **Claim CAS**: `claim_wait_record_for_poll` 的 `UPDATE ... WHERE` 仍然要求 status IN (WAITING, CANCELLED) 且 claim 可接管；`release_wait_record_poll_claim` 要求 claim_id 匹配。
- **Shared close deadline**: `WaitPollerSupervisor.close()` 仍使用单一 `close_drain_timeout_seconds`，不按线程数倍增。
- **Invalid deadline fail-closed**: `_handle_time_boundary` 的 INVALID boundary 仍调用 `_release_with_backoff(BOUNDARY_REJECTED)`，不调 provider、不写业务 LOST。
- **Expired wait 收口**: `_handle_time_boundary` 的 EXPIRED boundary 仍调用 `resolver.expire_wait`，不分裂终态。
- **Authoritative typed LOST**: `WaitPollLost(ResolveWaitLostOutcome(...))` 仍经 `_resolve_claimed_wait` → public `resolve_wait` → `mark_run_lost_from_waiting_in_transaction`。
- **Explicit lifecycle terminal**: `WaitExternalJobLifecycleApplied/Unsupported/Noop` 仍经 `_abandon_cancelled_wait` → `_MarkWaitRecordAbandonedOperation`，写 durable `poll_abandoned_at` + 清 claim。
- **R04 config ownership**: 三个 packaged provider mode 仍为 `poll`；`host_runtime.json` 12 字段 snapshot 与 accepted plan 一致。

## 6. Deferred Scope 完整性

以下 deferred items 经 source scan 确认零实现、零跨入：

| Item | owner/issue | 确认方式 |
|---|---|---|
| Issue 175 process-backed containment | existing Issue 175 | `rg 'process_backed\|subprocess\|process isolation' dayu --diff` → 零命中 |
| callback transport | deferred to later WU | `rg 'callback transport' dayu --diff` → 零命中 |
| unified authorization/permission | deferred to R06+ | `rg 'authorization\|permission' dayu --diff`（仅 pre-existing public API 字段） |
| R05-S2 Engine regression/public smoke | later approved R05-S2 | 当前 test files 无 R05-S2 覆盖 |
| R06+ | deferred | 零实现 |
| scheduler close / terminal promotion coordination | RETAINED RESIDUAL — Host scheduler lifecycle owner | `git diff --exit-code` PASS，probe 可复现，未修/未 waive |
| cancelled abandon 长期 timeout 无 terminal evidence | RETAINED RESIDUAL — future Host durable evidence policy owner | 行为与 plan 描述一致 |
| Host/tests README acceptance | R05-S2 | 未修改 |

## 7. Scheduler Residual 确认

原失败六元组保留且未因 R05-S1 diff 而变化：

- `dispatch.py`、`engine_ingest.py`、`test_dispatch_scheduler.py` 相对 fixed plan base 均为空 diff；
- R05 owner symbols（`wait_adapter`、`WaitPoller`、`WaitObservation`、`WaitRecord`、`mark_wait_record_poll_abandon_timeout`、`release_wait_record_poll_claim`）对 `test_dispatch_scheduler.py` 零命中；
- 确定性 probe `workspace/tmp/test_r05_scheduler_close_probe.py` 仍可复现 `HostApiError`。

R05-S1 没有误修、掩盖或引入新的 scheduler 传播。classification 保持 RETAINED RESIDUAL。

## 8. Test Quality 评估

### 8.1 Owner contract 断言

- `test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve`: 断言 poll timeout 后 `lost==0`、`adapter_errors==1`、`wait.status==WAITING`、`run.status==WAITING`、release fields 清空、backoff attempt==1、late Ready dropped、下一轮 Ready → RESOLVED。**覆盖 poll timeout 完整 lifecycle。**
- `test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal`: 断言 abandon timeout 后 `abandoned==0`、`adapter_errors==1`、`wait.status==CANCELLED`、`poll_abandoned_at is None`、release fields 清空、backoff attempt==1、late Applied dropped、下一轮 abandon success。**覆盖 abandon timeout 完整 lifecycle。**
- `test_cancelled_poll_timeout_release_preserves_claimability_after_due`: 断言 CANCELLED release 后 `poll_abandoned_at is None`、到期可再次 claim。**直接断言 durable owner contract。**
- `test_poll_abandon_success_marks_row_and_clears_claim`: parameterized over `ABANDONED/ABANDON_UNSUPPORTED/ABANDON_NOOP`，断言 explicit terminal marker 正确写入。**覆盖三个 lifecycle outcome。**

### 8.2 无自我实现 fake

- `_BlockingAdapter` 是真实 `WaitPollAdapter` Protocol 实现，通过 barrier control 模拟同步调用延迟。它不是 fake durable state、fake observation runner 或 fake resolve pipeline。
- `_RecordingPublicCommandResolver` 委托给真实 `resolve_wait` / `expire_wait` public command。它记录 idempotency key 但不替换 resolve 语义。
- `_NoResolveResolver` 用于 cancelled abandon 路径验证——正确断言 resolve_wait 不被调用。
- 无 raw SQL 直接写入绕过 public contract 的测试断言（`_set_poll_claim` 等 helper 只用于构造测试前提，不用于验证结果）。

### 8.3 覆盖缺口（已知且已登记）

- CANCELLED wait 的 expired deadline + abandon timeout 连续发生场景无显式测试。plan §1.3 已将 CANCELLED 长期 timeout 的行为登记为 RETAINED RESIDUAL。
- `_release_with_backoff` 在 CANCELLED 路径写入 `ABANDON_ERROR` 后，若 adapter 在下一次 poll 返回异常（非 timeout），release 仍会递增 `poll_backoff_attempt` 并重新计算 backoff。这个 "backoff 对 abandon error counting" 行为无专门测试，但它在 `test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal` 中已被间接覆盖（第二轮 poll 成功 abandon）。

### 8.4 时序脆弱性评估

- `test_supervisor_close_uses_one_shared_deadline_and_stays_closing` 使用 `time.monotonic()` 测量 elapsed，阈值 0.15s。在极慢 CI 环境可能 false positive。但这是 pre-existing 测试（非 R05-S1 新增），且 plan 已将其列为 R04 preservation baseline。不阻断当前 PASS。
- 其余 owner tests 使用 deterministic barrier（`threading.Event`）控制并发，不依赖 wall-clock sleep。

## 9. Type / Docstring / Maintainability

- `dayu/host/durable/state.py`: 模块与函数 docstring 完整；`release_wait_record_poll_claim` 与 `claim_wait_record_for_poll` 的 CAS WHERE 文档清晰。类型标注完整，pyright 零错误。
- `dayu/host/wait_adapter.py`: `WaitPoller.poll_once` 的 timeout 分支增加了正确的 docstring 注释（inline）；`_release_with_backoff` docstring 覆盖三个 timeout 分支需求。所有 `_POLL_ERROR_CODE_*` 常量有明确语义。pyright 零错误。
- `docs/host/design.md`: R05 句精确描述了 cancelled abandon timeout 的语义变更，与 wait_adapter.py 实现同源。
- 无 God object/function/dataclass；无兼容性 re-export/wrapper；无 `hasattr`/`getattr` 滥用。
- 无新增 `Any`、`object`、无类型参数。

## 10. Semantic Ownership Drift 检查

逐项对照 AGENTS.md 语义所有权约束：

- poll timeout diagnostic（`ADAPTER_ERROR / wait_observation_timeout`）的 owner 是 `WaitPoller`，production 在 `_release_with_backoff` → `release_wait_record_poll_claim` 投影到 durable。**无 drift。**
- abandon timeout diagnostic（`ABANDON_ERROR / wait_abandon_timeout`）的 owner 同样是 `WaitPoller`。**无 drift。**
- 两条 timeout 路径不再把 transient observation diagnostic 投影为 business LOST 或 terminal abandon——这正是 R05 修复的 root cause。**修复方向正确。**
- 测试断言直接引用 `WaitRecordStatus`、`WaitPollLastOutcome`、`RunStatus` 与 public `get_run`——全部来自 production public contract，不存在从 raw fields、日志或偶然行为反推语义。**无 drift。**
- `docs/host/design.md` 的 R05 句与 `wait_adapter.py` 实现逻辑一致。**设计真源与代码同源。**

## 11. Residual Owners 与下一入口

| residual | owner | destination |
|---|---|---|
| scheduler close / terminal promotion coordination | Host scheduler lifecycle (`dispatch.py` / `engine_ingest.py`) | Controller / user 裁决独立修复 gate |
| CANCELLED abandon 长期 timeout 无 terminal evidence | future Host durable evidence policy | deferred to later WU |
| DS-OBS-01（CANCELLED + expired deadline 不在 poller 路径处理） | future Host durable evidence policy（同上一项） | same deferred destination |
| DS-OBS-02（ADAPTER_ERROR 语义混合） | 可在后续 WU 放开 enum 约束时处理 | optional cleanup |
| R05-S2 Engine regression / public smoke / README | per accepted plan | next authorized gate |

## 12. Stop Status

本 review 完成。不修改产品、测试、设计、control、plan 或既有 artifacts。等待 Controller 裁决全部 findings 后，由 Controller 决定是否进入 fix / re-review / R05-S2 / S1 product commit。

---

**Reviewer**: AgentDS
**Date**: 2026-07-15
**Reviewed digest**: `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`
