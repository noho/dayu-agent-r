# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-D Plan Review (AgentDS)

## Review Metadata

- Review artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-plan-review-ds.md`
- Reviewer: AgentDS (adversarial plan review)
- Plan under review: `docs/host/wu-semantic-ownership-01-round3-r3-d-fins-financial-read-contracts-plan.md`
- Date: 2026-07-13 08:04:36 CST
- Review type: adversarial plan review (no implementation, no commit, no push)
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Control truth: `docs/host/issues-implementation-control.md`, `docs/phaseflow-umbrella-optimization-control.md`
- Source finding truth: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md` R3-D section
- Goal artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-d-goal-confirmation.md`

## Motive And Owner Judgment

**Motive: 成立，严重性评估 production-high 准确。**

直接证据链：

1. `financial_base.py:17-28` — `FinancialStatementResult` 的 `reason` 和 `statement_locator` 为 `NotRequired`，`periods` 为 `list[dict[str, Any]]`；`scale` 为 `str | None` 无 enum 约束。`data_quality` 为 bare `str`。Producer 可合法产出丢失 quality/reason 的结果。
2. `sec_xbrl_query.py:434-486` — `_query_facts_rows` 对每个 concept 的 `query_obj.execute()` 异常做 `except Exception: continue`（line 485），无法区分 "concept 无事实" 与 "查询执行异常"。
3. `bs_report_form_common.py:376-387` 和 `bs_six_k_processor.py:922-940` — 对非空 XBRL rows 硬编码 `scale=None`，而 `sec_processor.py:637` 已调用 `_infer_scale_from_xbrl_query`。同一语义 triple owner。
4. `read_runtime.py:236-249` — `_ProcessorFinancialStatementPayload` 是 shadow TypedDict，缺少 periods/scale；`:1639-1675` 投影时丢弃 quality/reason。
5. `read_runtime_helpers.py:1017-1036` — `_infer_fiscal_year` 丢弃 `fiscal_period` 参数后恒定返回 `None`，是 dead no-op。
6. `ten_q_processor.py:76-92` — `_postprocess_virtual_sections` 调用 `expand_ten_q_virtual_sections_content` 修改 `_virtual_sections` 但不重建 `_virtual_section_by_ref` 或 table assignment。
7. `cache.py:37-179` — 纯 LRU，无 revision 绑定；`read_runtime.py:2468-2514` hit 后不读 storage。
8. `sec_processor.py:845-858` — `_load_text` 使用 `errors="ignore"`。
9. `read_runtime.py:984-1026` — search index 构建后 `except Exception: pass`（line 1025-1026），随后使用空 BM25F 继续成功。
10. `sec_download_filing_workflow.py:529-558` — not_modified skip 无 `download_version` 检查；而 `sec_pipeline.py:1369-1425` 的 fast/remote skip 已检查。
11. `upload_company_meta.py:148-175` — `_normalize_ticker_aliases` 只 `strip().upper()`，不调用 `try_normalize_ticker`（`ticker_normalization.py:128`）。
12. `sec_section_build.py:896`、`sec_table_extraction.py:98`、`sec_xbrl_query.py:81` — 三份完全相同的 `_normalize_optional_string`。

所有 12 项均有 direct code evidence，属于 Fins owner boundary 内的 semantic ownership 失败，不是 style cleanup。

**Owner 判定**: 正确。Plan 将所有修复定位在 Fins domain/processor/read-runtime/tool/pipeline owner boundary 内，不在 Host/Engine 增加 Fins 分支。

## Assumptions Tested

| # | Assumption | Verdict | Evidence |
|---|-----------|---------|----------|
| A1 | edgartools `query_obj.execute()` 能区分 "成功 0 rows" 与 "执行异常" | **未证实** | Plan 自身 stop condition（line 396-397）承认此风险，但未提供 edgartools API 行为证据 |
| A2 | `_query_facts_rows` 返回类型变更后所有 caller 无需额外适配 | **部分证实** | 两个 caller（`sec_processor.py:712`、`bs_report_form_common.py:317`）在 S1 allowed files；但 plan 未显式写出 caller 消费 `XbrlConceptQuerySummary` 的代码形态 |
| A3 | storage canonical meta 字段足以唯一确定 processor input revision | **成立** | `_fs_source_document_core.py:805-828` 包含 `document_version`、`source_fingerprint`、`form_type`、`primary_document`、`files`（name/uri/etag/last_modified/size/sha256）等字段 |
| A4 | 10-Q expansion 后 child section ref 不会与 parent 冲突 | **未充分处理** | Plan 说 "重复 ref立即抛 ValueError"（line 257），但未说明 expansion 如何保证 ref 唯一性 |
| A5 | `try_normalize_ticker` 覆盖 plan 声称的 HK/CN/US 例子 | **成立** | `ticker_normalization.py:84-147` 支持 `700.HK→0700`、`BRK.B→BRK-B`、沪股/深股/美股 |
| A6 | 所有 HTML/OCR/BS SixK producer 路径在 S1 allowed files 中 | **成立** | `html_financial_statement_common.py`、`six_k_form_common.py`、`bs_six_k_processor.py` 均在 S1 allowed files |
| A7 | 现有 `document creation lock`（`read_runtime.py:2496-2497`）足以序列化 cache rebuild | **成立** | `_get_creation_lock` 已存在，plan 复用该锁做 evict+rebuild |

## Findings

### F1 — 中 — edgartools query API 能力边界未证实，S1 核心矩阵依赖未验证假设

- **位置**: Plan S1 Contract Decision 2（line 176-213），State matrix（line 203-209），Stop condition（line 396-397）
- **问题类型**: 不可直接实施 / open question 未收敛
- **当前写法**: Plan 的 XBRL state matrix 要求 `_query_facts_rows` 区分 "concept execute 成功但 0 rows"（legitimate empty）与 "concept execute 抛异常"（failure）。当前代码 `sec_xbrl_query.py:484-486` 用 `except Exception: continue` 抹平两者。Plan 自身 stop condition 写 "如果当前edgartools query API不能区分'execute成功无rows'和'execute抛错'，停止并补直接证据"。
- **反例/失败场景**: 若 edgartools 在 XBRL 解析内部错误时返回 `[]` 而非抛异常（常见于底层 XML 解析库静默丢弃无效节点），则 `XbrlConceptQuerySummary` 的 `failed_concepts` 永远为空，all-failed 路径不可达，plan 的 state matrix 第二行与第四行在实现上等价，all-failed → exception 的设计退化为 empty-success。
- **为什么有问题**: Plan 的核心 state matrix 的第四行（all attempted executable concepts fail → raise）依赖 edgartools 能力假设。若该假设不成立，plan 必须重新设计 failure 检测机制（如 pre-check XBRL validity、post-validate 至少一个 concept 有有意义输出），而非回退 catch-and-continue。这意味着 S1 可能从一开始就需要 design change，不应该在 implementation 中才发现。
- **直接证据**:
  - Plan line 396-397 自身承认此风险
  - `sec_xbrl_query.py:484-486`: `try: result_rows = query_obj.execute()` / `except Exception: continue`
  - Plan line 203 state matrix 第四行: "all attempted executable concepts fail → raise XbrlQueryExecutionError"
- **影响**: 实施 Agent 可能在实现到一半时发现 edgartools API 无法满足要求，被迫停止或回退设计，产生返工
- **建议改法和验证点**:
  1. Plan 应增加一节 "edgartools API pre-check"，提供具体证据（如 edgartools 源码/文档中 `.execute()` 的异常契约，或已有测试证明 XBRL 损坏时确实抛异常而非返空）
  2. 或：在 plan 中增加 fallback 策略——若 edgartools 不抛异常，通过 post-validate（如检查返回对象是否为有效 DataFrame/有预期列名）检测隐式失败；明确写出 fallback 不影响 state matrix 其余行
  3. 验证点：需要一个 test fixture 构造损坏 XBRL 或 edgartools 不可用的 scenario，证明 all-failed → exception 路径可达
- **修复风险（低）**: 只需补充 edgartools API 证据或 fallback 策略，不改变 plan 架构
- **严重程度（中）**:

### F2 — 中 — Meta cache 独立访问路径的 revision 校验未显式说明

- **位置**: Plan S2 Contract Decision 4（line 232-250），特别是 line 239-250 cache contract；S2 Exact Allowed Changes item 2（line 441）
- **问题类型**: 契约缺失 / 切片过粗
- **当前写法**: Plan 详细说明了 `_get_or_create_processor` 的 cache revision 校验流程（R1-build-R2 三段式）。但对 `_get_source_meta_cached_by_kind` 的独立调用路径（如 `list_documents`、`get_document_info` 场景），plan 只说 "meta cache也绑定同一 revision"（line 250），未写出 meta cache hit 时的 revision 比较逻辑。
- **反例/失败场景**: `list_documents()` 调用 `_get_source_meta_cached_by_kind` 获取 citation/filing metadata。若 source mutation 发生但 `list_documents` 未被触发 processor rebuild（因为不涉及 processor），meta cache 返回旧 revision 的 meta，LLM 看到旧 document list。而同一时刻 `get_financial_statement` 触发 processor rebuild 后看到新数据。两个 tool result 在同一 session 中对同一 document 产生不一致事实。
- **为什么有问题**: Plan 的 cache freshness 目标 "read runtime 只复用与当前 storage-owned source revision 一致的 processor/meta cache"（goal item 6）要求 meta cache 也校验 revision。但 plan 只在 processor get 路径显式写了校验，meta 路径只靠 propagation scan 规则补救。Implementation agent 可能只实现 processor 路径而遗漏 meta 路径。
- **直接证据**:
  - Plan line 250: "meta cache也绑定同一 revision，避免 citation/list result在source mutation后继续使用旧 meta"
  - Plan line 488（propagation scan）: "every cache get必须同一call path有revision comparison"
  - Plan line 441（exact change item 2）: "processor/meta cache entry绑定revision；hit/build前后按上文校验，mismatch清两类cache"
  - 但 S2 allowed changes 未显式列出 meta cache 独立 get 方法需要修改
- **影响**: 实施 Agent 可能实现 processor cache freshness 但遗漏 meta cache 独立路径，导致 citation/document list 在 source mutation 后返回旧数据
- **建议改法和验证点**:
  1. 在 S2 Exact Allowed Changes 中显式增加一条：`_get_source_meta_cached_by_kind` 增加 revision comparison，mismatch 时 evict 并重建
  2. 在 Required Assertions 中增加：meta cache 独立 hit 时校验 revision；source mutation 后 list_documents 返回新 meta
  3. 在 S2 Required Freshness / State Matrix（line 447-456）增加一行：`source revision changes, meta cache accessed independently → meta rebuilt from storage`
- **修复风险（低）**: 只增加一行 explicit change item 和一条 assertion，不改变架构
- **严重程度（中）**:

### F3 — 中 — `_query_facts_rows` 返回值类型迁移的两个 caller 适配未显式展开

- **位置**: Plan S1 Contract Decision 2（line 176-213），S1 Exact Allowed Changes item 2（line 338）
- **问题类型**: 不可直接实施
- **当前写法**: Plan 说 `_query_facts_rows` 返回 `XbrlConceptQuerySummary(rows, attempted_concepts, successful_concepts, failed_concepts)`（line 192-198），但两个 caller（`sec_processor.py:712-727`、`bs_report_form_common.py:317-332`）当前消费 `rows: list[dict[str, Any]]` 返回值并做 `total=len(rows)`。Plan 未写出 caller 如何从 summary 提取 rows 并构建 `XbrlFactsResult`（含 `data_quality` 和 `reason`）。
- **反例/失败场景**: Implementation agent 在 `_query_facts_rows` 返回 summary 后，caller 仍做 `total=len(summary)` 或 `rows = summary`，导致类型错误或 `total` 语义不一致（summary 不是 list）。更糟的是，caller 可能忽略 `failed_concepts` 信息，退化为 "successful rows only" 的隐式降级，违背 plan 的 partial failure 可见性要求。
- **为什么有问题**: `_query_facts_rows` → caller 的接口变更是 S1 的 core data flow change。Plan 的 state matrix 只在 processor 层定义了行为，但 caller 如何消费 summary 并映射到 `XbrlFactsResult` 的 `data_quality/reason` 是同一语义闭环的关键环节。缺少这一步，implementation agent 需要自行设计 mapping 逻辑，增加 review 风险和返工概率。
- **直接证据**:
  - `sec_processor.py:712`: `rows = _query_facts_rows(...)`
  - `sec_processor.py:726-727`: `"facts": rows, "total": len(rows)` — 当前直接消费 list
  - `bs_report_form_common.py:317`: `rows = _query_facts_rows(...)`
  - `bs_report_form_common.py:330-331`: `"facts": rows, "total": len(rows)` — 同上
  - Plan line 192-198 定义 `XbrlConceptQuerySummary` 但未写 caller 解构/消费方式
- **影响**: 实施 Agent 需自行设计 caller→summary 映射，可能产生与 plan state matrix 不一致的实现，增加 review 轮次
- **建议改法和验证点**:
  1. 在 S1 Exact Allowed Changes item 2 中显式写：caller 从 `XbrlConceptQuerySummary` 提取 `rows` 作为 facts、根据 `failed_concepts` 是否非空决定 `data_quality/reason`、根据 `attempted_concepts` 是否为空做 pre-validation
  2. 或在 Contract Decision 2 的 state matrix 后增加 pseudo-code：`summary = _query_facts_rows(...); if summary.failed_concepts: quality="partial"; reason="query_partially_failed" elif summary.successful_concepts == 0: quality="xbrl"; reason=None # legitimate empty`
