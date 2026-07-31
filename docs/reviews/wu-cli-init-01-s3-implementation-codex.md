# WU-CLI-INIT-01 S3 Implementation

## Gate metadata

- Gate：`implementation`
- Work unit：`WU-CLI-INIT-01`
- Slice：`S3 — Package defaults 与 Service compactor assembly`
- 日期：2026-07-30
- Scope：统一 package run/compactor baseline 与 compactor manifest 到 Mimo
  Token Plan family；在 Service Host assembly 边界分离 primary default、
  ordinary effective 与 compactor effective selection，并在 Host options 构造前
  对 durable primary/compactor family fail closed。
- Artifact path：
  `docs/reviews/wu-cli-init-01-s3-implementation-codex.md`

## First-principles and owner decision

- S3 动机成立。变更前 package 的 15 个普通/思考 scene 已使用 Mimo Token Plan
  family，但 compactor manifest 与四个 execution profile 的 8 个 baseline ref
  仍使用 DeepSeek，未执行 init 时会真实要求第二家 credential。
- `prepare_scene(...)` 已产生 typed `model_hints`；
  `select_runner_option_hint(...)` 已拥有字段级 selection source of truth；
  S2 accepted state 已提供唯一 `model_family_identity(ModelConfig)`。因此无需新增
  config schema、Host state 或第二套 family parser。
- Service `compose_open_host_options(...)` 是 primary scene 与 compactor typed
  selection 首次汇合、且 `_compose_options(...)`/secret resolution 尚未发生的最早
  owner boundary。runtime drift 校验放在这里成立。
- primary default 不消费 invocation override；ordinary effective 才消费
  `ServiceAssemblyOverrides`；compactor effective 使用真实 compactor scene hints
  且固定 `run_override=None`。因此跨 family `--model` 只改变 ordinary，不会被误判
  为 durable family drift。

## Pre-change DeepSeek inventory

Implementation 开始前执行：

```text
rg -n 'deepseek-v4-flash' dayu tests utils README.md docs/cli_ci.md
```

完整输出：

```text
tests/engine/test_provider_extension_config_adapter.py:104:    assert isinstance(parsed["deepseek-v4-flash"], DeepSeekThinkingExtension)
utils/smoke_async_agent_providers.py:161:        name="deepseek-v4-flash",
utils/smoke_async_agent_providers.py:165:        model="deepseek-v4-flash",
tests/engine/test_config_models.py:30:    assert config.models.models["deepseek-v4-flash"].provider_request_extension == {
tests/engine/test_config_models.py:41:        "deepseek-v4-flash",
tests/engine/test_config_models.py:42:        "deepseek-v4-flash-thinking",
tests/service/test_entrypoint_runtime_interactive_path.py:44:_MODEL_ID = "deepseek-v4-flash"
tests/service/test_host_assembly.py:117:_MODEL_ID = "deepseek-v4-flash"
tests/service/test_host_assembly.py:2615:    assert result.diagnostics.compactor_profile_compatibility.selected_model_id == "deepseek-v4-flash"
tests/service/test_host_assembly.py:2764:    model_id: str = "deepseek-v4-flash",
dayu/cli/init_catalog.py:143:        ordinary_model_id="deepseek-v4-flash",
dayu/cli/init_catalog.py:144:        thinking_model_id="deepseek-v4-flash-thinking",
tests/service/test_entrypoint_runtime_prompt_path.py:50:_MODEL_ID = "deepseek-v4-flash"
tests/service/test_entrypoint_runtime.py:108:_MODEL_ID = "deepseek-v4-flash"
tests/engine/test_smoke_async_agent_providers.py:156:        "SKIP deepseek-v4-flash missing_env=DEEPSEEK_API_KEY"
dayu/config/execution_profiles.json:8:        "model_id": "deepseek-v4-flash",
dayu/config/execution_profiles.json:12:        "model_id": "deepseek-v4-flash",
dayu/config/execution_profiles.json:94:        "model_id": "deepseek-v4-flash",
dayu/config/execution_profiles.json:98:        "model_id": "deepseek-v4-flash",
dayu/config/execution_profiles.json:180:        "model_id": "deepseek-v4-flash",
dayu/config/execution_profiles.json:184:        "model_id": "deepseek-v4-flash",
dayu/config/execution_profiles.json:266:        "model_id": "deepseek-v4-flash",
dayu/config/execution_profiles.json:270:        "model_id": "deepseek-v4-flash",
dayu/config/models.json:3:    "deepseek-v4-flash": {
dayu/config/models.json:6:      "model": "deepseek-v4-flash",
dayu/config/models.json:70:    "deepseek-v4-flash-thinking": {
dayu/config/models.json:71:      "extends": "deepseek-v4-flash",
tests/cli/test_transient_delivery_interruption_path.py:301:            assembly_overrides=ServiceAssemblyOverrides(model_id="deepseek-v4-flash"),
tests/cli/test_prompt_command.py:109:_MODEL_ID = "deepseek-v4-flash"
tests/cli/test_session_command.py:77:_MODEL_ID = "deepseek-v4-flash"
tests/cli/test_init_catalog.py:242:        ("DeepSeek Flash", "deepseek-v4-flash", "deepseek-v4-flash-thinking", "DEEPSEEK_API_KEY"),
tests/cli/test_interactive_command.py:87:_MODEL_ID = "deepseek-v4-flash"
tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py:97:_MODEL_ID = "deepseek-v4-flash"
tests/runtime/test_assembly_helpers.py:135:            model_id="deepseek-v4-flash",
tests/runtime/test_assembly_helpers.py:170:                    "model_id": "deepseek-v4-flash",
tests/runtime/test_assembly_helpers.py:184:            {"model_id": "deepseek-v4-flash", "provider": "deepseek"},
tests/runtime/test_assembly_helpers.py:382:    model = config.models.models["deepseek-v4-flash"]
tests/runtime/test_assembly_helpers.py:390:    assert diagnostic.selected_model_id == "deepseek-v4-flash"
tests/runtime/test_assembly_helpers.py:400:    model = config.models.models["deepseek-v4-flash"]
tests/runtime/test_config_loader.py:400:    assert config.models.models["deepseek-v4-flash"].model_id == "deepseek-v4-flash"
dayu/config/prompts/manifests/conversation_compaction.json:11:    "default_model_id": "deepseek-v4-flash",
dayu/config/README.md:349:    "deepseek-v4-flash": {
dayu/config/README.md:352:      "model": "deepseek-v4-flash",
tests/tools/test_combined_tools_acceptance.py:387:                model_id="deepseek-v4-flash",
tests/tools/test_combined_tools_acceptance.py:539:            "model": {"default_model_id": "deepseek-v4-flash"},
tests/host/public_smoke_support.py:782:        model="deepseek-v4-flash",
```

