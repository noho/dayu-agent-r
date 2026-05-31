# WU-AUDIT-01 Plan Re-Review

## Re-Review Target

- **Plan**: `docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`（已更新）
- **Prior review**: `docs/reviews/wu-audit-01-plan-review-mimo-20260531.md`
- **Re-review focus**: 三个 findings 是否已关闭、是否重新引入过度设计

## Finding 01 关闭检查：重放路径 completed 补写

**原 finding**：replay 路径未处理 `purge_completed` 补写，导致 completed append 失败 + 重试后 JSONL 永远缺少 completed line。

**Plan 更新内容**：

- Section 4 新增 "retry / replay 规则"（lines 176-181）：
  - `purge_session_durable(...)` 返回 `idempotent_replay is True` 时，command path 必须无条件尝试 append `purge_completed`。
  - 不读取、不扫描 JSONL 判断 completed 是否已存在；只依赖 `_append_audit_json_line` 的 source key `(line_kind, purge_attempt_ref)` 幂等去重。
  - 同 key retry 在 tombstone replay 后仍尝试 completed append；如果 completed 已存在，append helper 幂等跳过；如果上次 completed append 失败，则本次补写。
- Section 5.3 补充（line 261）：`PurgeSessionDeleteResult.idempotent_replay is True` 时仍无条件调用 `append_purge_completed_audit_record(...)`，不扫描 JSONL。
- Section 6 Slice 3 验收补充（line 328）：completed append 失败后同 key retry 最终只有一条 completed。
- Section 7.4 新增完整测试（lines 370-378）：覆盖首次 purge completed append 失败 → 同 key retry → replay → 补写 completed 的完整路径。

**验证**：设计语义正确——replay 时无条件尝试 completed append，幂等去重由 JSONL source key 保证，不引入 JSONL 扫描。与现有 `_append_text_if_absent` source key 冲突检测机制一致（`dayu/host/audit.py:516-536`）。

**结论**：**关闭**。

## Finding 02 关闭检查：build_purge_tombstone_digest 字段集

**原 finding**：`build_purge_tombstone_digest` 的"已持久字段"具体包含哪些字段不明确。

**Plan 更新内容**：

- Section 3 显式列出全部 17 个字段（lines 140-158）：`tombstone_id`、`session_id`、`client_request_id`、`semantic_request_digest`、`actor`、`source`、`operation_context_digest`、`operation_context_refs`、`reason`、`purged_at`、`precondition_digest`、`deleted_counts`、`deleted_counts_digest`、`deleted_refs_digest`、`audit_record_ref`、`audit_record_digest`、`request_context`。
- 明确说明 `audit_record_ref` / `audit_record_digest` 指向 started line，属于 committed tombstone row 的持久语义，必须纳入 digest。
- 明确说明 digest 不包含 `purge_completed` line 的 ref/digest 或任何 completed append 结果，避免循环依赖。
- Section 7.2 验收补充（line 351）：`build_purge_tombstone_digest(tombstone)` 覆盖 tombstone 全部已持久字段，包括指向 started line 的 `audit_record_ref/audit_record_digest`，且不包含 completed line 信息。

**验证**：字段集与 `host_purge_tombstones` DDL 和 `_tombstone_from_row`（`purge.py:2210-2279`）的持久字段完全一致。digest 包含 started audit ref/digest（因为它们是 tombstone row 的持久数据），不包含 completed 信息（避免循环依赖），语义清晰。

**结论**：**关闭**。

## Finding 03 关闭检查：request dataclass 字段未显式列出

**原 finding**：新 request dataclass 的字段未显式列出，需区分"request 携带"和"builder 内部生成"。

**Plan 更新内容**：

- Section 2.2 补充（line 69）：`schema_version`、`line_kind`、`audit_record_ref`、`purge_attempt_ref`、`line_digest` 必须由 builder 生成，调用方不得传入。`purge_attempt_ref` 必须由 builder 使用 `tombstone_id` 派生。
- Section 5.2 显式列出三个 request dataclass 的完整字段（lines 208-234）：
  - `PurgeStartedAuditRecordRequest`：10 个字段（tombstone_id、session_id、client_request_id、semantic_request_digest、actor、source、operation_context_digest、operation_context_refs、reason、request_context）。
  - `PurgeCompletedAuditRecordRequest`：2 个字段（tombstone: PurgeTombstoneRow、semantic_request_digest: str）。tombstone row 已包含全部 completed line 需要的信息。
  - `PurgeFailedAuditRecordRequest`：12 个字段（started 的 10 个 + failure_stage、failure_message）。
  - `PurgeAuditRecordResult`：2 个字段（audit_record_ref、audit_record_digest）。
