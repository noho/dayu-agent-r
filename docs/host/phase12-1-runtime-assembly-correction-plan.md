# Phase 12.1 Runtime Assembly Schema / Public Contract Correction Plan

## 1. Objective and Success Signals

### 目标

Phase 12.1 修正 Phase 12 runtime assembly 在真实 Service-like smoke 装配中暴露出的 schema / public contract mismatch，使 `ConfigLoader`、`ScenePrepare`、`ToolsDiscovery` 与装配 helper 能在不写脚本业务默认值的前提下，从配置、scene、工具发现结果和显式调用方 override 装配出 `open_host(options)` 与每 Run typed input。

本计划的动机成立：`docs/host/design.md` 已明确当前问题不是 Host 生命周期或 Engine loop 缺陷，而是 Host 外部 runtime assembly schema 与已冻结 typed public contract 没有同源对齐。正确修复路径是统一 schema、typed view、adapter/helper 与 smoke 验证，不是在 smoke 中补业务默认值，也不通过 Host public surface 扩字段绕过。

### 成功信号

- Config catalog record id 只来自 map key，JSON record 内不再出现重复 id 字段；`extends` 只引用同 catalog map key，重复 id 字段 fail fast。
- `models.json`、`execution_profiles.json`、`host_runtime.json`、`runtime_lanes.json`、`tool_discovery.json` 可被 `ConfigLoader` 加载为 typed view，且无旧 `runner_options_profiles`、`runner_hints`、`agent_hints`、旧 `context_budget`、旧 `memory_projection`、旧 `truncation` schema。
- `models.json.models[*].runtime_hints.runner_option_hints` 是 `RunnerCallOptions` hint 真源；execution profile 只保存 semantic `runner_option_hint_id`。
- Override 合并只发生在 Service / composition helper 边界，且只允许 typed allowlist；未知字段 fail fast；优先级固定为 UI / Run override > scene typed override > execution profile baseline > code default。
- `dayu.runtime` 新增 location resolver，输出 `config_overlay_dir`、`prompt_asset_root`、`scene_manifest_root` 的实际路径选择；`ConfigLoader` 和 `ScenePrepare` 不内置 workspace fallback。
- Host public `ContextBudgetPolicy` 与 `MemoryProjectionPolicy` 改为 `context_window_size` + ratio/floor/cap typed shape；公共命令、handle、`open_host(options)` 字段名、request / response dataclass 字段名与 `dayu.host` public exports 不变。
- `ToolTruncateSpec` 支持 declaration 缺省 limit / ttl，并由 assembly 根据 `tool_truncation_policy` 补齐 effective spec；`fetch_more` 名称不进入 config。
- `AgentPolicy` config profile 一比一对齐 public `AgentPolicy` 字段；`fallback_mode` 只允许 `force_answer` / `raise_error`，默认 `fallback_prompt` 为“请基于已获得的信息直接回答问题。信息不足时必须说明不确定性，不得编造。”。
- Scene manifest 删除 `conversation`、泛化 `runtime`、`prompt_mt`；使用 `model.default_model_id`、`model.runner_option_hint_id` 与可选顶层 typed `agent_policy` allowlist。
- 旧 `dayu-agent` 模型目录从 git 历史完整迁移进新 `models.json`，provider extension DSL 由 Engine 侧 helper 映射到 typed provider extension，未知值 fail closed；`dayu.runtime` 不 import Engine。
- `utils/smoke_host_public_multiturn.py` 默认通过 dedicated ordinary scene `smoke_host_public_multiturn`、runtime location resolver、ConfigLoader、ToolsDiscovery、ScenePrepare 与 adapter/helper 做 Service-like assembly；缺配置、缺 helper、缺 contract mapping 时输出装配诊断并在调用 Host 前失败。

## 2. Non-goals

