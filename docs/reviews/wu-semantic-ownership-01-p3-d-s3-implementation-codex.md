# WU-SEMANTIC-OWNERSHIP-01 / P3-D S3 implementation artifact

执行者：AgentCodex  
Gate：S3 implementation  
范围：Typed Engine error codes and propagation audit

## 目标与 owner boundary

S3 的真实问题成立：Engine 事件和 Agent run outcome 中的失败码原先以裸字符串表达，导致 Engine-owned 闭集失败码、provider / runner 专有协议码、Host durable/public 文本三种语义容易混在同一个弱类型字段中。问题严重性按 P3-D 评估成立，因为该语义会跨 Engine event、Agent outcome、Host RUN_FAILED、Tool Trace、Read API 与 outbox 传播。

语义所有权边界如下：

- Engine contract owner：定义 run failure code 的强类型公共契约。Engine 自己产生的已知失败码使用 `EngineRunErrorCode` 闭集；provider / runner 专有失败码使用 `RunnerSpecificErrorCode`。
- Provider / runner adapter owner：第一次产生 provider / runner 专有协议码；必须在进入 `RunnerProtocolErrorData` 时构造 wrapper，并保留闭集 source。
- Agent owner：把 `RunnerEvent` 归一成 Engine failure candidate / EngineEvent；已知 Agent/Engine failure 使用 enum，直接 provider / runner protocol pass-through 使用 wrapper，缺失 provider detail 使用 Engine fallback enum。
- Host ingest owner：Engine typed code 进入 Host durable/public 边界时调用同一个 serializer，写入 durable JSON 文本。
- Host read/tool-trace/outbox owner：只消费 Host durable serialized text；不得按 wrapper 内部结构分支或重建 provider-specific code。

## 实现摘要

- 新增 `dayu/engine/contracts/error_codes.py`：
  - `EngineRunErrorCode` 闭集枚举，覆盖 S3 要求的全部已知 Agent/Engine 失败码。
  - `RunnerSpecificErrorSource` 闭集 source。
  - `RunnerSpecificErrorCode` wrapper：构造时 trim，拒绝空白、空字符串与超过 128 字符的值。
  - `serialize_engine_error_code` 作为 Host durable/public 边界唯一序列化 helper。
  - `runner_protocol_error_code`、`http_provider_error_code`、`adapter_error_code` 作为显式构造入口。
- 更新 Engine contract dataclass：
  - `RunFailedData.error_code: EngineErrorCode`
  - `EngineRunOutcomeFailed.error_code: EngineErrorCode`
  - `ProviderProtocolErrorData.error_code: EngineErrorCode`
  - `RunnerProtocolErrorData.error_code: RunnerSpecificErrorCode`
  - 以上字段均在 `__post_init__` 做运行时类型校验，防止测试或动态构造绕过 pyright。
- 更新 OpenAI runner adapter：
  - provider payload code 经 `http_provider_error_code(...)` 包装。
  - parser / tool-call aggregator 产生的 runner protocol code 经 `runner_protocol_error_code(...)` 包装。
  - adapter 层私有 `ChoicePolicyError.error_code: str` 保持在 adapter 内部，进入 `RunnerProtocolErrorData` 前被包装，不作为 Engine/Runner public contract 暴露。
- 更新 Agent：
  - `_ERROR_*` 常量改为 `EngineRunErrorCode` enum member。
  - provider / runner protocol pass-through 保持 typed wrapper。
  - runner HTTP non-context failure 归一为 `adapter_error_code(...)`，不是空 wrapper。
  - fallback message 使用 `serialize_engine_error_code(...)`。
- 更新 Host ingest：
  - `RUN_FAILED`、provider protocol failure payload、failure metadata 均在 ingest 边界调用 `serialize_engine_error_code(...)`。
  - `read_api.py`、`tool_trace.py`、`outbox.py` 保持读取 durable serialized text，不读取 typed wrapper。
