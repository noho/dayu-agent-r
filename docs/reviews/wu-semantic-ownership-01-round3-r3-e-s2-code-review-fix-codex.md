# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E S2 code review fix — AgentCodex

## 1. Gate 与范围

- Work unit：`WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E - Web And Document Tool Egress, Resource Caps, Diagnostics, And Oracles`。
- Gate：R3-E Slice S2 code-review fix only。
- 依据：`docs/host/design.md`、`docs/engine/design.md`、R3-E accepted plan、S2 implementation / controller validation、两份 code review 与 controller adjudication。
- 本轮只修复 controller 接受的 `R3-E-S2-CR-F01`、`R3-E-S2-CR-F02`、`R3-E-S2-CR-F03`。
- 本轮不修改 F04 challenge lattice、F05 probe GET body owner 行为或 F06 S3 diagnostic fixture owner。
- 本轮不进入 code re-review，不进入 S3、S4、aggregate deepreview 或后续 gate；不 stage、commit、push。

## 2. 第一性原理与语义 owner 裁决

三个 accepted finding 的动机均成立，修复边界清晰：

1. 未编码 HTTP body 与压缩 body 共享 decoded-cap 事实，owner 是 `web_fetch_orchestrator` 的 body materialization contract；现有生产实现已正确执行 identity decoded cap，缺口仅在 owner-level boundary tests，不能为测试缺口改写生产逻辑。
2. 完整页面文本提取异常后的 HTML fallback 由 `web_playwright_backend._materialize_bounded_page_projection` 直接产生；可观测性必须加在该 fallback owner 分支。S3 才拥有 durable diagnostic schema、payload marker、storage 与 smoke，因此本轮只增加不含原文和 URL 的本地 debug 日志。
3. Browser resource budget failure reason 是 `web_playwright_backend` 内的封闭语义；异常校验、失败 payload 校验与调用点必须复用同一模块级集合及成员常量，不能各自持有字符串字面量。

上述方案只补齐当前 owner contract 和可观测性，不新增公共 schema、兼容分支、下游补偿或通用 tool-security framework，没有过度设计。

## 3. Finding 修复状态

| Finding | 最终状态 | 修复与直接证据 |
|---|---|---|
| `R3-E-S2-CR-F01` | 已修复 | 新增 `test_identity_body_exact_decoded_limit_and_limit_plus_one`：response 不含 `Content-Encoding`，wire budget 为 1024；decoded exact-limit 返回原 body，limit-plus-one 抛 `_FetchBodyLimitExceeded`，并断言 `limit_kind == "decompressed"`、`observed_bytes == limit + 1`。生产 body owner 未改。 |
| `R3-E-S2-CR-F02` | 已修复 | `_materialize_bounded_page_projection` 在 full-text `page.evaluate` 异常分支记录 owner-local debug，然后保持 `page_text = html`。日志不包含 URL、HTML、异常正文或 headers。新增 focused test 注入 full-text evaluate 异常，断言 HTML fallback、调用顺序和 debug 记录。未新增 S3 schema、payload marker、storage 或 smoke 字段。 |
| `R3-E-S2-CR-F03` | 已修复 | 提取 `_BROWSER_DOM_TOO_LARGE_REASON`、`_BROWSER_TEXT_TOO_LARGE_REASON` 与唯一 `_BROWSER_RESOURCE_BUDGET_FAILURE_REASONS`；`_BrowserResourceBudgetExceeded`、`_browser_budget_failure`、DOM/text preflight、完整投影复核与 Markdown 长度调用点全部复用该真源。稳定 reason 值和失败 payload 行为不变。 |

Controller 已拒绝或 deferred 的 finding 保持原裁决：

