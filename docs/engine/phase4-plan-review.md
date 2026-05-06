# Phase 4 Plan Review

> 状态：历史 review 记录，不再作为进入实施的 gate。
>
> 本 review 对当时的 `docs/engine/phase4-plan.md` 草案有效；但后续总控已决定取消当前阶段独立 Phase 4 实施，将 `suspend` / `run_suspended` / `ToolAwaitingOutcome` 转入 GitHub issue #4 跟踪，并在 issue #4 下拆分子 issue 后重新计划。因此本文只保留为历史审查记录，不能作为当前实施放行依据。

## 结论

通过，可以进入 Phase 4 实施准备。

本次只审查 `docs/engine/phase4-plan.md` 及必要上下文，没有实施代码，没有修改生产代码或测试代码，没有 commit / push。

计划整体符合 Phase 4 目标：只落地 `ToolAwaitingOutcome -> tool_awaiting -> run_suspended` 主链路，不实现 Host wait record、monitor、resume、RemoteProxy / RPC、HostEvent / WorkerEvent、ToolRegistry / ToolRuntime、context budget、continuation、truncation/fetch_more、provider_state/reasoning issue #10。计划已细化到 handoff 级，后续实施 Agent 可以据此接手。

## Findings

### 1-重要-批量 `tool_call_requested` 前缺少重复 `tool_call_id` 预检约束

- **位置**: `docs/engine/phase4-plan.md` §8.2、§11
- **问题**: 计划要求先为本批所有 tool call 发出 `tool_call_requested`，再按序执行工具，以保证 awaiting 时 Host 可观察完整 tool call batch。这一方向成立，但计划没有显式约束“批量发出 requested 前必须先完成整个 batch 的重复 `tool_call_id` 预检”。当前 Phase 3 实现是在逐个 call 上边检查、边发事件、边执行；Phase 4 若机械改成先全部发 requested，可能在同批存在重复 `tool_call_id`，或与历史已执行 id 冲突时，先产出污染性的 `tool_call_requested`，再失败。
- **后果**: Host 后续可能把非法 batch 误认为可恢复事实，等待记录或恢复上下文会被重复 id 污染；同时 Phase 3 已确认的 duplicate guard 语义可能回退。
- **建议**: 实施时在 `tool_call_requested` 批量发出前，先对按 `index_in_iteration` 排序后的整个 batch 做 preflight：
  - 检查同批重复 `tool_call_id`。
  - 检查是否已存在于 run 内 `_executed_tool_call_ids`。
  - 命中重复时保持 Phase 3 duplicate guard 收口：不执行工具、不发 `tool_awaiting`、不发 `tool_result_accepted`，只走唯一 terminal `run_failed("duplicate_tool_call_id")` 并关闭 Runner。
  - 增加 Phase 4 测试覆盖“重复 id 不因批量 requested 改造而提前污染事件流”。

## Handoff 可执行性评价

可执行性高。

计划具备实施 Agent 需要的关键 handoff 信息：

- 文件级改动清单明确，集中在 `dayu/engine/agent.py`、Engine event contracts、Agent run outcome 映射、测试与 README 触发同步。
- 契约变化明确，尤其是 `ToolAwaitingData` 补齐 `name/index_in_iteration/snapshot`，且禁止把显式事实塞入 metadata。
- 状态机边界清楚：awaiting 后不注入 tool message、不进入下一轮 Runner、不触发连续失败批次、不触发 max iteration force-answer、不伪装为 failed/cancelled/final answer。
- 完整 tool batch 可观测性已被作为核心目标写入计划，并给出推荐执行顺序。
- 测试清单覆盖 terminal 唯一性、Runner close、`run_agent_and_wait` suspended outcome、取消优先级、batch 完整观测、max_iterations / consecutive failed batches 交互。
- Review gate、停止条件、验证命令和实施汇报格式足够明确。

上述 finding 属于实施前需要显式传达给实施 Agent 的重要补强点，不阻塞进入 Phase 4 实施准备。

## 残余风险与待确认项

1. `tool_awaiting` 已发出后、`run_suspended` 前若 cancellation 命中，计划选择 cancellation 优先且 terminal 唯一。这是合理选择，但实现时要用测试固定，避免双 terminal。
2. Host resume 输入路线仍未确定。Phase 4 只输出足够事件事实，不新增 resume API，这个边界合理；后续 Host phase 需要单独设计。
3. `ToolAwaitingData` 字段扩展、批量 `tool_call_requested` 先发再执行、`RunSuspendedData.reason="tool_awaiting"` 三项建议进入实施前总控/用户确认。
4. README 触发规则已被计划覆盖。实施时只允许同步当前已落地事实，不得写 Host wait record、monitor、resume 或 Remote 能力已实现。

