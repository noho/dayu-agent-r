# Phase 12.1 Slice 2 Code Review

## Scope

- Mode: role-scoped code review handoff
- Branch: `docs/phase12-design-discussion`
- Base: `main`
- Output file: `docs/reviews/phase12-1-slice2-code-review-mimo-20260521.md`
- Review date: 2026-05-21
- Work unit: Phase 12.1 runtime assembly schema / public contract correction follow-up
- Gate: Slice 2 code review
- Design source: `docs/host/design.md`
- Control doc: `docs/host/implementation-control.md`
- Plan: `docs/host/phase12-1-runtime-assembly-correction-plan.md`
- Implementation artifact: `docs/reviews/phase12-1-slice2-implementation-codex-20260521.md`
- Included scope: Slice 2 owned files — `dayu/runtime/config_loader.py`、`dayu/runtime/location.py`、`dayu/runtime/__init__.py`、`dayu/config/models.json`、`dayu/config/execution_profiles.json`、`dayu/config/host_runtime.json`、`dayu/config/runtime_lanes.json`、`dayu/config/tool_discovery.json`、`tests/runtime/test_config_loader.py`、`tests/runtime/test_runtime_location.py`、`tests/runtime/test_import_boundary.py`、`tests/engine/test_config_models.py`、`dayu/config/README.md`、`dayu/README.md`、`tests/README.md`
- Excluded scope: `README.md`、`utils/smoke_host_public_multiturn.py`（pre-existing dirty，非本 Slice 范围）
- Parallel review coverage: 无

## Verdict

**PASS**

未发现实质性问题。

## Findings

### 审查过程与证据

#### 1. Schema 正确性

- `RuntimeConfig` 包含五个 typed view：`models`、`execution_profiles`、`host_runtime`、`runtime_lanes`、`tool_discovery`（`config_loader.py:531-545`）。
- `execution_profiles.json` 顶层字段为 `default_execution_profile_id`、`execution_profiles`、`agent_policy_profiles`，默认 id 为 `standard`。
- `host_runtime.json` 顶层字段为 `default_host_runtime_id`、`runtimes`，无内联 lane catalog、`worker_factory_kind`、`prompt_asset_root`、`scene_manifest_root`。
- `runtime_lanes.json` 为独立文件，包含 `coordinator` 与 `lanes`。
- 旧 `llm_models.json` 与 `run.json` 已从工作树删除，`_LEGACY_CONFIG_FILES` 集合用于 fail-fast 诊断（`config_loader.py:25-27`），不提供兼容读取。
- `_require_exact_fields` 确保未知字段 fail fast（`config_loader.py:1919-1937`）。

#### 2. ID 语义

- 所有 catalog record id 只来自 map key，通过 `_parse_*` 函数的 `record_id` 参数注入 typed dataclass。
- `_FORBIDDEN_RECORD_ID_FIELDS` 包含 `runtime_id`、`host_runtime_id`、`model_id`、`profile_id`、`execution_profile_id`、`provider_id`（`config_loader.py:42-51`）。
- `_require_no_forbidden_id_fields` 在所有 catalog record 解析前调用，出现重复 id 字段即 `ConfigFieldError`（`config_loader.py:1940-1953`）。
- `extends` validation 覆盖：missing target（`config_loader.py:990-993`）、self-reference（`config_loader.py:988-989`）、cycle（`config_loader.py:974-976`）、valid chain（递归解析，`config_loader.py:952-1007`）、invalid type / multi-inheritance（`config_loader.py:1022-1028`）。
- 测试覆盖全部 extends 错误路径：`test_extends_cycle_fails_fast`、`test_self_extends_fails_fast`、`test_multiple_extends_fails_fast`、`test_missing_extends_parent_fails_fast`、`test_invalid_extends_type_fails_fast`。

#### 3. Runtime 边界

