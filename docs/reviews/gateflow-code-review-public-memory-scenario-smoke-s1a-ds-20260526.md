# Gateflow Code Review: Host Public Conversation Memory Scenario Smoke S1a

- Gate: S1a code review
- Reviewer role: DS (DeepReview)
- Work unit: Host public conversation memory scenario smoke
- Slice: S1a pure script foundations
- Date: 2026-05-26

## Reviewed Artifacts

- Implementation: `utils/smoke_host_public_conversation_memory_scenarios.py`
- Implementation artifact: `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s1a-codex-20260526.md`
- Approved plan: `docs/reviews/gateflow-plan-public-memory-scenario-smoke-20260526.md`
- Controller adjudication: `docs/reviews/gateflow-plan-controller-adjudication-public-memory-scenario-smoke-20260526.md`

## Review Criteria & Findings

### 1. CLI Bounds Correctness — PASS

- `--suite {core,long,all}`：choices 从 `SuiteMode` 枚举值生成，默认 `core`。实测 `core`=14 rounds，`long`=25 rounds，`all`=39 rounds (14+25)，均正确。
- `--long-rounds`：类型为 `_parse_long_rounds`，范围 20..25（通过 `_MIN_LONG_ROUNDS`/`_MAX_LONG_ROUNDS` 常量）。实测 19→exit 2 + error message，26→exit 2 + error message，20→PASS (20 rounds)，25→PASS (25 rounds)。边界 fail-closed 行为正确。
- `--pressure-mode {auto,off}`：choices 从 `PressureMode` 枚举值生成，默认 `auto`。`off` 模式正确打印 `SMOKE PRESSURE disabled`。
- 保留 common args（`--workspace-root`、`--scene-id` 等）全部存在且默认值正确。
- `--long-rounds` 非整数输入（如 `abc`）经 `_parse_long_rounds` 的 `int()` 转换抛出 `ArgumentTypeError`，由 argparse fail-closed。实测确认。

### 2. Pure Spec Selection — PASS

- `select_round_specs` 按 `SuiteMode` 纯数据驱动分发，不存在 label-based `if/elif` 分支。
- `_core_round_specs` 直接构造 `RoundSpec` 元组，每个 spec 的 `label`、`prompt`、`tool_names`、`expected_tool_calls_after_round`、`hard_answer_contains`、`hard_answer_forbidden`、`soft_answer_contains`、`print_calls_by_key` 均为声明式数据。
- `_long_round_specs` 从 `LongRoundTemplate` 元组转换到 `RoundSpec`，无运行时分支。
- `assert_answer_contains` 和 `observe_soft_answer_contains` 为通用 helper，按参数执行，不按 label 分支。
- `RoundSpec` 字段设计完整，与计划 §11 一致。

### 3. Mock Tool Skeleton — PASS

- `MockFinanceMemoryTool` 实现为独立类，包含 `__init__`、`track_session`、`__call__` (async)、`call_count`、`calls_by_key` 属性。
- `calls_by_key` 使用 `Counter[str]`，以 fact key 聚合，未知事实用 `_UNKNOWN_FACT_KEY` 常量。
- session tracking：`_tracked_session_id` 初始为 `None`，仅与 `context.session_id` 完全匹配时计数，避免非 tracked session 污染。
- 未知事实返回 `known=False` 的稳定 shape（`fact_key=_UNKNOWN_FACT_KEY`、`marker=""`、`payload` 中包含 `known=False`），不抛异常。
- `_find_fact_record` 按 `company/ticker/period/topic/metric` 五元组匹配，逻辑正确。
- 六个固定 facts（maotai_revenue、wuliangye_revenue、catl_cashflow、byd_margin_long_input、cmb_nim、midea_long_session）全部在 `_MOCK_FACTS` 中，marker/values 与计划 §7 表格一致。
- pressure blob 构造：`include_pressure=true` 且 `pressure_mode=AUTO` 时返回重复文本（128次重复），`OFF` 或 `include_pressure=false` 时返回空字符串。
- `_fact_payload` 构造的 payload 字段稳定：`known`、`fact_key`、`company`、`ticker`、`period`、`topic`、`marker`、`pressure_blob` 加上 fact 特有 values。

