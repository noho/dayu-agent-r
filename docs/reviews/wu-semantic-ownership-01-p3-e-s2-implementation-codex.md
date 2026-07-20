# WU-SEMANTIC-OWNERSHIP-01 P3-E S2 Implementation - AgentCodex

## 状态

ready-for-controller-validation

## 第一性原理 / owner boundary 判断

S2 的问题真实存在，且严重性成立：

- `provider_status_ref` 是外部 callback transport payload 进入 Host typed contract 的边界事实。裸字符串没有携带 `adapter_key`，Service mapper 若自行补成 `callback`，就是在 owner resolver 缺席时伪造 provider status owner 信息。修复点必须在 `dayu.service.wait_callback_endpoint` 的 JSON -> typed envelope 入口校验处，而不是 Host adapter 或下游 resolver。
- accepted result status 的 owner 是 Host accept barrier / wait resolution 写入的 typed payload 字段，例如 `resolution_kind` 与 `tool_fact_kind`。`raw_tool_outcome.kind` / `result.ok` 是工具原始响应，不拥有 accepted-result projection status 语义。下游 Read API、RunInputBuilder、Memory、Compact material 都应消费统一 projection，不能各自从 raw outcome 反推 status。

因此本次修复落在两个真源边界：

- Service callback mapper 拒绝非 object 的 `provider_status_ref`。
- Host accepted-result projection 只从 typed status 字段派生 `AcceptedToolResultStatus`。

## 修改摘要

生产文件：

- `dayu/service/wait_callback_endpoint.py`
  - 删除 `_provider_status_ref_from_json(...)` 对裸字符串 `provider_status_ref` 的兼容分支。
  - 非 `None` 的 `provider_status_ref` 现在必须是 object shape：`adapter_key`、`status_ref`、可选 `status_digest`。

- `dayu/host/accepted_result_projection.py`
  - 删除 `_status_from_raw_outcome(...)`。
  - 删除只服务 raw status fallback 的 `_FIELD_RESULT`、`_FIELD_KIND`、`_FIELD_OK` 常量。
  - `_accepted_status(...)` 不再读取 raw outcome；payload unavailable 诊断映射 `LOST`。
  - payload available 但 typed status 缺失、空白、非法类型或未知值时映射 `UNKNOWN`，并追加 `accepted_status_unavailable`。
  - raw outcome 仍保留用于 `raw_outcome`、`result_text`、`result_details_text`，例如 `reason=not found` 仍可抽取。

测试 / 文档：

- `tests/service/test_wait_callback_endpoint.py`
  - `_lost_body()` 改为 typed object `provider_status_ref`。
  - 新增裸字符串 `provider_status_ref` 返回 `malformed_payload` 且不调用 adapter 的负测。

- `tests/host/test_accepted_result_projection.py`
  - 空白 typed status 不再抛错，改断言 `UNKNOWN + accepted_status_unavailable`。
  - unknown typed status 断言诊断保留。
  - raw `result.ok=false` 断言不再反推 `FAILED`，但仍抽取 `reason=not found`。

- `tests/host/test_resolve_wait_command.py`
  - 将 stale evidence renderer 断言从 `工具：long_tool` 对齐为当前唯一 renderer 输出 `工具名称：long_tool`。

- `tests/README.md`
  - 同步 Service wait callback endpoint 测试覆盖摘要，加入裸字符串 `provider_status_ref` 拒绝覆盖。

## `_result_payload(...)` exit audit

`_result_payload(...)` 当前返回路径：

- `resolved_payload_available=True` 且 `envelope is None`：
  - 返回 fallback payload，诊断 `accepted_evidence_envelope_missing`。
  - payload 本身可用，不属于 unavailable；status 若无 typed 字段则由 `_accepted_status(...)` 映射 `UNKNOWN + accepted_status_unavailable`。

- `resolved_payload_available=True` 且 `envelope is not None`：
  - 返回 fallback payload，无读取诊断。

- `resolved_payload_available=False` 且 `envelope is None`：
  - 返回 EventLog fallback payload，诊断 `accepted_evidence_envelope_missing`。
  - payload 可用，不映射 `LOST`。

- `resolved_payload_available=False` 且 descriptor 读取成功：
  - 返回 digest-checked result payload，无读取诊断。

- `resolved_payload_available=False` 且 descriptor 读取抛 `HostDurableError`：
  - 返回 `None`，诊断 `result_payload_unavailable`。
  - `_accepted_status(...)` 映射 `LOST`。

`_result_event_payload(...)` 的 EventLog payload 读取失败出口：

- 捕获 `HostDurableError` 后返回 `{}`，诊断 `event_payload_unavailable`。
- 后续 `_result_payload(...)` 会叠加 envelope missing，但 `_accepted_status(...)` 以 `event_payload_unavailable` 优先映射 `LOST`。

结论：missing event payload 与 missing result payload 都产生 unavailable diagnostic，并稳定映射 `LOST`；payload available 但 status typed 字段不可用时映射 `UNKNOWN`。

## Consumer disposition

- `dayu/host/read_api.py`
  - canonical `TOOL_RESULT_ACCEPTED` activity 调用 `project_accepted_tool_result(...)`，只消费 `projection.status`。
  - `UNKNOWN` 走 `_accepted_result_activity_state(...)` 的非 completed/cancelled 分支，展示为 failed/error activity；未发现 raw outcome status reconstruction。

