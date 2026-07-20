# WU-SEMANTIC-OWNERSHIP-01 R05 Plan Re-Review — AgentMiMo（完整双路第一路）

## 0. Review 身份与范围

- **reviewer**: AgentMiMo（完整 re-review 第一路）
- **immutable target**: `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
- **plan base / HEAD**: `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`
- **review scope**: plan 修订全文（非只看 PF-01..04 局部 diff）+ 以下周边 evidence：
  - `AGENTS.md`
  - `docs/host/issues-implementation-control.md` 当前 R05 状态
  - `docs/host/wu-semantic-ownership-01-umbrella-plan.md` R05 manifest（§12）
  - `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 5 final decision
  - `docs/host/design.md`（wait observation/abandon 段）
  - `docs/engine/design.md`（§11 §12 handshake 段）
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-controller-validation.md`
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-review-mimo.md`（初审）
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-review-ds.md`（初审 DS）
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-fix-controller-validation.md`
  - 当前 production 代码：`dayu/host/wait_adapter.py`、`dayu/host/_wait_observation.py`、`dayu/host/durable/state.py`、`dayu/host/durable/schema.py`、`dayu/engine/agent.py`
  - 当前测试：`tests/host/test_wait_observation_runner.py`、`tests/host/test_wait_adapter_polling.py`、`tests/host/test_phase7_waiting_integration.py`、`tests/host/test_wait_record_state.py`、`tests/engine/test_agent_phase3_tool_call.py`
  - `utils/smoke_host_public_awaiting_entrypoint.py`
- **review posture**: constructively adversarial；默认假设 plan 至少有一个重要问题，直到证据证明可靠。
- **review 生成时间**: 2026-07-15T21:13:39+08:00（系统时钟）

---

## 1. Assumptions Tested

