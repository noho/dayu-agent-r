# WU-ENG-02-R1 Provider Debugging Correlation Default Enablement And Fallback Diagnostics Plan

## 1. Goal / Motivation / Success Signal

### Goal

WU-ENG-02-R1 修复 #63 reopen 后确认的端到端缺口：真实 Service / CLI 默认路径必须默认启用 OpenAI-compatible client correlation，使普通 Agent -> Runner call 默认发送合法 `X-Client-Request-Id`，并在 provider 未返回 `provider_request_id` 时仍能通过既有日志、诊断、Tool Trace 与 terminal diagnostic 找到可报给厂商的 fallback `client_correlation_id`。

### Motivation

PR #114 已完成 lower-level mechanism，但默认 product path 没有启用。`dayu-cli prompt` 默认 scene 使用 mimo OpenAI-compatible 模型时，如果 provider response 没有当前采集的 `x-request-id`，就既没有 provider-native request id，也没有已发送给 provider 的 client correlation id，无法满足 #63 “trace 发现疑似 provider/model bug 时可给厂商请求级关联 ID”的验收目标。

### Success Signal

- `compose_open_host_options(...)` / `_runner_spec_from_model(...)` 产生的普通与 compactor `RunnerSpec.client_correlation_policy` 默认是 `ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID`。
- OpenAI-compatible Runner 在 policy enabled 且 `request_identity` 非空时继续发送现有格式 `X-Client-Request-Id`；policy disabled 的底层 contract tests 保留。
- 不新增配置项、profile switch、provider 字符串分支、`safety_identifier`、fake `user_id` 或 UI / Service 用户概念。
- 既有 Python runner `runner.http.response` 日志行必须在同一 log site、同一 log level、同一行携带 `client_correlation_id`；不得新增专用日志事件、额外日志行或提高日志等级。
- Host live watcher 与 outbox fallback 的 terminal public projection 必须在 `provider_request_id=None` 且 `client_correlation_id` 存在时展示同格式 fallback diagnostic suffix；不得修改 durable terminal payload `message` 或 payload digest。
- Tool Trace hot summary 与 cold JSONL 在 `provider_request_id=None` 但 `client_correlation_id` 存在时仍保留 fallback id。
- Provider request id 提取保持当前 `x-request-id` 单一路径；不得把 `x-trace-id`、`x-correlation-id`、`cf-ray` 或其它 tracing / infrastructure header 映射为 `provider_request_id`。若实现证据显示需要 header diagnostic，只能记录有界安全 header-name presence，不输出 header values，且不作为本 WU 必需实现项。

## 2. Non-Goals / Scope Boundary

- 不新增用户配置项或 execution profile switch。
- 不把 `session_id`、Service 用户身份、UI 用户身份或内部治理 id 投影成 provider end-user / safety governance field。
- 不改变已接受的 `RunnerRequestIdentity` schema、identity derivation 或 `dayu-` + full SHA-256 lowercase hex 格式，除非实现阶段发现 header contract 无法满足；当前代码证据未发现该问题。
- 不实现 Tool Trace analyzer；WU-OBS-00 / issue #70 负责。
- 不处理 usage observation 是否需要 correlation fields；WU-OBS-00B / issue #119 负责。
- 不实现 native Anthropic / Claude Code gateway adapter-specific request id semantics。
- 不新增日志点、不新增日志行、不提高日志等级；只能让既有日志 message、terminal projection、public event / outbox terminal view 或 Tool Trace projection 携带同源字段。
- 本 plan gate 只写本 artifact，不修改 `docs/host/issues-implementation-control.md`、生产代码、README、commit、push、PR。

## 3. Design Document Alignment

- Host design 固定分层为 `UI -> Service -> Host -> Engine`。本 WU 由 Service composition root 映射 typed RunnerSpec，Host 不解释 config / provider string，Engine 只消费 typed spec。
- Engine design 的 `ClientCorrelationPolicy` 是 provider-protocol-specific outbound mapping policy，不是 provider-name branch；OpenAI-compatible Runner 只在 `OPENAI_X_CLIENT_REQUEST_ID` 且 request identity 非空时发送 `X-Client-Request-Id`。
- Engine design 明确 `client_correlation_id` 只用于本地诊断关联和 provider adapter per-call mapping，不表达 Host lifecycle governance，也不是 provider end-user field。
- Host design 明确 projection、outbox、tool trace、diagnostic 都是 committed EventLog 的派生视图，不是 truth。本 WU 只能复用这些派生边界暴露已存在字段，不新增 Host truth。
- README 约束与设计真源一致：Engine / Runner 日志不得输出完整 prompt、headers、API key 或 provider payload；本 WU 的 header diagnostic 必须只输出 bounded safe names / presence，不输出 header values。

