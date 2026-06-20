# Plan Re-Review: WU-ENG-02-R1 Provider Debugging Correlation Plan (AgentDS)

- **Review type**: Plan re-review gate
- **Review target**: `docs/host/host-issues/wu-eng-02-r1-provider-debugging-correlation-plan.md`
- **Work unit**: WU-ENG-02-R1
- **Gate**: re-review
- **Reviewer**: AgentDS
- **Date**: 2026-06-20
- **Design sources**: `docs/host/design.md`, `docs/engine/design.md`
- **Control doc**: `docs/host/issues-implementation-control.md`
- **Plan-fix artifact**: `docs/reviews/wu-eng-02-r1-plan-fix-codex-20260620.md`
- **Prior review artifacts**: `docs/reviews/plan-review-20260620-210618.md` (AgentDS), `docs/reviews/plan-review-20260620-210656.md` (AgentMiMo)

---

## Re-Review Scope

This re-review verifies whether the 6 accepted findings from the prior plan reviews have been properly closed in the current plan artifact. It does not re-litigate already settled design decisions. Each finding is checked against the current plan text and the plan-fix mapping.

---

## Accepted Finding Closure Verification

### Finding 1: Terminal diagnostic path converged to minimal Host public projection suffix path, no durable payload message/digest mutation

**Status**: ✅ **CLOSED**

**Prior state** (DS F1, MiMo F01): Plan offered two competing options (error_message suffix vs typed fields) without recommending one, leaving the design decision to the implementation agent. The implementation boundary for constructing the diagnostic suffix was underspecified—three possible locations (engine_ingest.py, read_api.py, entrypoint_runtime.py) had different consequences for durable truth, digest integrity, and projection consistency.

**Current plan evidence**:

- §6 "Required Public Projection Change For Terminal Diagnostic": Explicitly requires keeping `HostEvent`, `OutboxTerminalItem`, and `EntrypointRunTerminalResult` public dataclass shapes unchanged. Specifies suffix source as the already durable terminal payload fields `provider_request_id` and `client_correlation_id`. Explicitly prohibits appending the suffix during Engine ingest, EventLog append, payload-store write, or any path that mutates durable terminal payload `message`; payload digest must remain unchanged.
- §7 Decision 7: Specifies the preferred output shape: `<existing error message>\nclient_correlation_id=<id>`.
- §8 Slice 4 Steps 5-7: Identifies exact projection functions in `read_api.py` (live watcher) and `outbox.py` (outbox fallback) where the suffix is to be appended.

**Verification**: The plan now converges on a single, minimal path: suffix appended at Host public projection boundaries only, sourced from already-durable payload fields, with no durable mutation. This is specific enough for an implementation agent to execute without re-design.

---

### Finding 2: Live watcher and outbox fallback use same suffix formatting helper and both have tests

**Status**: ✅ **CLOSED**

**Prior state** (DS F4, MiMo F02): Plan did not acknowledge that live watcher and outbox fallback are independent projection paths in code (`read_api.py` vs `outbox.py`). Implementation agent could have implemented suffix in only one path, causing inconsistent behavior between live and offline reconnection views.

**Current plan evidence**:

- §6: "Both projection paths must call the same module-level private Host projection helper for suffix formatting, so `provider_request_id=None` plus the same `client_correlation_id` renders identically in live and outbox fallback views."
- §8 Slice 4 Step 1: "Add a module-level private helper in the Host projection layer that formats the bounded suffix from `provider_request_id: str | None` and `client_correlation_id: str | None`."
- §8 Slice 4 Step 5: "Call the helper from the live failed terminal projection in `dayu/host/read_api.py`."
- §8 Slice 4 Step 6: "Call the same helper from the outbox terminal item projection in `dayu/host/outbox.py`."
- §8 Slice 4 Step 8: "Add tests covering `provider_request_id=None` and `client_correlation_id` present for both live watcher and outbox fallback, and assert the rendered suffix is identical across both paths."

**Verification**: Shared private helper required, both projection paths named, test requirement for identical rendering across both paths specified. The implementation agent has clear, unambiguous instructions.

---

### Finding 3: Python runner log visibility is mandatory on existing runner.http.response line, same log site and level, no extra log line

**Status**: ✅ **CLOSED**

