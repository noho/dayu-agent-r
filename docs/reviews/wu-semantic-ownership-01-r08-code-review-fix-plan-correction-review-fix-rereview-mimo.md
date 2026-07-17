# WU-SEMANTIC-OWNERSHIP-01 R08 Corrected-Plan Re-Review — AgentMiMo

## 1. Review target and scope

| 项 | 值 |
|---|---|
| umbrella / sub-WU | 既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`；不是新 WU、feature 或 issue |
| review target | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`（corrected plan，含 `R08-CR-PCPR-F01` fix） |
| review scope | complete adversarial re-review of full final plan，覆盖所有段落而非仅 `R08-CR-PCPR-F01` delta |
| final plan SHA-256 | `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` — **PASS**（独立重算） |
| protected 23-path `dayu/fins + tests` binary diff SHA-256 | `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d` — **PASS**（独立重算） |
| staged tree | empty — **PASS** |
| `git diff --check` | exit 0，no output — **PASS** |
| `test_fins_read_runtime.py` SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` — **PASS** |
| guards correction-entry SHA-256 | `4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` — **PASS** |
| review verdict | **PASS / 0 material finding / 0 blocker** |

本 review 是对最终 corrected plan 全文的完整 adversarial re-review。Reviewer 不修改 plan、product、tests、control 或既有 artifacts。

## 2. Context artifacts read

- 根 `AGENTS.md`
- `docs/phaseflow-umbrella-optimization-control.md`
- `docs/fins/design.md`
- `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`（完整 final plan，1065 行）
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-mimo.md`（初始 MiMo review）
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-ds.md`（初始 DS review）
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-review-fix-controller-validation.md`
- `dayu/fins/tools/read_runtime.py`（`KeyError → FinsReadArgumentError` 转换链验证）
- `dayu/fins/tools/read_runtime_helpers.py`（`_collect_available_document_types` 使用 `set`+`sorted` 验证）
- `tests/fins/test_fins_read_runtime.py`（当前 9 节点、四节点/九 imports 删除确认）
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`（当前 15 节点与 import 清单）

## 3. Hash verification

### 3.1 Final plan SHA-256

```bash
shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
```

```text
a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02
```

与 Controller validation §2、Codex fix artifact §1 精确一致。**PASS**。

### 3.2 Protected 23-path binary diff SHA-256

```bash
git diff --binary -- dayu/fins tests | shasum -a 256
```

```text
7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d
```

与 Codex fix artifact §5、Controller validation §2 精确一致。**PASS**。

### 3.3 Additional protected hashes

| Hash | Expected | Actual | Status |
|---|---|---|---|
| `test_fins_read_runtime.py` SHA-256 | `01db5538...6692` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | **PASS** |
| guards correction-entry SHA-256 | `4a076ca6...1ff` | `4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` | **PASS** |
| staged paths | empty | empty | **PASS** |
| `git diff --check` | exit 0 | exit 0，no output | **PASS** |

## 4. `R08-CR-PCPR-F01` closure verification

Controller adjudication 裁决 `R08-CR-PCPR-F01`（ACCEPTED）要求：在 candidate 2/3 中明确 typed fixture 必须抛 `KeyError`，`FinsReadRuntime` public seam 拥有并投影 `FinsReadArgumentError`，测试只观察 public failure。

### 4.1 Production code evidence

直接读取 `dayu/fins/tools/read_runtime.py` 验证两处 `KeyError → FinsReadArgumentError` 转换链：

**Section path**（行 1088-1111）：
```python
try:
    section_raw: SectionContent = processor.read_section(normalized_ref)
except KeyError as exc:
    # ... diagnosis ...
    raise FinsReadArgumentError("read_section", "ref", normalized_ref, hint, ...)
```

**Table path**（行 1812-1835）：
```python
try:
    table_raw: TableContent = processor.read_table(normalized_table_ref)
except KeyError as exc:
    # ... diagnosis ...
    raise FinsReadArgumentError("get_table", "table_ref", normalized_table_ref, hint, ...)
