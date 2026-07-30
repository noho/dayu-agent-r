# Code Review

## Scope

- Mode: current changes
- Branch: ci/pr-179-first-ci-readiness
- Base: 9e6cde82
- Output file: docs/reviews/wu-cli-init-01-s3-code-review-mimo.md
- Included scope: WU-CLI-INIT-01 S3 implementation — Package defaults 与 Service compactor assembly
- Excluded scope: S1/S2/S4/S5/S6 implementation, README updates
- Parallel review coverage: 无

## Findings

未发现实质性问题。

## Verified Contract Points

### 1. Package Defaults 迁移（8 baseline refs + 1 compactor manifest）

**变更文件**：
- `dayu/config/execution_profiles.json`：4 个 profile 的 8 个 `run_baseline.model_id` 与 `compactor_baseline.model_id`
- `dayu/config/prompts/manifests/conversation_compaction.json`：`default_model_id`

**证据**：
- pre-change inventory 显示 9 处 `deepseek-v4-flash` 全部在 package owner 文件中
- post-change `rg -n 'mimo-v2.5-pro-plan'` 确认 9 处精确替换
- `rg -n 'deepseek-v4-flash' dayu/config/execution_profiles.json dayu/config/prompts/manifests/conversation_compaction.json` 返回空
- JSON 格式通过 `python -m json.tool` 验证
- `runner_option_hint_id: "conversation_compaction"` 保持不变
- prompt、AgentPolicy、artifact path 未改

### 2. Service 三路 Selection 语义

**变更文件**：`dayu/service/host_assembly.py`

**实现验证**：
```python
# L605-611: primary_default_selection
primary_default_selection = select_runner_option_hint(
    models=config.models,
    execution_baseline=execution_profile.run_baseline,
    scene_model_hints=request.scene_inputs.model_hints,
    run_override=None,  # 不消费 invocation override
    base_policy=None,
)

# L612-618: ordinary_selection
ordinary_selection = select_runner_option_hint(
    models=config.models,
    execution_baseline=execution_profile.run_baseline,
    scene_model_hints=request.scene_inputs.model_hints,
    run_override=_model_runner_override_from_overrides(request.overrides),  # 消费 override
    base_policy=None,
)

# L619-628: compactor_selection
compactor_selection = select_runner_option_hint(
    models=config.models,
    execution_baseline=ExecutionBaselineConfig(...),
    scene_model_hints=compactor_scene_inputs.model_hints,  # 使用 compactor hints
    run_override=None,  # 不消费 invocation override
    base_policy=None,
)
```

**语义正确性**：
- `primary_default_selection` 代表 durable workspace/package primary truth，不含 invocation override
- `ordinary_selection` 代表本次 Run 的 effective selection，消费 `ServiceAssemblyOverrides`
- `compactor_selection` 代表 compactor 的 durable selection，使用 compactor scene hints
- 三者通过同一 `select_runner_option_hint()` 选择，确保 source of truth 统一

### 3. Compactor Model Hints 保留

**变更**：L625 `scene_model_hints=compactor_scene_inputs.model_hints`

**证据**：
- 旧代码传 `scene_model_hints=None`，导致 compactor 只用 baseline
- 新代码传入 `_prepare_compactor_scene_inputs(...)` 产生的 `model_hints`
- 测试 `test_compose_open_host_options_uses_runtime_tuning_from_config` 断言 `temperature == 0.3`（Mimo conversation_compaction hint 值），而非旧值 `0.4`（DeepSeek hint 值）
- compactor runner hint、temperature、top-p、stream 均来自选中 Mimo 模型的 `conversation_compaction` hint

### 4. Family 校验位置与脱敏

**变更**：L637-640 调用 `_require_matching_model_families()`

**验证**：
- 校验发生在 `_compose_options()` 和 secret header resolution 之前
- 使用 `model_family_identity()` 比较四字段：provider、provider_model、endpoint、credential_ref
- 错误消息只包含 `primary_model_id`、`compactor_model_id` 和 `mismatched_fields`
- 不包含 endpoint 值、credential ref 值、header 或 secret

