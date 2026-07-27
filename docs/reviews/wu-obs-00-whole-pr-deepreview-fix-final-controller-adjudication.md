# WU-OBS-00 Whole-PR Deepreview Fix Final Controller Adjudication

status=complete

work_unit=WU-OBS-00

gate=whole-PR-deepreview-fix-controller-review

decision=pass-to-dual-rereview

implementation_base=9519b02949941477bc5e2ca3dc7684967222a4ed

implementation_artifact=docs/reviews/wu-obs-00-whole-pr-deepreview-fix-codex.md

## Closure

### PR-CTRL-01 — closed

- read/identity `OSError` 与 close `OSError` 双失败时，read summary 与 direct cause 保持
  primary；
- read/identity 成功、close-only `OSError` 时，close failure 继续 typed fatal；
- 未把 close 改成 best-effort，也未改变 reason enum/public schema。

### PR-FIX-CTRL-01 — closed

- operation phase 捕获任意 `BaseException`，然后无条件尝试 close；
- operation 是 `OSError` 时映射既有 read typed error；
- operation 是 `KeyboardInterrupt` / `SystemExit` 等非 `OSError` 时，同一异常实例在 close
  后传播；
- operation 与 close 同时失败时 operation 保持 primary；
- 无 operation primary 时 close failure 按其原类型/typed mapping 传播；
- 没有使用会在 finally 中再次覆盖 primary 的 raise。

owner tests 覆盖：

- read OSError + close OSError；
- close-only OSError；
- KeyboardInterrupt + successful close；
- SystemExit + close OSError；
- close 调用次数、异常 identity、summary 与 direct cause。

## Verification

- focused input tests：`30 passed`；
- affected Tool Trace matrix：`244 passed`；
- full pyright：`0 errors / 0 warnings`；
- changed production branch coverage：`81%`；
- workspace / cold-file analyzer 只读 smoke：通过；
- `.dayu` 七项 hashes/counts 前后完全一致；
- `git diff --check`：通过；
- HEAD 未改变，未 commit/push/修改 PR metadata。

Controller 驳回的 rules/dataset lock-path contract扩张保持不实施。

blocking_open_questions=none

next_entry_point=AgentMiMo / AgentDS whole-PR fix dual re-review; never self-advance
