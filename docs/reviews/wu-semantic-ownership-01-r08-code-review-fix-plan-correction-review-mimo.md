# WU-SEMANTIC-OWNERSHIP-01 R08 Code-Review Fix Plan Correction — Complete Corrected-Plan Review (MiMo)

## 1. Review target and scope

| 项 | 值 |
|---|---|
| umbrella / sub-WU | 既有 `WU-SEMANTIC-OWNERSHIP-01` / `R08`；不是新 WU、feature 或 issue |
| review target | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`（corrected plan） |
| review scope | complete adversarial review of full corrected plan，覆盖所有段落而非仅新增段落 |
| corrected plan SHA-256 | `86bb76c768609451ca5f2de297f04f971832b719c6ca5a8b4a94d1617753fa65` — **PASS**（独立重算） |
| protected 23-path `dayu/fins + tests` binary diff SHA-256 | `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d` — **PASS**（独立重算） |
| staged tree | empty — **PASS** |
| `git diff --check` | exit 0，no output — **PASS** |
| review verdict | **PASS / 0 material finding / 0 blocker** |

本 review 是对 corrected plan 全文的完整 adversarial 审查。Reviewer 不修改 plan、product、tests、control 或既有 artifacts。

## 2. Context artifacts read

- 根 `AGENTS.md`
- `docs/phaseflow-umbrella-optimization-control.md`
- `docs/host/issues-implementation-control.md`（R08 相关行段）
- `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md`（完整 corrected plan，1065 行）
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-codex.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-code-review-fix-plan-correction-controller-validation.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-review-controller-adjudication.md`
- `docs/reviews/wu-semantic-ownership-01-r08-cumulative-code-review-fix-codex.md`
- `dayu/fins/tools/read_runtime.py`（FinsReadRuntime 公共方法签名与 helper 调用链）
- `dayu/fins/tools/read_runtime_helpers.py`（完整函数清单与 missing-lines 分布）
- `tests/fins/test_fins_read_runtime.py`（当前 9 节点确认）
- `tests/fins/test_read_runtime_semantic_ownership_guards.py`（当前 15 节点与 import 清单）

## 3. Hash verification

### 3.1 Corrected plan SHA-256

```bash
shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
```

```text
86bb76c768609451ca5f2de297f04f971832b719c6ca5a8b4a94d1617753fa65
```

与 Controller validation、Codex artifact 精确一致。**PASS**。

### 3.2 Protected 23-path binary diff SHA-256

```bash
git diff --binary -- dayu/fins tests | shasum -a 256
```

```text
7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d
```

与 Codex artifact §5、Controller validation §4 精确一致。**PASS**。

## 4. Adversarial challenge — 五项关键质疑

### 4.1 五个有序 owner-family candidate 是否通过 public FinsReadRuntime 真实执行到 read_runtime_helpers 并能贡献足够 statements？

**结论：PASS — 全部五个 candidate 确认可通过指定 seam 执行。**

逐一验证：

| # | family | 指定 seam | 代码验证 |
|---|---|---|---|
| 1 | document-type/filter | `FinsReadRuntime.list_documents` (read_runtime.py:835) | 确认调用 `_normalize_document_types`(:869)、`_normalize_periods`(:870)、`resolve_document_type_for_source`(:886)；传入 `document_types` 与 `fiscal_periods` 即可触发 |
| 2 | section payload | `FinsReadRuntime.read_section` (read_runtime.py:1011) | 确认调用 `_normalize_section_children`(:1117)、`_extract_page_range`(:1179)、`_collect_parent_titles`(:2704) |
| 3 | table payload | `FinsReadRuntime.get_table` (read_runtime.py:1735) | 确认调用 `_build_table_data_payload`(:1837)、`_normalize_table_type`(:1861) |
| 4 | XBRL taxonomy/default-concept | `FinsReadRuntime.query_xbrl_facts` (read_runtime.py:2089) | 确认 `concepts=None` 时 `normalized_concepts=[]`(falsy)，走 `_resolve_default_xbrl_concepts`(:2210)；taxonomy 通过 `_resolve_processor_taxonomy`(:2206) |
| 5 | search next-step | `build_search_next_section_fields` (read_runtime_helpers.py:573) | 确认是 module-level 纯函数，被 read_runtime.py:1425 和 :1568 调用；plan 明确为唯一 module-helper 例外 |

**Coverage 数学验证：**

当前基线：320/494 = 64.78%。需要达到 396/494 = 80.16%（≥76 条新增语句）。

