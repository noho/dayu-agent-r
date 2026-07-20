# WU-SEMANTIC-OWNERSHIP-01 R05-S1 Code Re-Review — AgentDS 第二路

## 1. Verdict

**PASS — zero material finding / no required fix gate.**

Controller final ledger 与本 re-review 独立确认一致：

| 分类 | 数量 | 状态 |
|---|---:|---|
| accepted current finding | 0 | CLOSED |
| rejected-as-finding observation | 1 | DS-OBS-02（`ADAPTER_ERROR` aggregation），NO_CURRENT_DEFECT，无当前修改 destination |
| retained residual | 1 | DS-OBS-01（CANCELLED + expired deadline 不在 poller 路径），future Host durable evidence policy |
| blocker | 0 | NONE |

本第二路独立完整 adversarial code re-review 对七路径 product/test/design diff、全部 existing review/fix evidence、no-diff owners、retained safety、deferred scope、scheduler residual 与 Controller adjudication 逐项进行了独立验证。所有验证均通过，七路径 protected digest 保持 `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`，zero-change proof 可信。两条原始 DS observation 的 Controller disposition 经独立复核仍正确，无新增 finding。

## 2. Reviewed Evidence (完整独立)

本 re-review 完整独立读取并验证了以下全部证据，不是只看 zero-change artifact 或依赖第一路 MiMo review：

### 2.1 指令与设计文档
| 文档 | 验证方式 |
|---|---|
| `AGENTS.md` | 完整读取；语义所有权约束、编码硬约束、架构硬约束作为审查基准 |
| `docs/host/issues-implementation-control.md` | 读取 R05 gate 状态段落 |
| `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md` | 完整读取；作为 owner contract 基准 |

### 2.2 现有 review artifacts
| artifact | 验证方式 |
|---|---|
| `implementation-codex.md` | 完整读取；确认实现与 diff 一致 |
| `validation-continuation-codex.md` | 完整读取；确认 validation evidence 可复现 |
| `controller-validation.md` | 完整读取；确认 Controller PASS / READY_FOR_DUAL_COMPLETE_CODE_REVIEW |
| `code-review-mimo.md` | 完整读取；交叉核对其 finding ledger |
| `code-review-ds.md` | 完整读取；交叉核对两条 observation |
| `code-review-controller-adjudication.md` | 完整读取；确认 Controller disposition |
| `code-review-fix-codex.md` | 完整读取；确认 zero-change record 可信 |
| `code-review-fix-controller-validation.md` | 完整读取；确认 Controller PASS / READY_FOR_DUAL_COMPLETE_CODE_REREVIEW |

### 2.3 七路径 product/test/design diff — 逐行独立阅读
| 路径 | 变更行数 | 验证方式 |
|---|---|---|
| `dayu/host/durable/state.py` | -73 | 确认删除 `mark_wait_record_poll_abandon_timeout`（78 行）+ 仅服务 invalid semantic 的代码 + unused `TERMINAL_RUN_STATUS_VALUES` import；`release_wait_record_poll_claim` 与 `mark_wait_record_poll_abandoned` 保留 |
| `dayu/host/wait_adapter.py` | +28/-77 | 确认 poll timeout → `_release_with_backoff(ADAPTER_ERROR/wait_observation_timeout)`，abandon timeout → `_release_with_backoff(ABANDON_ERROR/wait_abandon_timeout)`；删除 `_MarkWaitRecordAbandonTimeoutOperation` wrapper/import/call |
| `docs/host/design.md` | +4/-2 | 确认精确 R05 句改写：timeout → poll-local transient diagnostic + release/backoff，保持 CANCELLED 且不写 `poll_abandoned_at` |
| `tests/host/test_wait_observation_runner.py` | +134/-30 | 两条新 owner tests + `_MutableClock` + `_BlockingAdapter` 改造为返回 Ready |
| `tests/host/test_wait_adapter_polling.py` | +6/-2 | authoritative lost test 增加 idempotency key 断言 |
| `tests/host/test_phase7_waiting_integration.py` | +93/-2 | 新 integration test + 删除 `datetime.UTC` import |
| `tests/host/test_wait_record_state.py` | +69 | 新 CANCELLED timeout release claimability test |

