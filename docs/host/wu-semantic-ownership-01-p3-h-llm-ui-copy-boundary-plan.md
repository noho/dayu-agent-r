# WU-SEMANTIC-OWNERSHIP-01 P3-H LLM-facing and UI-copy boundary cleanup plan

## Gate

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-H - LLM-facing and UI-copy boundary cleanup`
- Gate: plan only
- Goal artifact: `docs/reviews/wu-semantic-ownership-01-p3-h-goal-confirmation.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Review source: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md` section `P3-H`

## Goal

Move LLM-facing next-action prose and user-visible UI copy to the boundary that owns projection, while keeping lower-level providers, downloaders, adapters, and runtime producers responsible only for typed machine facts and business execution facts.

Success signals:

- Web search provider internals no longer build `hint`, `next_action`, `next_action_args`, or `preferred_result_summary` prose for the LLM; Web tool projection builds those fields from provider facts.
- Fins direct-stream and wait-resolution visible text comes from a shared Fins direct/wait projection helper, not ad hoc literals inside `FinsIngestionRuntime` or `wait_adapter`.
- SEC downloader diagnostics no longer name CLI commands; CLI / README remain the owner for command names and user setup workflow.
- DS12 Host ToolRuntime hidden hint protocol remains closed unless implementation finds new direct production evidence.
- Affected tests, source scans, `git diff --check`, and pyright pass. Source scans are evidence checks only; they complement tests, helper coverage, and the propagation audit, and are not treated as exhaustive proof.

## First-principles judgment

The motivation is valid, but it is not a request to remove useful messages. The root problem is semantic ownership drift: provider/downloader/adapter code currently emits prose that tells an LLM or user what to do, even though those modules are not the owner of prompt/tool projection or CLI/user-facing guidance.

Correct owner boundary:

- Providers and downloaders may produce typed rows, selected result facts, status codes, error classifications, counts, URLs, and neutral diagnostics.
- Tool declaration/projection owners generate LLM-facing tool descriptions, display names, cancellation wording, success hints, and next-action guidance. A `@tool(...)` declaration site may remain the owner for its own `display_name` and `description`.
- Fins direct event / wait projection owner generates reusable direct-stream titles, progress messages, failure messages, and wait-resolution hints.
- CLI and user docs own command names such as `dayu-cli init`; Fins downloader diagnostics may reference typed configuration knobs such as `SEC_USER_AGENT`, but not CLI commands.

This is not overdesigned because it introduces only two small projection text helpers and one provider-output projection step. It does not add a localization framework, config-driven copy system, durable schema, EventLog migration, or new Host/Engine contract.

## Source finding dispositions

| Source finding | Disposition | Current direct evidence | Planned handling |
|---|---:|---|---|
| AgentMiMo `BI-2` Web search provider hardcodes LLM behavior instructions | accepted | `dayu/tools/web/web_search_providers.py:72-83` includes LLM-facing output fields; `:292-301` builds them in provider; `:815-925` builds `preferred_result_summary`, `next_action`, `next_action_args`, and prose `hint`. | Move output projection to Web search projection helper; provider returns only structured search facts via `SearchWebProviderResult`. |
| AgentMiMo `BI-3` ingestion runtime hardcodes Chinese UI copy | accepted | `dayu/fins/ingestion_runtime.py:181-184`, `:2791`, `:2810`, `:2849`, `:2868`, `:2907`, `:2918`, `:2932`, `:2954`, `:3509-3618`, `:3661` contain direct-stream visible text; `:3198`, `:3254`, `:3432`, `:3439`, `:6630-6635` contain job event sidecar text. | Centralize direct-stream and wait-outcome visible text under Fins direct/wait projection helper; classify job sidecar text separately and do not claim it moved unless it enters `FinsEvent`, wait outcome, or tool result. |
| AgentMiMo `BI-4` Fins wait adapter hardcodes LLM-facing hints | accepted | `dayu/fins/ingestion/wait_adapter.py:480-506` creates `ToolResultFailure.hint` and `ToolCancelledOutcome.message/hint` literals. | Wait adapter consumes the same Fins projection helper. |
| AgentMiMo `BI-5` SEC downloader references CLI command name | accepted | `dayu/fins/downloaders/sec_downloader.py:2035-2038` warning references `dayu-cli init`. | Downloader warning references `SEC_USER_AGENT` / caller configuration only; CLI docs/help remain owner of command name. |
| AgentMiMo `BI-6` Web tools hardcode display/cancel copy | accepted with narrowed owner | `dayu/tools/web/web_tools.py:165-166`, `:1193`, `:1232`, `:1340-1466`; `dayu/tools/web/web_cancellation_text.py:7`. Web tool declaration is already the owner for `display_name` and `description`; cancellation/recovery text is split across runtime module and cancellation-only helper. | Keep `display_name` / `description` at the `@tool(...)` declaration site unless implementation finds duplicate display-name ownership. Replace split cancellation/recovery literals with `web_tool_projection_text.py`; delete `web_cancellation_text.py` with no compatibility re-export. |
| AgentDS finding 12 / DS12 ToolRuntime hidden hint protocol | evidence-invalid for P3-H | Current source scan found no `_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`, no `_hint_with_diagnostic_refs`, and no `hint=policy_decision.reason_code` in `dayu` or `tests`; P3-E artifacts confirm deletion. | Do not reopen. Keep regression source scan in validation. |

Disposition counts: accepted `5`, accepted-with-narrowed-owner `1` included in the accepted total above, evidence-invalid `1`, rejected `0`, deferred `0`.

## Design alignment

- Host design: Host owns ToolRuntime governance, wait-resume, EventLog, memory, projection, and durable truth. P3-H does not move business copy into Host and does not modify Host durable state.
- Engine design: Engine consumes tool schemas and tool outcomes; it does not own tool provider prose or financial-domain UI text. P3-H keeps Engine unchanged.
- Fins README boundary: Fins direct stream is the CLI / Service direct user-visible progress boundary; Fins awaiting observation handle is Host wait adapter input, not Host durable truth.
- Fins direct-events boundary: `dayu/fins/direct_events.py` owns event contract shape and validation. `direct_event_text.py` must own only reusable text content and text-selection helpers; it does not replace the `FinsEvent`, `FinsResultSummary`, or `FinsProgress` contracts.
- LLM-facing text constraint: Any text that enters tool outcome `hint`, tool schema/display, direct events, memory, trace, or prompt must be self-explanatory and must not expose Host/Engine/downloader implementation terms as business facts.

## Affected files and modules

Expected production files:

- `dayu/tools/web/web_search_providers.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_tool_projection_text.py`
- `dayu/tools/web/web_search_projection.py`
- `dayu/tools/web/web_cancellation_text.py` for deletion only; do not keep compatibility re-export
- `dayu/fins/direct_event_text.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/fins/downloaders/sec_downloader.py`

Expected tests:

- `tests/tools/web/test_web_tools_provider.py`
- `tests/tools/test_combined_tools_acceptance.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_sec_downloader.py`
- `tests/host/test_wait_adapter_polling.py` and/or `tests/host/test_resolve_wait_command.py`
- `tests/service/test_fins_direct.py` and/or `tests/cli/test_fins_commands.py` only if existing direct-stream assertions need to follow the new helper owner

README candidates:

- `dayu/fins/README.md`: check after Fins helper is implemented. Update only if the code introduces a stable new direct/wait projection helper boundary that is useful to Fins developers.
- `tests/README.md`: check after tests change. Update only if a new testing layer or stable test responsibility is added, not for ordinary assertion updates.
- Root `README.md` and `dayu/README.md`: no update expected because P3-H should not change user commands, public workflow, package layering, or cross-package architecture.

## Contract, schema, and state-machine changes

- No durable schema change.
- No Host EventLog, memory, trace, wait record, or outbox schema change.
- No Engine contract change.
- No CLI command contract change.
- Web tool success JSON keeps the current LLM-facing `SearchWebOutput` shape for compatibility, but the owner of derived fields moves from provider to `web_search_projection.py`.
- Provider-internal search output type becomes `SearchWebProviderResult` in `web_search_providers.py`. Update imports and tests directly; do not add compatibility re-exports or wrapper aliases.

## Implementation slices

Three slices are enough because each slice is a separate semantic owner boundary with its own validation loop. Splitting further by file would add gate overhead without reducing semantic risk.

### S1 - Web search provider facts and Web tool projection text

Objective: make `dayu/tools/web/web_search_providers.py` produce structured search facts only, and make Web tool projection generate LLM-facing search guidance plus cancellation/recovery copy.

Allowed production files:

- `dayu/tools/web/web_search_providers.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_search_projection.py`
- `dayu/tools/web/web_tool_projection_text.py`
- `dayu/tools/web/web_cancellation_text.py` for deletion only

Exact allowed changes:

- In `web_search_providers.py`:
  - Replace provider-owned `SearchWebOutput` with `SearchWebProviderResult`, a provider-owned output type containing only `query`, `domains`, `total`, `preferred_result`, and `results`.
  - Remove provider-owned `_SEARCH_WEB_NEXT_ACTION_FETCH_PAGE`, `_SEARCH_WEB_NEXT_ACTION_REFINE_QUERY`, `_build_search_web_next_action`, `_build_search_web_next_action_args`, `_build_search_web_hint`, and `_build_search_web_preferred_summary` if no longer needed by provider facts.
  - Remove `WEB_CANCELLED_HINT` import and remove `hint` from `WebSearchCancelledError`; provider cancellation exception may carry a neutral cancellation message only.
  - Update docstrings that currently say provider messages are "面向 LLM".
- Add `web_search_projection.py`:
  - Own the current LLM-facing `SearchWebOutput` shape. `SearchWebOutput` moves from `web_search_providers.py` to this module; this is a direct import migration, not a compatibility alias.
  - Provide this builder signature:

```python
def build_search_web_output(provider_result: SearchWebProviderResult) -> SearchWebOutput:
    ...
