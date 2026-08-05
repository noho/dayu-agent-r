# Interactive Conversation Memory post-fix readiness observation

## Identity

- Target branch: `codex/interactive-oracle`
- Target commit: `3087b1b983a97ce5012d54e818795f4755434a98`
- PR: `#190`
- CI run: `interactive-memory-postfix-20260804TV7mSm6`
- Human-readable report: `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-postfix-20260804TV7mSm6/evidence/observed-behavior-postfix.md`
- Report SHA-256: `a12c1311686a8fadf7a40e5fa6c5f4468fded05f8951e8aaa585f839f28d85fc`
- Secret scan SHA-256: `947ffb3af9a8556e13f4af09fa1f51c2afbe7baa980754a50413270d018076e8`
- Registry mutation: none; this artifact records post-fix evidence and the user-adjudicated follow-up findings. Final replacement contracts still require Gateflow Goal Confirmation before implementation or registry mutation.

## Method

The Oracle controller ran real `dayu-cli interactive` processes in isolated CI-owned workspaces, using real Mimo plan first and real DeepSeek flash only after Mimo became unavailable for a provider-independent memory-classification path. No fake/mock provider or tool was used. Exit code and CLI summaries were not treated as correctness; accepted candidates, EventLog, Memory snapshots, formal Tool Trace, real tool results and cross-process reconnect behavior were inspected.

## Scenario closure matrix

| Scenario obligation | Observation status | Evidence judgment |
|---|---|---|
| `interactive.interactive.g06.summary-null` | executed | conforming: accepted JSON null clears prior summary and preserves four other semantic sections |
| `interactive.interactive.g06.drop-superseded` | executed | conforming: explicit superseded drops and correct reconnect |
| `interactive.interactive.g06.turn-group-atomicity` | executed | conforming: complete four-result Run group selected atomically and reconnect agrees |
| `interactive.interactive.g06.tool-trace-formal` | executed | partial: request/input reconstruction works; public response/provider/model identity absent |
| `interactive.interactive.g06.drop-policy-limit` | executed across calibrated attempts | not closed: no accepted candidate used policy_limit |

## Confirmed F11 / observed behavior #59: public compactor response identity remains unavailable

### Direct evidence

The formal Tool Trace query succeeded and reconstructed all runner calls with complete manifest/input descriptors. Both a successful compact and an intentional invalid single-attempt fallback were observed. However, the public Tool Trace result contains none of:

- `successful_response_identity`
- `effective_provider`
- `effective_model`
- `provider_request_id_availability`

The same identities exist in canonical EventLog payloads and confirm real Mimo execution, but private SQLite/EventLog payload inspection is not an acceptable replacement for the frozen public-resolver oracle.

### User adjudication

The original row/hot manifest mismatch is fixed, but the user-approved requirement was broader: the public formal resolver must expose compactor request, response and provider/model identity. This is an incomplete prior repair, not a new oracle gap. F09 is therefore only partially closed and must be finished without weakening the accepted public-resolver requirement.

### Root cause

The prior F09 repair closed the input-side lineage only. It made the runner-call manifest, compactor input projection, EventLog row and hot Tool Trace row share the same ref/digest, but it stopped at `RunnerCallResolvedProjection`, whose public typed result contains only the request signal, manifest, input projection and selected tool schema snapshot. Meanwhile the canonical accepted/rejected compaction terminal already owns `SuccessfulRunnerResponseIdentity`, including the actual effective provider/model, terminating `RunnerRequestIdentity`, and provider request id availability/value. `dayu.host.tool_trace` reduces `CONTEXT_COMPACTED` and `CONTEXT_COMPACTION_ATTEMPT_REJECTED` without projecting that canonical response identity into the public Tool Trace read contract.

The root cause is therefore a semantic-ownership boundary left incomplete: response identity is correctly produced and durably persisted by the canonical compaction terminal owner, but the public Tool Trace projection/resolver contract was designed and tested as request/input reconstruction only. The earlier repair verified row/hot/input identity and did not include an owner-level assertion that a public consumer can read the corresponding response identity.

### Semantic owner and repair boundary

The repair owner is the Host Tool Trace public typed projection/read contract for compaction terminal/attempt facts. It must project the response identity from the canonical `SuccessfulRunnerResponseIdentity` already owned by the same accepted/rejected compaction attempt, and expose a single typed public representation that formal Tool Trace analysis can consume.

It must not make CI query private SQLite/EventLog payloads directly, loosen manifest identity checks, infer provider/model from workspace configuration, copy provider identity from a neighboring event, or introduce a second response-identity truth. Provider request ids that are unavailable must remain explicitly unavailable rather than being fabricated.