```

两处都精确执行 `except KeyError as exc: raise FinsReadArgumentError(...) from exc` 转换。

### 4.2 Plan fix verification

Final plan §6.1 表中：

**Candidate 2**（行 524）现包含：
> "对于未知 `ref` 输入，typed fixture 的 `read_section` 必须抛 `KeyError`，再由 `FinsReadRuntime.read_section` public seam 精确转换为 `FinsReadArgumentError`；测试只观察该 public runtime failure，不直接断言 fixture 或其 `KeyError`。"

**Candidate 3**（行 525）现包含：
> "对于未知 `table_ref` 输入，typed fixture 的 `read_table` 必须抛 `KeyError`，再由 `FinsReadRuntime.get_table` public seam 精确转换为 `FinsReadArgumentError`；测试只观察该 public runtime failure，不直接断言 fixture 或其 `KeyError`。"

### 4.3 Closure verdict

| 要求 | 验证 |
|---|---|
| typed fixture 必须抛 `KeyError` | ✅ candidate 2/3 均明确 |
| `FinsReadRuntime` public seam 拥有并投影 `FinsReadArgumentError` | ✅ 与 production `except KeyError as exc: raise FinsReadArgumentError` 一致 |
| 测试只观察 public runtime failure | ✅ "不直接断言 fixture 或其 `KeyError`" |
| 五候选顺序/coverage/stop 未变 | ✅ 逐行比对确认 |
| DS M1/L1-L3 未被偷带 | ✅ 见 §5 |

**`R08-CR-PCPR-F01` CLOSED。**

## 5. DS rejected findings no-smuggle verification

### 5.1 DS M1 — `available_document_types` 顺序（REJECTED）

Controller adjudication §3.2 裁决 REJECTED，理由：`_collect_available_document_types` 使用 `set` 去重并 `return sorted(doc_types)`，public output 不继承 repository iteration order。

直接验证 `dayu/fins/tools/read_runtime_helpers.py:393`：

```python
def _collect_available_document_types(documents: list[Mapping[str, JsonValue]]) -> list[str]:
    doc_types: set[str] = set()
    # ...
    return sorted(doc_types)
```

确认 `set` + `sorted`，canonical order 已由 production owner 承诺。Candidate 1（行 523）"不得依赖 repository 返回顺序"与 owner 实现一致。**未被偷带。**

### 5.2 DS L1 — candidate 4 form type 间接驱动（REJECTED）

Controller adjudication §3.4 裁决 REJECTED AS ALREADY COVERED。计划已要求通过真实 document metadata 与 typed taxonomy-capable processor 提供 form/taxonomy business facts。

Final plan candidate 4（行 526）："用 typed taxonomy-capable processor 与明确 form/taxonomy business facts"。**未被偷带。**

### 5.3 DS L2 — AST import assertion "新增" 限定（REJECTED）

Controller adjudication §3.5 裁决 REJECTED AS ALREADY PRECISE。§6.7F 明确比较 correction-entry tree 的"新增" imports。

Final plan §6.7F（行 914-919）："AST import assertion 必须证明相对 correction-entry tree 新增的 `read_runtime_helpers.py` production symbol import 为空；只有确实执行到 §6.1 第 5 个候选时，才允许它精确等于 `{build_search_next_section_fields}`。"

Pre-existing imports（`FinsReadBusinessError`、`_resolve_processor_taxonomy`）在 guards 文件中已存在（行 51-52），不属于增量集合。**未被偷带。**

### 5.4 DS L3 — coverage 非单调理论风险（REJECTED）

Controller adjudication §3.6 裁决 REJECTED AS ALREADY CLOSED BY MECHANICAL LEDGER/STOP。§6.6 逐步记录 `covered / statements / percent / decision`，§8 要求任何 gate 失败即停回 Controller。

Final plan §6.6（行 696-699）保留完整增量 ledger 与 stop condition。**未被偷带。**

## 6. 五候选可执行性挑战

### 6.1 Candidate 1：document-type/filter public projection

**Seam**：`FinsReadRuntime.list_documents`（`read_runtime.py:835`）

**执行路径**：
```
list_documents(ticker, document_types, fiscal_periods)
  → _normalize_document_types(document_types)          # helpers:480
  → _normalize_periods(fiscal_periods)                  # helpers:732
  → resolve_document_type_for_source(...)               # helpers:352
  → _collect_available_document_types_for_source_documents
  → return ListDocumentsResult with filters, suggestion
