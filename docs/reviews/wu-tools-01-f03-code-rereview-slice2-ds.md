# WU-TOOLS-01-F03 Slice 2 Code Re-Review — AgentDS

## Re-Review Context

- **Work unit**: WU-TOOLS-01-F03 Web CI Smoke Generation
- **Slice**: Slice 2 fix gate re-review
- **Agent**: AgentDS (re-review only, no file modifications)
- **Date**: 2026-06-10
- **Input artifacts**:
  - `docs/reviews/wu-tools-01-f03-implementation-slice2-codex.md`
  - `docs/reviews/wu-tools-01-f03-code-review-slice2-mimo.md`
  - `docs/reviews/wu-tools-01-f03-code-review-slice2-ds.md`
  - `docs/reviews/wu-tools-01-f03-code-review-slice2-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f03-fix-slice2-codex.md`
- **Re-review target** (uncommitted):
  - `utils/smoke_web_ci.py`
  - `tests/tools/web/test_smoke_web_ci.py`

---

## Finding Status Table

| # | Finding | 来源 | 状态 | 证据 |
|---|---|---|---|---|
| 1 | exit code `0`/`1`/`2` 散落为魔法数字 | MiMo F1 | **已修复** | `_EXIT_OK`、`_EXIT_LOCAL_FAILURE`、`_EXIT_SCHEMA_OR_INFRA_FAILURE` 已定义（L37-39），全文语义 exit code 引用均使用常量，无散落字面量。测试中数值断言为 external contract 验证，符合 adjudication 豁免。 |
| 2 | `"not_opted_in"` bucket 未提取为常量 | MiMo F2 / DS F4 | **已修复** | `_BUCKET_NOT_OPTED_IN` 已定义（L44），`_skipped_summary` 中使用该常量（L1231）。 |
| 3 | `_STDIO_PREFIX_CHARS` / `_prefix_text` 死代码 | DS F1 | **已修复** | 两个符号已从文件中完全移除，全文搜索无匹配。 |
| 4 | Opt-in 后无 local cases 的 Slice 2 中间态不可见 | DS F2 / DS F5 | **已修复** | 新增 `_slice2_local_fixture_skip_item()`（L1506-1525），返回 `bucket=local_fixture_attached_by_slice3` 的 `SmokeItem`，明确说明 "local fixture smoke 由 Slice 3 接入"。仅在 `_execute_smoke()` 的 opt-in 路径注入（L1502），`_skipped_summary()` 的未 opt-in 路径不受影响。常量 `_BUCKET_LOCAL_FIXTURE_ATTACHED_BY_SLICE3` 已定义（L45）。测试 `test_opted_in_without_local_cases_reports_slice3_fixture_skip` 锁定此行为。测试 `test_external_limit_and_summary_paths_are_predictable` 也断言该 skip signal 存在。 |
| 5 | External schema validation 硬编码 `_CASE_LOCAL_HTML`，意图不清 | DS F3 | **已修复** | 新增 `_external_diagnostic_schema_gap()`（L490-508），docstring 明确说明 "外部 URL 在 Slice 2 只用于 diagnostic-only 汇总，只需要 HTML 级别的 requests/fetch 事实；这里刻意不要求 PDF content-type、内容长度或 Docling invocation evidence，避免把外部样本误提升为 local PDF gate"。`_classify_loaded_artifact` external 分支调用该函数（L792），代码意图自解释。 |
| 6 | Docling 异常类型名内联 | MiMo F3 | **未修复（deferred）** | `_docling_init_skip()` L660 仍使用内联 frozenset。Adjudication 明确 defer 到 Slice 3 或 Slice 5，当前决策仍然有效。 |
| 7 | 默认超时值内联 | MiMo F4 | **未修复（deferred）** | `--request-timeout` default=15.0（L1544）、`--tool-timeout-budget` default=30.0（L1545）仍为 argparse 内联。Adjudication 明确 defer 到 Slice 3 或 Slice 5，当前决策仍然有效。 |
| 8 | Dataclass docstring `Args:` vs `Attributes:` | MiMo F5 | **未修复（accepted-low）** | 所有 dataclass 仍使用 `Args:`。Slice 1 已 accepted-low，adjudication 维持此裁决。 |
| 9 | 日期格式字符串内联 | MiMo F6 | **未修复（accepted）** | `_utc_run_label()` L309 仍使用内联格式字符串。Adjudication 维持为 accepted 极低优先级。 |

---

## 逐范围检查

### Exit code semantic literals → 已修复

全文搜索 `exit_code\s*=\s*[012]` 在 `utils/smoke_web_ci.py` 中无匹配。所有语义 exit code 赋值均使用常量：

- `_EXIT_OK` — 15 处引用（L37 定义 + L782, L813, L822, L891, L1040, L1081, L1188, L1194, L1239 使用）
- `_EXIT_LOCAL_FAILURE` — 7 处引用（L38 定义 + L829, L860, L870, L925, L936, L947, L958 使用）
- `_EXIT_SCHEMA_OR_INFRA_FAILURE` — 8 处引用（L39 定义 + L841, L1126, L1148, L1189, L1190, L1620, L1623, L1634 使用）

测试文件中的数值断言（`exit_code=1`、`exit_code=2`、`exit_code=0`）用于验证 SmokeCaseResult 构造，属于 external contract 验证，符合 adjudication 豁免条件。

### `not_opted_in` bucket → 已修复

