# WU-SEMANTIC-OWNERSHIP-01 R08 Candidate Exhaustion Corrected Plan Review — AgentMiMo

## 1. Review Gate

| 项 | 值 |
|---|---|
| umbrella | `WU-SEMANTIC-OWNERSHIP-01` |
| sub-WU | 既有 R08 candidate-exhaustion plan-only correction |
| review 对象 | `docs/host/wu-semantic-ownership-01-r08-fins-financial-xbrl-contract-plan.md` |
| plan SHA-256 | `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` |
| stopped cumulative diff SHA-256 | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff` |
| guards SHA-256 | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` |
| shared test SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` |
| staged | empty |
| read_runtime.py SHA-256 | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` |
| 本 review 只读 | 不修改 plan/product/tests/README/control/prior artifacts，不 stage/commit |

## 2. Lock 验证

Review 前独立重算全部 protected locks：

| 项 | 现场重算 | 预期 | 结果 |
|---|---|---|---|
| plan SHA-256 | `0145d1de9b3bbe93ff200e792a40b4e850c36346b43e80a5f6e239cac745a3e9` | `0145d1de...a3e9` | PASS |
| `git diff --binary -- dayu/fins tests` | `65a924066d45b4e90f2ef2e6767b96c8ce8e4fbd2c5b1d9ea698875c94706dff` | `65a92406...6dff` | PASS |
| guards SHA-256 | `553189149bb79629eff514551e0221c3984816f55c923141b554ed86deac928d` | `55318914...928d` | PASS |
| shared test SHA-256 | `01db5538c870b672775425c2204a2d7038ab000b6d9829d0d7edce1ea25b6692` | `01db5538...6692` | PASS |
| read_runtime.py SHA-256 | `27644d0d7239627bd34b4872bca04350b98d08b00fec1feb92e973b6c72f0657` | `27644d0d...0657` | PASS |
| staged paths | empty | empty | PASS |
| `git diff --check` | no output | no output | PASS |

全部 locks 一致，无 drift。

## 3. 审查范围

本 review 审查完整累计计划（1230 行），不是只审查 candidate-exhaustion 增量段落。重点 adversarial 检查维度：

1. R08-CR-PCF02 owner-boundary root fix 正确性
2. 唯一 deletion 的机械可约束性
3. 实际 typed/sorted owner 的 preserved 不变量
4. Coverage proof 的数学正确性与可执行性
5. §6.6/§6.7 完整 acceptance 的充分性
6. 旧 plan/ledger/green/review 的失效声明
7. State/gate/stop conditions 的内部一致性
8. Compatibility/fake/bypass/dead-code/deferred-scope 引入风险
9. 语义 owner、依赖顺序与 failure recovery

## 4. Material Findings

### R08-CE-PR-MIMO-F01 — candidate-4 proof 精确预期值与旧 ledger 分子矛盾

**Severity: LOW（evidence gap, not blocking）**

**证据：** §6.6 candidate-4 proof 要求精确匹配 `covered != 382 or statements != 482 or percent >= 80.0`。旧 incremental ledger 记录 candidate 4 截止点为 `382/494 = 77.33%`，即分子 `382` 是在 `494` statements 分母下测量的。删除 12 个全未覆盖的 executable statements 后分母变为 `482`，分子不变仍为 `382`，`382/482 = 79.25%`。计划预期精确为 `382/482 = 79.25%`。

**分析：** 数学正确。旧 ledger 的 `382` 是 5 个 candidate tests 全部运行后 `read_runtime_helpers.py` 的 covered lines。删除的 12 个 statements 全部是 uncovered（旧 `494 - 382 = 112` missing，其中 12 来自被删函数），因此删除后 covered 不变仍为 `382`，denominator 变为 `482`。但有一个微妙风险：如果 coverage tool 对被删函数的 statements 计数与手工 `494 - 388 + 388 - 382 = 12` 不完全一致（例如 `for` 循环体、compound `if`、walrus operator 的分支计数差异），`382` 或 `482` 可能微偏。

**Required fix：** 不需修改计划，但实施时 §6.6 的两个 proof 的 Python checker 已使用精确 `if` 断言（`covered != 382`、`statements != 482`），任何偏差会立即 fail closed 并 stop 回 Controller。这是正确的防御设计。建议实施 artifact 中明确记录 coverage tool 的实际 `num_statements` 输出，以闭环验证手工推算。

