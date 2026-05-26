# PR 68 Post-Draft Re-Review: compactor_baseline scene_id schema/assembly fix

- Reviewer: mimo
- Date: 2026-05-23
- Gate: compactor_baseline.scene_id schema/assembly fix
- Verdict: **PASS**

## Scope

Review 限于当前未提交 diff，覆盖以下文件：
- `dayu/runtime/config_loader.py`
- `dayu/config/execution_profiles.json`
- `dayu/service/host_assembly.py`
- `tests/runtime/test_config_loader.py`
- `tests/service/test_host_assembly.py`
- `tests/host/test_public_compact_smoke.py`
- `dayu/README.md`, `dayu/config/README.md`, `dayu/host/README.md`, `docs/host/design.md`, `docs/host/implementation-control.md`

## Design Intent Verification

| Claim | Verdict | Evidence |
|-------|---------|----------|
| compactor scene name 不在 Service 中硬编码 | **PASS** | `host_assembly.py:75` 已删除 `_COMPACTOR_SCENE_ID` 常量；`_prepare_compactor_scene_inputs` 从 `execution_profile.compactor_baseline.scene_id` 读取 (`host_assembly.py:531`) |
| runtime config schema 要求 `compactor_baseline.scene_id` | **PASS** | `config_loader.py:200` 新增 `scene_id: str` 字段；`_parse_compactor_baseline` (`config_loader.py:1393`) 使用 `_require_str_field` 强制要求；`_require_exact_fields` (`config_loader.py:1386`) 已将 `scene_id` 加入 allowed set |
| default profiles 显式声明 `scene_id` | **PASS** | `execution_profiles.json` 四个 profile 的 `compactor_baseline` 均新增 `"scene_id": "conversation_compaction"` |
| compactor runner options 独立于普通 Run options | **PASS** | `CompactorBaselineConfig` 仍保留独立的 `runner_option_hint_id` 字段 (`config_loader.py:201`)；`_compactor_runner_options` 从 `compactor_baseline.runner_option_hint_id` 读取而非 `run_baseline` |
| Host 不 import `dayu.config` 或 `scene_prepare` | **PASS** | `grep` 在 `dayu/host/` 下无 `dayu.config` 或 `dayu.runtime.scene_prepare` 导入 |
| tests 证明自定义 scene id 改变 prompt | **PASS** | `test_compose_open_host_options_reads_compactor_scene_id_from_profile` (`test_host_assembly.py:142-218`) 构造 `_CUSTOM_COMPACTOR_SCENE_ID` 场景，断言 prompt 匹配自定义内容；`test_compactor_baseline_requires_scene_id` (`test_config_loader.py:741-764`) 验证缺 `scene_id` 报 `ConfigFieldError` |

## Findings

无 blocking findings。

## Target Smoke Assessment

- `tests/runtime/test_config_loader.py` — PASS (含新增 `test_compactor_baseline_requires_scene_id`)
- `tests/service/test_host_assembly.py` — PASS (含新增 `test_compose_open_host_options_reads_compactor_scene_id_from_profile`)
- `tests/host/test_public_compact_smoke.py` — PASS (`_compactor_prompts` 与 `_compactor_runner_options` 均从 profile 读取 scene_id/runner_option_hint_id)
- `pyright dayu/runtime/config_loader.py dayu/service/host_assembly.py tests/...` — 0 errors

全部 46 个受影响测试通过，pyright 无新增报错。

## Documentation Sync

README 与设计文档已同步更新：
- `dayu/README.md`: 更新 compaction 装配描述，移除硬编码 `conversation_compaction` 引用
- `dayu/config/README.md`: `compactor_baseline` 字段列表新增 `scene_id`
- `dayu/host/README.md`: 更新 compactor baseline 描述
- `docs/host/design.md`: 更新 `execution_profiles.json` 与 `LLMContextCompactor` 段落
- `docs/host/implementation-control.md`: 更新 gate 状态与结论

文档变更与代码变更语义一致，无残留旧术语。

## Residual Risks (non-blocking)

1. 当前四个 default profile 的 `scene_id` 均为 `"conversation_compaction"`，尚无实际使用不同 scene id 的生产场景。自定义 scene id 路径仅由测试覆盖，生产验证待首次非默认场景部署。
2. `runner_option_hint_id` 与 `scene_id` 在当前默认配置中值相同（均为 `"conversation_compaction"`），语义上二者独立但尚未有分离的实际案例。这是预期的，因为 hint 决定 runner 参数而 scene 决定 prompt asset，分离场景随业务演进自然出现。
