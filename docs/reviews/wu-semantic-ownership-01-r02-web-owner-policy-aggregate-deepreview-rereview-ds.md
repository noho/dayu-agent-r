# WU-SEMANTIC-OWNERSHIP-01 / R02 Aggregate Final Re-Review (AgentDS)

## 1. Gate 身份、Scope 与执行树

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`；本文是同一 R02 aggregate deepreview 的 DS 路 final re-review，不是新 WU。
- accepted plan：`2d42ceb6`（`gateflow: accept superseding R02 web owner policy plan`）。
- accepted slices：S1=`c7b01d82`、S2=`d8d6e9d9`、S3=`7e679796`。
- 当前 control gate：`R02 aggregate deepreview final re-review`（`docs/host/issues-implementation-control.md:158`）。
- 执行 HEAD：`4240ee75`。
- 审查范围：
  - `2d42ceb6..7e679796` 的完整 production/config/utils/tests/README diff；
  - 当前未提交 production fix（`dayu/tools/web/web_playwright_backend.py` 7 行 launch 失败 local runtime cleanup）；
  - 当前未提交 test fix（`tests/tools/web/test_web_tools_provider.py` 约 1321 行新增 typed fake 与 11 个 direct owner test functions）；
  - 所有 aggregate deepreview / fix / controller validation / fix2 artifacts。
- 固定输出路径：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-ds.md`。

本 re-review 不修改 production/test/control/既有 artifacts，不 commit/push。唯一允许新增本文。最终下一入口仅 Controller adjudication。

## 2. 必读真源与审查方法

本轮完整读取：

1. 根 `AGENTS.md`（含最高约束、思考纪律、语义所有权与修复边界、LLM-facing 文本约束、架构硬约束、编码硬约束、测试与验证）；
2. accepted R02 plan `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`（完整 1057 行，含 §1-§15 全部 contract、allowlist、时序与 gate commands）；
3. 原 aggregate validation（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-validation.md`）；
4. 原 aggregate Controller validation（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-controller-validation.md`）；
5. 原 AgentMiMo aggregate deepreview（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-mimo.md`，findings=0）；
6. 原 AgentDS aggregate deepreview（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-ds.md`，findings=5）；
7. Controller adjudication（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-controller-adjudication.md`，接受 F01-F05 全部五项）；
8. AgentCodex fix（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix-codex.md`，59 changed_definitions issues=0）；
9. Controller fix validation（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix-controller-validation.md`，REQUIRES_FIX + R02-AGG-CTRL-F01）；
10. AgentCodex fix2（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix2-codex.md`，60 changed_definitions issues=0）；
11. Controller fix2 validation（`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix2-controller-validation.md`，PASS）；
12. `docs/host/issues-implementation-control.md` 当前 R02 gate 行（gate=R02 aggregate deepreview final re-review，next entry point 确认）。

审查方法：主 reviewer 沿真实代码路径逐行走读全部 production diff、全部 test diff、全部 fake class 与全部 test function；独立运行 focused owner tests、full aggregate matrix、pyright、adversarial keyword scans 与 retained-security scans。

## 3. R02-AGG-DS-F01..F05 与 R02-AGG-CTRL-F01 逐项闭合验证

### 3.1 R02-AGG-DS-F01 — `_get_playwright_browser` 双检锁浏览器单例零直接测试覆盖

**状态：已闭合。**

原 finding：24 行双检锁逻辑（外层 null check、锁获取+内层 null check、旧 browser teardown、Playwright import、sync_playwright 启动、channel-based launch options、anti-detection args、`chromium.launch`、全局状态赋值、异常处理）全部 0% 覆盖。

闭合证据：

