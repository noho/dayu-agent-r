# WU-PROJ-01 S3/S4 Residual Code Review — AgentDS

## 元数据

- Work unit: `WU-PROJ-01`
- Gate: code review
- Reviewer: AgentDS
- Date: 2026-06-11
- Scope: `WU-PROJ-01-S3-R1` / `WU-PROJ-01-S4-R1`
- Changed files:
  - `tests/host/test_dispatch_scheduler.py`
  - `docs/host/issues-implementation-control.md`

## 结论：PASS

无 blocking finding，无非阻塞 finding。

## 审查范围与方法

只审查当前未提交 diff (`git diff HEAD`) 中 S3/S4 相关变更：
- `tests/host/test_dispatch_scheduler.py`：+151 行
- `docs/host/issues-implementation-control.md`：1 行状态更新

设计真源：`docs/host/design.md` 第 24.5 节（snapshot cursor == projection checkpoint → bounded catch-up / repair，非 Run crash recovery，不得进入 RECOVERING）和第 24.4 节（projection checkpoint 与 snapshot 在同一事务提交，catch-up 是 bounded repair，非 recovery 入口）。

## 逐项审查

### 1. S3-R1：新测试是否真正覆盖 dispatch before-worker checkpoint-covered happy path

**结论：是。**

新测试 `test_dispatch_checkpoint_covered_catchup_accepts_ordinary_run_input` 的结构：

1. **预追 projection checkpoint**：通过 `catch_up_conversation_memory_projection(...)` 用真实 production 路径将 conversation memory projection checkpoint 追到 `required_event_sequence`（= Attempt.started_event_sequence - 1）。
2. **验证 checkpoint 状态**：`_read_memory_checkpoint_sequence(...)` 断言 checkpoint `== required_event_sequence`，且预追结果 `target_reached is True`、`finished_cursor == required_event_sequence`。
3. **通过 monkeypatch wrapper 观察 dispatch 内部 catch-up**：`_observed_catch_up` 调用真实 `catch_up_conversation_memory_projection` 并记录返回值。wrapper 不改变语义，不替换返回值，不跳过 catch-up。
4. **走真实 dispatch 路径**：`_open_scheduler(...)` → `wake_dispatch(...)` → `drain_once()` 走完整 production `_catch_up_memory_projection_before_worker` → `_build_run_input_with_lag_repair` → `worker.accept(...)` 路径。没有替换 RunInputBuilder、scheduler 或 worker accept。
5. **断言 checkpoint-covered catch-up 行为**：
   - `dispatch_catchup.started_cursor == required_event_sequence` — catch-up 起点已是目标
   - `dispatch_catchup.finished_cursor == required_event_sequence` — catch-up 终点未变
   - `dispatch_catchup.events_scanned == 0` — 不重复扫描 EventLog
   - `dispatch_catchup.target_reached is True` — `_raise_if_memory_projection_target_not_reached` 通过（`failures == 0 and target_reached`）
   - `checkpoint_after_dispatch == checkpoint_before_dispatch` — checkpoint 稳定
6. **断言 ordinary RunInput 和 worker accept**：
   - `len(factory.accepted_snapshots) == 1`、`len(factory.accepted_requests) == 1` — worker accept 一次
   - `run.status == RUNNING`、`attempt.status == RUNNING` — 状态正确
   - `factory.accepted_requests[0].disable_tools is True` — ordinary no-tool RunInput 已构造
   - `accepted_contents[-1] == "dispatch prompt"` — 用户输入进入 request
7. **断言非 fail-closed / 非 recovery**：
   - `RUN_FAILED` count == 0
   - `RUN_RECOVERING` count == 0
   - Attempt count == 1（无 recovery 第二条 Attempt）

