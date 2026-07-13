# R3-E Aggregate Deepreview（AgentDS）

## Scope

- Mode: committed R3-E slice set aggregate review
- Work unit: `WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E`
- Accepted plan commit: `cd5e8595`
- Accepted slice commits:
  - S1 `a20efac7` — Web egress ownership & response lease
  - S2 `728e73af` — Web resource budget & challenge/search outcomes
  - S3 `94a12c9e` — Web diagnostic projection, storage-state lifecycle, smoke oracle
  - S4 `7e4749e5` — Documents bounded source & read/list/search pre-budget
- Control truth:
  - Design: `docs/host/design.md`, `docs/engine/design.md`
  - Plan: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`
  - Control doc R3-E row: `docs/host/issues-implementation-control.md:209`
  - Aggregate validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-aggregate-validation.md`
- Included scope: 58 files (production, test, README, docs/reviews artifacts)
- Excluded scope: R3-A/R3-B/R3-C/R3-D/R3-F, tool-security implementation, Fins, Host/Engine lifecycle changes

## Findings

**未发现实质性问题。**

R3-E S1–S4 四个已接受 slice 作为整体形成一致的 semantic owner 闭环。10 个 accepted plan findings 全部正确实现，4 个 slice 之间无 semantic drift、无下游补偿、无跨边界泄漏。未实现 plan 明确排除或 deferred 的项目。

## Aggregate Owner Closure Verification

### Slice Boundary 与 Cross-Slice Integration

| 集成点 | Producer (slice) | Consumer (slice) | 验证 |
|--------|------------------|------------------|------|
| Web egress policy | S1 `web_egress_policy.py` | S2 `web_fetch_orchestrator.py`, S3 `diagnose_web_access.py`, S3 `web_playwright_backend.py` | 单一 `WebEgressPolicy` 实例；diagnostic 不再自建 literal-host predicate（已删除 `_validate_url_safety`） |
| Web resource budget | S2 `web_resource_budget.py` | S2 `web_fetch_orchestrator.py`, S2 `web_playwright_backend.py`, S3 `diagnose_web_access.py` | 共享 `WebResourceBudget` typed value；diagnostic 使用 `_DIAGNOSTIC_RESOURCE_BUDGET` 冻结实例 |
| Challenge decision | S2 `web_challenge_detection.py` | S2 `web_fetch_orchestrator.py`, S3 `smoke_web_ci.py` | outcome 为封闭 `BotChallengeDecision` 枚举；S3 smoke classifier 正确读取 `challenge_decision` 字段 |
| Web diagnostic projection | S3 `web_diagnostics.py` | S3 `web_tools.py`, S3 `web_fetch_orchestrator.py`, S3 `web_playwright_backend.py`, S3 `diagnose_web_access.py`, S3 `smoke_web_ci.py` | 单向消费；producer paths 不再展开 raw content/header value |
| Schema v2 artifact | S3 `diagnose_web_access.py` | S3 `smoke_web_ci.py` | 同步迁移：producer 写 v2/revision 2，consumer 精确校验 v2/revision 2 + 递归拒绝旧 prefix 字段 |
| Bounded source snapshot | S4 `bounded_source.py` | S4 `doc_tools.py` → `_bounded_local_source` → 所有 read/list/search producer | 层中立；只依赖 `Source` protocol，不 import tools/Host/Engine |

### Plan Finding Closure Matrix

| Plan Finding | Severity | Slice | 实现位置 | 验证 |
|-------------|----------|-------|---------|------|
| DR-004: egress connect-time peer proof | production-high | S1 | `web_egress_policy.py` + `web_http_session.py` target-bound transport + `_new_conn()` override + `getpeername()` peer proof | AuthorizedHttpTarget 6 处引用；混合 A/AAAA fail closed；retry 同一 approved set |
| DR-015: wire/decoded/warmup/DOM cap before materialization | production-high | S2 | `WebResourceBudget` + `_materialize_response_body()` streaming budget + `_BUDGETED_DOM_METRICS_SCRIPT` TreeWalker | gzip.decompress 整包路径已删除；stream=True warmup；browser 预检不读 page.content() |
| DR-016: diagnostic no raw text prefix | production-high | S3 | `WebDiagnosticProjection` + `_FetchContentRuntimeContext` 只持 length/digest | `response_excerpt`/`_extract_response_snippet`/`_build_text_excerpt` 已删除；旧字段 scan 零命中 |
| DR-019: read/list/search input cap before materialization | production-high | S4 | `BoundedSourceSnapshot` + incremental decoder + bounded heap | `readlines()`/`read()` 整文件 API 已替换；bounded heap 替代全 tree list |
| DR-032: PASS must be independent oracle | production-high | S3 | parent-owned `FixtureLedger` + freeze-before-classify + expected exact bytes + negative controls | artifact `ok` 不是 PASS 充分条件；synthetic ok+no-ledger → failure |
| DR-033: diagnostic raw path reuse production owners | production-high | S1+S3 | diagnostic 共享 `WebEgressPolicy` + `WebDiagnosticProjection` | `_validate_url_safety` 已删除；storage-state atomic lifecycle |
| DS: redirect response leak | production-high | S1 | response lease context manager + `finally` close | 每 hop response close 在 transfer/拒绝/cancel 路径恰一次 |
| DS: challenge false positives | production-high | S2 | `BotChallengeDecision` 三态 + evidence classes | 宽泛文本单信号 `suspected`，组合信号 `confirmed`；fallback 不再 status-gated |
| DS: challenge/status mismatch | production-high | S2 | `challenge_fallback_action(decision, browser_availability)` | caller 不再重复 status 集合 gate；confirmed+500 → 同一 fallback |
| DS: DuckDuckGo shape drift | production-high | S2 | DuckDuckGo HTML parser + `WebSearchProviderResponseError(reason=response_shape_changed)` | explicit no-results 需精确命中 allowlist；malformed threshold >50% → shape drift |

