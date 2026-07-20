# WU-SEMANTIC-OWNERSHIP-01 / R08 Aggregate Deepreview — AgentMiMo

## 1. Scope

- Mode: current changes (cumulative uncommitted R08 tree)
- Branch: `phaseflow/host-issues-control`
- Base: `b1a0631f397967e7530b676a90ef7467d83a1817^..HEAD` + working tree
- Output file: `docs/reviews/wu-semantic-ownership-01-r08-aggregate-deepreview-mimo.md`
- Included scope: 23 tracked paths（15 `dayu/fins/` Python + `dayu/fins/README.md`，6 `tests/fins/` Python + `tests/README.md`）
- Excluded scope: none (immutable tree locked)
- Parallel review coverage: 使用 Explore agents 读取 R08 artifacts 与 control documents 摘要；所有 finding 判定、severity 裁决与最终 verdict 由主 reviewer 独立完成

## 2. Lock Verification

| Lock | Expected | Actual | Status |
|---|---|---|---|
| Cumulative `git diff --binary -- dayu/fins tests` SHA-256 | `01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d` | `01c2a1d51e4ed048da84331bb9a2bc2613f270c8cb1863d0ad9a641a25f3092d` | ✅ MATCH |
| Tracked paths | 23 | 23 | ✅ MATCH |
| Staged | empty | empty | ✅ MATCH |
| Guards SHA（`tests/fins/test_read_runtime_semantic_ownership_guards.py` 单文件 SHA-256） | `44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a` | `44d9eaadcba006ef5df815a5906e7d590c712b7e991d09916944df5c8f83471a` | ✅ MATCH |
| Controller code re-review adjudication SHA | `9fb0afe89ff73207f895b9a540133fbecdc0bde799248092b24991f825a8f82e` | `9fb0afe89ff73207f895b9a540133fbecdc0bde799248092b24991f825a8f82e` | ✅ MATCH |

全部 lock 核验通过。Controller adjudication SHA 从 `a56183bd...` 更新为 `9fb0afe8...`，系 DS artifact 三处行尾空格 normalization（artifact-only），产品 immutable diff `01c2a1d5...092d` 不变、verdict 不变。

## 3. Independent Verification Results

| Gate | Result |
|---|---|
| pyright (dayu/fins) | 0 errors, 0 warnings, 0 informations |
| pytest guards (24 cases) | 24 passed |
| pytest contracts (111 cases) | 111 passed |
| pytest full Fins (860 cases) | 859 passed, 1 skipped (existing Docling skip) |
| pytest remaining test files (201 cases) | 201 passed |
| `StatementLocator` references | 零命中 |
| `build_statement_locator` references | 零命中 |
| `statement_method_missing` / `statement_empty` | 零命中 |
| `deduped_fact_count` | 零命中 |
| `total` in XBRL result contracts | 零命中 |
| `_collect_available_document_types` | 零命中（定义/调用/import 全零） |
| `_normalize_concepts_for_query` | 零命中 |
| `_build_financials_payload` / `_FinancialStatementProcessor` | 零命中 |
| `type: ignore` / `pyright: ignore` in R08 files | 零命中 |

## 4. Finding Closure Verification

| Finding | Expected Status | Evidence |
|---|---|---|
| `R08-CR-CF01` | 已修复 | guards test 四个 generic/compat nodes 删除，九 imports/symbols 零命中 |
| `R08-CR-PCF02` | 已修复 | `_collect_available_document_types` 定义/调用/import 全零；actual typed/sorted owner 定义/调用 各一 |
| `R08-CR-PCF03` | 已修复 | candidate 6 public resolver test/import/三断言精确保留，无 bypass/padding |
| `R08-CR-PCF04` | 已修复 | prefix-five `387/485`、fresh prefix-six `391/485` 与 `[344,346,348,442]` 一致 |
| `R08-VAL-PY-F01` | 已修复 | optional public keys 先做 `"..." in result` membership proof |
| `R08-VAL-PY-F02` | 已修复 | test processor constructor 对 protocol-valid calls 可调用（taxonomy optional default） |
| `R08-VAL-PY-F03` | 已修复 | test-local XBRL success TypeGuard 只按必有 public field 收窄 |

## 5. Adversarial Failure Pass

### 5.1 Semantic Ownership Drift Check

**Financial result contract ownership:**
- `FinancialStatementResult` TypedDict 定义在 `financial_result_contract.py`（owner）
- `validate_financial_statement_result_payload` 在 owner 模块校验
- `project_financial_statement_result` 在 `result_types.py` 投影（read-side 单一出口）
- 所有 processors 直接构造 `FinancialStatementResult` 字面量并通过 `_validate_exact_keys` 校验键集
- read runtime 不再手动组装字典，改为调用 `project_financial_statement_result`
- **结论：无 drift。** producer 产、校验器验、投影器投，三者边界清晰。