### 2.4 No-diff owners — 独立 git diff --exit-code 验证
| 文件 | 结果 |
|---|---|
| `dayu/host/_wait_observation.py` | PASS / empty diff |
| `dayu/host/waiting.py` | PASS / empty diff |
| `dayu/engine/agent.py` | PASS / empty diff |
| `dayu/host/durable/schema.py` | PASS / empty diff |
| `dayu/host/dispatch.py` | PASS / empty diff |
| `dayu/host/engine_ingest.py` | PASS / empty diff |
| `tests/host/test_dispatch_scheduler.py` | PASS / empty diff |
| R05-S2 / README / config / Service / Fins paths | PASS / empty diff |

### 2.5 独立验证复跑

所有以下命令由本 re-review 独立执行，非引用既有 evidence：

```text
# 七路径 protected digest
$ git diff --binary 5ba0d8b... -- <seven paths> | shasum -a 256
3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2  — 与 protected value 精确一致

# 实际 changed production list
$ git diff --name-only 5ba0d8b... -- dayu
dayu/host/durable/state.py
dayu/host/wait_adapter.py  — 精确两文件

# 核心 owner contract 节点
$ pytest -q <五个 owner nodes>
7 passed in 0.40s

# 安全矩阵（12 个 focused nodes）
$ pytest -q <12 个 safety/token/lost/CAS/expired/abandon boundary nodes>
12 passed in 0.45s

# 四个 Host focused 文件
$ pytest -q test_wait_observation_runner.py test_wait_adapter_polling.py \
  test_phase7_waiting_integration.py test_wait_record_state.py
69 passed in 0.92s

# R04 config/composition preservation
$ pytest -q <17 个 R04 preservation nodes>
17 passed, 3 warnings in 1.00s

# pyright on changed production files
$ pyright dayu/host/durable/state.py dayu/host/wait_adapter.py
0 errors, 0 warnings, 0 informations

# Full pyright
$ pyright dayu/ tests/ utils/
0 errors, 0 warnings, 0 informations

# Changed-file Ruff
$ ruff check <八个 changed/related Python files>
All checks passed!

# Invalid timeout symbol guard
$ rg 'mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation' dayu tests
ZERO HITS (exit 1 / PASS)

# Deleted import guard — TERMINAL_RUN_STATUS_VALUES
$ rg 'TERMINAL_RUN_STATUS_VALUES' dayu/host/durable/state.py
ZERO HITS

# Deleted import guard — datetime.UTC
$ rg 'datetime.UTC' tests/host/test_phase7_waiting_integration.py
ZERO HITS

# Deleted old wrong test names
$ rg 'test_stuck_poll_times_out_to_lost|test_stuck_abandon_writes_timeout_marker' tests
ZERO HITS

# git diff --check
PASS

# Scheduler deterministic probe
$ pytest workspace/tmp/test_r05_scheduler_close_probe.py
1 passed in 0.30s

# Scheduler test R05 symbol scan
$ rg 'wait_adapter|WaitPoller|WaitObservation|WaitRecord|...' tests/host/test_dispatch_scheduler.py
ZERO HITS (exit 1 / PASS)

# Engine no-diff
$ git diff --exit-code 5ba0d8b... -- dayu/engine/agent.py
PASS

# Schema no-diff
$ git diff --exit-code 5ba0d8b... -- dayu/host/durable/schema.py
PASS
```

## 3. Finding Ledger — 逐维度独立验证

### 3.1 Semantic owner 判定

**结论：正确，无 finding。**

