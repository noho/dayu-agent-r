# WU-SEMANTIC-OWNERSHIP-01 P3-A plan review controller adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A - Host lifecycle, run status, and terminal event source of truth`
- Gate: plan review controller adjudication
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md`
- Plan review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-a-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-a-plan-review-ds.md`

## Verdict

Plan review does not pass yet. Both reviewers accepted the P3-A motivation, source finding裁决, owner boundary, and 3-slice structure, but both found blocking issues that must be fixed before implementation.

Next gate is P3-A plan fix by AgentCodex. The fix must update the plan artifact and write a fix report.

## Accepted Review Findings

### PF-01 [blocking] S3 Host lifecycle closeout identity scheme is under-specified

Sources:

- AgentDS B-1

Controller disposition: accepted.

Required plan fix:

- Add a concrete Host lifecycle event id namespace and derivation formula for worker EOF/crash closeout.
- Explain how the Host lifecycle id namespace is disjoint from current Engine-origin event ids.
- Explain how duplicate terminal detection handles Engine-origin candidate and Host-lifecycle candidate without event id collision.
- Define the routing information used by late rejection / closeout logic when the candidate is not an `EngineEventCandidate`.

### PF-02 [blocking] S3 CANCELLING interaction is not specified

Sources:

- AgentDS H-2

Controller disposition: accepted.

Required plan fix:

- Add a decision table for active-cancel races:
  - Engine-origin `FINAL_ANSWER` while Run is `CANCELLING`
  - Engine-origin `RUN_FAILED` while Run is `CANCELLING`
  - Host lifecycle worker clean EOF while Run is `CANCELLING`
  - Host lifecycle worker lost/crash while Run is `CANCELLING`
  - other Engine events while Run is `CANCELLING`
- The table must state whether the event is rejected, accepted, or converted to a diagnostic, and which owner records the fact.

### PF-03 [blocking] S3 candidate shape risks becoming a god bag

Sources:

- AgentDS H-3

Controller disposition: accepted.

Required plan fix:

- Replace the open-ended `_TerminalCloseoutCandidate` sketch with either:
  - two separate typed paths: existing `EngineEventCandidate` plus a new `HostLifecycleCloseoutCandidate`; or
  - a clearly tagged union with a discriminator and typed payloads.
- The plan must forbid optional-field probing as the semantic discriminator.

### PF-04 [blocking] S2 terminal event source scan must be mandatory and precise

Sources:

- AgentDS B-2
- AgentMiMo F-04

Controller disposition: accepted.

Required plan fix:

- Promote terminal event source scan to mandatory S2 validation.
- Use a precise pattern for terminal event constants only.
- Define exact allowed locations after implementation.
- Separately list non-terminal event constants that remain out of P3-A scope and record them as residual input for P3-J / future EventLog schema hardening.

### PF-05 [blocking] Import-cycle prevention must be concrete

Sources:

- AgentMiMo F-01
- AgentDS L-3

Controller disposition: accepted with severity correction.

Controller note:

- AgentDS verified the current import graph likely does not cycle because `dayu.host.api` does not import `dayu.host.durable`. This reduces the risk, but the plan still needs to record the dependency graph and verification command because S1/S2 propose new lifecycle imports.

Required plan fix:

- Add an import graph note for `lifecycle_events.py`, `api.py`, `durable.state`, `run_transition.py`, and `engine_ingest.py`.
- Add a concrete validation command that imports lifecycle helpers and affected modules after S1/S2.
- State that if helper placement introduces an import cycle, implementation must stop and return to design/plan fix.

### PF-06 [high] SM-7 needs a pre-implementation verification step

Sources:

- AgentDS H-1

Controller disposition: accepted.

Required plan fix:

- Add a pre-S1 verification step to search production call paths that construct `FollowupSnapshot` with `accepted_run_status=RunStatus.RECOVERING` or equivalent.
- If found, plan must either move SM-7 into P3-A scope or record a concrete deferred owner.
- If not found, record the search result as the needs-more-evidence closure basis.

### PF-07 [medium] SQL status helper needs query plan / index validation

Sources:

- AgentMiMo F-02

Controller disposition: accepted.

Required plan fix:

- Add S1/S2 validation for generated SQL `IN` clauses. This may be `EXPLAIN QUERY PLAN`, targeted durable state tests that assert equivalent query behavior, or both.
- The fix should not require preserving hand-written status lists to satisfy planner behavior.

### PF-08 [medium] `_TERMINAL_STATUS_PAIRS` owner decision is incomplete

Sources:

- AgentDS M-2

Controller disposition: accepted.

Required plan fix:

- Decide whether terminal status pairs are a derived transition invariant or a separate durable row-rule truth.
- If derived, specify derivation from Run / Attempt terminal status owners.
- If separate, move/name it as an explicit transition closeout invariant and document why it is not duplicate event mapping truth.

### PF-09 [medium] `START_BLOCKING_RUN_STATUSES` derivation assumption must be explicit

Sources:

- AgentDS M-3

Controller disposition: accepted.

Required plan fix:

- Explain the current assumption that all non-terminal statuses except `QUEUED` block starting another Run.
- Add a test expectation that makes new non-terminal statuses force an explicit review of this set.

### PF-10 [medium] Propagation audit needs executable verification criteria

Sources:

- AgentDS M-4

Controller disposition: accepted.

Required plan fix:

- For each propagation audit path, add concrete verification: source scan, owner-level test, transition test, read/projection test, or diagnostic assertion.

### PF-11 [medium] P3-B interface boundary must be preserved, not predesigned

Sources:

- AgentMiMo F-03

Controller disposition: accepted with correction.

Controller correction:

- P3-A must not predesign P3-B final-answer fields. Requiring P3-A to add `final_answer_text` to an internal closeout candidate would leak P3-B scope into P3-A.

Required plan fix:

- State that any S3 closeout extraction must preserve existing final-answer / terminal descriptor arguments and behavior without redesigning them.
- State that P3-B may later consume the same closeout path, but P3-A will not add final-answer-specific fields unless already required by existing `_close_terminal` arguments.

### PF-12 [low] README decision must require actual check

Sources:

- AgentDS L-1

Controller disposition: accepted.

Required plan fix:

- Replace "预计不更新" with an implementation requirement to inspect `dayu/host/README.md` and `tests/README.md` per AGENTS.md trigger rules and record the decision.

### PF-13 [low] Event type value helper strategy should be concrete

Sources:

- AgentDS L-2

Controller disposition: accepted.

Required plan fix:

- Choose simple separate helpers for Run and Attempt event type value projection unless implementation finds a stronger typed reason to generalize.
- Do not leave this as a TypeVar/overload design choice for implementation.

## Rejected Or No-Fix Review Items

None. All review findings above require either plan text changes or explicit scope correction in the plan.

## Next Gate

P3-A plan fix by AgentCodex.

Allowed files for plan fix:

- `docs/host/wu-semantic-ownership-01-p3-a-host-lifecycle-event-source-plan.md`
- `docs/reviews/wu-semantic-ownership-01-p3-a-plan-fix-codex.md`

Stop condition:

- Do not implement code.
- If any accepted plan review finding requires design truth changes before plan can be fixed, report blocked.
