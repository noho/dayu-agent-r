# WU-SEMANTIC-OWNERSHIP-01 R08 Code-Review Fix Plan Correction Review — AgentDS

## 1. Verdict

**PLAN ACCEPTED WITH 2 MEDIUM FINDINGS, 3 LOW OBSERVATIONS**。

Corrected plan 是 code-generation-ready。五个 owner-family candidate 均能通过 `FinsReadRuntime`
public seam 或唯一 module-helper 例外真实执行到 `read_runtime_helpers.py` 并贡献 coverage
statements。typed fixture+真实 repository 模式在当前仓库基础设施中已有完整先例。typed failure
（`FinsReadArgumentError`、`FinsReadBusinessError`、`KeyError`）与当前 API 完全一致。连续最短
前缀/首次80停止可机械验证。negative scans 无误伤 baseline。共享 `test_fins_read_runtime.py`
boundary 保持。没有 omnibus/compat 搬运。fake-only/private cache/processor/Host state/
偶然顺序均有硬 stop gate。完整 §6.6/§6.7、R07 no-touch、Host truncation、security/deferred
边界全部保留。

两项 MEDIUM finding 涉及 candidate 的 observable assertion 边界与实际 processor 行为对齐，
不是 plan 设计缺陷；三个 LOW observation 是文档清晰度建议。

## 2. Hash Verification

### 2.1 Protected hashes — 独立重算

| Hash | Expected | Actual | Status |
|---|---|---|---|
| corrected plan SHA-256 | `86bb76c768609451ca5f2de297f04f971832b719c6ca5a8b4a94d1617753fa65` | `86bb76c768609451ca5f2de297f04f971832b719c6ca5a8b4a94d1617753fa65` | **PASS** |
| protected 23-path `git diff --binary -- dayu/fins tests` SHA-256 | `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d` | `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d` | **PASS** |
| `test_fins_read_runtime.py` SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | **PASS** |
| guards correction-entry SHA-256 | `4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` | `4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` | **PASS** |
| staged paths | empty | empty | **PASS** |

### 2.2 Deletion boundary scans — 独立验证

- §6.7F shared-file deletion boundary scan on `test_fins_read_runtime.py`：exit 1，零命中。✅
- §6.7F compatibility/private-helper negative scan on `test_read_runtime_semantic_ownership_guards.py`：exit 1，零命中。✅
- 四个删除节点（`test_read_helper_document_discovery_rules_preserve_public_semantics` 等）与九个专用 imports（`_build_table_data_payload` 等）均不在 `test_fins_read_runtime.py` 中。✅

### 2.3 Current tree state

- `test_fins_read_runtime.py` 含 9 个 test functions：2 generic（LRU、form-matching）、6 normalize/dedup、1 fiscal。✅
- `test_read_runtime_semantic_ownership_guards.py` 含 15 个 test functions，均在既有 owner guard 范围。✅
- 无 `skip` / `xfail` / `pragma: no cover` / `type: ignore` bypass。✅

## 3. 完整 Corrected Plan 审查

### 3.1 §0–§2：Gate、第一性原理、完成定义与非目标

**审查结果：PASS。**

- §0 gate 定义精确：plan-only correction，授权只修改计划与 Codex artifact，不修改 product/tests/README。✅
- §1 六项第一性原理判断均有直接代码/coverage 证据支撑。`read_runtime_helpers.py` 的 `320/494 = 64.78%` 与 R08 normalize/dedup 闭包理论上限 `351/494 = 71.05%` 的数学自冲突分析正确——这是修正的根因，不是新的产品需求。✅
- §2.1 完成定义明确 guards 文件的新职责：承载最小 stable-owner evidence，首次 `>=80.00%` 停止。✅
- §2.2 不可回改 owner 表格精确列出 R06 transaction、R07 storage/identity/revision/snapshot/citation/provenance 的 no-touch 边界。✅
- §2.3 out-of-scope 明确排除 R09-R12、Issues 142/151/175/177/178、统一 authorization、Host/Engine/Service/UI。✅

### 3.2 §3：字段与 Owner Inventory

**审查结果：PASS。**