- 新增 weak-typing guard：
  - 禁止 `RunFailedData` / `EngineRunOutcomeFailed` / `ProviderProtocolErrorData` / `RunnerProtocolErrorData` 的 error_code 字段退化为裸 `str`。
  - 禁止关键 contract 构造点使用字符串字面量传 `error_code`。
  - 禁止 Host ingest 读取 `data.error_code` / `event.data.error_code` 时绕过统一 serializer。

## 变更文件

生产代码：

- `dayu/engine/contracts/error_codes.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/contracts/runner_events.py`
- `dayu/engine/contracts/__init__.py`
- `dayu/engine/__init__.py`
- `dayu/engine/agent.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`
- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `dayu/host/engine_ingest.py`

测试：

- `tests/engine/contracts/test_runner_events.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_package_exports.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_weak_typing_guard.py`
- `tests/host/test_engine_ingest_mapping.py`
- `tests/host/stress_support.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_llm_compaction.py`
- `tests/host/test_local_proxy_engine_ingest.py`
- `tests/host/test_phase5_local_execution_integration.py`
- `tests/host/test_public_retry_replay.py`
- `tests/host/test_watch_session_events.py`

文档：

- `dayu/engine/README.md`
- `dayu/host/README.md`
- `docs/engine/design.md`
- `docs/host/design.md`
- `tests/README.md`

## 源发现关闭情况

已关闭：

- Engine events / Agent run outcome 的失败码 contract 已从裸字符串改为 typed union。
- Provider / runner-specific code 未被强行塞进 global enum，而是经 `RunnerSpecificErrorCode(value, source)` 显式建模。
- wrapper 构造已 trim，并拒绝 whitespace-only、empty、overly long value。
- Host durable JSON、public HostEvent、Tool Trace、outbox 继续暴露 serialized text，且 serialized text 由 `serialize_engine_error_code(...)` 在 Host ingest 边界统一产生。
- 已有构造点中的 literal string error-code 已迁移为 enum member 或 wrapper constructor。
- 已增加 weak-typing guard，覆盖 contract 注解、关键构造点和 Host serializer boundary。

仍开放：

- 无 S3 范围内开放项。
- `dayu/engine/runners/openai/_choice_policy.py` 内部仍有私有 `ChoicePolicyError.error_code: str`。该字段不是 Engine/Runner public contract；进入 `RunnerProtocolErrorData` 前已包装，因此不属于 S3 禁止项。
- Host 内仍存在 `error_code: str` 类型字段，属于 Host durable text 或 Host 自有状态 / projection 字段，不是 Engine typed code object。

## 传播审计

1. Provider protocol code
   - OpenAI streaming / non-stream parser 和 tool-call aggregator 在产生 fatal runner protocol code 时构造 `RunnerSpecificErrorCode`。
   - provider payload 中的 error object code 通过 `http_provider_error_code(...)` 保留 provider 来源。
   - parser / adapter 自己产生的 protocol code 通过 `runner_protocol_error_code(...)` 保留 runner protocol 来源。

2. Agent failure candidate
   - `RunnerProtocolErrorData.error_code` 是 `RunnerSpecificErrorCode`，Agent 直接传给 `RunFailedData` 和 `ProviderProtocolErrorData`。
   - Agent-owned known failures 使用 `EngineRunErrorCode`。
   - HTTP runner error 的非 context-compaction failure 使用 `adapter_error_code(...)`；没有 provider detail 时不构造空 wrapper。

3. Engine `run_failed` / Agent outcome
   - `RunFailedData.error_code` 与 `EngineRunOutcomeFailed.error_code` 都是 `EngineErrorCode` typed union。
   - dataclass `__post_init__` 会拒绝裸字符串。

4. Host `RUN_FAILED`
   - `engine_ingest.py` 在 ingest boundary 对 `event.data.error_code` / `data.error_code` 调用 `serialize_engine_error_code(...)`。
   - Host EventLog / terminal plan / diagnostic payload 写入的是 durable serialized text。

