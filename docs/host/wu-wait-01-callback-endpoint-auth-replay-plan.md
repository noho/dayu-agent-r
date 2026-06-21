# WU-WAIT-01 Callback Endpoint / Auth / Replay Plan

## Goal / Motivation / Success Signal

目标：把外部 callback completion 建模为 Host-owned wait resolution，而不是 agent-local callback trick。callback endpoint 只是进入现有 `resolve_wait` 管线的 transport adapter；所有 Run / Attempt / wait record / EventLog durable 状态迁移仍由 Host wait resolution 统一负责。

动机成立。直接证据是：

- `dayu/host/api.py` 已有 `WaitResolutionSource.CALLBACK`，说明公共来源枚举预留了 callback 来源。
- `dayu/host/waiting.py` 的 `DefaultHostResolveWaitService.resolve_wait(...)` 已是 wait completion 的状态迁移 owner，包含 idempotency、late rejection、resume attempt 创建、terminal 收口和 projection catch-up。
- `dayu/host/wait_adapter.py` 只实现 poller 与 activation adapter，模块 docstring 明确“不实现 callback endpoint 或外部系统协议”。
- `tests/host/test_resolve_wait_command.py` 与 `tests/host/test_wait_cancel_late_result.py` 已覆盖 replay、同 key 不同 outcome conflict、failed/lost terminal、cancelled outcome、late rejection after cancel 等核心语义。

成功信号：

- Service/Web 收到 callback 后，只完成 transport parsing/auth/status mapping，然后调用 Host callback adapter。
- Host callback adapter 转换为 `ResolveWaitRequest(source=CALLBACK)` 并通过 command-layer `CallbackWaitResolvePort` 进入现有 `resolve_wait` 管线。
- callback / poller / manual resolve 在 durable wait resolution 语义上收敛。
- 同一 `(wait_id, idempotency_key)` 且同 outcome digest 为 replay；同 key 不同 outcome digest 为 conflict。
- unknown wait、cancelled/lost late callback、stale callback、digest mismatch、malformed payload、auth failure、transport rejection、successful replay 都有不同 typed diagnostic/status。

## Non-goals / Scope Boundary

- 不实现 issue #90 的 production poller loop / backoff / fencing / retry。
- 不实现 issue #92 的 external job physical cancel / revoke / abandon。
- 不修改 Engine awaiting public model。
- 不引入新的 public wait lifecycle。
- 不在 Host core 引入 FastAPI、Flask 或任何 HTTP framework。
- 不重写 `resolve_wait` 状态机。
- 不让 endpoint adapter 直接写 EventLog、Run、Attempt、wait record、projection 或 durable state。
- 不实现 Claude Code / Codex UI parity。

Stop conditions：

- 若 implementation 发现需要 durable schema migration，停止并回到 design gate。
- 若必须选择具体 HTTP framework 才能实现 Host contract，停止；HTTP framework 不得进入 Host core。
- 若 callback stale / auth / replay 需要改写 wait lifecycle 状态机，停止。
- 若实现开始处理 poller retry/fencing 或 external job physical cancel，停止并转 issue #90/#92。

## Design Document Alignment

对齐 `docs/host/design.md`：

- 分层保持 `UI -> Service -> Host -> Engine`。Service/Web 拥有实际 HTTP route、header/body parsing、auth transport mapping 和 HTTP status mapping；Host core 只暴露 framework-independent typed callback contract / adapter。
- Host 仍是 Run / Attempt / EventLog / wait governance 真源。callback 不成为第二套状态 owner。
- ToolRuntime / wait result 事实必须走 Host accept / resolve barrier；callback endpoint 不绕过 barrier。

对齐 `docs/engine/design.md`：

- Engine 只执行单次 `AgentRunRequest`，不拥有 Session / Run 生命周期，不持久化 Host 状态。
- WAITING 后恢复必须由 Host 构造新的 run input / attempt；callback 不修改 Engine awaiting public model。

对齐 issue #89：

