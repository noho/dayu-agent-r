# WU-RET-00 Plan Review — AgentMiMo

- reviewer: AgentMiMo
- review type: plan review
- artifact reviewed: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`
- design source: `docs/host/design.md`, `docs/engine/design.md`
- control doc: `docs/host/issues-implementation-control.md`
- date: 2026-06-12

---

## 1. Summary

WU-RET-00 plan 为 Host durable 存储生命周期补齐安全底座：operator 可观测存储占用 report、content-addressed artifact 安全删除证明与 orphan 文件回收、慢维护 command-path 隔离。

plan 的第一性原理判断成立：purge 成功后 `cleanup_refs` 永久泄漏（`command.py:892-897` 只消费 `tombstone`，`cleanup_refs` 被静默丢弃），publish-before-commit 残留无回收路径，operator 无存储可观测面。direct code evidence 全部准确、逻辑/数据同源。

plan 非目标合理：不重做 purge、不引入 scheduler、不自动按时间/用户/workspace 删除、不做 VACUUM、不碰 JSONL governance、不改 schema。

---

## 2. PASS/FAIL

**PASS** — 无 blocking finding。

---

## 3. Findings

### F1 — `_storage_paths()` 方法设计可优化（non-blocking）

- **位置**: plan §5 `command.py` EDIT、§7.1
- **证据**: plan 描述 `_storage_paths()` 返回 `(db_path, artifact_root, create_artifact_root)` typed 视图。实际代码中 `_audit_sink_options()`（`command.py:223-238`）通过 `self._durable_store.options.db_path` 和 `self._durable_store.options.payload_policy.artifact_root` 分别访问这两个值。`HostDurableStore.connect()`（`connection.py:77-89`）已提供独立 connection 开启能力。
- **风险**: 低。`_storage_paths()` 是 Host 内部私有方法，不影响公共 API。但把 db_path 和 artifact_root 打包成一个"storage paths"返回值，语义上混合了 SQLite 数据库路径与文件系统 artifact 路径两类不同关注点。
- **建议修正**: 拆为 `_db_path()` 和 `_artifact_root_options()` 两个独立 typed accessors，或直接在 `storage_maintenance.py` facade 中通过 `host._durable_store.options` 访问（沿用 `_audit_sink_options()` 同一模式）。保持单一职责。
- **裁决**: `deferred-with-owner` — owner = implementation agent，不阻塞 plan。

### F2 — `HostStorageUsageReport` 表清单不完整（non-blocking）

- **位置**: plan §6.4 `HostStorageUsageReport` 字段列表
- **证据**: plan 列出 16 个表的 row 计数字段，但 `schema.py:37-59` 实际定义 19 个表。遗漏的表包括 `host_session_slots`、`host_attempt_dispatch_records`、`host_wait_records`、`host_memory_diagnostics`、`host_audit_sink_markers`、`host_outbox_drain_idempotency`、`host_instances`。
- **风险**: 低。plan 已注明"其余表按实现期复核取舍"，且 `Q3` open question 明确此为实现期可自决细节。operator 可观测面不完整但不影响安全删除证明的正确性。
- **建议修正**: 实现期逐一裁决每个遗漏表是否纳入 report。优先覆盖 `host_session_slots`、`host_attempt_dispatch_records`、`host_wait_records`（与 operator 资源占用直接相关），其余按"自解释、覆盖验收信号枚举"取舍。
- **裁决**: `deferred-with-owner` — owner = implementation agent (Slice 2)，不阻塞 plan。

### F3 — `delete_artifact_file` 守卫函数引用需明确（non-blocking）

- **位置**: plan §8 Slice 1 `delete_artifact_file` exact changes
- **证据**: plan 写"_validate_relative_path_text + `_ensure_parent_dir_contained`/`_ensure_contained` 守卫后 unlink"。代码中 `_ensure_parent_dir_contained`（`artifact.py:262-278`）只校验**祖先目录**不通过 symlink 逃逸，不校验最终文件路径本身。最终文件路径的 containment 校验由 `_ensure_contained`（`artifact.py:245-259`）完成，该函数调用 `candidate.resolve(strict=True)` 后校验 `relative_to(resolved_root)`。
- **风险**: 低。若实现 agent 只调用 `_ensure_parent_dir_contained` 而不调用 `_ensure_contained`，则最终文件路径可能通过 symlink 逃逸。
- **建议修正**: `delete_artifact_file` 的守卫逻辑应为 `_validate_relative_path_text` → `_path_from_posix_relative` → `_ensure_contained(root, resolved_path)` → `unlink`。plan 描述中的"`_ensure_parent_dir_contained`/`_ensure_contained`"应明确为只用 `_ensure_contained`（后者已覆盖前者的功能）。
- **裁决**: `deferred-with-owner` — owner = implementation agent (Slice 1)，不阻塞 plan。

### F4 — orphan grace window 默认值未指定（non-blocking）

- **位置**: plan §6.4 `HostStorageMaintenanceRequest.orphan_grace_seconds`、§11 Q2
- **证据**: plan 说"facade 提供具名常量默认"，Q2 说"实现期取保守大值"。未给出默认值范围。
- **风险**: 低。operator 可通过参数控制。但缺少建议默认值可能导致实现 agent 取值不当（如 60s 过短、86400s 过长）。
- **建议修正**: 建议默认 `orphan_grace_seconds = 3600.0`（1 小时），显著大于任何合理 SQLite 事务延迟，并在 docstring 中说明取值理由。plan Q2 可在 plan gate 关闭前确认此值。
- **裁决**: `deferred-with-owner` — owner = implementation agent (Slice 3)，不阻塞 plan。

### F5 — `reclaim_orphan_artifact_files` transaction factory 注入方式未说明（non-blocking）

- **位置**: plan §8 Slice 4 `reclaim_orphan_artifact_files` exact changes
- **证据**: plan 说该函数接受 `transaction_factory` 参数，用于"重开读事务 recheck"。但未说明 facade 如何构造并注入该 factory。实际代码中 `host._transaction_runner().run_read` 可作为 factory 的基础，但需要包装为 `() -> HostTransaction` 的 callable。
- **风险**: 低。`HostTransactionRunner.run_read` 接受 `HostReadTransactionOperation[T]`（即 `(transaction) -> T`），需要一个 adapter 把 `run_read` 包装为 `transaction_factory`。实现模式清晰，但 plan 未显式说明。
- **建议修正**: 在 Slice 4 data flow 中补充说明 facade 通过 `lambda: host._run_read(lambda txn: txn)` 或等价方式注入 transaction factory。
- **裁决**: `deferred-with-owner` — owner = implementation agent (Slice 4)，不阻塞 plan。

### F6 — 单文件删除失败的结构化错误行为未明确（non-blocking）

- **位置**: plan §8 Slice 4 error handling
- **证据**: plan 说"单文件删除失败不静默吞掉整体（结构化错误/诊断），不破坏已删集合一致性返回"。但未明确：(a) 失败文件是否计入 `reclaimed_artifact_paths`？(b) 错误信息以何种形式返回？(c) 是否需要新增错误字段？
- **风险**: 低。`delete_artifact_file` 使用 `unlink(missing_ok=True)`，最常见的失败（文件已不存在）会静默返回 False。真正的 IO 错误（权限、磁盘）较为罕见。
- **建议修正**: 实现期明确：IO 错误的文件不计入 `reclaimed_artifact_paths`，错误信息通过 logging 或 `HostStorageMaintenanceResult` 新增 `errors: tuple[str, ...]` 字段返回。
- **裁决**: `deferred-with-owner` — owner = implementation agent (Slice 4)，不阻塞 plan。

### F7 — `physical_artifact_bytes` 计算时机与 report 重复（non-blocking）

- **位置**: plan §6.4 `HostStorageMaintenanceResult.physical_artifact_bytes`
- **证据**: `HostStorageUsageReport` 已有 `artifact_logical_bytes`（descriptor payload_size_bytes 求和）。`physical_artifact_bytes` 是 artifact root 实际文件字节和（排除 `.tmp`），需要遍历文件系统。
- **风险**: 极低。logical vs physical 的差异有意义（content-addressed 去重导致 logical ≥ physical）。report 不遍历（符合 §7.1 设计），maintenance 遍历是合理的。
- **建议修正**: 无需修正。在 `HostStorageMaintenanceResult` docstring 中说明 physical 与 logical 的差异含义（去重率）。
- **裁决**: `accepted` — 设计合理，补充 docstring 即可。

---

## 4. Artifact Deletion Proof 安全性审查

plan 的 artifact 删除证明是本 WU 的核心安全原语。逐层审查：

### 4.1 Content-addressed 共享安全性

- **plan 描述**: `artifact_relative_path_is_referenced(transaction, path) -> bool`：`SELECT 1 FROM payload_descriptors WHERE artifact_relative_path = ? LIMIT 1`。
- **验证**: 这是正确的安全原语。`artifact_relative_path` 由内容 digest 决定（`artifact.py:135-147`：`sha256/<shard>/<digest_hex>`），不同 `payload_ref` 若内容相同则指向同一物理文件。查询 `payload_descriptors.artifact_relative_path`（而非 `payload_ref`）覆盖所有 descriptor，杜绝 §4.2 的共享文件误删。
- **结论**: **sound**。

### 4.2 Projection lag 安全性

- **plan 描述**: `collect_referenced_artifact_paths(transaction)` 快照所有存活 descriptor 的非空 `artifact_relative_path`。
- **验证**: 这覆盖**全部**存活 descriptor（含其它 Session 的 descriptor），不依赖 purge 的 `_payload_reference_columns()` 逐列扫描。一个 descriptor 存活即意味着其 `artifact_relative_path` 被引用，无论该 descriptor 是否仍被 timeline / run_results / memory / tool_trace / outbox 引用。
- **结论**: **sound**。plan 的删除证明比 purge 的 `_payload_ref_is_still_referenced` 更保守：purge 只检查 `payload_ref` 是否被引用列引用，plan 检查 `artifact_relative_path` 是否被任何 descriptor 引用。

### 4.3 Publish-before-commit 竞态安全性

- **plan 描述**: grace window + 删除前 recheck。
- **验证**: 流程为 (a) 快照 referenced set → (b) 枚举 on-disk → (c) 差集 → (d) grace 过滤 → (e) recheck → (f) 删除。recheck 步骤（e）重开读事务确认 artifact_relative_path 仍无引用，收敛了 (a)-(d) 期间新 descriptor commit 的竞态。
- **残余风险**: R1 — 若 grace window 内新 descriptor 尚未 commit（事务延迟 > grace），理论上仍可误删。缓解：grace 显著大于最大事务延迟 + 默认 dry-run + operator 控制。
- **结论**: **sound with bounded residual risk**。

### 4.4 Containment 守卫

- **plan 描述**: 复用 `artifact.py` 既有 containment 守卫。
- **验证**: `_validate_relative_path_text`（`artifact.py:168-184`）拒绝空、绝对、`..` 遍历路径。`_ensure_contained`（`artifact.py:245-259`）resolve 后校验 `relative_to(root)`，杜绝 symlink 逃逸。
- **结论**: **sound**。需注意 `delete_artifact_file` 实现时必须调用 `_ensure_contained`（而非只调用 `_ensure_parent_dir_contained`），见 F3。

### 4.5 安全性总结

| 安全维度 | 评估 | 残余风险 |
| --- | --- | --- |
| Content-addressed 共享 | sound | 无 |
| Projection lag | sound | 无 |
| Publish-before-commit 竞态 | sound with bounded residual | R1（grace 缓解） |
| Containment 守卫 | sound | F3 实现期确认 |
| `.tmp` 文件排除 | sound | `iter_published_artifact_relative_paths` 跳过 `.tmp` 子树 |

---

## 5. Public/Internal API 边界审查

### 5.1 分层符合性

- `storage_lifecycle.py` 在 `dayu/host/durable/`（Host 内部 durable 层），只 import durable 层内部模块。✓
- `storage_maintenance.py` 在 `dayu/host/`（Host facade 层），通过 `host._run_read(...)` / `host._transaction_runner()` 访问 durable。✓
- `open_host.py` 的 async wrapper 委托同步 facade，沿用 `_PublicHostHandle` 既有模式。✓
- 不 import service / ui / fins / engine / runtime。✓

### 5.2 Command path 隔离

- `report_storage_usage` 走 `host._run_read(...)`，只读。✓
- `run_storage_maintenance` 不经 admission、不写 canonical facts。✓
- WAL checkpoint 用独立 connection（`host._durable_store.connect()`），不复用 command transaction。✓
- 文件遍历和删除只在 maintenance entrypoint 内执行。✓

### 5.3 与 purge 的边界

- 不修改 `purge_session_durable` 的 SQLite 删除事务语义。✓
- 不删除 `cleanup_refs` 字段（避免触碰 89KB 中心 purge 路径）。✓
- orphan 文件回收由 maintenance 全量扫描取代 purge 逐路径清理。✓

---

## 6. Slice 切分审查

| Slice | 可独立验证 | Allowed files 明确 | Data flow 明确 | Error handling 明确 | Invariants 明确 | Tests 明确 |
| --- | --- | --- | --- | --- | --- | --- |
| S1 — artifact helper | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| S2 — usage report | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| S3 — deletion proof + dry-run | ✓（依赖 S1+S2） | ✓ | ✓ | ✓ | ✓ | ✓ |
| S4 — orphan reclaim | ✓（依赖 S1+S3） | ✓ | ✓ | ✓ | ✓ | ✓ |

- **依赖链**: S1 → S3 → S4，S2 独立于 S1 但被 S3 依赖。依赖关系清晰。
- **每个 slice 的 completion signal**: 均为"测试通过 + pyright 干净"，S4 额外要求"全 §9 验证通过"。
- **slice 间 contract handoff**: S1 产出 `iter_published_artifact_relative_paths` + `delete_artifact_file`；S2 产出 `HostStorageUsageReport` + `_storage_paths`；S3 产出 deletion proof 原语 + `HostStorageMaintenanceRequest/Result` + dry-run maintenance；S4 产出 `reclaim_orphan_artifact_files` + opt-in destructive maintenance。handoff 稳定。

---

## 7. AGENTS.md 合规性审查

| 约束 | 合规 | 备注 |
| --- | --- | --- |
| 中文 docstring | ✓ | plan 要求"全部含中文 docstring" |
| 严格类型 | ✓ | plan 要求 `frozen=True, slots=True`；禁止 `Any` / `object` / 无类型签名 |
| 禁止 extra payload | ✓ | `now` / `grace_seconds` 作为显式参数传入 |
| 禁止魔法数字/字符串 | ✓ | schema 工具 schema 例外；grace 默认值用具名常量 |
| README 触发规则 | ✓ | §10 明确 `dayu/host/README.md` 和 `tests/README.md` 需更新 |
| 测试 + pyright | ✓ | §9 覆盖聚合验证命令和预期断言 |
| 职责分离 | ✓ | §7.7 明确 durable 原语 / containment / facade 分离 |
| 禁止 God object/function | ✓ | 每个函数职责单一 |

---

## 8. 设计真源对齐审查

| 设计真源条目 | plan 对齐 | 备注 |
| --- | --- | --- |
| `design.md:1435-1453` Payload 存储 | ✓ | report / proof 只读既有 descriptor / payload 字段，不改写语义 |
| `design.md:1445` publish-before-commit 残留 | ✓ | plan 实现被承诺但缺失的 cleanup 路径 |
| `design.md` Purge = 唯一 destructive EventLog retention exception | ✓ | 不向 command path 增加 destructive EventLog 行为 |
| Host durable truth vs projection/read model 边界 | ✓ | report 只读 durable truth + 派生 row 计数 |
| 分层 `UI -> Service -> Host -> Engine` | ✓ | 无反向依赖 |
| command path 边界 | ✓ | maintenance 不经 admission、不写 canonical facts |
| `docs/engine/design.md` | ✓ | Engine 无接口耦合，无需 Engine 侧改动 |

**无需修改 `docs/host/design.md` 或 `docs/engine/design.md`**：plan 实现 13.1 已承诺的 cleanup 路径，无设计语义新增。

---

## 9. Residual Risks

| ID | 风险 | 缓解措施 | Owner |
| --- | --- | --- | --- |
| R1 | publish-before-commit 竞态：grace window 内新 descriptor 尚未 commit 时可能误删在途文件 | grace + 删除前 recheck + 默认 dry-run + operator 控制 grace 值 | 当前 WU（grace 缓解） |
| R2 | purge `cleanup_refs` 死字段未清理 | maintenance 全量扫描已覆盖这些 orphan；后续清理不阻塞正确性 | 后续（deferred） |
| R3 | orphan SQLite payload 行回收未实现 | 本 WU 只报告计数；`write_sqlite_payload` 同事务写 descriptor + payload，orphan 行仅来自部分失败/未来 bug | 后续决策（deferred） |
| R4 | 大 artifact root 全量遍历成本 | 隔离在 operator 显式 maintenance entrypoint，不进 command path；report 不遍历 | 当前 WU（design 覆盖） |
| R5 | DB VACUUM 未实现 | 本 WU 只 checkpoint + size 诊断 | 后续 WU（deferred） |

---

## 10. Final Assessment

**plan-review PASS。**

- **blocking findings**: 0
- **non-blocking findings**: 7（F1–F7，均为实现期可自决细节）
- **artifact deletion proof**: sound（content-addressed 共享 / projection lag / grace+recheck / containment 全部通过）
- **public/internal API 边界**: 符合 Host 分层，无反向依赖，maintenance 不进入 command path
- **slice 切分**: code-generation-ready，依赖链清晰，每个 slice 有明确 allowed files / data flow / error handling / invariants / tests
- **AGENTS.md 合规**: 全部通过
- **设计真源对齐**: 全部通过，无需修改 design.md
- **residual risks**: R1–R5 已分类，均有缓解措施或明确 deferred owner

plan 可进入 implementation gate。
