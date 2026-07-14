# WU-SEMANTIC-OWNERSHIP-01 / R02-S1 plan drift 第二路完整 re-review — DS

## 1. 身份、范围与裁决真源

- **umbrella**: 既有 `WU-SEMANTIC-OWNERSHIP-01`；内部 remediation sub-WU: 既有 `R02`。
- **本轮身份**: 对 R02-S1 plan drift fix 的第二路完整 adversarial re-review；不是新 WU、feature、issue 或 implementation。
- **review target**: `docs/host/wu-semantic-ownership-01-r02-web-owner-policy-plan.md`（947 行最终修订版）。
- **review base**: 分支 `phaseflow/host-issues-control`，plan-time HEAD `02fcc5d8`；当前工作区 HEAD `4d2df703`。
- **full chain consumed**:
  - 原 plan-entry: 上述 plan（完整 947 行）。
  - 原 plan review: `...-plan-review-mimo.md`、`...-plan-review-ds.md`（历史 reference，不重新裁决）。
  - 原 controller adjudication: `...-plan-review-controller-adjudication.md`、`...-plan-rereview-controller-adjudication.md`（历史 disposition 不覆盖本次 drift）。
  - S1 drift evidence: `...-s1-plan-drift-codex.md`。
  - S1 drift controller adjudication: `...-s1-plan-drift-controller-adjudication.md`（**`R02-S1-DR-01..04` 唯一裁决真源**）。
  - S1 drift fix: `...-s1-plan-drift-fix-codex.md`。
  - 设计真源: `docs/host/design.md`、`docs/engine/design.md`、`docs/tool/design.md`、`docs/fins/design.md`、`docs/ui/design.md`。
  - Controller discussion: `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`（Topic 2、Topic 9）。
  - 项目约束: `AGENTS.md`、`CLAUDE.md`。
  - 当前代码: HEAD `4d2df703` 的 `dayu/tools/web/`、`utils/diagnose_web_access.py`、`tests/`、`pyrightconfig.json`。
- **不重开**: `R02-B01/B02`（plan-entry adjudication）、`R02-PF-01..10`（原 plan review adjudication）、`R02-RR-F01`（原 re-review）、Topic 2/Topic 9 controller discussion 的产品裁决、历史 reviewer 建议。
- **写唯一 artifact**: 本文。不修改 plan、control、产品、测试、README、其它 artifact；不 commit。
- **生成时间**: `2026-07-14 22:34:10 +0800`（本机系统时钟）。
- **结论预览**: **PASS-WITH-OBSERVATIONS** — 四项 drift finding 全部闭合；无 material blocker；两条 minor implementation observations 与一条 residual risk note。

## 2. Review posture 与假设

### 2.1 关键假设

| # | 假设 | 验证方式 |
|---|---|---|
| A1 | 九文件 `WebResourceBudget` 直接引用闭集完整，无遗漏 consumer | `rg -l '\bWebResourceBudget\b' dayu tests utils` 全仓扫描 |
| A2 | 四文件 drift consumer 确实直接 import/annotate/construct 旧类型 | 逐文件 `rg -n` 审计 |
| A3 | `pyrightconfig.json` 的 `include: ["dayu", "tests", "utils"]` 使 utility/test 不能延迟 | 直接读取 pyrightconfig.json |
| A4 | S1 不改变 sender pinned/no-proxy、search raw requests、browser/private coupling、diagnostic lifecycle/CLI | 逐文件 plan §8.2 边界说明 vs 当前代码行为 |
| A5 | S1 type-only 边界对 implementation agent 可执行 | 逐文件 plan 指令 vs 当前代码签名/调用链 |
| A6 | utility `1_024/80` 在 S1 是独立常量，不依赖 `WebResourceBudget` | 当前代码直接审计 |
| A7 | Controller 裁决不可被历史 reviewer 建议覆盖 | §1.1 优先级表格 |

### 2.2 自证覆盖范围

本次 re-review 的 adversarial 检查面：

- [x] 九文件直接 consumer 闭集完整性
- [x] 四文件 S1 type-only 边界可执行性
- [x] aggregate/child 与 worker/process payload owner 唯一性
- [x] utility 1024/80 S1 保留/S3 删除时序自洽性
- [x] 测试/coverage/pyright/README/completion 命令充分性
- [x] S2 transport/browser、S3 lifecycle、Issue 178、R03、统一 authorization 偷带检查
- [x] plan §0-§17 内部一致性（DR-01..04 在所有相关章节的传播）
- [x] 非 allowlist 测试的静默断裂风险

## 3. DR-01 至 DR-04 逐项闭合验证

### 3.1 `R02-S1-DR-01` — 四文件 S1 allowlist/propagation 漏项

**Controller 裁决**: 精确把四个文件加入 S1 changed-file allowlist，S1 只授权 type-only migration。

