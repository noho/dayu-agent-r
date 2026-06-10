# WU-TOOLS-01-F03 Slice 1 Code Review — AgentDS

## Reviewed Target

- **Work unit**: WU-TOOLS-01-F03 Slice 1: Diagnostics Observed Facts and Docling Invocation Evidence
- **Reviewed files** (uncommitted diff):
  - `utils/diagnose_web_access.py`
  - `tests/tools/web/test_diagnose_web_access.py`
  - `docs/reviews/wu-tools-01-f03-implementation-slice1-codex.md`
- **Approved plan**: `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md`
- **Review context**: controller adjudication (`docs/reviews/wu-tools-01-f03-plan-review-controller-adjudication.md`), MiMo re-review (`docs/reviews/wu-tools-01-f03-plan-rereview-mimo.md`), DS re-review (`docs/reviews/wu-tools-01-f03-plan-rereview-ds.md`)
- **Review date**: 2026-06-10

## Review Summary

Slice 1 实现忠实执行了 approved plan 的 Slice 1 规范。Docling wrapper instrumentation 的安装/恢复/委托/记录语义正确；observed facts 与 smoke classification 的字段命名清晰分离；所有新增字段均为 additive，未删除 F02 已有字段；生产 `fetch_web_page` LLM-facing success payload 未被修改。19 个 deterministic tests 全部通过，pyright 零错误。

发现 1 个 MEDIUM 和 3 个 LOW severity findings，无 HIGH severity finding。所有 findings 均为诊断侧内部实现细节，不影响 Slice 1 的 completion signal。

---

## Findings

### Finding 1 [MEDIUM] `_DIAGNOSTIC_SCHEMA_REVISION = 2` 缺少 revision 1，版本语义不自洽

**证据**:

- `utils/diagnose_web_access.py:52`: `_DIAGNOSTIC_SCHEMA_REVISION: Final[int] = 2`
- `utils/diagnose_web_access.py:51`: `_SCHEMA_VERSION: Final[str] = "web-diagnostics-v1"`
- F02 代码中不存在 `diagnostic_schema_revision` 字段，也未定义 revision 1。
- plan Slice 1 line 155 只要求"新增模块级常量定义稳定 diagnostics schema/version"，未指定起始值。

**分析**:

`diagnostic_schema_revision` 是新增字段，用于 smoke 做 schema validation（plan line 254-259）。在不存在 revision 1 的情况下从 2 起步，会让 consumer（smoke wrapper 或未来 reader）产生困惑：revision 1 在哪里？是否有一个未记录的 revision 1 存在于某个中间版本？

版本号应从 1 开始。从 2 开始暗示"已经有 revision 1 但未被记录"，削弱了 schema revision 作为稳定性信号的信任度。

**建议裁决**: **accepted** — 将 `_DIAGNOSTIC_SCHEMA_REVISION` 改为 `1`，表示这是 `web-diagnostics-v1` schema 的第一次 revision（即 Slice 1 新增 `observed_*` 字段和 `docling_conversion_invocation_evidence` 的版本）。

**受影响的测试**: `test_cli_single_mode_writes_deterministic_json` line 819 断言 `payload["diagnostic_schema_revision"] == 2`，需同步更新为 `1`。

---

### Finding 2 [LOW] `_DOCLING_DEPENDENCY_EXCEPTION_TYPES` 字符串匹配无法捕获异常子类

**证据**:

- `utils/diagnose_web_access.py:94-96`:
```python
_DOCLING_DEPENDENCY_EXCEPTION_TYPES: Final[frozenset[str]] = frozenset(
    {"DoclingRuntimeInitializationError", "ModuleNotFoundError", "ImportError"}
)
```
- `utils/diagnose_web_access.py:261-264`:
```python
self.docling_runtime_initialization_error = (
    isinstance(exc, DoclingRuntimeInitializationError)
    or exception_type in _DOCLING_DEPENDENCY_EXCEPTION_TYPES
)
```
- Python 中 `ModuleNotFoundError` 是 `ImportError` 的子类。

