# R02 Aggregate Final Re-review — AgentMiMo

> Review timestamp: 20260715-054307

## Scope

- Mode: aggregate final re-review (not a new WU; same umbrella `WU-SEMANTIC-OWNERSHIP-01`)
- Branch: `phaseflow/host-issues-control`
- Base: accepted S3 commit `7e679796` to current working tree (uncommitted aggregate deepreview fix changes)
- Output file: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-mimo.md`
- Included scope: complete `2d42ceb6..HEAD` diff of 11 changed production `.py` files + uncommitted fix for `web_playwright_backend.py`, all test files + uncommitted ~1200-line typed fake additions in `test_web_tools_provider.py`, all aggregate artifacts (validation, deepreview mimo/ds, controller adjudication, fix codex, fix controller-validation, fix2 codex, fix2 controller-validation)
- Excluded scope: `dayu/render/`, `utils/` non-web scripts, binary/vendor/build artifacts
- Parallel review coverage: 3 parallel agents reviewed (1) adversarial test-fake analysis with 13 typed fake classes, (2) production `_get_playwright_browser` cleanup code with race/exception/lock analysis, (3) retained security source/propagation/signature scans

## Finding Closure Confirmation

### R02-AGG-DS-F01 — browser singleton lifecycle: CLOSED

`_get_playwright_browser` owner contract is now directly tested:
- `test_get_playwright_browser_owner_creates_reuses_and_replaces_by_key`: first create, same-key reuse, channel-change cleanup+recreate, headless-change cleanup+recreate
- `test_get_playwright_browser_owner_does_not_publish_failed_state`: launch failure returns `None`, globals all `None`
- `test_get_playwright_browser_owner_cleans_local_runtime_without_publishing_failed_state`: launch failure with local `pw.stop()` success AND `stop()` exception — both assert `stop_calls == 1`, globals all `None`

The R02-AGG-CTRL-F01 follow-up (local runtime cleanup on launch failure) is correctly implemented: `pw` declared before `try`, cleanup only on acquired runtime, globals never published on failure path. No double-stop risk with `_close_playwright_browser`.

### R02-AGG-DS-F02 — URL normalizer + userinfo security: CLOSED

- `test_normalize_url_for_http_rejects_missing_transport_parts`: 3-parameter case (missing scheme, missing netloc, empty hostname)
- `test_normalize_url_for_http_encodes_idna_and_userinfo_for_transport`: IDNA hostname, Unicode userinfo, path/query/fragment quoting
- `test_web_egress_policy_owner_rejects_userinfo_url`: direct `WebEgressPolicy.authorize_http_target` assertion with `reason="userinfo is not allowed"`

Per Controller owner correction: normalizer only does transport encoding, security rejection stays with `WebEgressPolicy`.

### R02-AGG-DS-F03 — Browser text budget: CLOSED

- `test_materialize_bounded_page_projection_owns_text_too_large_reason`: 2-parameter case covering DOM-in-range but text preflight exceeded, AND preflight-in-range but actual text exceeded. Both assert `_BrowserResourceBudgetExceeded.reason == _BROWSER_TEXT_TOO_LARGE_REASON`.

### R02-AGG-DS-F04 — Browser route handler: CLOSED

- `test_route_handler_owner_selects_resource_policy_or_continue_action`: 5-parameter case covering image/font/media → abort, denied document → abort, allowed document → continue. `_RecordingPlaywrightRoute` only records action; policy decision by real `WebEgressPolicy`.

### R02-AGG-DS-F05 — Worker process fencing + cleanup: CLOSED

- `test_run_playwright_worker_process_cancellation_terminates_and_cleans_queue`: pre-cancelled token → terminate called, `CancelledError`, queue close/join
- `test_run_playwright_worker_process_no_result_exit_cleans_queue`: process exited, no payload → RuntimeError, non-blocking join, finally cleanup
- `test_run_playwright_worker_process_timeout_terminates_and_cleans_queue`: alive process, timeout=0 → TimeoutError, terminate, finally cleanup
- `test_close_playwright_browser_clears_singletons_after_success_or_error`: 3-parameter case (both succeed, browser close exception, runtime stop exception) — all assert globals cleared

### R02-AGG-CTRL-F01 — Launch failure local runtime cleanup: CLOSED

Production fix in `_get_playwright_browser` (7 lines added): local `pw` declared before `try`, cleanup `pw.stop()` in `except` only when `pw is not None`, stop exception swallowed to preserve original launch failure semantics. Test `test_get_playwright_browser_owner_cleans_local_runtime_without_publishing_failed_state` covers both stop-success and stop-exception paths.

## Retained Web Security Verification

All verification commands executed with `source .venv/bin/activate`.

| Dimension | Evidence | Verdict |
|---|---|---|
| DNS/address: dangerous/unspecified/multicast/mixed DNS/private deny/custom-port deny | 98 passed, 1 skipped retained matrix | PASS |
| redirect: initial URL + each hop re-authorize | `web_fetch_orchestrator.py` `_request_with_safe_redirects` per-hop `_authorize_http_target` | PASS |
| peer proof: numeric pin + actual peer compare, mismatch fail-closed | `_PinnedHTTPConnection._new_conn` → `sock.getpeername()` compare | PASS |
| proxy+proof incompatibility | `web_http_session.py:726-727`: `ProxyPeerProofIncompatibleError` before `send()` | PASS |
| proxy denied → empty proxies assert | `web_http_session.py:685,720-721` | PASS |
| browser/private decoupling | `_browser_fallback_available` checks only `browser_enabled` + `dns_peer_proof_enabled` | PASS |
| browser proof fail-close | `web_playwright_backend.py:1622-1627`: before `import playwright` | PASS |
| browser proxy env cleanup | `_playwright_process_entry`: `_clear_proxy_environment()` deletes 8 env vars | PASS |
| challenge detection | `web_challenge_detection.py` zero diff, shared detector preserved | PASS |
| redaction: URL/header/cookie/error | `web_diagnostics.py` + `_sanitize_response_headers` whitelist | PASS |
| containment/symlink | explicit storage-state input read-only, existing resolver preserved | PASS |
| budget exact/+1 | 10 passed direct nodes (aggregate validation §7) | PASS |
| diagnostics v2/revision 2 | filing HTTP/Playwright artifacts both `web-diagnostics-v2`/revision 2 | PASS |
| transport_policy signature audit | `transport_signature_audit=2 issues=0` | PASS |
| old contract zero-residual | `WebResourceBudget`/`_StorageStateLifecycle`/`storage_state_out`/`owner_final_name` zero matches | PASS |
| `_DEFAULT_DIAGNOSTIC_ERROR_CHARS`/`1_024`/`default=80` | zero matches in `diagnose_web_access.py` and its test | PASS |
| utility `getattr`/`hasattr` | zero matches in `diagnose_web_access.py` | PASS |
| challenge detector/smoke/batch/README zero diff | `git diff --exit-code` exit 0 | PASS |

## Adversarial Test Fake Review

### 13 typed fake classes reviewed

`_LifecyclePlaywrightBrowser`, `_LifecycleChromiumLauncher`, `_LifecyclePlaywrightInstance`, `_LifecyclePlaywrightStarter`, `_LifecycleSyncPlaywrightFactory`, `_RecordingRouteRequest`, `_RecordingPlaywrightRoute`, `_FakePlaywrightResultQueue`, `_FakePlaywrightProcess`, `_FakePlaywrightMultiprocessingContext`, `_FakePlaywrightContextFactory`, `_RecordingPlaywrightProcessTerminator`, `_ScriptedMonotonicClock`

**Anti-pattern check: do fakes replicate production policy/state machine?**

No. The fakes are behavior recorders/programmable responses, not policy re-implementations:
- Route fakes record abort/continue actions; policy decision is made by real `WebEgressPolicy`
- Process fakes provide scripted process lifecycle; no production lock/queue logic replicated
- Lifecycle fakes record close/stop calls; no production singleton management replicated
- Clock fake provides deterministic timestamps; no production timing logic replicated

**Over-coupling assessment:**

See Findings below. The most significant coupling is the `Process` target type annotation mirroring production's exact 5-parameter arity (medium), and the lifecycle test locking exact launch kwargs including the stealth flag (medium). Neither causes false passes today but both would break on production refactoring for non-contract reasons.

**Locking accidental ordering:**

The `process_target is _playwright_process_entry` and `method == "spawn"` assertions lock implementation identity rather than behavioral contract. The `process.daemon is True` assertion locks a process-lifetime detail already covered by cleanup assertions.

**Masking real defects:**

`_RecordingPlaywrightProcessTerminator` always returns `{"terminate": None, "kill": None}` and always calls `mark_terminated()`, collapsing the two-phase terminate/kill protocol. This means no integration-level test verifies cleanup diagnostic structure or the kill-after-terminate-if-still-alive behavior. However, the unit tests for `_terminate_playwright_process` itself (which exist separately) do cover this path.

**Strict type/docstring compliance:**

All method-level and `__init__` docstrings have complete Chinese `Args/Returns/Raises`. Several class-level docstrings lack `Args/Returns/Raises` sections (informational; project convention is mixed at class level).

## Production Cleanup Code Review

`_get_playwright_browser` uncommitted fix (7 lines):

1. **Scoping**: `pw` declared before `try`, visible in `except` — correct
2. **Cleanup trigger**: only when `pw is not None` (runtime acquired but launch failed) — correct
3. **Lock safety**: all under `_PW_LOCK`, cleanup operates on local variable only — no race
4. **Global publication**: globals untouched on failure path — no partial state
5. **Double-stop**: local `pw` never published to `_PW_INSTANCE`, so `_close_playwright_browser()` cannot see it — safe
6. **Stop failure**: `pw.stop()` exception swallowed with bare `pass` — functional but loses diagnostic information (see Finding R02-AGG-RV-F01)

## Findings

### R02-AGG-RV-F01 — 未修复 — [低] — `_get_playwright_browser` cleanup `pw.stop()` 异常被静默吞掉

- **入口/函数**: `dayu/tools/web/web_playwright_backend.py:_get_playwright_browser`
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:1072-1075`
- **输入场景**: Playwright runtime 启动成功但 `chromium.launch()` 失败，且 `pw.stop()` 自身也抛异常
- **实际分支**: `pw.stop()` 异常被 `except Exception: pass` 吞掉，只记录原始 launch 失败
- **预期行为**: stop 失败应留下诊断痕迹，至少 debug 级别日志，便于事后排查孤儿进程
- **实际行为**: stop 异常完全无日志；若 `stop()` 泄漏子进程，`_close_playwright_browser()` 回收不到（`_PW_INSTANCE` 仍为 `None`），孤儿进程持续到进程退出
- **直接证据**: `web_playwright_backend.py:1074` — `except Exception: pass`，无 `Log.debug` 或其他诊断
- **影响**: 生产中若 `stop()` 失败，无任何日志证据支持事后诊断；不影响正确性（返回 `None` 不变）
- **建议改法和验证点**: `except Exception as stop_exc: Log.debug(f"pw.stop() during cleanup failed: {stop_exc}", module=MODULE)`；不改返回值语义
- **修复风险（低）**: 纯日志增强，不改变控制流
- **严重程度（低）**: 功能正确，仅缺诊断；Controller 已验证当前行为可接受