| 语义 | owner | 当前实现 | 验证 |
|---|---|---|---|
| observation token/generation fence | `WaitObservationRunner` | `_publish` 检查 token identity、ACTIVE state、!closed、generation match，均在 `_lock` 内；timeout 先 `_invalidate_token` 再 `queue.Empty` | `_wait_observation.py` no diff，`test_timeout_invalidates_token_and_late_result_cannot_publish` 通过 |
| poll timeout 解释 | `WaitPoller` | `_release_with_backoff(ADAPTER_ERROR/wait_observation_timeout)`，不构造 `WaitPollLost`，不调 `_resolve_claimed_wait` | `wait_adapter.py:1072-1085` 逐行确认 |
| abandon timeout 解释 | `WaitPoller` | `_release_with_backoff(ABANDON_ERROR/wait_abandon_timeout)`，不写 `poll_abandoned_at`，不调 terminal marker | `wait_adapter.py:1320-1334` 逐行确认 |
| claim release/backoff 唯一真源 | `WaitPoller._release_with_backoff` + `release_wait_record_poll_claim` | `next_attempt = record.poll_backoff_attempt + 1` → `_backoff_delay_seconds(next_attempt, policy)` → durable atomic update | `wait_adapter.py:1473-1495`、`state.py:2589-2659` 逐行确认 |
| authoritative typed LOST | `WaitPoller._resolve_claimed_wait` → `resolver.resolve_wait` | `WaitPollLost(ResolveWaitLostOutcome(...))` 仍完整保留 | `wait_adapter.py:1113-1128`、`test_poll_adapter_lost_result_closes_run` 通过 |
| explicit lifecycle terminal (applied/unsupported/noop) | `WaitPoller._abandon_cancelled_wait` → `mark_wait_record_poll_abandoned` | `_MarkWaitRecordAbandonedOperation` 仍调用 `mark_wait_record_poll_abandoned`，写 `poll_abandoned_at` | `wait_adapter.py:1337-1357`、`state.py:2662-2724` 逐行确认 |
| deleted invalid primitive | `dayu/host/durable/state.py` | `mark_wait_record_poll_abandon_timeout` 零定义零调用 | `rg` exit 1 / PASS |

### 3.2 Poll/abandon 返回计数、CAS、backoff、diagnostic、Run/Wait projection

**结论：正确，无 finding。**

逐项独立验证（与原始 DS review 一致）：

| 维度 | poll timeout 行为 | abandon timeout 行为 | 验证方式 |
|---|---|---|---|
| `lost` 计数 | `lost == 0` | N/A | `test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve:361` |
| `abandoned` 计数 | N/A | `abandoned == 0` | `test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal:440` |
| `adapter_errors` | `adapter_errors == 1` | `adapter_errors == 1` | 同上测试 |
| claim 清理 (4 fields) | 全部 `None` | 全部 `None` | `test_wait_observation_runner.py:368-371`、`:452-455` |
| backoff attempt | `poll_backoff_attempt == 1` | `poll_backoff_attempt == 1` | `test_wait_observation_runner.py:382`、`:458` |
| next_observe_at | `clock.now() + 0.01s` (test override) | 同左 | `test_wait_observation_runner.py:383-385`、`:459-461` |
| poll_last_outcome | `ADAPTER_ERROR` | `ABANDON_ERROR` | `test_wait_observation_runner.py:386`、`:462` |
| poll_last_error_code | `"wait_observation_timeout"` | `"wait_abandon_timeout"` | `test_wait_observation_runner.py:387`、`:463` |
| poll_abandoned_at | 不写入 / `None` | 不写入 / `None` | `test_wait_observation_runner.py:455` |
| Wait 状态 | `WAITING` | `CANCELLED` | `test_wait_observation_runner.py:367`、`:451` |
| Run 状态 | `WAITING` | N/A | `test_wait_observation_runner.py:366` |
| resolver 调用 | 零调用 | 零调用 | `resolver.idempotency_keys == []`、`resolver.calls == []` |

Backoff 公式独立验证：`_backoff_delay_seconds` 在 `wait_adapter.py:1886-1889` 使用 `initial * (multiplier ** (attempt - 1))` 封顶 `max_delay`；`_release_with_backoff` 在 `wait_adapter.py:1475` 使用 `record.poll_backoff_attempt + 1`。两个 timeout 分支均调用同一 `_release_with_backoff`，无 timeout-local 时间公式、无第二 scheduler/policy。

### 3.3 Late publication token/generation fence 与跨轮污染

**结论：正确，无 finding。**

独立源码验证：

1. `WaitObservationRunner._start_observation`（`_wait_observation.py:288-306`）：创建 token 含 `generation=self._generation`、`result_queue=queue.Queue(maxsize=1)`
2. `WaitObservationRunner.observe`（`_wait_observation.py:204-220`）：timeout 在 `queue.Empty` 后调用 `self._invalidate_token(token)`，同一 registry lock 下检查 `token.state is ACTIVE`
3. `WaitObservationRunner._publish`（`_wait_observation.py:336-361`）：同一 lock 下四条件 guard — token identity、ACTIVE state、!closed、generation match；失败 → `dropped_count += 1`
4. 下一轮 `poll_once()` 创建全新 claim、新 observation、新 token；旧 token 已 INVALIDATED/FINISHED，result_queue maxsize=1 无跨轮污染路径

