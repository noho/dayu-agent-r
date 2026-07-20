# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-A Plan Re-Review — MiMo

## Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-A`
- Gate: plan re-review after AgentCodex plan fix
- Timestamp: `20260712-122404`
- Branch: `phaseflow/host-issues-control`
- Review target: `docs/host/wu-semantic-ownership-01-round3-r3-a-host-lifecycle-durable-plan.md`
- Plan-fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-fix-codex.md`
- Prior review inputs:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-review-controller-adjudication.md`
- Decision: `pass-with-risks`

## Re-Review Scope

1. Verify every accepted finding in controller adjudication is actually fixed in the plan.
2. Verify the new 8-slice structure is justified.
3. Verify R3-A accepted findings remain fully covered.
4. Verify S2-S5 handoffs are coherent.
5. Verify S1/S3/S6/S8 contract clarifications are concrete enough.
6. Verify no new material plan defect was introduced.

---

## 1. Controller Accepted Finding Verification

### DS Findings

| Finding | Status | Evidence |
| --- | --- | --- |
| F-01 S2 over-broad | **fixed** | 旧 S2 已拆为 S2 (admin opener/actor, `:298`)、S3 (health/admission, `:389`)、S4 (recovery, `:481`)、S5 (cancel watchdog, `:542`)。每个 slice 有独立目标/non-goals/allowed files/tests/stop condition。plan `:170` 显式论证了拆分理由和禁止合并关系。 |
| F-02 fatal/admission race test | **fixed** | S3 `:430-443` 定义了完整的 deterministic race mechanics：typed `_BarrierDurableInvoker`、`actor_entered`/`actor_release`/`fatal_started`/`wake_entered` 四个同步点、admission-first 脚本（4步）、fatal-first 脚本、caller-cancellation 变体。断言检查 durable identity + wake order + monotonic sequence，禁止 sleep/probabilistic oracle。 |
| F-03 daemon observation lifecycle | **fixed** | S6 `:148-152` 冻结了 token `ACTIVE→INVALIDATED→FINISHED` gate、`max_outstanding_adapter_calls`、shared monotonic close deadline、registry lock 追踪 live token/thread、publish 在同锁下验证 token+generation、supervisor CLOSING/STOPPED 反映真实线程状态。S6 反例 #6-#10 覆盖 stuck poll/abandon、late publish、cap=1、shared deadline。 |
| F-04 S1 schema feasibility | **fixed** | S1 `:107` 冻结了 schema pre-check 裁决（基于当前 DDL 证据，无需 DDL 变更）。S1 `:234-244` 定义了实施前 `rg` 命令、预期列清单和 zero-edit stop condition。 |
| F-05 process start ambiguity | **fixed** | S8 `:165` 冻结"start()异常后同一 handle 不可重试，调用方必须新建 handle"，明确不以 `pid is None`/`is_alive()` 猜测。S8 non-goal `:765` 和反例 #1-#2 覆盖 pre-spawn/post-spawn 两类失败。 |
| F-06 Host/HostAdmin Protocol | **fixed** | S2 `:112` 明确"两个独立 Protocol，不继承、不互相扩展、不保留 compatibility wrapper"。S2 反例 #3 验证 package export/compile tests 禁止 compatibility wrapper。方法集合在 `:112` 分别列出。 |

### MiMo Findings

