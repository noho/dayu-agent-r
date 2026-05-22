# Phase 12.3 Plan Review — AgentMiMo

review Agent：AgentMiMo
review 日期：2026-05-22
review 对象：`docs/host/phase12-3-config-usage-governance-plan.md`
设计真源：`docs/host/design.md`
总控文档：`docs/host/implementation-control.md`
辅助讨论稿：`docs/host/config-schema-followup-discussion.md`（仅用于背景核对）

## Verdict

**PASS_WITH_FINDINGS**

blocking findings: 0
non-blocking observations: 7

## Review 方法

逐项对照 design.md §3、§10.1、§11、§25 与 implementation-control.md Phase 12.3 目标、范围、禁止项和退出条件，结合当前实现状态（`dayu/config/*.json`、`dayu/runtime/config_loader.py`、`dayu/service/host_assembly.py`、`dayu/host/engine_ingest.py`、`dayu/host/context_budget.py`、`tests/host/test_engine_ingest_mapping.py`）做 adversarial check。

## 1. 设计对齐检查

### 1.1 agent_policy_profiles 删除

- design.md §3: `execution_profiles.json` 不保留顶层 `agent_policy_profiles` catalog、`agent_policy_profile_id`。
- implementation-control.md L1846: 删除顶层 `agent_policy_profiles` catalog，删除 `execution_profiles[*].agent_policy_profile_id`，每个 execution profile 直接内嵌完整 `agent_policy` block。
- plan Slice 1: 明确删除 `AgentPolicyProfileConfig`、`ExecutionProfilesConfig.agent_policy_profiles`、`ExecutionProfileConfig.agent_policy_profile_id`，新增 `AgentPolicyConfig` 并内嵌到 `ExecutionProfileConfig.agent_policy`。
- 当前实现证据：`execution_profiles.json` 仍有顶层 `agent_policy_profiles`（L60-71）与 `agent_policy_profile_id`（L57）；`config_loader.py` 仍有 `AgentPolicyProfileConfig`（L349）、`agent_policy_profile_id`（L345/1274）、`_parse_agent_policy_profile_map`（L1504+）、`_validate_execution_profile_references`（L1852+）；`host_assembly.py` 仍有 `agent_policy_profiles[...]` 查找（L273-274）。

结论：plan 正确对齐设计。动机成立。

### 1.2 默认 max_tokens 删除

- design.md §3: 默认 config 不使用 `max_tokens` 限制模型输出。
- implementation-control.md L1847-1849: 删除 runner option hint `max_tokens`，`RunnerCallOptions.max_tokens` 若保留只能作为显式 per-run / provider adapter override。
- plan Slice 1: `RunnerOptionHintConfig` 删除 `max_tokens`，`_runner_options_from_hint` 返回 `max_tokens=None`，保留 public contract 与 explicit override 测试。
- 当前实现证据：`models.json` 每个 runner option hint 均含 `max_tokens: 4096`（L29/35/41/47/53/59+）；`config_loader.py` 的 `RunnerOptionHintConfig.max_tokens`（L104）、`_parse_runner_option_hint` 允许 `max_tokens`（L1167/1172）；`host_assembly.py` 的 `_runner_options_from_hint` 映射 `hint.max_tokens`（L757）。

结论：plan 正确对齐设计。max_tokens public contract 保留，只切断默认 config 来源。

### 1.3 usage observation 消费

- design.md §3 L95: usage 是 provider capability 驱动的治理观测信号。Engine 只如实上报。Host ingest durable 化 `usage_reported` 并保留 attempt / execution context、估算 digest、policy ref。Context Governance 可主动消费，但 usage 是 post-call observation，不回头修改 dispatch decision。不提供 config override。
- design.md §25 L2633: 第一版只记录 usage observation 与 estimator calibration diagnostic，不根据 usage 自动动态调整 policy threshold。
- implementation-control.md L1850-1853: Engine 继续只负责如实上报 usage；Host ingest 补齐关联信息；Context Governance 主动消费但不回改 dispatch decision；usage 缺失不得导致 Run 失败。
- plan Slice 2: 不修改 Engine `UsageReportedData`；在 `_append_projection_signal` payload 新增 `session_id`、`run_id`、`provider_request_id`、`policy_ref`、`estimator_digest`、`estimated_input_tokens`、`usage_observation_status`、`usage_observation_digest`。usage 缺失或异常不导致 Run 失败。
- 当前实现证据：`engine_ingest.py` 的 `_append_usage_reported`（L2025-2057）payload 只含 `attempt_id`、`execution_id`、`iteration_id`、`prompt_tokens`、`completion_tokens`、`total_tokens`，不含 `policy_ref` / `estimator_digest`。`test_engine_ingest_mapping.py::test_usage_reported_is_projection_signal_without_state_change`（L1034）断言 `"policy_ref" not in payload` 和 `"estimator_digest" not in payload`。`context_budget.py` 的 `UsageObservation`（L225）已有 `session_id`、`run_id`、`provider_request_id`、`estimator_digest`、`policy_ref` 等字段。

