# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-B Engine Provider Protocol And Tool-Call Contract Plan

## Gate、状态与约束

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 / Round3 R3-B`
- 当前角色：AgentCodex，只执行 plan-fix gate
- 风险级别：`production-high`
- 当前状态：`ready-for-plan-rereview`
- 下一入口：plan re-review；本 artifact 完成后停止
- 计划切片数：3
- 设计真源：`docs/engine/design.md`、`docs/host/design.md`
- 控制真源：`docs/host/issues-implementation-control.md`、`docs/phaseflow-umbrella-optimization-control.md`、`docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md`
- Plan review 真源：`docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-mimo.md`、`docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-ds.md`、`docs/reviews/wu-semantic-ownership-01-round3-r3-b-plan-review-controller-adjudication.md`
- 禁止动作：本 gate 不修改生产代码、测试或 README，不 commit、不 push、不创建 PR、不进入 implementation

初始 plan preflight 直接结果：当前分支为 `phaseflow/host-issues-control`，dispatch 时工作区 clean。plan-fix preflight 仍在同一非受保护分支；dirty scope 只包含本 plan 与三份已知 plan-review artifacts，没有额外 owner 不明改动。控制文档确认 R3-F 与 R3-A 已在本地通过 final closeout；controller 已裁决进入 R3-B plan-fix，且无 blocking open question。

## Goal confirmation

### 目标与动机

本 work unit 成立。Engine 是 provider wire protocol 到 `RunnerEvent` / `EngineEvent` 的唯一归一边界；如果它接受互相冲突的 tool-call identity、伪造或缺失的 `finish_reason`、非法 event discriminator/data、错误 message role，Host 无法在不重新解释 provider 协议的前提下判断哪些事实可信。当前代码已直接复现两类高风险错误：

1. 两个独立 provider tool call 能被聚合成一个名称与参数均拼接、且 JSON 语法合法的可执行调用。这会改变工具名称和参数语义，风险高于普通诊断丢失。
2. Agent 已接受 `RunnerDone` 并产出 `iteration_completed` 后，恢复生成器时仍可被迟到取消改写；provider 的具体失败诊断也能被随后抛出的通用异常覆盖。

此外，公共 Engine event/message 构造器允许静态类型提示之外的非法运行时组合，non-stream parser 继续接受明确标记为 OLD 的 dict arguments，JSON Schema enum 使用 Python `==` 语义并未拒绝负计数边界。这些都是真实 owner 缺口，不应由 Host、工具调用方、测试 fixture 或展示层补救。

两项 controller confirmation 被当前代码直接否定或证据不足：runner identity 已使用类型前缀与字符串长度前缀，delimiter 不产生 canonical tuple 歧义；context overflow marker 是 OpenAI adapter 内部、structured-code-first、带 provenance 的有界 fallback，仅“硬编码”不能证明当前语义失败。二者不进入 implementation。

### 成功信号

1. `RunnerDoneData` 成为单次 Runner iteration 的 typed commit fact；其后到达的取消不再在 Agent 内层插入矛盾的 `run_cancelled`，done-derived final / failure 决策不再被取消 helper 覆盖。
2. 首个已接受的 provider / protocol failure diagnostic 保持 `error_code`、`provider_request_id`、`recoverable` 与 client correlation；通用 runner exception 只在没有更具体候选时产生。
3. `EngineEvent` 在构造时按唯一 mapping 校验 `EngineEventType -> data dataclass`；每种 `AgentMessage` 在构造时校验固有 role，`AgentRunRequest` 拒绝联合之外的消息实例。
4. OpenAI stream / non-stream parser 对 tool-call identity 与 terminal `finish_reason` 使用同一 fail-closed 规则；任何 identity 冲突都不会产出 `RunnerToolCallsCompletedData`，任何 tool-call/finish mismatch 都不会被强制改写成成功 `TOOL_CALLS`。
5. non-stream `function.arguments` 只接受 JSON string；dict、list、number、boolean、null 均按 provider protocol error 收口，不保留 OLD compatibility branch。
6. JSON Schema enum 按 JSON 类型语义比较，至少保证 `true != 1`、`false != 0`，同时保留 JSON number 的数学等价 `1 == 1.0`；`minLength`、`maxLength`、`minItems`、`maxItems` 在 schema 构造边界拒绝 bool、非整数和负数。
7. Host 不新增 provider parsing、event repair、fallback 或 schema compatibility；全量 pyright、默认 pytest、`git diff --check`、compatibility deletion scans 均通过。

### Scope boundary / non-goals

- 不修改 Host durable schema、EventLog schema、Run / Attempt 状态机、Host ingest mapping 或 outbox/memory/trace durable contract。
- 不修改 Fins、Web、Documents、CLI config 或 Service assembly 的生产实现；共享 `ToolParametersSchema` 变严后若暴露这些模块已有非法 schema，停止并返回 plan review，不在本 WU 顺手改业务 schema。
- 不新增 provider registry、finish-reason capability profile、error-marker 配置 DSL、通用 JSON Schema validator 或第三方 schema 依赖。
- 不实现旧 provider dict arguments 兼容 adapter，不保留 feature flag、alias、wrapper、loose parsing 或 caller-side repair。
- 不改变 Host 对 lifecycle 的治理所有权；本 WU 只修 Engine 单次 run 内 Runner fact 的接受顺序和 provider normalization。
- 不把 streaming 中“缺 index 但有稳定 id”的现有 synthetic identity 机制整体删除；只修显式非法 native index 与 identity 冲突。无 index/id 的 position continuation 不在本 finding 范围内重新设计。
- 不配置化 `_CONTEXT_OVERFLOW_MESSAGE_MARKERS`，不修改 `RunnerRequestIdentity` canonical encoding。

### Blocking questions

无。设计真源已明确 Engine 负责 provider normalization，当前代码足以冻结 implementation contract；无需用户在兼容行为、Host repair 或 provider capability 之间选择。

## 第一性原理复核与直接证据

本节行号以 plan gate 当前工作区为准；implementation 必须以函数/类型名为稳定定位，不机械依赖行号。

| Source finding | 当前直接代码 / 测试证据 | 裁决 | 唯一 owner |
| --- | --- | --- | --- |
| DR-013 late cancellation after RunnerDone | `dayu/engine/agent.py:1300-1308` 在 `_consume_runner_event()` 后无条件检查取消；`1555-1583` 已先写 `done_seen=True` 并产出 `ITERATION_COMPLETED`。外层 `891-895` 虽有 `not done_seen`，但永远晚于内层分支。`tests/engine/test_agent_phase2.py:1401-1428` 只覆盖 done 前取消。 | `accepted` | `_IterationState` 与 `_run_runner_iteration()` 的 RunnerDone commit transition；Host 不参与仲裁。 |
| DR-014 ToolCallAggregator merges provider calls | `_is_tool_call_index()` 在 `tool_call_aggregator.py:52-60` 接受负 int；synthetic key 从 `-1` 开始。`203-231` 在 target occupied 时直接拼 name/arguments；`270-278` 对同 id / 不同 index 无条件 remap。当前只读反例得到 `call-a + call-b -> ('call-a', 'lookupdelete', {'a': 1, 'b': 2})`，fatal errors 为空。 | `accepted` | `ToolCallAggregator` 的 native index、synthetic key、provider id 三方身份表。 |
| DR-031 EngineEvent discriminator / Message role | `EngineEvent` 在 `engine_events.py:553-572` 没有 `__post_init__` 或 mapping；测试 `test_engine_event_contract.py:39-59` 自己复制 mapping。`messages.py:46-118` 只有 `Literal`，无运行时 role 校验。当前可直接构造 `FINAL_ANSWER + ToolCallRequestedData` 与 `UserMessage(role=SYSTEM)`。 | `accepted` | `EngineEvent` contract mapping；四种 message dataclass 的固有 role；`AgentRunRequest` 的 message union membership。 |
| DR-034 OLD non-stream dict arguments | `non_stream_parser.py:452-455,530-560` 明确把 Mapping `json.dumps` 为 string；`test_old_protocol_parity_regressions.py:49-88` 将该行为锁为成功。stream aggregator 只接受 string buffer。 | `accepted` | OpenAI non-stream parser 的 wire shape normalization。 |
| DR-035 JSON equality / negative bounds | `tool_call_projection.py:649` 使用 `value not in enum_value`，当前 `boolean true + enum [1]` 返回 `ValidatedToolArguments`。`450-462,566-578` 只验 bound 是非 bool int，不要求非负；当前 `minLength=-1` 被接受，`maxLength=-1` 被伪装成用户 range failure。 | `accepted` | `ToolParametersSchema` 负责声明期 schema 合法性；`validate_and_project_arguments` 负责实例值与 enum 的 JSON 语义比较。 |
| non-stream finish_reason forcing | `non_stream_parser.py:362-370` 只要有 tool calls 就无条件写 `FinishReason.TOOL_CALLS`。`test_non_stream_response.py:395-430` 明确把 provider `stop` 强制成成功 TOOL_CALLS。SSE `sse_parser.py:661-684` 也存在同类推断。 | `accepted` | OpenAI `_choice_policy` + stream/non-stream parser 的 terminal shape policy。 |
| finish_reason missing policy mismatch | content-only stream/non-stream 已 fail closed，但 tool-call 两路都把 missing/null 推断为 TOOL_CALLS；Agent `_classify_iteration()` 还在 `agent.py:1756` 用 `or FinishReason.STOP` 掩盖内部缺失。`RunnerDoneData.finish_reason` 本身是必填 typed 字段，因此 reviewer 所称“公开 RunnerDone 可缺失”不成立。 | `narrowed` | parser 必须对所有成功 terminal 要求显式 finish reason；Agent 用 typed `RunnerDoneData` 消除内部 fallback，不新增公开 optional contract。 |
| agent failure_candidate overwrite | `agent.py:1482-1553` 已保存 protocol/HTTP 具体失败；runner generator 随后抛普通异常时 `1349-1355` 无条件覆盖为 `runner_exception` 且丢失 provider request id。 | `accepted` | `_IterationState` 的 first accepted failure candidate。 |
| runner identity delimiter weakness | `runner_identity.py:240-273` 对每个 part 使用类型前缀；字符串为 `s:<length>:<value>`，再连接 parts。值中出现 `|` 或 `:` 仍由 length framing 唯一分界，当前 reviewer 只观察到 delimiter，未考虑完整编码。 | `rejected-with-reason` | `RunnerRequestIdentity` 已是 owner；不改编码。可在现有 contract test 中保留/补充非阻断 delimiter regression，但不得据此改 wire digest。 |
| OpenAI error classifier hardcoded markers | `error_classifier.py:95-145` 先读取结构化 `error.code=context_length_exceeded`；结构化非 overflow code 会阻止 marker 覆盖；只有无结构化 code 时才走 module-owned marker fallback，并返回 `MESSAGE_MARKER_FALLBACK` provenance。`test_context_overflow_classifier.py:62-72` 已锁定非 overflow code 优先。没有多语言 provider 当前 contract 或错误分类反例。 | `rejected-with-reason` | OpenAI adapter error classifier；固定协议矩阵不是配置或 caller 的责任。 |

计数：`accepted=7`、`narrowed=1`、`rejected=2`，共复核 10 项 source findings / confirmations。

## 设计对齐与语义所有权

### Design truth alignment

- `docs/engine/design.md` §1、§7、§9 明确 Engine/Runner 负责 provider wire 到 `RunnerEvent` 的归一，Host 只消费 `EngineEvent`；因此 finish/tool identity 错误必须在 parser/aggregator 失败，不能留给 Host ingest 修复。
- `docs/engine/design.md` §13 的 Cancellation Commit Boundary 已承诺 Runner done 后 final/tool/failure candidate 不被迟到取消改写；当前代码违反既有设计，不需要新设计选择。
- `docs/engine/design.md` §14 把 `EngineEventType` 与 data 类型列为一一对应公共契约；production contract 必须拥有 mapping，不能让测试复制 truth。
- `docs/host/design.md` §13.4 规定 Host 将 EngineEvent 映射为具体 canonical/preview/diagnostic fact；如果 EngineEvent 自己允许 discriminator/data 冲突，Host 被迫猜测，违反下层 owner 原则。
- `docs/host/design.md` 已规定 provider diagnostic 不能成为 lifecycle/failure 的替代真源；本 WU 保留 first accepted provider failure，并不修改 Host durable projection。

### Owner matrix

| Semantic fact | Owner/source of truth | Projection / consumer | 禁止的下游补救 |
| --- | --- | --- | --- |
| Runner 已完成及 commit 时点 | `_IterationState.runner_done: RunnerDoneData | None` | Agent iteration classification、log、tool/final/failure transition | Host 看 `iteration_completed` 后重新裁决；分散 `done_seen + finish_reason + provider_id` 三字段反推。 |
| provider tool-call identity | `ToolCallAggregator` 的 index/id/synthetic mapping | Runner delta、completed tool calls | Agent/Host 按名称、JSON 可解析性或到达顺序合并。 |
| EngineEvent discriminator/data | `ENGINE_EVENT_TYPE_TO_DATA` + `EngineEvent.__post_init__` | Agent producer、Host candidate ingest | tests 复制 mapping；Host 根据 data class 覆盖错误 type。 |
| AgentMessage role | 每个 message dataclass `__post_init__`；`AgentRunRequest` 校验联合成员 | payload builder、trace/input projection | payload builder 硬编码 role 来“纠正”非法实例；使用 `getattr`/默认 role。 |
| non-stream function.arguments shape | OpenAI non-stream parser | aggregator string buffer | dict `json.dumps` compatibility；工具执行前 loose parsing。 |
| terminal finish_reason | `_choice_policy` + SSE/non-stream parser；`RunnerDoneData` 必填 | Agent typed runner_done | parser 强制 TOOL_CALLS；Agent 默认 STOP；Host 从 tool events 反推。 |
| failure diagnostic | `_IterationState` first accepted failure candidate | `RunFailedData` / Engine terminal | runner exception 或 Host projection 覆盖更具体 provider code/id。 |
| JSON Schema declaration bounds | `ToolParametersSchema` construction | tool declaration / provider payload / runtime projector | 每次调用把非法 schema 报成用户参数错；业务工具各自补检查。 |
| JSON enum instance equality | `dayu.runtime.tool_call_projection` | `ToolCallable` consumers | Python equality直接替代 JSON equality；每个 tool 重写 enum 校验。 |
| runner request canonical identity | 现有 `runner_identity.py` length-framed encoding | client correlation header/log | caller 转义 delimiter 或改 Host id 格式。 |
| context overflow message markers | OpenAI `error_classifier.py` structured-code-first fallback | typed detection + diagnostic provenance | Host/prompt/config重复匹配 provider 文本。 |

## 已冻结的 implementation decisions

### 1. Engine contract 与 RunnerDone state

1. `engine_events.py` 仿照已正确实现的 `runner_events.py`，增加唯一只读 `ENGINE_EVENT_TYPE_TO_DATA` mapping、`engine_event_type_for_data()`、`validate_engine_event_pairing()`，并由 `EngineEvent.__post_init__()` 调用。mapping/helper 在 `engine_events` 模块导出供 contract tests 使用，但不扩大 `dayu.engine` 包根稳定 export。
2. type 非 `EngineEventType` 或 data 不在封闭联合时抛 `TypeError`；type/data 不匹配时抛 `ValueError`。不得按类名字符串、`hasattr/getattr` 或 metadata 猜测。
3. `SystemMessage`、`UserMessage`、`AssistantMessage`、`ToolMessage` 各自在 `__post_init__` 校验 `AgentMessageRole` 类型与本类唯一 role；raw string role 不是合法替代。`AgentRunRequest.__post_init__` 同时拒绝 messages tuple 中联合之外的实例。
4. `_IterationState` 删除互相可能漂移的 `done_seen`、`finish_reason`、`provider_request_id`，改为单一 `runner_done: RunnerDoneData | None`。所有完成原因与 provider request id 只从该 typed fact 读取。
5. `_run_runner_iteration()` 消费并产出 `RunnerDone` 对应事件后，先按 `runner_done is not None` 结束 runner-event loop，再检查取消；因此生成器在 `iteration_completed` yield 后恢复时不会插入 `run_cancelled`。post-done test 必须直接手动驱动 Agent async iterator：读到 `ITERATION_COMPLETED` 后才调用 `token.request_cancel()`，再继续迭代；不得用 Runner 在 yield 后自取消的 helper 代替，因为 Agent 在 commit 后不应再次请求 Runner 的下一事件。
6. done-derived `_FinalDecision` 与 `RunFailedData` 直接进入对应 terminal constructor，不再调用会二次检查取消的 failure-or-cancel helper。force-answer 采用相同规则。
7. tool-call done 的 commit 含义是先接受并投影 batch-ready / requested tool facts；迟到取消可以在这些事实之后阻止尚未完成的 ToolExecutor handshake或下一 iteration，但不能在 tool-call candidate 对外投影前把本轮直接改成取消。不得忽略 Host 已注入的 cancellation token继续执行无限工作。
8. 增加 module-level first-candidate helper：只有 `failure_candidate is None` 时写入 protocol/HTTP/context/runner exception candidate。所有 `failure_candidate` 写入都必须通过该 helper，包括 runner generator 的普通 exception 分支；`agent.py` 除该 helper 内部的唯一赋值外不得再出现直接 `state.failure_candidate = ...`。无既有 candidate 且未取消时，runner exception 成为不可恢复 `runner_exception` terminal；已有 protocol/HTTP/context candidate 时只保留原 candidate，后来 exception 仅写诊断日志。
9. runner generator exception 没有 `RunnerDone` commit：若异常返回外层时 cancellation token 已取消，继续沿 `runner_done is None` 的 pre-done 仲裁产生 `run_cancelled`；若未取消则由 first candidate 分类为 `run_failed`。这保持设计中“Runner 未完成时取消可抢占”，也不允许 exception 直接赋值绕开 first-candidate owner。
10. 删除 `_classify_iteration()` 的 `state.finish_reason or FinishReason.STOP`。`_consume_runner_event()` 在接受 `RunnerDoneData` 前验证 `finish_reason` 是 `FinishReason`；非法/缺失值不得写入 `state.runner_done` 或产出 `ITERATION_COMPLETED`，而是通过 first-candidate helper记录 `EngineRunErrorCode.RUNNER_ABNORMAL_STOP` 与明确的 invalid/missing finish reason diagnostic。`_classify_iteration()` 在 `runner_done is None` 时只走既有 failure/abnormal-stop fail-closed 分支；在 non-None 时直接读取 typed `runner_done.finish_reason`，不允许 `None` 落入 tool/final 无关分支。S2 完成后此验证只保留为 injected Runner contract guard，不承担 parser compatibility。

### 2. OpenAI parser / aggregator normalization

1. provider wire 显式携带 `index` 时，合法值必须是非 bool 的非负 int；负数、bool、float、string 均产生 fatal `tool_call_invalid_index`，不得按“缺失 index”回落到 id/synthetic path。
2. 缺失 index 且有非空 id 时仍允许 synthetic key；同一 id 后续首次绑定到尚未占用的合法 native index 是唯一允许的迁移。
3. 以下全部 fatal，统一使用 `tool_call_identity_conflict` 并保留 bounded partial summaries：
   - synthetic source 迁移到已占用 native target；
   - 同一 provider id 已绑定一个 native index，后续声明另一个 native index；
   - 同一 native index 已绑定 id A，后续声明 id B；
   - 任一 remap 会让两个已有 partial 合并。
4. index、provider id、position 是三种 routing signal。`_resolve_index()` 无论通过哪一种 signal 得到 resolved index，都必须进入同一个 identity-binding validator 后才能修改 partial/id/position table；position fallback 只允许把无 index/id 的 continuation 追加到已经无歧义绑定的 partial，不能绕过 occupied target、same id/two indices、same index/two ids 或 remap-merge 检查。任一 routing mechanism 导致上述冲突都使用 `tool_call_identity_conflict` fatal。
5. fatal identity conflict 后不得拼接 name/arguments/provider state，不得产出 `RunnerToolCallsCompletedData`；SSE 最终只产 protocol error(s) + `RunnerDone(ERROR)`。相同 id + 相同 index 的正常分片，以及 position 指向同一无歧义 partial 的 id-less/index-less continuation继续合法。
6. `_choice_policy.py` 成为 stream/non-stream terminal shape 共用 owner：成功 response 必须有显式、已映射的 finish reason；`has_tool_calls` 当且仅当 finish reason 为 `TOOL_CALLS`。missing/null 继续使用现有 `sse_missing_finish_reason` / `non_stream_missing_finish_reason`；tool calls + STOP/LENGTH/CONTENT_FILTER 或无 tool calls + TOOL_CALLS 分别使用新增 `sse_tool_calls_finish_reason_mismatch` / `non_stream_tool_calls_finish_reason_mismatch`。规则只有一个私有 helper 真源，两个 transport wrapper 只提供各自错误码和诊断前缀。
7. parser 必须在产出 `RunnerToolCallsCompletedData` / `RunnerContentCompletedData` 前完成 terminal shape 校验；发生 mismatch 时不得先发成功 completed 再发 error。parser 中任何 `FinishReason.TOOL_CALLS` 命中都必须是消费 `_choice_policy` 已验证的显式 provider fact、比较/诊断分支或 fail-closed terminal policy；禁止 parser 直接赋值来强制成功。
8. 删除 non-stream Mapping arguments coercion。`function.arguments` 只有 string 合法；dict、list、number、boolean、null或缺失一律 `tool_call_arguments_not_string` + `RunnerDone(ERROR)`。测试必须断言不再有成功 completed。stream delta 对 `arguments=null` 的既有“无参数增量”语义不在此规则内改变。
9. 不保留 `allow_dict_arguments` flag、provider 名单、feature switch 或旧测试兼容分支。

### 3. JSON Schema declaration / instance validation

1. `ToolParametersSchema.__post_init__` 遍历顶层 `properties` 的每个 value：value 是 Mapping 时校验其中 `minLength`、`maxLength`、`minItems`、`maxItems`；若该 field schema 的 `type == "array"` 且 `items` 是 Mapping，再对该 scalar item schema 校验同四个关键字。value 或 items 非 Mapping 的既有语义不在本 WU 扩大。四个 bound 必须是非 bool int 且 `>= 0`：bool/非 int 抛 `TypeError`，负数抛 `ValueError`。错误在 tool schema construction/discovery 前暴露，不等到 LLM 调用后伪装为用户 `invalid_argument`。
2. 不扩展为完整 JSON Schema evaluator；不新增 `oneOf`、`pattern`、nested object properties、schema registry 或第三方依赖。只关闭当前 runtime 已声称支持的四个 count bounds。
3. `tool_call_projection.py` 保留相同非负检查作为对 mutable mapping / 非正常构造的防御；正常路径的真源仍是 contract construction。防御失败不得接受参数。
4. 新增私有递归 JSON equality helper并只用于 enum：bool 与 number 永不相等；int/finite float 作为 JSON number按数学值比较；null/string/list/object按类型与递归成员比较。不得使用序列化字符串比较，也不得改变 enum 的展示顺序。
5. 默认值继续经过同一个 `_project_field` + enum path，因此显式参数和 schema default 不会出现两套 equality 语义。

## Implementation slices

本轮采用 3 个 slices，符合 umbrella control 对 High Risk production work 的建议。S1 与 S2 都属于 Engine，但 S1 关闭公共 contract / Agent commit state，S2 关闭 provider wire normalization；它们有不同 failure injection 与 reviewer focus，因此分开。S3 属于层中立 `dayu.contracts` / `dayu.runtime` schema owner，不能与 provider parser混为一个 slice。拆成 4 个会把 Engine contract 与紧邻的 Agent state 做两次高风险 review，却没有独立 owner/验证收益；合并为 2 个则会让 schema contract failure 被 OpenAI parser test掩盖。当前 3 个是最小 owner-closed 切分。

### S1 — Engine Event / Message Contract And RunnerDone Commit

**Objective / expected outcome**

建立 Engine 公共 event/message 构造不变量，以单一 typed `runner_done` 提交 iteration，并保留 first accepted failure diagnostic。完成后 Agent 的 ordinary final、force-answer final、error done、tool-call done 都有明确迟到取消顺序。

**Prerequisite / dependency**

- 无代码前置；以当前 clean branch 与设计 §13/§14 为准。
- S2 依赖本 slice 的 Agent 不再修复或默认 provider finish semantics。

**Allowed production files/modules**

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/messages.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/agent.py`