```

**Coverage 贡献**：`_normalize_document_types`（~30 lines）、`_normalize_periods`（~25 lines）、`_resolve_document_type`（~28 lines）、`resolve_document_type_for_source`（~23 lines）、`_collect_available_document_types`（~30 lines）。

**Public seam 可达性**：`list_documents` 是 `FinsReadRuntime` public method。✅

**Repository-order independence**：`_collect_available_document_types` 使用 `set` + `sorted`，canonical order 已由 owner 承诺。✅

**Verdict：PASS。**

### 6.2 Candidate 2：section public payload projection

**Seam**：`FinsReadRuntime.read_section`（`read_runtime.py:1011`）

**执行路径**：
```
read_section(ticker, document_id, ref)
  → processor.read_section(normalized_ref)  # KeyError → FinsReadArgumentError
  → _normalize_section_children(section_raw.get("children"))
  → return SectionContentResult
```

**Coverage 贡献**：`_normalize_section_children`（~32 lines）、`_extract_page_range`（~22 lines）。

**KeyError → FinsReadArgumentError**：production 行 1092-1111 确认转换链。Plan candidate 2 明确 typed fixture 抛 `KeyError`，runtime 投影 `FinsReadArgumentError`，test 只观察 public failure。✅

**Verdict：PASS。**

### 6.3 Candidate 3：table public payload projection

**Seam**：`FinsReadRuntime.get_table`（`read_runtime.py:1735`）

**执行路径**：
```
get_table(ticker, document_id, table_ref)
  → processor.read_table(normalized_table_ref)  # KeyError → FinsReadArgumentError
  → _build_table_data_payload(table_raw)
  → _normalize_table_type(table_raw.get("table_type"))
  → return TableDetailResult
```

**Coverage 贡献**：`_build_table_data_payload`（~60 lines）、`_build_records_data_payload`（~28 lines）、`_normalize_table_rows`（~33 lines）、`_normalize_table_columns`（~35 lines）、`_coerce_table_text`（~20 lines）、`_looks_like_markdown_table`（~26 lines）、`_normalize_table_type`（~51 lines）——单个 family 中 coverage 贡献最大。

**KeyError → FinsReadArgumentError**：production 行 1816-1835 确认转换链。Plan candidate 3 明确与 candidate 2 相同的责任分离。✅

**Verdict：PASS。**

### 6.4 Candidate 4：XBRL taxonomy/default-concept selection

**Seam**：`FinsReadRuntime.query_xbrl_facts`（`read_runtime.py:2089`）

**执行路径**：
```
query_xbrl_facts(ticker, document_id)  # concepts 缺席
  → _resolve_document_form_type(borrow)       # private method, from doc metadata
  → _resolve_processor_taxonomy(processor)     # helpers:1103
  → _normalize_taxonomy_name(...)              # helpers:1121
  → _resolve_default_xbrl_concepts(...)        # helpers:1145
  → processor.query_xbrl_facts(concepts=resolved_concepts, ...)
```

**Coverage 贡献**：`_resolve_processor_taxonomy`（~17 lines）、`_normalize_taxonomy_name`（~23 lines）、`_resolve_default_xbrl_concepts`（~26 lines）。

**Public seam 可达性**：`query_xbrl_facts` 是 `FinsReadRuntime` public method。`_resolve_default_xbrl_concepts` 由 runtime 内部调用，不直接暴露。✅

**Verdict：PASS。**

### 6.5 Candidate 5：search next-step public projection

**Seam**：`build_search_next_section_fields`（`read_runtime_helpers.py:573`）——唯一 module-helper 例外。

**执行路径**：
```
build_search_next_section_fields(matches, queries)
  → 遍历 matches，按 section_ref 聚合 evidence_hit_count / _exact_match_count
  → sorted(..., key=lambda: (-evidence_hit_count, -_exact_match_count, _first_index))
  → _strip_search_section_internal_fields(ranked_sections[0])
  → return (next_section_to_read, next_section_by_query)