- **修复风险（低）**: 只增加 caller mapping 说明，不改变 contract
- **严重程度（中）**:

### F4 — 低 — 10-Q expansion 可能产生 child section ref 冲突

- **位置**: Plan S2 Contract Decision 5（line 253-261），特别是 line 257
- **问题类型**: 状态机漏洞
- **当前写法**: Plan 的 refresh helper step 1: "以最终 self._virtual_sections 重建 self._virtual_section_by_ref；重复 ref立即抛 ValueError。" `expand_ten_q_virtual_sections_content` 在 `ten_q_processor.py:89-92` 被调用，当前不重建 index。Plan 假定 expansion 后的 `_virtual_sections` 中所有 section（含 expansion 新增的 child sections）都有唯一 ref。
- **反例/失败场景**: 若 `expand_ten_q_virtual_sections_content` 为某个 parent section（如 "Item 2. Management's Discussion"）创建 child subsection（如 "Results of Operations"），并且 child 使用了与 parent 相同或与另一 section 冲突的 ref schema（如都映射到 `item_2`），则 refresh helper 在 step 1 重建 `_virtual_section_by_ref` 时触发 ValueError，read 操作 fail closed。虽然 fail closed 好于 silent inconsistency，但若合法 SEC 文档触发此路径，会导致原本可读的 10-Q 变为不可读。
- **为什么有问题**: Plan 未说明 expansion 后的 ref 唯一性保证机制。当前 `expand_ten_q_virtual_sections_content` 的实现细节（是否存在、如何生成 child section ref）在 plan 中未引用，implementation agent 不清楚 ref schema contract。
- **直接证据**:
  - `ten_q_processor.py:89-92`: `expand_ten_q_virtual_sections_content(full_text=full_text, virtual_sections=self._virtual_sections)` — expansion 后 `_virtual_sections` 被就地修改
  - Plan line 257: "重复 ref立即抛 ValueError" — 但未说明 expansion 如何避免重复
  - `sec_form_section_common.py:408`: `_virtual_section_by_ref = {section.ref: section for section in self._virtual_sections}` — 假设所有 section 有唯一 ref
