# Phase 11 Host Lifecycle / Recovery Plan Review

**Reviewer**: AgentDS
**Date**: 2026-05-19
**Target**: `docs/host/phase11-host-lifecycle-recovery-plan.md`
**Against**: `docs/host/design.md` §1, §2, §10, §17, §27, §27.1; `docs/host/implementation-control.md` Phase 11
**Focus**: recovery truth, positive orphan proof, startup classification, CANCELLING orphan decision, no schema/public API assumption, pending-dispatch integration, deterministic multiprocess tests, runtime lane scope, slice readiness
**Verdict**: **PASS** — blocking count 0

## Assumptions Tested

| # | Assumption | Evidence | Result |
|---|-----------|----------|--------|
| A1 | 当前 `_REGISTER_RUNNING_SOURCE_STATUSES` 含 `STOPPING`，需收紧 | `dayu/host/durable/liveness.py:42-44` 确认含 `RUNNING` 和 `STOPPING` | 成立 |
| A2 | 当前 `process_start_token` 是可预测占位 | `dayu/host/dispatch.py:2964` 确认 `f"dispatch-{host_handle_id}"` | 成立 |
| A3 | 当前 `open_host.__aenter__` 无 recovery scan | `dayu/host/open_host.py:478` 直接 log ready，无 scan | 成立 |
| A4 | 当前 `RECOVERING` cancel 未接入 | `dayu/host/command.py:1234-1237` 确认 exclude RECOVERING；`admission.py:4179-4181` 确认 check 存在但未接线 | 成立 |
| A5 | P10.5 public contract 已冻结 | `implementation-control.md:1309` 确认；plan 明确不新增 public API | 成立 |
| A6 | Recovery truth = EventLog canonical facts + state indexes | Design §27 与 plan §"Recovery 的输入只能 Host durable truth" 一致 | 成立 |

## Findings

### 1-U-中-RunInputBuilder-canonical-fact-硬化为风险备注而非-slice-任务

- **位置**: plan Non-blocking risks §"Existing RunInputBuilder may need small typed provider hardening"
- **问题类型**: 切片过粗
- **当前写法**: Slice 3 要求 "Verify dispatch path uses RunInputBuilder to rebuild messages from canonical facts"，但 RunInputBuilder 若当前依赖 projection / memory 为最新，需要的 hardening 仅在 non-blocking risk 中提及，未作为 Slice 3 的 exact change 任务。
- **反例/失败场景**: implementation agent 执行 Slice 3 时，integration test（crash recovery → final answer）失败，agent 发现 RunInputBuilder 依赖 projection 而非纯 EventLog canonical facts。此时 agent 面临选择：修改 RunInputBuilder（需理解其内部 provider protocol，可能超出 Slice 3 allowed files），或绕过问题（让 test 先跑通 projection，但违背 recovery truth 原则）。
- **为什么有问题**: plan 自身识别出该风险，但未将其从风险降级为 slice 内 explicit task。若 hardening 涉及的文件超出 Slice 3 allowed files（如 RunInputBuilder 内部 provider），agent 需停下判断，可能被误判为 stop condition。
- **直接证据**: plan L347-L348: "Existing RunInputBuilder may need small typed provider hardening to rebuild from canonical facts when projection is lagging; it must not fall back to memory/read model truth." 但 Slice 3 exact changes 中无对应 hardening 任务，只有 "Verify dispatch path uses RunInputBuilder..."
- **影响**: 实施 Agent 可能在 Slice 3 遇到意外阻塞，或需要 Controller 裁决是否扩大 allowed files。
- **建议改法和验证点**: 在 Slice 3 exact changes 中增加一条：若 RunInputBuilder 当前不可仅从 EventLog canonical facts 重建 messages，则添加必要的 typed provider hardening，且 hardening 范围限于 RunInputBuilder / dispatch path 内部，不扩大 allowed files。或者在 Slice 3 stop condition 中明确：若 RunInputBuilder hardening 需要修改超过 allowed files，停下交 Controller。
- **修复风险**: 低
- **严重程度**: 中（非阻塞）

### 2-U-低-WAITING-恢复-adapter-observation-可选但无-fallback

- **位置**: plan Slice 2 §"ACCEPTED / QUEUED / WAITING" 分类
- **问题类型**: 契约缺失
- **当前写法**: "WAITING: keep, no Attempt creation; optional wait observation wake if existing adapter supports it."
- **反例/失败场景**: Host 重启后 WAITING Run 的 wait adapter 不支持 observation wake，Run 保持 WAITING 无限期。当前无 timeout / watchdog 将 stuck WAITING 收口为 LOST 或 FAILED。用户可见行为是 Run 永远不会完成，且没有 diagnostic。
- **为什么有问题**: plan 没有规定 WAITING recovery observation 失败或无 adapter 时的 fallback。虽然 WAITING stuck 不是 recovery 引入的新问题（Phase 7 已有 wait poller），但 startup recovery scan 应该能识别 stuck WAITING 并至少记录 diagnostic。
- **直接证据**: plan L162: "WAITING: keep, no Attempt creation; optional wait observation wake if existing adapter supports it." 与 design.md §27: "WAITING Run 保持 WAITING，等待 wait record resolution."
- **影响**: stuck WAITING Run 在多次重启后累积，无自动清理或 diagnostic。
- **建议改法和验证点**: 明确 WAITING recovery 的最小行为：若 adapter 支持则 resume observation；若 adapter 不支持或 observation wake 失败，至少记录 recovery diagnostic event（event_class=diagnostic），不推进 Run 状态。该 diagnostic 帮助运维发现 stuck WAITING，但不替代 Phase 11 后续 watchdog。
- **修复风险**: 低
- **严重程度**: 低（非阻塞，因为 WAITING stuck 是既存问题，非 recovery 引入，且 deferred 到后续 phase 的 wait lifecycle hardening）

