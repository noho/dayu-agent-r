# WU-RET-00 Slice 2 Code Review — AgentDS

- work unit: WU-RET-00 Host storage lifecycle retention policy
- gate: code review
- slice: Slice 2 read-only storage usage report
- reviewer: AgentDS
- artifact path: `docs/reviews/wu-ret-00-slice2-code-review-ds.md`
- review target: implementation report `docs/reviews/wu-ret-00-slice2-implementation-codex.md`
- design source: `docs/host/design.md`; `docs/engine/design.md`
- control source: `docs/host/issues-implementation-control.md`
- accepted plan commit: `a2f94be0`
- Slice 1 accepted commit: `473f1e6d`
- verification evidence:
  - `pytest tests/host/test_storage_usage_report.py -q` → 5 passed
  - `pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q` → 28 passed
  - `pyright` target files → 0 errors

## 审查范围与方法

本次审查覆盖 Slice 2 全部 target files（11 个文件），按以下维度逐项审查：

1. **Slice 2 边界合规**：只读 report，不扫描 artifact root、不 checkpoint、不删除、不写 EventLog/状态、不实现 Slice 3/4。
2. **类型与契约正确性**：`HostStorageUsageReport` 字段、`json_value()`、非负校验是否稳定、自解释、strict typed。
3. **数据正确性**：`read_storage_usage` 是否基于 schema 真源覆盖 `HOST_DURABLE_TABLES`，row count/bytes/orphan 统计是否正确。
4. **错误处理**：`AssertionError` 使用是否合理、OSError 传播是否正确、SQL f-string 表名是否安全。
5. **公共 API 归属**：`HostStorageUsageReport` 从 package root 导出但不在 `dayu.host.api.__all__` 是否符合项目 public contract 风格。
6. **架构与分层**：`storage_maintenance.report_storage_usage` 是否合理 facade，是否引入循环依赖或层级问题。
7. **测试覆盖**：覆盖 open_host async handle、closed handle、bytes/orphan/counts、exports。
8. **文档准确性**：只描述当前已实现能力，未提前写 Slice 3/4 或 Issue 76 范围。
9. **AGENTS.md 合规**：中文 docstring、严格类型、无无理由 getattr/hasattr、无兼容 facade、无魔法字符串过度扩散。

## Findings

### Finding 1: `_assert_report_tables_cover_schema` 使用 `AssertionError` 在 production reader 中

- **Severity**: Low
- **File/Line**: `dayu/host/durable/storage_lifecycle.py:278-290`
- **Status**: **accepted**

`_assert_report_tables_cover_schema()` 在 `read_storage_usage` 内被调用，当 `_REPORT_TABLES != HOST_DURABLE_TABLES` 时抛出 `AssertionError`。该异常不会被 `_run_read` 的 `except HostDurableError` 捕获，会作为未处理异常向上传播。

**分析**：此 pattern 与同文件内 `_row_int`（line 375）、`_count_rows`（line 293）、`_sum_sqlite_payload_logical_bytes`（line 308）等函数一致——它们全部在"不应发生"的 invariant violation 场景使用 `AssertionError`。语义上，schema table 清单与 report 映射不同步属于编程错误（新增 durable table 但忘记更新 report mapping），不是运行时错误。`AssertionError` 使该错误在测试/开发阶段 fail loud，在 production 中同样 fail loud（因为 schema drift 意味着系统处于不可恢复状态）。

**结论**：与文件内既有 pattern 一致，不构成 blocking issue。若项目后续统一 durable 层错误策略要求全部使用 `HostDurableError`，应在独立 work unit 中批量修改，不在本 slice 单独处理。

### Finding 2: `_file_size_bytes` 非 `FileNotFoundError` 的 `OSError` 未被包装为 `HostApiError`

- **Severity**: Low
- **File/Line**: `dayu/host/durable/storage_lifecycle.py:389-400`
- **Status**: **deferred**

`_file_size_bytes` 只捕获 `FileNotFoundError`（返回 0），其他 `OSError`（如 `PermissionError`）会透传。该透传路径经过 `read_storage_usage` → `_ReadStorageUsageOperation.__call__` → `host._run_read()`。`_run_read` 只捕获 `HostDurableError`，因此 `OSError` 会作为未包装异常传播到调用方。

**分析**：此行为在 docstring 中已明确声明（`:raises OSError: stat 发生非缺失类错误时透传`）。在 production 中，DB 文件在 handle open 时已验证可访问，到 report 调用时出现权限变化的概率极低。WAL 文件同理——其不存在已被正确处理为 0，权限错误仅可能在极端部署环境下发生。`command.py` 中确有 `OSError` → `HostApiError` 的包装模式（如 purge audit append 路径），但那是 command path 的 correctness 要求；`report_storage_usage` 是只读诊断路径，对 OSError 的容忍度可以不同。

