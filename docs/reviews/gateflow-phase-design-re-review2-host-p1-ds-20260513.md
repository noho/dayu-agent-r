# Host Phase 1 Design Re-Review Round 2 (User Feedback Fix Round 2)

## Review Gate

phase design re-review after user feedback round 2

## Reviewer

AgentDS

## Reviewed Target

- Fix artifact: `docs/reviews/gateflow-phase-design-user-feedback-fix2-host-p1-codex-20260513.md`
- Updated docs: `dayu/README.md`, `docs/host/design.md`, `docs/host/implementation-control.md`

## Prior User Feedback

1. lane 必须跨进程；重排 phase，把现有 P12 后移，P12 专门给 ToolsDiscovery / ScenePrepare。

## Re-review Rules

只 re-review round2 fixes，不重新审查已通过 round1 的内容，不检查未修改文件。

---

## Per-item Re-review Result

### Item 1: Lane 从 process-local 改为 cross-process named semaphore / capacity guard

**Result: PASS**

Evidence:
- `dayu/README.md` 术语约定 §lane (line 121)：明确为 "cross-process named semaphore / capacity guard，用于单机多客户端 / 多进程下的具名容量治理"。
- `dayu/README.md` Runtime 节 (line 143)：明确 "它只表达单机多进程的具名资源容量控制，可被 Host、Service、Fins 或其它层复用"。
- `docs/host/design.md` §3 (line 67)：明确为 "层中立 cross-process named semaphore / capacity guard，用于单机多客户端 / 多进程"。
- `docs/host/design.md` §3.1 (line 78)：明确为 "层中立、cross-process 的 async named semaphore / capacity guard primitive"。
- `docs/host/implementation-control.md` Phase 1 关键设计问题 (line 315)：明确 "第一版是 cross-process named semaphore / capacity guard primitive，使用独立 runtime SQLite lane coordinator 表达跨进程 capacity claim"。

全部三份文档对 lane 的 cross-process 定位一致，且与 `dayu/README.md` 项目目标"支持单机多客户端 / 多进程"对齐。旧表述 "process-local"、"不提供跨进程" 已全部清除。

### Item 2: Cross-process lane 保持 runtime capacity boundary

**Result: PASS**

Evidence:
- `docs/host/design.md` §3.1 全程明确 lane token / claim 不是 Host truth：
  - line 155: "token id 只标识 runtime capacity claim，不得传入 Host EventLog 作为 canonical identity"。
  - line 172-173: "stale cleanup 只释放 runtime capacity，不能证明 Host Attempt orphan，不能驱动 Host recovery，不能写 EventLog"。
  - line 174: "heartbeat / TTL 不是 lease / fencing。即使某个 expired claim 被清理，也不授权旧 worker takeover"。
  - line 181: "lane token 不是 Host truth、不是 lease、不是 fencing token、不是 Attempt owner、不是 dispatch record 状态"。
  - line 182: "acquire 成功只表示当前 owner 在 runtime coordinator 中拿到资源容量；执行任何副作用前，Host 后续 dispatch phase 仍必须在短事务内 recheck durable precondition"。
- `dayu/README.md` line 143 完整保留 "它不能表达 Session / Run / Attempt owner，也不能替代 Host admission、SQLite transaction、CAS 状态迁移、lease / fencing、Attempt takeover、EventLog ordering 或 recovery proof"。
- `docs/host/implementation-control.md` 强制约束 (line 200) 保留 "lane 只能表达资源容量，不能替代 admission、事务、CAS 或 EventLog ordering"。

Cross-process 实现升级未导致 lane 语义越界为 Host truth。所有原本的 non-goals 边界完整保留。

### Item 3: SQLite runtime lane coordinator 设计与实施可行性

**Result: PASS**

Evidence:
- 独立 runtime DB：`docs/host/design.md` §3.1 line 80-84 明确使用独立 runtime SQLite 文件，不是 Host durable store；不复用 Host EventLog / state index 数据库；不被 Host recovery 当作 truth。
- 显式注入路径：line 145-146 要求 `LaneController.open(...)` 显式接收 `SQLiteLaneCoordinatorConfig`；`db_path` 不得默认为 Host durable store 路径，不得从 Host package 读取配置，不得通过模块级全局 singleton 隐式创建。
- 短事务 claim/release/stale cleanup：line 153 明确 acquire 在短事务内先清理 stale claims 再 insert；line 156 明确 release 在短事务内按 `(lane_name, claim_id, owner_id)` 删除。
- 不复用 Host durable store：line 147 明确 coordinator schema 只保存 lane capacity coordination rows，不得保存 Session / Run / Attempt / EventLog / Tool / 财报业务字段。
- Public API shape 完整覆盖 line 91-138：`LaneConfig`、`LaneOwner`、`SQLiteLaneCoordinatorConfig`、`LaneClaimToken`、`LaneAcquired`、`LaneAcquireCancelled`、`LaneAcquireTimedOut`、`LaneAcquireOutcome`、`LaneController`，以及 acquire/release/heartbeat/cancel/timeout/close 全生命周期。
- Import boundary 明确 line 192：只能依赖标准库（含 `sqlite3`）、CancellationToken 和同包层中立 helper。

