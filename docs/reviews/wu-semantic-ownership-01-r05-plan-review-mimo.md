# WU-SEMANTIC-OWNERSHIP-01 R05 Plan Review — AgentMiMo

## 1. Reviewed Target 与 Scope

- **target**：`docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
- **plan base / HEAD**：`5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`
- **review scope**：plan 全文 + 以下周边 evidence：
  - `docs/host/issues-implementation-control.md` 当前状态
  - `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` R05 manifest（§12）
  - `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 5 final decision
  - `docs/reviews/wu-semantic-ownership-01-r05-plan-controller-validation.md`
  - `docs/host/design.md`、`docs/engine/design.md`
  - `AGENTS.md`
  - 当前 production 代码：`dayu/host/wait_adapter.py`、`dayu/host/_wait_observation.py`、`dayu/host/durable/state.py`、`dayu/engine/agent.py`
  - 当前测试：`tests/host/test_wait_observation_runner.py`、`tests/host/test_wait_adapter_polling.py`、`tests/host/test_phase7_waiting_integration.py`、`tests/engine/test_agent_phase3_tool_call.py`
- **review posture**：constructively adversarial，默认假设 plan 至少有一个重要问题，直到证据证明可靠。

## 2. Assumptions Tested

| # | Assumption | Evidence Source | Verdict |
|---|---|---|---|
| A1 | poll timeout 的 root cause 在 `WaitPoller` 而非 runner fencing | `wait_adapter.py:1102-1128` 构造 `WaitPollLost(ResolveWaitLostOutcome(...))` 并调用 `_resolve_claimed_wait` | PASS — root cause 定位正确 |
| A2 | abandon timeout 的 root cause 在 `WaitPoller` 而非 store | `wait_adapter.py:1363-1382` 调用 `_MarkWaitRecordAbandonTimeoutOperation` 写 `poll_abandoned_at` | PASS — root cause 定位正确 |
| A3 | `WaitObservationRunner` token/generation fence 已正确 | `_wait_observation.py:123-137` invalidate + `_publish` 检查 token identity/state/closed/generation | PASS — 无需新增 fence |
| A4 | `release_wait_record_poll_claim` 支持 WAITING 和 CANCELLED | `wait_adapter.py:84` 注释确认；`_release_with_backoff` 当前已用于两种状态 | PASS — store primitive 足够 |
| A5 | Engine `agent.py` 在 accepted awaiting 后不复用 handshake timeout | `agent.py:2055-2088`：接受 awaiting 后立即 emit `RUN_SUSPENDED` 并 return，无 timeout 再读取 | PASS — production no-diff 判定成立 |
| A6 | `release_wait_record_poll_claim` 不写 `poll_abandoned_at` | `state.py:mark_wait_record_poll_abandon_timeout` 是唯一写 `poll_abandoned_at` 的 timeout 路径；`release_wait_record_poll_claim` 只清 claim 字段并写 backoff/diagnostic | PASS — cancelled record 保持 claimable |
| A7 | `poll_abandoned_at IS NULL` 是 cancelled record claim 的必要条件 | `state.py:2534-2538` SELECT 和 `state.py:2563-2568` UPDATE 都包含 `poll_abandoned_at IS NULL` guard | PASS — R05 释放 claim 而非写 marker 是正确的 |
| A8 | `_release_with_backoff` 可接受任意 `WaitPollLastOutcome` 值 | `wait_adapter.py:1503-1543` 参数类型为 `WaitPollLastOutcome`，由调用方传入 | PASS — `ADAPTER_ERROR` 和 `ABANDON_ERROR` 可直接传入 |
| A9 | `WaitPollLastOutcome.ADAPTER_ERROR` 和 `ABANDON_ERROR` 已存在 | `wait_adapter.py:46` import `WaitPollLastOutcome`；当前测试已断言 `ABANDON_ERROR` | PASS — 非新增 enum |
| A10 | Ruff baseline 167 条可在 changed-file F401 修复后精确匹配 | `wait_adapter.py` 已有 `_POLL_ERROR_CODE_ABANDON_TIMEOUT` 和 `_POLL_ERROR_CODE_OBSERVATION_TIMEOUT` 常量；changed files 定向 Ruff 当前只有 `test_phase7_waiting_integration.py:8` 的 F401 | PASS |

