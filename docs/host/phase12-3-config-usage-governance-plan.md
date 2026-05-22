# Phase 12.3 Config Schema / Usage Governance Follow-up Plan

状态：HANDOFF_READY  
Blocking questions：0  
当前 gate：Phase 12.3 plan artifact  
规划 Agent：AgentCodex  
计划真源：`docs/host/design.md`、`docs/host/implementation-control.md`  
辅助上下文：`docs/host/config-schema-followup-discussion.md` 仅用于核对讨论背景，不替代设计真源。

## 1. 目标与动机判断

Phase 12.3 的动机成立，且严重性评估合理。

直接证据：

- `docs/host/design.md` 已明确：`execution_profiles.json` 不保留顶层 `agent_policy_profiles` catalog、`agent_policy_profile_id`、`runner_options_profiles`、`runner_hints` 或 `agent_hints`；单个 execution profile 直接内嵌 `agent_policy`。
- `docs/host/design.md` 已明确：默认 config 不使用 `max_tokens` 限制模型输出；`RunnerCallOptions.max_tokens` 若保留，只能作为显式 per-run / provider adapter override，不能来自默认 model hint。
- `docs/host/design.md` 已明确：usage 是 provider capability 驱动的 post-call observation，不提供 `usage_enabled` / `collect_usage` / `include_usage` config override，不引入 `supports_usage`；Engine 只如实上报，Host ingest durable 化并补齐后续消费关联信息，Context Governance 可用于校准、diagnostic 与后续 Run / compaction 参考，不回改当前 dispatch decision。
- `docs/host/design.md` 已明确：execution profile 由 Service / composition root 显式选择；helper 只做兼容性校验和 diagnostic，不根据 `models.context_window_tokens` 自动切换。
- 当前实现证据显示 schema 仍未收口：`dayu/config/execution_profiles.json` 仍有顶层 `agent_policy_profiles` 与 `execution_profiles.standard.agent_policy_profile_id`；`dayu/config/models.json` 仍在 `runtime_hints.runner_option_hints` 内大量配置 `max_tokens`；`dayu/runtime/config_loader.py` 的 `RunnerOptionHintConfig`、`ExecutionProfileConfig`、`ExecutionProfilesConfig` 仍建模这些旧字段；`dayu/service/host_assembly.py` 仍从 `agent_policy_profiles` 查 profile，并把 hint `max_tokens` 映射到 `RunnerCallOptions.max_tokens`。
- 当前 Host usage 链路已有基础：Engine `usage_reported` 会被 `dayu/host/engine_ingest.py` 写为 `USAGE_REPORTED` projection signal；`dayu/host/context_budget.py` 已有 `UsageObservation` 类型。但当前测试 `tests/host/test_engine_ingest_mapping.py::test_usage_reported_is_projection_signal_without_state_change` 仍断言 payload 不含 `policy_ref` / `estimator_digest`，说明 durable association 和 Context Governance observation 消费尚未完成。

本 phase 不是为了重做 Engine usage 事件链，也不是为了新增用户配置开关；root cause 是 P12.1 / P12.2 后 schema 和 Service mapping 仍保留旧的间接引用与默认输出 token cap，同时 Host usage projection 缺少后续治理可消费的关联信息。

## 2. Worktree 与执行护栏

Implementation Agent 开始前必须先执行：

```bash
git branch --show-current
git status --short
git log -1 --oneline
```

预期：

- 分支不是 `main` / `master` / `develop` / `release/*`。
- 最近 commit 应为 Phase 12.3 baseline 附近提交；若不是 `af74cd4 Prepare phase 12.3 config governance follow-up`，记录实际 baseline 并继续前先确认没有 scope 风险。
- `git status --short` 为空，或只包含明确属于当前 Phase 12.3 gate 的文件。

若发现任何用户不想混入的未提交文件，或 unrelated dirty changes 影响 file ownership，必须停下报告 Controller；不得把 unrelated changes 纳入本 phase、不得顺手格式化、不得 revert 用户改动。

## 3. Scope

### 3.1 In Scope

