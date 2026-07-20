# Plan Re-Review: WU-SEMANTIC-OWNERSHIP-01 P3-H

## Review metadata

- **Reviewer**: AgentMiMo
- **Reviewed artifact**: `docs/host/wu-semantic-ownership-01-p3-h-llm-ui-copy-boundary-plan.md`
- **Work unit**: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- **Gate**: plan re-review (verify fixes, identify new blockers)
- **Date**: 2026-07-11
- **Prior review**: `docs/reviews/plan-review-20260711-061858.md`
- **DS review**: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-review-ds.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-review-controller-adjudication.md`
- **Fix report**: `docs/reviews/wu-semantic-ownership-01-p3-h-plan-fix-codex.md`

## Scope

Re-review only. Verify accepted fixes P3-H-PF-01 through P3-H-PF-06 are actually closed. Identify only new material plan blockers introduced by the fix. Do not edit production code, tests, or plan.

---

## PF verification

### P3-H-PF-01 — Clarify Fins direct-stream versus job-event sidecar scope

- **Sources**: AgentMiMo F1, F6; AgentDS Finding 2
- **Required**: update S2 with a concrete scope table for direct stream, wait adapter, and job sidecar text
- **Status**: **closed**
- **Evidence**: Fixed plan S2 lines 214-223 now contains an explicit scope table with six propagation paths:
  - Direct progress stream → in scope
  - Direct result stream → in scope
  - Wait resolution → in scope
  - Direct tool result derived from direct event → in scope (if direct evidence appears)
  - Job event sidecar → **explicitly out** for P3-H unless projected into `FinsEvent`, wait outcome, tool result, memory, or trace
  - Log-only/internal diagnostics → out
- Job sidecar text is no longer ambiguous. The table names the producer call (`_append_job_event_warn`), destination (durable job event/audit sidecar), and the explicit out-of-scope decision with rationale. Stop condition (lines 248-249) further instructs implementation to classify exact paths if projection is discovered.
- Original F1 and F6 concerns are fully addressed.

### P3-H-PF-02 — Expand and downgrade source scans to evidence checks

- **Sources**: AgentMiMo F2, F3; AgentDS Finding 5
- **Required**: expand Web and Fins scans to cover all known P3-H source literals/builders; state scans complement tests/helper coverage/propagation audit
- **Status**: **closed**
- **Evidence**:
  - Fins scan (line 298) expanded from 11 patterns to 35+ patterns, now covering: `_DIRECT_CANCELLED_MESSAGE`, `_DIRECT_FAILURE_TITLE`, `_DIRECT_SUCCESS_TITLE`, `_DIRECT_ERROR_TEXT_FALLBACK`, all direct progress stages (`下载准备中`, `下载已开始`, `下载已完成`, `预处理准备中`, `预处理已选择源文档`, etc.), all direct result titles (`操作已取消`, `操作完成`, `操作失败`, `执行失败`, `下载失败`, `预处理失败`, `上传失败`), and failure detail messages (`下载请求未写入任何源文档`, `没有任何请求文档完成预处理`, `上传运行时返回失败状态`).
  - Web scan (line 294) expanded to include `_build_search_web_preferred_summary`, `未找到可直接抓取正文`, `首选结果`, `标题：`, `日期：`, `摘要：`.
  - Job sidecar scan (line 299) explicitly lists retained sidecar patterns (`_append_job_event_warn`, `已记录取消请求`, `job 已进入队列`, etc.) with expected-scan-results note (line 310) that these are expected remaining hits.
  - Success signals (line 22) now state: "Source scans are evidence checks only; they complement tests, helper coverage, and the propagation audit, and are not treated as exhaustive proof."
  - Scan limitation section (lines 313-316) further clarifies scans are not exhaustive.
- Original F2 (23+ missing Fins patterns) and F3 (missing `_build_search_web_preferred_summary`) concerns are fully addressed.

### P3-H-PF-03 — Specify Web `SearchWebOutput` migration and imports

- **Sources**: AgentDS Finding 3
- **Required**: name provider-owned fact type, projection-owned output type, builder signature, import direction
- **Status**: **closed**
- **Evidence**: Fixed plan S1 specifies:
  - Provider-owned type: `SearchWebProviderResult` (line 116)
  - Projection-owned type: `SearchWebOutput` moves to `web_search_projection.py` (line 121)
  - Builder signature: `def build_search_web_output(provider_result: SearchWebProviderResult) -> SearchWebOutput` (lines 124-127)
  - Import direction: `web_tools.py` imports `SearchWebProviderResult` from `web_search_providers.py`, imports `SearchWebOutput` and `build_search_web_output` from `web_search_projection.py` (lines 137-138)
  - Contract section (lines 94-95) reiterates: "Provider-internal search output type becomes `SearchWebProviderResult` ... Update imports and tests directly; do not add compatibility re-exports or wrapper aliases."
- All four required specifications are present. Implementation agent has no ambiguous decisions.

### P3-H-PF-04 — Narrow Web display-name handling to the actual tool declaration owner

- **Sources**: AgentMiMo F4; AgentDS Open Question 3
- **Required**: revise S1 and BI-6 so display names/descriptions may remain in `@tool(...)` declaration site
- **Status**: **closed**
- **Evidence**:
  - S1 exact allowed changes (line 134): "Do not move `search_web` / `fetch_web_page` `display_name` or `description` out of the `@tool(...)` declaration unless implementation finds direct duplicate ownership outside the declaration site."
  - BI-6 disposition (line 45) changed to "accepted with narrowed owner" and specifies: "Keep `display_name` / `description` at the `@tool(...)` declaration site unless implementation finds duplicate display-name ownership."
  - `web_tool_projection_text.py` scope (line 133) narrowed to cancellation/recovery/search guidance constants only.
  - Expected scan results (line 308): "`display_name=\"联网搜索\"` and `display_name=\"抓取网页\"` may remain in `@tool(...)` declarations because that is the declaration owner."