**Allowed tests**

- `tests/engine/test_engine_event_contract.py`
- `tests/engine/contracts/test_messages.py`
- `tests/engine/contracts/test_agent_run.py`
- `tests/engine/test_agent_message_union.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/test_agent_phase3_tool_call.py`

**Concrete assertions**

- mapping keys等于全部 `EngineEventType`，data classes 唯一；合法 pair 全通过，mismatch / 非 enum / 非联合 data 分别按类型失败。
- 四种 message 正确 role成功；wrong enum role、raw string role失败；`AgentRunRequest` 拒绝 cast 注入的非 message。
- 新增并固定 post-done yield/resume 反例测试：`test_post_done_cancel_does_not_override_ordinary_final`、`test_post_done_cancel_does_not_override_force_answer_final`、`test_post_done_cancel_does_not_override_protocol_error_failure`、`test_post_done_cancel_does_not_override_http_error_failure`、`test_post_done_cancel_does_not_skip_tool_call_candidate`。每个测试都必须先用 `anext()` 驱动到 `ITERATION_COMPLETED`，再调用 `token.request_cancel()` 并消费剩余 stream；不得在 RunnerDone 前或 Runner 自身 yield continuation 中提前取消。
- post-done 预期：ordinary / force-answer 终态为 `FINAL_ANSWER`；protocol / HTTP error保留原 `RUN_FAILED` code、provider request id和 recoverable；tool-call 路径至少先产出 `TOOL_CALLS_BATCH_READY` 与全部 `TOOL_CALL_REQUESTED`，随后才允许 cancellation handshake 收口，不能从 `ITERATION_COMPLETED` 直接跳到 `RUN_CANCELLED`。
- done 前取消仍为 `run_cancelled`，Runner 无 done自然结束仍按既有 cancelled/abnormal-stop 规则；不倒置旧有正确语义。
- protocol/HTTP/context candidate 后 runner 抛异常时，terminal保留首个 candidate 的 code/id/recoverable；无 candidate且未取消的异常为 `runner_exception`；exception与取消并发且没有 RunnerDone时仍为 pre-done `run_cancelled`。
- 通过 `cast(FinishReason, None)` 注入 malformed `RunnerDoneData` 时，不得产出 `ITERATION_COMPLETED`、`FINAL_ANSWER` 或 tool-call decision；必须以 `RUNNER_ABNORMAL_STOP` owner diagnostic fail closed。正常 parser产出的每个 `RunnerDoneData` 仍携带真实 `FinishReason`。
- Runner close 仍 exactly once，terminal 仍唯一且最后出现。