## 3. Findings

### 001-未修复-中-CANCELLED wait abandon timeout 无限重试的资源影响

- **位置**：§4 分支矩阵 cancelled abandon timeout 行；§5.1 R05-S1 production 变更
- **问题类型**：状态机漏洞 / 最佳实践偏离
- **当前写法**：plan 要求 abandon timeout 走 `_release_with_backoff`，outcome `ABANDON_ERROR`，error code `wait_abandon_timeout`，保持 `CANCELLED` 且不写 `poll_abandoned_at`。这意味着 cancelled record 始终 claimable，每轮 poller 周期都会重新尝试 abandon observation。
- **反例/失败场景**：外部 job 永远不响应 cancel 信号（进程僵死、网络不通、provider 忽略 cancel）。每 5 分钟（backoff max 300s）消耗一个 claim slot 和一个 observation thread，无限循环。对于单个 stuck job，这不会立即造成资源耗尽；但如果多个 cancelled wait 同时卡住，它们会持续占用 `max_outstanding_adapter_calls=8` 的 capacity。
- **为什么有问题**：当前代码的 `poll_abandoned_at` 机制虽然语义错误（把 uncertainty 提升为 terminal），但它确实提供了 "最终停止重试" 的保障。R05 删除这个保障后，没有替代的 "最大 abandon 重试次数" 或 "abandon deadline" 来防止无限循环。plan §1.1 说 "下一轮到期后仍可重试 explicit provider lifecycle observation"，但没有说明如果 provider 永远不返回 lifecycle outcome 会怎样。
- **直接证据**：
  - `state.py:2534-2538`：cancelled record claimable 当且仅当 `poll_abandoned_at IS NULL`
  - `wait_adapter.py:1503-1543`：`_release_with_backoff` 不写 `poll_abandoned_at`
  - `wait_adapter.py:1363-1382`（当前代码）：timeout 路径写 `poll_abandoned_at` 并停止重试
- **影响**：不是立即 blocker，因为 backoff 限制了频率。但在生产环境中，如果多个外部 job 永远不响应 cancel，poller 会持续消耗线程 capacity。这是一个可接受的 residual risk，但 plan 应该显式声明。
- **建议改法和验证点**：
  1. 在 plan §15（Residual owners）中显式记录："cancelled wait abandon timeout 无限重试是有意设计；若外部 job 永远不响应 cancel，poller 会持续以 backoff 频率重试。未来可通过 Host durable evidence policy 或 Issue 175 的进程隔离提供硬上限。"
  2. 或者在 R05-S1 中增加一个 "max abandon retries" 配置（但这会扩大 scope）。
- **修复风险（低/中/高）**：低 — 只需在 plan 中添加 residual risk 声明。
- **严重程度（低/中/高/严重）**：中 — 行为正确但缺少显式 resource budget 声明。

### 002-未修复-低-smoke 测试的 timing 敏感性

- **位置**：§11 真实本地 smoke command 与通过证据
- **问题类型**：测试缺口
- **当前写法**：smoke 要求 `handshake budget < observation timeout < operation duration < timeout + initial backoff`，并 "等待真实 backoff 到期后" 再次 observation。
- **反例/失败场景**：CI 环境负载高时，backoff 到期后的 observation 可能因线程调度延迟而错过 `next_observe_at`，导致 poller sleep 时间超过预期。或者 observation timeout 的实际触发时间因 GIL 或 asyncio event loop 延迟而略超 budget，导致 timing 不等式被打破。
- **为什么有问题**：smoke 的 8 个 assertion 依赖精确的时序关系。如果 timing margins 不够大，CI 会间歇性失败（flaky test）。
- **直接证据**：plan §11 第 8 点要求 "timing 使用具名 smoke constants，并满足 `handshake budget < observation timeout < operation duration < timeout + initial backoff` 的明确不等式，给 CI 留出足够 margin"。但没有指定具体 margin 值。
- **影响**：CI flaky smoke 可能导致 S2 gate 延迟。
- **建议改法和验证点**：
  1. 在 plan 中为每个 timing constant 指定最小 margin，例如 `operation duration >= timeout + 2 * margin`，`margin >= 2s`。
  2. 或者在 smoke 中使用 polling-based 等待而非固定 sleep，例如 "等待直到 durable Run 状态变为 WAITING" 而非 "sleep N 秒后检查"。