```

  - Build `preferred_result_summary`, `next_action`, `next_action_args`, and `hint` from provider output.
  - Keep current output semantics unless a test proves they were wrong: preferred result exists -> `fetch_web_page` with URL; no preferred result -> `refine_query` with empty args and no fetch instruction.
  - Document that `next_action` is LLM-facing tool guidance, not a provider fact.
- Add or replace with `web_tool_projection_text.py`:
  - Own `WEB_SEARCH_CANCELLED_MESSAGE`, `WEB_FETCH_CANCELLED_MESSAGE`, `WEB_CANCELLED_HINT`, and any shared Web recovery/search guidance constants needed by `web_tools.py` or `web_search_projection.py`.
  - Do not move `search_web` / `fetch_web_page` `display_name` or `description` out of the `@tool(...)` declaration unless implementation finds direct duplicate ownership outside the declaration site.
  - Delete `web_cancellation_text.py` after moving `WEB_CANCELLED_HINT` into this helper. Update imports directly in production and tests; do not keep a compatibility re-export.
- In `web_tools.py`:
  - Import `SearchWebProviderResult`, `WebSearchCancelledError`, `WebSearchProviderUnavailableError`, and `search_public_web` from `web_search_providers.py`.
  - Import `SearchWebOutput` and `build_search_web_output` from `web_search_projection.py`.
  - `_search_web_business(...)` remains typed as returning `SearchWebOutput`: it calls `search_public_web(...)` for `SearchWebProviderResult`, then calls `build_search_web_output(...)` before returning the completed tool value.
  - Keep `display_name` and `description` in the `@tool(...)` declaration site.
  - Cancellation outcome paths use Web projection text constants.
- In tests:
  - Provider boundary fixtures and annotations use `web_search_providers.SearchWebProviderResult`.
  - Tool outcome tests import/assert the public `SearchWebOutput` shape from `web_search_projection.py` or through the completed tool value.
  - Tests referencing `WEB_CANCELLED_HINT` import it from `web_tool_projection_text.py`.

Tests and expected assertions:

- Update Web tests so provider fixtures return raw provider facts where testing provider boundary, and tool-call tests assert the final completed tool value still has `preferred_result_summary`, `next_action`, `next_action_args`, and `hint`.
- Add/adjust tests proving provider output has no `hint` / `next_action` fields before projection.
- Add/adjust tests proving Web cancellation/recovery text comes from the projection text helper.
- Add/adjust tests proving display names/descriptions remain declared at the `@tool(...)` boundary unless duplicate ownership is found.
- Focused command:

```bash
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
```

Stop condition:

- If removing provider output fields would require changing a public tool success JSON consumed outside `web_tools.py`, keep public JSON unchanged and move only its construction owner to `web_search_projection.py`.

### S2 - Fins direct stream and wait visible-language owner

Objective: centralize Fins direct-stream and wait-resolution visible text under a Fins projection helper, while keeping `ingestion_runtime` and `wait_adapter` responsible for execution facts and status mapping.

Allowed production files:

- `dayu/fins/direct_event_text.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/ingestion/wait_adapter.py`

Exact allowed changes:

- Add `direct_event_text.py` with complete Chinese docstrings and typed functions/constants.
  - It may import `FinsErrorKind`, `FinsOperationKind`, and `FinsResultStatus` from `dayu.fins.direct_events` as typed inputs.
  - It must not import, construct, wrap, or validate `FinsEvent`, `FinsResultSummary`, or `FinsProgress`; `direct_events.py` remains the contract-shape and validation owner.
  - It must not import `FinsIngestionRuntime`, wait adapter types, Host outcome types, storage types, or job store types.
  - It provides text constants and small lookup functions only. Required API shape:

```python
def direct_result_title(
    *,
    operation_kind: FinsOperationKind,
    status: FinsResultStatus,
) -> str:
    ...