**Prior state** (DS F2, MiMo F05): Plan had an escape hatch—"if implementation can thread request identity into _request_once(...) without awkward coupling"—that could let the implementation agent skip the log extension entirely. The user constraint required "logs must be able to show client_correlation_id," and the plan's uncertainty created ambiguity about whether terminal/Tool Trace visibility alone would satisfy that constraint.

**Current plan evidence**:

- §7 Decision 4: "Extend that existing line to include `client_correlation_id=%s` on the same line. This reuses the existing log site and level. Do not add a second log line."
- §7 Decision 4: "The value is available from `request_identity` in the caller and must be passed into the private attempt method, likely by adding a `client_correlation_id: str | None` parameter to `_do_attempt(...)`. This is an intra-class private signature change, not a public contract change."
- §7 Decision 4: "Do not add a new log point, do not add an extra log line, and do not change the log level."
- §1 Success Signal: "既有 Python runner `runner.http.response` 日志行必须在同一 log site、同一 log level、同一行携带 `client_correlation_id`；不得新增专用日志事件、额外日志行或提高日志等级。"

**Verification**: The escape hatch is removed. The plan now mandates the log extension at the existing site with the existing level, specifies the exact mechanism (parameter addition to `_do_attempt`), and explicitly prohibits new log points, extra lines, or level changes.

---

### Finding 4: provider_request_id extraction remains x-request-id only; no tracing/infrastructure headers mapped to provider_request_id

**Status**: ✅ **CLOSED**

**Prior state** (DS F3, MiMo F04): Plan suggested extending `_PROVIDER_REQUEST_ID_HEADER_NAMES` to include `x-requestid`, `x-correlation-id`, `x-trace-id`, `x-amzn-requestid`, `cf-ray`. Tracing/infrastructure headers (`x-trace-id`, `x-correlation-id`, `cf-ray`) would produce misleading `provider_request_id` values that provider vendors cannot use for request lookup.

**Current plan evidence**:

- §1 Success Signal: "Provider request id 提取保持当前 `x-request-id` 单一路径；不得把 `x-trace-id`、`x-correlation-id`、`cf-ray` 或其它 tracing / infrastructure header 映射为 `provider_request_id`。若实现证据显示需要 header diagnostic，只能记录有界安全 header-name presence，不输出 header values，且不作为本 WU 必需实现项。"
- §7 Decision 5: "Current extraction only checks `x-request-id`; keep that behavior. This WU has no direct evidence that any other response header is a provider-native request id for the default product path."
- §7 Decision 5: "Do not map `x-trace-id`, `x-correlation-id`, `cf-ray`, W3C trace context headers, proxy headers, CDN headers, or other infrastructure/tracing headers into `provider_request_id`."
- §8 Slice 2 Step 1: "Keep `_extract_provider_request_id(...)` limited to `x-request-id`; preserve case-insensitive extraction, trimming, and empty value ignore behavior."
- §8 Slice 2 Step 2: "Add or update tests confirming `x-trace-id`, `x-correlation-id`, `cf-ray`, and other infrastructure/tracing headers are not extracted as `provider_request_id`."

**Verification**: The speculative allowlist is removed. Extraction is bounded to `x-request-id` only. Tests must confirm that tracing/infrastructure headers are NOT extracted. Header diagnostic (if ever needed) is deferred and bounded to safe name presence only.

---

### Finding 5: Tool Trace diagnostic_ref=None is explicitly allowed; no fake event_id/provider id fallback

**Status**: ✅ **CLOSED**

**Prior state** (MiMo F03): Plan's risk description suggested that validation might reject `diagnostic_ref=None` and that an `event_id` fallback might be needed. Code evidence (`durable/tool_trace.py:988`) already proved `diagnostic_ref=None` is valid via `_require_optional_non_empty_text`.

**Current plan evidence**:

- §7 Decision 6: "Current Tool Trace hot row validation permits `diagnostic_ref=None`; keep `None` when there is no raw payload ref or provider request id. Do not introduce an `event_id` fallback, do not fake `diagnostic_ref`, and do not put `client_correlation_id` into `provider_request_id`."
- §8 Slice 3 Step 3: "Assert hot row has `provider_request_id is None`, `diagnostic_ref is None` when no raw payload ref exists."
- §11 Risks: "Tool Trace diagnostic rows with `diagnostic_ref=None` are currently valid. Tests should lock that a row with no provider id and no raw payload ref can still preserve `client_correlation_id`."

