# WU-TOOLS-01-F01-02-R3 Slice 3 S3-CR-01 Fix Re-Review

- **Reviewer**: MiMo
- **Date**: 2026-06-10
- **Gate**: re-review（S3-CR-01 fix focused review）
- **Scope**: `S3-CR-01` accepted finding fix 与回归面

## 结论

**PASS**

S3-CR-01 fix 正确消除了 `cancel_reason()` 向 LLM-facing message 的泄漏，新增 focused test 同时覆盖 pre-cancel 和深层搜索取消路径并断言不含 Host 治理标识。`ToolCancelledOutcome.reason` 保持 `host_cancelled`，无 legacy adapter 命中，pyright 0 errors，无回归。

---

## 检查项

### 1. `_cancelled_from_token` 不再读取/拼接 `cancel_reason()`

**结论**: ✅ PASS

`fins_tools.py:925`：`del cancellation_token` — token 参数被显式丢弃，函数体不再调用 `cancel_reason()`。message 使用固定业务可读文本 `"财报读取工具调用已被取消。"`，hint 使用模块常量 `_FINS_CANCELLED_HINT`（`"当前工具调用已停止；等待新的用户指令或后续调度。"`）。

`grep -n "cancel_reason" dayu/fins/tools/fins_tools.py`：无命中。

### 2. `raise_fins_cancelled` 不再读取/拼接 `cancel_reason()`

**结论**: ✅ PASS

`read_runtime_helpers.py:334`：`del cancellation_token` — token 参数被显式丢弃，函数体不再调用 `cancel_reason()`。`FinsReadCancelledError` 的 message 来自调用方传入的业务可读取消说明，hint 为固定文本 `"当前工具调用已停止；等待新的用户指令或后续调度。"`。

`grep -n "cancel_reason" dayu/fins/tools/read_runtime_helpers.py`：无命中。

### 3. `ToolCancelledOutcome.reason` 仍为 `host_cancelled`

**结论**: ✅ PASS

所有 cancelled outcome 断言统一通过 `_assert_host_cancelled_outcome` helper 完成，该 helper 断言：
- `isinstance(outcome, ToolCancelledOutcome)`
- `outcome.reason == TOOL_CANCELLED_REASON_HOST_CANCELLED`
- `outcome.meta` 非 None 且 `tool_name` / `started_at` / `finished_at` 正确
- `_assert_host_governance_terms_hidden(outcome)` — message/hint 不含治理标识

覆盖的测试：
- `test_list_documents_pre_cancel_returns_cancelled_outcome`
- `test_cancelled_read_outcomes_hide_host_governance_reason`（新增）
- `test_search_document_cancellation_during_search_stops_before_all_candidates`
- `test_search_document_semantic_enrichment_cancelled_error_is_not_swallowed`
- `test_read_section_cancelled_before_processor_read_returns_cancelled_outcome`
- `test_read_section_parent_title_lookup_cancelled_error_is_not_swallowed`
- `test_query_xbrl_facts_cancellation_during_filtering_stops_promptly`

### 4. 新 focused test 覆盖范围

**结论**: ✅ PASS

`test_cancelled_read_outcomes_hide_host_governance_reason`（`test_fins_storage_provider.py:787-831`）：

**Pre-cancel 路径**：
- 构造 `_ManualCancellationToken(cancel_reason=_HOST_GOVERNANCE_CANCEL_REASON)`
- 立即 cancel，调用 `list_documents`
- 断言 `_assert_host_cancelled_outcome`

**深层搜索取消路径**：
- 构造 `_ManualCancellationToken(cancel_reason=_HOST_GOVERNANCE_CANCEL_REASON)`
- 安装 `_SearchCancellingProcessor`，调用 `search_document`
- 断言 `_assert_host_cancelled_outcome` + `processor.search_calls == ["annual"]`

**Host 治理标识黑名单**（`_HOST_GOVERNANCE_FORBIDDEN_TERMS`）：

```
run_id, session_id, correlation_id, payload_ref, digest, cancellation_token,
run-secret, session-secret, correlation-secret, payload-secret, sha256-secret, token-secret
```

`_HOST_GOVERNANCE_CANCEL_REASON` 注入的测试 reason 包含全部 6 类治理标识的 key 和 value，`_assert_host_governance_terms_hidden` 逐一断言 message 和 hint 中不包含其中任何一个。

### 5. 未扩大到 Doc/Web 或其它非允许文件

**结论**: ⚠️ PASS（附 scope 观察）

Controller 批准的 fix scope 限于 `fins_tools.py`、`read_runtime_helpers.py`、`test_fins_storage_provider.py` 三个文件。实际 diff 还涉及 `provider.py`、`read_runtime.py`、`search_engine.py`，但这三个文件的改动是 Slice 3 整体迁移的一部分（移除 legacy adapter import 和 `cancel_reason()` 调用），不是 S3-CR-01 fix 独立引入。在当前工作树中这些改动与 S3-CR-01 fix 一并提交是合理的，因为它们属于同一个 finding（不应将 Host 治理取消原因投影给 LLM）的完整消除。

未触及 Doc/Web 文件。`docs/reviews/` 下新增的文件均为 review artifact，不属于代码变更。

### 6. 无新 legacy adapter 命中

**结论**: ✅ PASS

`grep -rn "_legacy_adapter\|LegacyToolDeclarationCollector\|adapt_collected_tools\|ToolBusinessError" dayu/fins/tools/ tests/fins/test_fins_storage_provider.py`：无命中。

### 7. 无 pyright / test regression

**结论**: ✅ PASS

- `pyright`：0 errors, 0 warnings, 0 informations
- Controller 验证：`pytest tests/fins/test_fins_storage_provider.py` 22 passed；`pytest tests/fins/test_fins_ingestion_tools.py -k cancellation` 1 passed

---

## Fix 质量评估

| 维度 | 评估 |
|---|---|
| `cancel_reason()` 泄漏消除 | 完整 — `fins_tools.py` 和 `read_runtime_helpers.py` 均用 `del cancellation_token` 显式丢弃 |
| 固定 message 语义 | 正确 — `"财报读取工具调用已被取消。"` 是面向 LLM 的业务可读取消说明 |
| hint 一致性 | 正确 — `_FINS_CANCELLED_HINT` 常量在 `_cancelled_from_token` 和 `raise_fins_cancelled` 间保持一致 |
| 治理标识黑名单覆盖度 | 充分 — 12 个 forbidden terms 覆盖 key 和 value 两级 |
| `_ManualCancellationToken` 可注入性 | 合理 — 通过 `cancel_reason` 参数支持测试注入任意 reason |
| `reason` 字段保持 | 正确 — 所有断言确认 `TOOL_CANCELLED_REASON_HOST_CANCELLED` |

---

## 总结

S3-CR-01 fix 完整实现了 controller adjudication 的要求：`_cancelled_from_token` 和 `raise_fins_cancelled` 不再读取 `cancel_reason()`，新增 focused test 覆盖 pre-cancel 和深层搜索取消两条路径并断言 12 个 Host 治理标识不出现在 LLM-facing message/hint 中。`ToolCancelledOutcome.reason` 保持 `host_cancelled`，无 legacy adapter 残留，pyright 0 errors，无回归。

---

*Reviewer: MiMo*
*Date: 2026-06-10*
*Artifact: docs/reviews/wu-tools-01-f01-02-r3-slice3-rereview-mimo.md*
