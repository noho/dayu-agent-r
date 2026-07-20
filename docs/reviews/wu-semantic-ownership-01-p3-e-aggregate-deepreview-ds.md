# WU-SEMANTIC-OWNERSHIP-01 P3-E Aggregate Deep Review (AgentDS)

## Scope

- **Mode**: aggregate deepreview over committed implementation range `5c03bfbc..HEAD`
- **Branch**: `phaseflow/host-issues-control`
- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- **Accepted implementation commits**:
  - Plan: `035611c8`
  - S1: `7c8bc0a8`
  - S2: `be4ed91c`
  - S3: `0b92a838`
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Plan**: `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md`
- **Pre-existing validation**: Aggregate pytest `588 passed, 3 warnings`; pyright `0 errors, 0 warnings, 0 informations`; `git diff --check` pass; stale-helper scan classified in aggregate-validation.md

### Included scope

All committed production changes in `dayu/contracts/tool_result.py`, `dayu/host/tool_runtime.py`, `dayu/host/accepted_result_projection.py`, `dayu/service/wait_callback_endpoint.py`, `dayu/service/fins_direct.py`, `dayu/fins/direct_events.py`, `dayu/fins/ingestion_runtime.py`, `dayu/cli/commands/fins.py`, plus all test changes and README updates.

### Excluded scope

Untracked files: `docs/cli_ci.md`, `docs/cli_ci_oracles.json`, `docs/cli_ci_scenarios.json`, `docs/reviews/code-review-20260710-135625.md`, `docs/reviews/code-review-20260710-141049.md`. Uncommitted control-doc/aggregate-validation bookkeeping treated as context only.

### Parallel review coverage

无。本次为单一 reviewer 全量走读。

## Review Method Summary

本 review 沿三条主链路逐一走读：

1. **ToolResult envelope → ToolRuntime → Engine LLM projection**：从 `__post_init__` 判别字段 invariant 出发，跟踪 governance/truncation/accept failure 的 hint 清理路径，验证 `last_error_code` 从 hint 迁移到 message/diagnostics 的完整性，确认 Engine `_project_tool_failure_for_llm` 的消费行为。
2. **Accepted result durable payload → projection → consumers**：从 `_result_event_payload` / `_result_payload` 的 None 出口审计出发，追踪 `_accepted_status` 对 payload unavailable (`LOST`) 与 typed status missing (`UNKNOWN`) 的分支，确认 `_status_from_raw_outcome` 已删除且 read_api/memory/compact/trace 消费者使用共享 projection。
3. **Fins direct stream producer → runtime → Service → CLI**：从 `_DirectStreamProducerDone` sentinel 的 finally 保证出发，追踪 runtime 的 RESULT buffering/duplicate detection、Service `_ensure_result_event` 的 fail-closed 行为、CLI `FinsDirectStreamContractViolation` 的删除与 `FinsDirectStreamProtocolError` 的统一渲染。

每条链路均执行了 adversarial failure pass：缺失必填字段、类型错误、空/空白值、重复终态、静默结束、payload 损坏、消费者降级路径。project constraints（semantic owner boundary、LLM-facing text、layering、strict typing、docstrings）作为审查基线。

## Findings

未发现实质性问题。

经逐链路走读与 adversarial failure pass，P3-E 实现范围内的所有关键语义所有权边界均已正确收束：

- **ToolResult 判别字段**：`ToolResultSuccess.__post_init__` 和 `ToolResultFailure.__post_init__` 在构造时 enforce `ok is True` / `ok is False`（`dayu/contracts/tool_result.py:83,113`）。测试覆盖了通过 `cast` 绕过静态类型的运行时构造（`tests/contracts/test_tool_result_envelope.py`）。

- **ToolRuntime hint 清理**：`_truncation_failure`（`dayu/host/tool_runtime.py:7443`）、`_governed_failure_outcome`（`:7466`）、`_accept_failure_outcome`（`:7482`）、`_awaiting_accept_failure_outcome`（`:7498`）均设置 `hint=None`。`_hint_with_diagnostic_refs` 与三个 hint-format 常量（`_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`、`_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`、`_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR`）已删除。九个 truncation reason 常量（`_TRUNCATION_UNSUPPORTED_REASON` 等）已删除。16 处测试断言验证了 `hint is None`，business-authored hints（`"retry with a narrower filing range"`）保留不变。

- **`last_error_code` 保留路径**：`_accept_timeout_message`（`:7523`）将 `last_error_code` 编码为 `f"{message} (last_error_code={last_error_code})"` 放入 `ToolResultFailure.message`。该 message 经 Engine `_project_tool_failure_for_llm`（`dayu/engine/agent.py:442`）投影到 LLM。此行为由 Plan S1 显式授权。`last_error_code` 同时保留在 `ToolFactRejectedAck` / `ToolFactAcceptTimedOut` 的 owner-owned diagnostics 中。

