# Host Phase Map / Implementation-Control Review — AgentDS

**Review date**: 2026-05-13
**Reviewer**: AgentDS
**Gate**: Host phase map / implementation-control review
**Target files**:
- `docs/design.md`
- `docs/host/implementation-control.md`

---

## P0

### P0-1. Truth-source path discrepancy — `docs/design.md` is not Host architecture

**Files and lines**:
- `docs/host/implementation-control.md` line 29–36, "真源层级" section
- `docs/design.md` (entire file, 59 lines)
- `docs/host/design.md` (entire file, ~2191 lines)

**Finding**:

The user explicitly asked to review `docs/design.md` as a Host architecture source alongside `docs/host/implementation-control.md`. The "真源层级" section in implementation-control.md states:

> ```
> design.md
>   -> Host 架构真源
>   -> 定义架构边界、状态机、公共接口、EventLog、恢复、并发、远程执行和关键治理路径
> ```

This refers to `design.md` without a `docs/host/` prefix. However:

1. `docs/design.md` is a 59-line document about logging/observability only. It contains no phase map, no state machine, no EventLog design, no recovery design, no public API design — none of the content the "真源层级" claims it provides.
2. The actual Host architecture document is `docs/host/design.md` (~2191 lines), which defines all the architecture boundaries, state machines, public interfaces, EventLog, recovery, concurrency, remote execution, and governance paths.
3. All 15 Phase entries in the Phase Map consistently reference `docs/host/design.md` under "对应设计章节" — confirming the real source.
4. The truth-source hierarchy in `implementation-control.md` is therefore misleading: it says `design.md` is the Host architecture source, but the real source is `docs/host/design.md`.

**Why it matters**: Any agent or reviewer reading the "真源层级" section will look for Host architecture in `docs/design.md` and find only logging content. This misdirects implementation agents and reviewers. The review scope itself was affected — the user asked to review `docs/design.md` based on this ambiguous reference.

**Proposed fix**: Change the "真源层级" in `docs/host/implementation-control.md` line 29 to reference `docs/host/design.md` explicitly:

```text
docs/host/design.md
  -> Host 架构真源
  -> 定义架构边界、状态机、公共接口、EventLog、恢复、并发、远程执行和关键治理路径
```

---

### P0-2. Phase 0 positioned before Phase 1 creates false blocking dependency for Phases 1-9

**Files and lines**:
- `docs/host/implementation-control.md` line 279, Phase 1 前置条件: "Phase 0 已完成"
- `docs/host/implementation-control.md` line 1096, 追踪区: "在进入 Host Context Governance / compact phase plan 前，必须先开一个 Engine contract cleanup work unit"

**Finding**:

Phase 0 (Engine Context Compaction Event cleanup) is positioned as Phase 0 in the phase map, making it the first phase that ALL subsequent phases depend on. Phase 1 lists Phase 0 as a hard precondition.

However, the tracking section at line 1096 states the actual dependency scope:

> "在进入 Host Context Governance / compact phase plan 前，必须先开一个 Engine contract cleanup work unit"

This means Phase 0 only needs to complete before Phase 10 (Context Governance), not before Phase 1 (公共契约与 runtime 基础设施).

Phase 0's scope is solely Engine code changes — modifying `context_compaction_requested` event semantics, clarifying `budget_state` as unknown/optional, updating Engine README and tests. None of this affects:
- Phase 1 (types, runtime helpers, ToolBundle)
- Phase 2 (SQLite store, EventLog, payload)
- Phase 3 (state machine, admission)
- Phase 4 (public API)
- Phase 5 (dispatch)
- Phase 6 (ToolRuntime)
- Phase 7 (Tool Awaiting)
- Phase 8 (Projection Core)
- Phase 9 (Memory)

Phase 1 acknowledges this with a soft-exception clause: "如果用户明确决定 Phase 0 只阻塞 Context Governance，则必须在本 phase plan 中写明该例外与后续回补点。" But this workaround shouldn't be necessary — the dependency is structurally wrong.

**Why it matters**: If the user does not confirm Engine code changes, the entire Host implementation pipeline is blocked at Phase 1. This is a false dependency that creates a single point of failure for all phases, when only Phase 10 actually needs Phase 0.

**Proposed fix**: Two options:

1. **Recommended**: Renumber Phase 0 as a parallel track (e.g., "Phase 0a") that runs independently of Phases 1-9, with its completion required only before Phase 10. Phase 1 removes Phase 0 from its preconditions entirely.

2. **Alternative**: Keep Phase 0 numbering but change Phase 1's precondition to explicitly state that Phase 0 is NOT a precondition for Phase 1, only for Phase 10. This is weaker because it still implies sequencing that doesn't exist.