- Original F4 concern (unnecessary indirection for display names) is fully addressed.

### P3-H-PF-05 — Choose the `web_cancellation_text.py` path

- **Sources**: AgentMiMo F5; AgentDS Open Question 1
- **Required**: choose one path; preferred: replace with new helper, update imports, no compatibility re-export
- **Status**: **closed**
- **Evidence**:
  - S1 exact allowed changes (line 135): "Delete `web_cancellation_text.py` after moving `WEB_CANCELLED_HINT` into this helper. Update imports directly in production and tests; do not keep a compatibility re-export."
  - Affected files (line 66): "`dayu/tools/web/web_cancellation_text.py` for deletion only; do not keep compatibility re-export"
  - Web cancellation scan (line 296): "`rg -n \"web_cancellation_text|WEB_CANCELLED_HINT\" dayu/tools/web tests/tools/web`"
  - Expected scan results (line 307): "no `web_cancellation_text.py` module/import remains"
- The plan unambiguously chooses the replacement-and-delete path. No implementation agent decision needed.

### P3-H-PF-06 — Specify Fins direct text helper API boundary

- **Sources**: AgentMiMo F7; AgentDS Finding 2 / residual risk
- **Required**: specify `direct_event_text.py` provides typed text constants and small lookup functions only; must not import/construct `FinsEvent`, `FinsResultSummary`, or `FinsProgress`
- **Status**: **closed**
- **Evidence**:
  - S2 exact allowed changes (lines 176-178): "It must not import, construct, wrap, or validate `FinsEvent`, `FinsResultSummary`, or `FinsProgress`; `direct_events.py` remains the contract-shape and validation owner."
  - Required API shape (lines 181-207) specifies six typed functions:
    - `direct_result_title(*, operation_kind: FinsOperationKind, status: FinsResultStatus) -> str`
    - `direct_failure_message(*, error_kind: FinsErrorKind | None, fallback_message: str | None) -> str`
    - `direct_progress_message(*, stage: str) -> str`
    - `wait_failed_hint() -> str`
    - `wait_cancelled_message() -> str`
    - `wait_cancelled_hint() -> str`
  - Design alignment (line 55): "`direct_event_text.py` must own only reusable text content and text-selection helpers; it does not replace the `FinsEvent`, `FinsResultSummary`, or `FinsProgress` contracts."
