# WU-TOOLS-01-F03 Web CI Smoke Generation Plan

## Goal / Motivation / Success Signal

目标：基于 WU-TOOLS-01-F02 已迁移的 Web diagnostics pipeline，生成显式 opt-in 的 Web smoke。该 smoke 默认不进入普通 deterministic CI；显式运行时至少覆盖 raw `requests` 路径、当前 `fetch_web_page` live 工具 callable 路径，以及本地 PDF 通过 `fetch_web_page` 进入 Docling convert 的非 HTML 路径。

动机成立。F02 已完成 `utils/diagnose_web_access.py`、shell wrapper、URL corpus 与 deterministic diagnostics tests，但 F02 closeout 明确保留 `WU-TOOLS-01-S5-R2`：仍没有 Web smoke pass / fail / skip / diagnostic-only 判定，也没有关闭 live network、real Playwright、provider/API availability 与 anti-bot 站点不稳定性的 residual。F03 应关闭这个测试治理缺口，而不是把真实网站偶发失败误报成生产 regression。

成功信号：

- 新增显式 opt-in smoke 入口；未显式启用时不会跑 live HTTP、不会进入默认 pytest、不会成为普通 CI gate。
- smoke 输出 Codex 可读 summary，包含最终状态、失败 bucket、证据文件路径、失败 URL、建议下一步、skip 原因和 diagnostic-only 外部站点结果。
- local HTML smoke 同时证明 raw `requests` 与当前 `fetch_web_page` 工具路径成功。
- local PDF smoke 启动本地 HTTP server 提供含稳定可抽取文本的小 PDF，通过当前 `fetch_web_page` callable 访问，并用诊断 artifact 记录 PDF 非 HTML 响应、fetch 成功、最小内容断言和 Docling conversion callable 的实际调用证据；不能只覆盖 HTML URL。
- 若 F03 需要超出 F02 最小字段集，字段只能在 `utils/diagnose_web_access.py` 的 diagnostic payload / batch row / summary 中强化，smoke 外壳不得绕过诊断真源自行重建 bucket 或恢复业务语义。
- F03 完成后，`WU-TOOLS-01-S5-R2` 要么关闭，要么把仍不稳定的外部站点、provider availability 或 real browser gap 转成有 owner 的 residual。

## Non-goals / Scope Boundary

非目标：

- 不把 `utils/web_ci_urls.jsonl` 全量变成 smoke gate。
- 不把 live network、real browser 或真实外部站点 smoke 放进普通单元测试或默认 CI gate。
- 不重写 Web search、fetch、Playwright、Docling 或 ToolRuntime 生产 pipeline。
- 不恢复 OLD `ToolRegistry`、OLD truncation manager、OLD `fetch_more`、`dayu.web` 或 UI 路径。
- 不把真实网站偶发失败、anti-bot challenge、quota、DNS、provider 或本机浏览器缺失直接解释为生产 regression。
- 不修改 Host / Engine / ToolRuntime durable schema、public Host contract、Engine state machine 或生产 Web tool 行为，除非实现时直接证明当前 Web tool PDF Docling 路径存在阻塞性 bug；若发生，停止并作为 blocking open question 回到用户裁决。

Scope boundary：

- Plan artifact 写在本文档。
- Implementation gate 只允许规划修改 `utils/diagnose_web_access.py`、`utils/web_ci_urls.jsonl`、`utils/` 下新增 smoke 脚本 / wrapper、`tests/tools/web/` 下 deterministic tests，以及必要时 `tests/README.md`。
- `docs/host/issues-implementation-control.md` 只规划状态更新点，不在 plan gate 修改。

## Design Document Alignment

Host 设计对齐：

- `docs/host/design.md` 固定 `UI -> Service -> Host -> Engine` 分层边界。F03 只在 `utils/` 与 tests 中生成 opt-in diagnostics / smoke，不改变 Host truth、EventLog、Attempt lifecycle、ToolRuntime accept barrier 或 Service assembly。
- Host 设计要求工具执行事实和诊断链可追溯。F03 smoke 必须输出证据文件路径和 bucket，而不是只给一行 pass/fail。
- LLM-facing 文本约束要求投影给模型的文本自解释。F03 的 summary 面向 Codex / 人类执行者，应写业务可读字段：失败 URL、证据路径、失败类别、建议下一步；不得用裸 event id、payload ref、digest 或 tool_call_id 替代诊断语义。

Engine 设计对齐：

- `docs/engine/design.md` 定义 Engine 只执行一次 Agent run，不拥有工具注册、真实 Web provider 或浏览器生命周期。F03 不应把 smoke 插入 Engine tests 或 Engine contract。
- Web tool callable 是当前 ToolDefinition boundary 下的业务工具执行路径；F03 通过 F02 diagnostics 复用当前 `ToolsDiscovery` / `ToolDefinition.callable` 访问 `fetch_web_page`，不回到 OLD registry。

总控对齐：

- `docs/host/issues-implementation-control.md` 当前把 `WU-TOOLS-01-F03` 定位为 GitHub Issue #120 under #98 follow-up，并把 `WU-TOOLS-01-S5-R2` 交给 F03 关闭或转移。
- 当前总控仍记录 PR #132 等待 merge；用户给定事实是 PR #132 已于 `2026-06-10T00:36:41Z` merge。Implementation closeout 时应只规划更新总控当前状态、F03 artifact、验证结果与 R2 residual 结论。

## First-principles Judgment and Direct Code Evidence

第一性原理判断：

