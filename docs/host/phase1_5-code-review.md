# Host P1.5 Code Review

## Review 范围

本轮审查 P1.5 代码实施 diff：

- `dayu/host/contracts.py`
- `dayu/host/_event_store.py`
- `dayu/host/_event_translation.py`
- `dayu/host/_run_harness.py`
- `dayu/host/__init__.py`
- `tests/host/`
- `dayu/host/README.md`
- `tests/README.md`

设计与计划依据：

- `docs/host/design.md`
- `docs/host/migration-plan.md`
- `docs/host/phase1_5-plan.md`

## 初审结论

初审不通过 code review gate。

核心实现方向基本正确：P1.5 没有偷做 P6 observer、P7 lifecycle governance、P2 ToolRuntime、
P3 Memory 或 P4 compact；包根没有泄漏 EngineWorker、LocalProxy、WorkerProxy、ToolExecutor 或 store
实现类；`RunEventDraft` 没有进入包根 `__all__`。

但存在一个阻断级语义问题、一个事实来源完整性缺口，以及若干测试没有覆盖“语义与实际实现逻辑差异”的
问题。按用户长期要求，code review 和 test case 必须验证语义触发点、顺序保证和边界条件，不能只看最终
happy path。

## Findings 与修复状态

### 1-已修复-高-Host-owned failure 捕获范围过宽，会把 Host / 翻译 / 契约错误伪装成 worker / proxy failure

位置：

- `dayu/host/_run_harness.py`
- `dayu/host/_event_translation.py`
- `dayu/host/_event_store.py`

问题：

- `_run_to_store()` 的 `try/except Exception` 包住了 `translate_engine_event`、`event_store.append` 和
  `terminal_result_from_event`。
- Host-owned failure 本应只覆盖 worker / proxy 异常导致 Host 无法获得 Engine terminal event 的路径。
- 若 Engine 产出 terminal event 但 data 类型不匹配，当前实现可能先 append 该 terminal，再因
  `terminal_result_from_event` 抛错追加 Host-owned `RUN_FAILED`。
- 这会导致 store 中出现两个 terminal：订阅流停在第一个 terminal，而 `get_run_result` 反向扫描返回后追加的
  Host failure，破坏 terminal event 与 RunResult 同源。

修复要求：

- 收窄 Host-owned failure 的异常边界，只捕获 worker / proxy stream 获取或迭代异常。
- `translate_engine_event`、`RunEventStore.append`、`terminal_result_from_event` 的 Host / 契约错误不得被
  转成 Host-owned failure。
- 增加回归测试，证明 Host / 契约错误不会追加第二个 terminal，不会造成 stream/result 终态不同源。

修复状态：

- `_run_to_store()` 已改为手动 `stream_engine_events()` / `anext()` 边界，只在 worker / proxy 取事件异常时
  调用 Host-owned failure helper。
- `translate_engine_event`、`event_store.append`、`terminal_result_from_event` 的错误不再被该 helper 捕获。
- 新增 `test_terminal_result_error_does_not_append_host_failure`，证明 terminal data 契约错误不会追加
  Host-owned failure，且 `get_run_result` 暴露同一 terminal 契约错误。

### 2-已修复-中-RunEvent provenance 约束没有在 append 边界强制

位置：

- `dayu/host/contracts.py`
- `dayu/host/_event_store.py`

问题：

- `RunEventDraft.source_engine_event_id` 是 `str | None`，但 store append 直接复制 draft。
- 语义上 `source=ENGINE` 必须携带 engine event id；`source=HOST` 必须 `source_engine_event_id is None`。
- 如果内部误用，store 会生成来源语义自相矛盾的 public `RunEvent`。

修复要求：

- 在 `RunEventStore.append` 边界拒绝非法 provenance。
- 增加测试覆盖 ENGINE 缺失 id 与 HOST 携带 id 两种非法 draft。

修复状态：

- `InMemoryRunEventStore.append()` 已调用 `_validate_draft_provenance()`。
- 新增测试覆盖 `source=ENGINE` 缺失 `source_engine_event_id` 与 `source=HOST` 携带 id 两种非法输入。

### 3-已修复-中-append-before-stream 测试没有真正防回归

位置：

- `tests/host/test_phase1_5_run_harness_eventlog.py`

问题：

- 现有测试先等待 store 里已有事件，再消费 `stream.events`。
- 如果未来实现错误地从 worker queue 直接 stream，只要测试消费前 append 已完成，也可能通过。