**Validation commands**

```bash
source .venv/bin/activate
pytest tests/engine/test_agent_phase2.py::test_post_done_cancel_does_not_override_ordinary_final tests/engine/test_agent_phase2.py::test_post_done_cancel_does_not_override_protocol_error_failure tests/engine/test_agent_phase2.py::test_post_done_cancel_does_not_override_http_error_failure tests/engine/test_agent_phase2.py::test_runner_exception_preserves_first_failure_candidate tests/engine/test_agent_phase2.py::test_runner_exception_and_cancel_without_done_prefers_cancel tests/engine/test_agent_phase2.py::test_runner_done_with_invalid_finish_reason_fails_closed tests/engine/test_agent_phase3_tool_call.py::test_post_done_cancel_does_not_override_force_answer_final tests/engine/test_agent_phase3_tool_call.py::test_post_done_cancel_does_not_skip_tool_call_candidate -q
pytest tests/engine/test_engine_event_contract.py tests/engine/contracts/test_messages.py tests/engine/contracts/test_agent_run.py tests/engine/test_agent_message_union.py tests/engine/test_agent_phase2.py tests/engine/test_agent_phase3_tool_call.py -q
python -m pyright dayu/ tests/ utils/
rg -n 'state\.(done_seen|finish_reason|provider_request_id)' dayu/engine/agent.py
rg -n 'or FinishReason\.STOP' dayu/engine/agent.py
rg -n 'state\.failure_candidate\s*=' dayu/engine/agent.py
git diff --check
```