- **影响**: 若合法文档的 expansion 产生 ref 冲突，会导致 read 操作失败；implementation agent 可能需要在 expansion 函数内增加 ref disambiguation 逻辑，超出 plan scope
- **建议改法和验证点**:
  1. Plan 应引用或简述 `expand_ten_q_virtual_sections_content` 的 ref 生成策略，或声明 expansion 不创建新 ref（只修改 content/order）
  2. 若 expansion 确实创建新 ref，需说明 ref schema 保证唯一性（如 child ref = `{parent_ref}.{child_index}`)
  3. 在 Required Assertions 中增加：expansion 后所有 virtual section ref 唯一
- **修复风险（低）**: 只需澄清 expansion 的 ref 策略
- **严重程度（低）**:

### F5 — 低 — HTML/OCR producer（`six_k_form_common.py`）的 financial contract 迁移细节未展开

- **位置**: Plan S1 Allowed Production Files（line 320-321）包含 `html_financial_statement_common.py` 和 `six_k_form_common.py`；S3 Allowed Production Files 包含 `value_normalization.py`
- **问题类型**: 不可直接实施
- **当前写法**: Plan 的 S1 Exact Allowed Changes item 3 说 "BS/Sec/HTML/OCR producer把period/scale evidence输入统一quality helper；units与scale拆分。" 但 `_build_statement_result_from_tables`（`six_k_form_common.py:883`）和 `extract_statement_result_from_ocr_pages`（`:907`）返回 `FinancialStatementResult` 的方式与 XBRL producer 不同——它们从 HTML table/OCR page 解析，没有 XBRL decimals 可用于 scale inference。Plan 未说明 HTML/OCR producer 如何满足新的 required scale/quality/reason 字段要求。
- **反例/失败场景**: Implementation agent 修改 XBRL producer（`sec_processor`、`bs_report_form_common`、`bs_six_k_processor`）以符合新 contract 后，HTML/OCR producer 仍返回旧格式（可能缺 scale/reason 字段），validator 拒绝。Agent 可能被迫为 HTML/OCR path 临时设计 scale/reason 语义——这正是 plan 试图消除的 "downstream fallback" 模式。
- **为什么有问题**: Plan 说覆盖 "所有真实 producer"（line 337），但 HTML/OCR path 的 scale/reason 语义不同于 XBRL path（无 decimals 证据），需要不同的 quality degradation 逻辑。Plan 未区分这两种 producer class 的 contract 差异。
- **直接证据**:
  - `six_k_form_common.py:883-904`: `_build_statement_result_from_tables` 调用 `_build_shared_statement_result_from_tables`
  - Plan line 165-166: `data_quality="partial"` 必须有非空 reason；`xbrl/extracted` 必须 `reason=None`
  - HTML/OCR producer 应返回 `data_quality="extracted"`，但 scale 从何而来？若 HTML 表格有 "($ in millions)" 表头，extract scale 的 owner 是谁？