## 4. First-Principles Judgment And Direct Code Evidence

### Judgment

动机成立，严重性评估成立。#63 的核心目标不是“底层能够发送 header”，而是“真实默认 product path 能让厂商排障拿到请求级关联 ID”。当前默认 Service assembly 将 policy 固定为 disabled，导致底层能力在 CLI / Service 默认路径不可达。

这不是配置缺失问题，不应新增配置项。default product path 已选择 OpenAI-compatible Runner，`RunnerSpec` 已有 typed policy 字段；最小正确修复是让 Service assembly 默认选择该 typed policy。

### Direct Evidence

- GitHub issue #63 当前为 Open；reopen comment 指出 PR #114 已有底层能力，但 `dayu/service/host_assembly.py` 把 `RunnerSpec.client_correlation_policy` 固定为 `ClientCorrelationPolicy.DISABLED`，导致 `dayu-cli prompt` 默认不会向 mimo 发送 `X-Client-Request-Id`。
- `dayu/service/host_assembly.py:1087-1115`：`_runner_spec_from_model(...)` 从 `ModelConfig` 构造 `RunnerSpec`，第 1107 行硬编码 `client_correlation_policy=ClientCorrelationPolicy.DISABLED`。
- `dayu/engine/contracts/runner_spec.py:263-288`：`RunnerSpec` 已有 required typed `client_correlation_policy` 字段。
- `dayu/engine/contracts/runner_spec.py:307-308`：policy 开启时静态 headers 不得包含 `X-Client-Request-Id`。
- `dayu/engine/runners/openai/runner.py:149-185`：OpenAI-compatible request header helper 已按 typed policy 映射 `X-Client-Request-Id`，无 provider 字符串分支。
- `dayu/engine/runners/openai/runner.py:114-129` 与 `600-613`：provider request id 当前仅从 response headers 的 `x-request-id` 提取，并在 existing debug log `runner.http.response ... provider_request_id=%s` 输出。
- `dayu/config/models.json` 的 mimo default entries 使用 `runner_kind=openai_compatible`，headers 只有 Authorization / Content-Type；仓库配置未发现静态 `X-Client-Request-Id` 冲突。
- `dayu/host/engine_ingest.py` 已将 failed terminal payload 写入 `provider_request_id` 与 `client_correlation_id`，例如 `_run_failed_plan(...)`。
- `dayu/host/tool_trace.py:1088-1096` 与 `1168-1185`：cold JSONL 和 hot `trace_summary` 已有 `client_correlation_id` 字段。
- `dayu/host/tool_trace.py:900-915`：diagnostic projection 当前在 `ENGINE_EVENT_DIAGNOSTIC` 且 `provider_request_id is None` 时直接 `return None`，会丢弃“provider id 缺失但 client fallback 存在”的 diagnostic trace。
- `dayu/host/api.py:3004-3036`、`dayu/host/read_api.py:965-984`、`dayu/host/outbox.py:269-280`、`dayu/service/entrypoint_runtime.py:321-344`：当前 live / outbox / entrypoint terminal view 只有 `error_message`，未直接暴露 `provider_request_id` / `client_correlation_id` 字段。terminal diagnostic 可见性需要在既有 terminal result / error display 边界内补充字段，或在 public event/outbox contract 中有界扩展。

## 5. Affected Files / Modules

Implementation agent 允许触及以下文件；若必须扩大范围，需要先在 implementation report 中说明直接证据：

- `dayu/service/host_assembly.py`
- `tests/service/test_host_assembly.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- `dayu/engine/runners/openai/runner.py`
- `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `tests/engine/runners/openai/test_runner_diagnostics.py`
- `dayu/host/tool_trace.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`
- `dayu/host/read_api.py`
- `dayu/host/outbox.py`
- a shared private Host projection helper module or existing Host projection utility
- affected tests under `tests/host/test_public_run_api.py`, `tests/host/test_public_outbox_api.py`, `tests/service/test_entrypoint_runtime.py`, `tests/service/test_entrypoint_runtime_prompt_path.py`, `tests/cli/test_prompt_command.py`
- README files only if docs decision below says update is required after implementation.

