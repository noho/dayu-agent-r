# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 3 Narrow Re-Review Controller Adjudication

## Inputs

- Accepted base：`b33bb80b`
- Accepted finding：`S3-RR-F01`
- AgentCodex fix：`docs/reviews/wu-host-session-event-delivery-01-slice3-rereview-fix-codex.md`
- AgentMiMo：`docs/reviews/wu-host-session-event-delivery-01-slice3-narrow-rereview-mimo.md`
- AgentDS：`docs/reviews/wu-host-session-event-delivery-01-slice3-narrow-rereview-ds.md`

两路原 reviewers 独立并行使用 `$deepreview --base b33bb80b` 完成 narrow re-review；均给出 `S3-RR-F01 CLOSED`、`0 new material finding`。

## Finding closure

### S3-RR-F01

- 裁决：`closed`
- durable owner仅保留 `project_terminal_notice_from_exact_run_event`，使用直接 typed `RunRow | None`、`EventLogRow | None` 与 keyword-only bool参数；没有为投影新增Protocol。
- admission、engine_ingest、recovery、dispatch、waiting五个consumer全部direct import/call，无alias、wrapper、re-export或本地notice构造。
- waiting旧pure projection已删除；terminal snapshot helper只负责terminal confirmation/replay并把exact rows交给shared owner。首次failed/lost/expiry flag与terminal replay flag保持。
- owner behavior覆盖row缺失与terminal id/sequence、Session、Run identity四类不一致；static test冻结五consumer闭集、直接导入和唯一构造。
- producer manifest、ordinary direct promotion allowlist、local-only/Engine/runtime边界、focused/full Host、单文件coverage与完整pyright均保持通过。

## New findings

`None`。两路均未报告新的material finding或未归属current-Slice residual risk。

## Decision

`accepted-slice-3`

Slice 3 exact terminal post-commit、producer wiring、local coordinator、cross-opener barriers与construction/close lifecycle闭环已完成。下一 gate=`accepted-commit-slice-3`；Controller只提交本 Slice production/tests/control/review artifacts，然后进入accepted plan的Slice 4。不得push、merge、mark ready或操作PR。
