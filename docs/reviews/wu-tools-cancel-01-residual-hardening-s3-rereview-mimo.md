# Code Review — S3 Re-review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-cancel-01`
- Base: `main` (workspace uncommitted changes since commit `4f9df113`)
- Output file: `docs/reviews/wu-tools-cancel-01-residual-hardening-s3-rereview-mimo.md`
- Included scope: S3 targeted re-review of DS-01/DS-02/DS-03 fix items
- Excluded scope: S1/S2A/S2B, unmodified production files
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### DS-02 验证 — 已关闭

**原 finding**: `_build_fins_aapl_xbrl_workspace` 的 `company_repository.upsert_company_meta(...)` 在 `begin_batch` 之外，若后续仓储操作失败，CompanyMeta 写入不回滚。

**当前代码** (`tests/fins/test_fins_storage_provider.py:1649-1690`):

```python
token = batching_repository.begin_batch("AAPL")
try:
    company_repository.upsert_company_meta(CompanyMeta(...))   # ← 在 try 内
    source_repository.create_source_document(...)
    handle = source_repository.get_source_handle(...)
    # ... blob_repository.store_file loop ...
    source_repository.update_source_document(...)
    batching_repository.commit_batch(token)
except Exception:
    batching_repository.rollback_batch(token)
    raise
```

**结论**: `upsert_company_meta` 现在位于 `begin_batch` 之后的同一 `try/rollback` 窗口内。异常路径执行 `rollback_batch(token)` 后 re-raise。DS-02 已关闭。

### DS-03 验证 — 已关闭

**原 finding**: `_web_process_failed_envelope` 使用 `cast(WebPayload, process_tool_failed_envelope(...))` 绕过类型系统。

**当前代码** (`dayu/tools/web/web_tools.py:1628-1655`):

```python
def _web_process_failed_envelope(
    *,
    error_type: str,
    message: str,
    hint: str | None,
) -> JsonValue:                          # ← 返回类型已改为 JsonValue
    ...
    return process_tool_failed_envelope(  # ← 直接返回，无 cast
        error_type=error_type.strip() or "execution_error",
        message=message.strip() or "Tool execution failed.",
        hint=hint,
    )
```

**调用方**: `_WebProcessTarget.__call__` 返回类型为 `JsonValue`（Protocol 定义），三个调用点（行 494、500、506）均直接 return 此函数结果。类型兼容，无下游影响。

**结论**: `cast(WebPayload, ...)` 已移除，返回类型从 `WebPayload` 改为 `JsonValue`，与合约 helper 返回类型一致。DS-03 已关闭。

### DS-01 验证 — rejected rationale 成立

**原 finding**: `doc_tools.py` 的 `_DocProcessTarget.__call__` 中 generic `Exception` 分支不传递 `hint`。

**当前代码** (`dayu/tools/doc_tools.py:378-385`):

```python
except _DocBusinessFailure as failure:
    return _process_failed_envelope(failure)    # ← 有 hint
except Exception:
    return process_tool_failed_envelope(
        error_type="execution_error",
        message=f"Tool {self.tool_name!r} execution failed.",
    )                                           # ← 无 hint
return process_tool_completed_envelope(value)
```

**rationale 复核**:
- `process_tool_failed_envelope` 的 `hint` 参数默认为 `None`，是可选字段。
- generic `Exception` 分支捕获的是未预期异常，没有具体的 Doc 恢复动作可推荐。
- 对比 fins_tools.py 的同一位置（行 278-285），fins 传递了 `_UNEXPECTED_FAILURE_HINT`，但该 hint 内容为 `"Inspect provider diagnostics or retry with narrower arguments."`，是泛化提示而非具体恢复动作。
- 对比 web_tools.py 的同一位置（行 511-515），web 也不传递 hint。
- Host 解析链（`tool_runtime.py:6586`）正确处理 `hint=None`。

**结论**: DS-01 的 controller rejected rationale 成立。hint 可选、无具体 Doc 恢复动作、行为与 web_tools 一致。不存在必须当前修复的 correctness 问题。

### 新增问题检查

无新增 architecture / type / test / fixture 问题：
- `_web_process_failed_envelope` 返回类型改为 `JsonValue` 后，与 `_WebProcessTarget.__call__` 的 Protocol 返回类型一致
- `_build_fins_aapl_xbrl_workspace` 的 batch 语义完整：所有仓储写入在同一 try/rollback 窗口
- 测试验证结果：114 passed, 1 skipped；pyright 0 errors；git diff --check passed

## Open Questions

- 无。

## Residual Risk

- 无新增。与初审 residual risk 一致（XBRL taxonomy 网络依赖、fixture 体积）。

## Conclusion

**PASS**

DS-02 和 DS-03 均已正确修复并关闭。DS-01 的 controller rejected rationale 成立，不存在 correctness 问题。无新增 findings。