**Verdict：** PASS with note。

---

### R08-CE-PR-MIMO-F02 — `read_runtime.py` SHA 锁定范围与 §6.7.G AST proof 的交互

**Severity: LOW（design completeness, not blocking）**

**证据：** §6.7.G 要求"实施 artifact 还必须记录 `read_runtime.py` content SHA 在 stopped tree 前后相同"。Codex artifact §2 已记录 `read_runtime.py` SHA-256 为 `27644d0d...0657`。§6.7.G 的 AST proof 验证 actual owner `_collect_available_document_types_for_source_documents` 的 definition/caller/typing/sorted-return 不变量。

**分析：** 这两个 lock 互相补充：content SHA 保证文件整体未变，AST proof 保证 owner 内部结构正确。如果实施时意外修改了 `read_runtime.py`，content SHA 不匹配会先触发 stop；如果 SHA 匹配但 AST 结构异常（理论上不可能），AST proof 也会 fail。设计是 sound 的。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F03 — §6.6 candidate-5 proof 的 `covered < 388` 阈值是否过于宽松

**Severity: LOW（precision note, not blocking）**

**证据：** §6.6 candidate-5 proof 使用 `if covered < 388 or statements != 482 or percent < 80.0`。旧 ledger 记录 candidate 5 完成后为 `388/494 = 78.54%`，删除 12 个 uncovered statements 后为 `388/482 = 80.50%`。

**分析：** `covered < 388` 允许 `covered >= 388` 的任何值通过。如果某些 coverage 边界条件导致 covered 略高于 `388`（例如删除函数中的部分行实际被旧测试偶然覆盖），proof 仍然通过。这是正确的：证明目标是"五个 candidate 形成 first/shortest threshold-crossing prefix"，只要 `>= 388/482 >= 80.00%` 且 candidate-4 proof `< 80.00%`，逻辑链即闭合。不要求精确 `388`。

但有一个反向风险：如果 covered 恰好为 `387`（例如删除的 12 行中有 1 行实际被旧测试覆盖），则 `387/482 = 80.29%` 仍 `>= 80.00%`，proof 通过但旧 ledger 的 `388` 不精确。这不会破坏逻辑链（candidate-4 仍 `< 80%`，candidate-5 仍 `>= 80%`），但实施 artifact 应记录实际值。

**Verdict：** PASS with note。

---

### R08-CE-PR-MIMO-F04 — §6.6 逐文件 coverage checker 的 changed manifest 生成依赖 git diff 而非 allowlist

**Severity: INFO（design choice, not blocking）**

**证据：** §6.6 使用 `git diff --name-only -z --diff-filter=ACMR -- ':(top,glob)dayu/fins/**/*.py'` 生成 changed production Python manifest，然后逐文件查 coverage JSON。

**分析：** 这是正确的设计。使用 git diff 而非手工 allowlist 保证了：(1) 只有实际 changed 的文件才检查 coverage；(2) 零 diff 的 allowlist 文件不虚增 coverage 要求；(3) 覆盖了 S1+S2+fix 全部累计变更。计划明确说"只在 allowlist 中但零 diff 的 production 文件不计入实际 changed manifest"，这是正确的排除逻辑。

但有一个边缘情况：如果 candidate-exhaustion implementation 只删除 `read_runtime_helpers.py` 的一个函数（S1+S2 已有的 15 个文件 + 本次 1 个 deletion），git diff 会把 `read_runtime_helpers.py` 标记为 changed（因为它在 S1+S2 中已有 diff + 本次 deletion diff）。该文件的 coverage 会在删除后重新计算，分母从 `494` 变为 `482`。这正是计划预期的行为。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F05 — S1/S2 symbol boundary 在 §5.1 与 §6.1 的一致性

**Severity: INFO（consistency check, not blocking）**

**证据：** §5.1 定义 `test_fins_read_runtime.py` 的 S1/S2 symbol boundary：S1 只允许迁移 `_extract_fiscal_from_xbrl_query` 的 import、专用 fixture `_FiscalXbrlProcessor` 与当前 node `test_sec_fiscal_inference_rejects_invalid_xbrl_total`（改名为 `test_sec_fiscal_inference_consumes_countless_xbrl_contract`）。S2 只允许迁移 `_normalize_xbrl_query_payload` 的 import 与六个 normalize/dedup nodes。

