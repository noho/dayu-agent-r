# WU-TOOLS-01-F01-02 Slice 4 Narrow Re-Review — AgentDS

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | Slice 4 fix re-review (narrow) |
| plan | `docs/host/wu-tools-01-f01-02-cancellation-plan.md` |
| implementation | `docs/reviews/wu-tools-01-f01-02-slice4-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-tools-01-f01-02-slice4-code-review-controller-adjudication.md` |
| fix artifact | `docs/reviews/wu-tools-01-f01-02-slice4-fix-codex.md` |
| reviewer | AgentDS |

## Scope

Narrow re-review of accepted fixes S4-F1 and S4-F2 per controller adjudication. Only validate:

1. S4-F1 closed: `read_section` parent-title lookup broad except no longer swallows `ToolBusinessError(code=tool_cancelled)`.
2. S4-F2 closed: `search_document` semantic enrichment broad except no longer swallows `ToolBusinessError(code=tool_cancelled)`.
3. Fix has no overreach: no Host/Engine contract, tool schema, storage boundary, or other checkpoint changes.
4. Focused pytest / pyright / diff check pass.
5. Blocking finding → PASS/FAIL verdict.

## Validation

### S4-F1: `read_section` Parent-Title Lookup Swallow

**Location**: `dayu/fins/tools/read_runtime.py:471-473`

**Before (swallow path)**:
```python
try:
    _raise_if_fins_cancelled(cancellation_token)
    parent_title = processor.get_section_title(str(parent_ref))
    _raise_if_fins_cancelled(cancellation_token)
except Exception:          # ← catches ToolBusinessError (subclass of Exception)
    parent_title = None    # ← cancellation silently downgraded to no parent title
```

**After (fixed)**:
```python
try:
    _raise_if_fins_cancelled(cancellation_token)
    parent_title = processor.get_section_title(str(parent_ref))
    _raise_if_fins_cancelled(cancellation_token)
except ToolBusinessError as exc:       # ← NEW: catches ToolBusinessError first
    if exc.code == _TOOL_CANCELLED_ERROR_CODE:
        raise                           # ← re-raises cancellation, NOT swallowed
    parent_title = None                 # ← other ToolBusinessError still best-effort
except Exception:                       # ← broad handler still for non-ToolBusinessError
    parent_title = None
```

**Test**: `test_read_section_parent_title_lookup_cancelled_error_is_not_swallowed`

- `_ParentTitleLookupCancellingProcessor.get_section_title` calls `self._token.cancel()` then returns title.
- The `_raise_if_fins_cancelled` at line 470 (after `get_section_title` returns) observes cancellation and raises `ToolBusinessError(code="tool_cancelled")`.
- Assertion: `outcome.result.error == "tool_cancelled"` — cancellation is NOT downgraded.
- Assertion: `processor.get_section_title_calls == 1` — processor was called, cancellation happened during the try block.

**Verdict**: ✅ S4-F1 CLOSED. Cancellation propagates through the previously swallowed path.

### S4-F2: `search_document` Semantic Enrichment Swallow

**Location**: `dayu/fins/tools/read_runtime.py:625-627`

**Before (swallow path)**:
```python
try:
    _raise_if_fins_cancelled(cancellation_token)
    all_secs = processor.list_sections()
    ...
except Exception:          # ← catches ToolBusinessError (subclass of Exception)
    pass                   # ← cancellation silently swallowed, search continues
```

**After (fixed)**:
```python
try:
    _raise_if_fins_cancelled(cancellation_token)
    all_secs = processor.list_sections()
    ...
except ToolBusinessError as exc:       # ← NEW: catches ToolBusinessError first
    if exc.code == _TOOL_CANCELLED_ERROR_CODE:
        raise                           # ← re-raises cancellation, NOT swallowed
except Exception:                       # ← broad handler still for non-ToolBusinessError
    pass
```

检查点覆盖了 try 块内的所有 `_raise_if_fins_cancelled` 调用（line 608, 610, 616, 618, 621）以及 `_enrich_sections_with_semantic` 内部可能抛出的取消异常。

**Test**: `test_search_document_semantic_enrichment_cancelled_error_is_not_swallowed`

- Monkeypatches `_enrich_sections_with_semantic` to raise `ToolBusinessError(code="tool_cancelled")`.
- Assertion: `outcome.result.error == "tool_cancelled"` — cancellation propagates.
- Assertion: `processor.search_calls == []` — search was never started, proving cancellation stopped execution.

**Verdict**: ✅ S4-F2 CLOSED. Cancellation propagates through the previously swallowed path.

### Overreach Check

| 边界 | 状态 | 证据 |
|---|---|---|
| Host/Engine contract | 未改 | diff 不触及 `dayu/host/`、`dayu/engine/`、`dayu/contracts/` |
| Tool schema | 未改 | `fins_tools.py` schema 参数无变更（execution_context 是 adapter 注入，不暴露给 LLM） |
| Storage 边界 | 未改 | diff 不触及 `dayu/fins/storage/` |
| Other checkpoint 位置 | 未改 | 仅 `read_runtime.py:471-473` 和 `625-627` 两处新增 except 分支 |
| Unrelated type debt | 未改 | 无其他类型签名的修改 |
| LLM-facing 内容 | 未改 | `test_combined_tools_acceptance.py` 新增断言确认 schema 无 `execution_context`/`cancellation_token` 污染 |

**Verdict**: ✅ 无越界。

### Validation Commands

```
source .venv/bin/activate && pytest tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_tools.py tests/tools/test_combined_tools_acceptance.py -q
→ 47 passed, 3 warnings

source .venv/bin/activate && pyright
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ passed (no output)
```

所有已存在测试和新增测试均通过；pyright 零报错。

## Finding Status

| ID | Description | Status |
|---|---|---|
| S4-F1 | `read_section` parent-title lookup broad except 吞 `tool_cancelled` | ✅ CLOSED |
| S4-F2 | `search_document` semantic enrichment broad except 吞 `tool_cancelled` | ✅ CLOSED |

## Conclusion

**PASS** — 无 blocking finding。

S4-F1 和 S4-F2 均以最小修改关闭：在每个 broad except 前插入专用 `ToolBusinessError` 分支，`code="tool_cancelled"` 时 re-raise，其他异常保持原有 best-effort 降级行为。修改范围严格限制在两处吞并路径，未触及 Host/Engine contract、tool schema、storage 边界或任何其他 checkpoint 位置。测试覆盖了两条修复路径的行为回归。pytest 47 passed，pyright 0 errors，git diff --check 通过。
