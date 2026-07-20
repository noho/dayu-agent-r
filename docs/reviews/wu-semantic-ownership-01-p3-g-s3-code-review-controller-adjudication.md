# WU-SEMANTIC-OWNERSHIP-01 P3-G S3 Code Review Controller Adjudication

## 结论

P3-G S3 accepted，无 fix gate。

两路 code review 均返回 PASS，未发现 material finding：

- `docs/reviews/wu-semantic-ownership-01-p3-g-s3-code-review-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-p3-g-s3-code-review-ds.md`

## Controller 裁决

本轮 accepted findings：0。

原因：

- `DownloadRejectionEntry` / `DownloadRejectionRegistry` 已成为 SEC 下载拒绝注册表唯一 typed contract。
- `FilingMaintenanceRepositoryProtocol`、文件系统仓储、SEC download state、SEC pipeline、download workflow、single filing workflow、SC13 filtering、download diagnostics 和 ingestion runtime rejected artifact 路径均消费 typed registry。
- 旧 `dict[str, dict[str, str]]` 只剩 `_fs_maintenance_core.py` 保存 JSON 前的局部 serialization payload，不是 public contract、compatibility shim 或第二真源。
- 文件系统仓储读取坏 registry 失败关闭，不再静默吞掉 durable state 错误。
- 两路 review 均确认 S3 未越界改动 S1/S2/S4 或 LLM-facing schema/prompt。

## 已验证

Controller validation artifact：

- `docs/reviews/wu-semantic-ownership-01-p3-g-s3-controller-validation.md`

验证结果：

- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py -q` -> `87 passed, 3 warnings`
- `pytest tests/fins/test_fins_ingestion_runtime.py::test_start_download_persists_rejected_filing_artifact -q` -> `1 passed, 3 warnings`
- `python -m pyright dayu/ tests/ utils/` -> `0 errors`
- `git diff --check` -> pass

## Propagation Audit

- 产生：SEC 下载拒绝事实由 `sec_download_state._record_rejection(...)` 产生；SC13 direction reject 通过同一 helper 写入；generic ingestion runtime rejected artifact 路径直接构造同一 typed entry。
- 校验：`DownloadRejectionEntry.__post_init__` 和 `from_dict(...)` 校验必填字段、canonical SEC form 和 registry key/document id 一致。
- 持久化：`FilingMaintenanceRepositoryProtocol` 是 registry 仓储边界；FS 实现 load 解析 typed entry 并 fail closed，save 通过 `entry.to_dict()` 落盘。
- 消费：SEC skip 判断读取 `entry.download_version`；SC13 workflow 只传递 typed registry；下载诊断读取 `entry.form_type` 统计 6-K filtered。
- 用户/LLM 可见：本 slice 不改 prompt/tool schema；间接可见 warning/summary 的 registry 依据从 typed registry 派生。

## 下一步

提交 accepted P3-G S3，然后进入 P3-G S4：XBRL processor result contract and read runtime consumption。
