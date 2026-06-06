# WU-TOOLS-01 Slice S6 Implementation

Gate: implementation
Work unit: WU-TOOLS-01
Slice: S6 - Combined Discovery / ToolRuntime Acceptance / Docs Closure
Agent: AgentCodex
Status: implementation complete; required full pytest currently blocked by existing Host failures outside S6 allowed scope; stopped before review / re-review / commit / push / PR

## Scope

- 新增 combined acceptance 测试，使用确定性 workspace config 同时启用 Doc、Fins 与 Web providers。
- 证明三个 provider 经当前 `ToolsDiscovery` 聚合为一个业务 `ToolBundle`，无重复工具名，且业务工具不占用 reserved `fetch_more`。
- 证明迁移工具的截断声明均为当前 `ToolTruncateSpec`；`FrameworkToolName.FETCH_MORE` 仍由当前 Host ToolRuntime 在 effective bundle 中注入并拥有。
- 证明 Service assembly 把 effective tool bundle 传入 `HostToolingOptions.business_tool_bundle`，Host 不重新发现或改写工具来源。
- 证明 current ToolRuntime 能执行 Doc、Fins、Web 代表工具，并通过 Host accept barrier 记录 accepted facts。
- 证明代表性输入投影 / coercion / validation 与 response projection 输出 current `ToolCompletedOutcome` / `ToolFailedOutcome`，不出现 OLD `ok/value` 成功 envelope。
- 证明 `ScenePrepare` 可通过 `doc`、`fins`、`web` tags 选择迁移工具。
- 证明 Web provider 的 `SERIAL_PER_PROVIDER` policy 在并发 callable 下串行生效。

Non-goals kept:

- 未迁移 OLD `ToolRegistry`、OLD `TruncationManager`、OLD `fetch_more` 或 OLD truncate/fetch-more projection。
- 未新增旧 registry / truncation / fetch_more 兼容代码。
- 未做 live model call、live external network、UI/CLI workflow implementation。

## Evidence

- `tests/tools/test_combined_tools_acceptance.py`
  - `test_combined_discovery_returns_single_bundle_without_reserved_names`：通过 `ConfigLoader` + `discover_service_tools` 的 fixture config 同时启用 `dayu.fins.tools:discover_tools`、`dayu.tools.doc_provider:discover_tools`、`dayu.tools.web:discover_tools`，断言单一 bundle 名称顺序为 Fins + Doc + Web，且不含 `fetch_more`。
  - `test_combined_truncate_specs_and_fetch_more_owner`：断言所有 truncating migrated definitions 的 `truncate` 精确类型为当前 `ToolTruncateSpec`；启用 current truncation manager 与 framework tool policy 后，`fetch_more` 只出现在 ToolRuntime effective bundle，callable 为 `FetchMoreToolCallable`。
  - `test_migrated_providers_and_adapter_do_not_import_old_runtime`：AST 扫描 `_legacy_adapter`、Doc provider/tools、Fins tools、Web tools，阻止 OLD registry / truncation / fetch_more import，并扫描 `project_for_llm`、`fetch_more_args`、`continuation_hint` 等 OLD projection token。
  - `test_compose_open_host_options_passes_effective_bundle_to_host`：断言 `compose_open_host_options` 返回的 `effective_tool_bundle` 与 `OpenHostOptions.tooling_options.business_tool_bundle` 是同一对象，并保留 discovered source refs。
  - `test_toolruntime_executes_representative_provider_tools_and_accepts_facts`：同一个 ToolRuntime 执行 `read_file`、`list_documents`、`search_web`，accept barrier 记录三条 accepted candidates；Doc 路径投影为绝对路径，Web `recency_days=7.0` / `max_results=3.0` coercion 为整数，三个成功值均无 OLD `ok` envelope。
  - `test_representative_failures_project_to_current_failed_outcomes`：代表性 Doc / Fins / Web 参数失败均返回 current `ToolFailedOutcome`。
  - `test_scene_prepare_tags_select_doc_fins_and_web_tools`：`tool_tags_any=["doc", "fins", "web"]` 能选择 `read_file`、`list_documents`、`search_web`。
  - `test_web_provider_serial_policy_holds_under_concurrent_calls`：并发调用同一 Web provider callable 时，provider-level lock 使 `max_active_calls == 1`。
- `tests/README.md`
  - 同步 `tests/tools/` 当前职责，补充 combined tools acceptance 覆盖范围与 deterministic/no-live-network 边界。

## Residual Closure / Defer Decisions

