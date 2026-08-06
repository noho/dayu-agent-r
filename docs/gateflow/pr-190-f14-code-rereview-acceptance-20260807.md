# PR 190 F14 code re-review acceptance

## Gate metadata

- gate: `code review`
- base: `b222b8b064f096d899a9de708e45cd1fb6e732e6`
- adjudication: `docs/gateflow/pr-190-f14-code-review-adjudication-20260806.md`
- MiMo re-review: `docs/reviews/pr-190-f14-code-rereview-mimo-20260806.md`
- DeepSeek re-review: `docs/reviews/pr-190-f14-code-rereview-ds-20260806.md`
- Controller evidence audit: current diff + focused validation
- verdict: `accepted`

## Accepted resolution

- C1：`group_consumed`必须同时具有非空`run_id`、唯一user anchor与consumed anchor ref；缺失Run identity保守进入typed/atomic owner并fail closed。回归先红`DID NOT RAISE`，修复后转绿。
- M1：三轮逐阶段owner test证明frontier严格单调、group/canonical order稳定、consumed/raw exact partition无gap/duplicate。
- M2：旧/新两条真实accepted evidence envelope进入两个正式terminal；旧fact/ref/provenance在后续strict重读不变，第二proposal不retain旧fact，新fact只绑定新evidence ref。四轮aging把correction raw user/answer/evidence推出recent window后，reopen Memory与ordinary RunInput只由第二replacement证明当前更正。
- M3：Host design改为build期间的两阶段proof，准确区分chain ref validation与material frontier/atomic validation。
- D2：metadata helper、Host design和README明确whole-group selector proof owner与final atomic owner。
- D3：删除虚假的宽泛`:raises Exception:`。
- rejected AgentDS F1未采纳：ordered SQL + stable tuple/list append已机械保证`group[0]`是minimum sequence。

## Independent re-review evidence

- AgentMiMo：`ACCEPTED`，focused 5 tests与完整affected union通过，pyright 0 errors。
- AgentDS：`ACCEPTED`，逐条核验C1/M1/M2/M3/D2/D3、scope与rejected finding均符合裁决。
- AgentController：人工读取M2完整fixture，确认真实`TOOL_RESULT_ACCEPTED`/`AcceptedEvidenceEnvelope`、production acceptance、strict payload、Memory/reopen RunInput的claim/ref/provenance来自同一accepted truth；没有summary-only替代证据。

## Validation snapshot

- finding-focused: `5 passed`
- affected union: `343 passed`
- changed production file coverage: `85%` (`190 passed`)
- focused pyright: `0 errors, 0 warnings, 0 informations`
- focused Ruff: pass
- `git diff --check`: pass
- forbidden-scope diff: empty

## Scope and residual risk

- 无schema、public contract、DB migration、second cursor、compatibility、fallback、prompt/provider/Engine/UI/Oracle变更。
- deterministic owner/integration tests不冒充production CLI；真实provider rolling-correction observation仍在后续Gate执行。
- accepted chain全量strict parse成本随Session terminal数量增长，仍是accepted plan明确记录的当前slice权衡。

## Decision

Code review gate通过。允许创建一个implementation commit；commit后进入aggregate deepreview，尚不push、不修改PR状态。
