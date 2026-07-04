# WU-LIFE-04 Plan Re-Review — AgentMiMo

Re-review target: `docs/host/wu-life-04-tool-execution-deadline-watchdog-plan.md`
Re-review date: 2026-07-04
Reviewer: AgentMiMo
Prior review: `docs/reviews/wu-life-04-plan-review-mimo.md`
Controller adjudication: `docs/reviews/wu-life-04-plan-review-controller-adjudication.md`
Fix artifact: `docs/reviews/wu-life-04-plan-fix-codex.md`

---

## Verdict: PASS

Blocking open questions: 0

---

## Accepted Finding Fix Status

### PLAN-F01 — 已修复

**要求**: 明确删除 `HostLocalExecutionOptions.active_cancel_timeout_seconds`，不保留内部 disable flag；watchdog 删除 timeout 后无条件启用；orphan `CANCELLING -> LOST` 测试用没有 accepted cancel fact 的 fixture。

**Plan 证据**:

- §6 line 108: "Delete `HostLocalExecutionOptions.active_cancel_timeout_seconds`." — 明确删除，非替换。
- §6 line 109: "Do not add an internal disable flag or any scheduler opt-out that can turn off the accepted-cancel watchdog. After deleting the timeout field, the watchdog is unconditionally enabled." — 无条件启用，无 opt-out。
- §8 Slice 2 line 225: "Tests that need to cover orphan `CANCELLING -> LOST` must use a fixture with no accepted cancel fact, so `_has_accepted_cancel_fact` is false; do not cover that path by disabling the watchdog." — orphan 路径用 fixture 覆盖，不关闭 watchdog。

**结论**: 完全满足 controller 裁决要求。

---

### PLAN-F02 — 已修复

**要求**: 覆盖 `active_cancel_timeout` reason / worker lifecycle signal / helper 命名 rename，且有 rg stop condition。

**Plan 证据**:

- §6 line 110: "Rename durable input/function/helper names that contain `ActiveCancelTimeout` / `active_cancel_timeout` to accepted-cancel watchdog closeout terminology."
- §6 line 111: "Rename terminal reason and worker lifecycle signal from `active_cancel_timeout` to `active_cancel_watchdog_closeout` or equivalent self-explanatory value."
- §8 Slice 2 line 221: "Replace `ActiveCancelTimeoutCloseoutInput` and `active_cancel_timeout_closeout_*` helpers with names matching accepted-cancel watchdog closeout, for example `ActiveCancelWatchdogCloseoutInput` and `active_cancel_watchdog_closeout_*`."
- §8 Slice 2 line 222: "Rename the terminal reason and worker lifecycle signal value from `active_cancel_timeout` to `active_cancel_watchdog_closeout` or equivalent self-explanatory value."
- §9 lines 273-274: `rg "active_cancel_timeout_seconds" dayu/host tests/host docs/host/design.md dayu/host/README.md` 和 `rg "active_cancel_timeout|timeout_seconds.*active" dayu/host tests/host docs/host/design.md dayu/host/README.md` 作为 stop condition。

**结论**: reason string、class name、helper name、worker lifecycle signal 全部纳入 rename scope，rg stop condition 覆盖所有受影响目录。

---

### PLAN-F03 — 已修复

**要求**: `tests/host/test_engine_ingest_mapping.py` 加入 affected/allowed files，范围限定为 closeout helper/import/fixture rename 与 payload assertion 同步。

**Plan 证据**:

- §5 line 86: "`tests/host/test_engine_ingest_mapping.py` only for closeout helper/import/fixture rename and payload assertion synchronization" — 已加入 allowed files，范围明确限定。
- §8 Slice 2 line 213: 在 Slice 2 allowed files 中列出。
- §9 line 264: 在 pytest 命令中包含。

**结论**: 文件已加入 allowed files，范围限定清晰。

---

### PLAN-F04 — 已修复

**要求**: `tests/host/test_run_attempt_transitions.py` 的影响说明为 helper/payload/reason rename，而非 direct field 引用。

**Plan 证据**:

- §1 line 21: "`tests/host/test_run_attempt_transitions.py` 当前通过 closeout helper、payload 字段和 terminal reason 间接依赖 `active_cancel_timeout` 语义。" — 明确说明是间接依赖。
- §8 Slice 2 line 232: "Update `tests/host/test_run_attempt_transitions.py` only for closeout helper, payload field, and terminal reason rename fallout; it is not affected by a direct `active_cancel_timeout_seconds` field reference." — 明确排除 direct field reference。

**结论**: 影响范围描述精确，implementation agent 不会误判修改范围。

---

### PLAN-F05 — 已修复

**要求**: `docs/host/design.md` 修改要求具体到删除 public timeout 段落、删除 None opt-out、改为 accepted-cancel closeout supervisor、说明不代表 physical stop。

**Plan 证据**:

- §4 line 65: "必须删除现有 `OpenHostOptions.active_cancel_timeout_seconds` 段落：不再描述独立 post-cancel timeout、timeout 到期判定或 `reason=active_cancel_timeout`。"
- §4 line 66: "必须删除 `active_cancel_timeout_seconds=None` opt-out 语义：watchdog 不再可通过 timeout option 关闭。"
- §4 line 67: "Host design 应改为：active `RUNNING` Attempt 收到 cancel 后...watchdog 是 accepted-cancel closeout supervisor，不提供 post-cancel timeout 预算。"
- §4 line 68: "Host design 应明确：该 closeout 不证明 provider/tool 已物理停止。"
- §8 Slice 1 lines 174-179: 具体修改步骤，逐一对应 controller 裁决的 4 项要求。

**结论**: design.md 变更要求具体、可执行，覆盖所有 4 项子要求。

---

### PLAN-I01 — 已修复

**要求**: no-extra-budget rationale 作为补充理由体现。

**Plan 证据**:

- §7 line 142: "This no-extra-budget choice is intentional: if a tool outcome was already durably accepted before cancel reached Engine, existing Engine/Host commit ordering preserves it; if it was not accepted yet, user cancel may close the Run before a later tool result appears. That is the correct tradeoff for an explicit cancel and does not require a separate waiting budget."

**结论**: 补充 rationale 已整合到 §7 设计决策中，语义清晰。

---

## New Material Blocker Check

Re-review 范围限定为验证 accepted findings 修复状态，除非 fix 引入新的 material blocker。

**检查结果**: 未发现新的 material blocker。Plan fix 仅在已有章节中补充精确化描述，未改变核心设计决策（delete `active_cancel_timeout_seconds`、no-extra-budget closeout、2-slice implementation），未引入新依赖或新 scope。

---

## Summary

| Finding | 状态 |
|---|---|
| PLAN-F01 | 已修复 |
| PLAN-F02 | 已修复 |
| PLAN-F03 | 已修复 |
| PLAN-F04 | 已修复 |
| PLAN-F05 | 已修复 |
| PLAN-I01 | 已修复 |

**Blocking open questions**: 0
**New material blockers**: 0
**Verdict**: PASS
**Artifact path**: `docs/reviews/wu-life-04-plan-rereview-mimo.md`
