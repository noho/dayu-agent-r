# WU-TOOLS-01-F02 Web CI Diagnostics Plan

## 元数据

- Work unit：`WU-TOOLS-01-F02 Web CI diagnostics pipeline migration`
- 类型：issue-backed feature follow-up
- 当前 gate：plan only
- 日期：2026-06-09
- plan gate 观察到的分支：`phase/wu-tools-01-f02`
- artifact path：`docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`
- 设计真源：`docs/host/design.md`；`docs/engine/design.md`
- 总控真源：`docs/host/issues-implementation-control.md`
- goal confirmation 真源：`docs/reviews/wu-tools-01-f02-goal-confirmation-controller.md`
- Issue owner：GitHub Issue 120
- 当前 gate 约束：本 gate 只创建 plan artifact；不得 implementation、review、fix、commit、push、PR、关闭 residual risk 或修改 controller artifact。

## 目标

将 OLD Web live diagnostics pipeline 迁移到当前仓库 `utils/`，使开发者能显式 opt-in 运行单 URL 与批量 Web live diagnostics。

迁移后的 pipeline 必须在同一轮诊断中采集：

- raw `requests` prepared headers 与实际 GET 结果；
- 通过当前工具契约调用的当前仓库 `fetch_web_page` 结果；
- 可选 Playwright browser navigation path；
- 可选 Playwright storage state 输入 / 输出；
- Playwright network request summary；
- 单 URL comparison bucket 与批量 summary。

## 动机

该动机成立，严重性没有被高估。

当前 deterministic Web tool tests 能证明 provider / adapter / mocked requests / mocked Playwright fallback 的受控行为，但不能证明真实站点、浏览器安装、storage state、反爬 challenge、跳转、编码、地区差异、网络失败或 provider API key 可用性。F02 应提供可重复采证的 opt-in diagnostics pipeline，为后续 Web tools 优化和 F03 Web smoke 提供证据。

F02 不是 Web smoke gate。本 work unit 只迁移诊断与分桶能力；`WU-TOOLS-01-S5-R2` 在 F02 后仍保持 `deferred/open`，由 WU-TOOLS-01-F03 生成 Web smoke 后关闭或转移。

## 成功信号

- 当前 repo 存在 `utils/diagnose_web_access.py`，支持单 URL 与批量 URL 模式。
- 当前 repo 存在 `utils/diag_web.sh`、`utils/diag_web_batch.sh`、`utils/web_ci_urls.jsonl`。
- 单 URL 模式可输出包含 `requests_profile`、`fetch_web_page_profile`、可选 `playwright_profile` 与 `comparison_bucket` 的 JSON artifact。
- 批量模式可读取 JSONL 或 TXT URL corpus，并写出 `corpus.normalized.jsonl`、per-url diagnostics JSON、`results.jsonl`、`summary.json` 与 `summary.md`。
- `fetch_web_page` 通过当前 `ToolDefinition.callable` / current outcome contract 调用，不恢复 OLD `ToolRegistry`、OLD truncation manager、OLD `fetch_more` 或 OLD `dayu.web`。
- 缺少 live network、Playwright package/browser、API key 或 storage state 时输出清晰 diagnostic / skip-safe evidence，不进入普通 deterministic CI。
- 默认 tests 使用 mocked/local deterministic evidence，不做 live network 或 real browser 请求。

## 非目标

- 不定义 Web smoke pass/fail/skip gate。
- 不关闭 `WU-TOOLS-01-S5-R2`。
- 不把 live network 或 real browser diagnostics 放入默认 pytest、pyright 或普通 CI workflow。
- 不恢复 OLD `ToolRegistry`、OLD truncation manager、OLD `fetch_more` 或 OLD `dayu.web` UI。
- 不重写 Web search / fetch / Playwright production behavior。
- 不修改 Host public contract、Engine public contract、ToolRuntime contract、durable schema、EventLog、Run/Attempt 状态机或默认 CI workflow。
- 不把单个 live 站点偶发失败判定为 production regression；F02 只输出证据和分类。

## 范围边界

后续 implementation 允许修改：

