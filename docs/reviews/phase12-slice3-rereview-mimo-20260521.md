# Phase 12 Slice 3 Re-Review — AgentMiMo

## Scope

- Mode: re-review of Slice 3 fix
- Branch: `docs/phase12-design-discussion`
- Reviewer role: AgentMiMo
- Purpose: 验证 controller 裁决的 accepted findings 是否已被 fix 收口
- Input artifacts:
  - `docs/reviews/phase12-slice3-code-review-controller-adjudication-20260521.md`
  - `docs/reviews/phase12-slice3-code-review-mimo-20260521.md`
  - `docs/reviews/phase12-slice3-code-review-ds-20260521.md`
  - `docs/reviews/phase12-slice3-implementation-codex-20260521.md`（含 fix addendum）
- Output file: `docs/reviews/phase12-slice3-rereview-mimo-20260521.md`

## Accepted Findings 修复状态

### P12-S3-F1: missing-parent extends regression test

- Source: MiMo finding 1 + DS finding 1
- Controller decision: accepted-current-fix
- Fix 预期: 新增 `test_extends_parent_not_found_fails_fast`，断言缺失父项抛出 `ConfigExtendsError` 且 match "missing parent"
- 实际状态: **已修复**
- 直接证据: `tests/runtime/test_config_loader.py:329-347` 新增 `test_missing_extends_parent_fails_fast`，写入 `extends: "missing-model"` 配置，断言 `pytest.raises(ConfigExtendsError, match="missing parent")`
- 验证: 测试通过（18 passed 中包含此测试）

### P12-S3-F2: test_default_models_do_not_use_extra_payloads_bag assertion mismatch

- Source: MiMo finding 2
- Controller decision: accepted-current-fix
- Fix 预期: 测试改为验证 typed `ModelConfig` dataclass 字段集合不包含 `extra_payloads`
- 实际状态: **已修复**
- 直接证据: `tests/engine/test_config_models.py:10-18` 改为使用 `dataclasses.fields(ModelConfig)` 获取字段名集合，断言 `"extra_payloads" not in model_fields` 且 `"provider_request_extension" in model_fields`。测试名称与断言语义现在一致。
- 验证: 测试通过（18 passed 中包含此测试）

### P12-S3-F3: non-map top-level workspace overlay test

- Source: MiMo finding 3
- Controller decision: accepted-current-fix
- Fix 预期: 新增测试验证 workspace 可覆盖 `default_profile_id` 等非 map 字段
- 实际状态: **已修复**
- 直接证据: `tests/runtime/test_config_loader.py:379-405` 新增 `test_workspace_non_map_top_level_field_overrides_package_default`，写入 workspace `execution_profiles.json` 覆盖 `default_profile_id` 为 `"workspace-profile"`，断言 `config.default_profile_id == "workspace-profile"` 且该 profile 存在且继承自 `ordinary`
- 验证: 测试通过（18 passed 中包含此测试）

### P12-S3-F4: invalid extends type + lane TTL/heartbeat validation tests

- Source: DS findings 2+3
- Controller decision: accepted-current-fix for narrow tests
- Fix 预期:
  - 新增 `test_invalid_extends_type_fails_fast` 覆盖 extends 为 number、bool、object
  - 新增 `test_lane_capacity_claim_ttl_must_exceed_heartbeat` 覆盖 `claim_ttl_seconds <= heartbeat_interval_seconds`
- 实际状态: **已修复**
- 直接证据:
  - `tests/runtime/test_config_loader.py:350-376` 新增 `test_invalid_extends_type_fails_fast`，`@pytest.mark.parametrize("extends_value", [123, True, {"parent": "base-model"}])`，断言 `ConfigExtendsError` match "string or null"
  - `tests/runtime/test_config_loader.py:497-539` 新增 `test_lane_capacity_claim_ttl_must_exceed_heartbeat`，设置 `claim_ttl_seconds: 2.0` 且 `heartbeat_interval_seconds: 2.0`（相等），断言 `ConfigFieldError` match "greater than heartbeat"
- 验证: 测试通过（18 passed 中包含此测试）

## 生产代码变更检查

- `git diff --name-only dayu/runtime/config_loader.py` → 无输出，确认生产代码未被修改
- Controller 要求 "No production code changes are expected unless a new test reveals a real implementation defect" → 已满足

## 验证命令执行结果

| 命令 | 结果 |
|------|------|
| `source .venv/bin/activate && pytest tests/runtime/test_config_loader.py tests/engine/test_config_models.py -q` | 18 passed |
| `source .venv/bin/activate && pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 7 passed |
| `source .venv/bin/activate && python -m pyright dayu/runtime tests/runtime tests/engine/test_config_models.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过，无 whitespace error |
| `git diff --name-only dayu/runtime/config_loader.py` | 无输出（生产代码未修改） |

## New Blocker 检查

未发现 new blocker。所有 fix 仅限于测试文件，未引入新的架构边界违反、类型错误或回归风险。

## Verdict

**PASS**

Controller 裁决的 4 个 accepted findings（P12-S3-F1 至 P12-S3-F4）均已通过测试 fix 收口。生产代码未被修改。所有验证命令通过。Slice 3 fix 满足 gate 要求。
