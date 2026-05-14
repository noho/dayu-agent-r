# Host Phase 2 Design Fix Re-Review

## Review Gate Name

Phase 2 design fix re-review — controller-accepted blocking questions verification.

## Reviewed Target

| Artifact | Path | Role |
| --- | --- | --- |
| Original review | `docs/reviews/gateflow-phase-design-host-p2-codex-20260514.md` | Phase 2 design refinement readiness review with 5 BQs |
| Fix artifact | `docs/reviews/gateflow-phase-design-fix-host-p2-codex-20260514.md` | Controller-accepted fix claim (all A 决策) |
| Design source | `docs/host/design.md` §10 Durable Store, §13 EventLog, §13.1 Payload, §27 Host Lifecycle | Architecture truth source |
| Control doc | `docs/host/implementation-control.md` Phase 2 entry, 追踪区 SQLite 多进程 | Phase tracking & decisions |

## Reviewer Conclusion

**Ready for plan gate.**

All 5 blocking questions (BQ1–BQ5) are fixed to a level that supports a handoff-ready plan to produce schema DDL, typed contracts, and test matrix without further architectural decisions. No new blocking findings. Two minor observations that do not block plan gate.

---

## Per-BQ Verification

### BQ1 — SQLite schema convention / fresh DB bootstrap

**Original blocker**: 表命名、主键类型、timestamp 存储、JSON 存储、schema version / user_version、外键策略、index / unique constraint convention、bootstrap 幂等语义、是否允许空 owner 表。

**Fix evidence**:
- `docs/host/design.md:648-656` — 新增 "SQLite schema convention" 段落：single SQLite DB、fresh bootstrap、`PRAGMA user_version`、TEXT durable ids、canonical JSON TEXT、显式 unique index / primary key、foreign keys ON、每表必须有语义 owner、禁止为后续 phase 预建空表。
- `docs/host/implementation-control.md:390` — 已确认决策同步到 Phase 2 进入条件栏。

**Verdict**: **Fixed.** Schema convention 已足够支撑 handoff plan 产出 DDL 与 bootstrap 幂等校验。

**Minor observation** (non-blocking): 原 BQ1 建议中 "INTEGER unix-ms or ISO UTC timestamp" 未在 convention 段落中显式裁决。各 row specification 中出现的 `occurred_at`、`created_at`、`heartbeat_at` 可由 plan 在 convention 框架内选择一种格式；不影响跨 phase 契约。

---

### BQ2 — Transaction runner、WAL / busy timeout、retry policy、错误分类

**Original blocker**: runner API、BEGIN mode、retryable error set、max attempts / backoff、busy timeout default、read/write transaction 区分、after-commit hook 语义。

**Fix evidence**:
- `docs/host/design.md:658-664` — 新增 "SQLite transaction runner" 段落：短 write transaction、`BEGIN IMMEDIATE`、WAL + `foreign_keys=ON` + busy timeout；retry 只包裹 busy / locked 短事务失败且有有限次数和退避；唯一约束冲突、外键错误、schema mismatch、digest mismatch、idempotency conflict、CAS precondition failed 不 retry；after-commit 只在 commit 成功后触发；长耗时工作不得在事务内执行。
- `docs/host/implementation-control.md:391` — 同步，并要求 plan 转成 typed API、schema、错误类型与测试断言。
- `docs/host/implementation-control.md:1264` — SQLite 多进程追踪项已更新为"已确认...handoff-ready plan 必须把这些决策转成 typed API"。

**Verdict**: **Fixed.** Transaction runner 语义已明确到足以写出 runner API 的 typed contract 和错误分类；具体 retry count 和 busy timeout 默认值属于 plan 阶段实现选择，不需要架构裁决。

---

### BQ3 — EventLog row typed contract 与 idempotency primitive 唯一约束

**Original blocker**: `event_sequence` 实现方式、`event_id` 全局唯一或仅 canonical_fact 唯一、preview/diagnostic 的 event_id、idempotency record 绑定 scope、duplicate 与 conflict 返回 shape。