- `utils/diagnose_web_access.py`
- `utils/diag_web.sh`
- `utils/diag_web_batch.sh`
- `utils/web_ci_urls.jsonl`
- `tests/tools/web/test_diagnose_web_access.py` 或等价 focused deterministic test
- `tests/README.md`，仅当实现新增稳定测试入口或诊断命令约定且属于该 README 职责范围时
- 必要的当前 CI / diagnostics 辅助代码，仅限直接代码证据证明可增强 opt-in diagnostics 且不改变默认 CI behavior 的情况

当前计划不修改 production Web tools。若 implementation 证明当前 `fetch_web_page` 无法通过 current contract 调用，只允许提出最小 callable boundary 修正；若该修正需要 Host/Engine/ToolRuntime public contract 或 Web production behavior 实质变更，必须停止并报告 Controller。

Controller artifacts 不是 implementation 目标；除非发现事实性错误并先报告 Controller，否则不得修改 `docs/host/issues-implementation-control.md` 或 `docs/reviews/wu-tools-01-f02-goal-confirmation-controller.md`。

## 设计真源对齐

Host 对齐：

- Host 仍是 Session / Run / Attempt / EventLog / ToolRuntime governance 真源。
- F02 不写 Host event，不创建 Host diagnostic truth，不改变 ToolRuntime accept barrier。
- 诊断脚本是 opt-in developer utility，不是 Service / Host / Engine workflow。

Engine 对齐：

- Engine 在真实 run 中只消费 `tool_schemas` 与 `ToolExecutor`。F02 不新增 Engine 入口，不改变 Engine tool loop。
- 诊断脚本可作为 developer utility 调用 current tool callable 并记录 current outcome；它不得伪装为一次 Engine run。

ToolsDiscovery / runtime 对齐：

- 当前 Web tools 由 `dayu.tools.web.provider.discover_tools` 通过 `ToolsDiscoveryProviderSpec` 暴露为 current `ToolDefinition`。
- 诊断必须复用 current provider/callable boundary，或复用 current `register_web_tools` + collector/adapter 路径；不得导入 OLD `dayu.engine.tool_registry`。

LLM-facing 语义对齐：

- diagnostic JSON、summary Markdown、错误说明与 hint 未来可能进入 LLM 上下文，因此必须业务可读、自解释。
- 不得用裸 `event_id`、`payload_ref`、digest、cursor 或 tool call id 代替 URL、HTTP status、fetch backend、challenge signals、error code、storage state 使用情况或 next action。
- 不得把内部治理状态伪装成业务事实。`browser_only_success` 这类 bucket 只能表示访问路径对比结果，不表示网页内容中的业务事实为真。

## 第一性原理判断

根问题是“真实网页访问失败时缺少可复现的同源证据”，不是 production Web code 缺一个入口。

当前 `fetch_web_page` 已具备 requests 主路径、Playwright fallback、storage state lookup、challenge detection 与 diagnostics payload。F02 缺的是 opt-in 脚本，把 raw requests、current fetch、独立浏览器观察和 URL corpus 汇总到同一份证据里。

因此正确方案是窄范围迁移 OLD diagnostics pipeline，并把 OLD imports 改为 current contract adapter。更大的 Web smoke framework、Host/Engine contract change、production fetch redesign 或 default live CI job 都会解决不同问题，超出 Issue 120 / F02。

## 直接代码证据

当前 repo 证据：

- 当前 repo 没有 `utils/diagnose_web_access.py`、`utils/diag_web.sh`、`utils/diag_web_batch.sh`、`utils/web_ci_urls.jsonl`。
- `dayu/tools/web/provider.py` 通过当前 `ToolsDiscoveryProviderSpec` 与 `ToolDefinition` 暴露 `search_web` 和 `fetch_web_page`。
- `dayu/tools/web/web_tools.py` 存在 `register_web_tools(...)` 与 `_create_fetch_web_page_tool(...)`；fetch closure 接收 `url` 与可选 `BatchToolExecutionContext`。
- `fetch_web_page` 已覆盖 URL safety、requests、warmup、content-type probe、content conversion、Playwright fallback、storage state path、storage-state cookies、challenge detection 与 diagnostic logging。
- `tests/tools/web/test_web_tools_provider.py` 覆盖 current provider discovery、current outcome projection、private URL policy、Playwright cancellation projection、truncate spec 与 forbidden OLD imports。
- `tests/README.md` 明确 `tests/tools/web/` 的 Web provider tests 必须 deterministic，通过 monkeypatch / fixture 控制搜索 provider、requests 主路径与 Playwright fallback，不做 live network 请求。

