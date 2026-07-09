# WU-SEMANTIC-OWNERSHIP-01 / P2-E Plan Re-Review Controller Adjudication

## Scope

本裁决只覆盖 P2-E fixed plan 对已接受 plan findings 的 re-review 结果，不重新打开 umbrella WU，也不扩大到后续 full-repo deepreview。

输入 artifact：

- `docs/reviews/wu-semantic-ownership-01-p2-e-plan-codex.md`
- `docs/reviews/wu-semantic-ownership-01-p2-e-plan-fix-codex.md`
- `docs/reviews/wu-semantic-ownership-01-p2-e-plan-rereview-mimo.md`
- `docs/reviews/wu-semantic-ownership-01-p2-e-plan-rereview-ds.md`

## Verdict

P2-E plan gate 通过。

AgentMiMo 与 AgentDS 均给出 `pass`，且均确认 P2E-PLAN-F01 到 P2E-PLAN-F05 已在 fixed plan 中闭合。没有新的 plan finding。

## Finding Closure

| Finding | Controller decision |
| --- | --- |
| P2E-PLAN-F01 | Closed. Implementation 必须同时覆盖 `STREAM_DEBUG_LOG_LEVEL` 正向捕获 heartbeat 与普通 `logging.DEBUG` 负向不捕获 heartbeat。 |
| P2E-PLAN-F02 | Closed. wait-resume 实施第一步必须诊断 `resume_request.messages`；正常路径必须断言 `UserMessage -> AssistantMessage(tool_call) -> ToolMessage`，且 `AssistantToolCall.id` 与原 awaiting `tool_call_id` 一致，`ToolMessage.tool_call_id` 与同一 id 一致。 |
| P2E-PLAN-F03 | Closed. purge fixture 必须使用 dedicated cancel request EventLog event id，并检查相关 parametrize 是否覆盖 `cancelled`；若覆盖则同步补齐合法 `cancel_request_event_id`。 |
| P2E-PLAN-F04 | Closed. 若 wait-resume 诊断触发 production owner，Slice E2 必须拆分，Host export / purge fixture alignment 独立推进，wait-resume 作为 production-owner follow-up。 |
| P2E-PLAN-F05 | Closed. Implementation closeout 必须记录 Engine / Host export snapshot alignment 是 test-only alignment，对齐既有 design / README public contract；除非诊断证明 production drift，否则生产代码和 README 不需要变更。 |

## Implementation Constraints

- P2-E 当前动机成立：7 个 broad-suite failures 的直接证据均指向 stale tests / fixture alignment，而不是 production contract drift。
- 修复边界仍是测试 owner 或测试 fixture owner；不得为了让测试通过而修改 `runner.py`、放宽 Host durable schema、接受旧英文 wait-resume guidance，或在 purge helper 中捕获 CHECK 失败。
- wait-resume 是唯一需要实施期先诊断的点。若实际 messages 是当前中文 fallback guidance 或缺 request atom / accepted evidence envelope，应先修 fixture/request atom；若出现旧英文 guidance，应停止该子路径并升级 production owner。
- stream heartbeat 负向断言必须避免假通过：负向路径需要使用与正向路径等效的 idle 条件，确保 heartbeat 本应产生但因普通 DEBUG threshold 不可见。

## Residual Risks

- wait-resume fixture 可能需要补齐 production request atom / accepted evidence envelope，不能用宽松文本断言替代 protocol closure。
- purge fixture helper 被多个测试路径复用，实现时必须检查调用方，避免把 `cancel_request_event_id` 错误写入不需要取消语义的 Run。
- broad suite 可能仍暴露其它 stale snapshot；实现 closeout 必须记录完整验证结果。

## Final Decision

P2-E accepted plan 可以进入 implementation gate。
