# WU-SEMANTIC-OWNERSHIP-01 P3-G S3 Controller Validation

## 结论

P3-G S3 的动机成立，当前实现进入 code review gate。

本 slice 修复的是 SEC 下载拒绝注册表的语义所有权漂移：拒绝事实以前以 `dict[str, dict[str, str]]` 在仓储、SEC 下载 pipeline、SC13 过滤和诊断之间传递，多个消费者各自解释字段；文件系统仓储还会在 registry 损坏时静默返回空映射或把字段 `str(...)` 化。该行为会掩盖坏 durable state，并可能导致重复下载、错误跳过或诊断误判。

## Controller 审阅范围

- `dayu/fins/domain/document_models.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/_fs_maintenance_core.py`
- `dayu/fins/storage/fs_filing_maintenance_repository.py`
- `dayu/fins/pipelines/sec_download_state.py`
- `dayu/fins/pipelines/sec_pipeline.py`
- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_sc13_filtering.py`
- `dayu/fins/pipelines/sec_download_diagnostics.py`
- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_sec_pipeline_download.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `dayu/fins/README.md`

## Owner Boundary 判定

- 事实产生：SEC 下载拒绝事实由 `sec_download_state._record_rejection(...)` 构造 `DownloadRejectionEntry`；SC13 direction reject 经同一 helper 写入；generic ingestion runtime rejected artifact 路径也构造同一 typed entry。
- 事实校验：`DownloadRejectionEntry.__post_init__` 和 `DownloadRejectionEntry.from_dict(...)` 校验必填字段、非空值、canonical SEC form，以及 registry key 与 `document_id` 一致性。
- 事实持久化：`FilingMaintenanceRepositoryProtocol` 持有 registry 仓储边界；FS 实现读取时解析 typed entry，坏 JSON/坏条目失败关闭；保存时校验 key 与 entry `document_id` 一致并只通过 `entry.to_dict()` 落盘。
- 事实投影/消费：SEC 下载 skip 判断只读 typed `download_version`；SC13 workflow 只传递 typed registry；下载诊断只读 typed `form_type` 统计被过滤 6-K；用户可见 warning/summary 仍由 pipeline result 产生，但其 registry 依据不再来自散字典字段猜测。

## Controller Source Scan

命令：

```bash
rg -n "dict\[str, dict\[str, str\]\]" dayu/fins/pipelines/sec_sc13_filtering.py dayu/fins/pipelines/sec_download_state.py dayu/fins/pipelines/sec_download_diagnostics.py dayu/fins/pipelines/sec_pipeline.py dayu/fins/storage tests/fins
```

结果仅命中：

- `dayu/fins/storage/_fs_maintenance_core.py:111`

分类：这是 `_save_download_rejection_registry_impl(...)` 内部写 JSON 前的局部 serialization payload，不是 public contract、pipeline contract 或兼容 shim。保存入口参数仍是 `DownloadRejectionRegistry`，并在写入前校验 key/document id 一致。

## 验证

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_sec_pipeline_download_stream.py -q
```

结果：`87 passed, 3 warnings`

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py::test_start_download_persists_rejected_filing_artifact -q
```

结果：`1 passed, 3 warnings`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

```bash
git diff --check
```

结果：通过。

## README 判定

- `dayu/fins/README.md` 已更新，因为本 slice 改变了 Fins package 的稳定仓储/pipeline contract。
- `tests/README.md` 未更新，因为测试组织、运行方式和测试边界说明未变化。

## 待 Code Review 挑战点

- `DownloadRejectionEntry` 是否足以表达当前所有 SEC reject producer 的业务事实，尤其是 generic ingestion runtime 的 rejected artifact 路径。
- FS repository 对坏 registry 失败关闭是否落在正确 owner boundary，而不是把错误推给 pipeline 消费者。
- 是否仍存在 public contract、protocol、workflow callback 或测试夹具使用 `dict[str, dict[str, str]]` 重建 registry 语义。
- SC13 过滤、SEC pipeline skip、下载诊断三类消费者是否都从同一个 typed registry 派生语义。
- 本 slice 是否越界改动 S4 XBRL、CN/HK 或 LLM-facing schema/prompt。