修复要求：

- 测试必须证明 `RunStream.events` 观察到的事件已先 append 到 store。
- 需要验证 stream 事件与 store append 事件同源，而不是只验证最终都能读到。

修复状态：

- 新增 `_RecordingRunEventStore` 测试 wrapper，记录 `append()` 返回的已落库事件。
- `test_run_stream_reads_events_after_store_append` 现在断言 stream 读到的事件就是 store append 返回的同源
  `RunEvent`。

### 4-已修复-中-subscribe lost-wakeup 测试没有命中 replay / follow 注册窗口

位置：

- `tests/host/test_phase1_5_event_store.py`

问题：

- 现有测试主要证明 waiter 已存在时 notify 有效。
- 不能防住“先 list 一次，随后注册 queue”这种两段式实现的 replay / follow 丢事件窗口。

修复要求：

- 增加更硬的并发 / 边界测试，证明实现基于 cursor predicate 循环等待。
- 不为了测试污染生产接口。

修复状态：

- 新增 `test_subscribe_follow_uses_cursor_predicate_without_waiter`：replay 后、下一次 `anext()` 注册 waiter 前
  append terminal，随后订阅仍必须通过 cursor predicate 补到该事件。
- 该测试覆盖“先 list 一次，随后注册 queue”的典型 lost-wakeup 回归。

### 5-已修复-低-canonical / preview 分类测试覆盖不足

位置：

- `tests/host/test_phase1_5_run_harness_eventlog.py`
- `tests/host/test_phase1_run_harness.py`

问题：

- P1.5 plan 要求至少覆盖 final、failed、cancelled、suspended、content delta、reasoning delta、tool call、
  tool result。
- 当前测试主要覆盖 content delta 与 final answer；tool 相关测试未断言 `kind`。

修复要求：

- 补齐 canonical / preview 分类覆盖。

修复状态：

- 新增 `test_engine_event_kind_classification_matrix`，覆盖 final、failed、cancelled、suspended、
  content delta、reasoning delta、tool call、tool result 的 canonical / preview 分类。

### 6-已修复-高-terminal 后仍可 append，破坏 stream / replay / result 同源

位置：

- `dayu/host/_event_store.py`
- `dayu/host/_run_harness.py`

问题：

- `_run_to_store()` 看到 terminal 后只记录 `terminal_seen`，仍可能继续消费 worker stream 并 append 后续事件。
- `InMemoryRunEventStore.append()` 只记录第一个 terminal cursor，不拒绝同一 run terminal 之后的新事件。
- 这会导致 `RunStream.events` 停在第一个 terminal，但 `list_events()`、`stream_run_events(after=terminal)` 或
  `get_run_result()` 可能观察到 terminal 之后的事件或第二个 terminal。

修复状态：

- `InMemoryRunEventStore.append()` 已在 store 边界拒绝同一 run terminal 后的任何新 `RunEventDraft`。
- `LocalRunHarness._run_to_store()` 已在首个 terminal append 后停止继续 append，并关闭支持 `aclose()` 的
  worker stream。
- `dayu.engine.run_agent_messages()` 已保证外层 async generator 被 `aclose()` 时向内部 Agent 事件流传播关闭，
  以触发 Runner close。
- 新增测试覆盖 terminal 后非终态事件、terminal 后第二 terminal，以及 `list_events` /
  `stream_run_events(after=terminal)` / `get_run_result` 三者同源一致性。

### 7-已修复-中-start_run 后台 task 内部错误缺少观测

位置：

- `dayu/host/_run_harness.py`

问题：

- `start_run()` 创建 detached background task 后没有 done callback。
- 翻译、append、terminal result 推导等 Host 内部错误从后台 task 冒出时，只会变成 asyncio 未取回异常告警。

修复状态：

- `start_run()` 已给后台 task 注册 done callback，取回异常并记录 `host.run.background_task_failed` ERROR 日志。
- 新增 public `start_run()` 路径测试，验证 terminal data mismatch 不追加 Host-owned failure，且后台异常可被
  ERROR 日志观测。
- 完整 supervisor、事件流传播 Host 内部错误、append 前失败时的公共收口语义属于 P7 governance，本轮不实现。

### 8-已修复-中-默认 harness 缓存强引用 event loop

位置：

- `dayu/host/_run_harness.py`

修复状态：

