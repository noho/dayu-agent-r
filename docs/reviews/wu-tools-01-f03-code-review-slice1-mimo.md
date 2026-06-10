# WU-TOOLS-01-F03 Slice 1 Code Review — AgentMiMo

## Review Target

- **Changed files**:
  - `utils/diagnose_web_access.py`
  - `tests/tools/web/test_diagnose_web_access.py`
- **Approved plan**: `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md` (Slice 1 section)
- **Implementation artifact**: `docs/reviews/wu-tools-01-f03-implementation-slice1-codex.md`
- **Date**: 2026-06-10

## Scope Verification

**Slice boundary check**: Implementation only modifies `utils/diagnose_web_access.py` and `tests/tools/web/test_diagnose_web_access.py`. No changes to:
- `utils/smoke_web_ci.py` (Slice 2 territory)
- `dayu/tools/web/` production modules
- Host / Engine / Service layers
- `utils/web_ci_urls.jsonl`

**Scope boundary verdict**: PASS. Implementation strictly stays within Slice 1 allowed files.

---

## Finding 1 [Low] — `_observed_failing_path_from_payload` 将 bucket 名直接用作 failing path

**Severity**: Low
**Location**: `utils/diagnose_web_access.py:2592-2597`

**Description**:

当 `failing_paths` 列表为空且 `comparison_bucket` 不在 `{all_success, partial_sample, requests_only_sampled}` 时，函数直接返回 `comparison_bucket` 作为 `observed_failing_path`。对于 `playwright_challenge_detected` 和 `browser_only_success` 这类 bucket，它们是 observed fact（"观察到浏览器挑战"、"只有浏览器路径成功"），不是可操作的失败路径名称。将它们作为 `observed_failing_path` 会让 smoke 消费者误以为存在可定位的失败路径。

**Evidence**:

```python
# diagnose_web_access.py:2592-2597
if not failing_paths and comparison_bucket not in {
    _OBSERVED_BUCKET_ALL_SUCCESS,
    _OBSERVED_BUCKET_PARTIAL_SAMPLE,
    _OBSERVED_BUCKET_REQUESTS_ONLY_SAMPLED,
}:
    return comparison_bucket  # e.g. "playwright_challenge_detected" 作为 failing_path
return ",".join(failing_paths)
```

**Risk**: Smoke 消费者读到 `observed_failing_path="playwright_challenge_detected"` 可能误以为存在可定位的失败路径，实际只是浏览器挑战观察事实。此字段在 Slice 1 diagnostics 输出中，不直接影响 smoke exit code。

**Suggested decision**: `deferred-with-owner — implementation-agent`。建议 Slice 2 smoke 消费端对此类 bucket 做 fallback，或在 Slice 1 中区分 "observed_bucket" 和真正的 failing path。不阻塞 Slice 1 功能正确性。

---

## Finding 2 [Low] — `_DoclingInvocationEvidence` class docstring 的 Args / Returns / Raises 部分不符合 dataclass 惯例

**Severity**: Low
**Location**: `utils/diagnose_web_access.py:179-197`

**Description**:

`_DoclingInvocationEvidence` 使用 `@dataclass(slots=True)` 但 class docstring 的 `Args:` 部分列出了 dataclass 字段，`Returns: 无。Raises: 无。` 描述的是 class 构造而非方法行为。dataclass 的字段文档通常应放在 `Attributes:` 或 `Fields:` 部分，而非 `Args:`。这不是阻塞性问题，但对后续维护者造成轻微理解负担。

**Evidence**:

```python
@dataclass(slots=True)
class _DoclingInvocationEvidence:
    """Docling 转换 callable 的诊断期调用证据。

    Args:           # <-- dataclass 字段应使用 Attributes
        diagnostic_url: 当前诊断 URL。
        ...
    Returns:        # <-- class 没有返回值
        无。
    Raises:         # <-- class 构造不抛异常
        无。
    """
```

**Risk**: Very Low。不影响功能或测试。

