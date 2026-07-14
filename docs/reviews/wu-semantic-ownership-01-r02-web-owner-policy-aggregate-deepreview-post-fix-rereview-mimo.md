# R02 Aggregate Post-Fix Final Re-Review — AgentMiMo

> Review timestamp: 20260715-060320

## Scope

- Mode: aggregate post-fix final re-review（同一 umbrella `WU-SEMANTIC-OWNERSHIP-01`，不是新 WU）
- Branch: `phaseflow/host-issues-control`
- Base: accepted S3 commit `7e679796` 到当前 working tree（含未提交 production/test fix）
- Output file: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-post-fix-rereview-mimo.md`
- Included scope: `2d42ceb6..7e679796` 完整 production diff + 当前未提交 production fix（`web_playwright_backend.py` 13 行新增：stage 常量 + launch 失败 local runtime cleanup + cleanup diagnostic）+ 当前未提交 test fix（`test_web_tools_provider.py` ~1293 行新增 typed fake + owner tests + lifecycle test contract 收窄）+ 全部 aggregate deepreview/fix/controller validation/review artifacts
- Excluded scope: `dayu/render/`、`utils/` 非 Web 脚本、binary/vendor/build artifacts
- Parallel review coverage: 3 parallel agents 覆盖 (1) production `_get_playwright_browser` cleanup 代码 race/exception/lock 分析, (2) 13 typed fake class 对抗审查, (3) retained security source/propagation/signature 扫描

## 必读真源与审查方法

本轮完整读取：

1. 根 `AGENTS.md`（含最高约束、思考纪律、语义所有权与修复边界、LLM-facing 文本约束、架构硬约束、编码硬约束、测试与验证）
2. `docs/host/issues-implementation-control.md` 当前 R02 gate 行（line 158: gate=R02 aggregate deepreview post-fix final re-review）
3. 两份上一轮 final re-review：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-mimo.md` 与 `rereview-ds.md`
4. Controller adjudication：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-controller-adjudication.md`
5. AgentCodex rereview-fix artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-fix-codex.md`
6. Controller fix validation：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-fix-controller-validation.md`
7. Production diff：`git diff 7e679796 -- dayu/tools/web/web_playwright_backend.py`
8. Test diff：`git diff 7e679796 -- tests/tools/web/test_web_tools_provider.py`

审查方法：主 reviewer 沿真实代码路径逐行走读 production fix（13 行）、test fix（~1293 行新增 + 53 行删除）、全部 fake class 定义、全部 owner test function 断言；独立运行 focused owner tests、full aggregate matrix、pyright、cleanup diagnostic 内容验证、lifecycle test contract 验证、adversarial keyword scans 与 retained-security scans。

## 逐项 Finding 闭合确认

### R02-AGG-DS-F01 — browser singleton lifecycle 直接测试覆盖：PASS

原 finding：`_get_playwright_browser` 24 行双检锁逻辑零覆盖。

闭合证据（代码行号直接引用）：
- `test_get_playwright_browser_owner_creates_reuses_and_replaces_by_key`（line 6516-6579）：覆盖首次创建、同 key 复用、channel 变化 cleanup+recreate、headless 变化 cleanup+recreate；断言 `(headless, channel)` 精确值与最终 global state。
- `test_get_playwright_browser_owner_cleans_local_runtime_without_publishing_failed_state`（line 6597-6667）：2 参数化 case 覆盖 stop 成功 / stop 异常，均断言 `stop_calls == 1`、返回 `None`、三项 global 为 `None`。

独立验证：`pytest -k 'test_get_playwright_browser_owner' -q` → `2 passed`。

### R02-AGG-DS-F02 — URL normalizer + userinfo 安全拒绝：PASS

闭合证据：
- `test_normalize_url_for_http_rejects_missing_transport_parts`（line 220）：3 参数 case 断言 `ValueError("无效 URL")`。
- `test_normalize_url_for_http_encodes_idna_anduserinfo_for_transport`（line 237）：精确字符串断言 IDNA/userinfo/path/query encoding。
- `test_web_egress_policy_owner_rejects_userinfo_url`（line 261）：直接断言 `WebEgressPolicy.authorize_http_target` 拒绝 userinfo，`reason="userinfo is not allowed"`。

安全拒绝唯一归 `WebEgressPolicy`，normalizer 只做 transport encoding。

### R02-AGG-DS-F03 — Browser text budget 强制执行：PASS

闭合证据：`test_materialize_bounded_page_projection_owns_text_too_large_reason`（line 6716）：2 参数化 case 分别覆盖 preflight textExceeded 和 actual text exceeded，均直接断言 `_BrowserResourceBudgetExceeded.reason == _BROWSER_TEXT_TOO_LARGE_REASON`。

### R02-AGG-DS-F04 — Browser route handler 分支覆盖：PASS

闭合证据：`test_route_handler_owner_selects_resource_policy_or_continue_action`（line 8283）：5 参数 case 覆盖 image/font/media→abort、denied document→abort、allowed document→continue。`_RecordingPlaywrightRoute` 只记录 action，policy 决策由真实 `WebEgressPolicy` 执行。

### R02-AGG-DS-F05 — Worker process fencing + cleanup：PASS

闭合证据：
- `test_run_playwright_worker_process_cancellation_terminates_and_cleans_queue`（line 8901）
- `test_run_playwright_worker_process_no_result_exit_cleans_queue`（line 8958）
- `test_run_playwright_worker_process_timeout_terminates_and_cleans_queue`（line 9012）
- `test_close_playwright_browser_clears_singletons_after_success_or_error`（line 9073）：3 参数 case 覆盖两成功、browser close 异常、runtime stop 异常。

独立验证：6 参数化 case 全部 passed。

### R02-AGG-CTRL-F01 — launch 失败 local runtime cleanup：PASS

Production fix（`web_playwright_backend.py:1057-1081`，13 行新增）：

```python
_PW_LAUNCH_FAILURE_RUNTIME_STOP_STAGE: Final = "browser_launch_failure_runtime_stop"  # line 416
...
pw: _PlaywrightInstanceProtocol | None = None          # line 1057: typed 局部声明
try:
    pw = cast(..., sync_playwright().start())           # line 1061: 只赋值局部
    browser = pw.chromium.launch(...)                   # line 1066: launch
    _PW_INSTANCE = pw                                   # line 1067: 成功后才发布