测试验证：`runner.diagnostics_snapshot().dropped_count == 1`、`runner.diagnostics_snapshot().invalidated_count == 1`。

### 3.4 Authoritative typed LOST、Ready/NotReady、explicit lifecycle terminal

**结论：正确，无 finding。**

独立验证：

- `WaitPollLost(ResolveWaitLostOutcome(...))` 仍完整保留在 typed public contract；`test_poll_adapter_lost_result_closes_run` 新增 `_RecordingPublicCommandResolver` idempotency key 断言 + `poll_last_error_code is None` 断言，确认 authoritative lost 仍走 `_resolve_claimed_wait` → `resolver.resolve_wait` → `mark_run_lost_from_waiting_in_transaction`
- `test_poll_adapter_ready_result_resolves_wait`、`test_poll_adapter_not_ready_leaves_wait_active` 保持原断言
- `test_cancelled_poll_wait_is_abandoned_once_without_resolve` 保持 explicit lifecycle terminal 的 `mark_wait_record_poll_abandoned` 路径
- `test_poll_abandon_success_marks_row_and_clears_claim` parameterized over `ABANDONED`/`ABANDON_UNSUPPORTED`/`ABANDON_NOOP`，均写 durable `poll_abandoned_at`
- `test_cancelled_poll_timeout_release_preserves_claimability_after_due` 证明 timeout release 后 `poll_abandoned_at is None`、到期可再次 claim

### 3.5 Durable primitive 删除 — dead import/caller/schema drift/public contract

**结论：正确，无 finding。**

独立验证：

- `mark_wait_record_poll_abandon_timeout`：production + tests 零定义、零调用（`rg` exit 1）
- `_MarkWaitRecordAbandonTimeoutOperation`：production + tests 零定义、零调用（`rg` exit 1）
- `mark_wait_record_poll_abandon_timeout` import 已从 `wait_adapter.py` 删除
- `TERMINAL_RUN_STATUS_VALUES` unused import 已从 `state.py` 删除
- `datetime.UTC` unused import 已从 `test_phase7_waiting_integration.py` 删除
- `dayu/host/durable/schema.py` no diff；`poll_abandoned_at` schema 字段保留
- `mark_wait_record_poll_abandoned(...)` 保留并继续服务 explicit lifecycle outcome
- `release_wait_record_poll_claim(...)` 保留，WHERE 子句中 `status IN (WAITING, CANCELLED)` 同时支持两条路径

### 3.6 Tests — owner contract、fake、时序、覆盖缺口

**结论：正确，无 finding。**

**Owner contract 断言质量：**
- 新 timeout tests 断言完整 claim 清理（四个 fields）、backoff attempt/next-observe、diagnostic code/outcome、Wait/Run 状态、resolver 零调用、late result dropped、下一轮恢复
- `_RecordingPublicCommandResolver` 记录 idempotency keys 但不替换 resolve 语义
- `_NoResolveResolver` 正确用于 abandon path 验证 resolve_wait 不被调用

**`_BlockingAdapter` 改造分析（关键 adversarial 检查）：**
- 旧 `_BlockingAdapter.poll_wait()` 返回 `WaitPollNotReady()`
- 新实现返回 `WaitPollReady(ResolveWaitCompletedOutcome(...))`
- **为什么是正确改造**：late result 必须是 Ready 才能验证 token fence（如果 late result 是 NotReady，poll_once 只释放 claim 并 schedule 短间隔复查，不进入 resolve path，无法证明 fence 阻止了 resolution）。改为 Ready 后，late publication 被 fence 拒绝，但下一轮主动 poll 拿到新 Ready → resolved = 1，同一条 test 既验证 fence 又验证 recovery。
- 无自我实现 fake：`_BlockingAdapter` 是真实 `WaitPollAdapter` Protocol 实现，通过 barrier control（`threading.Event`）模拟同步调用延迟

**时序确定性：**
- `_MutableClock` 显式 `advance(0.01)`，匹配 test override `backoff_initial_delay_seconds=0.01`，不依赖 `time.sleep()`
- `test_supervisor_close_uses_one_shared_deadline_and_stays_closing` 使用 `time.monotonic()`（pre-existing，非 R05-S1 新增，plan 已登记）