五个 family 联合覆盖的 missing lines 估算：

| family | 目标函数 missing lines | 保守覆盖估计 |
|---|---|---|
| 1 | `_normalize_document_types`(12) + `_normalize_periods`(9) + `_resolve_document_type`(5) + `_normalize_json_scalar_text`(1) + `_collect_available_document_types`(8) = 35 | ~28 |
| 2 | `_normalize_section_children`(10) + `_extract_page_range`(4) + `_collect_parent_titles`(1) = 15 | ~12 |
| 3 | `_build_table_data_payload`(11) + `_normalize_table_rows`(6) + `_normalize_table_columns`(5) + `_coerce_table_text`(5) + `_looks_like_markdown_table`(11) + `_normalize_table_type`(2) = 40 | ~30 |
| 4 | `_resolve_default_xbrl_concepts`(11) + `_normalize_taxonomy_name`(4) + `_normalize_xbrl_query_payload`(1) + `_normalize_single_fact`(7) + `_clean_fact_text_value`(5) + `_looks_like_html_text`(3) + `_deduplicate_xbrl_facts`(3) + `_build_segment_signature`(2) + `_parse_xbrl_decimals`(3) + `_parse_xbrl_decimals_value`(3) + `_to_optional_float`(4) = 46 | ~35 |
| 5 | `build_search_next_section_fields`(7) = 7 | ~7 |

保守总覆盖：320 + 28 + 12 + 30 + 35 + 7 = **432 / 494 = 87.4%**。

即使 family 1-4 只覆盖主要路径（忽略边缘分支），前三个 family 联合约 70 条新增语句已超过 76 条阈值。五个 family 全部耗尽仍低于 80% 的 stop condition 概率极低，plan 的 stop condition 设计合理。

**唯一 caveat：** `resolve_has_financial_data` 有 16 条 uncovered lines 且在当前测试环境中不可达（`_read_capability_flags` 的 `get_processed_meta` 总是抛 `FileNotFoundError`）。这 16 条不在任何 family 的覆盖范围内，但不影响达到 80% 阈值。plan §6.5 明确禁止 compatibility inputs 测试该函数，与 Controller 裁决一致。

### 4.2 typed fixture + 真实 repository 是否 code-generation-ready？

**结论：PASS。**

`test_read_runtime_semantic_ownership_guards.py` 已有成熟的测试基础设施：

- **真实 filesystem-backed repositories**：`FsCompanyMetaRepository`、`FsSourceDocumentRepository`、`FsDocumentBlobRepository`、`FsProcessedDocumentRepository`、`FsBatchingRepository` 通过 `_build_runtime_with_source_documents` helper（line 1252）构造。
- **真实 source document 创建**：`_create_source_document`（line 1312）在磁盘上创建实际文件。
- **Typed processor fixture**：`_FixedProcessorRegistry`（line 469）注入测试处理器，实现 `DocumentProcessor` protocol。
- **Instrumented repository**：`_CountingSourceRepository`（line 515）扩展 `FsSourceDocumentRepository` 以检测调用。
- **已有 15 个测试**，全部使用真实存储，不是 mock/fake。

五个 family 的 test node 均可复用此模式。plan §6.1 明确要求"组合真实 repository 与 public runtime"，与现有模式一致。

### 4.3 typed failure 是否与当前 API 一致？

**结论：PASS。**

- `FinsReadArgumentError`（read_runtime_helpers.py:166）是当前 public typed failure，已用于 `read_runtime.py` 多处。
- plan §6.1 表格中 family 1-4 均要求"未知 `ref` 精确抛 `FinsReadArgumentError`"，与当前 API 一致。
- guards 文件已有 `FinsReadBusinessError` import（line 31），`FinsReadArgumentError` 可以机械加入。
- §6.7F 明确允许 `FinsReadArgumentError` 作为 public typed failure assertion 的 import。

### 4.4 候选连续最短前缀 / 首次 80 停止是否可机械验证？

**结论：PASS。**

§6.6 定义了精确的增量 ledger 机制：

1. **Step 0**：固定记录当前删除后基线 `320/494 = 64.78%`。
2. **逐 node 增量**：每次只新增一个 exact node，运行完整 coverage 集。
3. **机械判定**：inline Python checker 输出 `STOP_ADDING_TESTS` 或 `CONTINUE_NEXT_OWNER_FAMILY`。
4. **首次过线即停**：percent 首次 `>=80.00` 立即停止，不追求 100%。
5. **五候选耗尽仍不过线**：stop 回 Controller。

