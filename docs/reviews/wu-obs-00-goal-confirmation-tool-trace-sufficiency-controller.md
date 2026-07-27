# WU-OBS-00 Goal Confirmation：Tool Trace 日常分析充分性

## 1. Gate 与结论

- Work Unit：`WU-OBS-00` Tool Trace Analyzer。
- 类型：GitHub Issue 70 对应的 observability / debug tooling issue。
- Gate：`goal confirmation`。
- 设计真源：`docs/host/design.md`。
- 总控真源：`docs/host/issues-implementation-control.md`。
- Controller 结论：`analyzer-ready`。
- Goal confirmation decision：`pass / awaiting-user-confirmation`。
- Blocking open questions：None。

当前 Tool Trace contract、producer 与 projection 已足以支撑日常 analyzer。现存工作主要是 analyzer
自身的输入发现、hot / cold / payload descriptor 解析、聚合、完整性校验、Host / Engine / Tool
归因和 limited-signal 呈现；没有真实证据要求先修改 Tool Trace producer、EventLog schema 或
Host / Engine 状态机。

`analyzer-ready` 不表示每个罕见事件在当前 workspace 都已有真实运行样本，也不表示单独一份 cold
JSONL 可以恢复所有外移 payload。Analyzer 必须区分 cold-only 输入与可解析 hot store / payload
descriptor 的目录输入，对无法证明的事实明确输出 limited signal，禁止 fallback、猜测或 loose
parsing。

## 2. 动机与第一性原理判断

动机成立。生产系统已经生成 Tool Trace hot row、cold JSONL 与 payload descriptor，但当前没有
operator-facing analyzer。人工排障仍需直接阅读 JSON、查询 SQLite、理解 EventLog 与 projection
代码，无法稳定产出 Host / Engine / Tool 分层归因。

这个问题不是“缺一条方便命令”这么轻，也不是要新建第二套 trace 真源。正确边界是：

1. EventLog 继续拥有 canonical fact；
2. Tool Trace 继续是 committed EventLog 的 read-only projection；
3. payload resolver 继续拥有 ref / digest / size 的完整性解析；
4. Analyzer 只消费这些真源与投影，拥有诊断规则、聚合和报告语义；
5. 报告不是 recovery、resume、memory、dispatch 或 Run / Attempt 状态迁移依据。

## 3. Preflight 与外部状态

- 分支基线：`main` 在 fresh fetch 后与 `github/main` ahead 0 / behind 0。
- PR 183：`MERGED`，merge commit=`d829a2ab5393cf4a538ce82194b61c9a53ea2360`。
- 当前工作分支：`work/wu-obs-00`。
- 启动时工作树：clean。
- merge / rebase / cherry-pick / revert：均无进行中状态。
- GitHub Issue 70：`OPEN`。
- GitHub Issue 34：`OPEN`，作为 Issue 70 的 analyzer integrity / large payload 子项。
- GitHub Issue 63：`CLOSED`，OpenAI-compatible provider debugging correlation 已有 owner。
- GitHub Issue 64：`OPEN`，native Anthropic / Claude Code gateway-specific signal 仍需 limited
  signal。
- GitHub Issue 117：`CLOSED`，runner-call reconstruction atoms 已交付。
- GitHub Issue 119：`OPEN`，由本 WU 的 analyzer 需求裁决 usage observation correlation。

## 4. 样本与验证来源

### 4.1 当前 workspace 真实生产样本

- Cold JSONL：
  `workspace/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl`
- Hot store：
  `workspace/.dayu/host/dayu_host.sqlite3`
- 样本规模：9 条 cold lines、9 条 hot rows、9 个唯一 `event_id`。
- 事件覆盖：
  - `RUNNER_CALL_INPUT_ASSEMBLED` × 2；
  - `USAGE_REPORTED` × 2；
  - `TOOL_CALL_REQUESTED` × 1；
  - `TOOL_AWAITING` × 1；
  - `RUN_WAITING` × 1；
  - `TOOL_RESULT_ACCEPTED` × 1；
  - `RUN_SUCCEEDED` × 1。