**XBRL result contract ownership:**
- `XbrlFactsResult` TypedDict 定义在 `xbrl_result_contract.py`（owner）
- `validate_xbrl_facts_result_payload` 在 owner 模块校验
- `project_xbrl_query_result` 在 `result_types.py` 投影
- `fact_count` 唯一赋值在 `project_xbrl_query_result` 的 `len(returned_facts_copy)`
- `XbrlQueryParams` TypedDict 在 owner 模块定义，扁平可选字段
- **结论：无 drift。** `total` 和 `deduped_fact_count` 已完全移除，`fact_count` 是唯一公共计数。

**Reason ownership:**
- `FinancialStatementReason` 封闭 7 值（删除 `statement_method_missing` 和 `statement_empty`）
- 所有 processors 统一使用 `statement_not_found` 替代旧的三个 reason
- `REPORT_FORM_HTML_FALLBACK_REASONS` 更新为 typed `frozenset[FinancialStatementReason]`
- LLM-facing description 列出全部 7 个 reason 及其安全动作
- **结论：无 drift。** reason 收窄且统一。

### 5.2 Overcoupling Pass

**`_validate_exact_keys` 重复定义:**
- `financial_result_contract.py` 和 `xbrl_result_contract.py` 各有一份私有 `_validate_exact_keys`
- 两者逻辑完全相同（frozenset 差集校验）
- 两个模块各自是独立的领域 owner，函数为模块私有（`_` 前缀）
- 提取到公共模块会引入跨 owner 的共享依赖
- **判定：非 finding。** 模块私有辅助函数在各自 owner 内重复是可接受的；提取反而引入不必要的耦合。

**Processor 共享 terminal:**
- `BsTenKFormProcessor`、`BsTenQFormProcessor`、`BsTwentyFFormProcessor` 均继承 `_BaseBsReportFormProcessor`
- 测试显式验证 `issubclass` 关系
- `_BaseBsReportFormProcessor._get_statement_from_xbrl` 统一使用 `statement_not_found`
- **结论：无 overcoupling。** 继承是合理的 terminal owner 共享。

**Read runtime → domain 依赖:**
- `read_runtime.py` 导入 `project_financial_statement_result`（from result_types）
- `read_runtime_helpers.py` 导入 `PublicXbrlQueryResult` 和 `project_xbrl_query_result`（from result_types）
- 不直接导入 domain 校验器
- **结论：依赖方向正确。** read runtime 通过 result_types 投影，不穿透到 domain 校验。

### 5.3 Adversarial Failure Scenarios

**Scenario 1: Producer 返回未知字段**
- `_validate_exact_keys` 会抛 `ValueError("包含未知字段: ...")`
- 测试 `test_financial_validator_rejects_unknown_fields_and_reason` 覆盖
- **结论：fail closed。**

**Scenario 2: reason=null 显式传入**
- `_optional_financial_reason` 检测 `"reason" in payload` 后要求非 null
- 测试 `{"reason": None}` → `"不得使用 null"` 覆盖
- **结论：fail closed。**

**Scenario 3: XBRL query_params 含未知过滤条件**
- `_XBRL_QUERY_PARAM_REQUIRED_KEYS` 和 `_XBRL_QUERY_PARAM_OPTIONAL_KEYS` 定义闭集
- 测试 `test_xbrl_validator_rejects_unknown_result_and_query_param_fields` 覆盖
- **结论：fail closed。**

**Scenario 4: XBRL min_value/max_value 传入 bool**
- `_optional_number` 检测 `isinstance(value, bool)` 并抛出
- 测试 `test_xbrl_validator_rejects_non_contract_filter_values` 覆盖
- **结论：fail closed。**

**Scenario 5: fiscal_period 传入非精确值（如 "fy"）**
- `_optional_fiscal_period` 要求 `value in FISCAL_PERIODS`（精确大写匹配）
- 测试 `"fy"` → `"fiscal_period 非法"` 覆盖
- **结论：fail closed。**

**Scenario 6: R07 snapshot/citation 被意外修改**
- R08 diff 不包含 `snapshot`、`citation` lifecycle 相关代码变更
- `result_types.py` 中 citation 类型从 `dict[str, Any]` 收窄为 `dict[str, JsonValue]`（更严格）
- **结论：no regression。**

## 6. Combination Behavior Verification

### 6.1 S1+S2 组合

- S1 收窄 financial/XBRL producer contract（删除 `StatementLocator`、`total`、旧 reason）
- S2 添加 typed public projection（`PublicFinancialStatementResult`、`PublicXbrlQueryResult`）
- S2 删除旧 tools types（`FinancialStatementResult`、`XbrlQueryResult`、`XbrlQueryParams` from result_types）
- S1+S2 组合后：producer 产窄 contract → domain 校验 → result_types 投影 → read runtime 返回
- **无冲突。**

### 6.2 Code-Review Corrections

- R08-CR-CF01: 删除 guards test 中四个 generic/compat nodes
- R08-CR-PCF02: 删除死代码 `_collect_available_document_types`
- R08-CR-PCF03: 精确保留 candidate 6 public resolver test
- R08-CR-PCF04: prefix-six coverage 精确到行

### 6.3 Candidate Exhaustion

