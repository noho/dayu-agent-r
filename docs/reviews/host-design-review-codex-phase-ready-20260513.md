# Host Design Phase Readiness Review

## Review Scope

- Review target: `docs/host/design.md`
- Terminology consistency source: `dayu/README.md`
- Date: 2026-05-13
- Scope rule: only `docs/host/design.md` and `dayu/README.md` were used as design truth. No old implementation notes, discussions, issues, archive branches, or prior reviews were used.
- Review objective: judge whether the Host architecture design is ready to guide the next phase design and phase plan, with adversarial focus on boundaries, semantic contracts, state-machine invariants, remote boundaries, EventLog / event_class, payload durability, Outbox, ToolRuntime, TruncationManager, wait / resume / cancel / steer / retry / replay / recovery, memory, and over-coupled design.

## Assumptions Tested

- Host, not Engine or remote worker, is the governance truth for Session / Run / Attempt / EventLog.
- EventLog `canonical_fact` is sufficient as recovery, resume, audit, memory, and outbox truth.
- Public APIs expose enough preconditions and idempotency shape for safe phase-level slicing.
- Remote execution is transport substitution, not a governance boundary.
- ToolRuntime can safely sit near the EngineWorker while preserving Host-mediated accept barrier.
- Projection / Sink / Outbox / Memory remain reconstructible read models and do not become reverse truth.
- README terminology matches the Host design closely enough to prevent phase discussion drift.
- Host handle, runtime options, policy providers, EventLog, RunInputBuilder, ToolRuntime, RemoteProxy, Sink, Outbox, and Memory can be sliced without creating unnecessary module knowledge, circular dependencies, or policy ownership ambiguity.

## Findings

### F-001 - high - `steer` request lacks a durable target-run precondition

- id: F-001
- severity: high
- file lines: `docs/host/design.md:520`, `docs/host/design.md:637`, `docs/host/design.md:639`
- problem: `SubmitFollowupRequest` only declares `session_id`, `client_request_id`, `input`, and `behavior`, but the steer contract says steer must have an active-run precondition and must reject "target Run mismatch". The request shape does not expose a target Run, expected active Run, active-run epoch, or cursor precondition.
- why this affects phase design / plan: a stale UI / Service client can submit `behavior=steer` after the originally visible active Run has already reached terminal and a queued Run has been promoted. With a session-only request shape, Host may steer the wrong active Run while still satisfying "there is an active Run". Phase design would have to guess whether steer is session-current, run-targeted, or cursor-guarded, which affects API types, idempotency scope, CAS predicates, tests, and UI semantics.
- minimal correction: define the steer-specific precondition explicitly. For example, require `target_run_id` or `expected_active_run_id` plus optional `expected_event_sequence` / active epoch for `behavior=steer`, and specify mismatch as `conflict` or `invalid_state`. Keep `queue` session-scoped if that is intended, but make `steer` run-targeted.

### F-002 - high - duplicate-governance `reuse` lacks a durable model-visible response contract

- id: F-002
- severity: high
- file lines: `docs/host/design.md:1074`, `docs/host/design.md:1081`, `docs/host/design.md:1129`, `docs/host/design.md:1139`
- problem: ToolRuntime must not return a tool result to Engine until Host durably accepts the corresponding tool fact, but `reuse` says it directly reuses prior accepted facts and "does not fake a new tool fact". The design does not state what canonical record durably represents the model-visible response for the current `tool_call_id`.
- why this affects phase design / plan: normal tool protocols require a model-visible tool response for the current tool call. If an implementation returns a reused result without a current durable record, recovery / replay cannot reconstruct the exact messages the Engine consumed. If it appends `TOOL_RESULT_ACCEPTED`, it violates the stated rule that reuse must not create a fake new tool fact. Implementation agents will have to invent incompatible encodings for `reuse`.
- minimal correction: specify the canonical representation for reuse before ToolRuntime phase design. One safe shape is: `TOOL_CALL_GOVERNED(action=reuse)` carries the current `tool_call_id`, prior accepted result refs, prior digest / evidence anchors, and the exact model-facing reused response ref / digest. Host ack of that canonical event authorizes ToolRuntime to return the reused response, while no new evidence fact is created. Add a RunInputBuilder recovery rule for reconstructing reused tool responses.

