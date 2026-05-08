# P6 Fix Re-Review

## 结论：通过

P6 fix agent 已修复三份 review 文档（架构 / 代码 / 并发）中全部已标记 `[已修复]` 的发现，
且未引入新问题。所有验证命令通过，8 个复审重点逐项确认，2 个追加核验项结论为 P6 可接受。

---

## 验证命令结果

| 命令 | 结果 |
|------|------|
| `pyright` | 0 errors, 0 warnings |
| `git diff --check` | clean |
| `pytest tests/host -q` | 189 passed in 0.50s |
| `pytest -q` | 552 passed in 1.62s |
| `python utils/smoke_host_p6_durable_eventlog.py` | 全部输出正确：RunSucceededResult, 3 observers caught_up, memory/timeline/audit 投影完整, run_state=succeeded, terminal_result=RunSucceededResult |

---

## 8 个复审重点逐项核验

### 1. 真实 run path 接入 ProjectionCoordinator

**通过。**

- `build_durable_harness` 构造 `LocalRunHarness` 时注入 `coordinator=coordinator`（`_durable_harness.py:130`）。
- `_project_terminal_run`（`_run_harness.py:1006-1028`）在 `coordinator is not None` 时走 `coordinator.drain()`，仅 coordinator=None 时退化为 `_project_run_events` fallback。
- durable harness 的 coordinator 由 `ProjectionCoordinator(...)` 创建，不为 None。
- smoke 脚本输出 `[checkpoint] observer=host_memory_projection status=caught_up` 证明 drain 真正执行。

### 2. Memory split-brain 修复

**通过。**

- `build_durable_harness` 创建 `actual_memory` 并同时传给 `MemoryProjectionObserver(memory_store=actual_memory)` 和 `LocalRunHarness(memory_store=actual_memory)`（`_durable_harness.py:99-135`）。
- `test_durable_harness_shares_memory_store_with_observer` 守护 `bundle.memory_store is bundle.harness.memory_store`。

### 3. Terminal result 持久化

**通过。**

- `_append_in_transaction` 在 `is_terminal` 时调用 `_write_terminal_result_snapshot`（`_durable_event_store.py:367-399`），使用同一 `HostStorageTransaction`。
- `_write_terminal_result_snapshot` 调用 `RunStateStore.write_terminal_result` 写入 `host_runs.result_payload`。
- `test_terminal_persists_run_result_succeeded/failed/cancelled/suspended` 四种终态 round-trip 测试通过。
- smoke 输出 `terminal_result=RunSucceededResult` 确认端到端可读。

### 4. AttemptStateStore 接入

**通过。**

- `LocalRunHarness` 新增 `attempt_state_store` 字段（`_run_harness.py`）。
- `_begin_attempt_if_durable` 在 attempt 起点创建 `CREATED → RUNNING`。
- `_finish_attempt_if_durable` 在终态写入 `SUCCEEDED/FAILED/CANCELLED/SUSPENDED`。
- context overflow compact retry 把旧 attempt 标记为 `STALE_DIAGNOSTIC` 后开新 attempt。
- finally 路径兜底关闭未推进 attempt。
- `test_durable_harness_start_run_drains_to_read_models` 验证 attempt state=SUCCEEDED。

### 5. 并发修复

**通过。**

- `_drain_lock`（`_event_observer.py:124`）：`drain()` 和 `run_once()` 入口加锁，防并发重入。
- `advance_success`：`existing[0] > position.value` 拒绝倒退，`==` 跳过 UPDATE 实现幂等。
- `_raise_business_error_for_integrity`（`_durable_event_store.py:672-698`）：`idx_host_run_events_engine_id` 违规映射为 `ValueError`。
- post-commit hook 循环 try/except（`_host_storage_transaction.py:192-202`）。
- `test_coordinator_drain_lock_serializes_concurrent_drains`、`test_advance_success_idempotent_replay`、`test_advance_success_regression_raises`、`test_duplicate_engine_event_id_raises_value_error`、`test_post_commit_hook_failure_does_not_break_transaction`、`test_multi_run_concurrent_append_global_position_monotonic` 全部通过。

### 6. Smoke 覆盖

**通过。**

