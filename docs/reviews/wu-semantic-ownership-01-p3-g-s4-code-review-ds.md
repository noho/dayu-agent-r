# Code Review — WU-SEMANTIC-OWNERSHIP-01 P3-G S4

## Scope

- Mode: current changes (unstaged)
- Branch: `phaseflow/host-issues-control`
- Slice: P3-G S4 — XBRL processor result contract and read runtime consumption
- Output file: `docs/reviews/wu-semantic-ownership-01-p3-g-s4-code-review-ds.md`
- Included scope: 7 files + 1 new (+198/-16)
- Validation: `pytest` 82 passed, `pyright` 0 errors, coverage 80%

## Verdict

**PASS** — 无 material finding。S4 正确将 XBRL facts `total` 所有权从 read runtime 回到 processor contract。Validator 在 `dayu.fins.domain` 作为轻量 contract owner，read runtime 和 fiscal inference 两个 direct consumers 均在 normalization/dedup 前先校验 raw contract。`total` 不再被覆盖。

---

## Findings

未发现实质性问题。

---

## Review Focus 逐项核实

### 1. XBRL `total` owner boundary 正确

| 层 | Owner | 实现 | 证据 |
| --- | --- | --- | --- |
| Producer | `sec_processor.py` / `bs_report_form_common.py` | 返回 raw `facts` + `total=len(facts)` | 未修改（S4 不碰 producer） |
| Validator | `dayu.fins.domain.xbrl_result_contract` | `validate_xbrl_facts_result_payload` 校验 raw contract | `xbrl_result_contract.py:29-56` |
| Consumer (read runtime) | `_normalize_xbrl_query_payload` | 先 validate → 再 normalize/dedupe → 保留 `validated.total` | `read_runtime_helpers.py:1393-1414` |
| Consumer (fiscal inference) | `_extract_fiscal_from_xbrl_query` | 先 validate → 再读 facts | `sec_fiscal_fields.py:494-498` |
| Projection | `XbrlQueryResult` TypedDict | `total` = processor truth; `deduped_fact_count` = derived | `result_types.py:299-304` |

### 2. Read runtime 不再在 validation 前过滤/覆盖 raw facts/total

`_normalize_xbrl_query_payload` 的执行顺序（`read_runtime_helpers.py:1393-1414`）：

1. `validated = validate_xbrl_facts_result_payload(payload)` — raw contract 校验
2. `query_params = dict(validated.query_params)` — 只对 query_params 补充 concepts
3. `for index, raw_fact in enumerate(validated.facts)` — 在 validated facts 上 normalize/dedupe
4. `normalized_payload["total"] = validated.total` — 保留 processor raw total
5. `if len(deduped_facts) != validated.total: deduped_fact_count` — 仅在需要时加派生字段

**旧代码**（已删除）：
```python
normalized_payload["total"] = len(deduped_facts)  # 覆盖 processor total
```

**新代码**：
```python
normalized_payload["total"] = validated.total  # 保留 processor truth
```

Source scan 确认：`rg "\"total\": len\(deduped_facts\)" dayu/fins tests/fins` → **零命中**。✅

### 3. Validator 位于正确的 owner boundary

`dayu/fins/domain/xbrl_result_contract.py` 的依赖：
- `dayu.contracts.json_value.JsonValue` — public contract
- `dayu.fins.domain.filing_semantics.FinancialDataQuality` / `normalize_financial_data_quality` — 同 domain 层
- `dataclasses`, `collections.abc.Mapping`, `typing.Optional` — 标准库

**无依赖** processor、pipeline、storage 或 tools。✅

这个位置是 `dayu.fins.domain` 而非 `dayu.fins.processors`，原因正确：
- processor 是 producer，domain 是 contract 真源
- validator 放在 domain 层，允许 read runtime（tools 层）和 fiscal inference（pipeline 层）两个不同层的 consumer 都消费同一契约
- `dayu.fins.processors` 是重型 package（含 SEC processing 逻辑），validator 不需要 processor 依赖

### 4. Fiscal inference consumer 行为正确

`_extract_fiscal_from_xbrl_query`（`sec_fiscal_fields.py:494-498`）变更：

**旧代码**:
```python
facts = query_result.get("facts")
if not isinstance(facts, list):
    return None, None
```

**新代码**:
```python
try:
    validated_query_result = validate_xbrl_facts_result_payload(query_result)
except ValueError:
    return None, None
facts = validated_query_result.facts
```

- 旧行为：`facts` 字段缺失或非 list 时返回 `(None, None)`（静默 best-effort）
- 新行为：整个 raw contract 校验（包括 `total`、`query_params`、`facts` 类型）失败时返回 `(None, None)`
- 这比旧的只检查 `facts is list` 更强——现在也拒绝 `total` 违约、`query_params` 非 object
- `return (None, None)` 保留 best-effort 语义：fiscal inference 是对 processor result 的增强读取，不因为 contract 违约而崩溃。与原行为一致：坏数据 → 不推断 fiscal fields。✅

