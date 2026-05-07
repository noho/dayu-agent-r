# P3 Conversation Memory 常规 Code Review

结论：不通过；以下 finding 已由修复 Agent 处理，待复查确认。

## Findings

### [已修复，待复查] Critical：`StartRunRequest.input` 仍可把历史 transcript 旁路写入 `USER_INPUT_ACCEPTED`

- 文件行号：`dayu/host/_run_harness.py:176`、`dayu/host/_run_harness.py:571`、`dayu/host/_run_harness.py:583`
- 问题：`start_run` 通过 `_extract_current_user_text()` 从 `request.input.messages` 中收集所有 `UserMessage`，并用换行拼成一个 `USER_INPUT_ACCEPTED`。但 `StartRunRequest.input` 的契约仍是 Engine 可消费的 `RunInput(messages=tuple[AgentMessage, ...])`，没有被收窄为“仅当前轮用户输入”。因此调用方只要传入旧的 display transcript / 历史 RunInput，就会把多个历史 user message 合并成“本轮用户输入”，再进入 EventLog、memory projection 和 RunInputBuilder。
- 影响：这破坏 P3 最核心不变量：用户输入虽然表面上 append-before-engine，但 canonical 事实可能已经被 `StartRunRequest.input` 中的展示/历史消息污染。下一轮 memory 与 Engine 输入会把旧 transcript 当成本轮用户事实，等价于仍存在从 `StartRunRequest.input` 旁路投影到 memory / RunInputBuilder 的路径。
- 建议：把 Host 入口显式建模为“当前用户输入”契约，例如新增内部 session run ingress，或在 `start_run` 边界严格校验只允许一个非空 `UserMessage` 且拒绝 system / assistant / tool / 多 user message。测试必须覆盖多消息历史 transcript 被拒绝，而不是只覆盖单条 `UserMessage` 的 happy path。

### [已修复，待复查] Medium：Host-owned failure terminal 不会触发 memory projection

- 文件行号：`dayu/host/_run_harness.py:257`、`dayu/host/_run_harness.py:272`、`dayu/host/_run_harness.py:291`
- 问题：worker / proxy 异常时 `_append_worker_failure_if_needed()` 会 append Host-owned `RUN_FAILED`，但调用方没有把 `terminal_seen` 更新为 true；`finally` 中只有 `terminal_seen` 为 true 才调用 `memory_store.project_run_events()`。因此 Host failure 已经是终态 RunEvent 和 RunResult 真源，却不会把本轮 canonical `USER_INPUT_ACCEPTED` 或 failure 摘要投影进 session memory。
- 影响：终态、EventLog、RunResult 与 memory 投影边界不一致。失败轮次在 EventLog 中终态完成，但下一轮无法从 memory 看到上一轮用户问题或失败事实，和 P3 “terminal 后从 canonical 事件投影 memory”的语义不一致。
- 建议：让 `_append_worker_failure_if_needed()` 返回已 append 的 failure event / terminal 标志，或在追加 Host failure 后统一走 terminal projection 路径。补测试覆盖 proxy 异常后下一轮 builder 能看到上一轮用户输入及中性失败摘要。

### [已修复，待复查] Medium：`USER_INPUT_ACCEPTED` 的 scope 是开放字符串，且投影忽略事件内 scope

- 文件行号：`dayu/host/contracts.py:121`、`dayu/host/contracts.py:135`、`dayu/host/_conversation_memory.py:785`、`dayu/host/_conversation_memory.py:790`
- 问题：`UserInputAcceptedData.scope` 使用 `str`，不是封闭 scope 类型；同时 `_provenance()` 固定写入 `MemoryScope.SESSION`，没有从事件 data 中读取或校验 scope。虽然当前 draft helper 只写 `"session"`，但 canonical event data 本身允许任意字符串，projection 也不会发现 scope mismatch。
- 影响：P3 声称类型上预留 direct user / group / project / user scope，但当前 canonical 用户输入事实并没有强类型约束。未来扩展 scope 时容易出现 EventLog scope 与 memory provenance scope 分叉。
- 建议：在 public contracts 中定义封闭 scope enum 或专门的 `UserInputAcceptedScope`，让 `UserInputAcceptedData.scope` 使用该类型；projection 应从事件 scope 派生 provenance scope，并对非法 scope fail fast。

### [已修复，待复查] Low：P3 测试未覆盖阻塞问题的真实入口形态

