# Gateflow Code Review Artifact: Host public conversation memory scenario smoke S3

## Gate 与角色

- 当前 gate：code review（S3）。
- 角色：review worker，不是 controller。
- Work unit：Host public conversation memory scenario smoke。
- Slice：S3 assembly and pure helper tests。
- Review target：
  - `tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py`
  - `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s3-codex-20260526.md`
- Approved plan：`docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
- 本 artifact 只对 S3 测试变更做 code review；不实施、不提交、不推送、不进入后续 gate。

## 审查结论

**PASS** — 无 blocking finding。

## 审查依据

本 review 对照以下源材料进行：

1. 计划文档第 12 节测试计划与第 8-9 节场景矩阵 / 断言总表。
2. S3 implementation artifact（`gateflow-implementation-public-memory-scenario-smoke-s3-codex-20260526.md`）。
3. 生产代码 `utils/smoke_host_public_conversation_memory_scenarios.py`（helper 函数、MockFinanceMemoryTool、CLI、spec selection、pressure helpers、normalization）。
4. 项目 CLAUDE.md 编码硬约束与测试纪律。

## 逐项审查

### 1. 测试是否覆盖 approved S3 目标

| S3 目标 | 对应测试 | 状态 |
|---|---|---|
| assembly 默认注入内置 mock tool，scene 只选中 manual-smoke | `test_runtime_assembly_adds_builtin_mock_tool_and_selects_manual_smoke` | PASS |
| workspace overlay 同名非 smoke 工具 fail closed | `test_runtime_assembly_fails_closed_on_non_smoke_same_name_tool` | PASS |
| CLI --suite core/long/all 成功，--long-rounds 20/25 成功，19/26/0/-1 fail closed | `test_cli_bounds_for_suite_and_long_rounds` | PASS |
| spec selection：core 累计 4、long 首轮 1、all 首轮 long 累计 5、long20 末轮保持 L25 | `test_pure_spec_selection_counts_and_long20_final_label` | PASS |
| C2 长输入确定、长度 8_000..15_000、三个 anchor 各出现一次 | `test_byd_long_input_is_deterministic_with_expected_anchors` | PASS |
| MockFinanceMemoryTool tracked session 计数、calls_by_key 摘要 | `test_mock_finance_memory_tool_tracks_session_and_calls_by_key` | PASS |
| pressure off 返回空、auto padding 落在 soft/hard 之间 | `test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds` | PASS |
| answer normalization + required contains + forbidden contains | `test_answer_normalization_contains_and_forbidden_behavior` | PASS |
| fresh/reuse session slot key | `test_smoke_uses_fresh_session_slot_by_default` | PASS |
| provider contract 输出单个 manual-smoke 工具 | `test_discover_smoke_tools_contract_exposes_single_manual_tool` | PASS |
| ToolBundle 可放入 provider 输出 | `test_find_mock_tool_uses_discovered_bundle_shape` | PASS |

所有 S3 目标均有对应测试覆盖，无遗漏。

### 2. 测试是否命中真实 LLM/网络或 private durable state

- 全部 11 个测试均不调用 `open_host`、`submit_followup`、`watch_session_events` 或任何真实 LLM provider。
- 无网络请求、无 DB/sqlite/EventLog/memory table 读取。
- `_prepare_runtime_assembly` 会读取包级配置文件（只读 package config），这是 assembly 测试的必要依赖，不构成 durable state 读取。
- `_write_non_smoke_tool_discovery_overlay` 写入的是 pytest `tmp_path`，隔离安全。
- **PASS**。

### 3. 测试是否对隐藏实现细节脆弱

- 测试断言的契约均为计划中明确定义的公开常量：tool name `get_mock_finance_memory_fact`、tag `manual-smoke`、provider id `host-public-conversation-memory-scenarios-smoke`、slot_key prefix `manual-smoke-conversation-memory-scenarios`、场景 marker 系列、spec label 序列。
- `calls_by_key_summary` 输出格式依赖 `sorted()` 排序，确定性由 Python 词法序保证（`_UNKNOWN_FACT_KEY` < `cmb_nim`），不会因运行环境漂移。
- `test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds` 中 pressure 估算使用了 `context_budget_policy` 的具体阈值比例，但这些比例来自包级配置（`standard-256k` profile），属于公开契约的一部分。若配置参数变更导致估算偏离 soft/hard 区间，测试应正常失败——这是预期行为，不是脆断。
- **PASS**。

### 4. 类型标注/docstring/项目测试风格

- 所有 11 个测试函数及模块级 helper 均有完整中文 docstring，包含参数与返回值说明。
- 无 `Any`、`object`、无类型参数或返回值。
- 模块级常量使用 `Final`。
- 发现一处轻微违规：`from typing import cast`（test 文件 L9）在测试文件中未被使用。`cast` 在此测试文件中为死 import，不违反类型安全但有违整洁原则。**非阻塞 observation**。
- **PASS**。

### 5. S3 implementation artifact 准确性

对照实际代码与测试结果，artifact 中的声明核实如下：

- "11 passed in 0.87s" — 与 controller 提供的验证输出一致。
- "17 passed"（含 test_scene_assets_migration.py）— 与提供的验证输出一致。
- "pyright 0 errors, 0 warnings" — 与提供的验证输出一致。
- 变更文件列表准确。
- 已实现测试覆盖描述准确，与代码一一对应。
- 残余风险分类正确：
  - "未运行真实 LLM / Host end-to-end smoke" — S3 non-goal，正确记录。
  - "自动测试通过 public/runtime helper 验证装配与规格" — 准确描述 S3 边界。
  - Host 内部 compaction/memory projection 语义由既有单元/集成测试承担 — 正确归类。
- 文档决策："未修改 README" — 与 S3 scope 一致（README 留给 S4）。
- **PASS**。

## Findings

### Blocking

无。

### Observation

**O1 — 未使用的 `cast` import（tests L9）**

`tests/runtime/test_smoke_host_public_conversation_memory_scenarios_assembly.py` 第 9 行 `from typing import cast` 在测试文件中无任何调用点。不影响类型安全或测试正确性，但属于死代码。

**建议**：可在 S4 或下一个 cleanup pass 移除。

**O2 — normalization 子串匹配的潜在边界敏感性（非阻塞）**

`normalize_answer` 做空白压缩 + 全角百分号转半角 + casefold 后，`assert_answer_contains` 使用子串包含检查。测试用例 `test_answer_normalization_contains_and_forbidden_behavior` 使用极短 token `"AbC"` 验证 forbidden 机制，展示了短 token 的误伤风险。生产 `RoundSpec.hard_forbidden` 中使用的实际 marker（如 `DAYU_MEM_MAOTAI_REV_2024H1_V1`）长度充足且唯一性高，实际误伤风险低。此 observation 仅记录设计取舍，不要求修改。

**O3 — `test_pressure_off_and_padding_helper_cover_runtime_pressure_bounds` 对配置文件的隐式依赖**

该测试通过 `_prepare_runtime_assembly` 间接依赖 `dayu/config/` 下的 execution profile 配置（`standard-256k`）。若 profile 配置变更导致 `context_budget_policy` 阈值比例偏移，测试可能因 pressure 估算偏离 `[soft, hard)` 区间而失败。这是 assembly 测试的设计意图（验证真实配置上下文中的行为），但需注意此类失败属于"配置变更需同步更新测试断言"的正常维护场景，不是测试脆断。

## Residual Risk 分类复核

对照计划第 15 节，S3 测试对 residual risks 的覆盖状态：

| 计划 residual risk | S3 覆盖状态 |
|---|---|
| `pinned_state` 内部 JSON 不可直接读取 | S3 不涉及；此风险由 Host memory 单元/集成测试承担 |
| compaction 真实触发不可作为 hard assertion | S3 测试验证 pressure padding 估算落在正确的阈值区间，不验证 compaction 是否发生 |
| LLM 可能不按要求输出 assertion line | S3 测试只验证 normalization/assertion helper 机制，不依赖 LLM 输出 |
| long suite 成本高 | S3 不运行真实 long suite，仅验证 spec 选择逻辑 |
| 与最小 smoke 的 assembly pattern 重复 | S3 不涉及；controller 已裁决不抽取 shared helper |

所有计划级别的 residual risk 在 S3 中均得到正确处置：要么由其他测试层承担，要么由 S3 的纯 helper 验证提供间接防护。

## 验证步骤

本 review 执行了以下验证：

1. 对比计划第 12 节测试计划与 11 个测试函数，确认覆盖率。
2. 逐函数阅读生产代码中被测试的 helper（`normalize_answer`、`assert_answer_contains`、`calls_by_key_summary`、`_build_byd_long_input`、`MockFinanceMemoryTool`、`_select_long_templates`、`_compact_pressure_padding` 及其依赖），确认测试断言的正确性。
3. 检查所有 import 路径，确认无 Host private module 泄漏。
4. 检查测试的 network/DB/durable-state 隔离性。
5. 对照 implementation artifact 逐条核实声明准确性。

## Stop Status

S3 code review 完成。PASS，无 blocking finding。本 artifact 不推进后续 gate。
