# Phase 12.1 Slice 6 Code Review - AgentMiMo - 2026-05-21

## Verdict

**PASS** — blocking count = 0。

## Review Scope

- `README.md`
- `dayu/README.md`
- `tests/README.md`
- `tests/runtime/test_import_boundary.py`
- `tests/runtime/test_weak_typing_guard.py`
- `docs/host/implementation-control.md`（gate bookkeeping only）
- `docs/reviews/phase12-1-slice6-implementation-codex-20260521.md`

基准：commit `dbb5266`（Slice 5 acceptance）。

## Review Criteria Checklist

### 1. README 只描述当前代码事实

**结论：PASS。**

逐项验证：

- `host_runtime.json` 描述更新为"Host opener 部署默认值、store/artifact roots、SQLite、Host execution lane 引用与 worker backend"。实际文件包含 `store_root`、`artifact_root`、`sqlite`、`host_execution_lane_name`、`worker_backend` 等字段，无 `prompt_asset_root` / `scene_manifest_root`。一致。
- 新增 `runtime_lanes.json` 描述为"runtime lane coordinator 与 lane catalog"。实际文件包含顶层 `coordinator`（含 `db_path` 等）和 `lanes`（含 `llm_api` lane 条目）。一致。
- execution profile 字段从旧 `ordinary` 更新为 `run_baseline`，从旧 `runner_options_profiles` 更新为只存 `model_id` + `runner_option_hint_id`。实际 `execution_profiles.json` 与 `config_loader.py` 的 `ExecutionProfileConfig.run_baseline` / `ExecutionBaselineConfig` 均对齐。一致。
- 模型配置示例使用 `runtime_hints.runner_option_hints`，字段为 `temperature`、`max_tokens`、`top_p`、`stream`。实际 `RunnerOptionHintConfig` dataclass 恰好是这四个字段。一致。
- catalog id 来自 `models` map key，record 内不重复 `model_id`。实际 `models.json` 验证通过。一致。
- `--label` 文档移除 `prompt_mt` scene 引用。`prompt_mt` 在 `dayu/` 源码中已不存在（仅 `dayu/config/README.md` 作为"旧 schema 不属于当前"的说明出现）。一致。
- scene manifest 字段描述使用 `model.default_model_id` 与 `model.runner_option_hint_id`。实际 `scene_prepare.py` 的 `_parse_scene_model_hints` 恰好解析这两个字段。一致。
- `provider_request_extension` 描述补充"由 Engine provider extension helper 映射为 typed contract"。与 `dayu/README.md` 新增扩展入口说明一致。

无未来设计、无过程叙述、无旧 schema 名残留。

### 2. README 职责边界

**结论：PASS。**

- 根 README：只更新用户可见配置说明（`host_runtime.json`、`runtime_lanes.json`、模型配置示例、`--label` 说明、配置文件职责表）。未越界写架构或开发指南。
- `dayu/README.md`：只新增 `assembly` 模块边界描述与 provider request extension DSL 扩展入口。未越界写用户手册。
- `tests/README.md`：只更新 import boundary 显式覆盖列表与弱类型守卫说明。未越界。

### 3. Boundary tests 覆盖新增 runtime 模块

**结论：PASS。**

- `test_import_boundary.py` 新增 `test_runtime_import_boundary_scan_covers_tool_truncation_module()`，断言 `_iter_python_files()` 输出包含 `tool_truncation.py`。`_iter_python_files()` 递归扫描 `dayu/runtime/` 全部 `.py` 文件，`tool_truncation.py` 确实存在于该目录。测试有效。
- 既有 `test_runtime_import_boundary_scan_covers_assembly_module()` 覆盖 `assembly.py`。
- 既有 `test_runtime_does_not_import_business_layers()` 是通用扫描，不因新增模块而弱化。

### 4. Weak typing guard coverage assertion

**结论：PASS。**

