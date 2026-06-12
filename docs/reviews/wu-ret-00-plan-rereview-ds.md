# WU-RET-00 Plan Re-review — AgentDS

- review type: plan re-review（只审查 fix delta）
- plan artifact: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`
- original review artifacts:
  - `docs/reviews/wu-ret-00-plan-review-mimo.md`
  - `docs/reviews/wu-ret-00-plan-review-ds.md`
- controller adjudication: `docs/reviews/wu-ret-00-plan-review-adjudication.md`
- design source: `docs/host/design.md`, `docs/engine/design.md`
- control doc: `docs/host/issues-implementation-control.md`
- date: 2026-06-12

---

## 1. Re-review Scope

仅审查 controller adjudication 中 accepted findings 的 plan fix delta。不重新审查原 review 已 PASS 的部分，不实现、不修改生产代码、不进入 implementation gate。

## 2. Accepted Findings — Fix Status

| # | Finding | Source | Verdict | Status | Evidence |
|---|---|---|---|---|---|
| 1 | Restrict artifact file scanning to `sha256/` namespace | AgentDS F6 | accepted | **已修复** | Slice 1 `iter_published_artifact_relative_paths` 明确"只递归遍历 `sha256/` namespace，跳过所有非 `sha256/` 路径"；§7.3 (b) 明确"唯一合法的 published artifact namespace `sha256/`"；Slice 3 tests 覆盖 audit/tool-trace 不入候选；R6 标记 fixed-in-plan |
| 2 | New public maintenance API requires design source sync | AgentDS F2 | accepted | **已修复** | §3 设计对齐表新增一行明确"实现期必须在 `docs/host/design.md` 增补最小设计说明"；§5 affected files 列入 `docs/host/design.md` EDIT；§10 Docs Decision 明确 design.md 需要更新 |
| 3 | Clarify descriptor logical bytes vs physical bytes | AgentDS F1 / AgentMiMo F7 | accepted | **已修复** | §6.4 field 重命名为 `artifact_descriptor_logical_bytes`，docstring 说明"这是 descriptor logical sum，不是物理文件占用；内容寻址共享下可能大于实际物理占用。物理文件占用见 maintenance result 的 `physical_artifact_bytes`" |
| 4 | Document recheck/unlink TOCTOU residual | AgentDS F3 | accepted | **已修复** | §7.3 (e) 显式列出"残余 TOCTOU：recheck 与 unlink 之间仍存在极短窗口"并说明缓解；§11 R1 覆盖 recheck/unlink TOCTOU；要求实现 docstring / README 显式记录 |
| 5 | Ensure one truth for artifact path reference check | AgentDS F4 | accepted | **已修复** | §7.2 明确"模块内只允许一个判定逻辑真源"，`artifact_relative_path_is_referenced` 和 `collect_referenced_artifact_paths` 必须复用同一判定语义（私有 `_artifact_relative_path_is_referenced`） |
| 6 | `_open_durable_connection()` close contract must be explicit | AgentDS F5 | accepted | **已修复** | §5 `command.py` EDIT 的 docstring 要求"明确调用方必须在 `finally` 或 context helper 中关闭 connection"；§7.5 同样约束 |
| 7 | Avoid storage path god bag | AgentMiMo F1 | accepted | **已修复** | §5 `command.py` EDIT 拆为 `_db_path()` 与 `_artifact_root_options()` 两个 typed accessors，"避免把 SQLite DB 路径和 artifact root 混成一个 bag" |
| 8 | Complete or justify usage report table coverage | AgentMiMo F2 | accepted | **已修复** | §8 Slice 2 新增 implementation note：要求实现期全量复核 `HOST_DURABLE_TABLES`，优先纳入 MiMo review 指出的 `host_session_slots`、`host_attempt_dispatch_records`、`host_wait_records`、`host_memory_diagnostics`、`host_audit_sink_markers`、`host_outbox_drain_idempotency`、`host_instances` 等遗漏表，或在 docstring 中说明排除理由 |
| 9 | Use final path containment guard for delete | AgentMiMo F3 | accepted | **已修复** | §8 Slice 1 `delete_artifact_file` 明确守卫链：`_validate_relative_path_text` → `_path_from_posix_relative` → `_ensure_contained(root, final_path)` → `unlink`；显式禁止只调用 `_ensure_parent_dir_contained` |
| 10 | Fix grace default | AgentMiMo F4 | accepted | **已修复** | §6.4 `orphan_grace_seconds: float = DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS`，具名常量默认值 `3600.0`，docstring 说明取值理由；§11 Q2 不再保留为 open question |
| 11 | Avoid leaking transaction outside transaction boundary | AgentMiMo F5 | accepted-with-correction | **已修复** | §8 Slice 4 `reclaim_orphan_artifact_files` 改为接受显式 `is_artifact_path_referenced` callable（而非 transaction factory），明确"不要把 `HostTransaction` 对象泄漏到事务边界外" |
| 12 | Clarify single-file deletion failure behavior | AgentMiMo F6 | accepted | **已修复** | §6.4 新增 `HostStorageMaintenanceFileError` 类型（`artifact_relative_path` / `error_message` / `operation`）；`HostStorageMaintenanceResult.file_errors` 收集结构化诊断；§8 Slice 4 明确"失败文件不进入 `reclaimed_artifact_paths`，以 `file_errors` 返回" |

**全部 12 个 accepted findings 状态为"已修复"。**

## 3. Controller Adjudication 合理性审查

### 3.1 Issue 76 deferral — 合理

Controller 将 DB VACUUM 需求 deferred to GitHub Issue 76，不在本 WU 实施。

验证：
- Plan §2 Non-Goals 明确列出"不实现完整 DB vacuum 平台...SQLite vacuum / space reclamation 的后续 owner 是 GitHub Issue 76"
- Plan §7.5 明确"**不做 VACUUM**（§2 非目标；DB vacuum / space reclamation owner = GitHub Issue 76）"
- Plan §11 R5 标记为 `deferred-with-owner: GitHub Issue 76`
- Plan §3 设计对齐表明确 maintenance entrypoint "DB VACUUM deferred to Issue 76"

**裁决合理**：本 WU 只暴露 DB/WAL size 诊断 + checkpoint，不扩展 DB 物理空间回收。Issue 76 是明确的外部 owner。

### 3.2 AgentMiMo design-source conclusion 驳回 — 合理

Controller 驳回了 AgentMiMo review §8 中"无需修改 `docs/host/design.md`"的结论，要求 plan 纳入 design.md 更新。

验证：
- Plan 已按裁决修正：§3、§5、§10 均明确 design.md 需在实现期增补
- 增补范围受限：仅 maintenance entrypoint、content-addressed-safe deletion proof、grace+recheck+containment、非 command-path 边界、DB VACUUM deferred to Issue 76
- 不扩写 scheduler / JSONL governance / VACUUM 平台

**裁决合理**：新增 operator-facing Host public API 属于 public contract 变更，按项目约束必须同步设计真源。

### 3.3 Transaction factory → recheck callable 修正 — 合理且正确

Controller 拒绝了 `lambda: host._run_read(lambda txn: txn)` 的建议（AgentMiMo F5），改为显式 recheck callable。

验证：
- Plan §8 Slice 4 已改为 `reclaim_orphan_artifact_files(is_artifact_path_referenced, ...)`
- 明确"不要把 `HostTransaction` 对象通过 transaction factory 泄漏到事务边界外"
- 这是正确的安全修正：`HostTransaction` 的生命周期由 `_run_read` context manager 管理，泄露到外部会导致 use-after-close

**裁决合理且正确**。

## 4. 修正后 Plan 最小正确闭环验证

| 维度 | 状态 | 证据 |
|---|---|---|
| 无 scheduler | PASS | §2 明确"不实现 scheduled retention scheduler：不引入周期 GC、后台线程、定时触发器" |
| 无自动 hard delete | PASS | §2 明确"不实现 time-window / user / workspace / run-scope 自动 hard delete" |
| 无 JSONL governance | PASS | §2 明确 Tool Trace cold JSONL 归 WU-RET-01/#36，Audit JSONL 归 WU-RET-02/#96 |
| 无 VACUUM 平台 | PASS | §2 / §7.5 / R5 均明确 deferred to Issue 76 |
| 无 schema 变更 | PASS | §6.1 明确"无 schema 变更" |
| 不碰 purge 语义 | PASS | §7.4 明确"purge 的 SQLite 删除事务语义完全不动" |
| 慢维护不进 command path | PASS | §7.6 明确 maintenance 不经 admission、不写 canonical facts |
| 只解决三件事 | PASS | report（可观测）+ deletion proof（安全删除）+ maintenance entrypoint（慢维护隔离） |

**结论：修正后 plan 仍是最小正确闭环，未引入任何被列为 non-goal 的能力。**

## 5. Code-Generation Readiness 验证

| Slice | 状态 | 检查项 |
|---|---|---|
| Slice 1 — artifact helper | PASS | objective / allowed files / data flow / error handling / invariants / tests / non-goals 完整且明确 |
| Slice 2 — usage report | PASS | 同上；implementation note 覆盖表清单复核要求 |
| Slice 3 — deletion proof + dry-run | PASS | 同上；tests 覆盖共享引用 / projection lag / purge 泄漏 / namespace 安全 / grace / checkpoint / 非 command-path |
| Slice 4 — orphan reclaim | PASS | 同上；tests 覆盖回收 / 共享引用保护 / recheck 命中 / 删除失败 / dry-run / 幂等 |

**所有 4 个 slice 均为 code-generation-ready。**

## 6. Residual Risks 追踪

| ID | 状态 | Owner | 备注 |
|---|---|---|---|
| R1 | accepted-current-WU | Slice 3/4 | publish-before-commit + recheck/unlink TOCTOU，dry-run + 3600s grace + recheck + containment 多层缓解 |
| R2 | deferred-with-owner | 后续 cleanup WU | purge `cleanup_refs` 死字段 |
| R3 | deferred-with-owner | 后续决策 | orphan SQLite payload row 只报告不删除 |
| R4 | covered-by-design | WU-RET-00 | artifact root 遍历仅在 maintenance |
| R5 | deferred-with-owner | GitHub Issue 76 | DB VACUUM |
| R6 | fixed-in-plan | WU-RET-00 | `sha256/` namespace restriction |

全部 6 个 risk 有 owner 和明确状态，无 orphan risk。

## 7. Gate 裁决

- **Plan re-review 结论**: **PASS**
- **Blocking findings**: 0
- **Accepted findings 状态**: 12/12 已修复
- **Controller adjudication 合理性**: 全部合理（Issue 76 deferral、design.md 更新要求、transaction boundary 修正）
- **最小正确闭环**: 维持，无 scope creep
- **Code-generation ready**: 是，4 个 slice 均具备实现条件
- **下一 gate**: implementation gate（Slice 1 → Slice 2 → Slice 3 → Slice 4，按序推进）

---

## 8. Re-review Artifact Metadata

- **artifact path**: `docs/reviews/wu-ret-00-plan-rereview-ds.md`
- **reviewer**: AgentDS
- **re-review type**: plan fix delta only
- **plan re-review PASS**
- **blocking findings**: 0
- **next step**: 进入 implementation gate，从 Slice 1 开始