- L44: `_BUCKET_NOT_OPTED_IN: Final[str] = "not_opted_in"` 定义。
- L1231: `bucket=_BUCKET_NOT_OPTED_IN` 使用。
- 全文仅 L44 包含裸字符串 `"not_opted_in"`（即常量定义本身）。

### `_STDIO_PREFIX_CHARS` / `_prefix_text` 死代码 → 已修复

全文搜索两个符号均无匹配。已从模块中完全移除。

### Opt-in but no local cases → 已修复

实现分三层：

1. **常量定义**（L45）: `_BUCKET_LOCAL_FIXTURE_ATTACHED_BY_SLICE3`
2. **工厂函数**（L1506-1525）: `_slice2_local_fixture_skip_item()` — 返回 `SmokeItem`，reason 明确说明 "当前 Slice 2 只验证 opt-in CLI、summary contract 与 diagnostics artifact 映射；local fixture smoke 由 Slice 3 接入"
3. **注入点**（L1502）: `_execute_smoke()` 的 `_summary_from_cases(extra_skips=(_slice2_local_fixture_skip_item(),))` — 仅 opt-in 路径生效

非 opt-in 的 `_skipped_summary()` 不受影响，`not_opted_in` skip item 保持不变。non-opt-in semantics 未变。

测试覆盖：
- `test_opted_in_without_local_cases_reports_slice3_fixture_skip` — 直接验证 Slice 3 信号
- `test_external_limit_and_summary_paths_are_predictable` — 验证 external+opt-in 场景下 Slice 3 信号仍存在

### External schema validation 意图 → 已修复

`_external_diagnostic_schema_gap()`（L490-508）替代原内联 `_diagnostic_schema_gap(payload, case_kind=_CASE_LOCAL_HTML)` 调用。docstring 完整解释了设计意图：外部 URL 只做 HTML 级别的 requests/fetch 事实检查，不要求 PDF 字段。调用点（L792）在 `_classify_loaded_artifact` 的 `case_kind == _CASE_EXTERNAL` 分支中。

### Deferred findings → 仍可 deferred

| Finding | 当前状态 | 为何仍可 defer |
|---|---|---|
| Docling 异常类型名 | L660 内联 frozenset | 值与 `diagnose_web_access.py` 一致；模块间分离合理；Slice 3 使用时可一并提取 |
| 默认超时值 | L1544-1545 argparse 内联 | 声明式配置，不参与逻辑分支；Slice 3 接入 local fixture 时可提取 |
| Dataclass docstring | 全文件 `Args:` | Slice 1 已裁决；Slice 5 统一处理 |
| 日期格式字符串 | L309 内联 | 单处使用，纯格式化 |

Fix gate 未引入新的 defer-to-fix 依赖，上述 defer 决定不被新的代码路径挑战。

---

## 独立验证结果

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q
# 25 passed in 0.35s

source .venv/bin/activate && python -m pyright utils/smoke_web_ci.py tests/tools/web/test_smoke_web_ci.py
# 0 errors, 0 warnings, 0 informations

git diff --check
# (无空白错误)
```

与 fix gate artifact 声明一致。测试数量从 24 增至 25（新增 `test_opted_in_without_local_cases_reports_slice3_fixture_skip`）。

---

## 新发现检查

在 re-review 过程中未发现 fix gate 引入的新 issue。具体检查：

- `_external_diagnostic_schema_gap()` 是 `_diagnostic_schema_gap(case_kind=_CASE_LOCAL_HTML)` 的语义包装，功能等价，不改变分类逻辑。
- `_slice2_local_fixture_skip_item()` 工厂函数返回固定的 `SmokeItem`，仅在 `_execute_smoke()` 的 `extra_skips` 中注入，不参与 exit code 计算。
- 新增常量（`_EXIT_OK`、`_EXIT_LOCAL_FAILURE`、`_EXIT_SCHEMA_OR_INFRA_FAILURE`、`_BUCKET_NOT_OPTED_IN`、`_BUCKET_LOCAL_FIXTURE_ATTACHED_BY_SLICE3`）均遵循 `Final[str]`/`Final[int]` 模式，与现有常量一致。
- 死代码移除不触及任何被引用的符号。

---

## Residual Risks（更新后）

| 风险 | 严重性 | 说明 |
|---|---|---|
| Slice 2 无 local HTTP fixture → 无法端到端验证 local smoke 判定 | Medium | 设计内，等待 Slice 3。`_slice2_local_fixture_skip_item()` 已显式标记此中间态。 |
| Docling init exception 字符串与 `diagnose_web_access.py` 重复定义 | Low | Deferred to Slice 3/5 |
| External site anti-bot/DNS/timeout/Playwright 稳定性 | Low | diagnostic-only by design |
| Diagnostics wrapper instrumentation 在生产 callable 名称变更时失效 | Low | Slice 1 residual，不因 Slice 2 恶化或改善 |

---

## Final Recommendation: **pass**

**理由**:

1. Controller adjudication 指定的 5 项 required fixes **全部已修复**，独立验证通过。
2. 4 项 deferred/accepted findings **仍然可 defer/accept**，fix gate 未引入新的 defer-to-fix 依赖。
3. Fix gate 未引入新 issue，代码质量未退化。
4. 测试全部通过（25 passed），pyright 零报错，git diff 无空白问题。
5. Slice 2 功能正确且符合 plan 要求，可推进到 Slice 3 或下一 gate。
