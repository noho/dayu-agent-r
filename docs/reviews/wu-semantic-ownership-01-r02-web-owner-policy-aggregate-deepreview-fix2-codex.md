# WU-SEMANTIC-OWNERSHIP-01 / R02 aggregate deepreview follow-up fix（AgentCodex）

## 1. Gate 身份、结论与边界

- gate：既有 `WU-SEMANTIC-OWNERSHIP-01` / R02 aggregate deepreview finding fix；不是新 WU、gate或slice。
- follow-up真源：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix-controller-validation.md`。
- accepted finding：`R02-AGG-CTRL-F01`；它是原 `R02-AGG-DS-F01` 初始化异常cleanup要求的闭合，不是新browser framework或Issue 178 lifecycle。
- 结论：`R02-AGG-CTRL-F01` 已在 browser lifecycle owner边界修复；launch失败时已启动但尚未发布的局部Playwright runtime会best-effort `stop()`，stop自身异常不遮蔽既有返回`None` contract，三个global仍保持未发布状态。
- follow-up production/test changed paths恰好为：
  1. `dayu/tools/web/web_playwright_backend.py`；
  2. `tests/tools/web/test_web_tools_provider.py`。
- 唯一新增follow-up artifact：本文。
- 首轮fix artifact与Controller validation、control及其它既有artifacts均保持不变。
- 未修改其它production/tests/config/utils/README；未commit/push，未启动re-review、completion或R03。

本结论只表示AgentCodex follow-up fix与验证完成，等待Controller re-validation；不等于R02 accepted。

## 2. 第一性原理、root cause与owner修复

Controller finding成立，且root cause与数据/逻辑同源：

```text
sync_playwright().start() -> local pw
pw.chromium.launch(...) -> failure
global publication尚未发生
_close_playwright_browser()看不到local pw
```

`_get_playwright_browser` 同时拥有runtime启动、browser launch与singleton publication，因此正确修复必须留在该函数；caller、adapter、smoke或下游fallback都无法回收尚未发布的局部runtime。

实现保持以下时序：

1. 进入初始化前声明typed局部 `pw: _PlaywrightInstanceProtocol | None = None`；
2. `sync_playwright().start()`成功后只写入local `pw`；
3. `pw.chromium.launch(...)`成功后才依次发布 `_PW_INSTANCE/_PW_BROWSER/_PW_BROWSER_KEY`；
4. 任一初始化异常时，若local `pw`已启动，则在同一owner异常边界best-effort `pw.stop()`；
5. `stop()`异常被局部吞掉，原launch失败仍记录warning并返回`None`；三个global不被提前写入。

没有为了cleanup提前发布 `_PW_INSTANCE`，没有新增compatibility、`getattr/hasattr`、downstream fallback、storage-state lifecycle或统一authorization路径。

## 3. Direct owner tests

### 原F01成功与cache/re-key contract

- `tests/tools/web/test_web_tools_provider.py::test_get_playwright_browser_owner_creates_reuses_and_replaces_by_key`
  - 直接调用真实 `_get_playwright_browser`；覆盖首次创建、同key复用、channel变化cleanup/recreate、headless变化cleanup/recreate。

### `R02-AGG-CTRL-F01`异常cleanup contract

- `tests/tools/web/test_web_tools_provider.py::test_get_playwright_browser_owner_cleans_local_runtime_without_publishing_failed_state`
  - 参数1：launch失败、local `stop()`成功；
  - 参数2：launch失败、local `stop()`自身抛异常；
  - 两个case都直接断言 `instance.stop_calls == 1`、owner返回`None`、`_PW_INSTANCE/_PW_BROWSER/_PW_BROWSER_KEY`全为`None`。

F01 focused命令结果：

```text
3 passed in 0.74s
```

首轮全部11个qualified owner functions重跑后，参数化共：

```text
21 passed in 0.57s
```

typed Playwright collaborators只替代外部runtime/browser，不依赖live Chromium。unit tests没有sleep或真实子进程；独立real Playwright证据见§4.5。

## 4. Validation

所有Python命令均在 `source .venv/bin/activate` 后执行。

### 4.1 完整provider与accepted plan §14.4 aggregate matrix

```text
pytest tests/tools/web/test_web_tools_provider.py -q
=> 194 passed, 1 skipped in 11.81s

pytest tests/tools/web/test_web_tools_provider.py \
  tests/tools/web/test_diagnose_web_access.py \
  tests/tools/web/test_smoke_web_ci.py \
  tests/runtime/test_config_loader.py -q