**Fix evidence**:
- `docs/host/design.md:1157-1158` — `event_sequence` 是 SQLite 分配的全局单调 INTEGER 序列；`event_id` 是 TEXT 全局唯一，所有 `event_class` 都必须有 ledger identity。
- `docs/host/design.md:1159` — EventLog schema 显式约束 `event_id` 全局唯一、`event_sequence` 全局单调唯一、`event_class` 必填、`event_type` 必填。
- `docs/host/design.md:1166-1171` — 新增 "idempotency record primitive" 段落：`(scope_kind, scope_id, idempotency_key)` 唯一绑定、`semantic_input_digest` + `result_kind` + `result_ref`；同 key 同 digest 返回已接受 result ref；同 key 不同 digest 返回 `idempotency_conflict`；冲突不按 busy retry 处理。
- `docs/host/implementation-control.md:392` — 同步。

**Verdict**: **Fixed.** EventLog typed contract 和 idempotency primitive 已收敛到可直接生成 CREATE TABLE DDL 和 typed dataclass；plan 需要确定 `event_sequence` 使用 `INTEGER PRIMARY KEY AUTOINCREMENT` 还是独立 sequence row，但这是实现选择而非架构未决。

---

### BQ4 — Payload threshold、descriptor shape、artifact root、外移失败顺序

**Original blocker**: threshold typed option、descriptor table 最小字段、artifact root 注入、artifact ref 路径规则、SQLite 与文件系统非同事务时的顺序和清理。

**Fix evidence**:
- `docs/host/design.md:1199-1204` — 新增内容：
  - 两类最小 descriptor：`sqlite_payload` 与本地 `artifact_ref`
  - Host composition root 显式注入 `payload_inline_threshold_bytes` 与 artifact root；默认值只能在 construction root 应用
  - ≤ threshold → `sqlite_payload` 与 EventLog 同 SQLite 事务
  - > threshold → artifact：temp write → flush/fsync → digest verify → atomic rename → SQLite tx 写 descriptor + EventLog
  - EventLog 不得引用未 durable、未 digest verified、非 artifact root 路径
  - SQLite 后续失败 → 已发布但未被 descriptor 引用的 artifact 只作 cleanup / diagnostics
- `docs/host/implementation-control.md:393` — 同步。

**Verdict**: **Fixed.** Payload foundation 的设计明确覆盖了 descriptor 类型、threshold 注入方式、artifact root、写入顺序和失败清理归属。`payload_inline_threshold_bytes` 的具体默认值和 descriptor table 精确字段可留到 plan 阶段确定。

---

### BQ5 — Host instance liveness foundation 最小边界

**Original blocker**: Phase 2 是否只提供 register/heartbeat 还是同时提供 liveness checker / stale classifier；字段类型、status enum、heartbeat ownership、process_start_token 来源。

**Fix evidence**:
- `docs/host/design.md:2379-2385` — 新增 "Host instance liveness foundation 的最小边界" 段落：
  - Phase 2 只提供 register current instance、heartbeat current instance、mark stopping / stopped best-effort、read instance row 的持久化 primitive
  - 最小字段 `host_instance_id`、`pid`、`process_start_token`、`boot_id?`、`created_at`、`heartbeat_at`、`status`
  - `status` 枚举 `running`、`stopping`、`stopped`、`crashed_suspected` — 仅诊断语义
  - heartbeat 只刷新本 instance row；不因 heartbeat stale 标记其它 instance 的 Attempt
  - positive orphan proof classifier、dispatch record join、Attempt LOST CAS、Run RECOVERING 属于后续 phase
  - 不引入 lease / fencing / Attempt takeover
- `docs/host/implementation-control.md:394` — 同步。

**Verdict**: **Fixed.** Host instance liveness 最小边界清晰；Phase 2 只交付持久化 primitive，不实现 classifier 或 recovery。足够 handoff plan 产出 liveness row schema 和 heartbeat API。