OLD 证据：

- OLD `/Users/leo/workspace/dayu-agent/utils/diagnose_web_access.py` 已实现单 URL / 批量 diagnostics、raw requests profile、fetch tool profile、Playwright profile、storage state、comparison buckets、`results.jsonl`、`summary.json` 与 `summary.md`。
- OLD `diag_web.sh` 与 `diag_web_batch.sh` 调用 `python -m utils.diagnose_web_access`，默认使用 headed browser 与 storage-state 目录。
- OLD `web_ci_urls.jsonl` 覆盖 foreign/china news、finance、government、regulator 与 exchange 代表性站点。
- OLD 脚本导入 OLD `dayu.engine.tool_registry.ToolRegistry`、OLD `dayu.engine.tool_errors.ToolBusinessError` 与 OLD `dayu.engine.tools.web_tools` 私有入口；这些边界不能照搬进当前 repo。

## 影响文件 / 模块

本 gate 创建：

- `docs/host/wu-tools-01-f02-web-ci-diagnostics-plan.md`

后续 implementation 计划修改：

- `utils/diagnose_web_access.py`
- `utils/diag_web.sh`
- `utils/diag_web_batch.sh`
- `utils/web_ci_urls.jsonl`
- `tests/tools/web/test_diagnose_web_access.py` 或等价 focused deterministic test
- `tests/README.md`，仅按 README 更新触发与职责边界按需更新

不计划修改：

- `dayu.host`
- `dayu.engine`
- `dayu.service`
- `dayu.ui`
- default CI workflow files
- `dayu/tools/web/` production code，除非 implementation 以直接证据证明存在最小 callable-boundary defect

## Contract / Schema / State-Machine / Public Interface 变化

Host / Engine / ToolRuntime：

- 无 contract 变化。
- 无 state-machine 变化。
- 无 durable schema 变化。
- 无 EventLog 或 HostEvent 变化。

Utility CLI interface：

- `python -m utils.diagnose_web_access --url <url> [options]`
- `python -m utils.diagnose_web_access --url-file <path> [options]`
- `utils/diag_web.sh <URL> [extra args...]`
- `utils/diag_web_batch.sh <URL file> [extra args...]`

Diagnostic JSON 是 utility artifact，不是 Host/Engine public contract，但需要足够稳定供 F03 消费。最小字段：

- 顶层字段：
  - `schema_version`：字符串，计划值 `web-diagnostics-v1`
  - `generated_at`：ISO 时间字符串
  - `url`：输入 URL
  - `comparison_bucket`：访问路径对比分桶
  - `requests_profile`：raw requests 证据对象
  - `fetch_web_page_profile`：current fetch 工具证据对象
  - `playwright_profile`：浏览器证据对象；跳过时包含 `skipped=true`
- `requests_profile`：
  - `normalized_url`
  - `prepared_headers`，敏感 header 值必须脱敏
  - `timeout_seconds`
  - `result`，成功时包含 status/final URL/headers/text prefix，失败时包含 error type/message/elapsed seconds
- `fetch_web_page_profile`：
  - `skipped` 可选布尔值
  - `ok`，采样时必填
  - 成功字段：`elapsed_seconds`、`title`、`final_url`、`fetch_backend`、`content_prefix`
  - 失败字段：`elapsed_seconds`、`error_code`、`message`、`hint`、`next_action`、`http_status`、`diagnostics`
- `playwright_profile`：
  - `skipped` 可选布尔值
  - `ok`，采样时必填
  - browser/channel/headed/timeout
  - navigation status/final URL/title/user-agent
  - main document request/response summaries
  - page text/html bounded prefixes and lengths
  - challenge detected/signals
  - storage state input/output path，只记录路径，不内联内容
  - bounded network request summaries

