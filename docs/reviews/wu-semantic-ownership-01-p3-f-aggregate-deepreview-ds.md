# Aggregate Deepreview — WU-SEMANTIC-OWNERSHIP-01 P3-F

## Scope

- Mode: all slices aggregate (committed)
- Branch: `phaseflow/host-issues-control`
- Accepted commits: S1 `42ea9c21`, S2 `3b2779e4`, S3 `edf303a4`, S4 `22683a8e`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-aggregate-deepreview-ds.md`
- Full P3-F diff: 23 files, +2089/-67
- Validation: `pytest` 256 passed, `pyright` 0 errors

## Verdict

**PASS** — P3-F 四个 slice 之间语义一致、owner boundary 清晰、无跨层穿透、无回归、无 downstream 特例补丁。所有 plan 中的 finding 均已按正确的 owner boundary 关闭。

---

## Findings

未发现实质性问题。

---

## Cross-Slice Semantic Ownership Verification

### 1. Source Provenance → Citation Projection (S1)

**真源链路**:

```
Producer (pipeline)          → Validator (repository)        → Projection (read runtime)    → LLM-facing
────────────────────────────────────────────────────────────────────────────────────────────────────────
SEC: FinsSourceProvider      → SourceDocumentProvenance      → _FILING_SOURCE_TYPES_        → Citation.source_type
  .SEC_EDGAR                   .from_meta(meta, source_kind)   BY_PROVIDER[provenance        = "SEC_EDGAR"
                                                               .source_provider]
CN: candidate.provider       → FinsSourceProvider             → _CITATION_PROVIDER_LABELS    → Citation.source_provider
  → from_storage_value         .from_storage_value              [provenance                  = "CNINFO"
                                                               .source_provider]
Upload: FinsSourceProvider   → (同上)                         → (同上)                       → "USER_UPLOAD"
  .USER_UPLOAD
```

**验证**:
- `source_provider` 在 3 个 pipeline 入口均写入：SEC `"sec_edgar"`（`sec_download_source_upsert.py:283`）、CN 通过 `from_storage_value` 校验（`cn_download_source_upsert.py:316`）、upload `"user_upload"`（`docling_upload_service.py:597`）
- `SourceDocumentProvenance.from_meta` 是唯一的 provider 校验入口（`document_models.py:144-178`）— 在 repository 层
- `_build_citation` 只消费 `provenance.source_provider` 和 `provenance.source_kind`（`read_runtime.py:1709-1714`）
- `document_id.startswith("fil_")` 仅在 `sec_rebuild_workflow.py:253` 残留（accession 重建，非 citation）
- `ingest_complete=False` 被 `_build_citation` 拒绝（`read_runtime.py:1715-1716`）

**无 semantic drift**: provider 事实从 pipeline producer → repository validator → citation projection 单链传递，无分支、无 fallback、无下游特例。

### 2. Blob Acknowledgement → Source Membership (S2)

**真源链路**:

```
Source repository staging    → Blob repository guard         → Source completion
────────────────────────────────────────────────────────────────────────────────
stage_source_document(req,   → store_file(SourceHandle, ...) → _upsert_source_document
  source_kind)                  _get_handle_meta(handle)        _staging_completion_
  _stage_source_document_impl   → FileNotFoundError             stable_fields_match
  → ingest_complete=False       (拒绝 ownerless 写入)           → FileExistsError
                                                              (拒绝改写 stable facts)
```

**验证**:
- Blob guard 在任何字节写入前执行（`_fs_blob_core.py:144-145`）— guard 位于 blob repository
- Upload staging 在 `for asset in pending_assets` 循环前（`docling_upload_service.py:260-268`）
- SEC staging 在 stream/legacy downloader callback 前（`sec_download_filing_workflow.py:414`）— 同一调用点覆盖两种路径
- Completion stable field protection 在 `_upsert_source_document` 内（`_fs_source_document_core.py:781-786`）
- CN 已有 staging 行为未回归（CN workflow 测试通过）

**无双重 staging truth**: 所有 staging 入口均通过 `SourceDocumentRepositoryProtocol.stage_source_document`；upload 和 SEC 分别有自己的 thin helper（`_acknowledge_source_before_blob_write`、`stage_downloaded_filing_source_document`），但均委托到同一个 repository contract。

### 3. Wait Timeout Ownership (S3)

**真源链路**:

```
Host wait record              → Fins adapter                  → Host poller
───────────────────────────────────────────────────────────────────────────
WaitRecordRow.deadline_at     → _wait_boundary_lost            → WaitPollNotReady
  (await_spec.deadline)          deadline_at                   (future / no boundary)
WaitRecordRow.expires_at        ?? expires_at                  → WaitPollLost
  (currently None)              → None → False (not ready)     (past / invalid boundary)
