# Plan Review — WU-SEMANTIC-OWNERSHIP-01 P3-G

## Scope

- Reviewed target: `docs/host/wu-semantic-ownership-01-p3-g-fins-domain-contracts-plan.md`
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-G - Fins form/domain typed rules and processor result contracts`
- Context: P3-F accepted deepreview commit `1f00491b`; plan produced by AgentCodex only; no implementation yet.
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-plan-review-mimo.md`

## Assumptions Tested

1. Source findings are correctly adjudicated and dispositioned.
2. Owner boundaries are correct for each domain fact.
3. S1 is implementable without hidden compatibility shims.
4. S2 correctly separates raw provider parsing from product-level filtering.
5. S3 provides a real typed contract, not just a dataclass wrapper.
6. S4's `total != len(facts)` rule is consistent with processor contract.
7. Tests, source scans, and propagation audit are sufficient.

## Findings

### 001-未修复-高-S4 XBRL `total` 校验规则与 processor 输出语义不一致

- **位置**: S4 "Exact allowed changes" 和 "Tests" 章节
- **问题类型**: 契约缺失 / 状态机漏洞
- **当前写法**: "Processor result `total != len(facts)` fails closed or is rejected by the validation helper." Read runtime may dedupe facts but must not overwrite processor-owned `total`.
- **反例/失败场景**: Processor `query_xbrl_facts(...)` 返回 `total=len(facts)` 其中 `facts` 是 processor 输出的完整列表（`sec_processor.py:722-726`：`facts = [_normalize_fact_row(row) for row in rows]`，`total = len(facts)`）。Read runtime 的 `_normalize_xbrl_query_payload(...)` 对这些 facts 做 dedup（`read_runtime_helpers.py:1409`：`deduped_facts = _deduplicate_xbrl_facts(normalized_pairs)`）。如果 processor 返回 100 条 facts（`total=100`），read runtime dedup 后剩 95 条，则 `total=100 != len(deduped_facts)=95`，validation helper 会 fail closed——即使 processor 输出完全正确。
- **为什么有问题**: Plan 的校验规则 `total != len(facts)` 没有明确是在 processor 输出层还是 read runtime dedup 后校验。如果在 read runtime dedup 后校验，processor 的合法 pre-dedup `total` 会被误判为违约。如果在 processor 输出层校验，read runtime 的 dedup 不应触发 fail closed。
- **直接证据**:
  - `sec_processor.py:722-726`: `facts = [_normalize_fact_row(row) for row in rows]; "total": len(facts)`
  - `read_runtime_helpers.py:1409,1413`: `deduped_facts = _deduplicate_xbrl_facts(normalized_pairs); normalized_payload["total"] = len(deduped_facts)`
  - Plan S4: "Processor result `total != len(facts)` fails closed"
- **影响**: Implementation agent 可能在 read runtime dedup 后实现 `total != len(facts)` 校验，导致所有 dedup 场景 fail closed；或在 processor 输出层实现校验但无法覆盖 read runtime 的 `total` 覆盖问题。
- **建议改法和验证点**:
  1. 明确校验层级：processor 输出层校验 `total == len(facts)`（processor 自身一致性）；read runtime 层不覆盖 `total`，dedup 后新增 `deduped_total` 或等价派生字段。
  2. 明确 `total` 语义：processor-owned `total` 是 processor 输出的 facts count，不是最终 LLM-facing dedup count。
  3. 测试应覆盖：processor 返回 `total=100` + 100 facts → read runtime dedup 到 95 → 输出保留 `total=100` + 派生 count。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 高

### 002-未修复-中-S1 范围过粗，未明确 `form_type_utils.py` 处置方式

- **位置**: S1 "Exact allowed changes" 章节
- **问题类型**: 切片过粗 / 不可直接实施
- **当前写法**: "Remove or stop using `processors/form_type_utils.py` and duplicate mappings in `sec_form_utils.py` / `sec_fiscal_fields.py`; update imports to domain truth."
- **反例/失败场景**: `form_type_utils.py` 被 6+ 个 processor 模块 import（`sec_processor.py`、`bs_report_form_common.py`、`sec_report_form_common.py`、`sec_form_section_common.py`）。Plan 说"remove or stop using"但未明确是删除文件还是保留文件只迁移调用方。如果删除文件，所有 import 都会 break；如果保留文件，source scan 会持续匹配，completion signal 难以判定。
- **为什么有问题**: Implementation agent 需要明确决策：是删除 `form_type_utils.py` 并更新所有 import，还是保留文件但将内部实现委托给 domain helper。两种路径的工作量和风险不同。
- **直接证据**:
  - `rg` 显示 `form_type_utils` 被 `sec_processor.py:47`、`bs_report_form_common.py:32`、`sec_report_form_common.py:26`、`sec_form_section_common.py:49` 等多处 import。
  - Plan S1 completion signal: "duplicate source-scan matches are classified as tests, deleted files, or deliberate call sites into the domain helper."
- **影响**: Implementation agent 可能选择保留 `form_type_utils.py` 作为 wrapper（违反 non-goal "不为旧 import path 增加兼容 re-export/wrapper"），或选择删除但遗漏某个 import 导致运行时 break。
- **建议改法和验证点**:
  1. 明确 `form_type_utils.py` 处置：删除文件，所有 import 迁移到 domain helper。
  2. 列出所有需要更新的 import 位置（至少 6 处）。
  3. Source scan 应该零匹配（文件已删除）。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 003-未修复-中-S2 下载器 product-level filtering 与 raw provider parsing 边界不清