- 旧 reason 值（`statement_method_missing`、`statement_empty`）已从类型、常量集、所有 processor 返回值和测试中完全移除
- `REPORT_FORM_HTML_FALLBACK_REASONS` 同步更新

### 6.4 Prefix-Six Exact Drift

- Guards test 文件是唯一在 pyright fix 阶段修改的文件
- 22 个非 guards 路径内容 hash 未变
- Guards test 24 cases 全部通过

### 6.5 Pyright Test-Owner Fix

- R08-VAL-PY-F01: membership proof 替代直接索引
- R08-VAL-PY-F02: test-only optional keyword default
- R08-VAL-PY-F03: test-local TypeGuard
- pyright 0 errors 确认

## 7. Design Consistency Audit

### 7.1 Topic 6 Ownership Boundaries

| Boundary | Status | Evidence |
|---|---|---|
| 6.1 Single Explicit Transaction Owner | N/A (no storage changes in R08) | — |
| 6.2 Source Meta / Staging | N/A (no ingestion changes in R08) | — |
| 6.3 Provenance/Revision/Typed Errors | PASS | citation 类型收窄为 `dict[str, JsonValue]`；typed errors 不变 |
| 6.4 Minimal LLM-Facing Contract | PASS | 7 required fields + optional reason；self-contained description |
| 6.5 Single Direct-Stream Terminal Validator | N/A（deferred to R09） | R08 无 Service/CLI/direct-stream 代码变更；processor `statement_not_found` 是 producer-level reason 统一，不是 Topic 6.5 的 direct-stream `RESULT` 终态验证器；本树未偷带或形成重复 validator |
| 6.6 HKEX Cumulative Pagination | N/A (no HKEX changes in R08) | — |
| 6.7 Containment / Opaque ID | N/A (no storage changes in R08) | — |

### 7.2 LLM-Facing Contract Narrowing

- `statement_locator` 完全移除（producer 不再产生，read runtime 不再投影）
- `reason` 从 required nullable 改为 `NotRequired`（缺席 vs null 语义区分）
- XBRL `total` 移除，`fact_count` 是唯一公共计数
- `deduped_fact_count` 移除
- `query_params` 从 `dict[str, JsonValue]` 收窄为 typed `XbrlQueryParams`
- `fiscal_period` 在 tool schema 中添加 `enum` 约束

### 7.3 No Compat Shim / No Downstream Repair

- 零 `hasattr`/`getattr` 用于逃逸类型检查（R08 变更范围内）
- 零 `cast` 用于绕过类型系统（domain 中的 `cast` 均在验证后合法收窄）
- 零 fallback / 特例 / 兼容分支
- 零 `type: ignore` / `pyright: ignore`

## 8. Security / No-Code / Deferred Boundaries

- Topic 8: Engine generic exception 240 字符硬编码、脱敏与截断后缀保留；R08 无 Engine delta
- Topic 9: 统一 tool authorization framework 未实现；无 R08 scope creep
- Containment/symlink/DNS/peer/resource budget/atomic write/process fencing 未弱化
- R07 snapshot/citation lifecycle 未触碰
- R09-R12 与 Issues 142/151/175/177/178 未偷带

## 9. README Consistency

- `dayu/fins/README.md` 已更新：移除 `statement_locator`、`total`、`deduped_fact_count`、旧 reason 描述；添加 typed projection 和 `fact_count` 说明
- `tests/README.md` 已更新：添加 Financial/XBRL contract 测试覆盖说明
- README 内容与当前代码一致

## 10. Artifact-to-Code Evidence Chain Audit

| Artifact Claim | Code Evidence |
|---|---|
| `fact_count` single assignment at `result_types.py:401` | ✅ `fact_count=len(returned_facts_copy)` 在 `project_xbrl_query_result` |
| `StatementLocator` fully removed | ✅ 零引用（grep 确认） |
| 7 actionable reasons | ✅ `_FINANCIAL_STATEMENT_REASONS` frozenset 含 7 值 |
| `XbrlDataQuality = Literal["xbrl", "partial"]` | ✅ `xbrl_result_contract.py:17` |
| `_validate_exact_keys` rejects unknown fields | ✅ 测试覆盖 |
| `NotSupportedResult` unchanged | ✅ `result_types.py:78` 仍为 `total=False` |
| processors use `FinancialStatementResult(...)` typed construction | ✅ 所有 processor diff 确认 |

## 11. Findings

未发现实质性问题。

## 12. Open Questions

无。

## 13. Residual Risk

1. **Docling 集成**: Issue 175 跟踪；当前 1 skip 为已有环境限制。
2. **`edgar` 依赖警告**: 三个 DeprecationWarning 为已有第三方库警告，不影响退出码。

## 14. Verdict

**PASS / ZERO_ACCEPTED_FINDING / ZERO_MATERIAL_DEFECT**

R08 cumulative 23-path diff 正确实现 controller 裁决的最小契约。所有 accepted findings 已关闭，无 regression，无 semantic ownership drift，无 overcoupling，无 LLM-facing 违规，无 compat shim，无下游修复。

Review verdict 不授权 commit。