### F-003 - high - Outbox delivery target source is not fully typed or precedence-defined

- id: F-003
- severity: high
- file lines: `docs/host/design.md:444`, `docs/host/design.md:455`, `docs/host/design.md:459`, `docs/host/design.md:954`, `docs/host/design.md:960`, `docs/host/design.md:961`, `docs/host/design.md:975`
- problem: the design requires Outbox delivery target to come from `HostCallContext`, Session binding, or explicit request fields, and forbids guessing from metadata. However `HostCallContext` only names an optional `delivery_target_hint`, request fragments do not show a typed delivery target field, and Session slot / binding semantics are only `(scope, slot_key)` plus metadata.
- why this affects phase design / plan: OutboxSink derives delivery work from terminal EventLog facts. Without a typed source and precedence rule, phase design can diverge on whether delivery target is mandatory at run acceptance, copied into terminal facts, read from session binding at terminal time, or treated as best-effort hint. That affects terminal event payload, outbox idempotency key derivation, channel fanout, retry records, and whether projection can be rebuilt deterministically from EventLog.
- minimal correction: define a typed delivery-target contract and precedence. For example: `delivery_target_ref` / `delivery_channel` are optional typed fields in `HostCallContext` or StartRun envelope, Session binding may provide a typed default, and the resolved target ref / channel / digest must be persisted in `RUN_ACCEPTED` or terminal facts. Also define the no-target behavior explicitly, such as "no outbox delivery record is produced".

### F-004 - high - replay of dirty final answers can be contaminated by generic assistant-conclusion inclusion

- id: F-004
- severity: high
- file lines: `docs/host/design.md:1316`, `docs/host/design.md:1319`, `docs/host/design.md:1321`, `docs/host/design.md:1372`, `docs/host/design.md:1405`, `docs/host/design.md:1459`
- problem: replay is explicitly used for dirty final answers, schema-invalid output, or output-policy failure, and should rebuild from accepted tool facts / evidence anchors. Separately, RunInputBuilder says assistant final answer / assistant conclusion is a typical fact that enters messages for conversation continuity. The design does not say whether the dirty source final answer is excluded, marked as invalid context, or included as a normal assistant message during replay.
- why this affects phase design / plan: if implementation agents follow the generic RunInputBuilder rule, replay may feed the invalid answer back to the model as ordinary assistant context, causing anchoring, repeated invalid structure, or apparent self-confirmation. If agents silently exclude all prior assistant conclusions, they may break normal follow-up continuity. This is a semantic contract gap in replay / RunInputBuilder policy, not an implementation detail.
- minimal correction: add a replay-specific inclusion rule: for `replay(run)` caused by dirty / schema-invalid / policy-failed output, the source final answer must not enter messages as an ordinary assistant conclusion. It may be excluded, summarized as rejected output with reason, or included only in a clearly marked repair instruction channel, while accepted tool facts and evidence anchors remain reusable.

### F-005 - high - README omits `STARTING` from Attempt status terminology

- id: F-005
- severity: high
- file lines: `dayu/README.md:40`, `dayu/README.md:51`, `docs/host/design.md:193`, `docs/host/design.md:196`, `docs/host/design.md:219`, `docs/host/design.md:333`, `docs/host/design.md:792`
- problem: `dayu/README.md` declares itself the project-level terminology source for Host / Engine / Service phase work, but its `Attempt status` list omits `STARTING`. `docs/host/design.md` defines `STARTING` as an Attempt state and uses it to separate durable dispatch intent from worker-accepted execution.
- why this affects phase design / plan: the `STARTING` boundary is central to dispatch failure, startup timeout, cancel during startup, and recovery classification. A phase plan derived from README terminology can accidentally collapse `ATTEMPT_STARTED` and `ATTEMPT_RUNNING`, weakening the exact boundary the Host design tries to preserve.
- minimal correction: update README terminology before phase work that relies on Attempt lifecycle. Add `STARTING` to `Attempt status` and state that `ATTEMPT_STARTED` means Host has durably created dispatch intent, while `ATTEMPT_RUNNING` means the worker accepted execution.