| Finding | Status | Evidence |
| --- | --- | --- |
| F1 DR-017/DR-029 diagnosis / S5 overdesign | **fixed-as-narrowed** | 第一性原理表 `:63` 纠正 DR-017 为 partial start/cleanup poisoning；`:65` 纠正 DR-029 为 release-failure-after-attempted-release。S8 `:162` 冻结最小修复：保留并发 gate、分离 cleanup completion、不强制五状态重写。S8 反例 #6 明确验证 failed token 仍 held 时 `_close_completed` 保持 false。 |
| F2 S2 over-broad | **fixed** | 同 DS F-01。 |
| F3 projector metadata descriptor shape | **fixed** | S1 `:102` 冻结六字段 `ProjectorMetadata` descriptor shape（`projector_metadata_id`、`projector_id`、`projector_schema_version`、`projector_digest`、`purpose`、`source_contract_refs`），三个 producer 填充规则，compactor `metadata_id→projector_metadata_id` rename，Tool Trace 五字段 projection。S1 反例 #2 验证 300-message descriptor shape 一致性。 |
| F4 durable actor thread-safety | **fixed** | S2 `:113-119` 完整定义：`_HostDurableInvoker` method-generic Protocol（`Callable[[HostCommandHandle], T]`）、`ThreadPoolExecutor(max_workers=1)` worker thread 拥有 command handle/connection、scheduler 独立 connection、`_ThreadsafeSchedulerWakeupPort`/`_ThreadsafeActiveWorkerCancelPort` bridge、caller cancellation shield、busy retry 只占 actor thread、close order 固定。S2 反例 #4-#8 和 review focus 覆盖 thread identity/bridge/cancel/close。 |
| F5 wait expiry helper relation | **fixed** | S6 `:144-146` 冻结 `ExpireWaitInput`/`ExpireWaitResult` typed 定义、caller-provided `HostTransaction`、复用 `ResolveWaitFailedOutcome`/`_wait_resolution_payload_plan()`/`fail_run_from_waiting_in_transaction()`、stable idempotency key。S6 反例 #1 transaction spy 验证不创建 nested transaction。 |
| F6 DR-017 queue cleanup | **fixed-merged** | S8 `:166` 冻结 queue close/feeder cleanup 进入 finally 路径、step completion recording、single-flight shielded cleanup task。S8 反例 #3 验证 kill/join/process close 分别抛异常后 queue 仍被清理。 |

**结论：controller adjudication 中全部12个 accepted findings 均已在 plan 中实际修复或澄清，无遗漏。**

---

## 2. 8-Slice 结构验证

### Control-doc 约束核对

`docs/phaseflow-umbrella-optimization-control.md:117` 规定生产 state machine / durable change "按真实 owner boundary 拆 2-4 个 slices"；`:119` 要求"超过 3 个 slices 时，plan 必须说明为什么不能合并"。

controller adjudication 进一步要求："More than five slices is acceptable only if each slice is owner-closed and reviewable; the plan must explicitly justify the extra gate cost against the optimization control."

### Plan 的论证

Plan `:170-185` 提供了逐对禁止合并的理由：

| 禁止合并对 | 理由 |
| --- | --- |
| S1↔S2 | runner payload stress 失败定位会被 opener 并发改动淹没 |
| S2↔S3 | connection/thread ownership 错误与 health state machine 错误需要独立回滚 |
| S3↔S4 | fatal lease correctness 不依赖 recovery cursor |
| S4↔S5 | recovery batching 和 cancel classification 是不同 owner/failure matrix |
| S5↔S6 | cancel governance 和 wait terminal 是不同 semantic owner |
| S6↔S7 | wait 和 compaction 虽都有 timeout，但 token 可写面/terminal oracle/provider-call barrier 不同 |
| S8↔任何 Host slice | runtime 层中立，不引入 Host 反向依赖 |

### 评估

每个 slice 确实是 owner-closed 的——有独立目标、non-goals、allowed files、tests、review focus 和 stop condition。8 个 slice 的 handoff 链（S1→S2→S3→S4→S5→S6→S7→S8）每一步都基于前一 slice 的输出作为下一 slice 的输入，不存在 orphan half-state。

额外 3 个 gate（相比 5-slice）的固定成本已被 plan 显式核算（`:172`），并论证该成本低于在单个 production-high 并发 slice 中定位跨线程/事务/恢复/取消组合故障的风险。

**风险**：8-slice 超出 control doc "2-4 slices" 建议范围较大。虽然论证合理，但实际执行时 gate 固定成本可能显著拖慢进度。如果实施过程中某些相邻 slice（如 S4+S5）实际变更范围远小于预期，controller 可在 per-slice review 后裁决合并后续 gate。这不是 plan defect，是执行风险。

