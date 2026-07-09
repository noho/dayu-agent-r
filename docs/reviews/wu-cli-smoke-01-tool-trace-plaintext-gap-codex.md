# wu-cli-smoke-01 Tool Trace 明文可审计性 GAP 调研

## 结论摘要

本次问题动机成立，且严重性没有被高估：当前 Tool Trace 能证明“发生了哪次 runner call / 哪个工具被请求和接受 / digest 与 ref 是什么”，但不能直接回答用户真正关心的“模型实际看到了什么 system prompt、user prompt、tool schema、tool result，以及最终回答是什么”。

真实运行数据中，Host durable SQLite 保存了一部分明文：`USER_INPUT_ACCEPTED.payload_json.system_prompt` 包含已展开的 `# 当前时间`、`# 当前分析对象`、`V（Visa Inc.）`，`USER_INPUT_ACCEPTED.payload_json.display_text/user_prompt` 包含用户输入，terminal sqlite payload 保存 final answer，`TOOL_RESULT_ACCEPTED.payload_json.raw_tool_outcome` 保存本次工具结果。但 Tool Trace hot/cold projection 只暴露 refs/digests/summary；runner-call manifest 也只保存 message digest、size、source refs，不保存完整 rendered message。

更大的 GAP 是：完整 tool schema JSON、provider request payload、runner-call projection artifact、第二轮 tool-result continuation 的完整 LLM-facing messages 当前没有可查询恢复的 artifact。第二轮 `RUNNER_CALL_INPUT_ASSEMBLED` 在真实 trace 中已经是 `limited_signal`，reason 为 `missing_projection_artifact`。

## 读取范围

- 设计真源：`docs/host/design.md`、`docs/engine/design.md`、`AGENTS.md`。
- 实现：`dayu/host/tool_trace.py`、`dayu/host/run_input.py`、`dayu/host/engine_ingest.py`、`dayu/host/durable/tool_trace.py`、`dayu/host/durable/schema.py`。
- 测试：`tests/host/test_tool_trace_projection.py`、`tests/host/test_tool_trace_queries.py`、`tests/host/test_run_input_builder.py`。
- 真实产物：`workspace/tmp/wu-cli-smoke-01-manual/prompt.log`、`workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`、`workspace/.dayu/host/dayu_host.sqlite3`。

## 设计与代码证据

设计真源明确要求 runner-call manifest 受限：`RUNNER_CALL_INPUT_ASSEMBLED` hot payload 只保存 manifest ref/digest、identity 和 validation status；完整 LLM-facing rendered messages 若需要，只能作为 `runner_call_projection_artifact` 派生 artifact 保存，不能成为 EventLog hot payload。见 `docs/host/design.md:1457`、`docs/host/design.md:1458`。

Tool Trace 设计也明确它是 EventLog 派生 projection，只消费 runner-call manifest refs/digests、工具参数/semantic query atoms、projector metadata summary、Engine 可观察 count/digest 和 projection artifact refs，不能重新运行 prompt builder 猜历史输入。见 `docs/host/design.md:1672` 到 `docs/host/design.md:1694`。

实现与设计一致：RunInputBuilder 实际构造 `AgentRunRequest.messages` 和 `tool_schemas`，但 manifest 只记录 digest/size/source refs。`projection_artifact_ref` 与 `projection_artifact_digest` 当前硬编码为 `None`。见 `dayu/host/run_input.py:2036` 到 `dayu/host/run_input.py:2075`、`dayu/host/run_input.py:4248` 到 `dayu/host/run_input.py:4295`、`dayu/host/run_input.py:4418` 到 `dayu/host/run_input.py:4447`。

Tool Trace projection 对 runner-call 只抽取 `manifest_ref`、`manifest_digest`、`message_count`、`role_sequence_digest`、`input_projection_digest`、`projector_metadata_summary`、`diagnostic`。见 `dayu/host/tool_trace.py:646` 到 `dayu/host/tool_trace.py:707`。Tool Trace 查询 API 也只分页读 hot rows 或 runner-call reconstruction signals，没有 payload/artifact resolve API。见 `dayu/host/durable/tool_trace.py:440` 到 `dayu/host/durable/tool_trace.py:572`。

