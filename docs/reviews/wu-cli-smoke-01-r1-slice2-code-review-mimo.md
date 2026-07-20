# Code Review — WU-CLI-SMOKE-01-R1 Slice 2

## Scope

- Mode: Current Changes Mode
- Branch: `phaseflow/wu-cli-smoke-01-r1`
- Base: `70ccda60`（accepted Slice 1 commit）
- Output file: `docs/reviews/wu-cli-smoke-01-r1-slice2-code-review-mimo.md`
- Included scope：当前工作树相对 `70ccda60` 的全部变更，含 tracked diff（四份 README、两个既有测试文件修改）与 untracked 新增（三份测试/support 文件、一份 implementation artifact）。controller-owned `docs/host/issues-implementation-control.md` 与 `docs/phaseflow-umbrella-optimization-control.md` 的状态更新不在 review 范围内。
- Excluded scope：controller-owned control docs 的 pre-existing 修改；`docs/reviews/wu-cli-smoke-01-r1-slice2-implementation-codex.md` 是 implementation artifact，只读取作为参考，不修改。
- Parallel review coverage：使用两个 subagent 分别覆盖（1）production source 文件核实与（2）test determinism/barrier 分析。主 reviewer 整合、去重并裁决 severity。

## Findings

### 1-F1-低-private-access-to-enable-deterministic-barrier

- **入口/函数**: `tests/host/test_transient_delta.py` — `test_subscription_wait_before_publish_wakes_at_barrier`、`test_subscription_drain_clear_publish_intersection_rechecks_owner_state`、`test_subscription_overflow_and_close_states_remain_ready`
- **文件(行号)**: `tests/host/test_transient_delta.py:246`、`:272`、`:302`
- **输入场景**: 所有需要 deterministic barrier 的 readiness 测试
- **实际分支**: 测试直接赋值 `subscription._ready = controlled_event`，替换 production `asyncio.Event`
- **预期行为**: 测试应通过 public contract 验证行为，不穿透 production 内部字段
- **实际行为**: 三个 async 测试替换 `_ready` 私有字段以注入 deterministic barrier；`_WaitEnteredEvent` 和 `_PublishOnClearEvent` 子类化 `asyncio.Event` 并 override `wait()`/`clear()`
- **直接证据**: `subscription._ready = controlled_event` 出现在 3 处；`transient_delta_module._TRANSIENT_WATCH_BUFFER_CAPACITY` 在 3 处引用（`:293`、`:296`、`:322`）
- **影响**: 若 production 将 `_ready` 从 `asyncio.Event` 改为 `asyncio.Condition` 或其他 primitive，这些测试不会自动失败——它们仍会注入自己的 Event 并"通过"，但不再验证真实 readiness 机制。不过，这不会掩盖 production bug，因为测试验证的是 `wait_ready` public contract 的行为正确性，而非内部实现细节。
- **建议改法和验证点**: 当前 trade-off 可接受——确定性 barrier 比 sleep-based 测试更重要。若 production 改变 readiness primitive，需同步更新测试 barrier。建议在测试中加一行注释说明此 coupling。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 2-F2-低-cli-test-capacity-proof-uses-polling

- **入口/函数**: `tests/cli/test_transient_slow_consumer_path.py` — `_wait_for_yielded_count`、`test_real_transient_slow_consumer_falls_back_once_with_original_typed_error`
- **文件(行号)**: `tests/cli/test_transient_slow_consumer_path.py:322`、`:414-432`、`:391-411`
- **输入场景**: Service relay 阻塞后验证 Host subscription overflow
- **实际分支**: 测试用 `asyncio.sleep(0.05)` 检查稳定性，用 polling loop 等待 `probe.yielded_count` 到达精确阻塞点
- **预期行为**: 关键 barrier 应为 deterministic Event-based
- **实际行为**: `_wait_for_yielded_count` 使用 `asyncio.sleep(0.005)` × 1000 轮 polling 等待 yielded count 到达 `block_start + 256 + 1`；稳定性检查用 `asyncio.sleep(0.05)`。两者均为 bounded polling，不是 unbounded sleep。
- **直接证据**: `asyncio.sleep(0.05)` at line 322；`asyncio.sleep(0.005)` at line 431；`asyncio.sleep(0.01)` at line 400
- **影响**: 在极端系统负载下，50ms 稳定性窗口理论上可能不足。但实际风险极低：count 是单调递增且有上界的，polling 有 5s 总 timeout。
- **建议改法和验证点**: 当前实现可接受。`_wait_for_run_succeeded` 和 `_wait_for_yielded_count` 都检查单调状态，不是时序敏感的交错。若要消除 polling，需要在 Service relay 层暴露 queue full 的 Event signal，这超出 Slice 2 scope。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 3-F3-低-cast-Host-掩盖-protocol-不完整性