- `_PHASE12_RUNTIME_HELPERS` frozenset 包含 6 个文件：`assembly.py`、`config_loader.py`、`location.py`、`scene_prepare.py`、`tool_truncation.py`、`tools_discovery.py`。
- 这 6 个文件恰好是 Phase 12 新增或重写的 runtime public/helper 模块。其他 runtime 文件（`lane.py`、`filelock.py`、`cancellation.py`、`log.py`、`log_levels.py`、`_digest.py`、`__init__.py`）是 Phase 12 前的基础设施或包初始化，不在 Phase 12 helper 范围。
- `test_runtime_weak_typing_scan_covers_phase12_helpers()` 断言 `_iter_runtime_files()` 输出覆盖全部 6 个文件。`_iter_runtime_files()` 与 `_iter_python_files()` 使用相同扫描逻辑（`root.rglob("*.py")` 排除 `__pycache__`）。测试有效。
- 既有 `test_runtime_disallows_weak_typing()` 是通用弱类型扫描，覆盖全部 runtime 文件。

### 5. 无生产行为变更

**结论：PASS。**

本 slice 变更仅涉及：
- README 文档更新（3 个文件）
- 测试新增（2 个文件，各增加 1 个测试函数）
- implementation-control.md gate bookkeeping
- implementation artifact 文档

无 `dayu/` 生产代码变更。

### 6. Validation evidence 充分性

**结论：PASS。**

Implementation artifact 报告的验证命令与 Slice 6 plan 定义的 validation 完全对齐：

| 验证命令 | 报告结果 |
|---------|---------|
| `pytest tests/runtime -q` | 208 passed |
| `pytest tests/engine/test_config_models.py tests/engine/test_provider_extension_config_adapter.py -q` | 11 passed |
| `pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py -q` | 75 passed |
| `python -m pyright dayu/contracts dayu/runtime dayu/engine dayu/host tests/runtime tests/engine tests/host utils/smoke_host_public_multiturn.py` | 0 errors |
| `git diff --check` | clean |

Review agent 独立复跑 boundary + weak typing guard tests：13 passed。pyright dayu/runtime tests/runtime：0 errors。

### 7. Residual risks 与 owner

**结论：PASS。**

Implementation artifact 列出 6 项 residual risk，每项均有明确 owner：

1. Service/composition helper 正式抽取 → 后续 Service assembly work unit
2. 默认 financial tool provider / real provider smoke → 后续 Service / Fins / tool provider hardening
3. Provider model catalog 维护 → 后续 execution profile / model catalog maintenance
4. 真实 Service / UI / CLI workflow 接入 → 后续 Service / UI / workflow work unit
5. Tool truncation declaration 覆盖度 → 后续 tool provider hardening
6. Financial scene 内容与 Fins storage 业务链路 → 后续 Service / Fins / 配置 work unit

与 plan section 7 的 residual risks 一致，无遗漏。

## Findings

无 blocking finding。

### N1: `dayu/README.md` 未更新 README trigger

`dayu/README.md` 修改了 `dayu.runtime` 模块列表（新增 `assembly` 描述），但 Slice 6 plan 的 README trigger 规则中未列出 `dayu/README.md` 对应的触发条件。实际上 `dayu/README.md` 的触发规则是"涉及分层关系、装配方式、UI / Service / Host / Agent 边界变化"，本次新增 `assembly` 模块描述属于"装配方式"范畴，触发合理。

**性质：informational，不阻塞。**

### N2: 根 README 配置文件职责表中 `runtime_lanes.json` 行缺少建议修改方式

根 README 在"建议修改方式"小节新增了"想调 runtime lane coordinator 或 lane capacity：改 `runtime_lanes.json`"，但配置文件职责表中 `runtime_lanes.json` 的描述列只写了"runtime lane coordinator 与 lane catalog"，比其他条目略短。不影响正确性。

**性质：informational，不阻塞。**

## Changed Files Summary

| 文件 | 变更性质 |
|------|---------|
| `README.md` | 文档：同步 config schema 事实、清理旧 scene 名、更新模型配置示例 |
| `dayu/README.md` | 文档：新增 assembly 模块边界与 provider extension DSL 扩展入口 |
| `tests/README.md` | 文档：同步 import boundary 覆盖列表与弱类型守卫说明 |
| `tests/runtime/test_import_boundary.py` | 测试：新增 `tool_truncation.py` 覆盖断言 |
| `tests/runtime/test_weak_typing_guard.py` | 测试：新增 Phase 12 helper 文件覆盖断言 |
| `docs/host/implementation-control.md` | Gate bookkeeping：推进到 Slice 6 code review |
