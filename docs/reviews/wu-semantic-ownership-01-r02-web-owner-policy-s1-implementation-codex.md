# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 implementation — AgentCodex

## 1. Gate、真源与结论

- Umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`，内部 remediation slice `R02-S1`；不是新 WU、feature 或 issue。
- 执行真源：superseding accepted-plan commit `2d42ceb6`、control commit `70ffc917`、最终 946 行 `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`。
- Controller correction 真源：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-controller-validation.md`。
- 本轮结论：`R02-S1-CV-F01..F04` 已按同一 S1 owner boundary 关闭；fresh tests、逐文件 coverage、完整 pyright、README、source/propagation/security/deferred/allowed-file scans 与 `git diff --check` 全部通过。
- 当前 gate：`WAITING CONTROLLER RE-VALIDATION`。未 commit、push、建 PR、更新 control 或进入 S2/S3/R03。

问题动机成立：旧 aggregate 使 HTTP、Browser、Diagnostic 三类资源事实混入同一 owner；首次实现又使 ordinary fetch failure 绕过当前 config 的 Diagnostic child、utility 在 private/local custom-port 路径发生行为回归、`WebToolsConfig` 重复 provider defaults，并用部分无关 helper assertions 支撑覆盖率。修复均落在各事实的 parser/config snapshot、projection 或既有 policy construction boundary，没有下游 fallback、兼容 shim 或新 parser。

## 2. Exact implementation changed files

### Production（9）

1. `dayu/tools/web/provider.py`
2. `dayu/tools/web/web_diagnostics.py`
3. `dayu/tools/web/web_egress_policy.py`
4. `dayu/tools/web/web_fetch_orchestrator.py`
5. `dayu/tools/web/web_http_session.py`
6. `dayu/tools/web/web_playwright_backend.py`
7. `dayu/tools/web/web_resource_budget.py`
8. `dayu/tools/web/web_search_providers.py`
9. `dayu/tools/web/web_tools.py`

### Config / utility（2）

1. `dayu/config/tool_discovery.json`
2. `utils/diagnose_web_access.py`

正确且唯一的 packaged config 路径是 `dayu/config/tool_discovery.json`；`dayu/config/defaults/tool_discovery.json` 不存在且未创建。

### Tests（3）

1. `tests/runtime/test_config_loader.py`
2. `tests/tools/web/test_diagnose_web_access.py`
3. `tests/tools/web/test_web_tools_provider.py`

### README（2）

1. `dayu/config/README.md`
2. `tests/README.md`

### 唯一 implementation artifact（1）

1. `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-implementation-codex.md`

`docs/host/issues-implementation-control.md` 与 Controller validation artifact 是进入本轮前已存在的 Controller-owned dirty paths，本轮保持只读；plan、control、Controller artifact 与既有 review artifacts均未由 AgentCodex修改。

## 3. R02-S1-CV findings closure

### F01 — ordinary fetch failure 消费当前 Diagnostic owner — closed

- 删除 `web_tools.py` 的全局 diagnostic error cap fallback；production 不再 import/读取 `DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET` 作为 ordinary failure default。
- `_raise_fetch_failure` 新增无 default、必填 `diagnostic_error_chars: int`；所有 URL normalization、redirect、timeout、HTTP/TLS、challenge、URL safety、body limit、conversion、empty-content 与 browser terminal failure call sites均显式传入当前 owner field。
- `_fetch_web_page_business` 只从本次 immutable `WebToolsConfig.resource_budgets.diagnostics.error_chars` 取得该字段；`web_tools.py` 仍是 aggregate 到 child owner 的唯一 projection point。
- 新增 non-default cap owner test：`error_chars=5` 控制普通 invalid-URL failure；扩展 ordinary failure matrix证明 HTTP/runtime/browser escalation 仍消费同一 config snapshot。
- 该 cap 暴露 `web_diagnostics.project_error_message` 的 owner-level根因：parser接受任意正整数，但固定 truncation suffix 在 cap 小于 suffix 时会抛 `ValueError`。`web_diagnostics.py` 现按 cap 决定是否附加 suffix，使所有合法正 cap 都可有界投影；schema `web-diagnostics-v2`、revision 2、redaction、safe URL 与 payload shape均未改变。这是关闭 F01 所必需的 owner 修复，不是无必要 diff。