```

**Coverage 贡献**：`build_search_next_section_fields`（~101 lines）、`_strip_search_section_internal_fields`（~23 lines）。

**例外合理性**：next-step projection 没有独立 public callable；`search_document` 内部调用它但会把检索/ranking owners 混入同一证据。✅

**Tiebreaker 独立性**：计划要求"不得构造平手后断言 first-index 偶然顺序"。排序 key 第三级是 `_first_index`——测试应构造非平手 evidence。✅

**Verdict：PASS。**

### 6.6 Coverage 数学验证

当前基线：`320/494 = 64.78%`。需达到 `396/494 = 80.16%`（≥76 条新增语句）。

| family | 目标函数 | 保守覆盖估计 |
|---|---|---|
| 1 | `_normalize_document_types` + `_normalize_periods` + `_resolve_document_type` + `_collect_available_document_types` + ... | ~28-35 |
| 2 | `_normalize_section_children` + `_extract_page_range` + `_collect_parent_titles` | ~12-15 |
| 3 | `_build_table_data_payload` + `_normalize_table_rows` + `_normalize_table_columns` + `_coerce_table_text` + `_looks_like_markdown_table` + `_normalize_table_type` | ~30-40 |
| 4 | `_resolve_default_xbrl_concepts` + `_normalize_taxonomy_name` + `_normalize_xbrl_query_payload` + ... | ~35-46 |
| 5 | `build_search_next_section_fields` + `_strip_search_section_internal_fields` | ~7 |

前三个 family 联合保守估计 ~70-90 条新增语句，已超过 76 条阈值。五个 family 全部耗尽仍低于 80% 的概率极低。Plan §6.6/§8 的 stop condition 设计合理。

## 7. 连续最短前缀 / 首次 80 停止挑战

**增量 ledger 机制**（§6.6，行 665-699）：

1. Step 0：固定记录基线 `320/494 = 64.78%`。
2. 逐 node 增量：每次只新增一个 exact node，运行完整 coverage 集。
3. 机械判定：inline Python checker 输出 `STOP_ADDING_TESTS` 或 `CONTINUE_NEXT_OWNER_FAMILY`。
4. 首次过线即停：percent 首次 `>=80.00` 立即停止。
5. 五候选耗尽仍不过线：stop 回 Controller。

**实现 artifact 要求**：逐 node 记录 `step / exact node / public seam / covered / statements / percent / decision`。

**§6.7F AST node assertion**：必须证明实际新增 tests 精确等于候选表的连续最短前缀。

**验证**：§6.6 checker 代码（行 681-693）精确实现 `percent >= 80.0` 判定。§8 stop conditions 表（行 991）明确"增量 ledger 首次达到 `read_runtime_helpers.py >=80.00%` → 立即停止新增 owner family"。§8 还明确"五个授权 owner family 仍低于 80% → 记录逐步 ledger 并 stop 回 Controller"。

**Verdict：PASS — 机械可验证，stop conditions 完整。**

## 8. 完整 §6.6 / §6.7 验证

### 8.1 §6.6 累计 validation gate

| 子项 | 验证 |
|---|---|
| 增量 ledger step 0 基线 | `320/494 = 64.78%`，与 Controller adjudication 一致 ✅ |
| 增量 coverage 收集命令 | 从 repository root 运行，8 个测试文件全集 ✅ |
| 逐 node 机械判定 | inline Python checker 精确实现 ✅ |
| 首次阈值后清空并完整重跑 | §6.6 明确"先 `coverage erase`，再从头完整执行" ✅ |
| S1 focused owner matrix | `pytest ... -k 'financial or statement or xbrl or quality or reason or fiscal'` ✅ |
| S2 focused/public matrix | 6 个测试文件 ✅ |
| 三段 forced-truncation public chain | `test_fins_read_aapl_xbrl_query_separates_pre_host_value_from_host_truncation` ✅ |
| AAPL/HTML/no-statement real smokes | 3 个 spawned-child/failed-outcome nodes ✅ |
| R08 aggregate matrix + full Fins regression | 8 个测试文件 + `pytest tests/fins -q` ✅ |
| 累计 coverage run + exact-key 15-file checker | 从 repository root 运行，NUL-safe manifest ✅ |
| full pyright | §6.6 明确 ✅ |
| NUL-safe changed Python Ruff manifest | `git diff --name-only -z` + Ruff ✅ |
| `git diff --check` | §6.6 明确 ✅ |

### 8.2 §6.7 双向 scans

| Scan | 验证 |
|---|---|
| A. Internal positive inventory | owner roots 精确 ✅ |
| B. Public/tool/schema/serializer/LLM negative scan | 禁止 literal 列表完整 ✅ |
| C. `fact_count` 唯一 owner scan | roots 覆盖所有可能产生第二赋值的文件 ✅ |
| D. R07 no-touch propagation scan | `git diff -U0` 核验 ✅ |
| E. AST、README、security、scope scan | 完整 ✅ |
| F. `R08-CR-PCF01` correction-specific source/AST scans | 三组 scan 完整 ✅ |

### 8.3 §6.7F specific scans

**共享文件删除边界 scan**（`test_fins_read_runtime.py`）：

```bash
rg -n 'test_read_helper_document_discovery_rules_preserve_public_semantics|...' tests/fins/test_fins_read_runtime.py
```

独立运行结果：exit 1，零命中。**PASS。**

**Compatibility/private-helper negative scan**（`test_read_runtime_semantic_ownership_guards.py`）：

```bash
rg -n 'availability|has_structured_financial_statements|...' tests/fins/test_read_runtime_semantic_ownership_guards.py
```

独立运行结果：exit 1，零命中。**PASS。**

**§6.7F completeness：PASS。**

## 9. 共享文件 boundary 挑战

### 9.1 `test_fins_read_runtime.py`

- **文件 SHA-256**：`01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` ✅
- **节点数**：恰好 9 个（2 generic + 6 normalize/dedup + 1 fiscal）✅
- **四节点删除确认**：rg scan 零命中 ✅
- **九 imports 删除确认**：rg scan 零命中 ✅
- **generic LRU/form-matching AST**：Codex artifact 证明零变化 ✅
- **§5.1 boundary 精确列出**：plan 行 379-401 ✅

### 9.2 `test_read_runtime_semantic_ownership_guards.py`

- **Correction-entry SHA-256**：`4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` ✅
- **当前节点数**：15 个 ✅
- **Compatibility scan**：零命中 ✅
- **Pre-existing imports**：`FinsReadBusinessError`、`_resolve_processor_taxonomy`（行 51-52），不在"新增"约束范围 ✅

### 9.3 Omnibus 搬运检查

| 原节点（已删） | 新 family | 本质区别 |
|---|---|---|
| `test_read_helper_document_discovery_rules_preserve_public_semantics` | Family 1: document-type/filter | 原断言 compatibility availability；新断言 document_types/fiscal_periods 过滤 |
| `test_search_next_section_owner_ranks_exact_hits_per_query` | Family 5: search next-step | 原在 shared file；新在 guards file 且不同 assertions |
| `test_table_data_projection_owner_emits_self_describing_shapes` | Family 3: table payload | 原通过 private helper；新通过 public get_table |
| `test_navigation_and_xbrl_default_rule_owners_fail_closed` | Family 4: XBRL taxonomy | 原混合多个 owner；新单一 owner |

**Verdict：PASS — 无搬运。**

## 10. R07/Host truncation/security/deferred no-drift 验证

| 维度 | 验证 |
|---|---|
| R07 snapshot acquire/borrow/release | §2.2 + §6.7D ✅ |
| R07 cache revision | §2.2 + §6.7D ✅ |
| R07 citation generation | §2.2 + §6.7D ✅ |
| R07 source-changed paths | §2.2 + §6.7D ✅ |
| Host truncation/fetch-more composition owner | §6.4 三段 forced-truncation 验证 ✅ |
| filesystem containment/symlink | §6.7E retained-security scan ✅ |
| atomic publication/recovery | §6.7E retained-security scan ✅ |
| unified tool authorization | §2.3 out-of-scope ✅ |
| R09-R12 | §2.3 out-of-scope ✅ |
| Issues 142/151/175/177/178 | §2.3 out-of-scope ✅ |
| §4 product contracts | 零变化（初始 MiMo review §7 已确认，本 re-review 再次确认） ✅ |
| S1/S2 path allowlists | 未扩大 ✅ |

**Verdict：PASS — 全部 no-drift。**

## 11. 补充 adversarial 挑战

### 11.1 Candidate 2/3 的 `FinsReadArgumentError` 是否会被 `FinsReadBusinessError` 干扰？

`FinsReadArgumentError` 是 `FinsReadBusinessError` 的子类（`read_runtime_helpers.py:166`）。测试使用 `pytest.raises(FinsReadArgumentError)` 而非 `FinsReadBusinessError`，精确匹配失败类型。✅

### 11.2 Candidate 1 的 `broaden_filter` suggestion 是否包含不可控顺序？

已验证 `_collect_available_document_types` 使用 `set` + `sorted`。`ListDocumentsResult.suggestion.available_document_types` 的顺序由 owner 承诺为字母序。✅

### 11.3 Candidate 4 的 `form_type` 间接驱动是否导致 fixture 不可构造？

`_resolve_document_form_type` 是 `FinsReadRuntime` private method，从 borrowed snapshot 的文档元数据获取 `form_type`。测试通过真实 repository 创建具有特定 `form_type` 的 source document，间接控制 taxonomy resolution。这与 plan 的"真实 document metadata + typed taxonomy-capable processor"要求一致。✅

### 11.4 §6.6 incremental coverage 的 `num_statements` 微变是否影响判定？

§8 已覆盖"新 stable-owner test 后任一 §6.6/§6.7 gate 失败 → stop 回 Controller"。若 `num_statements` 微变导致 `percent` 下降，属于 gate 失败，触发 stop。无需额外保护。✅

### 11.5 Candidate 5 `build_search_next_section_fields` 直接调用是否破坏 public/private 边界？

Plan 明确这是"唯一 module-helper 例外"，理由是 next-step projection 没有独立 public callable。该例外不扩展到 private cache、snapshot internals、processor private method 或 Host private truncation state。§6.7F 的 AST import assertion 限制只有进入 candidate 5 时才可新增 `build_search_next_section_fields` import。✅

## 12. `R08-CR-PCF01` closure 逐项确认

| 要求（来自 Controller adjudication §3） | 计划落点 | 验证 |
|---|---|---|
| 保留共享文件固定 symbol boundary 与删除结果 | §2.1、§5.1、§6.7F、§9 | PASS — 四节点/九 imports 不恢复，SHA 锁定 |
| 保留 15-file whole-file exact-key 80% 与完整 §6.6/§6.7 | §6.6、§6.7、§7、§9 | PASS — 完整 validation 命令保留 |
| 只在既有 guards path 授权 split stable-owner tests | §3.4、§6.1、§6.5 | PASS — 不扩 test path allowlist |
| 每 family 给出 exact node、business I/O/failure 与 seam | §6.1 | PASS — 五列表格精确给出 |
| public seam 优先、唯一 module-helper 例外 | §6.1 | PASS — 前四走 public，第 5 是唯一例外 |
| 禁止 compatibility/omnibus/private/fake/empty/skip/coverage bypass | §6.1、§6.6、§6.7F、§8、§9 | PASS — 多处明确禁止 |
| 增量 ledger 首次过线即停，再完整重验证 | §6.2、§6.6、§8、§9 | PASS — 机械 ledger + stop condition |
| 旧 hash/validation/reviews 失效并更新 aggregate handoff | §6.7F、§6.9、§7、§9 | PASS — §6.9 完整更新 handoff 序列 |
| `R08-CR-PCPR-F01` candidate 2: typed fixture 抛 `KeyError` + runtime 投影 `FinsReadArgumentError` | §6.1 candidate 2 | PASS — 与 production 行 1092-1111 一致 |
| `R08-CR-PCPR-F01` candidate 3: 同上 table path | §6.1 candidate 3 | PASS — 与 production 行 1816-1835 一致 |
| DS M1 not smuggled | candidate 1 | PASS — `_collect_available_document_types` 使用 `set`+`sorted` |
| DS L1-L3 not smuggled | §6.1、§6.7F、§6.6、§8 | PASS — 未增加 private injection、白名单或新假设 |

## 13. Verdict

**PASS / 0 material finding / 0 blocker。**

Final corrected plan 已 code-generation-ready：

1. `R08-CR-PCPR-F01` 精确闭合：typed fixture 对未知 section/table ref 产生 `KeyError`，public `FinsReadRuntime` 唯一投影 `FinsReadArgumentError`，测试只观察 public failure。与 production `except KeyError as exc: raise FinsReadArgumentError(...)` 转换链完全一致。
2. DS M1（`available_document_types` 顺序）未被偷带：production owner 使用 `set`+`sorted` 提供 canonical order。
3. DS L1-L3 未被偷带：未增加 private form injection、pre-existing import 白名单或新 coverage 假设。
4. 五个 candidate 全部确认可通过指定 public seam / module-helper 执行，coverage 数学上可达到 80%。
5. 连续最短前缀 / 首次 80 停止可机械验证，stop conditions 完整。
6. 完整 §6.6/§6.7 保留，包括增量 ledger、15-file checker、六类双向 scans、§6.7F correction-specific scans。
7. 共享 `test_fins_read_runtime.py` boundary 三重保障（SHA + scan + AST）。
8. 无 omnibus 搬运、fake-only、private state、偶然顺序。
9. R07 no-touch、Host truncation owner、retained security、R09-R12/Issues deferred boundaries 全部保留。
10. §4 product contracts、S1/S2 path allowlists 均未改变。

Reviewer 不修改 plan、product、tests、control 或既有 artifacts。停止回 Controller。