- 文件行号：`tests/host/test_phase3_multiturn_smoke.py:159`、`tests/host/test_phase3_boundary.py:151`、`tests/host/test_phase3_conversation_memory_projection.py:170`
- 问题：P3 smoke 和 boundary 测试的 `StartRunRequest.input` 都只构造单条 `UserMessage`；memory projection 测试则直接调用 `user_input_accepted_draft()`，绕开生产入口 `_extract_current_user_text()`。
- 影响：测试证明了 happy path 的 append-before-engine 和 projection，但没有证明实现能阻止历史 transcript / 多 user message / display-derived input 被接纳为 current user。
- 建议：增加真实 `LocalRunHarness.start_run` 路径测试：传入包含 system、assistant、历史 user、当前 user 的 `RunInput` 应被拒绝或只允许明确的 current user 契约；并断言 Engine 未启动、memory 未污染。

## Open Questions

- P3 是否准备继续复用 public `start_run(StartRunRequest(input=RunInput))` 作为 session 多轮入口？如果是，需要明确 `RunInput` 在 Host public 边界现在只能承载当前轮用户消息；如果不是，建议新增更窄的 internal/session ingress，避免让 Engine message list 同时承担用户输入 ingress。
- Host failure 轮次是否应进入 memory 的 recent raw turn？计划里倾向“terminal 后投影 canonical 事实”，但需要明确失败摘要的注入形态，避免把错误当作 assistant conclusion。

## Review Notes

- 已阅读 `docs/host/phase3-plan.md`、`docs/host/design.md` 第 12 节、P3 相关生产代码、P3 tests、`dayu/host/README.md` 与 `tests/README.md` diff。
- 未运行测试或 pyright；本 review 任务限定写入范围仅 `docs/host/phase3-code-review.md`，运行测试可能产生 `.pytest_cache` / `__pycache__` 等额外写入。
- 正向观察：`USER_INPUT_ACCEPTED` 在 happy path 中确实先于 Engine task append，append 失败不会启动 Engine；Host package root 未导出 internal memory store / builder / trace；preview / reasoning 在当前 projection happy path 中被过滤。

## 复查结果

复查结论：不通过。

### 旧 finding 复查状态

- Critical：`StartRunRequest.input` 历史 transcript 旁路污染已修复。`_extract_current_user_text()` 现在只接受一条非空 `UserMessage`，并在 append `USER_INPUT_ACCEPTED` 前拒绝 system / assistant / tool / 多 user message；`tests/host/test_phase3_boundary.py` 已覆盖真实 `LocalRunHarness.start_run` 入口的非法 transcript fail fast。
- Medium：Host-owned failure terminal 不触发 projection 的主问题已修复。`_append_worker_failure_if_needed()` 会返回终态标志，proxy / worker 失败路径会调用 `_project_run_events()`。
- Medium：`USER_INPUT_ACCEPTED.scope` 开放字符串问题已修复。`UserInputAcceptedData.scope` 已改为 `UserInputScope`，projection 通过 `scope_from_user_input_event()` 从事件 data 派生 `MemoryScope` 并对非法 scope fail fast。
- Low：入口污染测试缺口已修复。P3 boundary 测试覆盖空消息、空 user、非 user、多个 user、user + assistant 等历史 transcript 形态，并断言 Engine 未启动、EventLog / memory 未污染。

### Findings

#### [已修复，待复查] Medium：`RunInputBuilder` 未校验 snapshot 与当前用户事件的 session 一致性

- 文件行号：`dayu/host/_run_input_builder.py:152`、`dayu/host/_run_input_builder.py:172`、`dayu/host/_run_input_builder.py:178`
- 问题：`DefaultRunInputBuilder.build()` 只校验 `current_user_event` 是 Host-owned canonical `USER_INPUT_ACCEPTED`，随后直接把传入的 `ConversationMemorySnapshot` 内容渲染进 system memory block；它没有校验 `snapshot.session_id == current_user_event.session_id`。collector / trace 使用的是 `current_user_event.session_id`，但 memory 内容来自未校验的 snapshot。
- 影响：当前 `LocalRunHarness` 调用路径传入的是同一 `request.session_id` 的 snapshot，因此 happy path 安全；但 Builder 是独立 Host internal 边界，一旦后续调用点传错 snapshot，会静默把另一个 session 的 memory 注入当前 Engine RunInput，破坏 P3 “不同 session memory 不串读”的隔离语义。这个问题属于边界 fail-fast 缺失，不应只依赖上层调用纪律。
- 建议：在 `RunInputBuilder.build()` 开头校验 snapshot / current event 的 session id 一致，不一致时抛 `ValueError`；补充 builder 单元测试覆盖 mismatched session 被拒绝，且 trace / RunInput 均不产出。

