# WU-CM-01 Compact Contract Closure Plan Blocker Follow-Up Fix Re-Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-CM-01 Conversation Memory overall optimization |
| gate | compact contract closure plan blocker follow-up fix re-review adjudication |
| design source | `docs/host/design.md` |
| control doc | `docs/host/issues-implementation-control.md` |
| follow-up fix artifact | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-codex.md` |
| re-review artifacts | `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-rereview-mimo.md`; `docs/reviews/wu-cm-01-compact-contract-closure-plan-blocker-followup-fix-rereview-ds.md` |
| controller | AgentController |
| date | 2026-06-04 |

## Verdict

`accepted-plan`。

AgentMiMo 与 AgentDS 均裁决 `pass`，且无 blocking / non-blocking findings。Follow-up fix 已完整处理上一轮 Controller accepted findings，Pre-Slice C 可以重新进入 implementation gate。

## Finding Adjudication

| finding | 裁决 | 理由 |
|---|---|---|
| `open_host.py` / `api.py` 缺失于 Pre-Slice C allowed production files | accepted-as-fixed | Plan 已把 `dayu/host/open_host.py` 与 `dayu/host/api.py` 加入 allowed files，并严格限定为 `LLMContextCompactor` construction、`HostLocalExecutionOptions.context_compactor` typed option 与 single public `compact()` vNext contract 类型对齐。 |
| `open_host.py` / `api.py` scope 可能扩大到 Service/config/UI/OpenHost 行为 | accepted-as-fixed | Plan implementation boundary 与 exit signal 明确禁止 Service assembly、config-service、UI、OpenHost lifecycle、scheduler wiring、runtime behavior 与 public behavior 重构。 |
| `run_input.py` 对旧 `CompactMaterialBlockKind` enum members 的 severance 边界模糊 | accepted-as-fixed | Plan 已明确删除旧 enum members 前必须替换为 vNext section 分类 helper 或本模块私有分类，且不得提前迁移 full vNext memory prompt assembly。 |
| `EvidenceBackedFactCandidate` 处置策略未单独裁决 | accepted-as-fixed | Plan 已要求 implementation closeout 单独说明该符号处置策略，禁止新旧定义并存、alias、compatibility re-export 或旧 candidate wrapper。 |
| 条件测试边界 | accepted-as-fixed | Plan 已限定 `test_public_open_host_options.py` / `test_open_host_runtime.py` 仅在 typed option 或 construction 断言同步时追加，不扩大行为范围。 |
| control doc gate/status/next entry point 一致性 | accepted-as-fixed | Control doc 已一致指向 follow-up fix re-review gate；本裁决后将推进到 implementation gate。 |

## Next Gate

进入 `WU-CM-01 compact contract closure implementation gate`。

Implementation 必须由 AgentCodex 执行，并严格遵守更新后的 Pre-Slice C allowed files、实现边界、禁止项、测试命令和退出信号。AgentCodex 不得 commit、push、PR 或进入 code review gate；完成后只写 implementation artifact 并报告验证结果。
