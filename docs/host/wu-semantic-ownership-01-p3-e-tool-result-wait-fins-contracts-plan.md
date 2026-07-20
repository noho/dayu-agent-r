# WU-SEMANTIC-OWNERSHIP-01 P3-E Tool Result / Wait / Fins Contracts Plan

## 状态

`ready-for-plan-review`

本计划只覆盖 P3-E，不实施、不 review、不 fix、不 commit、不 push、不修改总控文档。当前工作树中 controller-owned `docs/host/issues-implementation-control.md` 与 `docs/reviews/wu-semantic-ownership-01-p3-e-goal-confirmation.md` 不属于本计划修改范围；现有 unrelated `docs/cli_ci*` 与 `docs/reviews/code-review-20260710-*` 不纳入本 WU。

## Goal / Motivation / Success Signal

目标是把工具结果 envelope 判别字段、accepted tool result status、wait callback provider status ref、Fins direct stream terminal result，以及 ToolRuntime 治理诊断与 LLM-facing hint 的边界收回到语义 owner。

第一性原理判断：这些不是展示格式问题，而是跨层协议事实。`ok` 判别字段决定 Engine / Host / ToolRuntime 对结果 union 的分支；accepted status 决定 Memory / evidence / compact / read model 对工具事实的分类；provider status ref 是 Host wait adapter 能否重读 provider 状态的结构化身份；Fins direct `RESULT` 是 direct stream 的唯一业务终态；ToolRuntime 的治理 reason / diagnostic refs 不能伪装成 LLM 可执行恢复提示。

成功信号：

- `ToolResultSuccess(ok=False, ...)` 与 `ToolResultFailure(ok=True, ...)` 在构造时 fail closed。
- generic wait callback endpoint 拒绝裸字符串 `provider_status_ref`；没有 owner resolver 时只接受 typed object shape。
- accepted result projection 不再从 `raw_tool_outcome.kind` 或 `raw_tool_outcome.result.ok` 重建 status；缺 typed status 时给出封闭 unknown / lost 读模型语义和诊断，不猜业务事实。
- Fins direct runtime 与 Service 对 missing / duplicate `RESULT` 抛 typed protocol error，不制造 failure business result、不静默吞重复终态。
- ToolRuntime 不再把治理 reason code、accept rejection reason 或 diagnostic refs 拼入 `ToolResultFailure.hint`；诊断 refs 仍保留在 Tool Trace / failure metadata / accept diagnostics 等 owner-owned diagnostic fields。
- 受影响测试、pyright、`git diff --check` 通过；README 按触发规则更新或记录 no-op。

## Non-goals / Scope Boundary

- 不重新设计 Host wait-resume 状态机，不引入 callback resolver 框架；本轮没有 owner-provided resolver，因此裸字符串 provider status ref 直接拒绝。
- 不新增跨进程 Fins direct durable job ledger，不修改 Fins 下载 / 预处理 / 上传业务语义。
- 不修改 CLI 展示、read view、outbox、Memory 或 LLM renderer 来掩盖上游 contract 缺口。
- 不扩大到 P3-F 的 Fins source document / blob / citation ownership。
- 不扩大到 P3-J 的 EventLog taxonomy、全局 lifecycle hardening 或 DDL closed-set cleanup。
- 不为旧 payload / 旧 callback body 增加兼容读取路径；测试跟随新 contract 迁移。

## Design Alignment

- `AGENTS.md` 要求修复落在 owner boundary 或直接上游输入校验处。本计划分别落在 `dayu.contracts.tool_result`、Host accepted projection / ToolRuntime、Service callback mapper 的 transport-to-typed 边界、Fins direct stream protocol。
- `docs/host/design.md` 明确 Host 是 tool governance、accept barrier、projection、wait-resume 的治理真源；projection 和下游消费者不得反向成为 EventLog / accepted result truth。
- `docs/engine/design.md` 明确 Engine 只消费 typed tool outcome 并把 `ToolResultFailure.hint` 投影给 LLM；因此治理码进入 hint 是 LLM-facing contract 问题，不应在 Engine 下游特殊处理。
- `docs/host/issues-implementation-control.md` 当前 next gate 是 P3-E plan；P3-E goal confirmation 已确认无 blocking open question。