- **位置**: S2 "Exact allowed changes" 和 "Tests" 章节
- **问题类型**: 架构边界 / 过度耦合
- **当前写法**: "Downloader adapters keep HTTP fetch/JSON decode/provider raw field normalization only." Pipeline helper handles title blocking, language filtering, fiscal inference.
- **反例/失败场景**: `cninfo_downloader.py:873` 的 `_is_title_blocked(title)` 检查标题是否包含"取消"、"更正"等关键词。这到底是 CNInfo provider 特定的 raw parsing（某些标题在 CNInfo 上不是财报），还是 product-level filtering（所有 provider 都应排除这类标题）？如果它是 provider-specific，应留在 downloader；如果是 product-level，应移到 pipeline。Plan 没有明确分类标准。
- **为什么有问题**: Implementation agent 可能把 provider-specific 解析逻辑错误移到 pipeline，或把 product-level 过滤错误留在 downloader。两种错误都会导致 S2 completion signal 难以满足。
- **直接证据**:
  - `cninfo_downloader.py:873`: `_is_title_blocked(title)` 检查"取消"、"更正"、"延期"等。
  - `hkexnews_downloader.py:1135`: `_looks_like_english_report_text(title)` 检查 "Annual Report"、"Interim Report" 等。
  - Plan S2: "Downloader adapters keep HTTP fetch/JSON decode/provider raw field normalization only."
- **影响**: Implementation agent 可能在边界判断上跑偏，导致 S2 返工或引入 regression。
- **建议改法和验证点**:
  1. 明确分类标准：如果过滤逻辑依赖 provider 特定的 HTTP response 格式或 provider 特定的字段命名，属于 raw parsing；如果过滤逻辑基于通用财报业务语义（如"取消"、"更正"），属于 product-level。
  2. 对 `_is_title_blocked`、`_looks_like_english_report_text`、`_infer_fiscal_year`、`_infer_fiscal_period_from_text` 逐个分类。
  3. 测试应证明 downloader 只返回 raw announcements，pipeline helper 负责 filtering。
- **修复风险（低/中/高）**: 中
- **严重程度（低/中/高/严重）**: 中

### 004-未修复-低-S3 `dict[str, dict[str, str]]` 在 `sec_sc13_filtering.py` 中有 7 处使用

- **位置**: S3 "Allowed files/modules" 章节
- **问题类型**: 过度耦合
- **当前写法**: Allowed files 包含 `sec_download_state.py`、`sec_download_diagnostics.py`、`sec_pipeline.py`，但未列出 `sec_sc13_filtering.py`。
- **反例/失败场景**: `sec_sc13_filtering.py` 有 7 处使用 `dict[str, dict[str, str]]` 作为 `rejection_registry` 参数类型。S3 将 repository protocol 改为 typed registry 后，`sec_sc13_filtering.py` 的所有调用方都需要更新。但 `sec_sc13_filtering.py` 不在 S3 allowed files 中。
- **为什么有问题**: S3 改 repository protocol 后，`sec_sc13_filtering.py` 的类型签名会 break pyright。Implementation agent 要么超范围修改 `sec_sc13_filtering.py`，要么留下类型错误。
- **直接证据**:
  - `rg` 显示 `sec_sc13_filtering.py` 有 7 处 `dict[str, dict[str, str]]`。
  - S3 allowed files 未包含 `sec_sc13_filtering.py`。
- **影响**: pyright 报错或 implementation agent 超范围修改。
- **建议改法和验证点**:
  1. 将 `sec_sc13_filtering.py` 加入 S3 allowed files。
  2. 或在 S3 中提供 typed registry → `dict[str, dict[str, str]]` 的兼容 shim（但违反 non-goal "不为旧 import path 增加兼容 re-export/wrapper"）。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- S1 的 `form_type_utils.py` 是否应该在 S1 中删除，还是保留到后续 phase？Plan 的 non-goal 说"不为旧 import path 增加兼容 re-export/wrapper"，但 S1 的 completion signal 允许 "deleted files"——需要明确。
- S2 的 `_is_title_blocked` 和 `_looks_like_english_report_text` 是否应该在 S2 中移到 pipeline，还是属于 provider-specific raw parsing？需要逐函数分类。
- S4 的 `total` 语义：processor-owned `total` 是 pre-dedup 还是 post-dedup？当前代码是 pre-dedup（`len(facts)` before read runtime dedup）。Plan 应明确。

## Residual Risks

- **S1 import 范围**: S1 触及 10+ 文件的 import 更新，source scan 需要仔细分类。
- **S2 测试 fragility**: CN/HK downloader tests 可能直接断言 filtering behavior，需要迁移为 pipeline helper tests。
- **S3 protocol 变更**: Repository protocol 变更可能影响 `sec_sc13_filtering.py`、`ingestion_runtime.py` 等未列入 allowed files 的模块。
- **S4 dedup 语义**: Processor 的 `total` 和 read runtime 的 dedup count 之间的关系需要明确，否则 implementation agent 可能引入 regression。

## Verdict

**pass-with-risks** — Plan 的动机成立，source findings 正确处置，owner boundaries 合理。但 S4 的 XBRL `total` 校验规则与 processor 输出语义存在不一致（finding 001），需要在 implementation 前明确校验层级和 `total` 语义。S1/S2/S3 有中等风险的范围/边界问题，不阻塞 plan 但需要 implementation agent 做额外决策。
