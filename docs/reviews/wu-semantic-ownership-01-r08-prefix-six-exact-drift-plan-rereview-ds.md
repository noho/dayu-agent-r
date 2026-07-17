# WU-SEMANTIC-OWNERSHIP-01 / R08 prefix-six exact-drift fixed plan — Complete Re-Review (AgentDS)

## 1. Verdict

`PASS / ALL_FIVE_ACCEPTED_FINDINGS_CLOSED / ZERO_NEW_MATERIAL_FINDING / READY_FOR_ACCEPTED_PLAN_COMMIT`

本 artifact 是对 fixed plan SHA-256 `0253e626d81aa46b3b987f8acf93487e03a7b031530ad10a9402537d91c64521` 的完整、独立、adversarial re-review。审查覆盖整份 fixed plan（1287 行），不是只看 fix patch。Reviewer verdict 不授权 implementation。

## 2. Review scope 与方法

### 2.1 审查范围

完整 fixed plan `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`，以及以下关联 artifacts：

- `AGENTS.md`
- `docs/host/issues-implementation-control.md`（R08 相关章节）
- `docs/phaseflow-umbrella-optimization-control.md`
- `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
- `docs/fins/design.md`
- 初审两路 artifacts：`wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-mimo.md`、`wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-ds.md`
- Controller adjudication：`wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-controller-adjudication.md`
- AgentCodex fix artifact：`wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-fix-codex.md`
- Controller validation：`wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-fix-controller-validation.md`
- S1/S2 implementation artifacts

### 2.2 审查方法

独立验证、不依赖任何 prior reviewer verdict、不信任 plan 自报值。逐项执行：

1. 独立重算全部 SHA-256 locks
2. 独立逐项验证 `R08-CR-PCPR-F01..F05` 在 fixed plan 中的 closure
3. 独立 source/AST 验证 candidate 6、dead helper deletion、actual owner、shared test 删除边界
4. 独立重算 391/485 arithmetic
5. 独立审计 [344,346,348,442] root evidence 链
6. 独立审计 mutation-before prefix-five predecessor provenance
7. 重新挑战全部 15 个 adversarial dimensions
8. 不重新包装已裁决/已拒绝事项

## 3. SHA-256 lock 独立验证

所有 lock 由 reviewer 在本地独立计算（非复制 plan 自报值）：

| Lock | Plan/Fix 声称值 | Reviewer 独立计算值 | 匹配 |
|---|---|---|---|
| Fixed plan | `0253e626d81aa46b3b987f8acf93487e03a7b031530ad10a9402537d91c64521` | `0253e626d81aa46b3b987f8acf93487e03a7b031530ad10a9402537d91c64521` | ✅ |
| Cumulative `dayu/fins + tests` binary diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` | ✅ |
| S1+S2 cumulative `read_runtime_helpers.py` content state（含 dead-helper deletion 与 public projection/normalization） | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` | ✅ |
| Actual-owner `read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` | ✅ |
| Candidate 6 guards | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` | ✅ |
| Shared test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | ✅ |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` | ✅ |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` | ✅ |
| Staged tree | empty | empty (SHA of empty = `e3b0c44...b855`) | ✅ |
| `git diff --check` | PASS | PASS | ✅ |

全部 10 项 lock 独立验证通过。

## 4. Finding closure ledger — R08-CR-PCPR-F01..F05

### 4.1 F01: 六个 shared-test name 从 stale 更新为 exact

**Fixed plan 状态**：`CLOSED`

**独立验证**：

Plan §5.1（lines 384-385）当前 shared-test symbol boundary 引用精确为：

```text
test_xbrl_query_payload_missing_facts_fails_closed
test_xbrl_query_payload_rejects_non_flat_query_params
test_xbrl_query_payload_preserves_raw_input_during_normalization
test_xbrl_query_payload_stable_dedup_projects_unique_fact_count
test_xbrl_query_payload_preserves_owner_quality_and_optional_reason
test_xbrl_query_payload_zero_hit_has_single_count_and_no_reason
```

Reviewer 独立 grep 确认 locked `tests/fins/test_fins_read_runtime.py`（SHA `01db5538...6692`）中的六个对应 nodes 精确为上述六名（lines 98, 125, 153, 198, 252, 285）。旧 `total`/dedup-era stale 名称（如 `test_xbrl_query_payload_missing_total_fails_closed`）在 plan 全文中零命中。