- 不修改 Host command path、Host handle methods、`open_host(options)` option 字段名、public request / response dataclass 字段名、`dayu.host` public exports。
- 不修改 Host durable state machine、admission、EventLog、recovery、ToolRuntime accept barrier 或 Engine execution loop 行为边界。
- 不修改具体财报业务工具实现，不修改 Fins storage。
- 不实现真实 Service / CLI / Web / GUI workflow 接入，不实现 Skill workflow、artifact store、parser / replay / retry / stop policy。
- 不提供旧 schema 兼容 reader、compatibility wrapper、compatibility re-export 或兼容测试。
- 不让 `dayu.runtime` import `dayu.engine`、`dayu.host`、`dayu.service`、`dayu.ui`、`dayu.fins` 或具体业务工具包。
- 不让 scene manifest 表达 workflow graph、conversation lifecycle、Host runtime deployment、lane、SQLite、artifact root、memory / context policy 或 worker backend。

## 3. Current-state Audit Instructions for Dirty Files

开始任何 implementation slice 前，controller / implementation agent 必须先记录并分类当前 dirty worktree。当前已知状态：

- 当前分支：`docs/phase12-design-discussion`。
- 已修改：`README.md`、`docs/host/design.md`、`docs/host/implementation-control.md`、`utils/smoke_host_public_multiturn.py`。
- 未跟踪：`docs/host/runtime-assembly-followup-discussion.md`。
- `utils/smoke_host_public_multiturn.py` 当前已有大规模半成品改动，不能直接视为 approved implementation。

Implementation worker 的前置审计步骤：

1. 运行 `git status --short`、`git diff --name-status`、`git diff --stat`，把 dirty 文件分成三类：design/control refinement、pre-existing smoke/README half-finished work、当前 slice intended edits。
2. 对 `docs/host/design.md` 与 `docs/host/implementation-control.md`：只读取作为当前 Phase 12.1 设计/控制真源；implementation slice 不应再修改它们，除非 controller 明确派发 design/control fix。
3. 对 `README.md` 与 `utils/smoke_host_public_multiturn.py`：先用 `git diff -- README.md utils/smoke_host_public_multiturn.py` 判断哪些内容可作为实现素材，哪些是旧 schema / 旧 adapter 临时补丁；不得盲目 preserve 或 discard。
4. 对 `docs/host/runtime-assembly-followup-discussion.md`：只作为 rationale reference；若与 `docs/host/design.md` 或 `docs/host/implementation-control.md` 冲突，以设计/控制真源为准。
5. 每个 slice 的 implementation artifact 必须写明：本 slice 接管了哪些 pre-existing dirty hunks、丢弃了哪些半成品思路、保留理由、验证命令和 residual risk。

## 4. Slice Breakdown

### Slice 1: Host Policy Contracts and Tool Truncate Boundary

Objective: 修正 Host public policy dataclass typed shape 与 `ToolTruncateSpec` declaration/effective 语义，为后续 ConfigLoader / adapter 生成 typed Host input 提供稳定目标。

Dependencies: 当前设计真源已写明 public contract 限界；本 slice 必须先于 config schema 和 smoke helper。

Owned files/modules:

- `dayu/host/context_policy.py`
- `dayu/host/context_budget.py`
- `dayu/host/context_governance.py`
- `dayu/host/memory.py`
- `dayu/host/memory_repair.py`
- `dayu/host/durable/memory.py`
- `dayu/contracts/tool_schema.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/tool_runtime_schema_projection.py`
- 相关 tests: `tests/host/test_context_policy.py`、`tests/host/test_context_budget.py`、`tests/host/test_memory_projection.py`、`tests/host/test_toolruntime_truncation_fetch_more.py`、`tests/host/test_phase6_toolruntime_integration.py`、`tests/host/test_public_open_host_options.py`

Allowed changes:

- 将 `ContextBudgetPolicy` 字段改为：`context_window_size`、`soft_threshold_context_ratio`、`hard_threshold_context_ratio`、`max_proactive_compactions_per_run`、`max_reactive_compactions_per_run`、`max_compaction_attempts_per_operation`、`policy_ref`。
- Host 内部用 `context_window_size * ratio` 派生 soft / hard threshold tokens；移除 public policy 中的 `reserved_output_tokens`、`safety_margin_ratio`、`hard_threshold_tokens`、`minimum_protection_tokens`。
- 将 `MemoryProjectionPolicy` 改为：`context_window_size`、`max_pinned_items`、`max_verified_facts`、`max_working_assumptions`、`recent_raw_turns_floor`、stable layer ratio/floor/cap、history pool ratio/floor/cap、raw turn ratio/floor/cap、`max_lag_events_for_inline_delta`、`max_delta_repair_events`。
- Host memory projection 内部只消费 derived effective size units；derived helper 可放在 `dayu.host.memory` 私有函数或专门 policy helper，不能要求上层传 callback / provider。
- 放宽 `ToolTruncateSpec` declaration：enabled 且有 strategy 时允许 `limits` 缺对应 key，允许 `ttl_seconds=None`；仍禁止未知 strategy、非法 limit、同时设置 `target_field` 和 `field_path` 等非法组合。
- 增加 effective truncate spec helper，输入 declaration spec + policy default limit/ttl，输出 Host ToolRuntime 消费的 complete typed spec；该 helper 放在 Host/tool runtime 边界或 runtime assembly helper，不能让 Engine 参与。

Forbidden changes:

- 不改 `OpenHostOptions.context_budget_policy`、`OpenHostOptions.memory_projection_policy` 字段名。
- 不新增 Host request / response 字段。
- 不让 ToolRuntime accept barrier 语义改变；截断仍在工具结果 accepted 前由 ToolRuntime 管理。

Tests and validation:

- `source .venv/bin/activate && pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py -q`
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_options.py tests/host/test_phase6_toolruntime_integration.py -q`
- `source .venv/bin/activate && python -m pyright dayu/host dayu/contracts tests/host`

README triggers:

- 修改 `dayu/host/` 时检查并按需更新 `dayu/host/README.md`。
- 修改公共分层/contract 表述时检查 `dayu/README.md`。
- 修改 tests 时检查 `tests/README.md`。

Stop condition:

- Host policy typed shape 与 truncate declaration/effective tests 通过；无 Host public surface 越界；implementation artifact 记录后续 ConfigLoader 需要使用的新字段。

### Slice 2: Config Schema, Location Resolver, Default Assets, Full Model Catalog

Objective: 将 runtime config schema 修正为设计真源定义的新形状，补齐 `runtime_lanes.json` 与全量模型目录迁移，并新增层中立 location resolver。

Dependencies: Slice 1 的 public policy target 已稳定。

Owned files/modules:

- `dayu/runtime/config_loader.py`
- 新增 `dayu/runtime/location.py` 或 `dayu/runtime/locations.py`
- `dayu/runtime/__init__.py` 仅更新模块概览，不做包根 re-export
- `dayu/config/models.json`
- `dayu/config/execution_profiles.json`
- `dayu/config/host_runtime.json`
- 新增 `dayu/config/runtime_lanes.json`
- `dayu/config/tool_discovery.json`
- 相关 tests: `tests/runtime/test_config_loader.py`、新增 `tests/runtime/test_runtime_location.py`、`tests/runtime/test_import_boundary.py`、`tests/runtime/test_weak_typing_guard.py`、`tests/engine/test_config_models.py`

Allowed changes:

- `ConfigLoader` 增加第五类 config view：`runtime_lanes`；`RuntimeConfig` 包含 `models`、`execution_profiles`、`host_runtime`、`runtime_lanes`、`tool_discovery`。
- 所有 catalog parser 使用 map key 注入 typed id，JSON record 内出现 `runtime_id`、`host_runtime_id`、`model_id`、`profile_id`、`execution_profile_id`、`provider_id` 等重复 id 字段时 fail fast。
- `execution_profiles.json` 顶层使用 `default_execution_profile_id` 与 `execution_profiles`；默认 id 为 `standard`。
- execution profile record 使用 `run_baseline`、`compactor_baseline`、`context_budget_policy`、`memory_projection_policy`、`tool_truncation_policy`、`agent_policy_profile_id`；顶层保留 `agent_policy_profiles`，删除 `runner_options_profiles`、`runner_hints`、`agent_hints`。
- `models.json` record 使用 `runtime_hints.runner_option_hints`，每个 hint 是完整 `RunnerCallOptions` 配置片段；execution profile baseline 只保存 `model_id` 和 semantic `runner_option_hint_id`。
- `host_runtime.json` 顶层使用 `default_host_runtime_id`；record 使用 `host_execution_lane_name` 与 `worker_backend`；删除内联 lane catalog、`worker_factory_kind`、`prompt_asset_root`、`scene_manifest_root` fallback 字段。
- `runtime_lanes.json` 拥有 runtime lane coordinator DB 路径和 lane catalog；`host_runtime.host_execution_lane_name` 必须引用已存在 lane。
- location resolver 位于 `dayu.runtime`，输入 project/workspace root 与 package config root，输出 typed result：`config_overlay_dir: Path | None`、`prompt_asset_root: Path`、`scene_manifest_root: Path`，其中 workspace `config` 不存在时 `config_overlay_dir=None`。
- 从 git 历史完整迁移旧模型目录。直接证据来源可用 `git show 9952fd4:dayu/config/llm_models.json`；必须迁移其中所有模型 record 到新 `models.json`，并把旧 `runtime_hints.temperature_profiles` 转成 `runtime_hints.runner_option_hints`。
- `provider_request_extension` 继续作为 JSON DSL 原样进入 runtime config typed view；不在 `dayu.runtime` 内 import Engine typed provider extension。

Forbidden changes:

- 不恢复 `dayu/config/llm_models.json` 或 `dayu/config/run.json`。
- 不写旧 schema compatibility reader。
- 不让 ConfigLoader 解析 secret、创建 provider client、解释 scene manifest 或构造 Host/Engine 对象。

Tests and validation:

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_runtime_location.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
- `source .venv/bin/activate && pytest tests/engine/test_config_models.py -q`
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime tests/engine/test_config_models.py`

README triggers:

- 修改 `dayu/config/` 时更新 `dayu/config/README.md`。
- 修改 `dayu/runtime` import boundary / 开发边界时检查 `dayu/README.md`。
- 修改 tests 时检查 `tests/README.md`。

Stop condition:

- 新默认配置可被完整加载；旧字段 fail fast；runtime import boundary clean；全量旧模型已迁移且 tests 证明 provider DSL 原样保留。

### Slice 3: ScenePrepare Schema and Scene Asset Migration

Objective: 将 scene manifest schema 修正为设计真源定义的 scene-only 输入，删除旧 conversation/runtime/prompt_mt 语义，并输出 typed model hints 与 typed agent policy override。

Dependencies: Slice 2 的 config hint 命名已稳定。

Owned files/modules:

- `dayu/runtime/scene_prepare.py`
- `dayu/config/prompts/manifests/*.json`
- `dayu/config/prompts/scenes/*.md`
- 删除 `dayu/config/prompts/manifests/prompt_mt.json` 与 `dayu/config/prompts/scenes/prompt_mt.md`
- 新增 dedicated smoke scene manifest / prompt fragments: `dayu/config/prompts/manifests/smoke_host_public_multiturn.json` 与必要 fragment
- 相关 tests: `tests/runtime/test_scene_prepare.py`、`tests/runtime/test_scene_tool_selection.py`、`tests/runtime/test_scene_assets_migration.py`

Allowed changes:

