# WU-TOOLS-01-F01-02-R3 Slice 4 Fix Re-Review — DS

## Review Metadata

- **Reviewer**: AgentDS
- **Date**: 2026-06-10
- **Gate**: focused re-review (post-fix)
- **Scope**: accepted finding S4-CR-01 fix only
- **Reviewed files**:
  - `tests/tools/test_doc_tools_provider.py`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice4-fix-codex.md`
- **Input artifacts**:
  - `docs/reviews/wu-tools-01-f01-02-r3-slice4-code-review-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice4-fix-codex.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice4-code-review-mimo.md`
  - `docs/reviews/wu-tools-01-f01-02-r3-slice4-code-review-ds.md`

## Verdict: PASS

Fix 精确对齐 Controller adjudication 要求，无新增问题，所有检查点通过。

---

## 1. Checkpoint-by-Checkpoint Verification

### 1.1 `test_read_tools_expose_current_truncate_spec_and_no_old_imports` 重新读取 doc_provider.py

**要求**: 恢复读取 `dayu/tools/doc_provider.py` 并在测试中对其做 AST import 扫描。

**实际** (lines 917-927):
```python
tools_root = Path(__file__).resolve().parents[2] / "dayu" / "tools"
doc_tools_source = (tools_root / "doc_tools.py").read_text(encoding="utf-8")
doc_provider_source = (tools_root / "doc_provider.py").read_text(encoding="utf-8")
old_runtime_modules = {
    "dayu.engine.tool_registry",
    "dayu.engine.truncation_manager",
    "dayu.engine.tool_result",
}
for source in (doc_tools_source, doc_provider_source):
    imported_modules = _imported_modules(source)
    assert old_runtime_modules.isdisjoint(imported_modules)
```

- `doc_provider_source` 已恢复（line 919）。
- `_imported_modules(...)` 对 **两个** source 执行（line 925-927）。
- 循环语义清晰：两个源码文件统一通过同一 denylist 检查。
- ✅ **通过**。

### 1.2 OLD runtime denylist 覆盖 doc_tools.py 和 doc_provider.py

**要求**: 两个文件都检查 `dayu.engine.tool_registry`、`dayu.engine.truncation_manager`、`dayu.engine.tool_result`。

**实际**:
- Denylist 定义（lines 920-924）包含全部 3 个 OLD runtime 模块。
- `for source in (doc_tools_source, doc_provider_source):` 遍历两个文件。
- `assert old_runtime_modules.isdisjoint(imported_modules)` 确保任一文件导入任一 denylist 模块时断言失败。
- ✅ **通过**。

### 1.3 无 legacy adapter 字符串断言恢复

**要求**: 不重新引入 `_legacy_adapter`、`LegacyToolDeclarationCollector`、`adapt_collected_tools` 字符串断言。

**实际**:
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" tests/tools/test_doc_tools_provider.py` → exit 1（零命中）。
- 对比原始 Slice 4 diff：已删除的 4 行负向断言（`"_legacy_adapter" not in doc_tools_source`、`"_legacy_adapter" not in doc_provider_source`、`"LegacyToolDeclarationCollector" not in doc_provider_source`、`"adapt_collected_tools" not in doc_provider_source`）**未恢复**。
- ✅ **通过**。

### 1.4 全局 legacy rg 零命中

**要求**: `dayu/tests` 下 legacy rg 仍零命中。

