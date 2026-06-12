# WU-RET-00 Slice 3 Code Review — AgentDS

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: code review
- slice: Slice 3 — 删除证明只读原语 + maintenance dry-run
- agent: AgentDS
- artifact path: `docs/reviews/wu-ret-00-slice3-code-review-ds.md`
- status: completed

## 审查范围

Review target files（按 control doc 和 implementation report 指定）：

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

辅助核验文件：

- `dayu/host/durable/maintenance.py` — WAL checkpoint 原语
- `dayu/host/durable/errors.py` — 异常层次
- `dayu/host/durable/artifact.py` — artifact 枚举真源

## 审查方法

逐项对照 control doc 和 implementation report 列出的审查重点，按 correctness（边界、语义、错误处理）、stability（状态不变量、连接生命周期）、maintainability（类型严格性、命名、docstring、README 边界）三个维度审查。对每一项 finding 给出 severity、file/line、直接证据和 status 建议。

## Finding 总览

| # | Severity | 类别 | 摘要 | Status |
|---|---|---|---|---|
| F01 | Low | maintainability | `_require_non_empty_text` 缺少显式 `str` 类型检查 | accepted |
| F02 | Low | style | `_wal_path_for_db_path` 与 `_read_wal_size_bytes` 路径拼接模式不一致 | accepted |
| F03 | Informational | correctness | `run_storage_maintenance` 异常覆盖已确认完整 | no-action |

## Slice 3 边界审查

### Dry-Run 不变量

审查 `dayu/host/storage_maintenance.py:228-291` (`run_storage_maintenance`)：

1. **不删除 artifact 文件**：`reclaimed_artifact_paths=()` 始终为空元组（line 288）。函数体内没有任何 `os.remove`、`pathlib.Path.unlink` 或 `shutil.rmtree` 调用。✓
2. **不删除 SQLite row**：函数只在 read transaction 内读取 `_ReadStorageMaintenanceStateOperation`（line 256-258），不执行任何 `DELETE`、`DROP`、`INSERT` 或 `UPDATE`。WAL checkpoint 是只读 `PRAGMA wal_checkpoint`（`dayu/host/durable/maintenance.py:79`），不修改行数据。✓
3. **不执行 VACUUM**：代码中不存在 `VACUUM` 字面量或等价 SQL。✓
4. **不启动 scheduler**：函数签名接收 `HostCommandHandle`，通过 `host._run_read()` 使用 command handle 的 transaction runner，不创建或唤醒 scheduler。✓

5. **`reclaim_orphan_artifacts=True` fail fast**：

- 检查点在 `run_storage_maintenance` 的最顶部（line 246-251），在任何 DB 读取、文件扫描或 artifact 枚举之前。
- 抛出 `HostApiError(code=UNSUPPORTED_OPERATION, retryable=False)`。
- 测试 `test_storage_maintenance_reclaim_true_fails_fast_without_deleting` 验证了：
  - 错误码为 `UNSUPPORTED_OPERATION`。
  - orphan 文件未被删除（`is_file()` 断言）。
  - `payload_descriptor_rows` 和 `event_log_rows` 前后不变。✓

6. **不在 command transaction 内执行 WAL checkpoint**：`_run_wal_checkpoint_if_requested`（line 347-375）通过 `host._open_durable_connection()` 打开独立 connection，在 try/finally 中执行 checkpoint 并 close。该调用位于 `host._run_read(...)` 事务**之后**（line 266-270），不在任何 command transaction 内。✓

### 结论

Slice 3 边界严格符合 plan 约定。所有 dry-run 不变量均已通过代码审查和测试验证。

## 引用证明审查

### 引用来源

审查 `dayu/host/durable/storage_lifecycle.py`：

