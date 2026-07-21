# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Second Stop Controller Adjudication

## Scope

- Gate: resumed `implementation-slice-3`
- Accepted Slice 3 plan amendment commit: `6c1cf62a`
- AgentCodex second stop artifact: `docs/reviews/wu-host-session-event-delivery-01-slice3-second-stop-scope-codex.md`

Controller只裁决 gate/scope；partial S3 implementation与当前通过的caller传播保持不变，不派发code review。

## Direct evidence

S3 focused gate已 `387 passed`，完整 `tests/host -q` 在 `2062 passed, 1 skipped, 6 deselected` 后只失败一项：`tests/host/test_watch_session_events.py` dual-opener barrier仍断言全局 `local_hook_calls.call_count == 0`。

该断言属于S2“local hook尚未接线”阶段的证据。S3接线后：

- opener A提交terminal后推进A自己的local watermark是合法且必需的。
- opener C不得因A的local action收到跨opener notice/wake，C自己的watermark必须保持不变。
- 全局class-level hook计数器把A的合法动作与C的barrier混为一谈，不再表达正确语义。

AgentCodex曾临时探索instance-local instrumentation，但在Controller指出allowlist缺口后已完整回滚；`tests/host/test_watch_session_events.py`当前相对HEAD无改动。

## Owner adjudication

Decision: `stop-confirmed; return-to-second-plan-amendment`。

正确owner是该dual-opener test instrumentation，而不是production coordinator、mailbox或cross-opener补偿。不得为了保住旧的全局零调用断言而禁止A本地hook、恢复未接线状态或添加跨opener广播。

## Minimal amendment

S3 Allowed tests只新增：

- `tests/host/test_watch_session_events.py`

授权严格限制为：把该dual-opener barrier从全局hook总调用数改为opener C局部watermark/hook与no-cross-opener wake观测；允许A局部hook前进，必须证明C未被A的local action推进或唤醒。不得修改production，不得改变S2 durable DB/fence correctness，不得改变其它测试业务语义。

验证必须包括：

1. 目标dual-opener barrier case通过。
2. `tests/host/test_watch_session_events.py`完整通过。
3. `tests/host -q` affected suite重跑，确保无第二个cross-opener regression。
4. 完整pyright与`git diff --check`通过。
5. constructor/source scan继续无新scope缺口。

## Gate decision

Decision: `return-to-plan-amendment`。

- Blocking open questions: `None`。
- Next owner: AgentCodex只修改accepted plan与second plan-fix artifact。
- 随后AgentMiMo/AgentDS独立并行 `$planreview`；Controller逐项裁决后才恢复implementation。