5. Tool Trace failure metadata
   - provider protocol failure metadata 中的 `provider_error_code` 由 `serialize_engine_error_code(...)` 写入。
   - `tool_trace.py` 只读取 durable `failure_metadata` 文本字段，不检查 wrapper source 或 wrapper internals。

6. Public HostEvent failure / Read API / Outbox
   - `read_api.py` 从 durable payload 读 `error_code` / `provider_error_code` 文本。
   - `outbox.py` 没有读取 Engine typed code object。
   - Host 不按 provider-specific runner code 分支。

7. Memory / compact / evidence / LLM-facing exclusion
   - 窄扫描 `dayu/config`、Host memory、compact material / payload / pipeline、LLM compaction、run input、terminal answer、accepted result projection 未命中 typed error-code 或 provider diagnostic 关键字。
   - provider diagnostic 和 provider error code 只出现在 Host read / tool trace / ingest / tests / docs 相关路径；未进入 prompt、memory、compact material、terminal answer 或 evidence renderer。

## 验证结果

必跑验证：

- `source .venv/bin/activate && pytest tests/engine/contracts tests/engine/test_engine_event_contract.py tests/engine/test_package_exports.py tests/engine/test_agent_phase2.py -q`
  - 结果：`144 passed in 0.18s`
- `source .venv/bin/activate && pytest tests/host/test_engine_ingest_mapping.py tests/host/test_public_host_event.py tests/host/test_read_api_terminal_policy.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_projection.py -q`
  - 结果：`155 passed in 1.56s`
- `source .venv/bin/activate && pytest tests/engine -q`
  - 结果：`514 passed in 2.08s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - 结果：`0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - 结果：通过，无输出。

覆盖率证据：

命令：

```bash
source .venv/bin/activate && pytest tests/engine tests/host/test_engine_ingest_mapping.py tests/host/test_public_host_event.py tests/host/test_read_api_terminal_policy.py tests/host/test_tool_trace_projection.py tests/host/test_outbox_projection.py --cov=dayu.engine.contracts.error_codes --cov=dayu.engine.contracts.agent_run --cov=dayu.engine.contracts.runner_events --cov=dayu.engine.contracts.engine_events --cov=dayu.engine.contracts --cov=dayu.engine --cov=dayu.engine.agent --cov=dayu.engine.runners.openai.sse_parser --cov=dayu.engine.runners.openai.non_stream_parser --cov=dayu.engine.runners.openai.tool_call_aggregator --cov=dayu.host.engine_ingest --cov-report=term-missing:skip-covered -q
```

结果：`669 passed in 5.13s`。触及生产文件覆盖率均不低于 80%：

- `dayu/engine/agent.py`：89%
- `dayu/engine/contracts/agent_run.py`：99%
- `dayu/engine/contracts/engine_events.py`：99%
- `dayu/engine/contracts/error_codes.py`：97%
- `dayu/engine/runners/openai/non_stream_parser.py`：93%
- `dayu/engine/runners/openai/sse_parser.py`：93%
- `dayu/engine/runners/openai/tool_call_aggregator.py`：89%
- `dayu/host/engine_ingest.py`：91%
- package `__init__.py` 聚合导出由 `tests/engine/test_package_exports.py` 覆盖，不作为独立业务逻辑覆盖率风险。

## 源码扫描

命令：

```bash
rg -n "error_code: str|error_code=\"|error_code=data\.error_code" dayu/engine dayu/host tests/engine tests/host
```

结论：

- 未发现 `dayu/engine/contracts` 目标字段退回 `error_code: str`。
- 命中 `dayu/engine/runners/openai/_choice_policy.py` 与 parser 私有 helper 的 `error_code: str`，属于 adapter 内部局部语义，进入 public `RunnerProtocolErrorData` 前已包装。
- 命中 `dayu/engine/agent.py` 的 `error_code=data.error_code` 是 typed wrapper / typed union pass-through。
- 命中 Host / tests 中的 `error_code: str` 是 durable text、Host 自有错误码或测试 projection 字段，不是 Engine typed code object。

