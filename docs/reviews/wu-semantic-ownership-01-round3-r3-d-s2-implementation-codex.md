# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S2 Implementation

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S2 — Virtual Section Consistency, Source Freshness, And Read Failure Contracts`
- Gate: `implementation`
- Implementer: `AgentCodex`
- Status: `complete`
- Scope: 仅 Accepted plan S2 allowed production/test files；未实施 S3、R3-E、tool-security，未 code review、commit、push。
- Design truth: `docs/host/design.md`、`docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`
- Accepted plan: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`

## First-Principles And Owner Decision

S2 动机成立，严重性是 production correctness，而不是缓存或文本解析风格清理：旧 processor/meta、扩展后的旧 section/table 派生状态，以及被吞掉的 decode/index exception，都会让 read tool 把不同 source 时刻或失败状态伪装成成功业务事实。

本实现固定以下唯一 owner：

- storage owner：产生、校验并对外承诺 `SourceDocumentRevision`；revision 只从 canonical source meta 派生。
- read runtime owner：决定 processor/meta cache 是否可复用；revision mismatch 同步失效，build/read race 零自动重试并 typed fail。
- `_VirtualSectionProcessorMixin`：从最终 section boundary/order 唯一重建 section index 与 table 双向映射。
- `processors/source_text.py`：独占 Fins processor/preview bytes/path 到 UTF-8 文本的严格转换。
- `FinsReadRuntime.search_document`：拥有 search readiness；index/list/enrichment/BM25F/profile exception 统一转 typed failure，取消优先。

没有在 citation、list/read consumer、tool fixture 或 display 层增加 fallback、loose parsing、TTL、mtime、ingestion callback 或 processed-meta freshness。

## Changed Files

### Production

- `dayu/fins/domain/document_models.py`
- `dayu/fins/storage/repository_protocols.py`
- `dayu/fins/storage/fs_source_document_repository.py`
- `dayu/fins/storage/_fs_source_document_core.py`
- `dayu/fins/processors/source_text.py`（新增）
- `dayu/fins/processors/sec_form_section_common.py`
- `dayu/fins/processors/ten_k_processor.py`
- `dayu/fins/processors/bs_ten_k_processor.py`
- `dayu/fins/processors/ten_q_processor.py`
- `dayu/fins/processors/bs_ten_q_processor.py`
- `dayu/fins/processors/sec_processor.py`
- `dayu/fins/processors/sec_report_form_common.py`
- `dayu/fins/pipelines/sec_6k_rules.py`
- `dayu/fins/tools/cache.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/read_runtime_helpers.py`
- `dayu/fins/tools/error_contract.py`
- `dayu/fins/tools/fins_tools.py`

### Tests