- smoke 使用 `harness.start_run` + `_StubProxy` 走完整路径：USER_INPUT_ACCEPTED → RunInputBuilder → proxy → translate → append → terminal → coordinator.drain → memory/timeline/audit 投影 + RunResult 持久化。
- `test_phase6_durable_harness_integration.py` 在测试套件层面持续守护端到端路径。

### 7. Review 文档标注

**通过。**

- `phase6-code-review.md`：12 个 findings 全部标注 `[已修复]` 或 `[无需修复-说明]`。
- `phase6-architecture-review.md`：5 个 findings 全部标注 `[已修复]`。
- `phase6-concurrency-review.md`：8 个 findings 全部标注 `[已修复]` 或 `[无需修复-说明]`。

### 8. 范围控制

**通过。**

未发现 P7（tool trace projection/sink）、P8（lease/fencing）、P9（lifecycle/admission）、P10（ToolRegistry）的偷做实现。P6 新增代码严格限于 durable EventLog、Run/Attempt state、ProjectionCoordinator/Observer/Checkpoint、serializer、harness 集成。

---

## 追加核验项

### A. post-commit hook 异常隔离

**结论：P6 可接受，无需继续修。**

hook 的职责是 `asyncio.Condition.notify_all()`（`_durable_event_store.py:590-612`），
属于 best-effort in-memory 通知，作用是唤醒正在 `condition.wait()` 的 `subscribe()` 调用方。

hook 失败的影响分析：
- **durable event 已 commit**：hook 在 `HostStorage.transaction()` 的 `commit()` 之后执行
  （`_host_storage_transaction.py:191-202`），数据已持久化到 SQLite。
- **subscribe 路径**：`_subscribe` 使用 replay-then-follow 设计（`_durable_event_store.py:436-448`），
  先从 SQLite 读 committed 数据（replay），再 `condition.wait()` 等新事件（follow）。
  hook 失败 → subscribe 方错过即时唤醒 → 但下次任何 append 或 terminal 的 hook 唤醒即可恢复；
  若 terminal 是最后一个事件，`_subscribe` 的 replay 阶段会读到 terminal 并正确退出。
- **drain 路径**：`ProjectionCoordinator.drain()` 通过 `fetch_events_by_position` 直接读 SQLite
  （`_durable_event_store.py:552-588`），不依赖 condition 通知，hook 是否失败不影响 drain。
- **memory projection**：在 durable 路径下通过 drain 触发，不依赖 hook。

hook 失败不会导致已提交事件对 stream / projection / replay 永久不可见。当前实现的
`try/except + _LOGGER.error` 隔离是 P6 可接受的防御。

### B. `_project_run_events` fallback

**结论：P6 可接受，无需继续修。**

durable harness 的 terminal 路径不再绕过 ProjectionCoordinator：

- `build_durable_harness` 构造 `LocalRunHarness` 时注入 `coordinator=coordinator`
  （`_durable_harness.py:130`），coordinator 是 `ProjectionCoordinator(...)` 实例，不为 None。
- `_project_terminal_run`（`_run_harness.py:1020-1027`）：`self.coordinator is not None` 时
  走 `coordinator.drain()` 并 return，不会执行 `_project_run_events`。
- `_project_run_events`（`_run_harness.py:1030-1038`）docstring 明确标注"仅在
  coordinator is None（P3-P5 InMemoryRunEventStore 路径）被使用"。
- `test_durable_harness_start_run_drains_to_read_models` 验证 observer 状态为 `caught_up`，
  证明 drain 路径生效而非 fallback。

`_project_run_events` 仅服务非 durable / in-memory 装配，是 P3-P5 测试路径的兼容保留，
不在 durable terminal path 中被调用。原 F-01 已真正修复。

---

## 原始发现验证表

### phase6-code-review.md