**Closure evidence**：六个 exact names 同时出现在 plan §5.1 与 locked shared file；plan 未改 tests、未恢复 `total`/`deduped_fact_count` 或 compatibility semantics。✅

### 4.2 F02: single-file prefix proof 与 15-file full acceptance 显式区分

**Fixed plan 状态**：`CLOSED`

**独立验证**：

Plan §1 item 9 明确陈述：

> `387/485 -> 391/485` prefix proof 只关闭 `dayu/fins/tools/read_runtime_helpers.py` 单文件 80% gap；全部 15 个 changed production files 的 coverage 由累计 S1+S2 owner tests、public projection tests 与 real smokes 共同提供，唯一验收真源是 §6.6 fresh exact-key checker。

Plan §6.6（lines 715-720）重复此区分并明确 prefix proof 不替代 15-file acceptance。

**Closure evidence**：两处显式区分、未弱化 `>=80.00%` 或 `first/shortest`、未将 prefix proof 声明为 full-acceptance substitute。✅

### 4.3 F03: §6.2 items 1-7 已完成标记、时态消除

**Fixed plan 状态**：`CLOSED`

**独立验证**：

Plan §6.2 items 1-7 全部以 "已完成于 stopped tree：" 开头（lines 613-620），明确描述当前 cumulative diff `e40de2a0...33f` 的受保护累计状态。Item 8 以 "Current verification action：" 开头，明确区分待执行的 verification。Plan §6.1 明确：

> 当前 stopped tree 的累计 diff `e40de2a0...33f` 已包含完整 S1+S2、dead-helper deletion 与 candidate 6；§6.2 items 1-7 是已完成且受保护的累计状态，不是待重复实施的指令。只有 §6.2 item 8 与 §6.6/§6.7 是本 continuation 的 current verification actions。

**Closure evidence**：全部 7 项标记为已完成、item 8 标记为 current verification、§6.1 有时序说明、无残存未来/祈使语气。✅

### 4.4 F04: §7 historical baseline provenance 精确标注

**Fixed plan 状态**：`CLOSED`

**独立验证**：

Plan §7（lines 1168-1170）当前明确：

> 以下 baseline 来自较早且不同 tree state 的 S2 artifact `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648`，只作历史数量级与继承问题参考，不是 current expected result；current exact results 只由 §6.6 fresh validation 产生。

**Closure evidence**：标注了 artifact SHA、不同 tree state、仅作历史参考；明确当前真源是 §6.6 fresh validation。✅

### 4.5 F05: helper cumulative content-state label 语义范围修正

**Fixed plan 状态**：`CLOSED`

**独立验证**：

Plan §0 table、§6.1、§6.7.G、§9 checklist、§10 self-check 全部使用统一标签：

> S1+S2 cumulative `read_runtime_helpers.py` content state（含 dead-helper deletion 与 public projection/normalization）

Hash 值 `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` 不变。历史 root-cause 叙述中保留对 deletion 事件的准确描述，但 lock label 不再局限于 "deletion 后"。

**Closure evidence**：全文 label 统一、hash 不变、历史叙述保留但不污染 lock semantics。✅

## 5. R08-CR-PCF04 retained implementation finding 验证

Plan §0 将 `R08-CR-PCF04` 作为 retained implementation finding，声明：

1. Candidate 6 已存在且正确，保留唯一 public-owner import/test 与三条断言
2. Fresh JSON 证明 candidate 6 相对 prefix-five 新覆盖 `[344, 346, 348, 442]` 四行
3. Prefix-six exact truth = `391/485 = 80.61855670%`

**独立验证**：

- Guards 文件中 `resolve_document_type_for_source` 唯一 import 在 line 57 ✅
- Candidate 6 `test_document_type_resolver_projects_material_other_and_cn_categories` 在 line 1955 ✅
- 三条 assertions：`"UNLISTED_MATERIAL" + MATERIAL → "material"`、`None + FILING → "other"`、`"FY" + FILING → "annual_report"` ✅
- 完整中文 docstring（Args/Returns/Raises）✅
- 无 `_resolve_document_type`、mapping constant、fake repository、monkeypatch、compat input ✅
- 算术：387（prefix-five covered）+ 4（candidate 6 new）= 391；391/485 = 80.61855670% ✅

**结论**：Retained finding 正确；candidate 6 不变、不新增第七项、不修改 production。

## 6. Independent source/AST verification