- 删除 execution profile schema 中的顶层 `agent_policy_profiles` 与 `execution_profiles[*].agent_policy_profile_id`。
- 每个 execution profile 内嵌完整 `agent_policy`，字段一比一对齐当前 Engine / Host public `AgentPolicy` typed shape。
- 从 `models.json.runtime_hints.runner_option_hints`、ConfigLoader typed schema、Service 默认 RunnerCallOptions 装配路径删除默认 `max_tokens` 来源。
- 保留 `RunnerCallOptions.max_tokens` public contract 时，只允许显式 per-run / provider adapter override 使用；OpenAI-compatible payload 继续仅对显式非 `None` 的 `RunnerCallOptions.max_tokens` 写 provider 字段。
- 保持 Engine usage 上报链；不改 Engine `usage_reported` event contract。
- Host ingest 扩展 `USAGE_REPORTED` durable projection signal payload，使其包含后续 Context Governance 消费需要的 attempt / execution context、policy ref、estimator digest 或估算缺失原因；provider request id 不是当前 Engine usage event contract 的必需字段，只能作为可选关联信息。
- Context Governance 把 durable usage 作为 post-call observation，用于估算器校准数据、diagnostic 与后续治理参考；不得改变当前已完成的 dispatch decision，usage 缺失或 observation 构造失败不得导致 Run 失败。
- execution profile 按场景和窗口显式分档，例如 `standard-256k`、`standard-1m`、`wechat-256k`、`wechat-1m`。
- Service / composition root 显式选择 profile；assembly helper 只做兼容性校验和 diagnostic，禁止基于 model context window 自动切换。

### 3.2 Non-goals

- 不启动完整 `$gateflow` 流程，不创建 commit，不 push，不创建 PR。
- 不实现真实 Service / CLI / Web / GUI workflow 接入。
- 不修改 Host command / handle public method，不改 `open_host(options)` 字段名，不改 `SubmitFollowupRequest` public 字段名。
- 不修改 Engine Agent loop 状态机、不修改 Runner usage event contract、不修改 ToolRuntime accept barrier。
- 不新增 `usage_enabled` / `collect_usage` / `include_usage` 配置项，不新增 `supports_usage`。
- 不把 post-call usage 回头用于当前 Run dispatch / admission / compaction 决策。
- 不删除或重命名 `RunnerCallOptions.max_tokens`；本 phase 只切断默认 config 来源，保留显式 override 行为。
- 不做旧 schema 兼容读取、不保留旧字段兼容测试、不新增 compatibility re-export / wrapper / facade。
- 不修改具体财报业务工具，不绕过 `dayu.fins.storage`。

## 4. Allowed Files / Modules

Implementation slices 可修改以下文件或同目录下紧邻测试文件。若需要超出列表，先停下报告 Controller。

- Config default / docs：
  - `dayu/config/models.json`
  - `dayu/config/execution_profiles.json`
  - `dayu/config/README.md`
- Runtime config / assembly：
  - `dayu/runtime/config_loader.py`
  - `dayu/runtime/assembly.py`
  - `tests/runtime/test_config_loader.py`
  - `tests/runtime/test_assembly_helpers.py`
  - `tests/runtime/test_import_boundary.py`
  - `tests/runtime/test_weak_typing_guard.py`
- Service assembly：
  - `dayu/service/host_assembly.py`
  - `tests/service/test_host_assembly.py`
- Host usage observation：
  - `dayu/host/context_budget.py`
  - `dayu/host/engine_ingest.py`
  - `tests/host/test_context_budget.py`
  - `tests/host/test_engine_ingest_mapping.py`
  - 必要时可触及 `dayu/host/context_events.py`，但只能新增 usage observation payload helper，不得改变 compact event schema 语义。
- Engine usage guard tests only：
  - `tests/engine/test_config_models.py`
  - `tests/engine/runners/openai/test_stream_usage_capability_gating.py`
  - `tests/engine/runners/openai/test_non_stream_response.py`
  - `tests/engine/runners/openai/test_sse_usage_recorded.py`
- README sync by trigger：
  - `dayu/host/README.md`
  - `dayu/engine/README.md`
  - `tests/README.md`
  - 根目录 `README.md` 仅当项目级使用方式、CLI、trace/render 入口或用户手册内容实际过期时更新。
  - `dayu/README.md` 仅当分层关系、装配方式或稳定术语发生实际变更时更新；本 plan 预期不需要。

## 5. Import Boundary

- `dayu.runtime` 只能依赖标准库、`dayu.contracts` 与同包层中立 helper；不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- `dayu.runtime.config_loader` 只负责读取、overlay、extends 解析、typed validation 和层中立 typed view；不得构造 Host / Engine typed object，不得创建 provider client，不得解析 secret。
- `dayu.runtime.assembly` 只做层中立选择、merge、compatibility validation 和 diagnostic；不得 import Host / Engine public contracts，不得自动选择 execution profile。
- `dayu.service.host_assembly` 可以依赖 Host / Engine public contracts，并负责把 runtime typed config 显式映射为 `OpenHostOptions`、`RunnerSpec`、`RunnerCallOptions`、`AgentPolicy`。
- `dayu.host` 不得 import `dayu.service` / `dayu.ui` / `dayu.fins`，不得理解 config 文件或 scene manifest。
- Engine 不得 import Host / Service，不得理解 Host budget、memory 或 usage governance。

