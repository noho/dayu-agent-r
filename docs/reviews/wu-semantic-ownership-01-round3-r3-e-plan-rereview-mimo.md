# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Plan Re-Review — AgentMiMo

## Review Metadata

- **Reviewer**: AgentMiMo
- **Review type**: plan re-review（只验证 accepted fixes 是否关闭，不修改代码/文档）
- **Timestamp**: `20260713-121620`
- **Plan artifact**: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`
- **Fix artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-fix-codex.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-controller-adjudication.md`
- **Original reviews**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-mimo.md`、`docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-ds.md`

## Scope

Re-review 只验证 controller accepted 的 `R3-E-PF-01` 至 `R3-E-PF-08` 是否在更新后的 plan 中正确关闭。不引入新 attack surface；只在 fix 验证过程中若发现 evidence-backed 新缺陷时报告。

## Fix Verification

### R3-E-PF-01 — design/source references ✓ 修复

- **原始 finding**: MiMo-01。§3 引用 `docs/host/design.md:68-81`、`:86`、`:108` 三处行号全部错误。
- **验证方法**: 检查 plan §3（lines 53-59）的引用是否改为实际存在的稳定章节名或模块 docstring。
- **证据**:
  - Line 55: 引用 `docs/engine/design.md` 的 "边界与职责"、"ToolDefinition 与 ToolCallable" 和 "ToolExecutionOutcome" 章节 — 使用章节名而非行号。
  - Line 56: 引用 `dayu/tools/__init__.py` 模块 docstring — 与原始 review 建议一致。
  - Line 56: 引用 `dayu/documents/__init__.py` 模块 docstring — 正确。
  - Line 57: 引用 `dayu/runtime/__init__.py` 模块 docstring — 正确。
  - Line 58: 引用 `dayu/tools/doc_tools.py` 的 `_ProcessBackedDocToolCallable` / `_build_doc_process_target` — 直接代码真源。
- **结论**: 所有错误行号引用已删除，替换为稳定章节名和模块 docstring。修复关闭。

### R3-E-PF-02 — concrete requests/urllib3 peer proof + retry test ✓ 修复

- **原始 finding**: MiMo-02 + DS-02。S1 peer proof 无具体实现策略；urllib3 Retry 与 pinned address 交互未测试。
- **验证方法**: 检查 §6.1 是否提供具体 urllib3 扩展点策略，§7 S1 测试矩阵是否覆盖 retry。
- **证据**:
  - §6.1 (lines 113-117): 明确 "自定义 `HTTPConnection` / `HTTPSConnection` 只 override `_new_conn()`"、"从 `approved_addresses` 中按确定顺序选择 numeric IPv4/IPv6，使用 urllib3 的 socket timeout/options 建立直连 socket"、"`getaddrinfo` 如被调用也只允许接收 numeric literal"、"`getpeername()` 规范化 IPv4/IPv6 并验证 peer 仍属于该 target 的 `approved_addresses`"。
  - §6.1: "pool 的 `host` 仍是 `AuthorizedHttpTarget.hostname`...保证 HTTP `Host` header、`HTTPSConnection.server_hostname` / TLS SNI 与 certificate `assert_hostname` 都使用原始 IDNA hostname"。
  - §6.1: "现有 urllib3 `Retry(connect=3, read=3, status_forcelist=...)` 可保留，但 connect retry 只能在该 pool 内重建 socket，不得重新 resolve/authorize"。
  - §7 S1 (line 260): 新增 `test_egress_pinned_retry_uses_same_approved_addresses`：第一个 socket 模拟 timeout/RST，后续 retry 成功；断言每次 `_new_conn()` 都收到同一 immutable approved set，实际 connect 从未离开该 set，原 hostname 没有第二次 resolve，且 retry 中的 SNI/cert host 仍为原 hostname。
  - §7 S1 (line 260): 另测所有 approved address 都失败的路径，断言 retry 耗尽后 typed failure 且无 fallback DNS。
- **结论**: urllib3 `_new_conn()` 覆盖策略具体且冻结在 2.6.3 扩展点；Retry 交互有明确测试覆盖。修复关闭。

### R3-E-PF-03 — 4-slice blast-radius split ✓ 修复

- **原始 finding**: DS-01。S2 合并 5 个不同 failure blast radius 的 owner concern。
- **验证方法**: 检查 slice 结构是否拆分，§8 是否给出 blast-radius 理由。
- **证据**:
  - §7 (lines 230-481): S1=Web egress/response ownership, S2=Web resource budget + challenge/search outcome, S3=diagnostic projection + storage-state lifecycle + smoke oracle, S4=Documents bounded source。
  - §8 (lines 486-492): "S1 先建立 Web egress、pinned transport、retry 与 response lifetime"、"S2 闭合 Web 内存/资源 cap 与 challenge/search provider outcome，blast radius 是 child OOM/稳定性和 LLM-facing Web 业务结果"、"S3 闭合 diagnostic schema/storage-state producer 与它的直接 smoke consumer，blast radius 是 secret/login-state 持久化和 CI 假 PASS"、"S4 是独立 Documents source/tool budget owner"。
  - §8: "第 4 个 slice 不是因为文件数或 reviewer ownership，而是 controller 已用直接失败证据裁决"。
- **结论**: 原 S2 拆为 S2+S3，OOM/provider outcome 与 secret/CI oracle 的 blast radius 隔离明确。4 slices 有直接证据支持。修复关闭。

### R3-E-PF-04 — Playwright bounded TreeWalker preflight ✓ 修复

- **原始 finding**: MiMo-03 + DS-03。Playwright DOM/text preflight API 未定义，可能使用非轻量操作。
- **验证方法**: 检查 §6.2 是否定义具体 JS 原语和计数公式。
- **证据**:
  - §6.2 (lines 129-131): "预检只允许一次 `page.evaluate(_BUDGETED_DOM_METRICS_SCRIPT, limits)`"、"script 使用 `document.createTreeWalker()` 遍历 element/text/comment node"、"只累加 tag/attribute name/value 的保守序列化上界与各 text node `nodeValue.length`"、"达到对应 `limit + 1` 立即停止，只返回有界 counters/booleans"。
  - §6.2: "预检 script 不得拼接 HTML/text，不得读取 `outerHTML`、`innerHTML`、`textContent` 或 `innerText`，也不得调用 `page.content()`"。
  - §6.2: 冻结计数公式 — element `2 * localName.length + 5`、attribute `name.length + 6 * value.length + 4`、text node DOM `5 * nodeValue.length`、text node text `nodeValue.length`、comment `nodeValue.length + 7`。
  - §7 S2 (line 317): "DOM/text fake 必须 spy `page.evaluate` 的 script/arguments；断言只调用 bounded TreeWalker script，断言 script 不含 forbidden API，并断言预检超限时 `page.content()` 与 full text extraction 均零调用"。
- **结论**: `document.createTreeWalker()` 是增量的，可在超限时早停；计数公式冻结；forbidden API 明确；spy 测试覆盖。修复关闭。

### R3-E-PF-05 — storage-state + BoundedSource SIGKILL cleanup residuals ✓ 修复

- **原始 finding**: MiMo-04 + DS-04。Storage state 异常退出清理未覆盖 SIGKILL；BoundedSource temp file SIGKILL 残留未分类。
- **验证方法**: 检查 §6.3 和 §6.5 是否正确处理 SIGKILL 为 residual。
- **证据**:
  - §6.3 (lines 140-142): "写入流程必须在目标同目录创建本 run 专用 `0600` temp，序列化后 flush + `fsync`，用 `os.replace()` 原子替换 final"。
  - §6.3: "每次 diagnostic 启动时，artifact lifecycle owner 先扫描显式目标目录中本 owner 命名的 orphan temp 和过期 final"。
  - §6.3: "`SIGKILL` / 主机崩溃时 Python cleanup 不保证；可能留下有界 temp 或尚未过期的 final。此 residual 的当前 owner 是 `utils/diagnose_web_access.py` storage-state lifecycle，当前 destination 是 S3 的原子写 + startup cleanup + TTL contract"。
  - §6.5 (line 159): "`SIGKILL` / 主机崩溃时 `BoundedSourceSnapshot` 的 context cleanup 不保证；最多可残留 `max_source_bytes` 内的系统 temp。当前 owner 是 `dayu.documents.processors.bounded_source`"。
  - §7 S3 (line 377): "不编写伪造 SIGKILL cleanup 保证的测试；用预置 orphan 证明 startup reconciliation"。
- **结论**: SIGKILL 正确分类为 residual 而非已保证的 cleanup；atomic write + startup cleanup 机制具体；owner/destination 明确。修复关闭。

### R3-E-PF-06 — parent-owned smoke fixture ledger ✓ 修复

- **原始 finding**: MiMo-05。Smoke oracle fixture 设计未规格化。
- **验证方法**: 检查 §7 S3 是否定义 ledger lifecycle、sentinel 生成、expected digest 来源和 negative controls。
- **证据**:
  - §7 S3 (lines 370-372): "parent-owned fixture ledger 由 `smoke_web_ci.py` 父进程在启动 diagnostic child 前创建，与本地 `ThreadingHTTPServer` 共生；handler 只追加到父进程内存 typed ledger，child/artifact producer 不能写入"。
  - §7 S3: "父进程用 `secrets.token_hex(32)` 生成 256-bit run/case sentinel"。
  - §7 S3: "父进程在 child 启动前从本次 fixture server 实际注册的 exact response bytes 计算 expected `sha256` 与 length，不从 diagnostic artifact、tool output 或 child stdout 反推"。
  - §7 S3 (lines 379): Required negative controls 列出 8 种扰动：artifact `ok=true` 但无 ledger request、缺失/错误/上一 run sentinel、错误 expected digest/length、challenge endpoint、Playwright 未执行/wrong backend、negative-control endpoint 意外成功、forged schema/artifact。
- **结论**: Ledger lifecycle、sentinel 生成、expected digest 来源和 negative controls 全部具体化。修复关闭。

### R3-E-PF-07 — DuckDuckGo shape/no-results/malformed/challenge criteria ✓ 修复

- **原始 finding**: MiMo-06 + DS open question。DuckDuckGo "已知 result shape" 判定标准未定义。
- **验证方法**: 检查 §6.4 是否定义 known result shape、explicit empty、malformed threshold 和 challenge/login criteria。
- **证据**:
  - §6.4 (lines 149-150): "已知 result shape 冻结为：顶层 `div.result`，每项必须有 `a.result__a`、非空规整 title，且 `href` 必须能解析为非空 `http` / `https` 目标；`a.result__snippet` / `div.result__snippet` 可选"。
  - §6.4 (line 151): "explicit no-results 只在...唯一 `.no-results` 元素，其规整文本精确命中封闭 allowlist `No results.` / `No more results.`"。
  - §6.4 (lines 150-151): "malformed item 定义为缺 anchor、title 为空、href 非字符串/为空或解析后不是 HTTP(S)"。"有效项为 0，或 `malformed_count * 2 > container_count`（严格超过 50%），整个 response 为 shape drift"。
  - §6.4 (line 152): "challenge/login shape 任一成立都覆盖 result/no-results"。
- **结论**: Known result shape、explicit empty、malformed threshold (>50%) 和 challenge/login criteria 全部具体化。修复关闭。

### R3-E-PF-08 — WebResourceBudget provider JSON path/example ✓ 修复

- **原始 finding**: MiMo-07。WebResourceBudget provider config override 键名未定义。
- **验证方法**: 检查 §6.6 是否定义 JSON path 和完整示例。
- **证据**:
  - §6.6 (lines 182-202): "packaged/effective provider JSON 的唯一路径固定为 `providers["web-tools"].config.resource_budget`"。
  - §6.6: 包含完整 7 字段 JSON 对象示例（wire_body_bytes, decoded_body_bytes, warmup_body_bytes, browser_dom_chars, browser_text_chars, diagnostic_error_chars, diagnostic_events）。
  - §6.6: "object 缺字段、未知字段、bool/零/负数均 fail fast，不做 partial fallback；只有整个 `resource_budget` 缺失时才使用上表的完整默认对象"。
  - §10 (line 521): README trigger 明确 "S2 新增可配置 `resource_budget` 后，触发 `dayu/config/README.md` 更新"。
- **结论**: JSON path、完整示例和 fail-fast 规则全部具体化。修复关闭。

## New Findings

在验证 8 个 accepted fixes 的过程中，未发现 evidence-backed 新缺陷。更新后的 plan 在以下方面表现一致：

- §6.1 urllib3 `_new_conn()` 覆盖策略具体，版本冻结在 2.33.1/2.6.3，stop condition 明确。
- §6.2 DOM preflight 使用增量 `createTreeWalker()`，计数公式冻结，forbidden API 列表完整。
- §6.3 storage-state lifecycle 覆盖 atomic write、startup cleanup、SIGKILL residual，owner/destination 明确。
- §6.4 DuckDuckGo 判定标准具体可测试。
- §6.5 Documents bounded source 使用系统 temp，SIGKILL residual 正确分类。
- §6.6 冻结 contract 包含完整字段定义、JSON 示例和 fail-fast 规则。
- 4 slices 的 blast-radius 隔离理由充分，依赖方向正确（S1→S2→S3，S4 独立）。
- §11 deferred items 分类合理，owner/destination 明确。

**新 findings 计数：0**

## Open Questions

无。

## Residual Risks

计划已正确识别并分类以下 residual risks，re-review 确认其 owner/destination 合理：

| Risk | Plan classification | Re-reviewer assessment |
|---|---|---|
| urllib3 版本升级破坏 `_new_conn()` 扩展点 | S1 residual + stop condition | 正确；S1 completion artifact 记录 tested versions |
| 公网 Playwright direct fail closed 降低可用性 | S1 residual | 正确；明确产品降级 |
| Chromium 内部 DOM 峰值 / TreeWalker CPU | S2 residual | 正确；process timeout/kill 已覆盖 |
| DOM 预检与投影之间的动态变更 | S2 residual | 正确；二次实际长度检查已覆盖 |
| digest 对低熵 secret 的字典猜测风险 | S3 residual | 正确；plan 已排除已识别 secret |
| SIGKILL 后 storage-state temp/final 残留 | S3 residual | 正确；atomic write + startup cleanup + TTL |
| SIGKILL 后 BoundedSourceSnapshot temp 残留 | S4 residual | 正确；系统 TMPDIR lifecycle |
| DuckDuckGo 外部 HTML shape 变更 | S2 residual | 正确；strict fail closed |
| Doc tool file-authority/symlink 竞态 | S4 residual | 正确；归后续 WU |
| 外部 live URL 不稳定 | S3 residual | 正确；diagnostic-only |

## Plan Re-Review Conclusion

**pass**

R3-E plan 的 8 个 accepted fixes 全部正确关闭。更新后的 plan 具备 implementation-ready 状态：

- 10 个 accepted source findings 的 owner、证据和修复路径一致。
- urllib3 `_new_conn()` 覆盖策略具体且版本冻结，stop condition 保护不可行场景。
- Playwright DOM preflight 使用增量 TreeWalker 而非完整序列化，计数公式冻结。
- SIGKILL cleanup 正确分类为 residual 而非已保证行为。
- DuckDuckGo 判定标准具体可测试，strict fail closed。
- WebResourceBudget provider config 路径和示例明确。
- 4 slices 按 blast radius 隔离，依赖方向正确。
- 无新 evidence-backed 缺陷。

**Verdict**: pass | Findings: 0 new | Fixed: 8/8 | Remaining: 0 | Blocking questions: 0

## Completion Report

- **Verdict**: pass
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-rereview-mimo.md`
- **Fixed IDs**: `R3-E-PF-01`, `R3-E-PF-02`, `R3-E-PF-03`, `R3-E-PF-04`, `R3-E-PF-05`, `R3-E-PF-06`, `R3-E-PF-07`, `R3-E-PF-08`（8/8）
- **Remaining IDs**: 0
- **New findings count**: 0
- **Blocking questions**: 0
- **Implementation slices**: 4（S1 Web egress/response, S2 Web resource/challenge/search, S3 Web diagnostic/storage-state/smoke, S4 Documents bounded source）