### 6.1 Dead helper deletion

```bash
rg -n '\b_collect_available_document_types\b' dayu/ tests/
# exit: 1 — 零命中
```

旧 helper 在 `dayu/` 与 `tests/` 全仓 definition/caller/import 均为零。Actual owner `_collect_available_document_types_for_source_documents` 不受 word-boundary pattern 影响。✅

### 6.2 Actual owner proof

`dayu/fins/tools/read_runtime.py` line 705: `def _collect_available_document_types_for_source_documents`，输入签名 `list[_SourceDocumentSummary]`，返回签名 `list[str]`，内部调用 `resolve_document_type_for_source` 并 `return sorted(doc_types)`。✅

### 6.3 Deleted nodes/imports in shared test

```bash
rg -n 'test_read_helper_document_discovery|test_search_next_section_owner|test_table_data_projection_owner|test_navigation_and_xbrl_default_rule|_build_table_data_payload|_normalize_document_types|_normalize_periods|_normalize_section_children|_normalize_taxonomy_name|_resolve_default_xbrl_concepts|build_search_next_section_fields|resolve_has_financial_data' tests/fins/test_fins_read_runtime.py
# exit: 1 — 零命中
```

四个已删除越界 nodes 与九个专用 imports 全部零命中。Generic LRU (line 50) 与 form-matching (line 80) nodes 保留。✅

### 6.4 Internal reason/locator deletion

```bash
rg -n 'statement_locator|StatementLocator|statement_method_missing|statement_empty|processor_error:|invalid_statement_result' \
  dayu/fins/domain/financial_result_contract.py dayu/fins/processors/ dayu/fins/pipelines/sec_fiscal_fields.py \
  tests/fins/test_financial_read_contracts.py tests/fins/test_sec_pipeline_download.py
# exit: 1 — 零命中
```

Producer domain、全部 processors、pipelines 与对应 tests 中旧 locator/reason 符号全部删除。✅

### 6.5 XBRL total/raw count deletion

```bash
rg -n 'raw_total|provider_total|reported_total|"total"' \
  dayu/fins/domain/xbrl_result_contract.py dayu/fins/processors/sec_processor.py \
  dayu/fins/processors/bs_report_form_common.py dayu/fins/processors/bs_six_k_processor.py \
  dayu/fins/processors/sec_xbrl_query.py dayu/fins/pipelines/sec_fiscal_fields.py
# exit: 1 — 零命中
```

Producer domain 与全部 actual processor 中旧 total/count 字段全部删除。✅

### 6.6 deduped_fact_count deletion

```bash
rg -n 'deduped_fact_count|deduped_count' dayu/fins/tools/ tests/fins/
# exit: 1 — 零命中
```

Public tools 层与 tests 中旧 dedup count 全部删除。✅

### 6.7 fact_count single owner

```bash
rg -n 'fact_count' dayu/fins/tools/result_types.py dayu/fins/tools/read_runtime_helpers.py \
  dayu/fins/tools/read_runtime.py dayu/fins/tools/fins_tools.py
```

结果：
- `result_types.py:279` — `PublicXbrlQueryResult` TypedDict 字段定义
- `result_types.py:314` — description metadata 文档
- `result_types.py:323` — 最小 JSON 示例
- `result_types.py:401` — builder 唯一赋值 `fact_count=len(returned_facts_copy)`

`read_runtime_helpers.py`、`read_runtime.py`、`fins_tools.py` 中零 `fact_count` 赋值/重算。✅

### 6.8 Old tools type names

`result_types.py` 中仅定义 `PublicFinancialStatementResult` (line 250) 与 `PublicXbrlQueryResult` (line 271)。旧 `FinancialStatementResult` / `XbrlQueryResult` 类定义已删除。Domain producer 类型通过 alias import（`ProducerFinancialStatementResult` / `ProcessorFinancialStatementResult`）消费，不是 public re-export。✅

### 6.9 sec_filing in LLM-facing content

```bash
rg -n 'sec_filing' dayu/fins/tools/result_types.py dayu/fins/tools/fins_tools.py \
  dayu/config/prompts/ tests/fins/test_fins_storage_provider.py
# exit: 1 — 零命中
```

LLM-facing tools 与 prompt 中旧 provider alias 全部删除。✅

## 7. Adversarial re-challenge — 全部 15 dimensions

### 7.1 391/485 exact arithmetic