---

## Scope Enforcement

对新增内容逐一检查是否夹带 Phase 3+ 内容：

| 检查项 | 是否出现 | 证据 |
| --- | --- | --- |
| Session / Run / Attempt 状态机 | 否 | Grep of added ranges (design.md:648-664,1157-1171,1199-1204,2379-2385) 无匹配 |
| Host command path | 否 | 同上 |
| Engine dispatch | 否 | 同上 |
| Projection / Memory / Audit / Trace / Outbox | 否 | 同上 |
| ToolRuntime / Remote transport | 否 | 同上 |
| Recovery classifier / positive orphan proof classifier | 否 | §27 显式写明属于后续 phase |
| Lease / fencing / takeover | 否 | §27 显式禁止 |
| 旧库兼容 / migration | 否 | Schema convention 显式禁止 |

无 Phase 3+ scope creep。

## Quality Checks

- `docs/host/design.md` 新增内容均为终态架构语义；无 review 过程、历史讨论、临时 open question 或"上一版对比"。
- `docs/host/implementation-control.md` 的新增内容为 Phase 2 已确认决策记录和追踪项状态更新；无新架构真源。
- 决策粒度支撑 handoff-ready plan 产出 schema DDL、EventLog / idempotency / payload / liveness 的 typed dataclass、transaction runner API、错误类型和 multi-process test matrix。

## Findings

0 blocking findings.

### Observation 1 (non-blocking): Timestamp 存储格式未显式裁决

原 BQ1 建议选项 A 中包含 "INTEGER unix-ms or ISO UTC timestamp"，当前 schema convention 未显式选择。`occurred_at`、`created_at`、`heartbeat_at` 等字段的具体存储类型可由 plan 在 convention 框架内选择（建议 ISO 8601 TEXT 以便可读性和 SQLite 查询友好性，或 INTEGER unix-ms 以节省空间）。不影响跨 phase 契约，不阻塞 plan gate。

### Observation 2 (non-blocking): `payload_inline_threshold_bytes` 与 retry 参数无默认值

`payload_inline_threshold_bytes` 默认值、busy timeout 毫秒数、retry max attempts 和 backoff strategy 的具体数值未在设计真源中指定。这些属于 Host storage policy 的可配置参数，plan 可以选择合理的初始默认值（例如 threshold 64KB、busy timeout 5000ms、retry 3 次、指数退避 10ms/100ms/1000ms）。后续生产化 phase 可调整为配置项。不阻塞 plan gate。

## Open Questions / Residual Risk

### 已解风险

- **Payload artifact orphan cleanup**：设计已明确 SQLite transaction 失败后未引用 artifact 只作 cleanup / diagnostics。plan 需覆盖 cleanup 触发时机（startup / periodic / on-error）和 failure 不阻塞 accepted fact 的测试。

- **Liveness boundary 被误用**：设计已明确 Phase 2 不实现 orphan classifier；plan review 需复核 implementation slices 是否严格遵守此边界。

### 持续追踪风险（来自原始 review）

- Multi-process concurrent append、busy timeout / retry、unique constraint conflict、transaction rollback 后 after-commit 不触发、payload artifact crash window、host instance heartbeat ownership — 这些是 plan review 阶段的压测重点，不属于 design fix re-review 范围。
- Payload descriptor 的 artifact ref 与后续 ToolRuntime / trace / domain repository 的边界 — 需要在后续 phase 持续追踪。

## Controller Decision Status

**Status = pending-controller-decision.**

本 re-review 确认所有 5 个 BQ 已按 controller-accepted A 决策修复到可支撑 handoff-ready plan。controller 需确认：

1. 本 re-review 的结论（ready for plan gate）。
2. 后续是否直接进入 Phase 2 handoff-ready plan gate（由 planning agent 产出 `docs/host/phase2-durable-store-eventlog-plan.md`）。

## Artifact Path

`docs/reviews/gateflow-phase-design-re-review-host-p2-ds-20260514.md`
