# Host P5 OLD / NEW 纵向语义 Review

## 结论

不通过。

P5 的动机成立：P1-P4 已经落地 EventLog、ToolRuntime、Conversation Memory / RunInputBuilder 与 context compact，各自测试不能证明它们在一次财报分析多轮会话中同源协作。P5 也正确限定为单进程、单调用方、顺序多轮 smoke，不应偷跑 P7+ 生产治理。

但当前 plan 存在一个阻断级语义矛盾：计划要求第一轮 terminal 后再补读 `fetch_more`，同时又要求第二轮看到 `fetch_more completed` fact；这与当前 P2 / P1.5 的 terminal guard 直接冲突。若不修正，P5 只能证明 `run_terminal` typed failure，不能证明 OLD truncate / fetch_more 的成功补读、next cursor 与 memory 接续在同一纵向路径中成立。

## Findings

### 1. [已修复] [阻断] terminal 后补读顺序与 P2 terminal guard 冲突，无法证明 fetch_more fact 进入下一轮 memory

引用：

- `docs/host/phase5-plan.md:119-127`：默认纵向路径写成 turn 1 先 append final terminal / memory projection，再 `get_tool_fetch_more_handle` / `fetch_more_tool_result`，随后 turn 2 的 RunInputBuilder 看见 `fetch_more fact`。
- `docs/host/phase5-plan.md:363-368`：happy path 测试要求 turn 1 terminal succeeded 后再补读一次，并断言 turn 2 RunInput / trace 包含 `fetch_more fact/source cursor`。
- `docs/host/design.md:898-901`：当前设计明确 terminal RunEvent 后的 `fetch_more` 返回 typed failure，且不追加新 RunEvent。
- `dayu/host/_tool_runtime.py:295-302`：`get_tool_fetch_more_handle()` 在 owner run 已 terminal 时直接返回 `run_terminal` failure。
- `dayu/host/_tool_runtime.py:369-379`：`fetch_more()` 在 owner run 已 terminal 时返回 `run_terminal` failure，`event_cursor=None`，不 append `TOOL_FETCH_MORE_COMPLETED`。

影响：

P5 计划当前的主路径无法产生 `TOOL_FETCH_MORE_REQUESTED` / `TOOL_FETCH_MORE_COMPLETED` canonical facts，也就无法让 terminal 后的 memory projection 把成功补读结果投影到第二轮 RunInput。这样 P5 最多证明“terminal 后补读被拒绝”，不能证明 OLD `TruncationManager` / `fetch_more` 的成功补读、旧 cursor single-use、新 cursor lineage 与 Conversation Memory 在同一事实链路里协作。

建议修复：

把 P5 happy path 改成“补读发生在 turn 1 terminal 之前”：

- turn 1 使用 gated fake WorkerProxy 或真实 Engine loop + fake ToolExecutor，先触发长工具结果截断并 append cursor facts。
- 测试 / smoke 消费到 cursor issued 后，在 run 仍未 terminal 时通过 Host public `get_tool_fetch_more_handle()` + `fetch_more_tool_result()` 成功补读。
- 补读完成后释放 fake WorkerProxy 继续产出 final terminal。
- terminal 后再投影 memory，并断言 turn 2 RunInput / trace 看见上一轮 user、final、tool truncation fact、fetch_more completed fact 与 source cursor。
- 保留 terminal 后旧 cursor / run terminal failure 作为单独负例，但不要把它当作成功补读事实链路。

### 2. [已修复] [重要] fake WorkerProxy 边界仍偏宽，P5 必须强制至少一条主用例让 ToolRuntime 真实参与纵向路径

引用：

- `docs/host/phase5-plan.md:28-29`：P5 必须走真实 `LocalRunHarness -> RunEventStore -> ToolRuntime -> ConversationMemoryStore -> DefaultRunInputBuilder -> ContextCompactCoordinator`。
- `docs/host/phase5-plan.md:139-141`：fake 只能模拟 provider stream 与底层业务工具返回值，不能替代 Host 治理组件。
- `docs/host/phase5-plan.md:296-297`：若使用 scripted WorkerProxy，计划允许“额外用现有 P2 / P3 测试或子 case”证明真实 ToolRuntime 路径。
- 当前 P3 smoke 的 `_RecordingProxy` 直接产出 `TOOL_RESULT_ACCEPTED` 与 final：`tests/host/test_phase3_multiturn_smoke.py:52-88`。
- 当前 P4 overflow 测试也主要由 fake proxy 直接脚本化 Engine events：`tests/host/test_phase4_overflow_retry.py:122-162`、`tests/host/test_phase4_overflow_retry.py:690-717`。

影响：

“复用现有 P2 / P3 测试”不足以证明 P5 的同一纵向路径。P2 测试能证明 ToolRuntime 自身可靠，P3/P4 测试能证明 memory / compact 自身可靠，但如果 P5 主测试仍由 scripted WorkerProxy 手写 tool facts，就会回到点状正确：EventLog、ToolRuntime、memory、compact 没有在同一 run / session / event store 中串起来。这个风险正是 P5 要消除的风险。

建议修复：

将 P5 主用例的验收条件写死：

- 至少一个 `test_phase5_sequential_multiturn_stitches_eventlog_toolruntime_memory` 必须使用同一个 `LocalRunHarness`、同一个 `InMemoryRunEventStore`、同一个 `InMemoryToolRuntime`。
- cursor 必须由 `InMemoryToolRuntime.execute_tool_call()` 按 `ToolTruncateSpec` 生成，不能手写 `ToolResultTruncatedData` / `ToolCursorIssuedData`。
- fake WorkerProxy 若不走真实 Engine loop，也必须在模拟工具调用时调用 `ToolRuntimeToolExecutor` 或 `InMemoryToolRuntime.execute_tool_call()`，再把返回 outcome 作为 Engine accepted tool fact 继续流出。
- 现有 P2 / P3 / P4 测试只能作为补充回归，不能替代 P5 主路径证明。

