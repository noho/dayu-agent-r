# Post-P10.5 Plan Readiness Review

**Reviewer**: MiMo (challenge reviewer)
**Date**: 2026-05-18
**Gate**: Host Phase 10.5 public API and contract decision review before implementation-ready plan
**Review type**: plan readiness / adversarial challenge
**Reviewed artifacts**: `docs/host/design.md`, `docs/host/implementation-control.md`, `docs/host/post-p10.md`
**Prior challenge artifacts**: `docs/reviews/post-p10-public-contract-challenge-mimo-20260518.md`, `docs/reviews/post-p10-wiring-smoke-challenge-ds-20260518.md`, `docs/reviews/post-p10-codex-challenge-20260518.md`

## Review Question

If we enter P10.5 plan and implementation based on these docs, can we ensure that a future real production Service can call only Host public interface and contract to complete an ordinary local multi-turn conversation loop?

## Conclusion

**P10.5 can proceed to implementation-ready planning.** The three design/control documents are now consistent on all P10.5 public contract decisions. All prior blocking findings from MiMo, DS, and Codex challenge reviews have been accepted and resolved into the docs. There are zero blocking findings, two non-blocking findings, and two clarification findings.

---

## Findings

### F1. Non-blocking: Smoke Coverage Matrix naming gap between post-p10.md and implementation-control.md

**Severity**: non-blocking
**Evidence**: `docs/host/post-p10.md:76-145` (S1-S5 matrix), `docs/host/implementation-control.md:1237` (smoke list), `docs/host/implementation-control.md:1256-1258` (verification requirements)

**Problem**: post-p10.md defines S1-S5 smoke categories (no-tool multi-turn, mock-tool wiring, real-runner matrix, compact, cancel). implementation-control.md Phase 10.5 verification requirements list: "real-runner no-tool multi-turn smoke, mock-tool wiring smoke, real-runner matrix smoke, compact smoke, WAITING resume smoke, steer / retry / replay local smoke, cancel smoke, close_session smoke." The two lists cover the same logical space but use different naming/grouping:

