# WU-HOST-SESSION-EVENT-DELIVERY-01 Slice 1 Code Re-Review (AgentDS)

## Scope

- Gate: `code-rereview-slice-1`
- Base: `33af05fa` (accepted plan amendment commit)
- Reviewer: AgentDS (Slice 1 原 reviewer)
- Controller adjudication: `docs/reviews/wu-host-session-event-delivery-01-slice1-code-review-controller-adjudication.md`
- Codex fix artifact: `docs/reviews/wu-host-session-event-delivery-01-slice1-fix-codex.md`
- 审查对象: Controller accepted finding DS-F02 的闭包、全部 S1 current changes 的 adversarial sweep
- 排除: AgentMiMo 原 review、AgentMiMo 本轮 re-review artifact、Controller 总控
- 方法: 逐行走读 `git diff 33af05fa` 全量变更 + 确定性 adversarial 场景验证 + 完整测试/pyright/coverage/stale scan

## 1. DS-F02 Closure Verification

### 1.1 Finding recap

Controller 将 DS-F02 从 low 提升为 correctness finding：

> `pop_next_nowait()` 在 accepted base 的 `drain_nowait()` 会丢弃 `_terminal_run_ids` 中的已排队项；当前 `pop_next_nowait()` 直接 `popleft()`，丢失了 watcher-local terminal fence。在 durable read await 交界处，同 Run transient 可先进入 mailbox；durable batch 返回后 mark_run_terminal 并交付同 Run terminal；下一次 `anext()` 会把 stale transient 交出去。

### 1.2 Fix analysis

Codex 在 `HostTransientDeltaSubscription.pop_next_nowait()`（`dayu/host/transient_delta.py:415-436`）实现了 single-pop owner boundary 内的 terminal fence 过滤：

```python
def pop_next_nowait(self) -> HostTransientDelta | None:
    if self._in_flight is not None:
        raise RuntimeError("subscription in-flight item must be released before pop")
    while self._mailbox:
        event = self._mailbox.popleft()
        if event.run_id in self._terminal_run_ids:
            continue          # ← stale item 释放，不进入 in-flight
        self._in_flight = event
        self._refresh_readiness()
        return event
    self._refresh_readiness()
    return None
```

### 1.3 Verified behaviors（均通过直接代码走读与运行期断言）

| 验证项 | 状态 | 直接证据 |
|---|---|---|
| stale item 绝不写入 `_in_flight` | ✅ | `continue` 跳过，mailbox item 已 `popleft()` 释放 |
| 有效 transfer 不降 retained count | ✅ | mailbox−1 + in_flight+1 = retained 不变，`retained_items` 公式 `len(mailbox)+(1 if in_flight else 0)` 对齐 |
| Controller 描述的 race 场景 | ✅ | mailbox 中预存 run-1 stale，`mark_run_terminal("run-1")` 后 `pop_next_nowait()` 返回 `None`，`retained_items` 变为 0 |
| mixed stale+valid 场景 | ✅ | [run-1, run-2] → mark run-1 terminal → pop 返回 run-2，run-1 filtered |
| `release_in_flight()` 后 retained 正确 | ✅ | 从 1 变为 0 |
| readiness 在 stale-only 后 clear | ✅ | `_is_ready()` 返回 False（mailbox empty, not overflowed, not closed）|
| readiness 在 mixed 后 set（in-flight 不 trigger ready）| ✅ | `_is_ready()` 只看 mailbox 非空/overflow/close，in-flight 不触发 ready |
| `_offer()` 的 `terminal_run_ids` 拒绝 | ✅ | mark 之后的同 Run publish 被 `_offer()` 行 524 的 `event.run_id in self._terminal_run_ids` 拒绝 |

### 1.4 Deterministic test 有效性

`tests/host/test_transient_delta.py:219-257` `test_single_pop_filters_prequeued_terminal_stale_item`：

