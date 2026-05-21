# Phase 12.1 Slice 6 Implementation Artifact - AgentCodex - 2026-05-21

## 范围与动机判断

本 slice 的动机成立：Phase 12.1 前序 slice 已落地 runtime config / scene / tools discovery / assembly / provider extension helper，收尾阶段需要用 README 与边界守卫证明当前事实没有旧 schema 残留、`dayu.runtime` import boundary 没被新增 helper 绕开、弱类型守卫没有漏扫新增公共 helper。

本次未启动 gateflow，未提交、未 push、未开 PR。

## 起始 worktree 审计

开始前执行 `git status --short`，输出为空，worktree 干净。没有接管 pre-existing dirty hunk，也没有丢弃半成品改动。

## 实现变更

- `README.md`
  - 同步当前 runtime config 事实：`host_runtime.json` 不再承载 prompt / scene asset root，新增 `runtime_lanes.json` 作为 lane coordinator 与 lane catalog 配置。
  - 清理用户手册中的旧 scene 名与旧 scene 字段表述，改为当前 `ScenePrepare` scene-only schema。
  - 更新模型配置示例：catalog id 来自 `models` map key，record 内不重复 id；`runtime_hints.runner_option_hints` 承载 `RunnerCallOptions` 片段；execution profile 只保存 `model_id` 与 `runner_option_hint_id`。
  - 写明 `provider_request_extension` 由 Engine provider extension helper 映射为 typed contract。
- `dayu/README.md`
  - 补充 `dayu.runtime.assembly` 的层中立 helper 边界。
  - 补充 provider request extension DSL 的扩展入口应位于 `dayu.engine.provider_extensions`，不进入 `dayu.runtime`。
- `tests/README.md`
  - 同步 runtime import boundary 显式覆盖模块列表，加入 `location.py`、`assembly.py` 与 `tool_truncation.py`。
  - 记录弱类型守卫显式确认 Phase 12 runtime helper 文件被扫描。
- `tests/runtime/test_import_boundary.py`
  - 增加 `tool_truncation.py` import boundary 显式覆盖测试。
- `tests/runtime/test_weak_typing_guard.py`
  - 增加 Phase 12 runtime helper 文件集合断言，证明弱类型守卫覆盖 `assembly.py`、`config_loader.py`、`location.py`、`scene_prepare.py`、`tool_truncation.py`、`tools_discovery.py`。

## README 审计结论

- `dayu/config/README.md` 已覆盖新 config schema、workspace overlay、prompts 目录职责、policy typed shapes、旧字段 fail-fast 与 removed old names 的必要说明；本 slice 未修改。
- `dayu/host/README.md` 已覆盖 ratio-first `ContextBudgetPolicy`、memory / ToolRuntime truncation 边界、`OpenHostOptions` construction boundary 与 per-run typed request boundary；本 slice 未修改。
- `dayu/engine/README.md` 已覆盖 `ProviderRequestExtension` 封闭联合与 `dayu.engine.provider_extensions.provider_request_extension_from_json` helper 边界；本 slice 未修改。

## 验证结果

- `source .venv/bin/activate && pytest tests/runtime -q`
  - 结果：208 passed in 4.78s
- `source .venv/bin/activate && pytest tests/engine/test_config_models.py tests/engine/test_provider_extension_config_adapter.py -q`
  - 结果：11 passed in 0.32s
- `source .venv/bin/activate && pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py -q`
  - 结果：75 passed in 0.82s
- `source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/engine dayu/host tests/runtime tests/engine tests/host utils/smoke_host_public_multiturn.py`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：通过，无输出

## Residual Risks 与 Owner

- Service/composition helper 正式抽取：owner 为后续 Service assembly work unit。当前 Phase 12.1 仍以 smoke-local adapter 和 runtime-neutral helper 证明装配边界，未创建真实 `dayu.service` API。
- 默认 financial tool provider / real provider smoke：owner 为后续 Service / Fins / tool provider hardening work unit。当前默认 `tool_discovery.json` 仍可能没有启用真实财报工具 provider；Host public multiturn smoke 会在未发现匹配工具时调用 Host 前 fail fast。
- Provider model catalog 维护：owner 为后续 execution profile / model catalog maintenance work unit。Phase 12.1 迁移当前 git 历史中的 catalog，并未承诺外部 provider 最新模型名、上下文窗口或 endpoint 实时正确。
- 真实 Service / UI / CLI workflow 接入：owner 为后续 Service / UI / workflow work unit。Phase 12.1 只交付 runtime assembly reference path 与 smoke diagnostics，未把真实多 Run 财报 workflow 接入 Service / UI。
- Tool truncation declaration 覆盖度：owner 为后续 tool provider hardening work unit。当前提供 declaration/effective 边界与 policy default 补齐，不强制所有既有业务工具声明截断策略。
- Financial scene 内容与 Fins storage 业务链路：owner 为后续 Service / Fins / 配置 work unit。当前 scene asset schema 已迁移，但财报场景内容质量、工具选择与真实文档仓储路径仍需后续业务验证。

## Changed Files

- `README.md`
- `dayu/README.md`
- `tests/README.md`
- `tests/runtime/test_import_boundary.py`
- `tests/runtime/test_weak_typing_guard.py`
- `docs/reviews/phase12-1-slice6-implementation-codex-20260521.md`