**测试证据**：`test_compactor_family_mismatch_fails_before_host_options_without_secret_leak`
- 断言 `"api.deepseek.com" not in rendered`
- 断言 `"token-plan-cn.xiaomimimo.com" not in rendered`
- 断言 `"DEEPSEEK_API_KEY" not in rendered`
- 断言 `"MIMO_PLAN_API_KEY" not in rendered`

### 5. Single Credential 证明

**Package MIMO-only 测试**：`test_package_defaults_use_only_mimo_and_isolate_cross_family_run_override`
- `env={"MIMO_PLAN_API_KEY": _MIMO_PLAN_API_KEY}` 成功完成 assembly
- 不需要/不读取 `DEEPSEEK_API_KEY`
- 跨 family Run override (`deepseek-v4-flash`) 只改变 ordinary selection
- compactor selection 在 override 前后不变

**Workspace DeepSeek-only 测试**：`test_workspace_projected_family_assembles_without_package_mimo_key`
- `env={"DEEPSEEK_API_KEY": _API_KEY}` 成功完成 assembly
- 不需要/不读取 `MIMO_PLAN_API_KEY`
- workspace projected compactor 使用 DeepSeek family

### 6. ValueError 使用合理性

**分析**：
- `_require_matching_model_families()` 抛出 `ValueError`
- 这符合 Service/CLI 既有错误所有权：`RuntimeAssemblySelectionError` 用于 catalog 选择缺失，`ValueError` 用于参数校验失败
- Family mismatch 是配置/参数层面的非法状态，使用 `ValueError` 合理
- 调用方 (`compose_open_host_options`) 未捕获该异常，让其传播到 CLI adapter 边界

### 7. 测试覆盖完整性

**S3 focused tests**：`244 passed`

**关键 owner assertions**：
1. `test_package_sixteen_manifests_share_mimo_token_plan_family`：16 个 package manifest 同属 Mimo family
2. `test_static_choice_compactor_projection_shares_ordinary_family`：13 个静态 choice 的 compactor 投影与 ordinary 同源
3. `test_package_execution_profile_baselines_share_mimo_token_plan_family`：8 个 baseline 同属 Mimo family
4. `test_package_defaults_use_only_mimo_and_isolate_cross_family_run_override`：package 默认只需 MIMO key
5. `test_workspace_projected_family_assembles_without_package_mimo_key`：workspace DeepSeek 投影只需 DEEPSEEK key
6. `test_compactor_family_mismatch_fails_before_host_options_without_secret_leak`：mismatch 脱敏失败

**Coverage**：`dayu/service/host_assembly.py 95%`（594 statements，30 missed）

### 8. Pyright 验证

```bash
python -m pyright dayu/ tests/ utils/
# Result: 0 errors, 0 warnings, 0 informations
```

### 9. Whitespace 验证

```bash
git diff --check
# Result: 无错误
```

## Open Questions

无。

## Residual Risk

1. **S2 记录的 execution profile no-follow read TOCTOU 与 managed transaction/path safety**：不属于 S3 scope。
   - classification: `covered by later approved slice S4`

2. **Versioned publication manifest、15-row real provider matrix、外部 provider availability/no-fallback evidence**：尚未执行。
   - classification: `covered by later approved slice S5`

3. **README 与 aggregate work-unit handoff**：尚未执行。
   - classification: `covered by later approved slice S6`

4. **S3 owner boundary 内无 unclassified residual risk**。

## Verdict

**PASS**

S3 实现完整满足 approved plan 的所有 contract points：
- Package defaults 已从 DeepSeek 迁移到 Mimo Token Plan family
- Service 三路 selection 语义正确：primary_default（durable truth）、ordinary（invocation effective）、compactor（durable compactor）
- compactor model hints 保留，temperature/stream/hint 来自 Mimo conversation_compaction hint
- Family 校验在 secret resolution 前 fail closed，错误脱敏
- Package MIMO-only 与 workspace DeepSeek-only 测试真实证明单 credential
- 244 tests passed，95% coverage，0 pyright errors
