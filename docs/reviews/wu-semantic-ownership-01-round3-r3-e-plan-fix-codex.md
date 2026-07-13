# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Plan Fix — AgentCodex

## Gate Metadata

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / Round3 / R3-E`
- Gate: `plan fix only`
- Timestamp: `2026-07-13T12:11:09+08:00`
- Plan target: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`
- Artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-fix-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-controller-adjudication.md`
- Review inputs: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-mimo.md`、`docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-ds.md`
- Write scope: 只修改 plan target 并新增本 artifact；未修改生产代码、测试、README、design/control truth 或 reviewer artifact，未 stage/commit/push，未进入 implementation。

## 第一性原理与 Owner 判断

Controller accepted 的 `R3-E-PF-01` 至 `R3-E-PF-08` 均成立，且严重性未被高估。这些不是扩张为仓库级 tool-security framework，而是补齐已 accepted owner 无法直接实施或无法验收的 contract：

- connect peer 事实必须由 target-bound transport 在 HTTP request bytes 前证明，且 retry 不能绕回 DNS。
- DOM/text preflight 不能用被限制的完整值本身来计数。
- storage state、diagnostic、smoke PASS 和 bounded source temp 都必须由各自 lifecycle/oracle owner 承诺可证明范围，不能把 `SIGKILL` 或 producer 自报当成已治理事实。
- Web resource/provider outcome、secret 持久化/CI oracle 与 Documents temp/resource 的 blast radius 不同，不应为了保持 3 slices 而合并 review failure domain。

Owner 边界保持不变：Web egress/resource/challenge/search/diagnostic 归 `dayu.tools.web`；diagnostic artifact/storage state 归 `utils/diagnose_web_access.py`；Web PASS classifier/fixture ledger 归 `utils/smoke_web_ci.py`；Doc business caps 归 `dayu.tools.doc_tools`；bounded source primitive 归层中立 `dayu.documents`。

## Controller Accepted Plan Fixes

### R3-E-PF-01 — 已修复

- 删除错误的 `docs/host/design.md` 行号声明和 source-adjudication 单行定位。
- 改为引用 `docs/engine/design.md` 的稳定章节名，以及 `dayu/tools/__init__.py`、`dayu/documents/__init__.py`、`dayu/runtime/__init__.py` 模块 docstring 和实际 process-backed 代码 owner。
- 不保留 reviewer 已证明不存在的 design line citation。

### R3-E-PF-02 — 已修复

- 用当前环境直接确认 `requests==2.33.1` / `urllib3==2.6.3`，并核对 `HTTPAdapter.get_connection_with_tls_context`、connection-pool `ConnectionCls`、`HTTPConnection._new_conn()` 与 `HTTPSConnection.connect()` 扩展点。
- Plan 冻结每 hop target-bound adapter/pool/connection：`_new_conn()` 只连 approved numeric addresses，`getpeername()` 在返回 socket 前验证 peer；pool host 保留原 IDNA hostname，因而 HTTP Host、TLS SNI 和 certificate hostname 不被 IP 替换。
- 现有 urllib3 Retry 只能在同一 immutable approved set 的 target-bound pool 内重建 socket；redirect 才创建新 target。测试固定首次 connect 失败后 retry 仍使用同一 approved set、不二次 resolve、不改 SNI/cert host。

### R3-E-PF-03 — 已修复

- 采用 controller 首选，把原 S2 拆为 S2 `Web 资源预算 + challenge/search outcome` 和 S3 `diagnostic projection + storage-state lifecycle + smoke oracle`；Documents 顺延为 S4。
- Plan 显式记录 4 slices 超过默认 1-3 建议的原因：OOM/provider outcome、secret persistence/CI oracle 和 Documents temp/resource 是不同 failure blast radius，每组有独立 validation 与 review failure domain。

### R3-E-PF-04 — 已修复

- Playwright preflight 只允许 `page.evaluate(_BUDGETED_DOM_METRICS_SCRIPT, limits)` 内的 bounded `document.createTreeWalker()`，冻结 element/attribute/text/comment/doctype 的保守计数公式并在 `limit + 1` 早停。
- 明确禁止 preflight 调用/读取 `page.content()`、`outerHTML`、`innerHTML`、`textContent` 或 `innerText`，并要求 spy test 检查 script 与零调用。
- Residual 明确为 Chromium 已构造 DOM 的内存、TreeWalker CPU 和动态 DOM race；owner 为 Web Playwright backend，destination 为后续 browser sandbox/resource-lane WU。

### R3-E-PF-05 — 已修复