结论：plan 正确对齐设计。Engine contract 不变，只扩展 Host 侧 durable projection signal payload。

### 1.4 execution profile 显式分档

- design.md §3 L91: execution profile 选择是 Service / composition root 的显式业务决策，不由 helper 根据 `models.context_window_tokens` 隐式切换。profile 可增加 `context_window_class` 或 `min_context_window_tokens` 用于校验。
- implementation-control.md L1854: `execution_profiles.json` 支持按场景显式分档，例如 `standard-256k`、`standard-1m`、`wechat-256k`、`wechat-1m`。Service 显式选择，helper 只做兼容性校验和 diagnostic。
- plan Slice 3: 新增 `context_window_class` 与 `min_context_window_tokens`，只用于校验和 diagnostic。Service helper 不自动切换。四类 profile 分档。
- 当前实现证据：`execution_profiles.json` 只有一个 profile `standard`（L4），无分档概念。

结论：plan 正确对齐设计。

### 1.5 import boundary

- design.md §3 L65-67: `dayu.runtime` 不得 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。
- implementation-control.md L1820: 保持 `dayu.runtime` import boundary。
- plan §5 Import Boundary: 完整列出每层 import 约束。`config_loader` 不构造 Host / Engine typed object；`assembly` 不 import Host / Engine public contracts。

结论：plan 正确对齐设计。

### 1.6 禁止项检查

| 禁止项（implementation-control.md L1838-1843） | plan 是否遵守 |
|---|---|
| 不实现真实 Service / CLI / Web / GUI workflow 接入 | 是（§3.2 Non-goals） |
| 不让 ConfigLoader 解析 secret / 创建 provider client / import Engine provider extension typed union | 是（§5 Import Boundary） |
| 不引入 `usage_enabled` / `collect_usage` / `include_usage` config override | 是（§3.2 Non-goals） |
| 不引入独立 `supports_usage` 字段 | 是（§3.2 Non-goals） |
| 不用 post-call usage 回头修改当前已完成的 dispatch decision | 是（§3.1 Slice 2） |

全部遵守。

## 2. Blocking Findings

无 blocking finding。

## 3. Non-blocking Observations

### O1: USAGE_REPORTED payload 新增字段的 session_id / run_id 来源路径需确认

plan Slice 2 要求在 `_append_usage_reported` payload 中新增 `session_id` 和 `run_id`。当前 payload 只从 `context.attempt` 取 `attempt_id` / `execution_id`。

证据：`engine_ingest.py:2047-2053` 当前 payload 结构。

实现时需确认 `_ValidatedCandidate` 或 `HostIngestContext` 是否已有 `session_id` / `run_id` 可直接读取；如果需要额外查找（例如通过 attempt_id 回溯），应评估对 ingest 热路径的开销。plan 假设这些字段在 context 中可得，但未说明具体来源路径。

建议：实现时优先检查 `_ValidatedCandidate` 已有字段；若缺少，通过 attempt 的 durable run row 获取，不引入额外查询。

### O2: estimator_digest 构造依赖 input event 可读性，需确认失败模式覆盖

plan Slice 2 要求 `estimator_digest` 通过 "当前 durable run input event 和当前 policy 重新构造与 pre-dispatch 同源的 conservative estimate"。若 input event 缺失或 payload 不可读，写 `None` 并设置 `usage_observation_status` 为 `estimate_unavailable`。

当前 `test_engine_ingest_mapping.py::test_usage_reported_is_projection_signal_without_state_change`（L1034）使用的 test fixture 并未 seed input event。这意味着实现后该测试需要扩展 fixture 或新增独立测试来覆盖 input event 缺失路径。

建议：plan 的 test section 已提到 "input event 缺失或估算异常时" 的测试（Slice 2 Tests L283），但应确保现有 `test_usage_reported_is_projection_signal_without_state_change` 也被更新，而不是只新增测试。

### O3: context_window_class 使用字符串字面量，后续扩展性有限

plan Slice 3 使用 `context_window_class: str`，只允许 `"256k"` / `"1m"` 两个值。

证据：plan L339: `context_window_class: str`，L345: `校验 context_window_class 只允许 "256k" / "1m"`。

第一版用字符串是合理的（简单、可读），但后续如果增加更多 class（如 `"128k"`、`"2m"`、`"10m"`），字符串校验会膨胀。可考虑后续 phase 将其收敛为 `StrEnum`，与 `_AGENT_FALLBACK_MODES` 的现有模式一致。这不是当前 phase 的 blocker。

