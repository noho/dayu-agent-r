# WU-SEMANTIC-OWNERSHIP-01 R05 Plan Adversarial Review — DS 第二路

## 0. Review 身份

- **reviewer**: AgentDS（第二路 plan review）
- **immutable target**: `docs/host/wu-semantic-ownership-01-r05-wait-observation-state-machine-plan.md`
- **base/HEAD**: `5ba0d8b61f9d03f52c4529f5b83a6cd353d002b1`
- **已读输入**: AGENTS.md、issues-implementation-control.md (R05 段)、umbrella remediation plan §12 (R05 manifest)、controller discussion Topic 5 final decision、docs/host/design.md (wait observation/abandon 段)、docs/engine/design.md (§11 §12)、target plan、controller validation
- **直接代码证据**: `dayu/host/wait_adapter.py` (全文件)、`dayu/host/_wait_observation.py` (全文件)、`dayu/host/waiting.py` (全文件)、`dayu/engine/agent.py` (handshake 段)、`dayu/host/durable/state.py` (claim/release/abandon/abandon_timeout 函数)、`utils/smoke_host_public_awaiting_entrypoint.py` (前 60 行)
- **证据收集命令**: rg 搜索 `tool_execution_timeout_seconds`、`_MarkWaitRecordAbandonTimeoutOperation`、`mark_wait_record_poll_abandon_timeout`、`poll_abandoned_at`、`claim_wait_record_for_poll` 等关键符号
- **结论**: **PASS**（零 blocker、零 accepted finding、五条 residual risk）

---

## 1. 攻击面覆盖矩阵

| 攻击维度 | 结论 | 直接证据 |
|---|---|---|
| root cause / semantic owner | PASS | `wait_adapter.py:1107-1108` 构造 `WaitPollLost(ResolveWaitLostOutcome(...))`；`wait_adapter.py:1367-1376` 构造 `_MarkWaitRecordAbandonTimeoutOperation`；owner 确认为 `WaitPoller` decision，非 runner/durable store |
| cancelled abandon timeout 是否真正 retry | PASS | `state.py:2537` 的 claim query 有 `poll_abandoned_at IS NULL` 条件；`state.py:2777` 的 `mark_wait_record_poll_abandon_timeout` 写入 `poll_abandoned_at` 阻断后续 claim；`_release_with_backoff` 不写 `poll_abandoned_at`，retry 通路成立 |
| late publication fence 唯一 | PASS | `_wait_observation.py:336-361` (`_publish`) 在线性化 gate 内校验 token identity/state/closed/generation；plan 不复制 fence |
| claim release / backoff 唯一真源 | PASS | `wait_adapter.py:1503-1543` (`_release_with_backoff`) 是唯一 release+backoff 路径；plan 复用而非复制 |
| 下一轮 terminal 闭环 (Ready/explicit lifecycle) | PASS | `state.py:2539` 要求 `poll_next_observe_at <= now`；backoff 到期后 claim 成功；explicit lifecycle (`mark_wait_record_poll_abandoned`) 仍写 `poll_abandoned_at` 实现 terminal |
| Engine `BatchToolExecutionContext.timeout_seconds` 与 accepted awaiting | PASS | `agent.py:1974` 和 `agent.py:2184` 只在 `_execute_batch` 内读取 timeout；`agent.py:2017-2019` 收到 `ToolAwaitingOutcome` 后加入 `awaiting_records` 且无后续 timeout 读取 |
| 两 slice 原子性 | PASS | S1 是唯一 production semantic transaction；S2 是跨层 contract evidence；S2 依赖 S1 完成 |
| closed allowlist | PASS | production write 只允许 `wait_adapter.py`；`_wait_observation.py`/`waiting.py` 预期 no diff；`agent.py` 预期 no diff；`durable/state.py` 为 read-only evidence |
| test-first 节点 | PASS | 两条新 owner test 在未改 production 的 base 上预期精确失败；Engine regression 预期在 base 上直接通过 |
| 真实 public smoke 时序 | PASS（附 residual risk） | `handshake budget < observation timeout (30s) < operation duration < timeout + initial backoff (60s)` 可行但慢 |
| coverage 基线 | PASS | `wait_adapter.py=83%` 当前已 >=80%；plan 对 changed file 设 >=80% 门禁 |
| Ruff 基线 | PASS | 全量 167 条既有红线；changed file 中 1 条 F401 必须清除；其余 166 按六元组继承 |
| README 决策 | PASS | Host/tests README 命中并计划更新；Engine README no diff 时不做机械修改 |
| security / deferred scope | PASS | 不实施 Issue 175/177/178、callback transport、unified authorization；cancellation/CAS/fencing 保留 |