实现 artifact 必须逐 node 记录 `step / exact node / public seam / covered / statements / percent / decision`，构成可审计的 mechanical ledger。§6.7F 还要求 AST node assertion 证明实际新增 tests 精确等于候选表的连续最短前缀。

### 4.5 negative scans 是否误伤 baseline 或与允许第 5 helper 矛盾？

**结论：PASS — 无矛盾。**

§6.7F 定义了两类 negative scan：

**Scan 1：共享文件删除边界（test_fins_read_runtime.py）**

```bash
rg -n 'test_read_helper_document_discovery_rules_preserve_public_semantics|...|resolve_has_financial_data' \
  tests/fins/test_fins_read_runtime.py
```

预期零命中。验证：当前 `test_fins_read_runtime.py` 确认不含任何被扫描的符号（已由 `R08-CR-CF01` 删除）。**不误伤 baseline。**

**Scan 2：新 stable-owner 测试文件（test_read_runtime_semantic_ownership_guards.py）**

```bash
rg -n 'availability|has_structured_financial_statements|...|_resolve_default_xbrl_concepts' \
  tests/fins/test_read_runtime_semantic_ownership_guards.py
```

预期零命中。验证：当前 guards 文件不含这些 compatibility/helper 符号。**不误伤 baseline。**

**与第 5 helper 矛盾？** 不矛盾。Scan 2 禁止的是 `_resolve_default_xbrl_concepts` 等私有 helper 的直接调用，而 family 4 通过 public `FinsReadRuntime.query_xbrl_facts` 间接触发该函数。§6.1 明确区分：前四个 family 必须走 public seam，第 5 个 family 的 `build_search_next_section_fields` 是唯一允许直接调用的 module helper。Scan 只扫 guards 文件中的直接 import/调用，不扫间接执行路径。

§6.7F 还要求 AST import assertion 证明新增的 `read_runtime_helpers.py` production symbol import 精确为空或 `{build_search_next_section_fields}`（仅当实现第 5 候选时）。这与 scan 2 的 `build_search_next_section_fields` 未被列为禁止项一致。

## 5. Adversarial challenge — 补充质疑

### 5.1 共享 test_fins_read_runtime boundary 是否保持？

**结论：PASS。**

独立验证 `tests/fins/test_fins_read_runtime.py` 当前状态：

- **节点数**：恰好 9 个（2 generic + 6 normalize/dedup + 1 fiscal）
- **四节点删除确认**：`test_read_helper_document_discovery_rules_preserve_public_semantics`、`test_search_next_section_owner_ranks_exact_hits_per_query`、`test_table_data_projection_owner_emits_self_describing_shapes`、`test_navigation_and_xbrl_default_rule_owners_fail_closed` 均不存在
- **九 imports 删除确认**：`_build_table_data_payload`、`_normalize_document_types`、`_normalize_periods`、`_normalize_section_children`、`_normalize_taxonomy_name`、`resolve_default_xbrl_concepts`、`build_search_next_section_fields`、`resolve_document_type_for_source`、`resolve_has_financial_data` 均未被 import
- **文件 SHA-256**：`01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692`（与 Controller validation §4 一致）

§5.1、§6.7F 的删除边界 scan 与 SHA 锁定三重保障 boundary 不被突破。

### 5.2 有没有把原四个 omnibus/compat tests 变相搬运？

**结论：PASS — 无搬运。**

- §5.1 明确禁止"恢复、改名、参数化或搬运其结构"。
- §6.1 明确禁止"复制原四节点的 omnibus 结构、只改 test 名搬运"。
- §6.5 要求每个新增 node "只覆盖一个 owner family"、"完整中文 docstring 说明 owner"。
- §6.7F 的 AST node assertion 要求证明"实际新增 tests 精确等于候选表的连续最短前缀"。

新增的五个 owner-family tests 与原四节点的业务覆盖完全不同：

| 原节点（已删） | 新 family | 本质区别 |
|---|---|---|
| `test_read_helper_document_discovery_rules_preserve_public_semantics` | Family 1: document-type/filter | 原节点断言 compatibility availability 字段；新 family 断言 document_types/fiscal_periods 过滤 |
| `test_search_next_section_owner_ranks_exact_hits_per_query` | Family 5: search next-step | 原节点在 shared file；新 family 在 guards file 且使用不同 assertions |
| `test_table_data_projection_owner_emits_self_describing_shapes` | Family 3: table payload | 原节点通过 private helper；新 family 通过 public get_table |
| `test_navigation_and_xbrl_default_rule_owners_fail_closed` | Family 4: XBRL taxonomy | 原节点混合多个 owner；新 family 单一 owner |

