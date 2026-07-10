# Code Re-Review — WU-SEMANTIC-OWNERSHIP-01 P3-F S1 Fix

## Scope

- Mode: current changes (unstaged) — fix re-review
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-rereview-ds.md`
- Reviewed artifacts:
  - MiMo review: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-mimo.md`
  - DS review: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-ds.md`
  - Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-controller-adjudication.md`
  - Fix report: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-fix-codex.md`
  - Controller fix validation: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-fix-controller-validation.md`
- Included scope: 17 unstaged files (867 insertions, original S1 was 633; +234 from fix)
- Excluded scope: untracked files per handoff
- Validation: `pytest` 79 passed, `pyright` 0 errors

## Verdict

**PASS** — 所有三个 controller 接受的 finding 均已正确修复，无新增 material defect，无 provenance ownership 漂移。

---

## Finding Status

### P3-F-S1-CR-F01 — 重复 meta 读取 ✅ FIXED

- **MiMo**: 001, **DS**: 1
- **Requirement**: 移除 `_build_citation` 对同一 meta.json 的双重文件读取，恢复缓存行为，不将 provider 分类重建在 read runtime。
- **Fix evidence** (逐条对照 controller adjudication):

| 要求 | 状态 | 直接证据 |
| --- | --- | --- |
| 单次 citation 构建只读一次 source meta | ✅ | `_build_citation` 通过 `_get_source_meta_cached_by_kind` 读取 meta（`read_runtime.py:1708`），传给 `get_source_document_provenance(meta=meta)` 复用（`read_runtime.py:1709-1714`） |
| Repository provenance 解析仍为 provider 校验真源 | ✅ | `get_source_document_provenance` 新增可选 `meta` 参数（协议 `repository_protocols.py:170`），内部 `meta if meta is not None else self.get_source_meta(...)`（`_fs_source_document_core.py:362`）——解析逻辑未移出 repository |
| read runtime 不重建 provider 分类 | ✅ | `_CITATION_PROVIDER_LABELS` / `_FILING_SOURCE_TYPES_BY_PROVIDER` 是 projection 映射（storage value → LLM-facing string），不替代 `FinsSourceProvider.from_storage_value` 的校验 |
| 所有 citation 仍走 `_build_citation` | ✅ | `rg` 扫描确认 1 定义 + 8 调用点，无新增分散 citation 构造 |
| 回归测试覆盖 | ✅ | `test_read_runtime_citation_reuses_single_cached_source_meta_read` 通过 `_CountingSourceRepository` 验证两次 `_build_citation` 仅触发 1 次 `get_source_meta` |

### P3-F-S1-CR-F02 — `ingest_complete` fail-closed + incomplete citation 拒绝 ✅ FIXED

- **MiMo**: 002, 003, **DS**: 2
- **Requirement**: `from_meta` 对缺失 `ingest_complete` fail-closed；`_build_citation` 拒绝 `ingest_complete=False`；增加回归测试。
- **Fix evidence**:

| 要求 | 状态 | 直接证据 |
| --- | --- | --- |
| `from_meta` 必填 `ingest_complete` | ✅ | `raw_ingest_complete = meta["ingest_complete"]`（`document_models.py:170`），缺失即 `KeyError` |
| `_build_citation` 拒绝 incomplete | ✅ | `if not provenance.ingest_complete: raise FileNotFoundError(...)`（`read_runtime.py:1715-1716`） |
| 缺失 `ingest_complete` → repository fail-closed | ✅ | `test_source_repository_fails_closed_for_missing_or_invalid_completed_provider` 新增 `missing_ingest_complete` 用例，`replace_source_meta` 移除字段后 `get_source_document_provenance` 抛 `KeyError` |
| incomplete → citation 拒绝 | ✅ | `test_read_runtime_citation_rejects_incomplete_source_meta` 构造 `ingest_complete=False` 文档，验证 `_build_citation` 抛 `FileNotFoundError` |

### P3-F-S1-CR-F03 — staging stable-field 冲突语义收紧 ✅ FIXED

- **MiMo**: 004, **DS**: 3
- **Requirement**: 移除 `internal_document_id` 重复校验；不允许省略既有 stable 字段绕过冲突检测；增加测试。
- **Fix evidence**:

| 要求 | 状态 | 直接证据 |
| --- | --- | --- |
| 移除 `internal_document_id` 重复 | ✅ | `_STAGING_STABLE_META_FIELDS` 从 `("internal_document_id", ...)` 改为 `("ingest_method", "source_provider", ...)`（`_fs_source_document_core.py:55-62`），显式比对保留为唯一真源（行 1051） |
| 省略既有 stable 字段 → 冲突 | ✅ | 新匹配逻辑：`existing_has_value != requested_has_value` 时返回 `False`（`_fs_source_document_core.py:1055-1056`）；当 existing 有 `source_fingerprint` 而 request 省略时检测到冲突 |
| 空字符串按"未提供"处理 | ✅ | `existing_has_value = existing_value is not None and existing_value != ""`（行 1053），空字符串与 `None` 同视为 absent |
| 相等 stable 字段仍幂等 | ✅ | `test_stage_source_document_requires_existing_stable_fields_on_retry`：第一次 staging + 匹配重入 → 返回同一 `SourceHandle` |
| 省略冲突测试 | ✅ | 同一测试：第一次写入 `source_fingerprint="fingerprint-v1"`，重入时不传 `source_fingerprint` → `FileExistsError` |

---

## New Defect Scan

对 fix 引入的全部新增/修改代码逐行走读，未发现新 material defect：

- **`_get_source_meta_cached_by_kind` helper**（`read_runtime.py:1742-1770`）：缓存 key 为 `(ticker, document_id)`，与 `_meta_cache` 的现有 key 一致。`document_id` 在 FILING/MATERIAL 间唯一，不会出现跨 source_kind 的 key 冲突。helper 不做 `try/except FileNotFoundError`，调用方 `_build_citation` 已通过 `_resolve_source_kind` 确认文档存在。
- **`_CountingSourceRepository` test**（`test_fins_storage_provider.py:534-579`）：正确继承 `FsSourceDocumentRepository`，只覆盖 `get_source_meta` 做计数，透传其余方法。
- **`test_stage_source_document_requires_existing_stable_fields_on_retry`**（行 846-901）：`first_request` 和 `matching_request` 的 `meta` 中 `ingest_complete=False` 在 `_stage_source_document_impl` 内被显式覆盖为 `False`，不受 `_upsert_source_document` 的 `setdefault(True)` 影响。已通过 `pytest` 验证。
- **`_build_citation` 中 `meta` 变量仍保留 `if meta else None` 守卫**（行 1719, 1729）：`_get_source_meta_cached_by_kind` 始终返回 `dict` 或抛异常，`meta` 永不为 `None`。守卫为无害死代码，不改动。
- **`_build_fins_workspace` / `_build_fins_financial_html_workspace` fixture 迁移**：两个 helper 的 create/update 路径均已补充 `source_provider: "user_upload"`，不依赖任何 fallback。

---

## Owner Boundary Re-Verification

| Owner | 职责 | Fix 后状态 |
| --- | --- | --- |
| Pipeline (SEC/CN/upload) | 写入 `source_provider` / `ingest_method` / `ingest_complete` | ✅ 不变，fix 未触及 pipeline |
| Repository (`SourceDocumentProvenance.from_meta` + `get_source_document_provenance`) | 校验并投影 typed provenance | ✅ `from_meta` 现在对缺失 `ingest_complete` fail-closed；`get_source_document_provenance` 接受可选 `meta` 参数避免重复读取，解析逻辑未移出 |
| Read runtime (`_build_citation`) | 从 provenance 投影 LLM-facing citation | ✅ 单次 meta 读取 + 缓存复用；拒绝 `ingest_complete=False`；`source_type` / `source_provider` 来自 `_FILING_SOURCE_TYPES_BY_PROVIDER` / `_CITATION_PROVIDER_LABELS` 映射（projection，非分类） |
| Staging (`stage_source_document` + `_staging_stable_fields_match`) | 未完成 source meta 生命周期 | ✅ `internal_document_id` 单一校验路径；省略既有 stable 字段被正确检测为冲突 |

---

## Propagation Audit

1. Source meta 仍由 pipeline / upload producer 写入 → ✅
2. Repository provenance parsing 是 `source_provider` / `ingest_complete` 的唯一校验 owner → ✅
3. Citation 从 repository provenance 派生 LLM-facing 字段 → ✅
4. Incomplete staging meta 不进入 LLM-facing citation → ✅（`_build_citation` 在 `provenance.ingest_complete is False` 时抛 `FileNotFoundError`）

---

## Residual Risk

- **S2 blob acknowledgement 未实现**：`stage_source_document` skeleton 已加强冲突检测，但 blob repository 仍未接入 source 承认守卫。S2 需基于此 skeleton 实现。
- **Coverage 未测量**：pytest-cov 本地不可用（numpy/pandas import 冲突），79 测试全部通过且 pyright 零报错，但单文件覆盖率百分比仍未知。
- **`_CountingSourceRepository` 仅覆盖 `get_source_meta` 调用次数**：未覆盖 `get_source_document_provenance` 内部跳过读取的路径（有 meta 参数时）。当前测试通过 citation 输出的正确性间接验证。

## Open Questions

无。