10/10 accepted plan findings closed。无 rejected/deferred/needs-more-evidence 残留。

### Cross-Slice Semantic Drift Check

1. **Web egress → diagnostic 不变**: S1 egress contract（`WebEgressPolicy.authorize_http_target` → `AuthorizedHttpTarget`）在 S3 diagnostic 中通过同一 policy instance 消费。`diagnose_web_access.py` imports `WebEgressPolicy, WebEgressPolicyError` (line 54-55)，不再有自建 URL safety 决策。

2. **Resource budget → diagnostic 不变**: S2 `WebResourceBudget` 在 S3 diagnostic 中通过 `_DIAGNOSTIC_RESOURCE_BUDGET` 冻结实例消费。Playwright body 读取复用 `decoded_body_bytes` budget。

3. **Challenge outcome → smoke 不变**: S2 `BotChallengeDecision` (NONE/SUSPECTED/CONFIRMED) 的正确消费者包括 S3 `_FetchContentRuntimeContext.challenge_decision`、S3 diagnostic artifact `challenge_decision` 字段、S3 smoke classifier `_classify_loaded_artifact` 的 challenge-control guard。

4. **Diagnostic schema v2 → smoke consumer 不变**: `web_diagnostics.py` 常量 `WEB_DIAGNOSTIC_SCHEMA_VERSION = "web-diagnostics-v2"` 和 `WEB_DIAGNOSTIC_SCHEMA_REVISION = 2` 被 `diagnose_web_access.py` 和 `smoke_web_ci.py` 精确引用。smoke 通过 `_diagnostic_schema_gap()` 精确校验 version/revision + `_legacy_diagnostic_field()` 递归拒绝旧 prefix。无 v1 fallback。

5. **Bounded Source → Doc tools 不变**: `BoundedSourceSnapshot` 通过 `_bounded_local_source()` (doc_tools.py:1919-1943) 包装 `LocalFileSource`，所有 read/list/search 路径通过 `with snapshot as snapshot:` context manager 消费。processor factory 接收 snapshot（IS-A Source），不再自行构造 `LocalFileSource`。

### No Downstream Compensation

- 无 `getattr`/`hasattr` 在新 S1-S4 生产代码中（scan 确认）。
- 无 loose parsing / `try-except` fallback 从旧 schema 字段恢复语义。
- 无 caller-side `if content_prefix is None: use content_length` 等补偿逻辑。
- 无 `extra payload` 注入 plan 已拒绝的字段。
- 无 `compatibility re-export`、`compatibility wrapper` 或 `compatibility shim`。

### No Unauthorized Boundary Crossings

| 检查项 | 结果 |
|--------|------|
| S4 Documents → `dayu.tools` import | 零命中（import boundary test 已锁定） |
| `dayu.fins` 修改 | 零命中（`git diff` 无 Fins 文件） |
| Host/Engine 修改 | 零命中 |
| `web_egress_policy.py` 在 S2-S4 中不必要修改 | S2-S4 diff 无该文件 |
| tool-security implementation | 零命中（scan 仅命中 artifacts explicit-exclusion 声明与 import-boundary forbidden list） |
| Fins upload allowlist / CN-HK provenance | 零命中 |
| generic capability system / OS sandbox | 零命中 |
| OpenAI invalid-UTF8 (DR-016 Engine part) | 未实现（Engine 未修改，按 plan §4.2 deferred） |
| DR-032 provider/Host memory smoke | 未实现（仅 `smoke_web_ci.py` 修改，按 plan §4.2 scope） |
| Playwright 公网 egress proxy | 未实现（`allow_private_network_url=True` only，按 plan §6.1） |
| Doc file-authority/symlink-race policy | 未实现（S4 保证 opened handle byte cap，按 plan §6.5 residual） |

### Plan Deferred Items Verification

Plan §11 列出的 6 个 deferred 项目全部验证为未实现：

1. Fins upload allowlist / symlink policy → 无 `dayu.fins` 变更
2. repository-wide tool-security framework → 无 `ToolSecurity` 类/模块
3. LLM-facing upload/download security schema → 无对应 schema 字段
4. Playwright 公网 egress proxy / browser sandbox → 无 proxy/sandbox 配置
5. DR-032 provider/Host memory smoke → 仅 `smoke_web_ci.py` 被修改
6. Doc tool file-authority/symlink 竞态 → 无 file-authority/symlink policy 代码