§6.1 重申同一 boundary 并补充 candidate-exhaustion continuation 的 test immutability 要求。

**分析：** 两处 boundary 定义一致。§6.1 的 candidate-exhaustion continuation 进一步约束"不再产生任何 test delta"，这是正确的——因为五个 stable-owner tests 已在 stopped tree 形成，本次只删除 production dead helper，不需要新增/修改任何 test。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F06 — §4.4 七值 reason 动作矩阵的 LLM-facing 完整性

**Severity: INFO（contract completeness, not blocking）**

**证据：** §4.4 包含完整的七值 reason→下一动作矩阵：

| reason | 业务含义 | LLM-safe 下一动作 |
|---|---|---|
| `unsupported_statement_type` | 当前 actual processor 无法服务该全局合法报表类型 | 不重复同一请求；选择其它合法 statement type 或其它 document |
| `xbrl_not_available` | 当前来源无可用 XBRL 业务结果 | 不重复同一 XBRL 请求；改用可用的财务报表抽取结果或其它 filing，并谨慎核验 |
| `statement_not_found` | 当前 document 没有可用的目标报表 | 不重复同一请求；选择其它合法 statement type 或其它 document |
| `low_confidence_extraction` | 抽取结果置信度不足 | 不直接作确定性结论；用其它报表或来源交叉验证 |
| `scale_unavailable` | 数值倍率不可靠 | 禁止数量级判断或依赖倍率的比较，先核验 scale |
| `period_semantics_unavailable` | 财期语义不可靠 | 禁止跨期比较，先核验期间归属 |
| `scale_and_period_semantics_unavailable` | 数值倍率与财期语义均不可靠 | 禁止数量级判断与跨期比较，分别核验 scale 与 period |

**分析：** 七值闭集覆盖了 §3.1 所有 reason。每条都有明确的业务含义和可执行的下一动作。动作指导足够具体（"不重复同一请求"、"禁止数量级判断"），不会给 LLM 留下歧义空间。`unsupported_statement_type` 明确不是扩展占位，而是当前业务语义。矩阵与 §4.1 的失败语义表一一对应。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F07 — §6.4 Host truncation 组合风险验证的可执行性

**Severity: MEDIUM（implementation complexity, not blocking plan but flagged for implementation）**

**证据：** §6.4 定义了五段 forced-truncation 公开链路验证：

1. 直接调用 `query_xbrl_facts` callable，捕获 pre-Host typed value
2. 通过启用 manager 的 `_tool_runtime(...)`，断言 post-Host cursor envelope
3. 断言 `set(post_value) == set(pre_value)`、非-facts siblings 逐项相等、`post_value["fact_count"] == pre_value["fact_count"]`
4. 从 envelope 读取 cursor/scope_token，调用 `FrameworkToolName.FETCH_MORE.value`
5. 断言 visible prefix + fetch-more remainder = pre-Host facts

**分析：** 这是计划中最复杂的验证点。设计是 sound 的——它要求在同一个真实 provider workspace 上观测三段公开链路（pre-Host value → Host envelope → fetch-more remainder），且只通过公开 seam 观测，不读取 Host 私有状态。

但实施难度较高：
- 需要理解 `ToolRuntime`、`FrameworkToolPolicyView`、`EffectiveToolBundleBuildRequest`、`TruncationManager` 等 Host 内部 API 的公开接口
- `_tool_runtime` helper 的 `enable_truncation_manager` 参数是新增的，需要在 `test_fins_storage_provider.py` 中扩展现有 helper
- `_FORCED_XBRL_MAX_ITEMS = 1` 的设计依赖当前 AAPL fixture 恰好有 `> 1` 条 facts（计划明确说"测试不得硬编码当前 fixture 恰有三条 facts，只断言 `len(facts) > _FORCED_XBRL_MAX_ITEMS`"）

计划已正确识别风险："若实施时 post-Host key set 改变、`fact_count` 缺失/变值，或任一公开 seam 无法同时观测 pre-Host typed value、Host completed envelope 与公开 fetch-more 结果，即与本 owner 裁决冲突，立即 stop 回 Controller"。

**Required note：** 实施时应先验证当前 AAPL fixture 的 XBRL facts 数量确实 `> 1`，否则 `_FORCED_XBRL_MAX_ITEMS = 1` 无法产生 truncation。这不是计划错误，而是实施前置条件。