- **场景 A**：mailbox 预存 [run-1, run-2]，mark run-1 terminal → pop 返回 run-2。断言：run-1 不被交付、run-2 是唯一 in-flight、retained_items 2→1、release 后 0、readiness cleared。
- **场景 B**：mailbox 只预存 run-3，mark terminal → pop 返回 None。断言：stale 不进入 in-flight、retained_items 1→0、readiness cleared。
- **红灯复现**：Codex 报告红灯失败输出 `run-1`（实际返回 stale），修复后通过。
- **本 reviewer 独立运行**：`1 passed in 0.30s`。红灯可复现性已验证（Codex 记录）。

### 1.5 DS-F02 结论

**已关闭。** watcher-local terminal fence 已在 `HostTransientDeltaSubscription.pop_next_nowait()` single-pop owner boundary 正确恢复，不使用下游 fallback、不进入 Slice 2 causal fence、不改变 Controller rejected findings。

---

## 2. Retained / Readiness / Overflow / Close Accounting

### 2.1 Retained items 不变量

公式：`retained_items = len(self._mailbox) + (1 if self._in_flight is not None else 0)`

| 操作 | mailbox Δ | in_flight Δ | retained Δ | 验证 |
|---|---|---|---|---|
| `_offer()` accept | +1 | 0 | +1 | ✅ `self._mailbox.append(event)` |
| `_offer()` overflow | 0 | 0 | 0 | ✅ 不 append，设 `_overflowed=True` |
| `_offer()` terminal fence | 0 | 0 | 0 | ✅ `event.run_id in self._terminal_run_ids → return` |
| `pop_next_nowait()` stale skip | −1 | 0 | −1 | ✅ `popleft()` + `continue` |
| `pop_next_nowait()` valid | −1 | +1 | 0 | ✅ `self._in_flight = event` |
| `release_in_flight()` | 0 | −1 | −1 | ✅ `self._in_flight = None` |
| `close()` / `_close_from_hub()` | clear→0 | None | 0 | ✅ `_clear_retained_state()` |

每条路径的 retained accounting 已验证正确。

### 2.2 Overflow 路径

- overflow 时 `_offer()` 设 `_overflowed=True`、从 fanout detach、记录低基数日志、set readiness → **不释放 reservation**
- 验证：`reservation.is_released is False` after overflow；`hub.reservation_count('session-1') == 1`
- overflow error 返回 `HostApiError(code=DELIVERY_INTERRUPTED, retryable=False, detail=HostSessionEventDeliveryDetail(reason=TRANSIENT_MAILBOX_OVERFLOW))`
- accepted prefix 保留在 mailbox 中，caller 仍可通过 `pop_next_nowait()` 消费
- 验证：cap=2，publish 3 items → 前 2 个可 pop，第 3 个触发 overflow，`overflow_error()` 返回 non-None

### 2.3 Readiness 信号

- `_is_ready()` = `bool(self._mailbox) or self._overflowed or self._closed`
- `_refresh_readiness()` 使用双检模式（clear + check + set if ready），避免唤醒丢失
- `wait_ready()` 使用双检 + `asyncio.wait_for(self._ready.wait(), timeout)` + `TimeoutError` 后 `_is_ready()` 复检
- 验证：publish-before-wait 立即 ready（level-triggered）、wait-before-publish 可靠唤醒（deterministic barrier 测试）

### 2.4 Close 路径

| close 路径 | 触发方式 | subscription close | reservation release | reason |
|---|---|---|---|---|
| `_HostSessionEventIterator.aclose()` | caller aclose / async for | ✅ `subscription.close()` | ✅ | CALLER_CLOSED |
| `_HostSessionEventIterator.__anext__` 异常 | generator 异常/EOF | ✅ `subscription.close()` | ✅ | CALLER_CLOSED |
| `_watch_session_events` finally | generator 结束 | ✅ `subscription.close()` | ✅ | CALLER_CLOSED |
| `hub.close()` → `_close_from_hub()` | Host close | ✅ cleared + released | ✅ | HOST_CLOSED |