**分析**:

`isinstance(exc, DoclingRuntimeInitializationError)` 是类型安全的检查。但 `exception_type in _DOCLING_DEPENDENCY_EXCEPTION_TYPES` 用的是 `type(exc).__name__` 字符串精确匹配，不会匹配 `ModuleNotFoundError` 的自定义子类或 `ImportError` 的子类（除 `ModuleNotFoundError` 外）。

在 Docling wrapper 的窄上下文中，实际抛出的异常类型由 Docling runtime 内部控制，`ModuleNotFoundError` 和 `ImportError` 是 Python 内置异常，通常不会被进一步子类化。因此实际风险很低。

此外，`"DoclingRuntimeInitializationError"` 在集合中是冗余的——`isinstance(exc, DoclingRuntimeInitializationError)` 已经覆盖。但这无害。

**建议裁决**: **deferred-with-owner** — 当前实现可接受。留给 smoke wrapper 实际使用时观察是否有遗漏的 Docling dependency 异常模式。如果有，在后续 slice 中改为 `isinstance(exc, ImportError)` 覆盖所有导入异常。

---

### Finding 3 [LOW] `_observed_failing_path_from_payload` 的 comparison_bucket fallback 可能将 comparison 分类语义泄漏到 observed facts

**证据**:

- `utils/diagnose_web_access.py:2592-2598`:
```python
if not failing_paths and comparison_bucket not in {
    _OBSERVED_BUCKET_ALL_SUCCESS,
    _OBSERVED_BUCKET_PARTIAL_SAMPLE,
    _OBSERVED_BUCKET_REQUESTS_ONLY_SAMPLED,
}:
    return comparison_bucket
```

**分析**:

当所有采样路径都成功（无 failing_path）但 comparison_bucket 不在排除列表时，函数返回 comparison_bucket 名作为 `observed_failing_path`。这意味着将来新增 comparison bucket 时，如果不更新此排除列表，comparison bucket 名会泄漏到 `observed_failing_path`——一个本应描述"哪些路径实际失败"的诊断观察字段。

当前所有已知 bucket 要么有 failing paths（正常返回路径名），要么在排除列表中（返回空字符串）。但"将来新增 bucket 但忘记更新此列表"是一个静默漂移风险。

然而，comparison bucket 新增属于 F02 的 `_classify_diagnostic_bucket` 变更，而这在 Slice 1 的 invariants 中明确禁止（plan line 192: "不改变 `_classify_diagnostic_bucket()` 现有 bucket 含义"）。因此这个风险在当前 scope 内不会触发。

**建议裁决**: **accepted-with-note** — 当前逻辑对已有 bucket 正确。添加注释说明排除列表需要与 `_classify_diagnostic_bucket` 保持同步，或者将 fallback 改为返回空字符串以避免静默泄漏。

---

### Finding 4 [LOW] batch summary 中 `schema_version` 与 `diagnostic_schema_version` 并存且值相同

**证据**:

- `utils/diagnose_web_access.py:2946-2948`:
```python
"schema_version": _SCHEMA_VERSION,
"diagnostic_schema_version": _SCHEMA_VERSION,
"diagnostic_schema_revision": _DIAGNOSTIC_SCHEMA_REVISION,
```
- `_build_single_diagnostic_payload` line 2168-2170 同样有 `schema_version` 和 `diagnostic_schema_version` 并存。

**分析**:

两个字段都设为 `"web-diagnostics-v1"`。`schema_version` 是 F02 既有字段，`diagnostic_schema_version` 是 Slice 1 新增字段。plan line 169 和 176 要求 batch row 和 summary 追加 `diagnostic_schema_version`，这是 smoke schema validation 的入口字段。

保留 `schema_version` 维持了向后兼容（F02 消费者可能依赖此字段）。但两个字段值完全相同，未来如果 schema 升级，是否需要同时更新两者？两个字段的语义差别（谁改、何时改、为什么会有两个相同的值）没有在代码中说明。