- `tests/fins/test_processor_read_consistency.py`（新增）
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_sec_pipeline_download.py`

### Artifact

- `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-implementation-codex.md`

未修改任何 S3、Host、Engine、R3-E 或 tool-security 文件。

## Contract Changes

### Source Revision

- 新增 frozen `SourceDocumentRevision(digest)`；digest 强制为 `sha256:<64 hex>`。
- `SourceDocumentRepositoryProtocol`、`FsSourceDocumentRepository` 与 storage core 新增 `get_source_revision(ticker, document_id, source_kind)`。
- revision 使用稳定 key/file 顺序的 canonical JSON + SHA-256，消费 `document_version`、`source_fingerprint`、`form_type`、`primary_document`、`ingest_complete`、`is_deleted` 和 `files` 的 `name/uri/etag/last_modified/size/sha256/content_type`。
- Accepted plan 列出的 file 字段之外纳入 `content_type`：直接代码证据表明 storage 用它产生 `Source.media_type`，而 registry 用 `media_type` 选择 processor；不纳入会遗漏真实 processor-selection input。
- 必需字段缺失、null 或类型非法 fail closed；fileless source meta 仍可产生稳定空-files revision，保持现有 list/citation 合法契约。

### Processor / Meta Cache Freshness

- processor/meta cache value 均绑定 `source_kind + SourceDocumentRevision`。
- `_get_or_create_processor()`、独立 `_get_source_meta_cached_by_kind()` 与 no-kind `_get_document_meta_cached()` delegate 都在各自路径读取并比较 storage revision。
- mismatch 在 document creation lock 内同步清理关联 processor/meta cache；no-kind positive fast path 已删除。
- processor build 使用 `R1 -> build once -> R2`；meta rebuild 使用 `M1 -> read/parse once -> M2`。第二次 revision 不同或不可读时，均不 cache、不 return、零自动 retry，立即抛 `source_changed_during_read`。
- cross-document locator diagnosis 的 cache `peek` 也先比较 storage revision；诊断路径不再消费 stale processor。
- 仅 processed output 变化不会改变 source revision；未增加 ingestion callback、TTL、mtime/stat 或 processed-meta freshness。

### Virtual Section State

- `_VirtualSectionProcessorMixin._refresh_virtual_section_state()` 成为唯一 refresh owner：校验 duplicate/parent/child ref，重建 `_virtual_section_by_ref`，清理并重建 table 双向映射，然后校验 base table、section table_refs 与 reverse map 完全一致。
- `_initialize_virtual_sections()`、edgartools/BS 10-K postprocess、edgartools/BS 10-Q postprocess 全部迁移到该 helper；form processor 不再手写 index/table rebuild。
- 两条 10-Q path 在 expansion 前记录 section object/ref multiset，expansion 后 refresh 前严格比较；创建、删除、替换 section/ref 立即 fail closed。boundary/order/content/preview 仍可原地更新。
- duplicate section ref、悬挂 parent/child/table ref、重复或无法分配 table ref 均不再 last-write-wins 或 downstream fallback。

### Strict Decode And Typed Read Failure

- 新增 `FinsSourceDecodeError`、`decode_source_bytes()`、`read_source_path_text()`、`materialize_source_text()` 与 registry 前文本 source UTF-8 validation。
- ASCII、UTF-8 与 UTF-8 BOM 正常；非法 byte sequence 保留 `UnicodeDecodeError` cause 并输出不含 path/raw bytes 的稳定错误。
- `SecProcessor` source load、report fallback 与 6-K preview 复用同一 strict decoder；materialize/read 失败不返回空文本。
- `FinsReadRuntime._create_processor()` 把 decode failure 映射为 `ErrorCode.SOURCE_DECODE_FAILED`。
- `ErrorCode` 新增 `SOURCE_DECODE_FAILED`、`SEARCH_INDEX_FAILED`、`SOURCE_CHANGED_DURING_READ`；`FinsReadBusinessError.code` 改为 enum，tool boundary 只投影 `.value`。
- `search_document` 删除 empty BM25F/semantic fallback。section list、enrichment、BM25F、profile 任一异常保留 cause 并转 `SEARCH_INDEX_FAILED`；若异常同时观察到取消，仍优先 `FinsReadCancelledError` / cancelled outcome。

## Tests And Validation

所有命令均在 `source .venv/bin/activate` 后执行。

1. `pytest tests/fins/test_processor_read_consistency.py tests/fins/test_read_runtime_semantic_ownership_guards.py -q`
   - 结果：`37 passed, 3 warnings`
   - 覆盖：10-Q/10-K 双 engine refresh、object/ref invariant、duplicate/dangling ref；revision equal/mismatch/delete/build race/meta race/concurrent rebuild/diagnostic peek；strict decode/read/materialize/report/preview；search list/enrichment/BM25F/profile failure 与 cancellation priority。
2. `pytest tests/fins/test_fins_storage_provider.py -q -k "search_document or processor_cache or source_meta_cache or source_revision"`
   - 结果：`19 passed, 46 deselected, 3 warnings`
   - 覆盖：revision 每个 canonical 字段、JSON/file order stability、invalid meta fail closed、source meta cache、search typed failed tool outcome。
3. `pytest tests/fins/test_sec_pipeline_download.py::test_sec_6k_preview_rejects_invalid_utf8 -q`
   - 结果：`1 passed, 3 warnings`
   - node id 存在并被精确收集执行。
4. `coverage run -m pytest tests/fins/test_processor_read_consistency.py -q`
   - 结果：`23 passed, 3 warnings`
5. `coverage report --include="dayu/fins/processors/source_text.py" --fail-under=80`
   - 结果：`94%`（36 statements，2 missed），通过 80% gate。
6. `python -m pyright dayu/ tests/ utils/`
   - 结果：`0 errors, 0 warnings, 0 informations`。
7. `git diff --check`
   - 结果：通过，无输出。

三类 pytest warning 均为 edgartools 既有 deprecation warning，不是 S2 failure。

## README Decision

- 已读取 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】`。
- 本 slice 不修改 README。Accepted plan 明确由 S3 aggregate docs step 一次更新当前 financial/read cache/source revision/failure contract，避免 S2 单独写入中间状态；本次严格不实施 S3。
- 不更新根 `README.md`、`dayu/README.md`、`tests/README.md`：无安装/CLI/用户工作流、分层边界或测试层级变化。

