# WU-LIFE-01 + WU-LIFE-02 Plan Review

日期：2026-06-01
Reviewer：mimo
Gate：plan review
输入 artifact：docs/host/wu-life-01-02-recovery-scheduler-lifecycle-plan.md
设计真源：docs/host/design.md
总控文档：docs/host/host-core-followup-implementation-control.md
讨论 artifact：docs/reviews/wu-life-01-02-discussion-code-inspection-20260601.md
Controller 裁决：docs/reviews/wu-life-01-02-discussion-controller-adjudication-20260601.md

## Review 方法

逐项核对 review lens：design source 对齐、code-generation-readiness、tests-first、file ownership、coverage annotation、production code trigger、stop conditions、RR-DUR-01/04、README/doc sync、correctness、maintainability、scope control、testability。

## Review Findings

### 1. Design Source 对齐

Plan 正确引用 `docs/host/design.md` 第 27 节作为 recovery 与 close 语义的真源。逐项核对：

- **Recovery scan 只基于 durable truth**：Plan 第 17-18 行、第 88 行明确 recovery truth source 仍只使用 durable Run / Attempt / EventLog / dispatch / wait / payload / liveness truth。与 design.md 第 2913 行一致。
- **positive orphan proof 才允许 recovery**：Plan 第 112-113 行 scanner still-live / inconclusive 测试断言不写 `ATTEMPT_LOST` / `RUN_RECOVERING`。与 design.md 第 2907-2908 行一致。
- **`WAITING` 不创建 recovery Attempt**：Plan 第 114 行、第 173-174 行明确 `WAITING` startup recovery diagnostic-only。与 design.md 第 2906 行、第 2944 行一致。
- **Host opener close 不写 terminal fact**：Plan 第 23 行、第 138-139 行、第 154-155 行多处明确 close 不写 `CANCEL_REQUESTED` / `RUN_CANCELLED` / `RUN_FAILED` / `RUN_LOST`。与 design.md 第 3015 行一致。
- **close 不无限 drain**：Plan 第 37 行、第 138-139 行明确 dispatch / promotion durable pending 状态由 next open recovery 解释。与 design.md 第 3040-3045 行 graceful shutdown 语义一致（停止接收、传播 cancel、不伪造 terminal）。
- **close 不替换 positive orphan proof**：Design.md 第 3015 行明确 close 后重启由 owner `STOPPED` lifecycle proof 推进 recovery。Plan 不改变该语义。

结论：Plan 与 design source 完全对齐，无偏离。

### 2. Tests-first 与 Production Rewrite 预设

Plan 第 26 行明确"默认实现路径是测试与证明补强，不预设 recovery 或 scheduler close 生产逻辑重写"。Slice A（第 119-131 行）和 Slice B（第 151-163 行）均只有 tests-first failure 才允许最小生产修复，且列出了精确的失败条件和允许修改范围。Plan 没有预设任何生产重写。

结论：满足。

### 3. Slice A / Slice B File Ownership

**Slice A allowed files**（第 222-230 行）：
- 主要：`tests/host/test_recovery_scan.py`、`tests/host/test_recovery_dispatch.py`
- 条件性：`tests/host/test_open_host_runtime.py`（仅当 public-path WAITING 测试）、`tests/host/test_recovery_orphan_classifier.py`（仅当 reason 缺口）
- 生产修复（仅 tests-first 失败时）：`dayu/host/recovery.py`、`dayu/host/recovery_process.py`、`dayu/host/durable/run_transition.py`

**Slice B allowed files**（第 286-291 行）：
- 主要：`tests/host/test_dispatch_scheduler.py`
- 条件性：`tests/host/test_open_host_runtime.py`、`tests/host/test_public_lifecycle_smoke.py`
- 生产修复（仅 tests-first 失败时）：`dayu/host/dispatch.py`、`dayu/host/open_host.py`

两 slice 无交叉 allowed production files。Slice A 的测试文件不碰 `test_dispatch_scheduler.py`，Slice B 的测试文件不碰 `test_recovery_scan.py`。file ownership 清晰且不混叠。

结论：满足。

### 4. Coverage Annotation

**Slice A matrix**（第 169-189 行）：20 行场景，每行标注 `existing coverage` / `new coverage` / `non-goal`。existing coverage 引用具体测试模块（如 `tests/host/test_recovery_scan.py`）。new coverage 标注目标测试位置。non-goal 包括 stress suite、RR-DUR-01、startup timeout reason mapping。

**Slice B matrix**（第 194-211 行）：18 行场景，同样标注。existing coverage 引用具体模块。new coverage 标注目标位置。non-goal 包括 drain-until-empty、global closed state、stress/fuzz。

所有场景均有明确覆盖标注，无遗漏。

结论：满足。

### 5. Production Code Allowed Changes 触发条件

**Slice A**（第 119-131 行）：列出 5 个 tests-first failure 条件；允许修改范围仅限 `recovery.py`、`recovery_process.py`、`run_transition.py`；禁止修改 `api.py`、durable schema、EventLog type、public opener contract。