## 6. Public Surface 禁止修改清单

本 phase 禁止修改以下 public surface：

- `OpenHostOptions` 字段名与语义。
- `SubmitFollowupRequest` 字段名与语义。
- Host public handle / command method 名称、参数与返回类型。
- Engine `AgentRunRequest`、`AgentRunResult`、`EngineEvent`、`UsageReportedData`、`RunnerUsageRecordedData` public event contract。
- `RunnerSpec.supports_stream_usage` 字段名与 capability 语义。
- `RunnerCallOptions.max_tokens` 字段名与 explicit override 语义。
- `dayu.host` 包根 public exports。
- ToolRuntime accept barrier、fetch_more、duplicate governance 与 wait record public behavior。

允许修改 `dayu.service.host_assembly.ServiceOpenHostAssemblyDiagnostics`，因为它是 Service 装配 helper 的诊断输出；若新增字段，必须同步测试和 README，并保证不把它当 Host public contract。

## 7. Implementation Slices

### Slice 1: Config Schema Cleanup

目标：删除旧 execution profile agent policy 间接引用和默认 `max_tokens` schema，更新 ConfigLoader、runtime assembly、Service default mapping 与默认配置。

Allowed files/modules:

- `dayu/config/models.json`
- `dayu/config/execution_profiles.json`
- `dayu/config/README.md`
- `dayu/runtime/config_loader.py`
- `dayu/runtime/assembly.py`
- `dayu/service/host_assembly.py`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_assembly_helpers.py`
- `tests/service/test_host_assembly.py`
- `tests/engine/test_config_models.py`
- `tests/runtime/test_import_boundary.py`
- `tests/runtime/test_weak_typing_guard.py`

Implementation decisions:

- 在 `dayu/runtime/config_loader.py` 中：
  - 将 `RunnerOptionHintConfig` 字段收敛为 `temperature: float`、`top_p: float`、`stream: bool`；删除 `max_tokens` 字段、docstring 参数和 `_parse_runner_option_hint` 对 `max_tokens` 的读取。
  - `_parse_runner_option_hint` 的 exact fields 改为只允许 `temperature` / `top_p` / `stream`；旧 `max_tokens` 出现时必须 fail fast 为 unknown field。
  - 删除 `AgentPolicyProfileConfig.agent_policy_profile_id` 与顶层 `agent_policy_profiles` catalog 概念；可将类型改名为 `AgentPolicyConfig`，不得保留兼容 alias。
  - `ExecutionProfileConfig` 删除 `agent_policy_profile_id: str`，新增 `agent_policy: AgentPolicyConfig`。
  - `ExecutionProfilesConfig` 删除 `agent_policy_profiles`。
  - `ConfigLoader.load_execution_profiles` 只接受顶层 `default_execution_profile_id` 和 `execution_profiles`；`map_fields` 只包含 `execution_profiles`。
  - `_parse_execution_profile` exact fields 必须包含 `agent_policy`，禁止 `agent_policy_profile_id`。
  - 删除 `_parse_agent_policy_profile_map`、`_validate_execution_profile_references` 以及所有顶层 agent policy catalog 引用。
  - 保留 agent policy 字段校验规则：`max_iterations` 正整数、`continuation_max_attempts` 非负整数、`allow_tool_calls` bool、`tool_execution_timeout_seconds` 正数、`fallback_mode` 只允许 `force_answer` / `raise_error`、`fallback_prompt` / `continuation_prompt` 字符串、`max_consecutive_failed_tool_batches` 正整数。
- 在 `dayu/runtime/assembly.py` 中：
  - 将 `AgentPolicyProfileConfig` import 和参数类型迁移到新的 `AgentPolicyConfig`。
  - `merge_agent_policy_config` 的 `execution_profile` 参数语义改为 execution profile 内嵌 agent policy baseline；函数名可保留，因为它表达 merge 行为而非旧 schema。
  - 不新增 Host / Engine import。
- 在 `dayu/service/host_assembly.py` 中：
  - 删除对 `config.execution_profiles.agent_policy_profiles[...]` 的查找。
  - `compose_open_host_options` 直接使用 `execution_profile.agent_policy` 作为 baseline，并与 scene override 合并。
  - `_runner_options_from_hint` 返回 `RunnerCallOptions(temperature=hint.temperature, max_tokens=None, top_p=hint.top_p, stream=hint.stream)`；`max_tokens=None` 是默认 config path 的唯一结果。
  - 删除 `ServiceOpenHostAssemblyDiagnostics.agent_policy_profile_id`，必要时替换为 `agent_policy_source: str` 或只保留 `agent_policy_sources`。
  - `_agent_policy_defaults_from_profile` 重命名为 `_agent_policy_defaults_from_config`，输入为内嵌 agent policy config；不保留旧 wrapper。
- 在 `dayu/config/models.json` 中删除所有 runner option hint 内的 `max_tokens`。
- 在 `dayu/config/execution_profiles.json` 中：
  - 删除顶层 `agent_policy_profiles`。
  - 删除每个 profile 的 `agent_policy_profile_id`。
  - 每个 profile 内嵌完整 `agent_policy` block。
  - 默认 profile 暂可仍由 Slice 3 改名分档；Slice 1 只保证旧 schema 字段不再存在。

Tests:

- 更新 `tests/runtime/test_config_loader.py` fixture：
  - `_runner_option_hints()` 不再写 `max_tokens`。
  - `_execution_profile_record()` 内嵌 `agent_policy`。
  - `_minimal_package_config()` 顶层不再写 `agent_policy_profiles`。
- 新增 / 修改断言：
  - 默认 `load_runtime_config()` 中 runner hint 没有 `max_tokens` 属性。
  - 旧 `models.json.runtime_hints.runner_option_hints.*.max_tokens` 被拒绝，错误消息指向 unknown field。
  - 旧顶层 `agent_policy_profiles` 被拒绝。
  - 旧 `execution_profiles.*.agent_policy_profile_id` 被拒绝。
  - 内嵌 `agent_policy` 缺字段、fallback mode 非法、字段类型非法均 fail fast。
- 更新 `tests/runtime/test_assembly_helpers.py`：
  - 通过 `config.execution_profiles.execution_profiles["..."].agent_policy` 获取 baseline。
  - `merge_agent_policy_config` field source 仍能区分 `execution_profile`、`scene_override`、`run_override`。
- 更新 `tests/service/test_host_assembly.py`：
  - overlay fixture 改为内嵌 `agent_policy`。
  - 增加断言：`result.options.ordinary_run_baseline.runner_options.max_tokens is None`。
  - 增加断言：scene agent policy override 仍按白名单覆盖内嵌 baseline。
- 更新 `tests/engine/test_config_models.py`：删除默认 config hint `max_tokens` 断言，改为断言默认 config 不携带输出 token cap。
- 保留 Engine/OpenAI payload explicit override 测试不变；如现有测试检查 `RunnerCallOptions(max_tokens=100)` 写入 payload，应继续通过，证明 public explicit override 未删除。

Validation commands:

```bash
source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py tests/engine/test_config_models.py -q
source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
source .venv/bin/activate && python -m pyright dayu/runtime dayu/service tests/runtime tests/service tests/engine/test_config_models.py
```

README sync:

- 必须更新 `dayu/config/README.md`：删除 `max_tokens` 默认 hint 说明、删除 `agent_policy_profiles` / `agent_policy_profile_id`，改为内嵌 `agent_policy`。
- `tests/README.md` 若列出 runtime config schema 覆盖项，应同步删除旧字段。
- 本 slice 预期不需要更新 root `README.md`、`dayu/README.md`、`dayu/host/README.md`、`dayu/engine/README.md`。

Acceptance criteria:

- `rg -n '"max_tokens"' dayu/config/models.json` 无输出。
- `rg -n 'agent_policy_profiles|agent_policy_profile_id' dayu/config dayu/runtime dayu/service tests/runtime tests/service` 无旧 schema 命中；若命中，只能是本 phase plan 或明确的 negative test 字符串。
- 默认 Service assembly 生成的 ordinary / compactor `RunnerCallOptions.max_tokens` 均为 `None`。
- 显式 per-run `RunnerCallOptions.max_tokens` 的现有 Host / Engine contract 测试仍通过。
- `dayu.runtime` import boundary tests 通过，无新增 pyright 错误。

Stop condition:

- 若删除旧 schema 后发现必须修改 Host / Engine public dataclass 字段才能继续，停下报告 Controller；不得夹带 public contract change。

### Slice 2: Usage Observation Consumer

目标：保持 Engine usage 上报链不变，在 Host ingest durable projection signal 中补齐后续 Context Governance 消费所需关联信息，并把 usage 作为 post-call observation 消费；usage 缺失或异常不导致 Run 失败，不回改当前 dispatch decision。

Allowed files/modules:

- `dayu/host/context_budget.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_context_budget.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/engine/runners/openai/test_stream_usage_capability_gating.py`
- `tests/engine/runners/openai/test_non_stream_response.py`
- `tests/engine/runners/openai/test_sse_usage_recorded.py`
- `dayu/host/README.md` if behavior text is stale
- `dayu/engine/README.md` if usage docs are stale
- `tests/README.md`

Implementation decisions:

- 不修改 Engine `RunnerUsageRecordedData` / `UsageReportedData` 字段，不修改 Engine Agent loop；本 phase 不建议、也不要求给 usage event contract 增加 `provider_request_id`。
- 在 `dayu/host/context_budget.py` 中补充 usage observation helper，推荐形态：
  - `UsageObservationDiagnostic` dataclass，字段使用严格类型，例如 `observation_digest: str`、`estimator_digest: str | None`、`policy_ref: str`、`estimated_input_tokens: int | None`、`prompt_token_delta: int | None`、`status: str`。
  - `build_usage_observation_diagnostic(observation: UsageObservation, *, estimated_input_tokens: int | None) -> UsageObservationDiagnostic`。
  - helper 只计算 post-call diagnostic / calibration data，不返回 `ContextBudgetDecision`，不修改 `BudgetEstimate`，不持久化。
  - 若实现更简单，也可不新增 dataclass，只新增返回 `Mapping[str, JsonValue]` 的私有 helper；但不得使用 `Any` 或 extra payload bag。
- 在 `dayu/host/engine_ingest.py` 中：
  - `_append_projection_signal` payload 必须继续写 `attempt_id`、`execution_id`、`iteration_id`、`prompt_tokens`、`completion_tokens`、`total_tokens`。
  - 新增必需 payload 字段：
    - `session_id`
    - `run_id`
    - `policy_ref`
    - `estimator_digest`
    - `estimated_input_tokens`
    - `usage_observation_status`
    - `usage_observation_digest` 或等价稳定 diagnostic ref
  - `provider_request_id` 是可选 payload 字段：当当前 Engine event/context 已经能在不改变 Engine usage contract、不增加脆弱 lookup 的前提下提供 provider request id 时可以写入；不可用时默认值必须为 `None`，并继续接受 usage projection。
  - `policy_ref` 在 `_context_budget_policy is None` 时写 `"none"`，不得抛错。
  - `estimator_digest` 通过当前 durable run input event 和当前 policy 重新构造与 pre-dispatch 同源的 conservative estimate；若 input event 缺失、payload 不可读或 estimate 失败，写 `None` 并设置 `usage_observation_status` 为明确原因，例如 `estimate_unavailable`，仍接受 usage projection signal。
  - 估算失败只能影响 observation diagnostic，不得关闭 Attempt、不得改变 Run 状态、不得让 usage ingest 返回 rejected。
  - 不把 observation 写为 canonical fact；继续使用 `EventClass.PROJECTION_SIGNAL`。
  - 不新增独立 durable table，除非 review 证明 EventLog projection signal 无法承载后续消费；如需 table，必须停下报告 Controller，因为这会扩大 durable schema scope。
- Engine/OpenAI usage capability 行为保持：
  - `stream=True` 且 `RunnerSpec.supports_stream_usage=True` 时 payload 写 `stream_options.include_usage=true`。
  - `stream=True` 且 `supports_stream_usage=False` 时不写 `stream_options`。
  - 非流式 response 有 usage 时继续读取并产生 Runner usage event。
  - malformed usage 仍为非终止诊断或被忽略，不导致 Run 失败。

Tests:

- 更新 `tests/host/test_engine_ingest_mapping.py::test_usage_reported_is_projection_signal_without_state_change`：
  - 仍断言 event class 为 `PROJECTION_SIGNAL`、event type 为 `USAGE_REPORTED`。
  - 断言 payload 包含 `attempt_id`、`execution_id`、`session_id`、`run_id`、`policy_ref`、`estimator_digest`、`usage_observation_status`。
  - 断言 Run / Attempt 仍为 `RUNNING`，证明不改当前 dispatch decision。
- 新增 Host ingest tests：
  - 有 context budget policy 和可读 input event 时，usage payload 包含非空 `estimator_digest`、`policy_ref` 等关联信息。
  - 无 context budget policy 时，payload 写 `policy_ref="none"`、`estimator_digest is None`，Run 仍不失败。
  - input event 缺失或估算异常时，usage projection signal 仍被接受，payload 记录 `estimate_unavailable`，Run / Attempt 状态不变。
  - provider request id 缺失时，usage projection signal 仍被接受，payload 中对应值为 `None`，Run / Attempt 状态不变。
  - 不允许测试要求从 `UsageReportedData` 或 `RunnerUsageRecordedData` 读取 `provider_request_id`；这些 Engine usage event contracts 在 Phase 12.3 保持不变。
- 更新 `tests/host/test_context_budget.py`：
  - `UsageObservation` 仍校验 token 非负、时间 UTC、必填 ids。
  - usage observation diagnostic / calibration helper 不调用 `decide_context_budget`，不改变已有 decision。
  - `prompt_token_delta` 或等价校准字段由 `prompt_tokens - estimated_input_tokens` 得出；缺少 estimate 时为 `None`。
- Engine tests 只做 regression：
  - `tests/engine/runners/openai/test_stream_usage_capability_gating.py`
  - `tests/engine/runners/openai/test_non_stream_response.py`
  - `tests/engine/runners/openai/test_sse_usage_recorded.py`

Validation commands:

```bash
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q
source .venv/bin/activate && pytest tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q
source .venv/bin/activate && python -m pyright dayu/host tests/host tests/engine/runners/openai
```

README sync:

- `dayu/host/README.md` 若仍描述 usage projection 缺少 policy / estimator association，必须更新为 post-call observation 事实。
- `dayu/engine/README.md` 只在 usage event / stream usage capability 说明过期时更新；不得把 Host governance 写成 Engine 职责。
- `tests/README.md` 更新 Host ingest / Context Governance usage observation 覆盖说明。

Acceptance criteria:

- Engine usage chain tests 不需要改 production Engine contract。
- Host `USAGE_REPORTED` projection signal durable payload 有后续消费关联信息。
- usage observation 不产生 canonical fact，不改变 Run / Attempt 状态，不触发 current dispatch decision 变更。
- usage 缺失、provider 不支持 usage、malformed usage 或 Host observation estimate 缺失均不导致 Run 失败。

Stop condition:

- 若实现需要 Engine 增加新 usage config capability、Host durable state machine schema change、或新增 public Host API，停下报告 Controller。

### Slice 3: Execution Profile 分档与 Compatibility Diagnostics

目标：默认 execution profiles 显式按场景和 context window 分档；Service 显式选择 profile，assembly helper 只做兼容性校验和 diagnostic，不根据 model `context_window_tokens` 自动切换。

Allowed files/modules:

- `dayu/config/execution_profiles.json`
- `dayu/config/README.md`
- `dayu/runtime/config_loader.py`
- `dayu/runtime/assembly.py`
- `dayu/service/host_assembly.py`
- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_assembly_helpers.py`
- `tests/service/test_host_assembly.py`
- `tests/runtime/test_import_boundary.py`
- `tests/runtime/test_weak_typing_guard.py`