当前方案没有过度设计：不新建抽象注册表、不引入 resolver SPI、不改 durable schema、不改 Engine message schema，只移除已确认的 fallback / fabricated truth，并在现有 typed contract 上加最小 invariant 与协议错误。

## Plan Fix Disposition

本计划已吸收 plan-fix gate 接受项 `P3-E-PF-01` 到 `P3-E-PF-06`：

- `P3-E-PF-01`: S1 明确审计所有 `last_error_code` 路径，禁止把它留在 LLM-facing `hint`，但必须在 `message`、owner-owned diagnostics、failure metadata 或 Tool Trace 中保留诊断语义。
- `P3-E-PF-02`: S1 明确在引用扫描后删除 `_hint_with_diagnostic_refs`、hint 分隔/key 常量，以及 hint 清理后无引用的 accept reason 常量。
- `P3-E-PF-03`: S2 明确区分 payload unavailable -> `LOST` 与 payload available but typed status missing -> `UNKNOWN`，并要求审计 `_result_payload(...)` 所有 `None` 出口和测试 unavailable payload。
- `P3-E-PF-04`: S2 增加 `UNKNOWN` status 的 read model、run input / evidence material、memory、compact material 消费者覆盖或显式 no-op 证据。
- `P3-E-PF-05`: S3 增加 `_DirectStreamProducerDone` producer lifecycle 审计、正常/异常/终态路径 sentinel 校验和 no-hang 验证；若发现 hang，只在 Fins runtime owner 处停下修复，不加下游 timeout hack。
- `P3-E-PF-06`: S3 明确 Fins-owned `FinsDirectStreamProtocolError` 是 direct stream protocol violation 的唯一真源，并将 CLI-local `FinsDirectStreamContractViolation` 删除或替换纳入范围。

## Source Finding Disposition

| Finding | Disposition | Evidence | Planned handling |
|---|---:|---|---|
| `ToolResultSuccess.ok` / `ToolResultFailure.ok` 只靠 `Literal`，运行时可构造错误判别字段。 | accepted | `dayu/contracts/tool_result.py` 中 `ToolResultSuccess` 无 `__post_init__`，`ToolResultFailure.__post_init__` 只校验 `error/message/hint`。 | 在 contract owner 添加 runtime invariant tests 与构造校验。 |
| generic callback endpoint 接受裸字符串 `provider_status_ref` 并伪造 `WaitAdapterKey("callback")`。 | accepted | `dayu/service/wait_callback_endpoint.py` `_provider_status_ref_from_json` 的 string branch 直接构造 `WaitProviderStatusRef(adapter_key=WaitAdapterKey("callback"), ...)`；未发现 resolver。 | 删除 string branch；仅接受 object typed shape；新增 malformed payload 测试。 |
| accepted result projection 从 raw outcome `kind` / `result.ok` fallback 重建 status。 | accepted | `dayu/host/accepted_result_projection.py` `_accepted_status` 调用 `_status_from_raw_outcome`；测试 `test_projection_maps_raw_result_ok_false_and_extracts_details` 当前断言 fallback 为 failed。 | 删除 raw status fallback；缺 typed status 返回 `UNKNOWN` 并记录诊断；保留 result details extraction。 |
| Fins runtime direct stream 静默吞 duplicate `RESULT`，missing `RESULT` 制造 failure result。 | accepted | `dayu/fins/ingestion_runtime.py` `_run_direct_stream` 对第二个 `RESULT` `continue`，结束未见 result 时 yield `_direct_missing_result_event(...)`。 | Fins protocol owner 抛 typed `FinsDirectStreamProtocolError`；删除 synthetic missing result event path。 |
| Service Fins direct helper 对 duplicate fail closed 但 missing `RESULT` 制造 failure result。 | accepted | `dayu/service/fins_direct.py` `_ensure_result_event` duplicate raise `FinsDirectUsageError`，missing yield `_missing_result_event(...)`；Service README 也记录该旧语义。 | Service 只校验/透传 direct protocol，missing/duplicate 均抛同一 typed protocol error；删除 synthetic missing result helper。 |
| governance reason / diagnostic refs 仍进入 LLM-facing `hint`。 | accepted | `dayu/host/tool_runtime.py` `_truncation_failure(... hint=reason_code)`、`_governed_failure_outcome(... hint=policy_decision.reason_code)`、`_accept_failure_outcome(... hint=accept_rejected:...)`、`_awaiting_accept_failure_outcome(... diagnostic_refs=...)`；`dayu/engine/agent.py` 会把 `ToolResultFailure.hint` 投影到 tool message。 | 从 ToolRuntime synthetic governed / accept / truncation failure 的 LLM-facing hint 移除治理码和 refs；诊断仍保留在 Tool Trace / failure metadata / accept diagnostics。 |