## Propagation Scans And Classification

### `rg -n 'errors="ignore"' dayu/fins`

- S2 owner paths（`processors/sec_processor.py`、`processors/sec_report_form_common.py`、`pipelines/sec_6k_rules.py`）为零匹配。
- 全局仍有 3 个既有匹配，均在未修改且不属于 S2 allowed files 的 `dayu/fins/downloaders/sec_downloader.py`：
  - line 568：下载阶段同 filing 相对 HTML link best-effort parser；
  - line 2342：SC13 index-headers party-role best-effort parser；
  - line 2392：index-headers `<DOCUMENT>` auxiliary metadata parser。
- 分类：`legitimate downloader-side third-party/auxiliary adapter`。它们不产生 processor/read source text、section/index success 或 6-K preview read result，不属于本 slice 的 source decoder owner；未用 ignore comment/allowlist 隐藏，也未越过 S2 allowed files 修改 downloader。

### `rg -n -U 'except Exception:\n\s+pass' dayu/fins/tools/read_runtime.py`

- 零匹配。原 search readiness swallow block 已删除。

### `rg -n '_virtual_section_by_ref\s*=|_assign_tables_to_virtual_sections\(' dayu/fins/processors`

- 所有 assignment/call/definition 只位于 `sec_form_section_common.py` mixin owner；10-K/10-Q form processors 只调用 `_refresh_virtual_section_state()`。

### Cache / Revision Scan

- `_processor_cache.get/put/peek` 的所有语义消费路径均在同一 call path 调用 `get_source_revision` 并比较 revision；eviction helper 内的 peek 只用于确定清理范围，不复用业务值。
- `_meta_cache.get/put/peek` 仅存在于 revision-aware meta/processor owner path；no-kind positive fast path已删除。
- `get_source_revision` 只由 storage protocol/facade/core 定义，并由 read runtime freshness owner消费。

### Typed Failure Scan

- `SourceDocumentRevision` 只存在于 domain typed projection、storage owner、cache entry与 tests。
- `source_changed_during_read`、`search_index_failed`、`source_decode_failed` 只由 `ErrorCode` 与对应 owner path产生；tool boundary只序列化 enum value。

### `rg -n 'mtime|stat\(' dayu/fins/tools/read_runtime.py`

- 零匹配。未引入 mtime/stat freshness。

### Scope / Hygiene

- `git status --short` 只包含 Accepted plan S2 allowed production/test files与本 artifact。
- `git diff --check` 通过。
- 未出现 Host/Engine、S3、R3-E 或 tool-security 文件。

## Residual Risks / Uncovered Areas

- strict UTF-8 会把历史非 UTF-8 source 显式暴露为 `source_decode_failed`。分类：`assigned to later work unit`；若业务需要其它 charset，必须先建立独立 encoding-policy owner，不得恢复 ignore/replace。
- 每次 cache reuse 增加一次 storage revision meta read。分类：`assigned to later work unit`；correctness 优先，后续只能基于 profiling 优化 storage projection成本，不能跳过 revision comparison。
- source revision 依赖 storage 写路径同步维护 file identity/content meta；本 slice未用 mtime 或 out-of-band filesystem probe补偿绕过 repository 的外部文件篡改。分类：`fixed in current slice` 覆盖全部受支持 repository mutation；绕过 repository 的文件篡改违反既有 storage ownership contract，不是合法读路径。
- downloader 的 3 个 global `errors="ignore"` 命中已按 auxiliary download adapter 分类，不属于 S2 read success contract；本 slice未扩 scope修改。
- 未运行完整 `pytest tests/fins -q`，因为 Accepted plan S2 validation profile未要求；已运行全部指定 focused matrix、全仓 pyright与 owner coverage。分类：`covered by later approved slice`，S3 aggregate validation 明确负责完整 `tests/fins`。

## Blocking Questions

无。

## Completion Status

- S2 implementation：`complete`
- Focused tests：`pass`
- Pyright：`pass`
- Coverage：`pass (94%)`
- Propagation scans：`classified; no S2 owner-path stale match`
- README：`no change by accepted S2/S3 docs boundary`
- Review/commit/push：未执行
- Next gate：由 controller 决定；本 implementation agent 不进入 code review 或 S3。