### F02 — utility local/custom-port S1 retained behavior — closed

- 只在 `utils/diagnose_web_access.py` 既有 `_build_single_diagnostic_payload` policy construction boundary，把现有 `allow_private_network_url` 同时投影给 `allow_private_network` 与 `allow_custom_port`。
- 没有新增 raw config parser、CLI 字段、S2 transport 或 S3 lifecycle cleanup。
- direct regression 使用 `http://127.0.0.1:43117/fixture.pdf`，证明 private/local diagnostic 模式继续允许既有 custom-port 行为。

### F03 — WebToolsConfig 删除重复 defaults — closed

- `WebToolsConfig` 保持 `frozen=True, slots=True`，全部字段变为无 default 的显式输入；provider、timeout、result/truncate、五 bool、channel、storage directory、transport policy 与 budgets均只能由 caller提供。
- production `WebToolsConfig(...)` 构造点扫描只命中 `provider._parse_config` 一处；raw/provider defaults 仍只由 parser owner保存并应用。
- owner test逐字段断言 `dataclasses.MISSING`，防止 downstream snapshot重新拥有 parser defaults。

### F04 — owner tests、typed callables 与 coverage — closed

- 删除 Controller 指出的四个无关 grouped helper tests：storage/URL/scalar、meta-refresh internals、routing/stream-name heuristics、Playwright channel/storage/warmup helper集合。
- 从 `test_playwright_process_entry_projects_separate_diagnostic_owner` 删除无关 storage/channel assertions；该 test只断言 Browser worker kwargs 与独立 Diagnostic process input。
- coverage补充只覆盖本 slice owner contracts：HTTP child的 declared/decoded/codec bounds、Browser child的 DOM/text/Markdown终态、Diagnostic process projection、ordinary failure child cap与 retained transport/security paths。
- Controller re-validation指出的最后四个无注解 lambda 已分别替换为窄 typed helper：diagnostic response-body materialize no-op、custom-port private resolver、Playwright worker picklability predicate、process-session no-op。四者均完整声明参数/返回类型并具有中文 Args/Returns/Raises docstring；process-session helper以 `False` 精确表示未执行 session 切换，测试行为不变。
- 新增/修改 callable均使用精确 typed signature；相对 `70ffc917` 的 added-line scan对任意 `lambda` 与 `**kwargs` 均为零。
- synthetic browser context fake改为显式 `viewport/user_agent/locale/accept_downloads/ignore_https_errors/extra_http_headers/storage_state` 参数；没有 loose catch-all。
- 所有实际 changed production file coverage仍为 `80%–100%`，没有 exclusion、降低门槛或总体百分比替代逐文件 gate。

## 4. S1 owner contract 与行为不变量

### Config / typed owners

- packaged config显式保存五个独立 bool：private=`true`、custom-port=`true`、peer-proof=`false`、environment-proxy=`true`、browser=`true`。
- `provider._parse_config` 是唯一 raw parser owner；missing field补对应 typed default，非 bool、unknown group/field、wrong object、bool-as-int、零和负数均精确拒绝。
- `resource_budget` 只有 `http`、`browser`、`diagnostics` 三个 child group；冻结值为 HTTP 128/256 MiB、Browser warmup 1 MiB、DOM/text 16/8 Mi chars、Diagnostic error/events 8192/512。
- `HttpResourceBudget`、`BrowserResourceBudget`、`DiagnosticResourceBudget` 均为 frozen typed owner；`WebResourceBudgets` 是无 default aggregate；`WebToolsConfig` 是无业务 default 的 immutable snapshot。
- search/body materialization只接 HTTP；warmup/render worker只接 Browser；failure/process diagnostics只接 Diagnostic；content-type probe无 budget。
- Playwright worker kwargs只含 Browser child，process wrapper独立接 Diagnostic child；不存在 aggregate worker bag、extra payload、alias/facade、dual schema或兼容 default。