def direct_failure_message(
    *,
    error_kind: FinsErrorKind | None,
    fallback_message: str | None,
) -> str:
    ...

def direct_progress_message(*, stage: str) -> str:
    ...

def wait_failed_hint() -> str:
    ...

def wait_cancelled_message() -> str:
    ...

def wait_cancelled_hint() -> str:
    ...
```

- The helper owns:
  - Direct result titles: success, cancelled, generic failure, and operation-specific failure titles for download/preprocess/upload.
  - Direct progress messages for current direct stages such as `download.preparing`, `download.started`, preprocess selected/document states/completed, and upload preparing/started/completed states.
  - Direct failure messages currently emitted by direct result paths: download wrote no source documents, preprocess completed no requested documents, upload runtime failed.
  - Wait-resolution failed hint and cancelled message/hint currently hardcoded in `wait_adapter`.
- Fins text scope by propagation path:

| Path | Producer call/site | Destination | P3-H scope | Owner decision |
|---|---|---|---:|---|
| Direct progress stream | `_emit_context_progress(...)` messages such as `下载准备中`, `预处理已选择源文档`, `下载已开始`, `下载已完成`, `上传已完成` | `FinsEvent.message` consumed by Service/CLI direct stream | in | Move text selection to `direct_event_text.py`; runtime supplies operation/stage/count facts. |
| Direct result stream | `_emit_direct_result(...)` titles/error messages such as `操作完成`, `操作已取消`, `下载失败`, `预处理失败`, `上传失败`, `执行失败` | `FinsResultSummary.title` / `error_message` inside `FinsEvent` | in | Move title/error-message selection to `direct_event_text.py`; runtime keeps status and payload facts. |
| Wait resolution | `ToolResultFailure.hint`, `ToolCancelledOutcome.message`, `ToolCancelledOutcome.hint` in `wait_adapter.py` | Host wait outcome and resumed tool result visible to the LLM | in | Move hint/message text to `direct_event_text.py`; adapter keeps status mapping and `payload_ref`. |
| Direct tool result derived from direct event | Any tool result or trace projection that reads direct event title/message | Tool outcome, trace, memory, or LLM-visible material | in if direct evidence appears | Use the same helper-derived `FinsEvent` text; do not create a second formatter. |
| Job event sidecar | `_append_job_event_warn(...)` and helpers returning `job 已进入队列`, `job 已开始执行`, `job 已成功完成`, `job 已失败`, `job 状态未终结`, `已记录取消请求` | Durable job event/audit sidecar, not direct stream or Host wait outcome | out for P3-H unless it is also projected into `FinsEvent`, wait outcome, tool result, memory, or trace | Leave in runtime/job lifecycle owner for this WU. This is not a current P3-H blocker because P3-H targets direct/wait projection; scans must list these as retained sidecar text rather than claiming all runtime UI text moved. |
| Log-only/internal diagnostics | `_LOGGER` messages or internal exception details not projected into direct/wait/tool/LLM paths | Logs/internal diagnostics | out | Do not move mechanically. |

- Move direct progress stage constants only if that reduces duplication. If stage constants stay in `ingestion_runtime.py`, the helper must not duplicate their string values in a second source of truth without a source scan/test explaining the boundary.
- In `ingestion_runtime.py`:
  - Replace direct event title/message/error-message literals in direct-stream result/progress paths with calls/constants from `direct_event_text.py`.
  - Keep machine status, payload keys, counts, source event type facts, job record state, and storage behavior in runtime.
  - Do not change Fins job store schema or observation lifecycle.
  - Do not mechanically move log-only or durable job sidecar messages unless they are projected into `FinsEvent`, wait outcome, tool result, memory, or trace. If such projection is found, classify the exact path before moving the text.
- In `wait_adapter.py`:
  - Replace `ToolResultFailure.hint`, `ToolCancelledOutcome.message`, and `ToolCancelledOutcome.hint` literals with helper calls/constants.
  - Keep status mapping, result meta, `payload_ref`, and Host wait outcome types unchanged.

Tests and expected assertions:

- Fins direct runtime tests still see the same user-visible text unless the helper deliberately normalizes duplicate text.
- Add direct helper unit coverage through existing Fins tests or a focused new test file; new production helper file must reach at least 80% coverage.
- Wait adapter tests assert failed/cancelled hints come from the helper and no Fins ingestion / Host wait implementation terms leak.
- Focused command:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q
```