Implementation decisions:

- 在 execution profile schema 中新增机器可读兼容性字段：
  - `context_window_class: str`，第一版允许 `"256k"` 与 `"1m"`。
  - `min_context_window_tokens: int`，必须为正整数。
  - 这两个字段只用于校验和 diagnostic，不用于自动选择 profile。
- 在 `dayu/runtime/config_loader.py` 中：
  - `ExecutionProfileConfig` 新增 `context_window_class` 与 `min_context_window_tokens`。
  - `_parse_execution_profile` exact fields 包含这两个字段。
  - 校验 `context_window_class` 只允许 `"256k"` / `"1m"`。
  - 校验 `min_context_window_tokens` 正整数。
- 在 `dayu/runtime/assembly.py` 中新增层中立 compatibility helper，推荐形态：
  - `ExecutionProfileCompatibilityDiagnostic` dataclass，字段例如 `profile_id: str`、`model_id: str`、`profile_context_window_class: str`、`model_context_window_tokens: int`、`status: str`、`message: str`。
  - `validate_execution_profile_context_window(profile: ExecutionProfileConfig, model: ModelConfig) -> ExecutionProfileCompatibilityDiagnostic`。
  - 当 `model.context_window_tokens < profile.min_context_window_tokens` 时抛 `RuntimeAssemblySelectionError` 或返回 `status="incompatible"` 并由 Service fail fast；推荐直接抛错，避免 Host 以错误 baseline 打开。
  - 当 profile 为 `256k` 且 model 达到 `1m` class 时允许，但 diagnostic 明确为 conservative，例如 `profile_conservative_for_model`。
  - 当 class 匹配时 diagnostic 为 `compatible`。
  - helper 不得选择替代 profile，不得读取 config catalog 默认 profile，不得 import Service / Host / Engine。