---

## 2. 逐项 Finding

### 2.1 已确认：cancelled abandon timeout 的真正阻断机制（非 finding，确认 plan 正确性）

- **位置**: plan §2.1、§4 branch matrix、§5.1 R05-S1 production 变更
- **直接证据**:
  - `dayu/host/durable/state.py:2537` — claim query 对 CANCELLED wait 要求 `poll_abandoned_at IS NULL`
  - `dayu/host/durable/state.py:2777` — `mark_wait_record_poll_abandon_timeout` 写入 `poll_abandoned_at = ?`
  - `dayu/host/durable/state.py:2479` — `read_next_wait_record_poll_due_at` 同样要求 `poll_abandoned_at IS NULL`
  - `dayu/host/durable/state.py:2654-2655` — `release_wait_record_poll_claim` WHERE 子句接受 `status IN (WAITING, CANCELLED)`，不检查 `poll_abandoned_at`
- **结论**: `poll_abandoned_at` 是真正的阻断字段。一旦 `_MarkWaitRecordAbandonTimeoutOperation` 写入该字段，cancelled wait 永久无法被 claim。plan 改用 `_release_with_backoff` 后不写 `poll_abandoned_at`，因此 cancelled wait 在 backoff 到期后可被重新 claim。retry 通路成立。**这是对 plan 正确性的确认，不是 finding。**

### 2.2 已确认：Engine handshake timeout no-diff（非 finding，确认 plan 正确性）

- **位置**: plan §5.2、§2.1 代码证据表
- **直接证据**:
  - `dayu/engine/agent.py:1974` — 构造 `BatchToolExecutionContext.timeout_seconds` 时读取 `agent_policy.tool_execution_timeout_seconds`
  - `dayu/engine/agent.py:2184` — `_execute_batch` 内部 `await_or_cancel_or_timeout` 使用同一 timeout
  - `dayu/engine/agent.py:2017-2019` — `_execute_batch` 返回后，对 `ToolAwaitingOutcome` 的处理仅在 `isinstance` 检查后加入 `awaiting_records`，**无后续 timeout 读取**
  - `dayu/engine/agent.py:1983` — `batch_outcome = await self._execute_batch(batch_request)` 之后，若返回 `WaitTimedOut`（line 1987-1991）直接 terminal；若返回 `WaitCompleted`（line 1993+），进入 outcome 分类，**不再有 timeout 检查**
- **设计真源验证**: `docs/engine/design.md:398` 明确 "合法的长事务工具必须在该 handshake budget 内返回 `ToolAwaitingOutcome`；Host durable accepted 之后继续运行的外部长事务不受 `tool_execution_timeout_seconds` 限制"
- **结论**: Engine `agent.py` 的 no-diff 判定有直接代码证据支撑，不是推断。`BatchToolExecutionContext.timeout_seconds` 是协作提示字段（`docs/engine/design.md:120`），不等于 Engine 的 handshake enforcement。**这是对 plan 正确性的确认，不是 finding。**

### 2.3 已确认：两 slice 的 call graph 可达性（非 finding，确认 plan 原子性）

- **位置**: plan §5
- **直接证据**:
  - **R05-S1 change surface**: `wait_adapter.py:1102-1128` (poll timeout → LOST branch) 和 `wait_adapter.py:1363-1382` (abandon timeout → terminal marker branch) 是仅有的两个需修改的代码路径
  - **S1 不改的文件**: `_wait_observation.py` token/fence 路径、`waiting.py` typed terminal resolution、`durable/state.py` store primitives
  - **S2 只读的文件**: `agent.py` handshake wrapper、`smoke_host_public_awaiting_entrypoint.py`
  - S1 和 S2 之间不存在循环依赖：S2 的 Engine regression 在 base 上预期直接通过（当前 production 已正确）；S2 的 public smoke 依赖 S1 的 Host behavior 变更
- **结论**: 两 slice 边界清晰，可独立验证和回滚。S1 是唯一 production semantic transaction。**这是对 plan 正确性的确认，不是 finding。**

---

## 3. Adversarial Challenges（挑战失败，转为确认）

### 3.1 Challenge: `_release_with_backoff` 对 CANCELLED wait 的 CAS 安全性

