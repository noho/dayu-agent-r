# WU-SEMANTIC-OWNERSHIP-01 / R03-S1 Plan Correction Controller Validation

## 1. Verdict

Controller verdict：**READY_FOR_DUAL_PLAN_REVIEW**。

修订仍属于既有 `WU-SEMANTIC-OWNERSHIP-01` / R03-S1，不创建新 WU、新 slice 或第四片。
当前 implementation diff 继续冻结；本 verdict 只授权 AgentMiMo / AgentDS 完整 review 修订计划，
不授权 implementation continuation、code review、commit、S2、S3 或 aggregate。

## 2. Owner 与 root-cause validation

- 直接 producer 缺陷确认：
  `dayu/host/durable/run_transition.py::_waiting_tool_result_event_request` 当前把 fresh
  wait-resolution `TOOL_RESULT_ACCEPTED.execution_id` 写成 `None`。
- 正确 owner 确认：resume 与 terminal transition 均已读取 suspended `AttemptRow` 与
  `WaitRecordRow`；result fact 属于 suspended source Attempt，不属于新 resume Attempt。
- 修订计划只新增 `dayu/host/durable/run_transition.py` 这一 production owner，要求 writer
  使用 source Attempt 的 attempt/execution identity，并在任何 append/state mutation 前校验
  `WaitRecord.execution_id == source_attempt.execution_id`。
- strict consumer equality、descriptor 冷热互斥 guard 与 governance-only
  `TOOL_AWAITING` fixture 均保留；没有用 fallback、loose parsing、测试 shim 或下游补偿处理
  producer 错误。

## 3. Test-path validation

Controller 初次校验发现修订前的 public-corruption 测试不可达 lower transition：public
`resolve_wait` 会先在 `_tool_result_resolution_payload -> _wait_tool_call_requested_event`
校验 request atom 与 `WaitRecord.execution_id`，因此先抛 `HostDurableError`，不会产生
transition `INVALID_STATE`。

follow-up 已关闭该问题：

- public completed/failed/lost tests 只证明正常 producer 写出的 result identity；
- 同一 `test_resolve_wait_command.py` 用 production durable store 与完整 typed
  `ResumeRunFromWaitingInput` / `WaitingRunTerminalInput` 直接调用两个 transition；
- mismatch fixture 新建 FK-valid 辅助 Attempt execution，只腐化目标 WaitRecord execution；
- 两分支均断言 `INVALID_STATE`，并比较 EventLog、Run、Attempt、Wait、dispatch 全表 snapshot，
  证明无 result/resume/terminal 或其它 partial fact/state mutation；
- public upstream guard 明确保留，但不冒充 lower owner proof。

该测试方案与当前 SQLite 独立 foreign keys、transition call graph 和 fresh-schema contract
一致，不需要新 test file 或 production seam。

## 4. Scope 与 artifact validation

- correction implementation allowlist：8 个 production、9 个 tests、2 个 README；相较已接受
  S1 边界只新增 `dayu/host/durable/run_transition.py`。
- correction gate 自身只修改原 R03 plan，并新增 AgentCodex correction artifact；现有
  production/tests/README/control/prior artifacts 均作为受保护输入。
- `git diff --check`：PASS。
- AgentCodex 记录 22 个受保护路径 SHA-256 未变化，`run_transition.py` 仍无 diff，HEAD 仍为
  `244bfdae`；Controller 状态文档与本 validation artifact 是总控后续写入，不属于 Agent
  artifact-only scope 违规。
- 未引入 S2/S3、Issue 177/178、兼容 schema、统一 tool authorization framework 或其它 deferred
  能力。

## 5. Review focus

双路 reviewer 必须完整检查：source Attempt identity 是否为唯一 owner、precondition 是否在所有
resume/terminal append 前执行、direct transition tests 是否可构造且能证明全表 no-mutation、
public/transition 两层测试职责是否分离，以及 exact allowlist/coverage/stop 是否闭合。任何 reviewer
verdict 都不单独授权 implementation；仍需 Controller adjudication。