### 3. [已修复] [中] OLD issue #48 的 pinned_state 纵向观察口径还不够明确

引用：

- `docs/host/phase5-plan.md:85-86`：P5 需要观察 OLD conversation memory / issue #48 的 pinned state、tool summary、recent raw turn 与 display/runtime 隔离是否在 NEW 路径中真实接续。
- `docs/host/phase3-plan.md:345-354`：#48 关键不变量要求 `pinned_state` 永远全量进入 RunInputBuilder，不参与 token pool 竞争；recent raw turn 是语义反退化下限。
- `docs/host/design.md:975-984`：当前 P3 builder 会把 pinned_state / task frame、evidence anchors / tool facts、recent raw turns 与 trace 注入运行态输入。
- `docs/host/phase5-plan.md:392-406`：P5 新增测试清单主要断言上一轮 user / final / tool fact / source cursor 与 preview/reasoning 隔离，没有明确要求 pinned_state 在普通第二轮与 compact retry 后都被保留。

影响：

如果 P5 只断言 raw turn + tool fact，OLD issue #48 最关键的 stable layer 不变量没有在纵向 smoke 中被观察到。尤其财报分析多轮追问依赖“当前任务框架、用户约束、已确认对象”这类 pinned state 保护；compact retry 又是最容易丢 stable layer 的路径。P4 单测覆盖 compact 保真，但 P5 plan 没有把它纳入“同一条多轮 smoke”验收。

建议修复：

在 P5 plan 中补一条明确断言：

- P5 fixture 可以用 Host internal memory store / patch 预置 pinned_state 或 task frame，但必须标明这是 P3 已落地 memory slot 的测试种子，不是 public memory edit API。
- 第二轮 RunInput 需要断言 pinned_state / task frame 与上一轮 recent raw turn、tool fact 同时存在。
- compact retry 的第二次 attempt input 需要断言当前 user、caller system prompt、pinned_state、必要 tool fact / evidence anchor / source cursor 同时保留。
- 不要求 P5 自动从用户输入或工具事实抽取 pinned_state；该能力仍是后续 scope，不能为了 smoke 写兼容逻辑或业务语义抽取。

## 通过项

- P5 明确不实现幂等、active run admission、多进程恢复、Outbox、audit hard-gate，符合迁移总控的 no-full-governance 定位：`docs/host/phase5-plan.md:36-49`、`docs/host/phase5-plan.md:271-289`。
- P5 明确 `USER_INPUT_ACCEPTED` 是每个 user turn 的 canonical 真源，并要求 compact retry 不追加第二个用户输入：`docs/host/phase5-plan.md:207-215`。当前实现也符合：`LocalRunHarness.start_run()` 在启动后台 task 前 append `USER_INPUT_ACCEPTED`，compact retry 用 `replace(request, input=compacted_input)` 重建 attempt，不再次 append 用户事件：`dayu/host/_run_harness.py:264-290`、`dayu/host/_run_harness.py:462-597`。
- EventLog append-before-stream 与 per-run cursor 真源清晰，当前 `InMemoryRunEventStore.append()` 在同一锁内分配 cursor、保存事件、通知订阅者，terminal 后拒绝 append：`dayu/host/_event_store.py:99-150`。
- preview / reasoning 隔离已被 P3 / P4 设计与现有测试支撑，P5 把它列为新增语义 guard 是正确的：`docs/host/phase5-plan.md:405-409`、`tests/host/test_phase3_conversation_memory_projection.py:351-384`、`tests/host/test_phase3_boundary.py:476-540`。
- P5 没有要求恢复 OLD Engine 内 compact / retry，也没有恢复 OLD LLM-facing `fetch_more` schema，方向符合 NEW 分层：`docs/host/phase5-plan.md:94-99`。

## 复审建议

修复 Finding 1 后需要复审 P5 plan。复审重点只看三件事：

- 成功 `fetch_more` 是否发生在 owner run terminal 前，并且 completed fact 能在 terminal projection 后进入下一轮 RunInput。
- ToolRuntime facts 是否由真实 `InMemoryToolRuntime` 产生，而不是 scripted WorkerProxy 手写。
- Pinned state / stable layer 是否在普通第二轮与 compact retry attempt 中都有纵向观察点。

## 复审结论

通过。

前一次 OLD / NEW 纵向语义 review 的三个语义 finding 已在 P5 plan 中修复，且 plan review 额外提出的文档同步 finding 也已补齐：

- 成功补读现在发生在 owner run terminal 前，terminal 后只作为 `run_terminal` typed failure 负例，不再要求 terminal 后追加 `fetch_more completed` fact。
- P5 主用例已要求真实 `InMemoryToolRuntime` 按 schema truncate spec 产生 truncation / cursor / fetch_more facts；scripted WorkerProxy 只能做 provider stream / gating，不能手写 ToolRuntime facts。
- OLD issue #48 关注的 pinned_state / stable layer 已进入纵向验收：普通第二轮要同时观察 pinned_state / task frame、recent raw turn 与 tool fact；compact retry attempt 要同时保留 caller system prompt、当前 user、pinned_state、必要 tool fact / evidence anchor / source cursor。
- README / docs 同步清单已要求清理 `docs/host/design.md` 12.10 与 `tests/README.md` 中落后于 P4/P5 的旧事实口径。

未发现新的 OLD / NEW 语义阻断点。P5 后续实施时，仍需用真实纵向测试证明这些约束落到了同一个 run / session / event store 事实链路中。