**覆盖缺口（已知且已登记）：**
- CANCELLED + expired deadline + abandon timeout 连续场景：plan §1.3 已登记为 RETAINED RESIDUAL
- 第二轮 abandon error backoff 计数：已被 `test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal` 间接覆盖（第二轮成功 abandon）

### 3.7 Type/docstring/coupling/semantic drift

**结论：正确，无 finding。**

- 所有新增/修改函数保持完整类型签名和中文 docstring
- `_MutableClock` 类型实现 `WaitPollClock` protocol，`now()` 返回 `datetime`
- `docs/host/design.md` R05 句与 `wait_adapter.py` 实现逻辑一致，设计真源与代码同源
- production diff 只涉及 `wait_adapter.py` 与 `state.py` 两个 owner 文件，无 coupling 增加
- 无 God object/function/dataclass；无兼容性 re-export/wrapper；无 `hasattr`/`getattr` 滥用
- 无新增 `Any`、`object`、无类型参数
- LLM-facing 文本不受影响（R05 不修改 tool schema、prompt、memory projection）

### 3.8 Retained safety — 是否被弱化

**结论：正确，无 finding。**

| 安全机制 | 状态 | 独立验证 |
|---|---|---|
| late publication token/generation fence | 保留 | `_wait_observation.py` no diff + `_publish` 四条件 guard + `dropped_count` |
| outstanding capacity | 保留 | `max_outstanding_adapter_calls` 不变 |
| shared close deadline | 保留 | `test_supervisor_close_uses_one_shared_deadline_and_stays_closing` 通过 |
| claim token CAS | 保留 | `claim_wait_record_for_poll` 的 WHERE 仍要求 status IN (WAITING, CANCELLED) |
| release/backoff 唯一真源 | 保留 | 两条 timeout branch 复用同一 `_release_with_backoff` |
| next-due claimability | 保留 | `test_cancelled_poll_timeout_release_preserves_claimability_after_due` 通过 |
| authoritative typed LOST via common resolver | 保留 | `test_poll_adapter_lost_result_closes_run` 通过 + idempotency key 断言 |
| explicit lifecycle terminal marker | 保留 | parameterized test 覆盖 ABANDONED/ABANDON_UNSUPPORTED/ABANDON_NOOP |
| invalid deadline fail-closed | 保留 | `test_invalid_poll_deadline_fails_closed_without_business_lost` 通过 |
| expired wait 收口 (non-CANCELLED) | 保留 | `_handle_time_boundary` 继续调用 `expire_wait` |
| invalid timeout-only symbol | 确认零残留 | `rg` exit 1 |

### 3.9 Deferred scope — 是否偷带

**结论：零偷带，无 finding。**

独立 security/deferred scope scan：
```text
$ git diff --unified=0 5ba0d8b... -- dayu | rg 'authorization|permission|callback transport|process isolation|process_backed|subprocess|Issue 175'
ZERO HITS (exit 1 / PASS)
```

以下 deferred items 均零实现：Issue 175、callback transport、unified authorization/permission、R05-S2 Engine regression/public smoke/README、R06+。

### 3.10 Scheduler residual — 是否被误修、掩盖或引入新传播

**结论：正确，无 finding。**

独立验证：
- `dispatch.py`、`engine_ingest.py`、`test_dispatch_scheduler.py` 相对 fixed plan base 均为 empty diff
- `test_dispatch_scheduler.py` 对 R05 owner symbols（`wait_adapter`、`WaitPoller`、`WaitObservation`、`WaitRecord`、`mark_wait_record_poll_abandon_timeout`、`release_wait_record_poll_claim`）零命中（`rg` exit 1）
- 确定性 probe `workspace/tmp/test_r05_scheduler_close_probe.py` 仍 `1 passed`，以预期 `HostApiError` 为通过条件，可确定性复现 close gate → clean EOF terminal closeout → promotion wake rejection
- 未修、未 waive、未建 issue、未归 Issue 175
- classification 保持 RETAINED RESIDUAL：独立 Host scheduler lifecycle owner

### 3.11 Controller 对原始两条 DS observation 的 disposition 复核

**结论：disposition 合理，无漏掉的可达 defect。**

