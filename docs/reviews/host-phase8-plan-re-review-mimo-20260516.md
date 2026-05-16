# Host Phase 8 Plan Re-review — MiMo — 2026-05-16

## Gate

当前 gate：Phase 8 plan re-review after accepted plan fix。

Review target：`docs/host/phase8-projection-core-event-stream-plan.md`

Fix artifact：`docs/reviews/host-phase8-plan-fix-codex-20260516.md`

Controller adjudication：`docs/reviews/host-phase8-plan-review-controller-adjudication-20260516.md`

原始 review artifacts：

- `docs/reviews/host-phase8-plan-review-mimo-20260516.md`
- `docs/reviews/host-phase8-plan-review-ds-20260516.md`

## Re-review Scope

验证 P8-PLAN-F1 至 P8-PLAN-F7 是否已在 plan 中正确修复，且 fix 未引入新 scope creep 或 implementation blocker。

## Verification: P8-PLAN-F1 至 P8-PLAN-F7

### P8-PLAN-F1: Checkpoint advance must be same transaction, no equivalence escape hatch

- **来源**: DS F-1, MiMo P8-PR-003
- **裁决**: accepted
- **验证**: Plan §5 条目 3 当前写法为 "Checkpoint advance 与对应 projection writes 必须处于同一个 `HostTransactionRunner.run_write()` 管理的 Host durable transaction。第一版禁止用"等价原子性"替代同事务提交，禁止引入第二套 transaction abstraction。"
- **证据**: 原 plan 含 "或由实现证明具备等价原子性" 逃生路径。当前版本该文字已删除，替换为明确的同事务约束和禁止声明。§1.4 成功信号也已同步更新为 "Projection checkpoint advance 与对应 projection writes 必须在同一个 `HostTransactionRunner` 管理的 Host durable transaction 内提交；consumer 幂等 upsert 只能作为 replay 防御，不能替代事务原子性。"
- **结论**: **FIXED**。逃生路径已关闭，约束明确。

### P8-PLAN-F2: ProjectionEventFilter must define per-class type semantics

- **来源**: DS F-2
- **裁决**: accepted
- **验证**: Plan §2.2 当前定义了 `ProjectionEventClassFilter(event_class: EventClass, event_types: tuple[str, ...] | None)` 和 `ProjectionEventFilter(class_filters: tuple[ProjectionEventClassFilter, ...])`。明确写了 "每个 event class 独立决定消费全部类型或指定类型，不存在跨 class 共享的全局 `event_types`"，并补充了匹配语义："各 class filter 之间 OR、单个 class filter 内 `event_class` 与 `event_type` AND"。
- **证据**: 原 plan 使用单一 `event_types` 覆盖所有 `event_classes`，无法表达 per-class 差异。当前版本通过 `ProjectionEventClassFilter` + `ProjectionEventFilter(class_filters)` 固定了 per-class 语义。P8-S1 测试要求也已更新："Runner filter test: per-class filters handle multi-class + type combinations without applying one class's `event_types` to another class。"
- **结论**: **FIXED**。Per-class filter 语义已明确，测试要求已覆盖。

### P8-PLAN-F3: RunResult terminal conflict handling must be explicit

- **来源**: MiMo P8-PR-002
- **裁决**: accepted
- **验证**: Plan §3.3 幂等段落当前写法为：consumer 必须先按 `run_id` 读取既有 row；若 row 不存在，插入新的 terminal row；若 row 存在且 `terminal_event_id` 与 `terminal_event_sequence` 均匹配当前 terminal event，返回 duplicate / no-op；若 row 存在但 `terminal_event_id` 或 `terminal_event_sequence` 与当前 terminal event 不同，必须 raise projection error，记录 projection failure，且 checkpoint 不推进。明确禁止 `INSERT OR REPLACE` 和 `ON CONFLICT(run_id) DO UPDATE`。
- **证据**: 原 plan 只说 "Different terminal event for same `run_id` indicates invariant violation"，未指定具体 consumer 行为。当前版本给出了完整的 SELECT-then-INSERT/ERROR 逻辑。P8-S3 测试也已更新："RunResult conflict test must prove no `INSERT OR REPLACE` or silent `ON CONFLICT(run_id) DO UPDATE` overwrite occurs when terminal identity differs。"
- **结论**: **FIXED**。RunResult 冲突处理逻辑已完全明确。

### P8-PLAN-F4: Repair reset and replay must be two-phase, batch-safe

