# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 Controller Validation

## 1. Gate identity and verdict

- Umbrella: existing `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation.
- Internal remediation sub-WU / slice: `R02-S1` Web config and typed owner split.
- Accepted plan truth: `2d42ceb6` and `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`.
- Validation base: `70ffc917` with the uncommitted AgentCodex implementation and `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-implementation-codex.md`.
- Verdict: **FAIL — RETURN TO THE SAME IMPLEMENTATION TASK FOR CORRECTION**.

The implementation has the correct overall direction and passes its reported tests, coverage and pyright, but four owner/scope findings remain. It must not enter dual code review until AgentCodex closes all four and Controller re-validates the corrected worktree. This is not a new gate, slice, sub-WU or product discussion.

## 2. Independently confirmed correct work

- Packaged Web config contains the accepted five booleans and three nested budget groups with the exact frozen values.
- `WebResourceBudget` and the flat complete-object parser are removed; the old class/flat-field scan is empty across `dayu`, `tests`, `utils` and root README.
- `HttpResourceBudget`, `BrowserResourceBudget`, `DiagnosticResourceBudget` and the no-default `WebResourceBudgets` aggregate exist at the intended owner boundary.
- HTTP response materialization, browser warmup/rendering, browser process diagnostics and search-result visibility have been split onto the intended child types or typed egress policy.
- `_probe_content_type` no longer receives a meaningless budget.
- S1 has not threaded `WebHttpTransportPolicy` into the sender; pinned/no-proxy behavior, raw provider requests, browser/private coupling and storage-state lifecycle remain in their later-slice state.
- The modified/untracked implementation files stay inside the accepted R02-S1 allowlist. `web_challenge_detection.py`, `web_diagnostics.py`, deferred Issues and unified authorization code have no diff.

## 3. Accepted Controller validation findings

### R02-S1-CV-F01 — HIGH — diagnostic budget override is bypassed in ordinary fetch failures

Direct evidence:

- `dayu/tools/web/web_tools.py:177` defines `_DEFAULT_WEB_DIAGNOSTIC_ERROR_CHARS` directly from `DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET`.
- `dayu/tools/web/web_tools.py:1208` `_raise_fetch_failure(...)` has no diagnostic budget/owner-field input and always passes that global default to `failed_projection(...)`.
- All ordinary HTTP, URL-safety, body-limit, conversion, challenge and empty-content failures call this helper. Therefore a provider config override such as `resource_budget.diagnostics.error_chars=5` is present in `WebToolsConfig.resource_budgets.diagnostics` but does not control those diagnostics.
- The accepted plan §4.2, §8.2 item 6 and §8.3 require `web_tools.py` to be the unique aggregate projection point and require diagnostics projection to receive `DiagnosticResourceBudget` or its explicit owner fields.

Required correction:

- Remove the global fallback path from production execution.
- Make ordinary fetch failure projection consume the current immutable config snapshot's diagnostic child budget or an explicit required owner field, and update every call site without a compatibility default.
- Add an owner-level test proving a non-default diagnostic error cap controls an ordinary fetch failure, not only Playwright process errors.

### R02-S1-CV-F02 — MEDIUM — S1 silently regresses diagnostic local/custom-port behavior

Direct evidence:

- Before this slice, `WebEgressPolicy(allow_private_network=True)` allowed a legal custom port because the custom-port check was coupled to the private flag.
- The new constructor adds `allow_custom_port=False`; `utils/diagnose_web_access.py:2705` still constructs only `WebEgressPolicy(allow_private_network=options.allow_private_network_url)`.
- Controller reproduced `WebEgressPolicy(allow_private_network=True).authorize_http_target("http://127.0.0.1:43117/fixture", ...)` failing with `custom port is not allowed`.
- The accepted S1 drift plan limits the utility move to HTTP/Browser budget type propagation and requires its CLI/profile/browser-availability behavior to remain unchanged until S3. The current change is therefore an accidental cross-owner behavior regression, not the accepted custom/private split.

Required correction:

- Preserve the accepted S1 diagnostic utility behavior explicitly at its policy construction boundary, without adding a second raw config parser, a new CLI field, S2 transport behavior or S3 cleanup.
- Add a focused regression for the utility's existing private/local custom-port diagnostic path.

### R02-S1-CV-F03 — MEDIUM — `WebToolsConfig` still owns a second set of provider defaults

Direct evidence:

- `provider.py` now defines `_DEFAULT_PROVIDER`, `_DEFAULT_REQUEST_TIMEOUT_SECONDS`, `_DEFAULT_MAX_SEARCH_RESULTS`, `_DEFAULT_FETCH_TRUNCATE_CHARS`, channel and storage-directory defaults and uses them in the sole raw parser.
- `WebToolsConfig` repeats the same values as dataclass field defaults (`"auto"`, `20.0`, `8`, `80_000`, `"chrome"`, `.dayu/web_tools_storage_states`).
- Only `provider._parse_config` constructs `WebToolsConfig` in production. Leaving constructor defaults creates two writable semantic owners for the same provider facts and permits bypassing the sole parser contract.

Required correction:

- Make `WebToolsConfig` a value-only immutable snapshot whose fields are all supplied by the parser; do not retain a second set of business defaults in the downstream dataclass.
- Keep packaged/default conformance tests anchored at the provider parser and typed budget constants.

### R02-S1-CV-F04 — MEDIUM — coverage additions freeze unrelated helper behavior and use loose substitutes

Direct evidence:

- `tests/tools/web/test_web_tools_provider.py` grew by 1,723 lines and the final changed-file coverage is exactly `80%` for `web_tools.py`, `web_fetch_orchestrator.py` and `web_playwright_backend.py`.
- New grouped tests such as `test_web_helper_boundaries_preserve_storage_url_and_scalar_semantics`, `test_meta_refresh_parser_keeps_exact_owner_failure_inputs`, `test_fetch_routing_helpers_preserve_exact_content_owner_rules` and `test_playwright_owner_helpers_keep_strict_failure_and_warmup_boundaries` assert storage cookie parsing, URL formatting, scalar argument helpers, meta-refresh internals, stream-name heuristics, picklability, channel/storage normalization and warmup branches that S1 did not change.
- `test_playwright_process_entry_projects_separate_diagnostic_owner` also appends unrelated storage/channel assertions.
- Newly added callables use loose `resolve_timeout_budget=lambda timeout_seconds, **kwargs: ...` and `convert_html=lambda **kwargs: ...`, despite the accepted plan requiring exact wrapper/fake/callable signatures for the migrated owner inputs.
- These tests can make the line percentage pass while freezing accidental implementation details and obscuring the actual child-budget propagation contract, contrary to `AGENTS.md` and the accepted plan.

Required correction:

- Remove or refactor unrelated grouped assertions so new tests directly exercise S1 owner contracts and retained behavior that the migrated signatures can actually affect.
- Replace newly introduced loose callables with exact typed substitutes.
- Keep every modified production file at `>=80%`; do not solve this finding by lowering, excluding or gaming the coverage gate.

## 4. Independent validation evidence

Commands and results run by Controller on the pre-correction worktree:

- Affected owner/config/direct matrix: `207 passed, 2 skipped`.
- Full pyright: `0 errors, 0 warnings, 0 informations`.
- Controller coverage rerun: provider `93%`, resource budget `100%`, egress `85%`, HTTP session `87%`, Web tools `80%`, search providers `87%`, fetch orchestrator `80%`, Playwright backend `80%`.
- `git diff --check`: pass.
- Legacy `WebResourceBudget` and flat-field scan: zero matches.
- S1 transitional utility diagnostic `1_024` / `default=80`: still present as required for later S3 removal.

These passing checks establish build/test health only; they do not override the four direct owner/scope findings above.

## 5. Scope and next gate

AgentCodex must correct all `R02-S1-CV-F01..F04` in the same implementation task, update the implementation artifact with exact changed files and fresh validation evidence, and stop for Controller re-validation. No S2 sender/proxy/peer/browser behavior, S3 storage lifecycle cleanup, Issue 178 work, R03 work or unified tool authorization design is authorized.

## 6. Correction re-validation

### 6.1 Finding disposition

- `R02-S1-CV-F01`：**closed**。`_raise_fetch_failure` 的 `diagnostic_error_chars` 已改为无 default 的必填 owner field；ordinary URL、redirect、timeout、HTTP/TLS、challenge、body、conversion、empty-content 与 browser terminal failure 均从本次 `WebToolsConfig.resource_budgets.diagnostics` 显式投影。全局 fallback 已删除，并有非默认小额度和失败矩阵 direct tests。
- `R02-S1-CV-F02`：**closed**。诊断 utility 只在既有 policy construction boundary 将现有 private/local 开关同时投影给 custom-port，保持 S1 前的本地自定义端口诊断行为；没有新增 parser/CLI 字段、S2 transport 或 S3 lifecycle 逻辑，并有 direct regression。
- `R02-S1-CV-F03`：**closed**。`WebToolsConfig` 全字段无 default；production 构造点只剩 `provider._parse_config`，provider/default/budget 事实没有第二 owner。
- `R02-S1-CV-F04`：**closed**。Controller 指定的无关 grouped assertions 已删除或收窄，新增 callables 使用精确 typed signature；相对 `70ffc917` 的 added-line `lambda`、`**kwargs`、`type: ignore`、`hasattr/getattr` 扫描均为空。新增 coverage nodes 直接覆盖 HTTP、Browser、Diagnostic child owner 传播与保留的安全边界。

`web_diagnostics.project_error_message` 的小额 cap 修正属于 F01 的必要 owner-level closure：parser 接受任意正整数，因此 projection 不能在 cap 小于固定 suffix 长度时反而抛错。当前实现仅在容得下 suffix 时附加 suffix；schema v2、revision 2、redaction、safe URL、payload shape 与 challenge evidence 均未改变。

### 6.2 Controller independent evidence

- 完整允许测试集：`247 passed, 1 skipped`。
- fresh coverage：九个 changed production files 分别为 provider `93%`、diagnostics `93%`、egress `86%`、fetch orchestrator `82%`、HTTP session `87%`、Playwright backend `80%`、resource budget `100%`、search providers `87%`、Web tools `80%`；总计 `84%`。
- 完整 pyright：`0 errors, 0 warnings, 0 informations`。
- `git diff --check`：通过。
- 精确旧类型 `WebResourceBudget`、旧 flat diagnostic 字段、production 第二 `WebToolsConfig` 构造点、added-line loose callable 与 deferred/no-code scope 扫描：均无非法命中。
- S1 retained boundary：`_send_authorized_request` 仍没有 transport policy；sender 仍 `trust_env=False` / `proxies={}`，search providers 仍是两处 `requests.post` 与一处 `requests.get`，browser/private coupling 仍在两个既有入口；utility-local `1_024` / `--max-network default=80` 与 storage lifecycle 留待 S3。
- `web_challenge_detection.py`、根 README、分层 README 与 deferred Issue owner 路径无 diff。

### 6.3 Final verdict and handoff

**PASS — ENTER DUAL CODE REVIEW.** `R02-S1-CV-F01..F04` 已全部关闭；当前 corrected implementation 可以进入 AgentMiMo / AgentDS 双路完整 code review。Review 必须继续 adversarial 检查大幅测试 diff 是否只锁定 owner contract、small diagnostic cap 的边界、S1 utility 临时投影，以及 S2/S3/deferred/no-code 范围未泄漏。R02-S1 尚未 accepted、未 commit，也不授权进入 R02-S2。