- `_DEFAULT_HARNESS_BY_LOOP` 已从普通 `dict` 改为 `WeakKeyDictionary`，避免对已关闭且无外部引用的 event loop
  保持强引用。

### 9-已修复-低-canonical / preview 分类矩阵遗漏 content completed

位置：

- `tests/host/test_phase1_5_run_harness_eventlog.py`

修复状态：

- `test_engine_event_kind_classification_matrix` 已补充 `RUNNER_CONTENT_COMPLETED`，并断言其分类为 `PREVIEW`。

## 当前验证记录

初审前总控已运行：

```bash
source .venv/bin/activate
python -m pytest tests/host tests/engine/test_import_boundary.py tests/engine/test_package_exports.py tests/contracts -q
python -m pyright
git diff --check
```

结果：

- 影响范围 pytest：43 passed。
- pyright：0 errors, 0 warnings, 0 informations。
- diff check：通过。

这些验证只能说明当前测试集通过；上述 findings 说明测试尚未充分覆盖语义与实际实现逻辑差异。

修复后总控复验：

```bash
source .venv/bin/activate
python -m pytest tests/host tests/engine/test_import_boundary.py tests/engine/test_package_exports.py tests/contracts -q
python -m pyright
git diff --check
```

结果：

- 影响范围 pytest：53 passed。
- pyright：0 errors, 0 warnings, 0 informations。
- diff check：通过。

## 复审状态

通过 code review gate。

复审确认：

- Host-owned failure 捕获边界已收窄，只覆盖 `stream_engine_events()` 获取和 `anext()` 取事件异常；
  翻译、append、terminal result 推导错误不会再被伪装成 Host failure。
- `RunEventStore.append()` 已校验 provenance，覆盖 `ENGINE` 缺 id、`HOST` 携带 id 两类非法 draft。
- `RunEventStore.append()` 已拒绝 terminal 后继续 append；harness 看到首个 terminal 后停止继续 append，并关闭
  worker stream。
- start_run 后台 task 内部错误已通过 ERROR 日志可观测，不扩展 public API，也不实现 P7 supervisor。
- append-before-stream 测试通过 recording store 断言 stream 读到的是 append 返回的同源 `RunEvent`。
- subscribe lost-wakeup 测试覆盖 replay 后、follow waiter 注册前 append 的窗口。
- canonical / preview 分类矩阵已覆盖 plan 要求的关键类型，并包含 `RUNNER_CONTENT_COMPLETED -> PREVIEW`。
- 包根未泄漏 `EngineWorker`、`LocalProxy`、`WorkerProxy`、`ToolExecutor` 或 store 实现类，
  `RunEventDraft` 也未进入包根 `__all__`。
- 文档更新描述的是当前 P1.5 已落地事实，没有偷做 P6 / P7 / P2 / P3 / P4。

按 `docs/host/migration-plan.md`，code review 通过后应停止，等待用户人工 review。用户确认后，
才能提交 P1.5 代码、测试和 README 更新。

## Review 后补充

用户要求增加必要日志与人工 smoke，以便通过 log 观察 P1.5 EventLog 行为；同时要求除
`utils/smoke_async_agent_providers.py` 外，其它 smoke 不再打印高频 delta 事件。

补充变更：

- `dayu.host._event_store` 增加 DEBUG 日志，覆盖 append、list、subscribe start / wait / batch /
  complete 等事实边界。
- 新增 `utils/smoke_host_eventlog.py`，本地 fake worker，不联网，覆盖 success 与 worker-failure 两条路径。
- `utils/smoke_async_agent_tool_call.py` 与 `utils/smoke_engine_worker.py` 跳过 content / reasoning delta 摘要输出。
- `dayu/host/README.md` 增加 Host EventLog smoke 使用方式。

补充验证：

```bash
source .venv/bin/activate
python -m pytest tests/host tests/engine/test_import_boundary.py tests/engine/test_package_exports.py tests/contracts -q
python -m pyright
python utils/smoke_host_eventlog.py --help
python utils/smoke_engine_worker.py --help
python utils/smoke_async_agent_tool_call.py --help
python utils/smoke_host_eventlog.py --case success --log-level DEBUG
python utils/smoke_host_eventlog.py --case worker-failure --log-level DEBUG
```

结果：

- 影响范围 pytest：53 passed。
- pyright：0 errors, 0 warnings, 0 informations。
- 三个 smoke help 均可正常解析。
- Host EventLog success / worker-failure smoke 均可运行，输出不包含 delta 刷屏。