前两条 source scan 预期均无结果；Runner completion 读取必须来自 `state.runner_done`。`state.failure_candidate =` scan 预期只命中 module-level first-candidate helper 内部的唯一赋值；任何 protocol/HTTP/context/exception 分支直接赋值均失败。

**Non-goals**

- 不改 Host `_cancelled_eof_candidate`、durable lifecycle 或 ingest mapping。
- 不改 parser、tool schema 或 context overflow marker。
- 不新增通用 Agent state-machine framework。

**Completion / stop condition**

focused tests、pyright、diff check 和 scans 全绿才可进入 S2。若 EngineEvent owner validation 暴露 Host 生产代码构造了 mismatch event，停止并回 plan review；不得在 Host 增加 fallback或扩大本 slice。

### S2 — OpenAI Tool Identity And Terminal Protocol Normalization

**Objective / expected outcome**

在 OpenAI adapter 边界拒绝 tool identity 冲突、OLD dict arguments 和 finish/tool shape mismatch，保证成功 completed event只来自无歧义 provider response。

**Prerequisite / dependency**

- S1 accepted；Agent 已不对缺失 finish reason 默认 STOP，也不在 Host 下游修复。

**Allowed production files/modules**

- `dayu/engine/runners/openai/tool_call_aggregator.py`
- `dayu/engine/runners/openai/_choice_policy.py`
- `dayu/engine/runners/openai/sse_parser.py`
- `dayu/engine/runners/openai/non_stream_parser.py`

