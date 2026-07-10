# WU-SEMANTIC-OWNERSHIP-01 P3-G S3 Implementation - Codex

## 动机校验

S3 动机成立。实现前的 SEC 下载拒绝注册表以 `dict[str, dict[str, str]]` 在仓储、下载 pipeline、SC13 过滤和诊断之间传递；文件系统仓储读取还会在 registry 损坏时返回空字典，并把 payload 值静默 `str(...)`。这会把“被拒绝 filing 的事实”从 owner 边界扩散到多个消费者各自解释，且坏状态可能被吞掉后导致重复下载或诊断误判。

本次只实现 S3：typed SEC download rejection registry。未进入 S4 XBRL、未改变 CN/HK S2 语义、未修改 S1 parser，除非通过既有 `parse_sec_form_type(...)` 复用 SEC form 校验。

## 文件变更

- `dayu/fins/domain/document_models.py`
  - 新增 frozen `DownloadRejectionEntry` 和 `DownloadRejectionRegistry`。
  - `DownloadRejectionEntry` 要求 `document_id`、`reason`、`category`、`form_type`、`filing_date`、`download_version` 全部显式非空；`form_type` 通过 domain parser 校验为 canonical SEC 单一 form。
  - 新增 `from_dict(...)` 和 `to_dict()`，作为 JSON decode/encode 的唯一 typed contract。
- `dayu/fins/storage/repository_protocols.py`
  - `FilingMaintenanceRepositoryProtocol.load_download_rejection_registry(...)` / `save_download_rejection_registry(...)` 改为 typed registry。
- `dayu/fins/storage/_fs_maintenance_core.py`
  - 读取缺文件仍返回空 registry。
  - JSON 非法、条目非对象、字段缺失/类型非法、registry key 与条目 `document_id` 不一致时失败关闭。
  - 保存时校验 key 与 entry `document_id` 一致，并只通过 `entry.to_dict()` 序列化。
- `dayu/fins/storage/fs_filing_maintenance_repository.py`
  - facade 签名同步 typed registry。