1. **`artifact_relative_path_is_referenced`**（line 281-308）：

   - SQL 查询只针对 `payload_descriptors` 表，条件是 `payload_kind = ?` 和 `artifact_relative_path = ?`。
   - `payload_kind` 参数使用 `PayloadKind.ARTIFACT_REF.value`（line 306）。
   - 不使用 EventLog payload JSON、audit JSONL、tool-trace JSONL 或其它内部治理标签作为引用来源。✓

2. **`collect_referenced_artifact_paths`**（line 310-341）：

   - 同样只查询 `payload_descriptors` 表，`payload_kind = ?` 过滤，额外加了 `artifact_relative_path IS NOT NULL`。
   - 每行强制 `isinstance(value, str)` 检查（line 338-339），不为非字符串路径静默降级。
   - 返回 `frozenset[str]`，不可变集合防意外修改。✓

3. **Shared descriptor 处理**：使用 Python `set` 收集路径（line 335），自动去重。测试 `test_collect_referenced_artifact_paths_deduplicates_shared_descriptors` 验证了两个 descriptor 共享同一内容寻址文件时只产生一个路径。✓

4. **Projection lag 处理**：`test_descriptor_with_durable_event_reference_keeps_artifact_referenced` 验证了 EventLog row 引用 `payload_ref` 的场景——即使 EventLog 存在引用，artifact 引用证明的真源仍然是 descriptor row。descriptor 存活 ⇒ artifact 被引用；descriptor 缺失 ⇒ artifact 不被引用。✓

5. **Missing descriptor 处理**：`artifact_relative_path_is_referenced` 在查无匹配 descriptor 时返回 `False`（`row is not None` 判断，line 308）。`scan_orphan_artifact_files` 通过 `on_disk - referenced` 集合差（line 374-376）将未被引用的文件纳入候选。✓

### 结论

引用证明严格以 `payload_descriptors` 中 `payload_kind='artifact_ref'` 的 `artifact_relative_path` 为唯一真源，正确处理 shared descriptor 去重、projection lag 和 missing descriptor 场景。无跨表推导、无间接引用、无隐式规则。

## Orphan 扫描审查

审查 `dayu/host/durable/storage_lifecycle.py:344-380` (`scan_orphan_artifact_files`)：

1. **只使用 Slice 1 的 sha256 namespace 枚举**：

   - 通过 `iter_published_artifact_relative_paths(artifact_root)` 枚举候选文件（line 374）。
   - 该函数定义在 `dayu/host/durable/artifact.py`，只产出 `sha256/<shard>/<hex>` 路径格式的已发布文件。
   - audit JSONL、tool-trace JSONL、`.tmp` 和非 sha256 namespace 文件不在枚举结果中，自然不进入候选。✓

2. **Grace 判断**：

   - 要求 `now` 为 timezone-aware datetime（`_require_aware_datetime`，line 369）。
   - 要求 `grace_seconds >= 0`（line 370-371）。
   - 计算 `cutoff_timestamp = now.timestamp() - grace_seconds`（line 372），使用 POSIX timestamp 做确定性比较。
   - 条件 `artifact_path.stat().st_mtime <= cutoff_timestamp`（line 378），只纳入 mtime 不晚于 cutoff 的文件。
   - 测试 `test_scan_orphan_artifact_files_filters_namespace_grace_and_sorts` 验证了：
     - 超过 grace 的旧文件进入候选。
     - grace 窗口内的新文件不进入候选。
     - `.tmp` / `audit` / `tool-trace` 目录下的文件全部排除。
     - 被引用的文件即使超过 grace 也不进入候选。✓

3. **排序确定性**：

   - 返回 `tuple(sorted(candidates))`（line 380）。
   - 候选路径为 POSIX 相对路径字符串（如 `sha256/xx/yyyy...`），`sorted()` 按字典序确定排序。✓