**Plan 写回位置**: §0（gate 状态）、§1.5（drift evidence 表）、§3.2（owner/contract 判定）、§6.1-6.5（闭集与 slice 时序）、§8.1-8.3（S1 逐文件步骤）、§14.1（coverage 候选）、§15.2-15.4（状态机/completion）、§17（完成信号）。

**直接代码证据**（HEAD `4d2df703`）:
```
dayu/tools/web/web_fetch_orchestrator.py:52:  from .web_resource_budget import WebResourceBudget
dayu/tools/web/web_fetch_orchestrator.py:666:  resource_budget: WebResourceBudget,  (+5 more signatures)
dayu/tools/web/web_playwright_backend.py:39:  from .web_resource_budget import WebResourceBudget
dayu/tools/web/web_playwright_backend.py:201:  resource_budget: WebResourceBudget  (+6 more signatures)
utils/diagnose_web_access.py:55:         from dayu.tools.web.web_resource_budget import WebResourceBudget
utils/diagnose_web_access.py:119:        _DIAGNOSTIC_RESOURCE_BUDGET: Final[WebResourceBudget] = WebResourceBudget()
utils/diagnose_web_access.py:2295:       resource_budget: WebResourceBudget,
tests/tools/web/test_diagnose_web_access.py:29:  from dayu.tools.web.web_resource_budget import WebResourceBudget
tests/tools/web/test_diagnose_web_access.py:747: budget = WebResourceBudget(decoded_body_bytes=4)
```

**Plan S1 边界**: 每个文件的 S1 授权精确且互不重叠：

| 文件 | S1 授权 | 禁止 |
|---|---|---|
| `web_fetch_orchestrator.py` | HTTP body→`HttpResourceBudget`; warmup→`BrowserResourceBudget`; probe 删 budget 参数; 只改 import/annotation/name/docstring/forwarding | `_send_authorized_request` 签名/行为、numeric pin、no-proxy、redirect、mixed DNS、body materialization |
| `web_playwright_backend.py` | DOM/text/worker→`BrowserResourceBudget`; process→`DiagnosticResourceBudget`; 拆 worker kwargs/process diagnostic input | `allows_private_network` 前置 return、Playwright import/process start、browser availability、proxy env、route/nav |
| `utils/diagnose_web_access.py` | 旧 budget import/constant/calls 拆为 HTTP+Browser child owner; 复用 owner typed defaults | CLI、lifecycle、writer、profile schema、browser availability |
| `test_diagnose_web_access.py` | 旧 import→`HttpResourceBudget`; 一个 direct budget test 输入改为 `HttpResourceBudget(wire_body_bytes=4, decoded_body_bytes=4)` | 其它 lifecycle/storage/CLI/artifact tests |

**验证**: DR-01 在 plan 所有相关章节中均已完整传播。§17 完成信号中明确列出四项闭合条件。四文件各自在 §8.2 items 9-12 有精确逐文件/逐符号指令。**CLOSED**。

### 3.2 `R02-S1-DR-02` — child type、参数与 worker/process payload owner map

**Controller 裁决**: aggregate 只允许停留在 `WebToolsConfig`；HTTP/Browser/Diagnostic 显式分发；probe 删无语义参数；worker kwargs 不含 diagnostic budget。

**Plan 写回位置**: §4.2（owner map 表格 + aggregate/child/worker/process 契约）、§8.2 items 2/6/9/10（逐文件实施）、§8.3（owner tests）、§9.4（S2 保留已拆 payload）、§15.4（completion 必填项）。

**当前代码违反**:
- `_WorkerKwargs` (web_playwright_backend.py:192-201): `resource_budget: WebResourceBudget` 同时被 browser DOM/text producer 与 diagnostic error projection（line 524: `max_error_chars = worker_kwargs["resource_budget"].diagnostic_error_chars`）消费 → **一个 bag 代签两个 owner**。
- `_PlaywrightFallbackKwargs` (web_tools.py:224-235): `resource_budget: WebResourceBudget` 单一字段。
- `_StageFetchKwargs` (web_tools.py:238-248): warmup 与 probe 共用 `resource_budget`。
- `_FetchConvertKwargs` (web_tools.py:251-262): 单一 `resource_budget`。

**Plan 目标 owner map**:

| owner type | 精确消费方 | 不消费方 |
|---|---|---|
| `HttpResourceBudget` | fetch body、search provider body、diagnostic Playwright response body | browser DOM/text、warmup、diagnostic error/events |
| `BrowserResourceBudget` | warmup、browser DOM/text/markdown、worker callable | HTTP wire/decoded、diagnostic error projection |
| `DiagnosticResourceBudget` | browser process/failure projection、diagnostics v2 | HTTP body、browser DOM/text |
| 无 budget | `_probe_content_type` | — |

