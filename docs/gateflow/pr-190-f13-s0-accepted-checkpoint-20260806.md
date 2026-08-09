# PR 190 F13 S0 Accepted Checkpoint

## Decision

- Slice：S0 — 设计真源切到 v4
- Controller verdict：ACCEPTED
- Accepted base：`2d914beefb7bdee3e762df06f5f1ef0d115da143`
- Branch：`codex/interactive-oracle`
- Push：否；该checkpoint只接受本地slice，等待后续Gateflow统一push到PR 190

## Accepted truth

- Host compact contract fresh-cut到v4：旧fact只能keep/omit，新fact只能引用当前真实evidence material。
- 每条accepted EvidenceFact是claim + selection/context + non-empty canonical evidence refs的原子事实。
- Context Governance从immutable boundary原子展开retained/new facts，并在durable accept前执行逐fact binding、combined caps、coverage与aggregate union验证。
- schema-5 artifact保存accepted proposal与accepted replacement；rolling、Memory、RunInput/reconnect、EventLog/audit与Tool Trace只消费同一strict replacement。
- 空evidence refs在source-boundary构造阶段、任何LLM调用前non-repairable fail closed；all-clear proposal在非空boundary下typed reject。
- reactive multi-pass保留atom整体并在root final重新验证；transient pass不得产生durable truth或Memory。
- Engine owner不变；Oracle formal replacement scenarios仍unadjudicated。

## Review closure

- MiMo initial review：`docs/reviews/code-review-20260806-145045.md`
- DeepSeek initial review：`docs/reviews/code-review-20260806-145052.md`
- Controller adjudication：`docs/gateflow/pr-190-f13-s0-review-adjudication-20260806.md`
- MiMo re-review：`docs/reviews/code-review-20260806-f13-s0-mimo-rereview.md`，M1–M3 FIXED，M4 reject reason成立。
- DeepSeek re-review：`docs/reviews/code-review-20260806-f13-s0-ds-rereview.md`，D1–D5全部FIXED。

## Verification

- `git diff --check`：PASS。
- Host design active v3 type/schema/function scan：0命中；legacy名字只出现在fresh reject与negative tests。
- required v4 types、selector、per-fact refs、accepted replacement与schema-5均有直接命中。
- Engine design truth check：PASS，无diff。
- S0仅设计与Gateflow/review artifacts；没有生产代码，因此没有把文档检查写成runtime通过。

## Next entry

S1必须严格按accepted plan与本checkpoint实现v4 domain/structure、Host accept owner、rolling material与prompt；不得引入旧schema兼容、entailment heuristic、drop ledger、flat-ref反填或consumer fallback。