测试明确锁定该行为：`test_runner_call_manifest_is_bounded_and_does_not_inline_messages` 断言大 prompt 不进入 manifest；`test_tool_trace_projects_runner_call_manifest_signal` 说明 Tool Trace 只复制 runner-call manifest refs/digests 与摘要 signal；large arguments 测试断言长参数原文不进入 cold JSONL。

## 真实运行产物观察

`prompt.log` 证明真实 runner 调用发生：首轮 `message_count=2`、`tool_schema_count=12`、HTTP body size 27738；模型调用 `get_current_time`；工具结果 accepted；第二轮 `message_count=4`；最终 `final_answer` accepted。

`tool-trace-cold.jsonl` 共有 7 条核心 trace：

- event_sequence 6：`RUNNER_CALL_INPUT_ASSEMBLED`，`message_count=2`，`validation_status=complete`，包含 manifest ref/digest、role digest、input projection digest、projector summary，不含 system/user 明文。
- event_sequence 39/67：两次 `USAGE_REPORTED`，包含 token 与 context pressure summary，不含 prompt 明文。
- event_sequence 43：`TOOL_CALL_REQUESTED`，包含 `tool_name=get_current_time`、tool schema digest、arguments digest，不含完整工具 schema；本次参数明文不在 cold line。
- event_sequence 44：`TOOL_RESULT_ACCEPTED`，包含 outcome digest、payload digest、timing，不含 `raw_tool_outcome` 明文。
- event_sequence 47：第二轮 `RUNNER_CALL_INPUT_ASSEMBLED`，`message_count=4`，`validation_status=limited_signal`，`reason=missing_projection_artifact`。
- event_sequence 71：`RUN_SUCCEEDED`，包含 terminal summary ref/digest，不含 final answer 明文。

SQLite 真实数据进一步说明：

- `event_log` 有 72 条左右事件，其中 `REASONING_DELTA` preview 47 条；Tool Trace 不消费这些 preview。
- `payload_descriptors` 只有 3 个 payload：两个 runner-call manifest、一个 terminal payload。
- 首个 runner-call manifest 的 `message_entries` 只有 `role`、`content_digest`、`content_size_bytes`、`source_refs`、`projection_artifact_ref=null`。
- `USER_INPUT_ACCEPTED.payload_json.system_prompt` 明文存在，且包含 `# 当前时间`、`# 当前分析对象`、`V（Visa Inc.）`；但它不是 Tool Trace 查询结果，也不是最终 normalized one-system-message 的 projection artifact。
- terminal sqlite payload 保存 final answer 明文：“当前时间是 **2026年7月7日 19:18:11**...”；Tool Trace 只保存 ref/digest。

附带风险：真实 `USER_INPUT_ACCEPTED.payload_json.effective_execution_config.runner_spec.headers` 中出现 provider Authorization header 明文。该问题不属于本次 Tool Trace 明文 GAP 的主线，但说明 retention/purge 与敏感字段脱敏不能 deferred 太久。

## 字段级 GAP