| # | Assumption | Evidence Source | Verdict |
|---|---|---|---|
| A1 | poll timeout root cause 在 `WaitPoller`，非 runner fencing | `wait_adapter.py:1107-1113` 构造 `WaitPollLost(ResolveWaitLostOutcome(...))` 并 `self._resolve_claimed_wait(record, timeout_result)` (line 1114) | PASS |
| A2 | abandon timeout root cause 在 `WaitPoller`，非 store | `wait_adapter.py:1366-1382` 构造 `_MarkWaitRecordAbandonTimeoutOperation` 写 `poll_abandoned_at` | PASS |
| A3 | `WaitObservationRunner` token/generation fence 已正确 | `_wait_observation.py:123-137` invalidate + `_publish` 检查 token identity/state/closed/generation | PASS |
| A4 | `release_wait_record_poll_claim` 支持 WAITING 和 CANCELLED | `state.py:2642-2655` WHERE clause `status IN (WAITING, CANCELLED)` | PASS |
| A5 | Engine `agent.py` 在 accepted awaiting 后不复用 handshake timeout | `agent.py:1974` 和 `agent.py:2184` 只在 `_execute_batch` 内读取 timeout；`agent.py:2055-2088` 接受 `ToolAwaitingOutcome` 后 emit `RUN_SUSPENDED` 并 return，无 timeout 再读取 | PASS |
| A6 | `release_wait_record_poll_claim` 不写 `poll_abandoned_at` | `state.py:2590-2660` 该函数只清 claim fields 写 backoff/diagnostic，不触及 `poll_abandoned_at` | PASS |
| A7 | `poll_abandoned_at IS NULL` 是 cancelled record claim 的必要条件 | `state.py:2537` claim query `status = CANCELLED AND poll_abandoned_at IS NULL` | PASS |
| A8 | `_release_with_backoff` 可接受 `ADAPTER_ERROR` 和 `ABANDON_ERROR` | `wait_adapter.py:1503-1543` 参数类型 `WaitPollLastOutcome`，调用方传入 | PASS |
| A9 | `WaitPollLastOutcome.ADAPTER_ERROR` 和 `ABANDON_ERROR` 已存在 | 当前测试已断言 `ABANDON_ERROR`（`test_wait_observation_runner.py:352`） | PASS |
| A10 | `mark_wait_record_poll_abandon_timeout` 在 production/tests 中只有单点 definition 与单点 import/wrapper/call | `state.py:2728-2797`（definition）；`wait_adapter.py:51`（import）、`wait_adapter.py:706-731`（wrapper class）、`wait_adapter.py:1368`（call）；tests 中零引用 | PASS |
| A11 | CANCELLED poll path 先走 `_abandon_cancelled_wait` 并 `continue`，绕过 `_handle_time_boundary` | `wait_adapter.py:1021-1036`：`if record.status is CANCELLED` → `_abandon_cancelled_wait` → `continue`；`_handle_time_boundary` 在 line 1030，不可达 | PASS |
| A12 | `mark_wait_record_poll_abandoned(...)`（explicit terminal）独立于 timeout-only primitive | `state.py:2663` 单独定义，写 `poll_abandoned_at` 用于 explicit applied/unsupported/noop lifecycle outcome | PASS |
| A13 | `durable/schema.py` 含 `poll_abandoned_at TEXT NULL` 字段 | `schema.py:873` | PASS |
| A14 | Ruff 全量 baseline = 167 errors | `python -m ruff check dayu tests utils` → `Found 167 errors` | PASS |
| A15 | pyright baseline = 0 errors | `python -m pyright dayu/ tests/ utils/` → `0 errors, 0 warnings, 0 informations` | PASS |
| A16 | §8 green coverage command = `1916 passed, 1 skipped, 5 deselected` | `python -m pytest -q tests/host --ignore=tests/host/test_toolruntime_executor.py` → `1916 passed, 1 skipped, 5 deselected`（51.27s） | PASS |
| A17 | §8 per-file coverage `durable/state.py=83%`, `wait_adapter.py>=80%` | 实测 `durable/state.py=83%`, `wait_adapter.py=86%` | PASS（86% > 85% plan claim, 均 >=80%） |
| A18 | §5.1 design.md writeback 目标句精确存在 | `design.md:2429-2430`："cancelled wait 的 abandon 超时只写 `wait_abandon_timeout` diagnostic/close marker，不宣称 provider 已取消成功。" | PASS |
| A19 | 两错误语义测试确实断言旧错误 | `test_stuck_poll_times_out_to_lost...` line 309: `wait.status is WaitRecordStatus.LOST`；`test_stuck_abandon_writes_timeout_marker...` line 351: `wait.poll_abandoned_at is not None` | PASS |

---

## 2. R05-PF-01..04 关闭状态逐项复核

### 2.1 R05-PF-01 — cancelled abandon timeout 长期 capped retry residual

**裁决：CLOSED ✅**

直接复核：

- `wait_adapter.py:1021-1029`：`CANCELLED` → `_abandon_cancelled_wait` → `continue`，确实绕过 `_handle_time_boundary`。
- 修订后 plan §2.1、§4、§15 已明确记录该事实，并列出当前安全边界（claim CAS、`max_outstanding_adapter_calls=8`、finite single-call timeout、late-publication fencing、backoff cap `300s`）。
- future owner 已分离为 Host cancel/abandon durable evidence policy（≠ Issue 175 process isolation）。
- 禁止 R05 发明 max retry、abandon deadline、timeout terminal marker 已显式声明。

controller adjudication R05-PF-01 的所有要求均已映射到修订 plan。

### 2.2 R05-PF-02 — public smoke timing 可执行性

**裁决：CLOSED ✅**

直接复核：

- 修订后 §5.2 和 §11 要求 event/condition/durable-state polling 驱动所有 phase 等待。
- 唯一 `time.monotonic()` overall deadline；每个 phase 从同一 deadline 计算 remaining budget。
- 具名 constants（handshake budget、adapter timeout、initial backoff、state-poll quantum、relative margin、overall deadline、CI cap）。
- 三段带 margin 严格不等式：`handshake budget + margin < observation timeout`、`observation timeout + margin < measured operation duration`、`measured operation duration + margin < observation timeout + initial backoff`；`margin >= 5 * state-poll quantum`。
- packaged snapshot 与 test-effective timing 分开打印/断言。
- phase 失败时输出 phase ledger、monotonic elapsed、runner dropped count、Run/Wait snapshot。
- 禁止 `WaitPollerRuntimePolicy()` 无参构造、禁止写回产品 config、禁止第二 backoff。

