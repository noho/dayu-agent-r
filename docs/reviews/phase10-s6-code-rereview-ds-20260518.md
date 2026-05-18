# Phase 10 Slice 6 Code Re-Review — AgentDS

**Review Date:** 2026-05-18
**Reviewer:** AgentDS
**Re-Review Scope:** F2 (必填 typed input) + F4 (multi-turn E2E) fix verification
**Verdict: PASS**

## 复核方法

逐条验证 Controller 裁决的两项修复（F2、F4），交叉检查是否引入新风险。不重新审查 controller-accepted residuals（F1、F3）。

---

## F2 复核: `context_window_size` / `reserved_output_tokens` 必填 typed input

### 2.1 默认值是否已移除

**验证:** `grep -rn 'HOST_CONTEXT_WINDOW_SIZE_DEFAULT\|HOST_RESERVED_OUTPUT_TOKENS_DEFAULT' dayu/host/` — **零匹配**。原 `api.py:61-63` 的两个常量已完全删除。

**验证:** `HostCommandHandleOptions` 字段声明（`api.py:1172-1173`）:

```python
context_window_size: int          # 无默认值
reserved_output_tokens: int       # 无默认值
```

对比修复前:
```python
context_window_size: int = HOST_CONTEXT_WINDOW_SIZE_DEFAULT   # 8192
reserved_output_tokens: int = HOST_RESERVED_OUTPUT_TOKENS_DEFAULT  # 1024
```

**验证:** `test_host_command_handle_options_require_explicit_budget_inputs` (`test_public_contracts.py:586-594`) 使用 `dataclasses.MISSING` 哨兵断言两个字段 `default is MISSING`。

**结论: F2 默认值已完全移除，字段为必填 typed input。** ✓

### 2.2 所有构造点是否已显式传入

**验证:** 检查所有 11 个受影响的测试文件:

| 文件 | 构造点 | 显式传入 |
|------|--------|----------|
| `test_public_contracts.py` | `_host_command_handle_options()` | `8192, 1024` |
| `test_command_handle.py` | `_options()` ×2, `test_factory_rejects_local_execution...` ×2 | `8192, 1024` |
| `test_active_cancel_dispatch.py` | `_command_options()` | `8192, 1024` |
| `test_logging.py` | `_command_options()` | `8192, 1024` |
| `test_projection_read_model.py` | `_options()` | `8192, 1024` |
| `test_public_cancel_session_runs.py` | `_options()` | `8192, 1024` |
| `test_public_event_stream.py` | `_options()` | `8192, 1024` |
| `test_public_run_api.py` | `_options()` | `8192, 1024` |
| `test_public_session_api.py` | `_options()` | `8192, 1024` |
| `test_resolve_wait_command.py` | `_options()` | `8192, 1024` |
| `test_phase5_local_execution_integration.py` | `_command_options()` | `8192, 1024` |

无遗漏。若 composition root 忘记传入，dataclass 构造直接 `TypeError: missing required arguments`，不会静默使用默认值。

**结论: 所有构造点已显式传入。** ✓

### 2.3 fallback 是否基于显式 options 而非旧固定 command 默认

**验证 `_validate_command_context_budget_fields`** (`api.py:1243-1269`):

```python
minimum_protection_tokens = (
    options.context_budget_minimum_protection_tokens
    if options.context_budget_minimum_protection_tokens is not None
    else DEFAULT_MINIMUM_PROTECTION_TOKENS  # 256, from context_policy.py
)
default_context_budget_policy(
    context_window_size=options.context_window_size,    # ← 显式 options 值
    reserved_output_tokens=options.reserved_output_tokens,  # ← 显式 options 值
    hard_threshold_tokens=options.context_budget_hard_threshold_tokens,
    minimum_protection_tokens=minimum_protection_tokens,
)
```

- `context_window_size` / `reserved_output_tokens` 直接来自 options 字段（无 command 级默认）
- 仅 `context_budget_minimum_protection_tokens=None` 时 fallback 到 `DEFAULT_MINIMUM_PROTECTION_TOKENS=256` — 这是 policy 层的通用常量，合法
- 不存在 `HOST_CONTEXT_WINDOW_SIZE_DEFAULT` / `HOST_RESERVED_OUTPUT_TOKENS_DEFAULT` 的静默回退路径

