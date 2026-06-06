# WU-TOOLS-01 Slice S6 Re-Review (A1 Fix)

Gate: re-review
Work unit: WU-TOOLS-01
Slice: S6
Reviewer: AgentMiMo
Verdict: **PASS**

## 验证 1：import boundary 测试是否仍能防止 business provider 暴露 `fetch_more`，没有过宽 allowlist

**PASS**

`test_fetch_more_token_stays_inside_toolruntime_owner_modules`（`test_import_boundary.py:236-263`）扫描 `dayu/` 全包 `.py` 文件（L244: `dayu_root = _host_root().parent`，L247: `_iter_python_files(dayu_root)`），非仅 `dayu/host/`。

两层 allowlist：

| Allowlist | 文件 | 用途 |
|---|---|---|
| `FETCH_MORE_ALLOWED_RELATIVE_FILES` (L41-43) | `host/tool_runtime.py`, `host/tooling.py`, `runtime/tools_discovery.py` | ToolRuntime / tooling owner |
| `FETCH_MORE_DEFENSIVE_ALLOWED_RELATIVE_FILES` (L44-50) | `tools/_legacy_adapter/__init__.py`, `definition_adapter.py`, `registry_collector.py` | reserved-name 防御性引用 |

Business providers（`doc_provider.py`、`web/`、`fins/tools/`）不在任何 allowlist 中。若这些文件出现 `fetch_more` 字符串，测试将失败。

`_legacy_adapter` 三文件的 `fetch_more` 引用均为防御性：
- `definition_adapter.py:42` — `_RESERVED_FETCH_MORE_TOOL_NAME = "fetch_more"`（常量用于拒绝暴露）
- `definition_adapter.py:435,462` — `raise ValueError("legacy adapter must not expose fetch_more as a business tool")`
- `__init__.py:5`, `registry_collector.py:6` — docstring 说明

S6 acceptance test `test_migrated_providers_and_adapter_do_not_import_old_runtime`（`test_combined_tools_acceptance.py:235-253`）也独立扫描 `_legacy_adapter/`（`_migrated_tool_source_paths()` L932），检测 OLD import 和 OLD projection token。双层防护互补。

## 验证 2：OLD fetch-more projection token 扫描是否有效且不会误伤常量自身

**PASS**

扫描 token（L52-56）：`fetch_more_args`、`project_for_llm`、`continuation_hint`。

扫描逻辑（L250-252）在 allowlist 跳过**之前**执行，对 `dayu/` 全包所有 `.py` 文件做字符串 `in` 匹配。

不会误伤常量自身：
- `_RESERVED_FETCH_MORE_TOOL_NAME = "fetch_more"`（`definition_adapter.py:42`）不包含 `fetch_more_args`、`project_for_llm`、`continuation_hint` 中任何一个。
- `FETCH_MORE_OWNERSHIP_TOKEN = "fetch_more"`（`test_import_boundary.py:51`）是测试自身常量，不在 `dayu/` 包内。

实际验证：`grep -rn 'fetch_more_args\|project_for_llm\|continuation_hint' dayu/ --include='*.py'` 返回 0 匹配。唯一 `fetch_more_args` 出现在 `dayu/config/prompts/base/tools.md`（非 `.py`，不在扫描范围）。

## 验证 3：`compaction_operation.py` allowlist 是否符合 Host -> Engine contract 边界

**PASS**

`compaction_operation.py` 的 Engine import（L23-24）：
```python
from dayu.engine.contracts.agent_run import AgentRunRequest
from dayu.engine.contracts.engine_events import RUNNER_INPUT_SERIALIZER_SCHEMA_VERSION
```

两者均为 Engine public contracts。`HOST_ENGINE_CONTRACT_ALLOWED_MODULES`（L58-67）已包含同类边界模块：`api.py`、`dispatch.py`、`llm_compaction.py`、`run_input.py`、`local_proxy.py`、`engine_ingest.py`、`_execution_config_projection.py`。`compaction_operation.py` 加入后保持一致。

全量交叉验证：`dayu/host/` 下 import `dayu.engine` 的 8 个文件均在 allowlist 中（grep 确认：`compaction_operation.py`、`llm_compaction.py`、`_execution_config_projection.py`、`run_input.py`、`api.py`、`dispatch.py`、`engine_ingest.py`、`local_proxy.py`）。无遗漏，无越界。

## 验证 4：`tests/README.md` 更新是否准确

**PASS**

两处变更（`git diff HEAD -- tests/README.md`）：

1. `tests/tools/` 段新增 combined tools acceptance 描述行（+1 行），内容与 `test_combined_tools_acceptance.py` 8 个测试覆盖范围一致。
2. `tests/host/` import boundary 描述更新：新增 "compaction operation" 边界提及；`fetch_more` 描述从 "只留在 ToolRuntime / tooling owner" 扩展为 "或 `_legacy_adapter` reserved-name 防御性引用中且不迁移 OLD fetch-more projection"。

两处变更均在 `tests/README.md` 职责范围内（`tests/` 修改 → 更新 `tests/README.md`），准确反映当前测试契约，不越界。

## 验证 5：本地验证可信

**PASS**

- `pytest tests/host/test_import_boundary.py tests/tools/test_combined_tools_acceptance.py` — 21 passed（独立运行确认）
- `pyright` — 0 errors, 0 warnings, 0 informations
- `git diff --check` — clean

## Blocking Finding

无。

## 结论

**PASS**

A1 fix 充分，未引入新 blocking regression。
