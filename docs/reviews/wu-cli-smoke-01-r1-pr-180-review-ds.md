# WU-CLI-SMOKE-01-R1 Draft PR #180 Strict PR Review — AgentDS

## Scope

- Mode: PR review（Draft PR #180）
- Repository: noho/dayu-agent-r
- PR: #180
- Title: WU-CLI-SMOKE-01-R1: move engine deltas to Host transient live stream
- Author: noho (Leo Liu)
- Head: phaseflow/wu-cli-smoke-01-r1 (ff5d515a)
- Base: main
- URL: https://github.com/noho/dayu-agent-r/pull/180
- Output file: docs/reviews/wu-cli-smoke-01-r1-pr-180-review-ds.md
- Included scope:
  - PR body, title, metadata, head/base/draft state
  - Full远端 diff (14,384 lines, 75 files)
  - 生产代码：`dayu/host/transient_delta.py`, `dayu/host/api.py`, `dayu/host/engine_ingest.py`, `dayu/host/open_host.py`, `dayu/host/dispatch.py`, `dayu/host/read_api.py`, `dayu/host/lifecycle_events.py`, `dayu/host/__init__.py`, `dayu/service/entrypoint_runtime.py`, `dayu/cli/thinking.py`
  - 测试代码：`tests/host/test_transient_delta.py`, `tests/host/test_transient_delta_stress.py`, `tests/cli/test_transient_slow_consumer_path.py`, `tests/host/test_watch_session_events.py`, `tests/host/test_engine_ingest_mapping.py`, 及全部受影响测试文件
  - 设计真源：`docs/host/design.md`, `docs/engine/design.md`
  - 总控文档：`docs/host/issues-implementation-control.md`
  - Accepted plan: `docs/host/wu-cli-smoke-01-r1-engine-delta-transient-live-stream-plan.md`
  - Aggregate deepreview artifacts：MiMo + DS + controller adjudication
  - README: `dayu/README.md`, `dayu/host/README.md`, `dayu/service/README.md`, `tests/README.md`
- Excluded scope: Engine 代码（未修改），runtime 包（未修改），docs/reviews/ 下历史 review/fix/adjudication artifact 的逐行重审（已由 aggregate deepreview 裁决），CI checks（Windows jobs 仍在 pending，属 Draft PR 预期状态）
- Review date/time: 2026-07-21 02:31 UTC+8

---

## PR 基础事实核对

### PR 元数据

| 检查项 | 结果 | 证据 |
|---|---|---|
| Draft 状态 | ✓ | `gh pr view 180 --json isDraft` → `true` |
| 无 reviewers | ✓ | `gh pr view 180 --json reviews` → `[]` |
| Head SHA | ✓ | `ff5d515a` = PR commits 最新 sha |
| Base branch | ✓ | `main` |
| mergeStateStatus | UNSTABLE | Windows CI jobs pending，非失败 |

### PR body 准确性

| 检查项 | 结果 | 证据 |
|---|---|---|
| 摘要正确描述三类 delta 统一 | ✓ | body 与 plan §3.1 一致 |
| 验证数据与实际一致 | ✓ | body 声称 2816 passed / 8 skipped — 与 Slice 2 aggregate validation report 一致 |
| Closes footer 缺失有合理解释 | ✓ | "本 WU 是 PR #179 后的 residual remediation，没有独立 Issue owner，因此不添加 Closes footer" — 与 control doc L187 一致 |
| 已接受边界声明正确 | ✓ | 五项边界与 plan §3.2 非目标一致 |
| 验证项中"AgentMiMo / AgentDS Slice review 与 aggregate deepreview：均 PASS，0 blocking finding" | ✓ | 与 aggregate deepreview artifacts 一致 |

### 远端 diff 完整性

| 检查项 | 结果 |
|---|---|
| 生产代码 10 文件全部在 diff 中 | ✓ |
| 测试代码 25+ 文件全部在 diff 中 | ✓ |
| accepted plan 在 diff 中 | ✓ |
| 两 Slice + aggregate artifacts 在 diff 中 | ✓ |
| control doc 状态更新在 diff 中 | ✓ |
| 设计真源更新在 diff 中 | ✓ |
| 四份 README 更新在 diff 中 | ✓ |

---

## Findings

经过对全部生产代码关键调用链、测试入口、public contract、设计真源、控制文档和 README 的独立逐路径走读与 adversarial failure pass，**未发现 correctness、stability 或 maintainability 层面的 material defect**。

