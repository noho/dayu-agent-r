# Gateflow Code Review：Public Memory Scenario Smoke S1b

## Gate

- Work unit：Host public conversation memory scenario smoke
- 当前 gate：code review (S1b)
- 复审目标：
  - `utils/smoke_host_public_conversation_memory_scenarios.py`
  - `docs/reviews/gateflow-implementation-public-memory-scenario-smoke-s1b-codex-20260526.md`
- 复审人：DS review worker
- Controller 已通过：`py_compile`、`pyright 0 errors`、边界 grep 全部 0 匹配。
- S1a accepted commit：`2c98662`
- 复审标准：Host public API boundary、Service 装配正确性、submit/watch/session 流程、terminal 处理、工具计数断言、hard/soft answer 断言、类型与 docstring 纪律、不触碰 private durable/EventLog/memory、不修改已有 minimal smoke。

---

## 逐项核对

### 1. Host public API boundary only

| 检查项 | 结果 |
|--------|------|
| import 来源均为 `dayu.host` 公共根导出（`__all__` 核实） | PASS |
| 未 import `dayu.host.durable`、`dayu.host.read_api` 内部子模块 | PASS |
| 未 import sqlite3、EventLog、memory table reader | PASS |
| 未读取 compact artifact 内容 | PASS |
| `get_run` 仅在 terminal failure 诊断路径调用，使用 public `RunSnapshot` 字段 | PASS |
| `get_session` / `ensure_session` 使用 public `SessionSnapshot` | PASS |

`dayu/host/__init__.py` 确认所有 import 符号均在 `__all__` 中：
`Host`、`HostEvent`、`HostEventKind`、`SessionSnapshot`、`SessionStatus`、`open_host`、
`OpenHostOptions`、`EnsureSessionRequest`、`FollowupBehavior`、`AuthorizationClaim`、
`HostCallContext`、`OperationContext`、`SubmitFollowupRequest` 均为公共导出。

### 2. Service-like assembly and ToolsDiscovery-compatible mock provider

| 检查项 | 结果 |
|--------|------|
| `discover_smoke_tools` 实现 `ToolsDiscoveryProvider` callable 签名（`(spec) -> ToolsDiscoveryProviderOutput`） | PASS |
| `_discover_builtin_smoke_tools` 走 `ToolsDiscovery().discover_from_bindings` | PASS |
| `_discover_smoke_service_tools` 先检查现有名冲突再合入 | PASS |
| `compose_open_host_options` / `compose_submit_followup_request` 使用对等 existing smoke 风格 | PASS |
| assembly flow：`resolve_runtime_locations` → `ConfigLoader.load` → `discover_service_tools` → `prepare_scene` → `compose_open_host_options` | PASS |

### 3. submit/watch/session flow correctness

| 检查项 | 结果 |
|--------|------|
| `open_host` 使用 async context manager | PASS |
| `ensure_session` → `watch_session_events` 建立 watcher | PASS |
| 每轮：`submit_followup`（`FollowupBehavior.QUEUE`） → `_next_terminal_for_run` 等待 terminal event | PASS |
| terminal non-success 时仅通过 `host.get_run(run_id)` 获取脱敏摘要，不读 durable | PASS |
| `_safe_summary_text` 脱敏 API key / bearer / token / secret | PASS |
| `_assert_session_open` 逐轮确认 session 未关闭 | PASS |
| `asyncio.wait_for` timeout 600s 保护 | PASS |

### 4. Per-round tool_names / tool call count / hard-soft assertions

| 检查项 | 结果 |
|--------|------|
| `tool_names` 通过 `compose_submit_followup_request` 透传 | PASS |
| 禁用工具轮使用 `frozenset()`（非 `None` 或 `[]`） | PASS |
| `_assert_tool_call_count` 按 `expected_tool_calls_after_round` 精确比对 | **FAIL**（见 Finding 1） |
| `assert_answer_contains` 硬断言 required/forbidden | PASS |
| `observe_soft_answer_contains` 软观察只打印不失败 | PASS |

### 5. Strict typing / docstrings / no Any-object-getattr-hasattr

| 检查项 | 结果 |
|--------|------|
| 无 `Any` / `object` 签名 | PASS（controller grep 已确认） |
| 无 `getattr` / `hasattr` | PASS |
| 所有公共函数有中文 docstring | PASS |
| `isinstance(definition.callable, MockFinanceMemoryTool)` 是类型检查非 `hasattr` 变体 | PASS |

### 6. 已有 minimal smoke 未被修改

| 文件 | 状态 |
|------|------|
| `utils/smoke_host_public_conversation_memory.py` | 未修改（`git diff` 0 行） |
| `utils/smoke_host_public_multiturn.py` | 未修改（`git diff` 0 行） |

### 7. S1b codex artifact 准确性

| 声称 | 核查 |
|------|------|
| "未修改现有 minimal smoke" | 确认 |
| "未读取 private Host durable state" | 确认 |
| pyright 0 errors | 确认 |
| 残余风险"End-to-end Host 执行尚未验证" | 确认合理 |
| 残余风险"默认 scene id 可能因资源缺失运行失败" | 确认合理 |

---

## 发现

### Finding 1 — [BLOCKING] `--suite all` 模式 round 累积调用断言错误

