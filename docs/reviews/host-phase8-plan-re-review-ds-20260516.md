# Host Phase 8 Plan Re-Review — DS — 2026-05-16

## Gate

当前 gate：Phase 8 plan re-review after accepted plan fix。

Review target：`docs/host/phase8-projection-core-event-stream-plan.md`

Fix artifact：`docs/reviews/host-phase8-plan-fix-codex-20260516.md`

Controller adjudication：`docs/reviews/host-phase8-plan-review-controller-adjudication-20260516.md`

Original reviews：`docs/reviews/host-phase8-plan-review-mimo-20260516.md`、`docs/reviews/host-phase8-plan-review-ds-20260516.md`

## Review Scope

Re-review only。验证 P8-PLAN-F1 至 P8-PLAN-F7 均已修复，无新 scope creep 或 implementation blocker 引入。不修改 plan、code、tests、README、design.md、implementation-control.md，不 commit。

## Finding 修复逐项验证

### P8-PLAN-F1: Checkpoint advance 必须同事务，删除等价原子性后门 → FIXED

- **来源**: DS F-1 / MiMo P8-PR-003 相关
- **修复要求**: 删除"或由实现证明具备等价原子性"，明确第一版 checkpoint advance 与 projection writes 必须在同一 `HostTransactionRunner` 事务内
- **当前 plan 证据**:
  - §5 条目 3：`Checkpoint advance 与对应 projection writes 必须处于同一个 HostTransactionRunner.run_write() 管理的 Host durable transaction。第一版禁止用"等价原子性"替代同事务提交，禁止引入第二套 transaction abstraction。`
  - §1.4 成功信号：`Projection checkpoint advance 与对应 projection writes 必须在同一个 HostTransactionRunner 管理的 Host durable transaction 内提交；consumer 幂等 upsert 只能防御 replay，不能替代事务原子性。`
  - 全文搜索"等价原子性"仅出现在禁止语句中，无逃生路径残留
- **结论**: FIXED

### P8-PLAN-F2: ProjectionEventFilter 必须定义 per-class type 语义 → FIXED

- **来源**: DS F-2
- **修复要求**: 将全局 `event_types` 改为 `ProjectionEventClassFilter(event_class, event_types)` + `ProjectionEventFilter(class_filters)`，每个 event class 独立声明消费范围
- **当前 plan 证据**:
  - §2.2：新增 `ProjectionEventClassFilter(event_class: EventClass, event_types: tuple[str, ...] | None)` 和 `ProjectionEventFilter(class_filters: tuple[ProjectionEventClassFilter, ...])`，语义明确为"各 class filter 之间 OR、单个 class filter 内 event_class 与 event_type AND。每个 event class 独立决定消费全部类型或指定类型，不存在跨 class 共享的全局 event_types。"
  - P8-S1 允许变更：`Add ProjectionEventClassFilter、ProjectionEventFilter、ProjectionConsumer typed Protocol and ProjectionRunner.`
  - P8-S1 tests：`per-class filters handle multi-class + type combinations without applying one class's event_types to another class.`
- **结论**: FIXED

### P8-PLAN-F3: RunResult terminal conflict 处理必须显式化 → FIXED

- **来源**: MiMo P8-PR-002
- **修复要求**: consumer 先 SELECT by run_id；不存在 INSERT；存在且 terminal_event_id 匹配 DUPLICATE；存在但不同 raise projection error 且 checkpoint 不推进；禁止 INSERT OR REPLACE 和静默 ON CONFLICT DO UPDATE
- **当前 plan 证据**:
  - §3.3 幂等段：完整的 consumer 逻辑——先按 `run_id` 读取既有 row；不存在时 INSERT；存在且 `terminal_event_id` 与 `terminal_event_sequence` 均匹配时 DUPLICATE；存在但不同时 raise projection error 且 checkpoint 不推进
  - §3.3：`禁止使用 INSERT OR REPLACE，也禁止使用会静默覆盖 terminal_event_id / terminal_event_sequence 的 ON CONFLICT(run_id) DO UPDATE。`
  - P8-S3 tests：`RunResult conflict test must prove no INSERT OR REPLACE or silent ON CONFLICT(run_id) DO UPDATE overwrite occurs when terminal identity differs.`
  - 全文搜索"INSERT OR REPLACE"和"ON CONFLICT"仅出现在禁止语句中
- **结论**: FIXED

### P8-PLAN-F4: Repair reset 与 replay 必须两阶段、batch-safe → FIXED