**Allowed tests**

- 新增 `tests/engine/runners/openai/test_tool_call_identity_conflicts.py`
- `tests/engine/runners/openai/test_sse_tool_call_index_fallback_to_id.py`
- `tests/engine/runners/openai/test_sse_tool_call_stream.py`
- `tests/engine/runners/openai/test_non_stream_response.py`
- `tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py`
- `tests/engine/runners/openai/test_old_protocol_parity_regressions.py`
- `tests/engine/runners/openai/test_protocol_error.py`
- `tests/engine/runners/openai/test_event_flow_ordering.py`

**Negative / positive matrix**

- native index：`-1/-2/True/1.5/"0"` 全 fatal；missing index + id 仍 synthetic；same id + same index continuation成功。
- migration：synthetic id -> empty native target成功；synthetic -> occupied target失败；same id -> two native indices失败；same native index -> two ids失败。
- position routing positive：先建立 `position -> resolved index/id` 后，后续无 index/id 的同 position fragment 只能追加到该无歧义 partial，最终 name/arguments完整且只有一个 tool call。
- position-routed conflict：先建立 A=`native index 0/id A/position 0` 与 B=`synthetic id B/position 1`，再让无 index/id 的 fragment 经 position 1 归入 B，最后让 id B 声明 native index 0；occupied A target 必须产生 `tool_call_identity_conflict`，B 的 position-routed fragment不得与 A 拼接。另覆盖 resolved position与 same-id/two-indices、same-index/two-ids 组合，证明 position table不能绕过统一 validator。
- 冲突反例必须证明不会得到拼接后的 `lookupdelete` 或合并 arguments；fatal 后无 completed tool calls。
- arguments transport：string JSON object成功；dict/list/number/bool/null 全 protocol error；invalid JSON string、JSON scalar string仍按既有 fatal分类。
- stream/non-stream terminal：content + STOP/LENGTH/CONTENT_FILTER成功；tool calls + TOOL_CALLS成功；missing/null、tool calls + non-tool reason、content + TOOL_CALLS、未知 reason全 fatal。两种 transport 的事件类别与最终 `RunnerDone(ERROR)` 对齐。
- fatal ordering：protocol error(s) 在唯一 `RunnerDone(ERROR)` 前；不得先发成功 completed。