| observation | Controller disposition | 本 re-review 独立判定 |
|---|---|---|
| DS-OBS-01: CANCELLED + expired deadline 不在 poller 路径处理 | `RETAINED_RESIDUAL / NO_R05-S1_FIX` | **同意**。`poll_once:991` 对 CANCELLED 先 `continue`，`_handle_time_boundary` 不可达。这是 accepted plan 已登记的同一 residual；owner 是 future Host durable evidence policy。R05-S1 的 claim CAS、finite timeout、capacity、late-result fence 与 capped backoff 限制资源但不创造 terminal evidence。 |
| DS-OBS-02: poll timeout 复用 `ADAPTER_ERROR` 而非专用 outcome | `NO_CURRENT_DEFECT / NO_FIX` | **同意**。plan §3.1 明确禁止新增 enum。durable `poll_last_error_code=wait_observation_timeout` 已在 row 层面提供根因区分。当前 public contract 未承诺 `adapter_errors` 聚合只统计 provider exception，没有业务消费者要求新 enum。 |

原始 DS review 对 shared-close wall-clock test 的 CI timing 备注和第二轮 abandon error backoff 的备注：前者是 pre-existing 测试（非 R05-S1 新增），后者已由完整 owner transaction 间接覆盖。不构成可达 defect。

### 3.12 Zero-change proof 可信度

**结论：可信，无 finding。**

独立验证：
- 七路径 protected digest 在创建前后均为 `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`
- `git diff --check` PASS
- actual changed production list 精确为 `dayu/host/durable/state.py` 与 `dayu/host/wait_adapter.py`
- AgentCodex zero-change artifact 前后 protected content、path set、evidence chain、working-tree status 均未变化
- Controller fix-validation 独立确认了以上所有

## 4. Owner Contract 逐项确认表

| 语义 | owner | 独立验证结果 |
|---|---|---|
| observation token/generation fence | `WaitObservationRunner` | PASS — `_publish` 四条件 guard，`dropped_count` 递增 |
| poll timeout → release + backoff, keep WAITING | `WaitPoller` | PASS — `_release_with_backoff(ADAPTER_ERROR/wait_observation_timeout)` |
| abandon timeout → release + backoff, keep CANCELLED | `WaitPoller` | PASS — `_release_with_backoff(ABANDON_ERROR/wait_abandon_timeout)`，不写 `poll_abandoned_at` |
| authoritative typed LOST | `WaitPoller` → `resolve_wait(ResolveWaitLostOutcome)` | PASS — `WaitPollLost` 保留，经 `_resolve_claimed_wait` |
| explicit lifecycle terminal | `_abandon_cancelled_wait` → `mark_wait_record_poll_abandoned` | PASS — `_MarkWaitRecordAbandonedOperation` 保留，写 `poll_abandoned_at` |
| claim CAS | `claim_wait_record_for_poll` / `release_wait_record_poll_claim` | PASS — WHERE 条件完整 |
| backoff policy 唯一真源 | `_backoff_delay_seconds` + `_release_with_backoff` | PASS — 公式不重复，无 timeout-local 计算 |
| capacity / shared close deadline | `WaitObservationRunner` / `WaitPollerSupervisor` | PASS — `max_outstanding_adapter_calls` 与 `close_drain_timeout_seconds` 不变 |
| R04 config ownership | `awaiting_resolution_mode` / `host_runtime.json` | PASS — 17 个 preservation tests 通过 |
| deleted symbol 零残留 | `state.py` | PASS — `rg` 零匹配 |
| Engine handshake no-diff | `agent.py` | PASS — `git diff --exit-code` 空 diff |
| schema no-diff | `durable/schema.py` | PASS — `git diff --exit-code` 空 diff |
| scheduler no-diff | `dispatch.py` / `engine_ingest.py` | PASS — `git diff --exit-code` 空 diff |

## 5. Retained Safety 确认

以下安全机制经逐项独立确认未被弱化或删除：