- `test_get_playwright_browser_owner_creates_reuses_and_replaces_by_key`：直接调用真实 `_get_playwright_browser`，以 typed `_LifecyclePlaywrightBrowser`/`_LifecycleChromiumLauncher`/`_LifecyclePlaywrightInstance`/`_LifecyclePlaywrightStarter`/`_LifecycleSyncPlaywrightFactory` 替换外部 `playwright.sync_api.sync_playwright` collaborator；覆盖首次创建（`first is browsers[0]`）、同 key 复用（`reused is first`，channel 经 `_normalize_playwright_channel` 归一化去空格）、channel 变化 cleanup+recreate（`channel_changed is browsers[1]`，`browsers[0].close_calls == 1`，`instances[0].stop_calls == 1`）、headless 变化 cleanup+recreate（`headless_changed is browsers[2]`，`browsers[1].close_calls == 1`）；逐次断言 launch_kwargs 精确值（含 `--disable-blink-features=AutomationControlled`）与最终 global state。
- `test_get_playwright_browser_owner_cleans_local_runtime_without_publishing_failed_state`：两参数化 case（launch 失败 + stop 成功 / launch 失败 + stop 自身异常），均断言 `instance.stop_calls == 1`、owner 返回 `None`、`_PW_INSTANCE/_PW_BROWSER/_PW_BROWSER_KEY` 全为 `None`。

直接证据：focused tests `3 passed in 0.74s`（F01 三函数）；production `_get_playwright_browser` 覆盖从 0 行提升至包含全部关键路径。

### 3.2 R02-AGG-DS-F02 — `_normalize_url_for_http` 安全拒绝路径未覆盖

**状态：已闭合（按 Controller owner correction）。**

原 finding：`ValueError` 拒绝路径（scheme/netloc 缺失、hostname 为空）和 credential 剥离路径未覆盖。

闭合证据：

- `test_normalize_url_for_http_rejects_missing_transport_parts`：三参数 case（`"//example.com/report"` 缺 scheme、`"https:///report"` 缺 netloc、`"https://@/report"` netloc 存在但缺 hostname），均断言 `ValueError("无效 URL")`。
- `test_normalize_url_for_http_encodes_idna_and_userinfo_for_transport`：直接断言 Unicode username/password quoting、IDNA hostname encoding 与 path/query/fragment ASCII quoting 的精确结果字符串；normalizer 继续允许并编码 userinfo，不承担安全拒绝。
- `test_web_egress_policy_owner_rejects_userinfo_url`：直接调用 `WebEgressPolicy.authorize_http_target`，断言 `reason="userinfo is not allowed"` 与 `stage="tool_input"`；安全拒绝唯一归 `WebEgressPolicy`。

直接证据：没有在 normalizer、sender、orchestrator 或下游增加重复 userinfo blacklist/fallback。`git diff -- dayu/tools/web/web_tools.py` 零 production diff。

### 3.3 R02-AGG-DS-F03 — `_materialize_bounded_page_projection` text budget 强制执行路径未覆盖

**状态：已闭合。**

原 finding：DOM budget exceeded 路径有覆盖；text budget exceeded 路径从未触发。

闭合证据：

- `test_materialize_bounded_page_projection_owns_text_too_large_reason`：两参数化 case 分别覆盖 preflight `textExceeded=true`（DOM 界内但 bounded text 预检直接超限，`expected_content_calls=0`、`expected_evaluate_calls=1`）与 preflight 界内但实际全文本超限（`expected_content_calls=1`、`expected_evaluate_calls=2`）。两个 case 均直接断言 `_BrowserResourceBudgetExceeded.reason == _BROWSER_TEXT_TOO_LARGE_REASON`，没有用任意错误文本或下游映射替代。

直接证据：focused test `2 passed`（参数化后）；使用既有 `_BudgetProbePage` synthetic page（line 852），不新增 page fake。

### 3.4 R02-AGG-DS-F04 — `_route_handler_abort_resources` 2/3 分支未覆盖

**状态：已闭合。**

原 finding：resource-type-based abort（image/font/media）和 allowed-resource continue 未被测试。

