# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D S2 Code Review (AgentDS)

## Artifact Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-D`
- Slice: `S2 — Virtual Section Consistency, Source Freshness, And Read Failure Contracts`
- Gate: `code review (AgentDS)`
- Reviewer: `AgentDS`
- Review date: `2026-07-13 10:04:41 CST`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-s2-controller-validation.md`
- Accepted plan: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`

## Scope

- Mode: current changes (S2 implementation diff)
- Branch: `phaseflow/host-issues-control`
- Base: `main`
- Included scope: All S2 allowed production/test files (18 production, 3 test files)
- Excluded scope: S3, R3-E, tool-security, Host/Engine files
- Review depth: 逐文件关键路径走读，含 adversarial failure pass 和 semantic ownership drift pass

## Review Method

1. 读取 accepted plan S2 章节、implementation artifact、controller validation
2. 沿真实代码路径逐行走读全部 18 个 production 文件和 3 个 test 文件的关键改动
3. 对 5 个重点深挖区域逐一检查：virtual section owner、tests/fakes、boundary inversion、README/docs、AGENTS.md 约束
4. 执行 adversarial failure pass：cache ABA、concurrent rebuild、decode failure、search cancellation priority、section duplicate/dangling ref
5. 执行 semantic ownership drift pass：storage → processor → read runtime → tool boundary

## Findings

未发现实质性问题。

### 重点深挖区域逐项分析

#### 1. Virtual Section Owner

**入口**: `_VirtualSectionProcessorMixin._refresh_virtual_section_state()` (`sec_form_section_common.py:426-497`)

**逐项验证**:

- **唯一 owner**: `_refresh_virtual_section_state()` 是 section index (`_virtual_section_by_ref`) 和 table 双向映射 (`_table_ref_to_virtual_ref`) 的唯一重建点。`ten_k_processor.py:87`、`bs_ten_k_processor.py:103`、`ten_q_processor.py:94`、`bs_ten_q_processor.py:105` 全部调用此方法；`_initialize_virtual_sections()` 在 `sec_form_section_common.py:408` 也调用它。零处手写 index/table rebuild。
- **10-K/10-Q edgartools 与 BS path 无 stale/dangling/last-write-wins**: refresh 方法在 `sec_form_section_common.py:450-497` 包含四层校验：
  1. 重复 section ref → `ValueError`（line 452-453）
  2. parent_ref/child_ref 悬挂或反向关系不一致 → `ValueError`（line 455-461）
  3. 底层 table_ref 重复 → `ValueError`（line 475-477）
  4. section table_ref 重复、悬挂、双向映射不一致、或存在未分配的底层 table → `ValueError`（line 479-497）
  - 所有非法状态均 fail closed，不存在 last-write-wins 或 silent dangling。
- **10-Q expansion identity multiset 约束**: 两条 10-Q path 在 expansion 前记录 `_virtual_section_identity_multiset()`（`ten_q_processor.py:89`、`bs_ten_q_processor.py:100`），expansion 后以 `expected_identity_multiset` 传入 refresh。`sec_form_section_common.py:446-448` 比较当前 multiset 与期望值，不等立即 `ValueError("虚拟章节 expansion 不得创建、删除或替换 section/ref")`。multiset 基于 `(id(section), section.ref)` 排序元组（line 424），正确捕获对象替换和 ref 变化。
- **10-K 路径不传 identity check**: `ten_k_processor.py:87` 和 `bs_ten_k_processor.py:103` 调用 refresh 时不传 `expected_identity_multiset`，因为 10-K expansion 允许创建新 section。设计正确。

**结论**: Section owner 语义完整，边界刚性，无下沉重算。

#### 2. Tests/Fakes

**入口**: `tests/fins/test_processor_read_consistency.py`（1565 行，23 个测试函数）

**逐项验证**:

- **Tests 断言 owner-level contract**: 每个测试均断言 owner 边界行为：
  - `test_processor_cache_reuses_equal_revision_and_rebuilds_after_source_change`（line 1267）：断言 processor 实例 identity、registry create_count、processor label 反映新 source。
  - `test_read_runtime_maps_invalid_utf8_to_source_decode_failure`（line 1294）：断言 `ErrorCode.SOURCE_DECODE_FAILED`、`__cause__` 是 `FinsSourceDecodeError`、registry create_count==0、processor cache size==0。
  - `test_processor_build_revision_race_has_zero_retry_and_no_cache_artifact`（line 1384）：断言 `ErrorCode.SOURCE_CHANGED_DURING_READ`、create_count==1（固定一次构建）、processor/meta cache 均为空。
- **Fakes 是真实子类，不限制生产行为**:
  - `_CountingProcessorRegistry` 继承 `ProcessorRegistry`，只增加计数和探针钩子（line 397-457）。
  - `_RevisionProbeRepository` 继承 `FsSourceDocumentRepository`，只覆盖 `get_primary_source` 和 `get_source_meta` 以注入可控行为（line 460-526）。
  - `_VirtualHarness` 是 `_VirtualSectionProcessorMixin` + `_VirtualBaseProcessor` 的多继承（line 692），不 mock mixin 内部方法。
  - 无 `unittest.mock.Mock`/`MagicMock` 或 `spec_set` 限制生产行为。
- **覆盖的 failure 场景**:
  - duplicate ref（`test_virtual_section_refresh_fails_closed_for_duplicate_or_dangling_refs`，line 1144）
  - dangling table ref（同上，`include_table_marker=False` 导致无法分配 table，line 1162-1164）
  - cache race：processor build race（line 1384）、meta read race（line 1409）、concurrent rebuild（line 1435）
  - search failure：list/enrichment/BM25F/profile 四个 stage（line 1485-1534），含 `__cause__` 验证
  - decode failure：非法 UTF-8 bytes（line 1043-1068）、materialize 失败（line 1071-1090）、report fallback 失败（line 1093-1117）
  - cancellation priority over search failure（line 1537-1564）
  - source 删除后 processor cache 不可用（line 1461-1482）
  - cross-document 诊断不消费 stale processor（line 1342-1381）

**测试缺口**: `_get_or_create_processor` 中 `FinsSourceDecodeError` 的 catch 分支（line 2613-2618）因 `_create_processor` 已将 `FinsSourceDecodeError` 转为 `FinsReadBusinessError` 而不可达。该分支无测试覆盖，但属于 dead code 而非行为缺陷——即使 `FinsSourceDecodeError` 以某种方式穿透，该 handler 仍正确转换为 `SOURCE_DECODE_FAILED`。不做为 finding 报告。

**结论**: Tests 覆盖全面，断言 owner-level contract，fakes 不限制生产行为。

#### 3. Boundary Inversion / Semantic Drift

**沿 storage → processor → read runtime → tool boundary 全链路走读**:

- **Storage → revision**: `_build_source_revision()`（`_fs_source_document_core.py:169-224`）仅从 canonical source meta 字段计算 digest（`document_version`、`source_fingerprint`、`form_type`、`primary_document`、`ingest_complete`、`is_deleted`、`files` 的 `name/uri/etag/last_modified/size/sha256/content_type`）。使用 canonical JSON（`sort_keys=True`） + SHA-256。不消费 mtime、log、processed state。`get_source_revision()` 方法在 protocol（`repository_protocols.py:252-274`）、facade（`fs_source_document_repository.py:439-462`）和 core（`_fs_source_document_core.py:499-524`）三层一致暴露 typed `SourceDocumentRevision`。
- **Read runtime → cache freshness**:
  - `_get_or_create_processor()`（`read_runtime.py:2544-2648`）：R1 → build → R2，mismatch 立即 typed fail，固定零 retry。evict 走 `_evict_processor_path_caches()`（line 2798-2833）同时清理 processor 和 meta（含 no-kind key）。
  - `_get_source_meta_cached_by_kind()`（line 2192-2273）：独立比较 revision（M1 → read/parse → M2），不依赖 `_get_or_create_processor` 已运行。evict 走 `_evict_source_kind_caches()`（line 2767-2796），清理匹配 source_kind 的 processor 和该 kind 的 meta。
  - `_get_document_meta_cached()`（line 2275-2292）：先 resolve source_kind，再委托 `_get_source_meta_cached_by_kind()`。无 no-kind positive fast path。
  - `_get_fresh_cached_processor_for_diagnosis()`（line 2500-2542）：诊断 peek 也先比较 revision，不返回 stale processor。