### F-006 - high - RunInputBuilder is coupled to a projection without a freshness / rebuild barrier

- id: F-006
- severity: high
- file lines: `dayu/README.md:80`, `dayu/README.md:98`, `docs/host/design.md:929`, `docs/host/design.md:1362`, `docs/host/design.md:1370`, `docs/host/design.md:1398`, `docs/host/design.md:1465`, `docs/host/design.md:1467`
- problem: Memory is defined as a projection / read model, and memory snapshot is not a fact truth source. At the same time, RunInputBuilder is the runtime entry that builds `AgentRunRequest.messages` and consumes `session memory snapshot`. The design also states that projection lag or sink failure cannot change RunInputBuilder output, but it does not define how a stale or missing memory snapshot is detected, refreshed, rebuilt, or bypassed.
- why this affects phase design / plan: without a freshness contract, phase agents have two unsafe choices. They can make RunInputBuilder depend on the memory projection being up to date, which couples the execution path to sink lag and projection failure. Or they can ignore memory snapshot freshness and produce different messages from the same EventLog depending on projection timing. Both outcomes violate the intended EventLog truth boundary and make memory / RunInputBuilder impossible to phase independently.
- minimal correction: define a memory-snapshot barrier before RunInputBuilder phase design. For example, RunInputBuilder should compute a required EventLog cursor for the session / run, accept a memory snapshot only when `snapshot_cursor >= required_cursor`, and otherwise rebuild the needed stable memory layer from canonical EventLog facts or enter a structured recoverable context-governance path. Memory snapshot remains an optimization / read model, not a blocking sink dependency.

### F-007 - high - policy ownership is named but not sliced by module boundary

- id: F-007
- severity: high
- file lines: `docs/host/design.md:381`, `docs/host/design.md:404`, `docs/host/design.md:408`, `docs/host/design.md:410`, `docs/host/design.md:416`, `docs/host/design.md:418`, `docs/host/design.md:1046`, `docs/host/design.md:1375`, `docs/host/design.md:1396`, `docs/host/design.md:1400`, `docs/host/design.md:1199`, `docs/host/design.md:1524`
- problem: `HostPolicyProviderSet` aggregates admission, worker selection, retry / replay, cancel, context budget, tool governance, and sink / outbox policy. The design says each provider must have a clear input, output, and owner, but it does not provide the ownership matrix or snapshot boundary across RunInputBuilder, ToolRuntime / TruncationManager, RemoteProxy attempt snapshot, Outbox / Sink, and memory / context governance.
- why this affects phase design / plan: if phase design treats `HostPolicyProviderSet` as a shared runtime object, modules will know too much about each other's policy surfaces: ToolRuntime may reach back into Host policy providers, RunInputBuilder may consume runner / tool / context policy through a god config, and sinks may depend on command-path policy objects. That creates hidden cycles and makes policy snapshot auditability hard, especially because attempts need immutable policy refs to explain execution.
- minimal correction: add a policy ownership matrix before implementation planning. Each policy should declare owner module, readers, decision time, durable snapshot / ref, and forbidden consumers. Composition root may assemble providers, but modules should receive explicit typed subsets or immutable snapshots, not the whole provider set. Sink / Outbox policy should be separate from command-path state-machine policy.

### F-008 - medium - RunInputBuilder trace observations can accidentally depend on tool trace projection

