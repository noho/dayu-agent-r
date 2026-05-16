# Host Phase 8 Plan Review — DS — 2026-05-16

## Gate

Phase 8 plan review gate。Review target: `docs/host/phase8-projection-core-event-stream-plan.md`。

## Review Scope

Plan review only。未修改 plan、production code、tests、README、design.md、implementation-control.md，未 commit。

## Sources

- **Plan artifact**: `docs/host/phase8-projection-core-event-stream-plan.md`
- **Design truth**: `docs/host/design.md` §14 Observer / Sink / Projection, §16 Read Model / Host Event Stream / Outbox
- **Control truth**: `docs/host/implementation-control.md` Phase 8 (lines 955-1011)
- **Design discussion**: `docs/reviews/host-phase8-design-discussion-codex-20260516.md`
- **Controller adjudication**: `docs/reviews/host-phase8-design-discussion-controller-adjudication-20260516.md`
- **Code facts**: `dayu/host/durable/event_log.py` (EventLogRow, EventClass), `dayu/host/read_api.py` (_StreamRunEventsOperation), `dayu/host/durable/transaction.py` (HostTransaction, HostTransactionRunner), `dayu/host/_event_payload.py` (payload_object), `dayu/host/api.py` (HostStreamCursor, HostEventStream), `tests/host/test_import_boundary.py`, `tests/host/test_weak_typing_guard.py`

## Assumptions Tested

1. Plan 的 typed consumer contract 阻止了 Any/object/untyped payload bag 边界。
2. Projection checkpoint / RunResult / Session timeline 不会反向成为 Host governance truth。
3. `stream_run_events` 的 truth 完全来自 EventLog cursor，fanout 只是 wakeup。
4. Checkpoint advance 与 projection writes 的原子性边界被正确固定。
5. Minimal read model rebuild/repair 是生产级内部 helper，不是仅测试 fixture。
6. Slice 可独立通过 tests 和 pyright。
7. 未引入 Audit / Tool Trace / Outbox concrete sink scope creep。
8. 未修改 Engine / dayu.runtime / command path 状态机。
9. Schema 变更与既有 HOST_SCHEMA_VERSION=4 一致。
10. Consumer Protocol 与既有 HostTransactionRunner 兼容。

## Findings

### F-1-未修复-中-checkpoint 原子性 "或由实现证明" 后门

- **位置**: §5 Checkpoint / 幂等 / 失败不变量, 条目 3
- **问题类型**: 状态机漏洞
- **当前写法**:
  > Checkpoint advance 与对应 projection writes 必须处于同一 Host durable transaction，或由实现证明具备等价原子性。第一版必须复用现有 HostTransactionRunner，不引入第二套 transaction abstraction。

- **反例/失败场景**: 若 implementation agent 选择 "或" 路径（非同一 transaction），例如先写 projection 再写 checkpoint 但中间存在 crash 窗口：crash 发生在 projection committed 但 checkpoint 未 commit 时，后续 replay 从旧 checkpoint 重放，consumer 依赖 `event_id` upsert 幂等做防御。这本身可工作——但 plan 没有规定 "等价原子性" 的证明标准是什么。如果 implementation agent 以 "event_id upsert 已经幂等" 为由声称等价，而实际 crash 窗口还涉及 projection failure row 写入时序（先写 projection 成功、crash、checkpoint 未推进、replay 重复 projection write 成功、但 failure row 留在旧状态），可能产生微妙的不一致。

- **为什么有问题**: 设计真源 `docs/host/design.md:1431-1432` 要求 checkpoint 按 `event_sequence` 追平，按 `event_id` 幂等。control truth `docs/host/implementation-control.md:1001` 退出条件要求 projection lag/failure 不影响 EventLog append / Run terminal / resume / memory truth。当前写法给了 implementation agent 一个无需强证明就能绕开同事务约束的后门。

- **直接证据**: Plan §5 条目 3 原文含 "或由实现证明具备等价原子性"；design.md §14 未提及允许非事务替代方案；implementation-control.md Phase 8 未讨论多事务原子性替代方案。

- **影响**: 实施 Agent 可能选择非事务路径并以幂等为理由声称等价，导致 checkpoint/projection 在 crash 场景下出现未检测的发散。

- **建议改法和验证点**: 删除 "或由实现证明具备等价原子性"，改为 "Checkpoint advance 与对应 projection writes 必须处于同一 Host durable transaction。不得将 consumer idempotency upsert 作为事务原子性的替代。" 如未来确实需要非事务方案（例如跨进程 sink），应由后续 phase 在设计真源中先固定契约。验证点：runner 测试必须证明 checkpoint 不推进当且仅当同一 transaction 内 projection write 失败。

- **修复风险**: 低（删除一句话，无下游影响）
- **严重程度**: 中

