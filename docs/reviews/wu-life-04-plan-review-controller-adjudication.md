# WU-LIFE-04 Plan Review Controller Adjudication

## 基本信息

- Work unit: WU-LIFE-04 Tool Execution Deadline And Issue 168 Watchdog Closeout
- Gate: plan review
- Date: 2026-07-04
- Plan artifact: `docs/host/wu-life-04-tool-execution-deadline-watchdog-plan.md`
- Review artifacts:
  - `docs/reviews/wu-life-04-plan-review-mimo.md`
  - `docs/reviews/wu-life-04-plan-review-ds.md`

## 总体裁决

Plan review 结论为 pass-with-findings。两路 reviewer 均确认 plan 的核心判断成立：

- 当前 `active_cancel_timeout_seconds` 是独立 post-cancel timeout，和 `tool_execution_timeout_seconds` 作为单次工具调用最长运行时间真源存在语义冲突。
- Host 当前没有 durable per-tool original deadline；用 `cancel_requested_at + tool_execution_timeout_seconds` 或 Attempt start time 推导 deadline 都会产生错误语义。
- no-extra-budget closeout 是当前 work unit 内最小正确方案。
- WU-TOOLS-CANCEL-01 的 tool/provider physical interrupt 不属于本 work unit。
- 2 个 implementation slices 符合 control doc 的 Slice 切分原则。

存在 accepted non-blocking findings，需要在 plan fix gate 中修正 plan artifact 后再进入 re-review。

## Finding 裁决

| ID | 来源 | 裁决 | 处理要求 |
|---|---|---|---|
| PLAN-F01 | AgentMiMo F01 / AgentDS DS-F01 | accepted | Plan 必须明确删除 `HostLocalExecutionOptions.active_cancel_timeout_seconds`，不保留内部 disable flag；watchdog 删除 timeout 后无条件启用。需要测试 orphan `CANCELLING -> LOST` 的路径时，应通过没有 accepted cancel fact 的 fixture 覆盖，而不是通过关闭 watchdog 覆盖。 |
| PLAN-F02 | AgentMiMo F02 / AgentDS DS-F03 | accepted | Plan 必须把 `active_cancel_timeout` reason / worker lifecycle signal / helper 命名纳入 Slice 2 exact changes 与 stop condition。实现后 `rg "active_cancel_timeout" dayu/host tests/host docs/host/design.md dayu/host/README.md` 不应留下 live timeout 语义。 |
| PLAN-F03 | AgentMiMo F03 | accepted | Plan 必须把 `tests/host/test_engine_ingest_mapping.py` 加入 affected / allowed files，范围限于 helper/import/fixture rename 与 payload assertion 同步。 |
| PLAN-F04 | AgentDS DS-F02 | accepted | Plan fix 应说明 `tests/host/test_run_attempt_transitions.py` 的影响来自 closeout helper、payload 字段和 reason rename，而不是 `active_cancel_timeout_seconds` 字段直接引用。 |
| PLAN-F05 | AgentDS DS-F04 | accepted | Plan 必须把 `docs/host/design.md` 的变更要求写到足够具体：删除现有 `OpenHostOptions.active_cancel_timeout_seconds` 段落、删除 `None` opt-out 语义、改写为 accepted-cancel watchdog closeout supervisor、说明该 closeout 不表示 provider/tool 物理停止。 |
| PLAN-I01 | AgentDS DS-F05 | accepted-as-rationale | 该项是设计权衡说明，不要求单独代码或 plan fix；可作为 plan 中 no-extra-budget 方案的补充理由。 |

## Residual Risk 裁决

- Physical interrupt remains assigned to WU-TOOLS-CANCEL-01: accepted deferred-with-owner.
- Per-tool original deadline durable observability remains assigned to WU-TOOLS-CANCEL-01 or Issue 87 child follow-up if future diagnostics require it: accepted deferred-with-owner.
- Active watchdog scan query optimization remains assigned to Issue 87 performance follow-up unless implementation naturally touches the query: accepted deferred-with-owner.
- Clock skew and diagnostics/audit hooks remain assigned to Issue 87 diagnostics/audit follow-up: accepted deferred-with-owner.
- Shared supervisor abstraction remains assigned to Issue 87 umbrella and is not required by this work unit: accepted deferred-with-owner.

## 下一步

进入 plan fix gate。AgentCodex 需要只修改 plan artifact，并写 `docs/reviews/wu-life-04-plan-fix-codex.md`，不得修改生产代码、测试、README、control doc、commit、push 或进入 implementation。