**Validation commands**

```bash
source .venv/bin/activate
pytest tests/engine/runners/openai/test_tool_call_identity_conflicts.py::test_position_routed_conflict_fails_closed_without_merge -q
pytest tests/engine/runners/openai/test_tool_call_identity_conflicts.py tests/engine/runners/openai/test_sse_tool_call_index_fallback_to_id.py tests/engine/runners/openai/test_sse_tool_call_stream.py tests/engine/runners/openai/test_non_stream_response.py tests/engine/runners/openai/test_stream_non_stream_terminal_parity.py tests/engine/runners/openai/test_old_protocol_parity_regressions.py tests/engine/runners/openai/test_protocol_error.py tests/engine/runners/openai/test_event_flow_ordering.py -q
python -m pyright dayu/ tests/ utils/
rg -n 'isinstance\(arguments, Mapping\)|json\.dumps\(dict\(arguments\)\)|dict arguments preserved' dayu/engine/runners/openai/non_stream_parser.py tests/engine/runners/openai
rg -n 'done_finish_reason = FinishReason\.TOOL_CALLS|finish = FinishReason\.TOOL_CALLS' dayu/engine/runners/openai/non_stream_parser.py dayu/engine/runners/openai/sse_parser.py
rg -n 'FinishReason\.TOOL_CALLS' dayu/engine/runners/openai/_choice_policy.py dayu/engine/runners/openai/non_stream_parser.py dayu/engine/runners/openai/sse_parser.py
rg -n 'source\.name \+ target\.name|source\.arguments_buffer \+ target\.arguments_buffer|target\.tool_call_id = target\.tool_call_id or source\.tool_call_id' dayu/engine/runners/openai/tool_call_aggregator.py
git diff --check
```

三个 exact scans（arguments coercion、parser direct forcing assignment、partial merge）预期无结果。`FinishReason.TOOL_CALLS` 语义级 scan允许有结果，但 implementation artifact和 reviewer必须逐项列出并分类为：`_choice_policy` 的显式 wire mapping/比较、parser消费已验证 policy fact、或 fail-closed mismatch诊断；任何 parser直接赋值/推断成功 TOOL_CALLS 都使 S2失败。不能用 helper重命名、变量改名或拆行逃避人工语义审计。

**Non-goals**

- 不删除所有 synthetic index / position continuation 行为。
- 不新增 provider-specific dict capability、marker config、retry或HTTP分类变更。
- 不改 Agent/Host 来接受 parser 输出的旧语义。

**Completion / stop condition**