Stop condition:

- If a direct runtime string is both durable job sidecar state and direct/wait user-visible projection, first identify the consumer path. Move only the direct/wait projection text to `direct_event_text.py`; do not change durable job sidecar semantics in this WU.
- If implementation finds that a job sidecar message is projected into `FinsEvent`, a Host wait outcome, a tool result, memory, or trace, update the scope table and tests before moving it. Do not silently treat all `_append_job_event_warn(...)` text as direct-stream copy.

### S3 - SEC downloader diagnostics, README decision, and aggregate scans

Objective: remove CLI command names from SEC downloader diagnostics, update tests/docs only where ownership requires it, and run the P3-H evidence scans.

Allowed production files:

- `dayu/fins/downloaders/sec_downloader.py`
- CLI/user-facing docs only if required by README decision
- Tests listed above

Exact allowed changes:

- In `sec_downloader.py`:
  - Replace the warning at `_resolve_user_agent(...)` so it references `SEC_USER_AGENT` and "caller configuration" / "deployment configuration" only.
  - Do not mention `dayu-cli init` or any CLI command.
  - Keep fallback `_UNCONFIGURED_USER_AGENT`, rate limit behavior, request headers, and SEC download behavior unchanged.
- In tests:
  - Add or update a `tests/fins/test_sec_downloader.py` assertion that missing User-Agent warning contains `SEC_USER_AGENT` and does not contain `dayu-cli`.
  - Keep CLI command-name assertions in CLI tests/docs only if they belong to CLI behavior.