### 4. Long Input Determinism — PASS

- `_build_byd_long_input()` 完全确定性：无随机数、无文件读取、无日期依赖、无外部状态。
- 实测：两次连续调用返回完全相同文本（`text1 == text2`），长度 12206 字符，在 8000..15000 范围内。
- 三个 anchor 各出现恰好一次：`DAYU_LONG_INPUT_FACTOR_1_EXPORT_MIX`(head)、`BATTERY_PRICE_PRESSURE_FACTOR_2`(middle)、`DAYU_LONG_INPUT_FACTOR_3_SCALE_EFFECT`(tail)。
- middle anchor 位于文本中部三分之一区间内（`_assert_byd_long_input` 断言通过）。
- 构造算法：head → 模板填充到 target/2 → middle → 模板填充到 target-len(tail) → tail → 句号填充补齐 → 断言校验。与计划 §8(C) 描述一致。
- `_joined_length` 正确处理空序列（返回 0）和非空序列（sum(len) + count-1 换行符）。

### 5. Long Template Selection — PASS

- `_LONG_ROUND_TEMPLATES` 包含 25 个 `LongRoundTemplate`，标签 L01-L25。
- `_select_long_templates(25)` 返回全部 25 个模板。
- `_select_long_templates(20)` 返回 20 个模板：L01-L19 + L25。实测最后一个是 `long-l25-constraint-assert`。
- 算法 `L01..L(N-1)+L25` 与计划 §8(E) 完全一致。
- 工具启用轮次：L01、L05、L09、L13、L17、L21（6个），与计划 §8(E) 表格一致。
- 工具压力轮次：同上 6 个（`include_tool_pressure=True`），与计划 "tool-enabled pressure" 一致。
- 用户压力轮次：L08、L16、L24（3个，`include_user_pressure=True`），与计划 "user prompt pressure" 一致。
- 所有非工具轮次的 `hard_forbidden` 均设置为 `_CORE_FORBIDDEN_MARKERS_FOR_LONG`（5个 core markers）。所有工具轮次的 `hard_forbidden` 为空元组。实测验证通过。
- L25 的 `hard_contains` 包含 `DAYU_MEM_MIDEA_LONG_2024H1_V1`、`人民币百万元`、`no_multiple_extrapolation`、`内销与外销`，与计划一致。
- `_long_round_specs` 中 `prompt_template.format(auto_user_pressure=pressure_text)` 使用 `str.format` 的额外 kwarg 忽略特性，对不含占位符的模板安全。

### 6. Strict Typing / No Any, No object — PASS

- 所有函数、方法、类均有完整类型注解（含参数、返回值）。
- `ToolArgumentsValue: TypeAlias = str | bool`、`ToolPayloadValue: TypeAlias = str | bool`，类型别名精确。
- 实测：`rg -n "Any|object"` 无匹配（不含 `from __future__ import annotations` 中的 `annotations` 字符串）。
- 所有 dataclass 使用 `frozen=True, slots=True`，字段类型明确。
- 无 `hasattr`/`getattr` 使用。
- 无 lazy import。
- 无嵌套函数/嵌套类。
- 无 `# type: ignore` 注释。

### 7. No Private Host/Durable Reads — PASS

- 实测：`rg -n "dayu\.(host|engine|fins)"` 无匹配。
- 无 `sqlite3` import。
- 无文件系统读取 `.dayu/host/`、EventLog、memory table、compact payload。
- 脚本完全 self-contained，仅依赖 Python 标准库（`argparse`、`asyncio`、`pathlib`、`re`、`sys`、`collections`、`dataclasses`、`enum`、`typing`）。
- `_skeleton_probe_tool` 直接实例化 `MockFinanceMemoryTool` 并调用，不经过 Host lifecycle。符合 S1a standalone skeleton 定位。

### 8. No Semantic Drift to Existing Minimal Smoke — PASS