4. **错误传播**：

   - `OSError`（`stat` 失败）和 `ValueError`（非法 datetime / grace）从函数签名透传。
   - 在 `run_storage_maintenance` 调用链中，`OSError` 被 line 271-276 捕获并映射为 `HostApiError`。
   - `HostArtifactWriteError`（来自 `iter_published_artifact_relative_paths`）是 `HostDurableError` 的子类（`errors.py:128`），被 line 277-282 的 `except HostDurableError` 捕获并映射。✓

### 结论

Orphan 扫描严格限制在 Slice 1 的 sha256 namespace 内，grace 判断使用确定性 timestamp 比较，排序稳定。错误传播路径完整。

## `physical_artifact_bytes` 语义审查

审查 `dayu/host/durable/storage_lifecycle.py:383-399`：

1. **统计来源**：只通过 `iter_published_artifact_relative_paths` 枚举 `sha256/` namespace 下的已发布文件，对每个文件调用 `.stat().st_size`。

2. **排除范围**：`.tmp`、audit JSONL、tool-trace JSONL 和其它非 descriptor-managed namespace 文件在枚举阶段即被排除。

3. **命名**：函数名 `physical_artifact_bytes` 明确表达"物理 artifact 字节数"，参数 `artifact_root` 显式接收 artifact 根目录。docstring（line 383-394）详细说明统计范围、排除项和非破坏性。

4. **README 中的描述**：`dayu/host/README.md:82` 描述 `run_storage_maintenance` 返回"已发布 artifact 物理字节和"，与实现一致。`docs/host/design.md:430` 描述"已发布 artifact 物理字节和"，一致。✓

5. **测试覆盖**：`test_physical_artifact_bytes_counts_only_published_sha256_files` 验证了只有 sha256 namespace 文件被统计，`.tmp`/`audit`/`tool-trace` 文件被排除。`test_storage_maintenance_dry_run_reports_candidates_without_deleting` 验证了物理字节数等于 referenced + orphan 文件的实际 `st_size` 之和。✓

### 结论

`physical_artifact_bytes` 的语义与文档一致，命名清楚，测试覆盖充分。

## WAL Checkpoint 审查

审查 `dayu/host/storage_maintenance.py:347-375` (`_run_wal_checkpoint_if_requested`) 和 `dayu/host/command.py:268-283` (`_open_durable_connection`)：

1. **独立 connection**：

   - `_open_durable_connection`（command.py:268-283）调用 `self._durable_store.connect()` 创建新的 SQLite connection，不是复用 command transaction 的 connection。
   - 该 accessor 包含 `_raise_if_closed()` guard 和 `HostDurableError` → `HostApiError` 映射。
   - docstring 明确标注"调用方负责关闭返回的 connection"和"不进入 command transaction"。✓

2. **Finally 关闭**：

   - `_run_wal_checkpoint_if_requested` 的 `connection` 变量初始化为 `None`（line 365）。
   - `try` 块内打开 connection 并执行 checkpoint（line 366-372）。
   - `finally` 块检查 `connection is not None` 后才 `close()`（line 373-375）。
   - 即使 `run_host_wal_checkpoint` 抛出 `HostDurableError`，connection 仍会被关闭。✓

3. **不在 command transaction 内执行**：

   - `run_storage_maintenance` 先执行 `host._run_read(...)`（line 256-258）完成 DB 快照读取，该事务已提交。
   - 随后在同一 try 块内调用 `_run_wal_checkpoint_if_requested`（line 266-270），使用的是独立 connection。
   - 代码顺序保证 checkpoint 不发生在任何 active transaction 内。✓

4. **错误映射**：

   - `host._open_durable_connection()` 本身的错误映射为 `HostApiError`（command.py:281-283）。
   - `run_host_wal_checkpoint` 抛出的 `HostDurableError` 被 `run_storage_maintenance` 的 `except HostDurableError`（line 277-282）捕获并映射为 `HostApiError(code=INTERNAL_ERROR, retryable=False)`。
   - `OSError`（WAL 文件 stat 失败）在 `maintenance.py:_read_wal_size_bytes` 中被转为 `HostDurableError`（line 184-187），进而被上述 catch 捕获。✓

