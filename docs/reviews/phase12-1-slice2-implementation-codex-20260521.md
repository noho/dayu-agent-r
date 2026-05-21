# Phase 12.1 Slice 2 Implementation Artifact

## Gate / Scope

- Work unit: Phase 12.1 runtime assembly schema / public contract correction follow-up。
- Current gate: Slice 2 implementation。
- Slice: Config Schema, Location Resolver, Default Assets, Full Model Catalog。
- Approved plan: `docs/host/phase12-1-runtime-assembly-correction-plan.md`。
- Baseline dependency: Slice 1 accepted commit `9974a2d`，policy contract 和 `ToolTruncateSpec` target 已稳定。
- Stop condition: 完成本 Slice 实现、测试、README 同步和本 artifact；不 commit、不 push、不开 PR、不进入其它 gate。

## Dirty Worktree 分类与接管范围

Preflight direct evidence:

- `git branch --show-current`: `docs/phase12-design-discussion`
- `git status --short` 初始输出只包含：
  - `M README.md`
  - `M utils/smoke_host_public_multiturn.py`
- `git diff --name-status` 初始输出同上。
- `git diff --stat` 初始输出显示 `README.md` 有 9 行左右变更，`utils/smoke_host_public_multiturn.py` 有约 749 行半成品变更。

分类：

- Out-of-scope pre-existing dirty: `README.md`、`utils/smoke_host_public_multiturn.py`。
- 本 Slice 接管并修改：`dayu/runtime/config_loader.py`、`dayu/runtime/location.py`、`dayu/runtime/__init__.py`、`dayu/config/models.json`、`dayu/config/execution_profiles.json`、`dayu/config/host_runtime.json`、`dayu/config/runtime_lanes.json`、`dayu/config/tool_discovery.json`、`tests/runtime/test_config_loader.py`、`tests/runtime/test_runtime_location.py`、`tests/runtime/test_import_boundary.py`、`tests/engine/test_config_models.py`、`dayu/config/README.md`、`dayu/README.md`、`tests/README.md`、本 artifact。
- 未接管：`README.md`、`utils/smoke_host_public_multiturn.py`。本 Slice 没有修改或 revert 它们；根 README 虽有项目级使用说明触发风险，但当前文件已有前序 dirty，且本 Slice 的稳定配置说明已落在职责更精确的 `dayu/config/README.md` 与 `dayu/README.md`。

## 旧模型 Source Preflight

直接证据：

- 已执行 `git show 9952fd4:dayu/config/llm_models.json`。
- 命令成功返回 JSON，包含旧模型源记录和顶层说明字段。
- 因直接源可访问，未使用 fallback 讨论列表。

迁移方式：

- 以 `9952fd4:dayu/config/llm_models.json` 为唯一旧模型源。
- 跳过旧源中的说明字段 `_comment`、`_usage`、`_capabilities_note`。
- 将每个旧模型 record 迁移到 `dayu/config/models.json.models[model_id]`，新 record 内不重复写 `model_id`。
- `runner_type` -> `runner_kind`。
- `endpoint_url` -> `endpoint`。
- `timeout` -> `default_timeout_seconds`。
- `stream_idle_timeout` -> `sse_idle_timeout_seconds`。
- `stream_idle_heartbeat_sec` -> `sse_heartbeat_seconds`。
- `max_context_tokens` -> `context_window_tokens`。
- `provider_request` -> `provider_request_extension`，按 JSON DSL 原样保留。
- `runtime_hints.temperature_profiles` -> `runtime_hints.runner_option_hints`，保留原 temperature，并补齐完整 RunnerCallOptions 字段 `max_tokens`、`top_p`、`stream`。
- `api_key_ref` 从旧 headers 的 `Authorization: Bearer {{KEY}}` 提取；无 Authorization 的 `ollama` 为 `null`。

## Schema 迁移 Checklist

- [x] `RuntimeConfig` 包含 `models`、`execution_profiles`、`host_runtime`、`runtime_lanes`、`tool_discovery`。
- [x] 所有 catalog record id 只来自 map key；record 内出现 `runtime_id`、`host_runtime_id`、`model_id`、`profile_id`、`execution_profile_id`、`provider_id` 会 fail fast。
- [x] `execution_profiles.json` 顶层改为 `default_execution_profile_id` 与 `execution_profiles`，默认 id 为 `standard`。
- [x] execution profile record 改为 `run_baseline`、`compactor_baseline`、`context_budget_policy`、`memory_projection_policy`、`tool_truncation_policy`、`agent_policy_profile_id`。
- [x] 顶层保留 `agent_policy_profiles`，删除并 fail fast 旧 `runner_options_profiles`、`runner_hints`、`agent_hints`。
- [x] `fallback_mode` 只允许 `force_answer` / `raise_error`，默认配置中的 `fallback_prompt` 使用指定中文文本。
- [x] `models.json` 使用 `runtime_hints.runner_option_hints`，每个 hint 是完整 RunnerCallOptions 片段。
- [x] execution profile baseline 只保存 `model_id` 和 semantic `runner_option_hint_id`。
- [x] `provider_request_extension` 作为 JSON DSL 原样进入 runtime config typed view；`dayu.runtime` 未 import Engine typed provider extension。
- [x] `host_runtime.json` 使用 `default_host_runtime_id`、`host_execution_lane_name` 与 `worker_backend`。
- [x] 删除 host runtime 内联 lane catalog、`worker_factory_kind`、`prompt_asset_root`、`scene_manifest_root`。
- [x] 新增 `runtime_lanes.json`，拥有 runtime lane coordinator DB 路径和 lane catalog。
- [x] `host_runtime.host_execution_lane_name` 校验必须引用已存在 lane。
- [x] 新增 `dayu.runtime.location`，输出 `config_overlay_dir`、`prompt_asset_root`、`scene_manifest_root`。
- [x] `workspace/config` 不存在时 `config_overlay_dir=None`。
- [x] `tests/runtime/test_import_boundary.py` 覆盖 `location.py`，runtime import boundary clean。
- [x] `extends` validation 覆盖 missing target、self-reference、circular A/B、valid chained A->B->C、invalid type、multi-inheritance。

