# WU-CM-01 Compact Contract Closure Plan Re-Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan re-review adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| plan doc | `docs/host/wu-cm-01-conversation-memory-plan.md` |
| fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-fix-codex.md` |
| re-review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-plan-rereview-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-plan-rereview-ds.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`accepted-plan`。

AgentMiMo 与 AgentDS 均裁决 `pass`。两路 review 都确认 AgentCodex 的 plan fix 已完整处理 Controller accepted findings，并确认新增 `Pre-Slice C - Compact Contract Closure` 可以进入 implementation gate。

## Finding Adjudication

| finding | 来源 | 裁决 | 理由 |
|---|---|---|---|
| `tests/host/test_compact_artifact_store.py` owner / test / exit signal 缺口 | DS B1 | accepted-as-fixed | Plan 已把该测试加入 Pre-Slice C allowed tests、测试命令、退出信号、Test Matrix 与最终验证命令，scope 限定为 artifact store 的 vNext candidate / quality check / material JSON 迁移。 |
| `dayu/host/compaction_evidence.py` owner 缺口 | DS B2 | accepted-as-fixed | Plan 已把该文件加入 Pre-Slice C allowed files，并限定为 compact evidence material section label / vNext material contract 迁移；implementation boundary 与 exit signal 均覆盖该文件。 |
| 旧 candidate / type / helper 退出信号不精确 | DS B3 | accepted-as-fixed | Plan 已从盲 grep 改为 production closeout files 内不得有 class definition、public export 或 production reference，并允许历史 docs / artifacts 命中旧 symbol。 |
| 必跑测试列表不够显式 | MiMo 1 | accepted-as-fixed | Plan 已显式列出 5 个 must-pass tests，并写明 fake / public smoke 的追加条件。 |
| 缺少 vNext positive adoption signals | MiMo 2 | accepted-as-fixed | Plan 已要求 `context_governance.py` production accept barrier 使用 vNext checker，并要求 operation closeout、repair、fallback 全部使用 vNext candidate / quality issue / payload helper。 |
| `compact()` 收敛、operation compactor 类型、payload cleanup、外部 implementor residual risk | DS N1 / N2 / N4 / residual | accepted-as-fixed | Plan 已明确 `compact_request_vnext()` 只能是未导出内部 helper，`run_compaction_operation()` 只能接收返回 vNext output 的 protocol，旧 compact payload constants / field allowlist / reader-writer helper 必须清理，仓库外 implementor 风险进入 implementation report。 |

## Non-Blocking Observations

| observation | 来源 | 裁决 | owner |
|---|---|---|---|
| `test_llm_compaction.py` 迁移工作量较大 | MiMo O1 | accepted-non-blocking | Pre-Slice C implementation report 必须列明 parser 测试迁移结果与验证命令。 |
| 控制文档状态历史可更清晰 | MiMo O2 | accepted-non-blocking | Controller 在本裁决与 control doc 中补记 compact contract closure plan review / fix / re-review artifacts。 |
| Pre-Slice C 与 Slice C 测试命令分离 | MiMo O3 | accepted-non-blocking | Pre-Slice C implementation 必须运行该 slice 的 focused tests 与 pyright；进入后续 Slice C 前由 Controller 按 gate 状态决定是否补全回归。 |
| `compaction_evidence.py` 无独立测试文件 | DS observation | accepted-non-blocking | Implementation 必须严格停在 section label / material contract 迁移范围；若逻辑超出 label 替换，应在现有 material 或 operation tests 中补断言。 |

## Next Gate

进入 `WU-CM-01 compact contract closure implementation gate`。

Implementation 必须由 AgentCodex 执行，严格限制在 plan 的 Pre-Slice C allowed files / modules 内。AgentCodex 不得 commit、push、PR 或进入 code review gate；完成后只写 implementation artifact 并报告测试与 pyright 结果。
