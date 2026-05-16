# Host Phase 7 Design Fix Re-Review — 2026-05-16

## Review Target

- **Controller adjudication**: `docs/reviews/host-phase7-design-re-review-controller-adjudication-20260516.md`
- **Fix diff**: `docs/host/design.md` 和 `docs/host/implementation-control.md` 当前 uncommitted diff（自上一轮 re-review 以来的增量）

## Review Scope

逐条核验 controller 接受的 8 条 findings 是否被正确关闭：

| # | Finding | 来源 | 裁决 |
|---|---|---|---|
| 1 | `resolve_wait` 返回类型未显式声明 | MiMo-1 | 接受，写回 design.md |
| 2 | `outcome_ref` 替换命名未显式声明 | MiMo-2 | 接受，写回 design.md |
| 3 | `observed_at` 类型未定 | DS-F1 | 接受为 plan gate requirement |
| 4 | `lost` outcome 语义歧义 | DS-F2 | 接受为 plan gate requirement |
| 5 | late result diagnostic 记录路径缺失 | DS-F3 | 接受，写回 design.md |
| 6 | WAITING cancel 单数措辞 | DS-F4 | 接受 |
| 7 | 测试矩阵缺少竞态覆盖 | DS-F5 | 接受 |
| 8 | adapter/snapshot/external refs 需 plan 具体化 | MiMo-3 / DS-F6 | 接受为 plan gate requirement |

## 核验明细

### 1. MiMo-1 — `resolve_wait` 返回类型 ✅ CLOSED

- **要求**: `resolve_wait` 签名应显式声明返回类型
- **写回**: `design.md` §20 line 2075 改为 `resolve_wait(wait_id, request) -> RunSnapshot`；§3 line 1034 public API 说明 "成功返回当前 `RunSnapshot`"
- **代码事实**: 当前 `dayu/host/command.py:487-489` 签名已为 `-> RunSnapshot`，设计真源与代码签名一致
- **结论**: 关闭

### 2. MiMo-2 — `outcome_ref` 替换命名 ✅ CLOSED

- **要求**: 明确 `outcome_ref: str` 必须被替换，而非叠加新字段
- **写回**: `design.md` §3 line 1032 "`ResolveWaitRequest.outcome_ref: str` 必须被强类型 `outcome` envelope 替代"
- **代码事实**: 当前 `dayu/host/api.py:1248` 仍为 `outcome_ref: str` — 这是在 Phase 7 实现中需要替换的目标
- **结论**: 关闭

### 3. DS-F1 — `observed_at` 类型 ✅ CLOSED (deferred to plan gate)

- **要求**: plan 必须明确 `observed_at` 用 `datetime` 还是 strict validated string
- **写回**: `implementation-control.md` 退出条件 line 802 "`observed_at` 类型或解析策略...均在 plan 与实现中明确"
- **验证**: 退出条件是 plan gate 的硬性检查点，planning agent 不能跳过
- **结论**: 关闭（design 层面免除歧义，plan 层面有显式退出条件）

### 4. DS-F2 — `lost` outcome 语义歧义 ✅ CLOSED (deferred to plan gate)

- **要求**: plan 必须区分 adapter-reported lost 与 Host-initiated wait record `lost`
- **写回**: `implementation-control.md` 退出条件 line 802 "lost outcome 与 wait record lost 状态区别...均在 plan 与实现中明确"
- **设计真源**: `design.md` §20 line 2095 "如果 job 状态无法确认，应进入 structured failed / lost" — Host 有自主裁决权
- **结论**: 关闭（design 层面免除歧义，plan 层面有显式退出条件）

### 5. DS-F3 — late result diagnostic 记录路径 ✅ CLOSED