- §3.1 Financial producer contract：`reason` 改为 optional、七值闭集、`statement_locator`/`StatementLocator`/`statement_method_missing`/`statement_empty` 删除。✅
- §3.2 XBRL processor-internal contract：`total`、`deduped_fact_count` 删除，`fact_count` 只属于 S2 public projection。✅
- §3.3 Actual producer inventory 表精确列出每个 processor 文件、当前偏差与 S1 动作。✅
- §3.4 Consumers、alternate owner 与 tests：`_build_financials_payload` alternate owner 删除、test migration inventory 明确。✅

### 3.3 §4：目标 Contracts（代码生成真源）

**审查结果：PASS。**

已验证当前 `result_types.py`（行 250-406）的目标 shape 与计划完全一致：

```python
# 行 250-263：PublicFinancialStatementResult — 与 §4.1 完全一致
class PublicFinancialStatementResult(TypedDict):
    ticker: str
    document_id: str
    citation: dict[str, JsonValue]
    statement_type: str
    periods: list[FinancialPeriod]
    rows: list[dict[str, JsonValue]]
    currency: str | None
    units: str | None
    scale: FinancialScale | None
    data_quality: FinancialDataQuality
    reason: NotRequired[FinancialStatementReason]

# 行 271-281：PublicXbrlQueryResult — 与 §4.3 完全一致
class PublicXbrlQueryResult(TypedDict):
    ticker: str
    document_id: str
    citation: dict[str, JsonValue]
    query_params: XbrlQueryParams
    facts: list[dict[str, JsonValue]]
    fact_count: int
    data_quality: XbrlDataQuality
    reason: NotRequired[XbrlQueryReason]
```

- `project_xbrl_query_result`（行 366-406）唯一 `fact_count = len(returned_facts_copy)`（行 401）。✅
- Description metadata（行 284-324）自足满足字段、类型、必填性、枚举、optional reason 规则与最小示例。✅
- 七值 reason 的业务含义与安全下一动作矩阵完整（行 293-310）。✅
- 示例使用 `SEC_EDGAR`，不含 `sec_filing`。✅
- `fiscal_period` schema 从 `FISCAL_PERIODS` 派生 `FY|H1|Q1|Q2|Q3|Q4`。✅
- `min_value` / `max_value` 保持 JSON Schema `number`，S1 domain validator 显式拒绝 `bool`。✅

### 3.4 §5：R08-S1 Producer Contracts + All Actual Processors

**审查结果：PASS。**

- §5.1 allowlist 精确列出 12 个 production、3 个 test paths。✅
- §5.1 共享文件 symbol boundary：1 S1 fiscal node + 6 S2 normalize/dedup nodes + 2 generic nodes = 9 nodes。当前 `test_fins_read_runtime.py` 恰好含 9 个 test functions，与计划完全一致。✅
- §5.1 四个删除节点与九个 imports 明确列出且禁止恢复。已验证当前文件中零命中。✅
- §5.4 S1 中间 tree 定位为 "blocked intermediate evidence"，不是独立 validation/review gate。这个设计决定消除了原 plan 的 B1（collection failure）和 B2（coverage gate）blocker，是正确的 plan-level 修复。✅
- §5.6 S1→S2 累计 cutover：同一 tree 连续实施，不在 S1/S2 之间 stage/commit/review。✅

### 3.5 §6.1–§6.2：R08-S2 allowlist 与 Five Owner-Family Candidates

这是本次 correction 的核心新增段落。以下逐 candidate 做 adversarial 挑战。

---

#### Candidate 1：document-type/filter public projection

**Seam**：`FinsReadRuntime.list_documents`（`read_runtime.py:835`）

**执行路径验证**：
```
list_documents(ticker, document_types, fiscal_periods)
  -> _normalize_document_types(document_types)          # helpers:480
  -> _normalize_periods(fiscal_periods)                  # helpers:732
  -> _collect_source_documents -> resolve_document_type_for_source  # helpers:352
  -> _collect_available_document_types_for_source_documents
  -> return ListDocumentsResult with filters, suggestion
```

**Coverage 贡献**：`_normalize_document_types`（~30 lines）、`_normalize_periods`（~25 lines）、`_resolve_document_type`（~28 lines）、`resolve_document_type_for_source`（~23 lines）、`_normalize_json_scalar_text`（~18 lines）、`_normalize_form_type_for_matching`（~26 lines）、`_collect_available_document_types`（~30 lines）、`_collect_parent_titles`（~31 lines）。估计 ~210 lines 中的 ~120-150 可覆盖行。

