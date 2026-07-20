# WU-SEMANTIC-OWNERSHIP-01 R08 Corrected-Plan Review Fix Re-Review — AgentDS

## 1. Verdict

**PASS / 0 MATERIAL FINDING / 0 BLOCKER**

R08-CR-PCPR-F01 已精确闭合。Final corrected plan SHA-256
`a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` 是
code-generation-ready。此前被 Controller 驳回的 M1、L1、L2、L3 均未被偷带回计划。五项
owner-family candidate 仍全部可执行。共享文件 boundary、§6.6/§6.7 完整验证、R07 no-touch、
Host truncation owner、retained security 与 R09-R12/deferred 边界全部保留。

本 re-review 是完整 adversarial 审查，覆盖从 §0 gate 到 §10 自检的全部计划段落，不是仅
candidate 2/3 delta。Reviewer 不修改 plan、product、tests、README、control 或既有 artifacts。

## 2. Hash Verification — 独立重算

### 2.1 Final corrected plan SHA-256

```bash
shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
```

| Expected | Actual | Status |
|---|---|---|
| `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` | `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02` | **PASS** |

与 Controller validation §2 和 AgentCodex fix artifact §1 精确一致。

### 2.2 Protected 23-path `git diff --binary -- dayu/fins tests` SHA-256

```bash
git diff --binary -- dayu/fins tests | shasum -a 256
```

| Expected | Actual | Status |
|---|---|---|
| `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d` | `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d` | **PASS** |

### 2.3 共享文件 sub-hash

| 文件 | Expected SHA-256 | Actual SHA-256 | Status |
|---|---|---|---|
| `test_fins_read_runtime.py` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | **PASS** |
| `test_read_runtime_semantic_ownership_guards.py` | `4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` | `4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` | **PASS** |

### 2.4 其它 gate 检查

| 检查项 | 结果 |
|---|---|
| `git diff --cached --name-only` | empty — **PASS** |
| `git diff --check` | exit 0, no output — **PASS** |

**任一 hash 漂移将立即停止。** 当前全部精确匹配。

## 3. R08-CR-PCPR-F01 Closure — 逐项验证

### 3.1 Candidate 2 — section public payload projection

**修改要点**（计划 line 524）：typed fixture 的 `read_section` 对未知 ref **必须抛 `KeyError`**，
再由 `FinsReadRuntime.read_section` public seam **精确转换为 `FinsReadArgumentError`**；
测试**只观察该 public runtime failure**，不直接断言 fixture 或其 `KeyError`。

**生产代码验证**（`read_runtime.py:1088-1112`）：

```python
# line 1088-1092
try:
    section_raw: SectionContent = processor.read_section(normalized_ref)
except KeyError as exc:
    ...
    raise FinsReadArgumentError("read_section", "ref", normalized_ref, hint) from exc
```

转换链确认：`processor.read_section(ref)` → `KeyError` → `except KeyError as exc` →
`raise FinsReadArgumentError(...) from exc`。计划文案与生产代码路径**逐字一致**。

### 3.2 Candidate 3 — table public payload projection

**修改要点**（计划 line 525）：typed fixture 的 `read_table` 对未知 table_ref **必须抛 `KeyError`**，
再由 `FinsReadRuntime.get_table` public seam **精确转换为 `FinsReadArgumentError`**；
测试**只观察该 public runtime failure**，不直接断言 fixture 或其 `KeyError`。

**生产代码验证**（`read_runtime.py:1812-1836`）：

```python
# line 1812-1816
try:
    table_raw: TableContent = processor.read_table(normalized_table_ref)
except KeyError as exc:
    ...
    raise FinsReadArgumentError("get_table", "table_ref", normalized_table_ref, hint) from exc
```

转换链确认：`processor.read_table(table_ref)` → `KeyError` → `except KeyError as exc` →
`raise FinsReadArgumentError(...) from exc`。计划文案与生产代码路径**逐字一致**。

### 3.3 修复完整性