### R02-AGG-RV-F02 — 未修复 — [低] — `_get_playwright_browser` docstring 未反映 cleanup 不变量

- **入口/函数**: `dayu/tools/web/web_playwright_backend.py:_get_playwright_browser`
- **文件(行号)**: `dayu/tools/web/web_playwright_backend.py:1034-1045`
- **输入场景**: 阅读函数 docstring 理解 cleanup 行为
- **实际分支**: docstring 只描述 Args/Returns/Raises，未提及初始化失败时的 local runtime cleanup
- **预期行为**: docstring 应说明：初始化失败时，已启动但未发布的 Playwright runtime 在 owner 异常边界被 best-effort 停止，全局单例保持 None
- **实际行为**: 该不变量仅由行内注释 `# runtime 尚未发布到全局，必须在当前 owner 异常边界就地回收` 记录
- **直接证据**: `web_playwright_backend.py:1034-1045` — 无 cleanup 语义描述
- **影响**: 维护者可能不理解 `pw` 为何在 `try` 前声明；不影响运行时行为
- **建议改法和验证点**: 在 Returns 后增加注释说明 cleanup 不变量
- **修复风险（低）**: 纯文档
- **严重程度（低）**: 不影响正确性或安全

### R02-AGG-RV-F03 — 未修复 — [低] — lifecycle 测试断言锁定 launch kwargs 实现细节

