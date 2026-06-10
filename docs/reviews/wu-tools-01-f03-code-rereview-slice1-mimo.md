# WU-TOOLS-01-F03 Slice 1 Code Re-Review — AgentMiMo

## Review Target

- **Gate**: fix gate re-review
- **Changed files**:
  - `utils/diagnose_web_access.py`
  - `tests/tools/web/test_diagnose_web_access.py`
- **Fix artifact**: `docs/reviews/wu-tools-01-f03-fix-slice1-codex.md`
- **Controller adjudication**: `docs/reviews/wu-tools-01-f03-code-review-slice1-controller-adjudication.md`
- **Date**: 2026-06-10

---

## Finding 状态总览

| # | 来源 | 描述 | 裁决 | 状态 |
|---|---|---|---|---|
| DS-1 | DS Finding 1 / controller required fix | `_DIAGNOSTIC_SCHEMA_REVISION` 应为 1 而非 2 | accepted (required) | **已修复** |
| DS-2 | DS Finding 2 | `_DOCLING_DEPENDENCY_EXCEPTION_TYPES` 字符串匹配不捕获子类 | deferred-with-owner | **仍可 deferred** |
| MiMo-1 / DS-3 | MiMo Finding 1 / DS Finding 3 | `_observed_failing_path_from_payload` bucket-as-path fallback | accepted-low | **已添加注释，行为不变，可接受** |
| MiMo-2 | MiMo Finding 2 | `_DoclingInvocationEvidence` dataclass docstring Args vs Attributes | accepted-low | **未修改，不阻塞** |
| DS-4 | DS Finding 4 | `schema_version` 与 `diagnostic_schema_version` 值相同 | accepted-low | **已添加注释，可接受** |
| MiMo-3/4/6 | MiMo Findings 3/4/6 | Info findings | accepted | **无需修改** |

---

## Required Fix 验证：DS Finding 1

**要求**: `_DIAGNOSTIC_SCHEMA_REVISION` 从 `2` 改为 `1`，同步更新测试断言。

**验证**:

- `utils/diagnose_web_access.py:54`: `_DIAGNOSTIC_SCHEMA_REVISION: Final[int] = 1` — **已修复**
- `tests/tools/web/test_diagnose_web_access.py:819`: `assert payload["diagnostic_schema_revision"] == 1` — **已修复**
- 所有引用 `_DIAGNOSTIC_SCHEMA_REVISION` 的位置（payload 构建、batch row、summary、child error payload、error payload）统一使用常量，值一致为 `1`。

**结论**: 已修复。版本语义自洽——这是 `web-diagnostics-v1` schema 的第一次显式 revision。

---

## Optional Accepted-Low 评论验证

### MiMo-1 / DS-3: `_observed_failing_path_from_payload` fallback 注释

`utils/diagnose_web_access.py:2599`:

```python
# 当前 fallback 仅服务既有 comparison bucket；新增 bucket 时需同步确认其是否代表真实失败路径。
return comparison_bucket
```

**结论**: 已添加局部化注释，行为未变。注释准确描述了同步要求。可接受。

### DS-4: schema constants 注释

`utils/diagnose_web_access.py:51-52`:

```python
# schema_version 标识 diagnostics artifact schema；diagnostic_schema_version/revision
# 是 F03 smoke 校验同一 artifact 时使用的显式标记。
```

**结论**: 已添加局部化注释，说明两个字段的来源和演进关系。可接受。

### MiMo-2: dataclass docstring Args vs Attributes

未修改。dataclass 字段文档使用 `Args:` 而非 `Attributes:` 是惯例差异，不影响功能或可读性。controller 裁决为 accepted-low 且不阻塞。

**结论**: 仍可 deferred，不阻塞 Slice 1。

---

## Deferred Findings 验证

### DS Finding 2: `_DOCLING_DEPENDENCY_EXCEPTION_TYPES` 字符串匹配

fix artifact 明确标注 "No evidence in this fix gate requires changing dependency exception classification"。

当前窄 wrapper 路径只处理 `DoclingRuntimeInitializationError`、`ModuleNotFoundError`、`ImportError` 三种具体异常。在 Docling runtime 上下文中，这些内置异常通常不被子类化。

**结论**: 仍可 deferred。不阻塞 Slice 1，留给 smoke 实际使用时观察。

---

## Fix Gate 副作用检查

fix gate 除 required fix 和 accepted-low 注释外，还应检查是否引入了新的风险：

1. **常量值一致性**: `_DIAGNOSTIC_SCHEMA_REVISION = 1` 在所有 7 处引用中一致。
2. **注释质量**: 两处新注释准确、简洁、不引入错误信息。
3. **测试覆盖**: 19 passed，未减少测试数量。
4. **类型安全**: pyright 0 errors。
5. **无新增依赖或 import**: fix gate 未新增任何 import。

**结论**: 无副作用风险。

---

## 验证结果

- `pytest tests/tools/web/test_diagnose_web_access.py -q`: **19 passed in 0.34s**
- `pyright utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py`: **0 errors, 0 warnings, 0 informations**
- `git diff --check`: **无 whitespace 错误**

---

## Final Recommendation: **pass**

Slice 1 fix gate 后状态满足全部要求：

1. **Required fix (DS-1)**: `_DIAGNOSTIC_SCHEMA_REVISION` 已从 `2` 改为 `1`，测试同步更新。版本语义自洽。
2. **Accepted-low 注释**: 两处局部化注释已添加，行为不变，风险不增加。
3. **Deferred findings**: DS-2 仍可 deferred，不阻塞 Slice 1。
4. **无新增风险**: fix gate 未引入副作用。
5. **验证通过**: 19 tests pass, pyright 0 errors, 无 whitespace 错误。

**Slice 1 可进入下一阶段。**