**可执行性**：PASS。现有 `test_read_runtime_semantic_ownership_guards.py` 已使用 `build_fs_repository_set`、`FsBatchingRepository`、`CompanyMeta`、`DocumentMeta` 等真实仓储构造。`list_documents` 测试已有先例（`test_list_documents_uses_two_typed_storage_lists_without_per_document_snapshot`）。✅

**公共 seam 可达性**：`list_documents` 是 `FinsReadRuntime` 的 public method。✅

**风险**：`broaden_filter` suggestion 中的 `available_document_types` 列表顺序来自 repository 迭代顺序。计划要求"不得依赖 repository 返回顺序"——测试断言应使用 `set` 比较或 `sorted()` 而非 list equality。

**→ MEDIUM finding M1**：`broaden_filter` suggestion 的 `available_document_types` 顺序依赖未在 candidate 描述中明确处理。

---

#### Candidate 2：section public payload projection

**Seam**：`FinsReadRuntime.read_section`（`read_runtime.py:1011`）

**执行路径验证**：
```
read_section(ticker, document_id, ref)
  -> _read_section_with_borrow
    -> processor.read_section(normalized_ref)  # KeyError -> FinsReadArgumentError
    -> _normalize_section_children(section_raw.get("children"))  # helpers:700
    -> return SectionContentResult
```

**Coverage 贡献**：`_normalize_section_children`（~32 lines）。额外 coverage 来自 `read_section` 流程中的 `_extract_page_range`（~22 lines）、citation 构造与 section semantic resolution。

**可执行性**：PASS with caveat。需要 processor 实现 `read_section` 并返回含 `children` 的 `SectionContent`。现有 guard tests 有 `_FinancialStatementPayloadProcessor` 但无 `read_section` 实现——需要扩展 typed fixture 或使用真实 processor。✅

**未知 ref 的 typed failure**：计划要求"未知 `ref` 精确抛 `FinsReadArgumentError`"。代码路径（`read_runtime.py:1092-1112`）：processor 抛 `KeyError` → caught → re-raised as `FinsReadArgumentError`。因此 typed fixture 的 `read_section` 必须对未知 ref 抛 `KeyError`（不是其他异常），才能触发正确的 `FinsReadArgumentError` 包装。

**→ MEDIUM finding M2**：candidate 2 描述未明确 typed fixture 的 `read_section` 必须对未知 ref 抛 `KeyError`（以匹配 production 的 `KeyError → FinsReadArgumentError` 转换链）。若 fixture 抛其他异常类型，typed failure assertion 会匹配到错误的异常。

---

#### Candidate 3：table public payload projection

**Seam**：`FinsReadRuntime.get_table`（`read_runtime.py:1735`）

**执行路径验证**：
```
get_table(ticker, document_id, table_ref)
  -> _get_table_with_borrow
    -> processor.read_table(normalized_table_ref)  # KeyError -> FinsReadArgumentError
    -> _build_table_data_payload(table_raw)          # helpers:850
      -> _build_records_data_payload / _normalize_table_rows / _coerce_table_text
    -> _normalize_table_type(table_raw.get("table_type"))  # helpers:1052
    -> return TableDetailResult
```

**Coverage 贡献**：`_build_table_data_payload`（~60 lines）、`_build_records_data_payload`（~28 lines）、`_normalize_table_rows`（~33 lines）、`_normalize_table_columns`（~35 lines）、`_coerce_table_text`（~20 lines）、`_looks_like_markdown_table`（~26 lines）、`_normalize_table_type`（~51 lines）、`_to_optional_float`（~31 lines）。估计 ~284 lines 中的 ~150-200 可覆盖行——这是五个 candidate 中 coverage 贡献最大的单个 family。

**可执行性**：PASS with same `KeyError` caveat as M2。需要 processor 返回 records/markdown/plain text 三种 `data.kind` 的 table。✅

**风险**：计划说"typed fixture 只提供协议输入，不得成为被断言对象"。`get_table` 的 `_build_table_data_payload` 返回三种 shape（records/markdown/raw_text），测试只需断言 `data.kind` 和对应 exact keys/values，不验证 fixture 自身。✅

