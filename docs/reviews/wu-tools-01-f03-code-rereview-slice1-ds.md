# WU-TOOLS-01-F03 Slice 1 Code Re-Review — AgentDS

## Re-Review Context

- **Work unit**: WU-TOOLS-01-F03 Slice 1: Diagnostics Observed Facts and Docling Invocation Evidence
- **Trigger**: controller adjudication required fix gate → AgentCodex dispatched fix → AgentDS re-review
- **Input artifacts**:
  - Implementation: `docs/reviews/wu-tools-01-f03-implementation-slice1-codex.md`
  - MiMo review: `docs/reviews/wu-tools-01-f03-code-review-slice1-mimo.md`
  - DS review: `docs/reviews/wu-tools-01-f03-code-review-slice1-ds.md`
  - Controller adjudication: `docs/reviews/wu-tools-01-f03-code-review-slice1-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-tools-01-f03-fix-slice1-codex.md`
- **Review date**: 2026-06-10
- **Re-review scope**: fix gate 后状态；DS Finding 1 required fix、accepted-low comments、deferred findings、verification

---

## Finding Status

### DS Finding 1 [MEDIUM] `_DIAGNOSTIC_SCHEMA_REVISION = 2` 缺少 revision 1

**状态**: **已修复**

**证据**:

- `utils/diagnose_web_access.py:54`: `_DIAGNOSTIC_SCHEMA_REVISION: Final[int] = 1`
- `tests/tools/web/test_diagnose_web_access.py:819`: `assert payload["diagnostic_schema_revision"] == 1`
- `_build_single_diagnostic_payload` / `_child_error_payload` / `_build_batch_summary` / `_build_batch_result_row` / error payload 全部引用 `_DIAGNOSTIC_SCHEMA_REVISION`，一致性验证通过。

revision 从 1 起步，语义自洽：`web-diagnostics-v1` schema 的第一次 revision（Slice 1 新增 observed facts + Docling evidence）。

---

### Controller accepted-low: schema constants comment

**状态**: **已实施，未引入风险**

**证据**: `utils/diagnose_web_access.py:51-52`:
```python
# schema_version 标识 diagnostics artifact schema；diagnostic_schema_version/revision
# 是 F03 smoke 校验同一 artifact 时使用的显式标记。
```

纯注释，不改变任何行为。解释了 `schema_version` 与 `diagnostic_schema_version` 并存的语义差异。

---

### Controller accepted-low: `_observed_failing_path_from_payload` fallback comment

**状态**: **已实施，未引入风险**

**证据**: `utils/diagnose_web_access.py:2599`:
```python
# 当前 fallback 仅服务既有 comparison bucket；新增 bucket 时需同步确认其是否代表真实失败路径。
```

纯注释，不改变任何行为。文档化了 fallback 的同步约束。

---

### DS Finding 2 [LOW] `_DOCLING_DEPENDENCY_EXCEPTION_TYPES` 字符串匹配

**状态**: **仍可 deferred，不阻塞 Slice 1**

**证据**: `_DOCLING_DEPENDENCY_EXCEPTION_TYPES` 仍为 `frozenset[str]` 字符串匹配。当前 wrapper 的窄上下文路径已正确覆盖预期的具体异常类型（`DoclingRuntimeInitializationError`、`ModuleNotFoundError`、`ImportError`）。`DoclingRuntimeInitializationError` 额外通过 `isinstance` 覆盖，双保险。无实际遗漏证据。

---

### DS Finding 3 / MiMo Finding 1 `_observed_failing_path_from_payload` bucket-as-path fallback

**状态**: **仍可 deferred，不阻塞 Slice 1**

**证据**: 行为未改变。仅追加了注释。当前所有已知 comparison bucket 已有正确覆盖（排除列表 + failing_paths 分支）。Slate 1 plan 明确禁止新增 comparison bucket，故新增 bucket 忘记同步的风险在当前 scope 内不会触发。

---

### DS Finding 4 [LOW] `schema_version` 与 `diagnostic_schema_version` 并存

**状态**: **accepted-low，已通过注释缓解**

**证据**: 两个字段值仍相同（均为 `"web-diagnostics-v1"`）。注释已说明语义差异：一个标识 artifact schema，一个作为 smoke validation marker。无行为变更。

---

### MiMo Finding 2 [LOW] `_DoclingInvocationEvidence` dataclass docstring 惯例

**状态**: **仍可 deferred，不阻塞 Slice 1**

**证据**: docstring 未修改。`Args:` / `Returns:` / `Raises:` 仍用于描述 dataclass 构造。无功能影响。

---

### MiMo Finding 3/4/6 [Info] accepted

**状态**: **无需处置**

---

### MiMo Finding 5 [LOW] 测试未覆盖 challenge/browser_only bucket 投影

**状态**: **仍可 deferred，不阻塞 Slice 1**

**证据**: 核心路径（Docling 成功/未调用/init error/普通转换异常/child_process_error）已锁定。boundary bucket 投影测试可在 Slice 2 或 Slice 5 补充。

---

## Fix Gate 未引入新 Findings

对照 fix gate diff 逐项检查：

| 变更 | 风险评估 |
|---|---|
| `_DIAGNOSTIC_SCHEMA_REVISION = 2 → 1` | 常量值变更，所有引用点统一。无风险。 |
| 测试断言 `2 → 1` | 与常量同步。无风险。 |
| schema constants comment | 纯注释。无风险。 |
| `_observed_failing_path_from_payload` comment | 纯注释。无风险。 |

fix gate 只修改了两处行为（常量值 + 测试断言）和两处注释。未触及任何生产逻辑路径、wrapper 恢复、分类判定或 payload 结构。

---

## Verification 复核

| 命令 | 结果 |
|---|---|
| `pytest tests/tools/web/test_diagnose_web_access.py -q` | **19 passed in 0.36s** |
| `pyright utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py` | **0 errors, 0 warnings, 0 informations** |

---

## Residual Risks（不变）

| 风险 | 严重性 | 仍然适用？ |
|---|---|---|
| Wrapper 随生产 callable 名称变化失效 | Low | 是 — Slice 1 invariant |
| `_DOCLING_DEPENDENCY_EXCEPTION_TYPES` 不捕获异常子类 | Very Low | 是 — deferred |
| `_observed_failing_path_from_payload` bucket-as-path 语义 | Low | 是 — comment added |
| 外部站点/Playwright/Provider 可用性 | Low | 是 — Slice 2+ territory |
| Slice 1 只输出 facts，无 smoke exit code | Medium | 是 — 等待 Slice 2 |

---

## Final Recommendation: **pass**

DS Finding 1 required fix 已正确实施：`_DIAGNOSTIC_SCHEMA_REVISION` 从 `2` 改为 `1`，测试断言同步更新。accepted-low comments 未引入任何风险。所有 deferred findings 仍可 deferred，不阻塞 Slice 1。

所有 19 个 deterministic tests 通过，pyright 零错误。无回归。无新 findings。

Slice 1 fix gate 通过。实现可推进至 Slice 2。