- **Wait callback provider_status_ref**：`_provider_status_ref_from_json`（`dayu/service/wait_callback_endpoint.py:542`）已删除裸字符串分支。非 None 值必须通过 `_require_json_object` 校验；只接受 typed object shape（`adapter_key`、`status_ref`、可选 `status_digest`）。测试覆盖了 malformed_payload 拒绝路径（`tests/service/test_wait_callback_endpoint.py`）。

- **Accepted result status**：`_accepted_status`（`dayu/host/accepted_result_projection.py:391`）只从 typed durable 字段（`resolution_kind` → `tool_fact_kind`）派生状态。`_status_from_raw_outcome` 已删除。payload unavailable 诊断（`result_payload_unavailable` / `event_payload_unavailable`）映射为 `LOST`；typed status 缺失/空白/未知值映射为 `UNKNOWN` 并附加 `accepted_status_unavailable` 诊断。`_payload_status_text`（`:441`）对缺失/非字符串/空白返回 `None`。raw outcome 仅用于 `_result_details_text` 抽取业务摘要。测试覆盖：`tool_fact_kind=None` + raw `ok:False` → `UNKNOWN`（`:798`）、空白 `resolution_kind` → `UNKNOWN`（`:282`）、descriptor 不可用 → `LOST`（`:604`）、EventLog payload 非 object → `LOST`（`:700`）。

- **消费者传播**：`read_api` 将非 `COMPLETED`/非 `CANCELLED` 状态统一映射为 `FAILED` activity（`dayu/host/read_api.py:1293-1297`），`UNKNOWN` 和 `LOST` 均落入此 catch-all——fail-closed，未从 raw outcome 重建状态。memory / compact material 通过 `AcceptedToolResultProjection.status` 字段消费状态（经 `ToolTraceProjectionConsumer` 和 `_memory_projection_event_from_view`），不直接分支于具体状态值。跨消费者一致性测试（`test_same_accepted_result_has_equivalent_consumer_projection`）验证了 trace/memory/compact/run_input 四条路径均使用共享 projection 的同一 `query_text`、`source_text`、`result_text` 和 `result_status`。

- **Fins direct stream 协议错误**：`FinsDirectStreamProtocolError`（`dayu/fins/direct_events.py:88`）是 shared typed protocol error。`FinsDirectStreamProtocolErrorKind` 定义 `MISSING_RESULT` / `DUPLICATE_RESULT`。构造时校验 enum 类型与非空 message。

  - **Runtime**：`_run_direct_stream`（`dayu/fins/ingestion_runtime.py:2645`）缓冲首个 `RESULT`，继续 drain 至 `_DirectStreamProducerDone`，重复 `RESULT` 抛 `DUPLICATE_RESULT`，无 `RESULT` 抛 `MISSING_RESULT`。`_direct_missing_result_event` 已删除。`_DirectStreamProducerDone` 在 `_run_direct_stream_producer` 的 `finally` 块中保证发射（`:2762`），覆盖正常完成、异常转 failure RESULT 后完成、以及 queue fallback（`:4543`）。Business failure `RESULT` 仍然正常通过（exception 在 producer 中被转为 `RESULT(status=FAILURE)` 后 sentinel 仍正常发射）。

  - **Service**：`_ensure_result_event`（`dayu/service/fins_direct.py:475`）对重复 `RESULT` 抛 `DUPLICATE_RESULT`，对缺失 `RESULT` 抛 `MISSING_RESULT`。`_missing_result_event` 已删除。

  - **CLI**：`FinsDirectStreamContractViolation` 已删除。`run_fins_direct_command` 捕获 `FinsDirectStreamProtocolError` 并渲染 `exc.message`（`dayu/cli/commands/fins.py:283-285`）。`_consume_fins_direct_events` 保留防御性 fallback raise（`:767`），注释标明仅兜底 mocked/截断流。CLI 测试验证 protocol error 渲染不包含 "Fins failure" 等伪造业务结果文本（`tests/cli/test_fins_commands.py:881,905`）。

- **README 同步**：`dayu/fins/README.md` 更新 direct stream 段为 "抛出 `FinsDirectStreamProtocolError`，不得合成业务 failure result"。`dayu/service/README.md` 更新为 "Service 会抛出 `FinsDirectStreamProtocolError`"。`tests/README.md` 更新为 "Service direct stream typed protocol error" 和 "裸字符串 provider_status_ref 拒绝"。更新内容与实现一致。

所有 stale-helper/protocol 扫描零命中（`_status_from_raw_outcome`、`_direct_missing_result_event`、`_missing_result_event`、`diagnostic_refs=.*hint`、`accept_rejected:`、`_hint_with_diagnostic_refs`、`FinsDirectStreamContractViolation`）。

## Open Questions

### OQ-01: `_accept_timeout_message` 中 `last_error_code` 的 LLM-facing 暴露格式