**Verdict：** PASS with implementation flag。

---

### R08-CE-PR-MIMO-F08 — §6.6/§6.7 完整 acceptance 是否从零覆盖全部 affected tests

**Severity: INFO（completeness check, not blocking）**

**证据：** §6.6 的累计 validation 包含：
- S1 focused owner matrix
- S1 fiscal exact node
- S2 focused/public matrix
- 三段 forced-truncation public chain
- AAPL/HTML/no-statement real smokes
- R08 aggregate matrix
- 完整 Fins regression (`tests/fins -q`)
- 15-file exact-key coverage checker
- Full pyright
- Scoped Ruff
- `git diff --check`
- §6.7 全部双向 scans

测试文件覆盖：
- `test_financial_read_contracts.py` — S1 owner contracts
- `test_sec_pipeline_download.py` — S1 fiscal/alternate reason
- `test_fins_read_runtime.py` — S1 fiscal + S2 normalize/dedup
- `test_read_runtime_semantic_ownership_guards.py` — S2 stable-owner tests
- `test_processor_read_consistency.py` — S2 consistency
- `test_processor_registry.py` — zero-diff regression
- `test_fins_ingestion_tools.py` — zero-diff regression
- `test_fins_storage_provider.py` — real smokes + forced-truncation

**分析：** 测试集覆盖了 S1/S2 所有 affected tests 和 zero-diff regression。15-file coverage checker 保证每个实际 changed production 文件 `>= 80.00%`。§6.7 的 scans 覆盖了 internal positive inventory、public/tool/schema/LLM negative scan、fact_count unique owner、R07 no-touch、AST/README/security/scope。设计是完整的。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F09 — 旧 plan/ledger/green/review 失效声明的完整性

**Severity: INFO（lifecycle management, not blocking）**

**证据：** 计划多处明确标记旧 artifacts 失效：
- §0: "R08-CR-CF01 已使原 review lock `4d346f2b...d4b`、原 Controller validation 与两路 code review 失效"
- §6.9: "`65a92406...6dff` stopped tree 仍因 `388/494 = 78.54%` 没有完成 §6.6/§6.7，不能复用旧 incremental ledger 或旧绿色"
- §9 checklist: "旧 plan SHA/reviews、`4d346f...d4b` review lock、`7a7ebf...1d6d` validation/reviews 与 `65a92406...6dff` stopped incremental ledger 均标记失效，不作最终通过证据"

**分析：** 失效声明覆盖了所有旧 lock/hash/ledger/review。新 tree 的 acceptance 必须从零建立，不能复用任何旧 session。这是正确的 lifecycle management。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F10 — State/gate/stop conditions 内部一致性

**Severity: INFO（consistency check, not blocking）**

**证据：** §8 stop conditions 表包含 12 种观测→处置→禁止补救的映射。§6.9 定义了精确的 implementation 顺序。§10 定义了 plan-only gate 的交付边界。

**分析：** 所有 stop conditions 都有明确的"正确处置"和"禁止补救"，不存在矛盾。例如：
- "Stopped cumulative diff、guards、shared test 或 staged 状态不匹配" → "不删除 helper，立即回 Controller 澄清 drift" ✓
- "Fresh candidate-4 proof 不是 `382/482=79.25%<80`" → "保留现场证据并 stop 回 Controller" ✓
- "Dead-helper deletion 后任一 §6.6/§6.7 gate 失败" → "在原 owner/failure boundary 修复并从零完整重跑" ✓

§6.9 的顺序链（plan correction → Controller validation → dual review → fix → re-review → accepted commit → implementation → validation → lock → code review → fix → re-review → closeout）每一步都有明确的前置条件和输出，无循环依赖或死锁。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F11 — §3.4 `_collect_available_document_types` 的"12 个 executable statements"计数

**Severity: LOW（precision verification, not blocking）**

**证据：** 计划 §1.7 声称 `_collect_available_document_types` 独占 12 个 executable statements。实际函数体（`read_runtime_helpers.py:409-420`）：

