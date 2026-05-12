# Host 实施总控

## 文档职责

本文档是 Host 设计与实施的总控文档，负责记录实施工作流、phase 编排、phase 进入 / 退出条件、交付物和验证要求。

本文档不承载新的架构决策，不替代设计文档，不作为实现细节说明书。

## 设计目标

Host 设计与实施必须始终服务于以下目标：

- 生产级买方财报分析 Agent。
- 范式是“宿主强约束下的 LLM in the loop”。
- 支持单机多客户端 / 多进程。
- 支持本地 Engine 和远程 Engine 并列执行。

任何 phase plan、implementation slice、review finding 裁决和 scope 调整，都必须显式对齐这些目标。若某项设计或实现选择削弱这些目标，应停下来回到 `discussion-note.md` 与 `design.md` 修正设计后再继续。

## 真源层级

Host 后续计划与实施遵循以下真源层级：

```text
discussion-note.md
  -> 讨论决议与设计来源
  -> 记录为什么这样设计

design.md
  -> 规范化后的 Host 架构真源
  -> 后续 handoff implementation-ready plan 的主真源

implementation-control.md
  -> 实施编排文档
  -> 只记录 phases、依赖、进入 / 退出条件、交付物和验证要求
```

`discussion-note.md` 与 `design.md` 都是生成 phase plan 的输入真源；如果两者出现表达差异，以 `design.md`
的规范化表述为准。

如果发现 `design.md` 漏掉或误写了 `discussion-note.md` 中已经确认的设计决议，应先修正 `design.md`，再生成或继续
phase plan。

术语真源是 `dayu/README.md` 的术语表。phase discussion、phase plan、implementation、review、fix 与 re-review
必须使用该术语表中的定义；不得由 planning / implementation agent 自行重解释 `Session`、`Run`、`Attempt`、
`EventLog`、`USER_INPUT_ACCEPTED`、`EngineEvent stream`、`Host event stream`、`TruncationManager`、
`scope_token` 等术语。若发现术语缺失、冲突或不足以指导实施，应先和用户讨论，并同步更新 `dayu/README.md`
及对应设计文档，再继续推进。

本文档不得引入新的架构边界、状态机、公共接口或事件语义。若实施编排过程中发现需要新的架构决策，应先回到
`discussion-note.md` 讨论并同步到 `design.md`，再更新本文档的 phase 编排。

## 工作流

Host 实施采用以下工作流：

```text
discussion-note.md
  -> generate / update design.md
  -> update implementation-control.md phases
  -> select one phase
  -> discuss and refine the corresponding design.md section with the user
  -> generate handoff implementation-ready plan for that phase
  -> review plan
  -> user confirmation
  -> implement phase
  -> verify
  -> update related docs
```

每个 phase 单独生成 handoff implementation-ready plan。phase plan 必须基于：

- `discussion-note.md`
- `design.md`
- 本文档中对应 phase 的范围、依赖和退出条件

phase plan 不得从旧设计稿、旧代码路径或非真源文档推导架构边界。

每个 phase 的第一步必须是和用户讨论并细化 `design.md` 中的对应章节。该讨论属于 `$gateflow` 的 feature
discussion / requirement clarification 阶段，必须在进入 plan gate 前完成。

phase discussion 至少需要确认：

- phase 目标与 success signal；
- 本 phase 是否服务于总控设计目标；
- 对应 `design.md` 章节是否足够具体；
- 本 phase 的 scope boundary、non-goals 与 stop conditions；
- 是否存在会阻塞 handoff implementation-ready plan 的架构、状态机、公共接口、schema、持久化或测试问题。

如果 discussion 发现 `design.md` 对应章节不足以支撑直接写 plan，应先更新 `design.md`，再进入该 phase 的 plan。

## 强制约束

- Host 后续每个复杂 work unit、phase plan、public contract change、schema / storage change、state-machine change
  和 architecture-sensitive task 都必须遵循 `$gateflow` 工作流。
- phase plan、implementation 或 fix 过程中如果需要修改 Engine 代码，必须立即停下来向用户确认。未经用户明确确认，
  不得把 Engine 代码修改夹带进 Host phase。
- phase 讨论、plan、implementation、review、fix 或 re-review 过程中出现 material open question 时，必须停下来和用户讨论；
  不得让 planning / implementation agent 自行选择会影响架构、公共接口、状态机、schema、持久化、并发、恢复、测试期望或用户可见行为的方案。
- 每个 phase 产生的潜在影响、未覆盖项、deferred risk、后续 phase 依赖和明确不做项，必须回写到本文档的追踪区；
  不得只保留在对话、临时 artifact 或 phase plan 中。

## Open Questions 与风险追踪

总控文档负责追踪跨 phase 的 open questions、潜在影响和未覆盖项。

追踪规则：

- `blocking` open question 必须在对应 phase 的 plan review 通过前解决，并写回 `design.md` 或 phase plan。
- `non-blocking` open question 必须写明 working assumption、风险、触发回看条件和归属 phase。
- implementation 中发现的新 open question，如果会影响设计边界或用户可见行为，必须停下交给用户讨论。
- residual risk 和 uncovered area 必须分类为：当前 phase 修复、后续 phase 覆盖、后续 work unit、用户明确接受、或需要新跟踪项。
- 任何 deferred 项都必须有 owner / destination；没有 destination 时不能关闭对应 phase。

### 追踪区

#### Tool Trace / Provider Request 排错追踪

背景核实：

- OpenAI API reference 的 Debugging requests 说明 `x-request-id` 是每次 API request 的唯一标识，并建议生产环境记录 request id，便于和 OpenAI support 排障。
- 同一官方章节说明调用方可显式提供 `X-Client-Request-Id`；当 timeout / network issue 导致拿不到 `X-Request-Id` response header 时，可用该值让 OpenAI support 查询是否收到请求以及收到时间。
- 当前 Engine 已把 provider response header 的 `x-request-id` 提取为 `provider_request_id`，并在 Runner / Engine 错误与终态链路中显式透传：`RunnerHTTPErrorData`、`RunnerProtocolErrorData`、`RunnerDoneData`、`ProviderProtocolErrorData`、`RunFailedData`、`EngineRunOutcomeFailed` 等字段已覆盖；相关测试也覆盖了 HTTP error、protocol error、iteration completed、run failed 的透传。

追踪项：

- 不修改 `design.md`；这不是 Host 架构边界新决策，而是 tool trace / analyze 工具排障能力需求。
- 后续实现 tool trace 与 `utils/analyze_tool_trace.py` 时，必须把 `provider_request_id` 纳入热 JSON projection 与冷 JSONL，便于按 OpenAI `x-request-id` 排查 provider 错误、超时、协议错误和重试耗尽。
- 后续若 Host / Service 为 OpenAI-compatible request 注入 `X-Client-Request-Id`，tool trace 也必须记录对应 client-side request id，并与 `provider_request_id`、`run_id`、`attempt_id`、`execution_id`、`event_sequence` 一起可查询。
- 对 timeout / network error 且 `provider_request_id=None` 的场景，analyze 工具应提示优先查看 client-side request id / `X-Client-Request-Id`、网络错误类型、attempt 次数和 retry history。

## 当前状态

当前阶段仍未进入 Host 代码实施。`discussion-note.md` 已沉淀为讨论记录，`design.md` 是 Host 架构真源；
下一步应基于 `design.md` 与本文档生成 phase 编排或选择第一个 phase，先讨论细化对应设计章节，再进入
handoff implementation-ready plan。