- **Late publication token/generation fence**: `WaitObservationRunner._publish` 的四条件 guard（token identity、ACTIVE state、!closed、generation match）全部保留
- **Outstanding capacity**: `max_outstanding_adapter_calls` 限制不变
- **Claim CAS**: `claim_wait_record_for_poll` 的 WHERE 条件要求 status IN (WAITING, CANCELLED)；`release_wait_record_poll_claim` 要求 claim_id 匹配
- **Shared close deadline**: `WaitPollerSupervisor.close()` 仍使用单一 `close_drain_timeout_seconds`
- **Invalid deadline fail-closed**: `_handle_time_boundary` 的 INVALID boundary 仍调用 `_release_with_backoff(BOUNDARY_REJECTED)`
- **Expired wait 收口**: `_handle_time_boundary` 的 EXPIRED boundary 仍调用 `resolver.expire_wait`
- **Authoritative typed LOST**: `WaitPollLost(ResolveWaitLostOutcome(...))` 仍经 `_resolve_claimed_wait` → public `resolve_wait`
- **Explicit lifecycle terminal**: `WaitExternalJobLifecycleApplied/Unsupported/Noop` 仍经 `_abandon_cancelled_wait` → `_MarkWaitRecordAbandonedOperation`
- **R04 config ownership**: 三个 packaged provider mode 仍为 `poll`；12 字段 snapshot 与 accepted plan 一致

## 6. Deferred Scope 完整性

以下 deferred items 经独立 source scan 确认零实现：

| Item | owner/issue | 确认方式 |
|---|---|---|
| Issue 175 process-backed containment | existing Issue 175 | production diff added-lines 零命中 |
| callback transport | deferred to later WU | 同上 |
| unified authorization/permission | deferred to R06+ | 同上 |
| R05-S2 Engine regression/public smoke | later approved R05-S2 | `tests/engine`、`utils/smoke` 空 diff |
| R06+ | deferred | 零实现 |
| scheduler close / terminal promotion coordination | RETAINED RESIDUAL | probe 可复现，未修/未 waive |
| cancelled abandon 长期 timeout 无 terminal evidence | RETAINED RESIDUAL | 行为与 plan 描述一致 |

## 7. Scheduler Residual 确认

独立验证：
- `dispatch.py`、`engine_ingest.py`、`test_dispatch_scheduler.py` 相对 fixed plan base 均为 empty diff
- R05 owner symbols 对 `test_dispatch_scheduler.py` 零命中
- 确定性 probe `workspace/tmp/test_r05_scheduler_close_probe.py` 仍 `1 passed`
- R05-S1 没有误修、掩盖或引入新的 scheduler 传播
- classification 保持 RETAINED RESIDUAL：独立 Host scheduler lifecycle owner，未修、未 waive、未建 issue、未归 Issue 175

## 8. Test Quality 独立评估

### 8.1 Owner contract 断言

- `test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve`: 完整断言 poll timeout → release/backoff → late Ready dropped → next round Ready resolve。共覆盖 15+ assertions。
- `test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal`: 完整断言 abandon timeout → release/backoff → late Applied dropped → next round explicit terminal。共覆盖 15+ assertions。
- `test_cancelled_poll_timeout_release_preserves_claimability_after_due`: 直接在 durable owner boundary 断言 claim → release → retry claim 的完整 CAS pipeline。
- `test_poll_abandon_success_marks_row_and_clears_claim`: parameterized over ABANDONED/ABANDON_UNSUPPORTED/ABANDON_NOOP。

### 8.2 无自我实现 fake

- `_BlockingAdapter` 是 `WaitPollAdapter` Protocol 的真实实现
- `_RecordingPublicCommandResolver` 委托给真实 public command
- `_NoResolveResolver` 正确用于验证 resolve 不被调用
- `_MutableClock` 实现 `WaitPollClock` protocol
- 无 raw SQL 直接写入绕过 public contract 的测试断言

### 8.3 时序脆弱性

- 所有新 owner tests 使用 deterministic barrier（`threading.Event`）控制并发
- `_MutableClock.advance()` 显式推进时间，不依赖 wall-clock sleep
- `test_supervisor_close_uses_one_shared_deadline_and_stays_closing` 使用 `time.monotonic()` — pre-existing，非 R05-S1 新增

## 9. Type / Docstring / Maintainability

- `dayu/host/durable/state.py`: 模块与函数 docstring 完整；类型标注完整，pyright 零错误
- `dayu/host/wait_adapter.py`: `_release_with_backoff` docstring 覆盖三个 release 分支；所有 `_POLL_ERROR_CODE_*` 常量有明确语义
- `docs/host/design.md`: R05 句精确描述 timeout 语义变更，与代码同源
- 无 God object/function/dataclass；无兼容性 re-export/wrapper；无 `hasattr`/`getattr` 滥用
- 无新增 `Any`、`object`、无类型参数
- `_MutableClock` 类型正确实现 `WaitPollClock` protocol