Batch outputs：

- `corpus.normalized.jsonl`：规范化输入 URL entries。
- `results.jsonl`：每个 URL 一行，包含输入 metadata、diagnostic path、comparison bucket、路径成功布尔值、status/error 字段、challenge signals 与 final URLs。
- `summary.json`：按路径与 bucket 统计。
- `summary.md`：简洁、业务可读的汇总。

F03 最小稳定 utility schema 子集：

- 顶层 `schema_version`、`url`、`comparison_bucket` 必须稳定存在。
- `requests_profile`、`fetch_web_page_profile`、`playwright_profile` 每个被采样路径必须稳定提供 `sampled`、`ok`、`elapsed_seconds`、`status` 与 `error` 字段；未采样路径必须提供 `sampled=false` 与业务可读 skip reason。
- `results.jsonl` 每行必须稳定提供 `url`、`diagnostic_path`、`comparison_bucket`、per-path `sampled` / `ok` / `status` / `error` 摘要字段。
- F02 只保证上述 utility schema 子集；F03 若消费更多字段，必须在 F03 plan 中重新声明依赖字段。schema mismatch 的 skip/fail 策略留给 F03 裁决，不在 F02 中定义。

## 实现决策

1. 通过 current tool contract 调用 `fetch_web_page`。

   CLI 入口保持同步函数模型。只在 current async `ToolDefinition.callable` 边界使用 `asyncio.run(...)`；Playwright profile 继续用 `playwright.sync_api.sync_playwright`，并封装在 optional browser helper 内部。F02 不支持嵌入已有 event loop 的 API；若未来需要从 async 测试或服务内调用 diagnostics，必须作为后续 work unit 增加显式 awaitable 入口。

   实现 `_build_fetch_web_page_definition(...)`，使用 `dayu.tools.web.provider.discover_tools(spec)`，或等价的 `dayu.tools.web.discover_tools(spec)` provider entry。该函数返回 `ToolsDiscoveryProviderOutput`，diagnostics 只读取 `ToolsDiscoveryProviderOutput.definitions`；不得使用 `dayu.runtime.tools_discovery.discover_tools(...)` 聚合入口，避免把 runtime aggregate discovery 的返回结构和 provider metadata 引入本 utility。

   `ToolsDiscoveryProviderSpec.config` 使用当前 `WebToolsConfig` 字段名与 JSON value 类型：

   | CLI 来源 | `WebToolsConfig` / `spec.config` 字段 | JSON value 类型 | 规则 |
   |---|---|---|---|
   | 无 CLI flag | `provider` | string | 默认不写入 config，使用 current 默认 `auto`；diagnostics 不暴露 search provider 选择。 |
   | `--request-timeout <seconds>` | `request_timeout_seconds` | number | 正数，传入 `float`。 |
   | 无 CLI flag | `max_search_results` | number | 默认不写入 config，使用 current 默认 `20`；fetch diagnostics 不消费 search 结果数。 |
   | `--fetch-truncate-chars <chars>` | `fetch_truncate_chars` | number | 正整数，传入 `int`。 |
   | `--allow-private-network-url` | `allow_private_network_url` | boolean | flag 存在传 `true`；不存在可省略或传 `false`，优先省略以保留 current 默认。 |
   | `--playwright-channel <channel>` | `playwright_channel` | string 或 null | 非空字符串传入 string；显式空值或 disable channel 时传 `null`；未传则省略并使用 current 默认 `chrome`。 |
   | `--storage-state-dir <path>` | `playwright_storage_state_dir` | string | 非空路径传入 string；未传则省略并使用 current 默认空字符串。 |

   从返回 definitions 中选择 name 为 `fetch_web_page` 的 `ToolDefinition`，再用 `asyncio.run(...)` 调用：

   - `ToolCallRequest(tool_call_id="diagnose-fetch-web-page", name="fetch_web_page", arguments={"url": url}, ...)`
   - `BatchToolExecutionContext(run_id="diagnose-web", session_id="diagnose-web", iteration_id="diagnose-web", timeout_seconds=tool_timeout_budget, cancellation_token=...)`

   记录 `ToolCompletedOutcome` 与 `ToolFailedOutcome`。该路径不恢复 OLD `ToolRegistry`，并保留 current argument validation、current outcome projection、execution context injection 与 provider config parsing。

   在 `utils/diagnose_web_access.py` 内定义私有 `_DiagnosticCancellationToken`，实现 current `CancellationToken` protocol：

   - `is_cancelled() -> bool` 恒返回 `False`。
   - `cancel_reason() -> str | None` 恒返回 `None`。
   - `requested_at() -> datetime | None` 恒返回 `None`。

   该 token 只表达 F02 diagnostics 的 never-cancelled semantics，不连接 Host 取消状态，不创建新的 cancellation public contract。