- **影响**: HTML/OCR producer 的 contract 迁移可能需要在 S1 中做未预见的 design work，或被迫给 HTML/OCR 返回 `partial` + `scale_unavailable`，降低其可用性
- **建议改法和验证点**:
  1. Plan 应明确 HTML/OCR producer 的 scale 策略：若能从表头文本提取 scale→使用 extracted scale；若不能→返回 `partial` + `scale_unavailable`
  2. 在 S1 Required Assertions 中增加 HTML/OCR producer 的 quality/reason 矩阵覆盖
- **修复风险（低）**: 只需澄清 HTML/OCR producer 的 quality semantics
- **严重程度（低）**:

### F6 — 低 — 6-K preview decode failure 的 allowed test 覆盖可能不够

- **位置**: Plan S2 Allowed Test Files line 436: `tests/fins/test_sec_pipeline_download.py`（只覆盖6-K preview decode failure；不改download policy）
- **问题类型**: 测试缺口
- **当前写法**: Plan 的 S2 text decode contract（line 266-267）要求 `sec_6k_rules._preview_payload` 复用 strict decoder。但 S2 test validation command（line 474）的 6-K test filter 是 `-k '6k and decode'`，而 `test_sec_pipeline_download.py` 可能没有名为 "6k" 和 "decode" 的 test。Plan 假定该文件已有或新增此 test，但未确认。
- **反例/失败场景**: 若 `test_sec_pipeline_download.py` 中没有覆盖 6-K decode 的 test，S2 的 `pytest ... -k '6k and decode'` 返回 0 selected / 0 passed（pytest 默认不报错），给 implementation agent 假阳性通过。
- **为什么有问题**: 6-K preview decode path（`sec_6k_rules.py:155-182`）是三个 `errors="ignore"` 位置之一。若 test filter 无匹配，该路径的 strict decode 修复可能未被测试覆盖，回归风险后移。
- **直接证据**:
  - Plan line 474: `pytest tests/fins/test_sec_pipeline_download.py -q -k '6k and decode'`
  - `sec_6k_rules.py:155-182` 使用 `errors="ignore"`（需 grep 确认，已在 review evidence 中证实）
  - Plan 未确认 `test_sec_pipeline_download.py` 当前是否有匹配的 test