- 在 `dayu/config/execution_profiles.json` 中：
  - 将默认 profile 改为 `standard-256k`，因为当前默认模型 `deepseek-v4-flash` 是 256K class。
  - 新增 `standard-1m`、`wechat-256k`、`wechat-1m`。
  - 可使用 config `extends` 减少重复，但继承解析后每条 profile 必须是完整 typed record。
  - 每条 profile 都必须内嵌完整 `agent_policy`。
  - `standard-1m` / `wechat-1m` 的 `min_context_window_tokens` 使用 `1000000`，`standard-256k` / `wechat-256k` 使用 `262144`。
  - `wechat-*` 可以用更保守的 memory / context policy 或工具截断默认值；若没有已确认业务差异，允许先与 `standard-*` 共享 baseline，但必须保留独立 profile id，避免 Service 未来依赖隐式切换。
- 在 `dayu/service/host_assembly.py` 中：
  - `_select_execution_profile_id` 仍只根据 explicit override 或 `default_execution_profile_id` 选择；不得根据 selected model 改 profile id。
  - `compose_open_host_options` 在 `ordinary_selection` 与 `compactor_selection` 完成后调用 compatibility helper。
  - 对 ordinary model 执行 fail-fast / diagnostic；compactor baseline 如窗口 class 不匹配也应 diagnostic，但是否 fail-fast 以 `min_context_window_tokens` 为准。
  - `ServiceOpenHostAssemblyDiagnostics` 新增 `profile_compatibility: tuple[str, ...]` 或等价字段，记录 ordinary / compactor compatibility status。

