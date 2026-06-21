# Code Review

## Scope

- Mode: current changes
- Branch: `phase/wu-tools-01-f03-r4`
- Base: `3f7fd44a` (gateflow: accept WU-TOOLS-01-F03-R4 slice 3)
- Output file: `docs/reviews/wu-tools-01-f03-r4-slice4-code-review-mimo.md`
- Included scope: Slice 4 only — `dayu/fins/tools/upload_provider.py`, `dayu/fins/tools/upload_tools.py`, `dayu/config/tool_discovery.json`, `dayu/config/prompts/manifests/*.json`, `tests/fins/test_fins_ingestion_tools.py`, `tests/runtime/test_scene_prepare.py`, `tests/runtime/test_config_loader.py`, `tests/tools/test_combined_tools_acceptance.py`, `dayu/config/README.md`, `dayu/fins/README.md`, `tests/README.md`, `docs/host/issues-implementation-control.md`
- Excluded scope: Slice 5/6 future work, `tests/runtime/test_smoke_host_public_multiturn_assembly.py` (not touched)
- Parallel review coverage: 无

## Verification

- `pytest tests/fins/test_fins_ingestion_tools.py tests/runtime/test_scene_prepare.py tests/runtime/test_config_loader.py tests/tools/test_combined_tools_acceptance.py -q`: **127 passed**, 3 upstream `edgar` deprecation warnings
- `pyright dayu tests utils`: **0 errors, 0 warnings, 0 informations**
- `rg -n "allowed_upload_roots|_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD|parse_allowed_upload_roots_config" dayu tests utils`: only `tests/runtime/test_config_loader.py:413` (negative assertion confirming absence)
- `rg -n '"fins"' dayu/config/prompts/manifests/`: no results (no broad fins tag in any manifest)
- `rg -n "fins-upload" dayu/config/prompts/manifests/`: no results (no fins-upload tag in any manifest)
- `rg -n "ingestion" dayu/config/prompts/manifests/`: no results (no stale ingestion tag in any manifest)

## Findings

未发现实质性问题。

逐项验证结果如下：

### Focus 1: Upload provider removes `allowed_upload_roots` entirely, always registers `start_fins_upload`

- ✅ `_CONFIG_ALLOWED_UPLOAD_ROOTS_FIELD` constant deleted (`upload_provider.py`)
- ✅ `parse_allowed_upload_roots_config(...)` function deleted (`upload_provider.py`)
- ✅ `Mapping`, `Path`, `JsonValue` imports removed (no longer needed)
- ✅ `__all__` no longer exports parser (`upload_provider.py:70`)
- ✅ `discover_tools(...)` has no early-return empty-definitions path; always calls `build_fins_upload_tool(ingestion_runtime)` (`upload_provider.py:39-46`)
- ✅ Missing `workspace_root` still raises `ValueError` via `parse_fins_workspace_root_config` (`upload_provider.py:36`)
- ✅ Test `test_upload_provider_registers_upload_tool_without_local_file_roots` proves tool registration without `allowed_upload_roots` (`test_fins_ingestion_tools.py:706-724`)
- ✅ Test `test_upload_provider_rejects_missing_workspace_root` proves fail-fast on empty config (`test_fins_ingestion_tools.py:727-740`)

### Focus 2: Upload tool removes allowlist containment, preserves validation

- ✅ `FinsUploadToolCallable.allowed_upload_roots` attribute removed (`upload_tools.py:64-72`)
- ✅ `build_fins_upload_tool(...)` no longer accepts `allowed_upload_roots` (`upload_tools.py:133`)
- ✅ `_normalize_allowed_upload_roots(...)` function deleted
- ✅ `_resolve_upload_path(...)` replaced by `_resolve_upload_file_path(raw_path)` — no allowlist check (`upload_tools.py:409-427`)
- ✅ Delete action still forbids files (`upload_tools.py:400-402`)
- ✅ Auto/create/update still require at least one file (`upload_tools.py:404-405`)
- ✅ `_resolve_upload_file_path` validates: `is_file()` and `st_size > 0` (`upload_tools.py:423-426`)
- ✅ Test `test_upload_tool_missing_file_returns_failed_outcome_before_observation_start` covers missing file (`test_fins_ingestion_tools.py:864-896`)
- ✅ Test `test_upload_tool_directory_returns_failed_outcome_before_observation_start` covers directory path (`test_fins_ingestion_tools.py:899-931`)
- ✅ Test `test_upload_tool_empty_file_returns_failed_outcome_before_observation_start` covers empty file (`test_fins_ingestion_tools.py:969-1002`)
- ✅ Test `test_upload_tool_delete_rejects_unnecessary_files_before_job_creation` covers delete-with-files (`test_fins_ingestion_tools.py:1005-`)