- id: F-008
- severity: medium
- file lines: `dayu/README.md:80`, `dayu/README.md:81`, `dayu/README.md:82`, `docs/host/design.md:52`, `docs/host/design.md:841`, `docs/host/design.md:860`, `docs/host/design.md:878`, `docs/host/design.md:888`, `docs/host/design.md:1421`
- problem: RunInputBuilder is told not to create an independent build-trace subsystem, and its context construction / evidence inclusion observations are to enter the "tool trace / trace system". Tool trace, however, is defined as an EventLog-derived projection / sink, not Host durable truth. The design does not specify whether RunInputBuilder writes neutral diagnostic / projection events that tool trace later consumes, or directly calls / depends on the tool trace projection.
- why this affects phase design / plan: a direct dependency from RunInputBuilder to tool trace storage or sink code would create a reverse dependency from the execution path into a projection. It would also make sink failure or retention policy visible to message construction diagnostics. This is not necessarily a runtime correctness blocker, but it creates avoidable coupling and unclear ownership for tracing phase slices.
- minimal correction: clarify the trace boundary. RunInputBuilder may emit diagnostic refs, structured logs, or `projection_signal` / canonical refs through Host-owned append / trace ports, but it must not call tool trace projection APIs or require tool trace availability. Tool trace should consume those committed events / refs as a sink.

### F-009 - medium - Host handle mixes command-path dependencies with background runners

- id: F-009
- severity: medium
- file lines: `docs/host/design.md:381`, `docs/host/design.md:383`, `docs/host/design.md:387`, `docs/host/design.md:393`, `docs/host/design.md:394`, `docs/host/design.md:461`, `docs/host/design.md:473`, `docs/host/design.md:841`, `docs/host/design.md:860`, `docs/host/design.md:952`, `docs/host/design.md:957`, `docs/host/design.md:964`
- problem: the Host handle / composition root dependency list includes both command-path dependencies such as durable store, EventLog appender, admission, dispatcher, ToolRuntime factory, and RunInputBuilder, and background projection / delivery dependencies such as Observer / Sink runner and Outbox dispatcher. The design correctly says terminal transactions must not synchronously write outbox and sinks cannot affect Host state, but it does not explicitly separate public command handles from background runtime supervisors.
- why this affects phase design / plan: if implementation agents make all public Host operations receive a handle exposing Sink runner and Outbox dispatcher, it becomes easy to call projection / delivery code from command transactions or after-commit paths in ad hoc ways. That would weaken the Observer / Sink boundary and turn the handle into the god object the design says it is not.
- minimal correction: split the composition contract in the phase design. Public mutating operations should require a `HostCore` / command handle with store, EventLog, admission, dispatch intent, RunInputBuilder, and after-commit wakeup port. Sink runners and OutboxDispatcher should live behind a `HostRuntimeSupervisor` / background runner that consumes committed EventLog cursors. If one top-level composition root owns both, expose them through separate typed facets.

## Open Questions

- Should `resolve_wait` use `HostCallContext.client_request_id`, its own `idempotency_key`, or both? The design is probably implementable either way, but the phase design should pick one typed envelope rule before writing API dataclasses.
- Should `permission_denied` be produced only by Host policy over provided claims, or can Host also return it for missing claims? This is phase-local but should be decided in public API error tests.
- For memory freshness, should RunInputBuilder rebuild directly from EventLog when memory snapshot is stale, or should context governance maintain a synchronous command-side memory materialization? The latter risks turning memory into more than a projection, so the safer default is EventLog rebuild / recoverable compact path.

## Residual Risks

- The design is broad. The next phase plan needs strict slice boundaries so EventLog schema, public API dataclasses, recovery, ToolRuntime, Outbox, and memory projection do not become one oversized implementation slice.
- SQL schema, wire protocol, typed event contracts, and test matrices are intentionally deferred. That is acceptable for this stage, but each phase design must turn the relevant semantic contract into concrete typed schemas and invariant tests before implementation.
- Over-coupling risk is concentrated around policy providers, memory freshness, and composition root shape. The phase plan should explicitly split command path, projection / sink path, and background runtime path.

## Readiness Verdict

No blocking findings.

Verdict: ready with phase-local followups.

Reason: the core Host architecture boundary is coherent enough to guide next-stage phase design: Host owns governance truth, Engine remains single-run execution, remote workers do not own state, EventLog canonical facts drive recovery, and projections stay derived. The high findings above, including the added over-coupling findings, should be resolved before their corresponding phase designs are handed to implementation agents, but they do not prevent starting the phase design process.