- README:
  - Read `dayu/fins/README.md` and `tests/README.md` update constraints before editing.
  - Expected decision: no root README change; no `dayu/README.md` change.
  - Update `dayu/fins/README.md` only if S2 adds a stable developer-facing helper boundary not already described by "Fins direct stream is CLI / Service direct user-visible progress boundary".
  - Update `tests/README.md` only if new tests introduce a new durable testing category.

Focused command:

```bash
source .venv/bin/activate && pytest tests/fins/test_sec_downloader.py -q
```

Aggregate validation commands:

```bash
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_combined_tools_acceptance.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_sec_downloader.py tests/host/test_wait_adapter_polling.py tests/host/test_resolve_wait_command.py tests/service/test_fins_direct.py tests/cli/test_fins_commands.py -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
git diff --check
```

Required source scans:

```bash
rg -n "_TOOL_RUNTIME_HINT_SECTION_SEPARATOR|_hint_with_diagnostic_refs|hint=policy_decision\\.reason_code" dayu tests
rg -n "_build_search_web_preferred_summary|_build_search_web_hint|_build_search_web_next_action|_build_search_web_next_action_args|当前没有可直接抓取|优先抓取首选结果正文|未找到可直接抓取正文|首选结果|标题：|日期：|摘要：" dayu/tools/web/web_search_providers.py tests/tools/web
rg -n "preferred_result_summary|next_action|next_action_args|\\\"hint\\\"" dayu/tools/web/web_search_providers.py
rg -n "web_cancellation_text|WEB_CANCELLED_HINT" dayu/tools/web tests/tools/web
rg -n "_WEB_SEARCH_CANCELLED_MESSAGE|_WEB_FETCH_CANCELLED_MESSAGE|当前工具调用已停止|搜索工具调用已取消|抓取工具调用已取消" dayu/tools/web/web_tools.py
rg -n "请检查 Fins ingestion|如仍需要该财报资料|Fins operation was cancelled before completion|_DIRECT_CANCELLED_MESSAGE|_DIRECT_FAILURE_TITLE|_DIRECT_SUCCESS_TITLE|_DIRECT_ERROR_TEXT_FALLBACK|下载准备中|下载已开始|下载已完成|下载已完成，存在失败候选|预处理准备中|预处理已选择源文档|预处理源文档已开始|预处理源文档不支持|预处理源文档失败|预处理源文档已完成|预处理源文档已跳过|预处理请求已完成|上传准备中|上传已开始|上传已完成|上传已完成，存在失败|操作已取消|操作完成|操作失败|执行失败|下载失败|预处理失败|上传失败|下载请求未写入任何源文档|没有任何请求文档完成预处理|上传运行时返回失败状态" dayu/fins/ingestion_runtime.py dayu/fins/ingestion/wait_adapter.py
rg -n "_append_job_event_warn|已记录取消请求|job 已进入队列|job 已开始执行|job 已取消|job 已成功完成|job 已失败|job 状态未终结" dayu/fins/ingestion_runtime.py
rg -n "dayu-cli init|dayu-cli" dayu/fins/downloaders tests/fins
```