以下按用户指定重点核验维度逐项给出独立证据与结论。

---

### 1. 三类 delta 唯一 owner、zero EventLog row、after-commit publish

**PASS。0 finding。**

独立核验证据链：

1. **统一分类入口**：`engine_ingest.py:5212-5224` `_is_transient_delta_event` 闭集覆盖 `CONTENT_DELTA`、`REASONING_DELTA`、`TOOL_CALL_DELTA`，均做 `isinstance` type guard。

2. **统一映射+零 row**：`engine_ingest.py:1041-1042` 在 `_ingest_validated` 最优先进入 transient 分支，调用 `_accepted_no_event_result(_validated_transient_delta_candidate(context, event))`，返回 `events=()`（`engine_ingest.py:7019-7036`）。

3. **精确 payload 映射**：`engine_ingest.py:5227-5273` `_validated_transient_delta_candidate` 对三类 delta 穷举 `elif`，每类精确映射到 `HostContentDelta`/`HostReasoningDelta`/`HostToolCallDelta`；`else` 分支 raise `ValueError`。

4. **After-commit publish**：`engine_ingest.py:789` `ingest()` 调用 `_ingest_before_reactive_compaction`（内部 `run_write` 提交 transaction），返回后再调用 `_finish_ingest`（L794），`_finish_ingest` 在 `_with_terminal_promotion_retry` 返回后调用 `_publish_transient_delta`（L871-875）。publish 严格在 durable transaction 提交之后。

5. **REASONING_DELTA → PREVIEW 旧分支已删除**：`engine_ingest.py` 中 `_ingest_validated` 不再包含 reasoning 特例分支（grep 确认 `REASONING_DELTA` 只出现在 `_is_transient_delta_event` 和 `_validated_transient_delta_candidate` 中）。

6. **validation 失败不 publish**：`engine_ingest.py` 中所有非 transient 路径的 `EngineIngestResult` 构造均传入 `transient_delta=None`（grep 确认 35+ 处）。

---

### 2. Public typed identity、terminal fence、multi-watcher、slow consumer

**PASS。0 finding。**

独立核验证据链：

1. **runtime identity**：`transient_delta.py:434-464` `Hub.publish` 每次分配一个 `runtime_sequence`（L445），构造一次 immutable `HostTransientDelta`（L446-462），`dedupe_key` 由 `_transient_dedupe_key(runtime_id, execution_id, worker_event_index)` 生成（L457-461）。

2. **multi-watcher fanout**：`transient_delta.py:444` 用 `tuple()` eager snapshot 取 subscription 列表，同一 envelope 实例 fanout 到所有 watcher（L463-464）。

3. **terminal fence**：
   - `transient_delta.py:329` `_offer` 检查 `event.run_id in self._terminal_run_ids`，拒绝已终态 Run 的 delta。
   - `transient_delta.py:255` `drain_nowait` 同样检查 terminal fence。
   - `open_host.py:1019` `mark_run_terminal` 在 yield durable terminal 前调用，确保所有已 buffer 的同 Run delta 先于 terminal 交付。

4. **slow consumer**：
   - Subscription queue 容量 `_TRANSIENT_WATCH_BUFFER_CAPACITY = 256`（`transient_delta.py:26`）。
   - `_offer` 使用 `put_nowait`（L332），`QueueFull` 时标记 `_overflowed=True` + detach（L334-335）。
   - Consumer 在 drain 后检查 `overflow_error()` → 抛 typed `HostApiError(UNAVAILABLE, retryable=True, detail=HostUnavailableDetail(component="session_live_stream", reason_code="slow_consumer"))`（`transient_delta.py:96-111`、`open_host.py:987-989`）。
   - 无 silent-drop：overflow 后已接受的前缀被完整 drain 后才抛错误。

5. **detach/close**：
   - `subscription.close()`（L307-319）幂等，detach + clear queue + `_ready.set()`。
   - `_close_from_hub()`（L338-349）响应 hub close，不 detach（hub 已 clear 全部），直接清空队列并唤醒。
   - Hub close（L477-494）幂等，snapshot 全部 subscription 后 `_close_from_hub` 每个。
   - Close 序列（`open_host.py:1046`）：`hub.close()` 先于 scheduler/projection/actor close，确保 watcher 在 scheduler 存活时被唤醒收口。