**Suggested decision**: `accepted-low`。Amend where cheap，不阻塞。

---

## Finding 3 [Info] — `_child_error_payload` 中 `diagnostic_schema_revision` 使用常量值

**Severity**: Info
**Location**: `utils/diagnose_web_access.py:2890`

**Description**:

`_child_error_payload` 给 `diagnostic_schema_revision` 设置 `_DIAGNOSTIC_SCHEMA_REVISION`（当前值 `2`），但子进程错误 payload 未包含来自实际诊断子进程的 schema revision。后续 `_build_batch_result_row` 从 `payload.get("diagnostic_schema_revision", _DIAGNOSTIC_SCHEMA_REVISION)` 读取，对该子进程错误行会得到 `2`。

这在当前实现中是正确的（子进程错误 payload 由诊断系统自己生成，revision 确实是 2）。但当未来 revision 递增时，如果 `_child_error_payload` 未同步更新常量引用，可能会产生 revision 不一致。

**Risk**: Very Low。当前正确，且子进程错误行不参与 schema validation 核心路径。

**Suggested decision**: `accepted-low`。当前正确，不阻塞。

---

## Finding 4 [Info] — `_build_batch_summary` 中 `observed_items` 对所有行做 `_build_observed_diagnostic_item` 投影

**Severity**: Info
**Location**: `utils/diagnose_web_access.py:2963`

**Description**:

`observed_items` 字段对 `rows` 中每一行都调用 `_build_observed_diagnostic_item(row)`，包括 `all_success` 行。这意味着 summary 中会包含成功行的 observed items。如果 smoke 消费端只需失败/skip/diagnostic-only items，需要自行过滤或使用 `diagnostic_only_observed_items` / `skip_observed_items`。

这与 plan 中 "Diagnostics 输出 observed facts" 的定位一致（成功也是 observed fact），但 smoke 消费端需要注意区分。

**Risk**: Info。设计决策，不影响正确性。

**Suggested decision**: `accepted`。符合 plan 设计意图。

---

## Finding 5 [Low] — 测试未覆盖 `_observed_failing_path_from_payload` 的 bucket-as-path 分支

**Severity**: Low
**Location**: `tests/tools/web/test_diagnose_web_access.py`

**Description**:

当前测试覆盖了：
- Docling wrapper 成功调用（`invoked=True`, `original_completed=True`）
- HTML fetch 不触发 Docling（`invoked=False`）
- PDF fetch 成功但 Docling 未触发（`invoked=False`）
- Docling 初始化异常 → skip observed item
- 普通 Docling 异常 → 非 skip
- Batch summary 各字段存在性

未覆盖的分支：
1. `playwright_challenge_detected` bucket → `observed_failing_path` 返回 bucket 名
2. `browser_only_success` bucket → `observed_failing_path` 返回 bucket 名
3. `_diagnostic_only_reason_from_payload` 的各条件分支
4. `_diagnostic_action_hint_from_payload` 的 `fetch_next_action` 分支
5. `comparison_bucket` 从 payload 读取（而非重新分类）的路径

**Risk**: Low。核心逻辑已锁定，未覆盖的是边界 bucket 的 observed field 投影。

**Suggested decision**: `deferred-with-owner — implementation-agent`。可在 Slice 2 或 Slice 5 补充。

---

## Finding 6 [Info] — `_attach_docling_evidence` 对每个 outcome 分支重复调用

**Severity**: Info
**Location**: `utils/diagnose_web_access.py:1526-1617`

**Description**:

`_build_tool_fetch_profile` 的 try/except 块内，每个 outcome 分支（`ToolCompletedOutcome`、`ToolFailedOutcome`、`ToolCancelledOutcome`、`ToolAwaitingOutcome`、`unknown_outcome`、`callable_exception`）都独立调用 `_attach_docling_evidence`。这是正确的实现方式——每个分支需要构造不同的 profile dict，evidence 附加在最外层。

不构成问题，只是说明实现选择了"每个分支独立附加"而非"统一出口附加"的模式。两种方式等价。