**结论：8-slice 结构有充分理由，每个 slice 是 owner-closed 的，比旧单一 S2 更可 review。通过。**

---

## 3. R3-A Accepted Finding 覆盖验证

Plan `:821-844` 提供了完整的 finding/confirmation traceability 账本。逐项核对：

| Finding | Slice | 测试覆盖 | Source scan | Stop condition | 评估 |
| --- | --- | --- | --- | --- | --- |
| DR-006 | S1 | 0/1/12/300 producer matrix + stress 12/12 | `projector_metadata_summary` scan | hot payload <4096 | ✅ |
| DR-010 | S1 | schema pre-check + tamper matrix | schema columns scan | 任一 tamper 接受即 stop | ✅ |
| compact ref fallback | S1 | missing/wrong request ref | `tool_call_event_ref = row.event_id` scan | 伪造 ref 接受即 stop | ✅ |
| DR-007 | S2 | no-secret real CLI list/purge | `open_host_admin/open_host` scan | admin 启动 scheduler 即 stop | ✅ |
| DR-011 | S2 | external lock + Event barrier ticker | `to_thread`/actor typing scan | ticker 不能推进即 stop | ✅ |
| DR-009 | S3 | deterministic admission-first/fatal-first race | health owner scan | accepted+zero-wake 即 stop | ✅ |
| retry exhaustion | S3 | one-shot retry 后最终 dispatch | retry branch scan | retry 导致 UNAVAILABLE 即 stop | ✅ |
| idempotent replay | S3 | pending/pre-start replay wake | `idempotent_replay` scan | replay 无 wake 即 stop | ✅ |
| recovery batching | S4 | batch=2、watermark、failure/replay | full reader/OFFSET scan | unbounded tx 即 stop | ✅ |
| watchdog wake | S5 | tick barrier second wake | `Queue(maxsize=1)` scan | 丢 wake 即 stop | ✅ |
| cancel race | S5 | transaction spy + multiprocess | `_is_deferred_cancel_state` scan | 第二 snapshot 即 stop | ✅ |
| DR-008 | S6 | helper contract + race | expire helper scan | expired Wait 仍 WAITING 即 stop | ✅ |
| DR-012 | S6 | stuck poll/abandon + cap + deadline | optional timeout/无参 join scan | close 无界即 stop | ✅ |
| Fins boundary | S6 | Host adapter tests | `dayu/fins/` diff 为空 | 修改 Fins 即 stop | ✅ |
| DR-025 | S7 | timeout→success + parent cancel | timeout target scan | parent token 被写即 stop | ✅ |
| proactive TOCTOU | S7 | recorder 后改 snapshot | prepare/pre-call scan | stale 调 provider 即 stop | ✅ |
| DR-017 | S8 | pre/post-spawn + partial failure | start/close gate scan | 同 handle 重试即 stop | ✅ |
| DR-029 | S8 | two-token one-fails + retry | `_close_completed` scan | failed token 仍 completed 即 stop | ✅ |

**结论：全部 R3-A accepted findings 和 confirmations 均有对应 slice、tests、source scan 和 stop condition 覆盖，无遗漏、无推迟。通过。**

---

## 4. S2-S5 Handoff 连贯性验证

### S2 → S3

- **S2 输出**：`_HostDurableActor`（connection/thread ownership）、`_ThreadsafeSchedulerWakeupPort`（actor→scheduler wake bridge）、`_ThreadsafeActiveWorkerCancelPort`（actor→worker cancel bridge）、`Host`/`HostAdmin` independent Protocol、close order。
- **S3 输入**：health gate 需要 actor 作为 public admission 的 durable command path；admission lease 覆盖 actor transaction + thread-safe wake bridge + future 收口；fatal transition 使用同一 lease。
- **验证**：S3 allowed files 包含 S2 交付的 `_durable_actor.py`（仅在允许列表隐含——S3 `:413` 说"S2的`_durable_actor.py`不在本slice allowed list"，但 S3 的 health gate 和 admission lease 是在 S2 actor 之上构建的，S3 修改的是 `_execution_health.py`、`admission.py`、`dispatch.py` 等，这些文件通过 S2 的 bridge/Protocol 与 actor 交互）。S3 stop condition `:479` 要求"deterministic admission-first/fatal-first/caller-cancel 三个脚本全绿"，这些脚本使用 S2 的真实 actor。
- **结论**：连贯，无 orphan half-state。