=> 330 passed, 1 skipped, 3 warnings in 12.83s
```

coverage canonical run对同一aggregate matrix再次得到 `330 passed, 1 skipped, 3 warnings in 13.49s`。唯一skip仍是既有opt-in live browser cleanup pytest；三条warning仍来自`edgar`依赖deprecation。

### 4.2 Corrected coverage JSON与逐文件threshold

- data：`workspace/tmp/.coverage-r02-aggregate-fix2`
- JSON：`workspace/tmp/coverage-r02-aggregate-fix2.json`

| file | statements | covered | missing | exact percent | `--fail-under=80` |
|---|---:|---:|---:|---:|---|
| `dayu/tools/web/web_tools.py` | 712 | 575 | 137 | `80.75842696629213%` | PASS |
| `dayu/tools/web/web_playwright_backend.py` | 539 | 485 | 54 | `89.98144712430427%` | PASS |

新增6个production statements来自local runtime cleanup分支；stop成功与stop异常路径均由direct tests执行。

### 4.3 Full pyright、whitespace与allowed paths

```text
python -m pyright
=> 0 errors, 0 warnings, 0 informations

git diff --check
=> PASS
```

对 `dayu/tests/utils/root README` tracked diff做exact set compare，排除进入本任务前既有的Controller-owned control diff后，production/test集合严格为：

```text
dayu/tools/web/web_playwright_backend.py
tests/tools/web/test_web_tools_provider.py
```

`tests/README.md`与根README `git diff --exit-code`通过。其它production/tests/config/utils均没有follow-up diff；首轮test/fix artifact与新Controller validation只作为既有输入保留。

### 4.4 Docstring与source/ownership scans

以HEAD源码为baseline递归比较两个changed code/test文件的definition AST，包含body变化的真实owner函数：

```text
changed_definitions=60 issues=0
playwright_local_runtime_cleanup_audit=pass
production_source_scan=0
test_no_sleep_real_process_scan=0
```

- 60项包含 `_get_playwright_browser` 与首轮新增typed collaborator/test definitions；function/method均有中文完整`Args/Returns/Raises`或accepted等价格式，class均有中文职责概览。
- owner AST scan确认 `start < launch < 三项global assignment`，异常handler存在local `pw.stop()`，handler内没有任何 `_PW_*` publication。
- production added-line scan对 `hasattr/getattr`、Issue 178、storage lifecycle、compatibility/fallback零命中。
- test added-line scan对 `time.sleep`与真实`multiprocessing.get_context(...)`调用零命中。

第一次把production/test合并做宽泛`storage_state` scan时，命中了首轮typed worker kwargs中的合法只读 `playwright_storage_state_path` 测试输入；该命中不是follow-up production/deferred-scope实现。修正为production-only owner scan和test no-sleep/real-process scan后均为0，未通过修改源码消除审计结果。

### 4.5 新目录independent real Playwright smoke

```text
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-aggregate-fix2-codex \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-aggregate-fix2-codex
=> status=passed, exit_code=0, local=11 passed, failures=0, skips=0
```

summary：`workspace/tmp/r02-web-owner-policy-aggregate-fix2-codex/summary.json`。真实`local-browser-playwright`与`local-filing-playwright`均执行通过；新增失败cleanup tests没有污染module globals/runtime。四个search case仍为accepted `diagnostic_only`，`external-limit=0`没有替代local hard gate。

## 5. README decision

- `dayu/tools/web/README.md`：不存在。
- `dayu/tools/README.md`：不存在。
- 根/其它分层README：`no-update-with-evidence`；本修复只纠正private browser runtime初始化失败cleanup，不改变安装、初始化、CLI/Web/WeChat入口、配置、LLM-facing文本、分层或最终用户工作流。
- `tests/README.md`：`no-update-with-evidence`；只补强同一现有Web provider owner test，没有新增测试层级、运行方式、marker、环境变量或维护规则。

因此本轮没有README diff。

## 6. Finding状态、residual与handoff

- `R02-AGG-CTRL-F01`：AgentCodex状态=`已修复`，等待Controller re-validation。
- 原 `R02-AGG-DS-F01`：create/reuse/re-key/global publication与初始化异常local runtime cleanup均已覆盖；最终状态仍由Controller与后续双路aggregate re-review裁决。
- `R02-AGG-DS-F02..F05`：沿用Controller validation已通过结论，本follow-up未改其owner contract。
- 没有新增ownerless residual、安全回归、deferred scope leakage或production open question。
- artifact path：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix2-codex.md`。
- next entry point仅为Controller re-validation；AgentCodex不自行commit/push、不更新control、不启动MiMo/DS re-review、completion或R03。
