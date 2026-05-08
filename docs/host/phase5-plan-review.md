# Host P5 Plan Review

## 结论

不通过。

P5 的总体动机成立：在 P6+ 生产治理前，用单进程、单调用方、顺序多轮 smoke 把 P1-P4 已落地能力串起来，是合理且必要的 guard。计划也基本守住了 no-full-governance 边界，没有把 `client_request_id` 幂等、同 Session active Run 仲裁、持久恢复、Outbox 或 audit hard-gate 当作 P5 必做项。

阻断点是：计划主路径把 `fetch_more completed` 事实安排在 turn 1 terminal 之后，但当前 P2/P4 实现明确禁止 terminal 后追加补读事实。这个错位会让核心测试和 smoke 无法按计划实现，也容易诱导迁移 Agent 为了通过 P5 去破坏既有 terminal guard。

## Findings

### [已修复] P0 阻断：P5 主路径要求 terminal 后产生 fetch_more completed 事实，和当前 Host 契约直接冲突

引用：

- `docs/host/phase5-plan.md:109` 的默认纵向路径先写入 `RunEventStore.append(final terminal)`，随后才调用 `get_tool_fetch_more_handle` 与 `fetch_more_tool_result`，并声称会 `RunEventStore.append(fetch_more requested / completed 或 typed failure)`。
- `docs/host/phase5-plan.md:363` 到 `docs/host/phase5-plan.md:368` 的实施步骤要求 turn 1 `terminal succeeded` 后再补读一次，并让 turn 2 断言上一轮 `fetch_more fact/source cursor` 进入 RunInput。
- `docs/host/phase5-plan.md:396` 到 `docs/host/phase5-plan.md:400` 的测试清单要求 `fetch_more completed` 有 event cursor，同时旧 cursor 再用失败。
- 但同一计划在 `docs/host/phase5-plan.md:211` 又承认 terminal 后 fetch_more 应返回 typed failure 或按 P2 当前契约处理，不伪造审计事实。
- 当前代码契约与测试证据一致：`dayu/host/_event_store.py:111` 到 `dayu/host/_event_store.py:116` 在 append 前校验 run 未 terminal，`dayu/host/_event_store.py:134` 到 `dayu/host/_event_store.py:138` 记录 terminal cursor，`dayu/host/_event_store.py:327` 到 `dayu/host/_event_store.py:341` 明确 terminal 后 append 抛错。
- `dayu/host/_tool_runtime.py:295` 到 `dayu/host/_tool_runtime.py:302` 中 handle 读取在 terminal run 上直接返回 `run_terminal` failure；`dayu/host/_tool_runtime.py:369` 到 `dayu/host/_tool_runtime.py:379` 中 fetch_more 在 terminal run 上返回 failure 且 `event_cursor=None`。
- `tests/host/test_phase2_tool_runtime_eventlog.py:341` 到 `tests/host/test_phase2_tool_runtime_eventlog.py:394` 已锁定 terminal 后 fetch_more 不追加新 RunEvent。
- `dayu/host/README.md:41` 到 `dayu/host/README.md:44` 也写明 terminal Run 后 `fetch_more_tool_result(...)` 返回 typed failure，不追加新 RunEvent。

影响：

这个问题不是措辞瑕疵，而是 P5 核心 happy path 的时序不可执行。按当前计划写测试时，turn 1 terminal 后无法产生 `TOOL_FETCH_MORE_COMPLETED` event cursor，因此 turn 2 也不可能从 memory projection 看到上一轮 `fetch_more completed` fact/source cursor。若迁移 Agent 为了满足计划去放松 terminal guard 或让 terminal 后补读追加事实，就会破坏 P1.5 append-only terminal 边界和 P2 补读契约，并把 P6/P7 才该讨论的 terminal 后审计语义偷带进 P5。

建议修复：

把 P5 的补读时序改成“terminal 前完成一次成功补读，terminal 后只验证 typed failure 不追加事实”。可执行写法是：

1. 使用 scripted WorkerProxy 或可暂停 fake Engine/tool loop，在工具截断与 cursor issued 已 append、final terminal 尚未 append 时，让测试通过 Host public `get_tool_fetch_more_handle` 和 `fetch_more_tool_result` 成功补读。
2. 成功补读后再让 worker/proxy 继续产出 final terminal，并等待 memory projection。
3. turn 2 再断言上一轮 canonical user、final、tool truncated/cursor/fetch_more completed facts 与 source cursor 进入 RunInput/trace。
4. 另设一个 terminal 后补读子断言：同一旧 cursor 或剩余 cursor 在 terminal 后返回 `run_terminal` typed failure，`denied=False`，`event_cursor=None`，且 EventLog 事件数不增加。
5. 同步修正 `docs/host/phase5-plan.md` 的架构路径、实施步骤、测试清单、smoke 输出示例和风险段落，避免继续暗示 terminal 后可追加 `fetch_more completed`。

### [已修复] P2 中：README/docs 同步清单未显式要求清理当前文档中的 P3/P4 事实矛盾

引用：

