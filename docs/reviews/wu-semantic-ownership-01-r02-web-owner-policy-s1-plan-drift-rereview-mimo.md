# R02-S1 plan drift re-review — MiMo（第一路）

- **target**: `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`（946行，drift fix 后最终版）
- **scope**: 验证 `R02-S1-DR-01..04` 在全链闭合；检查九文件直接 consumer 闭集、四文件 type-only 可执行性、owner/payload 唯一性、utility 1024/80 时序、tests/coverage/pyright/README/completion 一致性、S2/S3/Issue178/R03 scope leakage
- **evidence sources**: plan（946行）、drift-codex、controller-adjudication、fix-codex、AGENTS.md、controller discussion Topic 2/9、remediation-plan、plan-entry adjudication、plan-review-controller-adjudication、当前 HEAD 14个源文件代码事实
- **verdict**: **pass-with-risks** — DR-01..04 全部 closed-in-plan，无 blocker，两个低风险 open question 待 implementation 前收敛
- **生成时间**: `20260714-223617`

---

## 1. `R02-S1-DR-01` — 四文件 S1 allowlist 漏项 — **closed**

**closure 证据**: plan §0/§1.5/§3/§6.1-6.5/§8.1-8.4/§14/§15/§17 均列出四文件精确 S1 授权边界。fix-codex §3 DR-01 逐项写回。四文件均已在 R02 总 production/test allowlist（remediation-plan §7.4），drift 只修正 slice 时序。

**代码事实验证**:
- `web_fetch_orchestrator.py`: import `WebResourceBudget`；6个函数签名含 `resource_budget: WebResourceBudget`；`_probe_content_type` 有 budget 参数但函数体不读取
- `web_playwright_backend.py`: import `WebResourceBudget`；`_WorkerKwargs`/`_PlaywrightWorkerProtocol` 含单一 `resource_budget` 字段；`allows_private_network` 前置 return 存在
- `utils/diagnose_web_access.py`: import `WebResourceBudget`；`_DIAGNOSTIC_RESOURCE_BUDGET = WebResourceBudget()`；`_DEFAULT_DIAGNOSTIC_ERROR_CHARS=1_024`；`--max-network default=80`；`_StorageStateLifecycle` 存在
- `test_diagnose_web_access.py`: import `WebResourceBudget`；`WebResourceBudget(decoded_body_bytes=4)` 构造

四文件代码事实与 plan 声称的 type-only 迁移目标完全匹配。无第五个遗漏文件。

---

## 2. `R02-S1-DR-02` — child type/参数/payload owner map — **closed**

**closure 证据**: plan §4.2 冻结 `HttpResourceBudget`/`BrowserResourceBudget`/`DiagnosticResourceBudget`/`WebResourceBudgets` 四个 frozen dataclass、typed default constants 与精确 nested parser。§8.2 逐文件步骤、§8.3 owner tests、§9.4 S2 步骤、§15.4 completion 项均同步。

**关键 owner map 验证**:

| owner type | S1 consumers | 代码事实匹配 |
|---|---|---|
| `HttpResourceBudget` | fetch body/search body/diagnostic response body | `_materialize_response_body`/`_read_limited_response_body`/`_decompress_limited_response_body`/search `_materialize_bounded_search_response`/`_read_bounded_playwright_response_body` 均只读 `wire_body_bytes`/`decoded_body_bytes` ✓ |
| `BrowserResourceBudget` | warmup/DOM/text/markdown/worker callable | `_warmup_domain` 读 `warmup_body_bytes`；`_read_budgeted_dom_metrics` 读 `browser_dom_chars`/`browser_text_chars`；`_PlaywrightWorkerProtocol` 接单一 budget ✓ |
| `DiagnosticResourceBudget` | process failure/diagnostics v2 | `_playwright_process_entry` 读 `diagnostic_error_chars` ✓ |
| no budget | `_probe_content_type` | 当前签名有 `resource_budget` 但函数体不读取；plan 删除该参数 ✓ |

**aggregate 唯一性**: `WebResourceBudgets` 只停留在 `WebToolsConfig`（§4.2/§8.2），由 `web_tools.py` 唯一 projection point 拆分。下游不接 aggregate。