---

#### Candidate 4：XBRL taxonomy/default-concept selection

**Seam**：`FinsReadRuntime.query_xbrl_facts`（`read_runtime.py:2089`）

**执行路径验证**：
```
query_xbrl_facts(ticker, document_id)  # concepts 缺席
  -> _query_xbrl_facts_with_borrow
    -> form_type = self._resolve_document_form_type(borrow)  # read_runtime:2721 (private)
    -> taxonomy = _resolve_processor_taxonomy(processor)        # helpers:1103
      -> _normalize_taxonomy_name(processor.get_xbrl_taxonomy()) # helpers:1121
    -> resolved_concepts = _resolve_default_xbrl_concepts(       # helpers:1145
         form_type=form_type, taxonomy=taxonomy)
    -> processor.query_xbrl_facts(concepts=resolved_concepts, ...)
    -> _normalize_xbrl_query_payload -> return PublicXbrlQueryResult
```

**Coverage 贡献**：`_resolve_processor_taxonomy`（~17 lines）、`_normalize_taxonomy_name`（~23 lines）、`_resolve_default_xbrl_concepts`（~26 lines）。额外 coverage 来自 `query_xbrl_facts` 流程中的 normalization 路径。

**可执行性**：PASS。真实 `SecProcessor`（`sec_processor.py:787`）实现了 `get_xbrl_taxonomy()`，满足 `XbrlTaxonomyProcessor` Protocol（`read_runtime_helpers.py:1080`）。可使用 AAPL fixture + `SecProcessor` 或自定义 typed taxonomy-capable processor。✅

**关键约束验证**：
- "不得直接调用 `_normalize_taxonomy_name` 或 `_resolve_default_xbrl_concepts`"：public seam 满足——这两个 helper 由 `_query_xbrl_facts_with_borrow` 内部调用（行 2206-2210）。
- "不得断言 mapping 的内部遍历顺序"：`_resolve_default_xbrl_concepts` 返回 `list(matched)`——Python dict 的 `(form_type, taxonomy)` lookup 是 O(1) 而非遍历，无顺序依赖。
- "unknown taxonomy 必须走 global defaults"：`_resolve_default_xbrl_concepts` 在 `(form_type, taxonomy)` 不匹配且 taxonomy-only 不匹配时，fallback 到 `_GLOBAL_DEFAULT_XBRL_CONCEPTS`（行 1169）。✅

**→ LOW observation L1**：`_resolve_document_form_type` 是 `FinsReadRuntime` 的 private method（行 2721），测试无法直接控制其返回值。`form_type` 来自 borrowed snapshot 的文档元数据。测试必须通过真实文档元数据（而非 mock）驱动 taxonomy resolution——这与计划的 "typed fixture+真实 repository" 要求一致，但增加了 fixture 复杂度。

---

#### Candidate 5：search next-step public projection

**Seam**：`build_search_next_section_fields`（`read_runtime_helpers.py:573`）——唯一 module-helper 例外。

**执行路径验证**：
```
build_search_next_section_fields(matches, queries)
  -> 遍历 matches，按 section_ref 聚合 evidence_hit_count / _exact_match_count
  -> sorted(..., key=lambda: (-evidence_hit_count, -_exact_match_count, _first_index))
  -> _strip_search_section_internal_fields(ranked_sections[0])  # helpers:676
  -> return (next_section_to_read, next_section_by_query)
```

**Coverage 贡献**：`build_search_next_section_fields`（~101 lines）、`_strip_search_section_internal_fields`（~23 lines）。

**可执行性**：PASS。该函数是纯函数，接受 matches list 和 queries，返回 tuple。不需要 repository、processor 或 runtime。✅

**例外合理性验证**：`build_search_next_section_fields` 没有独立 public callable——`search_document` 内部调用它，但 `search_document` 的 public seam 会把检索/ranking owners 混入同一证据（计划 §6.1 已分析）。该例外不扩展到 private cache、snapshot internals、processor private method 或 Host private truncation state。✅

**禁止的断言模式**：
- "不得构造平手后断言 first-index 偶然顺序"：排序 key 的第三级是 `_first_index`（行 646）——平手时确实依赖 match 在原列表中的位置。测试应构造非平手 evidence（不同 `evidence_hit_count`），不依赖 `_first_index` tiebreaker。✅