controller adjudication R05-PF-02 的所有要求均已映射。

### 2.3 R05-PF-03 — Host design `close marker` 真源纠错

**裁决：CLOSED ✅**

直接复核：

- `docs/host/design.md` 已加入 R05-S1 implementation docs write allowlist（§5.1、§6.2）。
- §5.1 精确规定改写文本：cancelled wait 的 abandon observation timeout 只写 poll-local transient `wait_abandon_timeout` diagnostic、释放 claim 并按 Host policy backoff，durable status 保持 `CANCELLED` 且不写 terminal `poll_abandoned_at`；只有 provider 显式返回 applied / unsupported / noop lifecycle outcome，才沿既有 transition 写 terminal abandon marker，且不调用 wait resolve。
- 现有 design.md:2429-2430 的 "close marker" 可被读作 terminal marker，与裁决 retry 语义冲突；plan 的改写精确消除该歧义。
- 不新增 retry 上限、deadline、policy/schema；超出即 stop。

### 2.4 R05-PF-04 — durable invalid timeout-only primitive 删除

**裁决：CLOSED ✅**

直接复核：

- `dayu/host/durable/state.py` 已加入 R05-S1 production allowlist。
- §5.1 要求删除 `mark_wait_record_poll_abandon_timeout(...)` 完整定义，不得 deprecated wrapper/compat re-export/dead helper。
- strict zero-symbol guard：`mark_wait_record_poll_abandon_timeout|_MarkWaitRecordAbandonTimeoutOperation` 在 `dayu tests` 中零定义零调用。
- `durable/schema.py` no-diff 要求已明确。
- 保留 `mark_wait_record_poll_abandoned(...)`（explicit lifecycle terminal）与 `poll_abandoned_at` schema 字段。
- `tests/host/test_wait_record_state.py` 加入 S1 test allowlist，新增 CANCELLED release/backoff 后同 row 到期可再次 claim 的 durable owner test。
- actual changed production files（`durable/state.py`、`wait_adapter.py`）逐文件 `>=80%` 覆盖门禁。

---

## 3. 全计划 Adversarial Re-Review Findings

### 001-未修复-低-§2.3 Ruff changed-file 基线遗漏 `durable/state.py` F401

- **位置**: §2.3 静态基线；§9.2 Ruff 门禁
- **问题类型**: 测试缺口 / 基线不完整
- **当前写法**: §2.3 只登记一条 changed-file Ruff 基线诊断：`tests/host/test_phase7_waiting_integration.py:8:22` 的 `F401 datetime.UTC imported but unused`。§9.2 changed Python files Ruff 命令列表也不包含 `tests/host/test_wait_record_state.py`。
- **反例/失败场景**: 实际运行 §9.2 changed-file Ruff 命令（含 `dayu/host/durable/state.py`）发现第二条 F401：

  ```
  dayu/host/durable/state.py:40:5 — F401 `TERMINAL_RUN_STATUS_VALUES` imported but unused
  ```

  该诊断在 base SHA `5ba0d8b6` 上已存在（167 全量 baseline 不变），但未被 plan §2.3 登记。实施 Agent 若只修复 plan 登记的 test_phase7 F401，§9.2 changed-file Ruff 命令仍会返回非零。
- **为什么有问题**: plan §9.2 要求 "changed Python files 必须单独 Ruff 全绿"。`durable/state.py` 是 R05-S1 的 planned changed production file。若实施 Agent 只修 test_phase7 F401，changed-file Ruff 门禁会失败。
- **直接证据**:

  ```
  $ source .venv/bin/activate && python -m ruff check \
    dayu/host/durable/state.py dayu/host/wait_adapter.py \
    tests/host/test_wait_observation_runner.py tests/host/test_wait_adapter_polling.py \
    tests/host/test_phase7_waiting_integration.py tests/engine/test_agent_phase3_tool_call.py \
    utils/smoke_host_public_awaiting_entrypoint.py
  F401 [*] `dayu.host.durable._row_rules.TERMINAL_RUN_STATUS_VALUES` imported but unused
    --> dayu/host/durable/state.py:40:5
  F401 [*] `datetime.UTC` imported but unused
    --> tests/host/test_phase7_waiting_integration.py:8:22
  Found 2 errors.
  ```

