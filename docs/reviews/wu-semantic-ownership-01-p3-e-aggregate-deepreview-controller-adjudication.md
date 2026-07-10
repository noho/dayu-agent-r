# WU-SEMANTIC-OWNERSHIP-01 P3-E Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-E - Tool result, accepted status, wait callback, and Fins direct stream contracts`
- Gate: `aggregate deepreview`
- Review range: `5c03bfbc..HEAD`
- MiMo artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-aggregate-deepreview-mimo.md`
- DS artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-aggregate-deepreview-ds.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-p3-e-aggregate-validation.md`

## Verdict

`accepted`

Both aggregate deepreview artifacts return PASS with zero material findings. No fix gate is required for P3-E aggregate deepreview.

## Finding Adjudication

| Source | Raw item | Controller decision | Reason |
| --- | --- | --- | --- |
| AgentMiMo | No material finding | accepted-pass | MiMo walked the S1/S2/S3 owner paths and found no current-scope defect. |
| AgentDS | No material finding | accepted-pass | DS walked the ToolResult, accepted-result, wait callback, and Fins direct stream chains and found no current-scope defect. |
| AgentDS | OQ-01: `_accept_timeout_message` exposes `last_error_code` in message | rejected-as-current-defect; retained as non-blocking residual | P3-E plan explicitly kept `last_error_code` in the error message while removing governance details from `hint`. It is diagnostic text, not a duplicated status owner. Future LLM-facing wording hardening can happen at the projection/message owner if real model behavior shows confusion. |
| AgentDS | OQ-02: CLI `_consume_fins_direct_events` fallback raises shared protocol error | rejected-as-current-defect | The fallback uses the same shared `FinsDirectStreamProtocolError` contract and is defense-in-depth for mocked or truncated streams. It does not create a second protocol owner or fabricate a business result. |
| AgentDS | RR-01: future consumers may miss `UNKNOWN` status | retained as future-change guardrail | Current consumers use the shared projection and fail closed. Future exhaustive consumers must explicitly handle `UNKNOWN` / `LOST`. |
| AgentDS | RR-02: producer hang after `RESULT` before sentinel | retained as Fins runtime residual | Current producers are finite and the no-hang path is tested. If future producer lifecycle bugs appear, the fix owner is Fins runtime direct stream timeout/cancellation handling, not CLI or Service fallback. |
| AgentDS | RR-03: aggregate review did not cover full Engine and full ToolRuntime state machines | accepted residual scope note | P3-E aggregate deepreview covered the P3-E change surface. The umbrella WU still requires later sub WUs and full-repository review rounds before final closeout. |

## Propagation Audit

- `ToolResult` discriminator invariant remains owned by `dayu.contracts.tool_result`; ToolRuntime and Engine consume runtime-enforced envelopes.
- ToolRuntime failure projection no longer places governance reasons, diagnostic refs, accept rejection reasons, or truncation reason codes into LLM-facing `hint`; diagnostics remain in Tool Trace, messages, metadata, and accept owner fields.
- Service callback JSON parsing owns `provider_status_ref` shape validation; bare strings fail closed before Host adapter invocation.
- Host accepted-result projection owns accepted status derivation from typed durable fields. Raw outcome remains result/details material only.
- Read API, run input/evidence, memory, and compact material consume the shared accepted-result projection rather than reconstructing status.
- Fins runtime and Service enforce the unique terminal `RESULT` stream contract with shared typed protocol errors. CLI renders the protocol error and does not synthesize a business failure result.

## Controller Decision

- Required fix gate: no.
- Required re-review gate: no.
- P3-E aggregate deepreview status: pass.
- Next gate: accepted deepreview commit bookkeeping.

## Residual Risk

- P3-E does not close the umbrella WU. P3-F through P3-K and further full-repository deepreview rounds remain before final closeout.
- Future producer lifecycle hangs after a terminal `RESULT` remain owned by Fins runtime direct stream timeout/cancellation handling.
- Future consumers that perform exhaustive status branching must handle `UNKNOWN` and `LOST` explicitly.