- **来源**: MiMo P8-PR-003, DS F-3
- **裁决**: accepted
- **验证**: Plan §6 当前写法明确为两阶段：第一阶段 "只用一个短 `HostTransactionRunner.run_write()` transaction 删除 `host_run_results`、`host_session_timeline_items`、minimal read model consumer checkpoint 与 failure row；该 transaction 提交后，第二阶段从 cursor 0 replay。" 第二阶段 "必须按 `batch_size` 分批执行，每批使用独立 `HostTransactionRunner.run_write()` transaction，并在同一批 transaction 内写 projection rows 与推进 checkpoint。" 中途失败后 "已提交批次的 checkpoint 必须保留在最后成功 cursor；下一次 repair 从 checkpoint 继续，不得要求重新执行全量 reset，也不得把全量 replay 放进单个长 write transaction。"
- **证据**: 原 plan 的 "在一个 transaction 内删除...然后从 EventLog cursor 0 replay" 表述与 `batch_size` 参数语义冲突。当前版本消除了歧义，修复两阶段和每批独立事务的语义。P8-S3 测试也已更新："Repair batch test: `reset_checkpoint=True` performs a short reset transaction, then replays in multiple `batch_size` transactions; if a later batch fails, the next repair resumes from the last committed checkpoint。"
- **结论**: **FIXED**。Repair 事务边界与 batch replay 语义已明确且一致。

### P8-PLAN-F5: ProjectionRunner transaction injection and lifecycle must be specified

- **来源**: MiMo P8-PR-001, DS F-4 / Q3
- **裁决**: accepted
- **验证**: Plan §2.2 当前写法为 "`ProjectionRunner`：构造时必须接收现有 `HostTransactionRunner` 和 concrete consumers，由 `HostCommandHandle` 或后续 composition root 通过 private dependency 注入；不得自建 SQLite connection，不得持有或调用 public command facade。" 同时明确了生命周期策略："Phase 8 不强制接入 after-commit wakeup，也不要求 command / dispatch path 自动追平 read model。自动追平 owner 明确 deferred 给 Phase 9 Conversation Memory composition。"
- **证据**: 原 plan 未指定 `ProjectionRunner` 如何获取事务能力，也未明确自动追平策略。当前版本通过 constructor injection 固定了事务获取方式，并通过 deferred owner 声明明确了生命周期边界。P8-S1 测试要求也已更新："Construct `ProjectionRunner` with an injected `HostTransactionRunner`; runner must not open its own SQLite connection and must not depend on `HostCommandHandle` public command methods。"
- **结论**: **FIXED**。事务注入模式和自动追平策略已明确。

### P8-PLAN-F6: Fanout / wakeup scope and tests must not force dead code

- **来源**: MiMo P8-PR-004, DS F-5
- **裁决**: accepted
- **验证**: Plan §2.4 当前写法为 "Phase 8 的 fanout / wakeup 只允许作为可选 non-truth optimization；本计划不要求创建 fanout shell，也不把 wakeup 作为 Phase 8 correctness 或成功信号。" P8-S2 允许变更中删除了要求 fanout 实现的措辞，改为 "Do not add fanout / wakeup implementation in P8-S2. This slice only proves `stream_run_events` correctness is independent from projection, notification and read model side effects." P8-S2 非目标新增 "Do not create placeholder fanout modules or disabled notification shells just to satisfy tests." 测试已改为 "stream_run_events correctness does not depend on projection or notification side effects。"
- **证据**: 原 plan 的 "If adding a fanout / wakeup abstraction" 和测试名 "fanout wakeup missing or disabled does not affect cursor replay" 暗示 fanout 模块存在。当前版本消除了该暗示，fanout 明确为可选，测试命名不再预设 fanout 模块。
- **结论**: **FIXED**。Fanout / wakeup 范围和测试命名已修正。

### P8-PLAN-F7: Schema assumptions need implementation stop checks

- **来源**: DS Q1 / Q2
- **裁决**: accepted as explicit stop/check requirement
- **验证**: Plan §3 新增了两个 stop check：
  1. P8-S1 schema stop check："implementation agent 必须先确认 `event_log(event_sequence)` 是否满足 SQLite foreign key parent key 要求，也就是该列是 PRIMARY KEY 或受 UNIQUE 约束保护。若不满足，必须在 Phase 8 schema bump 内补齐唯一约束 / 唯一索引，或改用符合 SQLite FK 规则且仍保留 `event_sequence` 查询索引的 schema 方案，并新增 durable schema 测试覆盖 FK 可创建、可校验和无效引用会失败；不得留下无效 FK DDL。"
  2. P8-S3 payload stop check："implementation agent 必须确认 `USER_INPUT_ACCEPTED` 的 typed payload 是否包含 `display_text` 字段。若不存在，timeline consumer 不得从 raw payload、JSON 字符串或其它展示字段拼接文本；应保留 `payload_ref` / `payload_digest`，并将 nullable `display_text` 写为 NULL，同时用测试覆盖该行为。"