### O4: wechat-* profile 当前无业务差异化证据

plan Slice 3 要求新增 `wechat-256k` / `wechat-1m`，并注明 "若没有已确认业务差异，允许先与 `standard-*` 共享 baseline"。

证据：plan L360: `wechat-* 可以用更保守的 memory / context policy 或工具截断默认值；若没有已确认业务差异，允许先与 standard-* 共享 baseline`。

implementation-control.md L1854 也提到这些 profile 名称。但当前项目中没有找到任何 `wechat` 相关的业务需求文档或 scene manifest。这些 profile 在第一版可能只是占位。

建议：实现时明确在 `execution_profiles.json` 注释或 implementation report 中记录 `wechat-*` 当前与 `standard-*` 共享 baseline 的事实，避免后续误以为已有差异化调优。

### O5: Slice 4 聚合验证命令覆盖面可扩展

plan Slice 4 的聚合验证包括旧字段扫描、JSON smoke、focused tests、pyright 和 whitespace check。

证据：plan L432-468。

建议：Slice 4 可额外运行 `pytest tests/host -q` 全量回归，确保 usage payload 变更未影响其他 Host 测试。当前 Slice 4 focused tests 只覆盖 `test_engine_ingest_mapping` 和 `test_context_budget`，但 `_append_usage_reported` 可能被其他 Host smoke 或 integration test 间接调用。

### O6: Slice 2 的 UsageObservationDiagnostic helper 形态未最终确定

plan Slice 2 提到两种实现选择：`UsageObservationDiagnostic` dataclass 或 `Mapping[str, JsonValue]` 的私有 helper。

证据：plan L248-251: "若实现更简单，也可不新增 dataclass，只新增返回 Mapping[str, JsonValue] 的私有 helper"。

两种都可接受，但 implementation agent 需要在实现时做选择并记录。如果选择 Mapping 形态，需确保不违反 "禁止使用 `Any`、无类型参数" 的编码约束（`JsonValue` 已有严格定义，所以 Mapping[str, JsonValue] 是类型安全的）。

### O7: Slice 1 的 stop condition 触发路径值得验证

plan Slice 1 stop condition: "若删除旧 schema 后发现必须修改 Host / Engine public dataclass 字段才能继续，停下报告 Controller"。

证据：plan L223-225。

当前分析表明不需要改 public contract：`AgentPolicy` typed shape 已存在于 Engine / Host，`agent_policy` 内嵌只需对齐已有 shape；`max_tokens` 只从 config 来源删除，`RunnerCallOptions` public field 不变。但实现时如果发现 `AgentPolicyProfileConfig` 与 `AgentPolicy` 之间有未对齐的字段（例如 `fallback_prompt` 默认值来源），应在此 stop condition 下停下，而不是绕过。

## 4. 关键证据索引

| 检查项 | 证据文件 | 行号 |
|---|---|---|
| 旧 agent_policy_profiles 存在 | `dayu/config/execution_profiles.json` | 57, 60-71 |
| 旧 max_tokens 存在 | `dayu/config/models.json` | 29, 35, 41, 47, 53, 59+ |
| ConfigLoader 旧 schema | `dayu/runtime/config_loader.py` | 104, 345, 349, 1167, 1274, 1504 |
| Service 旧查找路径 | `dayu/service/host_assembly.py` | 273-274, 757 |
| USAGE_REPORTED 当前 payload | `dayu/host/engine_ingest.py` | 2047-2053 |
| USAGE_REPORTED 当前测试 | `tests/host/test_engine_ingest_mapping.py` | 1034-1065 |
| UsageObservation 已有字段 | `dayu/host/context_budget.py` | 225-284 |
| design.md §3 usage 设计 | `docs/host/design.md` | 95 |
| design.md §3 execution profile | `docs/host/design.md` | 89-91 |
| design.md §25 usage observation | `docs/host/design.md` | 2623, 2633 |
| implementation-control.md P12.3 | `docs/host/implementation-control.md` | 1813-1889 |

## 5. 结论

plan 完整对齐 design.md 和 implementation-control.md 的 Phase 12.3 目标。四个裁决（agent_policy 内嵌、删除默认 max_tokens、usage post-call observation、execution profile 显式分档）均正确收口为可实施的 slice。无旧 schema 兼容读取、无 RunnerCallOptions.max_tokens 误删、无 import boundary 破坏、无 usage config override、无 execution profile 自动切换。slice 划分合理，file ownership 清晰，测试覆盖要求充分。7 个 non-blocking observations 均为实现细节层面的建议，不阻塞 plan handoff。
