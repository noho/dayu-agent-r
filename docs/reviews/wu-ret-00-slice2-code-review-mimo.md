# WU-RET-00 Slice 2 Code Review — AgentMiMo

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: code review
- slice: Slice 2 — read-only storage usage report
- agent: AgentMiMo
- artifact path: `docs/reviews/wu-ret-00-slice2-code-review-mimo.md`
- review target commit base: `473f1e6d` (Slice 1 accepted)

## Review Scope

Review target files:
- `dayu/host/durable/storage_lifecycle.py`
- `dayu/host/storage_maintenance.py`
- `dayu/host/command.py`
- `dayu/host/open_host.py`
- `dayu/host/api.py`
- `dayu/host/__init__.py`
- `tests/host/test_storage_usage_report.py`
- `tests/host/test_package_exports.py`
- `docs/host/design.md`
- `dayu/host/README.md`
- `tests/README.md`

## Verified Evidence

- `pytest tests/host/test_storage_usage_report.py -q` => 5 passed ✓
- `pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` => 28 passed ✓
- `pyright` target files => 0 errors ✓

## Findings

### F01 — `_file_size_bytes` OSError 不匹配 `report_storage_usage` 公共契约

- **severity**: medium
- **file/line**: `dayu/host/durable/storage_lifecycle.py:389-400`, `dayu/host/storage_maintenance.py:25`
- **status**: needs-more-evidence

**描述**：

`_file_size_bytes` 只 catch `FileNotFoundError` 并返回 0；其它 `OSError`（如 `PermissionError`）会直接传播。`storage_maintenance.report_storage_usage` 的 docstring 声明只抛 `HostApiError`，但实际上 `OSError` 会绕过 `host._run_read` 的 `HostDurableError -> HostApiError` 映射直接传播给调用方。

**分析**：

`_file_size_bytes` 的 docstring 显式声明 `raises OSError: stat 发生非缺失类错误时透传`，说明这是有意设计。`host._run_read` 只捕获 `HostDurableError`，不捕获 `OSError`。在 `HostCommandHandle` 现有代码中，`_audit_sink_options` 和 `_db_path` 也有类似模式——它们不捕获底层 `OSError`。

但从 Service-facing 公共契约角度，`report_storage_usage` 的调用方预期的是 `HostApiError` 或 `HostClosedError`，不预期 `OSError`。

**裁决建议**：

两个选择：
1. 在 `storage_maintenance.report_storage_usage` 中 wrap `OSError` 为 `HostApiError(code=INTERNAL_ERROR)`，保持公共契约纯净。
2. 更新 `report_storage_usage` docstring 显式列出 `OSError`。

选项 1 更符合项目 `HostApiError` 作为 Service-facing 统一错误面的设计意图。若选择选项 2，需同步更新 `Host` Protocol docstring。

---

### F02 — `_assert_report_tables_cover_schema` 在 production reader 中抛 `AssertionError`

- **severity**: low
- **file/line**: `dayu/host/durable/storage_lifecycle.py:278-290`
- **status**: accepted

**描述**：

`_assert_report_tables_cover_schema` 在 `read_storage_usage` 的主路径中抛 `AssertionError`。同模块的 `_count_rows`、`_sum_sqlite_payload_logical_bytes` 等也在 SQLite 返回异常时抛 `AssertionError`。

**分析**：

这个 assertion 的目的是在开发阶段捕获 report 映射与 schema 真源不同步的编程错误，属于 contract guard。它只会在 `_HOST_DURABLE_TABLE_TO_REPORT_FIELD` 与 `HOST_DURABLE_TABLES` 不一致时触发，正常运行中不会命中。

项目现有模式（如 `_count_rows` 中的 `AssertionError`）一致使用 `AssertionError` 作为"SQLite 返回了不该返回的值"的 guard。本 finding 遵循同一模式。

**裁决**：accepted。`AssertionError` 在此处表达的是编程错误（report mapping out of sync with schema），不是运行时可恢复错误。现有的 `_row_int` 和 `_count_rows` 也使用同一模式，保持一致性。

---

### F03 — `HostStorageUsageReport` 不在 `dayu.host.api.__all__` 但通过 `TYPE_CHECKING` import 引用

- **severity**: informational
- **file/line**: `dayu/host/api.py:47-48`, `dayu/host/__init__.py:101-104`
- **status**: accepted

**描述**：

`HostStorageUsageReport` 定义在 `durable/storage_lifecycle.py`，通过 `storage_maintenance.py` re-export 到 `dayu.host.__init__` 的 `__all__`。`api.py` 的 `Host` Protocol 使用 `TYPE_CHECKING` import 引用它。它不在 `api.__all__` 中。

**分析**：

这与 `HostToolingOptions` 的模式完全一致：`HostToolingOptions` 定义在 `tooling.py`，通过 `__init__.py` re-export，不在 `api.__all__` 中。`test_package_exports.py` 的 `EXPECTED_STORAGE_MAINTENANCE_EXPORTS` 明确覆盖了 `HostStorageUsageReport` 和 `report_storage_usage`，并验证它们在包根但不在 `api` 中。`TYPE_CHECKING` import 避免了 `api -> durable schema -> api` 的循环依赖。

