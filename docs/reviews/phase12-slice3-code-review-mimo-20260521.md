# Code Review

## Scope

- Mode: current changes
- Branch: docs/phase12-design-discussion
- Base: HEAD (uncommitted workspace changes)
- Output file: docs/reviews/phase12-slice3-code-review-mimo-20260521.md
- Included scope: Phase 12 Slice 3 implementation - ConfigLoader typed config loading / validation and legacy config removal
- Excluded scope: Service / composition root mapping to RunnerSpec/RunnerCallOptions/AgentPolicy/OpenHostOptions (后续 slice)
- Parallel review coverage: 无

## Findings

### 1-未修复-低-测试覆盖缺口：extends 父项不存在路径未覆盖

- **入口/函数**: `_resolve_record` (config_loader.py:830-832)
- **文件(行号)**: dayu/runtime/config_loader.py:830-832
- **输入场景**: 配置记录声明 `extends: "non-existent-parent"`，但父项 id 不在同文件 records 中
- **实际分支**: `if parent_id not in records:` 会抛出 `ConfigExtendsError`
- **预期行为**: 配置加载应 fail fast 并抛出结构化错误
- **实际行为**: 实现正确抛出 `ConfigExtendsError`，但无测试覆盖此路径
- **直接证据**: config_loader.py:830-832 `raise ConfigExtendsError(f"{context}.{record_id} extends missing parent: {parent_id}")`
- **影响**: 低 - 实现正确，但缺少回归保护
- **建议改法和验证点**: 在 test_config_loader.py 中新增 `test_extends_parent_not_found_fails_fast` 测试
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-未修复-低-测试语义不匹配：test_default_models_do_not_use_extra_payloads_bag 断言与名称不符

- **入口/函数**: `test_default_models_do_not_use_extra_payloads_bag` (test_config_models.py:8-15)
- **文件(行号)**: tests/engine/test_config_models.py:14-15
- **输入场景**: 加载默认配置并遍历所有模型
- **实际分支**: 断言 `model.provider_request_extension is not None`
- **预期行为**: 测试名称暗示应验证"不使用 extra_payloads bag"，但断言只检查 provider_request_extension 非空
- **实际行为**: 断言语义与测试名称不匹配；如果某个模型的 provider_request_extension 为 null（合法配置），测试会误报失败
- **直接证据**: test_config_models.py:15 `assert model.provider_request_extension is not None`
- **影响**: 低 - 测试可能在合法配置变更时误报失败，或在真正引入 extra_payloads 时漏检
- **建议改法和验证点**: 改为验证 ModelConfig dataclass 不包含 `extra_payloads` 字段（通过检查 `__dataclass_fields__` 或使用 hasattr 反检），或重命名测试以准确反映断言意图
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-未修复-低-非 map 字段 overlay 行为未被测试覆盖

- **入口/函数**: `_overlay_roots` (config_loader.py:766-767)
- **文件(行号)**: dayu/runtime/config_loader.py:766-767
- **输入场景**: workspace 配置文件包含 `default_profile_id` 等非 map 顶层字段
- **实际分支**: `else: merged[field_name] = workspace_value` 直接替换
- **预期行为**: workspace 中的 `default_profile_id` 应覆盖包内默认值
- **实际行为**: 实现正确执行直接替换，但无测试覆盖 workspace 覆盖非 map 字段的行为
- **直接证据**: config_loader.py:766-767
- **影响**: 低 - 实现正确，但缺少回归保护
- **建议改法和验证点**: 在 test_config_loader.py 中新增测试验证 workspace 可以覆盖 `default_profile_id` 等非 map 字段
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

- 无

## Residual Risk

- `_require_mapping_contains` 的类型签名使用了多个 `|` 联合类型（config_loader.py:1812-1819），虽然在 Python 3.10+ 中合法，但如果后续需要扩展支持新的 config 类型，签名可能需要调整。当前不影响功能正确性。
- `execution_profiles.json` 中的 `reasoning` runner hint 引用 `model_id: "deepseek-reasoner"`，该模型在 `models.json` 中通过 extends 继承自 `deepseek-chat`，已通过 `_validate_execution_model_references` 校验，无风险。

## Verification Commands

```bash
# 已运行
source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q
# 结果：17 passed

source .venv/bin/activate && pytest tests/engine/test_config_models.py tests/engine/test_smoke_async_agent_providers.py -q
# 结果：9 passed

source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime
# 结果：0 errors, 0 warnings, 0 informations

source .venv/bin/activate && python -m pyright dayu/contracts dayu/runtime tests/runtime tests/engine/test_config_models.py
# 结果：0 errors, 0 warnings, 0 informations

# 架构边界检查
grep -r "from dayu\.\(host\|engine\|service\|ui\|fins\)" dayu/runtime/
# 结果：无匹配 - 确认无业务层反向依赖

grep -r "llm_models\.json\|run\.json" dayu/ --include="*.py"
# 结果：仅 config_loader.py 中的 _LEGACY_CONFIG_FILES 常量和 runner_spec.py 中的文档注释

# 未运行
# git diff --check (implementation report 已确认通过)
```

## Verdict

**PASS** - blocking findings count = 0

发现 3 个低严重程度问题，均为测试覆盖缺口或语义不匹配，不影响功能正确性或架构边界。实现符合设计意图：ConfigLoader 只依赖标准库和 dayu.contracts，无业务层反向依赖，overlay 和 extends 行为正确，secret/env 原样保留，旧配置文件已删除且无兼容读取路径。
