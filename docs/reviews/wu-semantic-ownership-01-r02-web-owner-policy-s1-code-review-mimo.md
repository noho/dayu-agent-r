# Code Review — WU-SEMANTIC-OWNERSHIP-01 / R02-S1 Web Config & Typed Owner Split

## Scope

- Mode: current changes
- Branch: `phaseflow/host-issues-control`
- Base: `70ffc917`
- Output file: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-code-review-mimo.md`
- Included scope: 9 production files, 2 config/utility files, 3 test files, 2 README files, 1 implementation artifact (17 files total, +2949 / -539 lines)
- Excluded scope: `docs/host/issues-implementation-control.md` (Controller-owned dirty path, read-only), plan/review/controller artifacts (read-only)
- Parallel review coverage: 4 subagents covered (1) core config/budget/provider/egress/session, (2) web_tools/orchestrator, (3) browser/diagnostics/search, (4) tests/utility/READMEs. Main reviewer cross-checked all findings against direct code evidence and performed independent adversarial pass on user-specified focus areas.

## Review Baseline Context

- Accepted plan truth: `2d42ceb6` + `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md` (946 lines)
- Controller validation: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-controller-validation.md` — 4 findings (F01–F04) all closed
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-implementation-codex.md`
- Controller independent evidence: 247 passed, 1 skipped; pyright 0; 9-file coverage 80%–100%; all scans clean
- Controller discussion Topic 2 (Web egress/budget/browser/challenge/diagnostics) and Topic 9 (tool security characterization) fully read

## Findings

### 01-未修复-低-provider 顶层 config 不拒绝未知字段

- **入口/函数**: `provider.py:_parse_config` (line 80)
- **文件(行号)**: `dayu/tools/web/provider.py:80-153`
- **输入场景**: 用户在 `tool_discovery.json` 的 Web provider record 中添加拼写错误的字段，如 `"allow_prvate_network_url": true`
- **实际分支**: parser 跳过未知字段，使用 typed default（`False`），不报错
- **预期行为**: 按 plan §8.2 "unknown/invalid precise fail fast"，顶层 parser 应与嵌套 `resource_budget` parser 一样拒绝未知字段
- **直接证据**: `resource_budget` 子 parser（`web_resource_budget.py:_parse_group` line 210）有 `unknown_fields = set(group_data.keys()) - set(expected_fields)` 精确拒绝；但 `_parse_config` 无等价检查。`grep -n "unknown\|unexpected\|extraneous" provider.py` 零命中。
- **影响**: 拼写错误的 config key 被静默忽略，operator 预期的保护可能未生效。但 config 文件为项目自控，风险有限。
- **建议改法和验证点**: 在 `_parse_config` 入口处增加已知顶层字段集合检查，拒绝未知 key 并报精确路径。验证：添加未知字段时 `_parse_config` 抛出 `ValueError`。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-诊断 utility S1 投影 custom-port 为 private 行为同源

- **入口/函数**: `utils/diagnose_web_access.py:_build_single_diagnostic_payload` (line 2705)
- **文件(行号)**: `utils/diagnose_web_access.py:2705-2708`
- **输入场景**: S1 临时将 `allow_private_network_url` 同时投影给 `allow_private_network` 和 `allow_custom_port`
- **实际分支**: `WebEgressPolicy(allow_private_network=options.allow_private_network_url, allow_custom_port=options.allow_private_network_url)`
- **预期行为**: S1 plan §4.4 与 R02-S1-CV-F02 要求保持既有诊断 utility 行为：private 模式同时允许 custom-port
- **直接证据**: R02-S1-CV-F02 裁决确认此为正确行为。旧实现中 private 和 custom-port 耦合在同一 flag；S1 拆分为独立 bool 后，utility 在 policy construction boundary 将现有开关同时投影给两者，保持旧行为。测试 `test_single_diagnostic_private_mode_preserves_local_custom_port` 用 `http://127.0.0.1:43117/fixture.pdf` 断言 `authorized_ports == [43117]`。
- **影响**: 这不是 bug，是 S1→S3 临时状态的正确实现。S3 将从 typed config 同源读取两个独立值。当前实现没有形成新 owner——投影仅发生在 policy construction boundary，utility 不拥有 custom-port 语义。
- **建议改法和验证点**: 无需修改。S3 时将此投影替换为 typed config 的两个独立字段。验证：S3 删除此行后 diagnostic 仍能读取 packaged config 的 `allow_custom_port_url`。
- **修复风险（低/中/高）**: 低（当前无需修复）
- **严重程度（低/中/高/严重）**: 低

