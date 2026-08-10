# WU-CLI-DOWNLOAD-03-DL-F15 Plan Review Adjudication

## Gate

- Gate：plan review
- Plan：`docs/gateflow/wu-cli-download-03-dl-f15-plan-20260810.md`
- MiMo review：`docs/reviews/plan-review-20260810-214126.md`
- DS review：`docs/reviews/plan-review-20260810-214223.md`
- Decision：进入 `fix`，修订计划后必须双路 re-review

## Findings 裁决

### PR-F1：代码行号引用偏差

- 来源：MiMo finding 3.1
- 裁决：`accepted`
- 理由：baseline 中 `run_docling_pdf_conversion` 从 510 行开始；精确引用有助于 implementation handoff。
- Required fix：把 `538-602` 更正为 `510-602`。

### PR-F2：coverage-supporting tests 是否 goal-bound / 80% 可达性未预估

- 来源：MiMo finding 3.2、DS finding 1
- 裁决：`accepted-in-part`
- 理由：单文件 coverage 不低于 80% 是用户明确 success signal，因此不能把这些 tests 降为 optional 或移出本 work unit；但实现不得机械完成全部列举 cases。计划应要求 implementation 先运行核心 tests 和 coverage baseline，然后按 missing lines 只补最小 owner cases，达到 80% 即停止。若在 allowed test boundary 内无法达到，必须停止交总控，不得扩大产品 diff、放宽门禁或添加 coverage bypass。
- Required fix：将 §8.5/§9.2/§10 改成上述增量策略和 stop condition；保留候选 test inventory 作为有界选择集，不把它们全部设为强制。

### PR-F3：真实 download 可能引入非目标分类/文档失败

- 来源：MiMo finding 3.3、DS finding 2/open question 2
- 裁决：`accepted-in-part`
- 理由：用户明确要求 production `dayu-cli download`，不能降为只跑 `process` 或手工准备 source。真实 download 仍是必要端到端证据；但本 WU verdict 只能绑定目标 0700 Q3（或替代 0066 Q2）的 conversion/publication/consume。非目标文档的新失败或分类差异只登记直接证据并停止扩修，不得使 Agent进入其它 finding 修复；若它阻止目标文档形成证据，则把本次真实补跑标为 gap。
- Required fix：在 §9.4 明确 target-specific evidence verdict、non-target observation 处理与 stop condition；不得要求非目标材料全部成功。

### PR-F4：deterministic test 使用 fake converter

- 来源：DS finding 3
- 裁决：`rejected-with-reason`
- 理由：测试替换 converter factory 但保留真实 attempt planner/runner/callback，精确拥有 stream lifecycle contract；真实 converter 组合链由用户要求的 production CLI run 覆盖。把真实重型 converter 引入 deterministic owner test 会增加外部依赖且不能稳定制造 first-attempt failure。
- Required fix：无；implementation closeout 明确两类证据边界即可。

## Open questions 裁决

- coverage 只实现达到 80% 所需的最小候选 cases；不是全部强制，也不能放宽阈值。
- 真实 evidence 必须在 accepted implementation commit 的 detached clean environment 运行，不能把未提交工作树当作正式 target。
- 非目标文档 failure 不参与 DL-F15 target verdict；只要不阻断目标证据，就登记但不扩修。

## Residual risk 分类

- 真实首 attempt 直接成功：`requiring explicit user decision` evidence gap。
- provider 不再返回目标文档或非目标错误阻断目标链：`requiring explicit user decision` external evidence gap。
- 其它分类、provider、storage、runner finding：不属于本 WU，只登记后停止扩面。

## Next entry point

`fix -> MiMo/DS re-review`