闭合证据：

- `test_route_handler_owner_selects_resource_policy_or_continue_action`：五参数 case 覆盖 `image→abort`、`font→abort`、`media→abort`、`denied document URL→abort`、`allowed document URL→continue`。使用 `_RecordingPlaywrightRoute`/`_RecordingRouteRequest` typed fakes，只记录 route action（`self.actions.append(_ROUTE_ABORT_ACTION)` 或 `_ROUTE_CONTINUE_ACTION`）；policy 判断仍由真实 `WebEgressPolicy` owner 执行，fake 不重算 policy。

直接证据：原 `FakeRoute`/`FakeRequest` 内联类已替换为 typed module-level `_RecordingPlaywrightRoute`/`_RecordingRouteRequest`；所有五个 case 的 `route.actions` 精确断言为 `[expected_action]`。

### 3.5 R02-AGG-DS-F05 — 取消杀死开关与进程清理路径未覆盖

**状态：已闭合。**

原 finding：取消杀死开关、worker 异常退出路径、`_close_playwright_browser` cleanup 实现全部未覆盖。

闭合证据：

- `test_run_playwright_worker_process_cancellation_terminates_and_cleans_queue`：fake token 预先取消 → 断言 `CancelledError("controller cancellation")`、`terminator.processes == [process]`、`result_queue.close_calls == 1`、`result_queue.join_thread_calls == 1`。
- `test_run_playwright_worker_process_no_result_exit_cleans_queue`：fake process 启动后已退出、queue 无 payload → scripted clock 跨过 result-drain grace → 断言 `RuntimeError("playwright worker exited without result")`、`process.join_timeouts == [0]`、finally queue cleanup。
- `test_run_playwright_worker_process_timeout_terminates_and_cleans_queue`：fake process 保持 alive、timeout=0 → scripted clock 立即到 deadline → 断言 `TimeoutError("playwright worker timeout")`、`terminator.processes == [process]`、finally queue cleanup。
- `test_close_playwright_browser_clears_singletons_after_success_or_error`：三参数 case（close/stop 均成功、browser close 异常、runtime stop 异常）→ 每个 case 断言 close/stop 均被调用一次且 `_PW_BROWSER/_PW_INSTANCE/_PW_BROWSER_KEY` 全为 `None`。

直接证据：focused tests `6 passed`（F05 四函数参数化后）；所有 unit cases 使用内存 fake multiprocessing context/process/queue/token 和 scripted monotonic clock；`rg 'time\.sleep|multiprocessing\.Process\(|subprocess\.Popen|os\.fork'` 在 test added lines 中零命中。

### 3.6 R02-AGG-CTRL-F01 — launch 失败局部 runtime 未回收

**状态：已闭合。**

Controller finding：`sync_playwright().start()` 成功但 `chromium.launch()` 失败时，局部 `pw` 未发布到全局，`_close_playwright_browser()` 无法回收，异常分支未调用 `pw.stop()`。

闭合证据：

**Production fix**（`dayu/tools/web/web_playwright_backend.py:1056-1075`，7 行新增）：

```python
pw: _PlaywrightInstanceProtocol | None = None          # L1056: typed 局部声明
try:
    ...
    pw = cast(..., sync_playwright().start())           # L1060: 只赋值局部
    browser = pw.chromium.launch(...)                   # L1065: launch
    _PW_INSTANCE = pw                                   # L1066: 成功后才发布
    ...
except Exception as exc:
    if pw is not None:                                  # L1070: 仅已启动时回收
        try:
            pw.stop()                                   # L1073: best-effort stop
        except Exception:
            pass                                        # L1075: stop 异常不遮蔽
    Log.warning(...)
    return None                                         # L1077: 保持原返回 contract
```