- **影响**: 实施 Agent 可能只修一条 F401，导致 §9.2 changed-file Ruff 门禁失败，需要额外 round-trip。
- **建议改法和验证点**:
  1. 在 §2.3 增加第二条 changed-file Ruff 基线诊断：`dayu/host/durable/state.py:40:5` 的 `F401 TERMINAL_RUN_STATUS_VALUES imported but unused`。
  2. 在 §9.2 changed Python files Ruff 命令中增加 `tests/host/test_wait_record_state.py`。
  3. 实施时同时清除两条 F401，使 changed-file Ruff 全绿。
- **修复风险（低/中/高）**: 低 — 只需在 plan 中补登记并实施时一并清除。
- **严重程度（低/中/高/严重）**: 低 — 不影响语义正确性，只是 plan 基线精确度。

---

## 4. Architecture Boundary Review

### 4.1 分层与依赖方向

| 维度 | plan 设计 | 直接证据 | Verdict |
|---|---|---|---|
| Host 不依赖 Engine | R05-S1 只改 `wait_adapter.py` + `durable/state.py`，不 import Engine | closed allowlist §6.2 | PASS |
| Engine 不依赖 Host | R05-S2 对 `agent.py` 预期 no diff；Engine 只读 Host public contract | §5.2 | PASS |
| `durable/state.py` 不向上泄漏 | 只删除一个 store primitive；不新增 public API | §5.1 | PASS |
| Service 不穿透 Host | smoke 经 `ServiceRunOverrides -> open_host -> durable poller` 公共链 | §5.2 | PASS |
| `dayu.runtime` 不被 R05 触及 | R05 不修改 runtime 包 | allowlist §6.2 | PASS |

### 4.2 Schema/Storage 边界

- `durable/schema.py` no-diff：plan 明确要求（§5.1、§10.1）。`poll_abandoned_at` 字段保留，只承载 explicit lifecycle terminal marker。
- 不新增 enum/migration/codec：plan §1.3 显式禁止。
- 删除的 `mark_wait_record_poll_abandon_timeout` 不是 public contract（无 export、无 migration consumer、无第二 production caller）。

### 4.3 Public Contract 边界

- R04 12-field policy snapshot：plan §1.2 完整列出，R05 不改变。
- R04 typed modes（`poll`/`callback`/`manual`）：plan §1.2 保留。
- `ResolveWaitLostOutcome` / `WaitPollLost`：保留，只用于 provider authoritative typed lost。
- `mark_wait_record_poll_abandoned(...)`：保留，只用于 explicit lifecycle terminal outcome。

---

## 5. Best-Practice Review

| 维度 | plan 作法 | 最佳实践对照 | Verdict |
|---|---|---|---|
| root cause 修复 | 在 `WaitPoller` decision owner 修复，复用 `_release_with_backoff` | bug fix 修 root cause，不在下游补兼容 | PASS |
| 语义 owner 单一 | timeout policy 解释归 `WaitPoller`；token/fence 归 `WaitObservationRunner`；typed terminal 归 `waiting.py` | 每个业务事实有唯一 owner | PASS |
| 无兼容代码 | 删除 invalid primitive，不保留 deprecated wrapper | 禁止兼容性 re-export/wrapper | PASS |
| 无 God object | 不新增通用 registry、builder、facade | 最小化满足需求 | PASS |
| 测试跟着边界迁移 | 替换旧错误语义测试为新 owner contract | 不为保住旧测试堆兼容逻辑 | PASS |
| coverage 逐文件门禁 | actual changed production files 各自 `>=80%` | 单文件覆盖率目标 >=80% | PASS |

---

## 6. Overengineering Review