| 编号 | 严重级别 | 描述 | 修复验证 |
|------|----------|------|----------|
| F-01 | HIGH | LocalRunHarness 绕过 ProjectionCoordinator | [已修复] `_project_terminal_run` 走 `coordinator.drain()`；smoke/测试验证 caught_up |
| F-02 | HIGH | memory_store split-brain | [已修复] `build_durable_harness` 共享同一 `actual_memory` 实例；测试守护 |
| F-03 | HIGH | terminal result 未同事务写入 | [已修复] `_write_terminal_result_snapshot` 在 append 事务内；4 种终态测试通过 |
| F-04 | MEDIUM | smoke 未覆盖真实 run path | [已修复] smoke 使用 `harness.start_run` + stub proxy；集成测试守护 |
| F-05 | MEDIUM | AttemptStateStore 未进入主路径 | [已修复] begin/finish lifecycle 接入；attempt state=SUCCEEDED 验证 |
| F-06 | LOW | serializer 处理 P7 tool cursor 事件 | [无需修复-说明] 已有 RunEventType 枚举的内在要求 |
| F-07 | LOW | `extended_state_from_run_state` 缺 wildcard | [无需修复-说明] RunState 是闭合 StrEnum，pyright 拦截 |
| F-08 | LOW | `_must_str`/`_must_bool` 重复 | [无需修复-说明] 不同业务边界，留 P7 统一 |
| F-09 | LOW | `_encode_fields`/`_decode_fields` god function | [无需修复-说明] 各分支数行，留后续重构 |
| F-10 | LOW | bare assert | [已修复] 替换为 `if ... raise RuntimeError` |
| F-11 | LOW | 4 张表 DDL 集中 | [无需修复-说明] 留 P7/P8 引入新表时重构 |
| F-12 | LOW | Engine 类型导入 Host | [无需修复-说明] 正向分层依赖 |

### phase6-architecture-review.md

| 编号 | 严重级别 | 描述 | 修复验证 |
|------|----------|------|----------|
| Finding 1 | 严重 | ProjectionCoordinator 未接入主路径 | [已修复] 同 F-01 |
| Finding 2 | 严重 | AttemptStateStore 未接入 | [已修复] 同 F-05 |
| Finding 3 | 中等 | write_terminal_result 未接入 | [已修复] 同 F-03 |
| Finding 4 | 中等 | smoke 未覆盖端到端 | [已修复] 同 F-04 |
| Finding 5 | 低 | `_project_run_events` 应删除或收窄 | [已修复] 降级为 coordinator=None fallback |

### phase6-concurrency-review.md

| 编号 | 严重级别 | 描述 | 修复验证 |
|------|----------|------|----------|
| F1 | 高 | terminal guard 竞争窗口 | [已修复] 防御性注释 + asyncio.Lock + BEGIN IMMEDIATE 双层保护 |
| F2 | 高 | 并发/故障注入测试缺失 | [已修复] `test_phase6_review_fixes.py` 覆盖并发 append、drain 重入、rollback、hook 隔离 |
| F3 | 中 | SELECT MAX 非原子分配 | [无需修复-说明] BEGIN IMMEDIATE 事务 + UNIQUE 兜底 |
| F4 | 中 | source_engine_event_id 冲突语义 | [已修复] IntegrityError → ValueError 映射；测试守护 |
| F5 | 中 | observer drain 缺防重入 | [已修复] `_drain_lock` + `advance_success` 幂等；测试守护 |
| F6 | 低 | post-commit hook 异常 | [已修复] try/except 隔离；测试守护 |
| F7 | 低 | lag 计算不在同一快照 | [无需修复-说明] 仅诊断展示 |
| F8 | 低 | ensure_host_schema 绕过事务 | [无需修复-说明] DDL IF NOT EXISTS 天然幂等 |

---

## 残余风险

以下为 P7+ 范围，不阻塞 P6：

| 风险 | 归属 | 说明 |
|------|------|------|
| 多进程真实并发 append/replay | P8 | 当前单进程 asyncio.Lock + SQLite BEGIN IMMEDIATE 已覆盖 |
| owner lease / fencing | P8 | attempt_id 已生成，lease 留 P8 |
| orphan / stale attempt recovery | P8 | STALE_DIAGNOSTIC 标记已就位，recovery 留 P8 |
| observer claim / lease / consumer group | P8+ | 当前 at-least-once + checkpoint 已够用 |
| `_must_str`/`_must_bool` 去重 | P7 | 留与新增 store/sink 一起统一 |
| `_encode_fields`/`_decode_fields` 重构 | P7 | dispatch table 留后续 |
| DDL 拆分到各 store 模块 | P7 | 留引入新表时一并重构 |
| episode summary / LLM compaction scene | P9 | 不在 Host durable 范围 |
| public memory edit / reset / forget API | P9 | 不在 Host durable 范围 |
| `RunResult` 等共享类型下沉到 `dayu.contracts` | P7+ | 层间耦合可接受 |
