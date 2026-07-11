# Targeted Rereview — WU-SEMANTIC-OWNERSHIP-01 Round2 Batch E1

## Scope

- **Mode**: current changes（targeted rereview，仅验证 accepted findings 是否关闭，不审全量 diff）
- **Branch**: `phaseflow/host-issues-control`
- **Base**: `main`
- **Output file**: `docs/reviews/wu-semantic-ownership-01-round2-batch-e1-rereview-ds.md`
- **Included scope**: 上一轮 E1 review 中 5 项 accepted findings 的修复路径及可能受影响的邻近代码
- **Excluded scope**: Controller 已拒绝/延期的项（`_ProcessorFinancialStatementPayload data_quality/reason`、`_iter_sections Any`、broad Any、`wait_adapter`），除非修复引入新直接 bug
- **Parallel review coverage**: 无

### 验证的 5 项 Accepted Findings

| # | Finding | 严重程度 | 状态 |
|---|---------|---------|------|
| 1 | source meta cache key 缺 source_kind | 中 | 已修复 |
| 2 | `_parse_source_document_meta` bool 非 bool 静默转 False | 中 | 已修复 |
| 3 | `_normalize_json_scalar_text` 双 owner | 中 | 已修复 |
| 4 | `get_financial_statement` rows 非 list 未 fail loud | 低 | 已修复 |
| 5 | guard tests brittle string-scan / private-field access | 低 | 已修复 |

---

## Evidence Per Accepted Finding

### Finding 1 — source_kind cache partition 修复验证

**修复位置**: `read_runtime.py:2207-2234` (`_get_source_meta_cached_by_kind`)

**Cache key 结构**:
```python
cache_key = ProcessorCacheKey(ticker=ticker, document_id=document_id, source_kind=source_kind.value)
```

**验证结论**:
- `source_kind` 已纳入 `ProcessorCacheKey`，不同 source_kind 的同 (ticker, document_id) 不会互相污染。
- `_processor_cache`（`ProcessorLRUCache[DocumentProcessor]`，line 589）与 `_meta_cache`（`ProcessorLRUCache[_CachedSourceDocumentMeta]`，line 592）是两个独立的 LRU 实例，不存在跨缓存污染。
- `_get_document_meta_cached`（line 2249）仍使用无 source_kind 的 `ProcessorCacheKey(ticker=ticker, document_id=document_id)`，但因其 `source_kind=None`，与 `_get_source_meta_cached_by_kind` 的带 source_kind 的 key 不冲突。两者在同一次 cache 命中/未命中场景下各自独立。
- 测试 `test_read_runtime_source_meta_cache_is_partitioned_by_source_kind`（test file line 636-669）验证：同一 (AAPL, doc-1) 在 FILING 和 MATERIAL 下分别命中各自的 meta 且各自只触发一次 `get_source_meta` 调用。

**不误伤 processor cache**: 确认。

---

### Finding 2 — bool 缺省 vs 错类型 修复验证

**修复位置**: `read_runtime.py:379-399` (`_read_bool_meta_field`)

**逻辑**:
```python
if field_name not in raw_meta:
    return default                  # 缺省 → storage contract 默认值
value = raw_meta[field_name]
if isinstance(value, bool):
    return value                    # 显式 bool → 原值
raise ValueError(...)               # 存在但非 bool → fail loud
```

**验证结论**:
- **缺省**：字段不存在时返回 storage contract 默认值（`ingest_complete=True`, `amended=False`, `is_deleted=False`）。测试 `test_parse_source_document_meta_preserves_bool_and_defaults` 验证：传入 `{"amended": True, "is_deleted": False}` 时 `ingest_complete` 取默认值 `True`。
- **错类型**：字段存在但非 bool（int 1、str "false"、None）时 raise `ValueError`，不再静默转换。测试 `test_parse_source_document_meta_rejects_non_bool_fields` 参数化覆盖三种非 bool 输入。
- **符合 storage contract**：storage 应始终写入 Python `bool`；若写入 `int 1` 则属于 storage bug，应在 ingestion 层修复而非在 read runtime 层静默兼容。`_read_bool_meta_field` 的 fail-loud 设计正确。

**无回归**。

---

### Finding 3 — `_normalize_json_scalar_text` 双 owner 修复验证

**证据**:
```bash
$ grep -n 'def _normalize_json_scalar_text' dayu/fins/tools/read_runtime.py dayu/fins/tools/read_runtime_helpers.py
dayu/fins/tools/read_runtime_helpers.py:437:def _normalize_json_scalar_text(...)
```
- `read_runtime.py:97` 从 `read_runtime_helpers` import `_normalize_json_scalar_text`。
- `read_runtime.py` 中已无本地定义。
- 唯一真源位于 `read_runtime_helpers.py:437`。