### F-2-未修复-中-ProjectionEventFilter 多 class/type 组合语义不明确

- **位置**: §2.2 Host 内部契约, `ProjectionEventFilter` 定义
- **问题类型**: 契约缺失
- **当前写法**:
  > `ProjectionEventFilter(event_classes: tuple[EventClass, ...], event_types: tuple[str, ...] | None)`：声明 consumer 消费哪些 event class / type。`event_types=None` 表示该 class 下全部类型。

- **反例/失败场景**: 给定 `event_classes=(CANONICAL_FACT, DIAGNOSTIC)` 且 `event_types=("TOOL_RESULT_ACCEPTED",)`。实现需要决定匹配语义是：(A) `event_class IN (CANONICAL_FACT, DIAGNOSTIC) AND event_type IN ("TOOL_RESULT_ACCEPTED", ...)` — 即所有 classes 中只取匹配 types，还是 (B) `event_class=CANONICAL_FACT AND event_type IN (...)` 但 DIAGNOSTIC class 因为没有指定 types 而取全部 DIAGNOSTIC events？如果是 (A)，consumer 可能意外消费了 DIAGNOSTIC 下的 TOOL_RESULT_ACCEPTED-like type（如果存在）。如果是 (B)，语义取决于 event_types 的 None/非 None 对每个 class 的独立作用。当前定义不支持 per-class type filter。

- **为什么有问题**: 设计真源 `docs/host/design.md:1433` 要求 "Sink 必须声明消费哪些 event_class / event_type"。但 plan 的 `ProjectionEventFilter` 用一个全局 `event_types` tuple 覆盖所有 `event_classes`，无法表达 "CANONICAL_FACT 下全部类型 + DIAGNOSTIC 下特定类型" 的组合。implementation agent 必须自行决定语义，可能偏离后续 phase (Memory, Recovery, Audit) 的预期。

- **直接证据**: Plan §2.2 `ProjectionEventFilter` 字段定义；`EventClass` enum 当前有 4 个成员（CANONICAL_FACT, PREVIEW, DIAGNOSTIC, PROJECTION_SIGNAL）；design.md §14 未规定 filter 组合语义的具体规则。

- **影响**: 实施 Agent 自行决定 filter 语义，后续 phase consumer 可能依赖未被明确固定的行为，导致跨 phase 契约理解不一致。

- **建议改法和验证点**: 将 `ProjectionEventFilter` 改为 `tuple[EventClassFilter, ...]`，其中 `EventClassFilter` 是 `tuple[EventClass, tuple[str, ...] | None]`，每个元素独立表达一个 class 及其 type 过滤集。或至少明确当前单 `event_types` tuple 作用于所有 `event_classes` 的 AND 语义。验证点：runner filter 测试覆盖多 class + 特定 type 组合。

- **修复风险**: 低（类型定义调整，consumer 声明格式变化但语义更清晰）
- **严重程度**: 中

### F-3-未修复-低中-repair 事务边界与 batch replay 的表述冲突

- **位置**: §6 Minimal Rebuild / Repair 路径
- **问题类型**: 契约缺失
- **当前写法**:
  > `reset_checkpoint=True` 时，在一个 transaction 内删除 `host_run_results`、`host_session_timeline_items`、minimal read model consumer checkpoint 与 failure row，然后从 EventLog cursor 0 replay。

- **反例/失败场景**: "在一个 transaction 内删除...然后从 EventLog cursor 0 replay" 可被误读为 delete + reset + 全量 replay 都在同一个 SQLite transaction 内完成。对于已有大量 EventLog rows 的生产环境，全量 replay 可能扫描数千到数万行，在单一 write transaction 内完成会长时间持有写锁，阻塞 command path 的 EventLog append 和 Run terminal。这与 §10 残余风险自述 "Checkpoint + projection writes share one SQLite transaction, so long consumers can hold write locks" 直接矛盾。

- **为什么有问题**: Plan 自己承认长事务是风险但 §6 的 repair 表述没有明确 delete/reset 和 replay 必须使用不同 transaction。§10 的 mitigation "Phase 8 consumer must keep work small and local" 针对正常追平场景可以成立（每次只追几条新 row），但 repair 的 `reset_checkpoint=True` 场景必须从 cursor 0 全量 replay，本质上是批量操作。

- **直接证据**: Plan §6 "在一个 transaction 内删除...然后从 EventLog cursor 0 replay"；Plan §10 "Checkpoint + projection writes share one SQLite transaction, so long consumers can hold write locks."

- **影响**: 实施 Agent 可能实现为单事务全量 repair，导致生产 repair 期间 write lock 阻塞 command path。