- `WU-TOOLS-01-R1 path safety adapter`：closed for WU-TOOLS-01 implementation evidence. S3 已证明 Doc path whitelist fail-closed；S6 进一步证明 combined ToolRuntime 执行 `read_file` 时路径参数由 adapter 投影为白名单内绝对路径。
- `WU-TOOLS-01-R2 typed config adapter`：closed for WU-TOOLS-01 implementation evidence. S6 使用 workspace `tool_discovery.json` fixture 向三个 provider 传入 typed provider-owned config，Service/runtime 只透传 JSON config，不解释业务语义。
- `WU-TOOLS-01-R3 ToolDiscovery / ToolRuntime adapter`：closed. S6 证明三个 provider 通过当前 `ToolsDiscovery` 聚合后，由 Host-owned ToolRuntime 执行并写入 accept barrier。
- `WU-TOOLS-01-R4 truncation / fetch_more owner`：closed. S6 证明业务 bundle 不含 reserved `fetch_more`，迁移工具只暴露 current `ToolTruncateSpec`，current ToolRuntime 在 effective bundle 中注入 `FetchMoreToolCallable`。
- `WU-TOOLS-01-R5 query / response projection adapter`：closed for migrated read/search/fetch acceptance surface. S3/S4/S5 已分别覆盖 provider 细节；S6 组合验证 direct pass-through、path projection、numeric coercion、validation failure 与 current outcome projection。
- `WU-TOOLS-01-S3-R1 response projector placement`：closed as no longer triggered. S4/S5 没有把更多 provider-specific response projector 分支塞进 `_legacy_adapter`；S6 扫描与 combined outcome 证明当前 projection 未扩散为 OLD projection owner。
- `WU-TOOLS-01-S4-R1 Fins ingestion waiting semantics`：deferred with owner. S4 已 fail-closed `include_ingestion_tools=true`，S6 combined acceptance 只覆盖 read tools。Remaining owner/destination: later WU-TOOLS follow-up or Host ToolRuntime wait-adapter work unit for durable awaiting / polling / cancel / late terminal result semantics.
- `WU-TOOLS-01-S5-R1 Web provider concurrency policy`：closed for current policy. S6 并发 callable 测试证明 `SERIAL_PER_PROVIDER` policy 生效。若未来要放宽为并发执行，需要独立 provider concurrency hardening 和 shared session / Playwright fallback 证据。
- `WU-TOOLS-01-S5-R2 Web live network / real browser coverage`：deferred with owner. S6 按用户硬约束继续 deterministic/no-live-network/no-real-browser。Remaining owner/destination: later optional integration-test work unit with explicit live network/browser credentials and policy.
- `WU-TOOLS-01-S1-R1 documents coverage / parity`：partially closed for consumed paths. S3/S6 Doc Markdown path、S3 Docling JSON fixture、S4/S6 Fins Markdown processor path、S5 Web mocked HTML/fetch paths cover currently consumed lightweight foundations. Full OLD parity / real PDF-OCR / heavy Docling runtime remains deferred to a dedicated documents parity or provider integration work unit if required.

No unclassified residual remains.

## README / Docs

- Updated `tests/README.md` because `tests/tools/` stable coverage now includes combined provider acceptance.
- No update to root `README.md`: no user-facing command, configuration entry, CLI workflow or trace/render entry changed.
- No update to `dayu/README.md`, `dayu/host/README.md`, `dayu/engine/README.md`, `dayu/fins/README.md`, or `dayu/config/README.md`: no production boundary, Host/Engine contract, Fins public interface, or packaged config schema changed in S6.

## Validation

- `source .venv/bin/activate && pytest tests/tools/test_combined_tools_acceptance.py`
  - 8 passed; 3 third-party `edgar` deprecation warnings.
- `source .venv/bin/activate && pyright tests/tools/test_combined_tools_acceptance.py`
  - 0 errors, 0 warnings, 0 informations.
- `source .venv/bin/activate && pytest tests/runtime tests/service tests/tools tests/fins tests/host`
  - 1548 passed, 1 skipped, 5 deselected, 13 failed, 3 third-party `edgar` deprecation warnings.
  - Runtime / Service / Tools / Fins portions passed, including `tests/tools/test_combined_tools_acceptance.py`.
  - Failures are in pre-existing Host suites outside S6 allowed production modules:
    - `tests/host/test_dispatch_scheduler.py::test_pre_start_governance_soft_threshold_compacts_before_attempt`
    - `tests/host/test_dispatch_scheduler.py::test_proactive_compaction_uses_selected_material_not_session_start_range`
    - `tests/host/test_dispatch_scheduler.py::test_proactive_material_pack_not_larger_than_ordinary_material_for_same_view`
    - `tests/host/test_dispatch_scheduler.py::test_wake_queue_promotion_uses_tracked_async_promotion_task`
    - `tests/host/test_dispatch_scheduler.py::test_proactive_compaction_calls_llm_outside_write_transaction`
    - `tests/host/test_dispatch_scheduler.py::test_proactive_compaction_retries_quality_rejection_before_accept`
    - `tests/host/test_dispatch_scheduler.py::test_multi_turn_proactive_compact_feeds_subsequent_run_input`
    - `tests/host/test_effective_execution_config.py::test_field_level_partial_merge_uses_baseline_for_omitted_fields`
    - `tests/host/test_effective_execution_config.py::test_descriptor_payload_dispatch_uses_per_run_override`
    - `tests/host/test_import_boundary.py::test_fetch_more_token_stays_inside_toolruntime_owner_modules`
    - `tests/host/test_import_boundary.py::test_host_engine_imports_stay_on_allowed_boundary_modules`
    - `tests/host/test_phase7_waiting_integration.py::test_local_awaiting_tool_manual_resolve_resumes_run`
    - `tests/host/test_resolve_wait_command.py::test_resolve_wait_completed_resumes_run_and_wakes_dispatch`
  - Direct failure signatures:
    - proactive compaction tests fail with `RuntimeError: accepted compaction is missing proposal manifest ref`.
    - effective execution config tests still expect raw system prompt, while current RunInputBuilder wraps it in the one-system-message envelope.
    - Host import boundary tests still forbid tokens/imports that current accepted code already contains: `_legacy_adapter` references reserved `fetch_more` to reject business exposure; `dayu.host.compaction_operation` imports Engine contract modules.
    - wait resume tests no longer find the old `"Accepted wait result fact:"` text in resume request messages.
  - No failure came from the new combined acceptance test or from Doc/Fins/Web provider ToolRuntime execution.
- `source .venv/bin/activate && pyright`
  - 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Passed; no whitespace errors.

## Validation Blocker Classification

The required combined acceptance objective is satisfied by the new S6 tests. The only failed required command is the broad `tests/host` regression set, and the failure signatures point to Host compaction / one-system-message / wait-resume / import-boundary expectations that are outside the S6 allowed production modules and were not introduced by this slice. I did not modify Host production code or weaken Host tests in this implementation gate.
