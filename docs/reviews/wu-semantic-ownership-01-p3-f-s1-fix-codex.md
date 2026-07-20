# WU-SEMANTIC-OWNERSHIP-01 P3-F S1 Fix Report

## Completion State

ready-for-rereview

## Accepted Findings Fixed

### P3-F-S1-CR-F01

`_build_citation(...)` 不再对同一 source meta 做重复读取。修复方式：

- `SourceDocumentRepositoryProtocol.get_source_document_provenance(...)`、filesystem core 与 repository 实现增加可选 `meta` 参数。
- `FinsReadRuntime._build_citation(...)` 先通过 runtime meta cache 读取一次 source meta，再把同一份 meta 交给 repository provenance parser。
- read runtime 仍只消费 repository provenance 结果映射 LLM-facing `source_type` / `source_provider`，没有在下游重建 provider 分类。
- 新增 `_CountingSourceRepository` 回归测试，验证同一 citation 重复构建只触发一次 `get_source_meta(...)`。

### P3-F-S1-CR-F02

`ingest_complete` 现在是 provenance 必填字段，incomplete source meta 不会进入 LLM-facing citation projection。修复方式：

- `SourceDocumentProvenance.from_meta(...)` 改为直接读取 `meta["ingest_complete"]`，缺失即 fail closed。
- `_build_citation(...)` 在取得 provenance 后检查 `provenance.ingest_complete`，为 `False` 时抛出 `FileNotFoundError`。
- 新增测试覆盖缺失 `ingest_complete` 的 repository provenance 失败关闭。
- 新增测试覆盖 `ingest_complete=False` source meta 被 `_build_citation(...)` 拒绝。

### P3-F-S1-CR-F03

staging stable-field 匹配不再通过重复或省略字段掩盖冲突。修复方式：

- 从 `_STAGING_STABLE_META_FIELDS` 中移除重复的 `internal_document_id`，保留显式 request 字段比对作为唯一真源。
- `_staging_stable_fields_match(...)` 对 stable meta 字段做双向存在性判断：当既有 staging meta 中存在非空 stable 值，重复 staging 请求省略该值会冲突。
- 空字符串按“未提供 stable value”处理，避免 repository 默认空 fingerprint 破坏双方都未提供 fingerprint 的幂等 staging。
- 新增 repository 测试覆盖匹配 staging 仍幂等、重复 staging 省略既有 `source_fingerprint` 时失败关闭。

## Owner Boundary and Propagation Audit

- Producer: SEC/CN/HK/download 与 upload producer 仍负责写入 `source_provider`、`ingest_method` 与 `ingest_complete`。
- Validator: `SourceDocumentProvenance.from_meta(...)` 与 source repository provenance API 是 `source_provider`、`ingest_method`、`ingest_complete` 的校验真源；缺失或非法字段失败关闭。
- Persistence: filesystem source repository 继续持久化 source meta；staging source meta 由 `stage_source_document(...)` 拥有并负责 stable-field conflict 检测。
- Projection: `FinsReadRuntime._build_citation(...)` 只用 `source_kind` 路由 source meta，citation `source_type` / `source_provider` 来自 repository provenance。
- LLM-facing output: `ingest_complete=False` source meta 会在 citation projection 前被拒绝，不会进入 read/search/section/table/page/financial statement 输出。

## Validation

- `source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_runtime.py tests/fins/test_docling_upload_service.py -q`
  - Passed: `79 passed, 3 warnings`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Passed: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Passed.
- Source scan: `rg -n 'startswith\("fil_"\)|startswith\('\''fil_'\''\)' dayu/fins/tools dayu/fins/pipelines`
  - One remaining match: `dayu/fins/pipelines/sec_rebuild_workflow.py:253`, classified as SEC accession reconstruction during rebuild, not citation/provenance source classification.
- Source scan: `rg -n 'def _build_citation|_build_citation\(' dayu/fins/tools/read_runtime.py`
  - One helper definition and all citation construction call sites remain routed through `_build_citation(...)`.

## README Decision

No additional README update was needed for this fix. The existing S1 README updates already describe the stable source provenance and citation projection contract; this fix tightens implementation and tests inside that same contract.

## Uncovered Risks

- S2 still owns blob acknowledgement enforcement and SEC/upload staging-before-blob sequencing.
- S1 staging conflict tests now cover omitted stable values for `source_fingerprint`; broader blob-write and workflow ordering coverage remains S2 scope.
- Coverage measurement remains unavailable in this local environment from the prior pytest-cov numpy/pandas collection issue; ordinary pytest and pyright validation passed.
