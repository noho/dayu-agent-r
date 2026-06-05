# WU-DUR / WU-OBS / WU-CM Closeout Slice 1 Code Review Controller Adjudication

## Gate

- Work unit: WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01
- Gate: Slice 1 code review adjudication
- Implementation artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice1-implementation-codex.md`
- Review artifacts:
  - `docs/reviews/wu-dur-obs-cm-closeout-slice1-code-review-mimo.md`
  - `docs/reviews/wu-dur-obs-cm-closeout-slice1-code-review-ds.md`

## Verdict

Code review result: pass-with-findings.

Controller judgment: no blocking finding. Two low-risk correctness/maintainability findings are accepted for immediate fix. One medium maintainability finding is deferred because production writes already fail closed and immediate repair would expand test-helper ownership beyond the current slice.

## Finding Adjudication

| Finding | Source | Ruling | Reason |
|---|---|---|---|
| Storage kind constants are duplicated between write and read modules | MiMo 1-NB, DS F2 | accepted | The project requires repeated runtime semantics to have one truth source. This is low-risk and in-scope because descriptor kind constants already live in `dayu/host/durable/schema.py`. |
| Inline arguments / semantic query reader ignores incompatible payload refs | DS F3 | accepted | Reader should fail closed on mutually exclusive inline/ref fields. The writer is currently correct, but accepting malformed durable payloads weakens the durable atom boundary. |
| `ToolAcceptCall.accepted_arguments` optional default can let low-level test helpers omit durable truth | DS F1 | deferred-with-owner | Current production accept path and reuse path pass accepted arguments, and EventLog write fails closed if missing. Making the field required requires broad test-helper changes beyond this slice. Owner: Slice 7 public/test closeout, or a dedicated cleanup before final closeout if reviewers see the risk materialize. |

## Required Fixes

1. Move storage kind constants to a single module-level truth source and make both write and read paths import the same constants.
2. Add fail-closed checks for illegal inline/ref combinations:
   - `arguments_storage_kind="inline_json"` must reject non-null `arguments_payload_ref`.
   - `semantic_query_storage_kind="inline_text"` must reject non-null `semantic_query_payload_ref`.
   - tests must cover these malformed payload cases.

## Residual Risks

- Optional `accepted_arguments` default remains a deferred maintainability risk with owner.
- Tool Trace hot projection for atom refs/digests remains later OBS scope.
- Compact evidence query consumption remains later Slice 5 scope.

## Next Gate

Next gate: Slice 1 fix by AgentCodex.

Expected fix artifact: `docs/reviews/wu-dur-obs-cm-closeout-slice1-fix-codex.md`.
