# Phase 12.3 Plan Review Controller Adjudication

日期：2026-05-22

对象：

- Plan artifact: `docs/host/phase12-3-config-usage-governance-plan.md`
- AgentMiMo review: `docs/reviews/phase12-3-plan-review-mimo-20260522.md`
- AgentDS review: `docs/reviews/phase12-3-plan-review-ds-20260522.md`

## Verdict

Plan review gate requires fix.

- AgentMiMo: `PASS_WITH_FINDINGS`, blocking count = 0.
- AgentDS: `PASS_WITH_FINDINGS`, blocking count = 1.

Controller accepts AgentDS B1 as a blocking plan defect, with modified fix direction.

## Accepted Blocking Finding

### P12.3-PLAN-B1: `provider_request_id` source is not available on usage events

Decision: accepted as blocking.

Reason:

- The plan requires Host `USAGE_REPORTED` projection payload to include `provider_request_id`.
- The plan also states that Phase 12.3 must not modify Engine `RunnerUsageRecordedData` / `UsageReportedData` or the Runner usage event contract.
- Current `UsageReportedData` and `RunnerUsageRecordedData` contain token counts but no `provider_request_id`.
- Therefore the plan currently asks implementation to read a field that does not exist while also forbidding the contract change that would provide it.

Controller fix direction:

- Do not expand Engine usage event contracts in Phase 12.3.
- Remove any requirement that `provider_request_id` must be read from `UsageReportedData`.
- Host usage observation may set `provider_request_id=None` when not available from current Engine event context.
- If the implementation can obtain a provider request id from an existing durable / execution context without changing Engine contracts or adding extra lookup fragility, it may include it, but this is optional.
- Add focused tests that prove missing `provider_request_id` does not block usage projection or Context Governance observation.
- Any future requirement to carry provider request id directly on usage events must be a separate Engine contract design gate, not a Phase 12.3 implementation detail.

Rejected part of AgentDS suggestion:

- AgentDS suggested adding `provider_request_id` fields to `RunnerUsageRecordedData` and `UsageReportedData`.
- This is rejected for current Phase 12.3 because `docs/host/implementation-control.md` explicitly forbids modifying the Runner usage event contract in this phase.

## Non-Blocking Observations

AgentMiMo O1-O7 and AgentDS N1-N7 are accepted as implementation guidance only. They do not require plan fix except where covered by P12.3-PLAN-B1.

Implementation agents should pay particular attention to:

- usage observation estimate-unavailable tests;
- `context_window_class` / `min_context_window_tokens` diagnostics;
- keeping `wechat-*` profile content honest if it initially shares `standard-*` policy values;
- optional broader Host regression in aggregate validation.

## Required Plan Fix

Update `docs/host/phase12-3-config-usage-governance-plan.md`:

- remove `provider_request_id` from required Host usage projection fields;
- remove tests that require `UsageReportedData.provider_request_id`;
- state that provider request id is optional and defaults to `None` when unavailable;
- add a test requirement that missing provider request id is accepted and does not affect Run / Attempt state;
- keep Engine usage event contracts unchanged.

After plan fix, run:

```bash
git diff --check -- docs/host/phase12-3-config-usage-governance-plan.md docs/reviews/phase12-3-plan-review-controller-adjudication-20260522.md
```

