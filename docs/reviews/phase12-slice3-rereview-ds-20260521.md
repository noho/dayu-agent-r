# Phase 12 Slice 3 Re-Review — AgentDS

## Scope

- Task: 对 Phase 12 Slice 3 Controller Adjudication 中 accepted findings 做 fix verification re-review
- Controller adjudication: `docs/reviews/phase12-slice3-code-review-controller-adjudication-20260521.md`
- Original reviews: MiMo (`phase12-slice3-code-review-mimo-20260521.md`), DS (`phase12-slice3-code-review-ds-20260521.md`)
- Implementation report (with fix addendum): `docs/reviews/phase12-slice3-implementation-codex-20260521.md`
- Fix scope: `tests/runtime/test_config_loader.py`, `tests/engine/test_config_models.py`, implementation report addendum
- Output file: `docs/reviews/phase12-slice3-rereview-ds-20260521.md`

## Accepted Findings — Fix Verification

### P12-S3-F1: missing-parent extends regression test

- **Controller decision**: accepted-current-fix
- **Fix claim**: 新增 `test_missing_extends_parent_fails_fast`
- **证据**: `tests/runtime/test_config_loader.py:329-347` — 声明 `extends: "missing-model"`，断言 `ConfigExtendsError` 且 `match="missing parent"`
- **Status**: ✅ FIXED

### P12-S3-F2: test_default_models_do_not_use_extra_payloads_bag assertion mismatch

- **Controller decision**: accepted-current-fix
- **Fix claim**: 改为检查 `ModelConfig` dataclass 字段集合，不包含 `extra_payloads`，包含 `provider_request_extension`
- **证据**: `tests/engine/test_config_models.py:15-18` — 使用 `fields(ModelConfig)` 获取字段名，`assert "extra_payloads" not in model_fields`，`assert "provider_request_extension" in model_fields`
- **Status**: ✅ FIXED — 断言语义现在与测试名称一致，不再用 `provider_request_extension is not None` 作为 weak bag 的 proxy 断言

### P12-S3-F3: non-map top-level workspace overlay regression coverage

- **Controller decision**: accepted-current-fix
- **Fix claim**: 新增 `test_workspace_non_map_top_level_field_overrides_package_default`
- **证据**: `tests/runtime/test_config_loader.py:379-405` — workspace 设置 `default_profile_id: "workspace-profile"` 并新增对应 profile；断言 `config.default_profile_id == "workspace-profile"` 且 workspace profile 正确继承 ordinary 的 model_id
- **Status**: ✅ FIXED

### P12-S3-F4a: invalid extends type test

- **Controller decision**: accepted-current-fix
- **Fix claim**: 新增 `test_invalid_extends_type_fails_fast` 覆盖 number/bool/object
- **证据**: `tests/runtime/test_config_loader.py:350-376` — parametrize `[123, True, {"parent": "base-model"}]`，断言 `ConfigExtendsError` 且 `match="string or null"`
- **Status**: ✅ FIXED

### P12-S3-F4b: lane claim_ttl_seconds <= heartbeat_interval_seconds validation test

- **Controller decision**: accepted-current-fix
- **Fix claim**: 新增 `test_lane_capacity_claim_ttl_must_exceed_heartbeat`
- **证据**: `tests/runtime/test_config_loader.py:497-539` — 设置 `claim_ttl_seconds: 2.0, heartbeat_interval_seconds: 2.0`（相等，不大于），断言 `ConfigFieldError` 且 `match="greater than heartbeat"`
- **Status**: ✅ FIXED

## 生产代码变更检查

Controller 明确要求"不应修改生产 schema/实现，除非测试揭示真实缺陷"。确认：

- 测试未揭示生产代码缺陷（所有新增测试在未修改的生产代码上直接 pass）
- `git diff` 中无 `dayu/runtime/config_loader.py`、`dayu/config/*.json` 的新的 diff
- 默认配置文件未被修改

## New Blockers

无。所有 5 个 accepted findings 的 fix 均已在测试文件中确认存在且语义正确。

## 验证命令及结果

| 命令 | 结果 |
|------|------|
| `pytest tests/runtime/test_config_loader.py tests/engine/test_config_models.py -q` | 18 passed |
| `pytest tests/runtime/test_import_boundary.py tests/runtime/test_weak_typing_guard.py -q` | 7 passed |
| `python -m pyright dayu/runtime tests/runtime tests/engine/test_config_models.py` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | 通过，无 whitespace error |

未运行命令：无（所有 controller 要求的验证命令均已运行）。

## Verdict

**PASS** — blocking findings count = 0

所有 5 个 Controller accepted findings 均已在 fix 中正确收口。新增测试语义与 finding 描述一致，测试全部通过，pyright 零报错，生产代码未被修改。未出现 new blocker。