- **入口/函数**: `tests/cli/test_transient_slow_consumer_path.py` — `test_real_transient_slow_consumer_falls_back_once_with_original_typed_error`
- **文件(行号)**: `tests/cli/test_transient_slow_consumer_path.py:289`
- **输入场景**: Service 调用 `cast(Host, probe)` 传入 `submit_entrypoint_turn_and_wait`
- **实际分支**: `_SlowConsumerHostProbe` 只实现 `watch_session_events`、`submit_followup`、`get_run`、`read_outbox_terminal_items` 四个方法
- **预期行为**: 传给 `submit_entrypoint_turn_and_wait` 的 `Host` 应满足完整 `Host` Protocol
- **实际行为**: `cast(Host, probe)` 是类型级谎言。若 Service 未来调用其它 `Host` 方法（如 `cancel_run`、`ensure_session`），将在运行时得到 `AttributeError`
- **直接证据**: `cast(Host, probe)` at line 289；`_SlowConsumerHostProbe` 类定义 at lines 97-227 只实现 4 个方法
- **影响**: 当前路径下 Service 只调用这四个方法，因此不触发。若 Service 新增对 `Host` 的调用，测试会在运行时报错而非编译时报错。
- **建议改法和验证点**: 可考虑让 probe 继承一个 stub 基类或使用 `unittest.mock.create_autospec`。但这不是 blocking issue——当前测试路径正确。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 4-F4-信息-stress-test-默认不运行

- **入口/函数**: `tests/host/test_transient_delta_stress.py`
- **文件(行号)**: `tests/host/test_transient_delta_stress.py:18` (`pytestmark = pytest.mark.stress`)
- **输入场景**: 默认 `pytest tests/host` 不运行 stress 测试
- **实际分支**: `addopts=-m 'not stress'` 排除 stress marker
- **预期行为**: 高量 zero-row 证据应定期运行
- **实际行为**: stress 测试需要显式 `pytest -o addopts="" -m stress tests/host/test_transient_delta_stress.py -q` 才能运行。implementation artifact 记录了该命令及其通过结果。
- **直接证据**: `pytestmark = pytest.mark.stress` at line 18；`tests/README.md` 记录显式运行方式
- **影响**: CI 默认不运行 3×1000 delta stress 测试。若 production 破坏 zero-row invariant，不会在常规 CI 中发现。
- **建议改法和验证点**: 这是仓库既有 convention（`test_host_production_stress.py` 同样如此），不是 Slice 2 新引入的。README 已正确记录运行方式。若需要定期运行，应在 CI pipeline 中添加显式 stress job。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 信息

## Adversarial Verification 对照

### 1. stress 是否真实经 open_host / Host ingest 各发布至少 1000 条三类 delta、严格零 EventLog rows

**PASS。** `test_three_thousand_transient_deltas_leave_zero_rows_and_durable_terminal` 经 `open_host(options)` 创建真实 Host，使用 `TransientStreamWorkerFactory` 产出 3×1000 delta。fast watcher 精确观察 `(1000, 1000, 1000)`。`event_log_type_count` 对三类 delta type 断言严格为 0。`RUN_SUCCEEDED` row 为 1。`read_transient_durable_snapshot` 核对 Run/Attempt/terminal 同源。direct evidence: `tests/host/test_transient_delta_stress.py:72-109`。

### 2. capacity 256 慢 watcher overflow 是否确定、快 watcher/terminal/Run 不受影响，typed error 原样

**PASS。** `test_capacity_slow_watcher_overflow_does_not_block_fast_watcher_or_terminal` 发送 86×3=258 delta，slow_watcher 不消费，fast_watcher 消费全部 258 + terminal。slow watcher 精确收到 256 条 prefix 后抛 `HostApiError(UNAVAILABLE, retryable=True, detail=HostUnavailableDetail(session_live_stream, slow_consumer))`。fast terminal 为 SUCCEEDED，Run 为 SUCCEEDED，三类 delta row 为 0。direct evidence: `tests/host/test_watch_session_events.py:541-610`。

