# Gateflow Fix Artifact：Public Memory Scenario Smoke S1b

## Gate

- Work unit：Host public conversation memory scenario smoke
- 当前 gate：S1b fix
- Worker：Codex fix worker
- Source review：`docs/reviews/gateflow-code-review-public-memory-scenario-smoke-s1b-ds-20260526.md`
- 约束：未启动 Gateflow；未提交、未 push、未开 PR、未进入其它 gate。

## Accepted Findings

### Finding 1 - 已修复 - [BLOCKING] `--suite all` 模式 round 累积调用断言错误

- **修复状态**：已修复。
- **修复内容**：
  - 新增共享 helper `_round_specs_for_suite`，让 `select_round_specs` 和 `_runtime_round_specs` 使用同一套 suite 选择逻辑。
  - `_long_round_specs` 新增 `base_expected_calls` keyword-only 参数，默认值为初始工具调用计数。
  - `SuiteMode.ALL` 先生成 core specs，再把 core 最后一轮的 `expected_tool_calls_after_round` 作为 long suite 的累计基数。
- **行为结果**：
  - core 独立运行最终期望工具调用数仍为 4。
  - long 独立运行仍从 0 基数开始，首个工具轮期望值仍为 1。
  - all 模式使用同一 session 时，long 首个工具轮期望值为 5，即 core final 4 + 1。

### Finding 2 - 已修复 - [INFO] `select_round_specs` 死代码/同类 ALL 模式 bug

- **修复状态**：已修复。
- **修复内容**：
  - 保留 `select_round_specs` 作为纯 spec 选择入口，但不再维护独立拼接逻辑。
  - `select_round_specs` 改为调用 `_round_specs_for_suite`，与 runtime 路径共享 ALL 模式累计计数语义。
- **行为结果**：纯 spec 入口与 runtime 入口不再存在两套 ALL 模式计数规则。

## Deferred Findings

- Finding 3 `_compact_pressure_reserve_tokens` 恒真分支：按 controller 指示 deferred，本次未修改。
- Finding 4 tiny context target edge：按 controller 指示 deferred，本次未修改。

## Changed Files

- `utils/smoke_host_public_conversation_memory_scenarios.py`
- `docs/reviews/gateflow-fix-public-memory-scenario-smoke-s1b-codex-20260526.md`

## Validation

执行目录：`/Users/leo/workspace/dayu-agent-r`

```bash
source .venv/bin/activate && python -m py_compile utils/smoke_host_public_conversation_memory_scenarios.py
```

结果：通过，无输出。

```bash
source .venv/bin/activate && pyright utils/smoke_host_public_conversation_memory_scenarios.py
```

结果：

```text
0 errors, 0 warnings, 0 informations
```

纯 spec 检查：

```bash
source .venv/bin/activate && python -c '<pure spec assertions>'
```

结果：

```text
SPEC_CHECK PASS core_final=4 long_first=1 all20_first_long=5 all25_first_long=5 long20_len=20 long25_len=25 long20_last=long-l25-constraint-assert
```

覆盖断言：

- core alone：最终 `expected_tool_calls_after_round == 4`。
- long alone：首个工具轮 `expected_tool_calls_after_round == 1`，保持相对 0 起算。
- all：first long tool round `expected_tool_calls_after_round == core final + 1 == 5`。
- long 20/25：20 轮仍为 `L01..L19 + L25`；25 轮仍为完整 `L01..L25`。

## Docs Decision

未更新 README。本次只修复 manual smoke 工具内部 suite spec 生成逻辑，未改变用户入口、CLI 参数、配置入口或项目分层说明；且 handoff 明确允许文件不包含 README。

## Residual Risks

- 未运行 full end-to-end Host smoke；S1b 当前仍受后续 scene manifest / prompt assets 准备状态影响。Owner：后续 S2 slice。
- Finding 3 与 Finding 4 按 controller 决策 defer。Owner：controller 后续裁决或后续 work unit。

## Stop Status

S1b fix 已完成并停止。未提交、未 push、未开 PR、未进入 re-review 或其它 gate。