**Suggested decision**: `accepted`。

---

## Adversarial Failure Pass

### Wrapper 恢复可靠性

- `_build_tool_fetch_profile` 中 `finally` 块始终恢复原始 callable（`diagnose_web_access.py:1542-1543`）。
- `test_docling_wrapper_records_invoked_true_and_restores_callable` 和 `test_docling_runtime_initialization_exception_becomes_skip_observed_item` 都断言 `web_tools_module._docling_convert_to_markdown is fake_docling`，证明 wrapper 在正常和异常路径都正确恢复。
- **Verdict**: PASS。

### Production payload 不泄露

- `_attach_docling_evidence` 只修改 `profile` dict（diagnostics 内部数据结构），不修改 `ToolCompletedOutcome.result.value`。
- `_build_single_diagnostic_payload` 将 evidence 写入顶层 `docling_conversion_invocation_evidence` 字段，不写入 `fetch_web_page_profile` 的 production-facing 子结构。
- `to_json()` 包含 `diagnostic_only_reason` 字段明确标注 "不会写入生产 fetch_web_page 返回给 LLM 的成功 payload"。
- **Verdict**: PASS。

### Schema version 覆盖

- `_build_single_diagnostic_payload` 同时输出 `schema_version` 和 `diagnostic_schema_version` / `diagnostic_schema_revision`。
- `_child_error_payload` 同样输出三个字段。
- `_build_batch_summary` 同样输出三个字段。
- `_build_batch_result_row` 从 payload 读取，有 fallback 默认值。
- **Verdict**: PASS。

### Docling init skip vs conversion failure 分类

- `_DOCLING_DEPENDENCY_EXCEPTION_TYPES` 包含 `DoclingRuntimeInitializationError`、`ModuleNotFoundError`、`ImportError`。
- `mark_exception` 使用 `isinstance` + exception type name 双重检查。
- `test_docling_runtime_initialization_exception_becomes_skip_observed_item` 验证 init error → skip。
- `test_generic_docling_conversion_exception_is_not_skip_observed_item` 验证 `RuntimeError` → 非 skip。
- **Verdict**: PASS。

### Tests deterministic

- 所有新测试通过 monkeypatch 替换 `_docling_convert_to_markdown` 和 `_fetch_web_page_definition`。
- 无 live network、无 real Docling、无 real Playwright。
- `test_batch_rows_and_summary_counts` 使用 synthetic payload。
- **Verdict**: PASS。

### 严格类型检查

- `_DoclingConvertCallable: TypeAlias = Callable[[bytes, str], tuple[str, str, str]]` — 严格类型。
- `_DoclingInvocationEvidence` 使用 dataclass with slots，所有字段有类型注解。
- `_DoclingInvocationWrapper.__call__` 有完整参数和返回类型注解。
- 所有新 helper 函数有 `*` keyword-only 参数和返回类型。
- 无 `Any`、`object`、无类型参数。
- **Verdict**: PASS。

### 中文 docstring

- 所有新类和函数有完整中文 docstring，包含 Args / Returns / Raises。
- **Verdict**: PASS（Finding 2 的 Args vs Attributes 是惯例问题，非 docstring 缺失）。

### 魔法字符串 / 魔法数字

- 所有常量定义为模块级 `Final` 变量（`_DOCLING_TARGET_MODULE`、`_OBSERVED_BUCKET_*`、`_PATH_*` 等）。
- `_DIAGNOSTIC_SCHEMA_REVISION: Final[int] = 2` — 明确常量。
- **Verdict**: PASS。

---

## Plan Compliance Checklist