## 审查范围

已阅读：

- `AGENTS.md`
- `docs/engine/design.md`
- `docs/host/design.md`
- `docs/engine/migration-plan.md`
- `docs/engine/phase4-plan.md`
- `dayu/engine/agent.py`
- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/contracts/tool_executor.py`
- `dayu/contracts/tool_result.py`
- 相关 Phase 2 / Phase 3 awaiting、duplicate、`run_agent_and_wait` 测试位置

未运行测试或 pyright；本次是计划文档 review，未修改代码。

---

## 增量复审

### 增量上下文

在首轮 review 通过后，`docs/engine/phase4-plan.md` 追加了两类内容：

1. **command line awaiting smoke**（§6.1 `utils/smoke_async_agent_awaiting.py`、§10 Slice G、§12 验证命令、§16 待确认项 #7）：新增命令行 smoke 脚本，使用一个 `ask_user_echo` 类极小 command line tool，ToolExecutor 在命令行读取用户输入后返回 `ToolAwaitingOutcome`，验证 `tool_awaiting -> run_suspended` 边界；不实现 resume，不把用户输入注入回 Engine。
2. **duplicate tool_call_id preflight**（§8.2 推荐执行顺序、§10 Slice D、§11 测试清单 #26/#27、§14 停止条件）：在批量发出本批所有 `tool_call_requested` 前，对整个 batch 做 duplicate id 预检；重复时不发本批 requested、不执行工具、不发 awaiting/result，只以 `run_failed("duplicate_tool_call_id")` 收口。

本轮增量复审只针对上述新增内容，不重复首轮 review 已确认的结论。

### 增量结论

**增量通过。**

两类新增内容均符合 Phase 4 边界，未偷跑 Host 能力，与 Phase 3 已确认语义相容，handoff 信息充足。Phase 4 plan 当前版本可以进入实施准备。

### 增量 Findings

#### F1-建议-smoke 脚本 safe_event_summary 需覆盖新事件类型

- **位置**: `docs/engine/phase4-plan.md` §10 Slice G
- **问题**: 计划要求 smoke 脚本"打印关键 EngineEvent，包括 `tool_call_requested`、`tool_awaiting`、`run_suspended`"。当前 `utils/smoke_async_agent_tool_call.py` 中的 `safe_event_summary` 函数只覆盖 `TOOL_CALL_REQUESTED`、`TOOL_RESULT_ACCEPTED`、`FINAL_ANSWER`，不识别 `TOOL_AWAITING` 和 `RUN_SUSPENDED`。新增 smoke 脚本要么复用并扩展该函数，要么自建事件摘要。
- **风险**: 低。不阻塞 Phase 4 边界，但实施时若遗漏会导致 smoke 输出丢失关键事件信息，降低验证有效性。
- **建议**: 实施时在 smoke 脚本中显式覆盖 `tool_awaiting`（打印 `iteration_id`、`tool_call_id`、`name`、`await_spec`）和 `run_suspended`（打印 `reason`），确保 smoke summary 能验证完整 suspended 链路。可在 Slice G 验收条件中补充"smoke 输出包含 `tool_awaiting` 和 `run_suspended` 事件摘要"。

#### F2-建议-duplicate preflight 失败后的行为测试应更显式

- **位置**: `docs/engine/phase4-plan.md` §11 测试清单 #26/#27
- **问题**: 测试清单 #26/#27 只写了"同批/跨批重复 `tool_call_id` 时，duplicate preflight 在任何本批 `tool_call_requested` 前失败"。§8.2 和 Slice D 验收条件已补充了"不发出任何本批 `tool_call_requested`、不执行工具、以 `run_failed("duplicate_tool_call_id")` 收口"，但测试清单本身未逐条覆盖 preflight 失败的三个关键断言：(a) 本批零个 `tool_call_requested` 事件；(b) 本批零个工具执行；(c) `run_failed` terminal 唯一且 error_code 正确。
- **风险**: 低。Slice D 验收条件已明确这些行为，但测试清单是实施 Agent 的直接检查表，逐条列出可减少遗漏。
- **建议**: 实施时在 `test_agent_phase4_awaiting.py` 中为 duplicate preflight 新增至少一个测试，同时断言：(a) 事件流中不含本批 `tool_call_requested`；(b) `ToolExecutor.execute` 未被调用；(c) 唯一 terminal 为 `run_failed("duplicate_tool_call_id")`。可在 Slice D 验收条件中补充此测试描述。

#### F3-观察-smoke 脚本在 utils/ 目录下无需测试覆盖

- **位置**: `docs/engine/phase4-plan.md` §10 Slice G、`CLAUDE.md` 测试与验证
- **观察**: `CLAUDE.md` 明确 "`dayu/render/` 和 `utils/` 下的脚本默认无需测试、无覆盖率要求"。新增 `utils/smoke_async_agent_awaiting.py` 符合此约束，无需为 smoke 脚本本身编写单元测试。计划 §12 已说明"该 smoke 不属于自动测试，不要求覆盖率"，与项目约束一致。
- **结论**: 无问题。

### 边界合规逐项检查

| 检查项 | 结论 |
| --- | --- |
| 仍符合 Phase 4 只落地 `ToolAwaitingOutcome -> tool_awaiting -> run_suspended` 的边界 | 通过。smoke 只验证该边界，duplicate preflight 是 batch 执行守卫，不引入新 outcome 或新 terminal。 |
| 未偷跑 Host wait record / monitor / resume / RemoteProxy/RPC / HostEvent/WorkerEvent / ToolRegistry/ToolRuntime | 通过。smoke 明确"不实现 Host resume"；duplicate preflight 是 Engine 内部 batch 守卫，不涉及 Host 治理。 |
| smoke 未把用户输入注入回 Engine / 未伪装成 resume | 通过。§10 Slice G 明确"不得在 Phase 4 内把它注入回 Engine 或伪造 resume"；用户输入只在脚本层打印。 |
| duplicate preflight 与 Phase 3 duplicate guard 相容 | 通过。Phase 3 已有 `_executed_tool_call_ids` 跨批检查（agent.py:832）；Phase 4 把该检查提前到 batch preflight，语义一致且更严格（不发 requested 即失败），不回退 Phase 3 行为。 |
| duplicate preflight 与批量 `tool_call_requested` 完整可观察性相容 | 通过。preflight 失败时不发本批任何 requested，Host 不会看到半成品 batch；preflight 通过后全部 requested 先发出，Host 可观察完整 batch。 |
| duplicate preflight 与 Host 后续 wait record 事实要求相容 | 通过。preflight 是守卫非法 batch，合法 batch 的完整事实仍通过 `tool_call_requested` + `tool_awaiting` 输出给 Host。 |
| 已有足够测试 / 验证 / 停止条件 / handoff 指引 | 通过。§11 #26/#27 覆盖 preflight；§10 Slice G 验收覆盖 smoke；§12 验证命令包含 smoke；§14 停止条件包含"无法在批量 `tool_call_requested` 前完成 duplicate preflight"。 |
| 未违反 README 默认约束或 utils 脚本测试覆盖例外 | 通过。`utils/` 脚本无测试覆盖要求；smoke 脚本触发 README 更新为根 README（`utils/` 变化），但计划 §10 Slice F 已限定只更新 Engine README 和 tests README，不更新根 README。实际实施时根 README 可选更新（新增 smoke 脚本用法说明），不阻塞。 |

### Handoff 可执行性补充评价

两类新增内容的 handoff 信息充足：

- **duplicate preflight**: §8.2 给出了完整的执行顺序和失败语义；Slice D 给出了文件、任务和验收条件；§11 给出了测试编号。
- **smoke 脚本**: §10 Slice G 给出了工具命名（`ask_user_echo`）、ToolExecutor 行为、输出风格、验收条件；§12 给出了运行命令；§16 #7 列为待确认项。

实施 Agent 可以据此直接接手，无需额外设计决策。

### 残余风险与待确认项

1. **F1 和 F2 属于实施时补强点**，不阻塞进入实施准备。建议实施 Agent 在 Slice G 和 Slice D 中分别补充。
2. `ToolAwaitingData` 字段扩展（首轮 review 残余 #3）、批量 `tool_call_requested` 先发再执行、`RunSuspendedData.reason="tool_awaiting"` 仍建议进入实施前总控/用户确认。
3. 增量新增的 §16 #7（是否同意新增 smoke 脚本）同样建议总控确认。

### 审查范围

增量复审已阅读：

- `docs/engine/phase4-plan.md`（新增 §6.1 smoke、§8.2 preflight、§10 Slice D/G、§11 #26/#27、§12 smoke 验证、§14 停止条件、§16 #7）
- `docs/engine/phase4-plan-review.md`（首轮 review 结论）
- `AGENTS.md`
- `docs/engine/design.md`
- `docs/host/design.md`
- `dayu/engine/agent.py`（当前 Phase 3 duplicate guard、awaiting 拒绝路径）
- `dayu/engine/contracts/engine_events.py`（当前 `ToolAwaitingData` 字段）
- `dayu/contracts/tool_outcome.py`（`ToolAwaitingOutcome` 定义）
- `utils/smoke_async_agent_tool_call.py`（现有 smoke 结构、`safe_event_summary` 覆盖范围）
- `tests/runtime/test_log.py`（已修改，runtime log 测试）

未运行测试或 pyright；本次是计划文档增量 review，未修改代码。