**独立验算**：387 ÷ 485 = 0.7979381443... → 79.79381443%；391 ÷ 485 = 0.8061855670... → 80.61855670%。

Checker（§6.6 Python script）的条件为 `covered != 391 or statements != 485 or percent < 80.0` 三者任一失败即 `raise SystemExit(1)`。393/485 = 81.03% 也被拒绝——必须精确为 391/485。

**脆弱性评估**：这是 intentional fail-closed design。若 coverage.py 版本升级改变 statement 计数，正确响应是 fail closed 回 Controller 重新建立 baseline，而非放宽 checker。Plan §8 明确覆盖此场景。

**结论**：PASS。✅

### 7.2 [344,346,348,442] root evidence

**独立 source 验证**：

```text
Line 344: return "material"          — _resolve_document_type material 分类分支
Line 346: return "other"              — _resolve_document_type other 分类分支
Line 348: return _CN_FORM_TYPE_TO_DOCUMENT_TYPE[form_type] — CN FY 分类分支
Line 442: return None                 — _normalize_form_type_for_matching(None) normalization
```

**调用链审计**：candidate 6 的 `form_type=None, source_kind=FILING` 断言 → `resolve_document_type_for_source(None, FILING)` → 内部 `_normalize_form_type_for_matching(None)` → 执行 line 442 `return None` → 返回后进入 `_resolve_document_type` → 执行 line 346 `return "other"`。

**关键判断**：line 442 不是独立偶然执行——它是 public-owner 调用链上 `form_type=None` 经过 normalization 短路的必经路径。三个 business classification branches（material/other/CN）加一个 normalization 短路构成不可分割的 4-statement 调用语义。

**结论**：PASS。✅

### 7.3 Mutation-before prefix-five predecessor provenance

**证据链审计**：

1. S2 cumulative implementation artifact 记录了 re-entry lock verification → prefix-five run → candidate 6 mutation → prefix-six run 的完整时序
2. Guards SHA 变化轨迹：mutation 前 `55318914...928d` → mutation 后 `cc4c5267...9274`，密码学证明 mutation 发生在两次 coverage run 之间
3. Prefix-five JSON SHA-256 `43986a2d9aca926a26396d420feea966be1526bc98da1c2fd1620335282b59fb` 固定在 plan §6.6
4. Plan 正确禁止回退 candidate 6 重跑 prefix-five（回退会破坏已证明正确的 test，且 predecessor evidence 已由 fresh JSON + guards SHA 变化完整记录）

**不可伪造性**：要在 candidate 6 已存在的 tree 上伪造 prefix-five 结果，必须临时删除 candidate 6 → 跑 coverage → 恢复 candidate 6。但 guards SHA 会被记录两次变化（删除后变回旧值、恢复后变回新值），而 prefix-five 只记录了 mutation 前的一个 SHA——这直接证明了 mutation 是向前增加而非临时回退。

**结论**：PASS。✅

### 7.4 Candidate 6 no-touch

**独立验证**：

- Guards SHA `cc4c5267...9274` 精确匹配 ✅
- `resolve_document_type_for_source` import 在 line 57，仅出现一次 ✅
- `test_document_type_resolver_projects_material_other_and_cn_categories` 在 line 1955，仅出现一次 ✅
- 三条 assertions 精确为 material/other/annual_report ✅
- 完整中文 docstring（Args/Returns/Raises）✅
- Plan §6.1、§6.2、§8、§9 checklist 多处声明 no-touch ✅
- Guards 文件共 21 个 tests，candidate 6 是最后一个业务 test（line 1991 是 `test_fins_import_boundary_keeps_host_exception_narrow`，属于 import boundary guard，不是 owner-family test）✅

**结论**：PASS。✅

### 7.5 392 passed zero deselect

**验证**：

- Prefix-six 命令使用八个测试文件路径、零 `--deselect`
- 八个文件在 locked tree 中精确匹配 S1/S2 test allowlists
- 确定性的 test 集合（无随机/过滤收集）
- 392 = 391（prefix-five test count）+ 1（candidate 6）
- Plan §8 stop condition：test count、numerator、denominator 任一 drift → fail closed

**Note**：Exact `392` count 依赖于八个文件中无其他 test 增删。若后续维护改变了任一文件的 test count，exact check 会 fail closed。这是 intentional design。

**结论**：PASS。✅

### 7.6 From-zero full matrix

**验证**：