Counts: accepted 6, rejected 0, deferred 0, needs-more-evidence 0.

## Owner Boundary And Propagation Path

- Tool result envelope:
  `ToolResultSuccess` / `ToolResultFailure` construction in `dayu.contracts.tool_result` -> ToolRuntime / tools produce `ToolExecutionOutcome` -> Engine projects accepted failure/success to LLM tool message -> Host ingest / trace / memory consume accepted facts. The discriminator invariant must be enforced at contract construction, before Engine or Host branches on it.
- ToolRuntime governance hint:
  Host ToolRuntime produces governed / truncation / accept-failure `ToolFailedOutcome` -> Engine `_project_tool_failure_for_llm` exposes `hint` to LLM -> Host trace stores failure metadata separately. Governance reason and diagnostic refs belong to ToolRuntime diagnostics / failure metadata, not LLM-facing hint.
- Accepted result status:
  Host accept barrier writes typed `tool_fact_kind` / `resolution_kind` durable payload -> `accepted_result_projection` reads typed status -> evidence / memory / compact / read consumers use projection. Raw outcome remains result detail material only; it must not reconstruct status truth.
- Wait callback provider status ref:
  external callback HTTP body -> Service `wait_callback_endpoint` validates transport shape -> Host `WaitCallbackCompletionEnvelope` / wait adapter consumes typed `WaitProviderStatusRef`. Without resolver, Service cannot invent adapter identity from a string.
- Fins direct RESULT:
  Fins producer emits direct events through `FinsIngestionRuntime._run_direct_stream` -> Service `FinsDirectCommandService` relays `AsyncIterator[FinsEvent]` -> CLI/UI consumers display progress/result. Runtime owns the unique terminal `RESULT` protocol; Service may fail closed on malformed stream but must not fabricate terminal business truth.

Propagation audit completion criteria:

- Source scans show no `_status_from_raw_outcome`, no `_direct_missing_result_event`, no `_missing_result_event` synthetic Service path, and no string branch in `_provider_status_ref_from_json`.
- Source scans show no `diagnostic_refs=` concatenated into `ToolResultFailure.hint`, no `accept_rejected:` hint, and no tests asserting governance reason codes as LLM-facing hints.
- Source scans and tests prove every `last_error_code` path touched by S1 preserves the code in owner-owned diagnostics / failure metadata / Tool Trace or a self-contained failure `message`; no `last_error_code` remains only in `ToolResultFailure.hint`.
- Tests prove durable diagnostic refs / failure metadata still carry owner diagnostics after hint cleanup.
- Tests prove result details may still be extracted from raw outcome while status stays typed / unknown, and consumers either handle `UNKNOWN` explicitly or have documented no-op evidence.

## Implementation Slices

### S1 - Tool result invariant and ToolRuntime LLM-facing hint cleanup

Goal:

- Enforce `ToolResultSuccess.ok is True` and `ToolResultFailure.ok is False` at construction.
- Stop ToolRuntime synthetic governance / truncation / accept failures from encoding reason codes or diagnostic refs in `ToolResultFailure.hint`.

Allowed files/modules:

- `dayu/contracts/tool_result.py`
- `dayu/host/tool_runtime.py`
- `tests/contracts/test_tool_result_envelope.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_toolruntime_truncation_fetch_more.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/fins/test_fins_storage_provider.py` only for existing ToolRuntime cancellation / provider assertions affected by hint expectations.

Implementation details:

- Add `ToolResultSuccess.__post_init__` with Chinese docstring; raise `ValueError("ToolResultSuccess.ok must be True")` when `self.ok is not True`.
- Extend `ToolResultFailure.__post_init__`; first validate `self.ok is False`, then existing `error/message/hint` checks.
- Before changing hints, audit every `last_error_code` reference in `dayu/host/tool_runtime.py` accept / awaiting-accept paths. The implementation must classify each path as one of:
  - already preserved by owner-owned diagnostics / failure metadata / Tool Trace;
  - needs a self-contained `message` update so user-visible recovery still has the last error semantics without relying on a code-only hint;
  - out of S1 scope because it is durable wait-state / adapter diagnostics and not projected as `ToolResultFailure.hint`.