```

**验证**:
- Fins adapter 不再拥有 terminal timeout：`_TRANSIENT_PENDING_MAX_SECONDS` / `_transient_pending_expired` 已删除（`rg` 零匹配）
- `_wait_boundary_lost` 按 Host callback precedence 消费：`deadline_at` first, `expires_at` second（`wait_adapter.py:618-622`）
- `created_at` 不再参与 lost 判定（`wait_adapter.py:609-629` 完全不读 `created_at`）
- 无 LLM-facing 泄漏：`_lost_outcome()` 仅返回 `"fins_observation_lost"` 和业务可读消息

**无 adapter-owned timeout**: terminal timeout 边界完全来自 Host wait record；adapter 仅做消费和投影。

### 4. Company Metadata Freshness (S4)

**真源链路**:

```
Upload entry                  → Freshness judgment            → Persistence
────────────────────────────────────────────────────────────────────────────────
upsert_company_meta_          → _existing_company_meta_is_fresh → repository
  for_upload(...)                (resolver_version comparison)   .upsert_company_meta
  ticker, company_name,          Fresh → warn + return          (CompanyMeta(
  ticker_aliases                 Stale → normalize + upsert      resolver_version=
                                                                  RESOLVER_VERSION))
```

**验证**:
- `_existing_company_meta_is_fresh` 仅比较 `resolver_version`（`upload_company_meta.py:192`）
- `updated_at` 仅作为审计写入时间，不用于 freshness（`upload_company_meta.py:81`）
- 下载路径不经过 upload freshness：CN download 用 `_RESOLVER_VERSION = "cn_download_v1"` 独立管理（`cn_download_company_meta.py:15`），SEC download 用自己的 company meta 写入
- Read runtime 不推断/刷新：`_read_company_info` 仅调用 `get_company_meta`（`read_runtime.py:1873`）

**无 freshness 泄露**: upload freshness 完全在 `upload_company_meta.py` 模块内，不向外扩散到 download、read runtime 或 repository 接口。

---

## Over-Coupling / Architecture Check

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 下层依赖上层 | 无 | `dayu.fins.storage` 不 import `dayu.fins.pipelines`；`wait_adapter` → `dayu.host.durable` 是正确方向 |
| 跨层穿透 | 无 | read runtime 不直接读写 blob；pipeline 不直接操作 source meta 文件 |
| 共享可变状态 | 无 | `FinsSourceProvider` / `SourceDocumentProvenance` 均为 frozen dataclass 或 str Enum |
| 特例补丁隐藏错误 | 无 | 无 `hasattr`/`getattr` 绕过类型；无 `document_id.startswith("fil_")` fallback；无 `ingest_method` 孤岛判定 |
| Protocol 依赖具体实现 | 无 | `SourceDocumentRepositoryProtocol` / `DocumentBlobRepositoryProtocol` 均为 Protocol；filesystem 实现仅通过 factory 装配 |
| 双向依赖 | 无 | 依赖方向：pipeline → repository → domain (uniform) |
| 多真源状态 | 无 | `source_provider` 只有 source meta 一个 durable 真源；`ingest_complete` 同理 |
| CN/SEC 各有独立 staging 语义 | 无 | 两者均通过 `stage_source_document` protocol；各自的 thin wrapper 不发明新语义 |

---

## Propagation Audit (完整 4-slice 路径)

### Source Provenance

```
SEC/CN/Upload pipeline
  → write source_provider in source meta (S1)
  → repository: SourceDocumentProvenance.from_meta validates (S1)
  → read runtime: _build_citation → Citation(source_type, source_provider) (S1)
  → LLM-facing output: Citation.to_dict() (S1)
```

### Blob → Source Membership

```
Pipeline constructs source identity
  → source_repository.stage_source_document(req) → ingest_complete=False (S2)
  → blob_repository.store_file(SourceHandle) → _get_handle_meta guard (S2)
  → pipeline final upsert → _staging_completion_stable_fields_match (S2)
  → source meta ingest_complete=True + files + membership
  → read runtime: _collect_source_documents excludes ingest_complete=False (S1)
  → _build_citation rejects ingest_complete=False (S1)
```

### Wait Timeout

```
Host wait creation → WaitRecordRow.deadline_at / expires_at
  → Fins adapter poll_wait → TRANSIENT_UNAVAILABLE (S3)
  → _wait_boundary_lost(wait_record) → past/invalid → WaitPollLost (S3)
  → future/no-boundary → WaitPollNotReady (S3)
  → Host poller resolve/cancel lifecycle (Host-owned)
```

### Company Metadata Freshness

```
Upload entry → upsert_company_meta_for_upload(repository, ticker, company_name, ...) (S4)
  → existing_meta + _existing_company_meta_is_fresh → same version → preserve (S4)
  → different version → normalize + _require_company_meta_field → upsert with RESOLVER_VERSION (S4)
  → read runtime: _read_company_info → get_company_meta only — no refresh (S4)
  → download paths: own cn_download_v1 / SEC producer writes — independent