- **代码验证**: `event_log(event_sequence)` 定义为 `INTEGER PRIMARY KEY AUTOINCREMENT`（`schema.py:121`），PRIMARY KEY 隐含 UNIQUE，满足 FK parent key 要求。`USER_INPUT_ACCEPTED` payload 包含 `display_text` 字段（`admission.py:1906`）。两个 stop check 在当前代码库下均能通过，但作为安全网仍然有价值。
- **结论**: **FIXED**。两个 stop check 已明确写入 plan，且与当前代码事实一致。

## New Findings Check

### Scope Creep 检查

Plan fix 只修改了 plan artifact 并新增 fix artifact。未修改 production code、tests、README、design.md 或 implementation-control.md。Plan 的非目标（§1.5）、禁止修改文件（§4.3）、slice 边界（§7）均未扩展。

### 新 Implementation Blocker 检查

- §2.2 的 `ProjectionRunner` constructor injection 模式与现有 `dispatch.py` 持有 `HostTransactionRunner` 的模式一致（`command.py:160-166`），不引入新 blocker。
- §6 的两阶段 repair 语义清晰，不与 `batch_size` 参数冲突。
- §2.2 的 `ProjectionEventFilter` per-class 语义虽然比原单一 tuple 更复杂，但类型定义简单，不引入实施 blocker。
- §3.3 的 RunResult SELECT-then-INSERT 逻辑是标准 pattern，不引入实施 blocker。
- Phase 9 auto-catchup deferred 是明确的 owner 分配，不是 plan 缺口。

### Code Fact 一致性检查

- `HOST_SCHEMA_VERSION` 当前为 4（`schema.py:24`），plan 要求 bump 到 5 → 一致。
- `event_log(event_sequence)` 为 `INTEGER PRIMARY KEY AUTOINCREMENT`（`schema.py:121`）→ 满足 FK parent key 要求，P8-S1 stop check 为安全网。
- `EventLogRow` 包含 plan 声明的所有字段 → 一致。
- `payload_object()` 存在（`_event_payload.py:359-373`）→ 一致。
- `USER_INPUT_ACCEPTED` payload 包含 `display_text`（`admission.py:1906`）→ P8-S3 stop check 为安全网。
- `HostTransactionRunner.run_write()` 提供事务能力（`transaction.py:213-265`）→ 一致。

## Residual Risks

Plan §10 已识别的残余风险未因 fix 而变化：

1. **Generic runner drift toward untyped event bus**: 由 §12 blocking criteria 和 weak typing guard 测试控制。风险等级：低。
2. **Long consumer holding write lock**: Phase 8 minimal read model consumer 工作量小；repair 已改为两阶段 batch 模式。重负载 sinks 后置到 Phase 13。风险等级：低。
3. **Stream fanout hidden truth**: 由 P8-S2 测试控制，fanout 已明确为可选 non-truth。风险等级：低。
4. **Repair helper only in tests**: P8-S3 要求 production internal helper。风险等级：低。
5. **Schema version skew**: Plan §3 要求 fresh schema bump 到 5，且有 stop check。风险等级：低。
6. **Automatic after-commit projection catch-up deferred**: Phase 9 owner 明确。Phase 8 交付可复用 runner / repair primitive。风险等级：低。

## Verdict

**PASS**。

P8-PLAN-F1 至 P8-PLAN-F7 全部已修复，证据充分：

| Finding | Status | Evidence |
|---------|--------|----------|
| F1: checkpoint atomicity | FIXED | §5 条目 3 逃生路径已删除，同事务约束明确 |
| F2: per-class filter | FIXED | §2.2 `ProjectionEventClassFilter` + per-class 语义已固定 |
| F3: RunResult conflict | FIXED | §3.3 SELECT-then-INSERT/ERROR 逻辑已明确，禁止 INSERT OR REPLACE |
| F4: repair two-phase | FIXED | §6 两阶段 + 每批独立事务语义已明确 |
| F5: runner injection | FIXED | §2.2 constructor injection + Phase 9 deferred owner 已明确 |
| F6: fanout optional | FIXED | §2.4 fanout 可选 + P8-S2 测试命名已修正 |
| F7: stop checks | FIXED | §3 P8-S1 schema stop check + P8-S3 payload stop check 已新增 |

Fix 未引入新 scope creep、新 implementation blocker 或新架构风险。Plan 的 slice 边界、non-goals、禁止修改文件列表均保持不变。Plan 满足 design.md §14/§16 和 implementation-control.md Phase 8 的约束，可进入 implementation。