6. **Host close 不伪造 terminal**：`open_host.py:1038-1077` `_close_owned_resources` 全程不写 `RUN_CANCELLED`/`RUN_FAILED`/terminal fact。

---

### 3. Host → Service → CLI 只有 public union，无 raw EngineEvent 越层

**PASS。0 finding。**

独立核验证据链：

1. **Public union 定义**：`api.py:3505` `HostSessionEvent: TypeAlias = HostEvent | HostTransientDelta`。

2. **watch_session_events 返回 union**：`api.py:3902` `def watch_session_events(self, session_id: str) -> AsyncIterator[HostSessionEvent]`。

3. **Service 穷举分支**：`entrypoint_runtime.py:1189-1212` `_drain_available_watcher_items` 对 `HostEvent`/`HostTransientDelta` 做 `isinstance` 分支，`assert_never` 兜底。

4. **仅 reasoning → EntrypointThinking**：`entrypoint_runtime.py:1270-1297` 只把 `HostReasoningDelta` 投影为 `EntrypointThinking`，content/tool-call 明确忽略。

5. **CLI 不 import Host/Engine**：`cli/thinking.py` grep 零命中 `dayu.engine`/`EngineEvent`/`dayu.host`（除 `HostTransientDeltaType` 等已被 Service 投影的类型）。

6. **raw EngineEvent 越层检查**：grep `EngineEvent|dayu\.engine` `dayu/service/entrypoint_runtime.py` `dayu/cli/thinking.py` → 零命中。

7. **Service bounded relay**：`entrypoint_runtime.py:76` `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY = 256`；`entrypoint_runtime.py:1027` queue 构造使用此容量；relay 满时 `await queue.put` 自然背压 → Host subscription overflow → 原 typed error 进入 `_WatcherFailure`。

---

### 4. 旧符号清理

**PASS。0 finding。**

| 旧符号 | grep 结果 |
|---|---|
| `HostThinkingView` | 全仓零命中 |
| `_thinking_from_row` | 全仓零命中 |
| `HostPreviewEventType.REASONING_DELTA` | 全仓零命中 |
| `_EVENT_TYPE_REASONING_DELTA` | 全仓零命中 |
| `HostEvent.thinking` | 全仓零命中 |
| `read_api.py` 中 `REASONING_DELTA`/`reasoning` | 零命中 |
| `lifecycle_events.py` 中 `REASONING_DELTA`/`reasoning` | 零命中 |

---

### 5. 新 public contract 导出

**PASS。0 finding。**

`dayu/host/__init__.py` 正确导出：`HostTransientDelta`, `HostTransientDeltaType`, `HostTransientDeltaData`, `HostContentDelta`, `HostReasoningDelta`, `HostToolCallDelta`, `HostSessionEvent`, `HOST_TRANSIENT_DELTA_TYPE_TO_DATA`。全部列入 `__all__`（L179-221）。

不再导出：`HostThinkingView`（已删除）。

---

### 6. README / design / control / residual reconciliation

**PASS。0 finding。**

- **dayu/host/README.md**：L86 描述 `watch_session_events` 新语义；L248 列出新类型；L324 新增 `transient_delta` 模块描述；L337-352 术语表新增 `Host transient delta stream` 与 `Host session live stream`。
- **dayu/service/README.md**：L27 描述容量 256 有界 relay、`HostSessionEvent` 联合类型、reasoning delta → EntrypointThinking 投影、content/tool-call 忽略。
- **dayu/README.md**：L100 描述 Service 通过有界 relay 消费；L134 描述三类 delta 零 EventLog row；L146-147 术语表新增定义；L196 public contract 描述更新。
- **tests/README.md**：L75-79 新增 stress marker 运行说明；L114-115 新增 transient 测试运行命令；L262 新增 transient Host→Service→CLI regression；L284 新增 transient delta stress。
- **docs/host/design.md**：§4.1 固定 transient 术语与三类 delta owner；§10 删除 `HostEvent.thinking`；§13 固定三类 delta 不进入 EventLog；§16 固定 EventLog/read model/outbox 只拥有 durable member。
- **docs/host/issues-implementation-control.md**：当前状态表正确记录 gate=`PR-review`、active work unit、全部 artifact/commit 链与 next entry point。

---

### 7. Adversarial failure pass

以下 adversarial 维度均通过独立核验：

