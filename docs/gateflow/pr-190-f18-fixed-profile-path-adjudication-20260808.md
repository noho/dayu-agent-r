# PR 190 F18 Fixed-profile Path Adjudication

## Decision

- Controller verdict：`accepted-with-pre-execution-conditions`。
- 本裁决 supersede
  `docs/gateflow/pr-190-f18-plan-review-adjudication-20260808.md` 中“旧 sequence 327 root-cause evidence 不可恢复，因此 B2
  formal observation 必须关闭”的结论；该 artifact 对原 plan 中跨 opener illegal 预判、synthetic replay、错误 manifest真源、
  不够 bounded 的 findings仍然有效。
- 新 binding scope 是
  `docs/gateflow/pr-190-f18-goal-confirmation-amendment-20260808.md`。

## Direct registry and design judgment

Controller 直接核对目标 scenario record、Oracle predicates 29/30、CLI CI handbook 与 Host design 后确认：

1. 没有条款要求 wide-cap baseline、wide-to-constrained hot-switch或旧 Trial2 root-cause closure。
2. `relevant-material-over-initial-output-caps` 可以在从第一个 opener即 constrained 的 fresh chain 中形成：先产生 cap内 accepted
   previous EvidenceFact，再加入新的真实 evidence并让其自然进入同一 compact boundary。
3. 旧 sequence 327 的诊断闭环与新 B2 conformance闭环是两个独立问题。前者不可恢复不会降低后者的 mandatory标准，也不应被
   升级成 registry 未要求的额外 gate。
4. 新成功只证明 fixed-profile formal scenario；旧失败继续作为 unresolved cross-opener/owner-observability residual。

## Accepted reviewer conditions

两路专项 reviewer 的 findings 全部接受并转成 plan 必填项：

- 更新 Goal/plan，删除旧 root hard dependency；
- replacement chain 必须用 owner facts证明 accepted previous atom、新 FY2025 evidence eligibility、protected floor退出与真实
  over-cap boundary；
- replacement/reconnect、repair、fallback 三条 fresh chain在 provider调用前冻结 exact budget与 stop/seal规则；
- public evidence最小集合、private raw owner、digest/secret/path scan最后 writer必须写清；
- 自然 non-trigger只能形成 `needs-more-evidence`，不能预先承诺 B2 evidence sufficient。

## Next gate

Plan 返回 AgentCodex 修订。修订后由 AgentMiMo、AgentDS 进行两路独立 re-review；通过前不得调用真实 provider。