**代码证据**：
- `dispatch.py:3020` — `_catch_up_memory_projection_before_worker` 调用 `catch_up_conversation_memory_projection` 后通过 `_raise_if_memory_projection_target_not_reached` 检查 `target_reached`。
- `dispatch.py:347-373` — `_raise_if_memory_projection_target_not_reached`：`failures == 0 and target_reached` 即 return，否则 raise `_MemoryProjectionDispatchDiagnosticError`。
- `memory_repair.py:517-528` — `_target_reached`：`finished_cursor >= max_event_sequence` 即 True。
- `projection.py:576-586` — `_process_next_event`：`row.event_sequence > max_event_sequence` 时 `scanned=False`，不推进 checkpoint。
- `projection.py:472-474` — `run_once`：`not step.scanned` 立即 break，不累计 events_scanned。

**设计一致性**：对齐 `docs/host/design.md` 第 3204 行："若 ordinary dispatch 前 snapshot cursor 不能覆盖 required EventLog cursor，Host 必须执行 bounded memory projection catch-up / rebuild...这不是 Run crash recovery，不得把 Run 推入 RECOVERING。"

### 2. S3-R1：是否过度 mock 或绕开真实 RunInputBuilder / scheduler 关键路径

**结论：否。**

- 使用 `_open_scheduler(...)` 构造真实 `HostDispatchScheduler`，与其所有 production 内部组件（RunInputBuilder、worker factory、lane controller）一致。
- 使用 `_seed_current_run(store)` 通过真实 durable store transaction 创建 running Run + STARTING Attempt + pending dispatch。
- 预追 catch-up 使用真实 `catch_up_conversation_memory_projection`（public API，非测试私有入口）。
- monkeypatch 的 wrapper 只追加一个 `observed_catchups.append(result)` 副作用并返回真实结果，不替换 catch-up 逻辑。
- `_read_memory_checkpoint_sequence` 使用 public `read_projection_checkpoint` 原语，不绕过 public contract。

**对比既有测试**：`test_dispatch_lag_repair_rebuild_not_reached_fails_closed`（line 2102）同样通过 monkeypatch 干预 catch-up（noop），覆盖相反方向（catch-up 失败 → fail-closed）。两个测试对称，覆盖同一生产路径的两种结果。

### 3. S4-R1：是否只稳定目标 flaky 测试的无关 lane timeout 风险，且不降低原断言强度

**结论：是。**

变更内容：
```python
scheduler = await _open_scheduler(
    tmp_path,
    store,
    factory,
    context_budget_policy=_soft_compact_policy(),
    lane_default_timeout_seconds=1.0,   # <-- 新增
)
```

- 只将 lane timeout 从 `_open_scheduler` 默认 `0.01` 改为 `1.0`。
- 该测试 `test_reactive_compact_failure_fallback_dispatch_uses_failed_view` 验证 reactive compact failure fallback dispatch 语义，不验证 lane acquire timeout。其 `_soft_compact_policy()` 的 `soft_threshold_context_ratio` 极低，触发 overflow → compact → failure → fallback 路径才是测试目标。lane acquire 是 Host 内部调度机制，将 timeout 收紧到 10ms 会把该测试的 fallback 语义断言暴露给无关的宿主机调度窗口。
- 保留所有原有断言：
  - `len(factory.accepted_snapshots) == 2` — 两条 Attempt
  - `factory.accepted_snapshots[1].attempt_id != seeded.attempt_id` — fallback 创建新 Attempt
  - `_attempt_count_for_run(...) == 2`
  - `CONTEXT_COMPACTED` count == 0
  - `RUN_LOST` count == 0
  - `CONTEXT_COMPACTION_FAILED` payload：`fallback_action == "dispatch"`、`fallback_policy_decision == "deterministic_recent_window"`
  - 第二次 request 不包含 compact artifact 文本
- 不修改生产 lane acquire 语义（`dayu/runtime/lane.py` 未改动）。
- 不修改 reactive compact failure fallback 生产逻辑（`dayu/host/dispatch.py` 未改动）。

### 4. 是否误改 production code、ordinary semantics、或引入 sleep/flaky/硬编码不合理值

**结论：否。**

