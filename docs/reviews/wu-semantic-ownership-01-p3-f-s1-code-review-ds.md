# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-F S1

## Scope

- Mode: current changes (unstaged)
- Branch: `phaseflow/host-issues-control`
- Base: `main` (implied by deepreview default; S1 changes are unstaged workspace modifications)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-f-s1-code-review-ds.md`
- Included scope: 17 unstaged files per `git diff --stat` (S1 changes only)
- Excluded scope: committed changes on branch (prior work units); untracked files listed in command args (`docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`)
- Parallel review coverage: 无（单 reviewer 走读全部 S1 改动）

## Review Summary

S1 实现了 plan 中定义的 source provenance 和 citation projection 的核心变更：引入 `FinsSourceProvider` / `SourceDocumentProvenance`、pipeline 写入 provider、repository 校验与投影、read runtime 从 provenance 派生 LLM-facing `source_type` / `source_provider`、移除 `document_id.startswith("fil_")` 前缀分类逻辑。整体 owner boundary 正确：producer (pipeline) → validator (repository) → projection (read runtime)，citation 只消费 provenance 真源。

共发现 3 个 material finding：1 个中等（I/O 效率回退）、2 个低（软默认弱化 fail-closed、稳定性字段冗余），无严重或高风险 finding。

## Findings

### 1-未修复-中-`_build_citation` 对同一 meta.json 执行两次文件读取，且绕过实例级 meta 缓存

- **入口/函数**: `FinsReadRuntime._build_citation`
- **文件(行号)**: `dayu/fins/tools/read_runtime.py:1707-1709`
- **输入场景**: 任一 read tool（`list_tables`、`read_section`、`search_document` 等）构造 citation 时触发。
- **实际分支**: `_build_citation` 先调用 `self._source_repository.get_source_meta(ticker, document_id, source_kind)` 直接读取 meta.json（行 1708），再调用 `self._source_repository.get_source_document_provenance(ticker, document_id, source_kind)` 获取 provenance（行 1709）。`get_source_document_provenance` 在 `_fs_source_document_core.py:360-361` 内部再次调用 `self.get_source_meta(...)` 读取同一 meta.json 并解析。
- **预期行为**: 一次 citation 构造应对同一 meta.json 只执行一次文件读取与 JSON 解析。
- **实际行为**: 同一 meta.json 被读取并解析两次。此外，旧代码（修改前）通过 `_get_document_meta_cached` 走实例级 `_meta_cache` 缓存，新代码直接调用 `get_source_meta` 绕过该缓存，同一 tool 调用链中多次构造 citation（如 `list_documents` 为每个文档调用 `_build_citation`）无法复用已读取的 meta。
- **直接证据**: 
  - `read_runtime.py:1708`: `meta = self._source_repository.get_source_meta(ticker, document_id, source_kind)` — 第一次读取
  - `read_runtime.py:1709`: `provenance = self._source_repository.get_source_document_provenance(...)` — 内部触发第二次读取
  - `_fs_source_document_core.py:360`: `meta = self.get_source_meta(ticker, document_id, normalized_source_kind)` — 第二次读取的实现位置
  - 修改前 `_build_citation` 使用 `self._get_document_meta_cached(ticker, document_id)`（`read_runtime.py` 旧行 1692），新代码未走该缓存路径
- **影响**: 性能回退。`list_documents` 场景下每个文档 citation 多一次无缓存文件 I/O。meta.json 文件通常很小（<2KB），实际延迟影响有限，但违反"避免不必要 I/O"的编码纪律。
- **建议改法和验证点**: 
  1. 让 `_build_citation` 先通过 `_get_document_meta_cached` 获取 meta（恢复缓存行为）。
  2. 从缓存 meta 中读取 `source_kind`（`meta["source_kind"]`）作为路由键，或保留 `_resolve_source_kind` 但将其结果传入 provenance 调用。
  3. 将已缓存的 meta 传入 provenance 解析，避免 `get_source_document_provenance` 内部再次读取——可考虑增加 `SourceDocumentProvenance.from_meta` 直接接收已读取的 meta。
  4. 验证：`pytest tests/fins/test_fins_storage_provider.py` 确认 citation 输出不变。
- **修复风险（低）**: 改动局限在 `_build_citation` 和缓存路径，不影响 provenance 语义。
- **严重程度（中）**:

### 2-未修复-低-`SourceDocumentProvenance.from_meta` 对缺失 `ingest_complete` 字段默认 `True`

- **入口/函数**: `SourceDocumentProvenance.from_meta`
- **文件(行号)**: `dayu/fins/domain/document_models.py:170`
- **输入场景**: staging source document 的 meta.json 被外部损坏导致 `ingest_complete` 字段缺失。
- **实际分支**: `raw_ingest_complete = meta.get("ingest_complete", True)` — 字段缺失时取默认值 `True`，后续 `isinstance(raw_ingest_complete, bool)` 检查通过，返回 `ingest_complete=True`。
- **预期行为**: 对 staging meta（`ingest_complete=False` 是 staging 的核心语义标记）缺失该字段应 fail-closed（如 `KeyError`），与缺失 `source_provider` 的行为一致。
- **实际行为**: 字段缺失时静默当作完成态，下游 read runtime 会将 staging 文档暴露给 list/search/read 工具。当前 staging 写入路径（`_stage_source_document_impl` 行 902）确实始终写入 `ingest_complete=False`，所以正常路径不受影响；但若发生文件系统损坏或手动编辑 meta.json，该软默认会掩盖 staging 未完成的事实。
- **直接证据**: `document_models.py:170`: `raw_ingest_complete = meta.get("ingest_complete", True)` — 对比同方法中 `source_provider` 和 `ingest_method` 用的是直接键访问 `meta["source_provider"]` / `meta["ingest_method"]`（行 164, 167），缺失即 `KeyError`。
- **影响**: 仅在 staging meta 损坏时可能暴露未完成文档；正常路径不受影响。暴露面极小。
- **建议改法和验证点**: 
  1. 将 `meta.get("ingest_complete", True)` 改为 `meta["ingest_complete"]`，缺失时让 `KeyError` 自然传播，或显式检查并抛出 `ValueError("ingest_complete 字段缺失")`。
  2. 验证：`test_source_repository_fails_closed_for_missing_or_invalid_completed_provider` 已覆盖 missing/invalid provider，不需要额外测试。
- **修复风险（低）**: 改动一行，不影响正常路径。
- **严重程度（低）**:

### 3-未修复-低-`_staging_stable_fields_match` 中 `internal_document_id` 被重复校验

- **入口/函数**: `_staging_stable_fields_match`
- **文件(行号)**: `dayu/fins/storage/_fs_source_document_core.py:1047-1058`
- **输入场景**: 重复 staging 请求，`req.meta` 中包含 `internal_document_id` 键。
- **实际分支**: `internal_document_id` 先在第 1051 行通过 `existing_meta.get("internal_document_id")` 与 `req.internal_document_id` 做显式比对；然后在第 1053-1058 行的 `_STAGING_STABLE_META_FIELDS` 循环中再次通过 `req.meta.get("internal_document_id")` 与 `existing_meta.get("internal_document_id")` 比对。
- **预期行为**: 每个稳定字段通过单一校验路径检查即可。
- **实际行为**: `internal_document_id` 被两条路径重复校验。显式比对覆盖 `req.internal_document_id`（请求对象字段），循环比对覆盖 `req.meta["internal_document_id"]`（meta 字典中的值）。两条路径的比对源不同（request 字段 vs meta 字典），虽然当前 `_upsert_source_document` 会将 `req.internal_document_id` 写入 meta，但重复逻辑增加了维护者理解成本：未来若修改 `_upsert_source_document` 的写 meta 逻辑，可能只更新一条校验路径而遗漏另一条。
- **直接证据**: 
  - 行 1051: `if str(existing_meta.get("internal_document_id", "")).strip() != req.internal_document_id:`
  - 行 1053-1058: `for field_name in _STAGING_STABLE_META_FIELDS:` 中 `"internal_document_id"` 作为 `_STAGING_STABLE_META_FIELDS` 的成员（行 56），`req.meta.get("internal_document_id")` 与 `existing_meta.get("internal_document_id")` 再次比对
- **影响**: 无运行时错误，但重复校验路径降低代码可维护性。S2 修改 staging 逻辑时可能引入两条路径不一致的风险。
- **建议改法和验证点**: 
  1. 从 `_STAGING_STABLE_META_FIELDS` 中移除 `"internal_document_id"`，仅保留显式比对（行 1051），或反之移除显式比对，统一走循环比对。
  2. 验证：当前 staging 测试在 S2 中覆盖，S1 无 staging 行为测试。
- **修复风险（低）**: 改动局限在 `_STAGING_STABLE_META_FIELDS` 常量或比对函数。
- **严重程度（低）**:

## Architecture / Contract Ownership Verification

逐项检查 plan 中的 owner boundary 和 propagation path：

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| Pipeline 写入 `source_provider` | ✅ SEC/CN/upload 均写入 | `sec_download_source_upsert.py:208`, `cn_download_source_upsert.py:316`, `docling_upload_service.py:540` |
| Repository 校验并投影 typed provenance | ✅ fail-closed | `_fs_source_document_core.py:337-361`, `document_models.py:144-178` |
| read runtime 只消费 provenance | ✅ 移除 `startswith("fil_")` 和 `ingest_method` 分类 | `read_runtime.py:1707-1714`, `rg` 验证零匹配 |
| Citation 所有路径走同一 helper | ✅ | `rg` 验证 1 定义 + 8 调用点 |
| LLM-facing 值自解释、非内部名 | ✅ | `_CITATION_PROVIDER_LABELS` 和 `_FILING_SOURCE_TYPES_BY_PROVIDER` 映射 |
| `source_kind` 仅作路由键 | ✅ | `source_kind is SourceKind.MATERIAL` 仅用于 filing/material 分支；`source_type` 来自 provider |
| `stage_source_document` S1 skeleton | ✅ | 协议签名 + core 实现，未接入 blob guard（S2 职责） |
| Fixture 迁移 | ✅ | `meta.json` 增加 `source_provider: "sec_edgar"` |
| `startswith("fil_")` 残留 | ✅ 仅 `sec_rebuild_workflow.py:253`，已分类为 accession 重建 | plan 允许 |
| `ingest_method` in read_runtime | ✅ 零匹配 | `rg` 验证 |
| README 更新 | ✅ 在约束范围内 | `dayu/fins/README.md` 和 `tests/README.md` |

## Adversarial Failure Pass

- **缺失 provider 的完成态 source**: `KeyError` 从 `from_meta` 的 `meta["source_provider"]` 传播 → `get_source_document_provenance` → `_build_citation` → 工具调用失败。**fail-closed 正确**。
- **非法 provider 字符串**: `ValueError` 从 `FinsSourceProvider.from_storage_value` 抛出。**fail-closed 正确**。
- **CN candidate.provider 非法值**: `FinsSourceProvider.from_storage_value(candidate.provider)` 在 meta 写入前校验，阻止非法值落盘。**输入校验正确**。
- **staging 重复调用稳定字段不匹配**: `FileExistsError` 阻止写入。**conflict detection 正确**。
- **staging 时已有完成态 meta**: `FileExistsError` 阻止降级。**正确**。
- **staging 写入与 `_upsert_source_document` 的 `ingest_complete` setdefault 交互**: `staging_meta["ingest_complete"] = False` 在 `req.meta` 中设置，`merged_meta.update(req.meta)` 后覆盖 setdefault。**正确**。
- **Material citation provider**: 始终从 `provenance.source_provider` 派生，不硬编码。**正确**。
- **TOCTOU race (staging check vs write)**: 跨进程场景下存在窗口，plan 已接受为 residual risk。S2 需在 blob guard 中考虑。**已知 residual**。

## Open Questions

1. `_build_citation` 的双重 meta 读取是否需要在 S1 修复，还是作为已知效率问题推迟到后续优化？如果 `list_documents` 对 50+ 文档每个构造一次 citation，50 次双重读取的影响虽然小但可测量。

## Residual Risk

- **S2 blob acknowledgement 未实现**: `stage_source_document` skeleton 已就位，但 blob repository (`DocumentBlobRepositoryProtocol.store_file`) 尚未校验 source 承认。当前 S1 后，blob 仍可在无 staging source document 的情况下写入。
- **Coverage 未测量**: AgentCodex 和 Controller 均报告 pytest-cov 因本地 numpy/pandas import 冲突无法运行。S1 的 76 个测试通过且 pyright 零报错，但无法量化单文件覆盖率是否满足 80% 目标。
- **`_build_citation` 对 provenance 异常的传播**: 若 repository provenance 解析失败（如 meta 损坏），异常会直接传播到工具调用层，无降级 citation。当前设计是 fail-closed，但如果未来需要部分降级（如返回 citation 但标记 source_provider 缺失），需要单独设计。
- **S2 需统一 CN staging 与 SEC staging**: CN 路径已有 `update_cn_staging_source_document` 工作流 helper，S2 需将其对齐到 `stage_source_document` 的同一 invariant。