- **两 slice 切分**：S1 是唯一 production semantic transaction（Host adapter decision + storage primitive deletion + design writeback），S2 是跨层 no-diff/public evidence。拆分理由成立——合并会混合 root fix 与跨层 evidence。继续拆第三 slice 增加无语义价值 gate。**PASS — 不过度。**
- **不新增 policy 字段/timer/scheduler/runner**：plan 复用既有 `_release_with_backoff` 与 `release_wait_record_poll_claim`。**PASS — 最小化。**
- **不引入 max retry / abandon deadline**：plan 显式声明为 future owner residual。当前安全边界（CAS/cap/timeout/fence/backoff cap）限制资源但不终止。**PASS — 不过度设计。**

---

## 7. Overcoupling Review

| 维度 | 检查 | Verdict |
|---|---|---|
| S1 两个 production file 是否过度绑定 | `wait_adapter.py` 删除 import/wrapper/call；`durable/state.py` 删除 function definition。两处是同一 invalid semantic 的 consumer 与 producer，必须同步删除 | PASS — 语义同源 |
| S2 是否必须依赖 S1 | Engine regression 预期在 base 上直接通过（当前 production 已正确）；public smoke 需要 S1 的 Host behavior 变更。S2 依赖 S1 语义但不依赖 S1 代码 | PASS — 依赖合理 |
| R04 config 是否被 R05 绑定 | R05 不改 config schema/fields/modes；只复用既有12-field snapshot | PASS — 无耦合 |
| test_wait_record_state.py 新增 test 是否要求 production 变更 | 新增 `test_cancelled_poll_timeout_release_preserves_claimability_after_due` 是 preservation green node：在 base 和 implementation 后都应为绿。它直接测 durable primitive 行为，不依赖 adapter 层修改 | PASS — 可独立验证 |
| `_wait_observation.py` / `waiting.py` 是否被不必要地绑入 | 预期 no diff；只做 read/verify。若出现 diff 则 stop | PASS — 防御性检查，非耦合 |

---

## 8. Smoke Event/Condition/Monotonic Margin 真实有界性验证

### 8.1 Phase 驱动可实现性

plan §11 规定的5个 phase 驱动方式：

1. `operation_started` event → `asyncio.Event` / `threading.Event` 可实现。
2. `first_observation_entered` event → adapter 首次调用由 event gate 阻塞 → 需要在 test adapter 中实现可控阻塞，当前 `_BlockingAdapter` pattern 已有先例。
3. timeout state 成立后 signal operation finish → 需要 durable state polling 确认 timeout diagnostic、claim release、backoff due time → `asyncio` 条件等待可实现。
4. `second_observation_entered` event → 不篡改 due time，按 state-poll quantum 查询 → 可实现。
5. SUCCEEDED + terminal event + outbox → 公共 entrypoint 验证可实现。

**结论：5个 phase 均可用 event/condition/durable-state polling 实现，不依赖固定 sleep 推断状态。**

### 8.2 Timing 不等式可满足性

以 packaged defaults 为例：

```
handshake budget = tool_execution_timeout_seconds (由 ServiceRunOverrides 设定 test-only 值)
adapter_call_timeout_seconds = 30
backoff_initial_delay_seconds = 30
```

不等式链：`handshake budget + margin < observation timeout(30) < operation duration < observation timeout + initial backoff(60)`

假设 handshake budget = 5s、margin = 2.5s（= 5 × quantum 0.5s）：

- `5 + 2.5 = 7.5 < 30` ✓
- `30 + 2.5 = 32.5 < operation duration` → 需要 operation duration > 32.5s
- `operation duration < 30 + 30 = 60` → 需要 operation duration < 60s

取 operation duration ≈ 45s → `32.5 < 45 < 60` ✓

总 smoke 耗时 ≈ handshake(5s) + first observation timeout(30s) + backoff wait(30s) + second observation(~0s) ≈ 65s，在 CI duration cap 内。

**结论：timing 不等式链可满足，总耗时有界。**

### 8.3 Monotonic Deadline 有界性

plan §11 第10点要求 `time.monotonic()` 建立 overall deadline，所有 phase wait 从该 deadline 计算 remaining budget，且 `overall deadline <= CI duration cap`。实现时只要 CI cap 设为例如120s，所有 phase 等待使用 `min(event_timeout, deadline_remaining)` 即可保证有界。