- `docs/host/phase5-plan.md:77` 把 `docs/host/design.md` 第 9、11、12 节与 `dayu/host/README.md` 定义为当前已落地边界的文档真源。
- `docs/host/design.md:1006` 到 `docs/host/design.md:1100` 已写明 P4 context overflow compact retry 当前落地边界。
- 但 `docs/host/design.md:1467` 到 `docs/host/design.md:1483` 的 “P3 最小落地与后移能力” 仍写着当前未落地包含 `context overflow compact / retry`。
- `tests/README.md:67` 到 `tests/README.md:70` 的 Host 小节开头仍称覆盖 “Host P3 最小 Run harness”，但同一节 `tests/README.md:97` 到 `tests/README.md:104` 已列出 P4 context compaction 覆盖。
- P5 计划的 README/docs 同步只要求新增 P5 路径与命令，见 `docs/host/phase5-plan.md:481` 到 `docs/host/phase5-plan.md:497`，没有明确要求清理这些旧事实冲突。

影响：

这不会单独阻塞代码实施，但会削弱 P5 文档收口的可信度。P5 实施后如果只追加 “P5 已串通” 段落，而不清理旧的 “context overflow compact / retry 当前未落地” 表述，review Agent 后续会看到同一文档同时声称 P4/P5 已落地和未落地，容易把已落地治理误判成 bug，或把未落地能力当作当前事实。

建议修复：

在 P5 plan 的 README/docs 同步段增加明确清理项：

- 更新 `docs/host/design.md` 时，必须同步清理或限定 `12.10 P3 最小落地与后移能力` 中的旧口径，例如改为 “P3 当时未落地；P4 已落地 context overflow compact retry”。
- 更新 `tests/README.md` 时，把 Host 小节总述从 P3 口径调整为当前 P4/P5 事实，新增 P5 integration guard 后避免标题级总述继续落后。
- 文档 review 时专门检查旧术语、旧阶段状态和当前事实是否并存。

## 已通过项

- 目标/非目标基本准确，明确限定为单进程、单调用方、顺序多轮，不把 P7+ lifecycle governance 放进 P5。
- 文件清单总体聚焦，生产代码修改被限定为发现真实 P1-P4 bug 或必要 observability 缺口时的小范围修复。
- 测试方向覆盖了语义与实现逻辑差异，包括 `USER_INPUT_ACCEPTED` 唯一性、preview/reasoning 隔离、compact retry 是 internal attempt、敏感输出过滤。
- 验证命令包含新增 P5 测试、`tests/host`、`tests/engine`、`pyright` 与手工 smoke。
- 停止条件足够清晰，尤其是需要新增 public API、改变 Engine compact 边界、实现 P7+ 治理或只能手工构造 facts 时必须停止。

## 通过条件

修复 P0 阻断 finding 后可重新进入 plan review。P2 文档同步 finding 建议在同一次 plan 修订中补齐，避免 P5 实施后再产生文档事实冲突。

## 复审结论

通过。

本次复审只确认前一次 plan review 的 findings 是否已在计划层修复，不评价尚未实施的 P5 代码。

- 成功 `fetch_more` 的时序已改为 owner run terminal 前完成：P5 默认纵向路径要求在 `pause before final terminal` 后、`release fake WorkerProxy / EngineWorker continuation` 前调用 `get_tool_fetch_more_handle` 与 `fetch_more_tool_result`，并 append `fetch_more requested / completed`；terminal 后补读被限定为 `run_terminal` typed failure、`denied=False`、`event_cursor=None`、EventLog count unchanged。该口径与当前 `InMemoryRunEventStore` terminal guard 以及 `InMemoryToolRuntime` terminal 后失败契约一致。
- P5 主用例已强制真实 `InMemoryToolRuntime` 参与：计划明确同一个 `LocalRunHarness`、`InMemoryRunEventStore`、`InMemoryToolRuntime` 与 memory store 必须参与主路径，cursor 必须由 `InMemoryToolRuntime.execute_tool_call()` 按 `ToolTruncateSpec` 生成，fake WorkerProxy 不得手写 `ToolResultTruncatedData` / `ToolCursorIssuedData` 冒充 tool runtime facts。
- `pinned_state` / stable layer 已纳入普通第二轮与 compact retry 观察点：计划要求 turn 2 RunInputBuilder 同时看到 fixture 预置的 pinned_state / task frame 与上一轮 recent raw turn；compact retry 第二次 attempt input 必须同时保留 caller system prompt、当前 user、pinned_state、必要 tool fact / evidence anchor / source cursor。
- docs 同步清单已要求清理旧事实口径：`docs/host/design.md` 更新项明确要求同步清理或限定 `12.10 P3 最小落地与后移能力` 中关于 context overflow compact / retry 的旧口径；`tests/README.md` 更新项明确要求将 Host 小节总述从 P3 口径调整为当前 P4/P5 事实。

未发现新的阻断 finding。P5 可进入实施，但实施 review 仍需按计划核验真实测试是否确实走同源 EventLog / ToolRuntime / memory / compact 路径，而不是只满足文档措辞。