- `dayu/host/run_input.py`
  - resume guidance 使用 `projection.status.value`。
  - evidence material 通过 accepted-result projection / evidence renderer 派生。
  - rg 命中 `tool_result_payload.get("result")` 位于旧 resume fallback result 文本读取，不用于 status reconstruction。

- `dayu/host/evidence.py`
  - `raw_tool_outcome` helper 只生成 canonical raw outcome 文本，用于 LLM-facing result text。
  - 不读取 raw outcome `kind` / `result.ok` 推断 accepted status。

- `dayu/host/memory.py`
  - 未命中 `AcceptedToolResultStatus` 或 `raw_tool_outcome` status 重建；Memory 消费 accepted evidence material。

- `dayu/host/compact_material.py`
  - 调用 `project_accepted_tool_result(...)` 后只用 `projection.llm_material` 进入 compact evidence block。
  - `raw_tool_outcome is missing` 仅是缺少 LLM material 的 fail-closed，不重建 status。

结论：消费者已有正确 owner 消费路径，无需生产代码改动；目标测试覆盖 read model、run input、memory、compact material 均通过。

## Propagation audit

- 产生：ToolRuntime accept barrier / wait resolution 写入 `TOOL_RESULT_ACCEPTED` typed payload status 字段；Service callback endpoint 只把合法 object provider ref 转成 `WaitProviderStatusRef`。
- 校验：Service mapper 校验 `provider_status_ref` object shape；accepted-result projection 校验 typed status 字段，不接受 raw outcome status fallback。
- 持久化：EventLog payload 保留 typed status、raw outcome、provider status ref object；raw outcome 不作为 status 真源。
- 审计 / 诊断：payload unavailable 通过 `event_payload_unavailable` / `result_payload_unavailable` 暴露并映射 `LOST`；typed status unavailable 通过 `accepted_status_unavailable` 暴露并映射 `UNKNOWN`。
- 投影：Read API、RunInputBuilder、Memory、Compact material 统一消费 `project_accepted_tool_result(...)`，不从 raw outcome 重建状态。
- LLM-facing 输出：evidence renderer 只输出业务可读工具名称、查询语义、业务来源、工具结果；status 语义来自 projection，不恢复 raw fallback。

## 验证命令与结果

```bash
source .venv/bin/activate && pytest tests/service/test_wait_callback_endpoint.py tests/host/test_accepted_result_projection.py tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_projection_read_model.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py -q
```

结果：`311 passed in 1.73s`

```bash
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

结果：`0 errors, 0 warnings, 0 informations`

```bash
rg -n "_result_payload|AcceptedToolResultStatus.UNKNOWN|_status_from_raw_outcome|raw_tool_outcome|result_payload_unavailable|event_payload_unavailable" dayu/host/accepted_result_projection.py dayu/host/read_api.py dayu/host/run_input.py dayu/host/evidence.py dayu/host/memory.py dayu/host/compact_material.py tests/host
```

结果摘要：

- `_status_from_raw_outcome` 无匹配。
- `raw_tool_outcome` 匹配保留在 raw result text/details、evidence material、测试 fixture 与 fail-closed 检查中。
- `AcceptedToolResultStatus.UNKNOWN` 只在 accepted-result projection 与相关测试断言中出现。
- `result_payload_unavailable` / `event_payload_unavailable` 只在 accepted-result projection 与测试断言中出现。

```bash
rg -n "provider_status_ref" dayu/service/wait_callback_endpoint.py tests/service/test_wait_callback_endpoint.py
```

结果摘要：

- 生产只保留 `_provider_status_ref_from_json(...)` object parser。
- 测试包含 typed object 正例与裸字符串 malformed 负例。

```bash
git diff --check
```

结果：通过，无输出。

## Coverage result

```bash
source .venv/bin/activate && pytest tests/service/test_wait_callback_endpoint.py tests/host/test_accepted_result_projection.py --cov=dayu.service.wait_callback_endpoint --cov=dayu.host.accepted_result_projection --cov-report=term-missing -q
```

结果：`62 passed in 0.51s`

- `dayu/host/accepted_result_projection.py`: 92%
- `dayu/service/wait_callback_endpoint.py`: 88%
- total: 90%

## README decision

- `dayu/host/README.md`：已检查 Agent 更新约束。当前变更没有改变 Host public 边界描述，只收紧 projection status owner 规则；无需更新。
- `tests/README.md`：测试覆盖摘要属于该 README 职责，已更新 wait callback endpoint 条目，加入裸字符串 `provider_status_ref` 拒绝覆盖。
- 根 `README.md`：最终用户手册，不记录 Service callback payload 内部契约；无需更新。
- `dayu/README.md`：总揽架构文档，不列 provider status ref object shape；无需更新。

## Residual risk

- `UNKNOWN` 在 Read API activity 仍映射为 failed/error severity；这是现有消费者策略，本次未改变。若产品层需要区分 unknown 与 failed，应作为后续 owner-level projection/display policy 变更处理，不能恢复 raw outcome fallback。
- Service callback endpoint 现在拒绝裸字符串 `provider_status_ref`。如果外部真实 callback 调用方仍发送旧 shape，会收到 `malformed_payload`；这是本 slice 明确要求的 fail-closed 行为。