- Web smoke 的可靠性边界应由“我们控制的输入”与“外部世界不稳定输入”分离。local HTTP server 的 HTML/PDF fixture 可以形成可重复 live HTTP path；真实外部站点只适合 diagnostic-only，除非未来有稳定 provider / 环境契约。
- smoke 判定应该消费 diagnostics 真源。F02 已经把 URL 安全、raw requests、current fetch、Playwright、batch row 与 bucket 放到 `utils/diagnose_web_access.py`；F03 若需要更多字段，应强化这些 payload / summary，而不是在 smoke 外壳里复制诊断逻辑。
- PDF Docling path 不能靠 HTML URL 间接覆盖，也不能只靠 content-type + fetch success + 静态代码推断证明。必须提供 `Content-Type: application/pdf` 的本地 PDF，并调用当前 `fetch_web_page` callable；diagnostic run 内必须对当前 Web module 的 Docling conversion callable 做窄 instrumentation，wrapper 记录调用证据后委托原始函数执行。
- 对外部站点的失败需要分类：本地 fixture 的 raw/fetch 失败才是 smoke fail；外部站点 challenge、DNS、timeout、browser unavailable 等只进入 diagnostic-only 或 transferred residual，避免误报生产 regression。

直接代码证据：

- `utils/diagnose_web_access.py:1811`-`1870` 已有 `_classify_diagnostic_bucket()`，覆盖 `all_success`、`fetch_only_success`、`fetch_only_failure`、`all_failed`、`playwright_challenge_detected`、`child_process_error` 等 bucket。
- `utils/diagnose_web_access.py:1873`-`1908` 的 `_build_single_diagnostic_payload()` 已按单 URL 采集 `requests_profile`、`fetch_web_page_profile` 和 `playwright_profile`，且支持 `--skip-tool-fetch` / `--skip-playwright`。
- `utils/diagnose_web_access.py:2222`-`2282` 的 `_build_batch_result_row()` 已把单 URL payload 投影为 batch row，包含 URL、diagnostic path、各路径 sampled / ok / status / error。
- `utils/diagnose_web_access.py:2339`-`2385` 的 `_build_batch_summary()` 目前只统计 count 与 bucket 分布，尚未直接输出 smoke 需要的失败 URL、证据路径和建议下一步；F03 需要在这里强化，而不是让 smoke 外壳绕过真源。
- `dayu/tools/web/web_fetch_orchestrator.py:675`-`682` 对 PDF content-type 或 `.pdf` URL 推断 `stream_name="page.pdf"`。
- `dayu/tools/web/web_fetch_orchestrator.py:694`-`730` 的 `_docling_convert_to_markdown()` 调用 `convert_pdf_bytes_with_docling(...)` 并返回 `extraction_source="docling"`。
- `dayu/tools/web/web_fetch_orchestrator.py:818`-`879` 包含 HTML 路由判断与非 HTML response 分支；非 HTML 分支调用 `convert_non_html(response.content, _infer_docling_stream_name(...))`。
- `dayu/tools/web/web_tools.py:1595`-`1608` 的 `_docling_convert_to_markdown()` 是当前 `fetch_web_page` callable 装配给 orchestrator 的非 HTML Docling conversion callable；diagnostics 可在单次诊断作用域内临时 wrapper 该 callable，记录 invocation evidence 后调用原始函数。
- `dayu/tools/web/web_tools.py:1566`-`1588` 成功路径内部诊断记录 `extraction_source` / `renderer_source`，但 `ToolCompletedOutcome` 对 LLM 可见 payload 只返回 `url/final_url/title/content/fetch_backend`。F03 不把 `extraction_source` 或其它 implementation-only 字段加入 production `fetch_web_page` LLM-facing success payload；除非后续用户明确批准生产契约变更，否则 Docling route evidence 只能写入 diagnostics artifact。
- `tests/README.md` 已声明 `tests/tools/web/` 必须 deterministic，Web provider tests 的搜索、requests 主路径和 Playwright fallback 都应通过 monkeypatch / fixture 替身控制，不做 live network 请求。

## Affected Files / Modules

Plan gate 已新增：

- `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md`

Implementation gate 预计允许修改：

- `utils/diagnose_web_access.py`
- `utils/web_ci_urls.jsonl`，仅当需要给小样本增加 smoke metadata；禁止把全量 corpus 升级为 gate。
- `utils/smoke_web_ci.py`，新增 opt-in smoke 主入口。
- `utils/smoke_web_ci.sh`，可选 shell wrapper。
- `tests/tools/web/test_diagnose_web_access.py`
- `tests/tools/web/test_smoke_web_ci.py`，新增 deterministic tests。
- `tests/README.md`，只有当前说明无法覆盖新增 opt-in smoke / deterministic test 边界时才更新。

只读 / 核对：

- `dayu/tools/web/web_fetch_orchestrator.py`
- `dayu/tools/web/web_tools.py`
- `docs/host/issues-implementation-control.md`
- `docs/reviews/wu-tools-01-f02-final-closeout-controller.md`

## Contract / Schema / State-machine / Public-interface Changes

生产 contract / schema / state-machine / public interface：预期无变更。

- 不修改 Host durable schema、EventLog canonical payload、Host public API、Engine public contracts、ToolRuntime contracts 或 Web tool LLM-facing schema。
- 不修改 `fetch_web_page` 对 LLM 返回字段；当前缺少 `extraction_source` 不作为 F03 生产行为 bug 处理。
- Diagnostics artifact 属于 `utils/` 手工 opt-in 输出，不是生产公共契约。F03 可以对 `web-diagnostics-v1` 追加自解释字段，但不得删除 F02 已有字段；若实现需要破坏性字段变更，停止并回到 plan review。
- 新增 smoke summary schema 只服务 `utils/smoke_web_ci.py` 输出，必须自解释：`status`、`exit_code`、`failures`、`skips`、`diagnostic_only`、`evidence_paths`、`suggested_next_steps` 等字段需在脚本文档和 tests 中固定。

