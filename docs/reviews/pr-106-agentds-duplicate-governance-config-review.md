# Code Review

## Scope

- Mode: PR
- PR: #106 — "Host duplicate governance attempt scope"
- Author: noho
- Head: fix/wu-tool-01-attempt-scoped-duplicate-governance
- Base: main
- Output file: docs/reviews/pr-106-agentds-duplicate-governance-config-review.md
- Included scope:
  - `dayu/config/execution_profiles.json` — tool_duplicate_governance_policy 字段
  - `dayu/runtime/config_loader.py` — typed config schema（`ToolDuplicateGovernancePolicyConfig`, `ToolDuplicateGovernanceMessagesConfig` 及解析函数）
  - `dayu/service/host_assembly.py` — `_duplicate_governance_policy_from_config` 及 `_tooling_options_from_discovery` 映射
  - `dayu/host/tool_duplicate_governance.py` — Host typed contracts（`DuplicateGovernancePolicy`, `DuplicateGovernanceMessages`, `InMemoryAttemptDuplicateGovernance`）
  - `dayu/host/tooling.py` — `HostToolingOptions.duplicate_governance_policy` 字段与校验
  - `dayu/host/dispatch.py` — dispatch 中 `duplicate_governance_policy` 传入 ToolRuntime factory
  - `dayu/host/tool_runtime.py` — `InMemoryAttemptDuplicateGovernance` 创建与 `ToolRuntimeExecutor` 集成
  - `utils/smoke_host_public_diagnostics.py` — duplicate governance 诊断打印
  - `tests/runtime/test_config_loader.py` — config loader 测试（duplicate governance 部分）
  - `tests/service/test_host_assembly.py` — Service assembly 测试（`test_tool_duplicate_governance_policy_is_derived_from_execution_profile`）
  - `tests/host/test_toolruntime_duplicate_governance.py` — Host ToolRuntime duplicate governance 测试
  - `tests/host/test_tooling_options.py` — HostToolingOptions 测试
  - `dayu/config/README.md` — 配置说明更新
- Excluded scope:
  - `dayu/host/tool_duplicate_governance.py` 中 `InMemoryAttemptDuplicateGovernance` 的并发正确性（已有专项 review）
  - `dayu/host/tool_runtime.py` 的 accept barrier 集成（不在本次 follow-up scope）
  - 历史 review artifacts（`docs/reviews/wu-tool-01-*.md`）——本次不重新 review 已裁定的 findings
  - UI 层、Engine 层、Fins 层
- Parallel review coverage: 无——本次 scope 集中，单 reviewer 沿数据流走读即可覆盖。

## Findings

## Controller Follow-up Resolution

- Finding 1 已处理：Service helper 改为接收 `ToolDuplicateGovernancePolicyConfig`，并且只在非空工具 bundle 分支内构造 Host `DuplicateGovernancePolicy`。
- Finding 2 已处理：`DuplicateGovernanceMessages.message_for` 现在显式处理 `DuplicateDecisionKind.DURABLE_MISSING`，未知决策类型会 fail fast。
- 补充验证：`pytest tests/runtime/test_config_loader.py tests/service/test_host_assembly.py tests/host/test_tooling_options.py tests/runtime/test_smoke_host_public_multiturn_assembly.py` 通过，`pyright` 0 errors。

### 1-未修复-低-Empty tool bundle 场景下 duplicate governance policy 被静默丢弃

- **入口/函数**: `_compose_options` → `_tooling_options_from_discovery`
- **文件(行号)**: `dayu/service/host_assembly.py:1017-1041`, `dayu/service/host_assembly.py:462-470`
- **输入场景**: `tool_bundle.definitions` 为空（即没有业务工具被发现或配置），但 execution profile 中配置了 `tool_duplicate_governance_policy`
- **实际分支**: `_tooling_options_from_discovery` 在 `not tool_bundle.definitions` 时直接返回 `None`（第 1032-1033 行），丢弃了传入的 `duplicate_governance_policy` 参数
- **预期行为**: 无工具时无需 duplicate governance 治理，丢弃 policy 是合理的；但 `_duplicate_governance_policy_from_config` 仍然在 `_compose_options` 中被调用（第 465-468 行），意味着该调用做了无用功
- **实际行为**: `_compose_options` 总是计算 `_duplicate_governance_policy_from_config()`，但在空工具场景下其结果被丢弃。这不会导致行为错误（无工具即无治理），但存在轻微浪费和代码意图不清的问题
- **直接证据**: `host_assembly.py:462-470` 总是调用 `_duplicate_governance_policy_from_config`；`host_assembly.py:1032-1033` 在 `not tool_bundle.definitions` 时直接 `return None`
- **影响**: 仅代码意图清晰度，无运行时行为错误。注意：无效配置仍会被 fail-fast（因为 `_duplicate_governance_policy_from_config` 无论如何都会执行），所以不良配置不会被静默吞没
- **建议改法和验证点**: 考虑在 `_compose_options` 中仅在 `effective_tool_bundle.definitions` 非空时才计算 policy（lazy evaluation），或在 docstring 中明确此路径的语义。当前行为可接受，不建议为美观增加条件分支
- **修复风险（低）**:
- **严重程度（低）**:

### 2-未修复-低-`duplicate_missing` 决策不在配置 allowlist 中但 `message_for` 通过隐式 else 分支映射

