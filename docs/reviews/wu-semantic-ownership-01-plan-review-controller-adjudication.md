# WU-SEMANTIC-OWNERSHIP-01 plan review controller adjudication

## Scope

- Plan artifact: `docs/host/wu-semantic-ownership-01-umbrella-plan.md`
- Review artifacts:
  - `docs/reviews/plan-review-20260709-143323.md`
  - `docs/reviews/plan-review-20260709-143500.md`
- Gate: plan review
- Controller decision: `fix-required`

Both reviews concluded `pass-with-risks`. The umbrella structure is accepted, but the plan must be fixed before plan re-review.

## Controller decisions

### C01: P0-A finish reason authority

Decision: accepted.

P0-A must default to the root-cause fix: remove `finish_reason` from `RunnerContentCompletedData` and `ContentCompleteData`, and make `RunnerDoneData.finish_reason` / `IterationCompletedData.finish_reason` the single Runner-call completion authority. Agent-side overwrite is rejected as the primary plan because it leaves a second non-authoritative field available for future consumers to misuse.

Before implementation, P0-A must still run a consumer scan for `ContentCompleteData.finish_reason` and `RunnerContentCompletedData.finish_reason`. If that scan finds an unexpected production consumer outside the Engine Agent event bridge or parser/tests, controller must re-open the contract decision before implementation.

### C02: P0-B Fins `ingest_method` coverage

Decision: accepted.

P0-B must explicitly require full `rg "ingest_method" dayu/fins/` coverage before implementation, and its allowed files must include all Fins pipeline and storage read/write points found by the scan. Known missing candidates include CN pipeline, CN rebuild/source upsert, SEC source upsert, and source-document storage core / maintenance paths.

### C03: P0-B preprocess success/result helper scope

Decision: accepted.

P0-B root-cause confirmation must choose the typed success/result contract before implementation: either a boolean helper on the summary type, or a typed status enum/helper. It must list all direct/job/awaiting/direct-stream consumers and state whether JSON summaries gain `not_supported_count`.

### C04: P1-A consumer migration pressure

Decision: accepted.

P1-A may keep a producer slice plus a consumer migration slice, but the plan must require a per-consumer completeness checklist for Tool Trace, Read API, Durable Memory, Conversation Memory, RunInputBuilder, and CompactMaterial. If implementation context is too large, split the consumer migration into smaller semantic slices rather than silently dropping a consumer.

### C05: P1-B `RUN_LOST` public outbox behavior

Decision: accepted with controller design decision.

`RUN_LOST` is a Host terminal/lifecycle fact, not a public outbox terminal item. Public outbox watermark logic must not treat `RUN_LOST` as requiring an outbox item. P1-B must introduce or reuse Host terminal helper semantics that distinguish:

- Host terminal event set, including `RUN_LOST`;
- public outbox terminal item event set, excluding `RUN_LOST`;
- explicit skip/diagnostic behavior for non-public terminal facts.

If `docs/host/design.md` lacks this distinction, P1-B must update the design truth before implementation.

### C06: P1-C LLM-facing waiting wording boundary

Decision: accepted with controller classification.

Business-level wording such as "等待工具结果返回" is allowed in tool schema/prompt only when it describes the model-visible behavior that a long-running tool returns a result later. Governance wording is not allowed in LLM-facing text, including "等待状态", "未进入等待状态", "后续调度", Host wait ids, poll/adapter terminology, and Host-governance default text such as "宿主取消" or "不要把本次取消视为业务失败".

P1-C must scan both prompt/config files and tool schema/outcome helpers. It must explicitly classify duplicate-tool/governance messages if they enter LLM-facing material.

### C07: P2-A session resume boundary

Decision: accepted with controller architecture direction.

P2-A must default to a Service-owned existing-session execution helper for prompt/interactive resume behavior. CLI modules should keep parameter parsing, terminal rendering, and command-specific output behavior; shared submit/watch/session execution semantics belong below CLI. A CLI-public helper is allowed only if P2-A root-cause confirmation proves the helper is purely UI/rendering logic and moving it into Service would leak CLI display concerns downward.

### C08: P2-B obsolete finding handling

Decision: accepted.

P2-B must begin with a finding status table: `active`, `obsolete-with-evidence`, `needs-design-update`, or `deferred-with-owner`. Obsolete findings do not require fake implementation churn; a controller-accepted confirmation artifact can close them with a no-code/no-commit pass for that finding. Active findings still require normal implementation/review/fix/re-review closure.

### C09: P2-C prompt source migration

Decision: accepted.

P2-C must begin with `rg "AgentPolicy\\(" dayu/ tests/` and classify construction sites by owner layer. Engine must not import runtime config or config loader to recover defaults. Production and tests must pass explicit prompt text from their owning assembly/fixture boundary; no production test-only default helper or compatibility wrapper is allowed.

### C10: Full-repository deepreview phase

Decision: accepted.

The umbrella plan must define the post-sub-WU deepreview phase more concretely:

- each round dispatches at least AgentMiMo and AgentDS over the full repository, not just changed files;
- review dimensions must include Engine contracts, Host durable truth, Host projections, Fins contracts, CLI/Service boundary, LLM-facing text, config/prompt, and tests/import-boundary coverage;
- controller adjudicates every finding;
- accepted current-umbrella findings become new sub WUs or slices under this umbrella;
- final closeout requires at least two consecutive full-repository rounds after fixes with no new accepted current-umbrella finding, unless the user explicitly changes the exit condition.

### C11: Sub WU contract conflict handling

Decision: accepted.

The plan must describe how controller handles a later sub WU conflicting with an accepted earlier sub WU contract: stop, update design truth if needed, then either modify the earlier accepted contract in a new fix slice or add an explicit typed mapping in the current sub WU. Do not silently layer a downstream workaround over a wrong upstream contract.

## Finding disposition

| Review finding | Disposition | Controller action |
|---|---|---|
| DS 01 / MiMo 06 P0-B allowed files incomplete | accepted | Plan fix C02 |
| DS 02 P1-C waiting wording classification | accepted | Plan fix C06 |
| DS 03 / MiMo 04 P2-A architecture choice | accepted | Plan fix C07 |
| DS 04 P2-C migration scope | accepted | Plan fix C09 |
| DS 05 deepreview phase details | accepted | Plan fix C10 |
| DS 06 P0-B preprocess helper scope | accepted | Plan fix C03 |
| DS 07 / MiMo 02 P1-B RUN_LOST behavior | accepted | Plan fix C05 |
| DS 08 / MiMo 05 P2-B obsolete criteria | accepted | Plan fix C08 |
| DS 09 sub WU conflict handling | accepted | Plan fix C11 |
| DS 10 / MiMo 01 P0-A finish reason option | accepted | Plan fix C01 |
| MiMo 03 P1-A consumer migration pressure | accepted | Plan fix C04 |

No finding is rejected. No finding is deferred outside this umbrella WU. None needs more evidence before the plan fix gate.

## Next gate

Proceed to plan fix. AgentCodex must update `docs/host/wu-semantic-ownership-01-umbrella-plan.md` to incorporate C01-C11, and must not modify production code, tests, README, push, commit, or enter implementation.