## Implementation Decisions

1. Smoke 必须显式 opt-in。
   - 新增 `utils/smoke_web_ci.py`，默认未设置 `DAYU_RUN_WEB_CI_SMOKE=1` 且未传 `--run-live` 时不发起 live HTTP，输出 `status="skipped"` summary 并以 exit code `0` 退出。
   - 显式启用后运行 local fixture smoke；外部 URL diagnostics 只能通过额外参数启用，例如 `--external-url-file` / `--external-limit`，且默认 diagnostic-only。

2. Local fixture 是 smoke gate，外部站点是 diagnostic-only。
   - local fixture 由 smoke 脚本启动 `127.0.0.1` HTTP server，提供 `/index.html` 和 `/fixture.pdf`。
   - `/index.html` 覆盖 raw `requests` 与 current `fetch_web_page` 的 HTML live path。
   - `/fixture.pdf` 使用很小但含稳定可抽取文本的 PDF bytes；不得复用空白或无文本 minimal PDF。响应头必须是 `Content-Type: application/pdf`，fixture 文本需包含固定短句并满足 smoke 的最小内容断言。
   - 调用 F02 diagnostics 时必须传 `--allow-private-network-url`，因为诊断脚本默认拒绝 local/private URL，这是正确安全边界。
   - local fixture 默认传 `--skip-playwright`，因为 F03 最小目标不是 real browser；browser 可作为后续显式 `--include-playwright` diagnostic-only。

3. Pass / fail / skip / diagnostic-only 判定规则固定。
   - `pass`：显式启用后，local HTML 的 diagnostics facts 显示 `requests_profile.result.ok=True` 且 `fetch_web_page_profile.ok=True`；若 Playwright 被 skip，不要求 `comparison_bucket=all_success`。local PDF 的 raw requests 成功、content-type 指向 PDF、`fetch_web_page_profile.ok=True`、fetch content 满足最小字符数，并且 diagnostics artifact 记录 Docling conversion callable 的实际 invocation evidence。
   - `fail`：显式启用后 local HTML / PDF fixture 的 raw requests 或 current fetch 失败；诊断子进程异常且不是 Docling runtime dependency/init skip；summary artifact 缺失；diagnostics schema/version 不含 smoke 所需字段；PDF 响应未被识别为 PDF；PDF fetch 成功但内容为空/过短；PDF fetch 成功但无法建立 Docling callable invocation evidence。
   - `skip`：未显式启用；Docling 依赖缺失或 Docling runtime initialization failure 造成 PDF local smoke 无法执行时，记录 skip bucket 和证据路径，exit code `0`。如果 HTML local smoke 失败，不能因为 PDF skip 掩盖 failure。
   - `diagnostic-only`：外部站点 URL 的 `all_failed`、`playwright_challenge_detected`、`browser_only_success`、timeout、DNS、HTTP 403/429/5xx、real browser unavailable、storage-state cookie gap 等，不改变 smoke exit code；只进入 summary 的 diagnostic-only 列表和 residual 分类。

4. Diagnostics 真源需要强化，但只输出 observed facts。
   - 在 `utils/diagnose_web_access.py` 中增加 helper，把 batch row / summary 的 URL、diagnostic_path、各路径 sampled/ok/status/error、observed bucket、observed failing path、error code、content-type、content length、schema version 等事实投影为自解释字段。
   - 对 PDF local smoke 增加 diagnostic-only route evidence 字段，例如 `docling_conversion_invocation_evidence`。该字段必须来自 diagnostic run 内对 `dayu.tools.web.web_tools._docling_convert_to_markdown` 的窄 wrapper 调用记录，至少包含 `invoked`、`stream_name`、原始函数是否 completed、是否捕获 Docling runtime initialization/dependency error、wrapper target module/function、fixture URL 或 diagnostic URL。字段必须说明它是诊断观察事实，不是财报事实、站点事实或 production tool public output。
   - `utils/smoke_web_ci.py` 负责 smoke-specific pass/fail/skip/diagnostic-only classification、primary failure 和 suggested next step。若 diagnostics 中保留 action hint，命名必须清楚表明只是 `diagnostic_action_hint`，不得混同 smoke primary failure 语义。
   - smoke 外壳只读取 diagnostics facts 和单 URL payload，不自行解析 raw HTML、不复制 Web fetch/Docling 路由逻辑、不读取 production private log。

5. 不新增默认 CI workflow。
   - 本 WU 只提供脚本和 tests；是否把 opt-in smoke 接入 GitHub Actions 手工 job 是后续显式决策，不在 F03 默认实施。

## Small Implementation Slices

### Slice 1: Diagnostics Observed Facts and Docling Invocation Evidence

Objective：强化 F02 diagnostics，使 smoke 能直接消费 observed facts、证据路径、失败 URL、schema version 和 Docling callable 实际调用证据。

Expected outcome：`utils/diagnose_web_access.py` 输出的 single payload / batch row / summary 足够支持 smoke classification，不需要 smoke 外壳复制诊断逻辑，也不需要修改 production `fetch_web_page` LLM-facing success payload。

Allowed files/modules：

- `utils/diagnose_web_access.py`
- `tests/tools/web/test_diagnose_web_access.py`

Prerequisites / dependencies：

- F02 diagnostics pipeline 已存在。
- 不修改 production Web tool behavior。