时序验证：`start < launch < 三项 global assignment`；异常 handler 内没有任何 `_PW_*` publication；`stop()` 异常被局部吞掉，原 launch 失败 warning 与 `return None` 不变。没有为 cleanup 提前发布 `_PW_INSTANCE`，没有新增 `hasattr`/`getattr`、compatibility branch、downstream fallback 或 storage-state lifecycle。

**Test fix**（`test_get_playwright_browser_owner_cleans_local_runtime_without_publishing_failed_state`，两参数化 case）：

- Case 1（`runtime_stop_error=None`）：launch 失败 → stop 成功 → `stop_calls == 1`、`result is None`、三项 global 为 `None`。
- Case 2（`runtime_stop_error=RuntimeError(...)`）：launch 失败 → stop 抛异常 → `stop_calls == 1`、`result is None`、三项 global 为 `None`。证明 stop 异常不遮蔽返回 contract。

直接证据：focused tests `2 passed in 0.60s`；production source scan 对 `hasattr/getattr`、Issue 178、storage lifecycle、compatibility/fallback 零命中。

## 4. Retained Web 安全逐项复核

### 4.1 DNS/peer/redirect 安全：PASS

- DNS resolution → dangerous/unspecified/multicast/private/loopback/link-local 拒绝：`web_egress_policy.py` 零 production diff 自 S3 accepted commit。
- Mixed DNS fail closed：同一 egress owner，零 diff。
- Redirect 每跳重新授权：`web_fetch_orchestrator.py` 零 S2 后 diff；每跳 `authorize_http_target(egress_policy, url=next_url, reason="http_redirect")` 保留。
- Peer proof mismatch fail closed：`web_http_session.py:_PinnedHTTPConnection._new_conn()` 零 diff。
- Proxy+proof incompatibility typed fail-closed：`web_http_session.py:726-727` 零 diff。
- Fixed provider endpoint DNS/egress/peer 防御：`web_search_providers.py` 零 diff。

### 4.2 Proxy/budgets/route/challenge/redaction/containment：PASS

- Proxy deny → `trust_env=false`、`proxies={}`：`web_http_session.py:685,720-721` 零 diff。
- Browser worker proxy env cleanup → 8 个标准 proxy 环境变量删除：`web_playwright_backend.py` 零 diff。
- HTTP wire/decoded、browser warmup/DOM/text、diagnostic error/events budgets：各自 owner 文件零 diff。
- Browser route/navigation 每 URL egress policy：`_route_handler_abort_resources` 消费同一 `WebEgressPolicy` 实例。
- Challenge detection：`web_challenge_detection.py` 零 diff。
- Redaction（header/cookie/URL/query/proxy credential）：`web_diagnostics.py` 零 diff。
- Containment/symlink：既有 production resolver 零 diff。

### 4.3 安全结论

所有 retained security 路径在 `2d42ceb6..7e679796` 与当前未提交 diff 中均未被削弱。未提交 production diff（7 行）仅增加 browser singleton launch 失败时的 local runtime best-effort cleanup，不触及任何安全决策路径。

## 5. Topic 2 裁决、Issue 178/R03/统一 authorization 偷带扫描

### 5.1 扫描结果

| 扫描目标 | 范围 | 结果 |
|---|---|---|
| Topic 2 / overdesign controller / no-code | production + test added lines | 零命中 |
| Issue 178 / R03 | production + test added lines | 零命中 |
| 统一 authorization / policy DSL / capability token | production + test added lines | 零命中 |
| proxy credential schema / storage state refresh/retention | production + test added lines | 零命中 |
| credential lifecycle（`_StorageStateLifecycle`、`output_enabled`、`ttl_seconds`、`published`、`reconcile`、`storage_state_out`） | production + test added lines | 零命中 |
| `hasattr` / `getattr` | test added lines | 零命中 |
| `Any` / `object` 类型 | test added lines | 零命中 |

### 5.2 结论

零偷带。Topic 2 no-code decision 保持；Issue 178 credential lifecycle 完全未实现；R03 LLM-facing projection 未启动；统一 authorization 未实施。