- **Processor → decode**: `source_text.py` 独占 bytes/path → UTF-8 转换。`_load_text()`（`sec_processor.py:877-890`）、`_extract_source_text_preserving_lines()`（`sec_report_form_common.py:598-617`）、`_extract_head_text()`（`sec_6k_rules.py:155-183`）全部复用。decode 失败保留 `UnicodeDecodeError` cause 且 message 不含 path/raw bytes。`_create_processor()`（`read_runtime.py:2695-2707`）在 registry 前校验 UTF-8，失败转 `SOURCE_DECODE_FAILED`。
- **Search → failure**: `search_document()`（`read_runtime.py:1006-1035`）的 section list、enrichment、BM25F、profile 四个阶段统一在 `except Exception` 块中先检查 cancellation priority，再转 `SEARCH_INDEX_FAILED`。无 empty BM25F fallback。
- **Tool boundary**: `FinsReadBusinessError.code` 使用 `ErrorCode` enum（`read_runtime_helpers.py:258`），tool boundary 投影 `.value`（`fins_tools.py:1048`）。新增 error code 枚举值（`error_contract.py:15-18`）与 plan 一致。

**验证无以下反模式**:
- downstream repair: 零处（citation/list/read/tool boundary 均无重算或 fallback）
- loose parsing: 零处（revision 字段严格校验类型，decode 严格拒绝非法字节）
- default masking: 零处（partial/degraded 状态均 typed fail，不返回成功空集）
- compat shim: 零处（无 re-export、wrapper、old-field alias）

**结论**: 全链路语义由正确 owner 产生、校验、投影。无 boundary inversion 或 semantic drift。

#### 4. README / Docs Decision