- **修复风险（低/中/高）**：低 — 只需在 plan 中明确 margin 策略。
- **严重程度（低/中/高/严重）**：低 — plan 已识别需要 margin，只是没有给出具体值。

## 4. Controller Validation Challenge Points 复核

Controller validation §8 列出了 5 个 reviewer 必须重点挑战的点。逐项复核：

### Challenge 1：cancelled-wait timeout 的 retry 是否会被 `poll_abandoned_at` 或 due-query 条件意外阻断

**结论：不会阻断。**

- R05-S1 将 abandon timeout 路径从 `_MarkWaitRecordAbandonTimeoutOperation`（写 `poll_abandoned_at`）改为 `_release_with_backoff`（不写 `poll_abandoned_at`）。
- `release_wait_record_poll_claim` 只清 claim 字段并写 backoff/diagnostic，不设置 `poll_abandoned_at`。
- `claim_wait_record_for_poll` 的 WHERE clause 要求 `poll_abandoned_at IS NULL`（`state.py:2534-2538`），R05 改后 `poll_abandoned_at` 保持 NULL，record 始终 claimable。
- `read_next_wait_record_poll_due_at` 同样要求 `poll_abandoned_at IS NULL`（`state.py:2476-2480`），cancelled record 的 `next_observe_at` 由 `_release_with_backoff` 设置，scheduler 可正常 sleep 到期。

**唯一 residual**：如果 abandon 永远 timeout，record 会无限重试（见 Finding 001）。

### Challenge 2：late publication、claim release 与下一轮 Ready/explicit lifecycle terminal 是否由同一 durable record 闭环

**结论：闭环成立。**

- observation timeout → token invalidation（`_wait_observation.py:123-137`）→ late result dropped（`_publish` 检查 token identity/state/closed/generation）。
- claim release + backoff + diagnostic 由 `_release_with_backoff` 原子写入同一 durable record（`wait_adapter.py:1503-1543` → `_ReleaseWaitRecordClaimOperation`）。
- 下一轮 observation 从同一 durable record 的 `next_observe_at` 读取 due time，claim 后调用 adapter。
- 如果 adapter 返回 Ready，走 `_resolve_claimed_wait` 路径；如果返回 explicit lifecycle outcome，走 `_MarkWaitRecordAbandonedOperation` 路径。两者都操作同一 durable record。

### Challenge 3：public smoke 是否真正跨过 Engine handshake budget 并等待 Host policy backoff

**结论：plan 设计正确，但需要实现时验证。**

- smoke §11 第 3 点：worker 收到 `AgentRunRequest` 必须含 test-only handshake budget。
- smoke §11 第 3 点：local external operation 的实测 duration 大于 handshake budget，但 awaiting handshake 在 budget 内被 accepted。
- 这意味着 ToolExecutor.execute 在 handshake budget 内返回 `ToolAwaitingOutcome`（accepted），Engine 立即 suspend。外部 operation 继续运行，不受 handshake timeout 影响。
- smoke §11 第 5-7 点：第一次 observation timeout → durable WAITING + claim released + backoff → 等待真实 backoff 到期 → 第二次 observation Ready → SUCCEEDED。
- **验证点**：实现时必须确保 ToolExecutor 在 handshake budget 内返回 awaiting，而非等到 operation 完成后才返回。这取决于 test executor 的实现。

### Challenge 4：`agent.py` no-diff 判定是否被 `BatchToolExecutionContext.timeout_seconds` 的协作语义误读

**结论：no-diff 判定正确。**

