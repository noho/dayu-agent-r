# Host Phase 2 Phase Design Fix Re-Review

## Review Gate Name

Phase 2 design fix re-review。

## Reviewed Target

- `docs/host/design.md` §10 Durable Store / SQLite schema convention / transaction runner
- `docs/host/design.md` §13 EventLog / §13.1 Payload 存储
- `docs/host/design.md` §27 Host Lifecycle / Recovery / host instance liveness foundation
- `docs/host/implementation-control.md` Phase 2 条目与已确认决策
- `docs/reviews/gateflow-phase-design-fix-host-p2-codex-20260514.md`

## Reviewer Conclusion

**ready for plan gate。**

5 个 controller-accepted blocking questions 均已在设计真源与总控文档中修复。设计决策具体到足以支撑后续 handoff-ready plan 生成 SQLite schema DDL、typed contract、错误分类、测试矩阵和 implementation slice。design.md 只写终态架构语义，未夹带 review 过程或历史状态；implementation-control.md 只记录 phase 状态、已确认决策和追踪项，未引入新架构真源。未发现新 blocker。

## Per-BQ Fixed / Not Fixed

### BQ1 - SQLite schema convention / fresh DB bootstrap

**fixed。**

evidence:

- `docs/host/design.md:648-656` 明确：单个 Host SQLite durable DB、fresh bootstrap 创建 schema 幂等校验、`PRAGMA user_version` 标识 schema version、TEXT durable ids、canonical JSON TEXT 存储结构化字段、显式 unique index / primary key、foreign keys on、不预创建后续 phase 空表。
- `docs/host/implementation-control.md:390` 同步记录已确认的 schema convention 决策。

schema convention 足以支撑 plan agent 在 Slice 1 直接写出 DDL 和 bootstrap 幂等测试，不需要现场选择命名或类型规则。

### BQ2 - Transaction runner、WAL / busy timeout、retry policy 和错误分类

**fixed。**

evidence:

- `docs/host/design.md:658-664` 明确：短 write transaction、`BEGIN IMMEDIATE`、WAL、`foreign_keys=ON`、明确 busy timeout、busy / locked 有限 retry + 退避、唯一约束冲突 / 外键错误 / schema mismatch / digest mismatch / idempotency conflict / CAS precondition failed 不 retry、after-commit callbacks 只在 commit 成功后执行、长耗时工作不得在 write transaction 内。
- `docs/host/implementation-control.md:391` 同步记录已确认的 transaction runner 决策。

transaction runner 设计足以支撑 plan agent 在 Slice 1 直接写出 typed API、retryable error set、busy timeout default、after-commit boundary 和 concurrent append smoke tests。

### BQ3 - EventLog row typed contract 与 idempotency primitive 唯一约束

**fixed。**

evidence:

- `docs/host/design.md:1131-1153` 给出 EventLog row 完整字段清单。
- `docs/host/design.md:1155-1164` 明确：`event_sequence` 是 SQLite 分配的全局单调 INTEGER cursor、`event_id` 是 TEXT ledger identity 并全局唯一、所有 event class 都必须有 ledger identity、schema 必须显式约束 `event_id` 全局唯一 / `event_sequence` 全局单调唯一 / `event_class` 必填 / `event_type` 必填。
- `docs/host/design.md:1166-1171` 明确：idempotency 以 `(scope_kind, scope_id, idempotency_key)` 唯一绑定 `semantic_input_digest`、`result_kind`、`result_ref`、`created_event_id?` / `created_event_sequence?`；同 key 同 digest 返回既有 result；同 key 不同 digest 返回 `idempotency_conflict`；幂等冲突不属于 busy retry。
- `docs/host/implementation-control.md:392` 同步记录已确认的 EventLog / idempotency 决策。

contract 足以支撑 plan agent 在 Slice 2 直接写出 EventLog table DDL、appender / reader typed API、idempotency table DDL、unique constraints 和 concurrent append + idempotency conflict tests。

### BQ4 - Payload threshold、descriptor shape、artifact root 注入与外移失败顺序

**fixed。**

evidence:

- `docs/host/design.md:1195-1208` 明确：Phase 2 支持 `sqlite_payload` 与本地 `artifact_ref` 两类最小 descriptor；composition root 注入 `payload_inline_threshold_bytes` 与 artifact root；小于等于 threshold 写 SQLite payload table 并与 EventLog 同事务提交；超过 threshold 的 artifact 先写临时文件 → flush / fsync → digest verify → atomic rename → 再在 SQLite transaction 写 descriptor + EventLog；SQLite 失败后 orphan artifact 只作 cleanup / diagnostics，不作 accepted fact。
- `docs/host/implementation-control.md:393` 同步记录已确认的 payload foundation 决策。