Exact changes：

- 新增模块级常量定义稳定 diagnostics schema/version 和 observed fact 类别，例如 `web-diagnostics-v1` 的最低 smoke schema revision、observed local fetch failure、observed external gap、docling dependency/init observed skip、browser unavailable observed gap。禁止魔法字符串散落在逻辑中。
- 新增私有 helper，例如 `_build_observed_diagnostic_item(row)` / `_build_diagnostic_action_hint(row)` / `_build_smoke_relevant_observed_facts(rows)`；函数必须有完整中文 docstring 和严格类型签名。helper 输出诊断事实与 diagnostic action hint，不输出 smoke primary failure。
- 在调用当前 `fetch_web_page` callable 的诊断作用域内，对 `dayu.tools.web.web_tools._docling_convert_to_markdown` 做窄 wrapper instrumentation：
  - wrapper 只在本次 diagnostic run 内安装，必须在 `finally` 恢复原始 callable。
  - wrapper 必须调用原始函数，不允许替代 Docling 行为或吞掉异常。
  - wrapper 记录 diagnostic-only evidence：`invoked`、`stream_name`、`raw_bytes_length`、`target_module`、`target_function`、`original_completed`、`original_exception_type`、`docling_runtime_initialization_error`、`diagnostic_url`。
  - 记录对象只写入 diagnostics artifact，不写入 `ToolCompletedOutcome.result.value`，不暴露给生产 LLM-facing payload。
- `_build_batch_result_row()` 保持既有字段，并追加自解释字段：
  - `observed_bucket`
  - `observed_failing_path`
  - `evidence_path`
  - `failure_url`
  - `diagnostic_action_hint`
  - `diagnostic_only_reason`
  - `diagnostic_schema_version`
- `_build_batch_summary()` 追加：
  - `observed_buckets`
  - `observed_items`
  - `diagnostic_only_observed_items`
  - `skip_observed_items`
  - `diagnostic_action_hints`
  - `diagnostic_schema_version`
- `_build_single_diagnostic_payload()` 在 raw requests 与 fetch profile 都可见后追加 `docling_conversion_invocation_evidence`。该字段必须来自 wrapper 记录的实际 invocation；HTML payload 或未触发 Docling 的 payload 必须明确 `invoked=False` 或省略并由 schema 说明其适用条件。
- 对 Playwright skipped + requests/fetch 成功的 local HTML 场景，计划采用 diagnostics facts 判定，不强制新增 bucket：smoke classification 直接读取 `requests_profile.result.ok=True`、`fetch_web_page_profile.ok=True`、`playwright_profile.sampled=False`。若 implementation 选择新增 bucket，也必须是 additive bucket，例如 `requests_and_fetch_success_playwright_skipped`，并保留 facts 判定。

Data flow：

`single diagnostic payload with observed facts -> batch result row -> batch summary -> smoke classification -> smoke summary`。smoke 外壳只消费 diagnostics 输出，不复制 Web fetch/Docling route 逻辑。

Error handling：

- 缺少诊断文件或 JSON 非对象仍按现有 child process error。
- diagnostics payload / summary 必须携带 schema version 或 smoke-required revision。缺少 schema version、version 低于 smoke 需求、缺少 `docling_conversion_invocation_evidence` 等必需字段时，smoke 应把它分类为 `diagnostic_schema_gap` failure，而不是静默 fallback。
- Docling runtime dependency/init failure 只能来自 wrapper evidence 或 fetch profile error 中清晰可识别的 Docling initialization/dependency signal；其它 Docling conversion exception 不得被归为 skip。

Invariants：

- 不删除 F02 已有字段。
- 不改变 `_classify_diagnostic_bucket()` 现有 bucket 含义，除非 tests 证明新 bucket 是 additive 且必要。
- 不把 HTTP status、internal diagnostics 或 log-only 字段伪装成 production tool public output。
- 不把 `extraction_source`、`renderer_source`、Docling callable name 等 implementation-only 字段加入 production `fetch_web_page` LLM-facing success payload。

Tests / validation commands：