Plan §6.6 要求：
1. `coverage erase` 清除所有历史 coverage data
2. Fresh `coverage run` 收集指定八个文件
3. Fresh `coverage json` 输出
4. Exact-key checker 机械验证
5. Prefix-six proof 通过后，从零完整重跑 §6.6/§6.7（focused owner matrix → S2 public → forced-truncation → real smokes → aggregate → full Fins regression → 15-file exact-key coverage → full pyright → scoped Ruff → all scans → `git diff --check`）

不接受旧 incremental ledger、Controller diagnostic、prior session JSON 或 display rounding 替代。

**结论**：PASS。✅

### 7.7 First/shortest 结论

**验证**：

- Prefix-five（原五个 stable-owner tests）：387/485 = 79.79% < 80.00% → 未过线
- Prefix-six（五个 + candidate 6）：391/485 = 80.62% >= 80.00% → 精确过线
- Candidate 6 是唯一新增测试，贡献 +4 covered statements
- 是否存在更短的 prefix（如 4 个或更少 tests 过线）？不可能——原五个 tests 按 owner family 排列且是完整连续前缀，删除任一 test 只会减少 covered statements

**范围限定**：Plan §§1/§6.6 已修正——first/shortest 结论仅适用于 `read_runtime_helpers.py` 单文件 threshold gap；15-file full acceptance 由 §6.6 exact-key checker 独立验证。

**结论**：PASS。✅

### 7.8 Fail-closed

**验证**：

Plan §8 定义了 18 项 stop conditions，每个均有明确的正向处置和禁止补救。覆盖维度：

| 维度 | 覆盖 |
|---|---|
| Producer contract drift | essential field 缺失 → stop + 禁止 read 默认 |
| Method absent/empty | terminal 统一 → `statement_not_found` |
| Provider raw total | internal inventory + 禁止 public 暴露 |
| S1 type change → S2 error | blocked intermediate + 继续 S2，不伪装通过 |
| Dedup mutation | 深复制后修改 public fact |
| Description drift | 消费 owner helper，不手写第二份 |
| Host truncation coupling | §6.4 三段 public seam 验证或 stop |
| 旧 test compatibility | 迁移 fixture/assertion，不保留 compat branch |
| Tree lock drift | 不运行 proof，回 Controller |
| Candidate 6 drift | 立即 stop |
| Dead helper 复活 | stop 回 Controller |
| Prefix proof mismatch | 保留现场、stop 回 Controller |
| Numerator/denominator/threshold drift | fail closed |
| Gate failure after deletion | 在 owner boundary 修复或 stop |
| Deferred scope discovery | 记录 out-of-scope，禁止扩张 |

无遗漏。✅

### 7.9 Semantic owner

**验证**：

Plan §2.2 owner table 精确分配三层语义：

| 语义 | 唯一 owner | R08 边界 |
|---|---|---|
| Financial producer result | `financial_result_contract.py` + actual processors | S1 唯一业务 owner |
| XBRL raw query result | `xbrl_result_contract.py` + actual processor | S1 唯一业务 owner |
| Public financial/XBRL result | `result_types.py` typed projection/helper | S2 唯一 public owner |
| List-documents suggestion | `read_runtime.py::_collect_available_document_types_for_source_documents` | 保留 typed owner |

每层有唯一 owner、无双重赋值、无 fallback 补偿、无下游重算。§2.3 明确所有 out-of-scope owners（R06/R07/R09-R12/Issues/Host/Engine/Service/UI）。✅

### 7.10 Scope/sequence/overcoupling

**Sequence**：S1 → S2 是同一次破坏性 cutover 的两个阶段。S1 不是独立 acceptance/review gate。S1/S2 之间不 stage/commit。累计 S1+S2 tree 是唯一 acceptance validation。

**Overcoupling 检查**：
- S1 和 S2 绑定为同一 cutover 是 **正确的设计**，不是过度耦合。Financial/XBRL producer contract 变更会立即破坏旧 public consumer 的 import graph。S1 独立 acceptance 会把"新 producer + 旧 consumer"声明为可接受状态——这是语义错误。
- `result_types.py` 是唯一 public projection owner
- `read_runtime_helpers.py` 是唯一 normalize/dedup owner
- `fins_tools.py` 只消费 owner helper
- Host truncation boundary 通过 public seam 验证
- R07 snapshot/citation no-touch