**Worker/process 拆分**: worker callable kwargs 只含 `BrowserResourceBudget`；process wrapper 另有独立 `DiagnosticResourceBudget` input 并逐字段构造 worker kwargs。`web_playwright_backend.py:524` (`max_error_chars = worker_kwargs["resource_budget"].diagnostic_error_chars`) 在 `_playwright_process_entry` 中——plan 要求该函数显式接 `DiagnosticResourceBudget`，不再从 worker kwargs 读取。

**验证**: owner map 唯一，无歧义。aggregate → child → worker/process 的投影链从 `WebToolsConfig`（唯一 projection point `web_tools.py`）到各 executor 是单向、无环、无重叠的。**CLOSED**。

### 3.3 `R02-S1-DR-03` — utility defaults 时序

**Controller 裁决 (narrowed-accepted)**: S1 utility HTTP/Browser defaults 复用 owner typed constants；S1 保留 `1_024/default=80`；S3 由 typed diagnostic config 删除并同源替换。

**Plan 写回位置**: §4.2（三个 typed default constants）、§4.4（S1 临时时序例外 + S3 删除契约）、§5.2（保留项明确列出）、§6.5（DR-03 裁决表）、§8.2 item 11（utility S1 实施）、§8.4（S1 scan 命令确认 `1_024/default=80` 保持且未扩散）、§10.1/10.3（S3 删除与同源替换）、§10.4（S3 scan 命令确认零残留）、§14.3（aggregate scan 命令覆盖 S1→S3 全时序）。

**当前代码证据**:
```
utils/diagnose_web_access.py:83:  _DEFAULT_DIAGNOSTIC_ERROR_CHARS: Final[int] = 1_024
utils/diagnose_web_access.py:1213: parser.add_argument("--max-network", type=int, default=80, ...)
dayu/tools/web/web_resource_budget.py:43: diagnostic_error_chars: int = 1_024  (旧 WebResourceBudget 默认)
```

