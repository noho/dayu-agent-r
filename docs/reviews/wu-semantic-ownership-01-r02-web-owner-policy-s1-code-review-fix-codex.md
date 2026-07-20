# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 Code Review Fix — AgentCodex

## 1. Gate identity、真源与结论

- Umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01`。
- 内部 remediation slice：既有 `R02-S1` Web config owner 与 typed policy split；不是新 WU、sub-WU、feature 或 issue。
- Fix base：`70ffc917..working tree`。
- 唯一 finding disposition 真源：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-controller-adjudication.md`。
- Controller validation follow-up 真源：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-fix-controller-validation.md`。
- Accepted findings：`R02-S1-CR-F01..F03` 与 follow-up `R02-S1-CR-CV-F01`，本 artifact 逐项记录 owner-side closure。
- 结论：三项原 accepted finding 与 Controller follow-up 均已实现并通过 direct/full tests、九个 production 文件逐文件 coverage、完整 pyright、whitespace 与指定 source scans；当前状态为 `WAITING CONTROLLER RE-VALIDATION`。
- Stop boundary：未 commit、push、修改 control/controller/review/plan、启动 re-review，或进入 R02-S2/S3、Issue #178、R03、统一 authorization。

问题动机成立。F01 的根因是唯一 raw parser owner 未校验自身顶层字段闭集；F02 的原始审计只覆盖 added-definition line，Controller validation 进一步证明 signature span 被本 slice 触及的既有 definition 也必须执行完整 docstring contract；F03 的根因是 diagnostics owner 为适配 runtime primitive 而在小 cap 下删除截断信号。修复分别落在 raw parser boundary、definition 自身和 diagnostics v2 error projection boundary，没有下游 fallback、兼容 alias、第二 parser 或 runtime primitive 修改。

## 2. Exact fix-authored changed files

### Production（5）

1. `dayu/tools/web/provider.py`
2. `dayu/tools/web/web_diagnostics.py`
3. `dayu/tools/web/web_fetch_orchestrator.py`
4. `dayu/tools/web/web_playwright_backend.py`
5. `dayu/tools/web/web_tools.py`

### Tests（2）

1. `tests/tools/web/test_web_tools_provider.py`
2. `tests/tools/web/test_diagnose_web_access.py`

### README（2）

1. `dayu/config/README.md`
2. `tests/README.md`

### Fix artifact（1）

1. `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-fix-codex.md`

本 fix 没有修改 `dayu/config/tool_discovery.json`、其余四个 S1 production 文件（`web_egress_policy.py`、`web_http_session.py`、`web_resource_budget.py`、`web_search_providers.py`）、`tests/runtime/test_config_loader.py`、`utils/diagnose_web_access.py` 或 implementation artifact；这些路径的既有 S1 diff 保持不变。Controller follow-up 对新增的三个 production 路径仅补 docstring。`docs/host/issues-implementation-control.md`、accepted plan、两路 code review、Controller disposition/validation artifacts均为只读。当前相对 `70ffc917` 的 tracked slice target 仍是 accepted S1 的九个 production 文件、一个 packaged config、一个 utility、三份 tests、两份 README，以及进入本轮前已存在的 Controller-owned control dirty path；没有新增 production/test/README allowlist 路径。

## 3. Finding closure

### R02-S1-CR-F01 — closed

- `provider._parse_config` 继续是 final Web provider record 的唯一 raw JSON parser owner。
- 新增 `_CONFIG_FIELDS: frozenset[str]`，精确包含当前全部 12 个合法顶层字段：四个既有 scalar、五个 S1 bool、两个 Playwright 字段和 nested `resource_budget`。
- `_parse_config` 在读取任何字段前计算 unknown 闭集；存在未知 key 时选择稳定字段名并抛出包含 `web provider config.<field>` 精确路径的 `ValueError`。没有 alias、loose ignore、第二 parser 或 schema DSL。
- Direct test 使用 typo `allow_prvate_network_url` 验证精确拒绝，并断言完整 12-field 闭集。
- 同一 direct test 把合法 partial final record 直接交给 parser，证明显式 `provider`、HTTP 单 field override 与其余 bool/group/field defaults按局部 owner 保持。
- ConfigLoader 两个既有 direct nodes继续证明同 id record 整条替换、不 deep merge，以及 partial replacement 不会从 package sibling 偷取字段；本 fix 未修改 ConfigLoader 或其测试。

### R02-S1-CR-F02 — closed

- 原 fix 闭集严格来自当时 `git diff -U0 70ffc917 -- '*.py'` 的 86 个 added definition lines，而不是 reviewer 示例子集。Controller follow-up 补充既有 definition 文档后，current diff hunk 对齐使最终 added-definition 闭集变为 89 个；两次扫描均为 `issues=0`。
- 最终 AST/docstring scan 共识别 89 个新增 function/method/nested fake/test function；全部有中文 docstring，并包含参数、返回值、异常说明。扫描同时逐个校验显式参数具有类型注解、在 docstring 中出现，且返回类型存在。
- 新增 test functions、`_IdentityZstd*` methods、`_SyntheticProcessPlaywrightWorker.__call__`、保留 closure 的 queue/recorder/budget fakes均补齐精确文档。
- 所有无状态且不捕获 closure 的新增 nested helper均提升为模块级私有 helper；最终 scan 为 `closure_free_added_nested_helpers=0`。确实捕获 case-local queue、recorder、browser 或 budget 的 nested fake保留嵌套。
- Added-line/AST loose callable scan结果：added lambda=`0`、added `*args`/`**kwargs`=`0`、无注解参数/返回=`0`、`type: ignore`/`hasattr`/`getattr`=`0`。
- 没有通用 fixture/builder、god bag、loose kwargs 或 baseline docstring/lambda 旧债清理；改动只覆盖本 slice added definitions。

Controller validation 将 F02 closure 扩展到“function signature span 与 `git diff -U0 70ffc917` added lines 相交”的完整闭集。复现真源算法得到 `signature_touched=132 issues=14`，按 current AST 精确限定名逐项补齐：

1. `dayu.tools.web.web_fetch_orchestrator._fetch_and_convert_content`、`dayu.tools.web.web_playwright_backend._fetch_and_convert_with_playwright`、`dayu.tools.web.web_tools._fetch_and_convert_content`。
2. `tests.tools.web.test_web_tools_provider.test_playwright_budget_failure_projects_stable_tool_error`、`_SyntheticNestedPlaywrightWorker.__call__`、`_LiveBrowserLongRunningWorker.__call__`、`_BlockedPlaywrightWorker.__call__`。
3. `test_playwright_public_direct_reports_typed_egress_policy_unavailable.unexpected_worker`、`test_fetch_playwright_url_safety_projects_permission_denied.fake_fetch_and_convert_with_playwright`、`test_fetch_playwright_cancel_projects_to_host_cancelled.fake_fetch_and_convert_with_playwright`、`test_try_playwright_fallback_pre_cancel_does_not_start_playwright.fake_fetch_and_convert_with_playwright`。
4. `test_playwright_unpicklable_worker_fails_closed.fake_worker`、`test_fetch_playwright_fallback_receives_channel_and_storage_state_path.fake_fetch_and_convert_with_playwright`、`test_fetch_playwright_fallback_uses_empty_storage_state_when_dir_empty.fake_fetch_and_convert_with_playwright`。

上述 14 个 definition 只补完整中文参数、返回值、异常文档，并明确本 slice 新增的 HTTP/Browser/Diagnostic child budget 与 cancellation 参数；没有修改签名、行为、test flow 或 owner placement，也没有清理未触及 baseline 旧债。相同算法最终结果为 `signature_touched=132 issues=0`。

### R02-S1-CR-F03 — closed

- 修复只落在 `web_diagnostics.project_error_message` owner boundary；`dayu.runtime.diagnostic_text.truncate_diagnostic_text` 公共 contract 零 diff。
- 脱敏仍先完整执行。未超限文本直接保持，无截断误报。
- cap=`1` 且发生截断时返回单字符明确 marker `…`；cap=`2..14` 使用同一最小 marker并由 runtime primitive 保证有界；cap 大于完整 suffix 长度 `14` 时继续使用原 `...<truncated>`。
- Direct test锁定：cap=`1` 返回 `…`；cap=`14` 返回 13 字符前缀加 `…`；cap=`15` 返回 1 字符前缀加完整 `...<truncated>`；未超限短文本原样返回。
- `WEB_DIAGNOSTIC_SCHEMA_VERSION="web-diagnostics-v2"`、revision `2`、redaction、safe URL、payload shape与 caller projection均未修改；对 schema/revision/redaction/payload 的 zero-context diff scan为空。

## 4. Tests 与 coverage

### Direct tests

| Gate | Result |
|---|---:|
| F01 typo/partial + F03 cap 1/14/15/untruncated direct nodes | `2 passed` |
| ConfigLoader record-replace / partial-no-deep-merge nodes | `2 passed` |
| F02 moved helper/fake affected nodes | `12 passed` |
| Controller follow-up signature-touched affected nodes | `14 passed` |

### 完整允许三文件 suite

命令：

```bash
source .venv/bin/activate
pytest tests/tools/web/test_web_tools_provider.py \
  tests/runtime/test_config_loader.py \
  tests/tools/web/test_diagnose_web_access.py -q
