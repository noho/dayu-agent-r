# Phase 12.1 Slice 4 implementation artifact

## Gate / Scope

- Gate：Phase 12.1 Slice 4 implementation。
- Slice：Assembly Helpers and Engine Provider Extension Helper。
- Approved plan：`docs/host/phase12-1-runtime-assembly-correction-plan.md`。
- 本次只实现 Slice 4 helper、focused tests、README 同步和本 artifact；未 commit、未 push、未开 PR，未进入其它 gate。

## Dirty worktree 分类

- Out-of-scope pre-existing dirty：`README.md`、`utils/smoke_host_public_multiturn.py`。本 Slice 未接管、未修改、未 revert；Service-like smoke rewrite 明确留给 Slice 5。
- 本 Slice intended edits：
  - `dayu/engine/provider_extensions.py`
  - `dayu/runtime/assembly.py`
  - `dayu/runtime/__init__.py`
  - `tests/engine/test_provider_extension_config_adapter.py`
  - `tests/runtime/test_assembly_helpers.py`
  - `tests/runtime/test_import_boundary.py`
  - `dayu/engine/README.md`
  - `tests/README.md`
  - `docs/reviews/phase12-1-slice4-implementation-codex-20260521.md`
- 未接管范围：Host public contract、Engine loop、Service 公共层、smoke script、根 `README.md`。

## 动机与 root cause 判断

动机成立。直接证据来自设计真源：Phase 12 runtime assembly 的缺口在 Host 外部 typed config / scene / tool / provider DSL 到已冻结 Host / Engine typed input 的装配边界，而不是 Host 生命周期、Host public contract 或 Engine loop 缺陷。因此本 Slice 只补最小 helper，不修改 Host public surface，不把 Service composition helper 放入 `dayu.runtime`。

## Helper placement rationale

- `dayu.runtime.assembly`：只实现层中立能力，包括 typed allowlist override 解析、模型 / runner option hint catalog selection、Agent policy 字段级合并、tool truncation policy default lookup 与 effective spec 补齐。该模块只依赖 `dayu.runtime` typed config / scene output 与更底层 `dayu.contracts`，不 import Host / Engine / Service / UI / Fins，不返回 Host / Engine typed object。
- `dayu.engine.provider_extensions`：负责 JSON DSL 到 `ProviderRequestExtension` typed union 的解析。该 helper 必须 import Engine contract，因此不能放入 `dayu.runtime`。
- 未新增 Service package：当前项目没有真实 Service 公共层，本 Slice 不引入公共业务层；把 `RunnerSpec` / `RunnerCallOptions`、Host policies、Engine `AgentPolicy` 的最终映射留给 Slice 5 smoke-local adapter 或后续真实 Service composition root。

## Implemented items

- Runtime-neutral model / hint selection：
  - `parse_model_runner_hint_override(...)`
  - `select_runner_option_hint(...)`
  - 优先级为 run override > scene hints > execution profile baseline > code default，按字段独立合并。
  - 缺 model / hint 以 `RuntimeAssemblySelectionError` 结构化 fail fast。
- Runtime-neutral typed allowlist merge：
  - `parse_agent_policy_override_config(...)`
  - `merge_agent_policy_config(...)`
  - 未知字段以 `RuntimeAssemblyFieldError` fail fast。
  - 返回 `MergedAgentPolicyConfig` 与 field source diagnostic，不构造 Engine `AgentPolicy`。
- Tool truncation default fill：
  - `tool_truncation_policy_defaults(...)`
  - `effective_tool_truncate_spec_from_policy(...)`
  - policy default limit / ttl 只补齐 declaration 缺省项，不修改 declaration strategy / target。
- Engine provider extension helper：
  - `provider_request_extension_from_json(...)`
  - 未知 type、未知字段、非法枚举、Engine contract 拒绝的字段组合均以 `ProviderExtensionConfigError` fail closed。
- README 同步：
  - `dayu/engine/README.md` 增加 provider extension helper 的稳定说明。
  - `tests/README.md` 增加 runtime assembly helper 与 provider extension adapter 测试事实。
  - `dayu/runtime/__init__.py` 只更新包概览，不做包根 re-export。
  - 未更新根 `README.md`：该文件为 pre-existing dirty，且本 Slice 未改变用户手册入口。

## Provider DSL coverage matrix

