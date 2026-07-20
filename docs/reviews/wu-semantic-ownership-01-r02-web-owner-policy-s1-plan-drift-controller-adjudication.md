# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 plan/slice allowlist drift — Controller adjudication

## 1. 身份与证据真源

- 本文裁决既有 umbrella `WU-SEMANTIC-OWNERSHIP-01` 内部 R02-S1 implementation entry 发现的 plan/slice allowlist drift；不是新 WU、feature、issue 或 implementation。
- 已接受但被本次直接代码证据 supersede 的 plan commit 是 `6e2a76b3`；当前 base 是 `4d2df703`。
- 直接 evidence artifact 是 `docs/reviews/wu-semantic-ownership-01-r02-web-owner-policy-s1-plan-drift-codex.md`。
- Controller 独立复核了全仓 `WebResourceBudget` 九文件直接引用闭集、相关函数签名/field reads、`pyrightconfig.json` 的 `dayu/tests/utils` include 与 accepted plan §4/§6/§8/§14/§15。
- 裁决优先保持 controller discussion Topic 2：Web resource budgets 必须由 HTTP/browser/diagnostics owner 拆分、可配置并同源；不得靠旧七字段 bag、兼容 facade、下游 fallback 或第二套默认值补救。

## 2. Root cause 与 stop 判定

Accepted plan 同时要求：

1. S1 删除 `WebResourceBudget`，所有 consumer 同步迁移，旧符号零残留；
2. 不允许旧/new dual schema、alias、flattened property 或 compatibility facade；
3. S1 changed-file allowlist 却遗漏四个直接 consumer：
   - `dayu/tools/web/web_fetch_orchestrator.py`
   - `dayu/tools/web/web_playwright_backend.py`
   - `utils/diagnose_web_access.py`
   - `tests/tools/web/test_diagnose_web_access.py`

前两个被错误地只排到 S2，后两个被错误地只排到 S3。删除 owner type 后，这些顶层 import、annotations、worker payload 和 direct test constructor 会立即破坏模块导入、test collection 与完整 pyright；`pyrightconfig.json` 不能让 utility/test 留到后续 slice。

这是 accepted plan §15.3 定义的 material owner/production-test allowlist drift。AgentCodex 在零产品 diff 时停止是正确行为；不得先越界实现再用测试倒逼裁决。

## 3. Finding dispositions

### `R02-S1-DR-01` — 四文件 S1 allowlist/propagation 漏项 — `accepted`

精确把以下四文件加入 S1 changed-file allowlist：

| 文件 | S1 唯一授权 |
|---|---|
| `dayu/tools/web/web_fetch_orchestrator.py` | HTTP body helpers 改接 `HttpResourceBudget`；warmup 改接 `BrowserResourceBudget`；删除 probe 的无语义 budget 参数；只同步 annotations/names/docstrings/forwarding |
| `dayu/tools/web/web_playwright_backend.py` | DOM/text/worker 改接 `BrowserResourceBudget`；process/failure projection 显式接 `DiagnosticResourceBudget`；拆开 worker callable kwargs 与 process diagnostic input |
| `utils/diagnose_web_access.py` | 只把旧 budget import/constant/calls 拆为 HTTP 与 Browser child owner；不改 CLI、storage lifecycle、writer、profile schema 或 browser availability |
| `tests/tools/web/test_diagnose_web_access.py` | 只迁移旧 import 与一个 direct HTTP body budget test；不改 lifecycle/storage/CLI/artifact tests |

这些文件原本已在 R02 总 production/test allowlist 中；本裁决只修正它们的 slice 时序和 S1 精确边界，不扩大 R02 product scope。

### `R02-S1-DR-02` — child type/参数 owner 映射 — `accepted`

