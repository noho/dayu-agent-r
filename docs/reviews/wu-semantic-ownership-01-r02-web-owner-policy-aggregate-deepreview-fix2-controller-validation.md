# WU-SEMANTIC-OWNERSHIP-01 / R02 aggregate deepreview fix2 Controller validation

## 1. 结论

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`；本轮是同一R02 aggregate deepreview fix follow-up，不是新WU/gate/slice。
- AgentCodex artifact：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix2-codex.md`。
- Controller verdict：`PASS`，进入MiMo/DS双路完整aggregate final re-review。
- `R02-AGG-CTRL-F01` 已关闭：launch失败时，尚未发布的局部Playwright runtime在owner异常边界best-effort `stop()`；stop自身异常不遮蔽既有返回`None` contract，三项global保持未发布。
- 原 `R02-AGG-DS-F01..F05` 的direct owner tests全部保留并通过。

该PASS不等于R02 accepted，不授权completion、R03、Issue 178 replacement lifecycle、proxy credential schema或统一tool authorization framework。

## 2. Owner与实现复核

Controller逐行复核 `dayu/tools/web/web_playwright_backend.py` diff：

1. `_get_playwright_browser` 是runtime启动、browser launch和singleton publication的唯一owner；
2. 新局部变量 `pw: _PlaywrightInstanceProtocol | None` 在try前声明；
3. `sync_playwright().start()` 与 `chromium.launch()` 都在global publication之前；
4. 异常handler仅对已启动局部runtime调用best-effort `stop()`，没有写入 `_PW_INSTANCE/_PW_BROWSER/_PW_BROWSER_KEY`；
5. stop异常被限制在cleanup边界，不改变原launch失败warning和返回`None`行为；
6. production diff没有caller/adapter fallback、storage-state lifecycle、兼容分支、`hasattr/getattr`或authorization设计。

这7行production diff修复root cause，不依赖下游或test shim。测试参数化覆盖stop成功与stop异常，并在两个case都断言`stop_calls == 1`和三项global为`None`。

## 3. 独立验证

所有Python命令均在 `source .venv/bin/activate` 后执行。

### 3.1 Direct owner、aggregate与类型

- 11个qualified direct-owner functions，参数化后：`21 passed in 0.61s`；
- accepted aggregate matrix：`330 passed, 1 skipped, 3 warnings in 13.50s`；
- full pyright：`0 errors, 0 warnings, 0 informations`。

唯一skip仍是既有opt-in live browser cleanup pytest；三条warning仍来自`edgar`依赖弃用提示。

### 3.2 Coverage

Controller独立coverage：

- data：`workspace/tmp/.coverage-r02-controller-deepreview-fix2`；
- JSON：`workspace/tmp/coverage-r02-controller-deepreview-fix2.json`；
- `dayu/tools/web/web_tools.py`：`575/712`，`80.75842696629213%`；
- `dayu/tools/web/web_playwright_backend.py`：`485/539`，`89.98144712430427%`；
- 两个exact `--fail-under=80` gate均PASS。

### 3.3 Real Playwright smoke

独立新目录：`workspace/tmp/r02-web-owner-policy-aggregate-fix2-controller`。

- status=`passed`、exit_code=`0`；
- local=`11 passed`、failures=`0`、skips=`0`；
- `local-browser-playwright`与`local-filing-playwright`均真实执行；
- requests filing与Playwright filing分别完整读取`1,503,780` bytes；
- diagnostics schema=`web-diagnostics-v2`、revision=`2`；
- search cases保持4个diagnostic-only，external-limit=`0`没有替代local hard gate。

### 3.4 范围、docstring与README

- `git diff --check`与fix2 artifact whitespace：PASS；
- changed definitions=`60`，中文完整docstring issues=`0`；
- HEAD相对code/test changed paths精确为`dayu/tools/web/web_playwright_backend.py`和`tests/tools/web/test_web_tools_provider.py`；
- production新增行对`hasattr/getattr`、Issue 178、storage lifecycle、compatibility/fallback零命中；
- test新增行对`time.sleep`和真实`multiprocessing.get_context(...)`调用零命中；
- `dayu/tools/web/README.md`与`dayu/tools/README.md`不存在；本private cleanup不改变用户工作流、分层、配置或LLM-facing文本；`tests/README.md`职责也未命中，接受`no-update-with-evidence`。

## 4. Finding状态与下一入口

- `R02-AGG-DS-F01..F05`：fix implementation与Controller validation均通过，等待final re-review；
- `R02-AGG-CTRL-F01`：closed by implementation + Controller validation，等待final re-review；
- 没有新增ownerless residual、安全回归、deferred-scope leakage或production open question。

下一入口仅为AgentMiMo/AgentDS并发完整aggregate final re-review。两路review必须覆盖完整R02 aggregate、首轮五项fix、Controller发现与fix2生产清理、retained security、deferred/no-code scope和约1,200行新增typed test fake的过度耦合风险。Controller最终裁决前不得commit、completion或进入R03。