- `agent.py:1973-1975`：`timeout_seconds` 设置在 `BatchToolExecutionContext` 上，是 informational metadata。
- `agent.py:2180-2186`：Engine 自己的 `await_or_cancel_or_timeout` 使用同一个 `tool_execution_timeout_seconds` 包裹 `ToolExecutor.execute`。
- `agent.py:2055-2088`：一旦 `ToolAwaitingOutcome` 被接受，Engine 立即 emit `RUN_SUSPENDED` 并 return。**没有**再次读取或应用 timeout。
- `BatchToolExecutionContext.timeout_seconds` 是给 ToolExecutor 的协作提示，不是 Engine 的二次 enforcement。Engine 的 timeout 只包裹 handshake，不包裹 accepted awaiting 外部 operation。
- **关键区别**：`timeout_seconds` 在 `BatchToolExecutionContext` 上是 "告诉 executor 你有多少时间返回 outcome"，而 `await_or_cancel_or_timeout` 是 "Engine 自己等多久"。两者使用同一个值，但语义不同。accepted awaiting 后，两者都不再生效。

### Challenge 5：Ruff baseline registry 与 exact node commands 是否能在 implementation completion 中复现

**结论：可复现。**

- baseline SHA 固定为 `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`。
- 当前全量 167 条 Ruff errors 是既有 registry。
- changed file `test_phase7_waiting_integration.py:8` 的 F401（`datetime.UTC imported but unused`）必须在 R05 清除。
- plan §9.2 给出了 changed Python files 的定向 Ruff 命令和全量 Ruff 命令。
- implementation completion 只需重跑这些命令并逐六元组匹配。

## 5. Coverage Matrix

| Slice | Changed Production File | Coverage Target | Notes |
|---|---|---|---|
| R05-S1 | `dayu/host/wait_adapter.py` | >= 80% | 唯一预期 production diff |
| R05-S1 | `dayu/host/_wait_observation.py` | 报告但不门禁 | 预期 no diff |
| R05-S1 | `dayu/host/waiting.py` | 报告但不门禁 | 预期 no diff |
| R05-S2 | `dayu/engine/agent.py` | 无 debt | 预期 no diff；若出现 diff 则 stop |

## 6. Residual Risks

| # | Risk | Owner | Tracking |
|---|---|---|---|
| R1 | cancelled wait abandon timeout 无限重试的资源影响 | Host durable evidence policy（future） | R05 residual；Issue 175 进程隔离可提供硬上限 |
| R2 | smoke timing 敏感性可能导致 CI flaky | R05 implementation（margin 策略） | R05-S2 smoke 实现时解决 |
| R3 | `_MarkWaitRecordAbandonTimeoutOperation` 和 `mark_wait_record_poll_abandon_timeout` 变为 dead code | 不在 R05 scope（store primitive 保持 read-only） | R05 source scan 确认零 production caller |
| R4 | Issue 175 进程隔离未实施 | Issue 175 owner | deferred |
| R5 | callback transport 与 authenticated callback ingress | future WU | deferred |

## 7. Blocking Questions

**无。**

所有 controller validation challenge points 已复核通过。plan 的 root cause 定位、semantic owner 判定、两 slice 原子性、closed allowlist、test-first 节点、验证矩阵、Ruff baseline、scans 和 stop conditions 均足够约束后续实施。

## 8. Final Plan Review Conclusion

**PASS-WITH-RISKS**

plan 达到 code-generation-ready 的 review 入口。两个 findings 均为 non-blocking：

1. Finding 001（中）：cancelled wait abandon timeout 无限重试的资源影响。建议在 plan §15 中显式声明为有意设计 residual risk。
2. Finding 002（低）：smoke timing 敏感性。建议在 plan 中明确 margin 策略。

plan 正确地把 root cause 定位在 `WaitPoller` 对 observation timeout 的业务解释，复用既有 `_release_with_backoff` 路径，不新增 schema/timer/scheduler/token/fence/lost outcome。Engine `agent.py` no-diff 判定有直接代码证据支持。两 slice 切分保持 umbrella 原子边界。closed allowlist 和 stop conditions 足以阻止 R06+/Issue 175/callback/permission 扩域。