### README Alignment

Plan §10 README trigger 决策与实际变更一致：

| README | Plan 决策 | 实际 | 对齐 |
|--------|----------|------|------|
| 根 `README.md` | 不触发（无最终用户入口变化） | 未修改 | ✅ |
| `dayu/README.md` | 不触发（无分层装配变化） | 未修改 | ✅ |
| `dayu/config/README.md` | S2 触发（新增 `resource_budget` config） | 已更新 §204-213 行，含完整字段、fail-fast 规则和最小示例 | ✅ |
| `tests/README.md` | S3/S4 触发（新测试层级） | 已更新：Web diagnostic schema v2/storage/live smoke 描述 + bounded source/partial scan 说明 | ✅ |
| `dayu/tools/README.md` | 不存在，不机械新建 | 未新建 | ✅ |
| `dayu/documents/README.md` | 不存在，不机械新建 | 未新建 | ✅ |

### Aggregate Validation Pass

| 命令 | 结果 |
|------|------|
| `pytest tests/tools/web tests/documents tests/tools/test_doc_tools_provider.py -q` | 280 passed, 2 skipped, 3 warnings |
| `pyright` | 0 errors, 0 warnings, 0 informations |
| `git diff --check` | PASS |

3 个 warnings 为既有 `edgar` deprecation warnings，与 R3-E 无关。

### Source Scan Summary

- **Old diagnostic fields**: `content_prefix`, `html_prefix`, `stderr_prefix`, `stdout_prefix` 仅出现在 `utils/smoke_web_ci.py` denylist（设计如此）；生产代码零命中。
- **Old URL decisions**: `_is_safe_public_url`, `_validate_url_safety` 在生产代码零命中。
- **Old `gzip.decompress` 无预算**: `web_fetch_orchestrator.py` 零命中。
- **`hasattr`/`getattr`**: S1-S4 新增生产代码零命中。
- **Tool-security / SSRF / TLS / symlink-safe / file-authority**: 生产代码零命中；仅 artifacts 显式 exclusion 声明和 import-boundary forbidden list。
- **S4 Documents → tools import**: `test_import_boundary.py` 已覆盖 `bounded_source.py`，继续锁定。
- **`dayu.runtime` → Host/Engine/Fins import**: 边界保持（`bounded_source.py` 只 import `Source` protocol）。

## Open Questions

无。

## Residual Risk（Aggregate）

下表汇总 R3-E 全部 4 个 slice 的 residual risks，均为 accepted contract limitation 或 assigned authority residual，无 unclassified blocker：

| 分类 | residual | owner / destination |
|------|----------|---------------------|
| accepted contract limitation | SIGKILL/主机崩溃可留下 storage-state temp/final（下次 startup/TTL cleanup） | `utils/diagnose_web_access.py` storage-state lifecycle |
| accepted contract limitation | SIGKILL/主机崩溃可留下至多 `max_source_bytes` 的系统命名 temp | `dayu.documents.processors.bounded_source` |
| accepted confidentiality limitation | 正文 digest 对低熵内容可能被字典猜测 | `dayu.tools.web.web_diagnostics` — digest 仅用于 deterministic fixture 关联 |
| low operational residual | Playwright API 不提供 response body streaming iterator | `utils/diagnose_web_access.py` — Content-Length 早拒绝 + 后验 budget |
| low operational residual | Processor 内部对象放大可能超过 raw byte size | S4 `doc_tools.py` — 本轮确保 processor 构造前 byte cap |
| assigned authority residual | Doc 路径校验到 `open()` 之间 symlink/rename TOCTOU | 后续 file-authority WU — S4 绑定 opened handle byte cap |
| assigned deployment residual | 公网 Playwright direct 默认 fail closed（无法证明 peer） | 后续 browser egress proxy/deployment WU |
| validation tooling residual | pytest-cov dotted source / NumPy double-load 在 S3/S4 触发 | coverage invocation/toolchain — 等价 coverage 流程通过 |
| accepted external boundary | 外部 live URL/search provider 保持 diagnostic-only | `utils/smoke_web_ci.py` external/search classifier |

## Completion Report

- **Aggregate review result**: **PASS** — 零 material finding。
- **10/10 accepted plan findings closed** 跨 S1-S4 形成一致 owner 闭环。
- **58 个已提交文件**（含 21 个 review/validation artifacts）覆盖完整 evidence chain。
- **Cross-slice integration**: 5 个集成点验证无 semantic drift。
- **No downstream compensation**: 零 `getattr`/`hasattr`/loose parsing/compat shim。
- **No unauthorized boundary crossing**: 零 Fins/Host/Engine/tool-security/egress-policy expansion。
- **Plan deferred items**: 6/6 确认未实现。
- **README alignment**: 4/4 README trigger 决策与实际变更一致。
- **Aggregate validation**: 280 passed, pyright 0 errors, git diff --check PASS。
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-aggregate-deepreview-ds.md`
- **Ready for**: R3-E final closeout。