- `last_error_code` must not be encoded into LLM-facing `hint`, but it also must not be dropped. If the code carries the only actionable diagnosis for an accept timeout or ack-lost path, preserve it in `message` as explanatory text and/or in ToolRuntime-owned diagnostics or failure metadata before setting `hint=None`.
- In `dayu.host.tool_runtime`, keep `error` and `message` as existing machine / human diagnostic fields, but change the following helper outputs:
  - `_truncation_failure(...)`: do not copy `reason_code` into `hint`; use `hint=None`. The specific reason remains in `error` plus message / trace path, and `fetch_more` callers still see actionable `message`.
  - `_governed_failure_outcome(...)`: use `hint=None` rather than `policy_decision.reason_code`.
  - `_accept_failure_outcome(...)`: use `hint=None` for rejected / timed out accept failures; do not expose `accept_rejected:<reason>` or `last_error_code` as LLM hint.
  - `_awaiting_accept_failure_outcome(...)`: use `hint=None` for rejected / timed out awaiting accept failures.
- After a reference scan, deterministically delete `_hint_with_diagnostic_refs` and the private hidden-hint protocol constants `_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`, `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`, and `_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR`. Also delete any accept reason constants that become unreferenced after the `message` / diagnostics migration, including `_TOOL_RUNTIME_ACCEPT_REJECTED_REASON` or `_TOOL_RUNTIME_ACCEPT_TIMEOUT_REASON` if they no longer feed `error`, `message`, diagnostics, or tests.
- Preserve existing Tool Trace / `failure_metadata.diagnostic_refs` / accept diagnostics fields; do not add new payload fields.

Tests:

- Add contract tests that intentionally bypass static typing with `cast(Literal[True], False)` / `cast(Literal[False], True)` or local ignored assignments, proving runtime constructors raise.
- Update ToolRuntime tests currently asserting `record.outcome.result.hint == "accept_rejected:..."`, `"accept_ack_lost;diagnostic_refs=..."`, `"missing_cursor"`, `"scope_token_mismatch"`, `"remainder_digest_mismatch"` etc. to assert `hint is None`, while separately asserting `error`, `message`, diagnostic emitter records, `failure_metadata.diagnostic_refs`, and durable cleanup reasons remain intact.
- Add or update accept timeout / ack-lost tests using a non-empty `last_error_code`, proving the code is preserved in `message`, owner diagnostics, `failure_metadata`, or Tool Trace while `hint is None`. The test must fail if `last_error_code` is only removed from hint with no replacement diagnostic path.
- Add one Engine-facing regression via existing ToolRuntime executor path that serializes a failed outcome through Engine projection if a suitable helper already exists; otherwise keep scope at ToolRuntime and rely on `dayu/engine/agent.py` evidence that `hint` is directly projected.

Validation:

```bash
source .venv/bin/activate
pytest tests/contracts/test_tool_result_envelope.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/fins/test_fins_storage_provider.py -q
rg -n "last_error_code|_hint_with_diagnostic_refs|_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY|_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR|accept_rejected:" dayu/host/tool_runtime.py tests/host
python -m pyright dayu/ tests/ utils/
git diff --check
```

The `rg` output must be reviewed, not blindly expected to be empty: `last_error_code` is expected in owner diagnostics, durable wait state, and tests; `_hint_with_diagnostic_refs`, the three hint-format constants, and `accept_rejected:` must have no remaining production references. Any remaining accept reason constant must have a non-hint owner diagnostic or message use.

Coverage gate: touched production files should remain at or above 80% single-file coverage. If local coverage tooling is available, run focused coverage for `dayu.contracts.tool_result` and `dayu.host.tool_runtime`; otherwise record the unavailable coverage command as implementation residual for controller validation.

Non-goals:

- Do not redesign `ToolResultFailure` schema.
- Do not remove business-authored recovery hints from Fins read/download/upload tools.
- Do not change Engine projection schema in this slice.

Stop conditions:

