# WU-TOOLS-01-F03-R3 Fix Re-Review Artifact

## Gate / Scope

- Gate: fix re-review
- Work unit: `WU-TOOLS-01-F03-R3`
- 原 review: `wu-tools-01-f03-r3-code-review-mimo.md`、`wu-tools-01-f03-r3-code-review-ds.md`
- Fix artifact: `wu-tools-01-f03-r3-fix-codex.md`
- 审查范围: 只审查 accepted findings（MiMo F1、MiMo F2、MiMo F4）是否修复，以及是否引入新 regression/secret 泄漏/语义漂移。

---

## Controller 复验

- `pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`: **39 passed, 3 warnings**
- `python -m pyright dayu/ tests/ utils/`: **0 errors, 0 warnings, 0 informations**
- `git diff --check`: **passed**

所有 warnings 来自 `edgar` 依赖的 deprecation warning，与本次 fix gate 无关。

---

## Findings

### F1 — Docling invocation blocker 跳过 search cases → **已修复**

**验证：**

1. `_execute_smoke()` 中 `search_cases = _run_search_provider_cases(options=options)` 现在在第 3332 行，位于 `if _has_docling_invocation_blocker(local_cases)`（第 3333 行）之前。Search provider diagnostics 不依赖 Docling runtime，在 Docling blocker 激活时仍然运行。

2. Docling blocker 分支（第 3334-3349 行）正确传参：
   - `external_cases=()` — external URL cases 仍被跳过。
   - `search_cases=search_cases` — search 结果传入 summary，不再为空。

3. Search assembly infra 失败不会被吞：`_summary_from_cases` 第 1969 行 `hard_gate_cases = tuple(local_cases) + tuple(search_cases)`，search case 的 `exit_code` 参与最终 exit_code 判定。

4. 新增 deterministic 覆盖 `test_pdf_invocation_blocker_runs_search_cases_and_stops_external_cases`（第 620 行）：
   - monkeypatch 替换 assembly 和 search cases 为 deterministic fake。
   - 构造 local PDF Docling invocation blocker。
   - 断言 `external_cases == ()`、`len(summary.search_cases) == 4`、`len(summary.diagnostic_only) == 4`、`blocker_path.is_file()`。

**结论：F1 修复完整。** Search provider diagnostics 在 Docling blocker 激活时正确运行并进入 summary；external URL cases 仍被跳过；search assembly failure 通过 `hard_gate_cases` 语义传播，不被吞。

---

### F2 — `discovered_configs: list[object]` → **已修复**

**验证：**

`tests/tools/web/test_smoke_web_ci.py` 第 163 行：
```python
discovered_configs: list[smoke.RuntimeConfig] = []
```

已从 `list[object]` 改为 `list[smoke.RuntimeConfig]`。`smoke.RuntimeConfig` 是 `dayu.runtime.config_loader.RuntimeConfig` 的类型别名。类型信息完整，与同文件 `loaded_overlay_dirs: list[Path]` 的写法一致。

**结论：F2 修复完整。** 类型精确，无 `object` 残留。

---

### F4 — `cast(CancellationToken, ...)` 绕过类型检查 → **已修复**

**验证：**

1. `utils/smoke_web_ci.py` 第 1053 行，`_tool_context()` 中：
   ```python
   cancellation_token=_OpenCancellationToken(),
   ```
   已移除 `cast(CancellationToken, ...)`，直接传入 `_OpenCancellationToken()` 实例。

2. `CancellationToken` Protocol 定义（`dayu/contracts/cancellation.py`）声明三个方法：
   - `is_cancelled() -> bool`
   - `cancel_reason() -> str | None`
   - `requested_at() -> datetime | None`

3. `_OpenCancellationToken`（第 226-272 行）完整实现三个方法，返回类型精确匹配：
   - `is_cancelled(self) -> bool` → `False`
   - `cancel_reason(self) -> str | None` → `None`
   - `requested_at(self) -> datetime | None` → `None`

4. `CancellationToken` 是 `@runtime_checkable` Protocol，pyright 通过结构性子类型推断接受 `_OpenCancellationToken`。实际运行 `python -m pyright dayu/ tests/ utils/` 结果：**0 errors, 0 warnings, 0 informations**。

**结论：F4 修复完整。** cast 已移除，pyright 通过，Protocol 结构兼容性已验证。

---

### 回归检查

按原 DS review S1-S7 逐项核对当前 diff，确认未引入新问题：

| 检查项 | 结论 |
|---|---|
| Search assembly failure 不被吞 | 通过 — `hard_gate_cases` 在第 1969 行仍包含 search_cases |
| External URL cases 在 blocker 分支跳过 | 通过 — 第 3339 行 `external_cases=()` |
| Secret 泄漏 | 通过 — 新增代码无不安全字符串，`api_key_env`/`api_key_present` 只写 env 变量名和 bool |
| diagnostic_only 语义不变 | 通过 — search provider 失败仍为 exit_code=0，不改变 local hard gate |
| Typed search_cases 无弱类型口袋 | 通过 — `SmokeCaseResult` 为 frozen slots dataclass，无 metadata 字段 |
| pytest deterministic | 通过 — 新测试 `test_pdf_invocation_blocker_runs_search_cases_and_stops_external_cases` 使用 monkeypatch，不依赖 live network |
| 分层约束 | 通过 — 修改只在 `utils/smoke_web_ci.py` 和 `tests/` 内，不触及 `dayu/` 分层 |
| AGENTS.md 类型约束 | 通过 — 无新增 Any/object/cast/hasattr/getattr |

**无新回归、无 secret 泄漏、无 hard/diagnostic-only 语义漂移。**

---

## Intentional No-Fix（不在本 gate 范围）

以下两项在原 review 中为 accepted no-fix，本次 re-review 确认代码未变：

- **MiMo F3**：中文错误文本 heuristic 作为 secondary classifier，未修改。
- **MiMo F5**：`_ASSEMBLY_PROVIDER_CONFIG` module-level dict，未修改。

---

## Open Questions

无。三项 accepted findings 均已正确修复，无遗留问题。

---

## Verdict

**pass**

F1、F2、F4 三项修复均正确实施：
- F1：search provider diagnostics 在 Docling blocker 激活时运行并进入 summary，external 跳过，search assembly failure 不被吞。
- F2：`discovered_configs` 类型从 `list[object]` 修正为 `list[smoke.RuntimeConfig]`。
- F4：`cast(CancellationToken, ...)` 移除，`_OpenCancellationToken` 结构性满足 `CancellationToken` Protocol，pyright 通过。
- 无新回归、无 secret 泄漏、无语义漂移。
- Controller 复验：39 passed、pyright 0、git diff --check passed。