完整 negative matrix、parity、pyright、diff check 和 deletion scans 全绿才可进入 S3。若某真实 provider 被证明只能返回 dict arguments，停止并要求独立 typed provider adapter design；不得恢复 generic compatibility。

### S3 — JSON Schema Bounds And Typed Enum Equality

**Objective / expected outcome**

让 tool schema 的 count bounds 在声明 owner 处失败，并让 runtime enum 使用 JSON equality；共享工具消费者不再把 schema bug 当作 LLM 参数错误。

**Prerequisite / dependency**

- S1/S2 accepted；本 slice 行为独立，但最后统一同步 Engine/design/test documentation truth。

**Allowed production files/modules**

- `dayu/contracts/tool_schema.py`
- `dayu/runtime/tool_call_projection.py`

**Allowed tests**

- `tests/contracts/test_tool_schema.py`
- `tests/runtime/test_tool_call_projection.py`
- 仅用于验证共享 contract 未破坏现有声明：`tests/tools/test_doc_tools_provider.py`、`tests/tools/web/test_web_tools_provider.py`、`tests/fins/test_fins_ingestion_tools.py`

**Allowed documentation after code/tests pass**

- `docs/engine/design.md`
- `dayu/engine/README.md`
- `tests/README.md`

**Concrete assertions**

- 四个 bounds 对 `-1`、bool、float、string均在 `ToolParametersSchema` construction失败；`0` 合法；array item schema的 string bounds同样覆盖。
- 防御性 runtime test用构造后被外部 mutable mapping篡改的 schema证明负 bound仍不会被接受。
- enum matrix覆盖 bool/int、bool/float、nested list、nested object；`1` 与 `1.0` 按 JSON number相等，`True` 与 `1` 永不相等。
- default 与显式 argument复用同一 enum equality。
- 当前 Doc/Web/Fins tool schemas 只作为 read-only validation target；不得为通过测试修改其生产实现。

**Validation commands**

```bash
source .venv/bin/activate
pytest tests/contracts/test_tool_schema.py tests/runtime/test_tool_call_projection.py tests/tools/test_doc_tools_provider.py tests/tools/web/test_web_tools_provider.py tests/fins/test_fins_ingestion_tools.py -q
python -m pyright dayu/ tests/ utils/
rg -n 'value not in enum_value|value in enum_value' dayu/runtime/tool_call_projection.py
rg -n '"(minLength|maxLength|minItems|maxItems)"\s*:\s*-' dayu tests
git diff --check
```

第一条 scan 预期无 Python membership 判断；第二条允许只命中新加的 negative tests，生产 `dayu/` 必须无命中。

**Non-goals**

- 不实现完整 JSON Schema draft、schema migration 或 provider discovery redesign。
- 不修改 Fins/Web/Documents/Doc tool生产 schema，不改变工具业务参数。
- 不更改 `invalid_argument` 成功/失败 envelope公共形状。

**Completion / stop condition**

focused tests、共享声明 smoke、pyright、diff check 全绿，且没有现有生产 schema 因新规则失败。若现有 schema 非法，停止并返回 plan review分类 owner；不得在 R3-B 顺手修业务模块。

## Aggregate validation and deepreview

所有 slices 通过各自 code review / fix / re-review 后，aggregate gate 必须使用 `$deepreview` 对当前未合并 workspace changes 做完整 review，并特别执行 adversarial failure pass：

- RunnerDone yield-resume 取消 race 是否在 ordinary、force-answer、error、tool call四路一致；是否有其它 cancel helper重新覆盖 done-derived failure。
- runner exception 是否与 protocol/HTTP/context 共用唯一 first-candidate helper；无 done 的 exception + cancel是否仍按 pre-done取消仲裁。
- Agent 是否彻底删除 STOP fallback，并让 malformed/missing finish reason在 owner guard fail closed而不是进入 tool/final无关分支。
- aggregator 是否仍能通过 position/id顺序构造隐式 merge；position-routed fragment遇到 occupied target时是否 fatal；fatal 后是否可能残留一个可执行 tool call。
- stream/non-stream 是否任一路仍推断 finish reason或先发 completed 后报错。
- EngineEvent/message validation 是否只存在于测试而非 production owner，或 Host 是否出现 downstream repair。
- schema enum helper是否对 nested JSON使用 Python equality，bounds是否只在用户调用时失败。
- 是否新增 compatibility flag、provider名单、`hasattr/getattr`、默认值、loose parsing或反向依赖。

Aggregate required commands：

```bash
source .venv/bin/activate
pytest -q
python -m pyright dayu/ tests/ utils/
git diff --check
rg -n 'state\.(done_seen|finish_reason|provider_request_id)|or FinishReason\.STOP' dayu/engine/agent.py
rg -n 'state\.failure_candidate\s*=' dayu/engine/agent.py
rg -n 'isinstance\(arguments, Mapping\)|json\.dumps\(dict\(arguments\)\)|dict arguments preserved' dayu/engine/runners/openai/non_stream_parser.py tests/engine/runners/openai
rg -n 'done_finish_reason = FinishReason\.TOOL_CALLS|finish = FinishReason\.TOOL_CALLS' dayu/engine/runners/openai/non_stream_parser.py dayu/engine/runners/openai/sse_parser.py
rg -n 'FinishReason\.TOOL_CALLS' dayu/engine/runners/openai/_choice_policy.py dayu/engine/runners/openai/non_stream_parser.py dayu/engine/runners/openai/sse_parser.py
rg -n 'source\.name \+ target\.name|source\.arguments_buffer \+ target\.arguments_buffer|target\.tool_call_id = target\.tool_call_id or source\.tool_call_id' dayu/engine/runners/openai/tool_call_aggregator.py
rg -n 'value not in enum_value|value in enum_value' dayu/runtime/tool_call_projection.py
rg -n '"(minLength|maxLength|minItems|maxItems)"\s*:\s*-' dayu
rg -n 'hasattr\(|getattr\(' dayu/engine/contracts/engine_events.py dayu/engine/contracts/messages.py dayu/engine/agent.py dayu/engine/runners/openai dayu/contracts/tool_schema.py dayu/runtime/tool_call_projection.py
```