- 完整性抽查：
  - 9 条 `line_digest == cold_trace_digest`；
  - 按当前 canonical JSON 规则重算 9 条 `line_digest`，mismatch=0；
  - hot / cold 的 `event_id + cold_trace_ref + cold_trace_digest` mismatch=0；
  - hot row / cold line source key 无重复。

这组样本直接证明了请求参数、等待、accepted result、业务可读结果、usage pressure、runner-call
manifest ref 和 resume 后输入投影链路。

### 4.2 既有 production-wiring 运行样本

`workspace/tmp/**/.dayu/artifacts/tool-trace/tool-trace-cold.jsonl` 中的既有 public smoke / real-run
产物用于补充观察：

- 182 条 `RUNNER_CALL_INPUT_ASSEMBLED`；
- 132 条 `USAGE_REPORTED`；
- 83 条 `TOOL_RESULT_ACCEPTED`；
- 82 条 `TOOL_CALL_REQUESTED`；
- 42 组 `TOOL_AWAITING` / `RUN_WAITING`；
- 41 条 duplicate decision signal；
- 33 条 bounded readable result 被截断的 signal；
- 1 条带 structured failure metadata 的 `CONTEXT_COMPACTION_FAILED`。

这些样本不替代当前代码验证，也不作为旧 schema 兼容依据；它们只证明真实运行中已有 analyzer
需要处理的重复治理、超长 readable result、context pressure 与 failure signal。

### 4.3 当前 owner-level contract 验证

执行：

```text
source .venv/bin/activate
pytest -q tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py
```

结果：`68 passed in 0.90s`。

这组测试作为真实样本的补充，验证当前 production projection / resolver 对以下罕见或破坏性场景
的 contract：

- provider request id / client correlation id；
- provider diagnostic / provider protocol error；
- partial tool-call signal；
- structured failure metadata；
- tool timing available / missing；
- context compaction pressure；
- large tool arguments payload resolution；
- runner-call manifest / projection resolution；
- payload digest mismatch；
- cold writer failure、rebuild 与 source-key digest conflict。

不得只凭这些测试宣称 trace 充分；本结论同时依赖 4.1 和 4.2 的真实运行数据。

## 5. 日常问题充分性矩阵