```bash
source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Expected assertions：

- Synthetic rows 生成稳定 `observed_items`、`diagnostic_only_observed_items`、`skip_observed_items` 和 `diagnostic_action_hints`。
- child process error 有证据路径和 diagnostic action hint。
- Wrapper instrumentation 在 synthetic Docling callable 调用下记录 `docling_conversion_invocation_evidence.invoked=True`、`stream_name="page.pdf"`、`original_completed=True`。
- HTML payload 不生成 invoked=True 的 Docling evidence；PDF content-type + fetch success 但 wrapper 未 invoked 时，后续 smoke classification 必须 fail。
- Docling initialization/dependency exception 被记录为可识别 skip evidence；通用 conversion exception 只记录 observed failure，不可归为 skip。

Completion signal：

- Existing diagnostics tests pass。
- 新 observed fact / schema version / Docling invocation evidence 字段被 tests 锁定。

Stop condition：

- 如果 diagnostics-side wrapper 无法在当前 `fetch_web_page` callable 执行路径内观察到 Docling conversion callable invocation，停止；不得退回 content-type + fetch success + static code inference，也不得修改 production success payload，除非用户后续明确批准生产契约变更。

### Slice 2: Opt-in Smoke CLI and Summary Contract

Objective：新增 `utils/smoke_web_ci.py`，定义 opt-in、exit code 和 Codex 可读 summary。

Expected outcome：开发者可运行一个明确命令获得 `workspace/output/web_smoke/<run_id>/summary.json` 和 `summary.md`，默认未 opt-in 时不联网。

Allowed files/modules：

- `utils/smoke_web_ci.py`
- `utils/smoke_web_ci.sh`
- `tests/tools/web/test_smoke_web_ci.py`

Prerequisites / dependencies：

- Slice 1 诊断 observed facts、schema version 和 Docling invocation evidence 字段完成。

Exact changes：

- 新增 `SmokeOptions`、`SmokeCaseResult`、`SmokeSummary` 等强类型 dataclass；不得使用 `Any`、`object`、无类型签名或裸容器注解。
- CLI 参数至少包含：
  - `--run-live`
  - `--output-dir`
  - `--request-timeout`
  - `--tool-timeout-budget`
  - `--include-playwright`
  - `--external-url-file`
  - `--external-limit`
  - `--diagnostic-only-external`
- 环境变量 `DAYU_RUN_WEB_CI_SMOKE=1` 与 `--run-live` 任一满足才执行 live smoke。
- Exit code：
  - `0`：pass、skip 或 diagnostic-only-only。
  - `1`：local gate failure。
  - `2`：CLI usage、diagnostics schema gap、artifact write failure 或 smoke infrastructure error。
- Smoke 读取 diagnostics artifact 前必须执行 schema validation：
  - `diagnostic_schema_version` 或等价 schema marker 存在。
  - version/revision 满足 F03 smoke 所需最低版本。
  - local HTML 必需 facts：requests sampled/ok、fetch sampled/ok、diagnostic path。
  - local PDF 必需 facts：requests sampled/ok、raw response content-type、raw response bytes/content length、fetch sampled/ok、fetch content length、`docling_conversion_invocation_evidence`。
  - 不满足时生成 `diagnostic_schema_gap` failure；local case exit code `2`，external case记录为 diagnostic-only schema gap 且不覆盖 local gate。
- 输出 `summary.json` 与 `summary.md`；summary 必须包含：
  - `status`: `passed` / `failed` / `skipped` / `diagnostic_only`
  - `exit_code`
  - `run_label`
  - `output_dir`
  - `failures`: 每项含 `bucket`、`evidence_path`、`url`、`suggested_next_step`
  - `skips`: 每项含 `bucket`、`evidence_path`、`url`、`reason`
  - `diagnostic_only`: 每项含 `bucket`、`evidence_path`、`url`、`suggested_next_step`
  - `local_cases`
  - `external_cases`

Smoke classification ownership：

- Diagnostics 输出 observed facts：URL、profiles、bucket、schema version、content-type、content length、Docling invocation evidence、diagnostic action hint。
- Smoke wrapper 输出 classification：`passed` / `failed` / `skipped` / `diagnostic_only`，以及 smoke-specific `primary_failure_bucket`、`suggested_next_step`、exit code。
- 不把 smoke-specific primary failure 语义写回 diagnostics，除非字段名清楚表明只是 diagnostic action hint。

Data flow：

`SmokeOptions -> local HTTP fixture URLs -> diagnose single/batch subprocess -> load diagnostics payloads -> validate diagnostics schema -> consume diagnostics observed facts -> smoke classification -> write smoke summary -> exit code`。

Error handling：

- 未 opt-in：写 skipped summary；不启动 server、不调用 diagnostics。
- diagnostics 子进程 return code、artifact 和 JSON 的映射必须按下表实现：

| 子进程 / artifact 信号 | Local HTML 判定 | Local PDF 判定 | External 判定 |
|---|---|---|---|
| return code `0`，JSON parse 成功，schema valid，requests ok，fetch ok | pass；Playwright skipped 可接受 | 继续检查 PDF content-type、最小内容和 Docling invocation evidence | diagnostic-only observed success/gap，不影响 exit code |
| return code `0`，JSON parse 成功，但 schema missing / version too old / required facts missing | `diagnostic_schema_gap`，exit code `2` | `diagnostic_schema_gap`，exit code `2` | diagnostic-only schema gap；若 local gate 已通过则 exit code 仍为 `0` |
| return code `0`，requests ok + fetch ok，但 Playwright skipped | pass；不要求 `all_success` bucket | 不适用 | diagnostic-only；browser gap 不影响 exit code |
| return code `0`，local PDF fetch ok，但 content-type 不是 PDF | 不适用 | fail，exit code `1` | diagnostic-only |
| return code `0`，local PDF fetch ok，但 fetch content 为空或短于 `PDF_FETCH_MIN_CHARS` | 不适用 | fail，exit code `1` | diagnostic-only |
| return code `0`，local PDF fetch ok，但 `docling_conversion_invocation_evidence.invoked` 不是 `True` | 不适用 | fail，exit code `1` | diagnostic-only |
| return code `0` 或非 `0`，evidence 清楚表明 Docling dependency/init failure | 不适用 | skip，exit code `0`，但不能掩盖 HTML failure | diagnostic-only provider/runtime gap |
| return code 非 `0`，JSON parse 成功，非 Docling init/dependency error | fail，exit code `1` | fail，exit code `1` | diagnostic-only child process error |
| 子进程无 artifact、JSON parse failure、JSON 非对象 | smoke infrastructure failure，exit code `2` | smoke infrastructure failure，exit code `2` | diagnostic-only parse/artifact gap；若 local 未跑或已通过则 exit code `0` |
| local server 启动失败、artifact 写入失败、CLI 参数非法 | exit code `2` | exit code `2` | exit code `2` when caused by explicit operator input |

- summary 写入失败：exit code `2`。

Invariants：

- 默认 pytest 和普通 CI 不触发 live HTTP。
- 外部 URL 永远不因站点行为导致 exit code `1`；只有 local fixture gate 能 fail smoke。
- smoke 外壳不得 import Host / Engine / Service / UI。

Tests / validation commands：

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# if utils/smoke_web_ci.sh is created:
bash -n utils/smoke_web_ci.sh
```

