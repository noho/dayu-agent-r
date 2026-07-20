# WU-SEMANTIC-OWNERSHIP-01 / R02 aggregate deepreview fix（AgentCodex）

## 1. Gate 身份、结论与边界

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`；本轮继续同一 R02 aggregate deepreview fix，不是新 WU。
- accepted plan：`2d42ceb6`；accepted slices：S1=`c7b01d82`、S2=`d8d6e9d9`、S3=`7e679796`。
- finding disposition 真源：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-controller-adjudication.md`。
- 本轮结论：`R02-AGG-DS-F01..F05` 五项 accepted owner-test gap 均已按 Controller 边界修复，direct owner tests、完整 provider tests、aggregate matrix、coverage、pyright、diff/路径/docstring gate 与独立 real Playwright local smoke 全部通过。
- 唯一 test diff：`tests/tools/web/test_web_tools_provider.py`。
- 唯一新增 artifact：本文。
- `tests/README.md`：`no-update-with-evidence`，见 §6。
- 本轮未修改 `dayu/**`、`utils/**`、config、control、其它 tests/README或既有 artifacts；未 commit/push，未启动 re-review、completion 或 R03。

该结论只表示 AgentCodex fix evidence 已准备好等待 Controller validation，不等于 R02 accepted，不授权 Issue 178 replacement lifecycle、proxy credential schema或统一 tool authorization framework。

## 2. 第一性原理与 owner 判定

五项 finding 的动机成立：它们不是为了抬高总体 coverage 数字，而是现有 suite 没有直接锁定 browser singleton lifecycle、transport URL normalizer、userinfo security owner、Browser text child-budget、browser route action和 worker process fencing/cleanup 的真实 owner contract。正确修复必须直接调用 owner，fake 只替换外部 Playwright/multiprocessing/page/route协作者；不能在下游重算规则或修改生产行为。

owner 边界如下：

| fact | unique owner | test boundary |
|---|---|---|
| browser singleton create/reuse/re-key/failed publication | `web_playwright_backend._get_playwright_browser` | patch `playwright.sync_api.sync_playwright` 为 typed runtime/browser collaborators，直接调用 owner |
| transport ASCII/IDNA/userinfo quoting与缺失 transport parts | `web_tools._normalize_url_for_http` | 直接调用 normalizer；不增加 security blacklist |
| userinfo安全拒绝 | `WebEgressPolicy.authorize_http_target` | 直接断言 typed `WebEgressPolicyError.reason` |
| Browser `text_chars` fail-bounded reason | `_materialize_bounded_page_projection` | synthetic page只提供 metrics/HTML/text；断言 typed exception `.reason` |
| route resource/policy/continue action | `_route_handler_abort_resources` | fake route只记录 `abort` / `continue`，不重算 policy |
| child process cancel/exit/timeout/finally fencing | `_run_playwright_worker_process` | fake context/process/queue/token与scripted monotonic clock；无sleep、无真实子进程 |
| process-local browser/runtime singleton cleanup | `_close_playwright_browser` | typed browser/runtime fake在成功或异常时记录close/stop；直接断言三项global清空 |

Direct owner tests没有暴露 accepted production behavior 缺陷，因此没有触发“停止回 Controller、禁止生产修改”的 stop condition。

## 3. Finding 与 test qualified name 映射

### `R02-AGG-DS-F01` — 已修复

- `tests/tools/web/test_web_tools_provider.py::test_get_playwright_browser_owner_creates_reuses_and_replaces_by_key`
  - 首次创建；相同 normalized `(channel, headless)` key复用；channel变化cleanup/recreate；headless变化cleanup/recreate；逐次断言旧browser close、旧runtime stop、launch typed kwargs与最终cache key。
- `tests/tools/web/test_web_tools_provider.py::test_get_playwright_browser_owner_does_not_publish_failed_state`
  - launch异常时直接断言返回 `None`，且 `_PW_INSTANCE/_PW_BROWSER/_PW_BROWSER_KEY` 全为 `None`，没有发布半状态。

这两项只替换外部 `sync_playwright` collaborator，不依赖 live Chromium，也不把具体锁获取顺序固化成业务 contract。

### `R02-AGG-DS-F02` — 已修复（按 Controller owner correction）

- `tests/tools/web/test_web_tools_provider.py::test_normalize_url_for_http_rejects_missing_transport_parts`
  - 三参数 case分别覆盖缺 scheme、缺 netloc、netloc存在但缺 hostname。