## 旧模型迁移清单

已迁移模型 id：

- `deepseek-v4-flash`
- `deepseek-v4-flash-thinking`
- `deepseek-v4-pro`
- `deepseek-v4-pro-thinking`
- `gpt-5.4`
- `gpt-5.4-thinking`
- `claude-sonnet-4-6`
- `claude-sonnet-4-6-thinking`
- `gemini-2.5-flash`
- `gemini-2.5-flash-thinking`
- `gemini-2.5-pro`
- `gemini-2.5-pro-thinking`
- `gemini-2.5-flash-lite`
- `gemini-2.5-flash-lite-thinking`
- `gemini-3.1-pro-preview`
- `gemini-3.1-pro-preview-thinking`
- `gemini-3.1-flash-lite-preview`
- `gemini-3.1-flash-lite-preview-thinking`
- `mimo-v2.5-pro`
- `mimo-v2.5-pro-thinking`
- `mimo-v2.5-pro-plan`
- `mimo-v2.5-pro-thinking-plan`
- `mimo-v2.5-pro-plan-sg`
- `mimo-v2.5-pro-thinking-plan-sg`
- `qwen-plus`
- `qwen-plus-thinking`
- `ollama`

## Changed Files

- `dayu/runtime/config_loader.py`: 重写新 schema typed view、五类配置加载、record id fail-fast、extends hardening、runtime lane 和 host lane 引用校验。
- `dayu/runtime/location.py`: 新增层中立 location resolver。
- `dayu/runtime/__init__.py`: 更新模块概览，不新增包根 re-export。
- `dayu/config/models.json`: 完整迁移旧模型目录到新 schema。
- `dayu/config/execution_profiles.json`: 新 execution profile / policy schema。
- `dayu/config/host_runtime.json`: 新 host runtime schema。
- `dayu/config/runtime_lanes.json`: 新 runtime lane coordinator 与 lane catalog。
- `dayu/config/tool_discovery.json`: 删除 record 内重复 `provider_id`。
- `tests/runtime/test_config_loader.py`: 迁移并扩展 ConfigLoader 测试。
- `tests/runtime/test_runtime_location.py`: 新增 location resolver 测试。
- `tests/runtime/test_import_boundary.py`: 覆盖 `location.py`。
- `tests/engine/test_config_models.py`: 覆盖全量模型迁移和 provider DSL 原样保留。
- `dayu/config/README.md`: 同步新默认配置、overlay 关系、prompts 职责、旧配置文件删除事实。
- `dayu/README.md`: 同步 runtime capability 总览中的 `runtime_lanes` 与 `location`。
- `tests/README.md`: 同步 runtime config / location 测试事实。

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_runtime_location.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - Result: `35 passed in 0.96s`
- `source .venv/bin/activate && pytest tests/engine/test_config_models.py -q`
  - Result: `4 passed in 0.11s`
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime tests/engine/test_config_models.py`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: clean

## Residual Risk / Deferred Items

- `README.md` 和 `utils/smoke_host_public_multiturn.py` 仍是前序 out-of-scope dirty，本 Slice 未接管；后续 Slice 5 或 controller 应继续按原 ownership 处理。
- `ScenePrepare` schema 仍属 Slice 3，本 Slice 只新增 location resolver，未修改 scene manifest parser。
- `provider_request_extension` 当前在 runtime typed view 中按 JSON DSL 原样保留；JSON DSL 到 Engine typed provider extension 的 fail-closed adapter 属于后续 Slice 4。
- `runtime_hints.runner_option_hints` 迁移时为旧 temperature profiles 补齐了 `max_tokens`、`top_p`、`stream` 默认值；这些是完成新 schema 所需的配置值，后续 Service/composition helper 可继续按模型与场景语义细化。

## Completion Status

Slice 2 implementation 完成，验证通过，停在 implementation report。未 commit、未 push、未开 PR、未进入其它 gate。