## 6. 约 1200 行新增 Typed Fake 对抗审查

### 6.1 Fake class 清单与职责

| Fake class | 行数（估算） | 唯一职责 | 是否复制 production policy |
|---|---|---|---|
| `_LifecyclePlaywrightBrowser` | ~50 | 记录 `close()` 调用，可注入关闭异常；`new_context()` 防御性拒绝 | 否 — 纯 recorder |
| `_LifecycleChromiumLauncher` | ~45 | 记录 `launch(**kwargs)` 参数，可注入 launch 异常 | 否 — 纯 recorder |
| `_LifecyclePlaywrightInstance` | ~40 | 记录 `stop()` 调用，可注入停止异常 | 否 — 纯 recorder |
| `_LifecyclePlaywrightStarter` | ~30 | 记录 `start()` 调用，返回配置的 runtime | 否 — 纯 factory |
| `_LifecycleSyncPlaywrightFactory` | ~40 | 按序返回 typed starter；防御性拒绝超用 | 否 — 纯 sequencer |
| `_RecordingRouteRequest` | ~5 | frozen dataclass：提供 `resource_type` 和 `url` | 否 — 纯 input |
| `_RecordingPlaywrightRoute` | ~40 | 记录 `abort()`/`continue_()` 动作，暴露 typed `request` | 否 — 纯 recorder |
| `_FakePlaywrightResultQueue` | ~90 | 模拟 `put/get/get_nowait/close/join_thread`；预置 payload 序列 | 否 — 内存 queue 模拟 |
| `_FakePlaywrightProcess` | ~55 | 模拟 `start/is_alive/join`；记录 join timeouts | 否 — 纯 state machine 模拟 |
| `_FakePlaywrightMultiprocessingContext` | ~70 | 提供固定 `Queue/Process`；记录 target/args | 否 — 纯 factory |
| `_FakePlaywrightContextFactory` | ~30 | 记录 `get_context(method)` 调用；断言 `spawn` | 否 — 纯 recorder |
| `_RecordingPlaywrightProcessTerminator` | ~30 | 记录被 terminate 的 process；调用 `mark_terminated()` | 否 — 纯 recorder |
| `_ScriptedMonotonicClock` | ~30 | 按序返回预置单调时间值 | 否 — 纯 sequencer |
| `_playwright_worker_process_kwargs` | ~20 | 构造 process owner 测试共用的 typed worker kwargs | 否 — helper factory |

### 6.2 是否复制 production policy/state machine

**结论：否。** 14 个新增 typed fake class/helper 中：

- 10 个是纯 recorder：只记录方法被调用的次数和参数，不包含任何生产决策逻辑。
- 3 个是纯 factory/sequencer：按配置返回预置对象，不包含生产决策逻辑。
- 1 个（`_FakePlaywrightResultQueue`）模拟内存队列行为（FIFO + Empty on empty），这是数据结构语义而非生产 policy。

没有 fake 重新实现 `WebEgressPolicy`、`WebHttpTransportPolicy`、budget enforcement、challenge detection、redaction 或任何其他生产安全/业务逻辑。

### 6.3 是否过度耦合

**结论：否。**

- `_FakePlaywrightMultiprocessingContext.Process()` 的 target/args 类型注解精确匹配 `_run_playwright_worker_process` 中的 `_playwright_process_entry` 签名。这是 typed fake 与 typed production 之间的必要协议耦合，不是过度耦合。若 production 签名变化，pyright 会在 fake 处报错——这正是类型安全的收益。
- `_FakePlaywrightResultQueue` 实现 `_ResultQueueProtocol` 的子集（`put/get/get_nowait/close/join_thread`），与 production 消费的 protocol 方法精确匹配。Protocol 变化 → fake 编译失败 → 测试必须同步。这是 Protocol-based design 的预期行为。
- `_RecordingPlaywrightRoute` 实现 `abort()`/`continue_()` 并暴露 `request: _RouteRequestProtocol`，与 production `_route_handler_abort_resources` 消费的 `_RouteProtocol` 匹配。
- 所有 fake 只依赖 production Protocol/type，不依赖 production 具体实现类。替换 Playwright backend 为另一个 browser engine 时，这些 fake 无需修改（只要 Protocol 不变）。