### Focus 3: Repository/write boundary preserved

- ✅ Local file path remains source input only — no destination path is caller-controlled in `_resolve_upload_file_path` or `_upload_request_from_arguments`
- ✅ Test `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` proves workspace-external file accepted as source input with no `.dayu` governance state written to source directory (`test_fins_ingestion_tools.py:934-966`)
- ✅ Failure-path tests assert `not tuple(_job_store_root(workspace_root).glob("*.json"))` — verifies no job-store writes before observation starts; not obsolete since these are pre-observation failure paths
- ✅ No test asserts job-store internals (job record structure, event sidecar content, sequence numbers)

### Focus 4: Packaged config correct

- ✅ `tool_discovery.json`: `financial-upload-tools.enabled = true` (`tool_discovery.json:50`)
- ✅ `financial-upload-tools.config` contains only `{"workspace_root": "workspace/"}` — no `allowed_upload_roots`
- ✅ Test `test_default_runtime_config_files_load_as_typed_views` asserts `upload_provider.enabled is True` and `"allowed_upload_roots" not in upload_provider.config` (`test_config_loader.py:411-413`)

### Focus 5: Default manifests avoid `start_fins_upload` selection

- ✅ All 10 non-upload scenes (confirm, decision, fix, infer, interactive, prompt, regenerate, repair, wechat, write) use explicit `tool_names` listing read/download/preprocess tools — no broad `"fins"` or `"ingestion"` tag
- ✅ No manifest contains `"fins-upload"` tag
- ✅ `tool_selection.allow_empty` remains `false` in all manifests
- ✅ `infer` manifest has `tool_tags_any: []` (no web); all others have `tool_tags_any: ["web"]` — correct per design
- ✅ Test `test_default_non_upload_scenes_do_not_select_upload_tool` iterates all 10 scenes, asserts `start_fins_upload` not in selected tools, asserts all Fins read/download/preprocess tools present, and asserts web tools present where `tool_tags_any` includes `"web"` (`test_scene_prepare.py:366-388`)

### Focus 6: LLM-facing upload schema text

- ✅ `files.description`: `"Local file paths to upload. Each path must point to an existing non-empty regular file. Required for auto, create and update; forbidden for delete."` — self-explanatory, no mention of configured roots (`upload_tools.py:229`)
- ✅ Tool description: clear about immediate return, observation handle, and use case (`upload_tools.py:153-158`)
- ✅ Error hint covers validation dimensions (`upload_tools.py:112`)

### Focus 7: README updates

- ✅ `dayu/config/README.md`: removed `allowed_upload_roots` description, updated upload provider default behavior, updated doc-tools default `enabled=false` — all direct-trigger sync for Slice 4 changes
- ✅ `dayu/fins/README.md`: removed allowlist references throughout, updated workspace rules, updated provider fail-fast description — all direct-trigger sync
- ✅ `tests/README.md`: updated test coverage description for upload provider — direct-trigger sync
- ✅ No docs overrun detected; changes are minimal factual corrections to match code
- ✅ `docs/host/issues-implementation-control.md`: gateflow status update — standard work-unit tracking

### Focus 8: Tests/pyright/rg sufficiency

- ✅ pyright: 0 errors
- ✅ rg: no stale `allowed_upload_roots` references in production code
- ✅ New `_NoOpExecutor` test double properly records submitted job IDs without side effects (`test_fins_ingestion_tools.py:574-608`)
- ✅ `_upload_spec` helper correctly simplified — no `allowed_upload_roots` parameter (`test_fins_ingestion_tools.py:1798-1818`)
- ✅ `_write_split_fins_provider_overlay` correctly simplified — no `upload_root` parameter (`test_fins_ingestion_tools.py:1663-1712`)
- ✅ Combined tools acceptance test correctly updated: `start_fins_upload` added to `_FINS_AWAITING_TOOL_NAMES`, source refs count updated from 5 to 6 (`test_combined_tools_acceptance.py:98-101, 214`)

## Open Questions

无。

## Residual Risk

- 本 Slice 不实现 Host policy、sandbox 或统一本地文件授权；upload tool 只做输入文件形态校验。这是 plan 中明确的 non-goal。
- `test_upload_tool_accepts_local_file_outside_workspace_without_source_side_effect` 覆盖 observation 启动边界与源目录无治理状态副作用，不执行真实 Docling upload conversion。真实 repository 写入边界由既有 Fins upload pipeline / storage 测试覆盖。
- `_resolve_upload_file_path` 中 `is_file()` 与 `stat().st_size` 之间存在 TOCTOU 窗口（文件可能在检查后被删除）。这是设计固有约束，不在本 Slice 范围内。
