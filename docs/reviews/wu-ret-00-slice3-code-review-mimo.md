# WU-RET-00 Slice 3 Code Review — AgentMiMo

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: code review
- slice: Slice 3 — 删除证明只读原语 + maintenance dry-run
- reviewer: AgentMiMo
- artifact path: `docs/reviews/wu-ret-00-slice3-code-review-mimo.md`
- review date: 2026-06-12

## Review Scope

Review target files:
- `dayu/host/durable/storage_lifecycle.py`
- `dayu/host/storage_maintenance.py`
- `dayu/host/command.py`
- `dayu/host/open_host.py`
- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `tests/host/test_storage_orphan_proof.py`
- `tests/host/test_storage_maintenance.py`
- `tests/host/test_package_exports.py`
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`

## Review Dimensions

### 1. Slice 3 Boundary Compliance

**结论：PASS**

| 边界约束 | 验证结果 | 证据 |
|---|---|---|
| dry-run 不删除文件 | ✅ | `run_storage_maintenance` 默认 `reclaim_orphan_artifacts=False`，`reclaimed_artifact_paths` 始终为 `()`。无 `unlink` / `delete` / `remove` 调用。 |
| 不删 row | ✅ | maintenance 路径无 `DELETE` SQL。只执行 `SELECT COUNT(*)`、`SELECT SUM(...)`、`SELECT artifact_relative_path`。 |
| 不 VACUUM | ✅ | 无 `VACUUM` / `incremental_vacuum` / `auto_vacuum` 调用。 |
| 不 scheduler | ✅ | maintenance 不触碰 `HostDispatchScheduler`、`ActiveWorkerRegistry` 或任何 wakeup port。 |
| `reclaim_orphan_artifacts=True` fail fast | ✅ | `storage_maintenance.py:246-251` 在任何扫描或删除逻辑前抛出 `UNSUPPORTED_OPERATION`。测试 `test_storage_maintenance_reclaim_true_fails_fast_without_deleting` 验证 fail fast 后文件和 row 不变。 |

### 2. Reference Proof Source

**结论：PASS**

- `artifact_relative_path_is_referenced` (`storage_lifecycle.py:281-308`)：只查询 `payload_descriptors` 中 `payload_kind = PayloadKind.ARTIFACT_REF` 且 `artifact_relative_path` 完全匹配的行。
- `collect_referenced_artifact_paths` (`storage_lifecycle.py:311-341`)：只收集 `payload_kind='artifact_ref'` 且 `artifact_relative_path IS NOT NULL` 的 descriptor。
- 两个函数都不解析 audit JSONL、tool-trace JSONL、EventLog payload JSON 或任何其它内部治理标签。
- docstring 明确声明证明来源边界。

### 3. Shared Descriptor / Projection Lag / Missing Descriptor

**结论：PASS**

| 场景 | 处理方式 | 测试覆盖 |
|---|---|---|
| shared descriptor（两个 descriptor 指向同一 artifact） | `collect_referenced_artifact_paths` 返回 `frozenset`，自动去重 | `test_collect_referenced_artifact_paths_deduplicates_shared_descriptors` |
| projection lag（descriptor 存活但 EventLog 事件可能已 purge） | 证明只检查 `payload_descriptors` 存在性，不检查 EventLog 引用 | `test_descriptor_with_durable_event_reference_keeps_artifact_referenced` |
| missing descriptor（无 descriptor 引用该路径） | `artifact_relative_path_is_referenced` 返回 `False` | `test_artifact_relative_path_reference_uses_descriptor_truth` 中的 `missing` 断言 |

### 4. Orphan Scan Namespace / Grace / Sorting

**结论：PASS**

- **namespace 安全**：`scan_orphan_artifact_files` 使用 `iter_published_artifact_relative_paths`，只枚举 `artifact_root/sha256/` 下的已发布普通文件。`.tmp`、`audit/`、`tool-trace/` 和其它非 `sha256/` 文件不会进入候选。
- **grace 判断**：`artifact_path.stat().st_mtime <= cutoff_timestamp` 排除 mtime 在 grace 窗口内的文件。
- **排序确定**：`tuple(sorted(candidates))` 保证输出稳定。
- **测试**：`test_scan_orphan_artifact_files_filters_namespace_grace_and_sorts` 创建 `.tmp/temp-file`、`audit/audit.jsonl`、`tool-trace/trace.jsonl` 和 grace 内新文件，验证它们都不进入候选。

### 5. `physical_artifact_bytes` 语义

**结论：PASS**

- 只统计 `sha256/` namespace 下已发布 artifact 文件的 `stat().st_size` 之和。
- 排除 `.tmp`、audit JSONL、tool-trace JSONL 和其它非 descriptor-managed namespace。
- docstring 清晰说明包含与排除范围。
- README 使用"已发布 artifact 物理字节和"表述，与代码一致。
- 测试 `test_physical_artifact_bytes_counts_only_published_sha256_files` 验证排除非 artifact 文件。

### 6. WAL Checkpoint

**结论：PASS**

| 要求 | 验证结果 | 证据 |
|---|---|---|
| 独立 connection | ✅ | `_run_wal_checkpoint_if_requested` 调用 `host._open_durable_connection()`，委托 `_durable_store.connect()` |
| finally 关闭 | ✅ | `finally: if connection is not None: connection.close()` (`storage_maintenance.py:373-375`) |
| 不在 command transaction 内 | ✅ | checkpoint 在 `host._run_read()` 返回后执行，使用独立 connection |
| 错误映射为 HostApiError | ✅ | `HostDurableError` 在 `storage_maintenance.py:277-282` 被捕获并映射为 `HostApiError(INTERNAL_ERROR)` |

### 7. Public API / Protocol / Package Exports

**结论：PASS**

- **Host Protocol** (`api.py:3309-3332`)：`report_storage_usage` 和 `run_storage_maintenance` 已声明，返回类型和异常文档完整。
- **`__init__.py`**：导出 `DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS`、`HostStorageMaintenanceFileError`、`HostStorageMaintenanceRequest`、`HostStorageMaintenanceResult`、`HostStorageUsageReport`、`report_storage_usage`、`run_storage_maintenance`、`HostWalCheckpointMode`、`HostWalCheckpointResult`。
- **`test_package_exports.py`**：`EXPECTED_STORAGE_MAINTENANCE_EXPORTS` 和 `EXPECTED_COMMAND_EXPORTS` 包含所有新符号。`test_host_protocol_exposes_public_handle_methods` 验证 Protocol 方法白名单。
- **`open_host.py`**：`_PublicHostHandle` 实现 `report_storage_usage` 和 `run_storage_maintenance` 异步包装。

### 8. Dataclass Type Strictness

**结论：PASS**

| 类型 | 校验 | 证据 |
|---|---|---|
| `HostStorageUsageReport` | 所有字段 `int`，`__post_init__` 调用 `_require_non_negative_int`（排除 `bool`） | `storage_lifecycle.py:149-158` |
| `HostStorageMaintenanceRequest` | `reclaim_orphan_artifacts: bool`、`orphan_grace_seconds: float`（非负）、`run_wal_checkpoint: bool`、`wal_checkpoint_mode: HostWalCheckpointMode` | `storage_maintenance.py:59-83` |
| `HostStorageMaintenanceResult` | `usage: HostStorageUsageReport`、`physical_artifact_bytes: int`（非负）、tuple 类型检查、`wal_checkpoint` 类型检查 | `storage_maintenance.py:157-192` |
| `HostStorageMaintenanceFileError` | 所有字段非空字符串 | `storage_maintenance.py:103-121` |
| `json_value()` | 所有 dataclass 都提供 `json_value() -> JsonValue` | 各类定义中 |

无 `Any`、`object`、无类型参数或无类型返回值。

### 9. Test Coverage

**结论：PASS**

#### `test_storage_orphan_proof.py`（5 tests）

| 测试 | 覆盖点 |
|---|---|
| `test_artifact_relative_path_reference_uses_descriptor_truth` | descriptor truth：已引用路径返回 True，未引用返回 False |
| `test_collect_referenced_artifact_paths_deduplicates_shared_descriptors` | shared descriptor 去重 |
| `test_descriptor_with_durable_event_reference_keeps_artifact_referenced` | projection lag：descriptor 存活即证明 artifact 仍被引用 |
| `test_scan_orphan_artifact_files_filters_namespace_grace_and_sorts` | namespace 安全、grace 过滤、排序确定性 |
| `test_physical_artifact_bytes_counts_only_published_sha256_files` | 物理 artifact size 排除非 artifact 文件 |

#### `test_storage_maintenance.py`（5 tests）

| 测试 | 覆盖点 |
|---|---|
| `test_storage_maintenance_dry_run_reports_candidates_without_deleting` | dry-run 不删文件、不删 row、候选正确、物理 bytes、checkpoint off |
| `test_storage_maintenance_wal_checkpoint_true_returns_result` | checkpoint on 返回 `HostWalCheckpointResult` |
| `test_storage_maintenance_reclaim_true_fails_fast_without_deleting` | destructive reclaim fail fast、文件和 row 不变 |
| `test_open_host_async_handle_runs_storage_maintenance_dry_run` | async open_host 入口 |
| `test_open_host_run_storage_maintenance_fails_after_close` | closed handle 错误语义 |

#### 覆盖的 dry-run invariants

- ✅ 不删除 artifact 文件
- ✅ 不删除 SQLite row
- ✅ 不执行 VACUUM
- ✅ 不启动 scheduler
- ✅ 不在 command transaction 内执行 WAL checkpoint
- ✅ artifact orphan proof 只读取 `payload_descriptors` 中 `payload_kind=artifact_ref` 的 `artifact_relative_path`
- ✅ audit JSONL、tool-trace JSONL、`.tmp` 和非 `sha256/` namespace 文件不进入 orphan 候选
- ✅ `reclaim_orphan_artifacts=True` fail fast
- ✅ EventLog/Session/Run 状态不变

### 10. Documentation

**结论：PASS**

- **`docs/host/design.md`**：新增 storage maintenance 设计说明（line ~979, ~1201-1205），只描述已实现 dry-run，不声明 destructive reclaim。明确 `reclaim_orphan_artifacts=True` 当前返回 unsupported operation。
- **`dayu/host/README.md`**：新增"Storage Usage Report"和"Storage Maintenance Dry-Run"小节，明确当前不删除文件/row/VACUUM/scheduler。
- **`tests/README.md`**：`tests/host/` 章节已更新，覆盖三个新测试文件的说明。

### 11. AGENTS.md Compliance

**结论：PASS**

| 要求 | 验证 |
|---|---|
| 中文 docstring | ✅ 所有公共函数、类和模块都有完整中文 docstring |
| 严格类型 | ✅ 无 `Any`、`object`、无类型参数、无类型返回值 |
| 无无理由 getattr/hasattr | ✅ 未发现 |
| 无兼容 facade | ✅ 无兼容性 wrapper / re-export |
| 无过度设计 | ✅ 实现严格匹配 plan 的最小正确闭环 |
| 无魔法数字/字符串 | ✅ `DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS = 3600.0` 为具名常量 |
| 职责分离 | ✅ durable 原语在 `storage_lifecycle.py`、facade 在 `storage_maintenance.py`、accessor 在 `command.py` |

### 12. command.py 新增 Accessor

**结论：PASS**

- `_db_path()` (`command.py:242-253`)：单职责，返回 durable SQLite DB 路径。有 `_raise_if_closed` guard 和 `HostDurableError -> HostApiError` 映射。
- `_artifact_root()` (`command.py:255-266`)：单职责，返回 artifact root 路径。同上。
- `_open_durable_connection()` (`command.py:268-283`)：委托 `_durable_store.connect()`，docstring 明确调用方必须关闭。有 closed guard 和错误映射。
- 不引入 god bag，不暴露 durable store 内部对象。

## Findings

### F01 — `storage_lifecycle.py:339` 使用 `AssertionError` 代替 `TypeError`

- **severity**: info
- **file/line**: `dayu/host/durable/storage_lifecycle.py:339`
- **description**: `collect_referenced_artifact_paths` 中 `if not isinstance(value, str): raise AssertionError(...)` 使用 `AssertionError` 而非 `TypeError`。虽然该路径在正常 SQLite 行为下不可达（`artifact_relative_path` 列定义为 TEXT），但使用 `TypeError` 语义更精确。
- **status**: accepted（不影响正确性，属于风格偏好；当前代码库其它处也有类似模式）

### F02 — `storage_lifecycle.py:412` 同上，`_assert_report_tables_cover_schema` 使用 `AssertionError`

- **severity**: info
- **file/line**: `dayu/host/durable/storage_lifecycle.py:412`
- **description**: 同 F01 风格问题。
- **status**: accepted

### F03 — dry-run 测试未覆盖 `orphan_grace_seconds=0` 场景

- **severity**: info
- **file/line**: `tests/host/test_storage_maintenance.py`
- **description**: 当前测试使用默认 grace（3600s）并通过 `_set_old_mtime` 将文件设为过期。未测试 `grace_seconds=0` 时所有 orphan 立即进入候选的边界。`test_storage_orphan_proof.py` 中的 grace 测试覆盖了 `grace_seconds=3600` 的过滤，但未测试零 grace。
- **status**: deferred-with-owner（可由后续 slice 或独立测试补充；不影响当前 slice 正确性）

## Residual Risks

| ID | 状态 | 说明 |
|---|---|---|
| R1 publish-before-commit 竞态 | covered by design | grace + 默认 dry-run + 删除前 recheck（Slice 4）共同缓解 |
| R2 purge `cleanup_refs` 死字段 | deferred | 不在本 slice 处理；maintenance 全量扫描已覆盖这些 orphan |
| R3 orphan SQLite payload 行回收 | deferred | 本 slice 只报告计数，不删行 |
| R4 大 artifact root 遍历成本 | covered by design | 隔离在 operator 显式 maintenance entrypoint |
| R5 DB VACUUM | deferred-with-owner: GitHub Issue #76 | 本 slice 只 checkpoint + size 诊断 |

## Conclusion

**PASS**

所有审查维度均通过。Slice 3 严格遵守 dry-run 边界：不删除文件、不删 row、不 VACUUM、不 scheduler。引用证明只以 `payload_descriptors` 中 `payload_kind=artifact_ref` 的 `artifact_relative_path` 为来源，正确处理 shared descriptor、projection lag 和 missing descriptor。orphan scan 只使用 `sha256/` namespace 枚举，audit/tool-trace/.tmp/非 sha256 文件不进入候选。WAL checkpoint 使用独立 connection 且 finally 关闭，不在 command transaction 内执行。所有 dataclass 严格类型校验，无 `Any`/`object`/无类型签名。测试覆盖 dry-run invariants、checkpoint on/off、no state mutation、closed handle、unsupported reclaim、namespace/grace/shared 引用。文档只描述已实现 dry-run，不提前声明 destructive reclaim。

0 blocking findings。