| Controller 裁决要求 | 计划落点 | 验证 |
|---|---|---|
| 只修改 corrected plan 与 Codex fix artifact | 仅计划 §6.1 candidate 2/3 的两行第四列变更 + 本 artifact | PASS — 无 product/test/README/control 修改 |
| candidate 2: fixture `read_section` 抛 `KeyError`，runtime 转换为 `FinsReadArgumentError` | line 524 | PASS — 精确匹配 |
| candidate 3: fixture `read_table` 抛 `KeyError`，runtime 转换为 `FinsReadArgumentError` | line 525 | PASS — 精确匹配 |
| assertion 只观察 public runtime failure | "测试只观察该 public runtime failure，不直接断言 fixture 或其 `KeyError`" | PASS — 两次明确 |
| 不改变五候选顺序/exact node names/coverage ledger/80% stop/path allowlist/product contract | §4、§5、§6 all unchanged except candidate 2/3 column 4 | PASS |

**R08-CR-PCPR-F01 已闭合。**

## 4. Rejected Findings — 未偷带验证

Controller adjudication §3 明确驳回 M1、L1、L2、L3。以下逐项验证其在 final corrected plan 中未被偷带回：

### 4.1 DS M1 — `available_document_types` 顺序

**Controller 裁决**：REJECTED AS FACTUALLY INCORRECT / ALREADY GUARDED。

**证据**：`_collect_available_document_types`（`read_runtime_helpers.py:393-420`）使用
`set[str]` 去重后 `return sorted(doc_types)`（line 420），公共 suggestion 的
`available_document_types` 具有 canonical sorted 顺序，不依赖 repository iteration order。
计划 §6.1 candidate 1 已明确"不得依赖 repository 返回顺序"。

**最终计划中 candidate 1 文案**：未变。未新增 `set()`/`sorted()` assertion 要求。→ **M1 未被偷带。** ✅

### 4.2 DS L1 — candidate 4 form_type 间接驱动

**Controller 裁决**：REJECTED AS ALREADY COVERED OBSERVATION。

**最终计划中 candidate 4 范围**：未变。未新增 private form_type injection mechanism。→ **L1 未被偷带。** ✅

### 4.3 DS L2 — AST import assertion "新增" 限定

**Controller 裁决**：REJECTED AS ALREADY PRECISE。

**最终计划 §6.7F**：未变。"新增"限定词保持原样，未加 pre-existing import 白名单。→ **L2 未被偷带。** ✅

### 4.4 DS L3 — coverage 非单调理论风险

**Controller 裁决**：REJECTED AS ALREADY CLOSED BY MECHANICAL LEDGER/STOP。

**最终计划 §6.6**：未变。增量 ledger 逐 step 记录 `covered/statements/percent/decision`，
§8 要求任何 gate 失败即停。→ **L3 未被偷带。** ✅

### 4.5 MiMo 零 material finding

MiMo 原 review 未提出 finding，Controller 接受其正向证据。最终计划无误伤 MiMo 审查范围的改动。→ ✅

## 5. 完整 Corrected Plan 再审查

以下是对全部 10 个 § 的完整 adversarial 再审查，不仅限于 §6.1 candidate 2/3。

### 5.1 §0–§2：Gate、第一性原理、完成定义与非目标

**再审查结果：PASS — 无漂移。**

- §0 gate 定义保持精确：plan-only correction，授权只修改 plan 与 Codex artifact。✅
- §1 六项第一性原理判断（包括 `read_runtime_helpers.py` `320/494=64.78%` 与理论 max `351/494=71.05%` 的数学自冲突分析）未变。✅
- §2.1 完成定义明确 guards 文件新职责：承载最小 stable-owner evidence。✅
- §2.2 不可回改 owner 表格（R06 transaction、R07 storage/identity/revision/snapshot/citation/provenance）完整保留。✅
- §2.3 out-of-scope（R09-R12、Issues 142/151/175/177/178、统一 authorization、Host/Engine/Service/UI）完整保留。✅

### 5.2 §3：字段与 Owner Inventory

**再审查结果：PASS — 无漂移。**

- §3.1 Financial producer contract、§3.2 XBRL processor-internal contract、§3.3 Actual producer inventory 表、§3.4 Consumers/alternate owner/tests 均未变。✅
- 七值 reason 闭集、`total`/`deduped_fact_count` 删除、`fact_count` 只属 S2 projection 的全部裁决保持。✅

### 5.3 §4：目标 Contracts（代码生成真源）

**再审查结果：PASS — 无漂移。**

已验证的当前 `result_types.py` 的 `PublicFinancialStatementResult` / `PublicXbrlQueryResult`
TypedDict shape、`project_xbrl_query_result` 唯一 `fact_count = len(returned_facts_copy)`、
description metadata/helper、七值 reason→下一动作矩阵、`SEC_EDGAR` 示例、`fiscal_period`
从 `FISCAL_PERIODS` 派生——全部**未变**。✅