**位置**：`_runtime_round_specs`（line 1951–1971）和 `select_round_specs`（line 1139–1157）

**描述**：

`_long_round_specs` 内部 `expected_calls` 从 0 起算，即默认 long 套件在独立 session 中运行。
当 `--suite all` 时，`_runtime_round_specs` 拼接 core + long：

```python
# line 1968–1971
return (
    *_core_round_specs(user_pressure_text),
    *_long_round_specs(user_pressure_text, args.long_rounds),
)
```

core 套件硬编码 `expected_calls` 最多到 4。long 套件 `expected_calls` 从 0 起算。
但 `MockFinanceMemoryTool._call_count` 是跨 suite 累积的——`track_session` 不重置计数器。

因此 `--suite all` 的实际行为：
- core 套件跑完 → `call_count = 4` ✓
- long L01（tool call）→ `expected = 1`，`actual = 5` → **RuntimeError**

**Proof（逻辑推演）**：

1. `_long_round_specs` line 1456：`expected_calls = 0`
2. line 1459：`if template.tool_enabled: expected_calls += 1`
3. line 1468：`expected_tool_calls_after_round=expected_calls`（long 套件内相对值）
4. `MockFinanceMemoryTool.track_session` line 1001：只设 `_tracked_session_id`，不重置计数
5. `_assert_tool_call_count` line 2224：`if smoke_tool.call_count != expected` 直接抛 `RuntimeError`
6. long 首轮 tool 断言值写死为 1，`call_count` 实际为 5

**影响**：`--suite all` 运行到 long 首轮必然 `RuntimeError`。虽然默认 `--suite core` 不受影响，但 `SuiteMode.ALL` 会静默失败。

**建议修复**：

`_long_round_specs` 增加 `base_expected_calls: int = 0` 参数；`--suite all` 时传入 core 套件结束后的累积值（当前为 4）。同理应修复 `select_round_specs`（如果保留该函数）或删除死代码。

---

### Finding 2 — [INFO] `select_round_specs` 死代码

**位置**：line 1139–1157

**描述**：`select_round_specs` 是公共函数，签名为 `(SmokeArgs) -> tuple[RoundSpec, ...]`，但其仅在定义处出现一次，`run_smoke` 走 `_runtime_round_specs`。当前无任何调用方。

该函数还包含与 Finding 1 相同的 ALL 模式 bug，且使用 `_user_pressure_placeholder`（不含 runtime budget 逻辑），与 `_runtime_round_specs` 语义不统一。

**建议**：删除或明确其用途。若保留，至少需修复 Finding 1 的一致性问题。

---

### Finding 3 — [INFO] `_compact_pressure_reserve_tokens` 恒真分支

**位置**：line 2307–2317

```python
def _compact_pressure_reserve_tokens(*, context_window_size: int) -> int:
    if context_window_size >= _COMPACT_PRESSURE_LARGE_WINDOW_TOKENS:
        return _COMPACT_PRESSURE_RESERVE_TOKENS
    return _COMPACT_PRESSURE_RESERVE_TOKENS
```

两个分支返回相同值，if/else 无实际分流效果。不影响正确性，但暗示可能缺失实际差异化逻辑。

**建议**：要么实现真实的窗口大小分流，要么压缩为单行 `return _COMPACT_PRESSURE_RESERVE_TOKENS`。

---

### Finding 4 — [INFO] `_compact_pressure_padding` target_tokens 边界

**位置**：line 2277–2280

```python
target_tokens = min(
    soft_threshold_tokens + _COMPACT_PRESSURE_TARGET_EXTRA_TOKENS,
    hard_threshold_tokens - _COMPACT_PRESSURE_HARD_MARGIN_TOKENS,
)
```

若模型 `context_window_size` 极小（如 < 25k），`hard_threshold_tokens - _COMPACT_PRESSURE_HARD_MARGIN_TOKENS` 可能为负，导致负 `target_tokens`。虽然生产模型窗口远超此值，但该函数未防护极值输入。下游 `prompt_tokens = max(_COMPACT_PRESSURE_MIN_PROMPT_TOKENS, ...)` 提供了兜底，故风险可控。

---

## Residual Risk（新增）

- **ALL mode bug（Finding 1）**：S2 场景如果使用 `--suite all`，long 套件断言必然失败。需在 S2 前修复。
- **select_round_specs 死代码（Finding 2）**：S2 或后续 slice 如果发现该函数并试图调用，也会触发相同的 ALL mode bug。
- 其余风险与 S1b codex artifact 记录一致（scene manifest 缺失、LLM answer 格式漂移等）。

---

## Verdict

**BLOCKED — Finding 1（`--suite all` 累积调用断言错误）**

Host public API boundary、Service 装配、submit/watch/session 流程、terminal 处理、类型与 docstring 纪律、不触碰 private 层均通过验证。

但 `_runtime_round_specs` 和 `select_round_specs` 在 `--suite all` 路径下存在正确的工具累积次数断言错误：long 套件的 `expected_tool_calls_after_round` 从 0 起算，但 `MockFinanceMemoryTool._call_count` 在 core 套件后已累积到 4，导致 long 首轮必然 RuntimeError。默认 `--suite core` 不受影响，但 `SuiteMode.ALL` 为静默 bug。需在 S2 前修复。

Finding 1 修复后，Review 可升级为 PASS。