- Storage state 改为同目录 `0600` temp -> flush/fsync -> `os.replace()` final -> mode 确认；startup 只清理本 owner 命名的 orphan temp 与过期 final。
- 正常 exception/cancel 和 TTL 路径保证 cleanup；不再承诺 `SIGKILL` / 主机崩溃的当场 cleanup。Storage-state residual owner/destination 为 S3 artifact lifecycle + startup/TTL，更强保证归后续 workspace secure-artifact cleanup WU。
- `BoundedSourceSnapshot` 优先 `SpooledTemporaryFile` / 系统 `TMPDIR`；`SIGKILL` 最多残留有界 source temp。Residual owner 为 bounded-source 模块，destination 为 S4 operational record / 后续 Documents temp-artifact cleanup WU。

### R3-E-PF-06 — 已修复

- Parent 在 diagnostic child 前创建与 local fixture server 共生的 typed in-memory ledger；handler 只追加，child/artifact 不能写，server 停止后 freeze/classify，分类后丢弃，不持久化 raw request/sentinel/header。
- 每 case 由 parent 用 `secrets.token_hex(32)` 生成 256-bit URL-query sentinel；ledger 只记 token digest。Expected digest/length 在 child 启动前从 fixture 注册的 exact response bytes 计算，不从 artifact 反推。
- 负控冻结为：`ok=true` 但无 ledger request、缺失/错误/重放 sentinel、digest/length 不同、challenge、browser 未执行/wrong backend、negative endpoint 意外成功与 forged schema/artifact。

### R3-E-PF-07 — 已修复

- Known result shape 冻结为 `div.result` + 必需 `a.result__a`/non-empty title/valid HTTP(S) href，snippet selector 可选。
- Explicit empty 只在无 result/challenge/login 且唯一 `.no-results` 文本精确命中封闭 allowlist 时成立。
- Malformed threshold 固定为有效项为 0 或严格超过 50%；challenge/anomaly/password/login form 覆盖 result/no-results 并投影 typed provider failure。

### R3-E-PF-08 — 已修复

- Provider JSON 唯一路径冻结为 `providers["web-tools"].config.resource_budget`。
- Plan 给出包含 7 个必需字段的完整 JSON 对象示例；整体缺失使用完整默认，对象部分缺失/未知/非正整数均 fail fast。
- 同步修正 README trigger：implementation 需更新 `dayu/config/README.md` 的 provider contract，packaged config 保持缺省该 object，避免复制数值真源。

## Slice 结构与 Residuals

- S1: Web egress、pinned transport、retry、response ownership。
- S2: Web resource budget、Playwright preflight、challenge/search outcome。
- S3: Web diagnostic projection、storage-state lifecycle、parent-owned smoke oracle。
- S4: Documents bounded source/read/list/search 预预算。

未扩张到 Fins upload/download security、Host/Engine 治理、repository-wide tool-security framework、公网 Playwright proxy 或 durable cleanup daemon。依然存在的 operational residual 均已在 plan 写明 owner/destination：urllib3 扩展点版本飘移、Chromium 内部 DOM/CPU、storage/source temp 的 `SIGKILL` 残留、低熵 digest 与外部 live URL 不稳定。

## Validation

- `git diff --check`: pass（exit 0，无输出）。
- `git diff --no-index --check /dev/null docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`: pass（无 whitespace diagnostic；exit 1 仅表示相对 `/dev/null` 存在内容差异）。
- `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-fix-codex.md`: pass（无 whitespace diagnostic；exit 1 仅表示相对 `/dev/null` 存在内容差异）。
- `git status --short` / scope check: pass。Preflight baseline 已包含 modified control doc、未跟踪 plan 与 3 个 review artifacts；最终状态相比 baseline 只修改指定 plan 内容并新增本 fix artifact。`git diff --name-only` 仅列出 pre-existing `docs/host/issues-implementation-control.md`；未跟踪列表只包含本轮 plan/fix/review Markdown artifacts。无 `dayu/`、`tests/` 或 README 状态变化。
- pytest / pyright: 未运行；本 gate 只修改 Markdown plan/review artifact，且用户明确禁止进入 implementation。

## Gate Result

- Fixed IDs: `R3-E-PF-01`、`R3-E-PF-02`、`R3-E-PF-03`、`R3-E-PF-04`、`R3-E-PF-05`、`R3-E-PF-06`、`R3-E-PF-07`、`R3-E-PF-08`。
- Implementation slices: 4（S1/S2/S3/S4）。
- Blocking questions: 0。
- Decision: `ready-for-plan-rereview` after final validation。
- Next gate: controller 派发 AgentMiMo 与 AgentDS plan re-review；本 Agent 不进入 re-review 或 implementation。