- **入口/函数**: `tests/tools/web/test_web_tools_provider.py::test_get_playwright_browser_owner_creates_reuses_and_replaces_by_key`
- **文件(行号)**: `tests/tools/web/test_web_tools_provider.py:6563-6583`
- **输入场景**: 生产代码修改 Chromium launch 参数（如移除 stealth flag）
- **实际分支**: 测试断言 exact `launch` kwargs 包括 `"args": ["--disable-blink-features=AutomationControlled"]`
- **预期行为**: 测试应断言 lifecycle contract（创建/复用/替换/清理），不锁定 launch 参数细节
- **实际行为**: 若 stealth flag 被移除或修改，测试因非 contract 原因失败
- **直接证据**: `test_web_tools_provider.py:6579` — `assert kwargs == {"headless": True, "args": ["--disable-blink-features=AutomationControlled"]}`
- **影响**: 增加测试维护成本；不影响当前正确性
- **建议改法和验证点**: 改为只断言 `kwargs["headless"] is True` 和 `"channel" not in kwargs`（无 channel case）
- **修复风险（低）**: 纯测试修改
- **严重程度（低）**: 测试耦合，非生产缺陷

### R02-AGG-RV-F04 — 未修复 — [信息] — 多个 test fake 类级 docstring 缺 Args/Returns/Raises

