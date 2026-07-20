# Aggregate Deepreview — WU-SEMANTIC-OWNERSHIP-01 P3-F

## Scope

- Mode: aggregate review of all P3-F accepted slices
- Branch: `phaseflow/host-issues-control`
- Accepted commits:
  - S1 source repository provenance and citation projection: `42ea9c21`
  - S2 blob acknowledgement and explicit staging source contract: `3b2779e4`
  - S3 Fins wait adapter deadline/expiry consumption: `edf303a4`
  - S4 company metadata freshness semantics: `22683a8e`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-aggregate-deepreview-mimo.md`
- Included scope: 15 production files + 10 test files (+4310/-69)
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`

## Findings

未发现实质性问题。

## Cross-Slice Semantic Ownership Consistency

### Source provenance → citation projection (S1)

- `FinsSourceProvider` / `SourceDocumentProvenance` 定义在 `document_models.py`，是 source provider 真源。
- `get_source_document_provenance(...)` 在 repository 协议和 filesystem 实现中统一提供。
- `_build_citation(...)` 通过 `_get_source_meta_cached_by_kind` 读取一次 meta，传入 `get_source_document_provenance(meta=meta)` 避免重复 I/O。
- `source_type` / `source_provider` 从 `provenance.source_provider` 通过 `_FILING_SOURCE_TYPES_BY_PROVIDER` / `_CITATION_PROVIDER_LABELS` 映射派生，不从 `document_id` prefix、`ingest_method` 或 `source_kind` 推断。
- `provenance.ingest_complete is False` 时 `_build_citation` 抛出 `FileNotFoundError`。
- 9 个 citation 调用点全部路由通过单一 `_build_citation` helper。
- `rg -n 'ingest_method|FinsIngestMethod' dayu/fins/tools/read_runtime.py` 零匹配。

### Blob acknowledgement → staging → completion (S2)

- `store_file(SourceHandle, ...)` 在任何字节写入前调用 `_get_handle_meta(handle)` 检查 source meta 存在性。
- Upload 路径通过 `_acknowledge_source_before_blob_write(...)` 在首个 blob 前调用 `stage_source_document(...)`。
- SEC stream/legacy 路径通过 `stage_downloaded_filing_source_document(...)` 在 downloader `store_file` callback 前 staging。
- `_upsert_source_document` 在 create 遇到 incomplete staging 时允许 staging-to-complete，但通过 `_staging_completion_stable_fields_match` 禁止改写 staging 已声明的 stable fields。
- S1 的 `_staging_stable_fields_match`（staging 阶段，双向匹配）与 S2 的 `_staging_completion_stable_fields_match`（completion 阶段，只保护已声明值）语义互补，不冲突。

### Wait deadline/expiry ownership (S3)

- `_TRANSIENT_PENDING_MAX_SECONDS` 和 `_transient_pending_expired(...)` 完全移除（rg 零匹配）。
- `_wait_boundary_lost(...)` 读 `deadline_at` first, `expires_at` second，与 `dayu/host/wait_callback.py:_stale_status_or_none` precedence 一致。
- 无边界 → `WaitPollNotReady`；过期或非法 → `WaitPollLost`。
- `_timestamp_or_now(...)` 仍在 `wait_adapter.py:366` 用于 observation handle 时间戳（不同用途），不影响 transient timeout 语义。
- `_lost_outcome()` 使用稳定常量，不暴露 wait id / deadline / expiry / Host governance 措辞。

### Upload company metadata freshness (S4)

- `_existing_company_meta_is_fresh(...)` 仅比较 `resolver_version`，不读 `updated_at`。
- `RESOLVER_VERSION` 是 `upload_company_meta.py` 模块级 `Final[str]` 常量。
- 同版本保留既有值；旧版本用当前字段刷新；旧版本缺 `company_name` fail closed。
- SEC/CN download 路径不经 upload freshness helper。
- `FinsReadRuntime._read_company_info(...)` 只读 repository meta，不推断 freshness。

### Cross-slice dependency integrity

| 依赖 | 方向 | 一致性 |
|---|---|---|
| S2 staging → S1 `stage_source_document` 协议 | S2 消费 S1 | ✅ 协议签名和实现一致 |
| S2 blob guard → S1 source meta existence | S2 消费 S1 | ✅ `_get_handle_meta` 检查 source meta |
| S2 completion → S1 `SourceDocumentProvenance` | S2 消费 S1 | ✅ `_upsert_source_document` 使用 `from_meta` |
| S4 upload → S1 `source_provider` | S4 写入 S1 定义的字段 | ✅ `FinsSourceProvider.USER_UPLOAD` |
| S3 独立于 S1/S2/S4 | 无跨 slice 依赖 | ✅ wait adapter 不涉及 source/blob/company |

## Plan Propagation Audit Criteria

### Source provenance and citation

| 标准 | 状态 | 证据 |
|---|---|---|
| 完成态 source meta 有 valid provider/ingest_method/ingest_complete | ✅ | `SourceDocumentProvenance.from_meta` fail closed |
| Repository provenance 是 citation source classification 唯一来源 | ✅ | `_build_citation` 从 provenance 派生 |
| `_build_citation` 用 `source_kind` 仅作路由 | ✅ | `source_kind is SourceKind.MATERIAL` 仅用于 filing/material 分支 |
| 所有 citation 路径走同一 helper | ✅ | 10 call sites (1 def + 9 calls) |
| 无 `document_id.startswith("fil_")` 分类 | ✅ | `rg` 仅 `sec_rebuild_workflow.py:253`（accession reconstruction） |
| CNINFO/HKEXNEWS `fil_*` 不投影为 SEC EDGAR | ✅ | `_FILING_SOURCE_TYPES_BY_PROVIDER` 按 provider 映射 |
| Upload/material provider 来自 provenance | ✅ | `FinsSourceProvider.USER_UPLOAD` |
| Exact citation output strings asserted | ✅ | 测试覆盖 SEC_EDGAR/CNINFO/HKEXNEWS/UPLOADED/SUPPLEMENTARY |