- S2 不修改任何 README。Accepted plan（line 528-531）明确：S2 不单独落 README，由 S3 aggregate docs step 统一更新 `dayu/fins/README.md`。
- Implementation artifact（line 123-127）正确记录此决策。
- 已读取 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】`——无违反。

**Residual risk 分类检查**（implementation artifact line 169-175）:
- 历史非 UTF-8 source：`assigned to later work unit`，owner 明确（encoding-policy decision）。
- cache reuse 增加 storage read：`assigned to later work unit`，owner 明确（profiling optimization）。
- 绕过 repository 的外部文件篡改：`fixed in current slice`，理由充分（违反既有 storage ownership contract）。
- downloader `errors="ignore"`：`legitimate downloader-side adapter`，分类正确（不在 read success contract 范围内）。
- 完整 `pytest tests/fins`：`covered by later approved slice`（S3 aggregate validation）。

**结论**: README decision 符合 accepted plan，residual risk 分类均有 owner/destination。

#### 5. AGENTS.md 约束

- **中文 docstring**: 全部新增/修改函数均包含中文 docstring，含 Args、Returns、Raises。验证通过的抽样：
  - `decode_source_bytes()`（`source_text.py:31-50`）
  - `_build_source_revision()`（`_fs_source_document_core.py:169-224`）
  - `_refresh_virtual_section_state()`（`sec_form_section_common.py:426-497`）
  - `_get_or_create_processor()`（`read_runtime.py:2544-2648`）
  - `_evict_source_kind_caches()`（`read_runtime.py:2767-2796`）
- **类型签名**: 无 `Any`、`object`、`hasattr`/`getattr` 在新增 public/internal contract 中。
  - `SourceDocumentRevision.digest: str`（frozen dataclass）
  - `CachedProcessor.revision: SourceDocumentRevision`（typed）
  - `FinsReadBusinessError.__init__(self, code: ErrorCode, ...)`（enum 类型）
  - `_build_source_revision() -> SourceDocumentRevision`（typed return）
- **无魔法字符串扩散**: Error codes 使用 `ErrorCode` enum；revision 字段名使用模块级 `Final` tuple 常量（`_SOURCE_REVISION_REQUIRED_TEXT_FIELDS` 等）。
- **无工具安全代码**: 零处涉及 upload allowlist、URL/TLS/redirect、sandbox、capability token。符合 plan hard non-goals。
- **无反向依赖**: `source_text.py` 只依赖标准库 + `dayu.documents.processors.source.Source`（公共契约）。`read_runtime.py` 只依赖 `dayu.fins.*` 和 `dayu.contracts.*`，无 `dayu.host`/`dayu.engine` import。验证：`grep -n 'dayu\.\(host\|engine\)' dayu/fins/tools/read_runtime.py` 零匹配。

**结论**: 全部 AGENTS.md 约束满足。

### Adversarial Failure Pass 补充验证

对以下反例逐一走读代码路径，确认行为正确：

| 反例 | 代码路径 | 实际行为 | 结论 |
| --- | --- | --- | --- |
| revision ABA（source A→B→A，中间 processor 缓存过期） | `_get_or_create_processor:2586-2599` | `cached.revision == revision_before` 使用值比较，ABA 下 cached.revision 与 revision_before 摘要相同 → cache hit | ✅ 正确复用 |
| revision 变化后 concurrent 双线程同时进入 lock | `_get_or_create_processor:2574-2648` | 第一个线程 build+put；第二个线程在 lock 内检查 `cached.revision == revision_before` → cache hit | ✅ 只构建一次（test_concurrent_reads 验证） |
| source 删除后 revision 读取抛异常，processor cache 未清理 | `_get_or_create_processor:2578-2585` | `except Exception` → `_evict_processor_path_caches` → raise | ✅ 缓存已清理 |
| `validate_source_utf8_text` 对二进制 source 跳过校验 | `source_text.py:111-119` | `media_type` 非文本且 suffix 不在 `_UTF8_TEXT_SUFFIXES` → 直接 return（line 120） | ✅ 二进制不校验 |
| search_document 的 list_sections 异常 + 同时 cancel | `read_runtime.py:1025-1031` | `FinsReadCancelledError` 优先 raise（line 1025-1026）；其他异常先 `_raise_if_fins_cancelled`（line 1030） | ✅ 取消优先 |
| 10-Q expansion 只修改 order/content 但 ref 不变 | `ten_q_processor.py:89-94` + `sec_form_section_common.py:446-448` | identity multiset 不变 → refresh 成功 | ✅ test_both_ten_q_paths 验证 |
| 10-Q expansion 创建新 section | `ten_q_processor.py:89-94` + `sec_form_section_common.py:447-448` | multiset 不同 → `ValueError("不得创建、删除或替换 section/ref")` | ✅ test_ten_q_path_rejects 验证 |

## Open Questions

无。

## Residual Risk

- `_get_or_create_processor` 中 `FinsSourceDecodeError` 的 catch 分支（`read_runtime.py:2613-2618`）因 `_create_processor` 已内层转换为 `FinsReadBusinessError` 而不可达。非 correctness 问题——若 `FinsSourceDecodeError` 以任意方式穿透，外层 handler 仍正确。不影响行为正确性，仅为 dead code。分类：`low-severity maintainability note`，可由 controller 裁决是否在 S3 清理。
- 10-K path 的 `test_both_ten_k_paths_migrate_to_shared_refresh_without_behavior_drift` 使用 no-op expansion（`_preserve_virtual_sections`），未验证 10-K expansion 创建新 section 后 refresh 的双向一致性。但 10-K expansion 创建 section 的行为在既有 `test_sec_pipeline_download.py` 中被集成测试覆盖，且 refresh 内部的 section/table 双向校验与 expansion 行为无关（无论 expansion 产生什么 section，refresh 均执行相同校验）。分类：`accepted test coverage gap`，S3 aggregate validation 覆盖。
