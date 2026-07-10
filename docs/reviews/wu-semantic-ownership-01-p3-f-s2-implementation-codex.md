# WU-SEMANTIC-OWNERSHIP-01 P3-F S2 Implementation Report

## 一阶动机检查

S2 问题真实存在且严重性成立：在 S1 之前 source provenance 已经收口到 source repository，但 blob 写入边界仍可能只凭 `SourceHandle` 路径写文件。如果 source meta 尚不存在，文件系统会产生 durable blob，却没有 source document acknowledgement、provenance、manifest 或 read-runtime 可见边界。这会制造“文件存在但 source owner 不存在”的状态，后续 citation / LLM-facing 输出即使 fail closed，也无法解释该 blob 的业务归属。

正确修复位置不是 read runtime 或测试夹具，而是 source/blob owner boundary：

- Source repository 拥有 source document acknowledgement：完成态 source meta，或 `stage_source_document(...)` 写入的 `ingest_complete=false` staging meta。
- Blob repository 拥有最终 blob 写入边界：`store_file(SourceHandle, ...)` 写入前必须确认 source meta 已存在。
- Pipeline 只能请求 source repository staging，不能自行构造第二份 staging truth。

## 本次修改文件

- `dayu/fins/storage/_fs_blob_core.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/pipelines/docling_upload_service.py`
- `dayu/fins/pipelines/sec_download_source_upsert.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/README.md`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_docling_upload_service.py`
- `tests/fins/test_sec_pipeline_download_stream.py`
- `docs/reviews/wu-semantic-ownership-01-p3-f-s2-implementation-codex.md`

工作区已有 `docs/host/issues-implementation-control.md` 修改和用户列出的 untracked 文件，本次未触碰、未纳入 S2 实现。

## 行为变更

- `FsDocumentBlobRepository.store_file(SourceHandle, ...)` 在任何文件写入前读取 source meta；source meta 不存在时抛 `FileNotFoundError`，且不会创建 blob。
- `stage_source_document(...)` 仍创建或复用 `ingest_complete=false` source meta，重复 staging 必须严格匹配既有 stable fields。
- source final commit 遇到既有 incomplete staging meta 时允许完成同一 source id；但 completion 不能改写 staging 已声明的 stable fields。CN/HK final commit 可补充 staging 阶段不可知的 `source_fingerprint`，但不能改变 remote fingerprint / provider / company id 等既有事实。
- upload create 路径在首个 blob 写入前通过 source repository staging；final upsert 失败时允许留下 incomplete source meta 和其名下 blob，不产生 ownerless blob。
- SEC stream 与 legacy non-stream 下载路径在 downloader `store_file` callback 之前调用 source repository staging；失败下载不产生完成态 source meta，重试可复用匹配 incomplete staging 并完成。
- README 更新：记录 storage acknowledgement contract；`tests/README.md` 未更新，因为测试层级、运行方式和维护规则未变化。

## Owner Boundary 与传播审计

1. Source facts 产生：download/upload pipeline 生成 ticker、document_id、provider、fingerprint、company id、ingest method 等 source facts。
2. Acknowledgement 持久化：pipeline 在首次 blob 写入前调用 `stage_source_document(...)`；source repository 写入 `ingest_complete=false` staging meta。
3. Blob 写入边界：blob repository 在 `store_file(SourceHandle, ...)` 内读取 source meta；不存在则拒绝写入。
4. Completion：source repository create/update 将同一 source id 更新为 `ingest_complete=true`，写入 final membership/files；completion 只能延续 staging 已声明 stable facts。
5. Read projection：read runtime 继续过滤 `ingest_complete=false` source document，citation 仍只从 source repository provenance 投影 LLM-facing `source_type` / `source_provider`。

结论：source acknowledgement、blob ownership、final source membership 与 LLM-facing citation 都从 source repository 真源派生；没有新增下游分类或展示层特例。

## 测试与验证

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_docling_upload_service.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_cn_download_workflow.py -q`
  - 结果：`66 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出

补充测试覆盖点：

- 首次 staging 创建 incomplete meta 并返回 `SourceHandle`。
- 重复匹配 staging 幂等。
- mismatched staging / mismatched completion stable fields fail closed。
- completed source meta 存在时 staging 拒绝。
- staging-to-complete commit 更新同一 source id。
- `store_file(SourceHandle)` 缺 source meta 时拒绝且不创建文件。
- staging 后 `store_file(SourceHandle)` 成功。
- read runtime list/citation 排除 incomplete source。
- upload 在首个 blob 写入前 staging；final upsert 失败后 blob 仍在 acknowledged staging source 下。
- SEC stream 和 legacy non-stream 路径在 downloader callback 前 staging。
- failed SEC download 不产生 completed source meta；retry 可复用匹配 incomplete staging 并完成。

## 残余风险 / 延后项

- SEC full pipeline 收尾可能通过 stale cleanup 删除失败 filing 的 incomplete staging meta；S2 contract 允许 failure 后“may leave” incomplete meta，核心约束是不得留下 ownerless blob。本次测试覆盖了无 ownerless blob，以及存在 matching staging 时 retry completion。
- 本次未做 coverage 命令测量；验证集中在 S2 owner boundary 的仓储、upload、SEC stream/non-stream、CN 对齐路径。
- 未实现 wait adapter deadline/expiry、company metadata freshness、P3-G/P3-H/P3-I/P3-J/P3-K，均为非 S2 scope。

## 完成状态

ready-for-code-review