- Scene manifest allowed top-level fields 固定为 `schema_version`、`scene`、`version`、`description`、`capability_tags`、`extends`、`model`、`agent_policy`、`tool_selection`、`defaults`、`fragments`、`context_slots`。
- 删除 `conversation` 与泛化 `runtime` 解析；这些字段出现必须 fail fast。
- `model.default_name` 改为 `model.default_model_id`；`model.temperature_profile` 改为 `model.runner_option_hint_id`。
- `agent_policy` 是可选顶层 typed override block，只允许字段：`max_iterations`、`continuation_max_attempts`、`allow_tool_calls`、`tool_execution_timeout_seconds`、`fallback_mode`、`fallback_prompt`、`continuation_prompt`、`max_consecutive_failed_tool_batches`；未知字段 fail fast。
- `PreparedSceneInputs` 输出不再包含 `runtime_hints` / `conversation_hint` 旧概念；如需要保持 typed output，可改为 `model_hints` 与 `agent_policy_override`。
- `prompt_mt` 不再作为独立 scene；如旧用途需要表达，合并为普通 `prompt` scene capability 或删除。
- Dedicated smoke scene `smoke_host_public_multiturn` 必须是普通 scene asset，不在 `ScenePrepare` 代码中写 special case。

Forbidden changes:

- 不让 scene manifest 表达 worker backend、lane、SQLite、artifact root、context/memory/truncation policy。
- 不让 ScenePrepare 读取 ConfigLoader、ToolsDiscovery 或 workspace fallback。

Tests and validation:

- `source .venv/bin/activate && pytest tests/runtime/test_scene_prepare.py tests/runtime/test_scene_tool_selection.py tests/runtime/test_scene_assets_migration.py -q`
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`

README triggers:

- 修改 `dayu/config/prompts` 与 scene schema 时更新 `dayu/config/README.md`。
- 修改 runtime assembly 概览时检查 `dayu/README.md`。
- 修改 tests 时检查 `tests/README.md`。

Stop condition:

- 所有包内 scene asset 均可被新 `ScenePrepare` 装配；旧字段均 fail fast；smoke scene 可作为普通 scene 装配。

### Slice 4: Assembly Helpers and Engine Provider Extension Helper

Objective: 放置并实现最小 adapter/helper，使 Service-like caller 可以从 runtime typed config、prepared scene、discovered tools 和显式 override 映射到现有 Host / Engine typed inputs，同时保持 `dayu.runtime` import boundary clean。

Dependencies: Slice 1-3 的 typed contracts、config view 与 scene output 已稳定。

Owned files/modules:

- 新增 `dayu/engine/provider_extensions.py` 或 `dayu/engine/contracts/provider_extensions.py`
- 新增 `dayu/runtime/assembly.py` 或 `dayu/runtime/assembly_helpers.py` 中仅保留 runtime-neutral helper
- 如 helper 需要 Host / Engine typed objects，放在 Service/composition 边界模块，不放入 `dayu.runtime`；当前项目如无 `dayu.service`，可放在 `utils` smoke 私有 adapter；若要新增 `dayu/host` 外部组合 helper，必须先经 controller 确认。本计划默认优先 smoke 私有 adapter + Engine helper，避免新公共业务层。
- `utils/smoke_host_public_multiturn.py` 可在 Slice 5 接管调用；本 slice 可先新增可测试 helper。
- 相关 tests: `tests/engine/test_provider_extension_config_adapter.py`、`tests/runtime/test_assembly_helpers.py` 或 smoke adapter focused tests。

Placement decisions:

- Runtime-neutral helper：路径解析、map-key catalog selection、typed allowlist merge、tool truncation policy default lookup、diagnostic data structure，可放 `dayu.runtime`，但不得引用 Host / Engine classes。
- Engine provider extension helper：JSON DSL -> `ProviderRequestExtension` typed union，放 `dayu.engine`，因为它必须 import Engine contract；未知 `type`、未知字段、非法 enum 值 fail closed。
- Service/composition helper：把 model config + runner option hint 映射为 `RunnerSpec` / `RunnerCallOptions`、把 execution profile + model context window 映射为 Host policies、把 scene `agent_policy` override 与 profile baseline 合并为 `AgentPolicy`，该 helper 不能放 `dayu.runtime`。Phase 12.1 若没有真实 Service package，先作为 smoke-local private helper 实现并在 smoke 输出 suggested adapter/helper function names；后续 Service 接入再搬迁。

Allowed changes:

- 实现 typed allowlist merge：UI / Run typed override > scene typed override > execution profile baseline > code default；每层只处理其白名单字段。
- 实现 runner option hint resolution：从 effective model 的 `runtime_hints.runner_option_hints[runner_option_hint_id]` 生成 `RunnerCallOptions`。
- 实现 policy assembly：从 model `context_window_tokens` 注入 `ContextBudgetPolicy.context_window_size` 与 `MemoryProjectionPolicy.context_window_size`。
- 实现 tool truncation effective spec default fill：policy default limit/ttl 补齐 declaration spec，不能改工具声明的 strategy/target。
- 实现 provider extension helper，支持当前 `ProviderRequestExtension` union 的所有已知 DSL：`openai_reasoning`、`anthropic_thinking`、`deepseek_thinking`、`mimo_thinking`、`gemini_thinking`、`qwen_thinking`；未知值 fail closed。

Forbidden changes:

- 不让 `dayu.runtime` import Engine typed contracts。
- 不把 helper 做成 compatibility facade。
- 不把显式参数塞进 extra payload。

Tests and validation:

- `source .venv/bin/activate && pytest tests/engine/test_provider_extension_config_adapter.py -q`
- `source .venv/bin/activate && pytest tests/runtime/test_assembly_helpers.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
- `source .venv/bin/activate && python -m pyright dayu/engine dayu/runtime tests/engine tests/runtime`