**Slice B**（第 151-163 行）：列出 5 个 tests-first failure 条件；允许修改范围仅限 `dispatch.py`、`open_host.py`（仅 opener close boundary）；禁止修改 `api.py`、durable schema、EventLog type、public cancel command。

每个 slice 的触发条件精确、可验证，且与 stop condition 互锁。production 修改被严格约束在 failing test 指向的范围内。

结论：满足。

### 6. Stop Conditions 覆盖度

**Slice A stop conditions**（第 274-278 行）覆盖：
- recovery scanner 基于 heartbeat stale / projection / inconclusive 写 recovery/terminal facts
- reason 无法区分各类 decision
- 需要改变 durable schema / EventLog type / public Host API / state machine / WAITING 语义
- 无法构造 deterministic test

**Slice B stop conditions**（第 334-338 行）覆盖：
- close cancellation 需要改变 public close guarantee / durable terminal semantics / public cancel semantics
- close queue/promotion non-drain 无法 deterministic 构造
- 需要 durable schema / EventLog type / state machine / public API 变化
- 需要引入 lease/fencing/global registry closed state

**Contract stop conditions**（第 91-96 行）额外覆盖：
- WAITING startup recovery 语义变化
- close user-visible behavior 变化
- recovery scanner 依赖 projection / stale long read transaction
- 修复需要新抽象

Stop conditions 完整覆盖 contract / schema / state-machine / public-interface 风险。

结论：满足。

### 7. RR-DUR-01 / RR-DUR-04

**RR-DUR-01**（第 106 行）：明确"在本 work unit 关闭，不进入 scope"。Reasoning 与 code inspection artifact 一致：recovery scanner 不依赖 projection checkpoint。

**RR-DUR-04**（第 105 行、第 189 行、第 238 行）：明确"进入 proof matrix 但不预设代码改动"。Plan 要求 implementation agent 逐项证明 recovery / queue promotion / dispatch recheck / active cancel / scheduler close / worker event ingest / compaction 不使用长 read transaction 或 projection lag 作为 truth。只有直接证据显示违规才允许 fix。

RR-DUR-01 closed，RR-DUR-04 进入 proof matrix 不预设改动。与 controller adjudication DCI-04 / DCI-05 完全一致。

结论：满足。

### 8. README / Doc Sync Decision

Plan 第 339-348 行定义了清晰的 README 触发规则：
- 只新增测试与 review artifacts 且不改 public contract：不更新 README
- 生产代码修复改变稳定开发说明：检查 `dayu/host/README.md`
- 新增稳定测试入口 / marker / 命令：更新 `tests/README.md`
- 改变 public API / schema / state machine：停止并回报 controller

与 AGENTS.md 的 README 固定职责和触发规则完全一致。

结论：满足。

### 9. Code-Generation-Readiness

Implementation agent 无需重新设计即可执行的证据：

- Slice A / B 均有明确的 **Objective**、**Allowed files / modules**、**Exact changes**、**Non-goals**、**Tests / validation commands**、**Completion signal**、**Stop condition**。
- Exact changes 列出了具体要增加的测试函数和测试场景，不是模糊描述。
- Validation commands 列出了具体的 pytest 命令和 pyright 命令。
- Completion signal 列出了可验证的通过标准。
- Completion report format（第 406-451 行）提供了标准化回报模板。
- Handoff criteria（第 377-393 行）明确了 controller 派发规则和 implementation agent 行为约束。

结论：Plan 是 code-generation-ready 的。

### 10. Scope Control

Plan 的 non-goals 边界严格：
- 不修改 durable schema
- 不新增 / 修改 EventLog event type
- 不修改 Host public API
- 不修改 Run / Attempt 状态机
- 不改变 `WAITING` durable 语义
- 不让 close 写 terminal facts
- 不实现旧 Attempt takeover
- 不引入 lease / fencing / remote ownership
- 不把 close 设计成 drain-until-empty
- 不把 projection / read model / memory lag 提升为 recovery truth
- 不扩大为 stress / fuzz / soak

非目标与 controller adjudication 和 design source 完全一致。没有 scope creep。

结论：满足。

### 11. Testability

所有新增测试场景都可 deterministic 构造：
- Scanner still-live / inconclusive：使用 fake process probe / current policy
- WAITING public/read：使用 durable read 或 public reopen/read
- cancel_all snapshot：直接构造 `ActiveWorkerRegistry`
- Close queue non-empty：构造 pending dispatch queue
- Close cancellation retry：使用 deterministic barrier / monkeypatch

Plan 第 400-401 行对"worker started but not durable accepted"窗口正确标注为需要 deterministic fixture，若无法构造则停止报告。

结论：满足。

## Blocking Findings

无。

## Blocking Open Questions

无。

## Conclusion

Pass。Plan 完全对齐 design source（第 27 节 recovery / close 语义）、controller adjudication 边界和总控文档验收信号。Plan 是 code-generation-ready 的，默认 tests-first，file ownership 清晰，coverage annotation 完整，production code trigger 严格，stop conditions 覆盖 contract/schema/state-machine/public-interface 风险，RR-DUR-01 closed / RR-DUR-04 进入 proof matrix，README/doc sync 符合 AGENTS.md 固定职责。0 个 blocking finding，0 个 blocking open questions。
