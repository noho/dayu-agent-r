# WU-LIFE-04 Plan Re-Review — AgentDS

Re-review gate: plan re-review
Review target: `docs/host/wu-life-04-tool-execution-deadline-watchdog-plan.md`
Prior review: `docs/reviews/wu-life-04-plan-review-ds.md`
Controller adjudication: `docs/reviews/wu-life-04-plan-review-controller-adjudication.md`
Fix artifact: `docs/reviews/wu-life-04-plan-fix-codex.md`
Date: 2026-07-04

## Re-Review Scope

仅验证 controller accepted findings 的修复状态，不重新打开已通过的整体设计。

## Finding 修复状态

### PLAN-F01 — 已修复

要求：删除 `HostLocalExecutionOptions.active_cancel_timeout_seconds`，不保留内部 disable flag；watchdog 删除 timeout 后无条件启用；orphan `CANCELLING -> LOST` 测试用没有 accepted cancel fact 的 fixture。

Plan 修复证据：

- §6 (line 108): "Delete `HostLocalExecutionOptions.active_cancel_timeout_seconds`."
- §6 (line 109): "Do not add an internal disable flag or any scheduler opt-out that can turn off the accepted-cancel watchdog. After deleting the timeout option, the watchdog is unconditionally enabled."
- §8 Slice 1 (line 172): "Remove `HostLocalExecutionOptions.active_cancel_timeout_seconds`."
- §8 Slice 1 (line 173): "Do not add an internal watchdog disable flag; the accepted-cancel watchdog must be unconditionally enabled after the timeout field is removed."
- §8 Slice 1 stop condition (line 195): "No internal disable flag or timeout-option opt-out exists for the accepted-cancel watchdog."
- §8 Slice 2 (line 225): "Tests that need to cover orphan `CANCELLING -> LOST` must use a fixture with no accepted cancel fact, so `_has_accepted_cancel_fact` is false; do not cover that path by disabling the watchdog."

判决：所有三条子要求均在 plan 中有明确文字。无歧义，无遗漏。

### PLAN-F02 — 已修复

要求：把 `active_cancel_timeout` reason / worker lifecycle signal / helper 命名纳入 Slice 2 exact changes 与 stop condition；`rg "active_cancel_timeout"` 不应留下 live timeout 语义。

Plan 修复证据：

- §6 (line 110): "Rename durable input/function/helper names that contain `ActiveCancelTimeout` / `active_cancel_timeout` to accepted-cancel watchdog closeout terminology."
- §6 (line 111): "Rename terminal reason and worker lifecycle signal from `active_cancel_timeout` to `active_cancel_watchdog_closeout` or equivalent self-explanatory value. No compatibility mapping is required."
- §8 Slice 2 (line 221): "Replace `ActiveCancelTimeoutCloseoutInput` and `active_cancel_timeout_closeout_*` helpers with names matching accepted-cancel watchdog closeout, for example `ActiveCancelWatchdogCloseoutInput` and `active_cancel_watchdog_closeout_*`."
- §8 Slice 2 (line 222): "Rename the terminal reason and worker lifecycle signal value from `active_cancel_timeout` to `active_cancel_watchdog_closeout` or equivalent self-explanatory value."
- §8 Slice 2 stop condition (line 254): "`rg \"active_cancel_timeout\" dayu/host tests/host docs/host/design.md dayu/host/README.md` leaves no live timeout semantic in reason strings, worker lifecycle signals, helper names, payload assertions, or design text."

判决：reason、worker lifecycle signal、helper 命名三项全部覆盖；rg stop condition 明确列出搜索范围和匹配目标。无遗漏。

### PLAN-F03 — 已修复

要求：把 `tests/host/test_engine_ingest_mapping.py` 加入 affected / allowed files，范围限于 helper/import/fixture rename 与 payload assertion 同步。

Plan 修复证据：

- §5 affected files (line 86): "`tests/host/test_engine_ingest_mapping.py` only for closeout helper/import/fixture rename and payload assertion synchronization"
- §8 Slice 2 allowed files (line 212): "`tests/host/test_engine_ingest_mapping.py` only for closeout helper/import/fixture rename and payload assertion synchronization."
- §9 pytest command (line 264): includes `tests/host/test_engine_ingest_mapping.py`

判决：三处均加入，范围限定明确（"only for closeout helper/import/fixture rename and payload assertion synchronization"）。无遗漏。

### PLAN-F04 — 已修复

要求：说明 `tests/host/test_run_attempt_transitions.py` 的影响来自 closeout helper、payload 字段和 reason rename，而非 direct field 引用。

Plan 修复证据：

- §1 evidence (line 21): "`tests/host/test_run_attempt_transitions.py` 当前通过 closeout helper、payload 字段和 terminal reason 间接依赖 `active_cancel_timeout` 语义。"
- §8 Slice 2 (line 232): "Update `tests/host/test_run_attempt_transitions.py` only for closeout helper, payload field, and terminal reason rename fallout; it is not affected by a direct `active_cancel_timeout_seconds` field reference."

判决：§1 evidence 说明间接依赖性质，§8 Slice 2 明确排除 direct field reference。解释充分。

### PLAN-F05 — 已修复

要求：`docs/host/design.md` 修改要求具体到删除 public timeout 段落、删除 None opt-out、改为 accepted-cancel closeout supervisor、说明不代表 physical stop。

Plan 修复证据：

- §4 (line 65): "`docs/host/design.md` Cancel 章节必须删除现有 `OpenHostOptions.active_cancel_timeout_seconds` 段落：不再描述独立 post-cancel timeout、timeout 到期判定或 `reason=active_cancel_timeout`。"
- §4 (line 66): "`docs/host/design.md` Startup recovery 章节必须删除 `active_cancel_timeout_seconds=None` opt-out 语义：watchdog 不再可通过 timeout option 关闭。"
- §4 (line 67): "Host design 应改为：...watchdog 是 accepted-cancel closeout supervisor，不提供 post-cancel timeout 预算。"
- §4 (line 68): "Host design 应明确：该 closeout 不证明 provider/tool 已物理停止；后续旧 worker / tool 事件按 existing identity、state 和 first-committer-wins 被接受或拒绝。"
- §8 Slice 1 (lines 174-178): 五条具体 bullet point——删除 public timeout 段落、删除 None opt-out、改写为 accepted-cancel watchdog closeout supervisor、说明不代表 physical stop、startup recovery 改为 watchdog tick 优先。

判决：§4 给出方向性要求，§8 Slice 1 给出可执行的 bullet point 列表。粒度足够 implementation agent 直接执行。

### PLAN-I01 — 已修复

要求：no-extra-budget rationale 作为补充理由体现。

Plan 修复证据：

- §7 (line 142): "This no-extra-budget choice is intentional: if a tool outcome was already durably accepted before cancel reached Engine, existing Engine/Host commit ordering preserves it; if it was not accepted yet, user cancel may close the Run before a later tool result appears. That is the correct tradeoff for an explicit cancel and does not require a separate waiting budget."

判决：DS-F05 的设计权衡分析已作为补充 rationale 写入 §7，解释了两种正确命运（已接受 outcome 保持优先、未接受结果可被 cancel closeout 截断）及其与 Engine cancellation commit boundary 的一致性。无需额外修改。

## Blocking Open Questions

无。所有 6 个 accepted findings 均已修复，plan fix 未引入新的 material blocker。

## 总评

**Re-review 结论：pass**

- 6/6 accepted findings 状态为"已修复"
- 0 blocking open questions
- Plan fix 仅增加 specificity，未改变 plan 的核心架构决策、slice 切分或 scope boundary
- Plan 可以进入 implementation gate