- `dayu/fins/pipelines/sec_download_state.py`
  - `_record_rejection(...)` 写入 `DownloadRejectionEntry`。
  - `_is_rejected(...)` 只读取 typed `entry.download_version`。
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_sc13_filtering.py`
- `dayu/fins/pipelines/sec_download_diagnostics.py`
  - registry 签名和消费改为 `DownloadRejectionRegistry`；诊断使用 typed 属性而非 dict lookup。
- `dayu/fins/ingestion_runtime.py`
  - 该文件存在额外 rejected artifact -> download rejection registry 写入点；为保持同一 owner contract，改为写入 `DownloadRejectionEntry`，未改变 rejected artifact 流程。
- `tests/fins/test_fins_storage_provider.py`
  - 覆盖 typed registry roundtrip、坏字段 fail closed、key/document_id 冲突保存失败。
- `tests/fins/test_sec_pipeline_download.py`
  - 覆盖 SEC rejection helper 写入/消费 typed registry、版本匹配和 overwrite 行为；真实 6-K filter 场景断言 JSON 持久化包含 `document_id`。
- `tests/fins/test_fins_ingestion_runtime.py`
  - 覆盖 ingestion runtime rejected artifact 写入 typed registry。
- `dayu/fins/README.md`
  - 按 README 约束补充当前已实现的 typed SEC 下载拒绝注册表稳定契约。

## Source Finding / Plan Item 覆盖

- typed entry：已新增 `DownloadRejectionEntry`，字段为 `document_id`、`reason`、`category`、`form_type`、`filing_date`、`download_version`。
- repository load：缺文件返回空；坏 JSON/坏 entry/坏字段失败关闭，不再静默 coercion。
- repository save：只接受 typed registry，并通过 `to_dict()` 持久化。
- pipeline consumption：SEC download state、pipeline facade、single filing workflow、download workflow、SC13 filtering、diagnostics 均消费 typed registry。
- no compatibility shim：未增加 typed-to-dict 兼容 wrapper；`_fs_maintenance_core.py` 中唯一 `dict[str, dict[str, str]]` 是写 JSON 的局部序列化 payload。
- extra consumer：`ingestion_runtime.py` 原本也直接写 registry；已同步到 typed owner contract，避免 pyright/语义残留。

## Owner Boundary / Propagation Audit

- 产生：SEC 下载拒绝事实由 `sec_download_state._record_rejection(...)` 产生；SC13 过滤通过该 helper 写入；generic ingestion runtime rejected artifact 路径直接构造同一 `DownloadRejectionEntry`。
- 校验：`DownloadRejectionEntry.__post_init__` 和 `from_dict(...)` 校验必填字段、canonical SEC form 和 key/document id 一致性。
- 持久化：`FilingMaintenanceRepositoryProtocol` 是 registry 仓储边界；文件系统实现读取时解析 typed entry，保存时通过 `to_dict()` 写 `_download_rejections.json`。
- 消费：`_is_rejected(...)` 只按 typed `download_version` 判断当前版本命中；`warn_insufficient_filings(...)` 只按 typed `form_type` 统计 6-K filtered；SC13/download workflow 只传递 typed registry。
- 用户/LLM 可见输出：本 slice 不改 tool schema 或 prompt。间接可见的下载 warning/summary 仍由 pipeline 结果产生；其拒绝计数和 warning 依据 typed registry，不再依赖散字典字段猜测。

## Source Scan 分类

执行命令：

```bash
source .venv/bin/activate && rg -n "dict\[str, dict\[str, str\]\]|load_download_rejection_registry|save_download_rejection_registry|rejection_registry|DownloadRejection" dayu/fins/pipelines/sec_sc13_filtering.py dayu/fins/pipelines/sec_download_state.py dayu/fins/pipelines/sec_download_diagnostics.py dayu/fins/pipelines/sec_pipeline.py dayu/fins/storage tests/fins
```

分类：

- `DownloadRejectionRegistry` / `DownloadRejectionEntry` import、签名、构造：S3 typed contract 预期命中。
- `load_download_rejection_registry` / `save_download_rejection_registry`：仓储协议和实现预期命中。
- `rejection_registry`：pipeline/workflow/test 中 typed registry 传递预期命中。
- `_fs_maintenance_core.py` 的 `payload: dict[str, dict[str, str]]`：仅为 JSON 文件写入前的局部序列化对象，不是 public contract 或兼容 shim。
- `tests/fins/...` 命中：新增/更新测试断言。
- 未发现旧 `dict[str, dict[str, str]]` 作为 pipeline/storage public contract 残留。

额外 scan：

```bash
source .venv/bin/activate && rg -n "dict\[str, dict\[str, str\]\]|load_download_rejection_registry|save_download_rejection_registry|rejection_registry|DownloadRejection" dayu/fins/ingestion_runtime.py
```

分类：仅剩 `DownloadRejectionEntry` import、load、typed 写入和 save。

## 验证

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py -q`
  - 结果：`87 passed, 3 warnings`
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py::test_start_download_persists_rejected_filing_artifact -q`
  - 结果：`1 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- source scan
  - 结果：仅 typed contract / serialization boundary / tests 命中，分类见上。
- `git diff --check`
  - 结果：通过，无 whitespace 错误。

覆盖率说明：本 slice 未新增 production helper/model 文件；`DownloadRejectionEntry` 放入既有宽 `document_models.py`。未单独对该宽文件使用 `--cov-fail-under=80`，改以 changed-boundary tests 覆盖新增 model、仓储 decode/encode、pipeline helper 和 ingestion runtime 写入路径。

## README 决策

- `dayu/fins/README.md`：已更新。原因是 `FilingMaintenanceRepositoryProtocol` 的 SEC 下载拒绝注册表成为当前已实现的稳定 typed storage/pipeline contract，属于该 README 的 package capability / stable boundary 范围。
- `tests/README.md`：未更新。测试目录职责和组织没有变化，只是补充既有 Fins storage/pipeline/ingestion runtime 测试覆盖。

## 残余风险 / Deferred

- 旧 workspace 中已经存在的 `_download_rejections.json` 若缺少 `document_id` 或字段类型不合法，现在会失败关闭；这符合 S3 要求，但没有做迁移兼容。
- `ingestion_runtime.py` 的 generic rejected artifact 路径使用自身 runtime rejection classification version 填充 typed `download_version`；该路径原本没有 SEC pipeline download version。当前选择保持 producer-owned 版本，不把 SEC pipeline 常量泄漏到 generic runtime。
- 未改变 LLM-facing tool schema、prompt 或 read runtime；S3 不涉及 citation 或 XBRL。

## Completion State

ready-for-code-review