Tests:

- `tests/runtime/test_config_loader.py`：
  - 默认 config 加载后包含 `standard-256k`、`standard-1m`、`wechat-256k`、`wechat-1m`。
  - `default_execution_profile_id == "standard-256k"`。
  - context window class 非法被拒绝。
  - `min_context_window_tokens <= 0` 被拒绝。
  - 每个 profile 继承解析后包含完整 `agent_policy`。
- `tests/runtime/test_assembly_helpers.py`：
  - 256K profile + 256K model -> compatible。
  - 1M profile + 256K model -> fail fast。
  - 256K profile + 1M model -> allowed with conservative diagnostic。
  - helper 不返回替代 profile id，不改 input profile。
- `tests/service/test_host_assembly.py`：
  - explicit `execution_profile_id="standard-1m"` + 256K default model fail fast。
  - explicit `execution_profile_id="standard-256k"` + 1M model override succeeds and diagnostics include conservative message。
  - default selection 使用 `default_execution_profile_id`，不按 model context window 自动切换。
  - diagnostics 中 profile id 与 selected model id 均可见。

Validation commands:

```bash
source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py -q
source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
source .venv/bin/activate && python -m pyright dayu/runtime dayu/service tests/runtime tests/service
```

README sync:

- 更新 `dayu/config/README.md`：
  - execution profile id 示例改为 `standard-256k` / `standard-1m` / `wechat-256k` / `wechat-1m`。
  - 说明 `context_window_class` / `min_context_window_tokens` 只用于校验和 diagnostic，不用于自动选择。
  - 说明 Service 必须显式选择 profile。