## 6. Contract / Schema / State-Machine / Public Interface Changes

### Required

- No durable schema migration is required for default enablement or Tool Trace fallback retention if implementation reuses existing EventLog payload fields and existing Tool Trace hot/cold shape.
- No Engine public contract change is required for default enablement; `RunnerSpec.client_correlation_policy` and `ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID` already exist.
- Service assembly behavior changes: Service-created `RunnerSpec` defaults to enabled OpenAI-compatible client correlation. This is behavior, not a new config schema.

### Required Public Projection Change For Terminal Diagnostic

Implementation must use the minimal public-contract path:

- Keep `HostEvent`, `OutboxTerminalItem`, and `EntrypointRunTerminalResult` public dataclass shapes unchanged.
- Append a bounded diagnostic suffix to existing failed terminal `error_message` only at Host public projection boundaries:
  - live watcher path: `dayu/host/read_api.py` failed terminal `HostEvent` projection.
  - outbox fallback path: `dayu/host/outbox.py` terminal item projection.
- The suffix source is the already durable terminal payload fields `provider_request_id` and `client_correlation_id`.
- Do not append the suffix during Engine ingest, EventLog append, payload-store write, or any path that mutates durable terminal payload `message`; payload digest must remain unchanged.
- Both projection paths must call the same module-level private Host projection helper for suffix formatting, so `provider_request_id=None` plus the same `client_correlation_id` renders identically in live and outbox fallback views.

Do not add optional correlation fields to public dataclasses, a new Host event type, EventLog canonical fact, outbox table column, Tool Trace hot row column, CLI log line, or logger call just for `client_correlation_id`.

### State Machine

No Run / Attempt state machine transition changes are intended. All changes must be read/projection/output behavior or Service assembly input behavior.

## 7. Implementation Decisions

### Decision 1: Default Enablement Belongs In Service Assembly

Change `_runner_spec_from_model(...)` so Service-created `RunnerSpec` uses `ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID`.

Rationale:

- It is the single mapping point from runtime model config to Engine typed `RunnerSpec` for normal Service / CLI assembly.
- It preserves typed provider policy boundary.
- It avoids adding config surface and avoids provider string governance branches.

Implementation notes:

- Both ordinary baseline and compactor baseline currently flow through `_runner_spec_from_model(...)`; enabling both is acceptable because compactor calls are still OpenAI-compatible Runner calls and benefit from fallback diagnostics.
- Existing direct tests or fakes that intentionally construct `RunnerSpec(... DISABLED ...)` can remain unchanged; this WU changes product assembly default, not the low-level disabled policy capability.
- If a workspace override has static `X-Client-Request-Id` in model headers, existing `RunnerSpec.__post_init__` must fail fast. Do not silently drop or override static header.

### Decision 2: No Provider String Branches

Do not branch on `model.provider == "mimo"` / `"openai"` / `"deepseek"` in Service, Host, or Agent. The protocol decision is the typed policy. Future non-OpenAI adapters need their own typed policy under their own issue.

### Decision 3: No End-User Governance Field

Do not add `safety_identifier`, `user_id`, `session_id`, UI user id, or Service actor id to provider payload. The existing `RunnerRequestIdentity.client_correlation_id` is a debugging correlation id only.

### Decision 4: Existing Runner Log Site Must Add Client Correlation Context

Runner already logs one `runner.http.response ... provider_request_id=%s` debug line. Extend that existing line to include `client_correlation_id=%s` on the same line. This reuses the existing log site and level. Do not add a second log line.

The value is available from `request_identity` in the caller and must be passed into the private attempt method, likely by adding a `client_correlation_id: str | None` parameter to `_do_attempt(...)`. This is an intra-class private signature change, not a public contract change.

Do not add a new log point, do not add an extra log line, and do not change the log level. Do not broaden Agent / Engine log churn. The mandatory acceptance target is the existing Runner response log plus terminal / Tool Trace diagnostics.

