# Code Re-review — WU-SEMANTIC-OWNERSHIP-01 P3-F S1 Fix

## Scope

- Mode: current changes (fix diff on top of S1)
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-rereview-mimo.md`
- Reviewed artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-ds.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-controller-adjudication.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s1-fix-codex.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-f-s1-fix-controller-validation.md`
- Included scope: 17 files (+867/-25) — S1 基础改动 + fix
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`

## Accepted Finding Status

### P3-F-S1-CR-F01 — 关闭 ✅

**Controller 要求**: 消除 `_build_citation` 对同一 meta.json 的重复读取；保留 repository-owned provenance parsing；不重建 provider 分类。

**Fix 验证**:

1. `_build_citation` 现在使用 `_get_source_meta_cached_by_kind(...)` 读取 source meta 并写入 `_meta_cache`（`read_runtime.py:1706`）。
2. 同一份 meta 通过 `meta=meta` 参数传入 `get_source_document_provenance(...)`（`read_runtime.py:1707-1711`），后者在 `_fs_source_document_core.py:365` 中检测到 `meta is not None` 时跳过文件读取。
3. `get_source_document_provenance(...)` 协议签名增加可选 `meta: DocumentMeta | None = None` 参数（`repository_protocols.py:169`），core 和 repository 实现一致。
4. Provider 分类仍由 `_FILING_SOURCE_TYPES_BY_PROVIDER` 和 `_CITATION_PROVIDER_LABELS` 从 provenance 派生，read runtime 未重建分类逻辑。
5. 所有 9 个 citation 调用点仍路由通过 `_build_citation`（source scan 确认）。
6. 新增 `test_read_runtime_citation_reuses_single_cached_source_meta_read` 使用 `_CountingSourceRepository` 验证两次 `_build_citation` 调用只触发一次 `get_source_meta`（`assert source_repository.get_source_meta_calls == 1`）。

**结论**: 修复正确。provenance parsing 仍在 repository 侧，read runtime 只消费投影结果。缓存键 `(ticker, document_id)` 与旧 `_get_document_meta_cached` 一致，无歧义。

### P3-F-S1-CR-F02 — 关闭 ✅

**Controller 要求**: `SourceDocumentProvenance.from_meta(...)` 必须显式要求 `ingest_complete`；`_build_citation` 必须拒绝 `provenance.ingest_complete is False`；增加回归覆盖。

**Fix 验证**:

1. `from_meta(...)` 将 `meta.get("ingest_complete", True)` 改为 `meta["ingest_complete"]`（`document_models.py:170`）。缺失时抛出 `KeyError`，与 `source_provider` / `ingest_method` 的 fail-closed 行为一致。
2. `_build_citation` 在取得 provenance 后检查 `if not provenance.ingest_complete: raise FileNotFoundError(...)`（`read_runtime.py:1712-1713`）。
3. `test_source_repository_fails_closed_for_missing_or_invalid_completed_provider` 现在覆盖三种失败场景：missing provider → `KeyError`、invalid provider → `ValueError`、missing `ingest_complete` → `KeyError`。测试通过先创建文档再用 `replace_source_meta` 移除 `ingest_complete` 字段来模拟损坏场景。
4. `test_read_runtime_citation_rejects_incomplete_source_meta` 构造 `ingest_complete=False` 的 `fil_incomplete` 文档，验证 `_build_citation` 抛出 `FileNotFoundError`（匹配 `"尚未完成入库"`）。
5. `_build_read_runtime_with_provenance_documents` helper 现在额外构造一个 `ingest_complete=False` 的 `fil_incomplete` 文档用于该测试。

**结论**: 修复正确。`ingest_complete` 现在与 `source_provider` / `ingest_method` 同等对待——缺失即 fail-closed。incomplete staging 文档在 citation projection 前被拒绝。

### P3-F-S1-CR-F03 — 关闭 ✅

**Controller 要求**: 移除 `internal_document_id` 重复校验；不能通过省略 stable field 掩盖冲突；增加或更新测试。

**Fix 验证**:

1. `_STAGING_STABLE_META_FIELDS` 从 tuple 中移除 `"internal_document_id"`（`_fs_source_document_core.py:55-61`），仅保留显式 request 字段比对（line 1047-1049）作为唯一真源。
2. `_staging_stable_fields_match(...)` 对 stable meta 字段做双向存在性判断（line 1053-1062）：
   - `existing_has_value = existing_value is not None and existing_value != ""` — 空字符串视为"未提供"。
   - `requested_has_value = requested_value is not None and requested_value != ""` — 同上。
   - `if not existing_has_value and not requested_has_value: continue` — 双方都未提供 → 匹配。
   - `if existing_has_value != requested_has_value: return False` — 一方有值另一方无 → 冲突。
   - `if existing_value != requested_value: return False` — 双方都有值但不同 → 冲突。
3. `test_stage_source_document_requires_existing_stable_fields_on_retry` 验证：
   - matching request（相同 `source_fingerprint`）→ 幂等返回同一 handle。
   - omitted fingerprint request（省略既有 `source_fingerprint`）→ `FileExistsError`（匹配 `"稳定字段冲突"`）。

**结论**: 修复正确。`internal_document_id` 不再重复校验。省略既有 stable field 正确触发冲突。空字符串按"未提供"处理，避免 repository 默认空 fingerprint 破坏幂等 staging。

## New Findings

未发现新 material defects。

**逐项检查**:

- `_get_source_meta_cached_by_kind` 与 `_get_document_meta_cached` 共享 `_meta_cache` 键 `(ticker, document_id)`：不产生歧义，因为同一 `(ticker, document_id)` 在给定 runtime 实例中对应唯一 source kind（由 `_resolve_source_kind` 确定）。
- `get_source_document_provenance(...)` 的 `meta` 可选参数在协议和实现间签名一致。
- `_staging_stable_fields_match` 的空字符串处理逻辑：当双方都为空时跳过比较（合理——repository 默认空 fingerprint 不应破坏双方都未提供 fingerprint 的幂等 staging）；当一方有值另一方为空时触发冲突（正确——空字符串 ≠ "未提供"，但当前实现将空字符串视为"未提供"以兼容 repository 默认值）。
- `_build_citation` 中 `meta` 由 `_get_source_meta_cached_by_kind` 返回，该方法在 cache miss 时调用 `get_source_meta` 并缓存结果；`get_source_meta` 在文档不存在时抛出 `FileNotFoundError`，不会将 `None` 写入 cache（与旧 `_get_document_meta_cached` 的 `try/except` 行为不同，但 `_resolve_source_kind` 已在上游确认文档存在）。

## Validation

- `pytest tests/fins/test_fins_storage_provider.py tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_runtime.py tests/fins/test_docling_upload_service.py -q`: **79 passed, 3 warnings**
- `pyright dayu/fins/...`: **0 errors**
- `git diff --check`: passed
- `rg -n 'startswith\("fil_"\)|startswith\('\''fil_'\''\)' dayu/fins/tools dayu/fins/pipelines`: 仅 `sec_rebuild_workflow.py:253`（SEC accession reconstruction，非 citation/provenance）
- `rg -n 'def _build_citation|_build_citation\(' dayu/fins/tools/read_runtime.py`: 1 定义 + 9 调用点，全部路由单一 helper