2. raw requests diagnostic 与 production fetch 保持分离。

   raw requests profile 只用于对照证据。headers 选择规则固定为：

   - 优先复用 current Web helper，前提是 implementation 可以通过当前已有模块边界完成，且不新增 production public export、不扩大 production public surface。
   - 若复用 current helper 需要新增 production export、改动 Web production helper 可见性或引入 facade，则不得修改 production code；改用本地 diagnostic headers。
   - 使用本地 diagnostic headers 时，单 URL JSON 与 summary 必须标注 `raw_requests_header_source="diagnostic_local"` 或等价字段，并用业务可读文本说明 raw requests 是 `raw diagnostic path`，不是 `fetch_web_page` production fetch path。

   无论选择哪条路径，都必须脱敏敏感 header 值，并避免把 raw requests 结果描述成 production Web tool 行为。

3. Playwright browser path 必须 optional / explicit。

   CLI 必须支持 `--skip-playwright`。Shell wrapper 可以默认 headed browser，因为它们本身是人工 opt-in；pytest 和普通 CI 不得调用该路径。缺少 Playwright package 或 browser executable 时返回 `ok=false` 的 profile，包含 `error_type` 与 `message`，不得让默认 deterministic tests 失败。

4. storage state 是诊断证据，不是业务事实。

   支持 `--storage-state-in`、`--storage-state-out`、`--storage-state-dir`。输出可记录本地路径与是否使用，但不得把 storage state 内容内联到 JSON summary 或 Markdown summary。

5. comparison bucket 保持粗粒度。

   默认保留 OLD bucket：

   - `requests_only_sampled`
   - `partial_sample`
   - `playwright_challenge_detected`
   - `all_success`
   - `browser_only_success`
   - `fetch_only_failure`
   - `requests_only_success`
   - `all_failed`
   - `fetch_outperforms_requests`
   - `requests_and_fetch_success_playwright_failed`
   - `fetch_only_success`
   - `mixed`

   bucket 只描述访问路径对比，不表达网页内容的业务事实。

   分类必须使用确定性 decision tree，不依赖字典遍历顺序或错误 message 文本的任意包含关系：

   1. 若 batch child process crash，没有可信 per-url diagnostic artifact，则该 row 使用 `status="child_process_error"` 或等价非 comparison status，不计算普通 `comparison_bucket`。
   2. 对单 URL artifact，先把 current outcome shapes 归一化为 fetch profile：`ToolCompletedOutcome` 且 payload 可采样为 `fetch_sampled=true`；成功 payload 置 `fetch_ok=true`；`ToolFailedOutcome`、`ToolCancelledOutcome`、`ToolAwaitingOutcome` 与无法识别 outcome 均置 `fetch_sampled=true`、`fetch_ok=false`，并保留 outcome status / error code / message。诊断脚本使用 never-cancelled token，但分类器仍必须覆盖 cancelled / awaiting synthetic case。
   3. requests profile 按 raw GET 是否完成采样归一化为 `requests_sampled` / `requests_ok`；HTTP 非 2xx/3xx、连接失败、超时、URL safety failure 均为 `requests_ok=false`，但保留 status 或 error。
   4. Playwright 被跳过时 `playwright_sampled=false`，不把 skip 当作 failure；执行后 navigation failure、browser missing、timeout、challenge blocking 归一化为 `playwright_sampled=true`、`playwright_ok=false`，并保留 challenge signals。
   5. 若 Playwright 采样且 challenge signals 为真，优先返回 `playwright_challenge_detected`，除非所有路径均完全成功且 challenge 只作为低置信提示；该例外需由 deterministic test 固定。
   6. 三条路径均采样且均成功，返回 `all_success`。
   7. fetch 成功、requests 失败、Playwright 未采样或失败，返回 `fetch_outperforms_requests`；若只有 fetch 成功且 requests / Playwright 均采样失败，返回 `fetch_only_success`。
   8. requests 成功、fetch 失败、Playwright 未采样或失败，返回 `requests_only_success`；若 requests 是唯一被采样成功路径且其他路径未采样，返回 `requests_only_sampled`。
   9. Playwright 成功且 fetch / requests 均失败，返回 `browser_only_success`。
   10. requests 与 fetch 成功但 Playwright 采样失败，返回 `requests_and_fetch_success_playwright_failed`。
   11. fetch 失败但至少一个其他路径成功，返回 `fetch_only_failure`。
   12. 所有采样路径均失败且至少一条路径被采样，返回 `all_failed`。
   13. 其他非空采样组合返回 `partial_sample`；仍无法归类的组合返回 `mixed`，并在 profile 中保留 per-path status 以便复查。

