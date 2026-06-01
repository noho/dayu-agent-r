# WU-CTX-02 + WU-CTX-03 Slice E Focused Re-Review — AgentDS

## 结论

**Accepted — F-1 已正确修复，无新增 findings，无阻塞项。**

## 核查范围

- **复核对象**: AgentCodex 对 DS F-1 (MEDIUM) 的修复 —— `tests/host/test_dispatch_scheduler.py` 中 `_soft_compact_policy` 的 `max_reactive_compactions_per_run` 默认值从字面量 `2` 改为 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN`。
- **变更文件**: 仅 `tests/host/test_dispatch_scheduler.py`（1 处 import 新增 + 1 处默认值修改）。
- **Fix artifact**: `docs/reviews/wu-ctx-02-03-fix-sliceE-codex-20260601.md`
- **先前 artifact**:
  - `docs/reviews/wu-ctx-02-03-implementation-sliceE-codex-20260601.md`
  - `docs/reviews/wu-ctx-02-03-code-review-sliceE-mimo-20260601.md`
  - `docs/reviews/wu-ctx-02-03-code-review-sliceE-ds-20260601.md`
- **Base**: Slice D accepted commit `13500ae` + Slice E implementation + 本次修复。

## Findings

### No blocking findings.

以下逐项核查。

---

### F-1 修复验证 (DS F-1, MEDIUM) — 已修复

**原始问题**: `_soft_compact_policy` 的 `max_reactive_compactions_per_run: int = 2` 与 `ContextBudgetPolicy` dataclass field default 形成双重真源。

**修复内容**:
1. 新增 import（line 67）:
   ```python
   from dayu.host.context_policy import (
       ...
       DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN,
   )
   ```
2. 默认值改为常量引用（line 4443）:
   ```python
   max_reactive_compactions_per_run: int = DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN,
   ```

**验证结果**:

| 检查项 | 状态 | 说明 |
|---|---|---|
| 常量定义位置 | ✅ | `dayu/host/context_policy.py:21`: `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN = 2` |
| 生产代码使用 | ✅ | `ContextBudgetPolicy` 两个 dataclass field（lines 168, 210）均引用该常量 |
| 常量在 `__all__` | ✅ | `context_policy.py:301` 导出，可被外部 import |
| 现有调用方行为不变 | ✅ | 16 处 `_soft_compact_policy()` 无参调用（lines 3154-4055）均获得 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` → `2`，行为与前一致 |
| 新测试显式值不变 | ✅ | `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` line 3970 显式传 `max_reactive_compactions_per_run=2`，与常量值一致 |
| 双重真源消除 | ✅ | 若未来 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` 改为 3，`_soft_compact_policy` 默认值同步变更，不再独立漂移 |

**结论**: F-1 已正确修复，未引入测试语义漂移。

---

### 测试语义漂移检查 — 无漂移

逐项确认：

1. **`_soft_compact_policy` 语义不变**: 默认值 `2` → `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN`（=2），运行时等价。无参调用方、显式传参调用方（`max_reactive_compactions_per_run=2`）行为完全不变。
2. **新测试断言不变**: `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` 的 `expected_attempt_count` 仍为 `1 + policy.max_reactive_compactions_per_run = 3`，所有事件计数断言不变。
3. **`<=` 冗余断言保留**: line 4010 `assert actual_attempt_count <= expected_attempt_count` 保留。MiMo 标记为 informational，controller 裁决保留——plan 明确要求同时断言 equality 和 upper bound。不阻塞。

---

### 此前 INFO Findings 状态

| Finding | 描述 | 本次处理 |
|---|---|---|
| DS F-2 (INFO) | `_REPEATED_OVERFLOW_SYNC_TIMEOUT_SECONDS` 语义归类 | Deferred — 不在本次修复范围 |
| DS F-3 (INFO) | `create_worker` 中 `del snapshot` 模式延续 | Deferred — 不在本次修复范围 |
| DS F-4 (INFO) | `_event_types_for_run` 硬编码 `limit=200` | Deferred — 不在本次修复范围 |
| MiMo F-01 (INFO) | `<=` 冗余断言 | 保留 — controller 裁决，plan 要求 |

均不阻塞本次 gate。

---

### README 变更判断

**无需更新。** 本次修复仅将测试 helper 默认值来源从字面量改为常量引用，不改变测试覆盖范围、不改变 public API、不改变配置入口。按 AGENTS.md README 触发规则逐项检查：

| README | 触发条件 | 是否触发 | 说明 |
|---|---|---|---|
| `tests/README.md` | `tests/` 修改 | 否（本次） | Slice E 实现阶段已更新（line 132: "连续 reactive overflow dispatch-loop 达到上限后 fail closed 且不写 `RUN_LOST`"），本次修复不改变覆盖语义 |
| `dayu/host/README.md` | `dayu/host/` 修改 | 否 | 无生产代码变更 |
| `dayu/config/README.md` | `dayu/config/` 修改 | 否 | 无配置变更 |
| 根 `README.md` | CLI/配置入口变化 | 否 | 无入口变化 |

---

## 验证可信度评估

Fix artifact 声称的验证结果：

| 声称 | 可信度 | 理由 |
|---|---|---|
| `pytest tests/host/test_dispatch_scheduler.py -q` → 57 passed | 高 | 与原始实现（57 passed, 1.10s）、MiMo 验证（57 passed, 1.02s）一致；修复仅改默认值来源，不改变运行时行为 |
| `python -m pyright dayu/ tests/ utils/` → 0 errors | 高 | 新增 import 从已导出的 `__all__` 符号引入，类型路径合法；MiMo 原始验证同为 0 errors |

改动极小（1 行 import + 1 行默认值），与已验证通过的原始实现行为等价，验证结果可信。

---

## 残余风险

- **F-2/F-3/F-4 deferred**: 三个 INFO 级 finding 保留，不阻塞后续 gate。若后续 Slice 触及相关代码区域，建议一并处理。
- **常量值未来变更**: 若 `DEFAULT_MAX_REACTIVE_COMPACTIONS_PER_RUN` 未来从 2 改为其他值，`_soft_compact_policy` 默认值将自动同步——这正是本修复的目的。但需注意 `test_reactive_repeated_overflow_dispatch_loop_fails_closed_at_limit` 显式传 `max_reactive_compactions_per_run=2`，届时需同步更新该测试的显式参数以保持语义一致。该风险属于"常量变更时的常规维护"，不属于本 Slice 缺陷。
