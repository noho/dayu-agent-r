# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-G S3

## Scope

- Mode: current changes (unstaged workspace diff)
- Branch: `phaseflow/host-issues-control`
- Base: `22683a8e` (S2 accepted commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-s3-code-review-mimo.md`
- Included scope: 15 files (+338/-74) — S3 typed SEC download rejection registry
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`

## Findings

未发现实质性问题。

逐项检查：

### 1. Owner boundary 正确性

**事实产生**：
- `sec_download_state._record_rejection(...)` 构造 `DownloadRejectionEntry`（line 148-155）。
- SC13 filtering 通过同一 helper 写入。
- `ingestion_runtime.py:3908-3915` 直接构造 `DownloadRejectionEntry`，使用自身 `_DOWNLOAD_REJECTION_CLASSIFICATION_VERSION`，不泄漏 SEC pipeline 常量。✅

**事实校验**：
- `DownloadRejectionEntry.__post_init__` 校验所有 6 个必填字段非空，并通过 `parse_sec_form_type(...)` 校验 `form_type` 为 canonical SEC 单一 form。
- `DownloadRejectionEntry.from_dict(...)` 校验字段类型、空值、form 类型，以及 `expected_document_id` 与条目 `document_id` 一致性。✅

**事实持久化**：
- `FilingMaintenanceRepositoryProtocol` 签名改为 `DownloadRejectionRegistry`。
- `_fs_maintenance_core.py` 读取时：缺文件返回空；非 dict 条目、字段缺失/类型非法、key/document_id 不一致时抛 `ValueError`（fail closed）。
- `_fs_maintenance_core.py` 保存时：校验 key 与 `entry.document_id` 一致，通过 `entry.to_dict()` 序列化。✅

**事实消费**：
- `_is_rejected(...)` 只读 typed `entry.download_version`（line 118）。
- `warn_insufficient_filings(...)` 只读 typed `entry.form_type`（line 107）。
- SC13/workflow 全部传递 typed `DownloadRejectionRegistry`。✅

### 2. 无残留 `dict[str, dict[str, str]]` 作为 public contract

Source scan `rg -n 'dict\[str, dict\[str, str\]\]' dayu/fins/pipelines/... dayu/fins/storage tests/fins` 仅命中 `_fs_maintenance_core.py:111`——局部序列化 payload，不是 public contract 或兼容 shim。`ingestion_runtime.py` 零匹配。✅

### 3. FS repository fail closed

旧代码 `except (ValueError, OSError): return {}` 静默吞掉坏 registry。新代码直接传播 `_read_json_object(path)` 和 `DownloadRejectionEntry.from_dict(...)` 的异常。坏 JSON、坏条目、坏字段、key/document_id 不一致全部失败关闭。✅

### 4. `ingestion_runtime.py` 使用自身 version

`_DOWNLOAD_REJECTION_CLASSIFICATION_VERSION` 是 ingestion runtime 自有的 rejection classification version，不是 SEC pipeline download version。这是正确的 producer-owned 版本选择——generic runtime 不应泄漏 SEC pipeline 常量。✅

### 5. SC13/diagnostics 从同一 typed registry 派生

- SC13 filtering 所有 6 个函数签名改为 `Optional[DownloadRejectionRegistry]`。
- `warn_insufficient_filings(...)` 签名改为 `DownloadRejectionRegistry`，通过 `entry.form_type` 统计 6-K filtered。
- SEC pipeline `_is_rejected(...)` / `_record_rejection(...)` 签名改为 `DownloadRejectionRegistry`。✅

### 6. S1/S2/S4 语义未改变

- S1 SEC form parser：仅通过 `parse_sec_form_type(...)` 复用，未修改。
- S2 CN/HK report selection：未修改。
- S4 XBRL total contract：未修改。✅

### 7. Tests、pyright、README

- **Tests**: 87 passed（storage/pipeline/stream）+ 1 passed（ingestion runtime）。
- **Pyright**: 0 errors。
- **Source scan**: 仅 `_fs_maintenance_core.py:111` 局部序列化 payload。
- **README**: `dayu/fins/README.md` 更新 typed SEC download rejection registry 稳定契约。✅

## Residual Risk

- 旧 workspace 中已存在的 `_download_rejections.json` 若缺少 `document_id` 或字段类型不合法，现在会 fail closed；符合 S3 要求，但没有迁移兼容。
- `ingestion_runtime.py` 使用自身 runtime rejection classification version，不与 SEC pipeline version 对齐——这是有意的 producer-owned 版本选择。

## Verdict

**PASS** — S3 正确实现了 plan 中的 typed SEC download rejection registry。`DownloadRejectionEntry` / `DownloadRejectionRegistry` 是唯一 contract，仓储 fail closed，pipeline/diagnostics/SC13 全部消费 typed registry，无 `dict[str, dict[str, str]]` public contract 残留。