### 3. publish-before-wait、wait-before-publish、drain-clear-publish、overflow/close wakeup barriers 是否真正确定

**PASS（with caveat）。** 四个 barrier 测试全部使用 deterministic `asyncio.Event`-based barrier，无 sleep-based 同步。`_WaitEnteredEvent` 通过 override `wait()` 暴露 wait-entered signal；`_PublishOnClearEvent` 通过 override `clear()` 在 clear 线性化点同步 publish。所有 timeout 均为 safety guard，正常行为下不触发。caveat：三个测试替换 `subscription._ready` 私有字段（Finding 1）。direct evidence: `tests/host/test_transient_delta.py:32-91`、`:220-308`。

### 4. tests/cli/test_transient_slow_consumer_path.py 是否真实走 Host publisher/subscription→Service bounded relay→CLI renderer

**PASS。** 完整链路：
1. `open_host(options)` 创建真实 Host（real SQLite, real hub, real subscription bounded queue capacity 256）
2. `_SlowConsumerHostProbe` 包装真实 Host，只阻塞首次 `get_run()`，其余方法透明透传
3. `submit_entrypoint_turn_and_wait(cast(Host, probe), ...)` 使用真实 Service entrypoint
4. Service drain task 填满 relay queue 后停在 `await queue.put`（第 257 个 item）
5. Host subscription overflow，typed `UNAVAILABLE/slow_consumer` 进入 `_WatcherFailure`
6. Service Outbox fallback 收口，terminal source 为 `OUTBOX_READ`
7. `render_prompt_terminal_result` 和 `CliThinkingRenderer` 使用真实 CLI renderer

DS-F02 闭环：thinking 展示一次（`"Thinking:"` 出现 1 次），final 展示一次（`_FINAL_ANSWER` 出现 1 次），30s timeout 内结束。唯一的 controlled injection 是 `TransientStreamWorkerFactory`（替代 LLM backend），这是避免网络不确定性的必要测试边界。direct evidence: `tests/cli/test_transient_slow_consumer_path.py:284-386`。

### 5. attach/no replay/first delta、cancel/aclose/missing/durable read failure/Host close cleanup 是否完整

**PASS。**
- attach/no replay/first delta: `test_watch_does_not_replay_pre_attach_transient_and_keeps_first_post_attach_delta` 证明 attach 前 Run 的 delta 不 replay，attach 后下一 Run 首个 delta 不丢。direct evidence: `test_watch_session_events.py:606-641`。
- cancel: `test_watch_cancel_after_first_delta_detaches_without_cancelling_run` 证明后续 iteration cancel 只 detach，不改变 RUNNING Run。direct evidence: `:554-601`。
- never-started/missing/close: `test_watch_never_started_first_cancel_missing_and_host_close_cleanup` 覆盖 never-started `aclose()`、missing Session `NOT_FOUND`、首次 `__anext__` cancel、started terminal 后 `aclose()`、Host close，均回收 subscription 到 0。direct evidence: `:655-698`。
- durable read failure: `test_watch_first_and_subsequent_durable_failures_are_public_and_detach` 用 `_replace_event_payload` 注入 SQLite corruption，首次和 transient 后均只暴露 `HostApiError(INTERNAL_ERROR, retryable=False)`，不泄漏 private exception。direct evidence: `:700-780`。

### 6. tests/host/transient_stream_support.py 572 行是否 God helper

**PASS。** 模块职责收敛：提供 `TransientStreamWorkerFactory`（可控 worker）、`TransientStreamCounts`（三类计数）、`TransientDurableSnapshot`（durable 快照）、`event_log_type_count`（EventLog row 计数）、`read_transient_durable_snapshot`（Run/Attempt/terminal 同源读取）、`transient_stream_open_host_options`（options 构造）。无 God function、无重复逻辑、无违反严格类型。所有 dataclass 为 `frozen=True, slots=True`，所有 helper 函数有完整中文 docstring。direct evidence: `tests/host/transient_stream_support.py` 全文。

### 7. private _PublicHostHandle / hub probe 与 SQLite corruption 是否是合理 owner-level testing boundary

