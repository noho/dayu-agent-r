# PR 68 Post-Draft Re-Review — compactor_baseline.scene_id Schema / Assembly Fix

**Date**: 2026-05-23
**Reviewer**: AgentDS (deepreview)
**Scope**: 当前未提交 diff，gate `compactor_baseline.scene_id` schema/assembly fix
**Verdict**: **PASS**

---

## Design Intent Verification Matrix

| # | Design Intent | Verdict | Evidence |
|---|---|---|---|
| 1 | Service 不硬编码 compactor scene 名 | **PASS** | `_COMPACTOR_SCENE_ID` 已从 `host_assembly.py` 移除；`_prepare_compactor_scene_inputs` 现在读取 `execution_profile.compactor_baseline.scene_id` (`host_assembly.py:531`) |
| 2 | runtime config schema 要求 `compactor_baseline.scene_id`，所有默认 profile 显式声明 | **PASS** | `CompactorBaselineConfig` 新增 `scene_id: str` 字段 (`config_loader.py:200`)；`_parse_compactor_baseline` 的 `allowed` 集合与 `_require_str_field` 均已包含 `scene_id` (`config_loader.py:1387,1393`)；4 个默认 profile 均显式声明 `"scene_id": "conversation_compaction"` (`execution_profiles.json:13,80,145,213`) |
| 3 | compactor runner options 仍独立于普通 Run options，通过 `runner_option_hint_id` 获取 | **PASS** | `runner_option_hint_id` 保留为独立必填字段 (`config_loader.py:201,1394-1398`)；`scene_id` 仅用于 prompt 装配，`runner_option_hint_id` 用于 `RunnerCallOptions`——两条配置路径不交叉 |
| 4 | Host 不 import `dayu.config` 或 `scene_prepare`；Host 只接收 typed `CompactorRunnerBaseline` prompt 字符串 | **PASS** | `grep "import.*dayu\.config\|from.*dayu\.config\|import.*scene_prepare\|from.*scene_prepare\|conversation_compaction" dayu/host/` 返回空 (`dayu/host/` 无匹配)；`CompactorRunnerBaseline` 的 `compactor_system_prompt` 和 `compactor_user_prompt_template` 均为 `str` 类型 (`api.py:938-939`)，docstring 写 "Service 从 compactor scene 装配的"——不引用具体 scene 名 |
| 5 | 测试证明自定义 compactor scene id 会改变 loaded prompt，硬编码路径会失败 | **PASS** | `test_compose_open_host_options_reads_compactor_scene_id_from_profile` (`test_host_assembly.py:369-445`)：创建 `custom_compactor_scene`，覆盖 profile 的 `scene_id`，断言 compactor prompt 与自定义 scene 文本一致；硬编码 `conversation_compaction` 将导致该测试失败 |

---

## Detailed Findings

### F1. `_COMPACTOR_SCENE_ID` 常量正确移除 (`host_assembly.py:76`)

旧常量 `_COMPACTOR_SCENE_ID: Final[str] = "conversation_compaction"` 已删除。这是该 gate 的 root cause fix——该常量使 Service 对 compactor scene 产生硬编码依赖。

### F2. `_prepare_compactor_scene_inputs` 签名变更正确 (`host_assembly.py:516-538`)

函数现在接收 `execution_profile: ExecutionProfileConfig` keyword-only 参数，并从 `execution_profile.compactor_baseline.scene_id` 读取 scene id。调用方 `compose_open_host_options` 正确传入 `execution_profile=execution_profile` (`host_assembly.py:276`)。

### F3. `CompactorBaselineConfig` schema 变更正确 (`config_loader.py:189-202`)

新增 `scene_id: str` 字段，位置在 `model_id` 之后、`runner_option_hint_id` 之前——字段排列语义合理（先定位 scene，再定位 runner hint）。`_parse_compactor_baseline` 同步更新 `allowed` 集合和 `_require_str_field` 调用。

### F4. 默认 profile 均显式声明 `scene_id` (`execution_profiles.json`)

4 个 profile (`standard-256k`, `standard-1m`, `wechat-256k`, `wechat-1m`) 的 `compactor_baseline` 均新增 `"scene_id": "conversation_compaction"`。默认值与当前唯一可用的 compactor scene 一致；未来新增 compactor scene 时可按 profile 切换。

