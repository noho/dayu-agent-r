# WU-SEMANTIC-OWNERSHIP-01 / R02 aggregate deepreview final re-review finding fix（AgentCodex）

## 1. Gate 身份、结论与边界

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`；本文是同一 R02 aggregate deepreview final re-review finding fix，不是新 WU、slice 或 R03。
- 必读真源已完整读取：根 `AGENTS.md`、AgentDS final re-review、AgentMiMo final re-review，以及 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-controller-adjudication.md`。
- Controller disposition：只接受 `R02-AGG-RV-F01` 与 `R02-AGG-RV-F03`；拒绝 `R02-AGG-RV-F02` 与 `R02-AGG-RV-F04`。
- 结论：F01、F03 已按 Controller 缩窄边界修复并完成验证；F02、F04 没有实施。
- 本次窄 fix 的 code/test 路径只有：
  1. `dayu/tools/web/web_playwright_backend.py`；
  2. `tests/tools/web/test_web_tools_provider.py`。
- 唯一新增 artifact：本文。
- 未修改 control、既有 review artifacts、其它 production/tests/config/utils 或 README；进入本 gate 前已有的 Controller-owned control diff 与既有未跟踪 artifacts 均保持不变。
- 未 commit/push，未启动 Controller validation 之后的 re-review、completion 或 R03。

本文只证明 AgentCodex 窄 fix 完成，不表示 R02 accepted。下一入口仅为 Controller validation。

## 2. 第一性原理、root cause 与语义 owner

### 2.1 `R02-AGG-RV-F01`

Finding 动机成立。`_get_playwright_browser` 同时拥有 Playwright runtime 启动、browser launch、失败 cleanup 与 singleton publication。launch 失败后，local runtime 尚未发布到 `_PW_INSTANCE`，因此只有该 owner 的异常边界能够回收它；若 `pw.stop()` 又失败，原 launch warning 不能表达“cleanup 可能未完成”这一独立事实。

正确边界不是 caller、adapter、下游 fallback 或通用 diagnostic framework，而是 `_get_playwright_browser` 的 local cleanup handler。修复保持：

1. `pw.stop()` 仍为 best-effort；
2. stop 异常不遮蔽原 launch warning；
3. 返回值仍为 `None`；
4. `_PW_INSTANCE/_PW_BROWSER/_PW_BROWSER_KEY` 在失败路径仍不发布；
5. cleanup-failure debug 只包含稳定 stage 与异常类型。

### 2.2 `R02-AGG-RV-F03`

Finding 动机成立。lifecycle test 的 owner contract 是按 `(normalized channel, headless)` 创建、复用、re-key 与 cleanup；stealth flag 和其它 launch tuning 不是该 finding 的稳定 contract。修复只收窄测试断言，不修改 production launch 参数。

### 2.3 被拒绝 findings

- `R02-AGG-RV-F02`：未修改 `_get_playwright_browser` docstring；既有中文行内注释继续拥有 local runtime cleanup 意图说明。
- `R02-AGG-RV-F04`：未修改任何 `_Lifecycle*`、`_Recording*` 或 `_Fake*` class-level docstring。

## 3. 实现

### 3.1 F01 production owner 修复

在 `web_playwright_backend.py` 新增唯一稳定 stage 常量：

```text
browser_launch_failure_runtime_stop
```

`pw.stop()` 抛异常时只执行 `Log.debug`，消息形态为：

```text
Playwright runtime cleanup failed stage=browser_launch_failure_runtime_stop exception_type=<异常类型名>
```

实现只读取 `type(stop_exc).__name__`，不读取或格式化 `str(stop_exc)` / `repr(stop_exc)`，因此不记录异常正文，也不可能从 stop 异常正文带出 URL、header、credential 或 storage path。原 launch warning 与 production launch kwargs 保持不变。

### 3.2 F01 direct parameterized test

`test_get_playwright_browser_owner_cleans_local_runtime_without_publishing_failed_state` 继续覆盖两个 case：

- stop 成功：cleanup-failure debug 数量精确为 `0`；
- stop 异常：cleanup-failure debug 数量精确为 `1`，stage 与 `exception_type=RuntimeError` 精确匹配。

stop 异常正文包含 synthetic URL、Authorization header、credential 与 storage path 哨兵；测试对整个 `caplog.text` 断言这些片段全部不存在，而不是只检查目标 debug 单行。两个 case 都继续断言 `stop_calls == 1`、返回 `None`、三项 global 为 `None`。

### 3.3 F03 lifecycle test contract

`test_get_playwright_browser_owner_creates_reuses_and_replaces_by_key` 现在：

- 精确断言三次 launch，每个 launcher 恰好调用一次；
- 逐次精确断言 `(headless, normalized channel)` 为：
  - `(True, "chrome")`；
  - `(True, "chromium")`；
  - `(False, "chromium")`；
- 不再读取或断言 `args` 内容、stealth flag 或其它 browser launch tuning；
- create/reuse/re-key/close/stop/global publication 断言全部保留。