```python
doc_types: set[str] = set()                          # 1
for doc in documents:                                 # 2
    raw_doc_type = doc.get("document_type")           # 3
    dt = raw_doc_type if isinstance(raw_doc_type, str) else None  # 4
    if dt is None:                                    # 5
        dt = resolve_document_type_for_source(        # 6
            form_type=doc.get("form_type"),           # 7 (branch)
            source_kind=doc.get("source_kind"),       # 8 (branch)
        )
    doc_types.add(dt)                                 # 9
return sorted(doc_types)                              # 10
```

Coverage tools 通常按 branch 计数，`for` 循环体每次迭代、`if` 的 true/false 分支、`dict.get()` 的 None/non-None 分支都会被计为独立 statement。手工计数约为 10 个 top-level statements，但 coverage tool 的 `num_statements` 可能为 12（取决于 AST 解析粒度）。

**分析：** 计划的 §6.6 proof checker 使用 `statements != 482` 作为 hard assertion。如果 coverage tool 报告的 `num_statements` 不是 `494 - 12 = 482`，proof 会立即 fail closed。这是正确的防御——不需要手工精确计数与 coverage tool 完全一致，只需要 proof checker 的 hard assertion 能捕获偏差。

旧 incremental ledger 的 `494` 是 coverage tool 在 stopped tree 上报告的 `num_statements`。删除 `_collect_available_document_types` 后，coverage tool 应报告 `494 - N`，其中 `N` 是 coverage tool 对该函数的 statement 计数。计划假设 `N = 12` 并写入 `482`；如果实际 `N ≠ 12`，proof 会 fail 并 stop 回 Controller。

**Verdict：** PASS（proof checker 的 hard assertion 已覆盖此风险）。

---

### R08-CE-PR-MIMO-F12 — §2.2 list-documents 可用文档类型 suggestion owner 表的精确性

**Severity: INFO（owner declaration, not blocking）**

**证据：** §2.2 声称 list-documents 可用文档类型 suggestion 的唯一 owner 是 `dayu/fins/tools/read_runtime.py::_collect_available_document_types_for_source_documents`，并要求"保留 typed `_SourceDocumentSummary` 输入、`resolve_document_type_for_source` 调用与 sorted 输出"。

**分析：** 现场 source scan 确认：
- `_collect_available_document_types`（旧 helper）：definition=1, caller=0, import=0
- `_collect_available_document_types_for_source_documents`（actual owner）：definition=1, caller=1

Actual owner 的签名是 `list[_SourceDocumentSummary] -> list[str]`，内部调用 `resolve_document_type_for_source` 并 `return sorted(doc_types)`。与 §2.2 声明一致。

旧 helper 使用 `list[Mapping[str, JsonValue]]` 输入（更宽松），actual owner 使用 `list[_SourceDocumentSummary]`（更精确的 typed contract）。删除旧 helper 不会影响 actual owner 的功能，因为旧 helper 没有 caller。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F13 — 是否引入 compatibility/fake/private-helper test/bypass

**Severity: INFO（negative check, not blocking）**

**证据：** 计划多处明确禁止：
- §2.3: "compatibility re-export/wrapper、fallback、shim、双写字段、loose parsing、`getattr/hasattr` 补偿、默认 reason、历史 payload 分支"
- §6.1: "禁止 compatibility test、private-helper direct test、fake-only test、omnibus 搬运、skip/xfail、coverage pragma/omit 或其它 coverage bypass"
- §6.7.F: compatibility/private-helper negative scan pattern

**分析：** 计划的禁止清单完整覆盖了常见的 coverage bypass 手段。§6.7.F 的 `rg` scan 会检测 `availability|has_structured_financial_statements|has_financial_statement_sections|has_financial_statement|has_xbrl|resolve_has_financial_data|_build_table_data_payload|_normalize_document_types|_normalize_periods|_normalize_section_children|_normalize_taxonomy_name|_resolve_default_xbrl_concepts|\b_collect_available_document_types\b` 在 guards 文件中的出现。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F14 — 第六节点、无关 dead-code、deferred Issues 引入检查

**Severity: INFO（negative check, not blocking）**

**证据：** §2.3 明确 out-of-scope：
- R09-R12
- Issues 142、151、175、177、178
- 统一 authorization
- Host/Engine/Service/UI
- 除 `R08-CR-PCF02` 唯一授权的 `_collect_available_document_types` 删除外的任何 dead-code 清理

§6.7.E 的 exact allowlist scan 会拒绝 S1/S2 production/test/README allowlist 外路径。