- `dayu.runtime` 不 import `dayu.engine` / `dayu.host` / `dayu.service` / `dayu.ui` / `dayu.fins`。`config_loader.py` 只 import `dayu.contracts.JsonValue` 与 `dayu.contracts.ToolBundleSourceKind`，均为公共契约。
- `ConfigLoader` 不解析 secret（`api_key_ref` 按字符串原样保留，`config_loader.py:1075`），不创建 provider client，不解释 scene manifest，不构造 Host/Engine 对象。
- `location.py` 只依赖 `pathlib.Path` 和 `dataclasses`，不 import 任何业务层。
- `test_import_boundary.py` AST 扫描覆盖 `dayu/runtime/` 下所有 `.py` 文件，确认无反向依赖，并显式确认 `location.py` 在扫描范围内。

#### 4. Location Resolver

- `resolve_runtime_locations` 输入 `project_root` 与 `package_config_root`，输出 `RuntimeLocations` dataclass（`location.py:32-62`）。
- `workspace/config` 不存在时 `config_overlay_dir=None`（`location.py:44-45`）。
- prompt asset root 和 scene manifest root 解析逻辑：workspace prompts 存在则用 workspace，否则用 package 默认（`location.py:65-100`）。
- `_resolve_prompt_asset_root` 与 `_resolve_scene_manifest_root` 不嵌入 ConfigLoader 或 ScenePrepare fallback，只做纯路径解析。
- 测试覆盖：workspace absent、workspace with prompts、workspace without prompts、missing package assets。

#### 5. 模型迁移

- 旧模型源 `9952fd4:dayu/config/llm_models.json` 可直接访问（implementation artifact 记录）。
- 迁移后 `models.json` 包含 27 个模型 id，与 implementation artifact 中的迁移清单完全一致。
- `provider_request_extension` 按 JSON DSL 原样保留，`dayu.runtime` 未 import Engine typed provider extension。
- `runtime_hints.runner_option_hints` 每个 hint 包含完整 `temperature`、`max_tokens`、`top_p`、`stream` 字段。
- `test_config_models.py` 验证全量模型 id 集合、provider DSL 原样保留和 runner option hints 存在。

#### 6. 测试与 README

- 35 个 runtime 测试全部通过（`test_config_loader.py` 18 个、`test_runtime_location.py` 4 个、`test_import_boundary.py` 12 个、`test_weak_typing_guard.py` 1 个）。
- 4 个 engine config models 测试全部通过。
- 测试覆盖 happy path 与关键 fail-fast 路径：extends 错误、embedded id、old fields、fallback mode、lane reference、claim TTL vs heartbeat、XOR import_path/entry_point、JSON shape error。
- `dayu/config/README.md` 准确描述新 schema、workspace overlay、prompts 目录职责，无旧术语残留。
- `dayu/README.md` 的 `dayu.runtime` 稳定边界描述已更新为五类 config view、`location`、`scene_prepare`、`tools_discovery`、`tool_truncation`。
- `tests/README.md` 已同步 runtime config loader 与 runtime location 测试事实。

#### 7. 项目规则

- 全部 dataclass 使用 `frozen=True, slots=True`。
- 全部函数和类提供中文 docstring，包含参数、返回值、异常。
- 无 `Any`、`object`、无类型参数或无类型返回值。
- 无兼容性 re-export、wrapper 或 facade。
- pyright：0 errors, 0 warnings, 0 informations。
- `git diff --check`：clean。

## Open Questions

无。

## Residual Risk

- `README.md` 与 `utils/smoke_host_public_multiturn.py` 仍是前序 out-of-scope dirty，本 Slice 未接管。
- `ScenePrepare` schema 仍属 Slice 3，本 Slice 只新增 location resolver。
- `provider_request_extension` JSON DSL 到 Engine typed provider extension 的 fail-closed adapter 属于后续 Slice 4。
- `runtime_hints.runner_option_hints` 迁移时为旧 temperature profiles 补齐了 `max_tokens`、`top_p`、`stream` 默认值，后续 Service/composition helper 可继续细化。

## Tests Run and Results

| 命令 | 结果 |
|---|---|
| `pytest tests/runtime/test_config_loader.py tests/runtime/test_runtime_location.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 35 passed in 0.84s |
| `pytest tests/engine/test_config_models.py -q` | 4 passed in 0.10s |
| `python -m pyright dayu/runtime tests/runtime tests/engine/test_config_models.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | clean（无输出） |