- `bool` 显式拒绝规则、flat typed query params、`filters_applied` 删除、five-condition raw total
  inventory 保留——全部**未变**。✅

### 5.4 §5：R08-S1 Producer Contracts + All Actual Processors

**再审查结果：PASS — 无漂移。**

- §5.1 12-production/3-test allowlist 未变。✅
- 共享文件 symbol boundary（1 S1 fiscal + 6 S2 normalize/dedup + 2 generic = 9 nodes）未变。
  当前 `test_fins_read_runtime.py` 恰好 9 个 test functions，与计划一致。✅
- 四个删除节点与九个 imports 列表未变，禁止恢复。✅
- §5.4 S1 中间 tree 定位为 "blocked intermediate evidence" 未变。✅
- §5.6 S1→S2 累计 cutover 未变：同 tree 连续实施，不单独 stage/commit/review。✅

### 5.5 §6.1–§6.2：R08-S2 allowlist 与 Five Owner-Family Candidates

**再审查结果：PASS — 仅 candidate 2/3 column 4 按 Controller 裁决变更，所有其它内容保持。**

#### Candidate 1：document-type/filter

Seam 仍为 `FinsReadRuntime.list_documents`（`read_runtime.py:835`）。执行路径、coverage
贡献估计、基础设施验证（已使用 `build_fs_repository_set` + typed processor fixtures）与
初审一致。⚠️ "不得依赖 repository 返回顺序"约束保持。

→ **仍可执行。** ✅

#### Candidate 2：section public payload projection

Seam 仍为 `FinsReadRuntime.read_section`（`read_runtime.py:1011`）。已确认 `_read_section_with_borrow`
在 `processor.read_section(normalized_ref)` 处用 `except KeyError as exc` 捕获并将 public
failure 投影为 `FinsReadArgumentError("read_section", "ref", normalized_ref, hint) from exc`。

**R08-CR-PCPR-F01 逐字验证**（§3.1 细节）：plan 现在精确要求 typed fixture 抛 `KeyError`、
runtime 转换为 `FinsReadArgumentError`、test 只观察 public failure——与生产代码逐行一致。

→ **完全可执行。** ✅

#### Candidate 3：table public payload projection

Seam 仍为 `FinsReadRuntime.get_table`（`read_runtime.py:1735`）。production 路径在
`processor.read_table(normalized_table_ref)` 处使用 `except KeyError as exc: raise
FinsReadArgumentError("get_table", "table_ref", ...) from exc`。

**R08-CR-PCPR-F01 逐字验证**（§3.2 细节）：plan 现在精确要求 typed fixture 抛 `KeyError`、
runtime 转换为 `FinsReadArgumentError`、test 只观察 public failure——与生产代码逐行一致。

→ **完全可执行。** ✅

#### Candidate 4：XBRL taxonomy/default-concept selection

Seam 仍为 `FinsReadRuntime.query_xbrl_facts`（`read_runtime.py:2089`）。concepts 缺席时走
`_resolve_processor_taxonomy` → `_normalize_taxonomy_name` → `_resolve_default_xbrl_concepts`，
public seam 满足。`SecProcessor` 实现 `get_xbrl_taxonomy()` 满足 `XbrlTaxonomyProcessor`
Protocol。

→ **仍可执行。** ✅

#### Candidate 5：search next-step

Seam 仍为 `build_search_next_section_fields`（`read_runtime_helpers.py:573`）——唯一
module-helper 例外。纯函数，不需 repository/processor/runtime。"不得构造平手后断言
first-index 偶然顺序"约束保持。

→ **仍可执行。** ✅

#### 约束完整性

| 约束 | 再验证 |
|---|---|
| 不扩大 test path allowlist | `test_read_runtime_semantic_ownership_guards.py` 已在既有 S2 allowlist |
| 四节点/九 imports 不恢复 | §6.7F scan exit 1（零命中）+ SHA-256 lock |
| 禁止 compatibility inputs | `availability` 等六项禁止保留 |
| 禁止 omnibus 改名搬运 | 每 candidate 单 owner family + exact docstring |
| 禁止 fake-only | 每 candidate 要求真实 repository + public runtime |
| 禁止 private cache/processor/Host state | 前四项 public seam，第五项唯一 module-helper 例外 |
| 增量 ledger 首次 >=80 停止 | §6.6 机械命令保留 |
| 五候选耗尽仍 <80% 则 stop | §8 保留 |