## Architecture Boundary Review

- Recovery 模块位于 `dayu/host/recovery.py`，是 Host 内部模块，不跨层。✓
- Recovery 不调用 Engine，只通过现有 dispatch scheduler 创建 pending dispatch。✓
- Recovery 输入为 EventLog + state indexes + dispatch record + host instance liveness，不读取 projection/memory/audit/trace/outbox。✓
- `dayu/runtime/lane.py` 修改仅限 close/acquire race、stale cleanup、active count invariant，不引入 Host truth。✓
- 无反向依赖引入。✓

## Best-Practice Review

- CAS recheck 在 transition helper 内做，不在 classifier 内做，分离读判定与写保护。✓
- Positive orphan classifier 输出 typed union（PositiveOrphanProof / OwnerStillLive / OrphanProofInconclusive），不靠返回 None 或异常表达分支。✓
- Graceful shutdown 不伪造 terminal fact，不写 CANCEL_REQUESTED / RUN_CANCELLED / RUN_FAILED / RUN_LOST。✓
- Recovery dispatch count 通过 EventLog canonical fact 计数，不用内存/projection。✓
- 每个 Run 最多一次 automatic startup recovery dispatch，防止无限重试。✓

## Optimal-Solution Review

- 第一版 positive orphan proof 只用 "heartbeat stale + pid 不存在" 作为 portable 证明，pid reused mismatch 作为 optional capability。这比试图在所有平台实现完整 pid-reuse detection 更务实。✓
- Recovery dispatch 复用现有 dispatch scheduler + RunInputBuilder，不重复实现派发逻辑。✓

## Overengineering Review

- 无多余 abstraction layer、builder、wrapper、protocol 或 migration。✓
- Recovery coordinator 是单一职责 coordinator，不是 God object。✓
- 不预建 schema 字段，不预建 public API。✓

## Overcoupling Review

- Recovery 只通过 dispatch scheduler 的 pending dispatch record 与 Attempt Dispatch 耦合，这是设计意图内的一对一接口。✓
- Recovery 不直接调用 WorkerProxy，不直接启动 Engine。✓
- Lane 修改不引入 Host 依赖方向反向。✓

## Slice Readiness

| Slice | 允许文件明确 | 精确变更明确 | 验证命令明确 | 依赖顺序正确 | 就绪 |
|-------|-------------|-------------|-------------|-------------|------|
| S1: Host Instance Lifecycle | ✓ | ✓ | ✓ | 无前置 | ✓ |
| S2: Recovery Scan + CAS Closeout | ✓ | ✓ | ✓ | 依赖 S1 | ✓ |
| S3: RECOVERING Dispatch | ✓ | ✓ | ✓ | 依赖 S2 | ✓* |
| S4: Cancel + Shutdown | ✓ | ✓ | ✓ | 依赖 S3 | ✓ |
| S5: Multi-process + Lane | ✓ | ✓ | ✓ | 依赖 S1-S4 | ✓ |

*S3 就绪但有 Finding 1-U 风险备注。

## Stop Conditions 评估

Plan 定义了 9 条 stop conditions，覆盖了关键风险边界：

- Engine 修改、public API 新增、schema 变更、误用非 truth 源、误杀存活进程、Recovery 直接调 WorkerProxy、test 依赖 projection truth、多进程 live-owner-not-harmed 失败、graceful shutdown 伪造事实。

所有 stop conditions 都与 design doc 约束一致，覆盖充分。

## Open Questions

无。Plan 自身无 blocking questions for controller。

## Residual Risks

| # | 风险 | 去向 |
|---|------|------|
| R1 | RunInputBuilder canonical-fact hardening 范围可能超过 Slice 3 allowed files | Slice 3 implementation + Finding 1-U 建议的 stop condition 明确化 |
| R2 | portable pid-reuse proof 受限，部分场景只能产出 inconclusive | 已记录为 non-blocking risk，后续平台 capability 增强 |
| R3 | recovery E2E 多进程测试 timing-sensitive | plan 建议 deterministic stale heartbeat setup |
| R4 | watch 轮询性能与 watcher close 行为 | deferred to 后续 public lifecycle hardening |
| R5 | lane close/acquire race 修复影响 `dayu.runtime` | 已限定 scope，且要求 review 确认 runtime 层中立 |

## Conclusion

Plan 与 `docs/host/design.md` §1, §2, §10, §17, §27, §27.1 及 `docs/host/implementation-control.md` Phase 11 一致。Recovery truth 源、positive orphan proof 判定、startup 分类、CANCELLING orphan 决策、schema/public API 边界、pending-dispatch 集成、runtime lane scope 均正确对齐设计真源。

5 个 slice 均具备 allowed files、exact changes、validation commands，可以顺序交付。两个 finding 均非阻塞（中/低严重度），可在 implementation 中自然消化或按建议微调 slice 任务描述。

**Verdict: PASS — 0 blocking findings.**