| DSL `type` | Engine typed target | 支持字段 | fail-closed 行为 |
| --- | --- | --- | --- |
| `openai_reasoning` | `OpenAIReasoningExtension` | `reasoning_effort` | 未知字段、非法 `OpenAIReasoningEffort` |
| `anthropic_thinking` | `AnthropicThinkingExtension` | `enabled`, `budget_tokens` | 未知字段、非法类型、enabled / budget 组合非法 |
| `deepseek_thinking` | `DeepSeekThinkingExtension` | `enabled`, `reasoning_effort` | 未知字段、非法 `DeepSeekReasoningEffort`、关闭时仍设置 effort |
| `mimo_thinking` | `MimoThinkingExtension` | `enabled` | 未知字段、非法类型 |
| `gemini_thinking` | `GeminiThinkingExtension` | `thinking_budget`, `include_thoughts`, `thinking_level` | 未知字段、非法 `GeminiThinkingLevel`、字段组合非法 |
| `qwen_thinking` | `QwenThinkingExtension` | `enable_thinking`, `thinking_budget` | 未知字段、非法类型、关闭 thinking 时仍设置 budget |

## Validation

- `source .venv/bin/activate && pytest tests/engine/test_provider_extension_config_adapter.py -q`：6 passed。
- `source .venv/bin/activate && pytest tests/runtime/test_assembly_helpers.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`：17 passed。
- `source .venv/bin/activate && python -m pyright dayu/engine dayu/runtime tests/engine tests/runtime`：0 errors, 0 warnings。
- `git diff --check`：pass。

## Residual risk / deferred items

- Service composition helper deferred to Slice 5 /后续真实 Service：本 Slice 未把 runtime config 映射成 `RunnerSpec` / `RunnerCallOptions`，未把 context window 注入 Host policies，未把 merged runtime-neutral agent policy 映射成 Engine `AgentPolicy`。
- `utils/smoke_host_public_multiturn.py` deferred to Slice 5：当前脚本仍是 pre-existing dirty 半成品，本 Slice 不接管。
- Provider DSL helper 已覆盖当前 union；未来新增 `ProviderRequestExtension` 成员时，需要同步扩展 helper、README 与 coverage matrix。

## Stop status

Slice 4 implementation complete，停在 implementation report，等待 Slice 4 code review。

## Fix addendum: controller-accepted findings

### Scope

- Gate：Phase 12.1 Slice 4 code review fix。
- Source adjudication：`docs/reviews/phase12-1-slice4-code-review-controller-adjudication-20260521.md`。
- Accepted findings：
  - P12.1-S4-F1：provider extension contract error wrapping 不一致。
  - P12.1-S4-F2：`assembly.py` fallback mode 双真源。
- Non-goals：未改 Engine loop、Host public contract、Service composition、`README.md`、`utils/smoke_host_public_multiturn.py`；未 commit、未 push、未开 PR。

### Fix status

- P12.1-S4-F1：已修复。
  - `_parse_openai_reasoning` 与 `_parse_mimo_thinking` 现在通过 `_wrap_contract_error` 构造 typed contract。
  - 补充 focused test，模拟未来 OpenAI / MiMo contract `ValueError`，确认统一转换为 `ProviderExtensionConfigError`。
- P12.1-S4-F2：已修复。
  - `_FALLBACK_MODES` 现在从 `SceneAgentFallbackMode` 枚举值派生，不再手写重复字面量。
  - 补充 focused test，确认 runtime override parser 接受全部 scene fallback enum 值。

### Changed files

- `dayu/engine/provider_extensions.py`
- `dayu/runtime/assembly.py`
- `tests/engine/test_provider_extension_config_adapter.py`
- `tests/runtime/test_assembly_helpers.py`
- `docs/reviews/phase12-1-slice4-implementation-codex-20260521.md`

### Validation

- `source .venv/bin/activate && pytest tests/engine/test_provider_extension_config_adapter.py -q`：7 passed。
- `source .venv/bin/activate && pytest tests/runtime/test_assembly_helpers.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`：18 passed。
- `source .venv/bin/activate && python -m pyright dayu/engine dayu/runtime tests/engine tests/runtime`：0 errors, 0 warnings。
- `git diff --check`：pass。

### Docs decision

- 本 fix 只收敛 review findings 的内部一致性，不改变用户入口、公共命令、分层说明或测试手册规则；不需要同步 README。

### Residual risk

- 未新增 residual risk。Provider DSL helper 未来新增 union 成员时仍需同步 helper、README 与测试矩阵，该风险已在原 implementation artifact 中归类为长期维护责任。