**Verification**: The plan now explicitly acknowledges that `diagnostic_ref=None` is valid, prohibits faking it with event_id or provider id fallbacks, and requires tests to lock this behavior.

---

### Finding 6: Slice 1 requires baseline assembly tests before default enablement

**Status**: ✅ **CLOSED**

**Prior state** (DS F5): Plan assumed "Existing disabled policy tests still pass" without verifying the baseline. Large test files (`test_host_assembly.py` at 80KB+, `test_smoke_host_public_multiturn_assembly.py`) had no `ClientCorrelationPolicy` assertions, and changing the default could silently break tests that do exact `RunnerSpec` field comparisons.

**Current plan evidence**:

- §8 Slice 1 Step 1: "Before changing the default, run the current baseline assembly tests listed for this slice and record whether they pass."
- §8 Slice 1 Step 6: "If tests fail after the default changes, classify each failure before editing: expected behavior change: update assertions that assumed `DISABLED` Service assembly default. regression: fix the implementation rather than weakening tests."

**Verification**: Baseline test run is now required before the default change. Failure classification (expected behavior change vs regression) is specified, preventing the implementation agent from either blindly updating all assertions or treating regressions as expected.

---

## Architecture Boundary Review

Re-verified that the plan respects all architectural constraints after fixes:

- **Layering**: Service assembly sets typed policy → Engine consumes typed spec → Host projects from durable payload. No cross-layer leakage. ✅
- **Dependency direction**: No reverse dependencies introduced. Service → Engine contracts, Host → durable payload. ✅
- **Public contracts**: `HostEvent`, `OutboxTerminalItem`, `EntrypointRunTerminalResult` shapes unchanged. Suffix at projection boundaries only. ✅
- **Durable truth**: No EventLog fact additions, no payload `message` mutation, no digest changes. ✅
- **State machine**: No Run/Attempt state transitions changed. All changes are read/projection/output behavior or Service assembly input behavior. ✅

## Overdesign Check

None found. The plan uses existing contracts, existing log sites, existing projection boundaries, and existing Tool Trace fields. No new config items, no provider string branches, no new event types, no new log infrastructure.

## Residual Risks

| # | Risk | Severity | Tracking |
|---|------|----------|----------|
| R1 | Provider rejects `X-Client-Request-Id` header (400 or silent ignore) | Medium | Plan §12 Stop Condition — stop implementation and report blocker with evidence |
| R2 | CLI output tests may exact-match `error_message` text and fail when suffix is appended | Low | Plan §8 Slice 1 baseline test run should catch this; Slice 4 implementation should update affected CLI/output test assertions |
| R3 | `client_correlation_id` parameter threading into `_do_attempt()` uses "likely" wording — minor softness in plan specificity | Very Low | Implementation agent must resolve exact mechanism; plan intent is unambiguous that the value must reach the log line |
| R4 | Diagnostic suffix format (`client_correlation_id=<id>`) is hardcoded — future i18n or format changes would require refactoring | Very Low | Format is simple, internal, operator-facing; low probability of change |

## Conclusion

**Pass**

All 6 accepted findings from prior plan reviews (AgentDS and AgentMiMo) are conclusively closed in the current plan artifact. The plan is code-generation-ready:

- Terminal diagnostic visibility is converged to a single minimal path at Host public projection boundaries with no durable mutation.
- Live watcher and outbox fallback share the same suffix formatting helper and both have test coverage requirements.
- Python runner log visibility is mandatory on the existing `runner.http.response` line with no escape hatch.
- Provider request id extraction is bounded to `x-request-id` only; tracing/infrastructure headers are explicitly excluded.
- Tool Trace `diagnostic_ref=None` is explicitly allowed; no fake fallback ids.
- Slice 1 requires baseline assembly tests before the default change with failure classification guidance.

Slices are independently testable, architecture boundaries are respected, and stop conditions are specified. No blocking findings remain.

**Blocking findings count**: 0

**Residual risks**: 4 (all low/medium severity, all have tracking destination or stop condition coverage)

---

## Summary

- **Artifact path**: `docs/reviews/plan-rereview-wu-eng-02-r1-ds-20260620.md`
- **Conclusion**: Pass
- **Blocking findings**: 0
- **Material findings**: 0
- **Residual risks**: R1 (provider header rejection, stop condition), R2 (CLI output test assertion updates), R3 (minor parameter threading softness), R4 (hardcoded suffix format)
- **Next step**: Plan is ready for implementation gate entry.
