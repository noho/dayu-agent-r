# P9.5 S18 Aggregate Validation And Readiness Evidence

## Scope

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening
- Slice: S18 Aggregate Validation And Readiness Evidence
- Branch: `p9.5-pre-p10-hardening`
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Plan: `docs/host/p9-5-pre-p10-hardening-plan.md`

## Aggregate Validation

The required S18 validation commands passed:

- `source .venv/bin/activate && pytest -q`
  - Result: 1066 passed in 9.46s.
- `source .venv/bin/activate && python -m pyright dayu tests`
  - Result: 0 errors / 0 warnings / 0 informations.
- `git diff --check`
  - Result: clean.

## Tracking Item Disposition

All P9.5 tracking items in `docs/host/implementation-control.md` have an owner and disposition:

| Tracking item | Disposition |
| --- | --- |
| Engine runner protocol decoupling | Fixed in S1; implementation and review artifacts recorded. |
| minimal read model single-consumer reset contract | Fixed in S6; multi-consumer schema remains non-goal. |
| durable / public API error taxonomy | Fixed in S3; no public API rewrite. |
| Command handle internal service encapsulation / lifecycle guard | Fixed in S3; public export / facade tests guard the boundary. |
| LocalProxy close / events race | Fixed in S7 with re-review. |
| read API enum mapping | Fixed in S6. |
| ToolRuntime / memory module boundary cleanup | Fixed in S11 and S14; no semantic move to runtime or Engine. |
| ToolRuntime truncation / duplicate defensive validation and focused test hardening | Fixed in S12. |
| TruncationManager initialization cost review | Adjudicated in S12 as no production fix needed; no singleton / durable cursor / cross-run reuse added. |
| Engine wait confirmation matching-ref contract hardening | Fixed in S8. |
| runtime lane hardening | Fixed in S9. |
| Host dispatch lifecycle / RunInputBuilder non-recovery cleanup and targeted tests | Fixed in S10. |
| late `resolve_wait` rejection redundant catch-up cleanup / tests | Fixed in S10 / S14 ownership area; late rejection remains diagnostic-only. |
| message / tool result size governance | Fixed in S13. |
| Host durable helper API tightening | Fixed in S4. |
| schema CHECK hardening | Fixed in S5. |
| Engine / OpenAI runner / parser hardening | Fixed in S2. |
| Engine / Host P1-P9 implemented-path necessary log under level semantics | Fixed in S15; Engine side audited and left unchanged where already sufficient. |
| Contract Ownership conformance audit | Fixed in S16 with automated import-boundary / export / `fetch_more` guards. |
| P9 memory cleanup not involving snapshot history | Fixed in S14. |
| P9 memory import boundary / preview exclusion / catch-up end-to-end / optional JSON helper wording / empty snapshot cleanup | Fixed in S14 and S17 documentation. |
| production memory projection catch-up composition wiring not involving snapshot history | Partially fixed by explicit concrete catch-up paths and cursor-bound dispatch catch-up in S14; generic default catch-up was rejected because it requires snapshot history. The rejected part is owned by future Context Governance / memory design, not P9.5. |
| God module / class cleanup and broader hardening without P10+ owner | Closed by concrete S1-S17 slices; no unowned broader hardening remains in P9.5. |

## Deferred Or Not-Fixed Items With Owners

The following are explicitly not fixed by P9.5 and remain owned by later phases or prior controller decisions:

- Conversation Memory snapshot history retention: not fixed; requires future Context Governance / memory design. S14 found direct evidence that generic post-commit catch-up without snapshot history can advance a latest-only snapshot past the current dispatch cursor.
- P10 Context Governance / compaction provider: not implemented by P9.5; remains Phase 10.
- RECOVERING recovery scan / positive orphan proof / active cancel watchdog: not implemented by P9.5; remains Phase 11.
- ToolsDiscovery / ScenePrepare manifest provider: not implemented by P9.5; remains Phase 12.
- Audit / Tool Trace / Outbox sinks: not implemented by P9.5; remains Phase 13.
- RemoteProxy / RemoteStub: not implemented by P9.5; remains Phase 14.
- purge / retention production hardening: not implemented by P9.5; remains Phase 15.

## Artifact Coverage

Every P9.5 implementation slice S1-S17 has implementation evidence and review evidence under `docs/reviews/`. Slices with accepted findings include fix / re-review artifacts. Control-document history entries record accepted slice commits through S17.

## Readiness Decision

S18 aggregate validation passes. P9.5 can proceed to aggregate deepreview under gateflow. The worktree should remain limited to this S18 readiness artifact and the subsequent control-document tracking update before the S18 accepted commit.

## Residual Risk

- Full validation proves the current repository state, but draft PR gate still requires aggregate deepreview and PR checks after push.
- Any future attempt to wire generic memory catch-up by default must first solve snapshot history / cursor coverage semantics; it must not be treated as a small P9.5 cleanup.