- **来源**: MiMo P8-PR-003 / DS F-3
- **修复要求**: reset_checkpoint=True 时分两阶段——第一阶段短事务删除 projection rows + checkpoint + failure row；第二阶段按 batch_size 分批 replay，每批独立 transaction 推进 checkpoint；中途失败从最后成功 checkpoint 继续
- **当前 plan 证据**:
  - §6：`reset_checkpoint=True 时，repair 必须两阶段执行：第一阶段只用一个短 HostTransactionRunner.run_write() transaction 删除...该 transaction 提交后，第二阶段从 cursor 0 replay。`
  - §6：`replay 必须按 batch_size 分批执行，每批使用独立 HostTransactionRunner.run_write() transaction，并在同一批 transaction 内写 projection rows 与推进 checkpoint。`
  - §6：`replay 中途失败时，已提交批次的 checkpoint 必须保留在最后成功 cursor；下一次 repair 从 checkpoint 继续，不得要求重新执行全量 reset，也不得把全量 replay 放进单个长 write transaction。`
  - P8-S3 tests：`Repair batch test: reset_checkpoint=True performs a short reset transaction, then replays in multiple batch_size transactions; if a later batch fails, the next repair resumes from the last committed checkpoint.`
- **结论**: FIXED

### P8-PLAN-F5: ProjectionRunner 事务注入与生命周期必须明确 → FIXED

- **来源**: MiMo P8-PR-001 / DS F-4/Q3
- **修复要求**: ProjectionRunner 构造时接收 HostTransactionRunner 注入；不得自建 SQLite connection；不得持有 public command facade；Phase 8 自动追平 deferred 给 Phase 9 owner
- **当前 plan 证据**:
  - §2.2：`ProjectionRunner：构造时必须接收现有 HostTransactionRunner 和 concrete consumers，由 HostCommandHandle 或后续 composition root 通过 private dependency 注入；不得自建 SQLite connection，不得持有或调用 public command facade。`
  - §2.2：`Phase 8 不强制接入 after-commit wakeup，也不要求 command / dispatch path 自动追平 read model。自动追平 owner 明确 deferred 给 Phase 9 Conversation Memory composition`
  - §6：`该 helper 只接收 HostTransactionRunner 或由它构造的 ProjectionRunner，不得持有 HostCommandHandle public command facade。`
  - P8-S1 允许变更：`Construct ProjectionRunner with an injected HostTransactionRunner; runner must not open its own SQLite connection and must not depend on HostCommandHandle public command methods.`
- **结论**: FIXED

### P8-PLAN-F6: Fanout/wakeup 范围与测试不得强制 dead code → FIXED

- **来源**: MiMo P8-PR-004 / DS F-5
- **修复要求**: fanout/wakeup 定义为可选 non-truth optimization；P8-S2 不要求 fanout shell；测试验证 stream_run_events 独立性
- **当前 plan 证据**:
  - §2.4：`Phase 8 的 fanout / wakeup 只允许作为可选 non-truth optimization；本计划不要求创建 fanout shell，也不把 wakeup 作为 Phase 8 correctness 或成功信号`
  - P8-S2 允许变更：`Do not add fanout / wakeup implementation in P8-S2. This slice only proves stream_run_events correctness is independent from projection, notification and read model side effects.`
  - P8-S2 非目标：`Do not create placeholder fanout modules or disabled notification shells just to satisfy tests.`
  - P8-S2 tests：`stream_run_events correctness does not depend on projection or notification side effects.`
  - P8-S2 停止条件：`If passing P8-S2 tests appears to require creating a fanout shell, stop and rename/reshape the test around EventLog-backed stream correctness instead.`
- **结论**: FIXED

### P8-PLAN-F7: Schema 假设需要 implementation stop checks → FIXED