**建议裁决**: **accepted-with-note** — 在 `_SCHEMA_VERSION` 常量旁添加注释，说明 `schema_version` 是 F02 遗留字段、`diagnostic_schema_version` 是 F03 smoke validation 入口字段。两者当前值为同一 schema identifier，未来可能独立演进。

---

### 补充检查项（无 finding）

以下 review focus 项已确认无问题：

| 检查项 | 状态 | 证据 |
|---|---|---|
| Slice 1 scope 边界 — 不越界到 smoke wrapper | 通过 | 无 `smoke_web_ci` import；无 pass/fail/skip classification 逻辑 |
| Slice 1 scope 边界 — 不修改生产 Web behavior | 通过 | `docling_conversion_invocation_evidence` 只在 diagnostics artifact；`ToolCompletedOutcome.result.value` 未修改 |
| Slice 1 scope 边界 — 不涉及 Host/Engine/ToolRuntime | 通过 | import 列表无 Host/Engine/ToolRuntime 模块 |
| Docling wrapper — 只在 diagnostic run 内安装 | 通过 | `_build_tool_fetch_profile()` line 1523-1525 安装，line 1542-1543 finally 恢复 |
| Docling wrapper — 调用原始 callable | 通过 | `_DoclingInvocationWrapper.__call__` line 340: `result = self._original(raw_bytes, stream_name)` |
| Docling wrapper — 不吞异常 | 通过 | line 341-343: `except Exception as exc: self._evidence.mark_exception(exc); raise` |
| 证据只写 diagnostics artifact | 通过 | `_attach_docling_evidence` 写入 fetch profile；`_docling_evidence_json_from_fetch_profile` 同步到顶层 payload；无写入 `ToolCompletedOutcome.result.value` |
| observed facts vs smoke classification 分离 | 通过 | 字段命名: `observed_bucket`, `observed_failing_path`, `diagnostic_action_hint`, `diagnostic_only_reason` — 均为诊断观察视角 |
| 字段命名自解释 | 通过 | 所有新增字段有明确中文语义；`diagnostic_only_reason` 说明"为什么只是诊断事实" |
| 向后兼容 — 不删除 F02 字段 | 通过 | `comparison_bucket`, `schema_version` 等 F02 字段均保留 |
| 向后兼容 — 新增字段均为 additive | 通过 | 所有新字段追加到 payload/row/summary，未改变既有字段结构 |
| Docling init/dependency skip 分类 | 通过 | `_DoclingInvocationEvidence.mark_exception` 正确区分 `DoclingRuntimeInitializationError` + `ImportError`/`ModuleNotFoundError` vs 通用异常；`_observed_bucket_from_payload` 提升为 `docling_runtime_initialization_error` bucket |
| 普通 conversion failure 不归为 skip | 通过 | `test_generic_docling_conversion_exception_is_not_skip_observed_item` 验证 `RuntimeError` → `observed_bucket != docling_runtime_initialization_error`, `skip_observed_items == []` |
| 严格类型签名 | 通过 | pyright 0 errors；所有函数有完整类型注解；无 `Any`/`object`/无类型签名 |
| 中文 docstring | 通过 | 所有新增 class/function 有完整中文 docstring（含 Args/Returns/Raises） |
| 无魔法字符串 | 通过 | 所有字符串常量定义为模块级 `Final` 常量（`_OBSERVED_BUCKET_*`, `_PATH_*`, `_SCHEMA_VERSION` 等） |
| 无魔法数字 | 通过 | 所有数字定义为模块级常量（`_TEXT_PREFIX_CHARS`, `_DIAGNOSTIC_SCHEMA_REVISION` 等） |
| tests deterministic | 通过 | 全部测试使用 synthetic payload、monkeypatch、tmp_path；无 live network |
| tests 覆盖 wrapper restore | 通过 | `test_docling_wrapper_records_invoked_true_and_restores_callable` line 515: `assert web_tools_module._docling_convert_to_markdown is fake_docling` |
| tests 覆盖异常后 restore | 通过 | `test_docling_runtime_initialization_exception_becomes_skip_observed_item` line 679: `assert web_tools_module._docling_convert_to_markdown is fake_docling` |
| tests 覆盖 invoked=false (HTML path) | 通过 | `test_html_fetch_profile_records_docling_invoked_false` |
| tests 覆盖 PDF fetch 成功但 wrapper 未调用 | 通过 | `test_pdf_fetch_success_without_docling_invocation_keeps_failure_evidence_for_smoke` |
| child_process_error 的 observed_failing_path | 通过 | `test_batch_rows_and_summary_counts` line 397: `assert rows[1]["observed_failing_path"] == "diagnostic_child_process"` |
| observed_items 结构 | 通过 | `test_batch_rows_and_summary_counts` line 402-404: `isinstance(observed_items, list)`, `len == 2` |
| diagnostic_action_hints 提取 | 通过 | `test_batch_rows_and_summary_counts` line 405-407: `isinstance(action_hints, list)`, `len == 1` |
| observed_buckets 汇总 | 通过 | line 390: `{"all_success": 1, "child_process_error": 1}` |
| diagnostic_schema_version 在 row/summary 中 | 通过 | lines 395, 401: `== "web-diagnostics-v1"` |