### 5.3 是否引入 fake-only / private cache / processor / Host state / 偶然顺序？

**结论：PASS — 无引入。**

- §6.1 明确要求"组合真实 repository 与 public runtime"。
- §6.1 明确禁止"fake-only test"、"不得读 processor private method/state"。
- §6.1 明确禁止"不得构造平手后断言 first-index 偶然顺序"。
- §6.5 明确禁止"fake-only padding、private cache/method"。
- §8 stop conditions 表中"一个 public-seam candidate 需要 private cache/processor method/Host state、fake-only 或 compatibility input 才能驱动"→ "立即 stop 回 Controller"。

现有 guards 文件的基础设施（real filesystem repositories、typed processor fixtures）确保新增 tests 不引入 fake-only 路径。

### 5.4 完整 §6.6/§6.7、R07 no-touch、Host truncation、security/deferred 边界是否保留？

**结论：PASS — 全部保留。**

- **§6.6 累计 validation gate**：完整保留，包括增量 ledger、首次过线停止、从零完整重跑、15-file exact-key coverage checker、full pyright、scoped Ruff、diff check。
- **§6.7 双向 scans**：完整保留 A-F 六类 scan，§6.7F 是本次 correction 新增的 correction-specific scans。
- **R07 no-touch**：§6.7D 明确要求 `read_runtime.py` 只改 financial/XBRL projection symbols，snapshot acquire/borrow/release、cache revision、citation generation 零 diff。
- **Host truncation**：§6.4 完整保留三段 forced-truncation 验证（pre-Host 等式、Host cursor envelope、fetch_more remainder）。
- **security**：§6.7E retained-security scan、§8 stop conditions 均完整保留。
- **deferred**：§2.3 明确 out-of-scope，§8 stop conditions 要求"记录 out-of-scope 并停止扩张"。

## 6. R08-CR-PCF01 closure verification

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

## 7. Product / security / deferred no-drift

- §4 financial/XBRL producer/public product contracts 零变化。
- R07 snapshot acquire/borrow/release、cache/revision、citation、source-changed owners 零授权。
- Host truncation/fetch-more composition owner 零变化。
- filesystem containment、symlink、snapshot/revision、atomic publication 与其它 retained security 机制未删除或弱化。
- 未实施统一 tool authorization framework。
- R09-R12、Issues 142/151/175/177/178 与其它 deferred owners 保持 out-of-scope。

## 8. §6.6/§6.7 completeness verification

§6.6 累计 validation 命令完整覆盖：

- [x] S1 focused owner matrix
- [x] S2 focused/public matrix
- [x] 三段 forced-truncation public chain
- [x] AAPL/HTML/no-statement real smokes
- [x] R08 aggregate matrix + full Fins regression
- [x] 累计 coverage run + exact-key 15-file checker
- [x] full pyright
- [x] NUL-safe changed Python Ruff manifest + checker
- [x] `git diff --check`

§6.7 双向 scans 完整覆盖：

- [x] A. Internal positive inventory
- [x] B. Public/tool/schema/serializer/LLM negative scan
- [x] C. `fact_count` 唯一 owner scan
- [x] D. R07 no-touch propagation scan
- [x] E. AST、README、security 与 scope scan
- [x] F. `R08-CR-PCF01` correction-specific source/AST scans（新增）

## 9. Verdict

**PASS / 0 material finding / 0 blocker。**

Corrected plan 已 code-generation-ready：

1. 五个 owner-family candidate 全部确认可通过指定 public seam / module-helper 执行，coverage 数学上可达到 80%。
2. Typed fixture + 真实 repository 模式成熟可复用。
3. Typed failure API 一致。
4. 连续最短前缀 / 首次 80 停止可机械验证。
5. Negative scans 不误伤 baseline，与第 5 helper 例外不矛盾。
6. 共享文件 boundary 三重保障（SHA + scan + AST）。
7. 无 omnibus 搬运、fake-only、private state、偶然顺序。
8. 完整 §6.6/§6.7、R07 no-touch、Host truncation、security/deferred 边界全部保留。
9. §4 product contracts、S1/S2 path allowlists、R07/Host/Topic 8-9/deferred boundaries 均未改变。

Reviewer 不修改 plan、product、tests、control 或既有 artifacts。停止回 Controller。