- **建议改法和验证点**: §6 明确 repair 分两阶段：(1) 一个 transaction 内 delete projection rows + reset checkpoint + clear failure row；(2) 按 `batch_size` 分批 replay，每批在独立 transaction 内完成（projection write + checkpoint advance）。验证点：repair 测试覆盖大量 EventLog rows 时 repair 不阻塞 append 的并发场景（至少用 separate connection 模拟）。

- **修复风险**: 低（澄清表述，实现逻辑不变）
- **严重程度**: 低中

### F-4-未修复-低中-ProjectionRunner 调用生命周期未指定

- **位置**: §4.1 `dayu/host/projection.py` + §4.1 `dayu/host/command.py` + §4.1 `dayu/host/dispatch.py`
- **问题类型**: 契约缺失
- **当前写法**: Plan 多处提及 runner 但不指定启动/停止/连接获取方式：
  - §4.1 command.py: "仅允许把 projection runner / repair helper 装配到 handle 的 private dependency 上；不得让 command path 同步运行 projection。"
  - §4.1 dispatch.py: "仅允许 after-commit wakeup 调用 projection runner 的 wakeup port；不得在 dispatch / terminal transaction 内执行 projection。"
  - P8-S1 非目标: "Do not wire runner into background supervisor unless a later slice explicitly uses it."

- **反例/失败场景**: P8-S1 创建了完整的 ProjectionRunner，但不 wire 到任何调用路径。P8-S2 不必然调用 runner（focus 是 event stream cursor）。P8-S3 需要 runner 来消费 EventLog 并写入 read model，但 P8-S3 允许文件不包含 `command.py` 和 `dispatch.py`（除非 P8-S2 已修改它们用于 fanout wiring）。如果 P8-S3 不修改 `dispatch.py` 或 `command.py`，minimal read model consumer 没有触发路径，只能通过 `repair_minimal_read_models` 手动触发。

- **为什么有问题**: Phase 8 的 read model consumer 需要在每次 EventLog append 后被触发才能保持新鲜。如果 runner 没有被任何代码路径触发，则 read model 永远为空（除非手动 repair），success signal "Minimal RunResult 能从 terminal canonical facts 重建" 只能通过 repair 证明而非自动投影证明。Phase 9 Memory 需要一个实际在运行的 projection runner 才能复用 consumer/checkpoint framework。

- **直接证据**: Plan P8-S1 非目标 "Do not wire runner into background supervisor"；P8-S3 允许文件不含 `command.py` / `dispatch.py`；P8-S3 测试描述均为直接 replay 场景，不测试 after-commit 自动触发。

- **影响**: Read model 不能自动保持新鲜。Phase 9 Memory owner 需要额外工作来发现 runner 没有被触发。

- **建议改法和验证点**: P8-S3 明确增加一个 slice 内步骤：在 `dispatch.py` after-commit 路径中增加对 projection runner 的 wakeup 调用（如果 P8-S2 未完成）。或者明确文档化：Phase 8 read model 的自动追平由 Phase 9 Memory owner 完成，Phase 8 只提供 runner + repair primitive，接受 read model 可能 stale 的中间状态。后者与 `docs/host/implementation-control.md:1007` 退出条件 "Memory phase 可以复用 checkpoint / consumer framework" 兼容。验证点：若选择延迟 wiring，必须在 implementation report 中显式记录该 deferred item 并指派 Phase 9 owner。

- **修复风险**: 低（澄清责任边界即可）
- **严重程度**: 低中

### F-5-未修复-低-P8-S2 fanout 测试假设与可选实现冲突

- **位置**: P8-S2 测试列表
- **问题类型**: 契约缺失
- **当前写法**: P8-S2 测试包含 "fanout wakeup missing or disabled does not affect cursor replay"，但 P8-S2 允许变更中写 "If adding a fanout / wakeup abstraction, keep it internal and non-truth"。fanout 实现是可选 ("if")。

- **反例/失败场景**: 若 implementation agent 选择不实现 fanout（合理选择），则没有 fanout 代码。测试 "fanout wakeup missing or disabled does not affect cursor replay" 实际上是在测试 `stream_run_events` 的独立性——即使没有 fanout 也能正常工作。这个测试是有效的（它验证 fanout 缺失时 stream 仍正确），但测试名称暗示有 fanout 模块需要被 disable。如果根本没有 fanout 模块，测试应该改为 "stream_run_events correctness does not depend on any fanout or notification path"。

- **为什么有问题**: 轻微。测试意图正确（证明 stream 独立于 fanout），但测试名称假设了 fanout 模块存在。如果 implementation agent 严格按字面意思创建 fanout 模块然后 disable 它来测试，会产生不必要的 dead code。

- **直接证据**: P8-S2 "If adding a fanout / wakeup abstraction" vs test "fanout wakeup missing or disabled does not affect cursor replay"。

- **影响**: 实施 Agent 可能创建不必要的空 fanout shell 以满足测试名称期望。