Expected assertions：

- 未 opt-in 时 status 为 `skipped` 且不会调用 diagnostics runner。
- Synthetic diagnostics result 能映射为 pass/fail/skip/diagnostic-only/diagnostic_schema_gap。
- local failure 生成 exit code `1` 和 Codex 可读 failure item。
- schema/version mismatch 生成 `diagnostic_schema_gap`，local case exit code `2`。
- external failure 进入 diagnostic-only，不影响 exit code。

Completion signal：

- smoke CLI deterministic tests pass。
- 如果创建 `utils/smoke_web_ci.sh`，`bash -n` wrapper pass；如果不创建 wrapper，implementation report 不列 `bash -n` 作为已执行验证。

Stop condition：

- 如果 smoke 需要复制 `_classify_diagnostic_bucket()` 或解析 raw tool internals 才能判定，停止并回到 Slice 1 强化 diagnostics。

### Slice 3: Local HTML/PDF Live Fixture and Docling Route Check

Objective：实现显式 opt-in local live smoke，覆盖 HTML 与 PDF。

Expected outcome：`DAYU_RUN_WEB_CI_SMOKE=1 python -m utils.smoke_web_ci --run-live` 启动本地 server，调用 F02 diagnostics 访问 local HTML 和 PDF，并输出 local gate 结果。

Allowed files/modules：

- `utils/smoke_web_ci.py`
- `tests/tools/web/test_smoke_web_ci.py`

Prerequisites / dependencies：

- Slice 2 smoke CLI 已存在。
- Slice 1 PDF Docling invocation evidence 字段已存在。

Exact changes：

- 新增私有 HTTP handler / server helper，只绑定 `127.0.0.1` 和随机可用端口。
- 提供 `/index.html`，内容包含稳定标题和正文，响应 `Content-Type: text/html; charset=utf-8`。
- 提供 `/fixture.pdf`，响应 `Content-Type: application/pdf`，PDF bytes 使用最小稳定 PDF fixture：
  - PDF 必须包含固定可抽取英文文本，例如 `Dayu Web Smoke PDF` 与 `This PDF verifies Docling conversion.`。
  - 定义模块级常量 `PDF_FETCH_MIN_CHARS`，最小值不得低于 20 个可打印字符；禁止用魔法数字散落。
  - 如果现有 minimal PDF 为空白或不能稳定抽取文本，不得复用；应在 smoke 脚本内定义新的小型文本 PDF fixture。
- 对两个 URL 调用 `python -m utils.diagnose_web_access --url ... --allow-private-network-url --skip-playwright --output <path>`；当 `--include-playwright` 时不传 `--skip-playwright`，但 Playwright 结果仍 diagnostic-only。
- HTML case pass 条件：raw requests sampled / ok，fetch sampled / ok。默认 `--skip-playwright` 时，`playwright_profile.sampled=False` 不影响 pass，也不要求 `comparison_bucket=all_success`；若新增 additive bucket `requests_and_fetch_success_playwright_skipped`，只能作为辅助事实。
- PDF case pass 条件：raw requests sampled / ok，response content-type 包含 PDF，raw response bytes length 大于 0，fetch sampled / ok，fetch content length >= `PDF_FETCH_MIN_CHARS`，diagnostics 给出 `docling_conversion_invocation_evidence.invoked=True`，`stream_name="page.pdf"`，原始 Docling callable completed。
- PDF fetch 成功但内容为空/过短必须 fail，不能因为 fetch ok 或 content-type 正确而 pass。这覆盖 Docling 静默丢弃内容的情况。
- Docling 未安装或 Docling runtime initialization failure：仅当 diagnostics evidence 清楚表明是 dependency/init failure 时，PDF case 标记 skipped；HTML case 仍必须 pass；summary 明确 `suggested_next_step` 为安装 / 修复 Docling runtime 后重跑。

Data flow：

`HTTP server fixture -> diagnose_web_access single URL subprocess -> diagnostic JSON -> smoke case result -> smoke summary`。

Error handling：

- Server 启动失败：smoke infrastructure error，exit code `2`。
- Local HTML 失败：exit code `1`。
- Local PDF 因 Docling dependency/init 缺失失败：skip；因 HTTP / fetch / schema / content-type / content length / invocation evidence 缺失失败：exit code `1` 或 schema gap 的 exit code `2`。
- Always close server in `finally`。

Invariants：

- Local private URL 只能在 diagnostics subprocess 中通过显式 `--allow-private-network-url` 放行。
- 不把 local fixture 加入 `utils/web_ci_urls.jsonl` 全量 corpus。
- 不把 PDF route check 降级为 HTML URL check。

Tests / validation commands：

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Expected assertions：

- Server helper 生成的 case URLs 指向 loopback，且 diagnostics command 含 `--allow-private-network-url`。
- HTML/PDF synthetic payload 判定符合 pass/fail/skip。
- Playwright skipped + requests ok + fetch ok 的 HTML payload pass。
- PDF case 缺 Docling invocation evidence、content-type 非 PDF、fetch content 为空或过短时 fail，不被误判为 pass。
- PDF Docling dependency/init evidence 只让 PDF case skip，不掩盖 HTML failure。

Completion signal：

- Opt-in smoke command 在有 Docling 环境且 fixture 文本可抽取时可以跑出 passed；无 Docling dependency/init 环境时输出 HTML passed + PDF skipped，exit code `0`。