---

### 3.6 §6.1 约束完整性审查

**审查结果：PASS with observations。**

| 约束 | 验证 |
|---|---|
| 不扩大 test path allowlist | `test_read_runtime_semantic_ownership_guards.py` 已在既有 S2 test allowlist 中（§6.1）。✅ |
| 四个删除节点/九 imports 不恢复 | §6.7F scan + SHA-256 lock 双重保证。✅ |
| 禁止 compatibility inputs | `availability`、`has_structured_financial_statements`、`has_financial_statement_sections`、`has_financial_statement`、`has_xbrl` 六项禁止。§6.7F scan 验证。✅ |
| 禁止 omnibus 改名搬运 | 每 candidate 单 owner family + exact node name + docstring。✅ |
| 禁止 fake-only | 每 candidate 要求真实 repository + public runtime。✅ |
| 禁止 private cache/processor/Host state | 前四项走 public seam，第五项是唯一 module-helper 例外。✅ |
| 禁止偶然顺序 | Candidate 1/4/5 均有明确的顺序独立性要求。✅ |
| 禁止 skip/xfail/pragma/omit | §8 stop conditions 明确。✅ |
| 增量 ledger 首次 >=80 停止 | §6.6 精确命令。✅ |
| 五候选耗尽仍 <80% 则 stop | §8 stop conditions 明确。✅ |

**→ LOW observation L2**：guards 文件当前已有 `_resolve_processor_taxonomy` import（行 52），§6.7F 的 AST import assertion 只约束"新增" import。本意是防止 candidate 实现绕过 public seam 直接 import private helpers。当前表述可能被误读为"零 import from helpers"。建议在 §6.7F 明确：pre-existing imports（`FinsReadBusinessError`、`_resolve_processor_taxonomy`）不在"新增"约束范围。

### 3.7 §6.3–§6.5：Input/Output Mapping、截断组合风险、累计 Tests

**审查结果：PASS。**

- §6.3 input/output mapping 表精确，禁止行为列完整。✅
- §6.4 Host truncation 组合风险裁决保留原 accepted plan 的 pre-Host 等式 + Host public cursor envelope + fetch-more remainder 三段验证。`fact_count` 仍由 Fins owner 持有，Host 不维护。✅
- §6.5 累计 owner/public tests 覆盖项与当前 `result_types.py`/`read_runtime_helpers.py` 实现一致。✅

### 3.8 §6.6：累计 S1+S2 Validation Gate

**审查结果：PASS。**

增量 ledger 的 step 0 基线 `320/494 = 64.78%` 与 Controller adjudication 和 S1 evidence 一致。coverage 收集命令从 repository root 运行，使用 `coverage json` + exact-key lookup——与 §6.6 原 15-file checker 完全同构。✅

"首次 `>=80.00` 立即停止" 的判定逻辑正确：
```python
decision = "STOP_ADDING_TESTS" if percent >= 80.0 else "CONTINUE_NEXT_OWNER_FAMILY"
```

**→ LOW observation L3**：coverage 在增量 ledger 中可能非单调——添加 node N+1 后 total statements 可能因 import 副作用微小变化。虽然极不可能导致 `percent` 下降，但若出现应 stop 回 Controller。当前 §8 已覆盖"新 stable-owner test 后任一 §6.6/§6.7 gate 失败"的情况。

### 3.9 §6.7：双向 Scans 与唯一同源证明

**审查结果：PASS。**

- §6.7A internal positive inventory scan：owner roots 精确。✅
- §6.7B public/tool/schema/serializer/LLM negative scan：roots 包含 `dayu/fins/tools`、`dayu/config/prompts`、README、tests。禁止 literal 列表完整。✅
- §6.7C `fact_count` 唯一 owner scan：roots 覆盖所有可能产生第二赋值的文件。✅
- §6.7D R07 no-touch propagation scan：以 `git diff -U0` 核验 `read_runtime.py`。✅
- §6.7E AST、README、security、scope scans：完整。✅
- §6.7F correction-specific scans：三组 scan（共享文件删除边界、compatibility/private-helper、AST import assertion）均已独立验证通过。✅