**裁决**：accepted。符合项目既有 public contract 风格。

---

### F04 — `storage_maintenance.report_storage_usage` 访问 `HostCommandHandle._db_path()` 私有方法

- **severity**: informational
- **file/line**: `dayu/host/storage_maintenance.py:28`, `dayu/host/command.py:241-253`
- **status**: accepted

**描述**：

`storage_maintenance.report_storage_usage` 通过 `host._db_path()` 获取 DB 路径。`_db_path` 是 `HostCommandHandle` 的私有方法。

**分析**：

`storage_maintenance` 是 Host 内部模块（非 Service / UI 层），访问 Host 内部 handle 的私有方法在 Host 内部是可接受的。`storage_maintenance` 已经通过 `host._run_read()` 访问了另一个私有方法，`_db_path()` 是同一层级的访问。`_db_path` 本身是简单的 typed accessor，只返回 `self._durable_store.options.db_path`。

`_db_path` 的引入是有意为之的——implementation report 明确说明"避免向 facade 暴露 durable store internals"。这比让 `storage_maintenance` 直接访问 `host._durable_store.options.db_path` 更好。

**裁决**：accepted。Host 内部模块访问 Host 内部 handle 的私有 accessor 是合理的分层。

---

### F05 — SQL f-string 表名安全性

- **severity**: informational
- **file/line**: `dayu/host/durable/storage_lifecycle.py:302, 316-319, 336-343, 359-368`
- **status**: accepted

**描述**：

SQL 查询使用 f-string 插入表名，如 `f"SELECT COUNT(*) AS row_count FROM {table_name}"`。

**分析**：

所有表名来源：
- `_count_rows` 的 `table_name` 来自 `_HOST_DURABLE_TABLE_TO_REPORT_FIELD`，其值全部是 `schema.py` 的 `TABLE_*` 常量。
- `_sum_sqlite_payload_logical_bytes` 使用 `TABLE_SQLITE_PAYLOADS` 常量。
- `_sum_artifact_descriptor_logical_bytes` 使用 `TABLE_PAYLOAD_DESCRIPTORS` 常量。
- `_count_orphan_sqlite_payloads` 使用 `TABLE_SQLITE_PAYLOADS` 和 `TABLE_PAYLOAD_DESCRIPTORS` 常量。

所有表名都是硬编码常量，不接受外部输入。值参数使用 `?` 占位符绑定（如 `PayloadKind.ARTIFACT_REF.value`）。

**裁决**：accepted。表名全部来自 schema 常量，无注入风险。

---

### F06 — DB/WAL 缺失时 `FileNotFoundError` 以外的 `OSError` 行为

- **severity**: low
- **file/line**: `dayu/host/durable/storage_lifecycle.py:389-400`
- **status**: accepted

**描述**：

`_file_size_bytes` 只处理 `FileNotFoundError`，其它 `OSError`（如 `PermissionError`、`NotADirectoryError`）直接透传。

**分析**：

docstring 明确声明 `raises OSError: stat 发生非缺失类错误时透传`。对于 operator-facing diagnostic 工具，让 permission error 透传是合理行为——operator 需要知道文件不可读。`FileNotFoundError` 返回 0 是因为 WAL 文件在无写事务时正常不存在。

与 F01 的区别：F01 关注的是公共契约层面的错误类型不一致；本 finding 关注的是 `_file_size_bytes` 本身的 OSError 处理策略是否合理。策略本身合理，但需与 F01 一并决策。

**裁决**：accepted。`_file_size_bytes` 的 OSError 透传策略本身合理，与 F01 一并处理。

---

### F07 — `_field_items` 返回类型标注不精确

- **severity**: informational
- **file/line**: `dayu/host/durable/storage_lifecycle.py:165-167`
- **status**: accepted

**描述**：

`_field_items` 的返回类型标注为 `tuple[tuple[str, int], ...]`，但实现返回的是包含 28 个元素的 tuple of tuples。类型标注在语义上正确（确实是 `tuple[tuple[str, int], ...]`），pyright 不报错。

**分析**：

这是 Python type system 的正常表达方式。`tuple[tuple[str, int], ...]` 精确描述了返回值结构。不需要更精确的 `NamedTuple` 或 `TypedDict`，因为这是私有辅助方法。

**裁决**：accepted。类型标注正确且足够。

---

### F08 — 测试覆盖完整性

- **severity**: informational
- **file/line**: `tests/host/test_storage_usage_report.py`
- **status**: accepted

**描述**：