README triggers:

- 修改 `dayu/engine/` 时更新 `dayu/engine/README.md`。
- 修改 runtime helper 时检查 `dayu/README.md`。
- 修改 tests 时检查 `tests/README.md`。

Stop condition:

- Provider DSL typed mapping fail-closed；runtime boundary tests 证明 `dayu.runtime` 不依赖 Engine/Host；assembly helper responsibility placement 在 implementation artifact 中明确。

### Slice 5: Service-like Multiturn Smoke Rewrite

Objective: 重写最终验证 smoke，使其通过真实 runtime assembly 路径暴露 schema / contract 缺口，而不是脚本内补业务默认值。

Dependencies: Slice 1-4 完成。

Owned files/modules:

- `utils/smoke_host_public_multiturn.py`
- 可新增 `tests/utils/test_smoke_host_public_multiturn_assembly.py` 或放在 `tests/runtime` / `tests/host` 的 smoke assembly focused tests
- Dedicated smoke scene asset 已由 Slice 3 拥有；本 slice 只消费

Allowed changes:

- 删除或废弃 `manual` / 旧硬编码装配模式；默认使用 runtime location resolver、ConfigLoader、ToolsDiscovery、ScenePrepare。
- CLI 参数保留必要显式 override，例如 workspace root、scene id、execution profile id、host runtime id、model override、runner option hint override；这些 override 必须是 typed allowlist，并按固定优先级合并。
- smoke 通过 ConfigLoader 选择 host runtime、runtime lane、execution profile、model、runner option hint、agent policy profile、tool truncation policy。
- smoke 通过 ToolsDiscovery 发现业务工具；scene tool selection 只在已发现 bundle 内选择工具子集。
- smoke 通过 ScenePrepare 装配 system messages；不得在脚本里拼业务 prompt 或对 `smoke_host_public_multiturn` 写 special case。
- smoke 在调用 Host 前输出 assembly diagnostics：所用 config overlay、prompt root、scene manifest root、host runtime id、execution profile id、model id、runner option hint id、lane name、tool provider report、tool selection、policy refs、provider extension DSL mapping status、suggested adapter/helper function names。
- 如果需要 Service/composition helper 但当前只在 smoke 私有实现，诊断必须明确建议后续提取位置，例如 `service.compose_open_host_options(...)`、`service.compose_submit_followup_request(...)`、`engine.provider_extension_from_config(...)`。