- `tests/README.md` 若提到 Service assembly / config 分档覆盖，更新测试说明。

Acceptance criteria:

- 默认配置提供四类 profile，且不包含旧 profile id `standard`，除非 review 要求保留为新 schema 下的真实 profile；不得保留仅为兼容旧 id 的 alias。
- Service helper 从不根据 model context 自动切 profile。
- 1M profile + 256K model fail fast；256K profile + 1M model允许但有 diagnostic。
- `dayu.runtime` import boundary 仍通过。

Stop condition:

- 若真实 Service / UI 已依赖旧 profile id `standard` 且当前 phase 无法迁移所有调用点，停下报告 Controller；不得新增 compatibility alias。

### Slice 4: Aggregate Validation / Docs / Residual Sweep

目标：对 P12.3 全量改动做聚合验证、旧字段残留扫描、README 同步和 residual risk 分类，确保 plan 范围内无旧 schema 兼容路径、无 usage config override、无 import boundary 破坏。

Allowed files/modules:

- 只允许修正 Slice 1-3 已触及文件中的遗漏。
- README 按触发规则更新：
  - `dayu/config/README.md`
  - `dayu/host/README.md`
  - `dayu/engine/README.md`
  - `tests/README.md`
  - 根目录 `README.md` / `dayu/README.md` 仅在实际职责命中时更新。
- 不允许新增 production module。

Implementation steps:

- 运行旧字段扫描：

```bash
rg -n "agent_policy_profiles|agent_policy_profile_id|runner_option_hints.*max_tokens|usage_enabled|collect_usage|include_usage|supports_usage" dayu tests docs README.md
```

预期：

- `agent_policy_profiles` / `agent_policy_profile_id` 只能出现在 negative tests、phase plan / review artifact 或历史 discussion 文档中；不得出现在 production schema / default config / README 当前说明中。
- `max_tokens` 可以继续出现在 `RunnerCallOptions` public contract、explicit override tests、OpenAI payload explicit mapping tests；不得出现在 default `models.json`、ConfigLoader runner hint schema、Service default config mapping。
- `include_usage` 只能出现在 Engine OpenAI payload implementation / tests，且受 `stream=True` + `supports_stream_usage=True` 门控；不得出现在 config schema。
- `usage_enabled` / `collect_usage` / `supports_usage` 不得出现在 production config schema 或 docs 当前说明中。

- 运行 JSON 加载 smoke：

