# WU-LIFE-01 + WU-LIFE-02 Plan Review

日期：2026-06-01
角色：plan review specialist (DS)
当前 gate：plan review
待 review plan：docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md
设计真源：docs/host/design.md
总控文档：docs/host/host-core-followup-implementation-control.md
讨论/code inspection artifact：docs/reviews/wu-life-01-02-discussion-code-inspection-20260601.md
controller adjudication artifact：docs/reviews/wu-life-01-02-discussion-controller-adjudication-20260601.md

## Review Scope

按 plan review gate 要求，逐项检查：
- 以 design.md 设计目标、第 27 节 Host Lifecycle / Recovery、Host opener close / scheduler close 语义为真源。
- 检查 plan 是否 code-generation-ready。
- 检查 plan 是否默认 tests/proof-first。
- 检查 Slice A / Slice B file ownership 是否清晰。
- 检查每个场景是否标注 existing coverage / new coverage / non-goal。
- 检查 production code allowed changes 是否被 tests-first failure 严格触发。
- 检查 stop conditions 是否覆盖 contract/schema/state-machine/public-interface 风险。
- 检查 RR-DUR-01 是否明确 closed/out of scope，RR-DUR-04 是否进入 proof matrix 但不预设代码改动。
- 检查 README/doc sync decision 是否符合 AGENTS.md 固定职责。
- 优先 correctness、maintainability、scope control、testability。

## Design Alignment Verification

### Design doc Section 27 (Host Lifecycle / Recovery)

Plan 与 design.md 第 27 节对齐验证：

| 设计真源要求 | Plan 对应 | 对齐 |
|---|---|---|
| Recovery scan 只基于 durable truth（Run/Attempt/EventLog/dispatch/wait/liveness），不依赖 projection/memory lag | Plan line 23: recovery truth = durable truth only；RR-DUR-04 matrix row 逐路径证明 | 对齐 |
| ACCEPTED / QUEUED / WAITING startup scan 不得被推进到 RECOVERING | Plan Slice A matrix: ACCEPTED→ACCEPTED_WAKE, QUEUED→QUEUE_PROMOTION_CHECK, WAITING→WAITING_DIAGNOSTIC_ONLY | 对齐 |
| 旧 Attempt 不 takeover，恢复必须创建新 Attempt | Plan line 21, 50-53: positive orphan proof → ATTEMPT_LOST + RUN_RECOVERING → new Attempt | 对齐 |
| positive orphan proof 必须同时满足 owner heartbeat stale + pid evidence + CAS recheck | Plan line 48-52: _classify_active_or_cancelling 只接受 PositiveOrphanProof | 对齐 |
| heartbeat stale alone / pid alone 不构成 orphan proof | Plan Slice A: OWNER_STILL_LIVE / ORPHAN_INCONCLUSIVE 不写 recovery facts | 对齐 |
| RECOVERING dispatch limit 基于 EventLog | Plan line 53: 基于 EventLog 统计 recovery dispatch 次数 | 对齐 |

### Design doc Section 11 (Host opener close / scheduler close 语义)

| 设计真源要求 | Plan 对应 | 对齐 |
|---|---|---|
| Host close 是 handle lifecycle，不是用户 cancel | Plan line 22-23: close 语义为 handle lifecycle, 不是用户 cancel | 对齐 |
| close 后 API fail-fast | Plan evidence line 59: _raise_if_closed() fail-fast | 对齐 |
| close 不得写 CANCEL_REQUESTED / RUN_CANCELLED / RUN_FAILED / RUN_LOST | Plan Slice B matrix: close non-drain / close cancellation retry 均断言无 terminal fact | 对齐 |
| close 传播 lifecycle cancel，未收口 Attempt 由 positive orphan proof 路径处理 | Plan line 62-63: cancel_all 快照取消语义；non-drain 后 durable pending 由 next open recovery 解释 | 对齐 |
| close 不得伪装用户意图 | Plan Slice B: close 不写 cancel/failed/lost，user cancel 走 cancel_session_runs 分离路径 | 对齐 |

**结论**：Plan 在所有关键语义上与 design.md 对齐，无冲突。

## Plan Review Findings

### Code-Generation Readiness

Plan 具备 code-generation-ready 特征：
- Slice A 与 Slice B 均有明确的 allowed files、exact changes、non-goals、validation commands、completion signal、stop condition。
- 每个 matrix row 有明确 expected decision / durable mutation。
- 新增测试的具体断言已描述（例如 "断言不写 ATTEMPT_LOST / RUN_RECOVERING / RUN_LOST"）。
- 生产代码修改的触发条件和允许范围已精确界定。
- 现有代码已存在 `_close_cleanup_done` retry pattern（dispatch.py:1665-1667），plan 的 close cancellation retry cleanup 策略有直接代码基础。

### Tests/Proof-First Verification

Plan 明确以 tests-first 为默认路径：
- Plan line 101: "Implementation agent 必须 tests-first：先补 proof matrix 与 focused tests；只有测试直接失败且失败对应本计划 stop condition 允许的最小生产修复，才修改生产代码。"
- Slice A production changes (line 119-132) 均受 failing test 严格触发。
- Slice B production changes (line 151-163) 均受 failing test 严格触发。
- 允许的最小生产修改范围精确到文件和条件。

### Slice A / Slice B File Ownership