Also update Phase 10 前置条件 to reference the renamed track explicitly.

---

### P0-3. Phase 12 (Audit/Tool Trace/Outbox) unnecessarily depends on Phase 11 (Recovery)

**Files and lines**:
- `docs/host/implementation-control.md` line 908-911, Phase 12 前置条件

**Finding**:

Phase 12 lists "Phase 11 recovery 已完成" as a precondition. However, Audit, Tool Trace, and Outbox are projection sinks that only consume committed EventLog facts. Per the design:

- `docs/host/design.md` line 1095-1096: "Sink 的输入是 committed EventLog event，不是事务中的临时状态。"
- `docs/host/design.md` line 1102: "Sink lag 只影响派生视图新鲜度，不影响 Run admission、cancel、resume、terminal 收口。"
- `docs/host/design.md` line 1103: "Sink 失败只能更新 sink-local retry / error state，不能回滚 EventLog，也不能改变 Run / Attempt 状态。"

Recovery creates new Attempts and canonical events (`ATTEMPT_LOST`, `RUN_RECOVERING`, `RUN_STARTED(start_reason=recovery)`, `ATTEMPT_STARTED`), but these are normal canonical facts in the EventLog. The Audit/Tool Trace/Outbox sinks process them as they would any other canonical fact — the event schema is defined in Phase 3 (canonical event contract matrix §13.3), not Phase 11.

Phase 12's real dependencies are:
- Phase 8 (Projection Core) — for the consumer framework, checkpoint
- Phase 6 (ToolRuntime) — for `ToolTraceDiagnosticEmitter` refs

Phase 11 is not semantically needed.

**Why it matters**: Serializing Phase 12 after Phase 11 unnecessarily delays audit/trace/outbox observability. These sinks could be developed in parallel with Phase 9 (Memory), Phase 10 (Context Governance), and Phase 11 (Recovery), reducing the critical path length.

**Proposed fix**: Remove Phase 11 from Phase 12's 前置条件. Keep only Phase 8 and Phase 6. If there's a testing concern (e.g., wanting recovery events in audit test data), that should be handled by test fixtures using synthetic EventLog events, not by sequencing the entire phase after recovery.

---

## P1

### P1-1. "真源层级" references bare `design.md` while all Phase entries use `docs/host/design.md`

**Files and lines**:
- `docs/host/implementation-control.md` line 29 ("design.md")
- All 15 Phase entries under "对应设计章节" reference `docs/host/design.md`

**Finding**:

This is a self-inconsistency within `implementation-control.md` itself. The "真源层级" section references `design.md` without a path prefix, but every Phase entry uniformly references `docs/host/design.md` as the design source. Even though P0-1 already addresses making the path explicit, this finding notes the internal contradiction.

**Why it matters**: Someone scanning only the "真源层级" section will be misled about which file is authoritative. Someone scanning only the Phase entries will find the correct file but won't notice the discrepancy.

**Proposed fix**: Same fix as P0-1 — update the "真源层级" to use `docs/host/design.md`.

---

### P1-2. Phase 3 scope overlaps with Phase 2 scope on table creation

**Files and lines**:
- `docs/host/implementation-control.md` line 340-341, Phase 2 范围: "Host store schema、transaction API、EventLog appender / reader、payload table / descriptor、idempotency table、host instance liveness record"
- `docs/host/implementation-control.md` line 398, Phase 3 范围: "Session / Run / Attempt tables、active index、queue index、transition service、admission service、promotion service"

**Finding**:

Phase 2 creates the "Host store schema" which presumably includes the base tables. Phase 3 then says it modifies "Session / Run / Attempt tables." The ownership boundary is unclear:
- Are Session/Run/Attempt tables created in Phase 2 (as part of "Host store schema") or Phase 3 (as part of state machine)?
- If created in Phase 2, Phase 3 would need to alter existing tables — creating migration debt.
- If created in Phase 3, Phase 2's "Host store schema" scope is vague.

Phase 2's scope says it creates the SQLite schema, but Phase 3 then creates the three most important tables. The division of table ownership between schema foundation (Phase 2) and state machine (Phase 3) needs explicit definition.

**Why it matters**: Without clear table ownership, the Phase 2 and Phase 3 implementation agents may create conflicting or overlapping schemas, or Phase 2 may create stub tables that Phase 3 must then migrate.