### F5. config loader 测试补齐 (`test_config_loader.py:738-768`)

`test_compactor_baseline_requires_scene_id`：构造缺少 `scene_id` 的 profile，断言 `ConfigFieldError` 且错误消息匹配 `scene_id`。同时 `test_default_runtime_config_files_load_as_typed_views` 增加了对 `standard_256k.compactor_baseline.scene_id == "conversation_compaction"` 的断言 (`test_config_loader.py:298`)。

### F6. smoke test 同步更新 (`test_public_compact_smoke.py:248-287`)

`_compactor_prompts()` 和 `_compactor_runner_options()` 不再使用硬编码 `_COMPACTOR_SCENE_ID` 常量；改为从 ConfigLoader 加载的 execution profile 中读取 `compactor_baseline.scene_id` 和 `compactor_baseline.runner_option_hint_id`。这是正确的——smoke test 现在走真实的 config→scene→prompt 路径。

### F7. 错误消息去硬编码 (`host_assembly.py:552-554`)

`_compactor_prompts_from_scene_inputs` 的 `ValueError` 消息从 `"conversation_compaction scene must provide exactly two prompt fragments"` 改为 `"compactor scene must provide exactly two prompt fragments"`。对应测试 `test_compactor_prompt_scene_requires_two_fragments` 的 match pattern 从 `"exactly two prompt fragments"` 改为 `"compactor scene"` (`test_host_assembly.py:292`)。

### F8. 文档同步一致

- `dayu/README.md:61`: "按 execution profile 的 `compactor_baseline.scene_id` 装配" 替代 "从 `conversation_compaction` scene asset 装配"
- `dayu/config/README.md:85`: `compactor_baseline` 文档字段列表增加 `scene_id`
- `dayu/config/README.md:160-161`: 新增 "Service assembly 不硬编码 compactor scene 名" 说明段
- `dayu/host/README.md:96`: "按 execution profile compactor scene 装配" 替代 "从 `conversation_compaction` scene 装配"
- `dayu/host/README.md:258`: "按 execution profile compactor scene 装配后的 prompt fragments" 替代 "`conversation_compaction` scene"
- `docs/host/design.md:89-90`: 设计描述同步更新，增加 `scene_id` 字段说明
- `docs/host/implementation-control.md:227`: gate 状态更新为 "compactor baseline scene id fix in progress"

---

## Target Smoke Assessment

`test_public_compact_smoke.py` 变更正确：smoke test 不再使用模块级 `_COMPACTOR_SCENE_ID = "conversation_compaction"` 常量，改为 `_COMPACTOR_PROFILE_ID = "standard-256k"` 并通过 ConfigLoader 加载 profile 后读取 `compactor_baseline.scene_id`。这确保 smoke test 走的是真实的 `config → typed config → scene_id → ScenePrepare → CompactorRunnerBaseline` 数据流，而非绕过 config 的捷径。

---

## Residual Risks (Non-Blocking)

1. **自定义 compactor scene 的 fragment count contract**: `_COMPACTOR_PROMPT_FRAGMENT_COUNT = 2` 仍是模块级常量。如果未来某个 profile 的 `scene_id` 指向非 2-fragment scene，会在运行时 `ValueError`。这不是本次 gate 范围——当前所有 profile 的 `scene_id` 均为 `conversation_compaction`，该 scene 的 fragment count 契约是 2。若将来支持可变 fragment count，需作为独立 schema change 处理。

2. **smoke test 中的 `_compactor_runner_options` 现从 ConfigLoader 读取**: smoke 不再是纯 Host public API 测试——它依赖 `dayu.runtime.config_loader`。这是在 P12.5 设计边界内（smoke 验证的是 "从 config 到 Host 的完整装配路径有效"），但值得注意。

---

## Conclusion

所有 5 项 design intent 均 **PASS**。变更范围精确：移除硬编码常量、扩展 typed config schema、更新 assembly 调用链、补齐 config validation 测试、新增 custom scene 集成测试、同步文档。无阻塞风险。