### 6.4 是否锁定偶然顺序

**结论：否。**

- `test_get_playwright_browser_owner_creates_reuses_and_replaces_by_key` 断言 `launch_calls[0] == {"headless": True, "channel": "chrome", "args": [...]}`。这些 kwargs 是 browser lifecycle owner 的 **contract**，不是偶然顺序。若 production 改变传递给 `chromium.launch()` 的参数，测试必须感知。
- `test_close_playwright_browser_clears_singletons_after_success_or_error` 断言 `browser.close_calls == 1` 和 `instance.stop_calls == 1`，但**不断言 close/stop 的调用顺序**。顺序是 production `_close_playwright_browser` 的实现细节（先 close browser 再 stop runtime），测试未将其固化为 contract。
- `_ScriptedMonotonicClock` 按预置序列返回值。每个测试 case 的时钟序列独立配置，不共享可变状态。序列值与 production timeout/fencing 逻辑精确对应，不依赖系统时钟偶然值。

### 6.5 是否掩盖真实缺陷

**结论：否。**

- `_FakePlaywrightResultQueue.get()` 在 `payloads` 为空时立即 `raise Empty`，而非等待真实 timeout。但 production 的 `_poll_playwright_result_queue` 显式 `except Empty: return None`，因此 fake 的立即 Empty 不会掩盖 behavior——它正确地触发了 production 的 Empty→None 路径。如果未来有人移除 `_poll_playwright_result_queue` 的 `except Empty` 守卫而直接调用 `queue.get()`，测试 fake 不会暴露该缺陷——但那是未来代码的缺陷，不是当前 fake 的问题。
- `_FakePlaywrightProcess` 不启动真实子进程。这是 unit test 的预期行为——process fencing 的 OS 级行为由 Python stdlib 保证，unit test 只需验证 owner 在正确时机调用了正确方法。
- `_RecordingPlaywrightProcessTerminator` 不调用 `os.kill()`。同理——`terminate()`/`kill()` 的 OS 行为是 Python stdlib contract。
- `_ScriptedMonotonicClock` 在序列耗尽后返回最后值。这是防御性设计——若 production 进入意外无限循环，test 会因 `pytest.raises` 未触发而失败（而非时钟耗尽后静默通过）。

### 6.7 是否违反严格类型/docstring/测试 owner 边界

**结论：否。**

- 14 个新增 class、1 个 helper function、11 个 test function 全部有完整中文 docstring（`Args`/`Returns`/`Raises`）。
- `_FakePlaywrightMultiprocessingContext.Process()` 的 target/args 有完整 typed callable signature，无 `Any`/`object`/裸容器。
- Playwright Protocol 的 `launch(**kwargs: JsonValue)` / `new_context(**kwargs: JsonValue)` 只复现既有第三方 Protocol 形状，不是 Dayu 层间类型绕过。
- 测试断言全部针对 owner-level contract（返回值、全局状态、fake 记录的方法调用），没有测试私有实现细节或偶然顺序。
- 新增 `import playwright.sync_api as playwright_sync_api`（line 35）仅用于 `monkeypatch.setattr(playwright_sync_api, "sync_playwright", factory)` 的精确 target，不引入运行时 Playwright 依赖。

### 6.6 对抗审查结论

新增 typed fake 不复制 production policy/state machine，不过度耦合，不锁定偶然顺序，不掩盖真实缺陷，不违反严格类型/docstring/测试 owner 边界。

## 7. `_get_playwright_browser` Launch 失败 Local Runtime Cleanup 并发/异常/Publication 语义复核