| 日常问题 | 所需语义 | 当前直接证据 | 状态 | Analyzer 额外 join / 限制 |
|---|---|---|---|---|
| 模型请求了什么工具、业务参数是什么 | tool name、tool call id、accepted canonical arguments、业务可读 query | 真实 `TOOL_CALL_REQUESTED` 的 `trace_summary.tool_request` 直接包含 `tool_name=start_fins_download`、`ticker=COIN`、query / summary text 与 digest 锚点 | `available` | 大 arguments 通过既有 payload resolver 校验；不得只显示 ref / digest |
| Host 接受了什么 request / governance outcome | canonical request、policy decision、duplicate decision / scope / prior refs | canonical event identity；真实 smoke 有 duplicate decision；projection tests 覆盖 `reuse` 与 policy fields | `available` | 无特殊治理时字段为 null，Analyzer 不得把 null 写成拒绝或复用 |
| 工具最终返回了什么 | accepted status、业务可读 details / summary、outcome digest、业务来源状态 | 真实 `TOOL_RESULT_ACCEPTED` 直接包含 `result_status=completed`、下载计数和 result summary；其它真实样本包含 available / unavailable business source | `available` | 完整外移 payload 通过 resolver；cold-only 输入只能报告 bounded summary |
| 哪些结果进入 memory / 下一轮上下文 | accepted tool fact 与实际 runner input projection 的同源 link | 真实 resume runner-call 有 `tool_result_message` projector metadata、manifest ref / digest 和完整 input projection ref / digest | `partial` | 需要解析 digest-verified manifest / projection；cold-only 文件缺 payload 时必须 limited signal。这是 Analyzer join 工作，不是 producer 缺口 |
| 等待 / 恢复链路发生了什么 | tool call、awaiting、Run waiting、accepted wait result、新 Attempt runner-call | 真实样本按 sequence 提供 `TOOL_AWAITING -> RUN_WAITING -> TOOL_RESULT_ACCEPTED -> RUNNER_CALL_INPUT_ASSEMBLED(host_resume)` | `available` | 只按 typed ids / refs / event type 关联，不从时间戳或字符串猜状态 |
| 重复调用为何被允许、提示、复用或阻断 | duplicate key、decision、scope、policy decision、prior refs | 真实 smoke 有 duplicate signal；current owner tests 覆盖 `reuse` | `available` | Analyzer 只解释已有 decision，不重新实现 duplicate policy |
| 工具失败与异常延迟归谁 | structured failure kind、bounded details、retryability、tool timing status / duration | production projection 明确投影 `failure_metadata` 与 `tool_timing`；真实 sample 包含 compaction failure，真实 tool sample明确 `missing_tool_result_meta` | `available` | timing 缺失必须报告 limited signal，不从 occurred_at 差值反推 duration |
| 截断后是否正确续读 | structured truncation fact、cursor / scope token、后续 `fetch_more` call | producer / projection contract 与 owner tests存在；真实样本有 readable-summary truncation，但当前样本没有真实 tool truncation fact | `partial` | 区分业务 truncation 与 Tool Trace 自身 bounded text；无真实 truncation signal时不得宣称“未截断” |
| provider / protocol 问题如何报障 | provider-native request id、client correlation id、partial tool call、raw diagnostic ref | production projection / query tests覆盖 terminal + protocol chain；Issue 63 已完成 | `partial` | 当前 workspace 无真实 protocol-error sample；native Anthropic / Claude Code gateway signal按 Issue 64 标记 limited |
| context pressure / compaction 为何发生 | usage pressure、policy / estimator refs、compaction failure category | 真实 `USAGE_REPORTED.context_pressure` 与真实 `CONTEXT_COMPACTION_FAILED` sample | `available` | Usage 只作为 post-call observation；不从 iteration id 猜 provider request identity |
| runner 实际看到了什么 | manifest、message count / role digest、projection payload、tool schema snapshot | 真实 runner-call summary和 resolver contract | `available` | 只有解析完整 typed manifest / projection 后才可下结论；缺 ref / digest 时 fail closed |
| trace 自身是否可信 | JSONL parse、line digest、cold digest、source key、hot/cold identity、payload ref / digest | 真实 9 行完整性重算通过；production resolver / failure tests覆盖 mismatch | `available` | corrupt / missing fixture属于 Analyzer tests；Analyzer 不修复或覆盖原 trace |
| payload 是否过大 | cold line size、runner projection size、descriptor size、source EventLog / resolved payload size、bounded-summary truncation | runner-call projection带显式 size；payload descriptor resolver返回 `payload_size_bytes`；真实样本有超长 result summary | `partial` | cold-only 输入不能总是恢复原始 inline payload size，必须给出 limited signal；目录输入可用 hot store / descriptor 直接度量，禁止按 digest 或截断文本猜大小 |

矩阵中没有 `missing` producer / projection 语义。`partial` 项均已有 typed ref / resolver 路径，或属于缺少
真实罕见样本时必须呈现的 limited-signal 状态；因此不需要在 plan 前新增 Tool Trace producer /
schema completion slice。

## 6. 语义 owner 裁决

- Canonical tool request / result / lifecycle / context facts：EventLog producer 与对应 Host / Engine
  typed contract。
- Tool request arguments：`TOOL_CALL_REQUESTED` request atom owner。
- Tool accepted result：`TOOL_RESULT_ACCEPTED` 与 shared accepted-result projection owner。
- Provider request identity：Engine provider correlation contract；Analyzer 不从 iteration、timestamp 或
  display text 推断。
- Tool timing / failure / partial tool call / context pressure：现有 signal producer contract。
- Hot row / cold JSONL bounded schema：`dayu.host.tool_trace` projection owner。
- Hot query、payload ref / digest / size resolution：`dayu.host.durable.tool_trace` 与 durable payload
  resolver。