6. `utils/` 代码也必须遵守强类型与中文 docstring。

   `utils/diagnose_web_access.py` 必须有中文模块 docstring。类和函数必须有中文 docstring，包含参数、返回值、异常。禁止 `Any`、`object`、无类型参数、无类型返回值和裸容器签名。

   对 Playwright 动态对象，优先使用本地 private `Protocol` 或窄 wrapper。避免 `getattr`；浏览器类型用 CLI enum 的显式 `if/elif` 分支选择。若确有动态边界，必须把理由写在窄 helper docstring 中，不能扩散到公共签名。

7. LLM-facing diagnostics 文本必须业务可读。

   错误说明、hint、summary label 与 Markdown 文本应说明 URL 访问路径发生了什么。不得用内部模块名、Host governance 字段、裸 tool call id、cursor、digest 或 payload ref 作为用户理解失败的唯一依据。

8. 用户补充授权不改变 F02 非目标。

   当前直接证据不要求修改默认 CI。若 implementation 发现已有 diagnostics CI entry 可在不启用 live network/browser 的前提下增强 opt-in 效果，可在 implementation report 中提出；不得在 F02 自行改变默认 CI workflow。

## 小切片计划

### Slice 1：静态 OLD Pipeline Assets

- Objective：迁移 shell wrappers 与 URL corpus。
- Allowed files：
  - `utils/diag_web.sh`
  - `utils/diag_web_batch.sh`
  - `utils/web_ci_urls.jsonl`
- Exact allowed changes：
  - 将 OLD corpus records 迁移到当前 `utils/web_ci_urls.jsonl`。
  - 新增 shell wrappers，调用 `python -m utils.diagnose_web_access`。
  - 默认输出根目录使用 `workspace/output/web_diagnostics`。
  - live/browser 行为只通过手工命令显式触发。
- Non-goals：
  - 不新增 CI workflow。
  - 不运行 live diagnostics tests。
- Validation：
  - Slice 2 创建 Python 模块后运行 `source .venv/bin/activate && python -m py_compile utils/diagnose_web_access.py`。
  - `bash -n utils/diag_web.sh utils/diag_web_batch.sh`。
- Stop condition：
  - 若 wrapper 需要当前 repo 不存在的 CLI infrastructure，则保持直接 `python -m` 调用并报告 gap。

### Slice 2：Current-Contract Diagnostic Script

- Objective：迁移 `utils/diagnose_web_access.py`，用 current adapter 替换 OLD imports。
- Allowed files：
  - `utils/diagnose_web_access.py`