### 7.1 并发语义

`_get_playwright_browser` 使用 `threading.Lock`（`_PW_LOCK`）保护 critical section。Production fix 在锁内执行：

1. 检查是否需要 teardown 旧 singleton（key 变化）；
2. 声明 typed 局部 `pw: _PlaywrightInstanceProtocol | None = None`；
3. `sync_playwright().start()` → 只写局部 `pw`；
4. `pw.chromium.launch(...)` → 成功后写三项 global；
5. 异常 handler：仅当 `pw is not None` 时 best-effort `pw.stop()`；
6. 返回 `_PW_BROWSER` 或 `None`。

**并发正确性**：
- 局部 `pw` 在锁内声明，其他线程不可见。
- 三项 global（`_PW_INSTANCE`/`_PW_BROWSER`/`_PW_BROWSER_KEY`）只在 launch 成功后写入，保持原子发布语义。
- `pw.stop()` 在锁内执行。若 `stop()` 阻塞，锁被持有——这是既有设计约束（`_close_playwright_browser` 同样在可能被锁保护或 atexit 的上下文中调用 `close()`/`stop()`），fix 未恶化该约束。
- `pw.stop()` 异常被局部吞掉，不传播到锁外。

### 7.2 异常语义

| 场景 | `start()` 结果 | `launch()` 结果 | `pw.stop()` 行为 | 返回值 | globals |
|---|---|---|---|---|---|
| 全部成功 | 成功 | 成功 | 不调用 | `browser` | 已发布 |
| launch 失败 + stop 成功 | 成功 | 异常 | 调用一次，成功 | `None` | 全 `None` |
| launch 失败 + stop 异常 | 成功 | 异常 | 调用一次，抛异常被吞 | `None` | 全 `None` |
| start 失败 | 异常（`pw=None`） | 不到达 | 不调用（`pw is None`） | `None` | 全 `None`（未变） |

所有异常路径保持 `return None` contract，三项 global 不会处于半发布状态。

### 7.3 Publication 语义

- 成功路径：`_PW_INSTANCE`、`_PW_BROWSER`、`_PW_BROWSER_KEY` 同时赋值，atomic 发布。
- 失败路径：无一被写入；`_close_playwright_browser()` 不可见局部 `pw`（因为它从未进入 global），因此 cleanup 责任完全由 `_get_playwright_browser` 的异常 handler 承担——这正是 fix 的语义。
- `stop()` 自身异常被限制在 handler 内，不改变原 warning 日志和返回 `None` 行为。

### 7.4 结论

Launch 失败 local runtime cleanup 的并发（锁内局部变量 + atomic global publication）、异常（三场景覆盖）和 publication（成功发布/失败不发布）语义均正确。

## 8. 只读验证结果

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

| gate | command | result |
|---|---|---|
| focused owner tests（11 qualified functions） | `pytest ... -k 'test_get_playwright_browser_owner or test_materialize_bounded_page_projection_owns_text or test_route_handler_owner_selects or test_run_playwright_worker_process or test_close_playwright_browser_clears or test_normalize_url_for_http or test_web_egress_policy_owner_rejects'` | `21 passed, 174 deselected in 0.66s` |
| full aggregate matrix | `pytest tests/tools/web/test_web_tools_provider.py tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py tests/runtime/test_config_loader.py -q` | `330 passed, 1 skipped, 3 warnings in 13.14s` |
| full pyright | `python -m pyright` | `0 errors, 0 warnings, 0 informations` |
| Issue 178/R03/统一auth 偷带扫描 | `rg` on production+test added lines | 零命中 |
| Topic 2 no-code 偷带扫描 | `rg` on production+test added lines | 零命中 |
| `hasattr`/`getattr`/`Any`/`object` 扫描 | `rg` on test added lines | 零命中 |
| `time.sleep`/真实子进程扫描 | `rg` on test added lines | 零命中 |
| production zero-diff（非 authorized paths） | `git diff --exit-code -- dayu/tools/web/web_egress_policy.py dayu/tools/web/web_http_session.py ...` | 仅 `web_playwright_backend.py` 有 diff（7 行 authorized） |

