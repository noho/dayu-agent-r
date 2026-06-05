# Code Review — Re-review

## Scope

- Mode: current changes (workspace uncommitted diff for WU-TOOLS-01 Slice S2 fix)
- Work unit: WU-TOOLS-01
- Gate: re-review
- Slice: S2 Tool Adapter And Typed Provider Config
- Branch: phaseflow/wu-tools-01
- Base: main
- Output file: docs/reviews/wu-tools-01-slice2-rereview-ds.md
- Reviewer: AgentDS
- Re-review target: Controller accepted S2 fixes only
- Included scope:
  - `dayu/tools/_legacy_adapter/definition_adapter.py` (fix changes)
  - `tests/tools/test_legacy_tool_adapter.py` (fix-added tests)
- Excluded scope: S1/S3/S4/S5/S6 implementation files, unmodified adapter modules, config loader changes (not part of fix), README changes (not part of fix), `tool_discovery.json` disabled provider stubs (already reviewed and accepted in original S2 review)
- Referenced artifacts:
  - Controller adjudication: `docs/reviews/wu-tools-01-slice2-code-review-controller-adjudication.md`
  - Fix artifact: `docs/reviews/wu-tools-01-slice2-fix-codex.md`
  - Original review: `docs/reviews/wu-tools-01-slice2-code-review-ds.md`
  - Implementation artifact: `docs/reviews/wu-tools-01-slice2-implementation-codex.md`

## Expected Checks

### C1 — batch `fetch_more` fail-fast

**Status: fixed.**

`adapt_collected_tools(...)` (`definition_adapter.py:338-339`) 现在对 reserved `fetch_more` 名抛出 `ValueError("legacy adapter must not expose fetch_more as a business tool")`，与 `adapt_collected_tool(...)` (`definition_adapter.py:311-312`) 行为一致。

测试 `test_fetch_more_is_not_emitted_as_business_tool` (`test_legacy_tool_adapter.py:441-456`) 传入含 `fetch_more` 和 `normal_tool` 的声明序列，断言 `pytest.raises(ValueError, match="fetch_more")`。batch adapter 不再静默跳过。

### C2 — strict OLD envelope detection

**Status: fixed.**

`project_legacy_return(...)` (`definition_adapter.py:211`) 现在要求 `ok_value is True` **且** `"value" in raw_value` 同时成立才进入 OLD 成功 envelope 解包分支。仅含 `ok` 业务字段的 dict（如 `{"ok": True, "status": "ready"}`）会 fall through 到 line 227 的普通成功投影。

测试 `test_plain_business_dict_with_ok_field_is_preserved` (`test_legacy_tool_adapter.py:368-385`) 传入 `{"ok": True, "status": "ready"}`，断言 `outcome.result.value == {"ok": True, "status": "ready"}` 原样保留。

### C3 — path policy coverage fail-closed

**Status: fixed.**

`_project_paths(...)` (`definition_adapter.py:414-428`) 在 `path_policy is not None` 时计算 `missing_path_params = set(declaration.file_path_params) - set(path_policy.file_path_params)`；若非空则返回 `ToolFailedOutcome(error="permission_denied")`，不进入后续路径校验，不调用迁移函数。

测试 `test_incomplete_path_policy_coverage_fails_before_calling_migrated_function` (`test_legacy_tool_adapter.py:260-329`) 声明 `file_path_params=("file_path", "directory")` 但 policy 只覆盖 `("file_path",)`，断言 `outcome.result.error == "permission_denied"` 且 `calls == []`。

### C4 — SERIAL_PER_PROVIDER shared lock test

**Status: fixed.**

测试 `test_serial_per_provider_shares_lock_across_tool_names` (`test_legacy_tool_adapter.py:548-641`) 创建两个不同工具名 (`provider_tool_a`, `provider_tool_b`) 均使用 `SERIAL_PER_PROVIDER`，并发 `asyncio.gather` 执行，通过共享 `active_count` / `concurrent_entries` 计数器证明不同工具名共享同一把 provider 级锁：`concurrent_entries == 0`。

