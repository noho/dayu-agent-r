# WU-SEMANTIC-OWNERSHIP-01 P3-H Plan Re-Review — AgentDS

## Review metadata

- **Reviewer**: AgentDS (re-review)
- **Reviewed artifact**: `docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md` (fixed)
- **Date**: 2026-07-11 06:28:44 CST
- **Gate**: plan re-review (post plan-fix)
- **Prior DS review**: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-review-ds.md`
- **AgentMiMo review**: `docs/reviews/plan-review-20260711-061858.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-review-controller-adjudication.md`
- **Fix report**: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-fix-codex.md`

## Scope

This is a plan re-review only. Scope is strictly limited to:

1. Verify that accepted plan fixes P3-H-PF-01 through P3-H-PF-06 are actually closed in the fixed plan.
2. Identify only new material plan blockers introduced by the fix.
3. Do not edit production code, tests, or plan.

Prior review findings (AgentDS Findings 1-7, AgentMiMo F1-F7) are not re-litigated; only fix closure is verified.

## PF-01 — Fins direct-stream versus job-event sidecar scope table

**Controller requirement**: "update S2 with a concrete scope table for direct stream, wait adapter, and job sidecar text. If job sidecar text remains out of scope, record why it is not a current P3-H blocker and how scans avoid pretending it was moved."

**Fixed plan evidence**:

- Lines 216-223: propagation path table with six rows covering Direct progress stream, Direct result stream, Wait resolution, Direct tool result derived from direct event, Job event sidecar, and Log-only/internal diagnostics.
- Each row specifies: Producer call/site, Destination, P3-H scope, and Owner decision.
- Job event sidecar row (line 222): explicitly marked "out for P3-H" with reason "Leave in runtime/job lifecycle owner for this WU. This is not a current P3-H blocker because P3-H targets direct/wait projection; scans must list these as retained sidecar text rather than claiming all runtime UI text moved."
- Line 299: separate `_append_job_event_warn` scan explicitly lists retained job sidecar strings and expects them to remain in `ingestion_runtime.py`.
- Line 249: S2 stop condition updated to require updating the scope table if implementation finds a job sidecar message projected into `FinsEvent`, wait outcome, tool result, memory, or trace.

**Verdict**: ✅ CLOSED. The scope table is concrete, complete, and self-documenting. Job sidecar text is explicitly out of scope with clear owner and reason. The separate job sidecar scan prevents false claims of cleanup.

## PF-02 — Expanded source scans downgraded to evidence checks

**Controller requirement**: "expand Web and Fins scans to cover all known P3-H source literals/builders, including `_build_search_web_preferred_summary` and its Chinese summary fragments. State that scans complement tests, helper coverage, and propagation audit rather than replacing them."

**Fixed plan evidence**:

- Line 294: Web provider scan now includes `_build_search_web_preferred_summary|_build_search_web_hint|_build_search_web_next_action|_build_search_web_next_action_args|当前没有可直接抓取|优先抓取首选结果正文|未找到可直接抓取正文|首选结果|标题：|日期：|摘要：` — covering all three builder functions and their Chinese prose fragments identified in AgentMiMo F3.
- Line 298: Fins direct/wait scan now includes ~40 Chinese string patterns covering all direct-stream titles, progress messages, failure messages, wait hints, and cancellation messages identified in AgentMiMo F2.
- Line 299: separate job sidecar scan for retained strings.
- Lines 313-315: explicit scan limitation statement: "These scans cover known source findings and likely regression strings. They are not exhaustive proof that no new prose was introduced in a wrong owner. If implementation adds or rewrites LLM-facing/user-visible text, it must update tests and, where the new text is in a provider/runtime/adapter file, add a matching scan pattern or explain why that file is the owner."
- Line 352: risks section updated: "Source scan risk: scans are intentionally narrow evidence checks. They must not be used as the only proof of correctness; tests, helper coverage, and propagation audit remain required."

**Verdict**: ✅ CLOSED. Scans cover all known source literals. They are explicitly downgraded to evidence checks with a clear statement that tests, coverage, and propagation audit are the real safety net.

## PF-03 — Web `SearchWebOutput` type migration specified

**Controller requirement**: "name the provider-owned fact type, name the projection-owned LLM-facing output type, specify the builder function signature, and specify import direction for `web_tools.py` and tests."

**Fixed plan evidence**:

- Line 116: provider-owned type named `SearchWebProviderResult`, with fields `query`, `domains`, `total`, `preferred_result`, and `results`.
- Line 121: projection-owned LLM-facing type keeps the name `SearchWebOutput`, moved to `web_search_projection.py`.
- Lines 124-126: builder signature explicitly specified: `def build_search_web_output(provider_result: SearchWebProviderResult) -> SearchWebOutput: ...`
- Lines 137-138: `web_tools.py` import direction: `SearchWebProviderResult` from `web_search_providers.py`; `SearchWebOutput` and `build_search_web_output` from `web_search_projection.py`.
- Line 143: test fixtures use `web_search_providers.SearchWebProviderResult`; tool outcome tests import `SearchWebOutput` from `web_search_projection.py`.
- Lines 94-95: contract section confirms type name and migration path.

**Verdict**: ✅ CLOSED. Type names, builder signature, and import direction are all explicitly specified. No ambiguity for the implementation agent.

## PF-04 — Web display-name handling narrowed to declaration owner

**Controller requirement**: "revise S1 and BI-6 disposition so display names/descriptions may remain in the `@tool` declaration site. The helper should own cancellation/recovery text and search-result guidance only."

**Fixed plan evidence**:

- Line 45: BI-6 disposition changed to "accepted with narrowed owner" with planned handling: "Keep `display_name` / `description` at the `@tool(...)` declaration site unless implementation finds duplicate display-name ownership. Replace split cancellation/recovery literals with `web_tool_projection_text.py`."
- Line 134: S1 helper section: "Do not move `search_web` / `fetch_web_page` `display_name` or `description` out of the `@tool(...)` declaration unless implementation finds direct duplicate ownership outside the declaration site."
- Line 140: S1 `web_tools.py` section: "Keep `display_name` and `description` in the `@tool(...)` declaration site."
- Line 308: expected scan results: "`display_name="联网搜索"` and `display_name="抓取网页"` may remain in `@tool(...)` declarations because that is the declaration owner."

**Verdict**: ✅ CLOSED. Display names and descriptions stay at the `@tool(...)` declaration site. The helper is scoped to cancellation/recovery text only. No unnecessary indirection introduced.

## PF-05 — `web_cancellation_text.py` replacement path chosen

**Controller requirement**: "choose one path. Preferred: replace `web_cancellation_text.py` with the new Web projection text owner, update imports directly, and do not keep a compatibility re-export."

**Fixed plan evidence**:

- Line 66: allowed files list: "`dayu/tools/web/web_cancellation_text.py` for deletion only; do not keep compatibility re-export."
- Line 135: S1 helper section: "Delete `web_cancellation_text.py` after moving `WEB_CANCELLED_HINT` into this helper. Update imports directly in production and tests; do not keep a compatibility re-export."
- Line 307: expected scan results: "no `web_cancellation_text.py` module/import remains; `WEB_CANCELLED_HINT` hits are allowed only in `web_tool_projection_text.py`, `web_tools.py` imports/usages, and tests that intentionally assert the helper owner."

**Verdict**: ✅ CLOSED. The replacement path is explicitly chosen. Old file deletion, import migration, and no-compatibility-re-export rule are all stated.

## PF-06 — Fins direct text helper API boundary specified

**Controller requirement**: "specify that `direct_event_text.py` provides typed text constants and small lookup functions only; it must not import or construct `FinsEvent`, `FinsResultSummary`, or `FinsProgress`."

**Fixed plan evidence**:

- Lines 176-178: explicit constraints: "It must not import, construct, wrap, or validate `FinsEvent`, `FinsResultSummary`, or `FinsProgress`; `direct_events.py` remains the contract-shape and validation owner. It must not import `FinsIngestionRuntime`, wait adapter types, Host outcome types, storage types, or job store types."
- Lines 181-207: concrete API shape with six typed function signatures:
  - `direct_result_title(*, operation_kind: FinsOperationKind, status: FinsResultStatus) -> str`
  - `direct_failure_message(*, error_kind: FinsErrorKind | None, fallback_message: str | None) -> str`
  - `direct_progress_message(*, stage: str) -> str`
  - `wait_failed_hint() -> str`
  - `wait_cancelled_message() -> str`
  - `wait_cancelled_hint() -> str`