- If removing hint breaks a real LLM-facing recovery path that has no equivalent `message`, stop and propose a business-readable hint mapping at ToolRuntime owner; do not reintroduce reason-code hints.
- If diagnostics are only available through hint and not through trace/failure metadata, stop and fix diagnostic propagation at ToolRuntime owner before closing S1.

### S2 - Wait callback typed provider status ref and accepted status projection

Goal:

- Make `provider_status_ref` object-only in the generic callback mapper unless a future owner resolver is explicitly provided.
- Remove accepted result status reconstruction from raw outcome JSON.

Allowed files/modules:

- `dayu/service/wait_callback_endpoint.py`
- `dayu/host/accepted_result_projection.py`
- `dayu/host/read_api.py`, `dayu/host/run_input.py`, `dayu/host/evidence.py`, `dayu/host/memory.py`, `dayu/host/compact_material.py` only if consumer regression proves an existing `UNKNOWN` handling bug; these files must not reintroduce raw outcome status reconstruction.
- `tests/service/test_wait_callback_endpoint.py`
- `tests/host/test_accepted_result_projection.py`
- `tests/host/test_projection_read_model.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_compact_material.py`

Implementation details:

- In `_provider_status_ref_from_json`, delete the `isinstance(raw, str)` branch. Non-`None` values must pass `_require_json_object(raw, "provider_status_ref")`.
- Keep object shape unchanged: `adapter_key`, `status_ref`, optional `status_digest`. The `WaitProviderStatusRef` dataclass remains the typed contract owner.
- Update `_lost_body()` test fixture to use object provider status ref.
- Add a negative test where `provider_status_ref: "jobs/provider-1/status"` returns `malformed_payload` and does not call adapter.
- In `accepted_result_projection`:
  - Inspect `_result_payload(...)` before changing `_accepted_status`; enumerate every exit that returns `result_payload=None` and prove it appends `result_payload_unavailable` or `event_payload_unavailable`.
  - Change `_accepted_status` to consume only `payload` and diagnostics list/tuple; it may use `_FIELD_RESOLUTION_KIND` then `_FIELD_TOOL_FACT_KIND`.
  - If payload unavailable diagnostics exist, return `LOST`. If the `_result_payload(...)` audit finds a `result_payload=None` exit without such a diagnostic, fix `_result_payload(...)` at the projection owner to emit one; do not infer `LOST` from `raw_outcome is None`.
  - If payload is available but neither typed status field exists or both are blank/unknown, return `UNKNOWN`; append / preserve a diagnostic reason such as `accepted_status_unavailable` for missing typed status.
  - The intended distinction is: unavailable accepted result payload means `LOST`; available payload with missing / blank / unrecognized typed accepted status means `UNKNOWN`.
  - Delete `_status_from_raw_outcome`; remove now-unused `_FIELD_KIND` / `_FIELD_OK` if they have no remaining uses.
  - Keep `raw_outcome` for `_result_details_text` only.
- Consumer impact must be checked at projection boundaries. `read_api`, `run_input` / evidence material, memory projection, and compact material may consume `AcceptedToolResultStatus.UNKNOWN`, but none may recover status from `raw_tool_outcome`. If a consumer already treats `UNKNOWN` fail-closed or textually, record no-op evidence in the implementation artifact; if not, fix that consumer at its projection boundary.
- Existing typed precedence stays: `resolution_kind` overrides `tool_fact_kind` for wait resolution rows.

Tests:

- Update `test_projection_maps_raw_result_ok_false_and_extracts_details`: same raw outcome should still extract `reason=not found`, but `projection.status is AcceptedToolResultStatus.UNKNOWN` when `tool_fact_kind` / `resolution_kind` is absent.
- Add / update tests proving `raw_tool_outcome.kind="completed"` does not override missing, blank, or unknown typed status.
- Add unavailable payload tests for `_result_payload(...)` paths: missing event payload / missing result payload must project `AcceptedToolResultStatus.LOST` with the expected diagnostic reason; available payload with absent typed status must project `UNKNOWN`.
- Keep tests for `tool_fact_kind="governed_error"` and `resolution_kind="cancelled"` precedence.
- Wait callback tests must cover valid object provider ref, invalid string provider ref, invalid object digest, and adapter not called on malformed payload.
- Add consumer regression checks for `UNKNOWN`:
  - read model / `read_api`: activity state remains fail-closed and does not crash or reclassify from raw outcome.
  - `run_input` / evidence material: LLM-facing material includes a self-explanatory unknown status or explicitly omits only where existing rules already omit non-actionable tool results; no raw fallback is used.
  - memory projection: accepted tool result material handles `UNKNOWN` without converting it to completed / failed from raw outcome.
  - compact material: compact input material handles `UNKNOWN` consistently with projection status and does not reconstruct raw status.
  If a named consumer has no direct code path from accepted result projection, record that no-op evidence with an `rg` result in the implementation artifact.

