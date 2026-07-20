# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Plan Re-Review — AgentDS

## Review metadata

- **Reviewer**: AgentDS
- **Review type**: plan re-review（只 re-review plan fixes，不修改代码/文档）
- **Updated plan**: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`
- **Fix artifact**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-fix-codex.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-controller-adjudication.md`
- **Original reviews**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-mimo.md` (MiMo, 6 findings, pass-with-risks)、`docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-ds.md` (DS, 4 findings, pass-with-risks)
- **Timestamp**: 20260713-122013

## Re-review scope

本 re-review 只验证 controller accepted 的 8 个 plan fix (R3-E-PF-01 至 R3-E-PF-08) 是否在 updated plan 中正确闭合，并识别 updated plan 中是否引入新的 plan defect。不重新审查已在 original review 中报告且未被 controller accepted 的内容，不修改代码/文档，不 stage/commit/push。

## Fix closure verification

### R3-E-PF-01 — design/source references ✓ CLOSED

- **Original**: MiMo-01 — §3 三处 `docs/host/design.md` 行号引用 (68-81, 86, 108) 指向错误内容。
- **Controller requirement**: Fix incorrect design/source references.
- **Fix claim**: 删除错误行号，改为引用 `docs/engine/design.md` 稳定章节名、模块 docstring 和实际 process-backed 代码 owner。
- **Plan evidence (verified)**:
  - §3 line 55: `docs/engine/design.md` 的 "边界与职责"、"ToolDefinition 与 ToolCallable"、"ToolExecutionOutcome" — 章节名引用，非行号 ✓
  - §3 line 56: `dayu/tools/__init__.py` 模块 docstring ✓
  - §3 line 57: `dayu/runtime/__init__.py` 模块 docstring ✓
  - §3 line 58: `dayu/tools/doc_tools.py` 中 `_ProcessBackedDocToolCallable` / `_build_doc_process_target` — 代码级引用 ✓
  - §3 中不再出现 `docs/host/design.md:68-81`、`:86`、`:108` 等错误行号 ✓
- **Verdict**: 闭合。所有引用均可追溯到实际代码或设计文档章节，无虚构行号。

### R3-E-PF-02 — concrete requests/urllib3 peer proof + retry test ✓ CLOSED

- **Original**: MiMo-02 + DS-02 — S1 peer-proof 无具体实现策略；retry 路径未进入测试矩阵。
- **Controller requirement**: Add concrete S1 peer-proof strategy including how approved addresses reach transport, TLS SNI/cert hostname, connect retry behavior, and retry validation test.
- **Fix claim**: 确认 requests==2.33.1/urllib3==2.6.3；冻结 per-hop target-bound adapter/pool/connection；`_new_conn()` override + `getpeername()` 验证；pool host 保留原 IDNA hostname；retry 在同一 immutable approved set 内；新增 retry 测试。
- **Plan evidence (verified)**:
  - §6.1 lines 113-114: 自定义 `HTTPConnection`/`HTTPSConnection` 只 override `_new_conn()`，从 `approved_addresses` 选 numeric IP，`getpeername()` 验证 peer，peer mismatch → close + typed failure ✓
  - §6.1 line 114: "urllib3 只在 `_new_conn()` 成功后才进入 TLS handshake / HTTP request，因此 peer proof 先于 HTTP request bytes" — 时序保证明确 ✓
  - §6.1 line 115: pool `host` 为 `AuthorizedHttpTarget.hostname`，"HTTP `Host` header、`HTTPSConnection.server_hostname` / TLS SNI 与 certificate `assert_hostname` 都使用原始 IDNA hostname" — TLS identity 保证 ✓
  - §6.1 line 116: "connect retry 只能在该 pool 内重建 socket，不得重新 resolve/authorize，也不得切换到 approved set 之外" — retry 安全约束 ✓
  - §6.1 line 116: "redirect 则不属于同一 target retry；每个 Location 必须重新产生新 target 和新 target-bound pool" — retry vs redirect 语义区分 ✓
  - §7 S1 Tests line 260: `test_egress_pinned_retry_uses_same_approved_addresses` — 首次 socket timeout/RST → retry 成功；断言 immutable approved set、无二次 resolve、SNI/cert host 不变；另测全地址失败路径 ✓
- **Verdict**: 闭合。实现了 connect-before-request peer proof 的完整技术路径（含 `_new_conn()` → `getpeername()` 时序链），TLS SNI/cert hostname 由 pool host 原样保留保证，retry 与 redirect 的安全语义明确区分，retry 测试规格化。

### R3-E-PF-03 — 4-slice blast-radius split ✓ CLOSED

- **Original**: DS-01 — S2 合并 5 个不同 failure blast radius (OOM/provider outcome/secret persistence/CI oracle/Documents temp)。
- **Controller requirement**: Split S2 or make blast-radius explicit. Controller prefers 4 slices.
- **Fix claim**: 采用 controller 首选，S2→Web 资源+challenge/search，S3→diagnostic+storage-state+smoke oracle，S4→Documents；显式记录 4 slices 原因。
- **Plan evidence (verified)**:
  - §7: 4 个 slice — S1 (egress/response ownership)、S2 (resource budget + challenge/search)、S3 (diagnostic projection + storage-state lifecycle + smoke oracle)、S4 (Documents bounded input) ✓
  - §7 S2 line 293-294: blast radius = "Web child 进程内存/稳定性与 Web 搜索/抓取业务 outcome" ✓
  - §7 S3 line 357: blast radius = "secret/login-state 持久化与 CI 假 PASS" ✓
  - §7 S4 line 490: blast radius = "Documents child 资源与系统 temp lifecycle" ✓
  - §8 lines 485-492: 显式记录超过 1-3 slice 上限的原因 — 三组 blast radius 独立，合并会导致 "一类 review failure 拖住其他已正确的 owner 闭环" ✓
  - §8 line 492: "四个 slices 均修改生产或发布门禁行为，必须 per-slice code review，不能合并到 aggregate review" ✓
- **Verdict**: 闭合。4 slices 按 failure blast radius (OOM/stability ↔ secret persistence/CI oracle ↔ Documents resource) 切分，与控制约束一致，每个 slice 有独立 validation matrix 和 review gate。

### R3-E-PF-04 — Playwright bounded TreeWalker preflight ✓ CLOSED

- **Original**: MiMo-03 + DS-03 — DOM cap "轻量计数" 未定义具体 JS 原语；可能使用非轻量操作。
- **Controller requirement**: Specify Playwright DOM/text preflight APIs and tests; forbid `page.content()`/`outerHTML`; state exactly what lightweight APIs are allowed.
- **Fix claim**: `page.evaluate(_BUDGETED_DOM_METRICS_SCRIPT, limits)` with `document.createTreeWalker()`；冻结计数公式；`limit+1` 早停；禁止 API 枚举；spy test。
- **Plan evidence (verified)**:
  - §6.2 lines 129-130: `page.evaluate(_BUDGETED_DOM_METRICS_SCRIPT, limits)`，使用 `document.createTreeWalker()` 遍历 element/text/comment node，不拼接 HTML/text ✓
  - §6.2 line 130: 冻结计数公式 — element: `2 * localName.length + 5`；attribute: `name.length + 6 * value.length + 4`；text DOM: `5 * nodeValue.length`；text: `nodeValue.length`；comment: `nodeValue.length + 7`；doctype: name/publicId/systemId + 32 ✓
  - §6.2 line 130: "乘数是 HTML escaping 的保守上界，不是精确 serializer" ✓
  - §6.2 lines 129-130: 明确禁止 script 读取 `outerHTML`、`innerHTML`、`textContent`、`innerText`、`page.content()` ✓
  - §6.2 line 131: 预检超限时 `page.content()` 与 full text extraction 均零调用；预检通过后才允许一次完整投影 + 二次实际长度验证 ✓
  - §7 S2 Tests line 317: spy `page.evaluate` 的 script/arguments；断言只调用 bounded TreeWalker script、不含 forbidden API、超限时零调用 `page.content()`/text extraction ✓
  - §7 S2 Stop condition line 346: 若预检需要 forbidden API 才能判定 cap → 停止 ✓
- **Verdict**: 闭合。DOM/text preflight 使用 `document.createTreeWalker()` 的保守上界公式，明确禁止完整序列化 API，预检与投影之间有二次验证，spy test 规格完整。

### R3-E-PF-05 — storage-state + BoundedSource SIGKILL cleanup residuals ✓ CLOSED

- **Original**: MiMo-04 + DS-04 — cleanup 承诺 "总是cleanup" 在 SIGKILL 下不可实现；storage state 异常退出未覆盖。
- **Controller requirement**: Add atomic write + startup cleanup for storage state; classify SIGKILL limits as residuals with owner/destination; same for bounded source temp files.
- **Fix claim**: Storage state: `0600` temp → flush/fsync → `os.replace()` final → mode confirm；startup 清 orphan temp + 过期 final；SIGKILL residual owner/destination 明确。BoundedSource: `SpooledTemporaryFile`/系统 `TMPDIR`；SIGKILL residual owner/destination 明确。
- **Plan evidence (verified)**:
  - §6.3 lines 140-142: storage state atomic write 完整流程 — 同目录 `0600` temp、flush + fsync、`os.replace()`、final mode 确认；startup 扫描 owner 命名 orphan temp + 过期 final (按 TTL + mtime)；正常 exception/cancel cleanup ✓
  - §6.3 line 142: SIGKILL residual — "此 residual 的当前 owner 是 `utils/diagnose_web_access.py` storage-state lifecycle，当前 destination 是 S3 的原子写 + startup cleanup + TTL contract；若产品要求无下次启动也能强制删除，则进入后续 workspace secure-artifact cleanup WU" ✓
  - §6.5 lines 158-159: `BoundedSourceSnapshot` — `SpooledTemporaryFile`、系统 `TMPDIR`、不在 workspace 创建 durable temp；context manager 覆盖正常/异常/取消 cleanup ✓
  - §6.5 line 159: BoundedSource SIGKILL residual — "当前 owner 是 `dayu.documents.processors.bounded_source`，destination 是 S4 使用系统 temp lifecycle 并在 artifact 记录这一 operational residual" ✓
  - §7 S3 Residual lines 403-404: storage-state SIGKILL residual 重复确认 ✓
  - §7 S4 Residual line 471: bounded source temp SIGKILL residual 重复确认 ✓
  - 全 plan 不再声称 "总是cleanup" 或 "SIGKILL 保证" ✓
- **Verdict**: 闭合。所有 cleanup 承诺拆分为可达路径 (Python exception/cancel → guaranteed cleanup) 和不可达路径 (SIGKILL/crash → residual with owner/destination)。Storage state 有完整的原子写 + startup reconciliation + TTL 机制。Bounded source 使用系统 TMPDIR lifecycle 兜底。两个 residual 均有明确 owner 和后续 WU destination。

### R3-E-PF-06 — parent-owned smoke fixture ledger ✓ CLOSED

- **Original**: MiMo-05 — smoke oracle fixture 设计未规格化。
- **Controller requirement**: Specify parent-owned fixture request ledger: lifecycle, scope, sentinel generation, expected digest source, negative controls.
- **Fix claim**: Parent 创建 typed in-memory ledger + `ThreadingHTTPServer`；handler only append；child/artifact 不可写；server stop → freeze → classify → discard；256-bit sentinel per case；expected digest from fixture registered bytes；negative controls frozen。
- **Plan evidence (verified)**:
  - §7 S3 line 370: Parent 在 child 启动前创建 typed in-memory ledger，与 `ThreadingHTTPServer` 共生 ✓
  - §7 S3 line 370: "handler 只追加到父进程内存 typed ledger，child/artifact producer 不能写入" ✓
  - §7 S3 line 370: "child 终止后先停止 server，再冻结 ledger 并分类；分类完毕后丢弃，不持久化 raw request、raw sentinel 或 header" ✓
  - §7 S3 line 371: sentinel 生成 — `secrets.token_hex(32)` 256-bit per-case token，作为 URL query 参数；ledger 只记录 token SHA-256、method、normalized path、response kind/digest、accepted/rejected、bounded count ✓
  - §7 S3 line 372: expected digest 来源 — "父进程在 child 启动前从本次 fixture server 实际注册的 exact response bytes 计算 expected `sha256` 与 length，不从 diagnostic artifact、tool output 或 child stdout 反推" ✓
  - §7 S3 line 372: PASS 标准 — "accepted ledger request + artifact content length/digest = parent expected + required backend execution evidence + negative-control must fail；artifact `ok` 只是 observation，不能单独使 case PASS" ✓
  - §7 S3 line 379: 负控冻结 — `ok=true` 但无 ledger request、缺失/错误/重放 sentinel、错误 expected digest/length、challenge endpoint、Playwright 未执行/wrong backend、negative endpoint 意外成功、伪造 schema/artifact ✓
- **Verdict**: 闭合。Fixture ledger 从创建、追加、冻结到分类的完整生命周期已定义；sentinel 生成 (256-bit)、ledger 记录 (digest only)、expected digest 来源 (fixture bytes → parent 预计算) 和 8 类负控均已规格化。PASS 判定正确地从 producer self-report 迁移到 parent-owned oracle。

### R3-E-PF-07 — DuckDuckGo shape/no-results/malformed/challenge criteria ✓ CLOSED

- **Original**: MiMo-06 + DS open question — "已知 result shape" 判定标准未定义。
- **Controller requirement**: Define known result shape, explicit no-results marker, malformed threshold, challenge/login shape drift criteria.
- **Fix claim**: Known shape = `div.result` + `a.result__a`/non-empty title/HTTP(S) href; explicit empty = `.no-results` text in closed allowlist; malformed threshold = 0 valid or >50%; challenge/anomaly/login form → typed provider failure.
- **Plan evidence (verified)**:
  - §6.4 line 149: Known result shape — 顶层 `div.result`，每项必须有 `a.result__a`、非空规整 title、href 解析为非空 HTTP(S)；`a.result__snippet`/`div.result__snippet` 可选；parser 必须检查全部 container 再按 `max_results` 投影 ✓
  - §6.4 line 150: Malformed 定义 — 缺 anchor、空 title、href 非字符串/空或非 HTTP(S)；阈值: 有效项为 0，或 `malformed_count * 2 > container_count` (严格超过 50%) → shape drift；否则丢弃 malformed 返回有效项 + bounded diagnostic count ✓
  - §6.4 line 151: Explicit no-results — 仅在"无 `div.result`、无 challenge/login 证据、唯一 `.no-results` 元素文本精确命中 `["No results.", "No more results."]`"时成立；标记缺失或未知文本 → 非空成功 ✓
  - §6.4 line 152: Challenge/login shape — challenge owner `confirmed`、DOM 已知 anomaly/challenge form/marker、password input、form action 命中 login/signin/auth → typed provider failure，不与空结果共用 `[]` ✓
  - §7 S2 Tests lines 319-320: 覆盖 valid known shape、snippet 缺失、explicit no-results 文本、未知 no-results 文本、challenge/anomaly HTML、password/login form、malformed ratio 0%/50%/>50%/100% ✓
- **Verdict**: 闭合。DuckDuckGo parser 的四个判定维度 (known shape、explicit empty、malformed threshold、challenge/login shape) 均以可测试的 selector 和数值阈值冻结。Strict fail-closed 语义 ("未知文本 → 非空成功"、"有效项 0 或 >50% malformed → shape drift") 正确。

### R3-E-PF-08 — WebResourceBudget provider JSON path/example ✓ CLOSED

- **Original**: MiMo-07 — budget override 键名/JSON path 未定义。
- **Controller requirement**: Define provider JSON path and include minimal full-object example.
- **Fix claim**: Path = `providers["web-tools"].config.resource_budget`；完整 JSON 示例含 7 字段；整体缺失→默认，部分→fail fast。
- **Plan evidence (verified)**:
  - §6.6 line 182: JSON path 冻结 — `providers["web-tools"].config.resource_budget`；解析路径: `provider.py::_parse_config` 从已定位到 `web-tools` 的 `spec.config["resource_budget"]` 解析整个 object ✓
  - §6.6 lines 184-201: 完整 JSON 示例，7 字段 (wire_body_bytes/decoded_body_bytes/warmup_body_bytes/browser_dom_chars/browser_text_chars/diagnostic_error_chars/diagnostic_events)，均为正整数 ✓
  - §6.6 line 182: Fail-fast 规则 — "object 缺字段、未知字段、bool/零/负数均 fail fast，不做 partial fallback；只有整个 `resource_budget` 缺失时才使用上表的完整默认对象" ✓
  - §7 S2 Tests line 320: provider config tests 覆盖完整对象成功、整体缺失使用默认、少字段/多未知字段/bool/非正整数 → fail fast ✓
  - §10: README trigger 同步修正 — `dayu/config/README.md` 更新 provider contract，packaged config 保持缺省 object ✓
- **Verdict**: 闭合。Provider JSON path 唯一确定，解析规则 (整体缺失→默认 vs 部分→fail fast) 明确，完整 JSON 示例提供，测试矩阵覆盖 config 的 4 种路径。

## Fix closure summary

| Fix ID | Source findings | Status | Evidence location in updated plan |
|---|---|---|---|
| R3-E-PF-01 | MiMo-01 | ✓ CLOSED | §3 lines 55-58 |
| R3-E-PF-02 | MiMo-02 + DS-02 | ✓ CLOSED | §6.1 lines 113-116; §7 S1 Tests line 260 |
| R3-E-PF-03 | DS-01 | ✓ CLOSED | §7 (4 slices); §8 lines 485-492 |
| R3-E-PF-04 | MiMo-03 + DS-03 | ✓ CLOSED | §6.2 lines 129-131; §7 S2 Tests line 317 |
| R3-E-PF-05 | MiMo-04 + DS-04 | ✓ CLOSED | §6.3 lines 140-142; §6.5 lines 158-159; §7 S3/S4 Residuals |
| R3-E-PF-06 | MiMo-05 | ✓ CLOSED | §7 S3 lines 370-372, 379 |
| R3-E-PF-07 | MiMo-06 + DS open question | ✓ CLOSED | §6.4 lines 149-152; §7 S2 Tests lines 319-320 |
| R3-E-PF-08 | MiMo-07 | ✓ CLOSED | §6.6 lines 182-201; §7 S2 Tests line 320 |

**8/8 fixes verified closed.** 所有 controller accepted 的 plan correction 均已在 updated plan 中以可直接实施的精度闭合。

## Remaining findings

经对 updated plan 的完整 adversarial re-review（含 architecture boundary、state machine、concurrency/recovery、contract completeness、test coverage、cross-slice dependency、stop condition 和 edge case 维度），**未发现新的 material plan defect**。

以下为 non-blocking observations（不构成 finding，仅记录供 implementation agent 注意）：

### Observation 1 — S1: `web_http_session.py` 现有 session 管理与 per-hop adapter 的过渡

- **位置**: §7 S1 文件列表含 `web_http_session.py`
- **内容**: Plan 要求创建 per-hop `HTTPAdapter` + pool (§6.1)，而当前 `web_http_session.py` 管理共享 `requests.Session` + `Retry` 配置。Plan 未描述现有 session 管理代码是保留给非 fetch HTTP 调用、改为 per-hop adapter factory、还是完全替换。
- **风险**: Implementation agent 可能尝试在共享 session 上 mount per-hop adapters，与 per-hop pool 模型冲突。
- **严重程度**: 观察级（implementation agent 可从 §6.1 的 "不将 target 藏入模块全局" 推断应使用 per-hop adapter factory 模式；code review 会在 S1 review gate 捕获任何偏离）

### Observation 2 — S3: fixture server port discovery 未规格化

- **位置**: §7 S3 fixture ledger 规格
- **内容**: Parent 创建 `ThreadingHTTPServer`，child 需向其发送 HTTP 请求。Child 发现 server port 的机制未定义（如 bind port 0 → env var → child）。
- **风险**: Implementation agent 需自行选择 port 传递方式，但不影响 oracle 独立性 contract。
- **严重程度**: 观察级（标准实现模式，code review 可验证）

### Observation 3 — §6.2 TreeWalker 计数公式的跨浏览器稳定性

- **位置**: §6.2 line 130 冻结的 DOM 计数公式
- **内容**: 公式基于 HTML escaping 上界 (`5 * nodeValue.length` for text, `6 * value.length` for attributes)。若 `page.content()` 的序列化实现与公式假设的 escaping 乘数不同（例如 Chromium 对某些 Unicode 使用 numeric character references 而非 UTF-8 直写），公式可能在某些边界情况下不是严格上界。
- **缓解**: Plan §6.2 line 130 已内置安全阀 — "实现若证明该公式对当前 `page.content()` 并非保守上界，必须更严格地 fail closed 或回到 plan/re-review"
- **严重程度**: 观察级（安全阀已覆盖，且 S2 stop condition 要求预检不能退化为 `page.content()` 调用）

## Architecture boundary verification (updated plan)

对 updated plan 的架构边界重新验证：

- **Layering**: Web 全部 owner 在 `dayu.tools.web`；Documents 的 `BoundedSourceSnapshot` 在 `dayu.documents`（层中立）；diagnostic wiring 在 `utils/`。无跨层 owner 泄漏 ✓
- **Dependency direction**: `dayu.documents` → 无 Host/Engine/Fins/tools 依赖；`dayu.tools.web` → `dayu.runtime`（层中立 primitives），无反向依赖 ✓
- **No Host/Engine modification**: Plan §4.2 明确排除，§7 各 slice 文件列表不含 Host/Engine 路径 ✓
- **Public contracts**: Diagnostic schema v2 (§6.6)、Doc tool LLM-facing outputs (§6.6)、Web failure codes (§6.6) 均内聚于各自 owner ✓
- **No overengineering**: 无 repository-wide framework、durable cursor、daemon、proxy 或 Host state machine ✓

## State machine / lifecycle verification

- **Response lifecycle**: create → use (caller copies facts) → close (lease owner)，redirect 中间 response 在 `_request_with_safe_redirects` 内关闭 → transfer 最终 response ✓
- **Storage state lifecycle**: temp (0600) → flush/fsync → os.replace → final (0600) → TTL expiry + startup reconciliation ✓
- **Fixture ledger lifecycle**: create (parent) → append (handler only) → freeze (after child exit) → classify → discard ✓
- **Bounded source lifecycle**: open → chunked copy → cap check → context manager cleanup；SIGKILL → system TMPDIR lifecycle ✓

## Test coverage assessment

| Slice | Test location | Key coverage | Adequate? |
|---|---|---|---|
| S1 | `tests/tools/web/test_web_tools_provider.py`, `test_diagnose_web_access.py` | Egress/peer/retry/redirect/close matrix; loopback HTTP/HTTPS integration; DNS rebinding fake | ✓ |
| S2 | `tests/tools/web/test_web_tools_provider.py` | Codec table-driven (gzip/deflate/brotli/zstd); DOM/text preflight spy; challenge matrix; DuckDuckGo parser matrix; provider config fail-fast | ✓ |
| S3 | `tests/tools/web/test_web_tools_provider.py`, `test_diagnose_web_access.py`, `test_smoke_web_ci.py` | Secret redaction; storage-state atomic/startup; ledger lifecycle; 8 negative controls | ✓ |
| S4 | `tests/documents/test_processors.py`, `test_import_boundary.py`, `tests/tools/test_doc_tools_provider.py` | Bounded read/line scan; directory entry cap; search source/result cap; cancellation; import boundary | ✓ |
| Aggregate | All above + `pyright` + `git diff --check` + source audit grep | Cross-slice integration; no old pattern leakage | ✓ |

## Residual risk classification (post-fix)

Plan 中所有 residual risks 均正确分类并有 owner/destination：

| Risk | Owner | Destination |
|---|---|---|
| urllib3 version drift on extension points | Web transport owner | S1 completion artifact + version upgrade regression |
| Playwright public direct fail closed → availability降级 | Web egress policy owner | Subsequent deployment/browser proxy WU |
| Chromium internal DOM/CPU不受Python cap控制 | Web Playwright backend owner | Subsequent browser sandbox/resource-lane WU |
| digest 低熵字典猜测 | Web diagnostic owner | Design constraint (只用于fixture关联) |
| 外部 live URL 不稳定 | Web smoke owner | Diagnostic-only, 不做 hard PASS |
| Storage-state SIGKILL 残留 | `utils/diagnose_web_access.py` | S3 atomic write + startup/TTL + subsequent secure-artifact cleanup WU |
| BoundedSource SIGKILL temp 残留 | `dayu.documents.processors.bounded_source` | S4 system TMPDIR lifecycle + subsequent Documents temp-artifact cleanup WU |
| Doc file-authority/symlink 竞态 | Doc tool file-authority owner | Subsequent Doc tool file-authority WU |
| Doc processor CPU/对象放大 | Doc tool processor owner | source cap + process timeout 治理 |

## Plan review conclusion

**Verdict: pass**

理由：

1. **8/8 controller accepted fixes verified closed** — 所有 PF-01 至 PF-08 的 plan correction 均已在 updated plan 中以可直接实施的精度闭合，无半修复或遗漏。
2. **No new material defects found** — 对 updated plan 的完整 adversarial re-review（architecture boundary、state machine、concurrency/recovery、contract completeness、test coverage、cross-slice dependency、stop condition、edge case）未发现新的 material plan defect。
3. **Plan is code-generation-ready** — 4 slices 各有明确的 owner closure、具体文件列表、冻结 contract、完整测试矩阵、精确 validation commands、stop condition 和 completion signal。Implementation agent 不需要重新设计核心决策。
4. **3 non-blocking observations** — 均为 implementation detail 级别，不构成 plan defect，code review gate 可自然覆盖。
5. **Residual risks correctly classified** — 9 项 residual risk 均有明确 owner 和后续 WU destination，不在 R3-E 内伪称已治理。

## Completion report

- **Verdict**: pass
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-rereview-ds.md`
- **Fixed IDs verified closed**: 8/8 (R3-E-PF-01 through R3-E-PF-08)
- **Remaining original review findings**: 0 (all controller-accepted findings fixed)
- **New findings**: 0
- **Non-blocking observations**: 3
- **Blocking questions**: 0
- **Slice count**: 4 (S1/S2/S3/S4, blast-radius justification in plan §8)
- **Accepted source findings**: 10
- **Rejected/deferred/needs-evidence source findings**: 0
- **Plan ready for implementation**: yes