- `WebResourceBudgets` aggregate 只允许停留在 `WebToolsConfig` immutable snapshot；下游不接 aggregate。
- HTTP wire/decoded materialization、search provider body、diagnostic Playwright response body只接 `HttpResourceBudget`。
- HTTP warmup、browser DOM/text/markdown与 browser worker只接 `BrowserResourceBudget`。
- browser process/failure diagnostic projection只接 `DiagnosticResourceBudget`或其显式 `error_chars`。
- `_probe_content_type` 不读取 budget，删除该参数；不能为了接口对称保留无语义输入。
- worker callable kwargs 不能夹带 worker 不消费的 diagnostic budget；process wrapper 必须拥有独立显式 diagnostic input并精确构造 worker kwargs。

### `R02-S1-DR-03` — utility defaults 时序 — `narrowed-accepted`

- S1 为删除旧类型而需要的 utility HTTP/Browser defaults 必须复用 `web_resource_budget.py` owner 暴露的 typed default constants；不得在 utility 重新写数值或通过 `HttpResourceBudget()`/`BrowserResourceBudget()` 隐式建立第二套默认 source。
- `utils/diagnose_web_access.py` 当前独立 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1024` 与 `--max-network=80` 不属于旧类型直接引用，本 S1 不修改其行为。
- 修订 plan 必须明确：S3 在 diagnostic utility 消费 typed Web config 时，删除这两个 utility-local diagnostic defaults，分别由 `DiagnosticResourceBudget.error_chars/events` 同源提供，并更新相应 CLI/profile/tests/README；S3 仍不得触碰 credential lifecycle 以外的普通 writer contract。
- Product Web path 在 S1 已通过 `DiagnosticResourceBudget` 使用冻结的 8192/512；utility 的旧 1024/80 只作为 S1→S3 的已登记临时状态，不得扩散到新 producer或被描述为最终 contract。

### `R02-S1-DR-04` — tests/validation 漏项 — `accepted`

- S1 targeted/full test matrix增加 `tests/tools/web/test_diagnose_web_access.py` 的 direct budget node；不得把整份 S3 lifecycle suite提前重写。
- S1 source scan必须覆盖 `dayu tests utils` 并要求 `WebResourceBudget` 零残留。
- S1 coverage候选增加实际有 diff 的 `web_fetch_orchestrator.py` 与 `web_playwright_backend.py`，仍逐 changed production file `>=80%`；`utils/**` 继续按 AGENTS.md免 coverage但必须有 direct behavior test。
- 完整 pyright继续包含 `dayu/tests/utils`，不得 skip/exclude。

## 4. 明确禁止的路径

- 不保留 `WebResourceBudget` alias/re-export/facade、flattened properties或旧/new dual schema。
- 不给任何新参数 compatibility default，不用 `**kwargs`、loose fake或测试 shim掩盖签名。
- 不在 S1 修改 `_send_authorized_request` 签名或 pinned/no-proxy行为。
- 不迁移 `web_search_providers.py` 的 raw `requests.get/post`；不做 proxy、peer-proof、warning或 fixed-endpoint transport行为。
- 不删除 browser/private coupling，不做 `browser_enabled` gate、`browser_peer_proof_unavailable`、proxy env或 route/navigation行为；这些仍归 S2。
- 不在 S1 删除 storage-state lifecycle/CLI、修改 ordinary writer或实现 Issue 178；这些仍归 S3/future Issue owner。
- 不进入 R03、统一 tool authorization framework或其它 deferred Issue。

## 5. Required plan gate recovery

当前 accepted plan commit `6e2a76b3` 保留为历史证据，但不再是可直接执行的 S1 truth。必须依次完成：

1. AgentCodex只修订现有 R02 plan，把 `R02-S1-DR-01..04` 写入 §4、§6、§8、§10、§14、§15/§17，并写 plan-drift fix artifact；
2. AgentMiMo/AgentDS对修订后的完整 plan 与全部 review/drift链做双路完整 re-review；
3. Controller裁决所有新 finding；accepted finding若存在，继续 fix + 完整 re-review；
4. 无 accepted finding后创建新的 superseding accepted-plan local commit；
5. Controller再单独切入 R02-S1 implementation。

修 plan/re-review期间不授权任何 product/test/README implementation diff。