Validation:

```bash
source .venv/bin/activate
pytest tests/service/test_wait_callback_endpoint.py tests/host/test_accepted_result_projection.py tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_projection_read_model.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py -q
rg -n "_result_payload|AcceptedToolResultStatus.UNKNOWN|_status_from_raw_outcome|raw_tool_outcome|result_payload_unavailable|event_payload_unavailable" dayu/host/accepted_result_projection.py dayu/host/read_api.py dayu/host/run_input.py dayu/host/evidence.py dayu/host/memory.py dayu/host/compact_material.py tests/host
python -m pyright dayu/ tests/ utils/
git diff --check
```

The S2 validation report must explicitly state the `_result_payload(...)` exit audit result and the consumer disposition for `read_api`, `run_input` / evidence material, memory, and compact material.

Coverage gate: touched production files `dayu/service/wait_callback_endpoint.py` and `dayu/host/accepted_result_projection.py` should stay >=80% single-file coverage; if coverage tooling is unavailable, implementation artifact must record the gap.

Non-goals:

- Do not add callback resolver SPI in this WU.
- Do not migrate old callback payloads.
- Do not change raw outcome result detail rendering except where tests must decouple status from raw outcome.

Stop conditions:

- If an existing production caller only has string provider refs and no adapter identity, stop and require owner-provided resolver design; do not fabricate `adapter_key="callback"`.
- If a downstream consumer cannot tolerate `UNKNOWN`, stop and fix that consumer to consume typed projection state rather than raw outcome.

### S3 - Fins direct unique RESULT protocol error and docs sync

Goal:

- Make missing or duplicate Fins direct `RESULT` a typed protocol error at runtime / Service direct boundaries.
- Remove synthetic business failure result construction for protocol violations.
- Update README files whose current text states the old synthetic failure behavior.

Allowed files/modules:

- `dayu/fins/direct_events.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/service/fins_direct.py`
- `dayu/cli/commands/fins.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/service/test_fins_direct.py`
- `tests/cli/test_fins_commands.py`
- README candidates listed below.

Implementation details:

- Before implementing RESULT buffering, audit `_DirectStreamProducerDone` lifecycle in `dayu/fins/ingestion_runtime.py`:
  - confirm normal producer completion puts exactly one sentinel;
  - confirm producer exception paths put the sentinel after surfacing the exception through the queue / runtime error path;
  - confirm every producer path that emits a terminal `RESULT` returns or otherwise reaches the sentinel promptly;
  - confirm no producer relies on the current early `break` after first `RESULT` for cleanup.
  Record the audit evidence in the implementation artifact with source line references.
- In `dayu.fins.direct_events`, add:
  - `FinsDirectStreamProtocolErrorKind(str, Enum)` with `MISSING_RESULT = "missing_result"` and `DUPLICATE_RESULT = "duplicate_result"`.
  - `FinsDirectStreamProtocolError(ValueError)` with typed attributes `reason`, `operation_kind`, and `message`; validate enum types and non-empty message in `__init__` / helper. Provide full Chinese docstring.
  - Export both symbols in `__all__`.
- In `FinsIngestionRuntime._run_direct_stream`:
  - Track first `RESULT` as a buffered terminal event.
  - Continue draining until `_DirectStreamProducerDone` so duplicate `RESULT` can be detected; on duplicate, raise `FinsDirectStreamProtocolError(DUPLICATE_RESULT, direct_operation_kind, "...")`.
  - Yield buffered non-result progress events as before before terminal; after producer done, yield the single buffered `RESULT`.
  - If producer completes without a result, raise `FinsDirectStreamProtocolError(MISSING_RESULT, direct_operation_kind, "...")`.
  - Delete `_direct_missing_result_event` if unused.