全部约束保留。✅

### 5.6 §6.3–§6.5：Input/Output Mapping、截断组合风险、累计 Tests

**再审查结果：PASS — 无漂移。**

- §6.3 input/output mapping 表与禁止行为列未变。✅
- §6.4 Host truncation 组合风险：三段验证（pre-Host typed equality、Host public cursor envelope、
  fetch-more remainder）完整保留。`fact_count` 仍由 Fins owner 持有。pre-Host 字段存在性
  与 `pre_value["fact_count"]` 直接索引断言（不用 `.get()`）保留。Cannot-test stop condition
  保留（若 public seam 不可观测则 stop 回 Controller）。✅
- §6.5 累计 owner/public tests 覆盖项未变。真实 AAPL/HTML/no-statement smokes 保留。✅

### 5.7 §6.6：累计 S1+S2 Validation Gate

**再审查结果：PASS — 无漂移。**

- 增量 ledger step 0 基线 `320/494 = 64.78%` 保持。✅
- Coverage 收集命令从 repository root 运行，使用 `coverage json` + exact-key lookup，与
  原 15-file checker 同构。✅
- "首次 `>=80.00` 立即停止"的 Python 判定逻辑保持。✅
- 累计 validation 命令矩阵（S1 focused、S2 focused/public、forced-truncation chain、
  AAPL/HTML/no-statement smokes、R08 aggregate、full Fins regression、coverage erase/run/json、
  15-file exact-key checker、full pyright、scoped Ruff manifest checker、`git diff --check`）
  全部保留。✅
- Coverage manifest 必须从 Git top-level glob pathspec 生成，exact-key JSON lookup，
  `summary.percent_covered >= 80.00` 逐文件检查——保留。✅

### 5.8 §6.7：双向 Scans 与唯一同源证明

**再审查结果：PASS — 无漂移。**

- §6.7A internal positive inventory scan：owner roots 与 five-condition evidence 保留。✅
- §6.7B public/tool/schema/serializer/LLM negative scan：roots 与禁止 literal 列表保留。
  独立运行 exit 1（零命中）。✅
- §6.7C `fact_count` 唯一 owner scan：roots 保留。✅
- §6.7D R07 no-touch propagation scan：`git diff -U0` + `read_runtime.py` 只改
  financial/XBRL projection symbols。✅
- §6.7E AST、README、security、scope scans：全部保留。✅
- §6.7F correction-specific scans：三组 scan（共享文件删除边界、compatibility/private-helper
  negative、AST import assertion）全部保留，且独立运行验证通过（exit 1，零命中）。✅

### 5.9 §6.8–§6.9：README 同步与 Review/Commit 边界

**再审查结果：PASS — 无漂移。**

- §6.8 README 同步触发规则未变。✅
- §6.9 gate sequence 保持精确：

  ```text
  AgentCodex plan-only correction
  → Controller plan-diff/protected-tree validation
  → AgentMiMo + AgentDS complete corrected-plan review
  → accepted plan findings fix（若有）
  → complete corrected-plan re-review / Controller adjudication
  → corrected-plan accepted local commit
  → AgentCodex test-only code-review fix from 7a7ebf...1d6d protected tree
  → §6.6 incremental coverage ledger, >=80 stop
  → full §6.6/§6.7 from zero
  → Controller locks new hash
  → AgentMiMo + AgentDS complete S1+S2+fix code re-review
  → aggregate deepreview
  ```

- 旧 hash/validation/reviews 全部标记失效。✅

### 5.10 §7–§10：Aggregate Deepreview、Stop Conditions、Checklist、自检

**再审查结果：PASS — 无漂移。**

- §7 aggregate deepreview 覆盖项保留（owner 唯一性、reason 动作性、count 单一同源、raw
  immutability、query params 单一 shape、tool/serializer drift、R07 no-touch、compat/shim、
  allowlist/README/tests 越界、四节点/九 imports 删除、stable-owner test 最小性、首次过线
  ledger、S1/S2/fix 之间的 semantic ownership drift）。✅