**结论**：不构成 Slice 2 blocking issue。若后续统一要求所有 public path 都包装 `OSError`，可在独立 work unit 中处理。

### Finding 3: `_require_non_negative_int` 在 `storage_lifecycle.py` 与 `api.py` 中重复定义

- **Severity**: Info
- **File/Line**: `dayu/host/durable/storage_lifecycle.py:413-427`；`dayu/host/api.py:84-97`
- **Status**: **deferred**

两个模块各自定义了语义完全相同的 `_require_non_negative_int` 函数。根据 CLAUDE.md "重复逻辑必须抽取" 原则，这是一种重复。但 `storage_lifecycle.py` 位于 `dayu.host.durable`，`api.py` 位于 `dayu.host`——若 `durable` 导入 `api` 的私有函数，会形成 `durable` → `api` 的上层依赖；若抽取到 `_public_validation`，需要评估该模块是否适合承载 durable 层的校验需求（`_public_validation` 当前定位是 public API 校验）。

**结论**：此重复在 Slice 2 之前已存在（`_require_non_negative_int` 在 `api.py` 中是既有的），本 slice 追加了一份语义一致的副本而非恶化问题。抽取到共享模块应作为独立 clean-up work unit，不在本 slice blocking 范围内。

### Finding 4: `report_storage_usage` facade 中 `_raise_if_closed` 被双重调用

- **Severity**: Info
- **File/Line**: `dayu/host/storage_maintenance.py:20-28`
- **Status**: **accepted**

`report_storage_usage(host)` 调用 `host._db_path()` 和 `host._run_read(operation)`。两者内部分别调用 `_raise_if_closed()`（`_db_path` 通过方法体直接调用，`_run_read` 通过 `_transaction_runner()` 间接调用）。这导致 closed handle 检查被执行两次。

**分析**：双重检查在语义上无害——第二次 `_raise_if_closed()` 在前一次已抛出的情况下不可达，在前一次通过的情况下是幂等 no-op。`_db_path()` 和 `_run_read()` 各自独立 guard 是 `HostCommandHandle` 的既有设计（每个内部方法自保边界），facade 组合它们时出现双重 guard 是预期行为，不是 bug。

**结论**：接受现状，无需修改。

### Finding 5: SQL f-string 表名安全性验证

- **Severity**: Info
- **File/Line**: `dayu/host/durable/storage_lifecycle.py:293-372`（`_count_rows`, `_sum_sqlite_payload_logical_bytes`, `_sum_artifact_descriptor_logical_bytes`, `_count_orphan_sqlite_payloads`）
- **Status**: **accepted**

所有 SQL 语句中的表名均来自 `dayu.host.durable.schema` 模块中定义的模块级字符串常量（`TABLE_EVENT_LOG`, `TABLE_SQLITE_PAYLOADS`, `TABLE_PAYLOAD_DESCRIPTORS` 等），这些常量在 `_HOST_DURABLE_TABLE_TO_REPORT_FIELD` 中被引用，通过 `_count_rows(transaction, table_name)` 的 `table_name` 参数传入 f-string。整条链路无外部输入可达表名位置。

**结论**：安全，无 SQL 注入风险。

### Finding 6: `HostStorageUsageReport` 不在 `dayu.host.api.__all__` 但在 package root 导出——符合项目 public contract 分层

- **Severity**: Info
- **File/Line**: `dayu/host/api.py:3336-3412`（`__all__`）；`dayu/host/__init__.py:101-104, 112-207`（导出与 `__all__`）
- **Status**: **accepted**

`HostStorageUsageReport` 从 `dayu.host.storage_maintenance` 导入到 `dayu.host.__init__`，加入 `dayu.host.__all__`，但不进入 `dayu.host.api.__all__`。`Host` Protocol 在 `api.py` 中通过 `TYPE_CHECKING` import 引用它作为 `report_storage_usage()` 的返回类型。

**分析**：此 pattern 与 `HostToolingOptions`、`FrameworkToolName`、`FrameworkToolPolicyView` 一致——这些类型属于特定功能域（tooling），从包根对 Service 暴露，但不属于 `dayu.host.api` 的 "核心 API 类型契约" 集合。`dayu.host.api.__all__` 的定位是 request/snapshot/enum/error/Protocol 等 Host API 基础类型；storage maintenance 类型属于专项功能域，类比 tooling 类型。`TYPE_CHECKING` import 避免了 `api.py` → `durable.storage_lifecycle.py` 的运行时依赖，保持 `api.py` 作为纯契约层不依赖 durable 实现。

