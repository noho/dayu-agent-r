# Code Review — Re-review

## Scope

- Mode: current changes
- Branch: phaseflow/wu-tools-01
- Base: main (uncommitted workspace diff)
- Output file: docs/reviews/wu-tools-01-slice2-rereview-mimo.md
- Included scope: Controller-accepted S2 adapter fix — `dayu/tools/_legacy_adapter/definition_adapter.py`, `tests/tools/test_legacy_tool_adapter.py`; S2 config layer changes — `dayu/runtime/config_loader.py`, `dayu/service/host_assembly.py`, `dayu/config/tool_discovery.json`, `tests/runtime/test_config_loader.py`, `tests/service/test_host_assembly.py`
- Excluded scope: Doc/Fins/Web business tool implementations (S3/S4/S5), Host/Engine runtime changes, `dayu/contracts/` public contract
- Parallel review coverage: 无

## Expected Checks — Verification

| # | Check | Status | Evidence |
|---|-------|--------|----------|
| 1 | `adapt_collected_tools(...)` fails fast for reserved `fetch_more`, matching `adapt_collected_tool(...)` | ✅ pass | `definition_adapter.py:338-339` raises `ValueError`; `definition_adapter.py:311` same behavior |
| 2 | Generic success envelope detection requires `ok is True` and `value` key present; plain business dict with `ok` field remains plain value | ✅ pass | `definition_adapter.py:210-211` dual guard; `test_legacy_tool_adapter.py:368-385` verifies `{"ok": True, "status": "ready"}` preserved |
| 3 | Incomplete `ToolPathValidationPolicy` coverage fails before migrated callable invocation | ✅ pass | `definition_adapter.py:413-428` returns `permission_denied` before line 441+ path validation; `test_legacy_tool_adapter.py:260-329` verifies `calls == []` |
| 4 | `SERIAL_PER_PROVIDER` shared lock and generic exception projection tests exist and are meaningful | ✅ pass | `test_legacy_tool_adapter.py:548-641` proves cross-tool lock sharing with concurrent entry detection; `test_legacy_tool_adapter.py:408-438` proves `RuntimeError` → `execution_error` |
| 5 | No Doc/Fins/Web providers or business tools added | ✅ pass | `tool_discovery.json` adds `doc-tools`/`web-tools` entries but all `enabled: false`; no actual provider module exists under `dayu/tools/` |
| 6 | No `ToolDefinition` / `ToolRuntime` / Engine public contract change | ✅ pass | `git diff -- dayu/contracts/` clean; no contract file in workspace diff |
| 7 | No OLD `ToolRegistry` / `TruncationManager` / `fetch_more` / projection owner imported or instantiated | ✅ pass | `test_legacy_tool_adapter.py:644-659` AST-based import boundary test covers `dayu.engine.tool_registry`, `dayu.engine.truncation_manager`, `dayu.engine.tool_result` |
| 8 | Validation in fix artifact is plausible | ✅ pass | Ran tests + pyright (see below) |

## Findings

未发现实质性问题。

4 项 fix 均正确实现且有测试覆盖。测试从 89 passed 增长到 93 passed，新增的 4 个测试覆盖了所有 accepted findings 的行为证明。

### Fix Implementation Verification

**M1 Batch fetch_more fail-fast** — `definition_adapter.py:337-339`

`adapt_collected_tools` 现在在循环内对 `fetch_more` 声明 raise `ValueError`，与 `adapt_collected_tool` 行为一致。测试 `test_fetch_more_is_not_emitted_as_business_tool` 验证了 batch fail-fast 行为。

**D1 Strict OLD envelope detection** — `definition_adapter.py:209-211`

`project_legacy_return` 现在要求 `ok_value is True` **且** `"value" in raw_value` 才解包为 OLD envelope。纯业务 dict 如 `{"ok": True, "status": "ready"}` 不含 `value` key，走正常成功投影。测试 `test_plain_business_dict_with_ok_field_is_preserved` 验证。

**D2 Path policy coverage fail-closed** — `definition_adapter.py:413-428`

`_project_paths` 在路径策略存在时先检查 `declaration.file_path_params` 是否被 `path_policy.file_path_params` 完全覆盖。不覆盖时返回 `permission_denied`，不进入后续路径校验或工具调用。测试 `test_incomplete_path_policy_coverage_fails_before_calling_migrated_function` 通过 `calls == []` 证明迁移函数未被调用。

**M2 SERIAL_PER_PROVIDER + generic exception tests** — `test_legacy_tool_adapter.py:548-641, 408-438`

`SERIAL_PER_PROVIDER` 测试使用两个不同工具名共享同一 `provider_lock`，通过 `active_count` 检测并发进入。`time.sleep(0.05)` 提供足够的竞态窗口。通用异常测试验证 `RuntimeError` 被正确投影为 `error="execution_error"`。

## Open Questions

无

## Residual Risk

- `dayu.tools._legacy_adapter` 当前没有实际的 Doc/Fins/Web provider 注册函数调用 collector；集成级验证需等 S3/S4/S5 实现具体 provider 后完成。
- `tool_contracts.py` 中 `DupCallSpec` 是 S2 收集但不投影的 metadata；其实际消费（重复调用治理）留待后续 slice。
- S2 config layer changes（`config_loader.py` optional `config` field, `host_assembly.py` pass-through, `tool_discovery.json` new provider entries）是 S2 实现的一部分，增加了配置解析与测试覆盖，但不属于 adapter fix scope。这些变更是一致的、安全的 scaffolding。

## Verdict

**pass**

全部 8 项 expected checks 通过。4 项 accepted findings 已正确修复，测试覆盖充分，未引入新的 correctness 或 architecture 问题。pyright 0 errors，93 tests passed。

## Validation Commands Run

```bash
source .venv/bin/activate && pytest tests/tools/test_legacy_tool_adapter.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/runtime/test_tools_discovery.py -q
# Result: 93 passed

source .venv/bin/activate && pyright
# Result: 0 errors, 0 warnings, 0 informations
```

全部验证通过，无新增或扩散报错。