### 3.10 §6.8–§6.9：README 同步与 Review/Commit 边界

**审查结果：PASS。**

- §6.8 README 同步触发规则正确。✅
- §6.9 新的 gate sequence 精确：plan-only correction → Controller validation → MiMo+DS review → fix → re-review → accepted plan commit → test-only continuation → coverage ledger → full revalidation → new lock → code re-review → aggregate deepreview。✅
- 旧 hash/validation/reviews 全部标记失效。✅

### 3.11 §7–§10：Aggregate Deepreview、Stop Conditions、Checklist、自检

**审查结果：PASS。**

- §7 aggregate deepreview 覆盖项完整。✅
- §8 stop conditions 表覆盖所有已知失败模式。✅
- §9 code-generation handoff checklist 覆盖 S1/S2/aggregate 全部 gate。✅
- §10 本 gate 自检要求精确。✅

## 4. Findings

### M1 (MEDIUM) — Candidate 1 `broaden_filter` suggestion 的 `available_document_types` 顺序约束不明确

**证据**：
- `list_documents`（`read_runtime.py:924-931`）：当 `filtered_documents` 为空时，调用 `_collect_available_document_types_for_source_documents(base_documents)` 构造 `suggestion.available_document_types`。
- `base_documents` 来自 `_collect_source_documents`（行 875），其顺序由 repository 实现决定。
- 计划 candidate 1 说"不得依赖 repository 返回顺序"，但 `broaden_filter` suggestion 是 `list_documents` 的 public output 的一部分——测试必须断言其内容。

**Root owner**：candidate 1 的 test assertion 设计（属于 AgentCodex 后续 implementation）。

**精确修复方向**：在 candidate 1 描述或 §6.5 中明确：`available_document_types` 的断言应使用 `set()` 比较或 `sorted()` 包装，不得使用 list equality 断言顺序。

**严重性**：不影响 plan correctness。若 implementation 直接做 list equality，可能因 repository 返回顺序差异导致 flaky test。属于 implementation-level 注意事项，不是 plan 设计缺陷。

---

### M2 (MEDIUM) — Candidate 2/3 的 typed fixture 必须抛 `KeyError` 以匹配 production 异常转换链

**证据**：
- `_read_section_with_borrow`（`read_runtime.py:1092`）：`processor.read_section(normalized_ref)` 抛 `KeyError` → caught → re-raised as `FinsReadArgumentError("read_section", "ref", ...)`。
- `_get_table_with_borrow`（`read_runtime.py:1816`）：同样 `KeyError → FinsReadArgumentError` 转换。
- 计划 candidate 2 说"未知 `ref` 精确抛 `FinsReadArgumentError`"、candidate 3 说"未知 `table_ref` 精确抛 `FinsReadArgumentError`"。
- 若 typed fixture 的 `read_section`/`read_table` 抛 `ValueError`、`LookupError` 或其他异常，不会被 `except KeyError` 捕获，会以不同异常类型传播。

**Root owner**：candidate 2/3 的 typed fixture 设计（属于 AgentCodex 后续 implementation）。

**精确修复方向**：在 candidate 2 和 candidate 3 描述中补充：typed fixture 的 `read_section`/`read_table` 必须对未知 ref 抛 `KeyError`（不是其他异常类型），以匹配 `read_runtime.py` 中 `except KeyError as exc: raise FinsReadArgumentError(...) from exc` 的转换链。typed failure assertion 应使用 `pytest.raises(FinsReadArgumentError, match="...")`。

**严重性**：不影响 plan correctness。若 implementation 的 fixture 抛错异常类型，typed failure test 会失败——这是 implementation bug，不是 plan bug。

---

### L1 (LOW) — Candidate 4 的 `form_type` 不可直接控制

**观察**：`query_xbrl_facts` 中 `form_type` 来自 `self._resolve_document_form_type(borrow)`（`read_runtime.py:2721`，private method）。测试只能通过文档元数据间接影响 `form_type`，不能直接注入。这意味着测试 candidate 4 的 "unknown taxonomy → global defaults" 分支需要构造特殊文档元数据（例如非标准 form_type + unknown taxonomy 的 processor），增加了 fixture 复杂度。