### Decision 5: Provider Request Id Header Extraction Must Stay Bounded

Current extraction only checks `x-request-id`; keep that behavior. This WU has no direct evidence that any other response header is a provider-native request id for the default product path.

Do not map `x-trace-id`, `x-correlation-id`, `cf-ray`, W3C trace context headers, proxy headers, CDN headers, or other infrastructure/tracing headers into `provider_request_id`. Returning `None` plus a visible `client_correlation_id` fallback is safer than persisting a misleading provider request id.

If implementation uncovers direct provider evidence requiring response header diagnostics, the only allowed diagnostic is bounded safe header-name presence with no header values. That diagnostic is not required for this WU and must not delay the minimal fix.

### Decision 6: Tool Trace Must Preserve Client Fallback Without Provider Id

Update `_extract_diagnostic_trace(...)` so `ENGINE_EVENT_DIAGNOSTIC` is skipped only when both `provider_request_id` and `client_correlation_id` are absent and there is no raw payload ref. If `client_correlation_id` exists, project the row even when `provider_request_id is None`.

Do not put `client_correlation_id` into `provider_request_id` hot column. It must remain a separate field in `trace_summary` and cold JSONL `client_correlation_id`.

`diagnostic_refs` may remain raw payload ref / provider request id based. Current Tool Trace hot row validation permits `diagnostic_ref=None`; keep `None` when there is no raw payload ref or provider request id. Do not introduce an `event_id` fallback, do not fake `diagnostic_ref`, and do not put `client_correlation_id` into `provider_request_id`.

### Decision 7: Terminal Diagnostic Visibility Reuses Existing Terminal Boundary

Provider failure terminal payload already contains `provider_request_id` and `client_correlation_id`. Implementation must make that visible in prompt / interactive failed terminal output without new logs.

Preferred output shape when `provider_request_id is None` and `client_correlation_id` exists:

```text
<existing error message>
client_correlation_id=<id>
```

If `provider_request_id` exists, output may include both ids. Keep the text bounded and single terminal message. Do not add internal event ids, payload refs, digests, headers, or Host state-machine terms to end-user terminal output. Do not extend public dataclasses for this WU.

## 8. Small Implementation Slices

### Slice 1: Service Default Policy Enablement

Files:

- `dayu/service/host_assembly.py`
- `tests/service/test_host_assembly.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`

Steps:

1. Before changing the default, run the current baseline assembly tests listed for this slice and record whether they pass.
2. Change `_runner_spec_from_model(...)` to set `client_correlation_policy=ClientCorrelationPolicy.OPENAI_X_CLIENT_REQUEST_ID`.
3. Add or update tests asserting ordinary baseline and compactor baseline runner specs from `compose_open_host_options(...)` use `OPENAI_X_CLIENT_REQUEST_ID`.
4. Add direct `_runner_spec_from_model(...)` test for a local/Ollama-style model if it still uses OpenAI-compatible Runner; default should be enabled there too unless static header conflict fails. Do not special-case local provider strings.
5. Add a negative test with static `X-Client-Request-Id` in headers through a minimal `ModelConfig` or existing config fixture, expecting `ValueError` from `RunnerSpec` validation.
6. If tests fail after the default changes, classify each failure before editing:
   - expected behavior change: update assertions that assumed `DISABLED` Service assembly default.
   - regression: fix the implementation rather than weakening tests.

Expected result: Service / CLI default assembly no longer disables client correlation.

### Slice 2: Existing Runner Diagnostics And Bounded Header Extraction

Files:

- `dayu/engine/runners/openai/runner.py`
- OpenAI runner tests listed above.

Steps:

1. Keep `_extract_provider_request_id(...)` limited to `x-request-id`; preserve case-insensitive extraction, trimming, and empty value ignore behavior.
2. Add or update tests confirming `x-trace-id`, `x-correlation-id`, `cf-ray`, and other infrastructure/tracing headers are not extracted as `provider_request_id`.
3. Ensure no test logs or persisted payloads include full response header values except the extracted `x-request-id` itself.
4. Pass `client_correlation_id` from `request_identity` into the private attempt method, likely `_do_attempt(...)`.
5. Extend the existing `runner.http.response` debug message to include `client_correlation_id` on the same line and same log level.
6. Add a log capture test for the existing `runner.http.response` site showing the same log line contains `provider_request_id` and `client_correlation_id`.