- **假设**: 两个 poller 同时对同一 CANCELLED wait race release
- **验证**: `release_wait_record_poll_claim` (state.py:2641-2643) 的 WHERE 子句要求 `poll_claim_id = ? AND status IN (WAITING, CANCELLED)`。claim CAS（state.py:2530-2549）保证只有一个 poller 持有有效 claim_id。第一个 release 成功后 claim_id 已清空，第二个 release 的 CAS 必然失败 → `CAS_LOST` → claim_conflicts += 1。这是与 WAITING 路径完全相同的既有语义。
- **结论**: 无新增 race condition。**挑战不成立。**

### 3.2 Challenge: explicit lifecycle terminal 之后是否会被 backoff 意外重试

- **假设**: explicit applied/unsupported/noop 之后，backoff 可能重新 claim
- **验证**: `mark_wait_record_poll_abandoned` (state.py:2707) 写入 `poll_abandoned_at` 且 WHERE 子句 (state.py:2712) 要求 `poll_abandoned_at IS NULL`。claim query (state.py:2537) 要求 `poll_abandoned_at IS NULL`。因此 explicit terminal 写入 `poll_abandoned_at` 后，claim 永远无法再次匹配。
- **结论**: explicit lifecycle terminal 的阻断机制不受 timeout→backoff 修改影响。**挑战不成立。**

### 3.3 Challenge: `poll_abandoned_at IS NULL` 是否意味着即使没有 timeout，cancelled wait 也会在 backoff 后无限重试

- **假设**: 没有显式 lifecycle outcome 且 adapter 永远 timeout，cancelled wait 永远 retry
- **验证**: 这是正确的设计意图——observation timeout 只能证明"本次查询没返回"，不能证明"外部 job 已取消"。wait deadline（`deadline_at`/`expires_at`）由 `_handle_time_boundary` (wait_adapter.py:1407-1452) 在 claim 后、adapter 调用前处理——deadline 到期会调用 `expire_wait` 将 Run/Wait 收为 FAILED。这与 observation timeout 的 retry 是正交的两个机制。
- **结论**: 不存在无限 retry 风险；deadline expiry 是独立的 terminal 路径。**挑战不成立。**

### 3.4 Challenge: public smoke 的 `dataclasses.replace` 是否可能创建第二 policy 真源

- **假设**: smoke 通过 `dataclasses.replace` 覆盖 policy 字段，可能形成"测试专用 policy 构造路径"，被后续代码复用
- **验证**: plan §5.2 明确要求 "不能调用无参数 `WaitPollerRuntimePolicy()`，不能把 smoke 值写回产品 config，也不能创建第二 backoff 算法。packaged snapshot 与 test-effective timing 分开打印。" 且 `WaitPollerRuntimePolicy` 的所有字段均为 required（`wait_adapter.py:418-429`），无法无参构造。
- **结论**: `dataclasses.replace` 从 packaged snapshot 派生是标准做法，不会创建第二真源。**挑战不成立。**

---

## 4. Residual Risks（非 finding，需追踪但不阻塞）

### RR-1: design.md line 2430 "close marker" 措辞歧义

- **位置**: `docs/host/design.md:2429-2430`
- **当前写法**: "cancelled wait 的 abandon 超时只写 `wait_abandon_timeout` diagnostic/close marker，不宣称 provider 已取消成功。"
- **歧义**: "close marker" 可被读作 "关闭（停止后续观察）的标记"（支持当前 `_MarkWaitRecordAbandonTimeoutOperation` 的行为），也可读作 "本次 abandon 观察的关闭标记"（支持 plan 的 retry 语义）。
- **为什么不是 blocker**: controller discussion Topic 5 的 "cancelled-wait abandon timeout 同样 non-terminal retry" 是真源层级中的最高优先级（umbrella plan §2），覆盖 design.md 的措辞歧义。
- **建议**: R05 implementation 完成后，在 `dayu/host/README.md` 更新时同时澄清 design.md 该句为 "只写 `wait_abandon_timeout` transient diagnostic、释放 claim 并进入 backoff，不写 `poll_abandoned_at`，不宣称 provider 已取消成功。"
- **严重程度**: 低
- **追踪**: R05 completion report residual risks 段

### RR-2: `mark_wait_record_poll_abandon_timeout` store primitive 成为死代码