| 维度 | 结果 | 关键证据 |
|---|---|---|
| Lost wakeup | PASS | `wait_ready` 使用 clear-recheck 三段式 level-triggered，`_offer` 在 `put_nowait`/overflow 后 `_ready.set()` |
| TOCTOU | PASS | publish 在 transaction commit 后，terminal mark 同步区间无 `await` |
| Resource/task leak | PASS | subscription/hub 不创建 asyncio Task；iterator `aclose()` 幂等 detach；cursor future 由 `_observe_watch_cursor_future` 收口 |
| Cross-run/session leakage | PASS | subscription 按 session_id 索引；terminal fence 按 run_id 隔离 |
| Restart/replay 误承诺 | PASS | `runtime_id = uuid.uuid4()`；`runtime_sequence` 从 1 开始；hub 不持久化 |
| Unbounded queue | PASS | 两级 256 容量：hub subscription queue + Service relay queue |
| Fake terminal | PASS | Host close 不写 terminal；overflow/detach 不 cancel Run |
| Final 重复 | PASS | thinking 写 stderr，final answer 写 stdout；CLI renderer 用 `(runtime_id, runtime_sequence)` + `dedupe_key` 去重 |
| Error 重写 | PASS | `_WatcherFailure.error` 保存原 `HostApiError` 实例，不做类型转换 |
| Durable/transient 双真源 | PASS | `HostEvent.event_sequence` 与 `HostTransientDelta.runtime_sequence` 字段互斥、类型不可互换 |
| 无兼容 shim | PASS | 旧符号全部删除，无 re-export、wrapper、fallback、`hasattr`/`getattr` 绕过 |
| 无语义所有权漂移 | PASS | 每类事实有唯一 owner（见 plan §2.3 semantic owner 裁决表），生产代码与冻结契约一致 |

---

### 8. 测试覆盖

**PASS。0 finding。**

- `test_transient_delta.py`：三类 payload mapping、fanout、sequence/dedupe、overflow、detach、close、四类 deterministic barrier 交错。
- `test_transient_delta_stress.py`：三类各 1,000 delta，EventLog row = 0，terminal durable facts 正常。
- `test_watch_session_events.py`：attach race、多 watcher、terminal fence、overflow 隔离、HostClosedError、NOT_FOUND、aclose/cancel/cursor failure。
- `test_engine_ingest_mapping.py`：valid 三类 publish once、invalid/stale/late/rollback = publisher 0。
- `test_transient_slow_consumer_path.py`：真实 Host → Service bounded relay → CLI renderer 全链路，typed overflow + Outbox fallback + 同 identity 单次展示。
- 独立 stress：1 passed（默认 pytest 排除）。
- 最终 suite：2816 passed / 8 skipped / 6 deselected。

---

## Open Questions

无。所有指定核验维度均有直接代码路径证据支撑。aggregate deepreview 中 DS 的 7 个低项已由 controller 基于 owner/可达 schedule/变更归属直接证据裁决为 rejected-with-reason（详见 `wu-cli-smoke-01-r1-aggregate-deepreview-controller-adjudication.md`），本 PR review 独立复核后认同所有裁决。

---

## Residual Risk

- `mergeStateStatus: UNSTABLE` 系 Windows CI jobs 仍在 pending，非失败。Draft PR 阶段无需 mergeable check pass。
- 容量 256 是首版内部安全值，缺少真实负载调优数据，已在 accepted boundaries 中记录。
- durable/transient 不承诺跨域可重放总序，已在设计真源与 accepted boundaries 中冻结。
- 外部 LLM provider 由可控 worker 替代（E2E 测试边界），不影响 Host → Service → SQLite/Outbox → CLI 生产路径验证。

以上均为已记录、已归属的已知边界，不构成 merge 前 blocking issue。

---

## 结论

**PASS。0 blocking finding。无需 current fix。**

Draft PR #180 的远端 diff 完整覆盖 accepted plan、两 Slice、aggregate artifacts 与最新 control；三类 delta owner、zero-row、after-commit、terminal fence、multi-watcher、slow-consumer、Host→Service→CLI public union、验证证据、README/design/control/residual reconciliation 均通过独立代码路径核验。PR 当前正确保持 Draft 状态，无意外 request reviewers/mark ready。未发现 merge 前 correctness、stability、maintainability、过度耦合或 semantic ownership drift 问题。