分类与处置：

1. package-default owner / 偶然默认断言：
   - `dayu/config/execution_profiles.json` 8 个 baseline ref；
   - `dayu/config/prompts/manifests/conversation_compaction.json` 1 个 scene owner；
   - `tests/service/test_host_assembly.py` 的旧 package compactor model/temperature
     断言。
   - 处置：迁移到 Mimo Token Plan package truth。
2. 显式 DeepSeek catalog / provider-specific production asset：
   - `dayu/config/models.json`、`dayu/cli/init_catalog.py`、
     `utils/smoke_async_agent_providers.py`、`dayu/config/README.md` 示例。
   - 处置：全部保留。
3. 显式 DeepSeek fixture / provider contract：
   - inventory 中其余 tests 命中，包括 plan inventory 之外实际出现的
     `tests/cli/test_session_command.py`。
   - 处置：不机械替换。Service assembly fixtures 仍显式选择 DeepSeek ordinary；
     仅因 production compactor 现为 Mimo，给真实双 runner assembly fixture 补入
     `MIMO_PLAN_API_KEY`，并让自定义 compactor scene fixture 默认使用 package Mimo
     family，使各测试意图自足。

## Changed files

- `dayu/config/execution_profiles.json`
- `dayu/config/prompts/manifests/conversation_compaction.json`
- `dayu/service/host_assembly.py`
- `tests/runtime/test_config_loader.py`
- `tests/service/test_host_assembly.py`
- `tests/cli/test_init_catalog.py`
- `docs/reviews/wu-cli-init-01-s3-implementation-codex.md`

## Implemented contract

1. 四个 package execution profile 的 `run_baseline.model_id` 与
   `compactor_baseline.model_id` 共 8 个 ref 全部改为
   `mimo-v2.5-pro-plan`。
2. package `conversation_compaction` manifest 的 `default_model_id` 改为
   `mimo-v2.5-pro-plan`；`runner_option_hint_id` 仍为
   `conversation_compaction`，prompt、AgentPolicy 与 artifact path 未改。
3. Service 在同一 typed owner chain 中分别求值：
   - `primary_default_selection`：主 scene hints + run baseline，无 override；
   - `ordinary_selection`：同一来源 + invocation override；
   - `compactor_selection`：compactor scene hints + compactor baseline，无 override。
4. compactor 不再丢弃 `_prepare_compactor_scene_inputs(...)` 产生的 model hints；
   compactor runner hint、temperature、top-p、stream 均来自选中 Mimo 模型的
   `conversation_compaction` hint，当前 package 值为 `0.3 / 1.0 / false`。
5. Service 使用 S2 唯一 `model_family_identity(...)` 构造四字段 identity，并显式
   比较 provider、provider model、endpoint、credential ref。mismatch 在
   `_compose_options(...)` 与 secret header resolution 前 fail closed。