- **位置**: `dayu/host/durable/state.py:2728-2797`
- **当前状态**: 定义在 `durable/state.py`，仅在 `wait_adapter.py:706-731`（`_MarkWaitRecordAbandonTimeoutOperation`）和 `wait_adapter.py:51`（import）中被引用
- **R05 后状态**: `_MarkWaitRecordAbandonTimeoutOperation` 类及其调用被删除；`mark_wait_record_poll_abandon_timeout` 函数定义保留在 state.py 但无 production caller
- **风险**: 死代码可能被未来开发者误用；全仓 source scan 会命中该符号
- **为什么不在 R05 删除**: plan §2.1 和 controller validation §4.2 已裁决——仅为删除不可达 helper 而扩大 production allowlist 到 `durable/state.py` 会把 behavior remediation 扩成 storage cleanup
- **建议**: 在 R05 completion report 明确记录该 primitive 为 intentional dead code，并在函数 docstring 标注 "Deprecated: R05 后该 primitive 不再有 production caller；cancelled abandon timeout 改用 `release_wait_record_poll_claim`"
- **严重程度**: 低
- **追踪**: R05 completion report；若未来 state.py 因其他 sub-WU 进入 allowlist，应同步清理

### RR-3: public smoke 执行时间较长（~60s+）

- **位置**: plan §11 smoke command
- **原因**: 时序不等式 `operation duration > adapter_call_timeout_seconds (30s)` 且需等待真实 backoff（30s），总耗时约 60-90s
- **风险**: CI 环境可能因资源竞争导致 timing 漂移；若 smoke 采用固定 sleep 而非 event-driven，偶发 false negative
- **缓解**: plan 已要求 "给 CI 留出足够 margin" 并使用具名 smoke constants 和明确不等式
- **建议**: smoke 实现时优先使用 `threading.Event` / `asyncio.Event` 信号而非纯 sleep 来证明 late publication fencing；仅在 backoff 等待段使用 sleep
- **严重程度**: 低
- **追踪**: R05-S2 implementation 和 smoke validation

### RR-4: cancelled wait 的 backoff attempt 从 0 开始（与 WAITING 路径不同）

- **位置**: plan §3.2 backoff 真源
- **场景**: WAITING wait 在经历若干次 adapter_error/timeout 后 `poll_backoff_attempt` 已递增到 N；若随后 wait 被取消（CANCELLED），新的一轮 abandon timeout 的 `_release_with_backoff` 会基于 `poll_backoff_attempt + 1 = N+1` 计算 backoff。这是正确的——backoff 是连续的，不会因取消而重置。
- **但**: 若 CANCELLED wait 从未经历过任何 observation（直接被取消），其 `poll_backoff_attempt=0`，第一次 abandon timeout backoff 为 `backoff_initial_delay_seconds * (backoff_multiplier ^ 0) = 30s`。这是合理的初始退避。
- **风险**: 无。backoff attempt 在 `_release_with_backoff` 中基于 durable 当前值递增，语义连续。
- **严重程度**: 无（非风险，仅为文档记录）
- **追踪**: 无需追踪

### RR-5: 当前 public smoke 尚未覆盖 long operation + late timeout retry

- **位置**: plan §2.2 "当前 public awaiting smoke：packaged modes 与 12-field snapshot 正确，Run 经 WAITING 最终 SUCCEEDED/outbox match；但尚未覆盖 long operation 与 late timeout retry"
- **风险**: S2 的 smoke 修改是首个覆盖该场景的测试；若 smoke 实现有误，可能漏检 regression
- **缓解**: plan §11 的 smoke 验证矩阵极为具体（8 条必须断言），大大降低了 smoke 实现偏差风险
- **严重程度**: 低
- **追踪**: R05-S2 smoke validation

---

## 5. Coverage Matrix（逐项通过证据）

| 验证维度 | plan 要求 | 直接证据 | 结论 |
|---|---|---|---|
| test-first 红→绿 | 两条新 owner test 在 base 上精确失败 | plan §7.1 给出了 exact test nodes；§2.2 证明当前 41 passed 中两条断言旧错误 | PASS |
| authoritative lost 保留 | typed `WaitPollLost` 仍可 terminalize | plan §4 branch matrix row 3 | PASS |
| explicit lifecycle terminal 保留 | applied/unsupported/noop 仍 terminal | plan §4 branch matrix rows 6-8 | PASS |
| adapter exception/capacity 保留 | 既有 release/backoff 不变 | plan §4 branch matrix rows 5, 10-11 | PASS |
| close-drain 保留 | shared deadline + CLOSING | plan §4 branch matrix row 12 | PASS |
| wait deadline 独立 | `_handle_time_boundary` 不变 | plan §4 branch matrix row 13 | PASS |
| Engine handshake 不变 | `agent.py` no diff | §2.1 代码证据表 + engine/design.md:398 | PASS |
| R04 config 不变 | 12-field snapshot + typed modes | plan §1.2 完整列出 12 字段及 packaged 值 | PASS |
| coverage 门禁 | changed production file >=80% | `wait_adapter.py=83%` 当前已达标 | PASS |
| pyright | 0 errors | plan §2.3 当前 0 errors | PASS |
| Ruff changed-file | 全绿 | plan §2.3 已识别唯一的 F401 并计划清除 | PASS |
| Ruff full | 167→166 | plan §9.2 六元组继承规则 | PASS |
| diff check | allowlist 内 | plan §6.2 closed allowlist | PASS |
| source scan | timeout 不传播成 terminal | plan §10.1-10.5 五组 scan 命令 | PASS |
| security scan | 不实施 deferred scope | plan §10.5 security/deferred scan | PASS |

