# WU-LIFE-04 Slice Code Review Controller Adjudication

## 基本信息

- Work unit: WU-LIFE-04 Tool Execution Deadline And Issue 168 Watchdog Closeout
- Gate: code review
- Date: 2026-07-04
- Reviewed target: current combined Slice 1 + Slice 2 implementation diff after accepted plan commit `59be8480`
- Implementation artifacts:
  - `docs/reviews/wu-life-04-slice1-implementation-codex.md`
  - `docs/reviews/wu-life-04-slice2-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-life-04-slice-code-review-mimo.md`
  - `docs/reviews/wu-life-04-slice-code-review-ds.md`

## 总体裁决

两路 code review 均为 pass，无 blocking open question。核心实现满足 accepted plan：

- `active_cancel_timeout_seconds` 已从 public API 和 internal local execution options 删除。
- Watchdog 不再按 `cancel_requested_at + timeout_seconds` 延迟 closeout。
- Closeout helper、reason、worker lifecycle signal 和 payload 已改为 accepted-cancel watchdog closeout 语义。
- Candidate preconditions 保持严格。
- Startup recovery 与 always-enabled watchdog 一致。
- Engine `tool_execution_timeout_seconds` contract 未修改。

存在 1 个当前 work unit 内应修复的 low finding，以及 1 个 deferred residual risk。

## Finding 裁决

| ID | 来源 | 裁决 | 处理要求 |
|---|---|---|---|
| S1S2-CR-F01 | AgentDS Finding 1 | accepted | 删除 `dayu/host/durable/run_transition.py` 中重构后无调用点的私有辅助函数 `_normalized_event_occurred_at`。这是当前 closeout payload 重构的直接遗留，修复风险低，应在本轮 fix gate 清理。 |
| S1S2-CR-R01 | AgentMiMo observation | deferred-with-owner | Watchdog loop fatal exit 后不会自动重启是 pre-existing watchdog operability risk，不是本 WU 引入的 correctness regression。Owner / destination: Issue 87 umbrella diagnostics / supervisor follow-up。当前不阻塞 slice closeout。 |

## Residual Risk 状态

- Physical interruption of provider/tool execution: deferred-with-owner to WU-TOOLS-CANCEL-01.
- Per-tool original deadline durable observability: deferred-with-owner to WU-TOOLS-CANCEL-01 or Issue 87 child follow-up if future diagnostics require it.
- Watchdog scan query optimization: deferred-with-owner to Issue 87 performance follow-up.
- Clock skew / multi-host timestamp ordering: deferred-with-owner to Issue 87 diagnostics/audit follow-up.
- Shared supervisor abstraction: deferred-with-owner to Issue 87 umbrella.

No unclassified residual risk remains for code review gate after S1S2-CR-F01 is fixed and re-reviewed.

## 下一步

进入 fix gate。AgentCodex 只需删除 dead helper 并写 fix artifact；随后进入 code re-review。
