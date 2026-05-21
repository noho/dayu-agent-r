# Phase 12.1 Slice 6 Code Review — AgentDS — 2026-05-22

## Review Scope

Phase 12.1 Slice 6 only, since commit `dbb5266`. Review target: README sync, boundary test hardening, aggregate validation. Design source: `docs/host/design.md`. Control doc: `docs/host/implementation-control.md`. Plan section: Slice 6 in `docs/host/phase12-1-runtime-assembly-correction-plan.md`. Implementation artifact: `docs/reviews/phase12-1-slice6-implementation-codex-20260521.md`.

## Changed Files

- `README.md`
- `dayu/README.md`
- `tests/README.md`
- `tests/runtime/test_import_boundary.py`
- `tests/runtime/test_weak_typing_guard.py`
- `docs/host/implementation-control.md` (gate bookkeeping only)

## Verification Results (Independent Rerun)

| Command | Result |
|---|---|
| `pytest tests/runtime -q` | 208 passed in 4.76s |
| `pytest tests/engine/test_config_models.py tests/engine/test_provider_extension_config_adapter.py -q` | 11 passed in 0.34s |
| `pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py -q` | 75 passed in 0.90s |
| `python -m pyright dayu/contracts dayu/runtime dayu/engine dayu/host tests/runtime tests/engine tests/host utils/smoke_host_public_multiturn.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean |

All passes match the implementation artifact claims.

## Findings

### F1 (NON-BLOCKING, INFO) — 根 README 旧 `run.json` 引用已正确删除

根 README 中 "当前 runtime config 不再读取旧 `run.json`" 被删除。该语句是以否定形式描述已移除配置文件的"非事实"，删除后文档更纯粹地描述当前配置事实。与 review criteria "no stale old schema names unless necessary and accurate" 一致。**判定：正确。**

### F2 (NON-BLOCKING, INFO) — `prompt_mt` 残留引用清理完整

根 README 中四处 `prompt_mt` 引用均已清理：
1. `--label` 参数说明中 "对应 scene 为 `prompt_mt`" → 删除
2. `prompt` 命令 `--label` 说明中 "首次创建时 scene 为 `prompt_mt`" → 删除
3. `interactive` 说明中关于 `prompt_mt` 与 `interactive` scene 的底层区分 → 删除
4. workspace 覆写 scene manifest 的约束从 "必须保留 `conversation.enabled=true`" → "必须使用当前 `ScenePrepare` 支持的 scene-only schema"

清理彻底，替换表述准确反映当前 `ScenePrepare` schema。**判定：正确。**

### F3 (NON-BLOCKING, INFO) — 模型配置示例与参数说明对齐当前 schema

根 README 中：
- `execution_profiles.json` 旧路径 `profiles.<id>.ordinary.model_id` → `execution_profiles.<id>.run_baseline.model_id`
- `model.default_name` → `model.default_model_id`
- `temperature_profile` → `runner_option_hint_id`
- 示例 JSON 中移除重复 `model_id` 字段，补充 `runtime_hints.runner_option_hints` 结构
- `runner_options_profiles` 归属说明从 `execution_profiles.json` → `models.json.runtime_hints.runner_option_hints`

全部与当前 `ConfigLoader`、`ScenePrepare` typed view 一致。**判定：正确。**

### F4 (NON-BLOCKING, INFO) — 配置文件表描述更新准确

根 README 配置文件表中：
- `host_runtime.json` 用途从 "lane 与 prompt/scene asset roots" → "Host execution lane 引用与 worker backend"（lane catalog 已移至 `runtime_lanes.json`，prompt/scene roots 已移至 location resolver）
- 新增 `runtime_lanes.json` 行

均反映 Slice 2-5 已落地的 schema 变化。**判定：正确。**

### F5 (NON-BLOCKING, INFO) — `dayu/README.md` 补充正确

- `assembly` 模块列入 runtime 层中立能力列表，描述准确（catalog selection、typed allowlist merge、Agent policy 来源诊断、工具截断 policy defaults 投影）
- 扩展入口新增 "新 provider request extension DSL" 条目，明确指出应放入 `dayu.engine.provider_extensions` 而非 `dayu.runtime`

均反映 Slice 4 已落地的 helper placement 决策。**判定：正确。**

### F6 (NON-BLOCKING, INFO) — `tests/README.md` import boundary 覆盖列表同步

import boundary 行从 `config_loader.py`、`scene_prepare.py` 与 `tools_discovery.py` 扩展为包含 `location.py`、`assembly.py` 与 `tool_truncation.py`。assembly helpers 描述补充 "弱类型守卫显式确认这些 Phase 12 runtime helper 文件被扫描"。均反映当前测试代码事实。**判定：正确。**

### F7 (NON-BLOCKING, INFO) — `test_runtime_import_boundary_scan_covers_tool_truncation_module` 测试正确

新增测试用例验证 `tool_truncation.py` 被 `_iter_python_files()` 遍历覆盖，从而被 `test_runtime_does_not_import_business_layers` 和 `test_runtime_does_not_import_phase0_forbidden_modules` 的通用扫描覆盖。测试结构与其他显式覆盖测试一致，未削弱通用 import 扫描。**判定：正确。**

### F8 (NON-BLOCKING, INFO) — `test_runtime_weak_typing_scan_covers_phase12_helpers` 测试正确

新增 `_PHASE12_RUNTIME_HELPERS` frozenset 包含 `assembly.py`、`config_loader.py`、`location.py`、`scene_prepare.py`、`tool_truncation.py`、`tools_discovery.py`。新测试用例断言该集合是 `_iter_runtime_files()` 扫描文件名的子集。该集合与当前 `dayu/runtime/` 下实际存在的模块一致（验证：`ls dayu/runtime/*.py` 输出包含所有六个文件）。测试不引入弱类型（frozenset 内容是字符串字面量），不削弱 `test_runtime_disallows_weak_typing` 的通用 AST 扫描。**判定：正确。**

### F9 (NON-BLOCKING, INFO) — 无生产行为变更

所有 diff 仅涉及文档（README）、测试（test_import_boundary.py、test_weak_typing_guard.py）和 gate bookkeeping（implementation-control.md）。未修改 `dayu/` 下任何生产 Python 模块。**判定：符合 Slice 6 约束。**

### F10 (NON-BLOCKING, INFO) — implementation-control.md gate bookkeeping 正确

gate 状态从 "Slice 6 implementation" → "Slice 6 code review"，下一 gate 更新为 "Slice 6 code review adjudication / fix decision"。追加的 Slice 6 implementation 事实条目记录了实现 agent、变更摘要和 controller 复跑验证结果。格式与其他 slice 一致。**判定：正确。**

## Stop Condition Assessment

Plan Slice 6 stop condition: "README 与代码事实一致；boundary tests 覆盖 `dayu.runtime` 禁止依赖；aggregate validation artifact 列出所有 residual risks 与 owner。"

- README 与代码事实一致：F1-F6 已逐项确认。**满足。**
- Boundary tests 覆盖 `dayu.runtime` 禁止依赖：F7 确认新增 `tool_truncation.py` 显式覆盖，通用 import scan 未削弱。**满足。**
- Aggregate validation artifact 列出 residual risks 与 owner：implementation artifact 所列 6 项 residual risks 均与 plan Section 7 对齐，owner 明确。本 review artifact 即为 aggregate validation artifact 之一。**满足。**

## Additional Checks

### README 职责边界

- 根 `README.md`：用户手册范围，只写安装、配置、跑通、CLI/smoke/trace/render 入口。未越界写开发细节。**通过。**
- `dayu/README.md`：开发手册总览，只写整体架构、稳定边界、扩展入口。未越界写用户指南。**通过。**
- `tests/README.md`：测试手册，只写测试分层、运行方式、维护约定。未越界写用户手册或 Engine 设计。**通过。**

### 编码硬约束

- 测试代码无 `Any`、`object`、无类型参数、无类型返回值（测试函数返回 `None`，均有注解）。
- 无魔法数字/字符串（`_PHASE12_RUNTIME_HELPERS` 使用模块名 frozenset，是合理的显式集合）。
- 无嵌套函数/类逃逸。
- pyright 0 errors 确认无类型违规。

## Verdict

**PASS** — 无 blocking findings。

Slice 6 变更范围严格限定于文档同步、边界测试补强和 gate bookkeeping，未触及生产代码行为；所有验证命令独立复跑通过；README 与当前代码事实一致，残留旧 schema 术语已清理；boundary tests 和 weak typing guard 覆盖了 Phase 12 新增 runtime helper 模块且未削弱通用扫描。

## Residual Risk Confirmation

Implementation artifact 所列 6 项 residual risks 及其 owners 均与 plan Section 7 对齐，Slice 6 未引入新的未归属风险：

1. Service/composition helper 正式抽取 — owner: Service assembly work unit
2. 默认 financial tool provider / real provider smoke — owner: Service / Fins / tool provider hardening
3. Provider model catalog 维护 — owner: execution profile / model catalog maintenance
4. 真实 Service / UI / CLI workflow 接入 — owner: Service / UI / workflow work unit
5. Tool truncation declaration 覆盖度 — owner: tool provider hardening
6. Financial scene 内容与 Fins storage 业务链路 — owner: Service / Fins / 配置 work unit