除显式说明外，compatibility / old-state / direct-membership / production-negative-bound scans 预期无结果。`state.failure_candidate =` 只能命中 first-candidate helper的唯一 owner赋值；`FinishReason.TOOL_CALLS` 语义 scan必须逐项人工分类，parser direct forcing零容忍。`hasattr/getattr` scan若命中既有且与本 diff无关的代码，artifact 必须逐项分类；本 WU 不得新增命中。

Aggregate deepreview artifact 必须记录：review target、changed files、三 slice validation结果、accepted/rejected findings、adversarial counterexamples、README/design decision、propagation audit、residual risks及最终 `pass / fix-required`。任何 accepted finding都必须进入 fix/re-review，不得直接关闭。

## README / design trigger decisions

- `docs/engine/design.md`：implementation 后必须更新。当前文档已承诺 RunnerDone commit boundary，但需把 EngineEvent/message construction validation、tool-call finish consistency、non-stream string-only arguments和 first failure diagnostic写成当前实现事实；删除重复的 final commit bullet。
- `dayu/engine/README.md`：必须更新。`dayu/engine/` 的 public contract、Runner normalization和 cancellation state machine均变化；README 当前只说明 RunnerEvent pairing，并且“missing finish 不默认 stop”没有明确 tool-call fail-closed语义。
- `tests/README.md`：必须更新。它精确列出 runtime tool-call projection与OpenAI parser当前覆盖；需同步 typed enum / non-negative bounds、identity-conflict negative matrix和strict finish parity。
- `docs/host/design.md`、`dayu/host/README.md`：不更新。Host层级、durable schema、ingest mapping和consumer contract不变；只作为验证“Host不修复Engine事件”的设计真源。
- `dayu/README.md`：不更新。`UI -> Service -> Host -> Engine` 分层与包职责不变，修改发生在既有 Engine/runtime/contracts owner内。
- 根 `README.md`：不更新。无用户可见安装、CLI、工作区、日志或最终用户工作流变化。
- Fins、Config README：不更新；对应生产 owner不在本 WU 修改。

本 plan gate 只创建本 artifact，不提前修改上述文档。

## Propagation audit

Implementation 与 aggregate review 必须逐项证明：

1. 所有生产 `EngineEvent(...)` 构造点（当前为 Engine Agent 与 Host cancel EOF candidate）均通过 owner pairing，无 Host fallback。
2. 所有生产 AgentMessage 构造点都传本类固有 enum role；payload/trace projection只消费合法实例，不再承担纠错。
3. Parser fatal tool call不会到达 Agent `_execute_tool_batch`，因此 Host/ToolRuntime不可能执行拼接调用。
4. `finish_reason` 从 provider choice policy到 `RunnerDoneData`、`IterationCompletedData`、`FinalAnswerData`保持同一 typed fact；不得由 Host或Agent默认/重算。
5. first failure candidate的 code/id进入 `ProviderProtocolErrorData` / `RunFailedData` 后保持一致；非致命 provider diagnostic仍不成为 failure candidate。
6. ToolParametersSchema bound验证不会造成 runtime反向依赖；`dayu.runtime`仍只依赖标准库与 `dayu.contracts`。
7. rejected runner identity / error-marker findings没有被伪装成已修复；现有 owner与理由保留在 implementation artifact。

## Residual risks and owners

只有直接证据支持以下 residual；均不阻塞 plan review：

| Risk / uncovered area | Classification | Owner / destination |
| --- | --- | --- |
| 严格拒绝 dict arguments可能暴露非规范 OpenAI-compatible provider | fixed by fail-closed policy；不是 compatibility residual | 若未来有真实 provider contract，只能由独立 provider-specific typed adapter WU承接；当前 R3-B不保留分支。 |
| Synthetic index仍会在 delta preview中使用负内部 key，最终 ToolCallRequest重新编号为非负 | accepted current design, covered by S2 matrix | `ToolCallAggregator`; 若后续要求公开 delta index非负，需独立 EngineEvent contract WU，不能在 Host修复。 |
| Context overflow marker覆盖语言/厂商有限 | rejected current finding，不是 active residual | OpenAI error classifier；出现真实误判/漏判反例后由 provider adapter WU处理。 |
| Runner identity delimiter测试当前未覆盖特殊字符 | production encoding已无歧义；test-only guard可在S1顺带补，但不是修复条件 | `RunnerRequestIdentity` contract tests；不得改变 digest wire truth。 |

不存在未分类 residual risk。

## 为什么没有过度设计

本方案复用现有 `RunnerEvent` pairing模式、现有 dataclass contract、现有 OpenAI `_choice_policy`、现有 ToolCallAggregator和窄 JSON Schema projector；只在各自 owner处增加缺失的不变量。它没有引入通用 provider registry、完整 schema engine、Host repair、迁移层或兼容开关。三 slices按真实 owner与验证故障面切分，既没有按 finding/file机械拆分，也没有把无直接失败证据的 delimiter/marker extensibility混入生产变更。

## Plan completion report

- status：`ready-for-plan-rereview`
- artifact path：`docs/host/wu-semantic-ownership-01-round3-r3-b-engine-provider-protocol-plan.md`
- source findings：`accepted=7`、`narrowed=1`、`rejected=2`
- proposed slice count：`3`
- blocking questions：`none`
- plan-review findings：`PF-01` 至 `PF-05` 均已写入 S1/S2 implementation decisions、assertions/matrix 与 validation commands；source finding裁决不变。
- current gate / next entry point：plan-fix 完成；下一未完成 gate 为 plan re-review。本轮按用户约束停止，不进入 re-review或implementation。
