# WU-TOOLS-01-F03 Slice 2 Re-Review — AgentMiMo

## Review Target

- **Gate**: fix gate re-review
- **Changed files**:
  - `utils/smoke_web_ci.py`（untracked，fix gate 后）
  - `tests/tools/web/test_smoke_web_ci.py`（untracked，fix gate 后）
- **Input artifacts**:
  - `docs/reviews/wu-tools-01-f03-implementation-slice2-codex.md`
  - `docs/reviews/wu-tools-01-f03-code-review-slice2-mimo.md`
  - `docs/reviews/wu-tools-01-f03-code-review-slice2-ds.md`
  - `docs/reviews/wu-tools-01-f03-code-review-slice2-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f03-fix-slice2-codex.md`
- **Date**: 2026-06-10

---

## Re-Review Scope 逐项验证

### 1. Exit code semantic literals 是否已提取为 constants

**状态: 已修复**

`utils/smoke_web_ci.py:37-39` 定义：

```python
_EXIT_OK: Final[int] = 0
_EXIT_LOCAL_FAILURE: Final[int] = 1
_EXIT_SCHEMA_OR_INFRA_FAILURE: Final[int] = 2
```

全文扫描确认所有语义 exit code 均使用常量：
- `_classify_loaded_artifact` 中 `_EXIT_OK`（L782, L813, L822, L891）、`_EXIT_LOCAL_FAILURE`（L829, L860, L870, L925, L935, L948, L959）、`_EXIT_SCHEMA_OR_INFRA_FAILURE`（L841）
- `_classify_child_result` 中 `_EXIT_SCHEMA_OR_INFRA_FAILURE`（L1127, L1148）
- `_summary_from_cases` 中 `_EXIT_OK`（L1188）、`_EXIT_SCHEMA_OR_INFRA_FAILURE`（L1189, L1190）、`_EXIT_LOCAL_FAILURE`（L1191, L1192）
- `_skipped_summary` 中 `_EXIT_OK`（L1239）
- `main()` 中 `_EXIT_SCHEMA_OR_INFRA_FAILURE`（L1620, L1623, L1634）

测试中 `exit_code` 断言使用数字字面量（`0`、`1`、`2`），这是正确的——测试验证的是外部契约值，不依赖内部常量名。

**结论**: 完全符合 controller adjudication 要求。

---

### 2. `not_opted_in` bucket 是否已提取为 constant

**状态: 已修复**

`utils/smoke_web_ci.py:44` 定义：

```python
_BUCKET_NOT_OPTED_IN: Final[str] = "not_opted_in"
```

`_skipped_summary()` 在 L1231 使用 `_BUCKET_NOT_OPTED_IN`。

测试 `test_not_opted_in_writes_skipped_summary_and_does_not_call_runner` 在 L49 断言 `bucket == "not_opted_in"`——使用字面量字符串验证外部契约，不依赖内部常量，符合要求。

**结论**: 完全符合 controller adjudication 要求。

---

### 3. `_STDIO_PREFIX_CHARS` / `_prefix_text` 死代码是否移除

**状态: 已修复**

全文 grep 确认 `_STDIO_PREFIX_CHARS` 和 `_prefix_text` 在 `utils/smoke_web_ci.py` 中已不存在。

**结论**: 完全符合 controller adjudication 要求。

---

### 4. Opt-in but no local cases 是否在 summary 中显式说明 Slice 3 接入

**状态: 已修复**

`_execute_smoke()`（L1497-1503）通过 `extra_skips` 参数传入 `_slice2_local_fixture_skip_item()`，该函数（L1506-1525）构造一个 skip item：
- `bucket=_BUCKET_LOCAL_FIXTURE_ATTACHED_BY_SLICE3`（值为 `"local_fixture_attached_by_slice3"`）
- `reason` 明确说明 "当前 Slice 2 只验证 opt-in CLI、summary contract 与 diagnostics artifact 映射；local fixture smoke 由 Slice 3 接入。"
- `suggested_next_step` 指向 Slice 3

`_skipped_summary()`（未 opt-in 路径）不调用此函数，使用 `_BUCKET_NOT_OPTED_IN`，non-opt-in semantics 未变。

新增测试 `test_opted_in_without_local_cases_reports_slice3_fixture_skip` 锁定此行为。`test_external_limit_and_summary_paths_are_predictable` 也断言了 `local_fixture_attached_by_slice3` skip item 存在。

**结论**: 完全符合 controller adjudication 要求。non-opt-in 语义未受影响。

---

### 5. External schema validation 的 HTML-level fact check 意图是否清楚

**状态: 已修复**

新增 `_external_diagnostic_schema_gap()` 函数（L490-508），docstring 明确说明：

> 外部 URL 在 Slice 2 只用于 diagnostic-only 汇总，只需要 HTML 级别的 requests/fetch 事实；这里刻意不要求 PDF content-type、内容长度或 Docling invocation evidence，避免把外部样本误提升为 local PDF gate。

函数体调用 `_diagnostic_schema_gap(payload, case_kind=_CASE_LOCAL_HTML)`，意图通过函数名和 docstring 完全自解释。