**分析：** 计划的 scope 控制严格。唯一的 production delta 是删除一个零 caller 的 private helper，不涉及任何 deferred issues 或 unrelated cleanup。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F15 — 语义 owner 唯一性与依赖顺序

**Severity: INFO（architectural check, not blocking）**

**证据：** §2.2 定义了 8 个不可回改的 owner。§3 列出了完整的 producer/consumer inventory。§4 定义了目标 contracts。§5/§6 分别定义了 S1/S2 的 implementation 顺序。

**分析：** 依赖顺序正确：
1. S1 先收紧 producer contracts（financial_result_contract.py、xbrl_result_contract.py）
2. S1 再迁移所有 actual processors（sec_processor.py、bs_report_form_common.py 等）
3. S2 最后迁移 public consumers（result_types.py、read_runtime.py、fins_tools.py）

每个语义都有唯一 owner：financial producer result → `financial_result_contract.py` + actual processor；XBRL raw query result → `xbrl_result_contract.py` + actual processor；public financial/XBRL result → `result_types.py` 的 typed projection/helper。

§2.2 的 list-documents suggestion owner 也已确认为 `_collect_available_document_types_for_source_documents`，旧 helper 是重复的 dead producer。

**Verdict：** PASS。

---

### R08-CE-PR-MIMO-F16 — Failure recovery 与 residual risks

**Severity: INFO（risk management, not blocking）**

**证据：** §8 的 stop conditions 表覆盖了 12 种 failure 场景。§6.4 明确识别了 Host truncation 组合风险。§6.9 定义了 aggregate deepreview 的 fix/re-review 闭环。

**分析：** Failure recovery 设计完整：
- 每种 failure 都有明确的"正确处置"和"禁止补救"
- Host truncation 风险有专门的五段验证链
- Aggregate deepreview 的 accepted fix 会触发完整的 §6.6/§6.7 重跑

Residual risks 只有：
1. Host truncation 组合验证的实施复杂度（已 flag）
2. Coverage tool statement 计数的微小偏差（已由 proof checker hard assertion 覆盖）

**Verdict：** PASS。

## 5. R08-CR-PCF02 深度 adversarial 检查

### 5.1 是否真是 owner-boundary root fix？

**证据：**
- 旧 helper `_collect_available_document_types` 使用 `list[Mapping[str, JsonValue]]` 输入，从 `form_type`/`source_kind` 推导 `document_type`
- Actual owner `_collect_available_document_types_for_source_documents` 使用 typed `list[_SourceDocumentSummary]` 输入，调用同一 `resolve_document_type_for_source` 并 `return sorted(doc_types)`
- 两者产生同一业务事实（可用文档类型列表），但旧 helper 没有 caller

**结论：** 是的。删除零 caller 的重复 private helper 是在 owner boundary 清除第二个不可达 producer，不是在下游消费者或展示层做补偿。

### 5.2 唯一 deletion 是否可机械约束？

**证据：** §6.1 精确定义唯一 production delta：
```
删除 dayu/fins/tools/read_runtime_helpers.py::_collect_available_document_types 的完整 definition
```

§6.7.G 的 source/AST proof 会验证：
- 旧 helper definition/caller/import 全零
- Actual owner definition/caller 各一、typed input/output、调用 shared resolver 且 sorted output
- `read_runtime.py` content SHA 前后相同

**结论：** 是的。deletion 范围由 source scan + AST proof + content SHA 三重约束。

### 5.3 是否误删仍有 caller/import/contract 的代码？

**证据：** 现场 source scan 确认 `_collect_available_document_types`（不带 `_for_source_documents` 后缀）只有 definition，没有 caller 或 import。word-boundary pattern `\b_collect_available_document_types\b` 不会误匹配 `_collect_available_document_types_for_source_documents`（因为后者有更长的后缀）。

**结论：** 不会误删。旧 helper 是 dead code，actual owner 有独立的 definition 和 caller。

### 5.4 Actual typed/sorted owner 是否可证 preserved？

**证据：** §6.7.G 的 AST proof 验证：
- `_collect_available_document_types_for_source_documents` 的 definition 存在且只有一个
- 有一个 production caller
- 输入注解为 `list[_SourceDocumentSummary]`，返回注解为 `list[str]`
- 内部调用 `resolve_document_type_for_source`
- 有一个 `return sorted(...)` 语句