---

## 9. 两 Slice、Engine agent.py No-Diff、R04 12 Fields/Modes 保持验证

### 9.1 两 slice 原子边界

| Slice | 性质 | Production 变更 | Evidence 变更 | 回滚边界 |
|---|---|---|---|---|
| R05-S1 | 唯一 production semantic transaction | `wait_adapter.py` + `durable/state.py` + `design.md` | host tests + `test_wait_record_state.py` | 单独可回滚 |
| R05-S2 | 跨层 contract evidence | 无 production 变更（`agent.py` no diff） | engine regression + public smoke + README | 不改 production |

**Verdict：PASS。** 两 slice 保持 umbrella 原子边界。S2 不创建第二 production transaction。

### 9.2 Engine `agent.py` no-diff

直接代码证据：

- `agent.py:1974`：`timeout_seconds` 只设置在 `BatchToolExecutionContext` 上。
- `agent.py:2184`：`await_or_cancel_or_timeout` 使用同一 timeout 包裹 `_call_tool_executor`。
- `agent.py:2055-2088`：接受 `ToolAwaitingOutcome` 后 emit `RUN_SUSPENDED` 并 return，无 timeout 再读取。
- `docs/engine/design.md:398`：明确 "合法的长事务工具必须在该 handshake budget 内返回 `ToolAwaitingOutcome`；Host durable accepted 之后继续运行的外部长事务不受 `tool_execution_timeout_seconds` 限制"

**Verdict：PASS。** no-diff 判定有直接代码证据支撑。R05 预期 `agent.py` 最终 diff 为空。

### 9.3 R04 12 fields / 3 modes

- plan §1.2 完整列出12字段及 packaged 值。
- §7.3 exact R04 preservation nodes 覆盖 `test_config_loader`、`test_fins_ingestion_tools`、`test_host_assembly`。
- §10.5 R04 ownership scan 命令：`rg -n 'awaiting_resolution_mode|wait_poller_policy'` 覆盖 config/service/prompts/execution_profiles。
- 禁止恢复 scene/name heuristic、无参数 `WaitPollerRuntimePolicy()` 构造。

**Verdict：PASS。**

---

## 10. Security / Deferred Boundaries 保持验证

| 边界 | plan 声明 | 代码事实 | Verdict |
|---|---|---|---|
| 不实施 unified authorization/permission | §1.3 非目标 | closed allowlist 不含相关文件 | PASS |
| 不实施 callback transport | §1.3 非目标 | R05 不改 Fins binding | PASS |
| 不实施 Issue 175 process isolation | §1.3 非目标 + §15 residual | 不含 `process_backed` / subprocess 修改 | PASS |
| 保留 token/fence/CAS/capacity/close-drain | §1.3 + §4 branch matrix | 既有 owner tests preservation | PASS |
| 不放宽 claim CAS | §10.3 scan 命令 | `_release_with_backoff` 使用同一 `_ReleaseWaitRecordClaimOperation` | PASS |

§10.5 security scan 命令：

```bash
git diff --unified=0 5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1 -- dayu \
  | rg -n 'authorization|permission|callback transport|process isolation|process_backed|subprocess|Issue 175'
```

预期零命中。

---

## 11. Coverage Matrix

| Slice | Changed Production File | Coverage Target | 当前实测 | Verdict |
|---|---|---|---|---|
| R05-S1 | `dayu/host/durable/state.py` | >= 80% | 83% | PASS |
| R05-S1 | `dayu/host/wait_adapter.py` | >= 80% | 86% | PASS |
| R05-S1 | `dayu/host/_wait_observation.py` | 报告但不门禁 | — | 预期 no diff |
| R05-S1 | `dayu/host/waiting.py` | 报告但不门禁 | — | 预期 no diff |
| R05-S2 | `dayu/engine/agent.py` | 无 debt | 80%（base） | 预期 no diff |

Coverage 命令验证：