### C5 — generic exception projection test

**Status: fixed.**

测试 `test_generic_exception_projects_to_execution_error_failure` (`test_legacy_tool_adapter.py:408-438`) 构造抛出 `RuntimeError("database temporarily unavailable")` 的工具，经 `adapt_collected_tool` → `_AdaptedLegacyCallable.__call__` → `project_legacy_exception`（`definition_adapter.py:287-294` catch-all 分支）映射为 `ToolFailedOutcome(error="execution_error")`。

### C6 — no Doc/Fins/Web providers or business tools

**Status: unchanged from original S2, still passes.**

`dayu/tools/` 仍仅含 `__init__.py` 和 `_legacy_adapter/`。无 `doc_provider.py`、`web.py` 或任何 fins 业务工具模块。`tool_discovery.json` 中 `doc-tools` / `web-tools` 均为 `enabled: false` 配置桩，已在原始 S2 review 中确认无实际 provider 代码。

### C7 — no ToolDefinition / ToolRuntime / Engine public contract change

**Status: unchanged from original S2, still passes.**

fix 只修改 `definition_adapter.py` 和测试文件，未触及 `dayu/contracts/`、`dayu/host/tool_runtime.py` 或任何 Engine 模块。

### C8 — no OLD registry/truncation/projection import

**Status: unchanged from original S2, still passes.**

`test_tools_adapter_import_boundary_excludes_old_runtime_owners` (`test_legacy_tool_adapter.py:644-659`) AST 扫描所有 adapter `.py` 文件，零违规。fix 未新增任何 import。

### C9 — validation plausibility

**Status: re-verified.**

命令重新运行：

```bash
source .venv/bin/activate && pytest tests/tools/test_legacy_tool_adapter.py tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/runtime/test_tools_discovery.py -q
# 93 passed in 0.62s

source .venv/bin/activate && pyright
# 0 errors, 0 warnings, 0 informations

git diff --check
# clean
```

与 fix artifact 声明的 93 passed / 0 pyright errors / diff check clean 一致。

## Findings

未发现实质性问题。

四项 Controller accepted findings 均已正确修复，fix 未引入新的 correctness 或 architecture 问题。

代码走读覆盖路径：

- `project_legacy_return` line 209-232：OLD envelope 二因子检测正确；`ok is True` + `"value" in raw_value` 组合不会误判纯业务 dict；`ok is False` 失败分支不受影响。
- `_project_paths` line 413-474：coverage check（line 414-428）在 path validation 之前执行，fail-closed；coverage 通过后使用 `declaration.file_path_params` 迭代，由 `path_policy.allowed_roots` / `path_policy.must_exist` 校验每个路径参数，逻辑自洽。
- `adapt_collected_tools` line 321-357：`fetch_more` fail-fast（line 338-339）在 loop 首位；`SERIAL_PER_PROVIDER` 共享 `provider_lock`（line 335 创建，line 347 复用）；锁选择逻辑无重叠分支。
- `project_legacy_exception` line 235-294：异常类型分发无重叠；catch-all `execution_error` 分支（line 287-294）正确覆盖所有未分类异常。

## Open Questions

无。

## Residual Risk

- Provider-specific typed config parsing 仍由 S3/S4/S5 覆盖。
- Provider-specific Doc path whitelist 仍由 S3 覆盖。
- 具体迁移截断工具仍由 S3/S4/S5 覆盖。
- 组合 ToolRuntime accept 路径仍由 S6 覆盖。
- `tests/tools/` 目录缺少 `__init__.py`，不影响 pytest 发现和运行，但若未来需要作为 package 导入则需补上。非阻塞项。

## Verdict

**pass**

四项 Controller accepted findings 全部正确修复，无新 findings。验证命令重新运行：93 passed, pyright 0 errors, diff check clean。