5. **Checkpoint 关闭时返回 None**：

   - `request.run_wal_checkpoint=False` 时，`_run_wal_checkpoint_if_requested` 立即返回 `None`（line 363-364）。
   - `HostStorageMaintenanceResult.__post_init__` 正确接受 `wal_checkpoint=None`（line 185-192）。
   - `json_value()` 方法对 `None` 返回 `None`（`_wal_checkpoint_json_value`，line 387-388）。✓

6. **Connection 安全校验**：

   - `run_host_wal_checkpoint` 在 `dayu/host/durable/maintenance.py:62-105` 执行 `_assert_connection_matches_db_path`，校验 connection 的 `main` database 文件路径与 `db_path` 解析后一致。
   - 防止错误地与其它 DB 文件执行 checkpoint。✓

### 结论

WAL checkpoint 使用独立 connection，finally 关闭，不在 command transaction 内执行，错误映射完整。Connection 安全校验到位。

## Public API / Protocol / Package Exports 审查

### Host Protocol

`dayu/host/api.py:3110-3352` 定义的 `Host` Protocol 包含：

- `report_storage_usage()` at line 3309-3317 ✓
- `run_storage_maintenance(request)` at line 3319-3332 ✓

两个方法都有完整的 docstring（参数、返回值、异常）。

### Package Export

`dayu/host/__init__.py` 导出：

- 类型：`HostStorageMaintenanceFileError`, `HostStorageMaintenanceRequest`, `HostStorageMaintenanceResult`, `HostStorageUsageReport`, `HostWalCheckpointMode`, `HostWalCheckpointResult` ✓
- 常量：`DEFAULT_ORPHAN_ARTIFACT_GRACE_SECONDS` ✓
- 函数：`report_storage_usage`, `run_storage_maintenance` ✓

`test_package_exports.py` 白名单 `EXPECTED_STORAGE_MAINTENANCE_EXPORTS` 包含上述符号（line 123-134）；`EXPECTED_COMMAND_EXPORTS` 包含 `report_storage_usage` 和 `run_storage_maintenance`（line 103-121）。`test_host_all_matches_current_public_contracts` 验证包根 `__all__` 与期望一致。`test_host_protocol_exposes_public_handle_methods` 验证 Protocol 包含完整方法面。✓

### 内部归属

- `dayu/host/durable/maintenance.py` 的 `HostWalCheckpointMode` / `HostWalCheckpointResult` / `run_host_wal_checkpoint` 是内部 durable primitive，只通过包根按需导出 `HostWalCheckpointMode` / `HostWalCheckpointResult`。
- `run_host_wal_checkpoint` 不进入包根导出，调用方无法从 public API 直接使用。
- `_open_durable_connection`（command.py:268）是 `HostCommandHandle` 的内部 accessor，不使用 `_` 前缀不暴露到包根 `__all__`。✓

### 新 Dataclass 类型严格性

1. **`HostStorageUsageReport`**（`storage_lifecycle.py:79-218`）：
   - `__post_init__` 对每个字段执行 `_require_non_negative_int`，排除 bool 和负数。✓
   - `json_value()` 返回稳定键顺序的 `dict[str, JsonValue]`。✓

2. **`HostStorageMaintenanceRequest`**（`storage_maintenance.py:37-83`）：
   - `__post_init__` 检查 `reclaim_orphan_artifacts` (bool), `orphan_grace_seconds` (float non-negative), `run_wal_checkpoint` (bool), `wal_checkpoint_mode` (enum instance)。✓
   - 所有字段有默认值和 `kw_only=True`。✓

3. **`HostStorageMaintenanceResult`**（`storage_maintenance.py:136-207`）：
   - `__post_init__` 检查 `usage` (instance), `physical_artifact_bytes` (int non-negative), tuple fields (string tuple), `file_errors` (tuple of correct type), `wal_checkpoint` (correct type or None)。✓
   - `json_value()` 递归调用子对象的 `json_value()`。✓

