# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E S2 implementation — AgentCodex

## Scope

- Gate：R3-E Slice S2 implementation only。
- 已实施：Web resource budget typed owner、provider 完整配置解析、有界 fetch/search HTTP wire/codec/warmup、Playwright DOM/text preflight、challenge decision/fallback owner、DuckDuckGo response shape outcome 与稳定工具失败投影。
- 未实施：S3 diagnostic schema v2、storage-state lifecycle、smoke oracle；S4 Documents bounded source；Host/Engine/Fins/tool-security；任何 aggregate gate。
- 第一性原理结论：修改动机成立。原实现直接整包解压、warmup 非流式、Playwright 在 preflight 前生成完整 HTML、challenge boolean 与 caller status allowlist 双真源、DuckDuckGo 未知 HTML 静默返回空成功，均有当前代码直接证据。

## Changed files

- `dayu/tools/web/web_resource_budget.py`（新增）
- `dayu/tools/web/provider.py`
- `dayu/tools/web/web_fetch_orchestrator.py`
- `dayu/tools/web/web_playwright_backend.py`
- `dayu/tools/web/web_challenge_detection.py`
- `dayu/tools/web/web_search_providers.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_tool_projection_text.py`
- `utils/diagnose_web_access.py`（controller clarification 授权的窄幅 public contract propagation）
- `dayu/config/README.md`
- `tests/tools/web/test_web_tools_provider.py`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-implementation-codex.md`（本 artifact）

未修改生产范围外的 S3/S4/Host/Engine/Fins 文件；未 stage、commit 或 push。

## Semantic owners

1. `WebResourceBudget` 是 `wire_body_bytes`、`decoded_body_bytes`、`warmup_body_bytes`、`browser_dom_chars`、`browser_text_chars`、`diagnostic_error_chars`、`diagnostic_events` 的唯一 typed 真源；构造期拒绝 bool、非整数和非正整数。
2. `provider.py::_resource_budget_default` 只拥有 provider JSON 到完整 typed budget 的边界：整个 object 缺失才使用完整默认；object 存在时缺字段、未知字段、bool 或非正整数全部 fail fast。
3. `web_fetch_orchestrator.py` 拥有 wire/body/codec/warmup 消费：wire 按 chunk 计数；gzip、zlib deflate、raw deflate 使用带 `remaining + 1` max output 的 `decompressobj`；zstandard 仅使用有界 `stream_reader.read(size)`；每层输出和最终 identity body 都受 decoded cap。三个固定 search provider endpoint 复用同一 materialization owner，不自行实现第二套 body cap。
4. `web_playwright_backend.py` 拥有 browser DOM/text cap：一次 bounded TreeWalker preflight 先于完整 HTML/text 投影；preflight 与实际投影后均复核长度；工具边界稳定投影 `browser_dom_too_large` / `browser_text_too_large`。
5. `web_challenge_detection.py` 拥有 `none` / `suspected` / `confirmed` decision、封闭 evidence class 与 `challenge_fallback_action`；caller 不再以 HTTP status 二次裁决 confirmed fallback。
6. `web_search_providers.py` 拥有固定 Tavily/Serper/DuckDuckGo provider response lifetime、DuckDuckGo known result、explicit no-results、malformed threshold 和 challenge/login shape；shape drift 抛 `WebSearchProviderResponseError`，resource 超限抛 `WebSearchProviderResourceError`，`web_tools.py` 分别投影 `search_provider_response_invalid` 与 `response_body_too_large`。

## Implementation decisions

- HTTP error response 在 `raise_for_status()` 前先执行有界 body materialization，避免 error snippet 读取尚未受限的 response body。
- `Content-Length` 只用于早拒绝；最终仍以 raw stream 实读 wire bytes 为准。
- warmup 改为 `stream=True`，最多读取 `warmup_body_bytes`，随后由 response lease 关闭。
- Tavily、Serper 与 DuckDuckGo 固定 endpoint 都改为 `stream=True`，显式只协商 `gzip, deflate`，在 JSON/HTML 解析前复用同一 wire/decoded materialization owner，并由 response context 在成功、HTTP error、shape error和 resource error 上关闭。它们显式 `allow_redirects=False`；固定 connector 不在 search module 内建立第二套 redirect/egress 语义。
- brotli Python API 不提供可传入 `remaining + 1` 的 bounded output 参数，因此旧整包 `brotli.decompress` 路径已删除，`br` 明确为 unsupported，且生产 `Accept-Encoding` 不再声明 `br`。当前只主动协商 `gzip, deflate`；zstd 仅在服务端声明且 `zstandard.stream_reader` 可用时有界解码。没有 whole-body fallback。
- Playwright preflight script 只使用 `document.createTreeWalker()` 和有界 counters，不包含 `page.content()`、`outerHTML`、`innerHTML`、`textContent`、`innerText`。preflight 通过后才允许一次完整 HTML 和完整文本读取；动态变大由实际长度二次拒绝，Markdown 投影后再检查 text cap。
- challenge 的强 vendor token/endpoint 可单独 confirmed；宽泛正文、普通基础设施 header 或 vendor header 单信号只 suspected；宽泛正文与 error status/vendor gate header/第二独立正文信号组合才 confirmed。confirmed + HTTP 500 同样只调用一次 browser fallback。
- DuckDuckGo parser 检查全部 `div.result` 后才按 `max_results` 投影；0 有效项或 `malformed_count * 2 > container_count` 是 shape drift；50% malformed 仍允许丢弃坏项；唯一 `.no-results` 且文本精确等于 `No results.` / `No more results.` 才是空成功；challenge/login/anomaly shape 覆盖 result/no-results。
- Controller clarification 将 `utils/diagnose_web_access.py` 两处旧 `challenge_detected` consumer 裁决为 S2 challenge public contract propagation，而非 S3 work。实现只让既有 v1 布尔投影从 `challenge.decision is BotChallengeDecision.CONFIRMED` 派生；未改字段名、diagnostic schema、storage-state、smoke oracle 或其它 S3 逻辑。

## Tests, pyright and diff-check

### Passed

- 聚焦命令：`62 passed, 2 skipped, 54 deselected`。两个 skip 分别为当前环境缺少可选 `zstandard` 与手工 live browser cleanup smoke。
- 完整 `tests/tools/web/test_web_tools_provider.py -q`：`116 passed, 2 skipped`。
- 受 controller clarification 影响的只读 diagnostic 回归：`pytest tests/tools/web/test_diagnose_web_access.py -q -k 'challenge or egress or redirect'`，`2 passed, 21 deselected`。
- 覆盖率等价运行（测试参数与三个 dotted coverage target 保持不变，额外设置 `PYTEST_PLUGINS=numpy,multiprocessing.connection` 只用于避免本机 pytest-cov source discovery 重复加载 NumPy/stdlib multiprocessing）：`116 passed, 2 skipped`；`web_resource_budget.py 100%`、`web_challenge_detection.py 90%`、`web_search_providers.py 87%`，总计 `89%`。
- 全仓 `pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 新增未跟踪 artifact 的 `git diff --no-index --check`：无 whitespace error。