- callback request contract 包含 auth source / claims、wait id、idempotency key、payload digest、observed/completed timestamp、typed outcome refs/payload。
- callback endpoint 不直接 append EventLog 或更新 durable state。
- diagnostics 区分 transport rejection、auth failure、malformed payload、digest mismatch、idempotency conflict、wait state rejection、successful replay。

## First-principles Judgment

问题真实存在，但严重性不在“缺少 HTTP route”本身，而在“缺少把 callback completion 约束进 Host-owned wait resolution 的 typed boundary”。如果直接在 Web route 中读取/写入 wait record，会绕过 Host 状态机，破坏 replay、late rejection 和 resume dispatch 的同源语义。

更好的方案不是把 FastAPI route 放进 Host，也不是给 ToolRuntime 增加 agent-local callback hook，而是：

1. Host core 增加 framework-independent callback envelope、auth protocol、adapter result/status。
2. Host adapter 只做 auth、typed validation、callback-specific digest/stale preflight 和 `ResolveWaitRequest(source=CALLBACK)` 转换。
3. Service/Web 增加无框架依赖的 HTTP-like mapper，真实 Web 框架日后只包一层薄 route。

这样可以复用现有 `resolve_wait` root cause 语义，避免复制状态机。

## Affected Files / Modules

预计新增：

- `dayu/host/wait_callback.py`
- `tests/host/test_wait_callback.py`
- `dayu/service/wait_callback_endpoint.py`
- `tests/service/test_wait_callback_endpoint.py`

预计修改：