- §8 stop conditions 表覆盖全部已知失败模式，与初审一致。✅
- §9 code-generation handoff checklist 覆盖 S1/S2/aggregate 全部 gate。✅
- §10 本 gate 自检要求保留。✅

## 6. Boundary Scans — 独立执行

### 6.1 Shared-file deletion boundary scan

```bash
rg -n 'test_read_helper_document_discovery_rules_preserve_public_semantics|...|resolve_has_financial_data' \
  tests/fins/test_fins_read_runtime.py
```

**结果**：exit 1（零命中）。✅

四个已删除节点的 symbols 与九个 imports 均不在文件中。

### 6.2 Compatibility/private-helper negative scan

```bash
rg -n 'availability|has_structured_financial_statements|...|_resolve_default_xbrl_concepts' \
  tests/fins/test_read_runtime_semantic_ownership_guards.py
```

**结果**：exit 1（零命中）。✅

无 compatibility 或 private helper 直接调用。

### 6.3 Public/tool/schema/LLM negative scan

```bash
rg -n -i 'raw[_ -]?total|deduped_fact_count|...|sec_filing' \
  dayu/fins/tools dayu/config/prompts
```

**结果**：exit 1（零命中）。✅

无越界 literal 泄漏到 public surface。

### 6.4 Shared file structure verification

`test_fins_read_runtime.py` 当前精确含 9 个 test functions：
- 2 generic（LRU、form-matching）
- 6 normalize/dedup（`test_xbrl_query_payload_*`）
- 1 fiscal（`test_sec_fiscal_inference_consumes_countless_xbrl_contract`）

SHA-256 `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` 与
Controller validation 精确一致。✅

`test_read_runtime_semantic_ownership_guards.py` 当前含 15 个 test functions，SHA-256
`4a076ca6c6efb5df986104833d9816e5bdfdda53ac0c292081a9be49223bc1ff` 与 Controller
validation 精确一致。✅

## 7. R07 / Host Truncation / Security / Deferred No-Drift

### 7.1 R07 no-touch

- §2.2 不可回改 owner 表格：opaque ticker/document identity、revision、stable snapshot、
  borrow/retire/cache lifecycle、provenance、citation——全部保留 R07 owner。✅
- §6.7D 要求 `read_runtime.py` 只改 financial/XBRL projection symbols，snapshot
  acquire/borrow/release、cache revision、citation generation、source-changed paths 零 diff。✅
- §6.7E retained-security scan 要求 R06/R07 storage、identity、revision、snapshot、citation、
  containment、symlink、atomic publication/recovery 语义均无语义 diff。✅

### 7.2 Host truncation owner

- §6.4 三段 forced-truncation 验证完整保留：pre-Host typed equality（`fact_count == len(facts)`）、
  Host public cursor envelope（`fact_count` sibling preserved）、fetch-more remainder（visible
  prefix + remainder = saved pre-Host facts）。✅
- `fact_count` 由 Fins owner 持有，Host 不维护。✅
- Cannot-test stop condition 保留：若 Host public seam 无法同时观测 pre-Host typed value、
  Host completed envelope 与公开 fetch-more result，立即 stop 回 Controller。✅
- 当前只读探测证据保留：pre-Host 与 post-Host 的 key set 相同，Host 只替换 `facts` 字段并
  保留全部顶层 siblings。正式测试在 S2 产生 `fact_count` 后重新证明。✅

### 7.3 Retained security

- filesystem containment、symlink、snapshot/revision、atomic publication 与其它 retained
  security mechanisms 未删除或弱化。✅
- §6.7E retained-security/no-touch scan 保留。✅

### 7.4 Deferred boundaries

- R09 direct-stream validator、R10 HKEX、R11 upload/placeholders、R12 init/reset 保持 out-of-scope。✅
- Issues 142、151、175、177、178、统一 authorization 保持 out-of-scope。✅
- Host generic truncation/cursor/fetch_more、Engine、Service、UI 保持 out-of-scope。✅
- §8 stop condition："发现 R09-R12/deferred issue → 记录 out-of-scope 并停止扩张"。✅

## 8. 五 Candidate 可执行性再验证

