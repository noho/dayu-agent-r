# WU-TOOLS-01-F03-R4 Slice 1 Implementation Artifact

## Gate / Scope

- Work unit: `WU-TOOLS-01-F03-R4 Tools Discovery Spec Semantics Cleanup`
- Gate: `implementation`
- Slice: `Slice 1 - Packaged schema and generic provider spec cleanup`
- Agent: Codex
- Date: 2026-06-21

本轮只实现 Slice 1。未进入 Fins provider、Doc provider、upload callable、scene manifest、design doc、README、总控文档、code review、commit、push 或 PR。

## Changed Files

Production / config:

- `dayu/config/tool_discovery.json`
- `dayu/runtime/config_loader.py`
- `dayu/runtime/tools_discovery.py`
- `dayu/service/host_assembly.py`

Tests / helper callers updated because `allow_empty` constructor field was removed:

- `tests/runtime/test_config_loader.py`
- `tests/runtime/test_tools_discovery.py`
- `tests/runtime/test_tools_discovery_digest.py`
- `tests/runtime/test_smoke_host_public_multiturn_assembly.py`
- `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
- `tests/service/test_host_assembly.py`
- `tests/service/test_entrypoint_runtime.py`
- `tests/tools/test_combined_tools_acceptance.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `utils/diagnose_web_access.py`

## Behavior Changes

- `tool_discovery.providers.<provider_id>.allow_empty` 从 packaged config、`ToolDiscoveryProviderConfig`、`ToolsDiscoveryProviderSpec` 和 Service mapping 中删除。
- `ConfigLoader` 不再允许 provider record 带 `allow_empty` 字段；旧 schema 会以 unknown fields fail fast。
- `ToolsDiscovery` 对所有被调用 provider 的空 `definitions` 统一 fail fast；保留最终空 `ToolBundle(definitions=(), _allow_empty=True)` 仅用于没有启用 provider 被调用的场景。
- packaged `financial-read-tools.config.workspace_root`、download、preprocess、upload workspace root 改为 `"workspace/"`；ConfigLoader 仍原样保留字符串。
- packaged `financial-read-tools.config.include_read_tools` 已删除。
- packaged `financial-upload-tools.config.allowed_upload_roots` 已删除。
- packaged `financial-read-tools.config.limits` 与 `doc-tools.config.limits` 已填入 OLD `run.json` 默认值。
- packaged `doc-tools.enabled=false`。
- 为满足 Slice 1 “Service tool discovery 可调用”，Service effective config 会把 Fins provider 的相对 `config.workspace_root` 解析为 runtime `workspace_root` 下的绝对路径，provider 仍只接收绝对路径。
- packaged `financial-upload-tools.enabled=false`。原因是本 slice 不允许修改 upload provider；删除 `allowed_upload_roots` 后旧 upload provider 会返回空 definitions，并被新的 generic invariant 正确拒绝。后续 upload provider slice 需要移除 provider 内 allowlist 逻辑并恢复默认注册。

## Validation

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py -q`
  - Result: `41 passed in 0.10s`
- `source .venv/bin/activate && pytest tests/runtime/test_tools_discovery.py tests/runtime/test_tools_discovery_digest.py -q`
  - Result: `19 passed in 0.04s`
- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/runtime/test_smoke_host_public_multiturn_assembly.py -q`
  - Result: `54 passed, 3 warnings in 1.89s`
  - Warnings: upstream `edgar` deprecation warnings only.
- `source .venv/bin/activate && pytest tests/tools/test_combined_tools_acceptance.py -q`
  - Result: `8 passed, 3 warnings in 1.45s`
  - Warnings: upstream `edgar` deprecation warnings only.
- `source .venv/bin/activate && pyright dayu tests utils`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Tool note: pyright reported newer version available `v1.1.409 -> v1.1.410`.

## README / Docs Decision

- `dayu/config/` changed, so `dayu/config/README.md` must be updated in the later docs slice to remove provider-level `allow_empty`, `include_read_tools`, upload `allowed_upload_roots`, and to document packaged limits / workspace semantics.
- `dayu/service/` and `dayu/runtime/` semantics changed; later docs/design slice should update the relevant ToolsDiscovery and Service effective config wording.
- `tests/` changed, so `tests/README.md` should be updated in the later docs slice if it still describes `include_read_tools=false`, upload empty allowlist behavior, or provider-level `allow_empty`.
- README files were not modified in this slice because the user explicitly forbade README modifications and the approved work unit reserves docs/design cleanup for later slices.
- `docs/host/issues-implementation-control.md` was only read. It already had pre-existing uncommitted changes and was not modified by this implementation.

## Residual Risks / Uncovered Areas

- Covered by later approved slice: upload provider still contains old `allowed_upload_roots` behavior; packaged upload is disabled in this slice to keep Service discovery callable until that provider is cleaned up.
- Covered by later approved slice: Fins read provider still understands `include_read_tools` internally; packaged/test discovery config no longer uses it, but provider cleanup remains future work.
- Covered by later approved slice: Doc provider still returns empty definitions for enabled empty `allowed_paths`; packaged doc-tools is disabled here, and provider-specific fail-fast remains future work.
- Covered by later approved slice: scene manifest exposure for future upload default registration was not changed.
- Covered by later docs slice: README/design documentation still describes old fields in places.

## Completion Status

Slice 1 implementation, validation, and artifact are complete.

No commit, push, PR, code review, deepreview, or later slice work was performed.