- **建议改法和验证点**: 将测试名称改为 "stream_run_events correctness does not depend on projection or notification side effects"，测试内容不变（验证 stream 只读 EventLog）。不强制创建 fanout 模块。

- **修复风险**: 低（纯测试命名澄清）
- **严重程度**: 低

## Specified Blocking Criteria Check

按用户指定审查标准逐项判定：

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Consumer boundary 使用 Any/object/untyped payload bag | **PASS** | Plan §2.2 显式 typed contract；§12 将 Any/object 列为 blocking |
| 2 | Projection 反向依赖 Host governance truth | **PASS** | Plan §5.10 禁止 import command transition/admission/recovery；§1.5 明确不修改 command path 状态机 |
| 3 | Stream fanout 作为 correctness path | **PASS** | Plan §2.4 明确 fanout non-truth；§12 将 fanout-as-truth 列为 blocking |
| 4 | Checkpoint advance 在 projection commit 之前 | **PASS with F-1** | Plan §5.3 要求同事务，但 "或由实现证明" 后门需要关闭 |
| 5 | 缺少 rebuild/repair 路径 | **PASS** | Plan §6 提供 `repair_minimal_read_models` 生产级 internal helper，非仅测试 fixture |
| 6 | Audit/Tool Trace/Outbox scope creep | **PASS** | Plan §1.5 明确排除；§4.3 禁止相关模块；§12 将 scope creep 列为 blocking |
| 7 | 修改 Engine | **PASS** | Plan §1.5 明确不修改 Engine；§4.3 禁止 `dayu/engine/**` |
| 8 | Slice 不能独立通过 tests 和 pyright | **PASS** | 每个 slice 有独立测试文件和验证命令。P8-S1 创建新模块和测试；P8-S2 依赖 P8-S1 的模块结构但不依赖 P8-S1 的测试；P8-S3 依赖 P8-S1 模块结构 |

## Open Questions

1. **Q1**: `event_log` 表的 `event_sequence` 列是否有 UNIQUE 约束？Plan §3.3/§3.4 的 FOREIGN KEY 引用 `event_log(event_sequence)` 需要该列有 UNIQUE 约束。若当前 schema 未定义，需在 Phase 8 schema bump 时添加。建议 implementation agent 在 P8-S1 开始前验证。

2. **Q2**: `USER_INPUT_ACCEPTED` event type 的 `display_text` 是否已由 `engine_ingest.py` 写入 EventLog payload？Plan §2.5/§3.4 的 timeline `display_text` 提取依赖该字段存在。建议 implementation agent 在 P8-S3 开始前从 EventLog schema 和 engine_ingest 代码确认。

3. **Q3**: `repair_minimal_read_models` 的 `host: HostCommandHandle` 参数——`HostCommandHandle` 是 Host 内部 concrete type。Repair 需要访问其 `_run_write` 或 transaction runner private interface。Plan 未说明 repair 如何获取 transaction runner。Implementation agent 需在设计时解决。

## Residual Risks

| Risk | Severity | Owner | Tracking |
|------|----------|-------|----------|
| Generic runner 随时间退化为 untyped event bus | 中 | Phase 13/15 owner | Plan §10 已标记；weak typing guard 测试作为持续防护 |
| Stream fanout 意外成为 hidden truth | 中 | Phase 8 implementation review | P8-S2 测试必须证明 `stream_run_events` 忽略 fanout 状态 |
| 长事务阻塞 write lock | 低中 | Phase 8 implementation | F-3 修复后缓解；Phase 13 heavy sinks 有独立 risk |
| Read model 自动追平未 wiring 到 after-commit | 低中 | Phase 9 Memory owner | F-4 如选择延迟 wiring，需显式 handoff |
| `RUN_LOST` event type 在第一版 EventLog 中可能尚不存在 | 低 | Phase 8 implementation | P8-S3 consumer 必须处理 unknown event type 为 SKIPPED |

## Verdict

**PASS** — 有 5 个 findings，无严重或高严重度项。

F-1（checkpoint 原子性后门）是唯一实质性风险，但修复只需删除一句话，不影响 plan 结构。F-2（filter 语义）建议类型重构但当前表述对第一版两个 consumer（RunResult: only CANONICAL_FACT terminal types; Timeline: CANONICAL_FACT + diagnostic summary）足够明确。F-3/F-4/F-5 均为低或低中严重度，可通过表述澄清或 implementation 阶段决策解决。

Plan 在所有 8 个用户指定 blocking criteria 上通过。Plan 满足 design.md §14/§16 和 implementation-control.md Phase 8 的约束，slice 边界清晰，non-goals 明确，停止条件可执行。

建议 plan review 后进入的下一 gate：accepted plan，可进入 P8-S1 implementation。