- 明确说明上述 request dataclass 不得包含 `schema_version`、`line_kind`、`audit_record_ref`、`purge_attempt_ref`、`line_digest` 字段。

**验证**：
- `PurgeStartedAuditRecordRequest` 字段恰好是 builder 构造 started line 所需的业务输入，无冗余。
- `PurgeCompletedAuditRecordRequest` 通过接收 `PurgeTombstoneRow` 避免重复携带 tombstone 已有字段，是最小设计。
- `PurgeFailedAuditRecordRequest` 与 started 共享字段集，额外携带 `failure_stage` / `failure_message`，合理。
- builder 派生字段（schema_version、line_kind、audit_record_ref、purge_attempt_ref、line_digest）不在 request 中，由 builder 根据 line kind 和 tombstone_id 统一生成。

**结论**：**关闭**。

## 过度设计检查

Plan 更新后是否重新引入过度设计：

| 新增项 | 必要性 | 判断 |
|---|---|---|
| retry / replay 规则（Section 4） | 必要——completed append 失败后的补写路径是 plan 核心语义的闭合条件 | 非过度设计 |
| `PurgeCompletedAuditRecordRequest(tombstone, semantic_request_digest)` | 最小——tombstone row 已包含全部 completed line 需要的字段 | 非过度设计 |
| Section 7.4 测试 | 必要——覆盖 replay + completed 补写的闭合路径 | 非过度设计 |
| docstring 更新要求（Section 9） | 必要——语义变更必须同步文档 | 非过度设计 |
| purge command path 直接写 JSONL 的例外说明（Section 2.2 line 71, Section 9 line 425） | 必要——防止该例外扩散为通用模式 | 非过度设计 |

**结论**：没有重新引入过度设计。所有新增项都是 findings 闭合的最小必要改动。

## 新增内容质量检查

### Section 2.2 purge 专用例外说明（line 71）

> purge command path 直接写 JSONL 是 purge 专用例外：目标 Session 的 EventLog 会被 purge 删除，无法依赖常规 EventLog audit projection 在事后生成 destructive purge 流水。该例外不得扩散成通用 command path 直接写 audit 模式；普通 Host command 仍应通过 committed EventLog facts 驱动 audit projection。

这是有价值的架构约束说明，正确解释了为什么 purge 需要例外，以及例外的边界。不是过度设计。

### Section 2.3 started line deterministic 约束（line 87）

> 字段必须完全 deterministic，不包含 timestamp、random id、进程 id 或其它会随 retry 变化的值，保证同一 `session_id`、`client_request_id`、semantic digest retry 时 started line digest 稳定，并依赖 `(line_kind, purge_attempt_ref)` 幂等去重。

这是 replay 幂等性的前提条件。如果 started line 包含 timestamp 等不稳定值，同 key retry 会产生不同 digest，source key 冲突检测会抛错而非幂等跳过。该约束是 Finding 01 闭合的必要条件，非过度设计。

### Section 9 docstring 更新要求（lines 417-425）

列出了 7 个必须更新 docstring 的位置。每条都有明确的更新内容说明。这些是实现阶段的 check-list，不是新的设计要求。

## Open Questions

无。

## Residual Risks

| Risk | Owner | Tracking |
|---|---|---|
| 无新增 residual risk | - | - |

## Final Re-Review Conclusion

**PASS**

三个 findings 均已关闭：
- Finding 01（重放路径 completed 补写）：Section 4 retry/replay 规则 + Section 5.3 command path + Section 7.4 测试，完整闭合。
- Finding 02（tombstone digest 字段集）：Section 3 显式列出全部 17 个字段，语义清晰。
- Finding 03（request dataclass 字段）：Section 5.2 显式列出三个 request dataclass 的完整字段，builder 派生字段明确排除。

Plan 更新后没有重新引入过度设计。所有新增内容都是 findings 闭合的最小必要改动。

Plan 达到 code-generation-ready，可进入 implementation。