- **来源**: DS open questions Q1/Q2
- **修复要求**: P8-S1 增加 event_log(event_sequence) FK 合法性 stop check；P8-S3 增加 USER_INPUT_ACCEPTED display_text 可用性 stop check
- **当前 plan 证据**:
  - §3 P8-S1 schema stop check：`implementation agent 必须先确认 event_log(event_sequence) 是否满足 SQLite foreign key parent key 要求...若不满足，必须在 Phase 8 schema bump 内补齐唯一约束 / 唯一索引...并新增 durable schema 测试覆盖`
  - §2.5 P8-S3 payload stop check：`implementation agent 必须确认 USER_INPUT_ACCEPTED 的 typed payload 是否包含 display_text 字段。若不存在，timeline consumer 不得从 raw payload、JSON 字符串或其它展示字段拼接文本`
  - P8-S1 停止条件：`If event_log(event_sequence) cannot be used as a SQLite FK target and no compliant schema/index alternative can be kept inside Phase 8 schema scope, stop and return to controller.`
  - P8-S3 停止条件：`If USER_INPUT_ACCEPTED payload lacks typed display_text, do not parse raw payload text or invent display text; keep refs and nullable display_text instead.`
  - P8-S1 tests：`Schema test: event_log(event_sequence) is a valid SQLite FK target for Phase 8 tables, or schema uses an explicitly tested compliant FK / index alternative.`
  - P8-S3 tests：`USER_INPUT_ACCEPTED without typed display_text keeps display_text NULL and preserves refs; timeline consumer must not synthesize display text from raw payload.`
- **结论**: FIXED

## 新增 Scope Creep / Implementation Blocker 检查

按以下维度逐项扫描 plan 全文：

| # | 检查维度 | 状态 | 证据 |
|---|---------|------|------|
| 1 | 是否新增 public API surface | PASS | §2.1 仍明确"不新增面向 Service / UI 的 public command API"，"第一版建议不新增 public timeline API" |
| 2 | 是否扩大了 slice 文件边界 | PASS | §7 P8-S1/P8-S2/P8-S3 允许文件列表未变化；§4.1/§4.2 文件清单未扩展 |
| 3 | 是否引入 Audit/Tool Trace/Outbox 实现 | PASS | §1.5 非目标不变；§4.3 禁止模块不变；§12 blocking criteria 不变 |
| 4 | 是否修改 Engine/Service/UI/Fins/runtime | PASS | §1.5 非目标不变；§4.3 禁止模块不变 |
| 5 | 是否修改 command path 状态机 | PASS | §1.5 非目标：`不修改 command path 状态机、Run / Attempt governance state` |
| 6 | 是否让 projection 成为 Host governance truth | PASS | §3：`所有新增表属于 projection / read model owner，不是 Host governance truth`；§5 条目 6-10 不变量不变 |
| 7 | 是否新增 untyped/Any/object 边界 | PASS | §2.2 typed contract 不变；§9 import guard 不变；§12 blocking criteria 不变 |
| 8 | 是否引入需 controller 裁决的新设计决策 | PASS | 无新增 open question；所有 deferred item 均有明确 owner |
| 9 | Slice 是否仍可独立通过 tests/pyright | PASS | §7 各 slice 仍有独立测试文件和验证命令 |
| 10 | 修复是否引入矛盾表述 | PASS | §5 条目 3（同事务）与 §5 条目 4（幂等防御 replay）语义一致；§6 两阶段 repair 与 §10 残余风险长事务 mitigation 一致 |

## 残余风险

| 风险 | 严重程度 | Owner | 说明 |
|------|---------|-------|------|
| `event_log(event_sequence)` 可能无 UNIQUE 约束 | 低 | P8-S1 implementation | Plan 已有 stop check，实现时需首先验证；若不满足则需补齐或改用合规方案 |
| `USER_INPUT_ACCEPTED` payload 可能无 typed `display_text` | 低 | P8-S3 implementation | Plan 已有 stop check 和降级行为（写 NULL、保留 refs） |
| Read model 在 Phase 8 内无自动追平 | 低 | Phase 9 owner | 已显式 deferred；Phase 8 交付 runner + repair primitive，Phase 9 接入 after-commit wakeup |
| 首次实现 per-class filter 语义 | 低 | P8-S1 implementation | Plan 要求多 class + type 组合测试覆盖 |
| Repair 大批量 replay 性能特征未验证 | 低 | Phase 15 owner | batch_size 默认值由实现选择；长事务风险由两阶段 + 分批设计缓解 |

## Open Questions

无。原 DS review 的 Q1/Q2/Q3 均已通过 P8-PLAN-F7（stop checks）和 P8-PLAN-F5（repair 接收 HostTransactionRunner）解决。

## Verdict

**PASS**

P8-PLAN-F1 至 P8-PLAN-F7 全部 7 个 finding 均已修复，有直接 plan 文本证据支持。无新增 scope creep、implementation blocker 或需 controller 重新裁决的设计变更。Plan 比原版更具体、更可实施，满足 design.md §14/§16 和 implementation-control.md Phase 8 的约束。

Plan 可以进入 implementation gate（P8-S1）。