所有路径均幂等（`_closed` flag + `_released` flag）。已验证对同一 subscription 先后调 calller close 和 hub close 无 double-free。

---

## 3. Adversarial Sweep — S1 全量 Current Changes

### 3.1 Production 文件

| 文件 | 审查结论 | 注 |
|---|---|---|
| `dayu/host/api.py` | PASS | 新增类型全部 frozen/slots、`__post_init__` 严格校验 bool/zero/negative；`HostSessionEventIterator` Protocol、`Host.watch_session_events` 改为 async factory；`HostApiErrorDetail` closed union 扩展；`__all__` 完整导出 |
| `dayu/host/__init__.py` | PASS | 导出符号与 api.py `__all__` 完全一致 |
| `dayu/host/transient_delta.py` | PASS | 完整替换 asyncio.Queue(256)/batch drain → deque mailbox + single in-flight + reservation token；DS-F02 已修复 |
| `dayu/host/open_host.py` | PASS | `watch_session_events` 改为 async factory（reserve → await cursor → attach → return iterator）；`_watch_session_events_after` 改用 `pop_next_nowait`/`release_in_flight`/`pending_durable`；iterator 创建从 lazy 改为 eager（语义等价）；hub close 移到 producer cleanup 之后（符合 plan §7 item 7）；删除 `_observe_watch_cursor_future`、`_ClosableHostSessionEventIterator` |
| `dayu/runtime/config_loader.py` | PASS | `SessionEventDeliveryPolicyConfig` frozen/slots、strict exact-two-fields positive-int parser |
| `dayu/config/host_runtime.json` | PASS | `session_event_delivery_policy.transient_mailbox_max_items=512, max_subscriptions_per_session=4` |
| `dayu/service/host_assembly.py` | PASS | `_compose_options` 从 config 一对一构造 `HostSessionEventDeliveryPolicy(...)` |
| `dayu/service/entrypoint_runtime.py` | PASS | 仅机械传播：删除 private `ClosableHostSessionEventIterator` Protocol/cast、改为 `await host.watch_session_events(...)`、更新类型 annotations；全部 relay 符号（`_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`、`_WatcherFailure`、queue、drain_task）按 plan §7 item 8-9 保留冻结 |

### 3.2 Tests / Fixtures

全部 53 changed files 中，test/fixture 变更分为三类：

1. **`OpenHostOptions(...)` 构造点补充 `session_event_delivery_policy`**：14 个 test/fixture 文件使用显式 `HostSessionEventDeliveryPolicy(transient_mailbox_max_items=512, max_subscriptions_per_session=4)`，无 hidden fallback
2. **`watch_session_events(...)` 改为 `await`**：全部 production/test/utils callers 显式 await
3. **Contract/owner tests 新增**：
   - `tests/host/test_public_contracts.py`：frozen/slots、enum values、policy validation、error detail
   - `tests/host/test_transient_delta.py`：reservation、mailbox、in-flight、overflow、readiness、DS-F02 terminal fence、deterministic barriers
   - `tests/host/test_watch_session_events.py`：async attach、iterator lifecycle、dual watcher、delivery interruption、retained accounting、cap admission
   - `tests/host/test_public_open_host_options.py`：required policy field 验证
   - `tests/runtime/test_config_loader.py`：strict policy parser
   - `tests/service/test_host_assembly.py` / `tests/service/test_host_admin.py`：assembly policy 传播

### 3.3 Adversarial 场景逐一验证

