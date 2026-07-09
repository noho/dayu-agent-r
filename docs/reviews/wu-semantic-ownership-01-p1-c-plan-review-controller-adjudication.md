# WU-SEMANTIC-OWNERSHIP-01 P1-C Plan Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P1-C`
- Gate: plan review adjudication
- Plan artifact: `docs/host/wu-semantic-ownership-01-p1-c-plan.md`
- AgentCodex delivery: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-p1-c-plan-controller-validation.md`
- AgentMiMo review: `docs/reviews/plan-review-20260709-p1-c-mimo.md`
- AgentDS review: `docs/reviews/plan-review-20260709-p1-c-ds.md`

## Review Results

- AgentMiMo: `pass`, 0 blocking and 7 non-blocking findings.
- AgentDS: `pass-with-risks`, 1 blocking and 5 non-blocking findings.

## Controller Decision

Decision: `fix-required`.

The plan structure is acceptable, but the plan must be tightened before implementation. In particular, `run_input.py` memory `evidence_kind=...` rendering is already proven to enter LLM context through `SystemMessage`; it must be a deterministic S1 action item, not a conditional discovery item.

## Accepted Findings

### P1C-PLAN-F01 — RunInput memory `evidence_kind` rendering must be a deterministic S1 action

- Sources: `P1C-PLAN-DS-F01`, `P1C-PLAN-MIMO-F01`, `P1C-PLAN-MIMO-F07`
- Severity: high
- Blocking: yes
- Required fix: update S1 to explicitly state that `_memory_evidence_fact_message()` and fallback codec rendering in `dayu/host/run_input.py` are LLM-facing and must be removed or converted to business-readable text. Add explicit `tests/host/test_run_input_builder.py` coverage.

### P1C-PLAN-F02 — Duplicate governance S0 classification must include non-AWAITING_FANOUT decisions

- Sources: `P1C-PLAN-DS-F02`, `P1C-PLAN-MIMO-F02`
- Severity: medium
- Blocking: no
- Required fix: update S0 to classify REUSE / HINT / HARD_STOP / REQUIRE_JUSTIFICATION / DURABLE_MISSING paths that can enter `ToolFailedOutcome`, and distinguish legitimate model-facing behavior guidance from governance leakage.

### P1C-PLAN-F03 — Waiting wording classification needs an explicit litmus test

- Sources: `P1C-PLAN-DS-F03`, `P1C-PLAN-MIMO-F03`
- Severity: medium
- Blocking: no
- Required fix: update S0 to include a practical decision rule for when "等待工具结果返回" is task-necessary business behavior text versus Host wait-governance leakage.

### P1C-PLAN-F04 — `ToolBusinessCancelled` fallback and Doc/Web cancellation text must be in S2 scope

- Sources: `P1C-PLAN-DS-F04`, `P1C-PLAN-MIMO-F04`
- Severity: medium
- Blocking: no
- Required fix: update S2 to explicitly analyze and migrate `ToolBusinessCancelled` optional message/hint fallback, and include Doc/Web cancellation messages that still contain "宿主取消" / "后续调度".

### P1C-PLAN-F05 — Evidence kind Host derivation strategy must be concrete before implementation

- Sources: `P1C-PLAN-DS-F05`, `P1C-PLAN-MIMO-F05`
- Severity: medium
- Blocking: no
- Required fix: update S1 to require selection and documentation of a reliable Host derivation strategy before changing compaction schema. The plan must list candidate strategies and state how old compact artifacts are handled under the no-compat policy.

### P1C-PLAN-F06 — Cancel hint wording duplicated across Fins/Doc/Web must have consistency guard

- Sources: `P1C-PLAN-DS-F06`, `P1C-PLAN-MIMO-F06`
- Severity: low
- Blocking: no
- Required fix: update S2 to require consistent neutral cancellation text across Fins, Doc and Web tool call owners. Prefer a shared layer-neutral helper/constant only if it does not reintroduce Host governance text; otherwise require implementation artifact consistency audit.

### P1C-PLAN-F07 — Validation should include P1-A projection contract preservation scan

- Sources: AgentDS validation observation, AgentMiMo validation observation
- Severity: low
- Blocking: no
- Required fix: add a validation or S3 scan confirming P1-C consumers still use/preserve P1-A accepted-result projection truth and do not rederive query/status/source semantics in LLM-facing text.

## Rejected / Not Accepted

- AgentMiMo's severity downgrade for DS F01 is accepted only as a severity discussion, not as a reason to leave the plan unchanged. The direct evidence that `evidence_kind=...` enters `SystemMessage` is enough to require a deterministic plan action.

## Required Plan Fix Validation

After the plan fix:

- `git diff --check`
- Re-review by AgentMiMo and AgentDS.