## Propagation Audit

1. **Producer truth**: SEC/CN/upload pipeline 写入 `source_provider`、`ingest_method`、`ingest_complete` — 未改变。
2. **Validator**: `SourceDocumentProvenance.from_meta(...)` 现在对 `ingest_complete` 做与 `source_provider` / `ingest_method` 同等的 fail-closed 校验 — 加强。
3. **Projection**: `_build_citation(...)` 通过 `_get_source_meta_cached_by_kind` 读取一次 meta，传入 repository provenance parsing，拒绝 `ingest_complete=False` — 加强。
4. **LLM-facing output**: incomplete staging meta 在 citation serialization 前被 `FileNotFoundError` 阻止 — 新增守卫。

## Residual Risk

- **Coverage 未测量**: pytest-cov 本地 numpy/pandas import 问题仍存在。79 tests + pyright 零报错，但单文件覆盖率数据缺失。
- **S2 blob acknowledgement**: `stage_source_document` skeleton 已就位，S2 需接入 blob 写入守卫。
- **`_meta_cache` 无 TTL**: 同一 runtime 实例内，如果 source meta 在 tool 调用期间被外部修改（如 staging → complete），cache 可能返回旧值。当前设计中 `_build_citation` 已加 `ingest_complete` 守卫，可覆盖该场景。

## Verdict

**PASS** — 三个 accepted findings 均已正确关闭，未引入新 material defects。provenance ownership 边界保持在 repository 侧，read runtime 只消费投影结果。