### Retained S1 transport / browser / utility behavior

- `_send_authorized_request` 仍无 `transport_policy` 参数，继续 `trust_env=False`、`proxies={}`、numeric pin/no-proxy；未提前 S2。
- `web_search_providers.py` 仍有三个模块级 raw sender：两处 `requests.post`、一处 `requests.get`；provider选择、endpoint、credential、query/domain与LLM-facing projection不变。
- Playwright仍在两个既有入口以前置 `egress_policy.allows_private_network` 决定 browser availability；private/browser coupling、process start、route/navigation、storage-state input与error reasons不变。
- redirect逐 hop authorization、approved numeric addresses、peer mismatch、mixed/private/multicast/unspecified deny、response lease、containment/symlink与challenge contract保留。
- utility storage-state output/TTL/lifecycle/reconcile、ordinary writer、profile schema与CLI保持；utility-local `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 和 `--max-network default=80` 保持并留给 S3。
- 没有 Issue #178、统一 authorization、R03、S2 sender/proxy/peer或S3 cleanup实现。

## 5. Fresh tests 与 coverage

### Tests

| Gate | Result |
|---|---:|
| S1 umbrella filter：`test_web_tools_provider.py -k 'config or resource_budget or egress_policy or provider'` | `159 passed, 1 skipped` |
| Diagnostic direct nodes：HTTP exact/over + utility local custom-port | `2 passed` |
| F04 exact-callable direct nodes：materialize/resolver/picklable/process-session | `4 passed` |
| Affected owner/config/direct matrix | `213 passed, 1 skipped` |
| Full allowed three-file suite | `247 passed, 1 skipped` |
| Accepted-plan coverage test run | `212 passed, 1 skipped` |

唯一 skip是既有条件式 smoke；没有 skip任何新增 owner case，也没有提前运行/改写 S3 lifecycle contract。

### Changed production file coverage

Coverage data：`workspace/tmp/.coverage-r02-s1`；JSON：`workspace/tmp/coverage-r02-s1.json`。每个文件均独立执行 `coverage report --include=<exact-file> --fail-under=80` 并返回 0。

| File | Coverage |
|---|---:|
| `dayu/tools/web/provider.py` | 93% |
| `dayu/tools/web/web_resource_budget.py` | 100% |
| `dayu/tools/web/web_egress_policy.py` | 85% |
| `dayu/tools/web/web_http_session.py` | 87% |
| `dayu/tools/web/web_tools.py` | 80% |
| `dayu/tools/web/web_diagnostics.py` | 91% |
| `dayu/tools/web/web_search_providers.py` | 87% |
| `dayu/tools/web/web_fetch_orchestrator.py` | 82% |
| `dayu/tools/web/web_playwright_backend.py` | 80% |

`utils/**` 按 AGENTS 免 coverage；F02已有 direct behavior node。

## 6. Pyright、README、source/propagation/security scans

### Pyright / whitespace

- `python -m pyright`：`0 errors, 0 warnings, 0 informations`；覆盖完整配置范围，无新增 exclude/skip。
- `git diff --check`：exit 0。

### Legacy / owner scans

- `dayu tests utils README.md` 扫描 `WebResourceBudget` 与七个 flat fields：零命中；九文件旧 direct-reference闭集零残留。
- `WebToolsConfig(` production scan只命中 `dayu/tools/web/provider.py` 一处。
- `web_tools.py` 扫描无 `_DEFAULT_WEB_DIAGNOSTIC_ERROR_CHARS` 与 `DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET`；`_raise_fetch_failure` 的 required owner field及所有 call sites均有显式命中。
- `git diff -U0 70ffc917 -- <two Web test files> | rg '^\+.*lambda'`：零命中；四个 Controller 指定 seam均已改为窄 typed helper。
- added-line loose callable scan：`**kwargs`、无注解 lambda与 loose lambda均零命中。
- 旧数值 scan命中分类：`dayu/config/README.md` 的 `1000000` 是模型 context window；test中的 `1024` 是局部边界 fixture；`64 * 1024` 是既有 streaming chunk size。均不是 Web旧部署 ceiling或第二默认。

### S1 / S2 / S3 propagation

- 五 bool 与三 budget groups均建立 `tool_discovery.json -> provider._parse_config -> WebToolsConfig -> exact child consumer` 链；下游不重读 raw config。
- `transport_policy` production命中只在 provider snapshot构造与 `WebToolsConfig` 字段；sender仍无该参数。
- raw search sender scan精确命中三处；browser/private coupling精确命中两个既有 production入口。
- S3 lifecycle scan继续命中既有 utility/tests；utility zero-context diff只含 HTTP/Browser type/constants/forwarding与 F02 policy construction，不含 lifecycle/writer/profile/parser变化。
- `_DEFAULT_DIAGNOSTIC_ERROR_CHARS|1_024|--max-network|default=80` 只确认既有 S1 transitional utility状态，没有新 producer或提前删除。

### Security / deferred scope

- diagnostics scan确认 `WEB_DIAGNOSTIC_SCHEMA_VERSION = "web-diagnostics-v2"`、revision 2、safe URL、redaction与challenge evidence仍有 owner/test命中。
- retained security scan确认 approved addresses、peer mismatch、multicast/unspecified deny、safe redirects与response lease owner/test仍在；affected/full suite通过。
- `web_challenge_detection.py`、根 `README.md`、`dayu/README.md` 及 Host/Engine/Fins README均零 diff。
- `authorization framework|policy DSL|capability token|storage state refresh|storage state retention|Issue #178|R03` 对 `dayu utils tests README` 扫描零命中。

### Allowed-file scan

- `git diff --name-only 70ffc917 --` 中 implementation tracked paths恰为本 artifact §2列出的16个 config/production/utility/test/README文件。
- 同一列表额外包含进入本轮前已存在的 Controller-owned `docs/host/issues-implementation-control.md` dirty path；本轮未写入。
- `git status --short` 另列固定 implementation artifact与进入本轮前已存在的 Controller validation artifact；后者保持只读。
- 除上述 Controller-owned paths外，没有第五个 drift-moved文件、非 allowlist production/test/README、plan或既有 review diff。

## 7. README decision

- `dayu/config/README.md`：`updated`。配置读者需要五 bool、三个 child owner、局部 override、冻结值及 S1 snapshot-only时序。
- `tests/README.md`：`updated`。测试目录事实增加 ordinary failure的非默认 Diagnostic cap与 utility private/local custom-port retained behavior，并保留 S1/S2/S3时序说明。
- 根 `README.md`：`no-update-with-evidence`。没有用户可见安装、初始化、CLI参数、入口、默认输出、日志位置或工作流变化。
- `dayu/README.md` 与 Host/Engine/Fins/UI README：`no-update-with-evidence`。没有层级或装配关系变化，且不在 S1 allowlist。

## 8. Residual risks 与 handoff

- S2 intentionally pending：transport policy仅保存于 snapshot；sender/proxy/peer-proof与browser capability解耦尚未实施。
- S3 intentionally pending：utility credential/storage lifecycle与local `1_024/default=80`仍按计划保留。
- `web_tools.py` 与 `web_playwright_backend.py` coverage均为门槛值80%；owner/security paths已有直接 tests，但后续 slice修改仍须重新逐文件验证。
- 本轮没有真实 allowlist failure、第五个 drift文件、pyright/coverage/test/security failure。

**停止于 Controller re-validation gate；不得自行 commit、更新 control、启动 code review 或进入 S2/S3/R03。**