### 5. `deduped_fact_count` 设计与 LLM-facing 清晰性

| 字段 | 含义 | 何时存在 |
| --- | --- | --- |
| `total` | Processor raw `total` — XBRL 查询返回的 business total | 始终存在 |
| `deduped_fact_count` | Read runtime dedup 后的展示数量 | 仅当 `len(deduped_facts) != validated.total` 时存在 |

- `deduped_fact_count` 只在值不同时出现——无冗余。当 dedup 不减少数量时，字段被显式 `pop` 掉（行 1414）。
- 命名 `deduped_fact_count` 清晰表达"去重后的 fact 数量"，不是 `total` 的同义词或替代。LLM 不会混淆。
- 在 `XbrlQueryResult` TypedDict 中标记为 `NotRequired`（`total=False`），类型安全。

### 6. 测试矩阵

| 场景 | 预期 | 测试文件 |
| --- | --- | --- |
| Missing `total` | `ValueError` fail closed | `test_fins_read_runtime.py` |
| Non-int `total`（string） | `ValueError` fail closed | `test_fins_read_runtime.py` |
| Raw `total != len(raw_facts)` | `ValueError` fail closed | `test_fins_read_runtime.py` |
| Valid raw `total` preserved after dedup | `total` 不变，`deduped_fact_count` ≤ `total` | `test_fins_read_runtime.py` |
| Dedupe shrink → `deduped_fact_count` present | 派生字段出现 | `test_fins_read_runtime.py` |
| No dedupe → no `deduped_fact_count` | 派生字段不出现 | `test_fins_read_runtime.py` |
| Fiscal inference consumer rejects bad contract | 返回 `(None, None)` | `test_fins_read_runtime.py` |
| Cancellation test processor obeys raw `total` contract | 更新 `_XbrlFactsProcessor` | `test_fins_storage_provider.py` |

### 7. S4 未越界

| Slice | 行为 | S4 状态 |
| --- | --- | --- |
| S1 SEC form parser | — | ❌ 未修改（仅复用 `normalize_financial_data_quality`） |
| S2 CN/HK report selection | — | ❌ 未修改 |
| S3 rejection registry | — | ❌ 未修改 |
| Processor producer 逻辑 | `sec_processor.py` / `bs_report_form_common.py` | ❌ 未修改（只加 contract 校验在 consumer 侧） |
| Tool schema / LLM-facing prompt | — | ❌ 未修改 |

---

## Owner Boundary Assessment

```
Processor (producer)
  │  query_xbrl_facts() → raw payload
  ▼
Domain validator (xbrl_result_contract.py)
  │  validate_xbrl_facts_result_payload(payload)
  │  → ValidatedXbrlFactsResult (total, facts, query_params, data_quality, reason)
  ├──► Read runtime consumer
  │      _normalize_xbrl_query_payload → deduped facts, total preserved
  │      → LLM-facing XbrlQueryResult (total + optional deduped_fact_count)
  └──► Fiscal inference consumer
         _extract_fiscal_from_xbrl_query → validated.facts
         → (fiscal_year, fiscal_period) or (None, None)
```

---

## Adversarial Failure Pass

- **`total` 缺失**: `_required_json_int` — `payload.get("total")` 返回 `None` → `isinstance(None, int)` → `False` → `ValueError` ✅
- **`total` 为 bool**: `isinstance(True, int)` is True, but `isinstance(value, bool)` gate catches it → `ValueError` ✅
- **`total` 为负**: `value < 0` → `ValueError` ✅
- **`facts` 缺失**: `_required_json_list` → `ValueError` ✅
- **`total != len(facts)`**: explicit check line 46-47 → `ValueError` ✅
- **`query_params` 非 object**: `_required_json_object` → `ValueError` ✅
- **`query_params` keys 非 str**: `_required_json_object` loop check → `ValueError` ✅
- **`data_quality` 存在但非法**: `_optional_financial_data_quality` → `normalize_financial_data_quality` → `ValueError` ✅
- **`deduped_fact_count` 与 `total` 相等时不出现**: `pop("deduped_fact_count", None)` → ✅
- **旧 `dict(payload)` copy 遗留 `deduped_fact_count`**: `pop` 清理 → ✅

## Residual Risk

- **Coverage 刚好 80%**: `xbrl_result_contract.py` 单文件覆盖率为 80%，刚好满足门檻。未覆盖所有 ValueError 消息分支。
- **Processor 非 JSON payload**: 若未来 processor 返回非 dict 类型，`cast(dict[str, JsonValue], ...)` 会在调用 validator 前崩溃。当前所有 processor 均返回 dict，但 `cast` 不提供运行时保护。这不属于 S4 scope（plan 未要求扩展 processor invocation type system）。