- `R3-E-S2-CR-F04`：`rejected-with-reason`，infra-only 继续为 `SUSPECTED`，不修改 challenge lattice。
- `R3-E-S2-CR-F05`：`rejected-with-reason`，probe GET 继续只读 headers 后关闭 lease，不消费 body。
- `R3-E-S2-CR-F06`：`deferred-with-owner`，由 R3-E S3 diagnostic projection/storage/smoke slice 处理 fixture owner；本轮不修改。

## 4. Changed files

- `dayu/tools/web/web_playwright_backend.py`
  - 增加 browser budget failure reason 单一真源并迁移当前调用点。
  - 为 full-text evaluate 异常后的 HTML fallback 增加安全 debug 日志。
- `tests/tools/web/test_web_tools_provider.py`
  - 增加 identity decoded-cap exact/limit-plus-one owner test。
  - 扩展 Playwright 测试 Page 以注入 full-text evaluate 错误，并增加 fallback 日志 focused test。
- `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-fix-codex.md`
  - 记录本 fix gate 的 decision、finding 状态、validation、docs decision 与 residual risks。

未修改其余现有 dirty files；未实施 Host、Engine、Fins、S3、S4、aggregate 或 tool-security 代码。

## 5. Validation

1. `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k "identity or playwright or body or decompress or resource_budget"`
   - 结果：`44 passed, 2 skipped, 74 deselected in 2.61s`。
2. `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q`
   - 结果：`118 passed, 2 skipped in 9.86s`。
3. `source .venv/bin/activate && pyright`
   - 结果：`0 errors, 0 warnings, 0 informations`。
   - pyright 仅提示存在新版本，不是类型检查失败。
4. `source .venv/bin/activate && git diff --check`
   - 结果：通过，无 whitespace error 输出。
5. `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-fix-codex.md`
   - 结果：无 whitespace error 输出；退出码 1 仅表示新增 artifact 与 `/dev/null` 存在内容差异。

## 6. README / docs 决策

- 不更新 `tests/README.md`：本轮只补充既有 Web provider 单文件中的 owner-level tests，没有新增测试层级、运行方式或维护规则。
- 不更新根 README、`dayu/README.md` 或 `dayu/config/README.md`：没有用户入口、分层装配、配置或公共工作流变化。
- 不更新设计真源或 control docs：本轮是 controller 已裁决的窄幅 fix gate，主控 bookkeeping 由 controller 持有。
- 本 artifact 是本轮唯一需要新增的文档。

## 7. Residual risks 与 uncovered areas

- `covered by later approved slice`：S3 durable diagnostic schema、payload projection、storage-state lifecycle、smoke oracle，以及 `R3-E-S2-CR-F06` 的 diagnostic budget fixture owner。本轮仅提供 owner-local debug，不抢占 S3 字段语义。
- `covered by later approved slice`：S4 Documents bounded source/read/list/search 工作，本轮未触碰。
- `assigned to later work unit`：Chromium 在 TreeWalker preflight 前已构造内部 DOM 的峰值资源风险，仍归后续 browser sandbox/resource-lane work unit；当前二次复核只保证超限完整投影不跨进程返回。
- `assigned to later work unit`：DuckDuckGo 外部 HTML shape 变化仍按既有严格 fail-closed 行为交由后续 provider maintenance；不引入 loose parsing。
- `assigned to later work unit`：brotli 仍保持 unsupported 且不主动协商；只有未来出现可证明有界的 streaming API 时，才能由 Web codec owner 另行实施。

没有新增或未分类 residual risk，没有 blocking open question。

## 8. Completion status

**COMPLETE — R3-E S2 code-review fix gate only。**

- `R3-E-S2-CR-F01`：已修复。
- `R3-E-S2-CR-F02`：已修复。
- `R3-E-S2-CR-F03`：已修复。
- 明确未实施 S3、S4 或 tool-security；未进入 aggregate gate。
- 未进入 re-review，未 commit，未 push。
- Controller 可用的下一入口：R3-E S2 code re-review；本 artifact 不自行进入 re-review，后续由 controller 继续推进。
- Artifact path：`docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-fix-codex.md`。