```bash
source .venv/bin/activate && python -m json.tool dayu/config/models.json >/dev/null
source .venv/bin/activate && python -m json.tool dayu/config/execution_profiles.json >/dev/null
```

- 运行 focused tests：

```bash
source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_assembly_helpers.py tests/service/test_host_assembly.py -q
source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_context_budget.py -q
source .venv/bin/activate && pytest tests/engine/test_config_models.py tests/engine/runners/openai/test_stream_usage_capability_gating.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_sse_usage_recorded.py -q
source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py tests/engine/test_import_boundary.py tests/engine/test_weak_typing_guard.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
```

- 运行 affected pyright：

```bash
source .venv/bin/activate && python -m pyright dayu/runtime dayu/service dayu/host dayu/engine tests/runtime tests/service tests/host tests/engine
```

- 运行 whitespace check：

```bash
git diff --check
```

README sync:

- `dayu/config/README.md` 必须与新 schema 完全一致。
- `dayu/host/README.md` 必须只写 Host usage observation 与 durable projection 事实，不把 Engine usage parsing 写成 Host 职责。
- `dayu/engine/README.md` 若更新，只写 Engine usage 上报与 `supports_stream_usage` gate；不得出现 Host budget 决策。
- `tests/README.md` 更新 runtime config、Service assembly、Host usage observation 覆盖说明。
- 不写过程状态、未来计划、版本记录。

Acceptance criteria:

- `dayu/config/*.json` 加载成功，无旧 schema 字段。
- Focused tests 全部通过。
- Pyright 无新增或扩散错误。
- `git diff --check` clean。
- README 与当前代码一致，不残留旧术语。
- Implementation report 明确列出 residual risks；所有 residual risk 必须分类为 fixed、later slice、later phase/work unit、existing issue 或 requiring user decision。

Stop condition:

- 若 aggregate validation 发现必须修改禁止 public surface、Engine Agent loop 状态机、Host durable state machine 或真实 Service workflow，停下报告 Controller。

## 8. Review Gates

Plan review 必须重点检查：

- 是否仍把 `docs/host/config-schema-followup-discussion.md` 当设计真源。
- 是否保留旧 schema 兼容读取、旧字段 alias、旧 tests。
- 是否误删 `RunnerCallOptions.max_tokens` public explicit override。
- 是否让 ConfigLoader / runtime assembly import Host / Engine / Service。
- 是否让 usage observation 影响当前 dispatch decision。
- 是否引入 usage config override 或 `supports_usage`。
- 是否让 Service helper 根据 model context window 自动选择 profile。
- Slice 是否过粗，是否把 future Service / UI workflow 接入夹带进本 phase。

Implementation code review 必须重点检查：

- ConfigLoader exact field validation 是否 fail closed。
- Service default RunnerCallOptions path 是否唯一地写 `max_tokens=None`。
- OpenAI payload explicit `max_tokens` override 行为是否仍由 explicit `RunnerCallOptions.max_tokens` 控制。
- Usage projection signal payload 是否 durable、可重放、字段类型稳定，且不影响 Run / Attempt status。
- Context Governance observation helper 是否只产生 calibration / diagnostic data。
- `dayu.runtime` import boundary 是否未破坏。
- README 是否按职责更新，未写未来计划。

## 9. Completion Report Format

Implementation Agent 每个 slice 完成后必须报告：

- Slice id / name。
- Changed files。
- Implemented plan items。
- Tests run and result。
- Pyright command and result。
- README decision。
- Residual risks and classification。
- Stop status：`SLICE_COMPLETE` 或 `BLOCKED`。

Aggregate completion 必须额外报告：

- 旧字段扫描结果。
- `git diff --check` 结果。
- 是否存在 blocking open question。
- 是否触及禁止 public surface。

## 10. Blocking Questions

无 blocking open question。

Non-blocking assumptions:

- `standard-256k` 可作为默认 profile，因为当前默认模型 `deepseek-v4-flash` 的 default config 是 256K class；若 implementation 发现默认模型已变为 1M class，应将 default profile 改为同 class，并在 implementation report 中记录证据。
- `context_window_class` + `min_context_window_tokens` 是足够的 profile compatibility schema；它只服务校验和 diagnostic，不引入自动选择。
- Usage observation durable association 可以承载在 `USAGE_REPORTED` EventLog projection signal payload 内，不需要新 durable table。若 review 证明后续消费无法可靠读取 projection signal，必须停下作为 schema/storage question 交给 Controller。

## 11. 本 plan artifact 验证

本 plan artifact 完成后只需验证：

```bash
git diff --check -- docs/host/phase12-3-config-usage-governance-plan.md
```

本 planning handoff 不运行 implementation tests、不运行 pyright、不修改 source/config/tests、不 commit、不 push。