| 场景 | 验证方式 | 结果 |
|---|---|---|
| policy bool 拒绝 | 运行期断言 | ✅ `must be int` |
| policy zero 拒绝 | 运行期断言 | ✅ `must be positive` |
| policy negative 拒绝 | 运行期断言 | ✅ `must be positive` |
| cap=1 的 cap+1 拒绝 | 运行期断言 | ✅ `RESOURCE_EXHAUSTED, retryable=True` |
| cap=1 的 different-Session isolation | 运行期断言 | ✅ session-2 独立 |
| overflow 不释放 reservation | 运行期断言 | ✅ `is_released=False` |
| close 释放 reservation | 运行期断言 | ✅ `is_released=True` |
| idempotent close（caller + hub） | 运行期断言 | ✅ 无 double-free |
| idempotent release | 运行期断言 | ✅ `_released` flag |
| mark_run_terminal 拒绝 future publish | 运行期断言 | ✅ `_offer` 中 `terminal_run_ids` 拒绝 |
| hub close 清空全部 subscription + reservation | 运行期断言 | ✅ count=0 |
| pop_next_nowait in-flight 未释放保护 | 代码走读 | ✅ `RuntimeError` guard |
| `_offer()` `terminal_run_ids` 双检 | 代码走读 | ✅ 先 `terminal_run_ids` 再 capacity check |
| `_is_ready()` 仅看 mailbox/overflow/closed | 代码走读 | ✅ in-flight 不算 ready |
| `_refresh_readiness()` 双检 | 代码走读 | ✅ clear + set-if-ready 模式 |

### 3.4 Automation gates

| Gate | Command | Result |
|---|---|---|
| S1 focused tests | `pytest tests/host/test_public_contracts.py ... tests/service/test_host_admin.py -q` | **318 passed**, 3 warnings（第三方 edgar deprecation） |
| DS-F02 test | `pytest tests/host/test_transient_delta.py::test_single_pop_filters_prequeued_terminal_stale_item -q` | **1 passed** |
| pyright | `python -m pyright dayu/ tests/ utils/` | **0 errors, 0 warnings, 0 informations** |
| coverage | `pytest ... --cov=dayu.host.transient_delta --cov-report=term-missing --cov-fail-under=80 -q` | **92.09%** (278 stmts, 22 missed — 均为 defensive TypeError/ValueError/early-return edge paths) |
| whitespace | `git diff --check` | **exit 0** |
| stale scan | `rg -n '_TRANSIENT_WATCH_BUFFER_CAPACITY|...'` | **仅 `_ENTRYPOINT_LIVE_EVENT_BUFFER_CAPACITY`**（plan §7 item 8-9 明确冻结，S4 删除） |
| `watch_session_events` callers | `rg -n 'watch_session_events\(' dayu tests utils` | **全部 production/test/utils callers 使用 `await`** |
| Engine delivery contract | `rg -n 'TerminalPostCommit\|session_event_delivery' dayu/engine` | **空（无新契约）** |
| Runtime reverse dep | `rg -n 'from dayu\.\(engine\|host\|...\)' dayu/runtime` | **仅注释（无反向依赖）** |

---

## 4. New Findings

**无新增 material finding。**

经过 adversarial sweep 覆盖全部 S1 current changes 的 production、test、config、assembly 和 utils 路径，未发现：

- 未关闭的 correctness bug（DS-F02 已修复）
- reservation/retained/readiness/overflow/close accounting 漂移
- public contract 语义错误或 owner 错位
- 类型检查逃逸或 hidden fallback
- 资源泄漏路径
- plan scope violation（S1 未授权模块未修改）

### 4.1 新 observed-but-not-material 观察

以下为代码走读中注意到的细节，不构成 material finding：

1. **`_HostSessionEventIterator.__anext__` 的 `except BaseException` 捕获 `StopAsyncIteration`**：catch 后 close subscription 并 re-raise。Python 的 `async for` 在收到 `StopAsyncIteration` 后不调 `aclose()`，因此该 catch 确保正常 EOF 也释放 reservation。`aclose()` 幂等检查 `_closed`，无 double-free。语义正确，非 bug。