- S5 cancel in post-p10.md maps to "cancel smoke" in implementation-control.md.
- WAITING resume smoke appears in implementation-control.md but has no explicit S-number in post-p10.md (it's covered by G9 in the gap tracking list, not the S-matrix).
- steer / retry / replay appear as G6/G7/G8 in post-p10.md gap tracking but are listed in implementation-control.md's smoke requirements without S-number.
- close_session smoke appears in implementation-control.md but not as an S-number in post-p10.md.

**Impact**: Implementation agent could misread which smokes are mandatory success signals vs. which are gap tracking items. Review agent could miscount coverage.

**Suggested fix**: P10.5 plan should explicitly reconcile the S1-S5 matrix from post-p10.md with the smoke list from implementation-control.md, producing a single unified coverage checklist. This is a planning step, not a doc change blocker.

---

### F2. Non-blocking: `open_host(options)` typed options shape not fully specified as a Python dataclass

**Severity**: non-blocking
**Evidence**: `docs/host/design.md:851-865` (options boundary), `docs/host/implementation-control.md:1179` (construction-time params), `docs/host/post-p10.md:480-481` (options shape)

**Problem**: All three docs agree that `open_host(options)` must accept typed construction-time parameters for durable store roots, runner/worker factory, ToolBundle, ContextCompactor, compactor execution baseline, budget policy, memory catch-up, and stream fanout ports. However, the exact Python dataclass shape (field names, types, defaults, required vs optional) is not specified as a concrete type definition. design.md gives the conceptual boundary, post-p10.md lists the parameters, and implementation-control.md references them, but none provide a frozen `OpenHostOptions` dataclass definition.

**Impact**: Implementation agent must design the concrete options dataclass. Field names and types can be derived from the documented requirements, but this is a design decision that falls within implementation scope. Since all three docs agree on the *content* of options, the risk of misalignment is low.

**Suggested fix**: P10.5 plan Slice 1 should include defining the concrete `open_host` options type. The plan should reference design.md §11 and post-p10.md §建议目标 as the source of required fields. No prior user discussion is needed since the parameter boundary is already frozen.

---

### F3. Clarification: `HostClosedError` public type identity

**Severity**: clarification
**Evidence**: `docs/host/design.md:853` ("typed `HostClosedError` or equivalent Host lifecycle exception"), `docs/host/implementation-control.md:1224` ("close语义不得重开讨论"), `docs/host/design.md:1175-1192` (error classification)

**Problem**: design.md specifies `HostClosedError` as "typed `HostClosedError` or equivalent Host lifecycle exception" and lists the public error codes as `not_found`, `invalid_state`, `conflict`, `idempotency_conflict`, `permission_denied`, `unsupported_operation`, `internal_error`. It does not explicitly state whether `HostClosedError` is:
- A standalone public exception class (like `HostClosedError(HostApiError)`), or
- `HostApiError` with code `invalid_state` and a specific detail, or
- A separate exception hierarchy not inheriting from `HostApiError`.

The docs are clear that it "does not write EventLog, does not return command-level `invalid_state`, and is not confused with `Session CLOSED`, not found, purged, retry precondition failed." This semantic boundary is sufficient for implementation.

**Impact**: Low. Implementation agent can choose between a standalone exception class or a HostApiError subclass with a distinguishing code. The semantic requirements are clear; only the Python type hierarchy is unspecified. This is a standard implementation decision.

**Suggested fix**: No doc change needed. P10.5 plan should note the design choice made for `HostClosedError` type identity. If a new error code is needed (e.g., `host_closed`), it should be added to the error classification in design.md as part of implementation.

---

### F4. Clarification: S5 cancel and WAITING resume smoke coverage checklist gaps

**Severity**: clarification
**Evidence**: `docs/host/post-p10.md:133-145` (S5 cancel smoke requirements), `docs/host/post-p10.md:267-270` (G9 WAITING resume), `docs/host/implementation-control.md:1256-1258` (verification requirements)

**Problem**: post-p10.md S5 defines detailed cancel smoke requirements (accepted/queued cancel, pre-dispatch cancel, active cancel visibility, session-scope cancel, event/read path, close boundary, Recovery exclusion). post-p10.md G9 defines WAITING resume smoke requirements. implementation-control.md verification requirements list both "WAITING resume smoke" and "cancel smoke." However, neither document provides a coverage checklist entry format that maps each S5 sub-requirement and G9 sub-requirement to covered / not covered but accepted / blocking gap.

**Impact**: Low. The requirements are documented; only the checklist template is missing. P10.5 plan and review agent can construct the checklist from the documented requirements.

**Suggested fix**: P10.5 plan should include a unified coverage checklist template that maps each smoke sub-requirement to its expected coverage status. This is a planning artifact, not a doc change.

---

## Consistency Verification

### 1. P10.5 goal, scope, non-goals

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| Goal: freeze ordinary local multi-turn public contract | §11 | Phase 10.5 目标 | 结论 + 建议目标 | Yes |
| Non-goal: Recovery | §27 | Phase 10.5 不做 | 当前讨论暂不考虑 | Yes |
| Non-goal: Service/CLI/WeChat/GUI | §2 | Phase 10.5 不做 | 当前讨论暂不考虑 | Yes |
| Non-goal: ToolsDiscovery/ScenePrepare | §3 | Phase 10.5 不做 | 当前讨论暂不考虑 | Yes |
| Non-goal: web tools migration | - | Phase 10.5 不做 | 当前讨论暂不考虑 | Yes |
| Non-goal: ConfigLoader | - | Phase 10.5 不做 | 当前讨论暂不考虑 | Yes |

### 2. Public API shape

| API | design.md | implementation-control.md | post-p10.md | Consistent? |
|-----|-----------|--------------------------|-------------|-------------|
| `open_host(options)` async context manager | §11 (lines 851-853) | Phase 10.5 (line 1178) | 建议目标 (line 476) | Yes |
| Handle methods: ensure/create/get/close/purge session, get_run, submit_followup, cancel_run, cancel_session_runs, retry_run, replay_run, resolve_wait, watch_session_events | §11 (lines 920-937) | Phase 10.5 (line 1180-1183) | 缺失清单 #1 (line 351) | Yes |
| `watch_session_events(session_id) -> AsyncIterator[HostEvent]` | §11 (lines 871-903) | Phase 10.5 (line 1227) | G4 (lines 222-224) | Yes |
| `SubmitFollowupRequest` shape with tool_names, runner_spec, runner_options, agent_policy | §11 (lines 1086-1098) | Phase 10.5 (lines 1230-1231) | G5 (lines 232-233), G7/G8 | Yes |
| `FollowupSnapshot` with accepted_run_id, accepted_run_status | §11 (line 1169) | Phase 10.5 (line 1230) | S1 (line 88) | Yes |
| `start_run` removed from public namespace | §11 (line 1159) | Phase 10.5 (line 1180) | Public API 变更护栏 (line 50) | Yes |
| `create_host_command_handle` internal only | §11 (line 942) | Phase 10.5 (line 1181) | 缺失清单 #1 (line 349) | Yes |
| `HostLocalRuntime` / `HostLocalExecutionOptions` internal only | §11 (line 943) | Phase 10.5 (line 1181) | 建议目标 (line 476) | Yes |

### 3. Runtime opener

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| Async-only, `open_host(options)` | §11 (line 851) | Phase 10.5 (line 1178) | 建议目标 (line 477) | Yes |
| Close = handle lifecycle, not cancel | §5 (line 346), §11 (line 855) | Phase 10.5 (line 1225) | G11 (line 285-289) | Yes |
| Close shutdown order | §11 (line 857) | Phase 10.5 (line 1225) | 建议目标 (line 479) | Yes |
| `HostClosedError` post-close API calls | §11 (line 853) | Phase 10.5 (line 1224) | 建议目标 (line 478) | Yes |

### 4. Event stream

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| Session-level live watch is main event entry | §11 (line 1130) | Phase 10.5 (line 1227) | G4 (line 224) | Yes |
| `HostEventView` internal only | §11 (line 1172) | Phase 10.5 (line 1227) | Public API 变更护栏 (line 55) | Yes |
| `stream_run_events` internal only | §11 (line 1155) | Phase 10.5 (line 1227) | Public API 变更护栏 (line 55) | Yes |
| `HostEvent` terminal view fields: content, filtered, degraded, finish_reason, terminal status | §11 (line 908) | Phase 10.5 (line 1235) | G15 (line 329) | Yes |

### 5. Final answer path

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| Terminal HostEvent is sole public final answer path | §11 (line 1148) | Phase 10.5 (line 1235) | G15 (line 329) | Yes |
| No `wait_final_answer(...)` public API | §11 (line 1148) | Phase 10.5 不做 (line 1221) | Public API 变更护栏 (line 46) | Yes |
| No public payload reader / `read_payload(ref)` | §11 (line 1149) | Phase 10.5 不做 (line 1221) | Public API 变更护栏 (line 54) | Yes |

### 6. Runner/tool/compactor options

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| Per-run runner_spec/runner_options/agent_policy in SubmitFollowupRequest | §11 (lines 1096-1098) | Phase 10.5 (line 1230) | 缺失清单 #7 (line 411) | Yes |
| Per-run tool_names selector | §10.1 (lines 798-807) | Phase 10.5 (line 1231) | G14 (lines 314-321) | Yes |
| Compactor execution baseline separated from ordinary Run override | §11 (line 865) | Phase 10.5 (line 1232) | G13 (line 307-309) | Yes |
| Compactor uses independent opener construction-time params | §11 (line 865) | Phase 10.5 (line 1232) | 缺失清单 #8 (line 431) | Yes |

### 7. Cancel/close/session lifecycle

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| close_session != cancel != opener close | §5 (line 346-348) | Phase 10.5 (line 1234) | G11 (lines 285-291) | Yes |
| close_session does not cancel active Runs | §5 (line 312) | Phase 10.5 (line 1234) | G11 (line 285) | Yes |
| Purge excluded from P10.5 | §5 (line 346) | Phase 10.5 不做 (line 1218) | G11 (line 286) | Yes |

### 8. Wait/resolve

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| resolve_wait public contract frozen in P10.5 | §11 (line 1162) | Phase 10.5 (line 1233) | G9 (line 269-270) | Yes |
| Callback endpoint / poller loop excluded from P10.5 | §11 (line 1162) | Phase 10.5 不做 (line 1217) | 缺失清单 #9 (line 443) | Yes |

### 9. Retry/replay/steer

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| steer local semantics in P10.5 | §12 | Phase 10.5 范围 (line 1210) | G6 (line 244) | Yes |
| retry_run local semantics in P10.5 | §21 | Phase 10.5 范围 (line 1210) | G7 (line 253) | Yes |
| replay_run local semantics in P10.5 | §21 | Phase 10.5 范围 (line 1210) | G8 (line 261) | Yes |
| LOST/RECOVERING retry excluded from P10.5 | §27 | Phase 10.5 不做 (line 1213) | G7 (line 253) | Yes |

### 10. Multi-client

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| No client ownership / lock / attach token | §9 (line 485) | Phase 10.5 (line 1228) | G3 (line 212-214) | Yes |
| Concurrent submit_followup with client_request_id idempotency | §9 (line 485) | Phase 10.5 (line 1228) | G3 (line 214) | Yes |

### 11. Outbox and Recovery exclusions

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| Outbox concrete read/drain excluded, assigned to P13 | §16 | Phase 10.5 不做 (line 1219) | G2 (line 201-203) | Yes |
| Recovery excluded, assigned to P11 | §27 | Phase 10.5 不做 (line 1213) | G10 (line 278) | Yes |
| P11 must not break P10.5 frozen contract | - | Phase 11 前置条件 (line 1287) | - | Yes |

### 12. Smoke coverage

| Aspect | design.md | implementation-control.md | post-p10.md | Consistent? |
|--------|-----------|--------------------------|-------------|-------------|
| Mock runner smoke removed | - | Phase 10.5 进入条件 (line 1206) | 测试替身约束 (line 61) | Yes |
| Real runner matrix: mimo, ds/deepseek, gemini, qwen | - | Phase 10.5 进入条件 (line 1206) | S3 (line 116) | Yes |
| Provider unavailable = explicit skip | - | Phase 10.5 进入条件 (line 1206) | S3 (line 120) | Yes |
| No wait_final_answer or payload reader in smoke | - | Phase 10.5 不做 (line 1221) | 测试替身约束 (line 68) | Yes |
| Final answer from terminal HostEvent | §11 (line 1148) | Phase 10.5 (line 1235) | S1 (line 97) | Yes |

---

## Prior Challenge Review Resolution Status

### MiMo challenge (post-p10-public-contract-challenge-mimo-20260518.md)

| Finding | Status | Resolution |
|---------|--------|------------|
| B1: Missing final answer content read facade | **Resolved** | design.md §11 (line 1148-1149): terminal HostEvent is sole public path; no payload reader. implementation-control.md Phase 10.5 不做 (line 1221). |
| B2: Missing Host local runtime / composition root | **Resolved** | design.md §11 (lines 851-853): `open_host(options)` async context manager. implementation-control.md Phase 10.5 (line 1178). post-p10.md 缺失清单 #1 (line 343-353). |
| B3: Command facade → scheduler wakeup no public wiring | **Resolved** | design.md §11 (line 867): wakeup ownership frozen. implementation-control.md Phase 10.5 (line 1226). post-p10.md 缺失清单 #2 (line 356-362). |
| B4: Missing Run terminal wait public API | **Resolved** | design.md §11 (line 1148): no `wait_final_answer`; final answer from terminal HostEvent. implementation-control.md Phase 10.5 (line 1221). post-p10.md Public API 变更护栏 (line 46). |

### DS challenge (post-p10-wiring-smoke-challenge-ds-20260518.md)

| Finding | Status | Resolution |
|---------|--------|------------|
| B1: Missing stable Host runtime / composition root | **Resolved** | Same as MiMo B2. |
| B2: Public command facade → scheduler wakeup no wiring | **Resolved** | Same as MiMo B3. |
| B3: Missing public final answer read path | **Resolved** | Same as MiMo B1. |
| B4: S1/S2/S3/S4 mock smoke tests don't exist | **Resolved** | design.md / implementation-control.md / post-p10.md all specify S1-S5 as P10.5 exit requirement, not current code state. |
| B5: Existing tests bypass public API | **Resolved** | post-p10.md (line 68): mock runner removed from success signal. implementation-control.md Phase 10.5 verification (line 1265): no internal table queries. |

### Codex challenge (post-p10-codex-challenge-20260518.md)

| Finding | Status | Resolution |
|---------|--------|------------|
| B1: P10.5 still at discussion brief, not implementation-ready | **Resolved** | All public contract decisions listed in Codex B1 open questions have been written back: runtime name/shape/lifecycle (design.md §11), terminal wait/answer (design.md §11 line 1148), follow-up execution target (design.md §11 line 863, implementation-control.md Phase 10.5 line 1230). |
| B2: Follow-up execution target / scene-policy continuity | **Resolved** | design.md §11 (lines 861-863): per-run typed override in SubmitFollowupRequest; omitted = open_host default. implementation-control.md Phase 10.5 (line 1230). post-p10.md 缺失清单 #7 (line 411). Controller accepted implementation requirement (post-p10.md line 541). |

---

## Blocking Findings

**None.** All prior blocking findings from MiMo, DS, and Codex challenge reviews have been accepted by the controller and resolved into the design/control documents. The three documents are consistent on all P10.5 public contract decisions.

---

## Residual Risks

1. **`open_host(options)` concrete dataclass shape**: The implementation agent must design the concrete Python type. Risk is low since the parameter boundary is fully documented. Owner: P10.5 Slice 1.

2. **`HostClosedError` type hierarchy**: Implementation agent must choose between standalone exception or HostApiError subclass. Risk is low since semantic requirements are clear. Owner: P10.5 Slice 1.

3. **Smoke coverage checklist template**: The S1-S5 matrix (post-p10.md) and the smoke list (implementation-control.md) use different naming. P10.5 plan must reconcile them into a single checklist. Owner: P10.5 plan.

4. **Real runner smoke environment dependency**: S3 depends on API keys and network availability for mimo, ds/deepseek, gemini, qwen. Provider unavailability results in explicit skip, not failure. Risk: if all providers are unavailable, S3 contributes no coverage. Owner: P10.5 Slice 6.

5. **Compactor adapter availability**: S4 compact smoke requires a real compactor adapter. If no LLM-backed compactor is available, compact smoke cannot demonstrate real compaction. Owner: P10.5 Slice 5/6.

6. **Recovery boundary**: P10.5 explicitly excludes Recovery. If P10.5 implementation accidentally creates code paths that assume crash-free execution (e.g., no handling for stale dispatch records from prior runs), P11 may need to modify P10.5-frozen interfaces. Mitigation: P10.5 plan should note which internal components have recovery-aware vs. crash-free assumptions. Owner: P10.5 plan + P11.

---

## Owner Phases for Residual Items

| Item | Owner Phase | Dependency |
|------|-------------|------------|
| Recovery / startup crash recovery | P11 | Must not break P10.5 frozen contract |
| ToolsDiscovery / ScenePrepare | P12 | Extends tooling, doesn't change P10.5 wiring |
| Audit / Tool Trace / Outbox | P13 | Consumes EventLog, independent of P10.5 public API |
| RemoteProxy | P14 | Extends execution, doesn't change local contract |
| Retention / Purge | P15 | Extends cleanup, doesn't change P10.5 lifecycle |

---

## Final Verdict

**P10.5 can proceed to implementation-ready planning.** The design truth (design.md), control truth (implementation-control.md), and discussion artifact (post-p10.md) are consistent on all P10.5 public contract decisions. All blocking findings from three independent challenge reviewers have been accepted and resolved. The four open questions identified by Codex (runtime shape, terminal wait/answer, follow-up execution target, S3 skip rules) are now answered in the docs. Implementation agent should generate a handoff plan referencing these frozen decisions, not re-deriving them.

**Blocking count**: 0
**Non-blocking count**: 2 (F1, F2)
**Clarification count**: 2 (F3, F4)