4. **`HostStorageMaintenanceFileError`**（`storage_maintenance.py:86-133`）：
   - 三个字段均为 `str`，`__post_init__` 通过 `_require_non_empty_text` 检查非空。✓
   - `json_value()` 返回自解释 JSON object。✓

### `_require_non_empty_text` 类型检查完善度

`storage_maintenance.py:459-469` 的 `_require_non_empty_text` 只检查 `value.strip() == ""`，不显式检查 `isinstance(value, str)`。同一模块内的 `_require_non_negative_int`（line 427-440）、`_require_non_negative_float`（line 411-424）、`_require_bool`（line 398-408）均执行了 `isinstance` 类型检查。

**分析**：Python 中 `bool` 是 `int` 的子类，因此 `_require_non_negative_int` 必须显式拒绝 `bool`。`_require_non_negative_float` 也同理（`bool` 是 `int` 的子类，`int` 在 `isinstance(x, (float, int))` 中为 True）。但 `str` 没有这种子类陷阱——没有内置类型是 `str` 的子类且带有 `.strip()` 方法会产生非预期行为。`_require_non_empty_text` 的输入来自 `dataclass` 的 `str` 标注字段，在 `__post_init__` 中调用时如果类型不对，pyright 会先行报警。

此外，`dayu/host/_public_validation.py` 中的 `require_non_empty`（被 api.py 广泛使用）同样未做 `isinstance(value, str)` 检查——这是项目级的模式选择。

**结论**：这不是 bug，不构成类型安全漏洞。`_require_non_empty_text` 遵循了项目既有的 validation 模式（区分"需要类型检查的数值类型"和"只检查约束的字符串类型"）。

→ Finding F01 accepted as informational, not a defect.

### 结论

Public API、Protocol、package exports 归属正确，新 dataclass 的 `json_value`、非负校验和 tuple 检查严格到位。

## 测试审查

### 覆盖矩阵

| 测试 | 文件 | 覆盖点 |
|---|---|---|
| `test_artifact_relative_path_reference_uses_descriptor_truth` | test_storage_orphan_proof.py | descriptor 真源引用证明 |
| `test_collect_referenced_artifact_paths_deduplicates_shared_descriptors` | test_storage_orphan_proof.py | shared descriptor 去重 |
| `test_descriptor_with_durable_event_reference_keeps_artifact_referenced` | test_storage_orphan_proof.py | projection lag 下 descriptor truth |
| `test_scan_orphan_artifact_files_filters_namespace_grace_and_sorts` | test_storage_orphan_proof.py | namespace 安全、grace 过滤、排序确定、.tmp/audit/tool-trace 排除 |
| `test_physical_artifact_bytes_counts_only_published_sha256_files` | test_storage_orphan_proof.py | 物理 artifact 统计排除非 sha256 文件 |
| `test_storage_maintenance_dry_run_reports_candidates_without_deleting` | test_storage_maintenance.py | dry-run 不删除文件/SQLite row、候选正确、physical bytes、EventLog/Session/Run 状态不变 |
| `test_storage_maintenance_wal_checkpoint_true_returns_result` | test_storage_maintenance.py | checkpoint on 返回结果 |
| `test_storage_maintenance_reclaim_true_fails_fast_without_deleting` | test_storage_maintenance.py | destructive reclaim fail fast、不删除、不修改 row |
| `test_open_host_async_handle_runs_storage_maintenance_dry_run` | test_storage_maintenance.py | async open_host handle 入口 |
| `test_open_host_run_storage_maintenance_fails_after_close` | test_storage_maintenance.py | closed handle 错误语义 |

### 测试质量