**Scope 约束**：§5.1/§6.1 production/test/README allowlists 精确；§2.3 out-of-scope 完整。✅

### 7.11 Topic 8-9 no-code

**验证**：

- Topic 8（Engine 240 chars）：overdesign controller discussion 已裁决 accepted as-is, no code fix
- Topic 9（Tool security wording）：design clarification only, no unified authorization framework
- Plan §2.3 out-of-scope 明确包含两者
- Plan 不授权任何 Topic 8/9 相关的 production code 修改

**结论**：PASS。✅

### 7.12 安全机制

**验证**：

Plan 不删除、不弱化任何现有安全机制：

- Path containment 保持（Fins design §9）✅
- DNS pin/peer proof 保持可配置（Topic 2 已裁决）✅
- Web egress private/local blocking 保持可配置 ✅
- Storage-state lifecycle 行为延迟至 Issue #178 ✅
- R06/R07 storage/identity/revision/snapshot/citation owner 保持 no-touch ✅
- §6.7.E retained-security/no-touch scan 覆盖全部安全边界 ✅
- Plan 不引入新的 security-sensitive path ✅

**结论**：PASS。✅

### 7.13 R07 no-touch

**验证**：

- `read_runtime.py` content SHA 保持 `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` ✅
- Plan §6.1 明确：即使 `read_runtime.py` 在 allowlist，R07 snapshot acquire/borrow/release、cache/revision、citation 与 source-changed symbols 不允许修改 ✅
- §6.7.D 要求 `git diff -U0` propagation scan 核验只改 financial/XBRL projection symbols ✅
- Plan §2.2 owner table 将 R07 storage 标注为"不可回改的 owner" ✅

**结论**：PASS。✅

### 7.14 Issues 142/151/175/177/178 与 R09-R12/deferred

**验证**：

Plan §2.3 明确 out-of-scope：

| Item | 状态 |
|---|---|
| R09 direct-stream validator | out-of-scope |
| R10 HKEX | out-of-scope |
| R11 upload/placeholders | out-of-scope |
| R12 init/reset | out-of-scope |
| Issue 142 (workspace migration) | out-of-scope |
| Issue 151 (write/upload assets) | out-of-scope |
| Issue 175 (Docling process isolation) | out-of-scope |
| Issue 177 (Doc truncation) | out-of-scope |
| Issue 178 (storage-state lifecycle) | out-of-scope |
| 统一 authorization | out-of-scope |
| Host/Engine/Service/UI | out-of-scope |

§8 stop condition："发现R09-R12/deferred issue → 记录out-of-scope并停止扩张"。§6.7.E exact allowlist scan 确保无越界实现。✅

### 7.15 §6.6/§6.7 current verification completeness

**验证**：

Fixed plan §6.2 item 8 与 §6.6/§6.7 构成的 current verification actions 覆盖：

1. Lock re-verification（全部 8 locks + staged）
2. Source/AST proof（dead helper deletion + actual owner + deleted nodes/imports）
3. Fresh prefix-five predecessor evidence 保留（不回退 candidate 6）
4. Fresh prefix-six proof（erase → 八文件零 deselect → 精确 392 passed + 391/485 ≥ 80%）
5. From-zero complete §6.6/§6.7 validation（focused → public → forced-truncation → real smokes → aggregate → full Fins regression → 15-file exact-key coverage → full pyright → scoped Ruff → all bidirectional scans → `git diff --check`）

验证矩阵完整；所有 gate 都 fail closed。✅

## 8. 旧已拒绝/已裁决事项确认不重新包装

以下事项经审查确认不是新 findings，不予重新包装：

| 事项 | 裁决来源 | 本轮确认 |
|---|---|---|
| Exact proof portability（coverage.py 版本差异） | Controller adjudication（Q3） | §8 stop condition 已覆盖，fail closed |
| Coverage narrative conflated scope | 原 DS M2，已在 F02 关闭 | Fixed plan §§1/§6.6 已显式区分 |
| §6.2 temporal scope ambiguity | 原 DS M3，已在 F03 关闭 | Fixed plan §6.2 全部标记为已完成 |
| Six stale test names | 原 DS M1，已在 F01 关闭 | Fixed plan §5.1 已使用 exact names |
| S2 artifact baseline different tree | 原 DS L1，已在 F04 关闭 | Fixed plan §7 已标注不同 tree state |
| Helper hash label 语义范围 | 原 DS L2，已在 F05 关闭 | Fixed plan 全文 label 已统一 |
| Unified authorization | Topic 9 已裁决为 design clarification only | Plan §2.3 out-of-scope |
| Host truncation boundary | Controller 已裁决 public seam 验证方式 | Plan §6.4 不修改 Host |
| S1 block evidence (B1/B2) | Controller 已裁决并通过 S2 cumulative tree 解决 | Plan 不再要求 S1 独立 gate |
| 未来 Issue 能力（142/151/175/177/178） | Overdesign controller discussion 已裁决 | Plan §2.3 out-of-scope |
| `390/485` 旧算术 | R08-CR-PCF04 superseded | Plan 全文使用 `391/485` |