2. **`_watch_session_events.finally` 与 `_HostSessionEventIterator.__anext__.except` 的 double-close**：两个路径都可能触发 `subscription.close()`，但 `close()` 通过 `if self._closed: return` 实现幂等。无 functional impact。

3. **`_HostSessionEventIterator` 的 iterator 从 lazy 改为 eager 创建**：`__init__` 中立即创建 generator 而非 delayed in `__anext__()`。Python async generator 在创建时不执行，首次 `__anext__()` 才启动。语义等价，无 behavioral change。

---

## 5. Open Questions

1. **`_SESSION_WATCH_POLL_INTERVAL_SECONDS = 0.02` 硬编码**（复用原 review DS-F04 相关）：该常量在 accepted base 已存在，非 S1 新行为。Controller 已 `rejected-with-reason`。当前无直接性能数据表明需修改。本 re-review 维持：非 S1 scope，不做进一步动作。

2. **S1 期间 Service relay 256 与 Host mailbox 512 的交叉**（复用原 review open question 3）：Controller 已 `closed-by-accepted-slice-sequencing`。确认中间态无实际风险：Service relay drain task 使用 `await queue.put(...)` 施加背压，Host mailbox overflow 仍由 subscription owner 独立决定。本 re-review 维持：不构成 S1 issue。

---

## 6. Residual Risk

1. **S2 causal fence 对 S1 基础设施的依赖**（同原 review residual 1）：S1 reservation/mailbox/in-flight/overflow 状态机已完成单 opener 边界验证。S2 cross-opener 验证将在此基础上进行。若 S1 有未被发现的 off-by-one（当前无证据），S2 reconciliation 可能放大。风险等级：低（S1 测试覆盖了 cap−1/cap/cap+1、并发 attach、detach readmission、different-Session isolation）。

2. **Host close ordering 的完整验证**：S1 实现了 hub close 移到 producer cleanup 之后。S3 将在两者之间插入 coordinator in-flight drain/port close。当前 S1 测试覆盖了"CLOSING 时 wait_ready + 最终 close wakeup"路径。S3 需确保插入的 coordinator close 不改变 delivery close semantics。

3. **Config `512/4` 多处置复**（同原 review residual 5）：packaged default 与独立 test fixtures 的重复是 plan 要求的"无 hidden fallback"设计，不是 DRY 违规。Controller 已 `rejected-with-reason`。

---

## 7. Verdict

**PASS — no fix required.**

| 维度 | 结论 |
|---|---|
| DS-F02 closure | **已关闭**：single-pop owner boundary terminal fence 正确恢复，有 deterministic test 证明 |
| Stale items 不进入 in-flight | **已验证**：`continue` 跳过，不设 `_in_flight` |
| Retained accounting 无回归 | **已验证**：7 条操作路径逐一验证 |
| Readiness 无回归 | **已验证**：level-triggered，双检模式，publish/wait barrier tests |
| Overflow 无回归 | **已验证**：不释放 reservation，accepted prefix 保留，typed error |
| Close 无回归 | **已验证**：4 条 close 路径幂等，reservation release 正确 |
| 新增 material finding | **0** |
| S1 focused tests | **318 passed** |
| pyright | **0 errors, 0 warnings, 0 informations** |
| coverage | **92.09%**（>80% target） |
| stale scan | **only frozen S4 symbols** |
| source propagation | **全部 await, 无 bypass, 无 reverse dep** |

DS-F02 是可接受且已修复的唯一 correctness finding。本轮 adversarial sweep 未发现任何新的 material regression。Slice 1 已达到 gate 通过条件。

---

**审查人**: AgentDS（Slice 1 原 reviewer）
**审查时间**: 2026-07-21
**下一 gate**: Controller 收集 AgentMiMo 与 AgentDS 两路 re-review 后裁决 `accepted-commit`
**不含**: 生产代码修改、测试修改、Controller 总控修改或他人 artifact 修改