```

结果：`249 passed, 1 skipped`。唯一 skip 是既有条件式 smoke；没有 skip任一 F01/F02/F03 direct node。

### 九个 changed production 文件逐文件 coverage

Coverage run 使用完整允许三文件 suite；data 为 `workspace/tmp/.coverage-r02-s1-cr-fix`，JSON 为 `workspace/tmp/coverage-r02-s1-cr-fix.json`。每个文件独立执行 `coverage report --include=<exact-file> --fail-under=80` 并 exit `0`。

| File | Coverage |
|---|---:|
| `dayu/tools/web/provider.py` | 93% |
| `dayu/tools/web/web_resource_budget.py` | 100% |
| `dayu/tools/web/web_egress_policy.py` | 86% |
| `dayu/tools/web/web_http_session.py` | 87% |
| `dayu/tools/web/web_tools.py` | 80% |
| `dayu/tools/web/web_diagnostics.py` | 92% |
| `dayu/tools/web/web_search_providers.py` | 87% |
| `dayu/tools/web/web_fetch_orchestrator.py` | 82% |
| `dayu/tools/web/web_playwright_backend.py` | 80% |

`utils/**` 仍按项目约束免 coverage；本 fix 没有修改 utility production code，既有 utility behavior direct tests通过。

## 5. Pyright、README 与 source scans

### Pyright / whitespace

- `python -m pyright`：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：exit `0`。
- fix artifact 另以 no-index whitespace check验证；预期因新文件内容差异返回 `1`，但无 whitespace diagnostic。

### Added-definition / loose callable / legacy owner

- Added-definition AST scan：`added_definitions=89 added_lambdas=0 closure_free_added_nested_helpers=0 issues=0`；Controller follow-up 前记录的 86 是修正文档扩展 diff hunk 前的同口径结果。
- Signature-touched AST scan：`signature_touched=132 issues=0`；14 个 Controller validation 缺口已归零。
- Added-line `lambda|**kwargs|type: ignore|hasattr|getattr` scan：零命中。
- `WebResourceBudget` 与七个 legacy flat fields对 `dayu tests utils README.md`：零命中。
- 旧数值 scan只命中配置 README 的模型 context window `1000000`、测试局部边界 fixture `1024` 与既有 streaming chunk `64 * 1024`；均不是 Web部署 ceiling、旧 owner 或 backend second default。

### S1 / S2 / S3 时序

- `transport_policy` production消费只在 provider构造与 `WebToolsConfig` snapshot；sender仍没有该参数。
- `web_search_providers.py` 仍精确保留两处 `requests.post` 和一处 `requests.get`。
- `web_playwright_backend.py` 仍精确保留两处 `allows_private_network` browser/private coupling。
- S3 storage lifecycle/CLI/profile/writer符号仍存在；对 `utils/diagnose_web_access.py` 的 lifecycle与 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS/default=80` zero-context diff scan为空。
- utility-local `_DEFAULT_DIAGNOSTIC_ERROR_CHARS=1_024` 与 `--max-network default=80` 仍只属于已登记 S1 transitional state，未扩散到新 producer。

### Deferred / security

- `authorization framework|policy DSL|capability token|storage state refresh|storage state retention|Issue #178|R03` 对 `dayu utils tests README.md`：零命中。
- `dayu/runtime/diagnostic_text.py` 与 `web_challenge_detection.py` 相对 base均零 diff。
- diagnostics scan确认 schema v2/revision 2与两个截断 marker；retained-source scan继续命中 redirect、approved addresses、peer、multicast/unspecified、containment/symlink owners及对应 tests。
- 完整允许 suite通过，覆盖 retained DNS/redirect/peer/body/browser/diagnostics/security contract；本 fix未修改 payload、revision、challenge detector或安全 primitive。

## 6. README decision

- `dayu/config/README.md`：`updated`。配置读者需要知道 Web final record 的 ConfigLoader record-replace、合法 partial/local defaults和顶层 unknown精确拒绝之间的关系。
- `tests/README.md`：`updated`。同步记录顶层 typo direct test，以及 cap=`1/14/15`和未超限无误报的 diagnostics owner contract。
- 根 `README.md`：`no-update-with-evidence`。安装、初始化、CLI参数、最终用户入口、默认输出、日志位置与工作流未变。
- `dayu/README.md` 与 Host/Engine/Fins/UI README：`no-update-with-evidence`。分层、装配和对应模块职责未变。
- Controller follow-up：`no-update-with-evidence`。本轮只补既有 callable docstring，产品、测试与读者 contract 均未变化；不再扩写 README，保留原 F01/F03 所需更新。

## 7. Residual risks 与 handoff

- Accepted findings：`R02-S1-CR-F01=closed`、`R02-S1-CR-F02=closed`、`R02-S1-CR-F03=closed`、`R02-S1-CR-CV-F01=closed`。
- Accepted observations保持原分类：`web_tools.py`与`web_playwright_backend.py` coverage位于80%门槛，S2修改时必须重新逐文件验证；S1 queue-based test与synthetic browser doubles的维护风险不改变当前 owner contract。
- S2 transport/browser execution与S3 credential lifecycle/utility diagnostic defaults仍由后续 approved slices拥有；本 fix没有提前实现。
- 无 unclassified residual risk、allowlist drift、pyright/test/coverage/security failure。
- 下一入口：等待 Controller re-validation。不得由 AgentCodex自行 commit、进入双路 re-review、R02-S2/S3、Issue #178、R03或统一 authorization。

Artifact path：`docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-fix-codex.md`。