- In `dayu.service.fins_direct._ensure_result_event`:
  - Raise `FinsDirectStreamProtocolError(DUPLICATE_RESULT, operation_kind, ...)` for duplicate `RESULT`.
  - Raise `FinsDirectStreamProtocolError(MISSING_RESULT, operation_kind, ...)` when stream ends normally without result.
  - Delete `_missing_result_event` if unused.
  - Keep `FinsDirectUsageError` for Service parameter misuse only; do not use it for runtime stream protocol violations.
- In `dayu/cli/commands/fins.py`, make the Fins-owned typed protocol error the only source of truth for direct stream protocol violations:
  - delete `FinsDirectStreamContractViolation` if it only represents missing terminal result;
  - replace CLI-local raises with `FinsDirectStreamProtocolError(MISSING_RESULT, operation_kind, ...)` or let the Service / runtime error propagate when already typed;
  - if CLI needs command-exit formatting, catch / render `FinsDirectStreamProtocolError` directly without introducing a second exception type for the same protocol fact.

Tests:

- Update `tests/fins/test_fins_ingestion_runtime.py::test_direct_stream_missing_result_returns_failure_result` to expect `FinsDirectStreamProtocolError.reason is MISSING_RESULT`.
- Add a runtime duplicate producer test that calls `_emit_direct_result` twice and expects `DUPLICATE_RESULT`.
- Update `tests/service/test_fins_direct.py::test_stream_without_result_closes_as_failure_result` to expect typed protocol error, not a synthetic `RESULT`.
- Update duplicate Service test to expect `FinsDirectStreamProtocolError` with `DUPLICATE_RESULT`.
- Keep tests proving real business failures still return `FinsEventType.RESULT` with `FinsResultStatus.FAILURE`.
- Add / adjust CLI tests to confirm typed protocol error surfaces as command failure without fabricated business result, and source scans show no `FinsDirectStreamContractViolation` remains.
- Add no-hang validation for the runtime buffering behavior. A focused async test should consume a normal direct stream through the new drain-until-sentinel path and complete without relying on arbitrary downstream timeouts. If an existing producer hangs after emitting `RESULT`, stop and fix producer termination at `FinsIngestionRuntime` / direct producer owner; do not add CLI / Service timeout wrappers that hide the protocol lifecycle bug.

Validation:

```bash
source .venv/bin/activate
pytest tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q
rg -n "_DirectStreamProducerDone|FinsDirectStreamContractViolation|FinsDirectStreamProtocolError|_direct_missing_result_event|_missing_result_event" dayu/fins dayu/service dayu/cli tests/fins tests/service tests/cli
python -m pyright dayu/ tests/ utils/
git diff --check
```

The `rg` output must be classified: `_DirectStreamProducerDone` and `FinsDirectStreamProtocolError` are expected; `FinsDirectStreamContractViolation`, `_direct_missing_result_event`, and `_missing_result_event` must have no remaining production references. No-hang validation passes when normal / business-failure direct stream tests complete through sentinel drain; if they hang, S3 stops at Fins runtime owner.

Coverage gate: touched `dayu/fins/direct_events.py`, `dayu/fins/ingestion_runtime.py`, and `dayu/service/fins_direct.py` should stay >=80% single-file coverage, with controller validation recording any file-specific exception if the existing suite cannot collect a meaningful single-file figure for the large runtime module.

Non-goals:

- Do not change Fins business result summaries for adapter / storage / user-input failures.
- Do not add durable job records or event sequence to direct stream.
- Do not make Service or CLI reconstruct terminal truth after protocol error.

Stop conditions:

- If the lifecycle audit cannot prove sentinel emission on normal, exception, and terminal-result paths, stop before changing consumer behavior and fix the producer lifecycle at Fins runtime owner.
- If buffering `RESULT` until producer done causes a normal or business-failure direct stream test to hang, stop and fix producer termination at Fins runtime owner; do not return to "yield result then ignore later protocol errors" and do not add downstream timeout hacks in Service / CLI.
- If CLI relies on synthetic missing result for user-visible exit status, stop and map `FinsDirectStreamProtocolError` to command failure at the direct command boundary without creating a fake `RESULT` or retaining a CLI-local protocol exception.

## README Update Decision