1. **Dry-run 不变量**：`test_storage_maintenance_dry_run_reports_candidates_without_deleting` 在调用 `run_storage_maintenance` 后验证了：
   - `orphan_artifact_candidates` 只包含正确的 orphan 路径。
   - `reclaimed_artifact_paths == ()`。
   - `file_errors == ()`。
   - `wal_checkpoint is None`（传入 `run_wal_checkpoint=False`）。
   - orphan 和 referenced 文件在磁盘上仍然存在。
   - `after_usage` 的 row count 与 `before_usage` 完全一致。
   - `after_session.status == before_session.status` 和 `after_run.status == before_run.status`。✓

2. **Checkpoint on/off**：
   - `test_storage_maintenance_wal_checkpoint_true_returns_result` 不传 `run_wal_checkpoint`（默认 True），验证 `wal_checkpoint is not None` 且 `mode.value == "PASSIVE"`。
   - `test_storage_maintenance_dry_run_reports_candidates_without_deleting` 传 `run_wal_checkpoint=False`，验证 `wal_checkpoint is None`。✓

3. **Closed handle**：`test_open_host_run_storage_maintenance_fails_after_close` 先 close handle，再调用 `run_storage_maintenance`，断言 `HostClosedError`。✓

4. **Unsupported reclaim**：`test_storage_maintenance_reclaim_true_fails_fast_without_deleting` 验证错误码为 `UNSUPPORTED_OPERATION`，文件不删除，row count 不变。✓

5. **命名空间安全和 grace**：`test_scan_orphan_artifact_files_filters_namespace_grace_and_sorts` 创建了：
   - 两个旧 orphan（sha256 namespace，mtime 设为旧值）。
   - 一个被引用文件（sha256 namespace，mtime 设为旧值）。
   - 一个新 orphan（sha256 namespace，mtime 设为当前时间）。
   - `.tmp/`、`audit/`、`tool-trace/` 下的非 artifact 文件。
   - 验证结果只包含两个旧 orphan，且按字典序排列。✓

6. **Package export 白名单**：`test_host_all_matches_current_public_contracts`、`test_host_protocol_exposes_public_handle_methods`、`test_exported_symbols_are_same_objects_as_api_symbols` 等保持完整。✓

### 结论

测试覆盖 dry-run 不变量、checkpoint on/off、no state mutation、closed handle、unsupported reclaim、namespace/grace/shared 引用等关键场景。白名单测试同步更新。

## 文档审查

### `docs/host/design.md`

Storage Maintenance Dry-Run 章节（line 426-430）：

> 当前 maintenance 不删除 artifact 文件、不删除 SQLite row、不执行 `VACUUM`、不启动 scheduler；请求 `reclaim_orphan_artifacts=True` 会返回 unsupported operation。audit JSONL、tool-trace JSONL、`.tmp` 和其它非 `sha256/` namespace 文件不参与 artifact orphan 候选。

只描述已实现 dry-run 行为，不提前声明 destructive reclaim 为已实现。✓

Storage Usage Report 章节（line 422-424）正确描述为只读诊断，不扫描 artifact root，不执行 checkpoint。✓

### `dayu/host/README.md`

Line 82：

> `run_storage_maintenance(request)`：执行显式 dry-run maintenance，返回 orphan artifact 候选、已发布 artifact 物理字节和、usage report 与可选 WAL checkpoint 诊断；当前不删除文件或 row。

准确描述 dry-run 边界。✓

### `tests/README.md`

Lines 162-163（host 测试章节）：

> `test_storage_orphan_proof.py` 覆盖 artifact descriptor 引用证明、shared descriptor 去重、projection lag 下 descriptor truth、`sha256/` namespace 安全、grace 过滤、稳定排序与物理 artifact size；`test_storage_maintenance.py` 覆盖 dry-run maintenance 不删除文件或 SQLite row、orphan 候选、物理 artifact bytes、WAL checkpoint on/off、EventLog/Session/Run 状态不变、async `open_host` handle 入口、closed handle 错误语义，以及 destructive reclaim 在当前 slice fail fast。