| 材料 | Tool Trace 当前可查 | Host durable 当前状态 | 分类 |
| --- | --- | --- | --- |
| system prompt full text | 不可查；只有 runner-call content digest/size/source refs | `USER_INPUT_ACCEPTED.system_prompt` 有 Service-prepared scene prompt 明文；最终 normalized system envelope 无 projection artifact | Host 有部分明文但 Tool Trace 未投影；最终 rendered message artifact 缺失 |
| user prompt full text | 不可查；manifest user entry 只有 digest/size/source ref | `USER_INPUT_ACCEPTED.display_text` / `user_prompt` 有明文 | Host 有明文但 Tool Trace 未投影 |
| tool schema full JSON/description | 不可查；只有 effective schema digest、tool_schema_snapshot ref、单工具 schema digest | 未发现完整 selected `ToolSchema` JSON payload；provider request body 未保存 | 根本未持久化完整可恢复明文/结构 |
| tool call args | cold line 只有 arguments digest；小参数可在 EventLog canonical payload 中看到 | 本次 `TOOL_CALL_REQUESTED.arguments_inline_json` 保存 `timezone=Asia/Shanghai` | Host 有明文但 Tool Trace 未投影 |
| tool result LLM-facing payload | cold line 只有 outcome/payload digest、timing | 本次 `TOOL_RESULT_ACCEPTED.raw_tool_outcome` 保存工具返回 JSON；但没有单独 LLM-facing tool message projection artifact | Host 有 raw outcome；LLM-facing tool message artifact 缺失 |
| final answer full text | cold line 只有 terminal_summary_ref/digest | terminal sqlite payload 有 final answer 明文 | Host 有明文但 Tool Trace 未投影 |
| reasoning/thinking delta | Tool Trace 不消费 preview | `REASONING_DELTA` preview rows 保存 delta 明文；非 canonical truth | Host durable preview 有明文；Tool Trace 不投影；需 retention 控制 |
| context slot 展开文本 | Tool Trace 不可查 | `USER_INPUT_ACCEPTED.system_prompt` 中可见当前时间、分析对象；最终 normalized system message未保存 | Host 有部分明文但 Tool Trace 未投影 |
| projector source text | Tool Trace 只有 projector id/schema/digest/purpose | manifest 只有 source refs、projector metadata；`projection_artifact_ref=null` | projection artifact missing |
| provider request payload | 不可查 | prompt.log 只有 body_bytes；SQLite 未保存完整 body | 根本未持久化，且不应默认完整保存 |

## 两类 GAP

### Host durable 有明文但 Tool Trace 查询没投影

- `USER_INPUT_ACCEPTED` 中的 user prompt 与 Service-prepared system prompt。
- `TOOL_CALL_REQUESTED` 中的小型 inline arguments。
- `TOOL_RESULT_ACCEPTED` 中的本次 raw tool outcome。
- terminal sqlite payload 中的 final answer。
- preview `REASONING_DELTA` 中的 reasoning deltas。

这些字段可以通过手工 SQL 追 EventLog/payload descriptor 找到，但 Tool Trace hot/cold 和现有查询 API没有提供“按 run 还原 LLM-facing输入/输出”的结构化入口。

### 根本未持久化明文或可恢复 artifact

- 完整 selected tool schema JSON/description/parameters。
- 完整 provider request body。
- runner-call projection artifact，即最终 normalized rendered messages 的可校验 artifact。
- 第二轮 tool-result continuation 的完整 `system/user/assistant/tool` messages。真实数据已经报 `limited_signal: missing_projection_artifact`。
- LLM-facing tool message text。当前有 raw tool outcome，但缺少“实际注入给模型的 tool role content”的派生 projection。

## Root Cause

Root cause 不是单一 bug，而是设计的 bounded manifest 与第一版 projection 能力之间存在明确未实现项。

1. 设计有意只在 runner-call manifest 保存 digest/ref/summary，避免 EventLog hot payload 膨胀和泄露。代码也按此实现，manifest entry 不内联 content，`projection_artifact_ref` 当前为 `None`。
2. `runner_call_projection_artifact` 是设计允许的 analyzer/debug 明文载体，但当前 RunInputBuilder 没写该 artifact，Engine-only continuation 也只能写 limited-signal manifest。
3. Tool Trace cold line 不展开 `payload_ref`，也不 resolve sqlite payload；它只复制 source event 的摘要字段和 digest。
4. Tool schema snapshot 当前只有 digest/ref 级信号，没有完整 selected schema payload descriptor；因此即使 analyzer resolve manifest，也无法恢复 provider-visible tool schema JSON。
5. 现有查询 API 只支持按 run/tool_call/provider_request/diagnostic ref 查 hot rows，缺少“resolve manifest -> resolve projection artifact -> resolve selected tool schemas/tool args/tool result/final answer”的诊断 API/CLI。

## 对 #70 / #71 的影响

### #70 Tool Trace analyzer