命令：

```bash
rg -n "RunFailedData\(|EngineRunOutcomeFailed\(|ProviderProtocolErrorData\(|RunnerProtocolErrorData\(" dayu/engine tests/engine
```

结论：

- 构造点均迁移为 enum member 或 wrapper constructor。
- `tests/engine/test_weak_typing_guard.py` 会在后续出现 literal string `error_code=` 构造时失败。

命令：

```bash
rg -n "error_code|provider_error_code|failure_metadata" dayu/host/engine_ingest.py dayu/host/read_api.py dayu/host/tool_trace.py dayu/host/outbox.py tests/host
```

结论：

- `dayu/host/engine_ingest.py` 是 typed Engine code 的唯一 Host ingest 边界，并调用 `serialize_engine_error_code(...)`。
- `read_api.py` 和 `tool_trace.py` 只读取 durable payload / `failure_metadata` 文本。
- `outbox.py` 未读取 Engine typed code object。

命令：

```bash
rg -n "_ERROR_|runner_error_done_without_detail|context_compaction_required|provider_error_code" dayu/engine dayu/host tests
```

结论：

- `_ERROR_*` 常量已为 `EngineRunErrorCode` enum member。
- `runner_error_done_without_detail`、`context_compaction_required` 作为 Engine-owned enum value / durable serialized text 出现。
- `provider_error_code` 只作为 Host durable/read/tool-trace projection text 出现；Host 不按 provider-specific wrapper source 或 code 分支。

LLM-facing leakage 窄扫描：

```bash
rg -n "PROVIDER_DIAGNOSTIC|message_marker_fallback|provider_diagnostic|provider_error_code|RunnerSpecificErrorCode|EngineRunErrorCode|runner_error_done_without_detail" dayu/config dayu/host/memory.py dayu/host/durable/memory.py dayu/host/compact_material.py dayu/host/compact_payload.py dayu/host/compact_pipeline.py dayu/host/compaction.py dayu/host/llm_compaction.py dayu/host/run_input.py dayu/host/_terminal_answer.py dayu/host/accepted_result_projection.py
```

结果：无命中。typed error-code 类型名、provider diagnostic 与 provider error code 没有进入 prompt、memory、compact material、run input、terminal answer 或 accepted result projection。

## README / design 更新判断

- `dayu/engine/README.md`：已更新。该 README 的 `Agent更新约束` 要求只写当前 `dayu.engine` package 已实现的公共契约、稳定边界和关键机制；本次修改改变 Engine failure code 公共 contract，因此属于职责范围。
- `dayu/host/README.md`：已更新。该 README 的 `Agent更新约束` 要求只写当前 `dayu.host` package 的公共契约、关键执行路径、事件流和稳定边界；本次修改明确 Host ingest/public projection 边界，因此属于职责范围。
- `tests/README.md`：已更新。该 README 明确“新增测试层级后，应同步更新本文件”，且只记录当前测试事实；本次新增 weak-typing guard 覆盖项，因此属于职责范围。
- `docs/engine/design.md`：已更新。该文件是本 gate design source，Engine failure code contract 已变化，需要同步设计语义。
- `docs/host/design.md`：已更新。Host ingest/public durable boundary 已变化，需要同步设计语义。
- 根目录 `README.md` 与 `dayu/README.md`：未更新。没有用户可见安装、CLI/Web/WeChat 入口、命令参数、默认输出通道、工作区文件位置、最终用户工作流、排障方式、分层关系或装配方式变化。

## 残余风险

- 本次有意改变 Engine public contract 类型，不保留旧 string-only 构造兼容；这符合 S3 non-goal / prohibition。
- Provider-specific protocol code 仍只以 durable serialized text 对外投影；Host 不掌握 wrapper source。若未来 public API 需要暴露 source，应由 Engine/Host public contract 单独设计，不能从 Host 消费者处 ad hoc 读取 wrapper internals。
- 未引入 provider plugin registry、generic observability framework 或 S1/S2 语义变更。