**Proposed fix**: Phase 2 scope should explicitly enumerate which tables it creates (e.g., `event_log`, `payload`, `idempotency_record`, `host_instance`, `projection_checkpoint`) and explicitly state that Session/Run/Attempt tables are created in Phase 3. Or, Phase 2 creates ALL tables and Phase 3 only adds indexes and transition logic. Either approach works, but it must be explicit.

---

### P1-3. wait record table creation not explicitly assigned to any phase scope

**Files and lines**:
- `docs/host/implementation-control.md` line 340-341, Phase 2 范围
- `docs/host/implementation-control.md` line 628, Phase 7 范围: "wait record store、ToolAwaitingOutcome accept path"

**Finding**:

Phase 7 scope says it creates "wait record store", but Phase 2 scope does not mention wait record tables. Phase 2 says it creates "Host store schema" in general terms, but the specific tables enumerated are: "EventLog appender / reader、payload table / descriptor、idempotency table、host instance liveness record."

The wait record table is a durable governance table — it should be part of the schema foundation or explicitly noted as created in Phase 7. If created in Phase 7, Phase 7 must also be permitted to extend the SQLite schema, which is currently only in Phase 2's scope.

**Why it matters**: Phase 7 implementation may attempt to create wait record tables without clear authority to modify the SQLite schema. If Phase 2 hardens the schema, Phase 7's schema additions may conflict.

**Proposed fix**: Either:
1. Add "wait record table" to Phase 2's scope as a schema element (preferred — it's a durable governance table), or
2. Explicitly add "schema extension for wait record table" to Phase 7's scope.

---

### P1-4. Phase 10 (Context Governance) preconditions don't include Phase 6 (ToolRuntime)

**Files and lines**:
- `docs/host/implementation-control.md` line 790-794, Phase 10 前置条件

**Finding**:

Phase 10 lists these preconditions: Phase 0, Phase 9 (memory), Phase 5 (dispatch). But the reactive context governance path needs to:
- Understand EngineEvent `context_compaction_requested` → which is ingested through the path built in Phase 5
- Close current Attempt by policy → which goes through state machine from Phase 3 and dispatch from Phase 5
- Potentially interact with tool execution states (tools running during context overflow)

The reactive compact path (`docs/host/design.md` line 2009-2020) says:
```
reactive trigger from EngineEvent.context_compaction_requested
  -> validate attempt_id + execution_id
  -> append CONTEXT_COMPACTION_REQUESTED(trigger_source=reactive)
  -> close current Attempt according to policy
```

This requires the EngineEvent ingest path to correctly identify and route `context_compaction_requested` events. The ingest path is built in Phase 5. Phase 5 IS listed as a precondition. However, the tool-related diagnostic refs needed for compact events (`docs/host/design.md` line 2029: "provider / runner error refs、provider request id、budget snapshot refs") partially come from ToolRuntime (Phase 6).

**Why it matters**: Phase 10 may need `ToolTraceDiagnosticEmitter` from Phase 6 to record compact diagnostics. If Phase 6 is skipped, compact event tracing is incomplete, though not broken.

**Proposed fix**: Add Phase 6 to Phase 10's preconditions with a note that only the diagnostic emitter interface (not full ToolRuntime governance) is needed. Alternatively, explicitly scope the compact diagnostic emission to not require Phase 6.

---

## P2

### P2-1. Phase 0 "对应设计章节" references Host design.md for Engine changes

**Files and lines**:
- `docs/host/implementation-control.md` line 218-220, Phase 0 对应设计章节: "docs/host/design.md §25 Context Governance"

**Finding**:

Phase 0 is about modifying Engine code — its scope is "Engine context overflow event contract、Engine README、Engine design docs、相关 Engine tests." Yet its "对应设计章节" references `docs/host/design.md` §25 (Context Governance), a Host design document.

The correct reference for Phase 0's Engine work should include Engine-specific design documents (e.g., `docs/engine/design.md` or Engine README), because the change is to Engine semantics, not Host semantics. The Host design §25 provides the context for WHY the Engine change is needed, but the WHAT (the actual contract to modify) is in Engine docs.

**Why it matters**: The implementation agent working on Phase 0 needs Engine contract documentation to know what to change, not just Host documentation explaining why.

**Proposed fix**: Add Engine-specific design references to Phase 0's "对应设计章节":

```text
对应设计章节：
- Engine context overflow event contract (当前 Engine 实现)
- docs/engine/design.md §<overflow event section>
- docs/host/design.md §25 Context Governance (provides the Host-side motivation and boundary)
- docs/host/implementation-control.md 追踪区 `Engine Context Compaction Event 语义前置`
```

---

### P2-2. Phase 14 unnecessarily depends on Phase 13 (Remote)