#### [已修复，待复查] Medium：Host-owned failure terminal 已触发 projection，但失败终态事实仍被丢弃

- 文件行号：`dayu/host/_conversation_memory.py:523`、`dayu/host/_conversation_memory.py:533`、`dayu/host/_conversation_memory.py:590`、`dayu/host/_conversation_memory.py:740`、`tests/host/test_phase3_boundary.py:370`
- 问题：修复后 Host failure 会触发 `_project_run_events()`，但 memory projection 实际只把 `USER_INPUT_ACCEPTED` 投成 raw turn，并只读取 `FINAL_ANSWER` 作为 assistant final；`_tool_fact_from_event()` 也只处理 Engine / ToolRuntime tool facts，`HostRunFailedData` / `RUN_FAILED` 会落到 `return None`。现有测试只断言失败轮次的用户输入进入 memory，没有断言失败终态事实或中性失败摘要进入 memory。
- 影响：旧 finding 的“terminal 后投影 canonical 事实”只修到用户输入，失败轮次在 EventLog / RunResult 中是失败终态，但下一轮 memory / RunInputBuilder 看不到“上一轮执行失败”这一 terminal fact。`docs/host/design.md:1299` 写的是默认接纳主 session 的 canonical user / tool / final / terminal facts；当前实现与 terminal facts 语义仍错开。
- 建议：为 Host-owned `RUN_FAILED` 增加中性 failure memory projection，例如独立 terminal fact / tool-like fact / raw turn failure slot，注意不要把 failure 当作 assistant conclusion；同步补测试断言下一轮 builder 可见中性失败摘要。若 P3 明确只要求失败轮次的用户输入进入 memory，则应反向收窄 design / README，避免文档继续承诺 terminal facts。

## 复查说明

- 本次只读审查了 `dayu/host`、`tests/host`、`dayu/host/README.md`、`tests/README.md`、`docs/host/design.md` 与本文件的修复状态。
- 未运行测试或 pyright；按本次任务要求避免产生 `.pytest_cache` / `__pycache__` 等额外写入，除本 review 文档外未修改生产代码或测试。

## 二次复查结果（2026-05-07）

复查结论：通过。

### 本轮新增 Medium 复查状态

- `RunInputBuilder` snapshot / 当前用户事件 session 一致性：已修复。`DefaultRunInputBuilder.build()` 在读取当前 canonical `USER_INPUT_ACCEPTED` 后立即校验 `snapshot.session_id != current_user_event.session_id` 并抛出 `snapshot_session_mismatch`，避免跨 session memory 静默注入；`tests/host/test_phase3_run_input_builder.py` 已覆盖 mismatched snapshot 被拒绝。
- Host-owned failure terminal memory 投影：已修复。`_project_raw_turn()` 对 Host-owned `RUN_FAILED` 生成 `terminal_summary` 与 `terminal_provenance`，producer/trust 使用 `HOST_PROJECTION` / `HOST_OBSERVED`；同一 raw turn 的 `assistant_final` 保持 `None`。RunInputBuilder 下一轮通过 raw turn 摘要输出 `terminal: run_failed...`，没有伪装为 assistant final；`tests/host/test_phase3_conversation_memory_projection.py` 已覆盖 snapshot 与下一轮 system memory block 可见中性失败摘要。

### 旧 findings 回归确认

- `StartRunRequest.input` 历史 transcript 旁路：未回归。入口仍只接受单条非空 `UserMessage`，非法 transcript fail fast，且测试断言 Engine 未启动、EventLog / memory 未污染。
- Host-owned failure terminal 触发 projection：未回归。worker / proxy 异常路径仍会 append Host-owned `RUN_FAILED` 并在终态后投影 run events。
- `USER_INPUT_ACCEPTED.scope` 封闭枚举与 projection scope 派生：未回归。`UserInputScope` 仍为封闭 enum，projection 对非法 scope fail fast。
- P3 真实入口形态测试：未回归。boundary 测试覆盖空消息、空 user、非 user、多 user、user + assistant 等入口污染形态。

### 验证

- 已运行：`source .venv/bin/activate && PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider tests/host/test_phase3_run_input_builder.py tests/host/test_phase3_conversation_memory_projection.py tests/host/test_phase3_boundary.py`，结果 28 passed。
- 已运行：`source .venv/bin/activate && pyright`，结果 0 errors / 0 warnings / 0 informations。
- 本轮除追加本复查记录外，未修改生产代码或测试。