- `utils/smoke_host_public_conversation_memory.py` 未被修改（不在 S1a allowed files 中）。
- 新脚本使用不同工具名 `get_mock_finance_memory_fact`（vs 最小 smoke 的 `get_mock_finance_facts`）。
- 新脚本使用不同 scene id `smoke_host_public_conversation_memory_scenarios`。
- 新脚本使用不同 provider id `host-public-conversation-memory-scenarios-smoke`。
- 新脚本使用不同 schema（多了 required `ticker` 字段），不会与最小 smoke 的 tool selection 冲突。
- 两个脚本各自独立，无 shared helper extraction，最小 smoke 语义不受影响。

### 9. S1a Artifact Accuracy — PASS

Implementation artifact 列出的所有 implemented items 均已在代码中验证存在：
- 中文 docstring：全部模块、类、函数、方法均有完整中文 docstring（含参数、返回值、异常）。
- CLI parsing：全部参数均在 `parse_args` 中实现。
- 基础类型：`SmokeArgs`、`SuiteMode`、`PressureMode`、`RoundSpec`、`LongRoundTemplate`、`MockFactRecord`、`MockFinanceMemoryTool`、`MockToolCallRequest`、`MockToolExecutionContext`、`MockToolResponse` 均已实现。
- Mock fact constants、markers、assertion lines、stdout prefix：均在模块级 `Final` 常量中。
- C2 deterministic long input builder：`_build_byd_long_input()` 实现完整。
- L01-L25 long templates：`_LONG_ROUND_TEMPLATES` 25 个模板，`_LONG_PROMPT_01` 到 `_LONG_PROMPT_25` 常量完整。
- calls_by_key formatter：`calls_by_key_summary` 实现，输出 `SMOKE TOOL_CALLS_BY_KEY key=count ...` 格式。
- answer normalization 与 assertion helper：`normalize_answer`、`assert_answer_contains`、`observe_soft_answer_contains` 均实现。
- `__main__` 入口：解析 CLI、选择 specs、执行 probe、打印 skeleton ready。

S1b 延后项（Host lifecycle、scene assembly、tool discovery、watcher、session/run assertions）均未实现，符合 S1a scope 约束。

### 10. Additional Observations (Non-blocking)

- **OBS-1 (cosmetic)**：`_core_round_specs` 中 `core-d2` prompt 在 `pressure_mode=OFF` 时产生 `：。`（冒号紧接句号），不影响功能。
- **OBS-2 (defensive)**：`_select_long_templates` 中的范围检查 `if round_count < _MIN_LONG_ROUNDS or round_count > _MAX_LONG_ROUNDS` 与 CLI 层 `_parse_long_rounds` 的检查重复。这是防御性编程，不构成问题，但若日后 CLI 层边界变更，需同步两处。
- **OBS-3 (consistency)**：`observe_soft_answer_contains` 的 `label` 参数通过 `del label` 显式标记为故意未使用，并在 docstring 说明保留给调用方打印诊断。这是合理的 API 一致性设计。

## Controller Validation Re-run

Controller 提供的验证已重新执行并确认：

```text
python -m py_compile utils/smoke_host_public_conversation_memory_scenarios.py  # PASS
python utils/smoke_host_public_conversation_memory_scenarios.py --suite core --pressure-mode off  # PASS, exit 0
python utils/smoke_host_public_conversation_memory_scenarios.py --suite long --pressure-mode off  # PASS, exit 0
python utils/smoke_host_public_conversation_memory_scenarios.py --suite all --pressure-mode off  # PASS, exit 0
```

pyright 已在 S1a implementation 阶段验证通过（0 errors）。

## Verdict

**PASS** — 无 blocking issue。

S1a pure script foundation 实现质量良好，所有 9 项 review criteria 均通过。CLI bounds 正确 fail-closed，spec selection 纯数据驱动，mock tool skeleton 完整且 session tracking 正确，长输入完全确定性，长模板选择 L01..L(N-1)+L25 逻辑正确，类型签名严格完整，无 private Host/durable 读取，现有最小 smoke 语义不受影响，S1a artifact 描述准确。

S1b（Host flow）、S2（scene assets）、S3（tests）、S4（README）按计划延后。