**验证 `_minimum_protection_tokens_from_options`** (`command.py:305-319`):

```python
if options.context_budget_minimum_protection_tokens is not None:
    return options.context_budget_minimum_protection_tokens
return default_context_budget_policy(
    context_window_size=options.context_window_size,    # ← 显式
    reserved_output_tokens=options.reserved_output_tokens,  # ← 显式
).minimum_protection_tokens
```

Fallback 路径构造临时 policy，从显式 window/reserved 推导默认 minimum_protection_tokens（256），不使用固定 command 默认。

**一致性验证:** `_validate_command_context_budget_fields` 和 `_minimum_protection_tokens_from_options` 对 `None` minimum_protection 的 fallback 行为等价（均得到 256），不会出现一者通过校验、另一者构造失败的情况。

**结论: fallback 均基于显式 options 字段。** ✓

### F2 裁定: **已修复，无残留。**

---

## F4 复核: Multi-turn aggregate integration test

### 4.1 测试是否真实串起 scheduler pre-start governance → proactive compact → CONTEXT_COMPACTED → memory projection → Engine request

**测试:** `test_multi_turn_proactive_compact_feeds_subsequent_run_input` (`test_dispatch_scheduler.py:2084-2183`)

**链路逐段验证:**

| 环节 | 验证方式 | 证据 |
|------|----------|------|
| **Scheduler pre-start governance** | `_dispatch_accepted_final_run` 调用 `scheduler.wake_queue_promotion()` | `command.py:2939` — 真实 public scheduler 路径 |
| **Run 2 Engine request 含 prior raw turn** | 读取 `factory.accepted_requests[1].messages` | `test_dispatch_scheduler.py:2119-2124` — "first raw turn for memory" 在消息中 |
| **Run 3 触发 soft threshold** | `_soft_threshold_prompt()` = `"x" * 120`，估算 ≈ `ceil(120/3) + 12 = 52` tokens，超过 soft threshold 50 | policy: window=110, reserved=10, safety_margin=0.5, hard=80 |
| **Proactive compact** | `CONTEXT_COMPACTED` 在 `RUN_STARTED` 之前出现 | `test_dispatch_scheduler.py:2145-2147` — `event_types.index(CONTEXT_COMPACTED) < event_types.index("RUN_STARTED")` |
| **CONTEXT_COMPACTED → memory projection catch-up** | compact artifact provider message 在 Engine request 中 | `test_dispatch_scheduler.py:2148-2152` — "Accepted compact artifact is available for this run." |
| **Run 4 Engine request 包含 compact 后 memory** | `after_compact_contents` 检查 pinned state、raw turn、episode summary | `test_dispatch_scheduler.py:2171-2181` — `current_goal=`、`confirmed_subject=subject:`、`title=Session `、`Memory episode summaries:` |
| **消息顺序** | `goal_index < raw_index < episode_index` | `test_dispatch_scheduler.py:2180` — pinned state → raw turns → episode summary → current prompt |

**关键设计说明:** 当前 pre-start governance estimate 只使用 `display_text`（当前输入），不包含 memory projection 的全量历史。这使 Run 3 的 `"x" * 120` 恰好触发 soft threshold（52 > 50），触发 proactive compact。Compact 后 memory projection catch-up 才将 compacted memory 写入 durable store。Run 4 的 Engine request 通过 RunInputBuilder 从 memory projection 构造消息，此时包含 compact 后的 pinned state、verified facts、episode summaries。这是正确的 design intent — governance gate 是 coarse filter，Engine request 携带全量 memory。

**不使用 mock 的证据:**
- `_event_types_for_run` 通过 `EventLogStore().read_events_after()` 直接读 DB (`test_dispatch_scheduler.py:2855-2869`)
- `factory.accepted_requests` 是 scheduler dispatch 的真实产物
- `_wait_for_run_status` 通过 durable store read 验证 Run 终态