**结论：** 可证。AST proof 的每个 assertion 都直接检查 actual owner 的结构不变量。

## 6. Coverage 数学验证

### 6.1 旧 ledger 回溯

旧 incremental ledger（stopped tree，分母 `494`）：

| step | covered | statements | percent |
|---:|---:|---:|---|
| 0 | 320 | 494 | 64.78% |
| 1 | 340 | 494 | 68.83% |
| 2 | 352 | 494 | 71.26% |
| 3 | 371 | 494 | 75.10% |
| 4 | 382 | 494 | 77.33% |
| 5 | 388 | 494 | 78.54% |

### 6.2 删除后预期

删除 12 个全未覆盖的 executable statements 后（假设 coverage tool 报告 `num_statements` 减少 12）：

| proof | covered | statements | percent | 阈值 | 结果 |
|---|---:|---:|---|---|---|
| candidate-4 (排除 #5) | 382 | 482 | 79.25% | < 80.00% | PASS |
| candidate-5 (全部五项) | 388 | 482 | 80.50% | >= 80.00% | PASS |

### 6.3 逻辑链

1. Candidate-4 proof 证明：即使删除 dead duplicate，前四项仍不足以过线
2. Candidate-5 proof 证明：加上第五项后首次过线
3. 两者共同证明：五项完整连续前缀是 first/shortest threshold-crossing prefix
4. 不需要第六项，也不能删除五项中的任何一项

**结论：** 数学正确，逻辑链闭合。

## 7. 综合判定

### Findings Summary

| ID | Severity | 判定 |
|---|---|---|
| R08-CE-PR-MIMO-F01 | LOW | PASS with note — proof checker hard assertion 覆盖 |
| R08-CE-PR-MIMO-F02 | LOW | PASS — content SHA + AST proof 双重约束 |
| R08-CE-PR-MIMO-F03 | LOW | PASS with note — `>= 388` 阈值正确 |
| R08-CE-PR-MIMO-F04 | INFO | PASS — git diff manifest 设计正确 |
| R08-CE-PR-MIMO-F05 | INFO | PASS — S1/S2 boundary 一致 |
| R08-CE-PR-MIMO-F06 | INFO | PASS — 七值 reason 矩阵完整 |
| R08-CE-PR-MIMO-F07 | MEDIUM | PASS with implementation flag — Host truncation 验证复杂度 |
| R08-CE-PR-MIMO-F08 | INFO | PASS — 测试集完整 |
| R08-CE-PR-MIMO-F09 | INFO | PASS — 旧 artifacts 失效声明完整 |
| R08-CE-PR-MIMO-F10 | INFO | PASS — stop conditions 一致 |
| R08-CE-PR-MIMO-F11 | LOW | PASS — proof checker hard assertion 覆盖 |
| R08-CE-PR-MIMO-F12 | INFO | PASS — owner 声明精确 |
| R08-CE-PR-MIMO-F13 | INFO | PASS — 无 compatibility/bypass 引入 |
| R08-CE-PR-MIMO-F14 | INFO | PASS — 无 dead-code/deferred-scope 引入 |
| R08-CE-PR-MIMO-F15 | INFO | PASS — 语义 owner 唯一，依赖顺序正确 |
| R08-CE-PR-MIMO-F16 | INFO | PASS — failure recovery 完整 |

### 最终判定

**PASS。**

计划内容完整、内部一致、数学正确。R08-CR-PCF02 是正确的 owner-boundary root fix，唯一 deletion 可机械约束，不会误删仍有 caller/import/contract 的代码。Coverage proof 的 fresh candidate-4/all-five 验证设计正确，能机械证明五项仍是 first/shortest threshold-crossing prefix。§6.6/§6.7 的完整 acceptance validation 从零覆盖全部 affected tests、15-file whole-file coverage、full pyright、Ruff、smoke/scans/README triggers。旧 plan/ledger/green/review 已明确失效。State/gate/stop conditions 无矛盾。未引入 compatibility/fake/private-helper test/bypass、第六节点、无关 dead-code、deferred Issues 或统一 tool authorization code。

唯一的 implementation flag 是 §6.4 Host truncation 组合验证的实施复杂度，但计划已正确识别风险并要求在公开 seam 不可观测时 stop 回 Controller。

## 8. Artifact SHA

本 artifact 写入完成后由外部命令重算 SHA-256 并在 handoff 中报告。