**Files and lines**:
- `docs/host/implementation-control.md` line 1027-1028, Phase 14 前置条件: "Phase 8 projection core、Phase 11 recovery、Phase 12 Audit / Tool Trace / Outbox、Phase 13 remote 已完成"

**Finding**:

Phase 14 (Retention/Purge/Production Hardening) lists Phase 13 (Remote) as a precondition. But `purge_session` operates on local Host durable state — it deletes local SQLite rows, local payloads, local projection data. The design explicitly says purge does NOT affect remote execution:
- `docs/host/design.md` line 155-160: Purge scope is "Host 本地数据"
- The Remote phase deals with transport substitution, not durable state ownership

Phase 14's integration tests include "multi-process / remote / recovery production smoke" — but remote smoke testing can be done with Phase 13 as a parallel dependency (both must complete before Phase 14) rather than a sequential one (Phase 13 must complete before Phase 14 starts).

**Why it matters**: Minor unnecessary serialization. Phase 14 could start immediately after Phase 12 if remote smoke tests are deferred to Phase 13.

**Proposed fix**: Either:
1. Remove Phase 13 from Phase 14 preconditions, or
2. Note that Phase 13 is only needed for the "remote smoke" slice of Phase 14, not for purge/tombstone/projection-rebuild slices.

---

### P2-3. Phase 4 defers `purge_session` implementation to Phase 14 — no explicit contract handoff tracking item

**Files and lines**:
- `docs/host/implementation-control.md` line 460-461, Phase 4 不做: "不实现 `purge_session` 的 destructive cleanup；该能力在 Phase 14 落地"
- `docs/host/implementation-control.md` line 482, Phase 4 交付物 includes `PurgeSessionResult` type

**Finding**:

Phase 4 defines `PurgeSessionResult` type and the `purge_session` function signature, but defers implementation to Phase 14. The Phase 4 → Phase 14 gap spans 10 phases. During this time, the API function exists but returns an error or unimplemented state. If Phase 4 defines the function with a specific signature and Phase 14 must match it, the interface contract between them should be explicitly tracked.

Phase 4's "后续依赖" section lists: "需要追踪到后续 phase 的事项：执行、projection、memory、remote 后续接入不得绕过 public command path。" — but doesn't specifically call out the `purge_session` contract handoff.

**Why it matters**: If Phase 14 changes the `purge_session` semantics (e.g., adds required fields to `PurgeSessionRequest`), it may break the API signature defined in Phase 4. A tracking item ensures Phase 14 doesn't silently deviate.

**Proposed fix**: Add to Phase 4 "后续依赖 → 需要追踪到后续 phase 的事项":

```text
- `purge_session` 的函数签名、PurgeSessionResult 类型和幂等语义由 Phase 4 定义，Phase 14 实现时不得改变公共契约；如需变更，必须先修改 Phase 4 代码。
```

---

### P2-4. No explicit tracking for cross-phase recovery + projection rebuild integration test

**Files and lines**:
- `docs/host/implementation-control.md` Phase 11 验证要求 (line 884-888)
- `docs/host/implementation-control.md` Phase 14 验证要求 (line 1058-1062)

**Finding**:

Phase 11 tests "crash after USER_INPUT_ACCEPTED before final answer, restart produces answer" and Phase 14 tests "projection rebuild." But the cross-cutting scenario — crash during a running run with active tool executions → recovery scan → new attempt → terminal → projection rebuild from post-recovery EventLog — is not explicitly listed as a test requirement in either phase.

This scenario exercises: EventLog append during recovery, stale execution_id rejection from old attempt, projection checkpoint advancement after recovery events, and audit/trace consistency across the recovery boundary.

**Why it matters**: This is the most complex multi-phase integration scenario and the most likely to expose subtle ordering bugs between EventLog, state machine, projection checkpoint, and recovery.

**Proposed fix**: Add to Phase 14 验证要求:

```text
- integration tests: full crash-recovery-projection-rebuild scenario: crash after USER_INPUT_ACCEPTED + tool execution, recovery scan, new attempt terminal, projection rebuild verifies all events from both old and new attempts.
```

---

## No Finding Notes

The following aspects were checked and found acceptable:

1. **Phase dependency ordering for core path (Phase 1→2→3→4→5)**: The foundational dependency chain (types → store → state machine → API → dispatch) is correct. Each phase provides exactly what the next needs.

2. **Phase 6 (ToolRuntime) → Phase 7 (Tool Awaiting) dependency**: Tool Awaiting depends on ToolRuntime accept barrier; correctly expressed.