- `tests/tools/web/test_web_tools_provider.py::test_normalize_url_for_http_encodes_idna_and_userinfo_for_transport`
  - 直接断言Unicode username/password、IDNA hostname、path/query/fragment的ASCII quoting结果；normalizer继续允许并编码userinfo，不承担安全拒绝。
- `tests/tools/web/test_web_tools_provider.py::test_web_egress_policy_owner_rejects_userinfo_url`
  - 直接调用 `WebEgressPolicy.authorize_http_target`，断言 `reason="userinfo is not allowed"` 与调用stage。

没有在 normalizer、sender、orchestrator或下游增加重复 userinfo blacklist/fallback；安全拒绝唯一归 `WebEgressPolicy`。

### `R02-AGG-DS-F03` — 已修复

- `tests/tools/web/test_web_tools_provider.py::test_materialize_bounded_page_projection_owns_text_too_large_reason`
  - 两参数 case覆盖DOM界内但 bounded text preflight超限，以及preflight界内但实际全文本超限；两者都直接断言 `_BrowserResourceBudgetExceeded.reason == _BROWSER_TEXT_TOO_LARGE_REASON`，没有用任意错误文本或下游映射替代。

### `R02-AGG-DS-F04` — 已修复

- `tests/tools/web/test_web_tools_provider.py::test_route_handler_owner_selects_resource_policy_or_continue_action`
  - 五参数 case覆盖 `image/font/media -> abort`、denied document URL -> abort、allowed document URL -> continue。
  - `_RecordingPlaywrightRoute` 只暴露request facts并记录action；policy判断仍由真实 `WebEgressPolicy` owner执行，fake不重算policy。

### `R02-AGG-DS-F05` — 已修复

- `tests/tools/web/test_web_tools_provider.py::test_run_playwright_worker_process_cancellation_terminates_and_cleans_queue`
  - fake token预先取消；直接断言terminate collaborator被调用、`CancelledError`保留cancel reason、queue close/join各一次。
- `tests/tools/web/test_web_tools_provider.py::test_run_playwright_worker_process_no_result_exit_cleans_queue`
  - fake process启动后已退出、queue无payload；scripted clock直接跨过result-drain grace，断言稳定RuntimeError、非阻塞join和finally queue cleanup。
- `tests/tools/web/test_web_tools_provider.py::test_run_playwright_worker_process_timeout_terminates_and_cleans_queue`
  - fake process保持alive、timeout为0；scripted clock立即到deadline，断言TimeoutError、terminate与finally queue cleanup。
- `tests/tools/web/test_web_tools_provider.py::test_close_playwright_browser_clears_singletons_after_success_or_error`
  - 三参数 case覆盖close/stop均成功、browser close异常、runtime stop异常；每个case都断言close/stop被调用且三项global状态清空。

所有 F05 unit cases均使用内存 fake multiprocessing context/process/queue/token和scripted monotonic clock；没有 `sleep`，没有启动真实子进程。真实浏览器可执行性由独立 §5.5 smoke验证，不与unit fencing owner混合。

## 4. Exact changed definitions 与中文 docstring audit

本轮新增 typed collaborator类别：

- Playwright lifecycle：`_LifecyclePlaywrightBrowser`、`_LifecycleChromiumLauncher`、`_LifecyclePlaywrightInstance`、`_LifecyclePlaywrightStarter`、`_LifecycleSyncPlaywrightFactory`；
- route action recorder：`_RecordingRouteRequest`、`_RecordingPlaywrightRoute`；
- process fencing：`_FakePlaywrightResultQueue`、`_FakePlaywrightProcess`、`_FakePlaywrightMultiprocessingContext`、`_FakePlaywrightContextFactory`、`_RecordingPlaywrightProcessTerminator`、`_ScriptedMonotonicClock`；
- typed helper：`_playwright_worker_process_kwargs`；
- §3列出的11个top-level test functions。

AST audit以 `HEAD:tests/tools/web/test_web_tools_provider.py` 为baseline，递归比较qualified name和function signature；对新增/签名变化的function/method要求中文且完整 `Args/Returns/Raises`（或accepted Sphinx等价格式），对class要求中文职责概览：

```text
added_or_signature_changed=59 issues=0
```

新增 fake没有 `Any`、`object`、裸容器或无类型签名。Playwright `new_context(**kwargs: JsonValue)` / `launch(**kwargs: JsonValue)` 只复现既有第三方Protocol形状；multiprocessing fake用精确typed queue/process target/args，不引入loose production seam。full pyright进一步确认所有测试协作者满足仓库类型边界。

