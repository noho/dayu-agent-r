# WU-LIFE-04 Plan Fix — AgentCodex

Gate: plan fix
Date: 2026-07-04
Plan artifact: `docs/host/wu-life-04-tool-execution-deadline-watchdog-plan.md`
Adjudication: `docs/reviews/wu-life-04-plan-review-controller-adjudication.md`

## Scope

本次只修改 plan artifact，并新增本 fix artifact。未修改生产代码、测试、README、control doc，未进入 implementation，未 commit、push 或创建 PR。

## Accepted Findings Fix Status

| ID | 状态 | 修改位置 | 说明 |
|---|---|---|---|
| PLAN-F01 | 已修复 | Plan §2, §6, §8 Slice 1, §8 Slice 2 | 明确删除 `HostLocalExecutionOptions.active_cancel_timeout_seconds`；明确不保留内部 disable flag 或 timeout opt-out；watchdog 删除 timeout 后无条件启用；orphan `CANCELLING -> LOST` 测试要求改用没有 accepted cancel fact 的 fixture。 |
| PLAN-F02 | 已修复 | Plan §6, §8 Slice 2, §9 | 将 `active_cancel_timeout` reason、worker lifecycle signal、`ActiveCancelTimeoutCloseoutInput` / helper 命名纳入 Slice 2 exact changes；新增 `rg "active_cancel_timeout" dayu/host tests/host docs/host/design.md dayu/host/README.md` stop condition。 |
| PLAN-F03 | 已修复 | Plan §5, §8 Slice 2, §9 | 将 `tests/host/test_engine_ingest_mapping.py` 加入 affected / allowed files 和 pytest 命令，范围限定为 closeout helper/import/fixture rename 与 payload assertion 同步。 |
| PLAN-F04 | 已修复 | Plan §1, §8 Slice 2 | 明确 `tests/host/test_run_attempt_transitions.py` 的影响来自 closeout helper、payload 字段和 reason rename，不是直接引用 `active_cancel_timeout_seconds` 字段。 |
| PLAN-F05 | 已修复 | Plan §4, §8 Slice 1 | 将 `docs/host/design.md` 修改要求写具体：删除现有 `OpenHostOptions.active_cancel_timeout_seconds` 段落、删除 `active_cancel_timeout_seconds=None` opt-out 语义、改写为 accepted-cancel watchdog closeout supervisor，并说明 closeout 不表示 provider/tool 物理停止。 |
| PLAN-I01 | 已修复 | Plan §7 | 将 AgentDS DS-F05 的 no-extra-budget 设计权衡作为补充 rationale：已接受的工具 outcome 保持优先，未接受的结果可被显式 cancel closeout 截断，不需要额外等待预算。 |

## Validation

Required validation:

```bash
git diff --check
```

Result: passed.

Note: the two files changed by this gate are currently untracked in git, so `git diff --check` validates tracked diff whitespace only. The requested command completed successfully.

## Blocking Open Questions

None.
