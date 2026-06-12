# WU-RET-00 Plan Re-Review — AgentMiMo

- reviewer: AgentMiMo
- review type: plan re-review（只审查 fix delta，不审查未变更部分）
- artifact reviewed: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`（post-fix）
- controller adjudication: `docs/reviews/wu-ret-00-plan-review-adjudication.md`
- date: 2026-06-12

---

## 1. Summary

Controller 裁决 12 项 accepted finding + 1 项 Issue 76 deferred。本 re-review 逐项核对 plan fix delta，确认每个 accepted finding 是否已在 plan 中修复，并验证修正后的 plan 仍是最小正确闭环、无过度设计、code-generation-ready。

---

## 2. PASS/FAIL

**PASS** — 无 blocking finding。

---

## 3. Accepted Finding 逐项核对

### F-1: Restrict artifact file scanning to `sha256/` namespace

- **来源**: AgentDS F6
- **裁决**: accepted
- **plan fix 位置**: §8 Slice 1 exact changes；§8 Slice 3 tests；§11 R6
- **fix 状态**: **已修复**
- **证据**:
  - Slice 1 `iter_published_artifact_relative_paths` 现在明确写"只递归遍历 artifact root 下的 `sha256/` namespace，跳过 `.tmp` 子树**和所有非 `sha256/` 路径**"。
  - Slice 1 tests 新增"越界路径和 symlink 逃逸被拒"以及"跳过 `.tmp`、`audit/`、`tool-trace/` 和其它非 artifact namespace"。
  - Slice 3 tests 新增"namespace 安全：`artifact_root/audit/*.jsonl`、`artifact_root/tool-trace/*.jsonl` 或其它非 `sha256/` 文件不得进入 orphan 候选"。
  - R6 从"fixed by plan review"升级为"fixed in plan"，明确"only `sha256/` namespace is eligible for artifact orphan scanning / reclaim"。
- **结论**: fix 完整，实现 agent 有明确约束和测试验证。

### F-2: New public maintenance API requires design source sync

- **来源**: AgentDS F2
- **裁决**: accepted
- **plan fix 位置**: §3 设计对齐表；§5 Affected Files；§10 Docs Decision
- **fix 状态**: **已修复**
- **证据**:
  - §3 新增一行"design.md public Host API / maintenance boundary"，明确"实现期必须在 `docs/host/design.md` 增补最小设计说明：maintenance entrypoint、content-addressed-safe artifact deletion proof、grace + recheck + containment、非 command-path 边界，以及 DB VACUUM deferred to Issue 76"。
  - §5 Affected Files 新增 `docs/host/design.md` EDIT 行。
  - §10 Docs Decision 从"不修改 `docs/host/design.md`"改为"**需要**更新"。
- **结论**: fix 完整，controller 正确推翻了原 MiMo review 的"无需修改 design.md"结论。

### F-3: Clarify descriptor logical bytes vs physical bytes

- **来源**: AgentDS F1 / AgentMiMo F7
- **裁决**: accepted
- **plan fix 位置**: §6.4 `HostStorageUsageReport` 字段
- **fix 状态**: **已修复**
- **证据**:
  - 字段已从 `artifact_logical_bytes` 重命名为 `artifact_descriptor_logical_bytes`。
  - docstring 明确"注：这是 descriptor logical sum，不是物理文件占用；内容寻址共享下它可能大于实际物理占用。物理文件占用见 maintenance result 的 `physical_artifact_bytes`"。
- **结论**: fix 完整，operator 不会误读为物理占用。

### F-4: Document recheck/unlink TOCTOU residual

- **来源**: AgentDS F3
- **裁决**: accepted
- **plan fix 位置**: §7.3 实现决策；§11 R1
- **fix 状态**: **已修复**
- **证据**:
  - §7.3 新增"残余 TOCTOU"段落：明确"recheck 与 unlink 之间仍存在极短窗口，另一个 write transaction 理论上可能提交同一路径 descriptor"，并说明"实现 docstring / README 必须显式记录该残余"。
  - §11 R1 更新：从"grace 缓解"扩展为"grace + 删除前 recheck + 默认 dry-run + 文档要求 grace 显著大于最大事务延迟"。
- **结论**: fix 完整，TOCTOU 残余有明确的文档化要求。

### F-5: Ensure one truth for artifact path reference check

- **来源**: AgentDS F4
- **裁决**: accepted
- **plan fix 位置**: §7.2 Implementation Decisions
- **fix 状态**: **已修复**
- **证据**:
  - §7.2 现在明确"模块内只允许一个判定逻辑真源，例如私有 `_artifact_relative_path_is_referenced(transaction, path) -> bool`"。
  - "public/internal helper `artifact_relative_path_is_referenced(...)` 和 `collect_referenced_artifact_paths(...)` 必须复用同一判定语义"。
- **结论**: fix 完整，单一真源判定逻辑有显式约束。

### F-6: `_open_durable_connection()` close contract must be explicit

- **来源**: AgentDS F5
- **裁决**: accepted
- **plan fix 位置**: §5 Affected Files；§7.5 Implementation Decisions
- **fix 状态**: **已修复**
- **证据**:
  - §5 `command.py` EDIT 描述中新增"docstring 必须明确调用方必须在 `finally` 或 context helper 中关闭 connection"。
  - §7.5 新增"必须在 `finally` 或 context helper 中关闭"。
- **结论**: fix 完整，connection 关闭契约不再隐式。

### F-7: Avoid storage path god bag

- **来源**: AgentMiMo F1
- **裁决**: accepted
- **plan fix 位置**: §5 Affected Files；§8 Slice 2
- **fix 状态**: **已修复**
- **证据**:
  - §5 `command.py` EDIT 从 `_storage_paths()` 改为"优先拆成 `_db_path()` 与 `_artifact_root_options()`，避免把 SQLite DB 路径和 artifact root 混成一个 bag"。
  - §8 Slice 2 exact changes 对齐。
- **结论**: fix 完整，单一职责 accessors 替代了 god bag。

### F-8: Complete or justify usage report table coverage

- **来源**: AgentMiMo F2
- **裁决**: accepted
- **plan fix 位置**: §8 Slice 2 implementation note
- **fix 状态**: **已修复**
- **证据**:
  - Slice 2 新增 implementation note："表清单必须在实现期基于 `HOST_DURABLE_TABLES` / `schema.py` 全量复核；至少覆盖控制文档验收信号中的 owner 分类，并优先纳入 `host_session_slots`、`host_attempt_dispatch_records`、`host_wait_records`、`host_memory_diagnostics`、`host_audit_sink_markers`、`host_outbox_drain_idempotency`、`host_instances` 等 MiMo review 指出的遗漏表，或在代码 docstring 中说明排除理由"。
- **结论**: fix 完整，遗漏表有明确的优先纳入指引。

### F-9: Use final path containment guard for delete

- **来源**: AgentMiMo F3
- **裁决**: accepted
- **plan fix 位置**: §8 Slice 1 exact changes
- **fix 状态**: **已修复**
- **证据**:
  - Slice 1 `delete_artifact_file` 现在写"不要只调用 `_ensure_parent_dir_contained`；最终文件路径本身必须经过 `_ensure_contained` 校验，防止 symlink 逃逸"。
  - 测试新增"越界路径和 symlink 逃逸被拒"。
- **结论**: fix 完整，`_ensure_contained` 而非仅 `_ensure_parent_dir_contained`。

### F-10: Fix grace default

- **来源**: AgentMiMo F4
- **裁决**: accepted
- **plan fix 位置**: §6.4 `HostStorageMaintenanceRequest`
- **fix 状态**: **已修复**
- **证据**:
  - `orphan_grace_seconds: float = DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS`，具名常量默认值为 `3600.0`。
  - docstring 说明："仅删除 mtime 早于 `now - grace` 的 orphan，防止删掉 publish 已落盘但 descriptor 尚未 commit 的在途文件"。
- **结论**: fix 完整，保守默认值 + 具名常量 + docstring 说明。

### F-11: Avoid leaking transaction outside transaction boundary

- **来源**: AgentMiMo F5
- **裁决**: accepted-with-correction
- **plan fix 位置**: §8 Slice 4 exact changes；adjudication table
- **fix 状态**: **已修复**
- **证据**:
  - Slice 4 改为"facade 传入一个显式 recheck callable，该 callable 内部用 `host._run_read(...)` 执行 `artifact_relative_path_is_referenced`。不要把 `HostTransaction` 对象通过 transaction factory 泄漏到事务边界外"。
  - Adjudication 明确"the suggested `lambda: host._run_read(lambda txn: txn)` is rejected as unsafe because it would return a transaction outside its valid boundary"。
- **结论**: fix 完整且正确。controller 正确拒绝了原建议的 unsafe lambda。

### F-12: Clarify single-file deletion failure behavior

- **来源**: AgentMiMo F6
- **裁决**: accepted
- **plan fix 位置**: §6.4 `HostStorageMaintenanceResult`；§6.4 新增 `HostStorageMaintenanceFileError`；§8 Slice 4 error handling
- **fix 状态**: **已修复**
- **证据**:
  - `HostStorageMaintenanceResult` 新增 `file_errors: tuple[HostStorageMaintenanceFileError, ...]`（"单文件删除失败或 stat 失败的结构化诊断；成功删除的文件才进入 `reclaimed_artifact_paths`"）。
  - 新增 `HostStorageMaintenanceFileError` 类型：`artifact_relative_path: str`、`error_message: str`、`operation: str`。
  - Slice 4 error handling 更新："单文件删除失败不得静默吞掉；失败文件不进入 `reclaimed_artifact_paths`，以 `file_errors` 返回结构化诊断并继续处理其它候选"。
- **结论**: fix 完整，结构化错误 + 不中断批量处理。

---

## 4. Issue 76 裁决审查

- **裁决**: DB VACUUM deferred to GitHub Issue 76；WU-RET-00 只暴露 DB/WAL size + checkpoint 诊断。
- **合理性**: **合理**
  - §2 Non-Goals 明确"不实现完整 DB vacuum 平台"。
  - §7.5 Implementation Decisions 明确"不做 VACUUM（§2 非目标；DB vacuum / space reclamation owner = GitHub Issue 76）"。
  - `run_storage_maintenance` 的 checkpoint 行为只复用既有 `run_host_wal_checkpoint`，不引入 `VACUUM` / `PRAGMA incremental_vacuum` / `auto-vacuum`。
  - 这与总控文档 WU-RET-00 非目标"不在 command path 做任何慢 cleanup / 文件扫描 / VACUUM"一致。
- **结论**: 裁决正确。VACUUM 是独立的 DB 物理空间回收策略，不应与 artifact orphan 文件回收混在同一 WU。

---

## 5. Minimal Correctness / Over-design Check

修正后的 plan 是否仍是最小正确闭环？

| 检查维度 | 评估 | 证据 |
| --- | --- | --- |
| 不引入 scheduler | ✓ | §2 Non-Goals 显式排除 |
| 不自动 hard delete | ✓ | 只回收"已无任何 durable 引用的 orphan 物理文件"，不按业务维度删除 |
| 不引入 JSONL governance | ✓ | §2 Non-Goals 排除 Tool Trace / Audit JSONL governance |
| 不引入 VACUUM 平台 | ✓ | §2 Non-Goals + Issue 76 deferred |
| 零 schema 变更 | ✓ | §6.1 明确 |
| Destructive 行为仅"删 orphan 物理文件" | ✓ | 且默认 dry-run、grace + recheck + containment |
| 复用既有原语 | ✓ | `run_host_wal_checkpoint`、artifact containment 守卫、purge 引用判定同义逻辑 |

**结论**: 修正后的 plan 仍然最小正确，未引入任何过度设计。

---

## 6. Code-Generation-Ready 验证

| Slice | Allowed files 明确 | Contract handoff 稳定 | Tests 覆盖 fix delta | 可独立验证 |
| --- | --- | --- | --- | --- |
| S1 — artifact helper | ✓ | ✓（`iter_published_artifact_relative_paths` + `delete_artifact_file`） | ✓（新增 `sha256/` namespace 限制测试） | ✓ |
| S2 — usage report | ✓ | ✓（`HostStorageUsageReport` + `_db_path()` / `_artifact_root_options()`） | ✓（新增 implementation note 覆盖遗漏表） | ✓（不依赖 S1） |
| S3 — deletion proof + dry-run | ✓ | ✓（deletion proof 原语 + `HostStorageMaintenanceRequest/Result`） | ✓（新增 namespace 安全测试） | ✓（依赖 S1+S2） |
| S4 — orphan reclaim | ✓ | ✓（`reclaim_orphan_artifact_files` + recheck callable） | ✓（新增 `file_errors` 测试） | ✓（依赖 S1+S3） |

- **依赖链**: S1 → S3 → S4，S2 独立于 S1 但被 S3 依赖。fix delta 未改变依赖链。
- **新类型**: `HostStorageMaintenanceFileError`（§6.4）有完整字段定义。
- **命名变更**: `artifact_logical_bytes` → `artifact_descriptor_logical_bytes` 在 §6.4 中一致。

**结论**: 修正后的 plan 仍 code-generation-ready。

---

## 7. Residual Risks

| ID | 状态 | Owner | 备注 |
| --- | --- | --- | --- |
| R1 | accepted-current-WU | Slice 3/4 + doc | publish-before-commit + TOCTOU 残余由 grace + recheck + dry-run + containment 缓解；plan 已要求实现期文档化 |
| R2 | deferred-with-owner | 后续清理 WU | purge `cleanup_refs` 死字段 |
| R3 | deferred-with-owner | 后续 storage lifecycle | orphan SQLite payload rows 只报告不删除 |
| R4 | covered-by-design | WU-RET-00 | artifact root scan 只在 maintenance entrypoint |
| R5 | deferred-with-owner | GitHub Issue 76 | DB VACUUM / space reclamation |
| R6 | fixed-in-plan | WU-RET-00 implementation | 只有 `sha256/` namespace 有资格扫描/回收 |

---

## 8. Final Assessment

**plan re-review PASS。**

- **blocking findings**: 0
- **accepted findings 修复状态**: 12/12 已修复
- **Issue 76 裁决**: 合理（DB VACUUM deferred，不属于本 WU scope）
- **过度设计检查**: 通过（无 scheduler / 无自动 hard delete / 无 JSONL governance / 无 VACUUM 平台）
- **code-generation-ready**: 是（4 个 slice 依赖链稳定，contract handoff 明确，tests 覆盖 fix delta）
- **artifact deletion proof**: sound（原 review 结论未变）
- **residual risks**: R1–R6 已分类，R6 已修复

plan 可进入 implementation gate。