## 10. Semantic Ownership Drift 检查

逐项对照 AGENTS.md 语义所有权约束：

- poll timeout diagnostic（`ADAPTER_ERROR / wait_observation_timeout`）owner 是 `WaitPoller`，projection 通过 `release_wait_record_poll_claim` → durable。**无 drift。**
- abandon timeout diagnostic（`ABANDON_ERROR / wait_abandon_timeout`）owner 同为 `WaitPoller`。**无 drift。**
- 两条 timeout 路径不再把 transient observation diagnostic 投影为 business LOST 或 terminal abandon — R05 root cause 修复正确。**无 drift。**
- 测试断言直接引用 `WaitRecordStatus`、`WaitPollLastOutcome`、`RunStatus` 与 public `get_run` — 全部来自 production public contract。**无 drift。**
- `docs/host/design.md` R05 句与 `wait_adapter.py` 实现逻辑一致。**无 drift。**
- `_wait_observation.py` 继续唯一拥有 publication fence；adapter/store 没有新建 token/queue/future。**无 drift。**
- `waiting.py` 继续唯一拥有 typed terminal resolution；timeout code 不出现在其 owner boundary。**无 drift。**

## 11. Finding Ledger 与 Destination

按 Controller final ledger 分类：

| 分类 | item | owner | destination |
|---|---|---|---|
| accepted current finding | —（零） | — | CLOSED |
| rejected-as-finding observation | DS-OBS-02（`ADAPTER_ERROR` aggregation，poll timeout 无专用 outcome enum） | 当前 owner contract 无修改需求；durable `poll_last_error_code` 已区分根因 | **无当前修改 destination**。若未来 diagnostics public contract 有独立业务需求，由 Host wait diagnostics schema owner 重新设计 |
| retained residual | DS-OBS-01 / CANCELLED abandon 长期 timeout 无 terminal evidence（含 expired deadline 不在 poller 路径处理的同一根因） | future Host durable evidence policy | deferred to later WU |
| retained residual（独立于 DS observation ledger） | scheduler close / terminal promotion coordination | Host scheduler lifecycle (`dispatch.py` / `engine_ingest.py`) | Controller / user 裁决独立修复 gate |
| pending gate | R05-S2 Engine regression / public smoke / README | per accepted plan | next authorized gate |
| blocker | —（零） | — | NONE |

## 12. 最终裁决

**PASS / zero material finding / no required fix gate.**

本第二路独立完整 adversarial code re-review 对全部 30+ 维度进行了独立验证：七路径 product/test/design diff 逐行阅读，no-diff owners 逐文件 git diff --exit-code 确认，核心 owner contract 测试独立重跑，pyright/Ruff/source scans/security scans/scheduler probe 独立执行。所有验证均通过。

R05-S1 的产品 transaction 精确落在 semantic owner boundary：`WaitPoller` 把 poll/cancelled-abandon observation timeout 解释为 poll-local transient diagnostic + claim release/backoff；durable state 删除 invalid timeout-only terminal primitive；Host design 真源同步纠正；owner tests 覆盖 late publication、retry、typed lost 与 explicit lifecycle terminal。没有 schema、Engine、scheduler、Service、config、README 或 deferred scope 修改。retained safety 完整，scheduler residual 未修复/未掩盖。

两条原始 DS observation 的 Controller disposition 经独立复核仍正确：DS-OBS-01 维持 retained residual，DS-OBS-02 维持 rejected-as-finding observation（NO_CURRENT_DEFECT），无新增 finding。Zero-change proof 可信。

本 re-review verdict 不独立授权 commit。Controller 必须裁决两路 re-review 的全部 findings（本路 ledger：accepted finding 0 / rejected-as-finding observation 1 / retained residual 1 / blocker 0），决定是否授权 R05-S1 accepted local commit。

---

**Reviewer**: AgentDS (第二路独立完整 adversarial re-review)
**Date**: 2026-07-15
**Reviewed digest**: `3439b542e4a4785aaff5be56d93c87e17065d13d0d370742475c3e9e595b0ba2`
**Write allowlist**: 仅 `docs/reviews/wu-semantic-ownership-01-r05-s1-code-rereview-ds.md`