- Exact allowed changes：
  - 实现单 URL / 批量 CLI parser。
  - 实现 URL entry dataclass、JSONL/TXT reader、去重与校验。
  - 实现 current fetch adapter：`discover_tools(...)`、`ToolCallRequest`、`BatchToolExecutionContext`、current outcomes。
  - 实现 raw requests profile。
  - 实现 optional Playwright profile、bounded network summary 与 storage state 输入 / 输出。
  - 实现 comparison bucket classification。
  - 实现 JSON / JSONL / Markdown writers。
  - 输出必须 JSON-compatible；正文、HTML、network entries 必须有界。
- Required imports：
  - current `dayu.tools.web` provider 或 `dayu.tools.web.provider`
  - current tool contracts / outcome contracts / JSON value contracts
  - standard library
  - `requests`
  - optional Playwright import 只能在 browser-profile helper 内部
- Forbidden imports：
  - `dayu.engine.tool_registry`
  - `dayu.engine.truncation_manager`
  - `dayu.engine.tools.fetch_more`
  - `dayu.web`
  - OLD `/Users/leo/workspace/dayu-agent/...`
- Error handling：
  - `--url` 与 `--url-file` 同时存在或同时缺失时清晰失败。
  - 单路径失败尽量记录在对应 profile 对象中。
  - batch 子进程 crash 或非 diagnostics failure 时，`results.jsonl` 为该 URL 写入 `status="child_process_error"` 或等价非 comparison status，保留 `return_code`、有界 `stderr_prefix`、`stdout_prefix`、`diagnostic_path=null` 与输入 URL metadata；该 row 不写入普通 comparison bucket，不混入 `all_failed` / `mixed` 等访问路径分桶。`summary.json` 与 `summary.md` 单独统计 `child_process_error`。
  - 缺少 Playwright 是 diagnostic profile failure，不是 ordinary test failure。
- Invariants：
  - `comparison_bucket` 必须写入每个单 URL payload。
  - batch mode 先写 normalized corpus，再执行 per-url children。
  - storage state 内容不得复制进 summary。
  - fetch adapter 不绕过 current argument validation。
- Stop condition：
  - 若 current `fetch_web_page` 无法在不恢复 OLD `ToolRegistry` 的情况下调用，停止并报告两个可选方案：在 current Web tools 增加最小 current callable helper，或让 F03 只消费 provider-level outcomes。不得实现 OLD registry compatibility。

### Slice 3：Deterministic Tests 与 Docs Decision

- Objective：验证 parser / classifier / current adapter 行为，不做 live network。
- Test rationale：虽然 `utils/` 默认无覆盖率要求，但 parser、classifier 与 current-contract adapter 包含非平凡分支，且会产出 F03 可能消费的 utility evidence；这些逻辑必须用 deterministic tests 保护。shell wrapper 与 corpus 文件风险较低，可用 `bash -n`、格式解析或轻量 smoke-style 检查覆盖，不要求把 wrapper 行为做成高覆盖率测试。
- Allowed files：
  - `tests/tools/web/test_diagnose_web_access.py` 或等价 focused test
  - `tests/README.md`，仅当新增稳定测试或诊断命令约定需要文档化时
- Exact tests：
  - JSONL / TXT corpus 解析、metadata 保留、去重、非法 JSONL 错误。
  - storage-state path 按 host 解析。
  - synthetic profile payload 的 comparison bucket matrix。
  - synthetic rows 的 batch summary count。
  - mocked `ToolDefinition.callable` 返回 `ToolCompletedOutcome` 时，current fetch adapter 生成 `ok=true` profile。
  - mocked `ToolDefinition.callable` 返回 `ToolFailedOutcome` 时，current fetch adapter 生成 `ok=false` profile，并保留业务可读 error / hint / diagnostic 字段。
  - CLI single mode 在 requests/fetch/playwright builder monkeypatch 后写出 deterministic JSON。
  - CLI batch mode 通过 monkeypatch child execution 或拆分 helper，不做 network。
  - AST/import guard 确认 `utils/diagnose_web_access.py` 不导入 OLD registry / truncation / fetch_more / UI。
- Live diagnostics boundary：
  - 默认 pytest 不运行 real network 或 Playwright。
  - manual validation command 只能作为 opt-in/manual validation 或 skip-safe 入口写入 implementation report。
