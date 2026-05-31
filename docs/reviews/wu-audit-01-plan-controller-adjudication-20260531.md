# WU-AUDIT-01 Plan Controller Adjudication

## Context

- Work unit: WU-AUDIT-01 Purge Audit Cross-medium Orphan Reconciliation
- Plan: `docs/host/wu-audit-01-purge-audit-reconciliation-plan.md`
- Design source: `docs/host/design.md`
- Control document: `docs/host/host-core-followup-implementation-control.md`
- Plan reviews:
  - `docs/reviews/wu-audit-01-plan-review-mimo-20260531.md`
  - `docs/reviews/wu-audit-01-plan-review-ds-20260531.md`
- Plan re-reviews:
  - `docs/reviews/wu-audit-01-plan-rereview-mimo-20260531.md`
  - `docs/reviews/wu-audit-01-plan-rereview-ds-20260531.md`

## Controller Judgment

Plan accepted.

The accepted plan is aligned with the Host design goal: audit JSONL remains destructive operation flow, while SQLite purge tombstone remains purge completion truth. The plan is also scoped to the current root cause: completion semantics were written to JSONL before SQLite commit. It does not introduce a generic audit analysis framework, reconciliation report, durable schema change, or new public result field.

## Finding Dispositions

| Finding | Source | Disposition | Rationale |
|---|---|---|---|
| Retry/replay path did not concretely补写 `purge_completed` | MiMo 01 / DS 01 | accepted-fixed | 基于 design_doc 的 durable truth 目标，commit 后 completed append 失败必须通过同 key retry 补写 completed；使用 JSONL source key 幂等去重是当前 phase 的最小正确方案。 |
| `build_purge_tombstone_digest` 字段集不明确 | MiMo 02 | accepted-fixed | completed 必须引用可复算的 committed tombstone digest；显式列出全部持久字段能避免 implementation agent 自行发明字段集。 |
| purge audit request dataclass 字段不明确 | MiMo 03 | accepted-fixed | 明确 request 输入与 builder 派生字段能减少计划歧义，且不扩大实现范围。 |
| command path 直接写 audit 的设计张力未声明 | DS 02 | accepted-fixed | purge 是删除 EventLog 的专用例外；显式写清边界能防止 direct audit write 模式扩散。 |
| `purge_started` retry 幂等确定性未声明 | DS 03 | accepted-fixed | started line 必须 deterministic 才能支撑同 key retry 不重复写入，这是当前最小 audit 方案的必要不变量。 |
| docstring 更新范围不明确 | DS 04 | accepted-fixed | tombstone audit ref 语义从 completed 收窄到 started，docstring 清单是防误读所需的最小文档同步。 |

## Residual Risks

| Risk | Disposition | Owner / Destination |
|---|---|---|
| completed append 在 SQLite commit 后失败时，需要调用方用同一 `client_request_id` retry 才能补写 completed line。 | accepted residual behavior | WU-AUDIT-01 implementation tests must cover retry补写 path. |
| `purge_failed` 是 best-effort；如果 failed append 也失败，JSONL 只留下 started line。 | accepted residual behavior | WU-AUDIT-01 implementation must ensure started line cannot be marked completed. |
| tombstone `audit_record_ref` / `audit_record_digest` 指向 started line。 | accepted documentation risk | WU-AUDIT-01 implementation must update docstrings and Host README if needed. |

## Gate Decision

Plan review gate passed. The work unit may proceed to accepted plan checkpoint and then implementation slice assignment.
