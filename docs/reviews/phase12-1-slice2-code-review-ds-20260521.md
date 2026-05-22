# Code Review

## Scope

- Mode: current changes (Slice 2 only)
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-1-slice2-code-review-ds-20260521.md`
- Included scope: 本 Slice 接管文件（`dayu/runtime/config_loader.py`、`dayu/runtime/location.py`、`dayu/runtime/__init__.py`、`dayu/config/models.json`、`dayu/config/execution_profiles.json`、`dayu/config/host_runtime.json`、`dayu/config/runtime_lanes.json`、`dayu/config/tool_discovery.json`、`tests/runtime/test_config_loader.py`、`tests/runtime/test_runtime_location.py`、`tests/runtime/test_import_boundary.py`、`tests/runtime/test_weak_typing_guard.py`、`tests/engine/test_config_models.py`、`dayu/config/README.md`、`dayu/README.md`、`tests/README.md`）
- Excluded scope: `README.md`（pre-existing dirty）、`utils/smoke_host_public_multiturn.py`（pre-existing dirty）、Slice 1 文件
- Parallel review coverage: 无

## Verdict: PASS

## Findings

未发现实质性问题。

## Evidence Summary

### 1. Schema Correctness Against Design/Plan

- `RuntimeConfig` 包含五类 view（`models`、`execution_profiles`、`host_runtime`、`runtime_lanes`、`tool_discovery`），与 plan Slice 2.124 行一致。`config_loader.py:530-545`
- `execution_profiles.json` 顶层使用 `default_execution_profile_id` + `execution_profiles` + `agent_policy_profiles`，删除 `runner_options_profiles`/`runner_hints`/`agent_hints`；旧字段 fail fast 有测试覆盖（`test_old_execution_profile_fields_fail_fast`）。
- 旧配置文件 `llm_models.json` 和 `run.json` 已删除，不在文件系统中。`test_legacy_files_do_not_exist_and_are_not_read` 验证旧文件不被读取。
- `host_runtime.json` 使用 `host_execution_lane_name` + `worker_backend`，无内联 lane catalog、`worker_factory_kind`、`prompt_asset_root`、`scene_manifest_root`。

### 2. ID Semantics

- 所有 catalog record id 仅来自 map key（`_FORBIDDEN_RECORD_ID_FIELDS` 包含 `model_id`、`profile_id`、`execution_profile_id`、`provider_id`、`runtime_id`、`host_runtime_id`）。`config_loader.py:1940-1953`
- 六个 parser 函数均调用 `_require_no_forbidden_id_fields`，全覆盖覆盖。`test_embedded_catalog_id_fields_fail_fast` 验证 fail fast。
- extends 校验覆盖：missing target（`test_missing_extends_parent_fails_fast`）、self-reference（`test_self_extends_fails_fast`）、cycle（`test_extends_cycle_fails_fast`）、valid chain A→B→C（`test_single_extends_chain_resolves_to_complete_typed_record`）、invalid type（`test_invalid_extends_type_fails_fast`）、multi-inheritance（`test_multiple_extends_fails_fast`）。

### 3. Runtime Boundary

- `dayu.runtime` 仅 import `dayu.contracts`（`JsonValue`、`ToolBundleSourceKind`），未 import `dayu.engine`/`dayu.host`/`dayu.service`/`dayu.ui`/`dayu.fins`。`test_runtime_does_not_import_business_layers` 通过。
- `ConfigLoader` 不解析 secret（`api_key_ref` 原样保留）、不创建 provider client、不解释 scene manifest、不构造 Host/Engine 对象。`test_secret_and_provider_extension_values_are_preserved_raw` 验证。

### 4. Location Resolver

- `workspace/config` 不存在 → `config_overlay_dir=None`。`test_workspace_config_absent_returns_none_overlay` 验证。
- `prompt_asset_root` 和 `scene_manifest_root` 各自独立 fallback：workspace 有 prompts 目录时用 workspace，否则用 package 默认。`location.py:65-100`
- 未嵌入 `ConfigLoader`/`ScenePrepare` 的 fallback 逻辑。Resolver 只返回路径选择结果。

### 5. Model Migration

- 旧模型源证据直接：`git show 9952fd4:dayu/config/llm_models.json`。
- 27 个模型 id 全部在新 `models.json` 中。`test_default_models_catalog_contains_migrated_legacy_records` 逐 id 验证。
- `provider_request_extension` 作为 JSON DSL 原样保留，不在 `dayu.runtime` 内解释。`test_default_models_keep_provider_extension_raw` 验证。

### 6. Tests and README

- 35 个 runtime 测试 + 4 个 engine 测试全部通过。
- 测试覆盖：happy path（默认配置加载、单继承链、workspace overlay）、fail-fast 路径（cycle、self-ref、multi-inheritance、missing parent、invalid extends type、embedded id fields、旧 schema 字段、fallback_mode 非法值、lane 引用不存在、claim_ttl ≤ heartbeat、import_path/entry_point XOR、JSON shape 错误）、边界条件（workspace partial record 不 deep merge、secret/extension 原样保留）。
- `test_runtime_import_boundary_scan_covers_location_module` 和 `test_runtime_import_boundary_scan_covers_config_loader_module` 确保边界扫描覆盖所有新模块。
- README 变更只更新了 `dayu/runtime` 能力描述和 `dayu/contracts` 契约列表，与当前代码一致。

### 7. Project Rules

- `test_runtime_disallows_weak_typing` 通过，无 `Any`/`object`/裸 builtin 容器。
- 所有公开函数有完整中文 docstring。
- 无兼容性 reader/wrapper。
- pyright：0 errors, 0 warnings, 0 informations。

### 8. Adversarial Failure Pass

- 对 `_resolve_record` 的递归栈管理做了审查：`visiting` 在入栈前检查、递归后 `pop()`，异常安全。`config_loader.py:952-1007`
- 对 `_overlay_roots` 的 workspace scalar 覆盖与 map 合并语义做了审查：workspace partial record 不会与 package deep merge，而是 fail fast（`test_workspace_partial_record_does_not_deep_merge_and_fails` 验证）。
- 对 `_require_exact_fields` 的双向检查（missing + unknown）做了审查：所有 parser 的 `allowed` 集合与 dataclass 字段一致。
- 对 `_parse_tool_discovery_provider` 的 `import_path` XOR `entry_point` 互斥验证做了审查：`(import_path is None) == (entry_point is None)` 正确覆盖两者都设和两者都不设的情况。
- 对 `_parse_runtime_lane` 的 `claim_ttl_seconds > heartbeat_interval_seconds` 校验做了审查：防竞态语义正确。

## Open Questions

无。

## Residual Risk

- `config_loader.py` 单文件 2201 行，包含大量重复性字段校验样板代码。当前结构清晰但在字段增删时需要同步修改 dataclass 定义、parser 函数、`_require_exact_fields` allowed 集合和字段提取行，维护负担较高。非本次 Slice 引入的问题，是显式无 schema 库依赖架构的固有取舍。
- `location.py` 硬编码 `workspace/config` 作为 workspace 覆盖路径，不可配置。plan 明确这是 Service-owned 约定，当前阶段可接受。
- Smoke test（`utils/smoke_host_public_multiturn.py`）因 pre-existing dirty 不在本 Slice scope，端到端装配验证需后续 Slice 完成。