### Blob acknowledgement

| 标准 | 状态 | 证据 |
|---|---|---|
| `SourceHandle` blob 写入前 source meta 必须存在 | ✅ | `_get_handle_meta` guard |
| Staging `ingest_complete=False` 排除 read/list | ✅ | `_build_citation` 检查 `ingest_complete` |
| Mismatched staging fail before blob write | ✅ | `_staging_stable_fields_match` |
| SEC staging 在 downloader callback 前 | ✅ | `stage_downloaded_filing_source_document` 在 stream/legacy 前 |
| Final meta `files[]` 只引用 acknowledged source 下的 blob | ✅ | staging → blob → completion 时序 |
| Failure 后不产生 ownerless blob | ✅ | `test_execute_upload_final_upsert_failure_keeps_acknowledged_staging` |

### Wait

| 标准 | 状态 | 证据 |
|---|---|---|
| TRANSIENT_UNAVAILABLE 使用 `deadline_at` / `expires_at` | ✅ | `_wait_boundary_lost` |
| 无边界 → `WaitPollNotReady` | ✅ | `boundary_text is None: return False` |
| `created_at` 年龄不影响 lost | ✅ | `_wait_boundary_lost` 不读 `created_at` |
| Terminal resolution 仍由 Host 拥有 | ✅ | adapter 只返回 typed poll result |

### Company metadata

| 标准 | 状态 | 证据 |
|---|---|---|
| Upload freshness 由 resolver version 决定 | ✅ | `_existing_company_meta_is_fresh` |
| `RESOLVER_VERSION` ownership 和变更规则已记录 | ✅ | README + 模块 docstring |
| Download paths 保持 producer-owned refresh | ✅ | diff 未修改下载路径 |
| Read runtime 不成为 resolver 或 freshness owner | ✅ | `_read_company_info` 只读 repository |

## Source Scans

| Scan | 要求 | 结果 |
|---|---|---|
| `_TRANSIENT_PENDING_MAX_SECONDS\|_transient_pending_expired` | 零匹配 | ✅ rg exit 1 |
| `startswith("fil_")` in citation/provenance paths | 零或已分类 | ✅ 仅 `sec_rebuild_workflow.py:253` |
| `_build_citation` definition + calls | 单一 helper | ✅ 1 def + 9 calls |
| `ingest_method\|FinsIngestMethod` in read_runtime | 零匹配 | ✅ |

## README Consistency

`dayu/fins/README.md` 在 S1/S2/S3/S4 各 slice 中逐步更新，最终状态覆盖：

- Source provenance 和 citation projection（S1，line 97）
- Source document acknowledgement 和 blob boundary（S2，line 99）
- Upload company meta freshness（S4，line 101）
- Storage source/blob ownership（S2，line 450）
- Wait adapter deadline/expiry consumption（S3，line 499）

`tests/README.md` 在 S1 中更新（source provenance 测试覆盖），S2-S4 未触发更新（测试层级和运行方式未变）。

## Over-Coupling / Downstream Special Casing

未发现：

- 所有 staging 通过 `stage_source_document` 协议，pipeline 不自行构造第二份 staging truth。
- Citation 只消费 repository provenance，不从 `document_id` prefix / `ingest_method` / `source_kind` 推断。
- Blob guard 在 repository 层，不在 pipeline 或 read runtime 层。
- Wait boundary 在 adapter 层消费 Host 字段，不在 adapter 内部制造 timeout。
- Company freshness 在 upload helper 层，不在 read runtime 或下载路径。
- 测试使用 spy/repository protocol 而非 brittle fixture-only assertions。

## Validation

- `pytest` (12 test files): **256 passed, 3 warnings**
- `pyright dayu/ tests/ utils/`: **0 errors**
- `git diff --check`: passed
- Source scans: all clean

## Residual Risks

- **Multi-process TOCTOU**: blob guard 的 source meta 检查与 blob 写入之间存在理论上的多进程竞争窗口。plan 已接受为 residual risk（当前 Host 单 storage assembly 运行）。
- **无边界 transient unavailable 长期 not ready**: 有意边界选择。Fins adapter 不拥有 terminal timeout；Host poller cadence / cancel / close lifecycle 负责治理。
- **`expires_at` 当前 Host creation path 写 `None`**: 实现已按 contract 支持该字段，供未来 Host-owned expiry truth 消费。
- **Coverage 未测量**: pytest-cov 本地 numpy/pandas import 问题仍存在。256 tests + pyright 零报错，但单文件覆盖率百分比未知。
- **SEC/CN/HK download company meta freshness 不在 P3-F scope**: 下载路径的 company meta 写入仍由各自 producer 处理。

## Verdict

**PASS** — P3-F 四个 slice 在 cross-slice 语义上一致：source provenance/citation、blob acknowledgement/staging、wait deadline/expiry、company metadata freshness 各自落在正确的 owner boundary，无回归、无 over-coupling、无 downstream special casing。plan propagation audit criteria 全部满足。