```bash
python -m pytest -q tests/host --ignore=tests/host/test_toolruntime_executor.py \
  --cov=dayu.host.durable.state --cov=dayu.host.wait_adapter --cov-branch \
  --cov-report=term-missing --cov-report=json:workspace/tmp/r05-s1-coverage.json
# → 1916 passed, 1 skipped, 5 deselected
# → durable/state.py=83%, wait_adapter.py=86%
```

逐文件门禁：

```bash
python -m coverage report --include='dayu/host/durable/state.py' --fail-under=80  # 83% PASS
python -m coverage report --include='dayu/host/wait_adapter.py' --fail-under=80   # 86% PASS
```

---

## 12. Branch Matrix 完整覆盖验证

plan §4 分支矩阵共14行。逐行验证 owner assertion 是否已存在或计划新增：

| # | 路径 | 现有/新增 assertion | Verdict |
|---|---|---|---|
| 1 | poll Ready | `test_poll_adapter_ready_result_resolves_wait` | PASS |
| 2 | poll NotReady | `test_poll_adapter_not_ready_leaves_wait_active` | PASS |
| 3 | poll authoritative Lost | `test_poll_adapter_lost_result_closes_run` | PASS |
| 4 | poll observation timeout | **新增** `test_poll_observation_timeout_releases_with_backoff_and_late_result_cannot_resolve` | PASS（test-first red→green） |
| 5 | poll adapter exception | `test_abandon_adapter_snapshot_projection_failure_releases_with_backoff` | PASS |
| 6 | poll capacity | `test_active_poll_claim_suppresses_second_poller_adapter_call` | PASS |
| 7 | cancelled explicit applied | `test_cancelled_poll_wait_is_abandoned_once_without_resolve` | PASS |
| 8 | cancelled explicit unsupported | parameterized in same test | PASS |
| 9 | cancelled explicit noop | parameterized in same test | PASS |
| 10 | cancelled observation timeout | **新增** `test_cancelled_abandon_timeout_releases_with_backoff_and_late_result_cannot_mark_terminal` | PASS（test-first red→green） |
| 11 | cancelled exception | `test_failed_cancelled_wait_abandon_is_retried_next_poll` | PASS |
| 12 | cancelled capacity | 既有 release/cadence test | PASS |
| 13 | close/drain | `test_supervisor_close_uses_one_shared_deadline_and_stays_closing` | PASS |
| 14 | wait deadline (non-CANCELLED) | `test_invalid_poll_deadline_fails_closed_without_business_lost` | PASS |

integration 覆盖：

- **新增** `test_poll_observation_timeout_keeps_waiting_then_ready_resumes_run`（§7.1 integration node）
- **新增** `test_cancelled_poll_timeout_release_preserves_claimability_after_due`（§7.1 durable owner node）
- 保留 `test_poll_abandon_success_marks_row_and_clears_claim`（explicit terminal preservation）

**14/14 路径均有 owner assertion。Verdict：PASS。**

---

## 13. Source / Propagation / Security Scan 可执行性验证

| Scan | 命令 | 预期结果 | Verdict |
|---|---|---|---|
| timeout 不传播成 terminal | `rg -n 'WaitObservationTimedOut\|wait_observation_timeout\|wait_abandon_timeout\|ResolveWaitLostOutcome' dayu/host/... tests/host` | timeout codes 只作为 diagnostic code 和测试预期；不在 `ResolveWaitLostOutcome` 构造中 | PASS |
| invalid symbol 零匹配 | `rg -n 'mark_wait_record_poll_abandon_timeout\|_MarkWaitRecordAbandonTimeoutOperation' dayu tests` | guard 返回零（exit 1 → "invalid symbol remains"） | PASS |
| schema no-diff | `git diff --exit-code 5ba0d8b6... -- dayu/host/durable/schema.py` | exit 0 | PASS |
| late token 唯一路径 | `rg -n '_start_observation\|_invalidate_token\|_publish\|...' dayu/host/_wait_observation.py dayu/host/wait_adapter.py tests/host` | runner 仍是唯一 publication authority | PASS |
| claim/backoff 唯一真源 | `rg -n '_release_with_backoff\|_backoff_delay_seconds\|release_wait_record_poll_claim\|...'` | timeout branches 只调用既有 `_release_with_backoff` | PASS |
| Engine no-diff | `git diff --exit-code 5ba0d8b6... -- dayu/engine/agent.py` | exit 0 | PASS |
| R04 ownership | `rg -n 'awaiting_resolution_mode\|wait_poller_policy' dayu/config/...` | 只从 owner 路径投影 | PASS |
| security/deferred scope | `git diff --unified=0 ... \| rg -n 'authorization\|...'` | 零命中 | PASS |