### 4.2 是否存在只测字符串、不测主路径的伪覆盖

**检查每个断言:**

| 断言 | 类型 | 是否伪覆盖 |
|------|------|-----------|
| `"first raw turn for memory" in second_contents` | 验证 raw turn 注入 | **否** — 验证跨轮 memory 传递 |
| `compacted_request_contents[-1] == _soft_threshold_prompt()` | 验证当前 prompt 为最后一条消息 | **否** — 验证消息排序完整性 |
| `event_types.index(CONTEXT_COMPACTED) < event_types.index("RUN_STARTED")` | 验证 compact 在 run start 前发生 | **否** — 验证治理时序 |
| `"Accepted compact artifact is available for this run."` | 验证 compact artifact provider 暴露 | **否** — 验证 compact 产物可用 |
| `"current_goal=" in joined` | 验证 pinned state 存在 | **否** — 验证 compacted memory 的结构化内容 |
| `"confirmed_subject=subject:" in joined` | 验证 verified fact 存在 | **否** — 同上 |
| `goal_index < raw_index < episode_index` | 验证 P9/P10 memory 排序 | **否** — 验证消息优先级顺序 |
| `after_compact_contents[-1] == "after compact prompt"` | 验证当前 prompt 位置 | **否** — 同上 |

所有断言均直接验证核心路径行为。不存在"只检查字符串但不验证因果链"的伪覆盖。

**已知限制（fix artifact 已声明）:** 测试使用 `_FinalAnswerWorker`（直接返回 final_answer），不经过 ToolRuntime accept barrier 与 verified fact 写入。完整业务工具 verified fact 链路由 `test_memory_projection.py` 和 `test_run_input_builder.py` 分层覆盖。该限制不影响本测试对 scheduler governance → compact → memory injection 链路的验证。

### 4.3 测试是否过度脆弱

**Sleep/ordering 假设:**
- `_wait_for_final_request_count`: 最多 200 次 × 0.01s = 2s 超时。与 `_wait_for_accepted_snapshot_count`、`_wait_for_run_status` 等现有 helper 一致
- 无固定 `asyncio.sleep(N)` 硬等待
- 轮询读取 durable store 或 worker factory 状态，是事件驱动测试的标准模式

**字符串断言脆弱性:**
- `"follow-up under budget"` 作为 raw turn 内容 — 这是测试自己写入的 display_text，格式受控
- `"current_goal="`、`"Memory episode summaries:"` 是 RunInputBuilder 的结构化 marker — 若格式变更，测试应该失败（正确行为）
- 无对外部系统或时间戳的依赖

**结论: 测试不脆弱。** ✓

### 4.4 是否绕过 Host public/scheduler 主路径

- 使用 `_seed_accepted_run` + `create_accepted_run_in_transaction` 写入 accepted Run — 这是测试 setup 的标准模式，与 `_dispatch_accepted_final_run` 一致，相当于 public `start_run` 的 admission commit 后状态
- 通过 `scheduler.wake_queue_promotion(seeded.session_id)` 触发 dispatch — 真实 scheduler 入口
- Worker 通过 `LocalEngineWorkerFactory` 协议注入 — 真实 scheduler dispatch 路径
- 不使用 mock/patch，不直接操作 scheduler 内部状态

**结论: 通过 Host public/scheduler 主路径。** ✓

### F4 裁定: **已修复，无残留。**

---

## 新增风险扫描

### N1. `_minimum_protection_tokens_from_options` 构造临时 policy

**文件:** `dayu/host/command.py:316-319`

**现象:** 当 `context_budget_minimum_protection_tokens=None` 时，函数构造 `default_context_budget_policy(context_window_size, reserved_output_tokens)` 并丢弃，仅提取 `minimum_protection_tokens`。