| Plan 要求 | 实现状态 | 证据 |
|---|---|---|
| 新增模块级常量定义 diagnostics schema/version | ✅ | `_DIAGNOSTIC_SCHEMA_REVISION`, `_OBSERVED_BUCKET_*`, `_PATH_*`, `_DOCLING_TARGET_*` |
| 新增 `_DoclingInvocationEvidence` 数据类 | ✅ | `diagnose_web_access.py:179-270` |
| 新增 `_DoclingInvocationWrapper` | ✅ | `diagnose_web_access.py:273-223` |
| wrapper 只在 diagnostic run 内安装，finally 恢复 | ✅ | `diagnose_web_access.py:1521-1543` |
| wrapper 调用原始 callable，不吞异常 | ✅ | `diagnose_web_access.py:216-222` |
| wrapper 记录 invoked/stream_name/raw_bytes_length/target_module/target_function/original_completed/original_exception_type/docling_runtime_initialization_error/diagnostic_url | ✅ | `to_json()` 输出全部字段 |
| evidence 只写入 diagnostics artifact，不写入 production payload | ✅ | `_attach_docling_evidence` 只修改 profile dict |
| `_build_single_diagnostic_payload` 追加 `docling_conversion_invocation_evidence` | ✅ | `diagnose_web_access.py:2184-2187` |
| `_build_batch_result_row` 追加 observed_bucket/observed_failing_path/evidence_path/failure_url/diagnostic_action_hint/diagnostic_only_reason/diagnostic_schema_version | ✅ | `diagnose_web_access.py:2857-2864` |
| `_build_batch_summary` 追加 observed_buckets/observed_items/diagnostic_only_observed_items/skip_observed_items/diagnostic_action_hints/diagnostic_schema_version | ✅ | `diagnose_web_access.py:2962-2966` |
| 不删除 F02 已有字段 | ✅ | diff 只做 additive 追加 |
| 不修改 production `fetch_web_page` LLM-facing payload | ✅ | 无 `web_tools.py` 变更 |
| 不新增 Playwright skipped bucket（保留 facts 判定） | ✅ | 未修改 `_classify_diagnostic_bucket` |
| Tests deterministic，无 live network | ✅ | monkeypatch + synthetic payload |
| pyright 通过 | ✅ | implementation artifact 报告 0 errors |

---

## Residual Risks

| 风险 | 严重性 | 说明 |
|---|---|---|
| `_observed_failing_path_from_payload` bucket-as-path 语义 | Low | Slice 2 smoke 消费端需注意区分 bucket 名和真正可操作的失败路径 |
| Wrapper 随生产 callable 名称变化失效 | Low | Plan 已要求失效时产生 fail 而非静默退回推断 |
| 未覆盖的测试分支（challenge/browser_only bucket 投影） | Low | 核心路径已锁定，边界 bucket 投影可在 Slice 2/5 补充 |

---

## Final Recommendation

**pass-with-fixes**

Implementation 严格遵循 Slice 1 plan，核心功能正确：

1. **Docling wrapper instrumentation**: 安装/恢复/委托/记录模式正确，`finally` 恢复在正常和异常路径都验证通过。
2. **Evidence isolation**: `docling_conversion_invocation_evidence` 只写入 diagnostics artifact，未触及 production LLM-facing payload。
3. **Observed facts separation**: 字段命名从 smoke 判定语义转为诊断观察语义（`observed_bucket`、`diagnostic_action_hint`），职责边界清晰。
4. **Schema version**: `diagnostic_schema_version` / `diagnostic_schema_revision` 在所有 payload 类型中一致输出。
5. **Docling init skip vs conversion failure**: 双重检查（`isinstance` + exception type name）覆盖 `DoclingRuntimeInitializationError`、`ModuleNotFoundError`、`ImportError`。
6. **Type safety**: 无 `Any`、`object`、无类型签名。所有新符号有严格类型注解。
7. **Tests**: 19 passed，deterministic，无 live network。

**Fixes needed** (non-blocking, 可在后续 slice 处理):
- Finding 1: `_observed_failing_path_from_payload` 的 bucket-as-path 分支语义模糊，建议 Slice 2 消费端或 Slice 5 补充测试时澄清。
- Finding 5: 补充 `playwright_challenge_detected` / `browser_only_success` bucket 的 observed field 投影测试。

**No blocking issue found.** Implementation can proceed to Slice 2.