**实际**:
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests` → exit 1（零命中）。
- ✅ **通过**。

### 1.5 无修改生产代码、README 或其它非范围文件

**要求**: Fix 只触及 `tests/tools/test_doc_tools_provider.py` 和 fix artifact。

**实际**:
- `git diff --name-only` 显示所有变更文件均为 Slice 4 原有改动（adapter 删除 + test 更新 + README 更新）。
- Fix 在 Slice 4 基础上仅进一步修改 `tests/tools/test_doc_tools_provider.py`。
- `dayu/fins/README.md` 和 `tests/README.md` 的修改属于 Slice 4 原始 scope，非 fix 引入。
- ✅ **通过**。

---

## 2. Controller Fix 后验证

### 2.1 pytest: 36 passed（focused）

```
$ pytest tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
36 passed, 3 warnings in 1.56s
```

✅ **通过**。3 个 edgar deprecation warnings 为第三方库问题，与本次变更无关。

### 2.2 pytest: 108 passed（完整 Slice 4 子集）

```
$ pytest tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py \
  tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_storage_provider.py \
  tests/tools/test_combined_tools_acceptance.py tests/host/test_import_boundary.py \
  tests/service/test_import_boundary.py -q
108 passed, 3 warnings in 3.37s
```

✅ **通过**。

### 2.3 pyright: 0 errors

```
0 errors, 0 warnings, 0 informations
```

✅ **通过**。

### 2.4 git diff --check: passed

```
exit 0, no output
```

✅ **通过**。无空白字符违规。

### 2.5 legacy rg: no matches

```
$ rg "_legacy_adapter|LegacyToolDeclarationCollector|adapt_collected_tools" dayu tests
exit 1
```

✅ **通过**。

---

## 3. AGENTS.md 合规性

| 约束 | 检查结果 |
|---|---|
| 禁止兼容性 re-export / wrapper | ✅ Fix 仅修改测试，不引入任何生产代码变更 |
| 禁止胶水 seam | ✅ 无新增 seam |
| 修改后必做（pytest / pyright / git diff --check） | ✅ 已全部独立验证 |
| 测试跟着实现边界迁移 | ✅ 测试变更仅强化已有防线，未新增兼容逻辑 |
| README 更新触发规则 | ✅ Fix 不触及任何 README 更新触发条件 |

---

## 4. Fix 质量评估

### 4.1 正确性

Fix 精确还原了 Controller adjudication 要求的行为：
- `doc_provider.py` 重新被读取并通过 `_imported_modules()` 扫描。
- 扫描逻辑统一循环处理两个文件，消除代码重复。
- Denylist 用 `set` + `isdisjoint()` 实现，比原来的逐条 `assert "X" not in imported_modules` 更简洁且更容易扩展。
- `fetch_more` 和 `TruncationManager` 的字符串断言保留在 `doc_tools_source` 上（这两个 token 属于 ToolRuntime owner 防御，不是 OLD runtime import 防御），逻辑合理。

### 4.2 可维护性

- 循环模式使新增被扫描文件变得简单（只需加一个 source）。
- `old_runtime_modules` 集合独立命名，意图明确。
- 测试 docstring 已更新为"不导入 OLD runtime"，语义准确。

### 4.3 无副作用

- 未修改任何生产代码。
- 未修改 README。
- 未修改 Combined Acceptance、Host Import Boundary 或其它测试。
- 未恢复 adapter 符号断言。

---

## 5. Residual Risks

| Risk | Status |
|---|---|
| `doc_provider.py` 当前不含 OLD runtime import，但未来维护者可能在不知情下引入 | 防线已建立：本测试 + combined acceptance 双重覆盖 |
| `fetch_more` / `TruncationManager` 检查仅作用于 `doc_tools_source`，未扩展至 `doc_provider_source` | 低风险：这两个 token 的 owner 是 ToolRuntime/tooling/ToolsDiscovery（见 Host Import Boundary 测试），doc_provider 引入它们的概率极低；且 combined acceptance 的 `test_native_providers_do_not_import_old_runtime` 覆盖了 `fetch_more` 的全局扫描 |
| 3 个 edgar deprecation warnings | 第三方库问题，非本次变更引入 |

---

## 6. 结论

S4-CR-01 fix 精确、最小化、无副作用。所有 5 个检查点通过，所有 Controller fix 后验证命令通过。**PASS**。

**下一 gate**: Slice 4 已通过 code review + fix + focused re-review 完整闭环，可进入 R3 aggregate deepreview 或直接进入 draft PR gate。