Expected scan results:

- DS12 scan: zero production/test hits.
- Web provider scan: zero hits for LLM next-action prose and derived output fields in provider internals; hits are allowed in `web_search_projection.py` / tests that intentionally assert projection.
- Web cancellation scan: no `web_cancellation_text.py` module/import remains; `WEB_CANCELLED_HINT` hits are allowed only in `web_tool_projection_text.py`, `web_tools.py` imports/usages, and tests that intentionally assert the helper owner.
- Web tools scan: no local cancellation/recovery literals in `web_tools.py`; helper references are allowed. `display_name="联网搜索"` and `display_name="抓取网页"` may remain in `@tool(...)` declarations because that is the declaration owner.
- Fins direct/wait scan: no listed hardcoded direct-stream or wait-outcome prose in `ingestion_runtime.py` or `wait_adapter.py`; hits are allowed in `direct_event_text.py` and tests.
- Fins job sidecar scan: remaining hits in `_append_job_event_warn(...)` / job lifecycle helpers are expected unless implementation finds they are projected into direct/wait/tool/LLM-visible paths. Implementation closeout must list retained sidecar text and confirm it was not counted as moved direct-stream copy.
- SEC downloader scan: no `dayu-cli` in `dayu/fins/downloaders` or Fins downloader tests.