关键事实:
- `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 是独立常量（不读取 `WebResourceBudget().diagnostic_error_chars`），删除 `WebResourceBudget` 类不会破坏它。
- 数值 `1024` 恰好与旧 `WebResourceBudget.diagnostic_error_chars` 默认相同，但这是历史巧合，不是依赖关系。
- 旧 `WebResourceBudget.diagnostic_events` 默认 `80` 与 `--max-network default=80` 数值相同，同样是历史巧合。

**时序自洽性**:

| 阶段 | `_DEFAULT_DIAGNOSTIC_ERROR_CHARS` | `--max-network default=80` | HTTP/Browser utility defaults |
|---|---|---|---|
| S1 | 保持独立常量 `=1_024` | 保持 `default=80` | 复用 `DEFAULT_HTTP_RESOURCE_BUDGET` / `DEFAULT_BROWSER_RESOURCE_BUDGET` |
| S3 | 删除；从 `DiagnosticResourceBudget.error_chars` 同源 | 删除 `default=80`；未提供态→typed config `events` | 不变（已在 S1 正源） |

**S1→S3 过渡的语义变更**: utility diagnostic error chars 从 `1_024` 变为 `8_192`（冻结值），events 从 `80` 变为 `512`。这是 controller 已冻结的数值变更，已登记为 §4.4 的显式时序。**CLOSED**。

### 3.4 `R02-S1-DR-04` — tests/validation 漏项

**Controller 裁决**: S1 test matrix 增加 diagnostic direct budget node；旧类型 scan 覆盖 `dayu tests utils`；coverage 候选增加 `web_fetch_orchestrator.py` 与 `web_playwright_backend.py`；utils coverage exemption + direct behavior test；完整 pyright 覆盖 `dayu/tests/utils`。

**Plan 写回位置**: §6.2-6.5（tests/docs 闭集）、§7（umbrella baseline 逐项映射）、§8.3 item 12（tests 逐项）、§8.4（S1 gate commands + scan commands）、§14.1（per-file coverage）、§14.3（source/propagation scans）、§15.4（completion 必填项 8-10）、§17（完成信号）。

**S1 gate commands 审计**:

1. **Targeted tests** (§8.4): 三组 pytest 命令覆盖 `test_web_tools_provider.py`（targeted + full）、`test_config_loader.py`、`test_diagnose_web_access.py` 的 direct budget node。Full `test_web_tools_provider.py` 运行（无 `-k` filter）覆盖 `web_fetch_orchestrator.py` 和 `web_playwright_backend.py` 的 exercised code paths。

2. **Coverage** (§8.4, §14.1): 逐 changed production file `>=80%`，不是 aggregate `--fail-under`。S1 候选显式列出 `web_fetch_orchestrator.py` 与 `web_playwright_backend.py`。命令使用 `coverage report --include='<exact-file>' --fail-under=80`。

3. **Source scans** (§8.4): 三条 `rg` 命令：
   - `\bWebResourceBudget\b|max_wire_body_bytes|...` 覆盖 `dayu tests utils`（全仓旧类型/旧字段零残留）
   - 旧数值 scan 覆盖 config + production + tests（`1024` 与 `1000000` 要求逐条归属）
   - utility transitional diagnostics scan（确认 `1_024/default=80` 保持且未扩散）

4. **pyright** (§8.4): `python -m pyright` 覆盖全仓，不 skip/exclude。

5. **Completion** (§15.4): 15 个必填项，其中 item 8-10 要求逐 slice pytest 结果（S1 单列 diagnostic direct budget node）、逐文件 coverage 百分比（S1 含两个新增 candidate）、全量 pyright 结果。

**验证**: 所有 validation gate 均可直接执行。Coverage 命令使用具体文件名而非通配符。Scan 命令覆盖正确的目录范围。**CLOSED**。

## 4. 专项 adversarial 检查

### 4.1 九文件直接 consumer 闭集完整性

**方法**: `rg -l '\bWebResourceBudget\b' dayu tests utils | sort`

**结果**（HEAD `4d2df703`）:
```
dayu/tools/web/provider.py
dayu/tools/web/web_fetch_orchestrator.py
dayu/tools/web/web_playwright_backend.py
dayu/tools/web/web_resource_budget.py
dayu/tools/web/web_search_providers.py
dayu/tools/web/web_tools.py
tests/tools/web/test_diagnose_web_access.py
tests/tools/web/test_web_tools_provider.py
utils/diagnose_web_access.py
```

**交叉验证**: `rg -l 'from.*web_resource_budget import|import.*web_resource_budget' dayu tests utils | sort` 返回相同的 8 个 importer（`web_resource_budget.py` 自身不 import 自己），与 9 文件闭集一致。

**`web_diagnostics.py`**: 零命中 `WebResourceBudget` 或 `resource_budget`。Plan 的判定"该文件不在 R02 allowlist 且预期无 diff"正确。

**结论**: 九文件闭集完整。无遗漏 consumer。无间接 import 链路需要额外追踪。**PASS**。

### 4.2 四文件 S1 type-only 边界可执行性

逐文件检查 plan §8.2 指令是否对 implementation agent 可执行：

**`web_fetch_orchestrator.py`** (§8.2 item 9):
- 指令: import→`HttpResourceBudget`/`BrowserResourceBudget`；annotation→对应 child type；parameter name 收窄；docstring 更新；forwarding 同步；probe 删 budget 参数。
- 当前代码: 6 个函数签名含 `resource_budget: WebResourceBudget`。`_warmup_domain` 读 `warmup_body_bytes`（→`BrowserResourceBudget.warmup_body_bytes`，字段名不变）。`_probe_content_type` 接收但不读取 budget（line 1343 的 docstring 明确说"不消费其 body budget"）。
- 可执行性: **清晰可执行**。字段名在 child type 中保留（`wire_body_bytes`、`decoded_body_bytes`、`warmup_body_bytes`），body materialization 算法不需要改动。

**`web_playwright_backend.py`** (§8.2 item 10):
- 指令: DOM/text/markdown/worker→`BrowserResourceBudget`；process/failure→`DiagnosticResourceBudget`；拆 worker kwargs 与 process diagnostic input。
- 当前代码: `_WorkerKwargs` 含 `resource_budget`，`_playwright_process_entry:524` 从中读 `diagnostic_error_chars`。`_run_playwright_worker_process` 传 `worker_kwargs` 给 process entry。
- 可执行性: **清晰可执行**。拆分路径明确：`_WorkerKwargs.resource_budget`→`browser_resource_budget: BrowserResourceBudget`；`_playwright_process_entry` 新增 `diagnostic_budget: DiagnosticResourceBudget` 参数；`_run_playwright_worker_process` 新增 `diagnostic_budget` 参数并传给 process entry。worker kwargs 不再夹带 diagnostic budget。

**`utils/diagnose_web_access.py`** (§8.2 item 11):
- 指令: import/constant/calls 拆为 HTTP + Browser child owner；HTTP/Browser 常量分别引用 `DEFAULT_HTTP_RESOURCE_BUDGET` / `DEFAULT_BROWSER_RESOURCE_BUDGET`；不改 CLI/lifecycle/writer/profile。
- 当前代码: `_DIAGNOSTIC_RESOURCE_BUDGET: Final[WebResourceBudget] = WebResourceBudget()` 用于三条路径（requests response、Playwright DOM/text、`_read_bounded_playwright_response_body`）。
- 可执行性: **清晰可执行**。拆为两个 `Final` 常量：`_DIAGNOSTIC_HTTP_BUDGET`（引 `DEFAULT_HTTP_RESOURCE_BUDGET`）与 `_DIAGNOSTIC_BROWSER_BUDGET`（引 `DEFAULT_BROWSER_RESOURCE_BUDGET`）。三条消费路径各取所需。

**`test_diagnose_web_access.py`** (§8.2 item 12):
- 指令: import→`HttpResourceBudget`；一个 test 的 `WebResourceBudget(decoded_body_bytes=4)`→`HttpResourceBudget(wire_body_bytes=4, decoded_body_bytes=4)`。
- 可执行性: **清晰可执行**。单行变更。

**Observations**:

- **OBS-01 (LOW)**: `_StageFetchKwargs` 拆解方式未逐行指定。plan §8.2 item 6 说"`_StageFetchKwargs`不再让warmup/probe共用budget"，但当前 `_fetch_web_page_business` (web_tools.py:1978-2012) 分别构造 `warmup_kwargs` 和 `probe_kwargs` 均为 `_StageFetchKwargs` 类型并通过 `**kwargs` 解包。S1 后 `_StageFetchKwargs` 含 `browser_resource_budget`，而 `_probe_content_type` 删除了 budget 参数——Python 会对 `**probe_kwargs` 中的 `browser_resource_budget` 抛出 `TypeError: unexpected keyword argument`。Implementation agent 需将 probe 调用改为显式传参（不传 budget field）而非 `**kwargs` 解包。plan 意图明确（probe 不接 budget），implementation agent 可自行选择最简路径。**建议**: 不修改 plan。

- **OBS-02 (LOW)**: `_playwright_process_entry` 当前从 `worker_kwargs["resource_budget"].diagnostic_error_chars` 读取诊断预算（line 524），拆分为独立 `DiagnosticResourceBudget` 参数后，需同时修改 `_run_playwright_worker_process` 的签名和调用链（当前 line 805 传 `args=(result_queue, playwright_sync_worker, worker_kwargs)`，需增加 diagnostic budget 参数）。plan 已覆盖此点（§8.2 item 10: "process wrapper另有独立diagnostic input并精确构造worker kwargs"）。**建议**: 不修改 plan。

### 4.3 aggregate/child 与 worker/process payload owner 唯一性

**owner 链验证**:

```
ConfigLoader (record replacement, 不变)
  → provider._parse_config (唯一 raw parser owner)
    → WebToolsConfig (immutable snapshot)
      → WebEgressPolicy(private, custom-port)
      → WebHttpTransportPolicy(proof, proxy)     [S1 构造但不 thread 到 sender]
      → browser_enabled: bool
      → WebResourceBudgets(http, browser, diagnostics)  [aggregate, 无 default, 无 validator]
        → HttpResourceBudget(wire_body_bytes, decoded_body_bytes)
        → BrowserResourceBudget(warmup_body_bytes, dom_chars, text_chars)
        → DiagnosticResourceBudget(error_chars, events)
