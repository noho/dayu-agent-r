# WU-SEMANTIC-OWNERSHIP-01 P3-F Plan Review (AgentMiMo)

## Review Target

- Plan: `docs/host/wu-semantic-ownership-01-p3-f-fins-source-provenance-plan.md`
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-F - Fins source document, blob, provenance, citation, and wait timeout ownership`
- Goal confirmation: `docs/reviews/wu-semantic-ownership-01-p3-f-goal-confirmation.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
- Design docs: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`

## Review Date

2026-07-11

## Assumptions Tested

1. Plan is code-generation-ready — implementation agent can follow slices without redesigning contracts.
2. Source document provenance, blob acknowledgement, citation projection are correctly placed at source repository owner boundary.
3. `store_file(SourceHandle)` validation plus staging contract avoids orphan blobs without unsafe partial-source behavior.
4. `SourceType`/provider expansion is LLM-facing and self-explanatory.
5. Slices are independent enough to avoid overcoupling.
6. Company metadata freshness is current-scope and narrow.
7. Wait adapter deadline/expiry aligns with Host wait record ownership.
8. Slice boundaries, order, tests, coverage, README triggers, source scans, and propagation audit are sufficient.

## Findings

### 01-未修复-高-SEC download staging contract 的 `stage_source_document` 幂等性未定义

- **位置**: Slice 2 - Blob Acknowledgement and Explicit Staging Source Contract, Proposed Contracts / APIs
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: Plan proposes `stage_source_document(req: SourceDocumentUpsertRequest, source_kind: SourceKind) -> SourceHandle` which "writes `ingest_complete=False` meta and returns the only handle valid for pre-commit blob writes." Plan says SEC download should "create an `ingest_complete=False` staging source document before any blob write."
- **反例/失败场景**: SEC download workflow 有 retry 路径。`sec_download_filing_workflow.py:409` 构造 `SourceHandle` 后写 blob，若中途失败后重试，staging source document 已存在于磁盘上（`ingest_complete=False`）。当前 `_upsert_source_document` 的 `is_create=True` 路径在 meta 已存在时抛 `FileExistsError`（line 683）。`stage_source_document` 的契约未说明：重复调用时是幂等返回已有 handle，还是要求调用方先检查是否存在？SEC workflow 的 retry 路径（`previous_meta` 不为 None 且 `ingest_complete=False`）需要明确的 resume 语义，否则 implementation agent 必须自行设计幂等策略。
- **为什么有问题**: SEC download 的 blob-before-meta 顺序变更需要 staging 先于 blob write。但 staging 的幂等性直接决定 retry 路径是否安全。如果 `stage_source_document` 在已存在时抛异常，SEC retry 路径会失败；如果它静默返回已有 handle，需要确认 `req` 参数变更（如不同 `source_fingerprint`）时的行为。
- **直接证据**:
  - `sec_download_filing_workflow.py:409-413` — SourceHandle 在 source meta 之前构造
  - `_fs_source_document_core.py:682-683` — `is_create and meta_exists` 抛 `FileExistsError`
  - `sec_download_filing_workflow.py` — 有 `previous_meta` 检查和 update 路径
  - CN download 的 staging 模式 (`cn_download_filing_workflow.py:169`) 已证明 staging 幂等可行，但 CN 用的是 `update_cn_staging_source_document` 而非 `create_source_document`
- **影响**: Implementation agent 必须自行设计 `stage_source_document` 的幂等语义。若设计不当，SEC retry 路径失败或产生重复 staging 文档。
- **建议改法和验证点**: Plan 应明确 `stage_source_document` 的幂等契约：(1) 若 staging doc 已存在且 `ingest_complete=False`，返回已有 handle；(2) 若 staging doc 已存在且 `ingest_complete=True`，抛异常或要求显式 reset；(3) 调用方传入的 `req` 字段与已有 staging doc 不一致时的处理策略。测试应覆盖：首次 staging、重复 staging（幂等）、staging 后 commit、staging 后失败重试。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 高

### 02-未修复-中-get_source_document_provenance 签名与 _build_citation 调用上下文不匹配

- **位置**: Proposed Contracts / APIs - `get_source_document_provenance`
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: Plan proposes `get_source_document_provenance(ticker: str, document_id: str, source_kind: SourceKind) -> SourceDocumentProvenance`。但 `_build_citation` 当前从 `_get_document_meta_cached(ticker, document_id)` 获取 `source_kind`（line 1683），调用 provenance 方法时需要先知道 `source_kind`。
- **反例/失败场景**: `_build_citation` 只有 `ticker` 和 `document_id`。它当前从 meta dict 读 `source_kind`。如果 `get_source_document_provenance` 要求 `source_kind` 作为参数，`_build_citation` 需要先获取 meta 来拿到 `source_kind`，再调用 provenance 方法——这与"provenance 是唯一 source"的目标矛盾，因为 meta 读取本身就需要 source_kind。
- **为什么有问题**: `SourceHandle` 只有 `ticker`, `document_id`, `source_kind`（都是 str）。`_build_citation` 的调用方传入 `ticker` 和 `document_id`，`source_kind` 需要从某处获取。当前实现从 meta dict 获取。Plan 应明确：provenance 方法是否可以不带 `source_kind`（通过 document_id 搜索所有 source_kind），或者 `_build_citation` 是否应改为接收 `SourceHandle`。
- **直接证据**:
  - `read_runtime.py:1683` — `source_kind = normalize_optional_text(meta.get("source_kind"))`
  - `repository_protocols.py:92-185` — 现有 protocol 方法都要求 `source_kind` 参数
  - `document_models.py:288-294` — `SourceHandle` 有 `source_kind: str`
- **影响**: Implementation agent 需要自行决定 provenance 方法签名和 `_build_citation` 的适配方式，可能导致不一致的调用模式。
- **建议改法和验证点**: Plan 应明确 `_build_citation` 改造后的调用方式：(a) 先从 meta 获取 source_kind 再调 provenance，或 (b) provenance 方法不要求 source_kind（内部查找），或 (c) `_build_citation` 改为接收 `SourceHandle`。推荐 (a) 作为 current-scope 最小变更，但 plan 需要显式说明这不是"provenance 是唯一 source"的例外——meta 读取只是为了拿到 routing key，provenance projection 才是分类真源。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 03-未修复-中-Citation.source_provider 字段类型和 LLM-facing 语义未充分定义

- **位置**: Proposed Contracts / APIs - Citation model update
- **问题类型**: 契约缺失 / LLM-facing 文本约束
- **当前写法**: Plan says "Add `source_provider: str | None` to `Citation`"。`FinsSourceProvider` enum values 为 `sec_edgar`, `cninfo`, `hkexnews`, `user_upload`（lowercase business strings）。Plan says SourceType expansion is "LLM-facing" and "self-explanatory"。
- **反例/失败场景**: `Citation` 是 LLM-facing 输出。`source_provider: str | None` 允许任意字符串。Plan 未说明：(1) 这个字段是否会进入 LLM context；(2) 如果进入，`sec_edgar` 对 LLM 是否足够自解释；(3) `None` 值的语义——是 unknown provider 还是 material source 不需要 provider？现有 `SourceType` 枚举值（`SEC_EDGAR`, `UPLOADED`, `SUPPLEMENTARY`）是大写 business strings，但 `FinsSourceProvider` 的 storage values 是 lowercase。LLM-facing 输出用哪种？
- **为什么有问题**: 项目约束要求 LLM-facing 文本"只写模型完成当前任务所需的动作、输入、输出、判断规则和禁止事项"。`source_provider` 如果进入 LLM context，需要自解释。如果用 lowercase storage values，`sec_edgar` 对 LLM 不如 `SEC_EDGAR` 直观。Plan 应明确这个字段的 LLM-facing 行为。
- **直接证据**:
  - `tool_models.py:17-28` — `SourceType` enum values are uppercase: `SEC_EDGAR`, `UPLOADED`, `SUPPLEMENTARY`
  - Plan proposes `FinsSourceProvider` storage values as lowercase: `sec_edgar`, `cninfo`, `hkexnews`, `user_upload`
  - `Citation.to_dict()` — 输出所有非 None 字段，包括新字段
- **影响**: Implementation agent 需要自行决定 `source_provider` 的输出格式和 LLM-facing 语义。可能产生 lowercase/uppercase 不一致，或 `None` 语义不清。
- **建议改法和验证点**: Plan 应明确：(1) `source_provider` 在 `Citation.to_dict()` 中的输出格式（lowercase storage value 或 uppercase display value）；(2) `None` 的语义（仅 material source 不需要 provider，还是 unknown provider）；(3) 这个字段是否对 LLM 可见（tool result 中的 citation dict）。建议保持与 `SourceType` 一致的大写格式用于 LLM-facing 输出。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 04-未修复-中-CNINFO/HKEXNEWS SourceType 值未定义

- **位置**: Proposed Contracts / APIs - SourceType expansion
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: Plan says "CNINFO downloaded filing -> a distinct CNINFO source type, provider `cninfo`" and "HKEXNEWS downloaded filing -> a distinct HKEXNEWS source type, provider `hkexnews`"。但没有给出具体的 `SourceType` 枚举值名称。
- **反例/失败场景**: 当前 `SourceType` 只有 `SEC_EDGAR`, `UPLOADED`, `SUPPLEMENTARY`。Plan 要求新增 CNINFO 和 HKEXNEWS 类型，但未定义枚举值名称。Implementation agent 可能选择 `CNINFO`, `HKEXNEWS`, `CN_DOWNLOAD`, `HK_DOWNLOAD` 等不同命名。这些值是 LLM-facing 的，命名不一致会影响 LLM 分类准确性。
- **为什么有问题**: `SourceType` 是 `str, Enum`，新值会直接进入 LLM context。Plan 应明确枚举值名称，避免 implementation agent 自行命名导致不一致。
- **直接证据**:
  - `tool_models.py:17-28` — 当前 `SourceType` 只有 3 个值
  - Plan 说 "a distinct CNINFO source type" 但未给出具体值名
- **影响**: Implementation agent 需要自行命名 SourceType 枚举值。不同 agent 可能选择不同命名，影响 LLM-facing 输出一致性。
- **建议改法和验证点**: Plan 应明确新增的 `SourceType` 枚举值：`CNINFO = "CNINFO"` 和 `HKEXNEWS = "HKEXNEWS"`（与现有 `SEC_EDGAR` 命名风格一致）。测试应验证这些值在 citation 输出中的正确性。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 中

### 05-未修复-低-store_file 验证需要 blob repository 依赖 source repository

- **位置**: Slice 2 - Behavior changes, Proposed Contracts / APIs
- **问题类型**: 架构边界 / 最佳实践偏离
- **当前写法**: Plan says "`store_file(SourceHandle, ...)` raises `FileNotFoundError` before writing if source meta is absent." 这要求 `FsDocumentBlobRepository.store_file` 读取 source meta 来验证 SourceHandle 有效性。
- **反例/失败场景**: 当前 `FsDocumentBlobRepository` 不依赖 `SourceDocumentRepository`。`store_file` 只做 key 构建和文件写入。如果在 `store_file` 中添加 source meta 验证，blob repository 需要引用 source repository（或至少 source meta 读取能力）。这引入了 blob -> source 的依赖方向，而当前两者是平行的仓储实现。
- **为什么有问题**: 项目约束要求"模块间依赖最小化，优先接口或协议"。Blob repository 直接读取 source meta 是跨仓储边界的行为。更干净的做法是在调用方（pipeline/workflow）层面验证，或通过构造时注入 source meta 查询能力。
- **直接证据**:
  - `_fs_blob_core.py:114-151` — 当前 `store_file` 无 source meta 依赖
  - `_fs_storage_infra.py` — `FsDocumentBlobRepository` 和 `FsSourceDocumentRepository` 是平行实现
- **影响**: 如果在 blob repository 中直接读取 source meta，会引入跨仓储耦合。但这是可接受的 pragmatic 选择，只要通过 protocol 注入而非直接依赖具体实现。
- **建议改法和验证点**: Plan 应明确验证方式：(a) blob repository 构造时注入 `SourceDocumentRepositoryProtocol` 引用，或 (b) 在 pipeline/workflow 层面做 pre-validation。推荐 (a)，在 `FsDocumentBlobRepository.__init__` 中接收 optional `source_repository: SourceDocumentRepositoryProtocol`。测试应验证验证逻辑的正确性而非具体的依赖注入方式。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

1. **Host 是否为所有 Fins wait records 填充 `deadline_at` 或 `expires_at`？** 如果某些 wait records 两个字段都为 None，wait adapter 的新行为会返回 `WaitPollNotReady` 永久重试，而当前行为会在 300 秒后返回 `WaitPollLost`。Plan 的测试覆盖了 no-boundary 场景，但未确认 Host 是否保证至少一个字段非 None。建议 implementation agent 检查 Host wait record creation 路径。

2. **SEC download 的 `source_handle` 构造点是否需要移动？** 当前 SEC workflow 在 line 409 构造 `SourceHandle`，在 line 425 用于 blob write callback。如果 staging 要求 source meta 先于 blob write 存在，`source_handle` 的构造可能需要改为从 `stage_source_document` 的返回值获取。Plan 未明确这个 sequencing 变更的细节。

3. **Staging source document 的物理清理是否需要在 P3-F 中考虑？** Plan 说 "Physical cleanup of stale staging directories is not required in P3-F"。但如果 staging doc 残留过多（如大量失败的 SEC download），是否会影响 `list_source_document_ids` 的性能或 `ingest_complete` 过滤的正确性？当前 `_collect_source_documents_by_kind` 逐个读取 meta 文件，staging doc 会增加 I/O 但不影响正确性（因为 `ingest_complete=False` 被过滤）。

4. **`_build_citation` 改造后，`_get_document_meta_cached` 是否仍需要？** 如果 provenance 方法返回 `SourceDocumentProvenance` 包含所有分类信息，`_build_citation` 是否仍需要读取完整 meta dict 来获取 `form_type`, `filing_date`, `accession_no` 等字段？如果是，provenance 方法只解决分类问题，meta 读取仍需保留。

## Residual Risks

1. **Test fixture 更新范围**: Plan 提到 "Adding strict provenance may require updating existing test fixtures"。这是合理的，但 implementation agent 需要提前扫描所有使用 `SourceHandle` 的测试 fixture，确保它们包含 `source_provider` 字段。建议在 Slice 1 开始前做一次 fixture 扫描。

2. **SEC download 的 `_build_downloaded_filing_meta_payload` 需要添加 `source_provider`**: 当前 SEC pipeline 不写 `source_provider`。Plan 要求添加 `source_provider=sec_edgar`。这是简单的 meta dict 变更，但需要确保 `source_provider` 在 `_upsert_source_document` 的 `req.meta` 中正确传递并持久化。

3. **Company metadata freshness 的 `RESOLVER_VERSION` 常量来源**: Plan 引用 `RESOLVER_VERSION` 但未说明它来自哪个模块。当前 `upload_company_meta.py:17` 定义 `RESOLVER_VERSION = "market_resolver_v1.0.0"`。Plan 的 freshness helper 应使用同一个常量，避免版本字符串不一致。

4. **`_build_citation` 的 10 个调用点是否都需要改造**: 当前 `_build_citation` 在 `read_runtime.py` 中被调用 10 次。Plan 说 "all read/search/section/table/page/financial statement outputs use the same citation helper"。改造 `_build_citation` 内部逻辑即可覆盖所有调用点，无需修改调用方。这是 plan 的优点。

## Conclusion

**pass-with-risks**

Plan 的架构方向正确：source repository 作为 provenance 真源、blob acknowledgement 作为独立不变量、wait adapter 消费 Host-owned boundary、company metadata freshness 使用 resolver version。四个 slice 的分离合理，测试覆盖充分，source scans 和 propagation audit 完整。

主要风险是 SEC download staging contract 的幂等性未定义（Finding 01），这会迫使 implementation agent 自行设计关键的 retry 语义。其余 findings 是契约细节的补充，不构成 blocker，但应在 implementation 前收敛。

Material finding count:
- 高: 1
- 中: 3
- 低: 1

Open questions: 4