Forbidden changes:

- 不在 smoke 中用业务默认值补齐缺失 schema 字段。
- 不隐藏 config/schema gap；缺字段、未知 override、未知 tool、未知 provider extension 均 fail fast。
- 不绕过 public `open_host(options)` 与 Host handle。

Tests and validation:

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_scene_prepare.py tests/runtime/test_tools_discovery.py -q`
- `source .venv/bin/activate && pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q`
- `source .venv/bin/activate && python utils/smoke_host_public_multiturn.py --help`
- 若环境具备 provider keys，运行真实 smoke；若 provider quota / network 不可用，implementation artifact 必须记录精确 skip / failure reason，但 assembly path tests 不能被跳过。
- `source .venv/bin/activate && python -m pyright utils/smoke_host_public_multiturn.py tests/runtime tests/host`

README triggers:

- 修改 `utils/smoke_host_public_multiturn.py` 或项目级 smoke 使用方式时更新根 `README.md`。
- 修改 tests 时检查 `tests/README.md`。

Stop condition:

- smoke 能在调用 Host 前完成 Service-like assembly diagnostics；缺失映射会失败而非补默认；help 与 assembly focused tests 通过。

### Slice 6: README Sync, Boundary Tests, Aggregate Validation Hardening

Objective: 收口文档、import boundary、weak typing guard、全量受影响验证与 residual risk 归属。

Dependencies: Slice 1-5 完成。

Owned files/modules:

- `README.md`
- `dayu/README.md`
- `dayu/config/README.md`
- `dayu/host/README.md`
- `dayu/engine/README.md`
- `tests/README.md`
- `tests/runtime/test_import_boundary.py`
- `tests/runtime/test_weak_typing_guard.py`
- 必要的 docs/reviews implementation artifact

Allowed changes:

- README 只同步当前代码事实，不写未来设计和过程状态。
- 根 README 只更新用户可见安装、配置、跑通、CLI / smoke / trace/render 入口。
- `dayu/README.md` 只更新整体架构、稳定边界、扩展入口。
- `dayu/config/README.md` 写清新 schema、workspace overlay、prompts 目录职责。
- `dayu/host/README.md` 写清 policy typed shape 与 opener/request 边界，不写 runtime assembly 业务指南。
- `dayu/engine/README.md` 写清 provider extension typed helper边界。
- `tests/README.md` 更新测试分层与新增 smoke/runtime assembly 约定。

Validation:

- `source .venv/bin/activate && pytest tests/runtime -q`
- `source .venv/bin/activate && pytest tests/engine/test_config_models.py tests/engine/test_provider_extension_config_adapter.py -q`
- `source .venv/bin/activate && pytest tests/host/test_context_policy.py tests/host/test_context_budget.py tests/host/test_memory_projection.py tests/host/test_toolruntime_truncation_fetch_more.py -q`
- `source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime dayu/engine dayu/host tests/runtime tests/engine tests/host utils/smoke_host_public_multiturn.py`
- `git diff --check`

Stop condition:

- README 与代码事实一致；boundary tests 覆盖 `dayu.runtime` 禁止依赖；aggregate validation artifact 列出所有 residual risks 与 owner。

## 5. Adapter / Helper Placement Decisions

- `dayu.runtime`：只放层中立能力，包括 location resolver、config typed loading、scene parsing、tool discovery、digest、schema-level allowlist / selector / diagnostic helper。不得 import Host / Engine / Service / UI / Fins / concrete tools。
- `dayu.engine`：放 provider extension DSL -> typed `ProviderRequestExtension` helper。原因是该 helper 必须 import Engine provider extension union；把它放 `dayu.runtime` 会违反 import boundary。
- Service / composition helper：负责把 runtime config + scene + tools + explicit UI/Run override 映射为 `OpenHostOptions`、`SubmitFollowupRequest`、`RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`、Host policies 与 tooling options。当前 Phase 12.1 不实现真实 Service package；如需落地代码，优先放 smoke 私有 helper 并通过 diagnostics 指出后续应抽取函数，避免创建没有 owner 的转发层。
- Host：只接收最终 typed inputs。Host 内可保留 policy derivation / validation helper，但不读取 config、scene 或 provider DSL。
- ToolsDiscovery：只发现 ToolBundle 与 source refs / digest，不读取 scene 或模型配置，不替工具声明截断 strategy/target。

## 6. Review Plan

### Plan review

- 当前 plan 写入后进入 plan review gate。
- 由两个 review Agents 独立执行 plan review，默认使用 `$planreview` / inline criteria。
- Review 必须重点检查：是否足够 code-generation-ready、slice ownership 是否清晰、public contract 限界是否越界、runtime import boundary 是否 clean、dirty files 审计是否可执行、schema migration 是否无兼容逻辑、smoke 是否真的暴露 schema gap。

### Slice code review / re-review

- 每个 implementation slice 完成后产出 durable implementation artifact，再派发至少两个 code review Agents。
- Code review finding 必须按 `$gateflow` finding 格式记录，并由 controller 裁决为 accepted / rejected-with-reason / deferred-with-owner / needs-more-evidence。
- Accepted findings 必须由 fix agent 只修当前 finding；re-review agent 回写最终标题状态。
- Slice commit 前必须确认只 stage 当前 slice 文件和 artifact，不 stage unrelated dirty changes。

### Aggregate deepreview

- 所有 slices accepted 后执行 aggregate deepreview，至少两个 review Agents。
- Deepreview 目标为当前 Phase 12.1 branch 相对 base 的完整 diff；若 base 不是 `main`，controller 必须记录原因。
- Aggregate review 重点：Host public surface 未越界、runtime import boundary、schema fail-fast、no compatibility readers、smoke no business defaults、provider extension fail-closed、README 与代码事实一致。
- Aggregate accepted findings 完成 fix / re-review 后，才可进入 `ready-to-open-draft-PR`。

## 7. Residual Risks and Owners

- 真实 Service / CLI / Web / GUI workflow 接入：owner 为后续 Service / UI / workflow work unit。Phase 12.1 只交付 assembly reference helper / smoke diagnostics，不接入真实业务入口。
- Provider model catalog 时效性：owner 为后续 execution profile / model catalog maintenance。Phase 12.1 只完整迁移当前 git 历史中的旧 catalog，不承诺实时校验外部 provider 最新模型名或上下文窗口。
- Financial tool provider 与财报 scene 内容：owner 为后续 Service / Fins / 配置 work unit。Phase 12.1 不改具体财报工具和 Fins storage。
- Tool truncation policy 与具体工具 declaration 覆盖度：owner 为后续 tool provider hardening。Phase 12.1 提供 declaration/effective boundary 与默认填充，不强制所有既有工具声明截断。
- Service/composition helper 正式归属：owner 为后续 Service assembly work unit。Phase 12.1 smoke 必须输出建议 helper 函数名和缺口诊断，避免把 smoke 私有 helper 误认为最终 Service API。

## Blocking Questions for Controller

无 blocking open questions。当前设计/控制真源已经给出本 phase 的 public contract 限界、schema 目标、切片方向和验证要求；旧模型目录可从 git history 恢复，当前 dirty smoke / README 改动可通过前置审计步骤归类，不阻塞 plan handoff。