## 9. New findings

### 9.1 无新的 material finding

经完整 adversarial re-review，未发现新的 material finding。所有五条 accepted findings 已在 fixed plan 中正确关闭，fixed plan 的 operational correctness、semantic owner boundaries、fail-closed stop conditions 与 scope/deferred boundaries 均完整且内洽。

### 9.2 Observation（非 finding）— guards 文件 21 tests 中 6 个 owner-family tests 之间的非 owner-family tests

**Observation**：Guards 文件 `cc4c5267...9274` 包含 21 个 tests。Plan §6.1 candidate table 列出的 6 个 owner-family tests（lines 1482, 1567, 1636, 1731, 1817, 1955）与其他 15 个 pre-existing guards tests（R07 snapshot/citation、processor taxonomy、public projection AST、import boundary 等）混在同一文件。这 15 个 pre-existing tests 不在 candidate table 中，但 prefix-six 的八文件命令会收集全部 21 个并执行。

**Risk**：低——prefix-six proof 的 `392 passed` 预期已包含所有 21 个 guards tests。任一 pre-existing test 因 S1/S2 contract 变更而意外失败，都会导致 test count 漂移并 fail closed。Plan 的 392-passed spec 是 aggregated file-level count，不区分 owner-family vs non-owner-family tests。

**Verdict**：不是 finding，不要求 plan 修改。§6.6 fresh validation 会自然暴露任何 regression。

## 10. Open questions

| # | Question | Reviewer answer |
|---|---|---|
| Q1 | Prefix-six fresh rerun 是否可能产生不同于 `391/485` 的结果？ | 可能性极低（同一 locked tree、同一命令、同一 coverage.py 版本），但若发生，§8 stop condition 明确 fail closed 回 Controller。这是 intentional design。 |
| Q2 | Guards 中 non-owner-family tests 是否全部能与 S1+S2 cumulative tree 兼容？ | guards SHA 保持 `cc4c5267...9274` 未变，证明 guards 内容在 stopped tree 中未漂移。S2 implementation 已在 tree 中完成，所有 imports 可解析。§6.6 fresh validation 会自然验证。 |
| Q3 | 15-file exact-key coverage checker 是否已在当前 locked tree 上验证过？ | 不是 plan blocker。本 continuation 尚未运行 full §6.6，fresh exact-key checker 正是唯一 destination。任何低于 80% 都 fail closed。 |
| Q4 | Prefix-five predecessor JSON 是否仍在 workspace？ | Controller adjudication §3 已确认两个 JSON 文件存在且 SHA 匹配。本 re-review 不再验证。 |

## 11. Residual risk

| Risk | Severity | Owner | Destination |
|---|---|---|---|
| Fresh prefix-six 391/485 因环境差异漂移 | LOW | §8 stop condition | Fail-closed → Controller 重新评估 baseline |
| 15-file coverage checker 某文件 < 80% | MEDIUM | §6.6 fresh validation | Fail-closed → Controller adjudication |
| Guards non-owner-family tests regression | LOW | §6.6 pytest collection | Fail-closed → Controller adjudication |
| R09-R12/deferred issues 被后续实现引入 regression | MEDIUM | R09-R12 plan review gates | Out of current plan scope |
| Exact test count 392 因八文件维护而漂移 | LOW | §8 stop condition | Fail-closed → Controller 重新评估 |

## 12. Final SHA and locks

