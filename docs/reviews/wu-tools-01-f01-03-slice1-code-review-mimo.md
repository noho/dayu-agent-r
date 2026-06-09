# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f01-03`
- Base: `main`
- Output file: `docs/reviews/wu-tools-01-f01-03-slice1-code-review-mimo.md`
- Included scope:
  - `dayu/fins/ingestion_runtime.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `dayu/fins/README.md`
  - `tests/README.md`
  - 只读参考 `docs/host/issues-implementation-control.md`、`docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`、`docs/reviews/wu-tools-01-f01-03-slice1-implementation-codex.md`
- Excluded scope: controller-owned dirty file `docs/host/issues-implementation-control.md` 未修改
- Parallel review coverage: 无

## Findings

### 1-未修复-低-模块级 docstring 未提及 upload 能力

- **入口/函数**: 模块级 docstring
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:1-6`
- **输入场景**: 任何阅读模块 docstring 的开发者或工具
- **实际分支**: docstring 描述为"本模块只承载 Fins 自有 ingestion job 的 typed 请求、结果摘要、持久化 job record、文件系统 job store 与运行时入口"
- **预期行为**: docstring 应覆盖模块当前全部职责，包括 upload job contract
- **实际行为**: docstring 未提及 upload 请求类型、upload runner 协议或 upload job lifecycle
- **直接证据**: `dayu/fins/ingestion_runtime.py:1-6` — "本模块只承载 Fins 自有 ingestion job 的 typed 请求、结果摘要、持久化 job record、文件系统 job store 与运行时入口。它不实现真实网络下载、Host wait adapter、tool provider 或 CLI。" 未提及 upload
- **影响**: 开发者阅读模块入口时可能遗漏 upload 能力；不影响运行时行为
- **建议改法和验证点**: 在 docstring 中补充 upload job contract 描述；pyright 和测试不受影响
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-FinsIngestionJobRecord docstring 未提及 upload

- **入口/函数**: `FinsIngestionJobRecord` 类 docstring
- **文件(行号)**: `dayu/fins/ingestion_runtime.py:648-649`
- **输入场景**: 阅读 job record 数据类的开发者
- **实际分支**: `operation_kind` 属性描述为"下载或预处理"
- **预期行为**: 描述应包含"下载、预处理或上传"
- **实际行为**: 仅提及"下载或预处理"
- **直接证据**: `dayu/fins/ingestion_runtime.py:649` — `operation_kind: 下载或预处理。`
- **影响**: 开发者可能误认为 job record 不支持 upload 操作类型；不影响运行时
- **建议改法和验证点**: 改为 `operation_kind: 下载、预处理或上传。`
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Verdict

**pass-with-findings**

0 blocking findings。2 个低严重性 finding 均为 docstring 遗漏，不影响运行时行为、类型安全或测试正确性。

## 针对审查重点的逐项结论

### 1. Upload contract 强类型、有界、可序列化、使用 SourceKind

- `FinsUploadFilingRequest` / `FinsUploadMaterialRequest` 均为 `frozen=True` dataclass，字段全部显式声明。
- `FinsUploadRequest = FinsUploadFilingRequest | FinsUploadMaterialRequest` 为封闭 union。
- filing/material 分流使用已有 `SourceKind.FILING` / `SourceKind.MATERIAL`，`_validate_upload_source_kind` 在 job 创建前校验请求类型与 SourceKind 一致性。未新增 `FinsUploadKind`。
- `FinsUploadResultSummary` 字段全为有界 JSON-compatible 类型；`to_json_summary()` 通过 `_bounded_text` / `_bounded_text_tuple` / `_optional_bounded_text` 执行长度和路径分隔符校验。
- `FinsJobCancellationChecker` 为 Protocol，`__call__ -> bool`，签名显式。
- `FinsUploadRunner` 为 Protocol，`run_upload(request, *, cancellation_checker) -> FinsUploadResultSummary`，签名强类型。
- `_RuntimeJobCancellationChecker` 为 `frozen=True` dataclass，持有 `job_store: FinsIngestionJobStore` 和 `job_id: str`。

**结论**: 满足。

### 2. start_upload 长事务建模、create 后 submit 前取消、runner 取消检查来源

- `start_upload` 沿用 `start_download` / `start_preprocess` 语义：ticker 归一化 -> 请求校验 -> 摘要构建 -> 取消 checkpoint -> 持久化 queued record -> 取消桥接 -> executor submit。
- `_CancelOnSecondCheckToken` 测试覆盖 create 后 submit 前取消：第二次 `_is_start_cancelled` 返回 `True`，runtime 调用 `_save_cancelled` 把 job 写入 `cancelled` 终态且不提交后台操作（`executor.operations == []`）。
- `_RuntimeJobCancellationChecker.__call__` 读取 `job_store.read_job(job_id)`，检查 `cancellation_requested` 或 `status in {CANCELLING, CANCELLED}`。取消检查来源是 Fins job store，非外部 token。
- `_run_upload_job` 在 `run_upload` 完成后再次读取 job store 检查取消状态，与 download/preprocess 一致。