---

## 6. Open Questions

**无 blocking open question。** 以下为已自行验证的 design-level 问题：

1. **Q**: design.md line 2430 的 "close marker" 是否与 plan 的 retry 语义矛盾？
   **A**: 已核实。controller discussion Topic 5 的真源优先级高于 design.md 措辞歧义。见 RR-1。

2. **Q**: `_release_with_backoff` 对 CANCELLED 是否与 WAITING 有语义差异？
   **A**: 已核实。`release_wait_record_poll_claim` 的 WHERE 子句同时接受 WAITING 和 CANCELLED（state.py:2654-2655），claim 清理、next_observe_at、backoff_attempt、diagnostic 写入完全一致。无差异。

3. **Q**: 若 cancelled wait 的 abandon 反复 timeout 且无 explicit lifecycle outcome，是否会无限重试？
   **A**: 已核实。wait deadline（`deadline_at`/`expires_at`）在 claim 后、adapter 调用前由 `_handle_time_boundary` 独立处理，到期后 expire_wait 将 Run/Wait 收为 FAILED。见 Challenge 3.3。

---

## 7. Controller Validation 一致性检查

对照 `docs/reviews/wu-semantic-ownership-01-r05-plan-controller-validation.md`：

| controller assertion | 本 review 验证 | 结论 |
|---|---|---|
| root cause 在 `WaitPoller` decision owner | `wait_adapter.py:1107-1108` + `wait_adapter.py:1367-1376` | 一致 |
| `_wait_observation.py` token/fence 正确 | `_wait_observation.py:336-361` `_publish` | 一致 |
| `waiting.py` typed terminal 正确 | `waiting.py:1016-1024` 只接受显式 `ResolveWaitLostOutcome` | 一致 |
| `durable/state.py` 足够且不需扩域 | `state.py:2654-2655` 已支持 WAITING/CANCELLED | 一致 |
| `agent.py` no-diff 判定 | `agent.py:1974,2184` 只在 handshake 内读取 timeout | 一致 |
| 两 slice 原子性 | S1 production change + S2 evidence | 一致 |
| `poll_abandoned_at` 阻断机制 | `state.py:2537,2777` claim query + abandon_timeout write | 确认 |
| closed allowlist 完整 | `wait_adapter.py` 唯一 production diff | 一致 |

**无矛盾。Controller validation 的所有关键判断均被直接代码证据确认。**

---

## 8. Final Plan Review Conclusion

**PASS**

该 plan 对 root cause 的定位精确（`WaitPoller` 对 `WaitObservationTimedOut` 的错误业务解释），对 semantic owner 的判定正确（runner fence、durable store primitive、typed resolver 均保持 read-only），对两 slice 的切分保持了 umbrella 裁决的最小原子边界。

所有 adversarial challenge 均在直接代码证据下失败——`poll_abandoned_at` 的阻断机制、`_release_with_backoff` 对 CANCELLED 的 CAS 安全性、explicit lifecycle terminal 的不可逆性、Engine handshake no-diff 的代码路径，均在 plan 的正确一侧。

五条 residual risk 均为非 blocking：一条设计文档措辞歧义（RR-1）、一条 intentional dead code（RR-2）、一条 smoke 性能注意（RR-3）、一条语义确认（RR-4）、一条 smoke 覆盖缺口（RR-5）。它们不影响 plan 的 code-generation-ready 判定。

**无 accepted finding、无 blocking question、无 owner/allowlist 修改建议。**

下一 gate：AgentCodex 创建 plan-fix artifact（即使 zero-change），随后 AgentMiMo + AgentDS 双路完整 plan re-review。