```

---

## Source Scan Results

| 扫描 | 要求 | 结果 |
| --- | --- | --- |
| `_TRANSIENT_PENDING_MAX_SECONDS\|_transient_pending_expired` | 零匹配 | ✅ 零匹配（exit code 1） |
| `startswith("fil_")` in tools/pipelines | 仅 SEC accession 重建 | ✅ 仅 `sec_rebuild_workflow.py:253` |
| `stage_source_document\|get_source_document_provenance\|_existing_company_meta_is_fresh\|_wait_boundary_lost` in dayu/fins + tests/fins | owner-boundary helpers | ✅ 仅正确位置 |
| `source_provider` in pipelines | SEC/CN/upload 均写入 | ✅ 3 pipeline sites |
| `_build_citation` in read_runtime.py | 1 定义 + 8 调用点 | ✅ |

---

## Regression Check

| 检查项 | 状态 |
| --- | --- |
| S1 failing 测试 (79 → 不变) | ✅ 79 passed |
| S2 failing 测试 (66 → 不变) | ✅ 66 passed |
| S3 failing 测试 (132 → 不变) | ✅ 132 passed |
| S4 failing 测试 (24 → 不变) | ✅ 24 passed |
| Full suite (256 passed) | ✅ |
| pyright (0 errors) | ✅ |
| CN workflow 未回归 | ✅ |
| SEC stream/legacy download 未回归 | ✅ |
| HKEXNEWS discovery 未回归 | ✅ |

---

## Test Coverage Assessment

不量化覆盖率（pytest-cov 本地不可用），但按 plan 要求的行为覆盖矩阵逐项确认：

| Plan 要求 | 测试 | Slice |
| --- | --- | --- |
| 4 种 provider provenance | `test_source_repository_projects_source_document_provenance` | S1 |
| Missing/invalid provider fail-closed | `test_source_repository_fails_closed_for_missing_or_invalid_completed_provider` | S1 |
| Missing `ingest_complete` fail-closed | 同上（S1 fix 后包含） | S1 |
| Citation from provenance (5 providers) | `test_read_runtime_citation_projects_provider_owned_source_types` | S1 |
| `Citation.to_dict()` omits None provider | `test_citation_to_dict_omits_none_source_provider` | S1 |
| Incomplete source → citation rejected | `test_read_runtime_citation_rejects_incomplete_source_meta` | S1 |
| Single cached meta read | `test_read_runtime_citation_reuses_single_cached_source_meta_read` | S1 fix |
| Staging idempotent + conflict | `test_stage_source_document_requires_existing_stable_fields_on_retry` | S1 fix |
| Staging → blob → completion lifecycle | `test_stage_source_document_lifecycle_and_blob_acknowledgement` | S2 |
| store_file rejects missing source | 同上 | S2 |
| Upload staging before blob | `test_execute_upload_stages_source_before_first_blob_write` | S2 |
| Upload failure → no ownerless blob | `test_execute_upload_final_upsert_failure_keeps_acknowledged_staging` | S2 |
| SEC stream staging before blob | `test_download_stream_stages_source_before_blob_write` | S2 |
| SEC legacy staging before blob | `test_download_legacy_path_stages_source_before_blob_write` | S2 |
| SEC fail → retry completes | `test_failed_sec_download_leaves_incomplete_staging_and_retry_completes` | S2 |
| Transient unavailable boundary matrix | `test_fins_wait_poll_adapter_transient_unavailable_uses_host_wait_boundaries` | S3 |
| Same-version preserve | `test_upload_filing_stream_preserves_same_version_company_meta` | S4 |
| Stale-version refresh | `test_upload_filing_stream_refreshes_stale_company_meta` (SEC + CN) | S4 |
| Stale + no company_name → fail-closed | `test_upload_filing_stream_stale_company_meta_requires_company_name` | S4 |

---

## README / Control-Doc Consistency

- `dayu/fins/README.md` 累计更新共计 4 段（S1 source provenance、S2 blob acknowledgement、S3 wait boundary、S4 company freshness），每段均在 `dayu/fins/` Agent update constraints 范围内
- `tests/README.md` 在 S1 更新，后续 S2-S4 未新增测试组织/维护规则，符合触发条件
- `docs/host/issues-implementation-control.md` 被更新为 P3-F `ready-for-draft-pr`

## Open Questions

无。

## Residual Risk

1. **Multi-process TOCTOU**: source-meta check 与 blob write 之间的窗口，plan 已接受为 S2 residual。当前 Host 单 storage assembly 运行，实际风险极低。
2. **No-boundary transient unavailable**: Host await spec 不提供 deadline 时，transient unavailable 无限期保持 not-ready。由 Host poller cadence / cancel / close lifecycle 控制，属于有意的 owner boundary 选择。
3. **Coverage 百分比未测量**: pytest-cov 在本地因 numpy/pandas import 冲突无法运行。所有 256 个 behavioral 测试通过 + pyright 零报错，行为覆盖矩阵已按 plan 逐项确认。
4. **Stale staging cleanup**: 下载失败后的 incomplete staging meta 无自动清理。plan 将物理清理标记为非必需。
5. **`expires_at` 当前 Host creation path 写 None**: S3 实现已 support 该字段供未来 Host-owned expiry truth 消费，但当前生产路径不会触发。