**处理**：当前计划已要求 "typed taxonomy-capable processor 与明确 form/taxonomy business facts"，这已足够。本 observation 仅记录实现复杂度，不构成 plan 缺陷。

---

### L2 (LOW) — §6.7F AST import assertion 的 "新增" 限定词可能被误读

**观察**：§6.7F 说 "AST import assertion 必须证明相对 correction-entry tree 新增的 read_runtime_helpers.py production symbol import 为空"。guards 文件当前已有 `_resolve_processor_taxonomy` import（行 52）——这是 pre-existing import，不在 "新增" 约束范围。但若 reviewer 未注意到 "新增" 限定词，可能误判为违规。

**处理**：当前表述已足够精确。建议在 implementation 阶段明确列出 pre-existing imports 白名单。

---

### L3 (LOW) — Coverage 非单调性的理论风险

**观察**：增量 ledger 依赖 coverage 单调递增假设。在极边缘情况下（如 import 顺序变化导致模块级代码执行顺序改变），`num_statements` 可能微小变化。计划 §8 已覆盖 "新 stable-owner test 后任一 §6.6/§6.7 gate 失败" 的 stop condition，间接处理了此风险。

**处理**：无需修改计划。Implementation artifact 应记录每次增量 ledger 的 `num_statements` 值。

## 5. 正向验证汇总

| 验证项 | 方法 | 结果 |
|---|---|---|
| 五个 candidate 能经 public seam 执行到 `read_runtime_helpers.py` | 逐 candidate 追踪 `FinsReadRuntime` public method → internal call chain → helper function | 全部可执行 |
| typed fixture + 真实 repository 模式可行 | 现有 `test_read_runtime_semantic_ownership_guards.py` 已使用 `build_fs_repository_set` + typed processor fixtures | 基础设施完备 |
| typed failure 与当前 API 一致 | `FinsReadArgumentError`、`FinsReadBusinessError` 签名验证 | 一致 |
| 连续最短前缀 / 首次 80 停止可机械验证 | §6.6 增量 ledger 命令验证 | 机械可验证 |
| negative scans 无误伤 baseline | 独立运行 §6.7F 两组 scan，均 exit 1（零命中） | 无误伤 |
| 共享 `test_fins_read_runtime.py` boundary 保持 | SHA-256 lock + 删除边界 scan | 保持 |
| 无 omnibus/compat 搬运 | candidate 描述要求单 owner family + exact node name + docstring | 有 stop gate |
| 无 fake-only/private cache/processor/Host state | §6.1 硬边界 + §8 stop conditions | 有 stop gate |
| §6.6/§6.7 完整保留 | 命令矩阵、scans、checker 全部保留 | 完整保留 |
| R07 no-touch | §2.2 + §6.7D + §6.7E | 保留 |
| Host truncation owner | §6.4 forced-truncation 三段验证 | 保留 |
| security/deferred boundaries | §2.3 + §6.7E | 保留 |
| Topic 8-9 no-code | §2.3 + Controller adjudication §3 | 保留 |
| R09-R12 / Issues 142/151/175/177/178 deferred | §2.3 | 保留 |

## 6. Final Hash Re-Verification（写入本 artifact 后重算）

### 6.1 Corrected plan SHA-256

```bash
shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
```

Expected: `86bb76c768609451ca5f2de297f04f971832b719c6ca5a8b4a94d1617753fa65`

（本 artifact 写入不修改 plan，该值不变。）

### 6.2 Protected git diff SHA-256

```bash
git diff --binary -- dayu/fins tests | shasum -a 256
```

Expected: `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d`

（本 artifact 不属于 `dayu/fins` 或 `tests`，不进入该 diff。）

## 7. Handoff

**Verdict**：PLAN ACCEPTED WITH 2 MEDIUM FINDINGS, 3 LOW OBSERVATIONS。

两项 MEDIUM finding 是 implementation-level 注意事项（assertion 顺序策略、fixture 异常类型对齐），不是 plan 设计缺陷。三项 LOW observation 是文档清晰度与边界情况建议。

Corrected plan 可进入 Controller adjudication 与 AgentMiMo 并发 review。后续 accepted findings 修复后需重跑完整 §6.6/§6.7。

停止回 Controller。未修改 plan/product/tests/README/control/prior artifacts，未 commit/push/PR。