Stop condition：

- 如果真实 `fetch_web_page` 对 local PDF 返回 success 但 diagnostics wrapper 无法证明 Docling callable invocation，停止并回到用户裁决；不得用 HTML smoke、content-type + fetch success、static code inference 或 production success payload 变更替代 PDF Docling evidence。

### Slice 4: Optional External Diagnostics Without Gate Semantics

Objective：让 F03 能从 F02 URL corpus 生成外部站点 diagnostic-only 摘要，但不把全量 corpus 变成 gate。

Expected outcome：显式传 `--external-url-file` 时，smoke 可运行小样本外部 diagnostics，并在 summary 中分类展示，不影响 local gate exit code。

Allowed files/modules：

- `utils/smoke_web_ci.py`
- `utils/web_ci_urls.jsonl`，仅当需要给少量 URL 添加 `smoke_candidate` / `diagnostic_only` metadata。
- `tests/tools/web/test_smoke_web_ci.py`

Prerequisites / dependencies：

- Slice 2 summary contract 已存在。

Exact changes：

- 默认不运行外部 URL。
- 传 `--external-url-file utils/web_ci_urls.jsonl --external-limit N` 时，只取前 N 个或带 metadata 的小样本；禁止默认全量。
- 外部 diagnostics 默认 `--skip-playwright`；`--include-playwright` 只用于 diagnostic-only。
- 外部结果不产生 exit code `1`。即使 `all_failed`，也进入 `diagnostic_only`，建议下一步说明可能是站点、网络、anti-bot、provider/browser gap。

Data flow：

`external URL file -> diagnose batch -> batch summary observed facts -> smoke diagnostic-only classification -> smoke summary external_cases`。

Error handling：

- 外部 URL 文件缺失或非法：如果用户显式请求，exit code `2`，因为这是 operator input error。
- 外部 diagnostics child process failure：记录 diagnostic-only item；不覆盖 local gate status。

Invariants：

- 不把真实网站失败解释为 production regression。
- 不要求 Playwright / storage state / Chrome channel 在默认 smoke 中存在。

Tests / validation commands：

```bash
source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
```

Expected assertions：

- 外部 `all_failed` / `playwright_challenge_detected` 进入 diagnostic-only。
- 外部 diagnostic-only 不影响 local pass exit code。
- `--external-limit` 生效，避免全量 corpus。

Completion signal：

- Optional external summary 能稳定输出 external gap，不新增默认 gate。

Stop condition：

- 如果用户要求外部站点失败变成 hard gate，停止；这超出 F03 非目标，需要新的稳定环境契约。

### Slice 5: Docs, Validation, and Residual Reconciliation

Objective：补齐 deterministic tests、README 判断、总控更新点和 R2 residual 结论。

Expected outcome：implementation closeout 可证明 F03 已完成或明确转移 residual。

Allowed files/modules：

- `tests/tools/web/test_diagnose_web_access.py`
- `tests/tools/web/test_smoke_web_ci.py`
- `tests/README.md`，仅当现有测试手册未覆盖新增 opt-in smoke 边界。
- `docs/host/issues-implementation-control.md`，只在 implementation closeout 阶段实际更新；本 plan gate 不编辑。

Prerequisites / dependencies：

- Slice 1-4 完成。

Exact changes：

- Tests 覆盖 deterministic logic；不在 default pytest 中跑真实 local server + real Docling，除非使用 monkeypatch 或 synthetic payload。
- README decision：
  - 若新增 `tests/tools/web/test_smoke_web_ci.py` 后，现有 `tests/README.md` 关于 Web tests deterministic 的说明仍准确，只需补一句“opt-in live smoke 位于 utils，不在默认 pytest 中运行”。
  - 若不新增测试层级或 README 已足够自解释，则不改 README。
- 总控更新点：
  - `当前状态`：active work unit 从 F03 推进到下一个入口。
  - `WU-TOOLS-01-F03`：记录 plan artifact、validation、smoke command、residual reconciliation。
  - `WU-TOOLS-01-S5-R2`：若 local HTML/PDF smoke 与 summary contract 完成，则标记 closed；若 external/browser/provider 仍不稳定，必须转移到具体 owner 或 issue，并说明不是 F03 local smoke 阻塞。无 owner 或 issue 时不得关闭 closeout。

Data flow：

`implementation results -> validation commands -> closeout artifact -> issues-implementation-control update`。

Error handling：

- pyright 或 focused pytest 失败不得进入 closeout。
- README 修改前必须先遵守 `tests/README.md` 文档职责，不做机械同步。

Invariants：

- F03 不新增 Host / Engine / Service / production Web tool changes。
- No compatibility wrapper / re-export。
- 所有新增函数中文 docstring，严格类型签名。

Tests / validation commands：

```bash
source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py tests/tools/web/test_smoke_web_ci.py -q
source .venv/bin/activate && python -m pyright dayu/ tests/ utils/
# if utils/smoke_web_ci.sh is created:
bash -n utils/smoke_web_ci.sh
git diff --check
```

Opt-in smoke manual command, not default CI：

```bash
source .venv/bin/activate && DAYU_RUN_WEB_CI_SMOKE=1 python -m utils.smoke_web_ci --run-live
```

Expected assertions：

- deterministic tests pass without external network。
- pyright returns `0 errors`。
- shell wrapper syntax passes if wrapper is created。
- manual opt-in smoke outputs `summary.json` / `summary.md` with pass / skip / diagnostic-only classification。

Completion signal：

- Closeout can state exact changed files, validation commands, artifact paths, and R2 residual status。