**worker/process payload 拆分**: `_WorkerKwargs` 当前有单一 `resource_budget`。plan 要求拆为 `BrowserResourceBudget` 在 worker kwargs、`DiagnosticResourceBudget` 在 process wrapper。§4.2/§8.2/§8.3 一致。

---

## 3. `R02-S1-DR-03` — utility defaults 时序 — **closed（narrowed-accept）**

**closure 证据**: plan §4.2/§4.4/§5/§6/§8/§10/§12/§14/§15/§17 统一写明时序。

**时序验证**:

| item | S1 | S3 | 一致性 |
|---|---|---|---|
| `DEFAULT_HTTP_RESOURCE_BUDGET` | utility 直接引用 owner typed constant | 同上 | ✓ |
| `DEFAULT_BROWSER_RESOURCE_BUDGET` | utility 直接引用 owner typed constant | 同上 | ✓ |
| `_DEFAULT_DIAGNOSTIC_ERROR_CHARS=1_024` | 保持不变 | 由 `DiagnosticResourceBudget.error_chars` 同源替换 | ✓ |
| `--max-network default=80` | 保持不变 | 由 `DiagnosticResourceBudget.events` 同源替换 | ✓ |

**无扩散验证**: plan §8.4 第三条 scan 确认 `1_024/default=80` 在 S1 只存在于 utility 既有位置且未扩散到新 producer。§10.3/§10.4 S3 scan 要求 utility-local diagnostic defaults 零残留。

**关键约束**: utility HTTP/Browser defaults 必须直接复用 owner typed constants（§4.2），不得调用 `HttpResourceBudget()`/`BrowserResourceBudget()` 隐式取默认或复制数值。当前 `_DIAGNOSTIC_RESOURCE_BUDGET = WebResourceBudget()` 构造调用将被删除。

---

## 4. `R02-S1-DR-04` — tests/validation 闭集 — **closed**

**closure 证据**: plan §6.2/§6.5/§7/§8.3-8.4/§14/§15.4/§17 统一写明。

| 验证项 | plan 位置 | 状态 |
|---|---|---|
| diagnostic direct budget node | §8.4 第一条 pytest | ✓ |
| `dayu tests utils` 旧类型 scan 零残留 | §8.4 第一条 `rg` | ✓ |
| `web_fetch_orchestrator.py`/`web_playwright_backend.py` coverage 候选 | §14.1 S1 候选表 | ✓ |
| utils 免 coverage 但 direct behavior test | §8.4/§14.1 | ✓ |
| 完整 pyright 覆盖 `dayu/tests/utils` | §14.2/§15.4 | ✓ |

---

## 5. 九文件直接 consumer 闭集完整性

代码审计确认九文件闭集与 plan §6.1/§6.5/fix-codex §2 完全一致：

| 文件 | 旧符号命中 | S1 行为 |
|---|---|---|
| `web_resource_budget.py` | owner | 删除旧 class，新建四个 frozen types |
| `provider.py` | parser | nested typed defaults/parser |
| `web_tools.py` | 13处引用 | aggregate 只在 config snapshot，拆分 child projection |
| `web_search_providers.py` | 6处引用 | 改接 `HttpResourceBudget` |
| `web_fetch_orchestrator.py` | 7处引用 | **drift 前移**：type-only HTTP/Browser split |
| `web_playwright_backend.py` | 7处引用 | **drift 前移**：type-only Browser/Diagnostic split |
| `utils/diagnose_web_access.py` | 4处引用 | **drift 前移**：type-only HTTP/Browser split |
| `test_web_tools_provider.py` | 26处引用 | 同步 helpers/fakes/workers |
| `test_diagnose_web_access.py` | 2处引用 | **drift 前移**：import + 一个 test |

无遗漏。`web_diagnostics.py` 不 import `WebResourceBudget`，不在九文件闭集内。

---

## 6. 四文件 S1 type-only 边界可执行性

**可执行**: 四文件的 S1 授权严格限于 import/annotation/parameter name/docstring/typed forwarding。以下行为不变量在 plan §8.2/§8.3/§4.4/§6.5 中明确冻结：
- `_send_authorized_request` 签名/pinned/no-proxy
- search provider 三个模块级 `requests.get/post`
- `allows_private_network` 前置 return / Playwright import / process start
- diagnostic lifecycle/CLI/writer/profile

---

## 7. S2/S3/Issue178/R03 scope leakage 检查