- Docs：
  - `tests/README.md` 已说明 Web provider tests 必须 deterministic；只有新增 diagnostics test 文件或手工命令改变维护事实时才更新。
  - 不预期更新 Host/Engine README，因为不计划 Host/Engine 代码变化。

## 测试 / 验证命令与预期断言

后续 implementation 若只修改 `utils/` 与 focused tests，验证命令为：

```bash
source .venv/bin/activate
pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_web_tools_provider.py -q
python -m pyright dayu/ tests/ utils/
bash -n utils/diag_web.sh utils/diag_web_batch.sh
git diff --check
```

预期断言：

- focused diagnostics tests 不访问 live network 且通过。
- 既有 Web provider tests 继续通过。
- pyright 不新增或扩散错误。
- shell wrappers 语法通过。
- `git diff --check` 无 whitespace error。

可选 manual opt-in validation 示例，只能用于 implementation report：

```bash
source .venv/bin/activate
python -m utils.diagnose_web_access --url https://www.sec.gov/ --skip-playwright --output workspace/output/web_diagnostics/manual-sec.json
python -m utils.diagnose_web_access --url-file utils/web_ci_urls.jsonl --skip-playwright --batch-output-dir workspace/output/web_diagnostics/manual-batch
```

这些命令不是默认 CI。若运行失败，应报告为 environment / live-network diagnostic，不作为 deterministic test failure。

本 plan gate 必需验证：

```bash
git diff --check
```

本 gate 未修改代码或 README，因此不要求运行 pytest / pyright。

## Docs Decision

本 plan gate 只需要本 plan artifact。

后续 implementation：

- 修改 `tests/` 后必须检查 `tests/README.md` 的 README 更新边界；只有新增测试层级、运行方式或维护规则事实变化时才更新。
- 不修改 `docs/host/design.md` 或 `docs/engine/design.md`，除非 implementation 发现真实 contract/design mismatch；若发现，这是 Controller stop condition，不是静默 patch。
- 不修改 controller artifact，除非 Controller 明确要求。

## 风险 / Open Questions

Blocking open questions：无。

Residual risks：

- live network 结果天然不稳定；F02 通过 explicit opt-in 和 evidence-only 输出降低风险。
- Playwright 安装与浏览器 channel 因机器不同而异；F02 将缺失记录为 diagnostic profile failure。
- current `fetch_web_page` internals 后续可能变化；通过 current `ToolDefinition.callable` 调用比导入 private fetch helper 更低耦合。
- diagnostic JSON 是 utility-level schema；F03 可能需要进一步裁决哪些字段进入 Web smoke evidence。
- 输出可能包含敏感 headers 或本地 storage-state path；implementation 必须脱敏敏感 header value，并且不得内联 storage state 内容。

## Stop Conditions

发现以下任一情况时，停止并报告 Controller：

- F02 需要 Host public contract、Engine public contract、ToolRuntime contract、durable schema、default CI workflow 或 Web production behavior 实质变更。
- current `fetch_web_page` 无法在不恢复 OLD `ToolRegistry` 或兼容 facade 的情况下调用。
- live diagnostics 只能通过 OLD truncation / fetch_more / UI imports 实现。
- 允许文件不足，因为直接代码证据显示这是 production Web boundary defect，而不是 diagnostics migration gap。
- LLM-facing diagnostic text 必须暴露内部治理 ID 才能解释用户可见结论。

## 为什么没有过度设计

该计划只迁移一个已有 OLD diagnostics pipeline 到 `utils/`，并修正 OLD-to-current callable boundary。不新增通用 observability platform、smoke framework、Host event、Engine event、CI workflow、schema registry 或 browser service。

唯一结构化 schema 是 OLD 脚本已经隐含、且 F03 需要消费的 utility JSON。实现切片只有静态资产、current-contract 脚本、deterministic tests/docs 三部分；每个切片都有本地验证方式，不要求重新设计 Web tools。

## Completion Report Format

后续 implementation closeout 必须使用：

- artifact path
- plan verdict：`ready` / `blocked`
- key implementation slices
- validations run
- blocking open questions
- residual risks

本 plan gate 若 `git diff --check` 通过，则 plan verdict 为 `ready`。