实施层面唯一需要在 Phase 1 implementation plan 中细化的是：heartbeat task ownership 实现方式（`LaneController` 管理 vs token context helper 驱动，line 157 允许两种选择）、SQLite schema DDL 具体列定义、busy timeout 测试策略。这些属于 plan 阶段应解决的细节，不构成 design 层面 blocker。

### Item 4: Phase Map 重排

**Result: PASS**

Evidence:
- `docs/host/implementation-control.md` Phase Map 已按用户裁决重排：
  - Phase 12: ToolsDiscovery / ScenePrepare (line 934-998)
  - Phase 13: Audit / Tool Trace / Outbox Projections (line 1000-1056)
  - Phase 14: RemoteProxy / RemoteStub (line 1058-1114)
  - Phase 15: Retention / Purge / Production Hardening (line 1116-1175)
- Phase 12 内容已重新专门写 ToolsDiscovery / ScenePrepare scope：目标 (line 937)、non-goals (line 961)、验证要求 (line 986-991)、退出条件 (line 992-995) 均与工具发现/场景装配边界一致，不混入 projection scope。
- Phase 12 non-goals 明确 "不实现 Audit / Tool Trace / Outbox projection；该能力在 Phase 13"。

跨文档引用一致性检查：
- Phase 4 non-goals line 497: `purge_session` destructive cleanup 指向 Phase 15 — 正确（Phase 15 为 Retention/Purge）。
- Phase 1 Deferred Slice line 332: ToolsDiscovery / ScenePrepare 标记 deferred destination 为 P12，projections 后移至 Phase 13 — 正确。
- Phase 4 后续依赖 line 527: `purge_session` destructive cleanup 指向 Phase 15 — 正确。
- Phase 11 recovery 前置条件 line 1129: Phase 13 Audit/Tool Trace/Outbox、Phase 14 remote 已完成 — 正确的依赖链。

### Item 5: 旧表述残留检查

**Result: PASS**

Residual text scan 结果（已通过直接 grep 验证）：

| 搜索模式 | `dayu/README.md` | `docs/host/design.md` | `docs/host/implementation-control.md` |
|---|---|---|---|
| `process-local` | 无匹配 | 无匹配 | 无匹配 |
| `不提供跨进程` | 无匹配 | 无匹配 | 无匹配 |
| `跨进程全局容量` | 无匹配 | 无匹配 | 无匹配 |
| `Phase 12.*Audit` | 无匹配 | 无匹配 | 无匹配 |
| `Phase 13.*RemoteProxy` | 无匹配 | 无匹配 | 无匹配 |
| `Phase 14.*Retention` | 无匹配 | 无匹配 | 无匹配 |

全部三个文件已无旧术语、旧 Phase 编号残留。各文档中对 Phase 12/13/14/15 的引用均指向重排后的正确 phase。

---

## New Blockers

0.

## Open Questions / Residual Risk

1. **Heartbeat task ownership** (`docs/host/design.md` line 157)：设计允许两种实现方式（Controller 管理 heartbeat task 或 token context helper 驱动）。Phase 1 handoff implementation plan 必须选择其一并保持一致性。这不是设计缺陷，是可接受的 implementation 阶段决策。

2. **SQLite busy timeout 测试覆盖** (`docs/host/design.md` line 149)：`busy_timeout_seconds` 语义已定义为只限制 runtime coordinator SQLite busy 等待。Phase 1 plan 需要覆盖 concurrent acquire 竞争时的 busy timeout 测试用例，确认超时不破坏 capacity invariant。

3. **Clock monotonic-to-wall 策略** (`docs/host/design.md` line 175)：设计明确跨进程 clock skew 只能影响 resource capacity availability，不能影响 Host truth。Phase 1 plan 需要在 TTL 过期测试中显式覆盖 clock skew scenario 并验证 capacity eventual consistency。

4. **默认路径注入** (`docs/host/design.md` line 145-146)：`db_path` 要求显式注入，不默认为 Host durable store 路径。Phase 1 plan 需约定 workspace runtime 目录结构和默认路径命名建议（如 `runtime_lanes.sqlite3`），并确保 cleanup 策略（谁负责删除 lane DB 文件）有文档说明。

以上均为可接受的 design-level residual risk，属于 Phase 1 implementation plan 或后续 phase 的细化范围，不阻塞当前 gate 进入 Phase 1 plan。

## Artifact Path

`docs/reviews/gateflow-phase-design-re-review2-host-p1-ds-20260513.md`