except Exception as exc:
    if pw is not None:                                  # line 1071: 仅已启动时回收
        try:
            pw.stop()                                   # line 1074: best-effort stop
        except Exception as stop_exc:
            Log.debug(                                  # line 1076: 脱敏诊断
                "Playwright runtime cleanup failed "
                f"stage={_PW_LAUNCH_FAILURE_RUNTIME_STOP_STAGE} "
                f"exception_type={type(stop_exc).__name__}",
                module=MODULE,
            )
    Log.warning(f"Playwright 浏览器初始化失败，回退不可用: {exc}", module=MODULE)
    return None
```

时序验证：`start < launch < 三项 global assignment`；异常 handler 内无 `_PW_*` publication；`stop()` 异常被脱敏记录后不遮蔽原 launch failure。

Test fix（`test_get_playwright_browser_owner_cleans_local_runtime_without_publishing_failed_state`，line 6597-6667）：2 参数化 case 验证 stop 成功（cleanup-failure debug=0）和 stop 异常（cleanup-failure debug=1，精确 stage + `exception_type=RuntimeError`），且整个 `caplog.text` 零敏感哨兵。

独立运行时验证 cleanup diagnostic 实际输出：`'[ENGINE.WEB_PLAYWRIGHT] Playwright runtime cleanup failed stage=browser_launch_failure_runtime_stop exception_type=RuntimeError'` — 无 URL、无 credential、无 storage path、无异常正文。

## R02-AGG-RV-F01/F03 闭合确认

### R02-AGG-RV-F01 — cleanup diagnostic 脱敏：PASS

Controller accepted 要求：stop 异常时记录 debug 诊断，只含稳定 stage 和异常类型，不含异常正文、URL、headers、credential 或 storage path。

实现证据：
- `_PW_LAUNCH_FAILURE_RUNTIME_STOP_STAGE` 是模块级 `Final` 常量（line 416），只读不写。
- `Log.debug` 只使用 `type(stop_exc).__name__`，不调用 `str(stop_exc)` 或 `repr(stop_exc)`（grep 确认 production 零命中）。
- 测试用含 URL/userinfo/password/query token/Authorization/credential/storage path 的异常正文作为哨兵；断言整个 `caplog.text` 零哨兵命中（line 6660-6667）。

### R02-AGG-RV-F03 — lifecycle test 不锁定 stealth tuning：PASS

Controller accepted 要求：保留 channel/headless 断言，不再把 `args` 内容或 stealth flag 固化为 lifecycle contract。

实现证据：
- lifecycle test（line 6564-6574）断言 `(headless, channel)` 精确值为 `(True, "chrome")`、`(True, "chromium")`、`(False, "chromium")`。
- 不读取或断言 `launch_calls[0]["args"]`、`"args"` key 或 `"--disable-blink-features=AutomationControlled"`（grep 确认 test 中零 `AutomationControlled` 命中）。
- Production `launch_kwargs["args"] = ["--disable-blink-features=AutomationControlled"]` 零修改（line 1065）。

### R02-AGG-RV-F02/F04 — rejected，未实现：PASS

- F02（docstring 未反映 cleanup 不变量）：Controller rejected，AGENTS.md 函数要求已满足，局部 cleanup 不变量由行内注释（line 1072）表达。未修改 docstring。
- F04（test fake 类级 docstring 缺 Args/Returns/Raises）：Controller rejected，AGENTS.md 类要求是中文概览 docstring。未修改任何 class-level docstring。

## Retained Web 安全复核

### DNS/peer/redirect/proxy/budgets/route/challenge/redaction/containment：全部 PASS

| 维度 | 文件 | S3 后 diff | 结论 |
|---|---|---|---|
| DNS dangerous/unspecified/multicast/private 拒绝 | `web_egress_policy.py` | 零 diff | PASS |
| Mixed DNS fail closed | `web_egress_policy.py` | 零 diff | PASS |
| Redirect 每跳重新授权 | `web_fetch_orchestrator.py` | 零 diff | PASS |
| Peer proof mismatch fail closed | `web_http_session.py` | 零 diff | PASS |
| Proxy+proof incompatibility | `web_http_session.py` | 零 diff | PASS |
| Proxy denied → empty proxies | `web_http_session.py` | 零 diff | PASS |
| Browser proxy env cleanup | `web_playwright_backend.py` | 零 diff | PASS |
| HTTP/browser budgets exact/+1 | 各 owner 文件 | 零 diff | PASS |
| Route handler per-URL egress | `web_playwright_backend.py` | 仅 cleanup fix，不触及 egress | PASS |
| Challenge detection | `web_challenge_detection.py` | 零 diff | PASS |
| Redaction header/cookie/URL/error | `web_diagnostics.py` | 零 diff | PASS |
| Containment/symlink | 既有 resolver | 零 diff | PASS |
| Diagnostics v2/revision 2 | `web_diagnostics.py` | 零 diff | PASS |
| Old contract zero-residual | 全 production | 零命中 | PASS |

Production 未提交 diff（13 行）仅增加 launch 失败时 local runtime best-effort cleanup + 脱敏 debug diagnostic，不触及任何安全决策路径。

## Topic 2 裁决、Issue 178/R03/统一 authorization 零偷带扫描

| 扫描目标 | 范围 | 结果 |
|---|---|---|
| Topic 2 / no-code decision | production + test added lines | 零命中 |
| Issue 178 / credential lifecycle | production + test added lines | 零命中 |
| R03 / LLM-facing projection | production + test added lines | 零命中 |
| 统一 authorization / policy DSL / capability token | production + test added lines | 零命中 |
| `hasattr` / `getattr` | production + test added lines | 零命中 |
| `Any` / `object` 类型 | production + test added lines | 零命中 |
| `str(stop_exc)` / `repr(stop_exc)` | production | 零命中 |

结论：零偷带。

## Typed Fake 对抗审查

### 13 typed fake class + 1 helper 重审

| Fake class | 职责 | 是否复制 production policy |
|---|---|---|
| `_LifecyclePlaywrightBrowser` | 记录 close 调用，可注入异常 | 否 — 纯 recorder |
| `_LifecycleChromiumLauncher` | 记录 launch 参数，可注入异常 | 否 — 纯 recorder |
| `_LifecyclePlaywrightInstance` | 记录 stop 调用，可注入异常 | 否 — 纯 recorder |
| `_LifecyclePlaywrightStarter` | 记录 start 调用 | 否 — 纯 factory |
| `_LifecycleSyncPlaywrightFactory` | 按序返回 starter | 否 — 纯 sequencer |
| `_RecordingRouteRequest` | frozen dataclass input | 否 — 纯 input |
| `_RecordingPlaywrightRoute` | 记录 abort/continue 动作 | 否 — 纯 recorder |
| `_FakePlaywrightResultQueue` | 模拟内存队列 FIFO | 否 — 数据结构语义 |
| `_FakePlaywrightProcess` | 模拟 process 生命周期 | 否 — 纯 state machine 模拟 |
| `_FakePlaywrightMultiprocessingContext` | 提供固定 Queue/Process | 否 — 纯 factory |
| `_FakePlaywrightContextFactory` | 记录 get_context 调用 | 否 — 纯 recorder |
| `_RecordingPlaywrightProcessTerminator` | 记录 terminate 进程 | 否 — 纯 recorder |
| `_ScriptedMonotonicClock` | 按序返回单调时间 | 否 — 纯 sequencer |
| `_playwright_worker_process_kwargs` | 构造 worker 测试 kwargs | 否 — helper factory |

**结论**：14 个 class/helper 均为纯 recorder/factory/sequencer/input，不包含任何生产决策逻辑。没有 fake 重新实现 `WebEgressPolicy`、budget enforcement、challenge detection、redaction 或任何其他安全/业务逻辑。

**过度耦合**：`_FakePlaywrightMultiprocessingContext.Process()` 的 target/args 类型注解精确匹配 production `_playwright_process_entry` 签名 — 这是 typed fake 与 typed production 之间的必要协议耦合。Protocol 变化 → pyright 报错 → 测试同步。这是类型安全的预期行为。

**掩盖缺陷**：`_FakePlaywrightResultQueue.get()` 在 payload 为空时立即 `raise Empty`，正确触发 production 的 `except Empty: return None` 路径。`_FakePlaywrightProcess` 不启动真实子进程 — unit test 预期行为。`_ScriptedMonotonicClock` 序列耗尽返回最后值 — 防御性设计。

## `_get_playwright_browser` Launch 失败 Cleanup 并发/异常/Publication 语义复核

### 并发

- 局部 `pw` 在 `_PW_LOCK` 锁内声明，其他线程不可见。
- 三项 global 只在 launch 成功后写入，保持 atomic publication。
- `pw.stop()` 在锁内执行 — 既有设计约束，fix 未恶化。

### 异常

| 场景 | start | launch | stop | 返回 | globals |
|---|---|---|---|---|---|
| 全部成功 | 成功 | 成功 | 不调用 | browser | 已发布 |
| launch 失败 + stop 成功 | 成功 | 异常 | 调用 1 次，成功 | None | 全 None |
| launch 失败 + stop 异常 | 成功 | 异常 | 调用 1 次，异常被脱敏记录 | None | 全 None |
| start 失败 | 异常 | 不到达 | 不调用 | None | 未变 |

所有路径保持 `return None` contract，global 不会半发布。

## 只读验证结果

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

| gate | command | result |
|---|---|---|
| focused owner tests（11 qualified functions） | `pytest -k 'test_get_playwright_browser_owner or test_materialize_bounded_page_projection_owns_text or test_route_handler_owner_selects or test_run_playwright_worker_process or test_close_playwright_browser_clears or test_normalize_url_for_http or test_web_egress_policy_owner_rejects'` | `21 passed, 174 deselected in 0.60s` |
| full aggregate matrix | `pytest test_web_tools_provider.py test_diagnose_web_access.py test_smoke_web_ci.py test_config_loader.py -q` | `330 passed, 1 skipped, 3 warnings in 13.16s` |
| full pyright | `python -m pyright` | `0 errors, 0 warnings, 0 informations` |
| git diff --check | `git diff --check 7e679796` | exit 0 |
| cleanup diagnostic 实际输出验证 | 独立 Python 脚本 | 仅含 stage + exception_type，零敏感哨兵 |
| lifecycle test contract 验证 | AST 分析 | 仅断言 headless/channel，零 AutomationControlled |
| `str(repr(stop_exc)` production 扫描 | `grep` | 零命中 |
| `hasattr`/`getattr` production 扫描 | `grep` | 零命中 |
| Issue 178/R03/统一 auth 偷带扫描 | `grep` | 零命中 |
| `AutomationControlled` test assertion 扫描 | `grep` | 零命中 |
| production changed files | `git diff --stat` | 仅 `web_playwright_backend.py`（13 行新增） |
| test changed files | `git diff --stat` | 仅 `test_web_tools_provider.py`（+1293/-53） |

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

| residual | owner / destination | non-blocking basis |
|---|---|---|
| credential refresh/retention/concurrent publish/cleanup | GitHub Issue #178 | R02 已删除提前实现，只保留 read input |
| live DOM/event/error 体量变化 | Web config owner | 当前版本化 fixture 未命中 ceiling |
| proxy/browser peer proof 限制 | typed fail-closed transport/browser owner | proof-on 在启动前 fail-close |
| external provider DNS/key/site 波动 | Web diagnostics/smoke owner | external-limit=0，local 11/11 |
| unified authorization 愿景 | Topic 9 future Controller decision | source/diff 零偷带 |
| accepted-result / LLM projection | umbrella R03 | 必须等待 R02 accepted 后另开 plan gate |
| `_PW_LOCK` 在 cleanup stop 期间持有 | 既有设计约束 | fix 未恶化，无阻塞证据 |

## Final Verdict

**PASS — findings=0。**

R02-AGG-DS-F01..F05 与 R02-AGG-CTRL-F01 六项全部确认闭合。R02-AGG-RV-F01（cleanup diagnostic 脱敏）和 R02-AGG-RV-F03（lifecycle test 不锁定 stealth tuning）按 Controller accepted 边界闭合。R02-AGG-RV-F02/F04 按 Controller rejection 保持未实现。Retained Web 安全零削弱（DNS/peer/redirect/proxy/budgets/route/challenge/redaction/containment）。Topic 2 裁决、Issue 178/R03/统一 authorization 零偷带。~1293 行新增 typed fake 不复制 production policy、不过度耦合、不掩盖缺陷。Production cleanup 代码正确实现 local runtime 回收 + 脱敏诊断，无竞态、无半状态发布、无 sensitive leak。

下一入口仅为 Controller 最终裁决。