production 中 `launch_kwargs["args"] = ["--disable-blink-features=AutomationControlled"]` 没有修改。

## 4. 验证

所有 Python 命令均在 `source .venv/bin/activate` 后执行。

### 4.1 Direct、owner matrix、provider 与 aggregate

| gate | 结果 |
|---|---|
| accepted F01/F03 direct nodes | `3 passed in 0.74s` |
| 全部 11 个 qualified owner functions，参数化后 21 cases | `21 passed, 174 deselected in 0.58s` |
| 完整 provider：`test_web_tools_provider.py` | `194 passed, 1 skipped in 11.78s` |
| accepted aggregate coverage run | `330 passed, 1 skipped, 3 warnings in 13.83s` |

唯一 skip 仍是既有 opt-in live browser cleanup pytest；三条 warning 仍来自 `edgar` 依赖的弃用提示，不是 changed owner failure。

### 4.2 Exact coverage

canonical data：`workspace/tmp/.coverage-r02-aggregate-rereview-fix-codex`。

JSON：`workspace/tmp/coverage-r02-aggregate-rereview-fix-codex.json`。

| production file | covered / statements | exact percent | exact `--fail-under=80` |
|---|---:|---:|---|
| `dayu/tools/web/web_tools.py` | `575 / 712` | `80.75842696629213%` | PASS |
| `dayu/tools/web/web_playwright_backend.py` | `486 / 540` | `90.0%` | PASS |

### 4.3 Pyright、whitespace、allowed paths 与 source scans

- full `python -m pyright`：`0 errors, 0 warnings, 0 informations`；仅提示存在较新 pyright 版本。
- `git diff --check`：PASS。
- code/test allowed-path exact set：`actual=2`，`extras=[]`，未跟踪 code/test/config/utils 路径为空。
- changed-definition AST audit：`changed_definitions=3 docstring_deferred_log_issues=0`。
- 三个 definitions 均有中文概览与完整 `Args/Returns/Raises`；没有实施 F02/F04。
- deferred-scope scan 对三个 changed definitions 检查 Issue 178、R03、authorization framework、policy DSL、capability token、storage refresh/retention/lifecycle/TTL/publication/reconcile：零命中。
- cleanup log AST/source audit确认：稳定 stage 常量唯一赋值且被 owner 使用，只读取 `type(stop_exc).__name__`，不存在 `str(stop_exc)`、`repr(stop_exc)` 或直接 f-string 异常正文。

审计器首次错误地要求 stage 字面量直接出现在函数体内，忽略了 owner 使用模块级稳定常量，产生一次 `cleanup_stage_missing` 假阳性。修正口径为“常量唯一赋值 + owner 引用”后 `issues=0`；该校验器错误没有导致任何源码修改。

### 4.4 新目录 real Playwright smoke

运行前确认目标目录不存在，随后执行：

```text
python utils/smoke_web_ci.py \
  --output-dir workspace/tmp/r02-web-owner-policy-aggregate-rereview-fix-codex \
  --external-limit 0 \
  --include-playwright \
  --request-timeout 20 \
  --tool-timeout-budget 60 \
  --run-label r02-web-owner-policy-aggregate-rereview-fix-codex
```

结果：`status=passed`、`exit_code=0`、local `11 passed`、failures=`0`、skips=`0`。`local-browser-playwright` 与 `local-filing-playwright` 均真实执行；4 个 search cases 保持 accepted `diagnostic_only`，`external-limit=0` 没有替代 local hard gate。

summary：`workspace/tmp/r02-web-owner-policy-aggregate-rereview-fix-codex/summary.json`。

对该目录 22 个 diagnostic JSON（排除独立显式空 read-input fixture）执行敏感值与 deferred lifecycle scan，结果 `sensitive_or_deferred_issues=0`。

## 5. README decision

- `tests/README.md`：`no-update-with-evidence`。本次只强化已有 Web provider owner test 的断言，没有新增测试层级、运行方式、marker、环境变量或维护规则。
- 根 `README.md`：`no-update-with-evidence`。没有安装、初始化、CLI/Web/WeChat 入口、默认输出、日志定位、工作区位置、用户工作流或排障变化。
- `dayu/README.md`：`no-update-with-evidence`。没有 UI / Service / Host / Engine 分层或装配变化。
- `dayu/tools/web/README.md` 与 `dayu/tools/README.md`：不存在。

上述 README 均保持零 diff。

## 6. Finding 状态、residual 与 handoff

- `R02-AGG-RV-F01`：AgentCodex 状态=`已修复`，等待 Controller validation。
- `R02-AGG-RV-F03`：AgentCodex 状态=`已修复`，等待 Controller validation。
- `R02-AGG-RV-F02`、`R02-AGG-RV-F04`：按 Controller rejection 保持未实施。
- 没有新增 ownerless residual、安全回归、deferred-scope leakage 或 production open question。
- artifact path：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-rereview-fix-codex.md`。
- 下一入口仅为 Controller validation；AgentCodex 不自行启动 re-review、completion 或 R03。