| 项目 | 值 |
|---|---|
| Reviewed fixed plan | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| Fixed plan SHA-256 | `0253e626d81aa46b3b987f8acf93487e03a7b031530ad10a9402537d91c64521` |
| Cumulative `dayu/fins + tests` binary diff | `e40de2a03ad1240ef78bf9d36e28195f54a9166f344dd03c73bf1d0e6f63f33f` |
| S1+S2 cumulative `read_runtime_helpers.py` content state（含 dead-helper deletion 与 public projection/normalization） | `1d7b4bf19b9f05f4273553af1a07acbe0db4dae3ebeab2ec09985c4d74e5ea9b` |
| Actual-owner `read_runtime.py` | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| Candidate 6 guards | `cc4c5267241093e55d80e648f8d1013f7b71f52ace1f244447869d3afced9274` |
| Shared test | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| S1 artifact | `d97eed501adbb8fd24b9f5f56e8ddb9fecc52f719d19a616a9e1ba3034ff5748` |
| S2 artifact | `08085bde5dcbe6296694c2e251526870c4935a5a330edc9d495bcd4cf299c648` |
| Staged tree | empty |
| `git diff --check` | PASS |
| `git status` production/test/README | 不变（pre-existing stopped-tree state） |

## 13. Compliance audit

### 13.1 本 gate 授权范围

本 re-review 验证 fixed plan 在本 gate 的授权范围内：

- Plan §10 授权：只修改 `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` 与新增 `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-fix-codex.md`
- AgentCodex fix artifact §5 确认：authored paths 精确为上述两条
- Controller validation §4 确认：product/tests/README/control/design/prior reviews 保持 no-touch
- 本 re-review 独立确认：`git status` 中 22 个 tracked modified 是 pre-existing stopped-tree state，非本 gate 产生

### 13.2 Plan review gate 合规

- ✅ Fixed plan SHA-256 精确匹配 fix artifact 声明值
- ✅ 全部 8 locks + staged 独立验证通过
- ✅ F01-F05 全部在 fixed plan 中正确关闭
- ✅ 未修改任何 production/test/README/control/design/prior reviews
- ✅ 未运行 implementation/tests/coverage/pyright/Ruff/smoke
- ✅ 未 stage/commit/push/PR

### 13.3 LLM-facing text 合规

Plan §4.4 tool description metadata 内的 reason→下一动作矩阵自足说明业务含义与安全下一动作，不含 processor method、fallback branch、异常消息或 Host 治理状态。最小示例使用 `SEC_EDGAR`，不含 `sec_filing`。✅

### 13.4 语义所有权合规

Plan §2.2 owner table 精确分配四层语义、§2.3 明确不可回改的 owner、§4 contracts 定义完整的 typed shape 与 validator rules。每层有唯一 owner，无双重赋值、无 fallback 补偿。✅

## 14. Reviewer stop

本 artifact 完成 fixed plan 的 complete re-review。不授权 implementation、test、coverage、pyright、Ruff、smoke、code review、aggregate deepreview、commit、push 或 PR。未修改 plan、control、product、tests、README、design 或 prior review artifacts。

`PASS / ALL_FIVE_ACCEPTED_FINDINGS_CLOSED / ZERO_NEW_MATERIAL_FINDING / READY_FOR_ACCEPTED_PLAN_COMMIT`

下一 gate：Controller 确认本 re-review → accepted-plan local commit → AgentCodex 按 §6.6/§6.9 从 `e40de2a0...33f` stopped tree 复核 locks → §6.7.G source/AST proof → fresh prefix-six proof → 完整 §6.6/§6.7 validation → 双路 code re-review → Controller adjudication → aggregate deepreview。

---

Review metadata：

| 项目 | 值 |
|---|---|
| Reviewer | AgentDS |
| Review type | Complete independent adversarial plan re-review |
| Reviewed plan SHA-256 | `0253e626d81aa46b3b987f8acf93487e03a7b031530ad10a9402537d91c64521` |
| Reviewed plan path | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| Prior reviews reviewed | MiMo `531662c2...2864`, DS `cfe34587...e57` |
| Controller adjudication reviewed | `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-controller-adjudication.md` |
| AgentCodex fix reviewed | `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-fix-codex.md` |
| Controller validation reviewed | `docs/reviews/wu-semantic-ownership-01-r08-prefix-six-exact-drift-plan-review-fix-controller-validation.md` |
| Accepted findings | `R08-CR-PCPR-F01..F05` — all closed |
| New material findings | 0 |
| Observations | 1（non-finding — §9.2） |
| Open questions | 4（all non-blocking — §10） |
| Verdict | PASS / READY_FOR_ACCEPTED_PLAN_COMMIT |