payload foundation 足以支撑 plan agent 在 Slice 3 直接写出 payload table DDL、descriptor typed contract、artifact write helper 最小实现、crash window 测试和 digest mismatch 断言。

### BQ5 - Host instance liveness foundation 的最小边界

**fixed。**

evidence:

- `docs/host/design.md:2379-2385` 明确：Phase 2 只实现 register / heartbeat / stopping / stopped / read row primitive；host instance row 最小字段包括 `host_instance_id`、`pid`、`process_start_token`、`boot_id?`、`created_at`、`heartbeat_at`、`status`；`status` 只表达本机 Host instance 生命周期诊断；heartbeat 只能刷新当前 instance 自己的 row；不实现 positive orphan proof classifier、不读取 dispatch record、不引入 lease / fencing / Attempt takeover。
- `docs/host/implementation-control.md:394` 同步记录已确认的 host instance liveness 决策。

liveness foundation 足以支撑 plan agent 在 Slice 3 直接写出 liveness table DDL、register / heartbeat / stopping / stopped / read row typed API 和 liveness row tests。positive orphan proof、dispatch record join、Attempt `LOST` CAS 留给 Phase 11。

## Check Standard Verification

### design.md 只写终态架构语义

**通过。** `docs/host/design.md` 全文不含 review 过程、用户确认过程、历史讨论、迁移痕迹或临时 open question。Phase 2 相关的 schema convention、transaction runner、EventLog contract、payload foundation 和 host instance liveness 均以终态设计语义书写。

### implementation-control.md 只记录 phase 状态、决策、追踪项

**通过。** Phase 2 条目（lines 359-419）的"已确认的 Phase 2 durable foundation 决策"记录了 5 项 controller-accepted 设计决策，属于 phase 状态与决策追踪。当前状态区（line 1360）记录 Phase 2 design fix 状态与后续 gate 说明。未引入新架构真源。

### 决策足够支撑 handoff-ready plan

**通过。** 5 项决策的具体程度足以让 planning agent 直接生成：
- Slice 1：SQLite DDL、bootstrap 幂等、`BEGIN IMMEDIATE` transaction runner、WAL / busy timeout 配置、retryable error set、after-commit boundary tests。
- Slice 2：EventLog table DDL、`event_sequence` INTEGER PRIMARY KEY、`event_id` TEXT UNIQUE、idempotency table DDL、`(scope_kind, scope_id, idempotency_key)` UNIQUE、appender / reader typed API、concurrent append tests。
- Slice 3：payload table DDL、descriptor typed contract、artifact write helper、host instance liveness table DDL、register / heartbeat / stopping / stopped / read row API、liveness row tests。

### 未夹带 Phase 3+ 内容

**通过。** design.md Phase 2 相关章节未包含 Session / Run / Attempt 状态机、Host command path、Engine dispatch、Projection、Memory、ToolRuntime、Remote transport、Recovery classifier、lease / fencing / takeover 的实现语义。host instance liveness 明确标注不实现 orphan classifier。

### 无新 blocker

**通过。** 未发现新的 blocking question。以下为 residual risk，不阻塞 plan gate。

## Findings

无 blocking finding。

## Open Questions / Residual Risk

1. `payload_inline_threshold_bytes` 的具体默认值未在设计中硬编码，由 composition root 注入。这是正确的架构选择 — 阈值是运行时配置，不是设计决策。plan agent 应在 Slice 3 中将其作为 typed option 的必填或有默认值的字段处理。

2. SQLite busy timeout 的具体毫秒值未在设计中硬编码。plan agent 应在 Slice 1 中将其作为 Host storage policy 的配置项，给出合理默认值并在测试中断言 retry 行为。

3. artifact write helper 只覆盖本地 artifact root，不进入 ToolRuntime / trace / domain repository。Phase 2 plan 不应把财报领域仓储或 tool trace cold store 变成 Host durable store 的内部实现。

4. host instance liveness foundation 不能被误用为 lease / fencing。positive orphan proof、Attempt `LOST`、Run `RECOVERING` 和新 Attempt 创建必须留给 Phase 11 recovery / state machine phase。

5. Phase 2 plan review 仍应重点复核 implementation slices 是否严格停留在 durable foundation，不夹带 Session / Run / Attempt 状态机、Host command path、Engine dispatch、Projection、Memory、ToolRuntime 或 Remote transport。

## Controller Decision Status

`pending-controller-decision`

## Artifact Path

`docs/reviews/gateflow-phase-design-re-review-host-p2-mimo-20260514.md`