测试覆盖：
1. ✅ fresh DB 零计数、非负文件大小（`test_fresh_storage_usage_report_has_zero_counts_and_non_negative_file_sizes`）
2. ✅ Session/Run/payload row count、logical bytes、orphan count（`test_storage_usage_report_counts_rows_logical_bytes_and_orphans`）
3. ✅ open_host async handle 入口（`test_open_host_async_handle_reports_storage_usage`）
4. ✅ closed handle 错误语义（`test_open_host_report_storage_usage_fails_after_close`）
5. ✅ `json_value()` 键集合稳定性、非负值（`test_storage_usage_json_value_is_stable_self_explaining_and_non_negative`）
6. ✅ WAL 缺失返回 0（在 test 1 中通过 `_ReadUsageWithDbPath` 验证）

**分析**：

测试充分覆盖了 implementation report 中列出的所有验证点。`test_package_exports.py` 的 `EXPECTED_STORAGE_MAINTENANCE_EXPORTS` 和 `EXPECTED_COMMAND_EXPORTS` 覆盖了导出契约。`test_host_protocol_exposes_public_handle_methods` 覆盖了 `Host` Protocol 的 `report_storage_usage` 方法。

不需要更强的 no-write assertion——`report_storage_usage` 的代码路径只有 `_run_read`（read transaction）和 `Path.stat()`（filesystem read），测试通过验证正确读取结果间接证明了只读语义。

**裁决**：accepted。测试覆盖充分。

---

### F09 — 文档只描述已实现能力

- **severity**: informational
- **file/line**: `docs/host/design.md`, `dayu/host/README.md`, `tests/README.md`
- **status**: accepted

**描述**：

三个文档都只描述当前已实现的只读 `report_storage_usage` 能力，未提前写 Slice 3/4 或 Issue 76 范围。

**分析**：

- `design.md`：新增 Storage Usage Report 小节，明确"不写 EventLog，不改变状态，不扫描 artifact root，不执行 checkpoint，也不删除文件或 row"。
- `README.md`：在接口列表中加入 `report_storage_usage()`，新增"Storage Usage Report"小节。
- `tests/README.md`：Host 测试 inventory 加入 `test_storage_usage_report.py` 覆盖点。

所有文档与代码实现一致。

**裁决**：accepted。

---

### F10 — AGENTS.md 合规性

- **severity**: informational
- **file/line**: 全部 target files
- **status**: accepted

**描述**：

检查项：
- ✅ 中文 docstring：所有新增函数、类、模块均有完整中文 docstring，包含参数、返回值、异常。
- ✅ 严格类型：所有字段为 `int`，无 `Any`、`object`、无类型参数。
- ✅ 无无理由 `getattr`/`hasattr`。
- ✅ 无兼容 facade：`storage_maintenance.report_storage_usage` 是有独立职责的 facade，不是兼容 wrapper。
- ✅ 魔法字符串：表名来自 schema 常量；错误消息中的字段名是辅助函数参数。

**裁决**：accepted。

---

### F11 — Slice 2 边界完整性

- **severity**: informational
- **file/line**: 全部 target files
- **status**: accepted

**描述**：

确认 Slice 2 实现严格遵守边界：
- ✅ 只读 report：`read_storage_usage` 只执行 `SELECT COUNT(*)`、`SELECT COALESCE(SUM(...))`、`Path.stat()`。
- ✅ 不扫描 artifact root：没有 `Path.iterdir()`、`Path.glob()` 或文件系统遍历。
- ✅ 不 checkpoint：没有 `PRAGMA wal_checkpoint` 或等价操作。
- ✅ 不删除：没有 `DELETE`、`DROP` 或 `Path.unlink()`。
- ✅ 不写 EventLog/状态：没有 `INSERT`、`UPDATE` 或 write transaction。
- ✅ 不实现 Slice 3/4：没有 artifact orphan proof、retention policy、cleanup 或 DB VACUUM。

**裁决**：accepted。

---

## Summary

| # | Finding | Severity | Status |
|---|---------|----------|--------|
| F01 | `_file_size_bytes` OSError 不匹配公共契约 | medium | needs-more-evidence |
| F02 | `_assert_report_tables_cover_schema` 抛 `AssertionError` | low | accepted |
| F03 | `HostStorageUsageReport` 不在 `api.__all__` | informational | accepted |
| F04 | `storage_maintenance` 访问 `_db_path()` 私有方法 | informational | accepted |
| F05 | SQL f-string 表名安全性 | informational | accepted |
| F06 | DB/WAL 缺失时 OSError 行为 | low | accepted |
| F07 | `_field_items` 返回类型标注 | informational | accepted |
| F08 | 测试覆盖完整性 | informational | accepted |
| F09 | 文档只描述已实现能力 | informational | accepted |
| F10 | AGENTS.md 合规性 | informational | accepted |
| F11 | Slice 2 边界完整性 | informational | accepted |

## Conclusion

**PASS**

Slice 2 实现严格遵守只读 report 边界，代码质量高，类型安全，测试充分，文档同步。1 个 medium finding（F01）需要 controller 裁决是否在本 slice 修复或 deferred——它不阻塞 slice 功能正确性，但影响公共错误契约的一致性。

Blocking findings: 0（F01 为 needs-more-evidence，由 controller 裁决是否 blocking）