**无回归**。

---

### Finding 4 — rows ValueError 修复验证

**修复位置**: `read_runtime.py:1639-1641`

```python
rows = statement_payload.get("rows")
if not isinstance(rows, list):
    raise ValueError("processor get_financial_statement result rows must be list")
```

**验证结论**:
- `statement_payload.get("rows")` 对缺失键返回 `None` → `isinstance(None, list)` → `False` → ValueError。
- 非 list 类型（如 dict）同样触发 ValueError。
- 正常 list（含空 list `[]`）正常通过。
- 测试 `test_get_financial_statement_rejects_missing_or_non_list_rows` 覆盖 `{}` 和 `{"rows": {"unexpected": "dict"}}` 两个非 list 场景。
- 测试 `test_get_financial_statement_accepts_list_rows` 验证空 rows 正常路径：`rows == []` 且 `statement_locator` 默认构造正确。

**不破坏正常 result**：确认。

---

### Finding 5 — AST guard 稳定性验证

**修复位置**: `tests/fins/test_read_runtime_semantic_ownership_guards.py`

**变更要点**:

| 维度 | 旧实现（brittle） | 新实现（AST） |
|------|-------------------|--------------|
| `getattr(processor` 检测 | 字符串 `not in` | `ast.walk` + `ast.Call` + `ast.Name("getattr")` 精确匹配 |
| 返回类型 `list[dict[str, Any]]` | 字符串片段匹配 | `ast.FunctionDef.returns` → `ast.unparse()` 规范化比对 |
| 参数弱类型 (`object`/`Any`) | 精确字符串匹配 | `ast.FunctionDef.args` → `_annotation_text` → 规范化比对 |
| `_meta_cache` 直接访问 | `runtime._meta_cache.size()` / `.keys_snapshot()` | **无**——改用 `_get_document_meta_cached` + 计数仓储 |

**AST 稳定性分析**:
- `ast.unparse()` 产出 Python 标准库规范化的源码文本，不因空格、换行、注释变化而改变。
- `ast.walk` 遍历 AST 节点不受格式化影响。
- `_getattr_processor_call_lines` 精确匹配 `getattr(processor, ...)` 而非 `"getattr(processor" in source`，不会因注释或字符串字面量中出现的字样而误报。

**不访问 `_meta_cache`**: 确认。`test_read_runtime_source_meta_cache_is_bounded`（line 612-633）仅通过 `_get_document_meta_cached` 公共接口和 `_CountingSourceRepository.get_source_meta_calls` 计数器验证缓存有界行为，无任何 `_meta_cache` 属性访问。`test_read_runtime_source_meta_cache_is_partitioned_by_source_kind`（line 636-669）同理。

**无回归**。

---

## 全量测试与类型检查

```
$ pytest tests/fins/test_read_runtime_semantic_ownership_guards.py -v
13 passed in 1.05s

$ pyright dayu/fins/tools/read_runtime.py dayu/fins/tools/read_runtime_helpers.py \
        dayu/fins/tools/cache.py tests/fins/test_read_runtime_semantic_ownership_guards.py
0 errors, 0 warnings
```

---

## Findings

未发现实质性问题。

---

## Open Questions

无。

---

## Residual Risk

1. **`_get_document_meta_cached` 与 `_get_source_meta_cached_by_kind` 共享 `_meta_cache` 但使用不同 key 形状**：前者 key 无 source_kind，后者 key 含 source_kind。这意味着同一 (ticker, document_id) 可能在 `_meta_cache` 中存在两份缓存条目（一份 by-kind，一份 no-kind）。这是设计层面的 trade-off（`_get_document_meta_cached` 在调用时尚未解析 source_kind），不是正确性 bug，但会导致极少数场景下缓存效率略降。建议后续考虑让 `_get_document_meta_cached` 复用 `_get_source_meta_cached_by_kind` 的缓存条目，或统一所有调用方走 by-kind 路径。
2. **`_build_citation` 新增 `FileNotFoundError` 抛出路径**：`_resolve_source_kind` 对不存在的文档抛出 `FileNotFoundError`。旧代码会返回 `source_type=SourceType.UPLOADED.value` 的弱 citation。当前 `_build_citation` 的所有调用方均在文档操作成功之后，理论上不会遇到文档不存在场景。若未来新增早于文档校验的 citation 构建调用，需处理此异常。

---

## 总评

5 项 accepted findings 全部正确关闭：
- source_kind cache partition 不误伤 processor cache ✓
- bool 缺省/错类型符合 storage contract ✓
- `_normalize_json_scalar_text` 单 owner ✓
- rows ValueError 不破坏正常 result ✓
- AST guard 比纯字符串扫描更稳且不访问 `_meta_cache` ✓

**判定：非 blocking。**