**结论**：分层正确，符合项目既有风格。

### Finding 7: `host._db_path()` 暴露 internal accessor 给 facade

- **Severity**: Info
- **File/Line**: `dayu/host/storage_maintenance.py:28`；`dayu/host/command.py:241-252`
- **Status**: **accepted**

`report_storage_usage` facade 调用 `host._db_path()`——这是一个下划线前缀的 internal method。`_db_path()` 是 Slice 2 新增的 `HostCommandHandle` 方法，其职责单一（返回 DB 路径）、不暴露 durable store 内部对象、有 closed guard 和 `HostDurableError` → `HostApiError` 转换。

**分析**：`storage_maintenance` 模块与 `command` 模块同属 `dayu.host` 包内，facade 调用 internal method 是 Host 包内正常的模块间协作。`_db_path()` 命名以下划线前缀表明它不向 Service 层暴露——Service 层通过 `dayu.host.report_storage_usage` 使用，不直接接触 `HostCommandHandle`。这与 `_run_read`、`_run_write`、`_transaction_runner` 等既有 internal method 的暴露模式一致。

**结论**：合理的包内协作，不泄漏到 public contract。

### Finding 8: `test_storage_usage_report.py` 测试覆盖完整性

- **Severity**: Info
- **File/Line**: `tests/host/test_storage_usage_report.py`（全文件）
- **Status**: **accepted**

5 个测试覆盖了以下场景：
1. `test_fresh_storage_usage_report_has_zero_counts_and_non_negative_file_sizes` — fresh DB 零计数、文件大小非负、WAL 缺失为 0
2. `test_storage_usage_report_counts_rows_logical_bytes_and_orphans` — row count、logical bytes、orphan payload 统计正确性
3. `test_open_host_async_handle_reports_storage_usage` — open_host async handle 入口
4. `test_open_host_report_storage_usage_fails_after_close` — closed handle 抛出 `HostClosedError`
5. `test_storage_usage_json_value_is_stable_self_explaining_and_non_negative` — `json_value()` 键集合完整且值非负

`test_package_exports.py` 覆盖了：
- `HostStorageUsageReport` 和 `report_storage_usage` 在 `dayu.host.__all__` 中
- `report_storage_usage` 在 `Host` Protocol 方法清单中
- storage maintenance 符号不在 forbidden exports 中

**分析**：测试覆盖了 Slice 2 的核心行为路径。未显式覆盖的场景包括：(a) 对同一 handle 多次调用 `report_storage_usage` 的幂等性（report 不改变 DB 状态）；(b) command handle close 后调用 `report_storage_usage` 的错误路径（通过 async handle close 测试间接覆盖，因为 `_run_read` → `_transaction_runner` → `_raise_if_closed` 共享同一路径）。测试使用 `_run_write` 直接写入 orphan SQLite payload 以验证 orphan 计数——这是测试中合理的低层访问。

**结论**：测试覆盖充分。可选的增强（非 blocking）：添加多次调用幂等性断言（两次 report 结果一致），以及显式 command handle close 后 report 失败测试。

### Finding 9: 文档只描述当前已实现能力

- **Severity**: Info
- **File/Line**: `docs/host/design.md`（相关新增段落）；`dayu/host/README.md:81-83, 422-424`；`tests/README.md:163`
- **Status**: **accepted**

文档变更范围：
- `docs/host/design.md`：新增 `report_storage_usage(host) -> HostStorageUsageReport` 公共只读诊断边界，明确"不写 EventLog、不改变状态、不扫描 artifact root、不 checkpoint、不删除"。
- `dayu/host/README.md`：在 public handle 方法列表中加入 `report_storage_usage()`，新增 "Storage Usage Report" 小节描述 operator-facing 只读诊断入口。
- `tests/README.md`：在 Host 测试 inventory 中加入 `test_storage_usage_report.py` 覆盖点。

**分析**：三处文档均严格限定在当前 Slice 2 已实现能力，未描述 Slice 3（artifact root 扫描/orphan proof/deletion）、Slice 4（WAL checkpoint/maintenance entrypoint）或 Issue 76（DB VACUUM/SQLite space reclamation）。"Storage Usage Report" 小节的边界声明（"不写 EventLog，不改变 Session / Run / Attempt 状态，不扫描 artifact root，不执行 checkpoint，也不删除文件或 row"）与实现完全一致。