### S3 → S4

- **S3 输出**：`HostExecutionHealthGate`（STARTING→READY→UNAVAILABLE→CLOSING→CLOSED）、admission lease。
- **S4 输入**：recovery batching 在 actor-owned command path 上执行；全部批次和 pending wake 成功后 health gate 才可 READY。
- **验证**：S4 `:497` 明确"opener loop只在该批commit后执行对应wake"；`:534` stop condition 要求"任一batch/invariant失败时opener不进入READY"。S4 的 READY handoff 直接消费 S3 的 health gate 状态。
- **结论**：连贯。

### S4 → S5

- **S4 输出**：recovery 完成后 health gate READY。
- **S5 输入**：active-cancel watchdog 改为 level-triggered Event；cancel classification 进入 `_CancelRunOperation` 同一 write transaction。
- **验证**：S5 non-goal `:553` 明确"不修改recovery cursor、health state machine、actor connection或wait adapter"。S5 反例 #7 验证"cancel释放active slot后promotion wake与durable classification一致"——这依赖 S2/S3 的 actor bridge 和 health gate，但不依赖 S4 的 recovery cursor。
- **结论**：连贯。S4 和 S5 是独立 owner，不需要 S4→S5 的直接数据 handoff；两者都消费 S2/S3 的基础设施。

### 中间状态测试可行性

S3 的 deterministic fatal/admission race 测试（`:430-443`）使用 S2 的真实 actor 和 typed barrier invoker。测试脚本在 S2 完成后即可运行，不依赖 S4/S5。S5 的 watchdog/cancel 测试使用 S3 的 health gate supervisor（watchdog critical task 异常走 S3 health gate，S5 `:141`），但不依赖 S4 的 recovery cursor。

**结论：S2-S5 handoff 链连贯，无 orphan half-state，无 impossible intermediate tests，无 hidden implementation redesign。通过。**

---

## 5. 关键契约具体性验证

### S1 Schema Feasibility Pre-Check

Plan `:107` 冻结了 pre-check 裁决，`:234-244` 定义了具体 `rg` 命令、预期列清单和 stop condition。足够具体。

### Projector Metadata Descriptor Shape

Plan `:102` 冻结了六字段 shape，三个 producer 的填充规则，compactor rename/schema/source refs。足够具体。

### `_HostDurableActor` Typing/Thread Ownership

Plan `:113-119` 定义了 method-generic `_HostDurableInvoker` Protocol（`Callable[[HostCommandHandle], T]`）、`ThreadPoolExecutor(max_workers=1)` worker thread、handle/connection 不离开该线程、scheduler 独立 connection、两个 thread-safe bridge port、caller cancellation shield、close order。足够具体。

### Fatal/Admission Deterministic Test

Plan `:430-443` 定义了 `_BarrierDurableInvoker`、四个 `asyncio.Event` 同步点、admission-first 四步脚本、fatal-first 脚本、caller-cancellation 变体、断言方式（durable identity + wake order + monotonic sequence）。足够具体，实施 agent 可直接编码。

### S3 Retry Exhaustion

Plan `:124` 明确"`HostTransactionRetryExhaustedError` 是 transient：drain record 保持 durable pending，按 `dispatch_poll_interval_seconds` 退避后重新 reconciliation，不关闭 scheduler、不 cancel active workers、不进入 UNAVAILABLE"。足够具体。

### S6 `_expire_wait_in_transaction` Contract

Plan `:144-146` 定义了 `ExpireWaitInput`/`ExpireWaitResult` typed 字段、caller-provided `HostTransaction`、复用 `ResolveWaitFailedOutcome`/`fail_run_from_waiting_in_transaction()`、stable idempotency key。足够具体。