- **要求**: 迟到结果不能静默丢弃，必须有最小 diagnostic 记录载体
- **写回**:
  - `design.md` §20 line 2109-2113: 迟到结果必须追加 `event_class=diagnostic`、`event_type=WAIT_LATE_RESULT_REJECTED` 的 EventLog diagnostic event，payload 包含 `wait_id`、`run_id`、`source`、`idempotency_key`、`observed_at`、rejection reason 与 outcome digest / refs
  - `design.md` §22 line 2224-2227: cancel 后的 late result 同样必须追加 `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event
  - `implementation-control.md` Phase 7 关键设计问题 line 802-803: 已确认迟到结果必须追加 diagnostic EventLog event
  - `implementation-control.md` 验证要求 line 818: 新增 "late result writes diagnostic EventLog event" 测试
- **架构安全验证**: `EventClass.DIAGNOSTIC` 已存在于 `dayu/host/durable/event_log.py:65`，SQLite schema `dayu/host/durable/schema.py:107-111` 已允许 `diagnostic`。`dayu/host/run_input.py:971` 已过滤 `event_class != CANONICAL_FACT`，确保 diagnostic event 不会泄漏到 RunInputBuilder。仅需新增 `event_type` 值，无需 schema migration
- **结论**: 关闭

### 6. DS-F4 — WAITING cancel 单数措辞 ✅ CLOSED

- **要求**: cancel 路径应表述为标记所有 active wait records，而非单数
- **写回**: `design.md` §22 line 2212-2215 "CAS 标记该 Run 下所有 active `status=waiting` wait records 为 `cancelled`"，并加注 "Phase 7 第一版应保持同一 Run 同时只有一个 active wait record 的 invariant，并用测试守护；复数更新是防御性状态收口"
- **结论**: 关闭

### 7. DS-F5 — 测试矩阵缺少竞态覆盖 ✅ CLOSED

- **要求**: 测试矩阵应包含 cancel-vs-resolve first-committer-wins 与 poll adapter 停轮询验证
- **写回**: `implementation-control.md` 验证要求 line 818-819 新增: "cancel-vs-resolve first-committer-wins、poll adapter observes cancelled wait and stops / abandons observation、late result writes diagnostic EventLog event"
- **结论**: 关闭

### 8. MiMo-3 / DS-F6 — typed refs 需 plan 具体化 ✅ CLOSED (deferred to plan gate)

- **要求**: `adapter_key` 来源、`snapshot_ref` 与 `external_job_id` 的 typed ref 约束在 plan 中明确
- **写回**: `implementation-control.md` 退出条件 line 802-803 "`adapter_key` 来源、`snapshot_ref` / `external_job_id` typed ref 约束均在 plan 与实现中明确"
- **结论**: 关闭（design 层面确认字段列表与禁止项，plan 层面有显式退出条件）

## Plan Gate Requirements 覆盖检查

Controller 列出 7 项 plan gate 必须覆盖的内容：

| # | Plan Gate Item | 覆盖位置 |
|---|---|---|
| 1 | `ResolveWaitRequest` typed outcome envelope 字段名/封闭联合成员/payload ref 约束 | `implementation-control.md` 退出条件 "typed outcome envelope 替代"；`design.md` §3 / §20 已描述四种 outcome 类型 |
| 2 | `observed_at` 用 `datetime` 还是 strict validated string | `implementation-control.md` 退出条件 "`observed_at` 类型或解析策略" |
| 3 | adapter reported lost vs Host wait record `lost` 裁决关系 | `implementation-control.md` 退出条件 "lost outcome 与 wait record lost 状态区别" |
| 4 | `adapter_key` 来源：不得扩展 Engine 契约 | `implementation-control.md` 退出条件 "`adapter_key` 来源"；`design.md` §20 line 2019 已约束 Engine |
| 5 | `snapshot_ref` 与 `external_job_id` 的 typed ref 约束 | `implementation-control.md` 退出条件 "`snapshot_ref` / `external_job_id` typed ref 约束" |
| 6 | `WAIT_LATE_RESULT_REJECTED` diagnostic EventLog event schema 与测试 | `design.md` §20 / §22 已指定 event 结构与 payload；`implementation-control.md` 验证要求已包含测试 |
| 7 | `WAITING` cancel 与 `resolve_wait` 并发 first-committer-wins | `implementation-control.md` 验证要求已包含 "cancel-vs-resolve first-committer-wins" |

全部 7 项已覆盖。

## Architecture Boundary Re-Check

Fix diff 未引入新的架构违规：

- **EventLog diagnostic event**: 使用已有 `EventClass.DIAGNOSTIC`，不改变 canonical fact 状态机，不创建 `EventClass.CANONICAL_FACT` 事件。`dayu/host/run_input.py:971` 已过滤非 `CANONICAL_FACT` 事件，防止 diagnostic event 泄漏到 messages 重建
- **Wait record plural cancel**: CAS 语义仍是 per-record 原子操作，cancel 遍历所有 active records 各自 CAS，不改变事务边界
- **Plan gate deferred items**: `adapter_key` 来源约束已写入 design.md（Host composition root 提供 typed adapter binding，不扩展 Engine 契约），plan 层面进一步具体化

## Residual Risks

| # | Risk | Tracking |
|---|---|---|
| R1 | `WAIT_LATE_RESULT_REJECTED` event 的 `rejection reason` 枚举值未定义，plan 需自行枚举（如 `wait_cancelled`、`wait_lost`、`wait_resolved`） | plan gate check |
| R2 | `outcome digest / refs` 在 diagnostic payload 中的具体格式未定，plan 需定义是摘要字符串还是结构化 payload | plan gate check |
| R3 | Phase 7 退出条件有 6 项 deferred-to-plan 条目，集中在同一个退出条件句中；planning agent 可能在单句表述中遗漏个别项 | controller 在 plan review 阶段逐项核验 |

## Final Re-Review Conclusion

**PASS**

8 条 accepted findings 全部关闭：
- 4 条在设计真源层面直接修复（MiMo-1, MiMo-2, DS-F3, DS-F4）
- 4 条作为 plan gate requirement 写入退出条件（DS-F1, DS-F2, DS-F5, MiMo-3/DS-F6）

Fix diff 未引入新的 design-level ambiguity、架构违规或 blocking open question。三个 residual risks 均为 plan 层面可闭合的实现细节，不需要回到 design discussion。