**分析:**
- 临时 policy 经过完整 `__post_init__` 校验（包括 `minimum_protection_tokens < input_budget`）
- 若 window/reserved 组合过小（如 window=200, reserved=100, input_budget=100），默认 `minimum_protection_tokens=256` 会使临时构造抛出 `ValueError`
- 但此错误会在 `_validate_command_context_budget_fields` 中先触发（`HostCommandHandleOptions.__post_init__` ），因为该校验使用相同的 `DEFAULT_MINIMUM_PROTECTION_TOKENS` 值
- 两处 fallback 行为等价，不会出现一者通过、一者失败的不一致

**Severity: INFO** — 非缺陷。临时对象构造略有不优雅，但正确性无影响。

### N2. 未检测到新分层/类型/docstring/pyright 风险

- **分层:** `command.py` 只 import `dayu.host.api`、`dayu.host.context_policy` — 均在 Host 层内 ✓
- **类型:** 所有新增字段有完整类型标注；`_minimum_protection_tokens_from_options` 返回 `int` ✓
- **Docstring:** `compose_host_local_execution_options` 和 `_minimum_protection_tokens_from_options` 有完整中文 docstring ✓
- **pyright:** 0 errors（Controller 已验证） ✓
- **`__all__`:** `compose_host_local_execution_options` 在 `command.py:1199` ✓

### N3. 未检测到测试覆盖回退

- 原 S6 所有 test（`test_public_contracts.py` 39 个、`test_context_budget.py` 20 个、其他 180 个）全部通过
- 新增 `test_host_command_handle_options_require_explicit_budget_inputs` — 验证无默认值
- 新增 `test_multi_turn_proactive_compact_feeds_subsequent_run_input` — 验证多轮 compact → memory 链路
- 无已有测试因字段变为必填而失败（所有构造点已同步更新）

---

## README 同步验证

| 文件 | 修复前问题 | 修复后 |
|------|-----------|--------|
| `dayu/host/README.md` | 未标注 context window/reserved 为必填 | 明确标注"必填 context window / reserved output token budget"、`compose_host_local_execution_options` 使用必填值构造 policy |
| `dayu/host/README.md` | 未标注 production composition root 的调用约束 | 新增 "production composition root 必须显式传入 `HostCommandHandleOptions.context_window_size` 与 `reserved_output_tokens`" |
| `tests/README.md` | 未分离 Context Governance 子模块运行入口 | 新增 `test_context_compact_events.py` 独立入口，标注 `test_context_budget.py`、`test_compaction_contract.py`、`test_compact_artifact_store.py` 对应覆盖类别 |
| `tests/README.md` | 未包含多轮 proactive compact 覆盖 | 新增 "proactive compact 后 compact artifact provider 重建当前 RunInputBuilder、multi-turn proactive compact 到后续 memory 注入链路" |

**结论: README 与修复后事实一致。** ✓

---

## 完整修复矩阵

| ID | 原严重级别 | 修复 | 状态 |
|----|----------|------|------|
| F2 | MEDIUM | 移除默认值，字段改为必填；所有构造点显式传入；fallback 基于显式 options | **CLOSED** |
| F4 | MEDIUM | 新增 4 轮 multi-turn aggregate integration test，覆盖 compact→memory→request 完整链路 | **CLOSED** |
| F1 | RESIDUAL | controller-accepted，未修 | (不在此次复核范围) |
| F3 | RESIDUAL | controller-accepted，未修 | (不在此次复核范围) |
| N1 | INFO | `_minimum_protection_tokens_from_options` 临时构造 policy | 非缺陷 |

---

## Verdict

**PASS** — F2（必填 typed input）和 F4（multi-turn aggregate integration test）均已正确修复，无 blocking finding，无新增 correctness/architecture/test coverage/public contract 风险。

- `context_window_size` / `reserved_output_tokens` 已为必填字段，无默认值，所有构造点显式传入
- Fallback 全部基于显式 options 字段，不存在旧固定 command 默认的静默回退
- Multi-turn 测试真实串起 scheduler pre-start governance → proactive compact → CONTEXT_COMPACTED → memory projection catch-up → subsequent Engine request memory 注入
- 测试通过 Host public/scheduler 主路径，使用真实 DB 读取和 worker dispatch，无 mock
- 无新增分层、类型、docstring、pyright、测试覆盖风险
- README 与修复后事实一致