**PASS（with caveat）。**
- `_subscription_count` 直接访问 `_PublicHostHandle._transient_delta_hub.subscription_count(session_id)`，这是 owner-level testing：测试需要验证 subscription lifecycle，而 `Host` Protocol 不暴露 subscription 计数。这是合理的 testing boundary，不是 production contract。
- `_replace_event_payload` 直接操作 SQLite 注入 corruption，这是 durable failure injection 的标准做法，不绕过 production code。
- caveat: `_PublicHostHandle` 是 private class，测试 import 它（`from dayu.host.open_host import _PublicHostHandle`）。若该类被重命名或移除，测试会 import error。但这是正常的 private-API testing coupling。

### 8. 四份 README 是否只描述当前实现且职责准确

**PASS。**
- `dayu/README.md`: 更新 Service 装配描述（有界 relay）、投递与派生视图（transient delta 不写 EventLog）、核心术语（`HostTransientDelta`、`HostSessionEvent`）、Host public contract 类型列表。所有描述与 Slice 1 production code 一致。
- `dayu/host/README.md`: 更新 `watch_session_events` 语义（attach-before-return、transient subscription）、新增 `transient_delta` 模块、更新 stable boundary、stream 术语、EventLog event class、HostEvent 与 HostTransientDelta 分离。所有描述准确。
- `dayu/service/README.md`: 更新 `entrypoint_runtime` 描述（有界 relay、await-put 背压、typed watcher failure、reasoning delta 投影）。准确。
- `tests/README.md`: 新增 transient delta stress 运行方式、transient Host→Service→CLI regression 描述、deterministic barrier 覆盖说明。准确。

### 9. 是否有本 Slice 应修的真实 production defect 被测试绕开

**PASS。** Slice 2 implementation artifact 正确声明"无 production 代码修改"。所有变更均为测试、test support 和 README。adversarial barrier、真实跨层 E2E 和全量回归没有发现 production correctness defect。测试通过真实 `open_host` 路径、真实 Service relay、真实 CLI renderer 验证，未用 fake 绕过 production 语义。

## Open Questions

无。

## Residual Risk

1. **stress test 默认不运行**：3×1000 delta zero-row 测试需要显式 `-m stress` 运行。若 CI pipeline 未包含该命令，zero-row invariant 的回归只在手动验证时发现。这是仓库既有 convention，非 Slice 2 新引入。
2. **private field barrier coupling**：三个 readiness 测试替换 `subscription._ready`。若 production 改变 readiness primitive（从 `asyncio.Event` 改为 `asyncio.Condition` 等），测试不会自动检测到 breakage——它们仍会注入自己的 Event 并"通过"。这不会掩盖 production bug（因为 public contract 行为仍被验证），但会使 barrier 失效。
3. **CLI test 50ms 稳定性窗口**：`asyncio.sleep(0.05)` 在极端负载下理论上可能不足。但实际风险极低：count 单调递增且有上界。
4. **E2E 使用可控 worker**：`TransientStreamWorkerFactory` 替代真实 LLM backend。Host publisher/subscription、Service relay/fallback、SQLite durable store/Outbox 和 CLI renderer 均为 production path，但 Engine→Host 的 EngineEvent 由测试产生。这是避免网络/供应商不确定性的必要边界。

## Verdict

**PASS。** 无 blocking finding，不需要 current fix。

- **Blocking finding 数**：0
- **需要 current fix**：否。Slice 2 无 production 代码变更，四个 low/informational finding 均不阻塞 merge。

**四个 low/informational finding 处置建议：**

| 编号 | 严重度 | 建议处置 |
|---|---|---|
| 1-F1 | 低 | **deferred-with-owner**：private `_ready` barrier coupling 是 deterministic testing 的合理 trade-off。若未来 production 改变 readiness primitive，需同步更新测试 barrier；当前无需修改。建议在测试中补一行注释说明此 coupling，可作为 follow-up cleanup。 |
| 2-F2 | 低 | **accepted**：bounded polling 是 Service relay 层不暴露 queue full signal 的必然结果。消除 polling 需扩展 Service public contract，超出本 WU scope。 |
| 3-F3 | 低 | **accepted**：`cast(Host, probe)` 是 narrow protocol test probe 的标准做法。当前 Service 只调用四个方法，运行时安全。若 Service 扩展 `Host` 调用面，测试会在运行时报错。 |
| 4-F4 | 信息 | **accepted**：stress test 默认不运行是仓库既有 convention（`test_host_production_stress.py` 同样如此）。README 已记录显式运行方式。若需定期覆盖，应在 CI pipeline 层面添加显式 stress job，不在本 Slice scope。 |