6. mismatch 错误只包含 primary/compactor model id 与
   `mismatched_fields`；不包含 endpoint 值、credential ref 值、header 或 secret。
7. Host options、diagnostics 与 public/durable schema 未新增字段；ordinary 与
   compactor 继续使用既有 effective selection。

## Tests and validation

- Pre-change focused baseline：

  ```text
  pytest tests/runtime/test_config_loader.py \
    tests/service/test_host_assembly.py tests/cli/test_init_catalog.py -q
  ```

  结果：`226 passed`。

- S3 focused：

  ```text
  pytest tests/runtime/test_config_loader.py \
    tests/service/test_host_assembly.py tests/cli/test_init_catalog.py -q
  ```

  结果：`244 passed`。关键 owner assertions：
  - 16 个 package manifests 与 8 个 baseline refs 为同一 Mimo Token Plan family；
  - 13 个静态 init choice 的 compactor projection 与 ordinary family 同源；
  - package assembly 只给 `MIMO_PLAN_API_KEY` 成功，不需要/不读取
    `DEEPSEEK_API_KEY`；
  - workspace DeepSeek 投影只给 `DEEPSEEK_API_KEY` 成功，不读取 package Mimo key；
  - no override 使用主 scene hint；
  - 跨 family Run override 只改变 ordinary selection；
  - compactor model、hint、temperature、top-p、stream 在 override 前后不变；
  - intentional compactor manifest mismatch 在 Host options/secret resolution 前
    fail closed，错误不泄 endpoint/credential。

- Coverage：

  ```text
  coverage erase
  coverage run -m pytest tests/runtime/test_config_loader.py \
    tests/service/test_host_assembly.py tests/cli/test_init_catalog.py -q
  coverage report --include='dayu/service/host_assembly.py'
  ```

  结果：`dayu/service/host_assembly.py 95%`（594 statements，30 missed）。

- Affected-scope pyright：

  ```text
  python -m pyright dayu/service/host_assembly.py \
    tests/runtime/test_config_loader.py tests/service/test_host_assembly.py \
    tests/cli/test_init_catalog.py
  ```

  结果：`0 errors, 0 warnings, 0 informations`。

- Full pyright：

  ```text
  python -m pyright dayu/ tests/ utils/
  ```

  结果：`0 errors, 0 warnings, 0 informations`。

- Ruff：

  ```text
  python -m ruff check dayu/service/host_assembly.py \
    tests/runtime/test_config_loader.py tests/service/test_host_assembly.py \
    tests/cli/test_init_catalog.py
  ```

  结果：`All checks passed!`。

- JSON parse：两个修改后的 package JSON 均通过 `python -m json.tool`。
- `git diff --check`：通过。
- owner residual scan：两个 package owner 文件不再包含
  `deepseek-v4-flash`；四个 profile 的 8 个 baseline ref 与 compactor manifest
  精确包含 `mimo-v2.5-pro-plan`。

## Docs decision

- `dayu/config/README.md` 与 `dayu/service/README.md` 当前没有独立
  `Agent更新约束` 章节；已按根 `AGENTS.md` 的职责触发规则检查。
- package defaults 与 Service selection 文档确需在 work-unit 完成前同步，但用户
  明确限制 S3 approved files 且要求 README 记录 S6 deferred；accepted plan 也把
  README 同步分配给 S6。
- 本 slice 不修改 README。classification：`covered by later approved slice S6`。
- accepted oracle、goal artifact、accepted plan 与 S1/S2 accepted artifacts：
  未修改。

## Findings fixed

- Controller A08（DeepSeek 默认引用 inventory 与分类）：`已修复`。完整 pre-change
  inventory 已记录；只迁移 package owner/偶然默认断言，显式 DeepSeek asset 与
  provider fixture 保留。
- Controller A09（primary default / compactor runtime fail-closed）：`已修复`。
  runtime anchor 不含 invocation override，mismatch 在 Host options 前失败。

## Residual risks

- S2 记录的 execution profile no-follow read TOCTOU 与 managed transaction/path
  safety 不属于 S3。
  - classification：`covered by later approved slice S4`
- versioned publication manifest、15-row real provider matrix、外部 provider
  availability/no-fallback evidence 尚未执行。
  - classification：`covered by later approved slice S5`
- README 与 aggregate work-unit handoff 尚未执行。
  - classification：`covered by later approved slice S6`
- S3 owner boundary 内无 unclassified residual risk。

## Completion

- Completion signal：`pass`
- Stop condition：`none`
- Package 与 workspace assembly 均无 second credential requirement。
- 严格只修改 S3 approved files 与本 artifact。
- 未修改 S4+、README、accepted oracle 或 accepted plan。
- 未提交。