- `dayu/host/README.md`: triggered by `dayu/host/` changes. Must check after S1/S2. Likely update one sentence in ToolRuntime / accepted projection area if current text does not state typed status-only and no LLM-facing governance hint protocol. Do not write work-unit history.
- `dayu/fins/README.md`: triggered by `dayu/fins/` changes. Must update the direct stream section that currently says stream ending without result is closed as a failure result; new text should state missing / duplicate `RESULT` is a direct stream protocol error.
- `tests/README.md`: triggered by `tests/` changes, but no new test layer or command pattern is planned. Expected no-op after checking existing update boundary.
- `dayu/service/README.md`: not named in AGENTS trigger list, but it currently states `fins_direct` synthesizes a failure result for missing `RESULT`. Because S3 changes that developer contract, update the Service README to avoid stale internal docs.
- root `README.md`: no user-visible command, install, default output channel, log location, workspace file location, or final user workflow change is planned. Expected no-op unless CLI protocol error mapping changes user-visible behavior.
- `dayu/README.md`: no cross-layer dependency direction or top-level architecture boundary change is planned. Expected no-op unless implementation changes public summary wording.
- `dayu/engine/README.md`: no Engine code planned. No-op.
- `dayu/config/README.md`: no config changes planned. No-op.

## Risks And Residual Risk

- Fins runtime duplicate detection may require delaying terminal `RESULT` until producer done. This is correct for a terminal protocol but could reveal producer lifecycle bugs; stop condition covers hanging producers.
- Removing ToolRuntime hints may reduce LLM recoverability for some framework-tool errors if `message` is not actionable enough. S1 must verify messages remain business-readable or add non-governance repair text at ToolRuntime owner.
- `UNKNOWN` accepted status may expose downstream assumptions that raw outcome fallback masked. Those assumptions should be fixed at consumers only if they incorrectly require a typed status while receiving unknown; they must not reintroduce raw reconstruction.
- Callback string provider refs may break callers using old ad hoc payloads. This is intentional contract hardening; without resolver, accepting strings is owner-boundary drift.
- Large focused suites around `dayu/host/tool_runtime.py` and `dayu/fins/ingestion_runtime.py` may make per-file coverage slow. Implementation artifacts must record exact coverage commands and gaps; pyright remains mandatory.

Residual risks assigned outside P3-E:

- Full EventLog taxonomy / DDL synchronization remains P3-J.
- Fins source document / provenance / citation ownership remains P3-F.
- Callback resolver SPI, if ever needed, is a future wait-adapter owner design, not this WU.

## Aggregate Validation

After all slices:

```bash
source .venv/bin/activate
pytest tests/contracts/test_tool_result_envelope.py tests/service/test_wait_callback_endpoint.py tests/host/test_accepted_result_projection.py tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_projection_read_model.py tests/host/test_run_input_builder.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_toolruntime_executor.py tests/host/test_toolruntime_truncation_fetch_more.py tests/host/test_toolruntime_duplicate_governance.py tests/fins/test_fins_storage_provider.py tests/fins/test_fins_ingestion_runtime.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
rg -n "_status_from_raw_outcome|_direct_missing_result_event|_missing_result_event|diagnostic_refs=.*hint|accept_rejected:|_hint_with_diagnostic_refs|FinsDirectStreamContractViolation|provider_status_ref\"\\s*:|last_error_code|_DirectStreamProducerDone|AcceptedToolResultStatus.UNKNOWN" dayu tests
```

The final `rg` is not expected to be zero-match for all terms because JSON fixtures may contain object `provider_status_ref`, `last_error_code` remains valid owner diagnostics, `_DirectStreamProducerDone` remains the Fins runtime sentinel, and `AcceptedToolResultStatus.UNKNOWN` should appear in projection / consumer tests. Implementation validation must report the remaining matches and classify them as expected typed contract uses or stale violations. `_status_from_raw_outcome`, synthetic missing-result helpers, hidden hint helper / format constants, `accept_rejected:` hint strings, and `FinsDirectStreamContractViolation` should have no remaining production references.

## Completion Report Format

- status: `ready-for-plan-review`
- artifact path: `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md`
- source findings accepted/rejected/deferred/needs-more-evidence counts: `6/0/0/0`
- proposed slice count: `3`
- blocking questions: `none`