## 9. Findings

未发现实质性问题。

本 re-review 对 R02 aggregate（`2d42ceb6..7e679796` accepted diff + 当前未提交 production 7 行 fix + 当前未提交 test ~1321 行 fix）进行了完整对抗审查：

- **R02-AGG-DS-F01..F05**：五项原 DS deepreview finding 全部闭合，每项有独立 direct owner test 与 production/test 双重证据。
- **R02-AGG-CTRL-F01**：Controller 发现的 launch 失败 local runtime 未回收已闭合，production fix（7 行）保持在 browser lifecycle owner 边界，test fix（2 参数化 case）验证 stop 成功与 stop 异常两条路径。
- **Retained Web 安全**：DNS/peer/redirect/proxy/budgets/route/challenge/redaction/containment 全部保留，零安全路径被削弱。
- **Topic 2 裁决**：no-code decision 保持，零代码偷带。
- **Issue 178/R03/统一 authorization**：零 production/test added lines 命中。
- **约 1321 行新增 typed test fake**：14 个 class/helper、11 个 test function 均不复制 production policy/state machine、不过度耦合、不锁定偶然顺序、不掩盖真实缺陷、不违反严格类型/docstring/测试 owner 边界。
- **`_get_playwright_browser` launch 失败 local runtime cleanup**：并发（锁内局部变量 + atomic global publication）、异常（三场景覆盖）和 publication 语义均正确。
- **只读验证**：21 focused owner tests passed、330 aggregate tests passed、pyright 0 errors、全部 adversarial 扫描零命中。

## 10. Open Questions

无。

## 11. Residual Risk

| residual | classification | owner / destination | non-blocking basis |
|---|---|---|---|
| `_get_playwright_browser` 双检锁的 OS 级线程安全 | stdlib guarantee | Python `threading.Lock` | unit test 不验证 OS 调度行为，这是合理的 test boundary |
| `_FakePlaywrightProcess` 不启动真实子进程 | test boundary | process fencing unit tests | `terminate()`/`kill()` 的 OS 行为是 Python stdlib contract；真实子进程由独立 real Playwright smoke 验证 |
| `abort_resource_types` 是 `_route_handler_abort_resources` 的局部变量 | code organization | `web_playwright_backend.py` | 若需要跨测试引用，可提升为模块级常量；当前 test 参数化覆盖已知类型，新增类型会被 route handler 行为测试感知（参数化 case 会失败） |
| `_PW_LOCK` 在 `pw.stop()` 期间持有 | 既有设计约束 | `_get_playwright_browser` | fix 未恶化该约束；若 `stop()` 可能长时间阻塞，应评估异步 close 或 lock 释放策略——这是既有 concern，不属于本次 fix |

## 12. Final Verdict

**PASS — findings=0。R02-AGG-DS-F01..F05 与 R02-AGG-CTRL-F01 全部闭合；retained Web 安全零削弱；Topic 2 / Issue 178 / R03 / 统一 authorization 零偷带；约 1321 行新增 typed test fake 不复制 production policy、不过度耦合、不掩盖缺陷；`_get_playwright_browser` launch 失败 local runtime cleanup 并发/异常/publication 语义正确。**

下一入口仅为 Controller adjudication。

---

**Review 执行信息**：
- 主 reviewer：AgentDS
- 审查方法：主 reviewer 沿真实代码路径逐行走读全部 production diff、全部 test diff、全部 fake class 与全部 test function；独立运行 focused owner tests、full aggregate matrix、pyright、adversarial keyword scans 与 retained-security scans
- 生成时间：2026-07-15 05:41:54 UTC+8