| 文件 | Slice A | Slice B | 评估 |
|---|---|---|---|
| tests/host/test_recovery_scan.py | 主文件：matrix 常量 + still-live/inconclusive/WAITING tests | 无 | 清晰 |
| tests/host/test_recovery_dispatch.py | 仅在 matrix mapping 或极小断言时 | 无 | 清晰 |
| tests/host/test_recovery_orphan_classifier.py | 仅在发现 reason 缺口时（默认不改） | 无 | 清晰 |
| tests/host/test_open_host_runtime.py | 仅在 public-path WAITING 语义测试时 | 仅在 opener close retry/finally 边界时 | 共享文件，但条件互斥，风险可控 |
| tests/host/test_dispatch_scheduler.py | 无 | 主文件：matrix 常量 + close-window tests | 清晰 |
| tests/host/test_public_lifecycle_smoke.py | 无 | 仅在补 public close terminal fact assertion 时（默认不改） | 清晰 |
| dayu/host/recovery.py | 仅在 test failure 证明 scanner 错误时 | 无 | 清晰 |
| dayu/host/recovery_process.py | 仅在 test failure 证明 classifier 错误时 | 无 | 清晰 |
| dayu/host/durable/run_transition.py | 仅在 test failure 证明 closeout payload/reason 错误时 | 无 | 清晰 |
| dayu/host/dispatch.py | 无 | 仅在 test failure 证明 close cleanup / cancel_all 错误时 | 清晰 |
| dayu/host/open_host.py | 无 | 仅在 test failure 证明 opener close retry/finally 边界错误时 | 清晰 |

**评估**：`test_open_host_runtime.py` 在 Slice A 和 Slice B 均出现，但各自条件互斥（Slice A 仅 public-path WAITING 语义，Slice B 仅 opener close retry/finally 边界），且 controller 按 slice 顺序派发，冲突风险低。allowed production files 范围精确——如果遇到需要触碰其他内部模块（如 `durable/state.py`）的 bug，stop condition 已覆盖 "需要改变 durable schema" 等约束，implementation agent 应停止并回报 controller。

### Coverage Annotation Completeness

Slice A matrix: 19 rows，全部标注 existing/new/non-goal。
Slice B matrix: 17 rows，全部标注 existing/new/non-goal 或条件覆盖（如 "new coverage if fixture can deterministically hit window"）。

未发现遗漏标注的 matrix row。

### Stop Condition Coverage

Plan stop conditions 覆盖了以下风险类别：

| 风险类别 | Slice A stop condition | Slice B stop condition |
|---|---|---|
| Durable schema 变更 | Line 276: "需要改变 durable schema" | Line 336: "需要 durable schema" |
| EventLog event type 变更 | Line 276: "EventLog event type" | Line 336: "EventLog event type" |
| Public API 变更 | Line 276: "public Host API" | Line 336: "public API 变化" |
| Run/Attempt 状态机变更 | Line 276: "Run / Attempt 状态机" | Line 336: "Run / Attempt 状态机" |
| WAITING durable 语义变更 | Line 276: "WAITING durable 语义" | 不适用 |
| Projection/read model 误用为 truth | Line 274: "依赖 projection/read model 或 inconclusive proof" | 不适用 |
| Close 写 terminal fact | 不适用 | Line 334: "需要改变...public cancel semantics" |
| 引入新抽象 (lease/fencing) | Line 277: "需要改变...引入新抽象" | Line 337: "需要引入 lease/fencing" |
| Close drain-until-empty | 不适用 | 非目标明确声明 |
| 无法 deterministic 构造测试 | Line 277: "无法构造 deterministic test" | Line 335: "无法 deterministic 构造" |
| Reason/diagnostic 不可区分 | Line 275: "reason / diagnostic 无法区分" | 不适用 |

**评估**：Stop conditions 覆盖完整。

### RR-DUR-01 / RR-DUR-04 Scope

- **RR-DUR-01**：Plan line 106-107 明确 "在本 work unit 关闭，不进入 scope。" Matrix 标注 "non-goal; closed by evidence." 关闭依据（recovery scanner 不依赖 projection checkpoint，已有 deterministic CAS 和 recovery projection-lag 测试）已在 discussion artifact 和 controller adjudication 中确认。**符合要求**。

- **RR-DUR-04**：Plan line 105-106 明确 "只进入 proof matrix...除非测试或直接代码证据证明某路径违规，否则不改生产代码。" Matrix 标注 "new coverage as proof matrix mapping; code evidence first." Slice A exact changes 包含 "将 RR-DUR-04 作为 matrix row：标注 recovery scanner 使用短 write transaction，projection lag existing tests 已覆盖，不新增 production code。" **符合要求**。

### README/Doc Sync Decision

Plan line 341-348 定义了后续 implementation gate 的 README 触发规则，与 CLAUDE.md 固定职责对齐：
- 只新增 tests 且不改 public contract → 不更新 README。
- 生产代码修复改变 Host close/recovery 稳定说明但不改 public API → 检查 dayu/host/README.md 是否需要同步。
- 新增稳定测试入口/marker/命令 → 更新 tests/README.md。
- 改变 public Host API / durable schema / EventLog / Run/Attempt 状态机 → 立即停止，先回 controller。

**符合 CLAUDE.md 和 control doc 要求**。

## Conclusion: pass

无 blocking finding。

Plan 满足 code-generation-ready 标准、tests-first 默认、清晰 slice ownership、完整 coverage annotation、严格 gated production changes、覆盖面完整的 stop conditions、正确的 RR-DUR-01/RR-DUR-04 scope 处理和符合 CLAUDE.md 的 README sync 决策。

## Blocking Open Questions

none。

## Review Summary

- **Artifact path**: docs/reviews/wu-life-01-02-plan-review-ds-20260601.md
- **结论**: pass
- **P1 findings**: 0
- **通过**: 是