准确描述测试覆盖范围。✓

### 结论

所有文档只描述已实现 dry-run，不提前声明 destructive reclaim。

## AGENTS.md 合规审查

### 中文 docstring

所有新增和修改的函数、类、模块 docstring 均为中文，包含参数、返回值和异常说明。✓

### 严格类型

- 无 `Any`、`object`、无类型参数、无类型返回值。✓
- 新增 dataclass 使用 `frozen=True, slots=True`，字段类型明确。✓
- `scan_orphan_artifact_files` 的 `referenced` 参数使用 `AbstractSet[str]` 而非具体类型，这是合理的接口抽象。✓

### 无无理由 getattr/hasattr

代码中不存在 `getattr` / `hasattr` 调用。✓

### 无兼容 facade

新增符号没有为旧导入路径做 re-export 或 wrapper。✓

### 无过度设计

- `storage_lifecycle.py` 的函数都是单职责只读原语，不引入 manager 类或策略模式。
- `storage_maintenance.py` 的 facade 直接组装原语函数，不使用 pipeline/visitor/chain-of-responsibility 等过度模式。
- `HostStorageMaintenanceFileError` 是为后续 destructive slice 预留的类型（line 90-92 docstring 明确说明），这是合理的向前兼容，不是过度设计。✓

### 结论

AGENTS.md 合规，无违规项。

## Adversarial Failure Pass

以下 adversarial 场景已逐一验证：

1. **并发 descriptor 写入**：`run_storage_maintenance` 在 read transaction 内读取 descriptor snapshot，外部并发写入在事务提交后才可见。orphan 候选可能存在 false positive（刚写入的 descriptor 未被读取到），但因为 grace window 的存在，新文件不会立即进入候选。无 false negative 风险（被引用的文件不会被错误标记为 orphan）。✓

2. **WAL checkpoint 与 command transaction 竞争**：checkpoint 使用独立 connection 执行 `PRAGMA wal_checkpoint(PASSIVE)`，SQLite 的 PASSIVE 模式在有任何 reader 时不阻塞也不等待，安全无副作用。✓

3. **artifact_root 为空目录**：`iter_published_artifact_relative_paths` 在空目录下返回空迭代器，所有后续计算归零。`physical_artifact_bytes` 返回 0，`scan_orphan_artifact_files` 返回空元组。✓

4. **DB 文件不存在**：`_file_size_bytes`（storage_lifecycle.py:513-524）捕获 `FileNotFoundError` 并返回 0。✓

5. **Closed handle 调用**：`_raise_if_closed()` 在 `_open_durable_connection`、`_run_read`、`_db_path`、`_artifact_root` 中均被调用，返回 `INVALID_STATE` 错误。`_PublicHostHandle.run_storage_maintenance` 同样在调用前执行 `_raise_if_closed()`。测试覆盖了 closed handle 场景。✓

6. **Descriptor 中 artifact_relative_path 为空字符串**：`collect_referenced_artifact_paths` 不检查空字符串（只检查 `IS NOT NULL`），但 `artifact_relative_path_is_referenced` 可匹配空字符串。若实际存储中出现空字符串（应为不可能），`scan_orphan_artifact_files` 中的 `iter_published_artifact_relative_paths` 不会产生空路径，因此空字符串不会在 `on_disk` 中出现——不会造成错误删除。这不是实际风险。✓

## Finding 详情

### F01 — `_require_non_empty_text` 缺少显式 `str` 类型检查