## Confirmed F12 / observed behavior #62: the compaction contract over-assigns deterministic governance to a stateless model

### Direct evidence

Multiple real-provider attempts exercised explicit item/character cap feedback, whole-candidate repair, source-boundary digest binding and recovery-tier boundary changes:

- Mimo: one five-rejection failure and one 1800-second provider timeout.
- DeepSeek: three five-rejection failures under progressively isolated caps.
- DeepSeek: one accepted cap repair that legitimately used `redundant`, not `policy_limit`.
- DeepSeek three-fact calibration: candidates attempted policy-limit classification but repeatedly represented and dropped the same source or violated the remaining cap, then exhausted repair/recovery attempts.

No accepted candidate contained `reason=policy_limit`. Failed operations correctly emitted `CONTEXT_COMPACTION_FAILED` and used fallback; none was misreported as compact success.

### User adjudication

Model outputs that are malformed, incomplete or strategically simplified are a normal property of an LLM: it is a stateless, fallible, context-bounded reasoner that tends to pattern-match and take shortcuts. The system must preserve three invariants:

1. machine-detectable invalidity must be rejected;
2. uncertain output must never contaminate accepted Memory;
3. rejection or exhaustion must still allow safe continuation through bounded repair and deterministic fallback.

The strict parser, Context Governance accept barrier and fallback already enforce those safety invariants and must remain. The finding is that the current LLM-facing task makes reliable first-pass success unnecessarily difficult and assigns some Host-owned governance/audit decisions to the model.

### Root cause

The v2 contract asks one stateless model call to simultaneously:

- reconstruct five semantic Memory sections and their provenance;
- cover an exact closed set of source labels;
- explicitly account for every omitted source;
- distinguish four drop reasons whose business boundaries are subtle;
- satisfy several item/character caps; and
- after rejection, regenerate the whole candidate under feedback that only exists in the new request.

The specific `policy_limit` branch exposes the ownership mismatch. Whether a candidate exceeds a configured cap, which whole items fit, and which omitted labels were pruned solely because of that cap are deterministic facts owned by Host policy and the accept barrier. The current contract nevertheless requires the LLM to declare `reason=policy_limit`, while forbidding that value on the initial attempt until Host first rejects the candidate and returns a cap. That design forces at least one failure for the mandatory branch and asks the model to reproduce a Host ledger on a later whole-candidate replay.

`CompactExplicitDropV2` also scales an audit ledger with the number of omitted input labels. The ledger itself consumes output context, its four natural-language reasons are only partly machine-verifiable, and most of those reason strings do not change the resulting semantic Memory projection. Host can strictly verify label coverage and caps, but it cannot prove that a model-selected `redundant` versus `out_of_scope` explanation is semantically true. This is over-designed where bookkeeping has displaced the actual compaction task.

The prompt compounds the problem. The current system and user compactor prompts total 16,429 bytes and mix input schema, output schema, semantic guidance, coverage accounting, repair protocol and long examples. A fresh model must rediscover the important output shape inside a large instruction surface. This violates the practical design premise that each call is stateless even though every individual rule is documented.

### OLD calibration evidence

The OLD implementation at `/Users/leo/workspace/dayu-agent` used a 1,701-byte compactor prompt with a concrete JSON template near the top. It asked for two top-level objects and twelve simple business fields, without source-label coverage, explicit drop reasons, caps, diagnostics or a repair protocol. Its implementation made one provider call and had no semantic repair loop.

That reference supports the user's operational observation that a concrete JSON template materially improves conformance, but it is not a contract to copy verbatim. OLD also accepted a much weaker shape: it stripped Markdown fences, rejected only invalid/non-object output, missing `episode_summary` and empty title, and coerced several missing fields. It also contained an ambiguous empty-versus-preserve patch contract. Its lower observed repair frequency therefore came from both a simpler task and a lower acceptance bar. The new design must retain current strict parsing and fail-closed acceptance rather than importing OLD's leniency.

### Required design direction for Goal Confirmation

The fixing work unit must challenge and then confirm a minimal replacement contract before implementation. The recommended direction is:

1. Keep strict JSON decoding, exact typed validation, immutable input-boundary binding, caps, single canonical terminal, bounded retries and deterministic safe fallback.
2. Put a concise, complete concrete JSON template and its necessary field semantics in every LLM request. The structural contract must have one owner and feed that prompt projection, provider-native JSON Schema/structured output where supported, and Host validation; do not dump redundant schema text into the prompt or maintain drifting handwritten shapes in several layers.
3. Include the actual applicable caps in the initial request. Do not make the model learn deterministic policy only after a deliberately rejected first response.
4. Project initial and repair instructions separately, or conditionally, so the first request does not carry the full repair protocol. Every repair request must still be self-contained because the model has no memory of the rejected call.
5. Reduce the model's responsibility to semantic Memory content plus only provenance that is necessary to validate/support that content. Host must derive the represented-label set, omitted-label set and cap-driven audit from the accepted semantic result and the immutable source boundary.
6. Remove or materially narrow the four-reason `CompactExplicitDropV2` ledger. If a genuinely useful business relation must remain—for example an explicit new item superseding a stale prior item—represent it as a narrow, structurally checkable relation attached to retained content, not as a mandatory free-standing explanation for every omission.
7. Do not add natural-language heuristics, a second LLM judge as correctness owner, renderer-side rewriting, loose parsing, unbounded retries, compatibility aliases or old-schema shims. Semantic uncertainty must continue to reject/fallback rather than enter Memory.
8. Treat schema changes as a fresh contract under `AGENTS.md`. Update design truth, typed owner contracts, prompt projection, public artifacts, tests and README responsibilities together.

This direction is a Goal Confirmation input, not permission to mechanically transplant OLD or to preserve `CompactExplicitDropV2` merely because the current code/tests contain it.

### Oracle/scenario impact

The accepted oracle and scenario registries currently require a successful `policy_limit` branch. That literal obligation depends on the present over-assigned schema. The fixing agent must not silently mutate the frozen registries to make an implementation pass. Goal Confirmation must first freeze the replacement business behavior and ownership. Only after explicit Oracle-controller confirmation may the registry be changed to express the newly adjudicated contract, with the old obligation and its superseding decision recorded. The implementation must then be observed with real providers before the replacement scenario can be marked ready.

### Semantic owner and implementation boundary

LLM-facing task semantics belong to the packaged compactor prompt/schema projection. Semantic Memory content belongs to the accepted typed candidate. Exact boundary accounting, deterministic policy caps, cap-driven omissions and acceptance remain Host Context Governance facts. Durable terminal, artifact, Memory and Tool Trace projections must continue to derive from one accepted truth.

The repair must be made at those owners, not in Memory consumers, CLI rendering, scenario fixtures or provider-specific branches. The first implementation slice must prove the replacement contract against counterexamples before production code is changed.

## Readiness decision after finding adjudication

F08 and F10 have sufficient post-fix real evidence. Interactive command closure still has two confirmed blockers: incomplete F11 public response-identity projection and F12's compaction contract/ownership redesign. Consequently this artifact does not yet change accepted oracle/scenario registries and does not claim that `init/prompt/interactive` are ready for an unqualified second-round CI run. After implementation, #59 must be re-observed through only the public formal Tool Trace API, and the replacement compact contract must receive new real-provider observation and user adjudication before registry readiness is frozen.

## Final implementation status appended on 2026-08-06

The frozen finding text above remains the historical pre-implementation observation and has not been rewritten. The final implementation/evidence state is:

- Implementation: **PASS**. F11 now exposes Host-owned compactor response identity through the public Tool Trace resolver and analysis projection; F12 now uses the fresh v3 semantic candidate with Host-owned provenance partition, omitted complement, caps, usage audit, bounded repair/fallback and one accepted durable truth.
- Real observation: **complete**. The accepted immutable S4 root is `/Users/leo/workspace/.dayu-cli-ci/interactive-memory-v3-20260805T-s4-restart-uOZytY`; its human-readable report is `observed-report.md` with SHA-256 `bbaa52a04100932c09e0a8e20d19c81ed6d865378db502bc6d4f1936c9694411`; root `digest.json` SHA-256 is `38f0b01f12c2ab55ce1af3c16080b71013d1a19512d65051f5532b747f71da0d`. S4 acceptance is recorded in `docs/reviews/pr-190-f11-f12-s4-evidence-acceptance-20260806.md`.
- Oracle: **pending**. `cli.interactive.core-execution@1` and the three legacy scenarios are superseded; current `core-execution@2` is accepted from the user's explicit 2026-08-05 F11/F12 replacement-contract decision. `tool-trace-formal@2`, `rolling-correction-replacement@1` and `cap-constrained-memory-replacement@1` remain `unadjudicated` despite complete S4 evidence.
- F11 status: implementation and real public/canonical equality observation complete; replacement scenario adjudication remains owned by the Oracle controller.
- F12 status: fresh v3 implementation and real provenance/omitted/cap/repair/reconnect observation complete; replacement scenario adjudication remains owned by the Oracle controller.
- Registry/readiness: both registries remain `calibration`; this artifact does **not** mark interactive, Oracle or registry readiness as ready.
- Immediate Gateflow entry point: controller dual code review of the S5 registry/docs implementation slice. After that review loop, the next unresolved product-validation owner remains the Oracle controller.