### 03-未低-低-web_diagnostics 小 cap 行为正确但边界需知悉

- **入口/函数**: `web_diagnostics.py:project_error_message` (line 435)
- **文件(行号)**: `dayu/tools/web/web_diagnostics.py:435-444`
- **输入场景**: `error_chars` 极小值（1–13）
- **实际分支**: `max_chars <= 13` → suffix 设为空字符串 → `truncate_diagnostic_text` 执行硬截断 `message[:max_chars]`
- **预期行为**: parser 接受任意正整数，projection 不能在 cap 小于 suffix 长度时抛 `ValueError`
- **直接证据**: `_ERROR_TRUNCATION_SUFFIX = "...<truncated>"`（长度 13）。条件 `max_chars > len(_ERROR_TRUNCATION_SUFFIX)` 确保 cap ≤ 13 时 suffix 为空。下游 `truncate_diagnostic_text` 检查 `len(truncated_suffix) >= max_chars`，空 suffix（长度 0）对任意正 max_chars 均通过。
- **影响**: 行为正确。`error_chars=1` 时只返回第一个字符，无 suffix。这是 F01 的必要 owner-level closure。
- **建议改法和验证点**: 无需修改。建议在 test 中增加 `error_chars=1` 和 `error_chars=13` 的边界断言，明确锁定此行为。
- **修复风险（低/中/高）**: 低（当前无需修复）
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无。

## Adversarial Check Results

### 1. 巨幅 test diff 是否真正锁定 S1 owner contract

**结论：是。**

- CV-F04 指出的四个无关 grouped helper tests 已删除：`grep` 零命中。
- S1 新增 tests 直接覆盖 owner contracts：
  - F01 test（line 228）：`error_chars=5` 控制普通 fetch failure 长度
  - F02 test（line 609）：diagnostic utility private/local custom-port 行为保持
  - F03 test（line 2053）：`WebToolsConfig` 全字段 `MISSING`，`WebResourceBudgets` 无 `__post_init__`
  - 旧类型 `WebResourceBudget` 零残留（`grep` 覆盖 `dayu/ tests/ utils/`）
- 新增 callables 均为窄 typed helper（如 `preserve_materialized_response_body`、`_private_loopback_resolver`、`_picklable_worker_predicate`、`_process_session_noop`），不是 loose lambda。
- 但 pre-existing tests 仍有大量 lambda（line 3213–3215 等），这是既有债务，非 S1 回归。

### 2. web_diagnostics 极小正整数 cap/suffix 行为

**结论：正确。** 见 Finding 03。

### 3. diagnostic utility S1 临时 private→custom-port 投影

**结论：正确且未形成新 owner。** 见 Finding 02。投影仅在 policy construction boundary，utility 不拥有 custom-port 语义。

### 4. 五 bool/三 child budgets 的 parser/default/propagation

**结论：正确。**
- 五 bool 独立解析，bool-as-int/string/null 均 fail fast
- 三 child budgets 各自 `__post_init__` 拒绝非正整数
- `WebResourceBudgets` 无 default、无 validator、无 flattened property
- packaged JSON 冻结值与 typed constants 完全一致
- `WebToolsConfig` 无业务 default，唯一构造点在 `provider._parse_config`
- 传播链：`tool_discovery.json → _parse_config → WebToolsConfig → exact child consumer`，下游不重读 raw config