Scan limitation:

- These scans cover known source findings and likely regression strings. They are not exhaustive proof that no new prose was introduced in a wrong owner. If implementation adds or rewrites LLM-facing/user-visible text, it must update tests and, where the new text is in a provider/runtime/adapter file, add a matching scan pattern or explain why that file is the owner.

## Propagation audit criteria

Implementation closeout must include this audit:

- Web search path:
  - Producer: search provider returns query/domain/result facts only.
  - Projection owner: Web search projection builds `preferred_result_summary`, `next_action`, `next_action_args`, and `hint`.
  - Tool outcome: `completed_outcome` contains the projected JSON.
  - LLM-visible path: Engine tool message receives projected tool result; provider internals do not own LLM instructions.
- Web cancellation/declaration path:
  - Declaration owner: `@tool(...)` declaration in `web_tools.py` owns `display_name` and `description` unless duplicate ownership is found.
  - Projection text owner: Web tool text helper owns cancellation/recovery copy.
  - Tool schema/outcome: `web_tools.py` consumes helper constants for cancellation outcomes and keeps declaration-local display metadata.
  - LLM-visible path: cancelled tool outcome hint/message contains helper text only.
- Fins direct path:
  - Producer: runtime emits typed operation/status/count/payload facts.
  - Projection owner: Fins direct/wait text helper supplies direct progress/result text.
  - User-visible path: Service/CLI direct stream consumes `FinsEvent` text derived from helper.
- Fins job sidecar path:
  - Producer/owner for this WU: runtime job lifecycle/audit code may retain `_append_job_event_warn(...)` sidecar text.
  - Destination: durable job event/audit sidecar, not direct stream or wait outcome unless direct code inspection proves otherwise.
  - Audit requirement: implementation closeout lists retained sidecar messages and confirms they were not counted as direct/wait cleanup.
- Fins wait path:
  - Producer: observation snapshot carries status/result/error facts.
  - Adapter: wait adapter maps typed facts to Host wait outcome and consumes helper for LLM-facing hint/message.
  - LLM-visible path: resumed tool result gets helper text, not adapter-owned hardcoded recovery prose.
- SEC diagnostics path:
  - Producer: downloader reports missing `SEC_USER_AGENT` / config fact.
  - CLI/user docs: command names remain only in CLI/docs owner.
  - User-visible path: downloader warning does not leak CLI command names.

## Risks and open questions

- Web output contract risk: tests or downstream code may rely on `SearchWebOutput` type from `web_search_providers.py`. The implementation must move the public type to `web_search_projection.py`, introduce `SearchWebProviderResult` in `web_search_providers.py`, update imports directly, and avoid compatibility aliases.
- Fins direct text scope risk: `ingestion_runtime.py` contains direct-stream visible text, wait-visible source facts, and durable job sidecar messages. The implementation must classify by propagation path and avoid changing durable job state merely to satisfy a string scan.
- Source scan risk: scans are intentionally narrow evidence checks. They must not be used as the only proof of correctness; tests, helper coverage, and propagation audit remain required.
- Coverage risk: new helper modules require focused tests to meet the single-file coverage target.
- No blocking open question currently prevents implementation.

## Completion report format for implementation gate

Implementation agents must report:

- Changed files.
- Slice IDs completed.
- Source finding disposition changes, if any.
- Tests and pyright commands run with result.
- README decision and any README files changed.
- Source scan results.
- Retained Fins job sidecar text, if any, with propagation-path reason.
- Propagation audit result.
- Residual risks or uncovered areas.