3. **Phase 8 (Projection Core) → Phase 9 (Memory) dependency**: Memory projection depends on the projection runner framework; correctly expressed.

4. **Phase 5 (Dispatch) → Phase 11 (Recovery) dependency**: Recovery needs dispatch records and LocalProxy from Phase 5; correctly expressed.

5. **Phase 8 + Phase 5 → Phase 9 (Memory) dependency**: Memory needs projection runner AND RunInputBuilder provider boundary; correctly expressed.

6. **Phase 11 (Recovery) → Phase 13 (Remote) dependency**: Remote needs positive orphan proof from recovery; correctly expressed.

7. **"不做" sections are consistent with design non-goals**: Each phase's explicit exclusions align with `docs/host/design.md` §28 (第一版 Non-goals).

8. **Tracking section covers cross-cutting concerns**: External job cancel, tool trace provider request tracking, SQLite multi-process verification, remote exactly-once non-goal, session purge, cross-layer testing strategy, and UI/Service outbox dedup boundaries are all tracked.

9. **Forced constraint section (强制约束) correctly restates design invariants**: All 20+ constraints are faithful restatements of `docs/host/design.md` invariants, with no new architectural decisions introduced.

10. **Phase entry template compliance**: All 15 phases use the required template. The "建议 slice 切分" are all reasonable starting points for phase discussion.

11. **Phase 0 exception clause (Phase 1 前置条件)**: Despite the structural issue (P0-2), the exception clause "如果用户明确决定 Phase 0 只阻塞 Context Governance" is a thoughtful escape hatch that shows awareness of the dependency tension.

12. **`STEER_LOST` is correctly classified as non-canonical**: In `docs/host/design.md` line 858-859: "它不是 canonical fact，不驱动 recovery、memory、resume 或 Run 状态迁移。" This is consistent with the Phase 3 state machine design.

13. **Phase 9 (Memory) explicitly excludes final_answer as verified fact**: Phase 9 验证要求 includes "final_answer not verified fact" — consistent with the design's strongest invariant.

---

## Residual Risks

These risks are accepted as non-blocking for the phase map as drafted, but should be tracked:

1. **Phase 4 defers 4 capabilities to later phases** (`resolve_wait` to Phase 7, execution to Phase 5, `purge_session` to Phase 14, UI/Service channel delivery to later work). Deferred API functions that return "not implemented" errors for 10+ phases may create friction for integration testing of intermediate phases. Mitigation: Phase 4 should implement these as explicit `not_implemented` stubs with clear error messages, not silently succeed or crash.

2. **`ToolTraceDiagnosticEmitter` defined in Phase 6, sinks in Phase 12**: Phases 6-11 will have no persistent tool trace observability during development. Mitigation: Phase 6's diagnostic emitter can log to DEBUG/VERBOSE as an interim output until Phase 12 wiring.

3. **Multi-phase SQLite schema evolution**: Phases 2, 3, 7, 8, 9, 10, 11 each add tables or columns to the SQLite store. The phase map says "migration-free fresh DB bootstrap" (Phase 2 line 361), but doesn't address whether Phase 3+ schemas are additive (new tables only) or require migration of Phase 2 tables. If each phase modifies existing tables, the cumulative migration surface grows with each phase. Mitigation: Explicitly require all Phase 3+ schema changes to be additive (new tables/indexes only, no ALTER of existing tables) or define a migration strategy in Phase 2 that subsequent phases follow.

4. **Phase 0 Engine modification requires user confirmation**: Phase 0's only precondition is "用户明确确认允许修改 Engine 代码." If this confirmation is delayed or denied, Phases 1-9 should not be blocked (as noted in P0-2). The exception clause in Phase 1 is a workaround, not a structural solution.

---

## Summary

**Blocking findings (P0)**: 3
- P0-1: The "真源层级" section references `design.md` but the real Host architecture is `docs/host/design.md`
- P0-2: Phase 0 blocks Phases 1-9 but only Phase 10 semantically needs it
- P0-3: Phase 12 (Audit/Tool Trace/Outbox) unnecessarily depends on Phase 11 (Recovery)

**Non-blocking findings (P1)**: 4
**Minor findings (P2)**: 4
**No-finding confirmations**: 13
**Residual risks**: 4

All P0 findings are structural dependency/sequencing issues. They do not indicate flaws in the underlying design (`docs/host/design.md`), which is thorough and internally consistent. The issues are in how the implementation-control document maps design sections to phases and sequences those phases.

The phase map is otherwise well-structured: canonical events are correctly classified, state transitions are explicit, forced constraints faithfully restate design invariants, and the tracking section covers the major cross-cutting concerns.