---

## Residual Risks

| 风险 | 严重性 | 说明 | 处置 |
|---|---|---|---|
| Wrapper 依赖 `_web_tools_module._docling_convert_to_markdown` 模块属性 | Low | 如果生产代码重命名此属性或改变 Docling callable 装配方式，`_build_tool_fetch_profile` 会在调用时产生 `AttributeError`，被外层 `except Exception` 捕获为 `callable_exception` profile，不会静默 pass | 可接受 — 已由 Slice 1 stop condition 覆盖：wrapper 无法观察到 invocation 时停止 |
| 字符串匹配 `_DOCLING_DEPENDENCY_EXCEPTION_TYPES` 不捕获异常子类 | Very Low | Docling 运行时的 `ModuleNotFoundError`/`ImportError` 通常不被子类化 | deferred — 留给 smoke 实际使用时观察 |
| `_observed_failing_path_from_payload` 的 comparison_bucket fallback | Very Low | 当前所有 bucket 已有正确覆盖；新 bucket 需同步更新排除列表 | Finding 3 已建议添加注释 |
| `diagnostic_schema_revision = 2` 缺少 revision 1 | Low | 不会导致功能问题，但削弱版本语义信任度 | Finding 1 建议改为 1 |

---

## Final Recommendation: **pass-with-fixes**

Slice 1 实现满足 approved plan 的全部 Slice 1 要求：

1. Docling wrapper instrumentation 安装/恢复/委托/记录语义正确，finally 恢复原始 callable，不吞异常，证据只写 diagnostics artifact。
2. observed facts 与 smoke classification 字段分离清晰，命名自解释（`observed_bucket`、`observed_failing_path`、`diagnostic_action_hint`）。
3. schema/revision 字段在 single payload、batch row、summary 中一致追加。
4. Docling init/dependency skip 与普通 conversion failure 分类正确。
5. 严格类型、中文 docstring、无 Any/object/魔法字符串/魔法数字。
6. 19 个 deterministic tests pass，pyright 0 errors。

**建议在进入 Slice 2 前修复**:

- **Finding 1 [MEDIUM]**: `_DIAGNOSTIC_SCHEMA_REVISION` 改为 `1`，同步更新测试断言。

其余 findings (2/3/4) 为 LOW，不阻塞 Slice 2 推进；可在 Slice 2 实现中顺手处理或作为 deferred residual。

---

## Validation Results

- `pytest tests/tools/web/test_diagnose_web_access.py -q`: **19 passed in 0.32s**
- `pyright utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py`: **0 errors, 0 warnings, 0 informations**