### 5. 所有 ordinary/browser failure 是否使用当前 Diagnostic owner

**结论：是。** `_raise_fetch_failure` 签名 `diagnostic_error_chars: int` 无 default；15 个 call sites 全部显式传入 `resource_budgets.diagnostics.error_chars` 或 `diagnostic_resource_budget.error_chars`。全局 `_DEFAULT_WEB_DIAGNOSTIC_ERROR_CHARS` 与 `DEFAULT_DIAGNOSTIC_RESOURCE_BUDGET` 生产 import 已删除。

### 6. custom-port 与 private 是否独立

**结论：是。** `WebEgressPolicy.__init__` 的 `allow_private_network` 和 `allow_custom_port` 是独立参数，`authorize_http_target` 分别在 line 331 和 line 333 独立检查。

### 7. 是否越入 S2/S3/Issue 178/R03/统一 authorization

**结论：否。**
- `_send_authorized_request` 无 `transport_policy` 参数，sender 仍 `trust_env=False` / `proxies={}`
- `web_search_providers.py` 仍为三处模块级 raw `requests.get/post`
- browser/private coupling 仍在两个既有入口（`allows_private_network` pre-return）
- utility `_DEFAULT_DIAGNOSTIC_ERROR_CHARS=1_024` 与 `--max-network default=80` 保持
- storage lifecycle 符号/CLI/writer 保持
- `authorization framework|policy DSL|capability token|storage state refresh|Issue #178|R03` 扫描零命中
- `web_challenge_detection.py`、根 README、分层 README 零 diff

### 8. README 是否准确表达 snapshot-only 时序

**结论：是。** config README 准确描述："当前 S1 只把 `dns_peer_proof_enabled`、`allow_environment_proxy` 与 `browser_enabled` 保存为不可变 typed snapshot；HTTP sender 仍保持既有 numeric pin / no-proxy 行为，browser backend 也保持既有 private-policy coupling。" 无 Issue #178 lifecycle 承诺。

### 9. 安全机制是否误删

**结论：否。** 以下安全机制全部保留并有 test 覆盖：
- redirect 逐 hop authorization
- dangerous/unspecified/multicast 始终拒绝
- mixed DNS fail closed
- peer proof numeric pin/mismatch fail closed
- proxy 禁用时 `trust_env=false`
- header/cookie/URL credential redaction
- diagnostic containment/symlink 防御
- challenge detection/evidence
- response body size limits

## Residual Risk

- `web_tools.py` 与 `web_playwright_backend.py` coverage 均为门槛值 80%；owner/security paths 已有直接 tests，但后续 slice 修改仍须重新逐文件验证。
- Pre-existing test lambda 债务（非 S1 回归，可独立跟踪）。
- provider 顶层 config 未知字段不拒绝（非 blocking，config 为项目自控）。
- S2 将引入 transport policy 到 sender、proxy/proof 分支、browser/private 解耦——这些是后续 slice 的增量风险，不在 S1 scope。
- S3 将删除 utility-local `1_024/default=80` 和 credential lifecycle——这些是后续 slice 的增量风险，不在 S1 scope。

## Verdict

**PASS-WITH-RISKS**

S1 implementation 正确完成了 config owner 与 typed policy split。所有 4 个 Controller validation findings (F01–F04) 已关闭。旧 `WebResourceBudget` 零残留。五 bool 独立解析、三 child budgets typed owner 分离、`_raise_fetch_failure` 消费当前 Diagnostic owner、search result visibility 使用同一 typed egress policy、diagnostic utility S1 临时投影正确保留行为、browser/private coupling 未被提前删除、安全机制全部保留。

**Risks：**
- provider 顶层 config 未知字段不拒绝（低风险，建议后续修复）
- 两个文件 coverage 在门槛值 80%（需后续 slice 重新验证）
- S2/S3 的 transport/browser/lifecycle 变更将引入增量风险，需独立 review

当前 implementation 可以进入 controller accepted-slice commit 流程。