如果 #70 analyzer 只能拿到当前 digest/ref/summary，它不能诊断用户关心的“模型实际看到了什么 system prompt / user prompt / tool schema / tool result / final answer”。它最多能输出：

- runner-call 是否存在、message_count、role_sequence_digest、input_projection_digest。
- prepared manifest 是否 complete，或者 continuation 是否 limited_signal/mismatch。
- 工具名、tool_call_id、arguments digest、tool schema digest、outcome digest、terminal summary ref/digest。
- usage、tool timing、context pressure 等摘要。

只能 limited_signal 的诊断包括：

- system prompt 是否包含 `# 当前时间`、`# 当前分析对象`、`V（Visa Inc.）`。
- user prompt 是否与 CLI 输入完全一致。
- tool schema 描述、参数说明、枚举说明是否真的暴露给模型。
- tool result 注入给第二轮模型的 tool message 正文。
- final answer 明文。
- 第二轮 tool-result continuation 的完整 input。当前真实 trace 已经是 `missing_projection_artifact`。

因此 #70 若目标是“解释 tool trace 中工具调用链路和摘要”，当前基础可用；若目标是“审计 LLM-facing 明文输入输出”，当前是前置 blocker。

### #71 prompt-based Tool Trace diagnostics

#71 需要从 prompt/final answer 反查工具调用和 LLM 输入事实。当前缺以下可恢复材料：

- 按 runner call 保存的 rendered messages artifact，至少含每条 message 的 role、content、content digest、source refs。
- selected tool schema full JSON snapshot，能从 runner call 反查当时暴露的工具集合与每个工具 description/parameters。
- tool result LLM-facing payload，即实际注入 tool role 的 content，而不是只有 raw outcome 或 accepted evidence envelope。
- final answer resolve API，从 terminal_summary_ref 取回明文并校验 digest。
- prompt text 到 runner-call/message-entry 的索引能力，例如按 content substring/digest/source ref 找 run、runner_call、tool_call。

没有这些，#71 只能基于 EventLog 手工 SQL 做局部反查，不能形成稳定 prompt-based diagnostics。

### 支撑 #70/#71 的最小保存/查询集合

建议最小集如下：

- runner-call projection artifact：每次 runner call 的最终 LLM-facing messages，字段为 `index`、`role`、`content`、`content_digest`、`content_size_bytes`、`source_refs`、`projector_metadata_id`。artifact ref/digest 回写到 manifest 的每条 message entry 或 manifest-level projection refs。
- selected tool schema snapshot payload：当次可见 tools 的完整 JSON，包括 name、description、parameters、required、additional_properties、display metadata 可选摘要；用 digest/ref 关联 manifest。
- tool call arguments resolver：短参数可 inline；长参数走 payload descriptor；Tool Trace analyzer 能 resolve，但 cold line 不必直接内联。
- tool result LLM-facing payload artifact：保存实际注入模型的 tool message content；raw outcome 可作为 source，不等同于 LLM-facing text。
- final answer resolver：通过 terminal_summary_ref 返回 final answer 明文和 digest 校验结果。
- reasoning delta：默认不作为 #70/#71 blocker；若保留，必须标记 preview / sensitive / retention-bound，不能默认无限期进入 analyzer 输出。

### Retention / purge owner

以下内容必须归入 retention/purge owner，而不是无限期保留：

- runner-call projection artifact 与 provider request/response diagnostic artifact。
- selected tool schema snapshot，如果包含业务内部工具说明、参数语义或策略文本。
- tool result LLM-facing payload，尤其是长网页、财报片段、用户私有文件内容。
- final answer payload。
- reasoning/thinking delta preview。
- `USER_INPUT_ACCEPTED` 中的 system/user prompt，以及当前发现的 runner headers/Authorization 类敏感字段。

建议把 owner 明确落到 retention/purge 工作（例如 #43/#78/WU-RET-03 一类），并定义 run/session/workspace 粒度 TTL、按 label 清理、敏感字段脱敏和 artifact tombstone 语义。

### Blocker 分类

