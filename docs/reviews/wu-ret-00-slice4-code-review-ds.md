# WU-RET-00 Slice 4 Code Review — AgentDS

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: code review
- slice: Slice 4 opt-in orphan artifact reclaim
- reviewer: AgentDS
- artifact path: `docs/reviews/wu-ret-00-slice4-code-review-ds.md`
- design source: `docs/host/design.md`, `docs/engine/design.md`
- control source: `docs/host/issues-implementation-control.md`
- accepted plan: `docs/host/wu-ret-00-storage-lifecycle-retention-plan.md`
- implementation report: `docs/reviews/wu-ret-00-slice4-implementation-codex.md`

## 审查范围

- `dayu/host/durable/storage_lifecycle.py`
- `dayu/host/storage_maintenance.py`
- `tests/host/test_storage_maintenance.py`
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`

## 已验证证据

- `pytest tests/host/test_storage_maintenance.py -q` => 9 passed
- `pytest tests/host/test_artifact_store.py tests/host/test_storage_usage_report.py tests/host/test_storage_orphan_proof.py tests/host/test_purge_session.py -q` => 56 passed
- `pyright dayu/host/durable/storage_lifecycle.py dayu/host/storage_maintenance.py tests/host/test_storage_maintenance.py` => 0 errors
- `git diff --check` => passed

## 逐项审查

### 1. Destructive Safety

**审查结论：PASS，无缺陷。**

证据：

1. **只删除 sha256/ namespace 文件**：`scan_orphan_artifact_files` (storage_lifecycle.py:449) 只通过 `iter_published_artifact_relative_paths` 枚举 `artifact_root/sha256` 内容寻址 namespace，该函数 (artifact.py:136-164) 硬编码只遍历 `sha256/` 目录、跳过 `.tmp` 子树、跳过 symlink，对每个 entry 执行 `_ensure_contained` 逃逸校验。

2. **只删除 recheck 仍 orphan 的文件**：`reclaim_orphan_artifact_files` (storage_lifecycle.py:486-487) 在对每个 candidate 执行 `delete_artifact_file` 前，先调用 `is_artifact_path_referenced(relative_path)` recheck；返回 `True` 则 `continue` 跳过。

3. **只删除 grace window 外的文件**：`scan_orphan_artifact_files` (storage_lifecycle.py:452) 检查 `artifact_path.stat().st_mtime <= cutoff_timestamp`，其中 `cutoff_timestamp = now.timestamp() - grace_seconds` (line 447)。

4. **containment 守卫**：`delete_artifact_file` (artifact.py:167-197) 对最终文件路径执行 `_ensure_contained(artifact_root, final_path)` (line 191) 与 `_validate_published_artifact_relative_path` (line 183)，双重校验路径在 `sha256/` namespace 内且不逃逸 root。

5. **绝不删除的文件类别**：
   - 被引用文件：recheck 命中 → skip (storage_lifecycle.py:486-487)
   - shared reference 文件：`collect_referenced_artifact_paths` (storage_lifecycle.py:386-416) 收集所有存活 descriptor 的非空 `artifact_relative_path` 做 frozenset，不去重同一路径 → 只要任一 descriptor 引用就保留
   - `.tmp` 文件：`iter_published_artifact_relative_paths` 不枚举 (artifact.py:316)
   - audit/tool-trace 文件：路径不在 `sha256/` namespace (artifact.py:261-263)
   - 非 sha256/ 路径：`_validate_published_artifact_relative_path` 拒绝 (artifact.py:261-263)
   - root 外路径：`_ensure_contained` 拒绝 (artifact.py:361-364)

6. **DB row 不变**：`delete_artifact_file` 是纯文件系统操作 (artifact.py:192)；maintenance 路径不写任何 SQL DELETE/UPDATE。测试断言 `after_usage.payload_descriptor_rows == before_usage.payload_descriptor_rows` 与 `after_usage.event_log_rows == before_usage.event_log_rows` (test_storage_maintenance.py:408-409)。

### 2. Recheck Callable 边界

**审查结论：PASS，无缺陷。**

证据：

1. `reclaim_orphan_artifact_files` 接收 `is_artifact_path_referenced: Callable[[str], bool]` (storage_lifecycle.py:462)。这是一个纯函数签名，不依赖任何 Host/durable 内部类型。

2. facade 侧 `_ArtifactPathReferenceChecker` (storage_maintenance.py:374-391) 持有 `HostCommandHandle`，通过 `self.host._run_read(_ArtifactPathReferencedOperation(relative_path))` 为每个 candidate 打开独立 read transaction 执行复查。

3. `_ArtifactPathReferencedOperation` (storage_maintenance.py:355-371) 是 `HostTransaction -> bool` 的 callable，内部调用 `artifact_relative_path_is_referenced(transaction, self.relative_path)`。

4. 没有任何 `HostTransaction` 对象、transaction factory 或 `_run_read` 引用通过 `reclaim_orphan_artifact_files` 的接口泄漏到 durable helper 外部。callable 在 facade 层闭包 `HostCommandHandle`，durable 层只看到一个 `(str) -> bool`。

### 3. `reclaim_orphan_artifact_files` 行为

**审查结论：PASS，无缺陷。**

证据：

1. **逐候选 recheck** (storage_lifecycle.py:486-487)：每个 candidate 在删除前调用 `is_artifact_path_referenced(relative_path)`。测试 `test_storage_maintenance_reclaim_recheck_hit_skips_delete` (test_storage_maintenance.py:450-479) 通过注入在 recheck 内写入 descriptor 的 callable 证明命中引用时文件不被删除。

2. **使用 `delete_artifact_file` 删除** (storage_lifecycle.py:489)：调用 Slice 1 的 containment-guarded 删除 helper。

3. **删除失败进入 file_errors** (storage_lifecycle.py:490-498)：`HostArtifactWriteError` 被捕获，转换为 `DurableArtifactFileError(path, operation, message)`，加入 `file_errors` 列表，`continue` 处理下一个候选。测试 `test_storage_maintenance_reclaim_file_error_keeps_processing` (test_storage_maintenance.py:482-531) 通过 monkeypatch 注入单文件失败，证明失败文件不进入 `reclaimed_paths`、其它候选继续处理。

4. **失败文件不进入 reclaimed** (storage_lifecycle.py:499-500)：`reclaimed_paths.append(relative_path)` 只在 `deleted` 为 `True` 时执行；异常路径 `continue` 跳过此行。

5. **非单文件可恢复异常透传** (storage_lifecycle.py:478-479)：docstring 明确 "recheck callable 或删除 helper 抛出非单文件可恢复错误时透传"；代码只捕获 `HostArtifactWriteError`，其它异常自然传播。

6. **`delete_artifact_file` 返回 `False` 时的行为** (artifact.py:189-190 + storage_lifecycle.py:499)：若文件在 scan 与 delete 之间已被其它进程删除，`os.path.lexists` 返回 `False`，`delete_artifact_file` 返回 `False`，路径既不进入 `reclaimed_paths` 也不进入 `file_errors`。这实现了正确的幂等语义——已被删除的文件无害跳过。

### 4. Dry-run 默认

**审查结论：PASS，无缺陷。**

证据：

1. `HostStorageMaintenanceRequest.reclaim_orphan_artifacts: bool = False` (storage_maintenance.py:59)。

2. `_reclaim_orphan_artifacts_if_requested` (storage_maintenance.py:421-422)：`if not request.reclaim_orphan_artifacts: return _MaintenanceReclaimResult(reclaimed_paths=(), file_errors=())`。

3. 测试 `test_storage_maintenance_dry_run_reports_candidates_without_deleting` (test_storage_maintenance.py:309-353) 验证：`orphan_artifact_candidates == (orphan_path,)`、`reclaimed_artifact_paths == ()`、`file_errors == ()`、文件仍存在。

### 5. DB Row 不变

**审查结论：PASS，无缺陷。**

证据：

1. 所有 maintenance 路径不执行 SQL DELETE/UPDATE。`delete_artifact_file` 是纯文件系统操作 (artifact.py:192)。

2. `run_storage_maintenance` 的 read transaction (`_ReadStorageMaintenanceStateOperation`, storage_maintenance.py:333-352) 只执行 `SELECT`。

3. 测试断言：
   - `test_storage_maintenance_dry_run_reports_candidates_without_deleting` line 350-351: `after_usage.event_log_rows == before_usage.event_log_rows`、`after_usage.payload_descriptor_rows == before_usage.payload_descriptor_rows`
   - `test_storage_maintenance_reclaim_true_deletes_orphan_without_db_row_changes` line 408-409: 同上
   - Session/Run 状态不变 (line 352-353, 410-411)

### 6. Residual TOCTOU 文档

**审查结论：PASS，无缺陷。**

证据：

1. `storage_lifecycle.py` `reclaim_orphan_artifact_files` docstring (lines 469-471): "recheck 与 unlink 之间仍存在极短 TOCTOU 窗口；maintenance 默认 grace window、content-addressed artifact 可重写性与 containment 守卫共同降低风险。"

2. `storage_maintenance.py` `run_storage_maintenance` docstring (lines 244-246): "recheck 与 unlink 之间仍存在极短 TOCTOU 窗口；默认 grace、content-addressed artifact 可重写性与 containment-guarded delete 用于降低风险。"

3. `dayu/host/README.md` Storage Maintenance 节 (line 431): "recheck 与 unlink 之间仍有极短 TOCTOU 窗口；默认 grace、content-addressed artifact 可重写性与 containment-guarded delete 用于降低风险。"

4. Accepted plan §7.3 明确记录该残余 TOCTOU 为已知风险，且缓解措施（grace + recheck + content-addressed 可重写性 + containment）已全部落地。三处文档与 plan 一致。

### 7. 测试覆盖

**审查结论：PASS，无缺陷。**

| 测试 | 覆盖场景 | 文件:行 |
|---|---|---|
| `test_storage_maintenance_dry_run_reports_candidates_without_deleting` | dry-run 不删除、候选正确、非 artifact 文件不入候选、DB row/状态不变 | test_storage_maintenance.py:309-353 |
| `test_storage_maintenance_wal_checkpoint_true_returns_result` | 默认 WAL checkpoint 返回诊断 | test_storage_maintenance.py:356-368 |
| `test_storage_maintenance_reclaim_true_deletes_orphan_without_db_row_changes` | opt-in 成功删除 orphan、保留被引用文件、DB row/状态不变 | test_storage_maintenance.py:371-411 |
| `test_storage_maintenance_reclaim_keeps_shared_referenced_artifact` | shared reference：两个 descriptor 指向同一 artifact，删一个后文件仍被保留 | test_storage_maintenance.py:414-447 |
| `test_storage_maintenance_reclaim_recheck_hit_skips_delete` | recheck 命中：scan 后写入新 descriptor，recheck 返回 True 跳过删除 | test_storage_maintenance.py:450-479 |
| `test_storage_maintenance_reclaim_file_error_keeps_processing` | 单文件删除失败：失败文件进 file_errors，其它候选继续，失败文件不进入 reclaimed | test_storage_maintenance.py:482-531 |
| `test_storage_maintenance_reclaim_is_idempotent` | 幂等：连续两次 reclaim，第二次无候选无错误 | test_storage_maintenance.py:535-558 |
| `test_open_host_async_handle_runs_storage_maintenance_dry_run` | async handle 暴露 maintenance 入口 | test_storage_maintenance.py:561-573 |
| `test_open_host_run_storage_maintenance_fails_after_close` | handle 关闭后 maintenance 抛错 | test_storage_maintenance.py:576-587 |

全覆盖矩阵：
- ✅ 成功删除 orphan
- ✅ 被引用文件保留
- ✅ Shared reference 保留
- ✅ Recheck 命中跳过
- ✅ 单文件删除失败继续
- ✅ Dry-run 不删除
- ✅ 幂等
- ✅ WAL checkpoint
- ✅ Async handle / closed handle

### 8. 文档边界

**审查结论：PASS，无缺陷。**

`dayu/host/README.md` Storage Maintenance 节 (lines 422-432):
- ✅ 只描述已实现的 opt-in reclaim
- ✅ 明确 dry-run 默认
- ✅ 明确不删除 SQLite row / orphan SQLite payload row / VACUUM / scheduler
- ✅ 明确 audit JSONL、tool-trace JSONL、.tmp 不参与 candidate
- ✅ 无 scheduler / VACUUM / JSONL retention 描述

`tests/README.md` (line 162):
- ✅ 准确描述测试覆盖范围

`docs/host/design.md`:
- ✅ 本次 Slice 4 无新增 design.md 变更（design.md 的 maintenance 描述已在 Slice 3 完成）

### 9. AGENTS.md 合规

**审查结论：PASS，1 个 deferred finding。**

| 检查项 | 结果 |
|---|---|
| 中文 docstring | ✅ 所有新增函数/类/模块有完整中文 docstring |
| 严格类型 | ✅ 无 `Any`、`object`、无类型参数、无类型返回值 |
| 无 getattr/hasattr | ✅ 未使用 |
| 无兼容性 facade | ✅ 全新代码，无兼容 re-export/wrapper |
| 无过度设计 | ✅ 最小正确闭环；无 scheduler/VACUUM/JSONL governance |
| 职责分离 | ✅ durable 原语与 facade 编排分离；数据处理/存储/工具调用分离 |
| 禁止 God object/function/dataclass | ✅ 每个 dataclass/function 职责单一 |
| 禁止魔法数字/字符串 | ✅ `_RECLAIM_ARTIFACT_OPERATION` 具名常量；`DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS` 具名常量 |
| 无隐式依赖 | ✅ `now: datetime` 作为显式参数传入，facade 注入 `datetime.now(UTC)` |

## Findings

### Finding DS-F01 — Duplicate private validation helpers (Medium, Code Smell)

- **file/line**: `dayu/host/durable/storage_lifecycle.py:685-727` 与 `dayu/host/storage_maintenance.py:533-574`
- **status**: accepted
- **evidence**: `_require_string_tuple`、`_require_non_empty_text`、`_require_non_negative_int` 三个私有 helper 在 `storage_lifecycle.py` (durable 层) 和 `storage_maintenance.py` (facade 层) 中完全重复，每对约 7-10 行。
- **severity**: Medium — 不影响正确性，但违反 CLAUDE.md "重复逻辑必须抽取" 原则。
- **analysis**: 两个模块分别在 `dayu/host/durable/` 和 `dayu/host/` 子包中，属于不同层。当前每个 helper 体量极小（~7 行），抽取到共享位置（如 `dayu/host/durable/` 内私有 `_validation.py` 或 `dayu.runtime`）可能构成过度工程。当前重复不会导致发散风险（语义相同、变更同步概率低），且 plan 已明确 "优先最小化满足需求"。
- **recommendation**: deferred-with-owner。若后续 slice 或 work unit 新增第三个使用点，应抽取到共享私有模块；当前不阻塞 slice commit。

### Finding DS-F02 — `_require_non_empty_text` 使用 `strip()` 而非长度检查 (Info, Design Choice)

- **file/line**: `dayu/host/durable/storage_lifecycle.py:726`, `dayu/host/storage_maintenance.py:574`
- **status**: accepted
- **evidence**: `_require_non_empty_text` 用 `value.strip() == ""` 判断空字符串，将纯空白字符串也视为空。对 `DurableArtifactFileError.path` / `operation` / `message` 字段而言，纯空白字符串确实无意义。
- **severity**: Info — 设计选择，符合语义。
- **recommendation**: 接受当前实现。若未来 `path` 字段可能合法包含空白字符，再讨论调整；当前业务场景不成立。

## Adversarial Failure Pass

以 adversarial reviewer 视角主动构造以下 failure scenario，逐一验证代码行为：

### Scenario 1: recheck 返回后、unlink 前 descriptor 写入
- **攻击面**: TOCTOU race — recheck 返回 False，但在 `delete_artifact_file` 执行 `unlink` 前，另一个 write transaction 提交了同一路径的 descriptor。
- **代码行为**: unlink 执行，文件被删。但 content-addressed 路径下同一内容可重新发布；grace window 保证文件已足够旧。TOCTOU 窗口为微秒级。
- **结论**: 计划已接受此残余风险 (R1)，当前实现正确降险。

### Scenario 2: symlink 逃逸攻击
- **攻击面**: 攻击者在 `sha256/` 目录下放置指向 root 外路径的 symlink。
- **代码行为**: `iter_published_artifact_relative_paths` 对每个 entry 执行 `_ensure_contained` (artifact.py:318)；symlink 的 `resolve(strict=True)` 会解析到真实路径，`relative_to(root)` 失败 → `HostArtifactWriteError`。
- **结论**: 安全。

### Scenario 3: `..` 目录穿越路径注入
- **攻击面**: candidate 列表包含 `sha256/../../etc/passwd` 路径。
- **代码行为**: `delete_artifact_file` 调用 `_validate_relative_path_text` (artifact.py:248) → `".." in path.parts` 检测 → `HostDurableError` → 转换为 `HostArtifactWriteError` → 被 `reclaim_orphan_artifact_files` 捕获进入 `file_errors`。
- **结论**: 安全，且不中断其它候选处理。

### Scenario 4: 并发 reclaim 导致同一文件被两次 delete
- **攻击面**: 两个 maintenance 实例同时 reclaim 同一候选集。
- **代码行为**: 第一个实例删除成功。第二个实例 recheck 仍为 False，`delete_artifact_file` 中 `lexists` 返回 `False` → 返回 `False` → 不进入 `reclaimed_paths`，也不抛错。
- **结论**: 幂等安全。

### Scenario 5: DB connection 在 recheck 中途失败
- **攻击面**: `host._run_read(...)` 因 SQLite busy/locked 抛 `HostDurableError`。
- **代码行为**: 异常从 `_ArtifactPathReferenceChecker.__call__` 经 `reclaim_orphan_artifact_files` 的 for 循环传播（未被 `except HostArtifactWriteError` 捕获），最终被 `run_storage_maintenance` 的外层 `except HostDurableError` 捕获并转换为 `HostApiError(INTERNAL_ERROR)`。
- **结论**: 正确 fail-fast，不静默跳过。

## 综合结论

**PASS** — 当前 slice 无 blocking finding。

### 统计

- Total findings: 2
- Blocking: 0
- Accepted: 1 (DS-F01 duplicate helpers, medium)
- Accepted info: 1 (DS-F02 strip semantics, info)

### 验证摘要

| 验证项 | 结果 |
|---|---|
| destructive safety（7 条 invariants） | PASS |
| recheck callable 边界（4 条检查） | PASS |
| `reclaim_orphan_artifact_files` 行为（6 条检查） | PASS |
| dry-run 默认 | PASS |
| DB row 不变 | PASS |
| residual TOCTOU 文档 | PASS |
| 测试覆盖（9 场景） | PASS |
| 文档边界 | PASS |
| AGENTS.md 合规 | PASS (1 deferred) |
| Adversarial failure pass（5 scenarios） | PASS |

### 未覆盖风险（已由 accepted plan / prior slice 跟踪）

- **R1 publish-before-commit TOCTOU**: 当前通过 grace + recheck + content-addressed + containment 缓解；尾部风险由 operator 调 grace 控制。
- **R2 purge `cleanup_refs` 死字段**: 不影响正确性；maintenance 扫描覆盖这些 orphan。
- **R3 orphan SQLite payload row**: 仅报告计数不删除；后续 work unit 决策。
- **R5 DB VACUUM**: deferred to GitHub Issue #76。
- **R6 非 sha256/ namespace**: 已通过 `iter_published_artifact_relative_paths` 实现 + 测试覆盖。