### Coverage command environment note

用户给定的无环境前缀 dotted-module coverage 命令连续两次在 test collection 前失败：pytest-cov source discovery 先导入 `dayu.tools.web`，随后收集阶段再次加载 NumPy C extension，报 `ImportError: cannot load module more than once per process`。直接导入 numpy/pandas、普通 pytest 与 directory-source coverage 均正常。只预加载 NumPy 会进一步暴露 multiprocessing function identity 重载；同时预加载 `numpy,multiprocessing.connection` 后，同一测试参数和三个 coverage target 全部通过。未修改生产 import seam、未添加 lazy import 或 coverage 特例。

### Controller clarification and pyright closure

- 初次全仓 `pyright` 精确暴露 `utils/diagnose_web_access.py` 两处旧 `challenge.challenge_detected` consumer。
- Controller 随后澄清：这两处属于 S2 challenge public contract propagation，并窄幅授权修改该脚本；不是 S3 diagnostic schema/storage-state/smoke work。
- 两处现均以 `challenge.decision is BotChallengeDecision.CONFIRMED` 产生原有 v1 布尔字段。没有恢复 compatibility property，没有 `getattr` fallback，也没有改变任何 S3 schema 或下游 classifier。
- 修复后全仓 `pyright` 通过：`0 errors, 0 warnings, 0 informations`。