- **入口/函数**: `DuplicateGovernanceMessages.message_for`
- **文件(行号)**: `dayu/host/tool_duplicate_governance.py:119-136`
- **输入场景**: 调用 `message_for(DuplicateDecisionKind.DURABLE_MISSING)`
- **实际分支**: `kind is DuplicateDecisionKind.ALLOW` → `kind is DuplicateDecisionKind.REUSE` → ... → `return self.prior_accept_missing`（else 分支）
- **预期行为**: `DURABLE_MISSING` 是运行时产生的决策，不由用户配置。预期应返回 `prior_accept_missing` 消息，当前 else 恰好做了正确的事
- **实际行为**: 通过 if-elif 链的缺省 else 返回 `prior_accept_missing`，而非显式映射 `DURABLE_MISSING`。如果未来新增决策类型且未更新此方法，可能意外落入 else 分支
- **直接证据**: `tool_duplicate_governance.py:126-136`——缺少显式 `if kind is DuplicateDecisionKind.DURABLE_MISSING` 分支
- **影响**: 当前无实际行为错误；未来新增 DuplicateDecisionKind 值时有引入静默错误映射的回归风险
- **建议改法和验证点**: 将 else 改为显式 `elif kind is DuplicateDecisionKind.DURABLE_MISSING`，然后 else 改为 `raise ValueError(...)` fail-fast
- **修复风险（低）**:
- **严重程度（低）**:

## Open Questions

1. **`DURABLE_MISSING` 消息映射是否正确**：当前 `message_for(DURABLE_MISSING)` 返回 `prior_accept_missing`。此决策由 `InMemoryAttemptDuplicateGovernance.decide_duplicate` 在 `DURABLE_MISSING` 分支中显式构造 `DuplicateDecision` 时同时使用 `message=self._policy.messages.prior_accept_missing` 和 `diagnostic_message=self._policy.messages.prior_accept_missing`（`tool_duplicate_governance.py:414-424`）。而 `_decision_for_accepted_entry`（第 467-498 行）的 `decision is DURABLE_MISSING` 路径不可达（因为调用者已提前处理）。`message_for` 的隐式映射与此处的显式赋值一致，但语义上 `DURABLE_MISSING` 和"prior accept missing"不完全是同一概念——两者分别用于"需要显式消息"和"缺省诊断"场景。建议确认两者是否需要不同消息。

2. **workspace overlay 只替换整条 record 的行为对 messages 的影响**：当前 workspace overlay 不支持 messages 子字段的 partial merge。如果用户只希望修改 `hard_stop` 消息为中文，也必须复制全部 7 条消息。这是故意的 design choice（JSON 层不做 deep merge），但文档中建议明确说明此限制。

## Residual Risk

- **全链路集成测试缺失**：当前测试覆盖了 ConfigLoader → Service assembly 的映射正确性（`test_tool_duplicate_governance_policy_is_derived_from_execution_profile`），以及 Host 层 `InMemoryAttemptDuplicateGovernance` 的单元行为。但缺少从配置加载到 Host ToolRuntime 执行期的端到端集成测试（config → assembly → dispatch → ToolRuntime → decide_duplicate → record_accepted）。当前测试通过 `_write_execution_profile_overlay` 直接构造 JSON fixture 绕过 ConfigLoader，未验证真实 `execution_profiles.json` 的完整 JSON 到 typed policy 的往返。
- **Smoke diagnostics 仅打印 default 和 per-tool 摘要**：`utils/smoke_host_public_diagnostics.py` 打印了 `default_duplicate_decision`、`decisions_by_tool_name`、`justification_argument_names_by_tool_name` 和 `messages.hint`，但未打印完整的 messages 校验（如所有 7 条消息是否存在且非空）。如果 workspace overlay 写入了不完整的 messages，此问题只能在执行期暴露。
- **`HostToolingOptions.__post_init__` 不校验 `decisions_by_tool_name` 的工具名是否对应实际已发现的工具**：配置可以写入不存在工具名的决策覆盖，会永远不生效且不报警。这一行为与 codebase 的 fail-fast 原则不完全一致，但工具发现的完整集合在 ConfigLoader 加载时未知（ToolsDiscovery 在 Service assembly 阶段才执行），所以 ConfigLoader 层无法做此校验。
- **`_require_exact_fields` 的防御性覆盖已充分**：在 execution profile 级别和 `tool_duplicate_governance_policy` 子对象级别均使用 `_require_exact_fields`；`_TOOL_DUPLICATE_GOVERNANCE_DECISIONS` frozenset 对所有决策字符串做闭集校验；`_parse_tool_duplicate_decision_mapping` 拒绝空工具名；`_require_str_field` 拒绝对空消息字符串。以下路径均已覆盖 fail-fast：
  - `execution_profiles.json` 顶层 unknown field → `ConfigFieldError`
  - `tool_duplicate_governance_policy` unknown field → `ConfigFieldError`
  - `messages` unknown field → `ConfigFieldError`
  - `decisions_by_tool_name` 空 key → `ConfigFieldError`
  - `decisions_by_tool_name` 非法值（如 `"retry"`）→ `ConfigFieldError`（测试覆盖：`test_tool_duplicate_governance_unknown_decision_fails_fast`）
  - `default_duplicate_decision` 非法值 → `ConfigFieldError`

- **pyright 与测试均通过**：105 个相关测试全部通过，pyright 在 `config_loader.py`、`host_assembly.py`、`tool_duplicate_governance.py`、`tooling.py` 上 0 errors 0 warnings。