### S8 Partial Cleanup Completion

Plan `:162-168` 定义了 start/close gate 与 cleanup completion 分离、single-flight shielded cleanup task、step completion recording、partial release retry、`_close_completed` 只在 held_tokens 为空且无 error 时写 true。足够具体。

**结论：所有要求的契约澄清均足够具体，实施 agent 可直接编码。通过。**

---

## 6. 新 Material Plan Defect 检查

### 检查项

- S3 deterministic test 的 `fatal_started` 同步点是否充分？→ 充分。fatal coroutine 在同一 event loop turn 设置 `fatal_started` 后继续到 lease acquire，主 test 等待 `fatal_started` 后 fatal 已排在 lease 队列中。
- S5 反例 #7 的 promotion wake 验证是否依赖 S4 recovery？→ 不依赖。cancel 释放 active slot 后的 promotion wake 是 S2/S3 bridge 的行为，与 S4 recovery cursor 无关。
- S2 的两个 connection（scheduler-owned + actor-owned）是否会导致 WAL 并发问题？→ SQLite WAL 允许多 reader + 单 writer，两个 connection 各自持锁，不会互相阻塞。S2 反例 #5 的 external `BEGIN IMMEDIATE` 测试验证了这一点。
- S6 的 `max_outstanding_adapter_calls` 是否与现有 code 兼容？→ 新增 policy 字段，现有 code 不使用它；S6 反例 #8 验证 cap=1 行为。
- S8 的 `asyncio.shield()` cleanup task 是否可能泄漏？→ Plan `:166` 要求"每个process/queue步骤只在成功后记录completed；task失败时第二次close基于步骤记录补齐未完成步骤"。有界。

**结论：未发现新的 material plan defect。**

---

## Findings

无 material remaining findings。

---

## Open Questions

1. **S3 health gate 与现有 scheduler close 的交互**：S3 定义了 health gate（STARTING→READY→UNAVAILABLE→CLOSING→CLOSED），但现有 scheduler close 流程（S2 close order）也涉及 CLOSING/CLOSED 状态。Plan 未显式说明 health gate 的 CLOSING/CLOSED 与 scheduler close 的 CLOSING/CLOSED 是否是同一个状态机。风险低：S2 close order `:119` 已明确 close 顺序，S3 health gate 的 CLOSING 应该是 scheduler close 的入口之一。实施时需确认。

2. **S4 recovery batching 与 S3 READY 的精确交界**：S4 要求"全部批次和pending wake成功后health gate才可READY"，但 S3 的 READY 条件也包含"actor、startup recovery、scheduler critical tasks 都成功"。两者是否可能产生 READY 条件循环依赖？风险低：S4 是 S3 的子步骤，S3 的 READY 条件应包含 S4 recovery completion。

---

## Residual Risks

| Risk | Owner | Destination |
| --- | --- | --- |
| 8-slice gate 固定成本可能拖慢进度 | Controller | per-slice review 后可裁决合并后续 gate |
| S3 health gate 与 scheduler close 状态机交界 | S3 implementer | 实施时确认，或在 S3 review 中验证 |
| Fins wait-adapter reverse dependency (R3-D half) | R3-D owner | controller 已裁决 |
| scheduler-owned transaction 可能仍阻塞 heartbeat | R3-A residual | 需集成 lock probe |

---

## Final Plan Review Conclusion

**Pass with risks.**

Plan 已正确修复 controller adjudication 中全部 12 个 accepted findings。8-slice 结构有充分理由且每个 slice 是 owner-closed 的。R3-A 全部 accepted findings 和 confirmations 均有完整覆盖。S2-S5 handoff 链连贯。关键契约澄清足够具体。未发现新的 material plan defect。

两个 open questions 是低风险实施确认项，不构成 blocker。8-slice 的 gate 成本是已知执行风险，可在 per-slice review 后由 controller 动态调整。

**Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-a-plan-rereview-mimo.md`
