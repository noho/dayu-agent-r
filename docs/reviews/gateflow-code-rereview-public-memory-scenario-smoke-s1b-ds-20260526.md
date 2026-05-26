# Gateflow Code Re-Review：Public Memory Scenario Smoke S1b

## Gate

- Work unit：Host public conversation memory scenario smoke
- 当前 gate：S1b re-review
- 复审目标（fixed）：
  - `utils/smoke_host_public_conversation_memory_scenarios.py`
- 源 review：`docs/reviews/gateflow-code-review-public-memory-scenario-smoke-s1b-ds-20260526.md`
- Fix artifact：`docs/reviews/gateflow-fix-public-memory-scenario-smoke-s1b-codex-20260526.md`
- 复审范围：Finding 1、Finding 2。Finding 3/4 deferred，仅在修复恶化时报告。

---

## Fix 变更审查

### 变更点

| 变更 | 位置 | 说明 |
|------|------|------|
| 新增 `_INITIAL_TOOL_CALL_COUNT` | line 103 | `Final[int] = 0`，消除魔法数字 |
| 新增 `_round_specs_for_suite` | line 1155–1180 | 共享 helper，统一 CORE/LONG/ALL 三种 suite 的 spec 生成与累积计数 |
| 新增 `_final_expected_tool_calls` | line 1183–1193 | 从 spec 序列读取最后一轮的 `expected_tool_calls_after_round`；空序列返回 `_INITIAL_TOOL_CALL_COUNT` |
| 重构 `select_round_specs` | line 1140–1152 | 删除内联重复逻辑，委托 `_round_specs_for_suite` |
| 重构 `_runtime_round_specs` | line 1990–2007 | 删除内联重复逻辑，委托 `_round_specs_for_suite` |
| `_long_round_specs` 增加 `base_expected_calls` | line 1479–1495 | keyword-only 参数，默认 `_INITIAL_TOOL_CALL_COUNT`；`expected_calls` 从该基数起算而非硬编码 0 |

### 修复策略评估

修复策略与初 review 建议一致：给 `_long_round_specs` 增加 `base_expected_calls` 参数，ALL 模式传入 core 最后一轮的累计值。同时通过 `_round_specs_for_suite` 消除了 `select_round_specs` 与 `_runtime_round_specs` 之间的重复逻辑。

修复无需改变 `MockFinanceMemoryTool` 的计数行为，不引入 session 重置或副作用，最小化改动量，符合修复纪律。

---

## Finding 1 逐路径验证

### CORE alone

```
select_round_specs(suite=CORE) → _core_round_specs(...)
_runtime_round_specs(suite=CORE) → _core_round_specs(...)
```

core 规格未修改，`expected_tool_calls_after_round` 仍为 `1,1,2,2,3,3,3,3,3,3,3,3,4,4,4`。

**PASS** — core final = 4，与修复前一致。

### LONG alone

```
_runtime_round_specs(suite=LONG) → _long_round_specs(pressure, rounds)
  base_expected_calls 默认 = _INITIAL_TOOL_CALL_COUNT = 0
```

`expected_calls` 从 0 起算，长套件内首轮工具期望值 = 1。

**PASS** — long standalone 行为不变。

### ALL mode

```
_runtime_round_specs(suite=ALL) → _round_specs_for_suite(suite=ALL)
  core_specs = _core_round_specs(...)                    # final = 4
  long_specs = _long_round_specs(pressure, rounds,
    base_expected_calls=_final_expected_tool_calls(core_specs))  # base = 4
```

long 套件内 `expected_calls` 从 4 起算，首轮工具 L01 期望值 = 5。

**PASS** — 修复前此处 `expected=1, actual=5` 必然 RuntimeError；修复后 `expected=5, actual=5`。

### ALL mode (path via select_round_specs)

```
select_round_specs(suite=ALL) → _round_specs_for_suite(suite=ALL)
```

与 runtime 路径共享同一 `_round_specs_for_suite` 逻辑。

**PASS** — `select_round_specs` 不再包含独立的错误拼接逻辑。

### long 20/25 round counts

`_select_long_templates(20)` → L01..L19 + L25 = 20 rounds  
`_select_long_templates(25)` → full L01..L25 = 25 rounds  
long20 last label = `long-l25-constraint-assert`  
long25 last label = `long-l25-constraint-assert`

**PASS** — round count selection 不变。

### Controller SPEC_CHECK 确认

```
SPEC_CHECK PASS core_final=4 long_first=1 all20_first_long=5 all25_first_long=5
long20_len=20 long25_len=25 long20_last=long-l25-constraint-assert
```

所有断言值与手动推演一致。

---

## Finding 2 验证

**原问题**：`select_round_specs` 死代码，且包含与 Finding 1 相同的 ALL 模式 bug，与 `_runtime_round_specs` 存在两套不一致的拼接逻辑。

**修复后**：`select_round_specs` 委托 `_round_specs_for_suite`，与 runtime 路径共享同一 suite 选择逻辑和累积计数。仅在 `user_pressure_text` 来源上有意区分：
- `select_round_specs` → `_user_pressure_placeholder`（纯 spec，不需要 runtime options）
- `_runtime_round_specs` → `_runtime_user_pressure_text`（带 budget-based padding）

**PASS** — `select_round_specs` 不再是死代码，ALL 模式 bug 已消除，两路径语义一致。

---

## 回归检查

| 检查项 | 结果 |
|--------|------|
| pyright 单文件 0 errors | PASS（controller 已验证） |
| py_compile 通过 | PASS（controller 已验证） |
| Host public API boundary 是否保持 | PASS（未新增 private import） |
| 已有 minimal smoke 未修改 | PASS（`smoke_host_public_conversation_memory.py`、`smoke_host_public_multiturn.py` 不变） |
| Finding 3/4 是否恶化 | PASS（`_compact_pressure_reserve_tokens` 和 padding 逻辑未改动） |
| 是否引入新魔法数字或 Any/object | PASS（新增 `_INITIAL_TOOL_CALL_COUNT` 是 Final[int]，`_final_expected_tool_calls` 返回 int，类型严格） |
| 修复是否引入新 bug | PASS（变更限于 spec 生成路径，不影响 runtime submit/watch/session 流程） |

---

## Finding 状态映射

| Finding | 初 review 状态 | 修复后状态 |
|---------|---------------|-----------|
| Finding 1 — ALL mode 累积调用断言错误 | BLOCKING | **RESOLVED** |
| Finding 2 — `select_round_specs` 死代码/ALL mode bug | INFO | **RESOLVED** |
| Finding 3 — `_compact_pressure_reserve_tokens` 恒真分支 | INFO | DEFERRED（controller 决策，未恶化） |
| Finding 4 — `target_tokens` 极小窗口边界 | INFO | DEFERRED（controller 决策，未恶化） |

---

## Verdict

**PASS**

Finding 1（BLOCKING）和 Finding 2（INFO）均已正确修复。`_round_specs_for_suite` 共享 helper 同时消除了两个函数中的重复拼接逻辑和 ALL 模式累积计数错误。CORE/LONG standalone 行为不变。修复策略与初 review 建议一致，无新增 blocker，未恶化 deferred finding。controller SPEC_CHECK 全覆盖验证通过。