```

**唯一 projection point** (§8.2 item 6): `web_tools.py` 的 `_search_web_business` 只传 `config.resource_budgets.http`；`_fetch_web_page_business` 分发 warmup=`browser`、probe=无、fetch=`http`、browser fallback=`browser + diagnostics`。

**worker/process payload 拆分**: worker callable kwargs→只含 `BrowserResourceBudget`；process wrapper→独立 `DiagnosticResourceBudget`。两者不重叠。

**验证**: 每个 child type 有唯一 consumer 集合；不存在两个 consumer 各自从 raw config 重建同一 child value；worker kwargs 不含 diagnostic budget。**PASS**。

### 4.4 utility 1024/80 S1 保留/S3 删除时序自洽性

**S1 状态** (§4.4, §8.2 item 11):
- `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024` 保留，不改值，不扩散。
- `--max-network default=80` 保留，不改值，不扩散。
- 新增 HTTP/Browser utility defaults 分别引用 `DEFAULT_HTTP_RESOURCE_BUDGET` / `DEFAULT_BROWSER_RESOURCE_BUDGET`。不得调用 `HttpResourceBudget()`/`BrowserResourceBudget()` 隐式取默认。

**S3 状态** (§10.1, §10.3):
- 删除 `_DEFAULT_DIAGNOSTIC_ERROR_CHARS = 1_024`。
- 删除 `--max-network` 的 `default=80`；未提供态→typed config `DiagnosticResourceBudget.events`。
- Utility 从 typed Web config 的 `DiagnosticResourceBudget.error_chars/events` 同源取值。

**S1→S3 scan 覆盖**:

| 阶段 | scan 命令 | 预期结果 |
|---|---|---|
| S1 (§8.4) | `rg -n '_DEFAULT_DIAGNOSTIC_ERROR_CHARS\|1_024\|--max-network\|default=80' utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py` | `1_024/default=80` 存在于 utility 既有位置，未扩散 |
| S3 (§10.4) | `rg -n '_DEFAULT_DIAGNOSTIC_ERROR_CHARS\|1_024\|default=80' utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py tests/README.md dayu/config/README.md` | 零残留 |
| S3 (§10.4) | `rg -n 'DiagnosticResourceBudget\|error_chars\|events\|max_network' utils/diagnose_web_access.py tests/tools/web/test_diagnose_web_access.py dayu/config/README.md tests/README.md` | 每个符号有唯一 owner 并被 consumer 断言 |
| Aggregate (§14.3) | 同上第五条 + 第六条 | S1 artifact 记录 `1_024/default=80` 位置且未扩散；S3 零残留；typed diagnostic config 同源 |

**时序验证**: S1 scan 预期命中（保留），S3 scan 预期零命中（删除），aggregate scan 覆盖两者。S1→S3 过渡有明确的数值变更登记（1024→8192, 80→512），由 controller 冻结值驱动，不是静默行为变更。**PASS**。

### 4.5 测试/coverage/pyright/README/completion 命令充分性

**测试覆盖**:

| slice | 命令 | 覆盖范围 |
|---|---|---|
| S1 (§8.4) | `pytest ... -k 'config or resource_budget or egress_policy or provider'` + full `test_web_tools_provider.py` + `test_config_loader.py` + direct budget node | 所有 changed production files 的 exercised paths |
| S2 (§9.6) | `pytest ... -k 'private or custom_port or proxy or peer or redirect or browser or challenge'` + full `test_web_tools_provider.py` | S2 行为变更的所有 owner/security cases |
| S3 (§10.4) | targeted `-k 'diagnostic or storage_state or challenge'` + full 三份 test files | lifecycle 删除 + diagnostic v2 + typed config |
| Aggregate (§14.4) | 四份 test files 全量 + smoke | full regression + real browser |

**Coverage**: 每 slice 逐 changed production file `>=80%`（§14.1）。命令使用 `coverage report --include='<exact-file>.py' --fail-under=80`。S1 候选显式列出 `web_fetch_orchestrator.py` 与 `web_playwright_backend.py`。`utils/**` 按 AGENTS.md 免 coverage 但有 direct behavior test。

**pyright**: 每 slice + aggregate 运行 `python -m pyright`。包含 `dayu/tests/utils`。§14.2 要求 0 新增/扩散；触及旧错误必须修复。

**README**: §12 精确列出需更新文件与触发条件。根 README 预期无 diff（当前不描述 developer diagnostic CLI）。

**Completion**: §15.4 的 15 项必填项覆盖所有维度。S1 必须单列 diagnostic direct budget node 且不得声称整份 S3 lifecycle suite 已迁移。

**评估**: 所有 gate commands 是可直接复制执行的 bash 命令。Coverage 使用 per-file 而非 aggregate。pyright 无 skip/exclude。**PASS**。

### 4.6 S2/S3/Issue178/R03/统一 authorization 偷带检查

逐节扫描 plan 文本中 S1 相关章节（§4、§6、§8、§14、§15），检查是否包含仅应在 S2/S3 实施的行为描述：

| S1 章节 | 潜在偷带检查 | 结果 |
|---|---|---|
| §4.3 transport | "S1只在`WebToolsConfig` snapshot内构造并保存frozen `WebHttpTransportPolicy`，`_send_authorized_request`与所有caller仍保持当前secure pinned/no-proxy行为" | **S2 行为未偷带** |
| §4.3 browser | "`browser_enabled`...不授予 private/custom-port 权限" + "只有HTTP结果/challenge事实已经决定进入browser fallback...才检查proof-on" | **S2 行为未偷带**（描述的是 S2 终态，但 §8.2 item 10 明确 S1 不实施） |
| §6.5 DR table | "不得提前S2/S3、Issue #178、R03或统一authorization" | **显式禁止** |
| §8.2 item 5 | "S1不修改`_send_authorized_request`签名或行为" | **S2 行为未偷带** |
| §8.2 item 8 | "三个模块级`requests.get/post`...S2才迁到同一typed attempt sender。不得在S1提前混入transport行为" | **S2 行为未偷带** |
| §8.2 item 10 | "删除coupling与proof gate只在S2" | **S2 行为未偷带** |
| §8.2 item 11 | "S3按§10删除两项本地diagnostic defaults与credential lifecycle" | **S3 行为未偷带** |
| §5.3 non-goals | "统一 tool authorization framework...Issue #178...R03...新 proxy credential schema" | **显式非目标** |
| §14.3 final scan | `rg -n 'authorization framework\|policy DSL\|capability token\|storage state refresh\|storage state retention'` | **Completion scan 验证零新增** |

**验证**: 所有 S1 章节均显式声明行为冻结边界。§4.3 中某些描述读起来像终态行为（如 browser+proof 组合），但 §8.2 明确将这些行为分配到 S2。`web_search_providers.py` 的 `requests.get/post` 在 S1 逐行为保持。**PASS — 无偷带**。

### 4.7 非 allowlist 测试静默断裂风险

**范围**: 检查 `allow_private_network_url` 在 R02 test allowlist 外的出现位置。

**命中**:
- `tests/service/test_host_assembly.py:1352`: `"allow_private_network_url": True` (config dict literal)
- `tests/service/test_host_assembly.py:1751`: `"allow_private_network_url": True` (config dict literal)
- `tests/tools/test_combined_tools_acceptance.py:797`: `"allow_private_network_url": False` (config dict literal)

**分析**:
- 三个命中均**显式设值**，不依赖 packaged default。
- S1 保留 `allow_private_network_url` 字段名，仅新增 `allow_custom_port_url` 等 sibling 字段。
- 新 parser 对 final record 中缺失 field 补 typed default，已存在 sibling 不变（§4.1）。
- 这些测试不 import `WebResourceBudget`、`WebEgressPolicy` 或任何 `web_resource_budget` 符号。
- 这些测试不包含 `resource_budget` config 字段。

**结论**: 三个测试不应因 S1 变更而断裂。Plan 的 §15.3 stop condition 覆盖了"需要任何其它 production/test/README allowlist 扩展"的场景——如果实现中意外断裂，agent 必须 stop 回 controller。**PASS — residual risk note only**。

## 5. 内部一致性：DR-01..04 在 plan 全章节的传播

| plan 章节 | DR-01 传播 | DR-02 传播 | DR-03 传播 | DR-04 传播 |
|---|---|---|---|---|
| §0 gate 身份 | ✓ 四文件+type-only | ✓ aggregate/child owner | ✓ defaults 时序 | ✓ tests/validation |
| §1.5 drift evidence | ✓ 四文件表 | ✓ owner map | ✓ narrowed-accepted | ✓ validation 闭集 |
| §3 temporal audit | ✓ S1 plan-drift adjudication | — | — | — |
| §4.2 budget owner | ✓ HTTP/Browser/Diagnostic | ✓ owner map table | ✓ default constants | — |
| §4.4 diagnostics | — | — | ✓ S1 临时例外 + S3 删除 | — |
| §5.2 retain | — | — | ✓ `1_024/80` as transitional | — |
| §6.1-6.5 闭集 | ✓ 四文件 in S1 table | ✓ §6.5 DR table | ✓ §6.5 DR table | ✓ §6.5 DR table |
| §8.2 S1 逐文件 | ✓ items 9-12 | ✓ items 2/6/9/10 | ✓ item 11 | ✓ item 12 |
| §8.3 S1 owner tests | ✓ utility/diagnostic assertions | ✓ owner map assertions | ✓ defaults assertions | ✓ coverage/scans |
| §8.4 S1 gate commands | ✓ diagnostic direct node | ✓ scan commands | ✓ scan commands | ✓ scan commands |
| §10 S3 | — | — | ✓ delete + same-source | — |
| §12 README | — | — | ✓ S3 `1_024/default=80` | — |
| §14 coverage/scans | ✓ S1 candidates | ✓ aggregate scans | ✓ S1/S3 scans | ✓ per-file coverage |
| §15.4 completion | ✓ item 3 (四文件 type-only) | ✓ item 4 (owner contract) | ✓ item 5 (delete contract) | ✓ items 8-10 |
| §17 完成信号 | ✓ 四项闭合 | ✓ owner map frozen | ✓ defaults timing | ✓ validation closure |

**验证**: DR-01..04 在所有相关章节均有精确文字传播，不存在"某节只提 DR-01 不提 DR-03"的不一致。**PASS**。

## 6. Finding 汇总

### 6.1 DR-01..04 闭合状态

| Finding ID | 状态 | 证据 |
|---|---|---|
| `R02-S1-DR-01` | **CLOSED** | §3.1 — 四文件全部写回 §6/§8/§14/§15/§17，逐文件 type-only 边界精确 |
| `R02-S1-DR-02` | **CLOSED** | §3.2 — owner map 在 §4.2 冻结，aggregate/child/worker/process 单向无重叠 |
| `R02-S1-DR-03` | **CLOSED** | §3.3 — S1 保留/S3 删除时序自洽，scan 命令覆盖全时序 |
| `R02-S1-DR-04` | **CLOSED** | §3.4 — tests/coverage/pyright/scans/completion 命令均可直接执行 |

### 6.2 新 finding

**R02-S1-DRR-F01 (LOW — observation)** — `_StageFetchKwargs` 拆解后的 `**kwargs` 解包冲突

- **位置**: plan §8.2 item 6、`web_tools.py:1978-2012`
- **问题类型**: 实施细节未逐行指定
- **当前写法**: plan 说"`_StageFetchKwargs`不再让warmup/probe共用budget"，但未指定 `probe_kwargs`（含 `browser_resource_budget`）解包到不再接收 budget 参数的 `_probe_content_type` 时的具体机制
- **反例/失败场景**: implementation agent 机械地将 `_StageFetchKwargs.resource_budget` 替换为 `browser_resource_budget`，然后 `**probe_kwargs` 解包到新的 `_probe_content_type`（无 budget 参数）触发 `TypeError: unexpected keyword argument 'browser_resource_budget'`
- **为什么有问题**: plan 意图明确但 implementation agent 可能选择错误的拆解方式
- **直接证据**: 当前 `_fetch_web_page_business:1989-2012` 分别用 `**warmup_kwargs` 和 `**probe_kwargs` 解包同一 `_StageFetchKwargs` 类型；S1 后 `_probe_content_type` 不再接受 budget 参数
- **影响**: 实施 Agent 需额外判断（显式传参不用 `**kwargs`），但不改变 plan 架构
- **建议改法和验证点**: 不修改 plan。implementation agent 将 probe 调用改为显式 keyword args（不传 budget），或拆分 `_StageFetchKwargs` 为 warmup/probe 各自独立 TypedDict。S1 gate test 会立即捕获 TypeError
- **修复风险**: 低（implementation agent 自行选择最简路径）
- **严重程度**: 低

**R02-S1-DRR-F02 (LOW — residual risk note)** — 非 allowlist 测试含 Web config 字面量

- **位置**: `tests/service/test_host_assembly.py:1352,1751`、`tests/tools/test_combined_tools_acceptance.py:797`
- **问题类型**: residual risk
- **当前写法**: 这些测试构造含 `"allow_private_network_url"` 的 config dict literal，但不在 R02 test allowlist
- **反例/失败场景**: 若 S1 的 parser/config 变更意外改变 config record 的 shape（尽管 plan 说 record replacement 不变），这些测试可能静默断裂
- **为什么有问题**: 测试不在 allowlist 中，实现 agent 不会主动检查它们；S1 gate commands 不运行这些测试
- **直接证据**: `rg -n 'allow_private_network_url' tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py` 返回三处命中
- **影响**: 低——三个命中均显式设值，S1 保留字段名，parser 只对缺失 field 补 default；实际断裂概率极低。Plan §15.3 stop condition 覆盖了"需要任何其它 allowlist 扩展"的场景
- **建议改法和验证点**: 不修改 plan。S1 implementation 后建议运行全量 `pytest tests/` 一次作为 safety net（非 gate requirement）
- **修复风险**: 不适用（residual risk，非待修 defect）
- **严重程度**: 低

## 7. Open questions

无。所有 plan 边界、时序和 gate commands 均已充分定义。

## 8. Residual risks

| risk | 当前处理 | owner |
|---|---|---|
| 非 allowlist 测试含 Web config 字面量（DRR-F02） | 三处均显式设值，不应断裂；§15.3 stop condition 兜底 | Controller（若断裂则裁决 allowlist 扩展） |
| `_StageFetchKwargs` 拆解机制（DRR-F01） | implementation agent 自行选择最简路径；plan 意图明确 | Implementation agent |
| live 网站 DOM/event 规模变化 | §11.2 只记录 metrics，直接超限才 stop | Web config owner；非 R02 scope |
| proxy 下无法证明 origin peer | §16 residual table: typed fail closed | Web HTTP transport owner；非 R02 scope |
| external provider/challenge 波动 | §13.3 local hard gate + external 补充 | Web diagnostics/smoke owner |

## 9. Final plan review conclusion

**Verdict: PASS-WITH-OBSERVATIONS**

**Rationale**:

1. 四项 drift finding (`R02-S1-DR-01..04`) 均已完整闭合——plan 的 §4、§6、§8、§10、§14、§15、§17 全部同步了 Controller 裁决。
2. 九文件 consumer 闭集完整——全仓 `WebResourceBudget` 扫描确认无遗漏。
3. 四文件 S1 type-only 边界可执行——逐文件指令有精确的符号级别描述和明确的行为冻结边界。
4. aggregate/child/worker/process payload owner 唯一——从 `WebToolsConfig` 到各 executor 是单向无重叠投影链。
5. utility 1024/80 时序自洽——S1 保留（登记为临时状态）、S3 删除并同源替换，scan 命令覆盖全时序。
6. 无 S2/S3/Issue178/R03/统一 authorization 偷带——所有 S1 章节显式声明行为冻结。
7. 两条 observations (DRR-F01, DRR-F02) 均为 LOW severity，不需要修改 plan；不影响 S1 implementation entry。

**可进入下一 gate 的条件**: Controller 完成 MiMo 第二路 re-review、裁决所有 findings、创建 superseding accepted-plan commit 后，可切入 S1 implementation。

Handoff: DS re-review 完成，等待 Controller。

---

*本 artifact 由 AgentDS 在 `2026-07-14 22:34:10 +0800` 生成。不修改 plan、control、产品、测试、README 或其它 artifact。不 commit。*