`git diff HEAD --stat` 确认只修改了两个文件：
- `tests/host/test_dispatch_scheduler.py`：测试代码
- `docs/host/issues-implementation-control.md`：控制文档状态更新

零 production code 修改。无 `asyncio.sleep`、无 `time.sleep`、无硬编码 magic number（`lane_default_timeout_seconds=1.0` 是测试 fixture 参数，遵循 `_open_scheduler` 的 keyword-only 接口约定）。

### 5. 测试 helper 和 imports 是否符合 AGENTS.md

**新增 helper `_read_memory_checkpoint_sequence`**（line 6130）：

| 检查项 | 结果 |
|---|---|
| 中文 docstring | ✓ 模块级、函数级、嵌套级均有 |
| 参数说明 | ✓ `:param transaction_runner:` 加说明 |
| 返回值说明 | ✓ `:returns: memory projection checkpoint sequence。` |
| 异常说明 | ✓ `:raises AssertionError:` 加说明 |
| 类型完整 | ✓ 参数 `HostTransactionRunner`，返回 `int` |
| 无 Any/object | ✓ |
| 无兼容 wrapper | ✓ 直接使用 public `read_projection_checkpoint` |
| 模块级私有函数 | ✓ 函数名为 `_read_memory_checkpoint_sequence`，定义在模块顶层 |

**新增 imports**：

| Import | 用途 | 合规 |
|---|---|---|
| `import dayu.host.dispatch as host_dispatch` | monkeypatch 目标 | ✓ 必要，模块级 import |
| `MemoryProjectionPolicy` | wrapper 函数类型注解 | ✓ 公共类型 |
| `ConversationMemoryProjectionRepairResult` | observed_catchups 列表类型 | ✓ 公共类型 |
| `MemoryProjectionCatchupBudget` | wrapper 函数类型注解 | ✓ 公共类型 |
| `catch_up_conversation_memory_projection` | 预追和 wrapper 内实调 | ✓ 公共 API |
| `read_projection_checkpoint` | 读取 checkpoint | ✓ 公共 API |

无兼容性 re-export、无 `Any`/`object`、无未使用 import、无胶水 seam。

**嵌套函数**：`_observed_catch_up` 在测试函数内定义，通过闭包捕获 `observed_catchups` 列表。这符合既有模式（同文件 `test_dispatch_lag_repair_rebuild_not_reached_fails_closed` 在 line 2129-2137 定义嵌套 `_noop_catch_up` 和 `_fake_builder_for_dispatch`），且嵌套理由充分（需要非平凡闭包捕获）。

### 6. README 判断是否合理

**结论：合理。**

`implementation-codex` artifact 判断"无需更新 README"，理由是"仅在既有 `tests/host/test_dispatch_scheduler.py` 内补充 dispatch scheduler 行为覆盖并调整单个测试的 lane timeout fixture，不新增测试层级、运行方式、公共测试约定或维护入口。"

对照 `tests/README.md` 更新触发规则（"`tests/` 修改 -> 检查并按需更新 `tests/README.md`"）：
- 不新增测试文件、测试目录或测试层级
- 不改变测试运行方式（`python -m pytest` 不变）
- 不新增公共测试约定、测试 helper 公共导出或 fixture 公共入口
- `_read_memory_checkpoint_sequence` 是模块级 `_` 前缀私有辅助函数，不是公共测试工具
- 已有测试不改变行为或入口

判断与 README 更新触发规则一致。

## 验证复验

Controller 复验已确认。本 reviewer 独立复验：

```
python -m pytest tests/host/test_dispatch_scheduler.py -q
68 passed in 1.36s
```

```
pyright tests/host/test_dispatch_scheduler.py
0 errors, 0 warnings, 0 informations
```

```
git diff --check
(无输出，通过)
```

## 剩余风险

无新增 residual risk。S3-R1 和 S4-R1 已在当前 diff 内关闭。

## 完成状态

Code review gate complete. 未 commit、未 push、未修改文件。