- `dayu/host/__init__.py`
- `dayu/host/command.py` 或现有 Host command assembly 模块，用于实现 `CallbackWaitResolvePort` 并复用 dispatch wakeup 语义。
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`
- `dayu/service/__init__.py`，仅在 Service 包当前导出策略需要公开 mapper 时修改。
- `dayu/host/README.md`、`dayu/service/README.md` 按 README 约束检查后决定是否更新。

不应修改：

- `dayu/engine/**`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/state.py` 的 schema/state machine shape，除非 implementation 发现必须迁移；一旦必须迁移即停止。
- `dayu/host/waiting.py` 的 resolve state machine，除非只为暴露已有 replay result 做极小签名/port 适配；默认不改。

## Contract / Schema / State-machine / Public Interface Changes

Durable schema：不变。

State machine：不新增 wait lifecycle。callback resolution 等价于：

```text
WaitCallbackCompletionEnvelope
  -> authenticate / validate / stale preflight
  -> ResolveWaitRequest(source=CALLBACK)
  -> CallbackWaitResolvePort
  -> existing resolve_wait pipeline with command wakeup semantics
```

Host public interface 新增 framework-independent contract，建议放在 `dayu/host/wait_callback.py` 并由 `dayu.host` root 导出：

```python
class WaitCallbackAdapterStatus(StrEnum):
    ACCEPTED = "accepted"
    REPLAYED = "replayed"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    UNKNOWN_WAIT = "unknown_wait"
    LATE_WAIT_CANCELLED = "late_wait_cancelled"
    LATE_WAIT_LOST = "late_wait_lost"
    STALE_CALLBACK = "stale_callback"
    DIGEST_MISMATCH = "digest_mismatch"
    AUTH_FAILED = "auth_failed"
    INVALID_WAIT_STATE = "invalid_wait_state"
    INTERNAL_ERROR = "internal_error"
```

`TRANSPORT_REJECTED` and `MALFORMED_PAYLOAD` are not Host adapter statuses. They are Service/Web transport mapper diagnostics used before a Host envelope exists:

```python
class WaitCallbackTransportStatus(StrEnum):
    TRANSPORT_REJECTED = "transport_rejected"
    MALFORMED_PAYLOAD = "malformed_payload"
```

Core dataclass shape：

- `WaitCallbackAuthInput`
  - `auth_source: str`
  - `credential_ref: str`
  - `presented_claims: tuple[AuthorizationClaim, ...]`
- `WaitCallbackAuthAccepted`
  - `actor: str`
  - `authorization_claims: tuple[AuthorizationClaim, ...]`
- `WaitCallbackAuthRejected`
  - `reason_code: str`
  - `message: str`
  - `retryable: bool`
- `WaitCallbackAuthenticator(Protocol)`
  - `authenticate_callback(request: WaitCallbackAuthRequest) -> WaitCallbackAuthResult`
- `WaitCallbackCompletionEnvelope`
  - `wait_id: str`
  - `idempotency_key: str`
  - `payload_digest: str`
  - `observed_at: datetime`
  - `completed_at: datetime`
  - `outcome: ResolveWaitOutcome`
  - `auth: WaitCallbackAuthInput`
  - `request_id: str`
  - `correlation_id: str | None`
- `WaitCallbackAdapterResult`
  - `status: WaitCallbackAdapterStatus`
  - `run: RunSnapshot | None`
  - `idempotent_replay: bool`
  - `diagnostic_code: str`
  - `message: str`
  - `retryable: bool`

Callback resolve port shape：

- `CallbackWaitResolvePort(Protocol)`
  - `resolve_callback_wait(wait_id: str, request: ResolveWaitRequest, context: HostCallContext) -> CallbackWaitResolveResult`
- `CallbackWaitResolveResult`
  - `run: RunSnapshot`
  - `idempotent_replay: bool`

The command-layer implementation of this port is the only component allowed to bridge from callback adapter to the existing wait resolution internals. It must call the existing resolve pipeline, convert any internal `RunRow` to `RunSnapshot` before returning, and preserve the existing command wakeup behavior: when resolve creates a dispatch record and `idempotent_replay` is false, it must call the dispatch wakeup port exactly once. Replay must not wake dispatch again.

`payload_digest` 是 callback sender 对 wait resolution canonical outcome material 的声明摘要。Host adapter 用 `sha256_digest_json` 对 existing wait resolution digest material 重新计算：

```json
{
  "wait_id": "wait-123",
  "idempotency_key": "provider-completion-abc",
  "outcome": {"kind": "completed", "...": "..."}
}
```

This intentionally matches the existing wait resolution digest semantics: `wait_id + idempotency_key + outcome`. `observed_at` and `completed_at` are excluded and must not affect replay conflict. A same callback replay with a different `observed_at` or `completed_at` remains `REPLAYED` when the outcome is unchanged. Same idempotency key with a different outcome still reaches the existing resolve pipeline and is classified as `IDEMPOTENCY_CONFLICT`. Auth, transport headers, request id, correlation id, `observed_at`, and `completed_at` are never digest inputs.

`completed_at` is transport/audit input only for callback validation and stale classification in this WU. It is not persisted by `resolve_wait`, not added to `ResolveWaitRequest` payload, and not included in wait resolution digest. `ResolveWaitRequest.observed_at` remains the Host-observed callback time used by the existing EventLog path.

Stale rule：只使用现有 wait record fields，不新增 schema。Current code only populates `WaitRecordRow.deadline_at`; `expires_at` exists in schema but is currently reserved and written as `None` by the wait creation path. Adapter stale classification therefore depends on `deadline_at` today. If a future path populates `expires_at`, the same comparison may apply without changing this contract.

`deadline_at` / `expires_at` are persisted as UTC timestamp strings. Adapter must parse them with existing Host timestamp helpers where available; accepted input is an ISO-8601 UTC timestamp (`Z` or explicit `+00:00`). If both fields are absent, callback must not be rejected as stale. If `completed_at` is later than the parsed deadline boundary, adapter returns `STALE_CALLBACK`, does not call the resolve port, and writes no durable state. Invalid persisted deadline/expires strings are treated as `INVALID_WAIT_STATE`, not as stale, because the callback is not the source of that corruption.

## Exact Callback Endpoint Form and Layer Boundary

Host core 不实现 HTTP route。Service/Web 的稳定 route 形式为：

```text
POST /api/dayu/waits/{wait_id}/callback-completions
Content-Type: application/json
Authorization: Bearer <token>
X-Dayu-Callback-Auth-Source: bearer
X-Dayu-Callback-Request-Id: <client request id>
X-Dayu-Callback-Correlation-Id: <optional correlation id>
```

Body：

```json
{
  "wait_id": "wait-123",
  "idempotency_key": "provider-completion-abc",
  "payload_digest": "sha256:...",
  "observed_at": "2026-06-21T10:00:01.000000Z",
  "completed_at": "2026-06-21T10:00:00.000000Z",
  "outcome": {
    "kind": "completed",
    "result": {"ok": true, "value": {"answer": 42}, "meta": null},
    "payload_ref": null
  }
}
```

Supported `outcome.kind` values map one-to-one to existing Host outcomes. The Service mapper owns these JSON shapes and must construct the typed Host outcome dataclasses before calling Host adapter.

- `completed` -> `ResolveWaitCompletedOutcome`
- `failed` -> `ResolveWaitFailedOutcome`
- `cancelled` -> `ResolveWaitCancelledOutcome`
- `lost` -> `ResolveWaitLostOutcome`

Completed example:

```json
{
  "kind": "completed",
  "result": {
    "ok": true,
    "value": {"answer": 42},
    "meta": null
  },
  "payload_ref": null
}
```

Failed example:

```json
{
  "kind": "failed",
  "failure": {
    "error_code": "provider_error",
    "message": "Provider returned a terminal error.",
    "meta": {"provider_status": "failed"}
  },
  "payload_ref": null
}
```

Cancelled example:

```json
{
  "kind": "cancelled",
  "cancelled": {
    "reason_code": "user_cancelled",
    "message": "The external job was cancelled before completion."
  },
  "payload_ref": null
}
```

Lost example:

```json
{
  "kind": "lost",
  "reason_code": "provider_lost",
  "message": "The provider can no longer locate the external job.",
  "provider_status_ref": "jobs/provider-123/status/last-seen"
}
```

Path `wait_id` and body `wait_id` must match. Mismatch is `TRANSPORT_REJECTED` / HTTP 400 and must not call Host adapter.

HTTP status mapping belongs to Service/Web:

- `ACCEPTED` -> 202
- `REPLAYED` -> 200
- `UNKNOWN_WAIT` -> 404
- `AUTH_FAILED` -> 401 when credential is missing, malformed, expired, or otherwise not authenticated; 403 when credential is authenticated but lacks permission for the wait/callback action. This mapping is deterministic and based on `WaitCallbackAuthRejected.reason_code`, not exception text.
- `DIGEST_MISMATCH` -> 400
- Service `MALFORMED_PAYLOAD`, Service `TRANSPORT_REJECTED` -> 400
- `IDEMPOTENCY_CONFLICT`, `INVALID_WAIT_STATE` -> 409
- `LATE_WAIT_CANCELLED`, `LATE_WAIT_LOST`, `STALE_CALLBACK` -> 410
- `INTERNAL_ERROR` -> 500

Response body must include typed `status`, `diagnostic_code`, `message`, `retryable`, and when available `run_id` / `run_status`; it must not echo result payload.

## Implementation Decisions

- Host callback adapter may read wait record for diagnostic/stale classification, but may not write durable state except through the injected `CallbackWaitResolvePort`.
- Host adapter must not call `DefaultHostResolveWaitService` directly. It calls an injected `CallbackWaitResolvePort` implemented in the command layer. This port returns `RunSnapshot` plus `idempotent_replay`, converts internal rows before producing the adapter result, and guarantees dispatch wakeup for non-replay resolves that create dispatch.
- Auth verification is framework-independent: Host adapter calls an injected `WaitCallbackAuthenticator`; Service/Web implements credential extraction and authenticator construction.
- Service/Web parser converts raw JSON into typed Host outcomes. It does not import FastAPI/Flask.
- No payload or result body should be logged or echoed in diagnostics.
- No compatibility alias or old callback schema should be added; this is a new contract.

## Implementation Slices

### Slice 1: Host callback contract and adapter

Allowed files/modules:

- `dayu/host/wait_callback.py`
- `dayu/host/__init__.py`
- `tests/host/test_wait_callback.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_import_boundary.py`

Exact changes:

- Add the dataclasses/protocols/status enum listed above with full Chinese docstrings and strict type validation.
- Add `CallbackWaitResolvePort` and `CallbackWaitResolveResult`.
- Add `DefaultWaitCallbackAdapter.resolve_callback(envelope: WaitCallbackCompletionEnvelope) -> WaitCallbackAdapterResult`.
- Add a command-layer adapter/factory that implements `CallbackWaitResolvePort` by calling the existing resolve service and preserving command wakeup semantics. If this needs to live outside `wait_callback.py` to avoid durable imports in the adapter module, keep the port in `wait_callback.py` and place the implementation beside existing command assembly.
- Adapter flow:
  1. Validate non-empty ids, UTC timestamps, digest format, typed outcome.
  2. Call injected authenticator; `WaitCallbackAuthRejected` maps to `AUTH_FAILED` and does not call resolver.
  3. Read wait record by `wait_id` for unknown/stale/status classification. This read may classify a stable pre-existing cancelled/lost wait before resolve; it must not be used to infer resolver-internal race outcomes after a concurrent change.
  4. Verify `payload_digest` against the existing wait resolution digest material `{wait_id, idempotency_key, outcome}`; mismatch maps to `DIGEST_MISMATCH` and does not call resolver. `observed_at` and `completed_at` must not affect this check.
  5. Build `HostCallContext` with actor/source/request id/claims from auth result.
  6. Build `ResolveWaitRequest(source=WaitResolutionSource.CALLBACK, observed_at=envelope.observed_at, ...)`.
  7. Call `CallbackWaitResolvePort.resolve_callback_wait(...)`.
  8. Return `ACCEPTED` or `REPLAYED` using `CallbackWaitResolveResult.idempotent_replay`.
  9. Map `HostApiErrorCode.NOT_FOUND` to `UNKNOWN_WAIT`; `IDEMPOTENCY_CONFLICT` to `IDEMPOTENCY_CONFLICT`.
  10. Do not parse `HostApiError.message`. `INVALID_STATE` from the resolve port maps to `INVALID_WAIT_STATE` unless the adapter already made a stable pre-resolve classification such as `LATE_WAIT_CANCELLED`, `LATE_WAIT_LOST`, or `STALE_CALLBACK`. Concurrent races may safely collapse to `INVALID_WAIT_STATE`. A more precise raced late-state classification requires a future structured subcode/result and is not part of this WU.
  11. Catch non-`HostApiError` unexpected exceptions as `INTERNAL_ERROR` without echoing payload.
- Export only stable public callback symbols from `dayu.host`; do not export implementation internals if not needed.

Invariants:

- Adapter never appends EventLog directly.
- Adapter never updates Run / Attempt / wait record directly.
- Adapter does not import Service/UI/Engine HTTP code or web frameworks.
- `ResolveWaitRequest.source` is always `CALLBACK`.

Non-goals:

- No actual HTTP route.
- No production secret store.
- No durable schema migration.

Tests:

- Successful completed callback resumes through existing wait resolution and creates the same terminal/resume event sequence as direct resolve.
- Accepted callback that creates resume dispatch wakes dispatch exactly once.
- Same callback replay returns `REPLAYED`, appends no new EventLog, and does not wake a second dispatch.
- Same idempotency key with changed outcome returns `IDEMPOTENCY_CONFLICT`.
- Unknown wait returns `UNKNOWN_WAIT`.
- Stable pre-existing cancelled wait late callback returns `LATE_WAIT_CANCELLED`; concurrent races may return `INVALID_WAIT_STATE`.
- Stable pre-existing lost wait late callback returns `LATE_WAIT_LOST`; concurrent races may return `INVALID_WAIT_STATE`.
- Stale callback with existing `deadline_at` exceeded returns `STALE_CALLBACK` without EventLog append.
- Wait with `deadline_at=None` and `expires_at=None` is not rejected as stale.
- Digest mismatch returns `DIGEST_MISMATCH` without resolver call.
- Same callback replay with changed `observed_at` or `completed_at` still returns `REPLAYED` when outcome is unchanged.
- Auth rejection returns `AUTH_FAILED` without resolver call.
- Adapter import boundary has no Service/UI/web framework dependency.
- Host adapter tests do not include HTTP method/content-type/path-body mismatch or malformed JSON shape; those belong to Service mapper tests.

Stop condition:

- If distinct replay detection cannot be obtained without modifying `DefaultHostResolveWaitService` state machine, stop and report. A narrow internal result exposure is acceptable; rewriting state machine is not.

### Slice 2: Service/Web transport mapper and status mapping

Allowed files/modules:

- `dayu/service/wait_callback_endpoint.py`
- `dayu/service/__init__.py` if package export is needed
- `tests/service/test_wait_callback_endpoint.py`
- `tests/service/test_import_boundary.py`
- README files only after reading their update constraints

Exact changes:

- Add a framework-neutral endpoint mapper, not an HTTP server:
  - `WaitCallbackHttpRequest(method: str, path_wait_id: str, headers: tuple[HeaderEntry, ...], body: JsonValue)`
  - `WaitCallbackHttpResponse(status_code: int, body: JsonValue)`
  - `handle_wait_callback_completion(request, adapter) -> WaitCallbackHttpResponse`
- Parse only the exact route form defined above; actual router passes `path_wait_id`.
- Extract auth transport fields into `WaitCallbackAuthInput`; do not verify secrets in parser.
- Convert body `outcome.kind` into existing Host outcome dataclasses.
- Reject method/content-type/path/body wait mismatch as Service `TRANSPORT_REJECTED` and do not call Host adapter.
- Catch JSON parse, dataclass validation, and JSON outcome shape errors as Service `MALFORMED_PAYLOAD` and do not call Host adapter.
- Map `WaitCallbackAdapterResult.status` to the HTTP status table above.
- Map `AUTH_FAILED` deterministically: missing/malformed/expired/invalid credentials return 401; authenticated-but-forbidden credentials return 403.

Invariants:

- Service mapper does not import Host durable modules, EventLog, transaction runner, or state mutation helpers.
- Service mapper does not write durable state.
- Service mapper does not depend on FastAPI/Flask.
- Service response must not echo outcome payload.

Non-goals:

- No concrete Web app route registration.
- No HMAC/token secret backend implementation beyond injected authenticator contract.
- No UI E2E smoke; WU-WAIT-04 depends on #89/#90/#92.

Tests:

- Valid HTTP-like request calls fake adapter with typed envelope and returns 202/200 according to adapter result.
- Path/body wait mismatch returns 400 `transport_rejected` and does not call adapter.
- Missing/invalid content type returns 400 or 415 per mapper decision, with typed body.
- Malformed outcome shape returns 400 `malformed_payload`.
- Completed, failed, cancelled, and lost JSON outcome bodies each map to the expected typed Host outcome.
- Auth failed responses map to 401 for missing/invalid credential and 403 for forbidden credential.
- Adapter statuses map to expected HTTP codes and typed response bodies.
- Response body excludes result payload.

Stop condition:

- If adding a real route requires choosing FastAPI/Flask or changing app assembly outside current repo patterns, stop and leave only framework-neutral mapper.

## Slice Count Rationale

Proposed slice count: 2.

This is within the control-doc default 1-3 slices for small same-semantics cleanup. One slice would mix Host state-governance adapter review with Service transport parsing/status mapping review. Three slices would be mechanical because docs/tests/final validation do not form a separate behavior owner here. Two slices preserve semantic closure:

- Slice 1 proves callback completion enters common Host wait resolution.
- Slice 2 proves endpoint transport concerns stay outside Host core.

## Tests / Validation Commands

Implementation validation should run:

```bash
source .venv/bin/activate
pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py
pytest tests/service/test_wait_callback_endpoint.py tests/service/test_import_boundary.py
pyright
```

Expected assertions:

- No new pyright errors.
- Callback accepted/replayed/conflict behavior matches direct `resolve_wait`.
- Callback accepted path wakes dispatch once when resolve creates dispatch; replay path does not wake dispatch again.
- Pre-resolve failures do not append EventLog or call resolver.
- `observed_at` / `completed_at` changes do not affect replay conflict when outcome is unchanged.
- Service mapper covers completed/failed/cancelled/lost outcome JSON.
- No-deadline waits are not stale; deadline-exceeded callbacks are stale.
- Service mapper has no durable write path and no HTTP framework import.

## Docs / README Decision

Because implementation will touch `dayu/host/` and likely `dayu/service/`, implementation must first read:

- `dayu/host/README.md`
- `dayu/service/README.md`

Update them only if their Agent update constraints say callback adapter / Service endpoint mapper belongs to their reader scope.

Root `README.md` should not be updated unless a concrete user-visible Web/CLI command or deployed route is exposed. This plan only adds framework-neutral Service mapper and Host contract, so root README is likely not in scope.

`docs/host/design.md` should not be changed in this work unit unless implementation reveals the design source is insufficient. Current design source plus issue #89 are sufficient for code-generation-ready implementation.

## Risks / Open Questions

- Stale callback semantics currently depend on existing `deadline_at`; `expires_at` is schema-reserved and currently unpopulated. Tests must seed `deadline_at` explicitly for stale rejection; do not invent a new timeout lifecycle in this WU.
- Auth verification is only a typed protocol in Host. Real bearer/HMAC secret storage remains Service/Web deployment responsibility.
- HTTP route registration is intentionally not included because no current Web framework boundary is present in the inspected code. A real route can wrap the mapper later without changing Host core.
- Mapping `LATE_WAIT_CANCELLED` / `LATE_WAIT_LOST` is stable only when the pre-resolve read sees an already-cancelled/lost wait. Races during resolve may return `INVALID_WAIT_STATE`, which is acceptable unless a future structured subcode is added.

Blocking open questions: none.

## Why This Is Not Over-designed

The plan adds only the missing boundary that issue #89 requires: typed callback envelope/auth/result mapping into existing `resolve_wait`. It does not add a new queue, scheduler, callback store, retry engine, webhook registry, durable schema, or wait lifecycle. The Service mapper is framework-neutral because the repository currently has no Web route owner in scope, and putting HTTP framework code in Host would violate the design source.

The only new abstraction with a protocol is auth, because Host core cannot know deployment-specific bearer/HMAC verification but still needs a typed, testable authentication decision before resolving a wait.

## Completion Report Format

Implementation closeout should report:

- Artifact path: `docs/host/wu-wait-01-callback-endpoint-auth-replay-plan.md`
- Slice implemented and files changed.
- Callback statuses covered by tests.
- Validation commands run and results.
- README/doc decision and any doc files changed.
- Residual risks or deferred owners, especially anything that belongs to #90 or #92.

## Plan-gate Validation Performed

Read / inspection commands performed for this plan gate:

- `rg --files docs/host docs/engine dayu/host dayu/service tests/host tests/service`
- `sed -n '1,260p' docs/host/design.md`
- `sed -n '1,260p' docs/engine/design.md`
- `sed -n '1,260p' docs/host/issues-implementation-control.md`
- `sed -n '1,260p' dayu/host/api.py`
- `rg -n "WaitResolution|ResolveWait|wait|CALLBACK|idempotency|digest|stale|late|cancel" dayu/host/api.py`
- `sed -n '1,760p' dayu/host/waiting.py`
- `sed -n '1,760p' dayu/host/wait_adapter.py`
- `sed -n '1,860p' tests/host/test_resolve_wait_command.py`
- `gh issue view 89 --repo noho/dayu-agent-r --json number,title,state,body,labels,comments`
- `rg -n "resolve_wait|ResolveWait|WaitResolutionSource|WaitAdapter|callback|Callback|FastAPI|Flask|route|HTTP|endpoint" dayu/host dayu/service tests/host tests/service`
- `sed -n '1,320p' tests/host/test_wait_cancel_late_result.py`

No code tests were required or run for this plan gate.