- Host / Engine / Tool 分层规则、聚合、优先级、建议动作、Markdown / structured report：
  WU-OBS-00 Analyzer。
- File-only / directory input 的 limited-signal 说明：Analyzer；不得在 adapter、fixture 或报告层用
  fallback 补造缺失事实。

### WU-OBS-00B / Issue 119 裁决

当前 analyzer 只需把 usage observation 作为 run / attempt / execution 下的 post-call context pressure
signal；provider debugging 使用 terminal / protocol diagnostic 主链路的 provider request identity。
不存在把同一个 provider request identity 塞入 `USAGE_REPORTED` 的必要证据。

因此当前裁决是：不扩展 `UsageReportedData`、Host usage payload 或 Tool Trace usage schema；Analyzer
必须保持 usage observation 与 provider debugging terminal chain 分离。`WU-ENG-02-S3-R1` 可在
implementation / closeout 中按这一证据关闭。若后续实现发现一个 Attempt 内多个 provider call
必须做 request-level usage attribution且现有 typed runner-call identity无法证明，再回到 design
gate，不得以顺序或时间戳补偿。

## 7. Goal / Success Signal

目标：

- 交付本地 operator-facing Tool Trace Analyzer；
- 输入当前 Dayu Tool Trace 文件或目录；
- 输出 structured report 与 Markdown（或等价可读格式）；
- 按 Host / Engine / Tool 分层；
- 每条诊断引用直接 trace 证据；
- 覆盖重复调用、失败、protocol error、payload size、truncation / fetch_more、冷热与 payload
  integrity、context pressure 和 vendor debugging block；
- file-only、缺 payload、缺 provider-specific signal 时明确 limited signal。

成功信号：

- Analyzer 可运行且不依赖旧仓库 schema；
- current hot / cold / payload descriptor 均由 typed parser / resolver 读取；
- corrupt / missing / mismatch 输入 fail closed 或产生明确 integrity finding；
- provider-native request id 与本地 run / attempt / trace refs 同报告呈现；
- Issue 64 未交付路径明确 limited signal；
- tests、pyright、覆盖率与相关 README / usage docs 通过；
- WU-OBS-01 可复用同一 analyzer / rules，而不另建平行实现。

## 8. 非目标与不会做的过度设计

- 不修改 Host / Engine 状态机。
- 不把 Analyzer report 变成 durable truth 或新的 projection。
- 不复制旧 `tool_trace_v2` schema、Engine-owned recorder 或 raw payload 布局。
- 不实现 prompt / final answer 反查；由 WU-OBS-01 / Issue 71 承接。
- 不接入真实 provider、外部观测平台、数据库服务或告警平台。
- 不新增通用 rule-engine、plugin framework、DSL、stream processor 或长期存储层。
- 不为 native Anthropic / Claude Code gateway 猜 request id。
- 不把业务财报结论写进 Analyzer。

## 9. Slice 切分约束

Plan 必须遵循 control doc 的 Slice 切分原则：

- 按语义闭环、依赖顺序、失败 / 回滚风险和验证矩阵切分；
- 不按文件、模块或 reviewer ownership 机械切分；
- Analyzer 属于中型跨 parser / diagnostics / operator entrypoint 工作，默认控制在 3-5 个 slices；
- 超过 3 个 slices 必须解释为什么不能合并；
- 每个 slice 必须形成可独立验证的行为闭环；
- 不设置 trace-completion slice，除非 plan 阶段出现新的真实直接证据并先回到 Controller 裁决。

## 10. 下一入口

用户确认本 goal confirmation 后：

1. Controller 将 control doc 的 next entry point 更新为 `plan`；
2. 重新 discovery Agent pane；
3. `/clear` AgentMiMo / AgentDS、`/clear` AgentCodex 仅在各自首次 assigned gate 前执行；
4. 当前下一具体任务只派发给 AgentCodex：生成 code-generation-ready plan；
5. Plan 完成后由 AgentMiMo 与 AgentDS 使用 `/planreview` 并行 review；
6. 禁止任一 Agent commit、push、创建 PR、merge 或自行进入下一 gate。
