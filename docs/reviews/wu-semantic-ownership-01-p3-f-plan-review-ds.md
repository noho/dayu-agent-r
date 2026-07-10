# WU-SEMANTIC-OWNERSHIP-01 P3-F Plan Review — AgentDS

## Review Target

- Plan: `docs/host/wu-semantic-ownership-01-p3-f-fins-source-provenance-plan.md`
- Status claimed in plan: `ready-for-plan-review`
- Goal confirmation: `docs/reviews/wu-semantic-ownership-01-p3-f-goal-confirmation.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control doc: `docs/host/issues-implementation-control.md`

## Assumptions Tested

1. **Assumption**: `_build_citation` classifies source by `document_id.startswith("fil_")` and `ingest_method` → **Confirmed**. Direct code evidence at `read_runtime.py:1695-1708`.
2. **Assumption**: `store_file` does not validate `SourceHandle` against source repository → **Confirmed**. `_fs_blob_core.py:114-151` delegates directly to `file_store.put_object()` with no source meta check.
3. **Assumption**: Fins wait adapter uses hardcoded 300s from `created_at` → **Confirmed**. `wait_adapter.py:105` defines `_TRANSIENT_PENDING_MAX_SECONDS = 300.0` and `wait_adapter.py:609-619` computes age from `created_at`.
4. **Assumption**: Upload ignores fresh company data when existing meta exists → **Confirmed**. `upload_company_meta.py:52-59` warns and returns if `existing_meta is not None`, never checking freshness.
5. **Assumption**: Host `WaitRecordRow` has `deadline_at` / `expires_at` → **Confirmed**. `state.py:467-468`.
6. **Assumption**: Host callback already uses `deadline_at` → `expires_at` precedence → **Confirmed**. `wait_callback.py:535-538`.
7. **Assumption**: CN pipeline already has staging pattern (`ingest_complete=False`) → **Confirmed**. `cn_download_source_upsert.py:123-159` writes staging meta with `ingest_complete=False`.
8. **Assumption**: SEC download and upload paths write blob files before source meta commit → **Confirmed**. `docling_upload_service.py:260` calls `store_file` before `_upsert_source_document`. `sec_download_filing_workflow.py:409-425` creates `source_handle` and passes `store_file` callback before source upsert.

## Material Findings

### DS-F01-未修复-中-SourceType新值未命名
- **位置**: Slice 1, "Proposed Contracts / APIs", 第 83-88 行
- **问题类型**: 不可直接实施
- **当前写法**: 计划要求 "CNINFO downloaded filing -> a distinct CNINFO source type" 和 "HKEXNEWS downloaded filing -> a distinct HKEXNEWS source type"，但未给出具体 `SourceType` 枚举值名称。
- **反例/失败场景**: 实施 agent 需要自行发明 `SourceType` 枚举值名称（如 `CNINFO_FILING`、`HKEXNEWS_FILING`、`CNINFO`、`HKEXNEWS` 等），这些值进入 LLM-facing `Citation.source_type`，直接影响模型行为。命名不当可能导致模型误解来源语义。
- **为什么有问题**: 当前 `SourceType` 枚举（`tool_models.py:17-27`）只有 `SEC_EDGAR`、`UPLOADED`、`SUPPLEMENTARY` 三个值。新增的 CNINFO 和 HKEXNEWS 枚举值是 LLM-facing 的 `source_type` 字符串，会直接进入模型上下文。计划要求 "LLM-facing 且自说明"，但未给出自说明的枚举值名称。同时 `FinsSourceProvider` 使用小写下划线（`cninfo`、`hkexnews`），`SourceType` 使用大写（`SEC_EDGAR`、`UPLOADED`），新增值应遵循哪种命名惯例未定。
- **直接证据**: `tool_models.py:17-27` 只有三个 `SourceType` 值；计划第 83-88 行只说 "a distinct CNINFO source type" / "a distinct HKEXNEWS source type"。
- **影响**: 实施 Agent 跑偏 / review 不可验收
- **建议改法和验证点**: 显式命名新增的 `SourceType` 值，例如 `CNINFO_FILING` 和 `HKEXNEWS_FILING`（遵循现有大写下划线惯例），或 `CNINFO` 和 `HKEXNEWS`（更简洁但在同一命名空间与 `FinsSourceProvider` 可能冲突）。命名后应验证在 citation 输出中自说明。
- **修复风险（低）**:
- **严重程度（中）**:

### DS-F02-未修复-中-SEC staging 插入点未指定
- **位置**: Slice 2, "Behavior changes", 第 163-164 行
- **问题类型**: 不可直接实施
- **当前写法**: "Upload and SEC download create an `ingest_complete=False` staging source document before any blob write."
- **反例/失败场景**: 当前 SEC 下载流程（`sec_download_filing_workflow.py:409-469`）在进入 `download_files_stream` 或 `download_files` 之前构造 `SourceHandle` 并传入 `_build_store_file(source_handle)`。`_build_store_file` 返回的闭包会直接调用 `blob_repository.store_file(handle=source_handle, ...)`。而 staging source document 的写入需要在构造 `SourceHandle` 之后、第一个 `store_file` 调用之前插入。这个插入点必须同时处理 `sec_download_filing_workflow.py`（per-filing 下载入口）和 `sec_pipeline.py:_build_store_file` 的调用链。如果插入点选错，可能遗漏某些调用路径或过早写 staging meta。
- **为什么有问题**: 计划只说 "before any blob write"，但没有指定在 SEC 管线的哪个函数、哪个位置插入 `stage_source_document` 调用。CN 已有独立入口 `update_cn_staging_source_document`（`cn_download_source_upsert.py:123`），但 SEC 没有等价入口。实施 agent 需要自行设计 SEC staging 调用的位置和形态，这可能导致 staging 写入时机错误（如构造 source_handle 之前调用，或某些下载路径遗漏 staging）。
- **直接证据**: `sec_download_filing_workflow.py:409-425`；`sec_pipeline.py:1553-1566`；`cn_download_source_upsert.py:123-187`
- **影响**: 实施 Agent 跑偏 / 后续返工
- **建议改法和验证点**: 明确 SEC staging 调用位置：在 `_download_single_filing_stream` 中，构造 `source_handle` 之后、进入 `download_files_stream` / `download_files` 之前，调用新增的 `stage_source_document`。或者按 CN 模式抽取独立的 `_build_sec_staging_source_document` helper。明确 staging 使用的文件和字段（类似于 CN 的 `file_entries` 和 `primary_document` 占位值）。
- **修复风险（低）**:
- **严重程度（中）**:

### DS-F03-未修复-中-低-公司元数据 resolver_version 变更机制缺失
- **位置**: Slice 4, "Behavior changes", 第 238-241 行
- **问题类型**: 范围漂移 / 过度设计
- **当前写法**: "Upload preserves existing company meta only when `existing_meta.resolver_version == RESOLVER_VERSION`." "Upload treats existing meta with a different resolver version as stale and requires current `company_name` to refresh it."
- **反例/失败场景**: 当前 `upload_company_meta.py:17` 定义 `RESOLVER_VERSION: Final[str] = "market_resolver_v1.0.0"` 为模块级常量。如果这个常量永远不变，则 `existing_meta.resolver_version == RESOLVER_VERSION` 永远为 `True`（因为 existing meta 也是用同一个常量写入的），freshness 检查退化为无操作。计划没有说明什么情况下 `RESOLVER_VERSION` 会变化、由谁管理版本号、版本变更后旧数据迁移如何处理。
- **为什么有问题**: 如果 `RESOLVER_VERSION` 从不变化，这个 Slice 实际上没有改变任何行为——所有已有 meta 都能通过 freshness 检查，上传路径仍然会在 `existing_meta is not None` 时直接返回（line 53-59）。如果未来要变更版本，如何确保所有已有 meta 被正确标记为 stale 而不是静默复用，是计划未覆盖的。这要么使当前 scope 无效（版本永不变 = 无行为变化），要么是低信号但需要设计决策的缺口。
- **直接证据**: `upload_company_meta.py:17`；`upload_company_meta.py:52-59`；`upload_company_meta.py:72-81`
- **影响**: 实施 Agent 跑偏 / 风险后移
- **建议改法和验证点**: 二选一：(a) 如果 `RESOLVER_VERSION` 的语义是每次 resolver 逻辑变更时递增，则在 plan 中说明版本管理策略（谁是版本拥有者、递增规则、是否需要测试证明版本跃迁行为）；(b) 如果当前无实际 version 变更需求，则将 freshness 规则从 "resolver_version 匹配" 改为更简单的规则（如 "上传路径始终覆盖 company_name 并用当前 fields 刷新"，因为 upload 场景下用户提供了显式 company 字段）。当前 scope 的定位是 "narrow"，不应引入一个永不触发的 freshness 机制。
- **修复风险（低）**:
- **严重程度（中-低）**:

### DS-F04-未修复-低-store_file TOCTOU 竞态风险
- **位置**: Slice 2, "Behavior changes", 第 163 行
- **问题类型**: 并发恢复风险
- **当前写法**: "`store_file(SourceHandle, ...)` raises `FileNotFoundError` before writing if source meta is absent."
- **反例/失败场景**: 两个进程（如两个 Host worker）同时上传同一 ticker 的不同文档。进程 A 检查 source meta → absent，通过检查；进程 B 也检查 source meta → absent，也通过检查；然后两者都写 blob。虽然文件系统级原子写入和 SQLite 事务可能防止损坏，但 `FileNotFoundError` 的 read-check-then-write 语义在并发场景不是原子的。
- **为什么有问题**: 这是一个真实但低概率的缺陷。项目通常单进程运行 Host，文件操作有 `dayu.runtime.filelock` 保护，但 `store_file` 本身没有在文件锁保护下做 check-then-write。这是 plan 未考虑的边界条件。
- **直接证据**: `_fs_blob_core.py:114-151`；`dayu.runtime.filelock` 是互斥锁但不保护 storage 内部操作。
- **影响**: 状态不一致（低概率）
- **建议改法和验证点**: 在 residual risk 中记录此 TOCTOU 风险。如果以后有多 worker 并发场景，需要将 source meta check 和 blob write 纳入同一文件锁临界区或使用 O_CREATE|O_EXCL 等原子文件系统语义。
- **修复风险（低）**:
- **严重程度（低）**:

### DS-F05-未修复-低-Slice 依赖关系未显式声明
- **位置**: Implementation Slices, Slice 1 和 Slice 2
- **问题类型**: 切片过粗 / 顺序不合理
- **当前写法**: Slice 1 和 Slice 2 都列出 `repository_protocols.py` 和 `_fs_source_document_core.py`。Slice 2 的 `stage_source_document` 方法依赖于 Slice 1 中的新 `SourceDocumentRepositoryProtocol` 方法。
- **反例/失败场景**: 如果 Slice 1 实现时没有在 `SourceDocumentRepositoryProtocol` 中添加 `stage_source_document` 方法（因为 Slice 1 的 scope 是 provenance/citation，不涉及 staging），则 Slice 2 启动时会发现协议缺少所需方法，需要回补 Slice 1。
- **为什么有问题**: 计划在 Slice 1 的 Proposed Contracts 中一起定义了 `stage_source_document`（第 73 行），但在 Slice 2 的 Files 列表中才列出 `repository_protocols.py`。实施 agent 按 Slice 顺序推进时，可能分别在两个 Slice 中重复修改同一文件，或者 Slice 1 遗漏了 Slice 2 需要的前置契约。
- **直接证据**: 计划第 102、150 行；第 73 行
- **影响**: 实施 Agent 跑偏 / 后续返工
- **建议改法和验证点**: 明确 Slice 边界：(a) Slice 1 负责 `SourceDocumentRepositoryProtocol` 新增方法（包括 `get_source_document_provenance` 和 `stage_source_document`），以及 `_fs_source_document_core.py` 中的对应实现骨架；(b) Slice 2 只负责 `store_file` 中消费这些方法、以及各管线中的 staging 调用。这避免 Slice 2 回补 Slice 1 的协议定义。
- **修复风险（低）**:
- **严重程度（低）**:

### DS-F06-未修复-低-测试 fixture 迁移工作量被低估
- **位置**: Slice 1, Tests, 第 136 行
- **问题类型**: 测试缺口
- **当前写法**: "Update fixture meta in `tests/fins/fixtures/.../meta.json` only if the touched tests load completed source meta through the new strict provenance contract."
- **反例/失败场景**: 一旦 `SourceDocumentProvenance.from_meta(...)` 对 completed source documents 严格校验 `source_provider`（plan 第 68 行："must fail closed on missing/invalid provider for completed source documents"），任何加载 completed source meta 的测试只要 fixture 缺少 `source_provider` 字段就会失败。当前 fixture meta.json 普遍不包含 `source_provider` 字段（SEC pipeline 当前不写 `source_provider`——见 `sec_download_source_upsert.py:202-226` meta dict 中无 `source_provider` 键）。这意味着几乎所有加载 SEC/C 下载 filing meta 的测试都会因为 provenance 解析失败而 break，不仅仅是 "touched tests"。
- **为什么有问题**: 计划说 "only if the touched tests load completed source meta through the new strict provenance contract"，但这低估了影响面。一旦 `get_source_document_provenance` 成为 `_build_citation` 的唯一入口（Slice 1 behavior），所有经过 `_build_citation` 的 read runtime 测试都会间接触发 provenance 解析。这个影响面可能比 "touched tests" 大很多。
- **直接证据**: `sec_download_source_upsert.py:202-226` 不写 `source_provider`；`read_runtime.py:1690` 通过 `_get_document_meta_cached` 读取 meta
- **影响**: 实施 Agent 跑偏 / 后续返工
- **建议改法和验证点**: 在 plan 中增加 fixture 影响面扫描要求：在实施前运行 `rg -l "meta\.json" tests/fins/fixtures/` 列出所有 meta fixture，并确认哪些会经过 provenance 解析路径。为这些 fixture 补齐 `source_provider` 字段，或用测试 helper 构造最小 valid provenance fixture。将 fixture 更新作为 Slice 1 的必要交付物而非可选步骤。
- **修复风险（低）**:
- **严重程度（低）**:

## Open Questions

### OQ-01: `store_file` 对 ProcessedHandle 的验证范围
计划第 77 行说 "`ProcessedHandle` behavior remains existing processed ownership." 但 `store_file` 签名接受 `SourceHandle | ProcessedHandle`（`repository_protocols.py:239-249`）。新增的 source meta 验证应该只在 `isinstance(handle, SourceHandle)` 时触发，还是对 ProcessedHandle 也需要等价验证？如果 processed blob 也有 orphan 问题（processed artifact 引用了不存在 source document 的 blob），应该纳入 scope 还是 deferred？计划未处理此边界。

### OQ-02: CN pipeline 已有 staging 模式与计划 staging 的一致性
CN 已有 `update_cn_staging_source_document`（`cn_download_source_upsert.py:123`），写入 `ingest_complete=False` meta。计划新增的 `stage_source_document` 是否应与 CN staging 共享同一个协议方法，还是两个独立入口？如果共享，CN staging 需要迁移到新的 `stage_source_document` 方法，这会导致 CN 路径的额外修改（与计划第 159 行 "CN already has staging behavior and should not be rewritten broadly" 矛盾）。如果不共享，则引入了两套 staging 机制。建议在 plan 中澄清 staging 协议的语义边界。

### OQ-03: SEC download staging 时 primary_document 和 file_entries 的占位值
CN staging（`cn_download_source_upsert.py:168`）写入 `ingest_complete=False` 和已知的 file_entries（因为 staging 在 PDF 下载完成后、Docling 转换前）。SEC 下载的 staging 需要在任何 blob 写入之前，此时还不知道 `primary_document` 和 `file_entries`。计划未指定 staging meta 中的这些字段用什么占位值。如果写入空 `files: []` 或 `primary_document: None`，需要确认 `list_documents` / read runtime 的 `ingest_complete=False` 排除逻辑能容忍这些占位值。

## Residual Risks

- **R1**: Slice 2 staging 失败后残留的 `ingest_complete=False` meta 不会被自动清理。计划承认这点（第 340-341 行）并接受为当前 scope 可容忍。若未来积累大量 staging meta 影响 `list_documents` 性能，需要独立的 cleanup WU。
- **R2**: `store_file` TOCTOU（DS-F04）在并发场景下仍有理论风险，但概率低且项目当前单进程运行。
- **R3**: `SourceType` 新值命名（DS-F01）影响 LLM-facing behavior。如果实施时选了不合适名称，需要 review gate 捕获。

## Deferred 项验证

计划第 339-343 行列出的 deferred items 边界合理：
- Stale staging 残留 → 已说明接受条件。
- Company metadata TTL → 明确在 P3-F 不引入。
- SourceType LLM-facing 约束 → 在 plan 中有 LLM-facing 文本约束声明。
- Rejected filing artifact storage → 已分类为 separate maintenance owner。

## Conclusion

**pass-with-risks**

Plan 的动机成立，owner boundary 放置在正确位置，四个 slice 的语义闭环清晰。整体 code-generation-ready 程度中等偏高：citation 路径、wait adapter 路径和 company metadata 路径的契约足够具体，可直接实施。但有三处需要收敛才能避免实施 agent 自行设计：

1. **DS-F01（中）**: `SourceType` 新增枚举值需显式命名。
2. **DS-F02（中）**: SEC staging 插入点需指定具体文件和函数位置。
3. **DS-F03（中-低）**: Company metadata `RESOLVER_VERSION` 需明确变更机制，否则建议简化为直接覆盖。

其余三项低严重度 finding（DS-F04 TOCTOU、DS-F05 slice 依赖声明、DS-F06 fixture 影响面）可作为 plan fix 补充说明或在 implementation report 中验证闭环。三个 open questions 不应阻塞进入 implementation gate，但需在进入前记录处置。

---

**Material finding count by severity**: 中 2, 中-低 1, 低 3。无严重 finding。无 blocking finding。

**Open questions**: 3