- **影响**: 实施 Agent 可能漏测 6-K decode 路径，或需要自行设计 test
- **建议改法和验证点**:
  1. Plan 应确认 `test_sec_pipeline_download.py` 中已有或 S2 将新增 6-K decode test
  2. 或：在 validation command 中使用显式 test function name 而非 `-k` filter
  3. 若当前无匹配 test，改为新增 test file 或 test function 的具体名称
- **修复风险（低）**: 只需确认或调整 test filter
- **严重程度（低）**:

## Accepted Plan Strengths

1. **Owner boundary 判定精确**。Plan 对 13 个 accepted findings 逐一做了 first-principles owner 分析，每项修复定位在正确的 Fins domain/processor/read-runtime/tool/pipeline owner。无一处将 processor 语义修补在 read runtime，无一处用 downstream fallback 补偿。

2. **Slice 划分合理**。3 slices 按 validation/blast-radius 切分：S1（financial/XBRL public contract）→ S2（processor/source freshness consistency）→ S3（domain helpers + aggregate closure）。依赖方向正确（S2 依赖 S1 contract，S3 依赖 S1+S2），无循环依赖。不是 one-finding-per-slice。

3. **Hard non-goals 和 scope corrections 明确**。Plan 明确排除 tool-security（upload/download security、SSRF、allowlist、TLS、byte budget）、R3-E、6-K 双引擎 fallback、全量 `DocumentMeta` migration、creation-lock lifetime。Scope 边界清晰，不会在执行中被动扩张。