- **位置**：`dayu/host/tool_runtime.py:7523-7533` → Engine `_project_tool_failure_for_llm`（`dayu/engine/agent.py:442`）→ LLM tool message
- **触发条件**：accept timeout / ack-lost 路径产生 `last_error_code="accept_ack_lost"` 或 `"accept_timeout"`
- **当前行为**：`message` 格式为 `"tool accept ack timed out (last_error_code=accept_ack_lost)"`，该文本被 Engine 原样投影到 LLM 的 tool message 中
- **Plan 授权**：Plan S1 显式允许 `last_error_code` 保留在 `message` 中
- **CLAUDE.md 约束**："内部治理标识如 label、id、ref、digest、cursor 只有任务必须引用时才可暴露；暴露时必须说明它只是引用标签，不是业务事实或推理依据"
- **分析**：当前格式 `(last_error_code=accept_ack_lost)` 未附带"这只是引用标签"的说明。但该代码出现在完整的 human-readable 失败消息末尾、以括号标注，LLM 误将其当作业务事实推理的风险较低。Plan 已授权此行为，且 P3-E 的语义所有权目标（治理码不进入 hint）已达成。
- **建议**：不在本 WU 修改。若后续发现 LLM 确实尝试推理 `last_error_code` 值，可在 Engine projection 层或 ToolRuntime message 构造时增加一行说明（如 "这是内部诊断标签，不影响工具结果"）。当前实现符合 Plan 要求且风险可控。

### OQ-02: CLI `_consume_fins_direct_events` 的防御性 fallback raise

- **位置**：`dayu/cli/commands/fins.py:767-772`
- **触发条件**：Service stream 正常结束但未产出 RESULT，且 Service 层未先抛 `FinsDirectStreamProtocolError`
- **当前行为**：CLI 自己 raise `FinsDirectStreamProtocolError(MISSING_RESULT, ...)`
- **分析**：在正常生产路径中，Service 的 `_ensure_result_event` 会先抛同一 typed protocol error，CLI 的 fallback 不可达。该 fallback 仅对 mocked/截断 stream 生效，属于防御性设计。它使用同一 `FinsDirectStreamProtocolError` 类型，不引入第二套协议异常。不是语义所有权问题。
- **建议**：保持现状。如果未来确认该路径在测试中也不可达，可删除并简化。

## Residual Risk

### RR-01: `UNKNOWN` accepted status 在下游消费者中的长尾覆盖

- `AcceptedToolResultStatus.UNKNOWN` 是 P3-E 新增的封闭状态值。`read_api` 将其 catch-all 映射为 `FAILED`（安全）。memory、compact material 和 trace 消费者通过 projection 字段（`status`、`llm_material`、`result_text`）间接消费，不显式分支于具体状态值。
- 若未来新增消费者显式 match `AcceptedToolResultStatus` 各分支但遗漏 `UNKNOWN` / `LOST` case，Python 不会在 exhaustiveness check 中告警（`StrEnum` 无 `match` exhaustiveness）。
- **缓解**：当前所有已知消费者均不执行 exhaustive match；`read_api` 的 if-elif-else 已覆盖所有非 `COMPLETED`/非 `CANCELLED` 状态。风险较低。

### RR-02: S3 delayed RESULT buffering 对 producer 生命周期 bug 的敏感性

- Runtime 现在延迟 yield terminal `RESULT` 直到 `_DirectStreamProducerDone` sentinel。如果 producer 在 emit `RESULT` 后挂起（不死、不异常、不返回），runtime 的 `while True` drain 循环会永久阻塞在 `_direct_queue_get`。
- `_DirectStreamProducerDone` 在 `finally` 中保证发射，覆盖了 producer 正常返回和异常路径。但如果 producer 自身永不返回且不抛异常（例如死循环、死锁），sentinel 永远不会入队。
- **缓解**：现有 producer 均为同步有限步骤实现（download/preprocess/upload），不存在无限循环。no-hang 测试 `test_direct_stream_drains_to_done_before_yielding_result` 验证正常路径不挂起。Plan 已将此类风险明确分配给 Fins runtime owner（"future producer lifecycle bugs should surface at the runtime owner"）。
- **建议**：在后续 WU 中为 `_direct_queue_get` 增加可配置的整体超时（区别于当前 0.5s poll 超时），超时后 raise `FinsDirectStreamProtocolError` 并标记 producer thread 为 abandoned。当前不作为 P3-E finding。

### RR-03: Aggregate deepreview 未覆盖的区域

- Engine projection layer（`dayu/engine/agent.py`）仅作为消费端证据读取，未逐函数走读 Engine 完整状态机。
- `dayu/host/tool_runtime.py` 的完整 state machine（~7500 行）中，本 review 聚焦于 hint 清理路径和 truncation/accept/governance failure 出口，未逐路径走读 duplicate governance、awaiting activation、wait-resume 等非 P3-E 改动区域。
- P3-E 不关闭 umbrella WU-SEMANTIC-OWNERSHIP-01；后续 WU 的 aggregate deepreview 应覆盖本次未 review 的区域。
