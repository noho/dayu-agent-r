# WU-SEMANTIC-OWNERSHIP-01 / R02 aggregate deepreview Controller adjudication

## 1. Gate 结论

- AgentMiMo：`PASS`，finding=`0`。
- AgentDS：`PASS`，finding=`5`（1 medium、4 low），均为 owner-level test-contract coverage gap；没有生产所有权漂移、安全回归或 deferred scope leakage。
- Controller：接受 `R02-AGG-DS-F01..F05` 全部五项；不得按严重性延后。
- 下一 gate：AgentCodex aggregate deepreview fix；当前只授权测试与 fix artifact，不授权生产代码修改。

该裁决不接受 R02、不创建 completion、不进入 R03，也不授权 Issue 178 replacement lifecycle、proxy credential schema或统一 tool authorization framework。

## 2. Finding disposition

### `R02-AGG-DS-F01` — accepted

`_get_playwright_browser` 是 browser lifecycle owner，首次创建、同 key 缓存、key 变化关闭旧实例并重建、初始化异常不发布半成品状态均应由直接 owner test 锁定。当前所有测试注入 callable而绕过实际函数，coverage 证据成立。

修复要求：直接调用真实 `_get_playwright_browser` 函数，以 typed fake Playwright collaborators替换外部 runtime；不得依赖 live Chromium，也不得测试私有实现偶然顺序之外的 contract。至少覆盖首次创建、同 key复用、channel/headless key变化 cleanup+recreate和失败后状态。

### `R02-AGG-DS-F02` — accepted with owner correction

原 finding 把 URL normalizer 描述为“安全拒绝第一道防线”不准确。业务安全 userinfo 拒绝的唯一 owner 是 `WebEgressPolicy.authorize_http_target`；`_normalize_url_for_http` 只拥有 scheme/netloc validation和可传输 ASCII/IDNA/userinfo quoting。因此不允许在 normalizer 中新增 security rejection或改变生产行为。

修复要求：

1. 为 `_normalize_url_for_http` 直接覆盖缺 scheme/netloc/hostname、IDNA和 userinfo quoting等其自身 contract；
2. 在 `WebEgressPolicy` owner test中直接断言 userinfo URL 被拒绝，证明 LLM/tool输入不会把 credential带入 HTTP路径；
3. 不在下游调用者增加重复 userinfo blacklist或 fallback。

### `R02-AGG-DS-F03` — accepted

Browser `text_chars` 是 R02 拆分后的核心 child-budget contract。现有 tests覆盖 DOM超限，但没有直接触发 `text_exceeded` / `text_chars > limit` 路径。

修复要求：用 synthetic page直接调用 `_materialize_bounded_page_projection`，让 DOM在界内而 text预检或实际值超过上限，并断言 typed `_BROWSER_TEXT_TOO_LARGE_REASON`；不得用任意错误文本或下游映射替代 owner assertion。

### `R02-AGG-DS-F04` — accepted

R02 修改了 route egress policy消费边界；当前仅覆盖 policy reject abort，未覆盖 resource-type abort和allowed continue。三个分支共同定义 browser route owner contract。

修复要求：直接调用 `_route_handler_abort_resources`，分别断言 image/font/media abort、allowed document continue和既有 denied URL abort；fake只记录 route action，不重算 policy。

### `R02-AGG-DS-F05` — accepted

`_run_playwright_worker_process` 是 browser子进程取消/超时/result-drain fencing owner，`_close_playwright_browser` 是进程内 browser/runtime singleton cleanup owner。coverage 显示 cancellation、无结果/超时和 cleanup异常路径未被直接验证；这些是 Host强约束取消向 Web worker落地的关键边界。

修复要求：以 fake multiprocessing context/process/queue和 cancellation token直接调用 owner；覆盖 cancellation terminate+`CancelledError`、无结果退出、timeout、finally cleanup。另直接覆盖 `_close_playwright_browser` 在 close/stop成功和抛异常时都清空三项全局状态。不得 sleep、启动真实子进程或通过 wrapper/下游结果间接断言。

## 3. Fix boundary

唯一预授权 test path：

- `tests/tools/web/test_web_tools_provider.py`

`tests/README.md` 仅在读取其职责后、确有测试工作流/contract文档变化时允许更新；若只是补齐既有 contract 的 owner tests，应记录 no-update-with-evidence。

唯一新增 artifact：

- `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-aggregate-deepreview-fix-codex.md`

不授权修改 `dayu/**`、`utils/**`、config、其它 tests/README或既有 artifacts。若 direct owner test暴露生产行为与 accepted contract不符，AgentCodex必须停止回 Controller并给直接 failing evidence，不得自行扩展生产 allowlist。

## 4. Mandatory validation

AgentCodex 必须记录：

1. 每个 accepted finding 与新增 test qualified name的一一映射；
2. focused new-node tests、完整 `test_web_tools_provider.py`、§14.4 aggregate matrix；
3. `web_tools.py` 与 `web_playwright_backend.py` corrected coverage JSON及逐文件 `--fail-under=80`；
4. full pyright、`git diff --check`、authored-path/production-zero-diff scans、中文 docstring audit；
5. deterministic local real Playwright smoke，确认 test新增没有污染 module globals/runtime；
6. `tests/README.md` updated或no-update-with-evidence。

AgentCodex 不 commit/push、不更新 control、不启动 re-review/completion/R03。Controller validation 后必须由 MiMo/DS 对完整 aggregate target与五项 closure并发 re-review。