| Candidate | Seam | Public? | 基础设施 | 约束 | Adversarial Risk | Status |
|---|---|---|---|---|---|---|
| 1 | `list_documents` | ✅ public method | 已有 `list_documents` tests | 禁止 repository order 依赖、禁止 compatibility inputs | `broaden_filter` 构造需真实多文档 workspace | PASS |
| 2 | `read_section` | ✅ public method | 需 `read_section` 在 typed fixture 上实现 | fixture 必须抛 `KeyError`、test 只观察 public `FinsReadArgumentError` | fixture 须返回含 children 的 SectionContent | PASS |
| 3 | `get_table` | ✅ public method | 需 `read_table` 在 typed fixture 上实现 + records/markdown/text shapes | fixture 必须抛 `KeyError`、test 只观察 public `FinsReadArgumentError` | 需三种 data.kind shape 的 table fixture | PASS |
| 4 | `query_xbrl_facts` | ✅ public method | 已有 `SecProcessor` 含 `get_xbrl_taxonomy()` | 不得直接调 `_normalize_taxonomy_name` / `_resolve_default_xbrl_concepts` | `form_type` 来自 borrowed doc meta | PASS |
| 5 | `build_search_next_section_fields` | ⚠️ 唯一 module-helper 例外 | 纯函数 | 禁止偶然 order tiebreaker | 排序 key 第三级是 `_first_index` | PASS |

### 8.1 Coverage 数学重验证

初始基线（step 0）：320/494 = 64.78%。初审核实的各 family 覆盖估计与 MiMo 独立估算一致。
前三个 family 联合约 70 条新增语句，超过 76 条阈值（396/494 = 80.16%）。五个 family 联合
保守估计 432/494 = 87.4%。

80% stop condition 在 family 3 或 family 4 首次过线的概率高。五候选全部耗尽后仍低于 80%
的 stop condition 数学概率极低——但若发生，§8 已明确要求立即 stop 回 Controller，不追求
100%、不补 coverage padding。

### 8.2 连续最短前缀机械验证

§6.6 增量 ledger 的 `STOP_ADDING_TESTS / CONTINUE_NEXT_OWNER_FAMILY` 判定是纯机械的。
`percent >= 80.0` 无歧义。实现 artifact 必须逐 node 记录 `step / exact node / public seam /
covered / statements / percent / decision`——这是可审计的不可变链。

## 9. §6.6/§6.7 完整性确认

以下由初审 DS 和 MiMo 均验证为完整保留，再验证为未变：

### 9.1 §6.6 累计 validation

- [x] 增量 ledger：step 0 基线 → 逐 node 增量 → 机械 80% stop → 完整重跑
- [x] S1 focused owner matrix
- [x] S2 focused/public matrix
- [x] 三段 forced-truncation public chain
- [x] AAPL/HTML/no-statement real smokes
- [x] R08 aggregate matrix + full Fins regression
- [x] 累计 coverage run + 15-file exact-key checker（`>=80.00%` per file）
- [x] full pyright（`0 errors`）
- [x] NUL-safe changed Python Ruff manifest + checker
- [x] `git diff --check`

### 9.2 §6.7 双向 scans

- [x] A. Internal positive inventory
- [x] B. Public/tool/schema/serializer/LLM negative scan
- [x] C. `fact_count` 唯一 owner scan
- [x] D. R07 no-touch propagation scan
- [x] E. AST、README、security 与 scope scan
- [x] F. `R08-CR-PCPR01` correction-specific scans

## 10. Controller Adjudication 尊重确认

| 裁决项 | Agent | 裁决 | 最终计划中? | 本 re-review |
|---|---|---|---|---|
| 无 material finding | MiMo | 接受正向证据 | N/A | 确认无回退 |
| DS M1 | DS | REJECTED — `sorted()` + 计划已 guard | 未被偷带 | 独立确认 `sorted(doc_types)` at line 420 |
| DS M2 | DS | **ACCEPTED → R08-CR-PCPR-F01** | 已修复 | **§3 确认闭合** |
| DS L1 | DS | REJECTED — 已覆盖 | 未被偷带 | 确认无 form_type injection |
| DS L2 | DS | REJECTED — 已精确 | 未被偷带 | 确认 "新增" 限定词保留 |
| DS L3 | DS | REJECTED — 已被 ledger/stop 关闭 | 未被偷带 | 确认 §6.6/§8 停止规则保留 |

全部 Controller 裁决被严格执行。无越界修改、无静默回退、无裁决重开。

## 11. Forward Verification Summary