## 5. Validation

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### 5.1 Focused owner nodes

显式执行 §3 的11个qualified test functions（参数化后20 cases）：

```text
20 passed in 0.73s
```

case归属为 F01=`2`、F02=`5`、F03=`2`、F04=`5`、F05=`6`；零skip、零真实子进程。

### 5.2 完整 provider tests

```text
pytest tests/tools/web/test_web_tools_provider.py -q
=> 193 passed, 1 skipped in 11.79s
```

唯一skip仍是既有opt-in live browser cleanup pytest，不是本轮direct owner nodes或real Playwright hard gate。

### 5.3 Accepted plan §14.4 aggregate matrix

```text
pytest tests/tools/web/test_web_tools_provider.py \
  tests/tools/web/test_diagnose_web_access.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_config_loader.py -q
=> 329 passed, 1 skipped, 3 warnings in 13.02s
```

coverage canonical run对同一四文件matrix再次得到 `329 passed, 1 skipped, 3 warnings in 13.49s`。三条warning仍来自`edgar`依赖deprecation，不是R02 owner/test failure。

### 5.4 Corrected coverage JSON 与逐文件 threshold

- coverage data：`workspace/tmp/.coverage-r02-aggregate-fix`
- coverage JSON：`workspace/tmp/coverage-r02-aggregate-fix.json`

| production owner file | statements | covered | missing | exact percent | `--fail-under=80` |
|---|---:|---:|---:|---:|---|
| `dayu/tools/web/web_tools.py` | 712 | 575 | 137 | `80.75842696629213%` | PASS |
| `dayu/tools/web/web_playwright_backend.py` | 533 | 479 | 54 | `89.8686679174484%` | PASS |

coverage提升来自直接 owner branches；没有生产代码改动、coverage omit/waiver或测试skip。

### 5.5 独立 deterministic local real Playwright smoke

使用新目录，执行 accepted plan §13命令：

```text
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-aggregate-fix-codex \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-aggregate-fix-codex
=> status=passed, exit_code=0, local=11 passed, failures=0, skips=0
```

summary：`workspace/tmp/r02-web-owner-policy-aggregate-fix-codex/summary.json`。真实 `local-browser-playwright` 与 `local-filing-playwright` 均执行并通过；新增unit tests没有污染module globals或browser runtime。四个search case均为accepted `diagnostic_only`，`external-limit=0`没有替代local hard gate。

### 5.6 类型、whitespace、authored path 与 production zero-diff

```text
python -m pyright
=> 0 errors, 0 warnings, 0 informations

git diff --check
=> PASS

git diff --exit-code -- dayu utils README.md dayu/config tests/README.md
=> PASS（零输出）
```

preflight已存在的dirty state是control修改与五份aggregate validation/review/controller artifacts；本轮没有修改这些路径。排除既有dirty inputs后，AgentCodex authored repository paths恰好为：

1. `tests/tools/web/test_web_tools_provider.py`；
2. `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix-codex.md`。

production/config/utils/root README/tests README均zero diff；没有隐藏生产修复、normalizer blacklist、policy fallback、smoke脚本修改或control gate推进。

## 6. README decision

完整读取 `tests/README.md` 后决定：`no-update-with-evidence`。

理由：本轮只在现有 `tests/tools/web/test_web_tools_provider.py` 内补齐既有Web owner contract的直接unit cases；没有新增测试层级、测试目录、公共测试helper、运行命令、marker、环境变量或维护规则。README当前职责只要求这些事实发生变化时更新；把11个具体private test qualified names写入测试手册会越过其稳定分层/维护边界。根/分层/config README同样没有职责内变化且保持zero diff。

## 7. Residual risk、完成状态与 handoff

- `R02-AGG-DS-F01..F05`：AgentCodex fix状态均为`已修复`，等待 Controller validation与MiMo/DS双路完整aggregate re-review最终裁决。
- 没有新增 production defect、owner drift、安全回归、deferred scope leakage或ownerless residual。
- R02既有 residual destination保持不变：credential lifecycle -> Issue 178；future live-size variability -> Web config owner；proxy/browser peer-proof限制 -> typed fail-closed transport/browser owner；external provider variability -> diagnostics/smoke owner；accepted-result/LLM projection -> 后续R03；统一authorization -> Topic 9 no-code decision。
- artifact path：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix-codex.md`。
- next entry point仅为 Controller validation。AgentCodex不自行commit/push、不更新control、不启动re-review/completion/R03。
