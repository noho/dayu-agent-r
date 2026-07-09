# WU-SEMANTIC-OWNERSHIP-01 / P2-E Plan Re-Review — AgentDS

## Review Context

- Reviewer: AgentDS
- Gate: plan re-review
- Plan under review: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-codex.md`（已按 controller adjudication 修复）
- Plan fix artifact: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p2-e-plan-review-controller-adjudication.md`
- Prior review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p2-e-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p2-e-plan-review-ds.md`
- Design ground truth: `docs/engine/design.md`, `docs/host/design.md`, `AGENTS.md`
- Control doc: `docs/host/issues-implementation-control.md`

## Scope

本次 re-review 只验证已修复 P2-E plan 是否完全闭合 controller 接受的 5 个 findings（P2E-PLAN-F01 至 P2E-PLAN-F05）。不做新一轮全量 plan review。

## Controller Findings Closure Verification

### P2E-PLAN-F01: stream heartbeat 正负断言

**Controller 要求：** 普通 `DEBUG` 负向断言必须从可选证据提升为必做 test change；修复后测试必须同时证明 `STREAM_DEBUG_LOG_LEVEL` 能捕获 heartbeat 且普通 `DEBUG` 不能。

**Plan 修复后内容（failure 1, lines 66-68）：**
- 正向断言：使用 `STREAM_DEBUG_LOG_LEVEL` 捕获 heartbeat，且继续确认 response bytes 未丢失。
- 负向断言：使用普通 `logging.DEBUG` 捕获同类流过程时不得出现 heartbeat 记录；不得通过放宽 logger、提升生产日志级别或改 `runner.py` 让测试通过。

**验证：** 正负断言均已成为必做实现要求，负向断言不再是"evidence still needed"。`runner.py` 不可修改的约束已写入 plan。闭合逻辑：heartbeat 生产日志级别为 `STREAM_DEBUG_LOG_LEVEL=9`，低于 `logging.DEBUG=10`，因此 `caplog.at_level(logging.DEBUG)` 天然不捕获——但测试必须显式证明这一点，防止未来有人无意中提升生产日志级别。

**结论：CLOSED。** 无残留缺口。

### P2E-PLAN-F02: wait-resume 诊断优先 + tool-call identity closure

**Controller 要求：** Slice E2 实现第一步必须先诊断 `resume_request.messages`；正常路径断言 `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`，且 `AssistantToolCall.id == 原始 awaiting tool_call_id`、`ToolMessage.tool_call_id == 同一 id`；fallback → 先修 fixture/request atom；旧英文 guidance → 停止并升级 production owner。

**Plan 修复后内容（failure 6, lines 131-146）：**
- 第一步诊断 `resume_request.messages`，记录实际 message types、tool call id、tool name、arguments 与 tool result JSON——已明确（line 131-132）。
- 正常路径断言顺序 `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`——已明确（line 140）。
- `AssistantToolCall.id` 必须等于原 awaiting `tool_call_id`——已明确（line 141）。
- `ToolMessage.tool_call_id` 必须等于同一个 `AssistantToolCall.id`——已明确（line 142）。
- 只有当前中文 fallback guidance 时先修 fixture/request atom——已明确（lines 144-145）。
- 旧英文 guidance 仍出现时停止并升级 production owner——已明确（line 146）。
- 确认测试经 production `DefaultHostToolAwaitingAcceptPort` 写入 request atom / accepted evidence envelope——已明确（line 133）。

**验证：** 诊断顺序、identity closure（双向 tool_call_id 匹配）、fixture 修复优先、旧英文 guidance 的 escalation 路径均已成为必做实现步骤。身份闭环是关键的语义不变量：它证明 resume 重建的是原 tool call 身份，而非泛化的"某个工具调用结果"。缺失这一断言则测试可能接受一个部分正确的 replay（例如包含 tool call 但 id 不匹配）。

**结论：CLOSED。** 无残留缺口。

### P2E-PLAN-F03: purge fixture 专用 cancel request event id + cancelled 覆盖

**Controller 要求：** fixture 修复必须使用专用 cancel request EventLog event id（不能复用任意已有 event）；实现必须检查 `cancelled` 是否在同组 parametrize 中，若是则一并修复。

**Plan 修复后内容（failure 7, lines 160-162）：**
- "为 `cancelling` Run 写入 dedicated cancel request EventLog row（使用专用 event id，不能复用任意已有 event），并把 `cancel_request_event_id` 插入 Run row"——已明确。
- "若相关 parametrize 包含 `cancelled`，同样应用该 durable invariant fix"——已明确。
- 不放宽 schema，不在 purge helper 捕获 CHECK 失败——已明确（line 162）。

**验证：** 专用 event id 约束排除了复用任意已有 event 的"快捷但语义错误"做法。`cancelled` 条件的覆盖检查确保不会漏掉同组 parametrize 中的相同语义缺口。不放宽 schema 和不做 defensive fallback 的约束保护了 durable invariant 的权威性。

**结论：CLOSED。** 无残留缺口。

### P2E-PLAN-F04: E2 split policy 显式化

**Controller 要求：** 若 wait-resume 诊断触发 production work，Slice E2 必须拆分：Host export / purge fixture alignment 独立完成，wait-resume 作为 production-owner follow-up slice 单独处理。

**Plan 修复后内容（Slice E2 stop condition and split policy, lines 202-205）：**
- "如果 wait-resume 诊断触发 production owner，Slice E2 必须拆分：先独立完成 Host export / purge fixture alignment，再把 wait-resume 作为 production-owner follow-up slice 处理；不得让 wait-resume production 风险阻塞已确认的 Host export / purge fixture 测试对齐。"

**验证：** Split policy 已从 stop condition 中的单句提示（原 plan 只说"停止"）升级为显式的拆分策略，明确了拆分后两个 slice 的独立推进顺序和"不得互相阻塞"的约束。该策略位于 plan 的 stop condition 段，implementation agent 在进入 E2 时即可看到。

**结论：CLOSED。** 无残留缺口。

### P2E-PLAN-F05: closeout 记录 export snapshot propagation

**Controller 要求：** implementation closeout 必须显式记录 Engine 和 Host export snapshot 对齐是 test-only alignment，针对既有 design/README public contract，不需要 production/README 变更。

**Plan 修复后内容（Implementation closeout requirement, lines 241-245）：**
- "必须显式记录 Engine `input_projection` / projection export snapshot alignment 与 Host `HostThinkingView` export snapshot alignment 均是测试对既有 design / README public contract 的对齐；生产代码、生产契约和 README 不需要变更。"
- "若 wait-resume 诊断触发 production owner，closeout 必须记录 Slice E2 已拆分，以及 Host export / purge fixture alignment 与 wait-resume follow-up 的边界。"

**验证：** Closeout 记录要求已从 INFO 级建议变为 plan 中的显式实现要求。两条路径（正常对齐完成 / 触发 production owner 拆分）的 closeout 记录内容均已明确。该要求落在 Implementation closeout requirement 段，实现 agent 在 closeout 阶段必然看到。

**结论：CLOSED。** 无残留缺口。

---

## 第一性原理 Owner-Boundary 复核

按照 AGENTS.md 语义所有权约束逐条复核 plan 的 owner boundary 判断：

| 事实 | 产生者 | 校验者 | 持久化者 | 投影者 | Plan 修复落在 |
|---|---|---|---|---|---|
| stream heartbeat 日志级别 | `runner.py` `_iter_response_bytes_with_idle` | `dayu.runtime.log_levels` | 运行时日志 | 测试 caplog | 测试端（capture level 对齐生产日志级别真源）✓ |
| `input_projection` Engine 字段/导出 | `_AsyncAgent` iteration_started | `docs/engine/design.md` | EngineEvent stream | `IterationStartedData` / `engine.__all__` | 测试端（快照对齐已接受 public contract）✓ |
| `HostThinkingView` 导出 | `host/api.py` HostEvent | `dayu/host/README.md` | Host public API | `host.__all__` / `host.api.__all__` | 测试端（快照对齐已接受 public contract）✓ |
| resume request messages | `run_input.py` RunInputBuilder | Host ToolRuntime durable facts | resume_request.messages | LLM context / integration test | 测试端（assertion 对齐 production 协议闭环）；若缺失 durable facts → fixture 修复；若旧英文 guidance → production owner escalation ✓ |
| purge cancelling durable invariant | Host admission / cancel transition | `schema.py` CHECK | Durable Run row | purge precondition | 测试端（fixture 补齐合法 `cancel_request_event_id`）；不放宽 schema ✓ |

所有 5 个 controller finding 的修复均落在正确的 owner boundary。没有任何修复落在下游消费者、展示层或测试夹具中以特例分支掩盖错误语义。

---

## 反例压力测试

### 下游 masking 检查

- **F01:** 测试改为 `STREAM_DEBUG_LOG_LEVEL` 捕获 + `DEBUG` 不捕获，是让测试对齐生产日志级别真源，而非在测试中放宽 capture 来掩盖生产日志级别变更。✓
- **F02:** 测试改为断言协议闭环身份，比旧断言（检查英文 fallback 文本）更严格。如果 fixture 只有 fallback guidance，plan 要求先修 fixture 再改 assertion，而非把 assertion 放宽为接受 fallback。✓
- **F03:** fixture 补 `cancel_request_event_id` 是让 fixture 遵守生产 schema invariant，而非在 purge helper 中做 defensive fallback 来掩盖 fixture 缺陷。✓

### Fixture cheating 检查

- **F02:** 如果 fixture 没有 request atom，plan 要求先修 fixture（注入正确的 durable facts），而非在 assertion 中接受 fallback guidance 或放宽检查。这避免了"fixture 不合法但测试通过"的假阳性。✓
- **F03:** plan 要求专用 cancel request event id，而非复用已有 terminal event。复用 terminal event 会让 fixture 在语法上合法（CHECK 通过）但语义上错误（`cancel_request_event_id` 指向的不是 cancel request）。✓

### Production-contract drift 检查

- **F02:** 如果诊断发现旧英文 guidance 仍在 production 中出现，plan 要求停止并升级 production owner。这防止了"production 已经 drift 但测试按新 contract 写"的假阴性。✓
- **F01/F03/F04/F05:** 这些 finding 不涉及 production contract 变更——生产行为 intended，只是测试滞后。✓

---

## 结论

**pass。**

全部 5 个 controller-accepted findings（P2E-PLAN-F01 至 P2E-PLAN-F05）已在 fixed plan 中完全闭合。每条修复均落在正确的 semantic owner boundary，没有下游 masking、fixture cheating 或 production-contract drift。Plan 已 code-generation-ready。

---

## Residual Implementation Risks

以下风险属于实现阶段风险，不是 plan 缺陷。不需要修改 plan，但 implementation agent 和 reviewer 应关注：

### R1: wait-resume fixture 诊断复杂度（MEDIUM risk to Slice E2）

`test_local_awaiting_tool_manual_resolve_resumes_run` 的 fixture chain（`_seed_active_integration_run`）可能不完全经过 `DefaultHostToolAwaitingAcceptPort` 的 production 路径创建 request atom 和 accepted evidence envelope。如果 fixture 需要修复，实现 agent 必须理解完整的 durable write path（`TOOL_CALL_REQUESTED` → `TOOL_AWAITING` → wait record → `TOOL_RESULT_ACCEPTED`），而非简单添加一行数据。Plan 要求 fixture 修复后再迁移 assertion，但未给出 fixture 修复的具体方式——这属于实现细节，不需要在 plan 层面指定。

**建议：** Implementation agent 在 Slice E2 开始时，先单独运行 `_build_resume_request` 的诊断脚本（打印 `resume_request.messages` 的 types/ids/content），将结果记录在 implementation artifact 中，再决定走正常 assertion 迁移路径还是 fixture 修复路径。

### R2: purge fixture 修改对共享 helper 的涟漪效应（LOW risk to Slice E2）

`_insert_run_row` 被多个测试路径使用。如果修改其签名（添加 `cancel_request_event_id` 参数），所有调用方都需要更新。如果只在 `_SeedClosedSessionMatrixOperation` 内部单独 INSERT cancel request event 并直接写 Run row，则不影响其他调用方。Plan 不规定具体实现方式，两种方案均可行。

**建议：** Implementation agent 优先选择最小侵入方案（在 `_SeedClosedSessionMatrixOperation` 的 shortcut 路径中单独处理），除非共享 helper 修改更清晰且不引入 regression。

### R3: stream heartbeat 负向断言的假通过风险（LOW risk to Slice E1）

负向断言（`logging.DEBUG` 不捕获 heartbeat）只有在 heartbeat 确实触发的条件下才有效。如果测试重构导致 heartbeat 在负向断言路径中未触发（例如 idle timeout 设置过短或 SSE stream 提前结束），负向断言会"假通过"——不是因为 log level gating 正确，而是因为 heartbeat 根本没产生。

**建议：** Implementation agent 应确保正负断言在相同或等效的 stream idle 条件下执行。正向断言先确认 heartbeat 产生，负向断言再确认 `DEBUG` 不捕获它。可以考虑在同一测试函数内先做正向（`STREAM_DEBUG_LOG_LEVEL`），再重复等效流过程做负向（`logging.DEBUG`）。

### R4: implementation agent 遵守 stop condition 的纪律风险（LOW risk to Slice E2）

Plan 的 stop condition 要求实现 agent 在发现特定条件时停止并报告，而非继续机械执行。如果 implementation agent 忽略 stop condition 直接改 assertion，可能掩盖 production regression。此风险无法通过 plan 修改消除——它取决于 implementation agent 的执行纪律。

**建议：** Reviewer 在审查 implementation artifact 时，必须验证 wait-resume 诊断步骤已被执行且结果已记录，而非直接跳到 assertion 变更。

### R5: broad suite 其他 stale snapshot（LOW residual）

Plan 的 regression validation 覆盖了 `tests/engine` 和 `tests/host` 的 broad suite。但 P2-D 的 public contract expansion 可能还影响了其他未在 7 个 targeted failure 中出现的 snapshot/contract locking 测试。此风险较低，因为 controller 的 broad validation 已经跑了完整 suite 且只报告了这 7 个失败。

**建议：** Implementation closeout 时确认 broad suite 无新增失败，无需 plan 修改。

---

## Evidence Verification Log

| Plan claim | Direct evidence | Result |
|---|---|---|
| F01 正负断言均为必做要求 | plan lines 66-68 | Confirmed |
| F02 第一步诊断 + identity closure (双向 tool_call_id) | plan lines 131-146 | Confirmed |
| F03 专用 cancel request event id + cancelled 覆盖 | plan lines 160-162 | Confirmed |
| F04 E2 split policy 显式化 | plan lines 202-205 | Confirmed |
| F05 closeout 记录 export snapshot propagation | plan lines 241-245 | Confirmed |
| 所有修复落在 test owner boundary | plan 各 failure 的 Proposed fix location | Confirmed |
| 无 production code change 要求 | plan 各 failure 的 Semantic owner boundary | Confirmed |
| Design ground truth 支撑所有 public contract claims | `docs/engine/design.md` §2, §14; `dayu/host/README.md` | Confirmed (by MiMo/DS initial review, unchanged in fix) |

---

## Final Verdict

**pass。** Plan 已 code-generation-ready。Implementation 可以 proceed 到 Slice E1 和 Slice E2。