4. **Stop conditions 完整**。每个 slice 有独立 stop condition，覆盖 API 能力不足、scope creep、charset policy 缺失、downstream 重算、security 扩张等关键风险点。S1 stop condition（line 396-397）直接承认 edgartools API 风险。

5. **Validation commands 和 propagation scans 具体**。每个 slice 的 pytest、coverage、pyright 命令和 rg propagation scan 均为可直接执行的 shell 命令。Scan expected result 写明了零匹配目标。Code-generation-ready 程度高。

6. **LLM-facing contract 设计克制**。tool description 只要求自足说明字段、类型、allowed values 和 scale-vs-units 区别（line 223-228），不暴露 internal governance terms。与 `docs/engine/design.md:340-356`（completed/failed outcome 边界）和 `docs/host/design.md:3141-3145`（self-explaining evidence）一致。

7. **Cache freshness 采用 revision comparison 而非 TTL/ingestion callback**。Plan 选择 "reuse 前验证 source freshness"（line 249-250），不把 ingestion callback 耦合进 read runtime，不依赖 mtime/processed meta。与 storage owner 一致。

8. **README 决策有节制**。只在 S3 aggregate closure 更新 `dayu/fins/README.md`，不在中间 slice 写 future state。

## Blocking Questions

1. **edgartools API 能力边界**：Plan 自身 S1 stop condition（line 396-397）承认 "如果当前edgartools query API不能区分'execute成功无rows'和'execute抛错'，停止并补直接证据"。Controller 是否应要求在 plan 进入 implementation 前提供此证据（或 fallback 策略），而非在 S1 implementation 中才发现？参见 F1。

2. **HTML/OCR producer scale semantics**：`six_k_form_common.py` 和 `html_financial_statement_common.py` 的 producer 不消费 XBRL decimals，其 scale 来源是 HTML 表头文本解析。Plan 是否应明确这些 producer 的 scale extraction owner 和 degradation 策略？参见 F5。

## Residual Risks

| Risk | Owner | Suggested tracking |
|------|-------|--------------------|
| edgartools API 无法区分 "0 rows" 与 "execute error"，迫使 S1 redesign | Controller: pre-S1 API verification | 在 S1 implementation start 前运行 edgartools smoke test |
| Meta cache 独立路径的 revision 校验被 implementation agent 遗漏 | S2 implementation agent + MiMo review | 在 S2 review checklist 显式增加 meta cache 路径检查 |
| 10-Q expansion child section ref 冲突在边界文档上触发 runtime ValueError | S2 implementation agent | 在 10-Q test fixture 中包含 subsection-heavy 文档 |
| HTML/OCR producer contract 迁移需要未预见 design work | S1 implementation agent | 在 S1 start 时先 audit HTML/OCR producer 的当前 FinancialStatementResult shape |
| Legacy SEC version + all not-modified 路径 test fixture 不存在 | S3 implementation agent | 构造 legacy version meta fixture 验证 behavior |

## Final Decision

**changes_requested**

Plan 在 owner 判定、slice 划分、scope 边界、LLM-facing contract 设计和 propagation scan 方面扎实。但 F1（edgartools API 能力未证实）和 F2（meta cache 独立路径 revision 校验未显式说明）需要 plan 修正后才能安全交给 implementation agent。

F1 是 S1 核心 matrix 的前置条件——若 edgartools 不能区分 "0 rows" 与 "execute error"，S1 的 all-failed → exception 路径不可达，需要 design change。建议在 plan 中增加 edgartools API pre-check 证据或 fallback 策略。

F2 是 S2 cache freshness 完整性的 gap——`_get_source_meta_cached_by_kind` 的独立调用路径缺少显式的 revision check 说明，存在 implementation agent 遗漏风险。

其余 findings（F3-F6）为低严重度，可在 plan 修订中一并处理，不单独阻塞 gate。

**Finding count: 6（2 中，4 低）**
