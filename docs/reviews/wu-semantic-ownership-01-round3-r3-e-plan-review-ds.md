# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Plan Review — AgentDS

## Review metadata

- **Reviewer**: AgentDS
- **Reviewed artifact**: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`
- **Review type**: adversarial plan review（不修改代码/文档）
- **Design truth**: `docs/host/design.md`, `docs/engine/design.md`
- **Control truth**: `docs/host/issues-implementation-control.md`, `docs/phaseflow-umbrella-optimization-control.md`
- **Goal confirmation**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-goal-confirmation.md`
- **Source adjudication**: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round3-controller-adjudication.md` §R3-E (lines 154-180)
- **Timestamp**: 20260713-114802

## Assumptions tested

1. **10 accepted findings have correct semantic owner, direct evidence, and executable fix path** — tested against code evidence in §5 table and source adjudication.
2. **3 slices are correctly cut by owner boundary, not by file/raw finding** — tested against phaseflow control §Slice 切分约束.
3. **No real owner missed; no scope expansion into Fins/tool-security/Host/Engine** — tested against §4 scope/non-goals and §11 deferred items.
4. **Web egress requests/urllib3 connect-before-request peer proof is achievable** — tested against urllib3 2.6.3 connection internals.
5. **Test matrices cover resource caps, diagnostic redaction, challenge/DuckDuckGo, Documents bounded source, and smoke oracle** — tested against §7 per-slice test plans.
6. **README trigger, tool-security boundary, and residual destinations are clear** — tested against §10 and §11.

## Findings

### 01-未修复-中-S2 合并 5 个不同 failure blast radius 的 owner concern；phaseflow slice 约束要求按 blast radius 拆分

- **位置**: Plan §7 Slice 2 范围定义
- **问题类型**: 切片过粗 / 控制文件偏离
- **当前写法**: S2 合并 `WebResourceBudget + diagnostic projection + challenge/parser outcome producer -> tool/diagnostic projection -> local fixture independent oracle/negative controls`。Plan §7 给出合并理由："smoke_web_ci.py 直接消费 diagnose_web_access.py schema并据此分类 PASS，diagnostic schema/redaction变化若没有同slice迁移oracle，会形成'producer已变、classifier仍信旧自报字段'的孤立半成品；二者共享 Web validation matrix和失败 blast radius。"
- **反例/失败场景**:
  1. Resource budget 实现引入 OOM bug → review 发现 → **整个 S2 打回重做**，challenge/parser/oracle/diagnostic 的正确实现也被搁置。
  2. Diagnostic redaction 漏掉一个 secret sentinel → review 发现 → resource budget 和 challenge 的正确实现也需陪同重交。
  3. 五者的 failure blast radius 实际不同：resource budget bug → OOM/进程被杀（稳定性）；challenge false positive → 正常页面被标为 blocked（LLM 工具结果错误）；DuckDuckGo shape drift → 空结果伪装成功（LLM 工具结果错误）；diagnostic redaction bug → secret 写入磁盘（安全泄漏）；smoke oracle bug → CI 假通过（发布门禁绕过）。
- **为什么有问题**: Phaseflow control §Slice 切分约束 (lines 97-104) 要求"是否有不同 failure blast radius？只有答案为'是'时才拆分"。Plan 声称五者共享 blast radius，但 OOM、安全泄漏和 CI 门禁绕过的 blast radius 显然不同——它们影响的系统边界（进程内存、磁盘文件、CI pipeline）是独立的。Plan 的合并理由是 consumer 耦合（smoke → diagnostic），不是 owner 内聚——这是 consumer-driven merge，不是 owner-driven merge，与控制约束的语义不一致。
- **直接证据**:
  - Phaseflow control lines 99-103: "是否有不同 failure blast radius？...只有答案为'是'时才拆分。"
  - Plan §7 S2 scope: 5 distinct concerns listed under single owner closure
  - Plan §7 S2 justification paragraph: merge reason is consumer coupling, not blast radius identity
  - Plan §6.2 residual: DOM gate 列 residual risk，但 diagnostic redaction 的安全泄漏风险是不同类别的 residual
- **影响**: 实施 Agent 跑偏 / review 不可验收 / 后续返工——单个 concern 的 review failure 迫使全部 5 个 concern 重新提交，增加 gate 往返次数和 controller 裁决成本。
- **建议改法和验证点**:
  - 方案 A（推荐）: 将 S2 拆为 S2a (resource budget + challenge/parser) 和 S2b (diagnostic projection + smoke oracle)，保持 producer→consumer 顺序依赖但不合并 review gate。S2a 先 freeze，S2b 消费 S2a 的 frozen contract。
  - 方案 B: 保持 3 slices，但在 plan 中显式承认 blast radius 不同，并记录为 accepted risk（controller 确认后方可进入 implementation）。
  - 验证点: 修改后的 plan 对每个 slice 列出其唯一的 failure blast radius，确认不跨 blast radius 合并。
- **修复风险**: 低——只需调整 slice 边界和 gate 顺序，不改变实现内容。
- **严重程度**: 中

### 02-未修复-中-urllib3 Retry 与 pinned address 交互未进入 S1 测试矩阵；retry 新建连接可能绕过地址绑定

- **位置**: Plan §7 Slice 1 Tests 与 `web_http_session.py` 现有 Retry 配置
- **问题类型**: 测试缺口 / 并发恢复风险
- **当前写法**: Plan §7 S1 Tests 覆盖 DNS rebinding（首次公网→二次私网）、literal/private IP 拒绝、302 redirect 拒绝、response close 矩阵。但未提及 urllib3 `Retry` 机制与 pinned address transport 的交互测试。
- **反例/失败场景**:
  1. 自定义 transport 在首次 `_new_conn()` 使用 pinned address A 创建 socket。
  2. 连接失败（超时/RST）。
  3. urllib3 `Retry(connect=3)` 触发重试，调用 `_new_conn()` 创建**新**连接。
  4. 若自定义 transport 在重试路径上未复用同一 `AuthorizedHttpTarget` 的 approved addresses，而是重新调用 resolver → DNS rebinding 可在此窗口返回私网 IP。
  5. 重试连接成功连接到私网地址，egress policy 被绕过。
- **为什么有问题**: 现有 `web_http_session.py:43-53` 配置 `Retry(connect=_RETRY_CONNECT=3, read=_RETRY_READ=3)`——每次 connect 重试创建全新 socket。若 pinned address transport 只在首次连接时注入 approved addresses 而 retry 路径走默认 DNS 解析，则 egress policy 的 "connect 时不重新解析 hostname" 约束在 retry 场景下被破坏。
- **直接证据**:
  - `web_http_session.py:43-53`: `Retry(connect=3, read=3, ...)` + `HTTPAdapter(max_retries=retry)`——明确存在 connect 重试路径。
  - `web_http_session.py:81-92`: `_create_no_retry_session()` 的 `Retry(connect=0)`——说明代码库已知 retry 与安全语义的交互（no-retry session 用于 probe/warmup）。
  - Plan §7 S1 Tests: 完整测试矩阵列举但没有 "retry 后仍使用同一 pinned address" 或 "retry 不触发额外 DNS" 的断言。
  - Plan §6.1: "不得在 connect 时重新对原 hostname 做不受控 DNS"——这个约束需要在 retry 场景下显式验证。
- **影响**: 实施 Agent 可能正确实现首次连接的 pinning，但遗漏 retry 路径的保护，导致 egress policy 在间歇性网络故障时被绕过——这是最难发现的 TOCTOU 变体（只在首次连接失败时触发）。
- **建议改法和验证点**:
  - S1 测试矩阵增加：注入第一次 connect 失败（模拟超时/RST）、第二次 connect 成功的 fake transport；断言两次 connect 使用同一组 approved addresses，未调用额外 DNS 解析。
  - 或：S1 的 pinned transport 默认使用 `Retry(connect=0)`（类似 `_create_no_retry_session`），由上层 `_request_with_safe_redirects` 在每次 hop 失败时决定是否重试整个 hop（含重新 resolve→authorize 流程），而不是依赖 urllib3 内部 retry。
  - 验证点: `tests/tools/web/test_web_tools_provider.py` 新增 `test_egress_pinned_retry_uses_same_approved_addresses`。
- **修复风险**: 低——增加一个测试用例和/或调整 retry 策略。
- **严重程度**: 中

### 03-未修复-低中-Playwright DOM cap "轻量计数" 方案未定义具体 JS 原语；可能使用非轻量操作

- **位置**: Plan §6.2 "Playwright 在调用 `page.content()` / full innerText 前先读取轻量计数并与 DOM/text cap 比较"
- **问题类型**: 契约缺失 / 不可直接实施
- **当前写法**: Plan 只说"轻量计数"，未定义具体用什么 JS API 获取计数。`page.content()` 返回 `document.documentElement.outerHTML`，其大小无法在不序列化整个 DOM 的情况下精确预知。可用的近似计数包括 `document.querySelectorAll('*').length`（元素数量）、`document.body.textContent.length`（文本长度）、`document.documentElement.outerHTML.length`（恰恰是要限制的操作本身）。
- **反例/失败场景**:
  1. 实施 Agent 选择 `document.documentElement.outerHTML.length` 作为"轻量计数"——这在 JS 侧已经是完整 DOM 序列化，只是不跨进程传输。Chromium 进程内的内存分配未被阻止，cap 只保护了 Python 侧。
  2. 实施 Agent 选择 `document.querySelectorAll('*').length`——元素数量与 HTML 字符串长度无稳定比例关系（一个 `<div>` 有大量 data 属性 vs 一万个空 `<span>`），无法准确预判。
- **为什么有问题**: Plan §2.2 目标要求"完整物化前受限"——若轻量计数本身就是一次完整物化（只是在浏览器进程内而不是 Python 进程内），cap 的语义从"阻止分配"降级为"阻止跨进程传输"。Plan §6.2 已将此列为 residual risk，但未给出足够约束让实施 Agent 做出正确选择。
- **直接证据**:
  - Plan §6.2: "Playwright 在调用 `page.content()` / full innerText 前先读取轻量计数并与 DOM/text cap 比较；超限关闭 context/process result并返回 `browser_dom_too_large`。"——未定义轻量计数的具体 API。
  - `web_playwright_backend.py:1241`: 当前 `page.content()` 无任何 cap 检查。
  - Plan §6.2 residual: "这只承诺阻止完整 DOM跨进程/Python materialization；浏览器进程本身仍由现有 process-backed timeout/kill治理"——承认浏览器进程内的内存不受控。
- **影响**: 实施 Agent 可能选择看起来合理但实际上不轻量的计数方式。若选择 `outerHTML.length`，cap 语义退化为"阻止跨进程传输"而非"阻止分配"，与 Plan §2.2 的目标不完全一致（但 Plan residual 已承认此限制）。
- **建议改法和验证点**:
  - 明确轻量计数 API：建议使用 `page.evaluate("() => document.body ? document.body.textContent.length : 0")` 作为 text cap 的前置检查（textContent 不需要序列化 HTML 标签），使用 `page.evaluate("() => document.querySelectorAll('*').length")` 作为 DOM 复杂度的辅助信号（非精确大小预测）。
  - 在测试矩阵中增加：断言 DOM cap 检查**不调用** `page.content()` 或 `document.documentElement.outerHTML`。
  - 验证点: `tests/tools/web/test_web_tools_provider.py` 中 DOM cap 测试 spy `page.evaluate()` 调用，断言 cap 检查只使用指定轻量 API。
- **修复风险**: 低——只需明确 API 选择并在 test 中断言。
- **严重程度**: 低-中

### 04-未修复-低-process-backed execution 下 `BoundedSourceSnapshot` 临时文件在 SIGKILL 时无法 cleanup

- **位置**: Plan §6.5 cleanup 承诺与 §3 process-backed execution 声明
- **问题类型**: 状态机漏洞 / residual risk 未完全分类
- **当前写法**: Plan §6.5: "source snapshot/context退出总是cleanup；取消与resource failure不留下temp file"。Plan §3: "Doc/Web blocking 工具使用 process-backed execution"。
- **反例/失败场景**: Child process 被 SIGKILL（非 SIGTERM）时，Python 的 `__exit__`、`finally`、`atexit` 和 `signal handler` 全部不执行。若 `BoundedSourceSnapshot` 使用 `tempfile.SpooledTemporaryFile` 或显式 temp 文件，SIGKILL 后文件残留。
- **为什么有问题**: Plan 承诺"总是cleanup"，但 process-backed execution + SIGKILL 使这个承诺不可实现。Plan §6.2 已将 process-backed timeout/kill 列为 residual risk，但未将此 temp file cleanup 限制关联到该 residual。
- **直接证据**:
  - Plan §6.5: "source snapshot/context退出总是cleanup；取消与resource failure不留下temp file"
  - Plan §3: "Doc/Web blocking 工具使用 process-backed execution"
  - Plan §6.2 residual: "浏览器进程本身仍由现有 process-backed timeout/kill治理，列为 residual risk"——仅提到浏览器进程，未包括 Documents bounded source temp file。
  - Python 文档: `SIGKILL` 不可捕获，`__exit__`/`finally`/`atexit` 均不执行。
- **影响**: 极端情况下 temp 文件残留。若 temp 文件写入系统标准 temp 目录（`/tmp` 或 `TMPDIR`），OS 级清理可兜底；若写入 workspace 自定义目录，残留文件可能累积。严重程度低因为：content 已经是 bounded（最多 32MB），且不包含 secret（temp 文件是 source bytes 的副本，不是 diagnostic artifact）。
- **建议改法和验证点**:
  - 在 §6.5 或 §7 S3 residual risks 中显式记录：SIGKILL 场景下 temp file cleanup 不保证，依赖 OS temp dir 或后续 workspace cleanup 兜底。
  - `BoundedSourceSnapshot` 优先使用 `tempfile.SpooledTemporaryFile`（内存缓冲）或系统 `TMPDIR` 下的 temp 文件（OS 重启时自动清理）。
  - 验证点: 不要求 SIGKILL cleanup 的自动化测试（不可测试），只需文档记录。
- **修复风险**: 低——添加一行 residual risk 记录。
- **严重程度**: 低

## Open questions

1. **`dayu.runtime` diagnostic primitives 与 Web projection 的 API 匹配度**: Plan §6.3 说复用 `dayu.runtime.diagnostic_text` / `json_redaction` / digest。已验证这些模块存在（`dayu/runtime/diagnostic_text.py`, `json_redaction.py`, `_digest.py`），但 `json_redaction` 是否支持 URL userinfo/query 剥离和 header allowlist 过滤需在 S2 实施时验证。若不支持，`web_diagnostics.py` 需补充 Web-specific sanitization——这在 plan 的 ownership boundary 内（"不把 URL/HTTP业务规则下沉到 runtime"），不构成 plan defect。

2. **`_request_with_safe_redirects` 的逐 hop 地址绑定与 `AuthorizedHttpTarget` 的对接方式**: Plan §6.1 定义了 contract（每 hop 一个 `AuthorizedHttpTarget` → transport 只用 approved addresses），但没有定义两者之间的具体接口（参数传递方式）。实施 Agent 需要在 `_request_with_safe_redirects` 内为每个 hop 创建新的 `AuthorizedHttpTarget` 并传递给 transport。这是合理的实施细节，不构成 plan defect，但 reviewer 应在 S1 code review 时验证接口简洁性。

## Residual risks and suggested tracking

| Risk | Suggested destination |
|---|---|
| urllib3 版本升级后 pinned transport 扩展点变化 | S1 completion artifact 记录 tested-against urllib3 version，后续版本升级时回归 |
| Playwright 公网 direct 默认 fail closed 降低部分站点可用性 | Plan §7 S1 residual（已记录）——后续 deployment/browser proxy WU |
| Chromium 进程内 DOM 不受 Python cap 控制 | Plan §6.2 residual（已记录）——后续 browser sandbox WU |
| digest 对低熵 secret 存在字典猜测风险 | Plan §7 S2 residual（已记录） |
| Doc tool file-authority/symlink 竞态 | Plan §7 S3 residual（已记录）——后续 Doc tool file-authority WU |
| SIGKILL 下 temp file 残留 | 本 review F-04——建议加入 §7 S3 residual |
| urllib3 Retry + pinned address TOCTOU | 本 review F-02——建议加入 S1 测试矩阵 |

## 10 accepted findings ownership verification

对 §5 表中 10 个 accepted findings 逐个验证：

| Finding | Semantic owner 正确？ | 直接代码证据存在？ | 修复路径可执行？ | 备注 |
|---|---|---|---|---|
| DR-004 | ✓ `dayu.tools.web` egress policy | ✓ `web_tools.py:2869-2946` DNS→predicate gap | ✓ S1 | — |
| DR-015 | ✓ Web resource budget owner | ✓ `web_fetch_orchestrator.py:552-578` 整包 gzip.decompress | ✓ S2 | — |
| DR-016 (Web) | ✓ Web diagnostic projection | ✓ `web_tools.py:1194-1207` `diagnostics={payload}` | ✓ S2 | — |
| DR-019 | ✓ `doc_tools.py` business cap | ✓ `doc_tools.py:1364-1387,1581-1621,1921-1963,1991-2002` | ✓ S3 | — |
| DR-032 (Web) | ✓ `smoke_web_ci.py` oracle | ✓ `smoke_web_ci.py:1207-1231` 只要求字段存在 | ✓ S2 | — |
| DR-033 | ✓ shared egress/diagnostic | ✓ `diagnose_web_access.py:1132-1152` 自建 policy | ✓ S1+S2 | — |
| DS redirect leak | ✓ response lease owner | ✓ `web_fetch_orchestrator.py:696-723` cancel/reject before close | ✓ S1 | — |
| DS challenge FP | ✓ challenge decision owner | ✓ `web_challenge_detection.py:17-49,135-146` 宽泛单信号→True | ✓ S2 | — |
| DS challenge/status | ✓ fallback decision owner | ✓ `web_tools.py:2029-2054` status in {401,403,429,503} gate | ✓ S2 | — |
| DS DuckDuckGo | ✓ parser outcome owner | ✓ `web_search_providers.py:691-728` 遍历 div.result→[] | ✓ S2 | — |

全部 10 个 finding 的 semantic owner、直接证据和修复路径均成立。无遗漏真实 owner。无错误扩张到 Fins/Host/Engine。

## README trigger verification

Plan §10 的 README trigger 分析经核对：

- **根 `README.md`**: 约束为"最终用户使用手册"（lines 14-21）。R3-E 不改变 CLI 入口、安装、工作区文件位置或用户工作流。**不触发，正确。**
- **`dayu/README.md`**: 约束为"已实现的总揽级设计意图"（lines 11-17）。R3-E 不改变 `UI→Service→Host→Engine` 分层或 `dayu.tools`/`dayu.documents` 依赖方向。但 S3 在 `dayu.documents` 新增 `BoundedSourceSnapshot`——这是 `dayu.documents` 的 **新 public primitive**，不是 internal helper。若 `dayu/README.md` 的"稳定边界"章节涵盖了 `dayu.documents` 的公共接口列表，则此新增可能需要更新。Plan §10 的条件触发（"若implementation实际新增跨包public contract...必须停止并重新做trigger判断"）覆盖了此风险。**Plan 判断正确，条件触发合理。**
- **`tests/README.md`**: lines 164-179 覆盖 Documents/Web/Doc tools 测试层级。Plan 预期新增 SSRF peer、resource bomb、diagnostic redaction、oracle negative-control 和 document cap 测试——这些属于其读者职责。**触发，正确。**

## Tool-security boundary verification

Plan §11 的 tool-security 边界清晰：
- R3-E 实现：Web egress peer safety、resource caps、diagnostic redaction、challenge/fallback、DuckDuckGo outcome、Doc pre-budget、smoke oracle
- Deferred（含 owner/destination）：Fins upload、tool-security framework、LLM-facing security schema、Playwright proxy、provider/Host memory smoke、Engine UTF-8 diagnostic、Doc file-authority

经核对：
- 无 Fins upload/download 变更
- 无全仓 security framework
- 无 Host/Engine 修改
- 所有 deferred 项有明确 owner/destination

**Plan 的 tool-security boundary 划分正确。**

## Final plan review conclusion

**Verdict: pass-with-risks**

理由：
- 10 个 accepted findings 的 semantic owner、直接代码证据和可执行修复路径全部成立。
- 3 slices 的 owner boundary 切割基本合理，S1→S2→S3 依赖方向正确。
- Web egress 方案在 requests 2.33.1 + urllib3 2.6.3 下具有可行性（通过自定义 `HTTPAdapter`/`HTTPSConnection`子类实现地址绑定与 peer 验证），stop condition 保护了不可行场景。
- 非目标边界（Fins/Host/Engine/tool-security framework）明确且未越界。
- README trigger 分析正确，conditional trigger 覆盖了 S3 可能触发 `dayu/README.md` 更新的边界情况。

4 个 findings（2 中 + 1 低中 + 1 低）均不构成 blocker，但建议在 plan 进入 implementation 前由 controller 裁决 F-01（S2 blast radius）和 F-02（Retry + pinned address test gap）的处理方式。

## Completion report

- **Verdict**: pass-with-risks
- **Artifact path**: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-plan-review-ds.md`
- **Findings count**: 4（2 medium, 1 low-medium, 1 low）
- **Blocking questions**: 0
- **Open questions**: 2（非阻塞）
- **Accepted finding ownership verified**: 10/10 ✓
- **Slice count**: 3（在 phaseflow control 1-3 建议范围内）
- **README trigger**: 正确——仅 `tests/README.md` 触发
- **Tool-security boundary**: 清晰且未越界
- **Residual risks classified**: 6（4 from plan + 2 from this review）