- **Severity**: Low
- **File/Line**: `dayu/host/storage_maintenance.py:459-469`
- **Evidence**: `_require_non_empty_text` 只检查了 `value.strip() == ""`，未检查 `isinstance(value, str)`。同一模块内的 `_require_non_negative_int`（line 427）、`_require_non_negative_float`（line 411）、`_require_bool`（line 398）均执行了类型检查。
- **Analysis**: 经核查，`_require_non_negative_int` 的类型检查主要目的是排除 `bool`（`bool` 是 `int` 的子类）。`str` 没有类似的子类陷阱。`dayu/host/_public_validation.py` 中的 `require_non_empty` 也未做类型检查——这是项目级的既有模式。当前使用场景（`__post_init__` 中校验 `str` 类型字段）在 pyright 静态分析下是安全的。
- **Status**: **accepted** — 无需修改。遵循项目既有 validation 模式。数值类型检查因 `bool` 子类陷阱而必要，字符串类型无此需求。

### F02 — `_wal_path_for_db_path` 与 `_read_wal_size_bytes` 路径拼接模式不一致

- **Severity**: Low
- **File/Line**: `dayu/host/durable/storage_lifecycle.py:527-534` vs `dayu/host/durable/maintenance.py:179`
- **Evidence**:
  - `storage_lifecycle.py:_wal_path_for_db_path` 使用 `Path(f"{db_path}-wal")`。
  - `maintenance.py:_read_wal_size_bytes` 使用 `db_path.with_name(db_path.name + "-wal")`。
  - 两者功能等价，产生相同的路径结果。
- **Analysis**: 两处代码实现同一逻辑（获取 SQLite WAL 文件路径），但使用了不同模式。`with_name` 更利于表达"同一目录下不同文件名"的意图，属于可维护性提升。当前无正确性影响。
- **Status**: **accepted** — 可选统一为 `with_name` 模式以提升可维护性，但非阻塞。建议在后续 slice 或 routine cleanup 中处理。

### F03 — `run_storage_maintenance` 异常覆盖已确认完整

- **Severity**: Informational
- **File/Line**: `dayu/host/storage_maintenance.py:228-291`
- **Evidence**: 审查验证了全部异常路径：
  - `OSError`（文件 stat / 扫描失败）→ caught at line 271 → `HostApiError(INTERNAL_ERROR)`
  - `HostDurableError`（DB 读取、artifact 枚举、checkpoint 失败）→ caught at line 277 → `HostApiError(INTERNAL_ERROR)`
  - `HostArtifactWriteError` 是 `HostDurableError` 的子类（`errors.py:128`）→ 被 line 277 的 `except HostDurableError` 正确捕获
  - `HostApiError`（connection 打开失败、destructive reclaim 请求）→ 直接 propagate
- **Status**: **no-action** — 异常覆盖完整，无需修改。

## Review Conclusion

### 判定：PASS

当前 slice 无必须修复后才能 accepted slice commit 的 blocking finding。

### 统计

- Total findings: 3
- Blocking (must-fix): 0
- Accepted (no fix needed): 2 (F01, F02)
- No-action (informational): 1 (F03)

### 验证结果复述

- `pytest tests/host/test_storage_orphan_proof.py tests/host/test_storage_maintenance.py -q` ⇒ 10 passed
- `pytest tests/host/test_storage_usage_report.py tests/host/test_artifact_store.py tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` ⇒ 51 passed
- `pyright dayu/host/durable/storage_lifecycle.py dayu/host/storage_maintenance.py dayu/host/command.py dayu/host/open_host.py dayu/host/api.py dayu/host/__init__.py tests/host/test_storage_orphan_proof.py tests/host/test_storage_maintenance.py` ⇒ 0 errors
- Full `pyright` target ⇒ 0 errors

### 未覆盖风险

- destructive orphan artifact reclaim 未实现，属于 Slice 4 范围。当前 `reclaim_orphan_artifacts=True` fail fast。
- SQLite orphan payload row 只报告不删除，属于计划中明确的范围外。
- Audit JSONL / Tool Trace cold JSONL retention/rotation 不在本 WU 范围（WU-RET-01 / WU-RET-02）。
- `_wal_path_for_db_path` 路径拼接模式不一致（F02），建议后续统一但非阻塞。