## README decision

- `dayu/config/README.md`：已更新。`providers["web-tools"].config.resource_budget` 已对外生效，README 记录完整七字段示例、整体缺失默认与 object 内 fail-fast 规则。
- `tests/README.md`：不更新。没有新增测试层级、公共测试 harness 或运行入口；且不在本 slice 允许文件中。
- 根 README / `dayu/README.md`：不触发；未改变用户入口、安装、CLI 工作流或分层装配关系。

## Propagation audit

规定扫描的命中分类：

- `gzip.decompress` / `brotli.decompress` / `zstd.*decompress`：生产和测试均无命中；旧无界整包路径已删除。
- `page.content()`：生产仅命中 `web_playwright_backend.py` 的 post-preflight 完整投影，以及 `web_tools.py` 对该顺序的 docstring；测试命中 forbidden-token 反向断言。超限 preflight 测试证明 `content()` 与 full text extraction 均零调用。
- `innerText`：生产仅命中 post-preflight 的 `_FULL_PAGE_TEXT_SCRIPT`；不在 `_BUDGETED_DOM_METRICS_SCRIPT` 中。测试逐项断言 preflight script 不含该 token。
- `outerHTML` / `innerHTML` / `textContent`：仅测试 forbidden-token 断言命中，生产无命中。
- `challenge_detected.*http_status`：无命中；confirmed fallback 不再依赖旧 status set。
- `div.result`：只命中严格 DuckDuckGo parser 的 container 与 snippet selector；parser 检查全部 container 和 malformed ratio。
- `resource_budget`：命中新增 owner、provider parse、fetch/search HTTP、warmup/probe/browser 显式传播、README 完整示例与 owner tests，均为预期。

Controller clarification 后，两处 producer 现只从 `BotChallengeDecision.CONFIRMED` 派生既有 v1 diagnostic boolean；下游 schema/smoke 命中保持原状且未在 S2 修改。未发现新的第二套 challenge decision 或无界 codec fallback。HTTP response lease 仍包围 warmup/probe/main；固定 search connector response 使用 `stream=True`、共享 body owner、禁用自动 redirect，并在 context 内关闭；新增超限/unsupported 路径均在 lease/context 内退出并关闭。

## Residual risks

1. Chromium 在 preflight 前已构造内部 DOM；TreeWalker 消耗 CPU，动态页面可在 preflight 后变大。二次长度检查只阻止超限值跨进程投影，不能消除浏览器内部峰值。Owner：Web Playwright backend；destination：后续 browser sandbox/resource-lane WU。
2. DuckDuckGo 是外部 HTML contract；严格 fail closed 会在 provider 改版时短期降级。Owner：Web search provider；destination：后续 provider selector/shape 更新，不允许 loose parse。
3. brotli 当前明确 unsupported 且不主动协商；如果未来依赖提供可限制单次输出的 streaming API，应由 Web codec owner新增并重新走 review，不得恢复整包解压。
4. `diagnostic_error_chars` / `diagnostic_events` 已进入完整 typed config，但实际 diagnostic projection 消费属于 S3，当前未越界实施。

## Stop status

**COMPLETE — stopped at S2 implementation artifact.**

Controller clarification 已完成闭环；S2 实现、owner tests、覆盖率、全仓 pyright、diff-check 与 propagation audit 均完成。没有 blocking question。未进入 S3/S4/aggregate，未 stage、commit 或 push。