- Line 55: design alignment section: "`direct_event_text.py` must own only reusable text content and text-selection helpers; it does not replace the `FinsEvent`, `FinsResultSummary`, or `FinsProgress` contracts."

**Verdict**: ✅ CLOSED. Helper API is explicitly specified with typed signatures. Boundary constraints (no `FinsEvent`/`FinsResultSummary`/`FinsProgress` import or construction) are stated in three separate locations for redundancy.

## New issues scan

I performed an adversarial scan of the fixed plan for new material blockers introduced by the fixes. Scope: architecture boundary violations, over-coupling, underspecification that would force the implementation agent to redesign, test gaps, contract conflicts, and semantic ownership regressions.

### Observations (not blockers)

1. **`direct_progress_message` stage parameter is untyped (`str`)**: The API accepts any string for `stage`. The plan says (line 225): "Move direct progress stage constants only if that reduces duplication. If stage constants stay in `ingestion_runtime.py`, the helper must not duplicate their string values in a second source of truth without a source scan/test explaining the boundary." This means the helper does not own the set of valid stage identifiers — it is a pure text lookup. This is a deliberate design choice, not an oversight. The helper's role is text content ownership, not stage identifier validation. No blocker.

2. **Conditional scope row in propagation path table**: The row "Direct tool result derived from direct event" (line 221) is scoped "in if direct evidence appears." This creates a small discovery task during S2 implementation. The plan's stop condition (line 249) already covers this: "If implementation finds that a job sidecar message is projected into `FinsEvent`, a Host wait outcome, a tool result, memory, or trace, update the scope table and tests before moving it." This is a well-gated conditional, not a blocker.

3. **`direct_failure_message` dual-None edge case**: The API `direct_failure_message(*, error_kind: FinsErrorKind | None, fallback_message: str | None) -> str` does not specify behavior when both parameters are `None`. This is an implementation detail the implementation agent can resolve with a sensible default (e.g., return a generic failure message). Does not rise to the level of a plan blocker.

4. **Source scan patterns are now very long**: The Fins scan (line 298) contains ~40 Chinese string patterns. While comprehensive, long literal lists are brittle to even minor text changes. The plan already acknowledges this (lines 313-315) and states the real safety net is tests + coverage + propagation audit. Adequately mitigated.

### New blockers

**None found.** The six fixes are well-scoped, internally consistent, and do not introduce architecture violations, over-coupling, underspecification, test gaps, or contract conflicts.

## Residual risks

| Risk | Severity | Origin | Mitigation in plan |
|------|----------|--------|-------------------|
| `direct_progress_message` accepts untyped `stage: str`; invalid stage values could be passed at runtime | 低 | PF-06 API design | Helper is a text lookup, not a validator. Stage constants may remain in runtime (line 225). If moved to helper, they become typed. |
| "Direct tool result derived from direct event" scope is conditional on implementation discovery | 低 | PF-01 scope table | S2 stop condition (line 249) gates expansion on direct evidence. |
| Source scan patterns are long literal lists; minor text changes could produce false negatives | 低 | PF-02 scan expansion | Plan explicitly states scans are evidence checks, not exhaustive proof (lines 313-315). Tests + coverage + propagation audit are the real safety net. |
| Web output contract: downstream code may import `SearchWebOutput` from old location | 低 | Original plan risk | S1 explicit import migration path (lines 137-138, 143-144). Aggregate scan catches remaining references. |

## Conclusion

**Verdict: pass**

All six accepted plan fixes (P3-H-PF-01 through P3-H-PF-06) are verified closed in the fixed plan. Each fix is backed by direct plan-text evidence at specific line numbers. The fixes are internally consistent and do not introduce new architecture violations, over-coupling, underspecification, or test gaps.

The fixed plan is code-generation-ready. The three implementation slices are well-scoped with explicit allowed files, exact allowed changes, focused test commands, stop conditions, and propagation audit criteria. The implementation agent has sufficient specification to proceed without redesigning.

### Completion report

- **Verdict**: pass
- **PF-01** (Fins scope table): ✅ closed
- **PF-02** (expanded scans as evidence checks): ✅ closed
- **PF-03** (Web type migration specified): ✅ closed
- **PF-04** (display-name handling narrowed): ✅ closed
- **PF-05** (cancellation text replacement path): ✅ closed
- **PF-06** (Fins helper API boundary): ✅ closed
- **New findings**: 0
- **New blockers**: 0
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-rereview-ds.md`
