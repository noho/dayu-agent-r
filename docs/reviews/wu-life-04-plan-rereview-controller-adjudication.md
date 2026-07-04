# WU-LIFE-04 Plan Re-Review Controller Adjudication

## 基本信息

- Work unit: WU-LIFE-04 Tool Execution Deadline And Issue 168 Watchdog Closeout
- Gate: plan re-review
- Date: 2026-07-04
- Plan artifact: `docs/host/wu-life-04-tool-execution-deadline-watchdog-plan.md`
- Fix artifact: `docs/reviews/wu-life-04-plan-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-life-04-plan-rereview-mimo.md`
  - `docs/reviews/wu-life-04-plan-rereview-ds.md`

## 总体裁决

Plan re-review 通过。两路 reviewer 均确认 controller accepted findings 已全部修复，且 plan fix 未引入新的 material blocker。

## Finding 最终状态

| ID | 最终状态 | 依据 |
|---|---|---|
| PLAN-F01 | 已修复 | Plan 明确删除 `HostLocalExecutionOptions.active_cancel_timeout_seconds`，不保留 internal disable flag，watchdog 删除 timeout 后无条件启用；orphan `CANCELLING -> LOST` 测试改用无 accepted cancel fact fixture。 |
| PLAN-F02 | 已修复 | Plan 已覆盖 `active_cancel_timeout` reason、worker lifecycle signal、helper / input 命名 rename，并加入 `rg "active_cancel_timeout"` stop condition。 |
| PLAN-F03 | 已修复 | Plan 已加入 `tests/host/test_engine_ingest_mapping.py`，范围限定为 helper/import/fixture rename 与 payload assertion 同步。 |
| PLAN-F04 | 已修复 | Plan 已说明 `tests/host/test_run_attempt_transitions.py` 的影响来自 closeout helper、payload 字段和 reason rename，不是直接引用 `active_cancel_timeout_seconds`。 |
| PLAN-F05 | 已修复 | Plan 已具体说明 `docs/host/design.md` 要删除 public timeout 段落、删除 `None` opt-out、改写为 accepted-cancel closeout supervisor，并说明不代表 provider/tool physical stop。 |
| PLAN-I01 | 已修复 | Plan 已把 no-extra-budget 设计权衡写入 rationale。 |

## Residual Risk 状态

- WU-TOOLS-CANCEL-01 owns physical interrupt boundary and escalation: deferred-with-owner.
- Issue 87 owns optional per-tool deadline observability, scan query optimization, clock skew, diagnostics/audit hooks, and shared supervisor abstraction decision: deferred-with-owner.
- No unclassified residual risk remains for plan gate.

## 下一步

Plan gate 可以进入 accepted plan commit。提交后，control doc 的 next entry point 应进入 implementation gate。