`_classify_loaded_artifact` 的 external 分支（L792）调用 `_external_diagnostic_schema_gap(payload)` 而非直接调用 `_diagnostic_schema_gap(payload, case_kind=_CASE_LOCAL_HTML)`，消除了原 DS Finding 3 的意图模糊问题。

**结论**: 完全符合 controller adjudication 要求。

---

### 6. Deferred findings 是否仍可 deferred

| Finding | 状态 | 说明 |
|---|---|---|
| Docling 异常类型名内联 frozenset（原 MiMo Finding 3） | **仍可 deferred** | `{"DoclingRuntimeInitializationError", "ModuleNotFoundError", "ImportError"}` 仍在 L660 内联。值与 `diagnose_web_access.py` 一致，模块间分离合理。Owner: Slice 3 或 Slice 5。 |
| 默认超时值内联（原 MiMo Finding 4） | **仍可 deferred** | `15.0`（L1544）和 `30.0`（L1545）仍在 argparse 定义中内联。argparse 默认值是声明式配置，严重性低于逻辑分支中的散落字面量。Owner: Slice 3 或 Slice 5。 |

两个 deferred finding 均未被 fix gate 触及，严重性未变化，仍可按原计划 deferred。

---

### 7. 验证是否通过

| 验证项 | 结果 |
|---|---|
| `pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q` | **25 passed in 0.35s** |
| `pyright utils/smoke_web_ci.py tests/tools/web/test_smoke_web_ci.py` | **0 errors, 0 warnings, 0 informations** |
| `git diff --check` | **通过** |

---

## Finding 状态汇总

| # | Finding | 来源 | 状态 |
|---|---|---|---|
| 1 | Exit code `0`/`1`/`2` 魔法数字 | MiMo F1 / Controller | **已修复** |
| 2 | `not_opted_in` bucket 内联字符串 | MiMo F2 / DS F4 / Controller | **已修复** |
| 3 | `_STDIO_PREFIX_CHARS` / `_prefix_text` 死代码 | DS F1 / Controller | **已修复** |
| 4 | Opt-in 无 local cases 的 summary 信号 | DS F2 / DS F5 / Controller | **已修复** |
| 5 | External schema validation 意图不清 | DS F3 / Controller | **已修复** |
| 6 | Docling 异常类型名内联 | MiMo F3 / Controller | **Deferred**（Slice 3/5） |
| 7 | 默认超时值内联 | MiMo F4 / Controller | **Deferred**（Slice 3/5） |
| 8 | dataclass `Args:` vs `Attributes:` | MiMo F5 | **Accepted**（已知惯例差异） |
| 9 | 日期格式字符串内联 | MiMo F6 | **Accepted**（极低优先级） |

---

## Controller Adjudication Compliance

| Required Action | Compliance |
|---|---|
| Add `_EXIT_OK`, `_EXIT_LOCAL_FAILURE`, `_EXIT_SCHEMA_OR_INFRA_FAILURE` constants | **DONE** — L37-39 |
| Add `_BUCKET_NOT_OPTED_IN` and use in `_skipped_summary` | **DONE** — L44, L1231 |
| Remove `_STDIO_PREFIX_CHARS` and `_prefix_text` | **DONE** — grep 确认不存在 |
| Add explicit skip item for opt-in/no-local-case Slice 2 state | **DONE** — `_slice2_local_fixture_skip_item()`, `extra_skips` 参数 |
| Non-opt-in semantics unchanged | **DONE** — `_skipped_summary` 路径不涉及 `_slice2_local_fixture_skip_item` |
| Add comment/helper for external `_CASE_LOCAL_HTML` usage | **DONE** — `_external_diagnostic_schema_gap()` with docstring |
| Deferred findings stay deferred | **DONE** — 未触及 |
| Test data may still assert numeric exit codes | **DONE** — 测试使用 `0`/`1`/`2` 字面量 |

---

## Residual Risks

| 风险 | 严重性 | 说明 |
|---|---|---|
| Docling 异常类型名内联 frozenset | Low | Deferred to Slice 3/5，值与 diagnose_web_access.py 一致 |
| 默认超时值无常量 | Very Low | Deferred to Slice 3/5，argparse 声明式配置 |
| dataclass `Args:` vs `Attributes:` 惯例 | Info | Slice 1 已 accepted-low |
| Slice 2 仍无 local fixture 端到端验证 | Medium | 设计内，等待 Slice 3 |

---

## Final Recommendation: **pass**

**理由**:

1. **Controller adjudication 全部 5 项 required action 均已完成**，无遗漏。
2. **测试通过**：25 passed，0 errors。
3. **pyright 通过**：0 errors, 0 warnings。
4. **Non-opt-in 语义未变**：`_skipped_summary` 路径完全独立于 `_slice2_local_fixture_skip_item`。
5. **Deferred findings 未被意外触及**，严重性未变化。
6. **新增 1 个测试** `test_opted_in_without_local_cases_reports_slice3_fixture_skip` 锁定 opt-in/no-local-case 信号。
7. **代码质量**：无新增 `Any`/`object`/无类型签名；所有函数完整中文 docstring；无 import 越界。

fix gate 修复完整，可推进至下一阶段。
