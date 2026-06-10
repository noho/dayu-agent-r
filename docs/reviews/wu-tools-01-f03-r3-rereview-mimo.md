# WU-TOOLS-01-F03-R3 Fix Re-Review — AgentMiMo

## Scope

- Gate: fix re-review
- Agent: MiMo
- 审查范围：只验证 Controller accepted findings 是否修复，不改文件。
- 参考：
  - 原 code review：`docs/reviews/wu-tools-01-f03-r3-code-review-mimo.md`、`docs/reviews/wu-tools-01-f03-r3-code-review-ds.md`
  - fix artifact：`docs/reviews/wu-tools-01-f03-r3-fix-codex.md`
  - 当前 git diff（8 files）
- Controller 复验：`pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`：39 passed；`pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/tools/web/test_web_tools_provider.py tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`：133 passed；`python -m pyright dayu/ tests/ utils/`：0 errors；`git diff --check`：passed。

---

## Findings

### F1 — Docling blocker early return 时 search provider diagnostics 仍运行

**结论：已修复。**

`_execute_smoke` 中 `_run_search_provider_cases()` 调用已移至 `_has_docling_invocation_blocker` 检查之前（diff line 3329）：

```python
local_cases = _run_local_cases(options=options, runner=runner)
search_cases = _run_search_provider_cases(options=options)   # 在 blocker 检查前执行
if _has_docling_invocation_blocker(local_cases):
    ...
    summary = _summary_from_cases(..., search_cases=search_cases)  # search_cases 传入 summary
```

验证：
- Docling blocker 分支仍写 blocker artifact。
- Docling blocker 分支仍跳过 external cases（`external_cases=()`）。
- search_cases 不依赖 Docling，结果传入 `_summary_from_cases(search_cases=...)`。
- search assembly failure（ConfigLoader/discovery 失败）通过 `hard_gate_cases = tuple(local_cases) + tuple(search_cases)` 进入 summary，贡献 schema/infra exit code。
- 新增测试 `test_pdf_invocation_blocker_runs_search_cases_and_stops_external_cases` 断言：`summary.external_cases == ()`、`len(summary.search_cases) == 4`、`len(summary.diagnostic_only) == 4`。

### F2 — `discovered_configs` 不再是 `list[object]`

**结论：已修复。**

`tests/tools/web/test_smoke_web_ci.py` line 319：

```python
discovered_configs: list[smoke.RuntimeConfig] = []
```

类型已从 `list[object]` 改为 `list[smoke.RuntimeConfig]`。`smoke.RuntimeConfig` 作为 type alias 可用。pyright 通过。

### F4 — `_tool_context` 取消 cast 后 pyright 仍通过

**结论：已修复，有合理说明。**

`utils/smoke_web_ci.py` `_tool_context()` 中：

```python
cancellation_token=_OpenCancellationToken(),
```

`cast(CancellationToken, ...)` 已移除。验证 `CancellationToken` Protocol（`dayu/contracts/cancellation.py:21`）与 `_OpenCancellationToken` 的结构化兼容性：

| Protocol 方法 | `_OpenCancellationToken` 方法 | 签名匹配 |
|---|---|---|
| `is_cancelled(self) -> bool` | `is_cancelled(self) -> bool` | 完全匹配 |
| `cancel_reason(self) -> str \| None` | `cancel_reason(self) -> str \| None` | 完全匹配 |
| `requested_at(self) -> datetime \| None` | `requested_at(self) -> datetime \| None` | 完全匹配 |

三个方法签名完全一致，pyright structural subtyping 自动满足。`python -m pyright dayu/ tests/ utils/` 通过 0 errors。

---

## Regression 检查

- **新增 test regression**：无。133 passed 全部通过，与原 code review 时一致。
- **Secret 泄漏**：无。artifact 只写 `api_key_env`（env 变量名）和 `api_key_present`（bool），不写 key 值。
- **Hard/diagnostic-only 语义漂移**：无。search assembly failure（ConfigLoader/discovery/tool missing）仍为 `status=failed, exit_code=非0`；search callable 失败仍为 `status=diagnostic_only, exit_code=0`。`hard_gate_cases = tuple(local_cases) + tuple(search_cases)` 正确包含 search assembly 级失败。
- **分层违反**：无。`utils/smoke_web_ci.py` import 的 `ConfigLoader`、`RuntimeConfig`、`discover_service_tools` 均为 Service/Runtime 公共 API，与原 code review 判断一致。
- **pyright 扩散**：无。0 errors。

---

## Open Questions

无。F3（中文错误文本 heuristic）和 F5（`_ASSEMBLY_PROVIDER_CONFIG` module-level dict）为 Controller 未接受的 intentional no-fix，fix artifact 已明确说明，不阻塞本次 re-review。

---

## Verdict

**pass**

三个 accepted findings（F1、F2、F4）均已修复：
- F1：`_run_search_provider_cases()` 在 Docling blocker 检查前执行，search_cases 传入 summary，Docling blocker 分支仍跳过 external cases，search assembly failure 仍贡献 hard gate exit code。新增 deterministictest 覆盖。
- F2：`discovered_configs` 类型从 `list[object]` 改为 `list[smoke.RuntimeConfig]`。
- F4：`cast` 已移除，`_OpenCancellationToken` 与 `CancellationToken` Protocol 完全结构匹配，pyright 通过。

无新 regression、无 secret 泄漏、无 hard/diagnostic-only 语义漂移。