| 验证项 | 方法 | 结果 |
|---|---|---|
| Final corrected plan SHA-256 | 独立 `shasum -a 256` | `a79268ea...a02` — PASS |
| Protected diff SHA-256 | 独立 `git diff --binary -- dayu/fins tests \| shasum -a 256` | `7a7ebf...1d6d` — PASS |
| Shared file sub-hashes | 独立 `shasum -a 256` 两个文件 | 均匹配 — PASS |
| R08-CR-PCPR-F01 closure | 计划文案 + 生产代码转换链交叉验证 | CLOSED — PASS |
| Rejected findings 未偷带 | 逐项 diff candidate 1/§6.7F/§6.6/§6.7 | 全部保持 — PASS |
| 五 candidate 可执行性 | 代码路径追踪 + 基础设施 + adversarial risks | 全部可执行 — PASS |
| 连续最短前缀 / 80 stop 机械性 | §6.6 ledger 命令 + stop condition review | 机械可验证 — PASS |
| Shared-file boundary | SHA-256 lock + deletion scan + AST verification | 保持 — PASS |
| 完整 §6.6/§6.7 | 命令矩阵 + scan list review | 完整保留 — PASS |
| R07 no-touch | §2.2 + §6.7D + §6.7E review | 保留 — PASS |
| Host truncation owner | §6.4 三段验证 review | 保留 — PASS |
| Security no-drift | §6.7E retained-security scan | 保留 — PASS |
| Deferred boundaries | §2.3 + §8 review | 保留 — PASS |
| Topic 8-9 no-code | §2.3 + Controller adjudication | 保留 — PASS |
| Controller adjudication 尊重 | 逐裁决项检查 | 全部尊重 — PASS |
| Public/tool/schema negative scan | 独立 `rg` zero-hit | PASS |
| Shared-file deletion boundary scan | 独立 `rg` zero-hit | PASS |
| Guards compatibility scan | 独立 `rg` zero-hit | PASS |
| Staged files | `git diff --cached --name-only` | empty — PASS |
| Whitespace check | `git diff --check` | PASS — PASS |

## 12. Findings

**0 MATERIAL FINDING / 0 BLOCKER。**

本次完整 re-review 覆盖从 §0 到 §10 的全部计划段落、全部五 candidate 可执行性、全部
boundary condition、全部 scan、全部 adjudication 裁决。Final corrected plan 上不存在
material finding 或 blocker。

## 13. Artifact Hash Verification（写入后重算）

本 artifact 写入后立即执行：

### 13.1 Final corrected plan SHA-256（重算）

```bash
shasum -a 256 docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
```

**重算值**：（见下方 §14 实际执行输出）

Required: `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02`

### 13.2 Protected diff SHA-256（重算）

```bash
git diff --binary -- dayu/fins tests | shasum -a 256
```

**重算值**：（见下方 §14 实际执行输出）

Required: `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d`

本 artifact 位于 `docs/reviews/`，不属于 `dayu/fins` 或 `tests`，不进入 protected diff。

## 14. Post-Write Hash Recalculation

以下为 artifact 写入完成后的独立重算结果。

### 14.1 Corrected plan

```text
a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02  docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md
```

→ **PASS** — 与 required value 精确一致。

### 14.2 Protected diff

```text
7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d  -
```

→ **PASS** — 与 required value 精确一致。

### 14.3 Gate checks

- `git diff --cached --name-only`：empty — **PASS**
- `git diff --check`：exit 0, no output — **PASS**

## 15. Handoff

**Verdict**：PASS / 0 MATERIAL FINDING / 0 BLOCKER。

Final corrected plan SHA-256 `a79268ea8d45f6af8854859269ce3592506f753272c32ecffab76d765cad7a02`
与 protected diff SHA-256 `7a7ebf939b758ce8fdd92413210743e5a90b65272df62e466bf70332eb771d6d`
均独立验证通过。

R08-CR-PCPR-F01 已精确闭合于计划 §6.1 candidate 2/3 column 4。此前被驳回的 M1、L1、L2、L3
均未被偷带回计划。五项 owner-family candidate 仍全部可执行。共享文件 boundary、完整
§6.6/§6.7、R07 no-touch、Host truncation owner、retained security 与 R09-R12/deferred
边界全部保留。Controller 全部裁决被严格尊重。

Corrected plan 可继续进入 Controller adjudication 闭合本 re-review gate。

停止回 Controller。未修改 plan/product/tests/README/control/prior artifacts，未
commit/push/PR。
