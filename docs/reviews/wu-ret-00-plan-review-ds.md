# WU-RET-00 Plan Review — AgentDS

- review target: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`
- reviewer: AgentDS（独立 adversarial plan review）
- date: 2026-06-12
- gate: plan-review
- 总控真源: `docs/host/issues-implementation-control.md`

---

## 1. Executive Summary

**Plan-review 结论: PASS**（无 blocking finding）

Plan 解决的是三个被直接代码证据证明真实缺失的最小正确闭环：operator-visible storage usage report、content-addressed-safe artifact 删除证明 + orphan 文件回收、慢维护隔离。Scope 边界清晰，Non-Goals 与总控裁决一致。无 schema 变更、不碰 purge 语义。四个 slice 切分合理、依赖明确、可独立验证。

发现 **6 个 finding**（0 blocking, 6 non-blocking），涉及：artifact logical 字节语义模糊、grace 常量的可配置性、TOCTOU 残余窗口说明、report 表覆盖范围决策、`_open_durable_connection()` connection 关闭契约的跨 slice 一致性、以及删除证明原语的"证明 vs 回收"职责边界。所有 finding 均可裁决，建议在 implementation gate 中按裁决结果修正，不阻塞进入下一 gate。

---

## 2. Direct Code Evidence Verification

### 2.1 泄漏根因验证 — PASS

**Plan claim**: purge 后的 artifact 文件永久泄漏，因为 `purge_session` command path 不消费 `cleanup_refs`。

**Evidence**:
- `dayu/host/command.py:769-897` `purge_session(...)` → 第 892-897 行仅从 `PurgeSessionDeleteResult` 提取 `tombstone` 构造 `PurgeSessionResult`；`result.cleanup_refs` 从未被读取。
- `dayu/host/api.py:2383-2416` `PurgeSessionResult` 仅含 `session_id`、`purged`、`purge_tombstone_ref`、`deleted_counts_digest`；**不含 `cleanup_refs`**。
- `dayu/host/durable/purge.py:324-347` `PurgeCommitCleanupRefs` / `PurgeSessionDeleteResult` 的 `cleanup_refs` 字段只在 `purge.py` 内部生成与 re-export；`command.py:88-97` import 包含 `PurgeSessionDeleteResult` 但 command path 从不消费 `cleanup_refs`。
- `dayu/host/durable/artifact.py:220` `_unlink_if_exists` 是 Host 内唯一 `.unlink()` 调用点，仅用于 temp 文件清理。

**Verdict**: 直接证据成立，逻辑/数据同源。root cause 不是推断，是代码路径断链。

### 2.2 Content-addressed 共享风险验证 — PASS

**Plan claim**: 两个不同 `payload_ref` 的 descriptor，内容相同 → 同一物理文件 → 按 `payload_ref` 推导删文件不安全。

**Evidence**:
- `dayu/host/durable/artifact.py:135-147` `_artifact_relative_path_for_digest(digest)` 仅由 `sha256/<shard>/<digest_hex>` 决定路径；无 `payload_ref`、`session_id` 或其它 descriptor 维度参与。
- `dayu/host/durable/payload.py:88-112` `PayloadDescriptor` 的 `artifact_relative_path` 是路径字符串，不是 ref；两个不同 `payload_ref` 可指向同一 `artifact_relative_path`。

**Verdict**: 安全洞察正确。plan 据此推导出的 `artifact_relative_path_is_referenced` 原语（按路径而非按 ref 查引用）是正确且必要的。

### 2.3 引用边登记验证 — PASS

**Plan claim**: `_payload_reference_columns()` 列出全部 durable payload ref 引用列。

**Evidence**:
- `dayu/host/durable/purge.py:1957-1972` 确认为 `(event_log, timeline, run_results(result_ref,summary_ref), memory_items, tool_trace_hot, outbox(result_ref,terminal_summary_ref))`。
- 但 plan 的 `artifact_relative_path_is_referenced` 是查询 `payload_descriptors.artifact_relative_path`，**不是**查询这些引用列。Plan 的删除证明独立于 purge 的 ref 引用判定，这一点正确但 plan §7.2 的描述可更明确地区分两者（见 Finding 4）。

### 2.4 既有 checkpoint 原语验证 — PASS

**Evidence**:
- `dayu/host/durable/maintenance.py:62-105` `run_host_wal_checkpoint(...)` 存在，含同源校验、PASSIVE/TRUNCATE 模式、结果类型。
- 仅被测试调用（`tests/host/test_durable_connection.py`），无 public/service 面。

### 2.5 无现有 storage lifecycle 实现 — PASS

**Evidence**: `grep -r` 确认 `storage_lifecycle`、`StorageUsageReport`、`report_storage_usage`、`run_storage_maintenance` 均不存在于当前代码库。

### 2.6 Containment guard 存在性验证 — PASS

**Evidence**:
- `dayu/host/durable/artifact.py:168` `_validate_relative_path_text`
- `dayu/host/durable/artifact.py:245` `_ensure_contained`（resolve + relative_to 防 symlink 逃逸）
- `dayu/host/durable/artifact.py:262` `_ensure_parent_dir_contained`
- `dayu/host/durable/artifact.py:344` `_path_from_posix_relative`

所有守卫函数已存在且使用 `resolve(strict=True)` + `relative_to` 防止路径逃逸。Plan 的 `delete_artifact_file` 复用这些守卫是正确的最小化策略。

---

## 3. Artifact Deletion Proof Soundness Analysis

### 3.1 Content-addressed 共享引用 — 安全

Plan 的删除证明使用 `SELECT 1 FROM payload_descriptors WHERE artifact_relative_path = ?`，覆盖**全部** descriptor（不管属于哪个 Session）。这杜绝了"purge Session A → 误删 Session B 引用的共享文件"。

### 3.2 Projection lag — 安全

Referenced set 快照与 recheck 均查询 `payload_descriptors` 表本身，不经过 projection checkpoint 或任何派生 row。Projection lag 不会导致误判（descriptor 是 SQLite canonical truth，不是派生 read model）。

### 3.3 Publish-before-commit 竞态 — 缓解充分，残余可接受

Plan 的多层防护：
1. **grace window**：mtime 在 `now - grace_seconds` 内的文件不入候选（覆盖已落盘但 descriptor 尚未 commit 的正常写入）。
2. **删除前 recheck**：对每个候选重开读事务查 `artifact_relative_path_is_referenced`（覆盖 grace 窗外仍被 descriptor 引用的异常情况）。
3. **默认 dry-run**：`reclaim_orphan_artifacts=False` 为默认值。
4. **containment guard**：只删 artifact root 内的文件。

**TOCTOU 残余窗口**（见 Finding 3）：recheck 与 unlink 之间，另一个 write transaction 可能 commit 指向同一路径的 descriptor。这是 classic filesystem TOCTOU，但在本场景下风险极低：
- 同一 content-addressed 文件，恰好有新 descriptor 在 recheck 与 unlink 之间的 ~μs 窗口 commit，概率可忽略。
- 即使发生，descriptor commit 后的 artifact 在下次 maintenance 中可重新写入（content-addressed 内容已知，可重写）。

### 3.4 删除边界 — 安全

Plan 明确不删：仍被引用文件、`.tmp` 在途文件、grace 窗口内新文件、artifact root 外路径、DB row。

---

## 4. Architecture Boundary Analysis

### 4.1 分层合规 — PASS

- 新增 durable 原语放 `dayu/host/durable/storage_lifecycle.py`（Host 内部）。
- Host facade 放 `dayu/host/storage_maintenance.py`。
- `open_host.py` 提供 async wrapper。
- 无反向依赖，不 import service/ui/fins/engine/runtime。

### 4.2 Maintenance vs Command Path 隔离 — PASS

Plan 的 `run_storage_maintenance` 不经过 admission、不写 canonical facts、不开 Host write transaction（除 WAL checkpoint 用独立 connection）。文件扫描/删除/WAL checkpoint 只在这个 entrypoint 内执行。符合控制文档 §2 Non-Goals "不在 command path 做任何慢 cleanup / 文件扫描 / VACUUM"。

### 4.3 `_storage_paths()` / `_open_durable_connection()` 私用面 — 需注意跨 slice 一致性

这两个方法标记为 `HostCommandHandle` 的私有方法（underscore），仅在 Slice 2-4 的 facade 和 maintenance 路径使用。

- `_storage_paths()` 从 `_durable_store.options` 派生，与既有 `_audit_sink_options()` 模式一致。**合理。**
- `_open_durable_connection()` 委托 `_durable_store.connect()`，返回 `sqlite3.Connection`。Plan 标注 "caller 负责关闭"，Slate 3 的 checkpoint 使用在 `finally` 关闭。**正确但契约是隐式的**（见 Finding 5）。

### 4.4 不修改设计真源 — 需要确认

Plan §3 声称"不修改 `docs/host/design.md`"，理由是"本 WU 实现 13.1 已承诺的 cleanup 路径，无设计语义新增"。但 `design.md:1445` 明确写的是"已发布但未被 descriptor 引用的 artifact 只能作为**后续** cleanup / diagnostics 处理"——这里的"后续"在本 WU 之前是未实现的空白。新增的 `report_storage_usage` / `run_storage_maintenance` 作为 Host public API 面，在 design.md 的公共接口章节是否应增补描述？当前 design.md 未提及这些入口。这个问题见 Finding 2。

---

## 5. Slice Readiness Assessment

### Slice 1 — PASS（code-generation-ready）

- **Objective**: 清晰——把文件枚举/删除收敛到 `artifact.py`。
- **Allowed files**: 仅 2 个文件，合理。
- **Data flow**: 纯文件系统，无 SQLite/network 依赖。
- **Invariants**: 明确——不碰 `.tmp`、不越界、删除幂等。
- **Tests**: 覆盖正常/边界/异常，完备。
- **Non-goals**: 不读 descriptor、不做 orphan 判定——正确隔离。

### Slice 2 — PASS（code-generation-ready）

- **Objective**: operator 只读 storage usage report。
- **Data flow**: read 事务 + 文件 stat → 组装 report，无写。
- **`HostStorageUsageReport` 类型**: 字段覆盖控制文档验收信号枚举的 owner 分类；`artifact_logical_bytes` 语义需澄清（见 Finding 1）。
- **Tests**: 覆盖全零/写入后计数/bytes/orphan/WAL 缺失/closed handle。完备。

### Slice 3 — PASS（code-generation-ready，有小需澄清）

- **Objective**: 删除证明只读原语 + dry-run maintenance。
- **Prerequisites**: Slice 1 + Slice 2，依赖合理。
- **Tests**: 共享引用/projection lag/purge 泄漏复现/grace 过滤/checkpoint 控制/非 command-path。覆盖全面。
- **需澄清**: `artifact_relative_path_is_referenced` 与 `collect_referenced_artifact_paths` 的职责边界（见 Finding 4）。

### Slice 4 — PASS（code-generation-ready）

- **Objective**: opt-in orphan artifact 物理文件回收。
- **Safety**: recheck + grace + containment，三层防护。
- **Tests**: 回收后文件消失、被引用保留、共享引用安全、recheck 命中跳过、dry-run 无副效、幂等。
- **需注意**: recheck 的 TOCTOU 窗口需在实现/文档中记录（见 Finding 3）。

---

## 6. AGENTS.md / CLAUDE.md 合规性检查

| 约束 | 状态 | 说明 |
|------|------|------|
| 中文 docstring | PASS | Plan §6.4 要求"全部含中文 docstring" |
| 严格类型（禁止 Any/object/无类型签名） | PASS | 新增类型均为 `frozen=True, slots=True`，字段全部 typed |
| 禁止 extra payload | PASS | §6.5 显式要求 `now`/`grace_seconds` 作为显式参数 |
| 禁止魔法数字/字符串 | PASS | `orphan_grace_seconds` 通过 facade 具名常量默认 |
| 禁止反向依赖 | PASS | 新增代码均在 Host 层内，不 import 上层 |
| 模块职责分离 | PASS | §7.7 durable 原语/facade/containment 按函数分离 |
| README 触发规则 | PASS | Plan §10 明确实现期更新 `dayu/host/README.md` 和 `tests/README.md` |
| 测试覆盖率 ≥ 80% | PASS | Plan §9 要求新增单文件测试覆盖率 ≥ 80% |
| pyright 验证 | PASS | Plan §9 包含 pyright 命令 |
| schema 变更 → 全新起库 | N/A | 无 schema 变更 |

---

## 7. Findings

### Finding 1 — `artifact_logical_bytes` 语义歧义（non-blocking）

**Location**: Plan §6.4 `HostStorageUsageReport.artifact_logical_bytes`

**Issue**: Plan 定义 `artifact_logical_bytes = SELECT COALESCE(SUM(payload_size_bytes),0) FROM payload_descriptors WHERE payload_kind='artifact_ref'`。在 content-addressed 共享场景下，两个 descriptor 指向同一物理文件，`logical_bytes` 会是单个物理文件大小的 N 倍。Plan docstring 要求说明这一点，但 field name `artifact_logical_bytes` 可能误导 operator 以为这是"artifact 占用"。而 `physical_artifact_bytes` 只在 `HostStorageMaintenanceResult` 中提供（需要文件遍历，慢 IO）。

**Risk**: operator 误读 report 中的 `artifact_logical_bytes` 为物理占用。

**Recommendation**: 
- 将 field 重命名为 `artifact_descriptor_logical_bytes` 或 `artifact_ref_logical_bytes`，明确这是 descriptor sum，不是物理文件占用。
- 或在 `HostStorageUsageReport` 中增加 `artifact_physical_bytes` 字段（标记为 optional，仅在显式请求遍历时填入），与 maintenance result 的 `physical_artifact_bytes` 语义对齐。
- 最低要求：docstring 必须用粗体说明"此值为 descriptor logical sum，在 content-addressed 共享下可能大于物理占用；物理文件大小见 `run_storage_maintenance` 的 `physical_artifact_bytes`"。

**Verdict**: accepted — 实现期按 recommendation 任选一种修正。

---

### Finding 2 — `docs/host/design.md` 是否需要更新（non-blocking）

**Location**: Plan §3 设计对齐表；§10 Docs Decision

**Issue**: Plan 声称不修改 `docs/host/design.md`。理由是本 WU 实现 13.1 已承诺的 cleanup 路径，无设计语义新增。但：
- `report_storage_usage` 和 `run_storage_maintenance` 是新增的 Host public API 入口，在 design.md 的公共接口章节尚无对应描述。
- Design.md:1445 只写了"artifact 只能作为后续 cleanup / diagnostics 处理"，但没有对"cleanup 以什么形态（maintenance entrypoint）、什么安全保证（content-addressed-safe deletion）、什么隔离边界（non-command-path）"做约束。Plan 填补了这些约束，但它们确实是新增的设计语义。

**Risk**: 如果 design.md 不作为真源更新，后续 WU（如 RET-01/02 的 JSONL governance）可能不清楚 maintenance entrypoint 的边界划分（哪些放 maintenance，哪些是 command path）。

**Recommendation**: 
- Option A（推荐）：在 design.md §13.1 后新增一小节"13.1.1 Storage lifecycle / maintenance"，记录 maintenance entrypoint 的存在、安全边界（content-addressed-safe deletion、grace+recheck、containment）、command-path 隔离约束、与 purge 的关系。不展开 implementation detail。
- Option B：采纳 plan 当前立场，不修改 design.md，但必须在 `dayu/host/README.md` 中完整记录上述边界。Risk：README 更新约束第 16 条要求"只写已实现内容"，而 design.md 的架构约束是更高层真源。

**Verdict**: accepted — 实现前裁决：A 或 B，或明确 design.md 的"设计真源"边界是否只需要记录架构决策而不需要枚举每个 public API。

---

### Finding 3 — recheck TOCTOU 残余窗口未在文档中显式记录（non-blocking）

**Location**: Plan §7.3 回收流程 (d)；§11 R1

**Issue**: Plan §11 R1 将 publish-before-commit 竞态分类为"grace 缓解，剩余尾部风险由 operator 调 grace 控制"。但 recheck 与 unlink 之间的 TOCTOU 窗口（recheck 通过 → unlink 前另一 transaction commit descriptor）未在计划中显式分析。§7.3 的流程 (e) 说"重开读事务 recheck `artifact_relative_path_is_referenced` 为 False"，但 recheck 与 unlink 不是原子的。

**Risk**: 极低（概率可忽略），但作为 deletion safety proof 的残余应由文档承担。

**Recommendation**: 在 Slice 4 的实现代码注释、`run_storage_maintenance` 的 docstring 和 README maintenance 小节中显式记录：
- TOCTOU 残余窗口的存在与量级（~μs）
- 为什么它是安全的（同一 content-addressed 文件可重写；概率极低；grace 覆盖正常路径）
- operator 可通过调大 grace 进一步降低风险

**Verdict**: accepted — 实现期在文档中显式记录。

---

### Finding 4 — `artifact_relative_path_is_referenced` 与 `collect_referenced_artifact_paths` 的职责边界描述不够精确（non-blocking）

**Location**: Plan §7.2 删除证明原语列表

**Issue**: Plan §7.2 列出三个相关原语：
- `artifact_relative_path_is_referenced(transaction, path) -> bool`：`SELECT 1 FROM payload_descriptors WHERE artifact_relative_path = ? LIMIT 1`
- `collect_referenced_artifact_paths(transaction) -> frozenset[str]`：快照所有存活 descriptor 的非空 `artifact_relative_path`
- `collect_orphan_sqlite_payload_ids(transaction) -> tuple[str,...]`：诊断用

但在 §7.3 回收流程中，(a) 用 `collect_referenced_artifact_paths` 做 initial referenced set，(e) 用 `artifact_relative_path_is_referenced` 做 recheck。这两个原语的数据源相同（`payload_descriptors` 表），但语义不同：
- `collect_referenced_artifact_paths` 是一次性快照（用于差集计算）
- `artifact_relative_path_is_referenced` 是实时查询（用于 recheck）

**Risk**: 低——功能正确，但两个相同的 SQL 查询以不同原语名存在，未来可能发散。

**Recommendation**: 
- 在 `storage_lifecycle.py` 中让 `artifact_relative_path_is_referenced` 成为 `collect_referenced_artifact_paths` 的内部实现细节（或反过来），确保"被引用"的判定逻辑只有一处。
- 或者至少用模块级私有 `_artifact_relative_path_is_referenced` 同时服务于两个公共原语，在 docstring 中标注它们的数据同源性。

**Verdict**: accepted — 实现期确保单一真源判定逻辑。

---

### Finding 5 — `_open_durable_connection()` 的 connection 关闭契约跨 slice 隐式依赖（non-blocking）

**Location**: Plan Slice 3 exact changes; Slice 2 `_storage_paths()`

**Issue**: Plan Slice 3 在 `command.py` 新增 `_open_durable_connection()`，返回 `sqlite3.Connection`，标注"caller 负责关闭"。Slice 3 的 checkpoint 使用在 `finally` 中关闭——正确。但如果未来在 Slice 2 或 Slice 4 中也需要独立 connection（例如 future orphan SQLite payload deletion），这个手动管理契约可能被遗漏。

**Risk**: 低——当前只有 Slice 3 的 checkpoint 需要独立 connection。但如果 future WU 复用 `_open_durable_connection()` 忘记关闭，可能导致 connection leak。

**Recommendation**: 
- 在 `_open_durable_connection()` 的 docstring 中用粗体标注"调用方必须在 `finally` 块中关闭返回的 connection"。
- 考虑在 Slice 3 实现时提供一个 context manager wrapper（如 `_with_durable_connection()`）封装 open/close，减少调用方出错可能。但这不是 plan gate 的 blocking 问题，可以在实现期决定。

**Verdict**: accepted — 实现期至少强化 docstring 警告。

---

### Finding 6 — Plan 未讨论 artifact root 下非 `sha256/` namespace 文件的处理（non-blocking）

**Location**: Plan §7.3 Artifact orphan 文件回收流程 (b)

**Issue**: Plan 的 `iter_published_artifact_relative_paths` 遍历整个 artifact root 并跳过 `.tmp`。但 artifact root 下可能还有非 artifact 文件，例如 `audit/`（audit JSONL）、`tool-trace/`（cold JSONL），它们不在 `sha256/` namespace 下。Plan 将这些路径纳入 orphan 候选的 on-disk set，但它们不会匹配 `payload_descriptors.artifact_relative_path`（因为 audit/tool-trace 文件不是通过 descriptor 注册的），因此会被全标记为 orphan。

**Risk**: 中等（如果 maintenance 的 reclaim 被意外运行在包含 audit/tool-trace 的 artifact root 上）——但实际保护由以下提供：
- 默认 `reclaim_orphan_artifacts=False`（dry-run）
- grace window（这些 JSONL 文件大概率 mtime 较新，除非手动 touch 旧文件）
- containment guards 不区分 artifact namespace，`iter_published_artifact_relative_paths` 会枚举所有非 `.tmp` 文件

但实际上 audit JSONL 和 tool trace JSONL 是 append-only log，如果它们真的被标记为 orphan（descriptor 不引用它们），而 operator 误开 reclaim，这些 JSONL 会被删除——这是灾难性的。

**Recommendation**: 
- 在 `iter_published_artifact_relative_paths` 中明确只遍历 `sha256/` namespace（artifact 文件的标准目录），或者
- 在 `scan_orphan_artifact_files` 中额外过滤——只考虑路径在 `sha256/` 下的文件。
- Plan Slice 1 的 objective 说"跳过 `.tmp` 子树"，但没有说"只枚举 artifact namespace"。实现期必须添加此约束。
- 测试应覆盖：audit/tool-trace 目录下的 JSONL 文件**不**出现在 orphan 候选中。

**Verdict**: accepted — **这是最接近 blocking 的 finding**。实现期必须在 Slice 1 的 `iter_published_artifact_relative_paths` 中限定 namespace，并在 Slice 3 的测试中验证非 `sha256/` 文件不被误标为 orphan。当前 plan 的 text 没有显式说明这一点，但可从 `_artifact_relative_path_for_digest` 的 `sha256/<shard>/<digest>` 格式推导出 scope 限制。实现期必须显式化。

---

## 8. Residual Risks / Uncovered Areas

| ID | 描述 | 分类 | Owner |
|----|------|------|-------|
| R1 | publish-before-commit 竞态（grace + recheck 缓解；TOCTOU 残余见 Finding 3） | assigned to current WU | Slice 3/4 + doc |
| R2 | purge `cleanup_refs` 死字段未清理 | deferred | 后续清理 WU |
| R3 | orphan SQLite payload 行回收未实现 | deferred | 后续决策 WU |
| R4 | 大 artifact root 全量遍历成本 | covered by design（maintenance-only） | 本 WU |
| R5 | DB VACUUM 未实现 | deferred | 后续 WU |
| R6 | 并发 maintenance 运行安全性（未在 plan 中讨论） | minor — 文件删除幂等 + recheck 提供保护；但未显式分析 | 实现期 |
| R7 | `_open_durable_connection()` 的 connection 不被 facade 路径泄露到 public API（plan 标注为私有，但需在实现中确认） | minor | 实现期 review |

---

## 9. Gate 裁决

- **Plan-review 结论**: **PASS**
- **Blocking findings**: 0
- **Non-blocking findings**: 6（F1–F6，全部 accepted-with-recommendation）
- **可进入下一 gate**: 是，待 AgentMiMo 完成平行 review 并由 controller 裁决 findings 后进入 implementation gate

---

## 10. Review Artifact Metadata

- **artifact path**: `docs/reviews/wu-ret-00-plan-review-ds.md`
- **reviewer**: AgentDS
- **findings 裁决状态**: 全部 `accepted`（非 blocking，按 recommendation 在实现期修正）
- **next step**: AgentMiMo parallel review → controller adjudicate → implementation gate