Expected result: provider request id extraction remains current `x-request-id` only, Python runner logs show `client_correlation_id` at the existing response log site, and no speculative header mapping is introduced.

### Slice 3: Tool Trace Fallback Preservation

Files:

- `dayu/host/tool_trace.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_tool_trace_queries.py`

Steps:

1. Change diagnostic extraction skip condition so `client_correlation_id` alone is enough to keep the trace row.
2. Add fixture for `EventClass.DIAGNOSTIC`, `event_type="PROVIDER_PROTOCOL_ERROR"` or `ENGINE_EVENT_DIAGNOSTIC`, `provider_request_id=None`, `client_correlation_id="client-fallback"`, no raw payload ref if supported.
3. Assert hot row has `provider_request_id is None`, `diagnostic_ref is None` when no raw payload ref exists, `trace_summary["client_correlation_id"] == "client-fallback"`, and cold JSONL top-level `client_correlation_id == "client-fallback"`.
4. Assert provider-request-id query does not incorrectly return this row under a fake provider id.
5. If there are multiple diagnostic extraction paths with the same `provider_request_id is None` guard, update and test each path.

Expected result: Tool Trace hot / cold projection can carry fallback client id even when provider id is absent.

### Slice 4: Terminal Diagnostic Visibility

Files:

- `dayu/host/read_api.py`
- `dayu/host/outbox.py`
- a shared private Host projection helper module or existing Host projection utility
- service / CLI tests only if exact output assertions need updating; CLI renderer should not need new parsing logic
- related host / service / CLI tests.

Steps:

1. Add a module-level private helper in the Host projection layer that formats the bounded suffix from `provider_request_id: str | None` and `client_correlation_id: str | None`.
2. The helper must return an empty suffix when both ids are absent.
3. The helper must include `client_correlation_id=<id>` when `provider_request_id is None` and `client_correlation_id` exists.
4. The helper may include both `provider_request_id=<id>` and `client_correlation_id=<id>` when both exist.
5. Call the helper from the live failed terminal projection in `dayu/host/read_api.py` and append the suffix to public `HostEvent.error_message`.
6. Call the same helper from the outbox terminal item projection in `dayu/host/outbox.py` and append the suffix to public `OutboxTerminalItem.error_message`.
7. Do not change durable terminal payload `message`, payload digest, EventLog facts, public dataclass fields, or Service / CLI renderer contracts.
8. Add tests covering `provider_request_id=None` and `client_correlation_id` present for both live watcher and outbox fallback, and assert the rendered suffix is identical across both paths.
9. Add a test or assertion proving the underlying terminal payload `message` remains unchanged while projected `error_message` gains the suffix.

Expected result: CLI failed terminal output gives a vendor-reportable fallback id without adding logging.

### Slice 5: README / Docs Sync

Files only if required by trigger decision:

- `dayu/service/README.md`
- `dayu/engine/README.md`
- `dayu/host/README.md`
- `README.md`
- `tests/README.md`

Steps:

1. Update only current-code facts after implementation passes.
2. Do not write work unit history or future plan into README.

Expected result: docs reflect current default behavior and diagnostics only where their stated reader boundary requires it.

## 9. Tests / Validation Commands And Expected Assertions

Implementation gate must run from activated venv:

```bash
source .venv/bin/activate
pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q
pytest tests/engine/runners/openai/test_request_identity.py tests/engine/runners/openai/test_streaming_capability_and_content_type.py tests/engine/runners/openai/test_http_error_event.py tests/engine/runners/openai/test_runner_diagnostics.py -q
pytest tests/host/test_tool_trace_projection.py tests/host/test_tool_trace_queries.py -q
pytest tests/service/test_entrypoint_runtime.py tests/service/test_entrypoint_runtime_prompt_path.py tests/cli/test_prompt_command.py -q
pyright
git diff --check
```

Expected assertions:

- Service assembly default ordinary and compactor `RunnerSpec.client_correlation_policy` are `OPENAI_X_CLIENT_REQUEST_ID`.
- OpenAI runner still sends `X-Client-Request-Id` only when policy enabled and identity exists.
- Static `X-Client-Request-Id` header with enabled policy fails fast.
- Provider request id extraction still uses `x-request-id` only; infrastructure/tracing headers such as `x-trace-id`, `x-correlation-id`, and `cf-ray` are not persisted as `provider_request_id`.
- Existing `runner.http.response` log line contains `client_correlation_id` on the same log line and same log level.
- No test asserts use of `safety_identifier`, `user_id`, or Service/UI user identity.
- `provider_request_id=None` plus `client_correlation_id` survives Host terminal payload -> Tool Trace hot summary -> cold JSONL.
- Live watcher and outbox fallback projected terminal `error_message` contain the same fallback `client_correlation_id` suffix when provider id is missing.
- Durable terminal payload `message` and payload digest remain unchanged when public projections add the suffix.
- Existing disabled policy tests still pass.

Plan gate validation:

```bash
git diff --check
```

No pytest is required for this plan gate because only this Markdown artifact is added.

## 10. Docs / README Decision

Plan gate writes no README.

Implementation gate must check:

- `dayu/service/README.md`: likely update, because Service assembly default now materially says it maps model config to `RunnerSpec` with default client correlation policy.
- `dayu/engine/README.md`: update only if runner diagnostic wording changes current Engine behavior. It already documents client correlation policy and OpenAI-compatible header behavior; provider request id extraction remains `x-request-id` only.
- `dayu/host/README.md`: update if terminal/outbox public projection suffix or Tool Trace fallback behavior changes documented developer-facing contract.
- root `README.md`: update only if user-visible CLI failed terminal diagnostics or troubleshooting instructions change. Do not expose internal Host/Engine details.
- `tests/README.md`: update if new tests materially change described coverage for Service assembly default, terminal diagnostics, or Tool Trace correlation.

## 11. Risks / Open Questions

- Terminal diagnostic visibility is the only likely public interface risk. The accepted path intentionally uses an error-message suffix at Host public projection boundaries to avoid public dataclass changes; tests must guard that durable payload `message` and payload digest do not change.
- Provider request id header extraction beyond `x-request-id` is speculative and out of scope for this WU. If future evidence appears, handle it in a separate issue or a separately justified change.
- Tool Trace diagnostic rows with `diagnostic_ref=None` are currently valid. Tests should lock that a row with no provider id and no raw payload ref can still preserve `client_correlation_id`.
- Default enabling applies to all Service-created OpenAI-compatible models, including local OpenAI-compatible endpoints. This is intentional unless static header conflict or provider contract evidence proves unsafe. Current code/config evidence shows no blocker.
- If a provider rejects unknown `X-Client-Request-Id`, implementation must stop and report blocker with evidence. Current issue/design assume OpenAI-compatible providers accept the debugging header.

## 12. Stop Conditions

Stop implementation and write blocker if any of the following is proven:

- Default enablement conflicts with provider contract or causes default configured provider to reject requests.
- Static header conflict cannot fail fast without adding compatibility behavior.
- No existing terminal/log/Tool Trace boundary can expose `client_correlation_id` without adding new log lines, new event types, or leaking sensitive data.
- Existing `x-request-id` provider response header access cannot be preserved without leaking sensitive header values.

No stop condition was found during this plan gate.

## 13. Completion Report Format

Implementation agent final report must use:

```text
artifact path: docs/host/host-issues/wu-eng-02-r1-provider-debugging-correlation-plan.md
plan status: ready
direct evidence summary:
- ...
proposed slices:
- Slice 1 ...
- Slice 2 ...
required validation:
- ...
docs decision:
- ...
residual risks / open questions:
- ...
```

If a stop condition is hit, use `plan status: blocked` and include the direct evidence that blocked implementation.

## 14. Why This Is Not Over-Designed

- It uses the existing `ClientCorrelationPolicy` typed contract instead of adding config.
- It changes the single Service assembly default rather than scattering provider branches.
- It reuses existing `RunnerRequestIdentity`, Runner header mapping, Host terminal payloads, Tool Trace hot/cold projection, outbox/live terminal display, and logging sites.
- It avoids new EventLog facts, durable schema, user identity concepts, analyzer implementation, and provider-specific adapter semantics outside #63.
- The slices are each independently testable and map to existing ownership boundaries: Service assembly, Engine/OpenAI runner, Host Tool Trace, and CLI terminal diagnostics.