---

## 14. Open Questions

**无 blocking open question。**

---

## 15. Residual Risks

| # | Risk | 分类 | Owner / Destination | 当前边界 |
|---|---|---|---|---|
| R1 | cancelled abandon observation 可能长期 capped-backoff retry 并间歇占用有限 capacity | `requiring new issue or explicit user decision` | future Host cancel/abandon durable evidence policy | CAS/cap/timeout/fence/backoff cap 限制单轮/并发资源，非终止证据 |
| R2 | Fins Docling 物理终止/containment | `tracked by existing issue` | Issue 175 | 不与 Host durable stop evidence 混同 |
| R3 | public smoke 执行时间 ~65s | `fixed in current slice` | R05-S2 | event/condition/state-poll + monotonic deadline + CI cap |
| R4 | `mark_wait_record_poll_abandon_timeout` 在 state.py 中留有定义（implementation 后删除） | `fixed in current slice` | R05-S1 | owner-boundary deletion + zero-symbol scan |
| R5 | callback / unified authorization / R06+ | `assigned to later work unit` | 既有 umbrella later WU/issue | 本 plan 无变更 |
| R6 | future explicit Host LOST durable evidence policy | `requiring new issue or explicit user decision` | future Host policy | R05 不预留 heuristic branch |

---

## 16. Finding 001 修复验证

Finding 001 指出 §2.3 遗漏了 `durable/state.py:40` 的 F401。该遗漏不影响 plan 的语义正确性或可实施性——实施 Agent 在执行 §9.2 changed-file Ruff 命令时会自然遇到该错误并修复。但 plan 应精确反映基线，避免实施 Agent 额外 round-trip。

**建议**：在 §2.3 增加一条 changed-file Ruff 基线诊断，在 §9.2 增加 `tests/host/test_wait_record_state.py`。

---

## 17. Final Plan Review Conclusion

**PASS**

该 plan 对 root cause 的定位精确（`WaitPoller` 对 `WaitObservationTimedOut` 的错误业务解释），对 semantic owner 的判定正确（runner fence、durable store primitive、typed resolver 均保持 read-only），对两 slice 的切分保持了 umbrella 裁决的最小原子边界。

所有 adversarial lens 均未发现 blocker：

- **Architecture boundary**：分层、依赖方向、schema/storage 边界、public contract 边界均正确。
- **Best practice**：root cause 修复、语义 owner 单一、无兼容代码、测试跟着边界迁移、coverage 逐文件门禁均满足。
- **Optimal solution**：复用既有 `_release_with_backoff` + `release_wait_record_poll_claim` 是最实际路径。
- **Overengineering**：两 slice 不过度；不新增 policy/timer/scheduler/runner。
- **Overcoupling**：两个 production file 语义同源必须同步删除；S2 依赖合理。

R05-PF-01 至 R05-PF-04 均已在 plan 层关闭，controller validation 已 PASS。

唯一新 finding（001，低严重度）是 §2.3 Ruff 基线遗漏了 `durable/state.py:40` 的 F401 和 §9.2 遗漏了 `test_wait_record_state.py`。这不影响 plan 的 code-generation-ready 判定——实施 Agent 在执行 §9.2 命令时会自然遇到并修复。

五条 residual risk 均为非 blocking，已分类并分配 owner。

**plan 达到 code-generation-ready 的实施入口。无 accepted finding、无 blocking question、无 owner/allowlist 修改建议。**

下一 gate：AgentDS 对修订计划全文作完整双路 re-review；两路 re-review 与 Controller adjudication 完成前，不得进入 implementation。
