# WU-CLI-SMOKE-01-R1 Slice 1 Code Re-review Controller Adjudication

## Scope

- Base: `929691ea`。
- Accepted finding: DS-F03。
- Fix artifact: `docs/reviews/wu-cli-smoke-01-r1-slice1-fix-codex.md`。
- Controller validation: `docs/reviews/wu-cli-smoke-01-r1-slice1-fix-controller-validation.md`。
- Re-review artifacts:
  - `docs/reviews/code-review-20260721-011148.md`（AgentMiMo）。
  - `docs/reviews/code-review-20260721-010824.md`（AgentDS）。

## Decisions

- AgentMiMo: `accepted`；DS-F03 fixed，无新增 material defect。
- AgentDS: `accepted`；DS-F03 fixed，无新增 material defect。
- DS-F03 final status: `fixed`。新测试先证明 enabled renderer 可输出，再在 `close()` 后使用新 dedupe key、更大 runtime sequence、不同文本调用 `record()`，精确断言 stderr 不变；dedupe、倒序、disabled 分支均不能制造假通过。
- Fix boundary: pass。仅新增直接测试与 fix/review artifacts，没有生产代码 fix、兼容分支、fake owner 或 Slice 2 scope。
- DS-F01 final status: `rejected-with-reason`，本 re-review 未提供新的反例。
- DS-F02 final status for this gate: `deferred-with-owner` to Slice 2；必须在 Slice 2 E2E / slow-consumer validation 收口。

## Validation

- AgentCodex: renderer tests 9 passed；prompt / interactive tests 90 passed；pyright 0 errors；diff check pass。
- Controller: combined CLI focused tests 99 passed；pyright 0 errors；diff check pass。
- AgentMiMo: renderer tests 9 passed；prompt / interactive tests 90 passed；pyright 0 errors；diff check pass。
- AgentDS: combined CLI focused tests 99 passed；pyright 0 errors；diff check pass。
- warnings 均为既有 `edgar` dependency deprecation，不归当前 fix。

## README / Propagation / Residual

- README decision: no update；test-only fix 未改变测试层级、命令或维护规则。
- Propagation audit: Host transient owner、Service DTO、CLI production contract 与 durable boundary 均未被 fix 改变。
- Current-slice residual: none。
- Slice 2 owner: DS-F02、deterministic readiness / terminal barrier、3×1000 scale、真实 slow-consumer E2E 与 README closure。

## Decision

`accepted-slice1-rereview`。Slice 1 可进入 accepted slice commit；不得跳过 commit 直接进入 Slice 2。
