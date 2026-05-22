# Phase 12 Slice 3 Implementation Report

## 基本信息

- Current gate: Phase 12 Slice 3 implementation
- Work unit: ToolsDiscovery / ScenePrepare / ConfigLoader runtime assembly
- Assigned slice: ConfigLoader typed config loading / validation and legacy config removal
- Agent role: AgentCodex implementation handoff
- Design source: `docs/host/design.md`
- Plan source: `docs/host/phase12-runtime-assembly-plan.md`

## 变更摘要

- 新增 `dayu.runtime.config_loader`，提供层中立 `ConfigLoader`、四类 typed config view dataclasses、结构化配置错误、包内默认配置加载、调用方显式 workspace 覆盖、顶层 map 按稳定 id overlay、单继承 `extends` 解析与字段校验。
- 新增四个默认配置文件：`models.json`、`execution_profiles.json`、`host_runtime.json`、`tool_discovery.json`。
- 删除旧 `dayu/config/llm_models.json` 与 `dayu/config/run.json`，未保留兼容读取、兼容 wrapper 或旧名 re-export。
- 新增 `tests/runtime/test_config_loader.py`，覆盖默认加载、workspace 整条替换、单继承成功、循环继承失败、多继承失败、partial record 不 deep merge、secret/provider extension 原样保留、旧文件不读取和工具发现 provider 二选一校验。
- 迁移旧 Engine 配置测试为 `tests/engine/test_config_models.py`，避免继续读取旧配置文件。
- 更新 runtime import boundary 测试，确认扫描覆盖 `config_loader.py`。

## 架构边界说明

- `dayu.runtime.config_loader` 只 import 标准库与 `dayu.contracts` 中的 `JsonValue`、`ToolBundleSourceKind`。
- ConfigLoader 不 import `dayu.host`、`dayu.engine`、`dayu.service`、`dayu.ui`、`dayu.fins` 或具体业务工具包。
- ConfigLoader 不构造 Host、不创建 provider client、不解释 scene manifest、不读取 Fins storage、不做工具 import 或 discovery。
- `api_key_ref`、`headers`、`provider_request_extension` 按 JSON 配置原样进入 typed view；实现不解析环境变量、不替换 secret、不脱敏。
- workspace overlay 只在顶层 map 按 id 合并；同 id 记录整条替换，不做隐式 deep merge。配置复用只通过显式单继承 `extends`。

## 测试结果

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - 结果：17 passed
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime`
  - 结果：0 errors, 0 warnings, 0 informations
- `source .venv/bin/activate && pytest tests/engine/test_config_models.py tests/engine/test_smoke_async_agent_providers.py -q`
  - 结果：9 passed
- `source .venv/bin/activate && python -m pyright tests/engine/test_config_models.py`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：通过，无 whitespace error

## README 同步

- 更新 `dayu/config/README.md`：同步四类新配置职责、overlay / extends 规则、旧配置删除事实、ConfigLoader 边界和最小 workspace 覆盖示例。
- 更新根目录 `README.md`：清理旧 `workspace/config/llm_models.json` / `run.json` 用户入口，改为 `models.json`、`execution_profiles.json`、`host_runtime.json`、`tool_discovery.json`。
- 更新 `dayu/README.md`：在 runtime 稳定边界中加入 `config_loader`。
- 更新 `tests/README.md`：补充 runtime config loader 测试职责。

## 未覆盖风险

- 本 slice 只输出 typed config view，不实现 Service 将其映射为 `RunnerSpec`、`RunnerCallOptions`、`AgentPolicy` 或 `OpenHostOptions` 的装配逻辑；该风险属于后续 Service / composition root slice。
- `tool_discovery.json` 默认 provider 只作为 typed spec 示例读取，当前 slice 不验证该 import path 对应 provider 是否存在；provider import 与聚合由 `ToolsDiscovery` slice 负责。
- Scene manifest 和 prompt asset 仍属于后续 `ScenePrepare` / asset migration slice，本 slice 不读取或验证 prompts 目录内容。

## 完成状态

Slice 3 implementation scope 已完成，未执行 commit、push、开 PR 或进入下一 gate。

## Fix addendum — Phase 12 Slice 3 test hardening

### Fix scope

- 仅修改 `tests/runtime/test_config_loader.py`、`tests/engine/test_config_models.py` 与本文档。
- 未修改生产 schema、默认配置或 `dayu.runtime.config_loader` 实现。
- 未执行 commit、push、开 PR 或进入下一 gate。

### Review findings 修复状态

- P12-S3-F1 missing-parent `extends` branch lacks regression coverage：已修复。新增 `test_missing_extends_parent_fails_fast`，断言缺失父项抛出 `ConfigExtendsError` 且错误片段包含 `missing parent`。
- P12-S3-F2 `test_default_models_do_not_use_extra_payloads_bag` assertion does not match its name：已修复。测试改为检查 typed `ModelConfig` dataclass 字段集合不包含 `extra_payloads`，并确认保留显式 typed 字段 `provider_request_extension`，不再用 `provider_request_extension is not None` 表达弱类型 bag 语义。
- P12-S3-F3 non-map top-level workspace overlay lacks regression coverage：已修复。新增 `test_workspace_non_map_top_level_field_overrides_package_default`，覆盖 workspace 覆盖 `default_profile_id` 并指向 workspace 新增 profile。
- P12-S3-F4 additional validation branches lack focused tests：已修复当前裁决范围。新增 `test_invalid_extends_type_fails_fast` 覆盖 `extends` 为 number、bool、object 的非法类型；新增 `test_lane_capacity_claim_ttl_must_exceed_heartbeat` 覆盖 `claim_ttl_seconds <= heartbeat_interval_seconds` 抛出 `ConfigFieldError`。

### 验证结果

- `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/engine/test_config_models.py -q`
  - 结果：18 passed
- `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q`
  - 结果：7 passed
- `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime tests/engine/test_config_models.py`
  - 结果：0 errors, 0 warnings, 0 informations
- `git diff --check`
  - 结果：通过，无 whitespace error

### 剩余风险

- 本次 fix 只补 review 已裁决的测试覆盖和测试语义，不扩大到自循环以外的其它 residual coverage 项。
- 未覆盖 Service / composition root 对 typed config 的映射；该项仍属于后续 slice。