**无 leakage**:
- §8.2/§8.3: S1 sender 保持 pinned/no-proxy；search raw requests 不变；browser/private coupling 不变
- §4.4/§5/§10: S3 lifecycle/CLI 删除不提前
- §0/§5.3/§16: Issue 178/R03/统一 authorization 明确非目标
- §15.3: stop conditions 覆盖所有 scope breach 场景

---

## 8. 新发现

### 8.1 [低风险] "type-only" 标签对 S1 整体范围的描述过度简化

- **位置**: §8.1、§8.2、fix-codex §4
- **问题类型**: 描述精度
- **当前写法**: plan 反复称 S1 为"config owner 与 typed policy split"，drift fix 强调四文件"只做 type-only"
- **反例**: `web_egress_policy.py`（非 drift 文件、S1 原有成员）在 S1 新增独立 `allow_custom_port` 字段，是行为变更而非类型变更。`web_http_session.py` 新增 `WebHttpTransportPolicy` frozen class。`provider.py` 新增 nested parser 逻辑。S1 不是纯 type-only
- **为什么有问题**: 对 implementation agent 可能造成边界困惑：drift 文件确实是 type-only，但 S1 整体包含行为变更
- **直接影响**: 低。drift 文件的 type-only 约束在 §8.2 逐文件步骤中足够清晰，implementation agent 按文件查表即可
- **建议**: 无需修改 plan。"type-only" 精确指的是四文件的 S1 授权边界，不是 S1 整体描述。§8.1 的"config owner 与 typed policy split"已准确覆盖 S1 全范围

### 8.2 [低风险] `web_diagnostics.py` 与 `DiagnosticResourceBudget` 的投影路径未明确

- **位置**: §4.2 S1 consumers 列表、§8.2 第7步
- **问题类型**: 契约精度
- **当前写法**: §4.2 声称 `DiagnosticResourceBudget` 的 S1 consumers 包括 "`web_diagnostics.py` 及 `web_tools.py` wrappers"
- **反例**: 代码审计确认 `web_diagnostics.py` **不 import 也不接收 `WebResourceBudget`**。它当前接收显式 `max_error_chars` 等 owner fields。plan §8.2 第7步写"diagnostics projection signatures 只接 `DiagnosticResourceBudget` 或两个显式 owner fields"
- **为什么有问题**: 若 `web_diagnostics.py` 当前不接任何 budget type，则 S1 对它可能无 diff。plan 文字暗示它需要改为接 `DiagnosticResourceBudget`，但未说明具体哪些函数签名需要改、`DiagnosticResourceBudget` 从哪里传入
- **直接影响**: 低。`web_diagnostics.py` 不在九文件直接 consumer 闭集内；即使 S1 对它无 diff，也不影响旧类型删除和 pyright 通过。§6.1 也注明"inspect-only，预期无 diff"
- **建议**: implementation 前确认 `web_diagnostics.py` 的 S1 预期 diff 是否确实为零。若是，§4.2 的 consumers 列表应修正

---

## 9. Open Questions

1. **`web_diagnostics.py` S1 diff 预期**: plan §4.2 声称它是 `DiagnosticResourceBudget` consumer，但代码不 import 任何 budget type。需确认 S1 是否需要对它做签名变更，或它只是 inspect-only
2. **`_PlaywrightFallbackKwargs` 拆分后的运行时传播**: §8.2 第6步要求拆为 `browser_resource_budget` + `diagnostic_resource_budget`。需确认 `web_tools.py` 的 `_try_playwright_fallback` 能从 `WebToolsConfig.resource_budgets` 正确提取两个 child 值并传递到 `web_playwright_backend.py` 的 `_fetch_and_convert_with_playwright`

---

## 10. 结论

**verdict: pass-with-risks**

`R02-S1-DR-01..04` 全部 closed-in-plan。九文件直接 consumer 闭集完整且与代码事实一致。四文件 type-only 边界在 §8.2 逐文件步骤中可执行。aggregate/child 与 worker/process payload owner 唯一性已冻结。utility 1024/80 时序自洽（S1 保持、S3 由 typed diagnostic config 删除）。tests/coverage/pyright/README/completion 命令一致。无 S2 transport/browser、S3 lifecycle、Issue 178、R03 或统一 authorization scope leakage。

两个低风险 open question 不阻塞 plan acceptance，但应在 implementation entry 前由 controller 确认。