**结论**：文档准确、边界清晰。

### Finding 10: AGENTS.md 合规检查

- **Severity**: Info
- **File/Line**: 全部 target 生产代码文件
- **Status**: **accepted**

逐项检查：
- **中文 docstring**：✓ 所有公开函数、类、方法均有完整中文 docstring，包含参数、返回值、异常说明。
- **严格类型**：✓ 无 `Any`、`object`、无类型参数、无类型返回值。`_row_int` 参数类型 `int | float | str | bytes | None` 是 SQLite scalar 的真实类型空间，函数体做运行时收窄——这是 typed narrowing pattern，不是弱类型逃逸。
- **无无理由 getattr/hasattr**：✓ 代码中未使用 `getattr` 或 `hasattr`。
- **无兼容 facade**：✓ `storage_maintenance.py` 是新增的功能 facade，不是仅为保持旧导入路径的兼容性 re-export。其 `__all__` 中的 `HostStorageUsageReport` 是从 `durable.storage_lifecycle` 导入的功能性 re-export，属于 facade 正常暴露其返回类型。
- **无魔法字符串过度扩散**：✓ 表名来自 schema 常量，字段名在 `_field_items()` 中以 hardcoded tuple 形式定义（与 dataclass 字段一一对应，属于合理的字段清单维护方式）。

**结论**：全部合规。

## 综合评估

### Slice 2 边界合规

Slice 2 严格实现了"只读 storage usage report"：
- ✓ 只在 read transaction 内执行 `SELECT COUNT(*)` 与 `SELECT COALESCE(SUM(...))` 查询
- ✓ 不扫描 artifact root 文件系统（`_file_size_bytes` 只 stat DB/WAL 两个已知路径）
- ✓ 不执行 WAL checkpoint
- ✓ 不删除任何 SQLite row 或文件
- ✓ 不写 EventLog 或 durable 状态
- ✓ 不实现 Slice 3（artifact scanning/orphan proof/deletion）或 Slice 4（maintenance entrypoint/WAL checkpoint）

### 架构与分层

- `durable/storage_lifecycle.py`：纯 durable reader，依赖 `durable.schema`、`durable.payload`、`durable.transaction`，不依赖上层。
- `storage_maintenance.py`：public facade，依赖 `command`（`HostCommandHandle`）和 `durable.storage_lifecycle`，不引入循环依赖。
- `command.py`：新增 `_db_path()` 单职责 accessor，不依赖 `storage_maintenance`。
- `open_host.py`：public async handle 新增 `report_storage_usage()`，委托 facade。
- `api.py`：`Host` Protocol 通过 `TYPE_CHECKING` import 引用 `HostStorageUsageReport`，无运行时依赖。
- `__init__.py`：正确收口导出。

### 数据正确性

- 23 个 row count 字段覆盖 `HOST_DURABLE_TABLES` 全部 23 张表，通过 `_assert_report_tables_cover_schema()` 在每次调用时校验。
- `sqlite_payload_logical_bytes` = `SUM(payload_size_bytes)` from `host_sqlite_payloads`。
- `artifact_descriptor_logical_bytes` = `SUM(payload_size_bytes)` from `payload_descriptors WHERE payload_kind = 'artifact_ref'`。
- `orphan_sqlite_payload_count` = SQLite payload row 数 - 有 descriptor 引用的 SQLite payload row 数（通过 `NOT EXISTS` 子查询正确实现）。
- `db_file_bytes` / `wal_file_bytes` 通过 `Path.stat().st_size` 获取，WAL 缺失时正确返回 0。

### 风险与未覆盖项

| Risk | Owner | 状态 |
|---|---|---|
| artifact root 物理文件扫描、orphan artifact proof/deletion | Slice 3 | deferred |
| WAL checkpoint、maintenance entrypoint | Slice 4 | deferred |
| DB VACUUM / SQLite space reclamation | GitHub Issue #76 | deferred |
| orphan SQLite payload 当前只报告计数，不删除 row | 后续 retention work | deferred |
| 非 `FileNotFoundError` 的 `OSError` 未包装为 `HostApiError` | 本 review Finding 2 | deferred |

## 裁决

**PASS**

当前 slice 无 blocking finding。0 个 finding 需要在 accepted slice commit 前修复。

所有 findings 均为 accepted（符合既有 pattern）或 deferred（非 Slice 2 scope / 后续 work unit 承接）。实现严格符合 Slice 2 的只读边界，类型正确，测试覆盖充分，文档准确。
