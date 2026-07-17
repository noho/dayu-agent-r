# WU-SEMANTIC-OWNERSHIP-01 R09 Plan Fix Controller Validation

## 0. Identity and decision

- Umbrella: `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation.
- Internal sub-WU: `R09 — Fins direct-stream terminal validator`.
- Original plan SHA-256: `85a783fbc21b699a0078c94532ac9562542095e2bfc9255ef811bbe4aad34210`, 689 lines.
- Fixed plan: `docs/host/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan.md`.
- Fixed plan SHA-256: `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d`, 773 lines.
- AgentCodex fix artifact: `docs/reviews/wu-semantic-ownership-01-r09-fins-direct-stream-validator-plan-fix-codex.md`.
- Fix artifact SHA-256: `b735f4f2990c8ddbb6896aaa8d84d63cfb79be318a31f00579a002cc9dc55c2c`, 92 lines.
- Controller result: `PASS / AWAITING_DUAL_FULL_PLAN_REREVIEW / IMPLEMENTATION_NOT_AUTHORIZED`.

Controller 已完整读取 fixed plan 773 行和 fix artifact 92 行，并以 current code signatures、producer/error source scan、README trigger、两路 review与 Controller adjudication复核。没有直接设计矛盾、未关闭 accepted plan finding 或 scope 扩张。

## 1. Source and workspace locks

| Evidence | Result |
|---|---|
| original plan / Controller adjudication / MiMo / DS hashes | match fix artifact and plan §1.4 |
| current control transition | SHA-256 `3d9403bcda79cb195e887141bbf75ffeac5e2ea6ca4d9072f9d2718d04461507`, match |
| production/test/design/umbrella/R08 source locks | match plan §1.3 |
| staged tree | empty |
| product/tests/README diff | none |
| plan-only write scope | fixed plan + AgentCodex fix artifact; Controller artifacts/control are separate Controller-owned inputs |
| `git diff --check` | PASS |

## 2. Accepted finding closure

| Finding | Controller validation | Status |
|---|---|---|
| `R09-PR-F01` | §3.4 enumerates exact runtime plain-def cutover, raw async-generator bridge, Service plain-def narrowing/direct pass-through and CLI no-new-await call sites. | closed |
| `R09-PR-F02` | §4 fixes upstream/cancel or typed validator error as primary; cleanup failure is explicit cause only; explicit close failure preserves identity; raw close is attempted at most once, including failure. Exact owner tests cover all branches. | closed |
| `R09-PR-F03` | speculative producer protocol-error queue/catch/test is absent. Queue union and generic execution-exception-to-bounded-business-failure RESULT remain unchanged; validator is sole protocol-error constructor. | closed |
| `R09-PR-F04` | early `terminal_result` access is ordinary `RuntimeError` with a module-owned safe constant; no new public/private error class or extra state split; four availability/object tests are explicit. | closed |
| `R09-PR-F05` | CLI keeps existing `dayu-cli {command}: {message}` and exit 1, does not expose/parse/enumerate raw reason. Root/dayu README remain no-update; Fins/Service/tests README updates follow actual owner changes. | closed |
| `R09-PR-F06` | Service/CLI provenance tests assert same stream/error and Fins-owned `reason/operation_kind/message/object`, including process aliases versus runtime `PREPROCESS`. | closed |

## 3. Architecture and overdesign validation

- Unique owner is `dayu.fins.direct_stream.ValidatedFinsEventStream`; `direct_events.py` owns typed data contracts, ingestion runtime owns raw producer/queue composition, Service/CLI are mechanical consumers.
- No factory, callback seam, wrapper/facade, compatibility re-export, loose iterator contract, `hasattr/getattr` close probing, parallel error schema or second validator is planned.
- `FinsIngestionRuntime.download/preprocess/upload` become plain `def` returning the concrete stream; Service methods stay plain `def`; only raw bridge and consuming helpers remain async where awaiting/iteration is real.
- Producer queue union/control flow stays unchanged. Generic producer execution failures remain bounded business failure results; invalid event sequence errors originate only in the consumer-side Fins validator.
- CLI presentation remains a user-readable projection rather than exposing an internal enum code. No LLM-facing or user-facing new protocol is introduced.

## 4. Lifecycle, tests and verification validation

- The state machine buffers the first RESULT until clean raw EOF and rejects missing, duplicate and event-after-result once at the Fins owner.
- Result-then-error never publishes success. Upstream error/cancellation identity remains primary; cleanup close failure is chained without replacing the semantic error.
- Explicit consumer close without a primary propagates the same close exception, and repeated close does not call the raw source twice.
- `terminal_result` distinguishes clean proof through one availability flag/guard without inventing clean/aborted public states.
- Owner, Service and CLI test nodes cover protocol decisions at the owner and propagation/presentation at consumers. Fixtures may feed raw sequences to the production validator but may not reproduce its algorithm.
- Complete validation retains affected tests, R06/R08/full Fins regression, five per-file coverage targets `>=80.00%`, full pyright zero, scoped Ruff, source/propagation scans, README checks and real download/process/upload success smoke. No coverage waiver was introduced.

## 5. README, security and deferred scope

- Root `README.md` and `dayu/README.md`: no update because command grammar, existing prefix/message, exit mapping, workflow, workspace and layer composition do not change.
- `dayu/fins/README.md`, `dayu/service/README.md` and `tests/README.md`: implementation update is required because owner/type/test narratives actually change.
- Retained: direct-event safe-text/leakage guards, operation-scoped cancellation, consumer-close cancellation state, queue backpressure, late publication defenses, storage containment/symlink/atomic behavior, R06 transaction, Host/ToolRuntime authorization and process fencing.
- Not implemented: Topic 8/9, unified tool authorization, R10-R12, Issues 142/151/175/177/178, Web/WeChat/render, process isolation, thread kill, Host wait/schema redesign or compatibility paths.

## 6. Next gate

AgentMiMo and AgentDS must independently perform a complete re-review of immutable fixed plan SHA-256 `a46cd4457121bf976368076ee729436a10a89ed0c50852f3eb73de90fbb1dd8d`. They must verify all six closures, full plan coherence, source/README/security/deferred boundaries and implementation readiness. Reviewer PASS cannot authorize implementation; Controller adjudication and an exact-scope accepted-plan local commit remain required.

Final state: `PASS / R09 dual complete fixed-plan re-review / IMPLEMENTATION_NOT_AUTHORIZED`.
