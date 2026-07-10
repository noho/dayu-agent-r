# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-G S4

## Scope

- Mode: current changes (unstaged workspace diff)
- Branch: `phaseflow/host-issues-control`
- Base: `22683a8e` (S3 accepted commit)
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-s4-code-review-mimo.md`
- Included scope: 7 files (+198/-16) — S4 XBRL processor result contract and read runtime consumption
- Excluded scope: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`

## Findings

未发现实质性问题。

逐项检查：

### 1. XBRL facts `total` owner boundary 正确

**Producer**: `sec_processor.py:722-726` 和 `bs_report_form_common.py:330` 的 `query_xbrl_facts(...)` 返回 `total=len(facts)`。未修改。✅

**Validator**: `dayu.fins.domain.xbrl_result_contract.validate_xbrl_facts_result_payload(...)`：
- `query_params` 必须为 object（key 为字符串）。
- `facts` 必须为 list。
- `total` 必须为非 bool 整数、≥ 0。
- `total == len(facts)`（raw total 与 raw facts 数量一致）。
- 可选 `data_quality` 复用 `normalize_financial_data_quality(...)`。
- 可选 `reason` 必须为非空字符串。
- 位于 `dayu.fins.domain`，只依赖标准库和 domain `filing_semantics`。✅

**Consumer**:
- `_normalize_xbrl_query_payload(...)` 先调 `validate_xbrl_facts_result_payload(payload)`，再做 fact normalization / dedupe。
- `_extract_fiscal_from_xbrl_query(...)` 先调 `validate_xbrl_facts_result_payload(query_result)`，失败返回 `(None, None)`。✅

### 2. Read runtime 不在 validation 前过滤/dedupe/覆盖

- `_normalize_xbrl_query_payload(...)` 第一步调 `validate_xbrl_facts_result_payload(payload)`。
- `validated.facts` 作为 raw facts 源；`validated.total` 作为 processor-owned total。
- Fact normalization / dedupe 在 validation 之后。
- `normalized_payload["total"] = validated.total`（保留 processor raw total，不重算）。
- `deduped_fact_count` 仅在 `len(deduped_facts) != validated.total` 时设置。✅

### 3. Validator 位于 `dayu.fins.domain` 轻量 contract

`xbrl_result_contract.py` 只 import：
- `collections.abc.Mapping`
- `dataclasses.dataclass`
- `typing.Optional`
- `dayu.contracts.json_value.JsonValue`
- `dayu.fins.domain.filing_semantics`（`FinancialDataQuality`、`normalize_financial_data_quality`）

不 import `dayu.fins.processors`、`dayu.fins.tools` 或任何重型包。✅

### 4. `sec_fiscal_fields` fail closed

`_extract_fiscal_from_xbrl_query(...)` 对 invalid total fail closed 为 `(None, None)`：
```python
try:
    validated_query_result = validate_xbrl_facts_result_payload(query_result)
except ValueError:
    return None, None
```
这是正确行为——fiscal inference 是可选的，不应掩盖 processor contract violation。旧代码对坏 `facts` 也返回 `(None, None)`，语义一致但更强（现在对坏 `total` 也 fail closed）。✅

### 5. `deduped_fact_count` 命名清晰

- `result_types.py:302`：`deduped_fact_count: int` 作为 `XbrlQueryResult` 可选字段。
- 仅在 `len(deduped_facts) != validated.total` 时设置；否则 `pop`。
- 不冒充 processor raw `total`。✅

### 6. 测试覆盖

| 测试 | 场景 | 断言 |
|---|---|---|
| `test_xbrl_query_payload_missing_total_fails_closed` | 缺少 `total` | `ValueError("total 必须为整数")` |
| `test_xbrl_query_payload_non_int_total_fails_closed` | 非 int `total` | `ValueError("total 必须为整数")` |
| `test_xbrl_query_payload_mismatched_raw_total_fails_closed_before_dedup` | `total=1` + 2 facts | `ValueError("total 必须等于 raw facts 数量")` |
| `test_xbrl_query_payload_preserves_processor_total_after_dedup` | `total=2` + 2 dup facts | `total==2`, `deduped_fact_count==1`, `len(facts)==1` |
| `test_sec_fiscal_inference_rejects_invalid_xbrl_total` | `total=0` + 1 fact | `(None, None)` |
| `test_fins_storage_provider.py` | XBRL cancellation fixture | 加 `"total": len(facts)` 合规 |

Coverage: `xbrl_result_contract.py` 80%（≥80% 阈值）。✅

### 7. S1/S2/S3 语义未改变

- S1 SEC form parser：未修改。
- S2 CN/HK report selection：未修改。
- S3 rejection registry：未修改。✅

### 8. Tests、pyright、README

- **Tests**: 82 passed, 3 warnings。
- **Pyright**: 0 errors。
- **Coverage**: `xbrl_result_contract.py` 80%。
- **Source scan**: 无 `"total": len(deduped_facts)`；`normalized_payload["total"] = validated.total` 是保留 processor raw total。
- **README**: 记录 XBRL facts processor result contract 稳定 owner 和 read runtime consumption 规则。✅

## Residual Risk

- `xbrl_result_contract.py` 覆盖率刚好 80%，未覆盖所有错误消息分支。
- 若第三方 processor 返回非 JSON payload，当前按既有 cast 边界进入 validator；本 slice 不扩展 processor invocation type system。

## Verdict

**PASS** — S4 正确实现了 plan 中的 XBRL processor result contract and read runtime consumption。Validator 位于 `dayu.fins.domain` 轻量 contract，read runtime 和 fiscal inference 都在 validation 后才处理 raw payload，processor-owned `total` 不被覆盖，`deduped_fact_count` 是清晰的派生字段。