Stop condition：

- Any unclassified residual risk remains。
- Any implementation requires production Web tool behavior change to satisfy smoke docling evidence。
- Any external site instability is proposed as default hard gate without explicit user approval。
- Any external/browser/provider instability is closed without concrete owner or issue。

## Docs Decision

Plan gate：

- 新增本文档。
- 不修改 `docs/host/issues-implementation-control.md`，只在计划中列出 closeout 更新点。
- 不修改 `tests/README.md`，因为 plan gate 不新增测试文件。

Implementation gate：

- 如果新增 `tests/tools/web/test_smoke_web_ci.py`，应检查 `tests/README.md` 的 `Agent更新约束` / 文档职责。当前 README 已声明 `tests/tools/web/` 必须 deterministic，因此只需在不造成职责扩张的前提下补充 opt-in live smoke 位于 `utils/`，默认测试仅覆盖 smoke 判定逻辑。
- 不更新 Host / Engine README，因为 F03 不修改 Host / Engine。

## Risks / Open Questions

Risks：

- 文本 PDF fixture 在部分 Docling 版本或平台上仍可能产生空/过短 markdown。计划允许把 Docling runtime dependency/init failure 作为 skip；但只要 Docling callable completed 且 `fetch_web_page` 成功返回，内容为空/过短就是 local PDF fail，必须调整 fixture 或修正真实 bug，不得跳过 PDF route。
- 当前 `fetch_web_page` success payload 不暴露 `extraction_source` / `renderer_source`。F03 计划用 diagnostics-side wrapper 记录当前 Docling conversion callable 的实际 invocation evidence；不得把 `extraction_source` 或 implementation-only 字段加入 production success payload，除非后续用户明确批准生产契约变更。
- Diagnostics wrapper instrumentation 可能随生产 callable 名称或装配方式变化而失效。失效时应产生 `diagnostic_schema_gap` 或 local PDF fail，不能静默退回 static code inference。
- Local loopback smoke 需要 `--allow-private-network-url`。这是诊断脚本显式 opt-in，不得弱化默认 URL 安全策略。
- External corpus diagnostic-only 可能仍耗时或受 anti-bot 影响；必须保持小样本、显式参数和 non-gating。

Blocking open questions：

- 当前计划无 blocking open question。
- 若 implementation 发现当前 Web tool 对 local PDF 的 Docling path 真实失败，且失败不是 Docling dependency/init skip，而是生产 route bug，则停止并把问题作为 F03 blocker 回报；不得扩大范围直接修 production pipeline。

## Residual Risk Handling

`WU-TOOLS-01-S5-R2` 关闭条件：

- local HTML raw requests + current `fetch_web_page` smoke 已实现并通过 opt-in 验证或 deterministic synthetic coverage 锁定判定。
- local PDF `fetch_web_page` Docling route smoke 已实现，diagnostics artifact 记录 Docling callable invocation evidence，且 summary 明确 pass / skip / fail。
- summary 输出可读 failure bucket、evidence path、failed URL、suggested next step。
- 默认 deterministic CI 不运行 live network。

若满足以上条件：

- `WU-TOOLS-01-S5-R2` 可在 closeout 中标记 `closed`，依据是 F03 已提供 explicit opt-in Web smoke generation 并保留外部不稳定性 diagnostic-only。

需要转移的 residual：

- Real external sites challenge / anti-bot / DNS / timeout：转移到具体 Web provider observability issue、operator-run diagnostic maintenance issue，或明确 owner 角色；不阻塞 R2。
- Real Playwright browser / Chrome channel / storage-state cookies：如果 F03 只提供 diagnostic-only browser option，则转移到具体 browser-capability smoke issue 或明确 owner 角色；不得算作 local Web smoke failure。
- Provider/API availability：转移到具体 provider-specific smoke / environment issue 或明确 owner 角色。

不得留下无 owner residual。若 closeout 时无法写出具体 GitHub Issue 编号、控制文档条目或明确 owner 角色，不得关闭 `WU-TOOLS-01-S5-R2`，必须停止让用户裁决。

## Completion Report Format

Implementation closeout 最终说明必须包含：

- 改了什么：
  - diagnostics fields
  - smoke script / wrapper
  - local HTML/PDF cases
  - tests / README / control doc updates
- 验证了什么：
  - focused pytest 命令与结果
  - pyright 命令与结果
  - 若创建 shell wrapper，`bash -n` 结果；若未创建，明确说明 wrapper 未创建且该验证不适用
  - opt-in smoke 命令、summary path、status
- R2 residual 结论：
  - `WU-TOOLS-01-S5-R2 closed` 或 `transferred-with-owner`
  - 若有 transfer，列出 owner、原因、证据路径
- 风险或未覆盖：
  - external diagnostic-only gaps
  - browser/storage-state gaps
  - Docling dependency skip 状态

## Why This Is Not Overdesigned

- 只新增一个 opt-in smoke 入口和必要 diagnostics observed facts，不引入 CI workflow、平台服务、插件系统或新工具 runtime。
- 复用 F02 diagnostics pipeline 作为真源，并用窄 wrapper 观察当前 Docling conversion callable，避免复制 raw requests / fetch / Playwright / Docling 路由逻辑。
- 使用 local HTTP server 控制 HTML/PDF fixture，避免把真实外部站点稳定性问题伪装成 production regression。
- 外部 URL 保持 diagnostic-only 和小样本，不把全量 corpus 变成 hard gate。
- 不修改 Host / Engine / ToolRuntime / production Web tool public behavior，保持 F03 在 smoke generation 范围内。