- Helper API boundary is fully specified. Import restrictions are explicit. Implementation agent has clear contract.

---

## New findings check

After verifying all six PFs are closed, I checked for new material plan blockers introduced by the fixes.

### Scan: no new material blockers found

The fixes addressed the original review's concerns without introducing new architectural risks:

1. **Scope table addition** (PF-01): Adds clarity without changing architecture. The out-of-scope decision for job sidecar text is well-reasoned and explicitly documented with retention rationale.

2. **Scan pattern expansion** (PF-02): Adds coverage without false claims. The "evidence checks, not exhaustive proof" framing and scan-limitation section prevent over-reliance on scans.

3. **Type migration specification** (PF-03): Names concrete types and import paths. No ambiguity remains for implementation agent.

4. **Display-name narrowing** (PF-04): Reduces helper scope, which simplifies implementation. The `@tool(...)` declaration remains the natural owner.

5. **Deletion path choice** (PF-05): Eliminates the two-option ambiguity. One clear path forward.

6. **Helper API specification** (PF-06): Provides typed function signatures. The import restriction (`FinsEvent`/`FinsResultSummary`/`FinsProgress` prohibited) correctly prevents the helper from becoming a second contract layer.

### Minor observations (not findings, not blockers)

- **Dynamic message templates**: Some Fins direct progress messages use f-strings with embedded counts/filenames (e.g., `"下载已完成，存在失败候选"` with count). The helper's `direct_progress_message(*, stage: str) -> str` signature handles this via stage-based lookup, but implementation must decide whether to embed template parameters in the function or return format strings. This is an implementation detail, not a plan blocker.

- **Scan pattern maintenance**: The expanded scan patterns are comprehensive for current code, but the plan already addresses this in the scan-limitation section: "If implementation adds or rewrites LLM-facing/user-visible text, it must update tests and ... add a matching scan pattern."

Neither observation rises to the level of a material finding.

---

## Open questions

None. All open questions from the prior review and DS review have been addressed by the plan fixes:
- Fins direct-stream vs job-event scope → PF-01 scope table
- `web_cancellation_text.py` deletion path → PF-05 explicit choice
- `direct_event_text.py` API shape → PF-06 typed function signatures
- `SearchWebOutput` migration path → PF-03 concrete type names and imports
- Display-name ownership → PF-04 narrowed to `@tool(...)` declaration
- Scan brittleness → PF-02 "evidence checks" framing

## Residual risks

All residual risks from the prior review remain at the same severity level and are adequately mitigated by the fixed plan:

| Risk | Severity | Mitigation in fixed plan |
|------|----------|--------------------------|
| Fins direct text scope: some strings may serve both job sidecar and direct stream | Low | Scope table + stop condition classify by propagation path |
| Coverage risk: new helper modules need focused tests | Low | Plan specifies "new production helper file must reach at least 80% coverage" (line 238) |
| Web output contract: test import migration | Low | Plan specifies direct import migration, no compatibility aliases (lines 94-95) |
| Source scan incompleteness | Low | Scan limitation section (lines 313-316) + propagation audit requirement |

No new residual risks introduced by the fixes.

---

## Final plan review conclusion

**pass**

All six accepted plan fixes (P3-H-PF-01 through P3-H-PF-06) are verified closed:

| PF | Status | Key evidence |
|----|--------|-------------|
| P3-H-PF-01 | closed | S2 scope table with 6 propagation paths; job sidecar explicitly out |
| P3-H-PF-02 | closed | Fins scan expanded to 35+ patterns; "evidence checks" framing |
| P3-H-PF-03 | closed | `SearchWebProviderResult` / `SearchWebOutput` / `build_search_web_output` named |
| P3-H-PF-04 | closed | display_name stays at `@tool(...)` declaration |
| P3-H-PF-05 | closed | delete `web_cancellation_text.py`, no compatibility re-export |
| P3-H-PF-06 | closed | 6 typed functions, `FinsEvent`/`FinsResultSummary`/`FinsProgress` import prohibited |

New material plan blockers introduced by the fixes: **0**

The plan is now code-generation-ready. Implementation agent can proceed to S1.