- **入口/函数**: 多个 `_Lifecycle*`/`_Recording*`/`_Fake*` 类
- **文件(行号)**: `tests/tools/web/test_web_tools_provider.py:1207,1263,1311,1355,1433,1440,1963`
- **输入场景**: 阅读 test fake 类 docstring
- **实际分支**: 类级 docstring 有中文职责概览但缺 Args/Returns/Raises
- **预期行为**: 按 AGENTS.md 编码硬约束，类应提供中文概览 docstring
- **实际行为**: 所有 `__init__` 和方法级 docstring 完整；仅类级 docstring 缺结构化参数说明
- **直接证据**: `_LifecyclePlaywrightBrowser` docstring 为 `"""记录 browser singleton 生命周期动作并可注入关闭异常。"""`，无 Args
- **影响**: 不影响类型检查或测试正确性
- **建议改法和验证点**: 补充类字段说明
- **修复风险（低）**: 纯文档
- **严重程度（低）**: 测试文档完整性

## Open Questions

无。

## Residual Risk

| residual | owner / destination | non-blocking basis |
|---|---|---|
| credential refresh/retention/concurrent publish/cleanup | GitHub Issue #178 | R02 已删除提前实现，只保留 read input |
| live DOM/event/error 体量变化 | Web config owner | 当前版本化 fixture 未命中 ceiling |
| proxy/browser peer proof 限制 | typed fail-closed transport/browser owner | proof-on 在启动前 fail-closed |
| external provider DNS/key/site 波动 | Web diagnostics/smoke owner | external-limit=0，local 11/11 |
| unified authorization 愿景 | Topic 9 future Controller decision | source/diff 零偷带 |
| accepted-result / LLM projection | umbrella R03 | 必须等待 R02 accepted 后另开 plan gate |
| test fake 过度耦合 launch kwargs/进程参数类型注解 | R02 aggregate fix gate 或后续测试维护 | 不影响当前正确性，增加未来 refactoring 成本 |
| `_RecordingPlaywrightProcessTerminator` 不验证 cleanup 诊断结构 | 同上 | `_terminate_playwright_process` 自身有独立 unit test 覆盖两阶段协议 |

## Final Verdict

**PASS — findings=0 blocking, 4 non-blocking (2 low production, 1 low test, 1 informational)。**

R02-AGG-DS-F01..F05 和 R02-AGG-CTRL-F01 六项全部确认闭合。retained Web 安全完整（DNS/peer/redirect/proxy/budgets/route/challenge/redaction/containment）。Topic 2 裁决、Issue 178/R03/统一 authorization 零偷带。~1200 行新增 typed fake 未复制 production policy/state machine，未过度锁定生产 contract，未掩盖真实缺陷；最大耦合点（launch kwargs 断言、进程 target 类型注解）为低严重性测试维护风险。production cleanup 代码正确实现 local runtime 回收，无竞态、无半状态发布、无 double-stop。

下一入口仅为 Controller adjudication。