当前 WU 必须修复的 blocker：本次是只读 GAP 调研，不应改代码。若当前 WU 的验收要求是“只能用 Tool Trace 验证占位符展开”，则 blocker 是 Tool Trace 缺 runner-call projection artifact 与明文 resolve API；目前只能用 Host durable `USER_INPUT_ACCEPTED` 或 Service prepare 重建验证，不能用 Tool Trace 单独验证。

#70/#71 前置 blocker：

- 写入并校验 `runner_call_projection_artifact`。
- 保存或可查询 selected tool schema full JSON snapshot。
- 提供 Tool Trace analyzer resolver API/CLI，能从 hot row 的 refs/digests 解析 manifest、projection artifact、tool args、tool result payload、terminal payload。
- 为 Engine-only continuation 写入可恢复 input projection，而不是只写 limited_signal。

可 deferred 的 retention/privacy 风险：

- reasoning delta 是否保留与展示策略。
- provider raw request/response 是否保存；建议默认不保存，只有显式 debug/audit profile 且脱敏后保存。
- cold JSONL 分片归档、压缩、TTL 与 purge tombstone。
- 大型 tool result 与财报片段的 artifact lifecycle。

不可 deferred 太久的安全风险：真实 durable payload 中出现 provider Authorization header 明文，应尽快由配置/Host durable payload owner 明确脱敏或禁止持久化 secret-bearing execution config。

## 最佳实践修复建议

1. 不要把完整 messages 塞进 EventLog hot payload。按设计新增 `runner_call_projection_artifact`，以 payload descriptor/artifact ref + digest 连接 manifest。
2. 在 RunInputBuilder 完成 `_normalize_ordinary_run_messages` 后同步生成 projection artifact，内容是最终 LLM-facing messages，不是 merge 前候选 messages。
3. 对 Engine-only continuation，在 Engine/Agent 边界提供 typed observed input projection，至少能保存 assistant tool calls digest、tool messages full text、selected schema snapshot ref；不能只输出 `missing_projection_artifact`。
4. 新增 `tool_schema_snapshot` payload descriptor kind，保存 selected tools full schema JSON；manifest 的 `tool_schema_snapshot_refs` 应引用该 payload digest，而不是仅由 count/disable_tools 派生。
5. Tool Trace analyzer 不应默认展开所有明文到 cold JSONL；应提供按需 resolver，输出时带 digest verification、size、truncation policy 和 redaction status。
6. 对 final answer 与 tool result，保留 ref/digest 在 hot/cold trace 中即可，但 analyzer 必须能 resolve terminal payload 和 LLM-facing tool payload。
7. reasoning delta 默认只作为 preview diagnostic，需单独 retention 开关；不应作为普通 #70 输出默认展示。
8. 在 retention/purge 设计落地前，至少先阻止 secret-bearing runner headers/API key 进入 durable prompt/input payload。

## 需要的测试

- RunInputBuilder：生成 projection artifact，断言 artifact content digest 等于 manifest entry content digest；大 prompt 不进 hot payload，但 artifact 可 resolve。
- Tool schema snapshot：断言 selected tool schema full JSON 可由 manifest ref resolve，且 digest 随 description/parameters 变化。
- Tool Trace projection：hot/cold 仍只保存 refs/digests/summary，不内联大明文。
- Tool Trace analyzer：按 run 输出 system/user/tool schema/tool args/tool result/final answer 的 resolved view；缺 projection artifact 时输出 limited_signal。
- Continuation：工具结果后的第二轮 runner call 不再只产生 `missing_projection_artifact`。
- Retention：purge 后 analyzer 输出明确 unavailable/redacted，而不是伪造重建。
- Security：durable payload 不保存 Authorization/API key 明文。

## 验证记录

本次只读执行了：

- `sed` / `rg` 阅读设计、实现与测试。
- `sqlite3` 只读查询 `event_log`、`payload_descriptors`、`host_sqlite_payloads`、`host_tool_trace_hot` 相关字段。
- `sed` 读取 `prompt.log` 与 `tool-trace-cold.jsonl`。

未运行测试、未运行 pyright，因为本次没有修改生产代码。除本文档外未写文件、未 commit、未 push、未创建 issue/PR。