**结论**: 满足。

### 3. 未装配 production upload runner 时明确 failed terminal

- `_run_upload_job` 第 1611 行：`if self.upload_runner is None:` 分支写入 `_save_failed`，message 为 `_UNSUPPORTED_UPLOAD_RUNTIME_MESSAGE`（"不支持的上传运行时 (unsupported upload runtime): production upload runner 尚未装配"），result_summary 为 `FinsUploadResultSummary(source_kind=request.source_kind, status="failed")`。
- 该路径不读取本地上传文件、不写 source/blob 仓储、不伪造成功。
- 测试 `test_start_upload_without_runner_writes_failed_terminal_record` 验证了 `FAILED` 终态、`source_kind` 传递和 failure message 内容。

**结论**: 满足。

### 4. Job record 序列化/反序列化约束与路径泄漏

- `_validate_record_operation_fields` 对 upload 约束：`source is not None` -> raise；`source_kind is None` -> raise。即 upload 必须 `source=None` 且 `source_kind` 非空。
- `_record_from_json` 反序列化后调用 `_record_to_json(record)` 做 round-trip 校验。
- `_upload_request_summary` 只保存 `file_count: len(request.files)`，不保存 `files` 中的 `Path` 对象。
- 测试 `test_start_upload_persists_queued_record` 断言 `str(tmp_path) not in payload_text` 和 `"aapl-10k.pdf" not in payload_text`。
- 测试 `test_job_serialization_validates_upload_operation_shape` 手动 corrupt `source_kind=None` 后验证反序列化拒绝。

**结论**: 满足。

### 5. AGENTS.md 约束合规

- 分层：`ingestion_runtime.py` 不 import `dayu.host` / `dayu.engine` / `dayu.service` / `dayu.ui`。
- 类型：所有新增函数/方法均有类型注解；无 `Any`、`object`、无类型参数或无类型返回值。
- docstring：所有新增类和模块级私有函数均有中文 docstring，包含 Args / Returns / Raises。存在 2 个已有 docstring 未更新的低严重性 finding。
- 无兼容 wrapper / facade / re-export。
- 无魔法字符串：所有字符串字面量均为命名常量（`_UPLOAD_ACTION_AUTO` 等）或 schema 例外。
- 模块级私有辅助函数：`_normalize_upload_request`、`_normalize_upload_action`、`_validate_upload_source_kind`、`_upload_request_summary`、`_validate_upload_file_count`、`_optional_non_negative_int` 均为模块级私有函数。

**结论**: 满足（2 个低严重性 docstring 遗漏不构成约束违反）。

### 6. 测试覆盖与 README 更新

- 测试覆盖：35 passed。新增测试覆盖 queued upload persistence、ticker normalization、create-before-submit cancellation、unsupported runner terminal failure、bounded result summary、SourceKind discrimination、file path leakage prevention、serialization validation。
- README 更新：`dayu/fins/README.md` 和 `tests/README.md` 更新命中各自职责，描述当前代码已实现的事实，未过度扩写。

**结论**: 满足。

### 7. 是否阻塞后续迁移

- `FinsUploadRunner` 协议设计允许 Slice 4 注入 production runner 而不修改 `FinsIngestionRuntime`。
- `FinsUploadRequest` union 使用 `SourceKind` 区分，允许后续 SEC/CN upload workflow 按 source_kind 分流。
- `FinsJobCancellationChecker` 协议允许后续 upload workflow 在任意 checkpoint 观察取消。
- job record 序列化约束与 download/preprocess 一致，不阻塞后续 wait adapter 绑定。

**结论**: 当前 contract 不阻塞后续 Slice 2-5 迁移。

## Open Questions

- 无。

## Residual Risk

| Risk | Classification | Owner / Destination |
|---|---|---|
| Production upload runner 未接入，默认 runner absent 会失败终态。 | covered by later approved slice | WU-TOOLS-01-F01-03 Slice 4 |
| Upload awaiting tool / wait adapter 未接入。 | covered by later approved slice | WU-TOOLS-01-F01-03 Slice 5 |
| `start_upload` 需纳入 Issue 129 prepare / activate tracking。 | tracked by existing issue | GitHub Issue 129 |
| Runner 抛出异常时的 upload-specific failed terminal 路径未被 upload 专项测试直接覆盖（间接由 preprocess `_save_failed_from_exception` 测试覆盖同一机制）。 | low risk, covered by shared mechanism | 测试 |

无 unclassified residual risk。
