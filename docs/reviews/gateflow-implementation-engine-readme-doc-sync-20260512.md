# Gateflow Implementation Artifact: Engine README Doc Sync

- **work gate name**: implementation
- **work-unit name**: 将 Engine 文档对齐到当前代码，以代码为准
- **assigned slice id**: engine-readme-doc-sync
- **approved plan path**: 无；用户最新指令明确跳过 plan，直接进入 implementation handoff
- **artifact path**: `docs/reviews/gateflow-implementation-engine-readme-doc-sync-20260512.md`

## Assigned Scope

- **允许修改的目标文件**: `dayu/engine/README.md`
- **允许写入的 artifact 文件**: `docs/reviews/gateflow-implementation-engine-readme-doc-sync-20260512.md`
- **显式非目标**:
  - 不修改 `docs/engine/design.md`
  - 不修改代码
  - 不修改测试
  - 不新增未来设计
  - 不写过程状态
  - 不越过 `dayu/engine/README.md` 的 Engine 开发手册职责边界

## Direct Evidence

1. `dayu/engine/__init__.py` 包根导出 `ProviderRequestExtension`、各 provider extension 类型、`RunnerHTTPErrorCode`、`RunnerSpec`、`RunnerCallOptions` 等公共契约；`tests/engine/test_package_exports.py` 用严格集合锁定这些导出。
2. `dayu/engine/contracts/runner_spec.py` 定义 `ProviderRequestExtension` 封闭联合，成员为 `OpenAIReasoningExtension`、`AnthropicThinkingExtension`、`DeepSeekThinkingExtension`、`MimoThinkingExtension`、`GeminiThinkingExtension`、`QwenThinkingExtension`。
3. `dayu/engine/contracts/runner_spec.py` 的 `RunnerSpec.__post_init__` 校验 `stream_idle_timeout_seconds` 与 `stream_idle_heartbeat_seconds`：heartbeat 依赖 timeout，二者必须为正数，heartbeat 不得大于 timeout；`tests/engine/contracts/test_runner_spec.py` 覆盖这些字段集合与失败路径。
4. `dayu/engine/runners/openai/payload.py` 只在 `RunnerCallOptions.stream=True` 且 `RunnerSpec.supports_stream_usage=True` 时写入 `stream_options.include_usage=True`；`tests/engine/runners/openai/test_stream_usage_capability_gating.py` 覆盖正反路径。
5. `dayu/engine/contracts/runner_events.py` 定义 `RunnerHTTPErrorCode` 枚举成员：`rate_limit_exceeded`、`server_error`、`client_error`、`network_error`、`timeout`、`context_length_exceeded`、`unknown_http_status`；`tests/engine/contracts/test_runner_events.py` 和 OpenAI runner HTTP error 测试覆盖这些成员。
6. `dayu/engine/agent.py` 在 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` 分支提升 `context_compaction_requested`，并设置可恢复 `run_failed(context_compaction_required)` 候选。
7. `dayu/engine/agent.py` 的挂起路径由私有 `_AsyncAgent` 实现，公共 README 执行路径中残留的 `AsyncAgent emits` 容易被误读为公共或旧实现名；包根测试明确禁止导出 `AsyncAgent` / `_AsyncAgent`。

## Implemented Items

- 在 `dayu/engine/README.md` 的 Runner 接口说明中补充 `RunnerSpec.provider_request` 的当前封闭联合成员，并说明显式调用参数只进入 `RunnerCallOptions`。
- 在 `dayu/engine/README.md` 的 Runner 接口说明中补充 `supports_stream_usage` 对 `stream_options.include_usage=True` 的门控语义，以及 SSE idle timeout / heartbeat 的公共校验约束。
- 在 `dayu/engine/README.md` 的公共契约说明中补充 `RunnerHTTPErrorCode` 当前成员，并说明 `context_length_exceeded` 在 Agent 提升阶段对应 `context_compaction_requested` 与可恢复失败。
- 将执行路径中的 `AsyncAgent emits` 改为中性的 `emit`，避免 README 暗示不存在的公共 `AsyncAgent` 接口。

## Not Implemented

- 未修改 `docs/engine/design.md`：该文件不在本 handoff 的 allowed target file 内；当前工作区中它已有 dirty change，但本 slice 未触碰。
- 未新增或修改测试：本次只更新 README，现有 `tests/engine` 已覆盖本次补充的契约事实。
- 未修改代码：直接证据显示问题是 README 表述缺失或旧称残留，不是实现错误。

## Validation

1. `source .venv/bin/activate && python -m pytest tests/engine -q`
   - 结果：通过
   - 输出摘要：`303 passed in 1.11s`
2. `source .venv/bin/activate && pyright dayu/engine tests/engine`
   - 结果：通过
   - 输出摘要：`0 errors, 0 warnings, 0 informations`

## Documentation Decision

- 已更新 `dayu/engine/README.md`，因为本 slice 命中 `dayu/engine/` README 职责，且变更内容属于 Engine 公共契约、事件流与关键机制说明。
- 未更新根 README、`dayu/README.md` 或其它包 README，因为本 slice 未改变项目级使用方式、分层装配关系或其它包职责。

## Plan Gaps Or Controller Decisions

- 用户最新指令明确取消 plan artifact 工作并要求直接修改，因此本 artifact 记录 `approved plan path` 为无。
- 未发现需要 controller 即刻裁决的 blocker。

## Residual Risks And Uncovered Areas

- **已在当前 slice 修复**: `dayu/engine/README.md` 对 provider extension、stream usage/idle、Runner HTTP error 枚举和 `AsyncAgent` 残留称谓的对齐问题。
- **accepted as covered by a later slice in the approved plan**: `docs/engine/design.md` 的对齐工作由另一个 slice / Agent 负责；本 slice 不修改。
- **assigned to a later phase or work unit**: 无。
- **tracked by an existing issue**: 无。
- **requiring a new issue or explicit user decision**: 无。

## Completion Signal

- `dayu/engine/README.md` 已按当前代码和测试锁定契约完成对齐。
- 验证命令已通过。
- 未触碰非目标文件。

## Stop Condition Status

- 当前 assigned slice 已达到停止条件：目标 README 和 artifact 已写入，验证已完成。
- 不阻止另一个 slice 启动。
