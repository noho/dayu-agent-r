# WU-SEMANTIC-OWNERSHIP-01 / R10 独立计划 — AgentDS adversarial plan review

## 1. Review identity 与 target lock

- **reviewer**：AgentDS（第二路独立 adversarial plan review）
- **review type**：adversarial plan review，不是 plan acceptance 或 implementation authorization
- **target artifact**：`docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`
- **target lock**：605 lines；SHA-256 `5f8b1d3880fc5cf3fac370117edea441ffc1fc1c05574844fd0c0814e30db699` —— **已核对一致**
- **baseline HEAD**：`1c2585275f4134d8456a3fda2d84464e4e52c9d7` —— **已核对一致**
- **branch**：`phaseflow/host-issues-control`
- **staged tree**：empty —— **已核对一致**
- **review timestamp**：2026-07-17T18:05:46+08:00

## 2. Authority sources consumed

按 plan §2.1 的 authority order 逐项完整读取并核对：

| # | Source | 读取状态 | 与 plan lock 一致 |
|---|--------|---------|-------------------|
| 1 | `AGENTS.md` (128 lines) | 完整读取 | ✓ |
| 2 | `docs/fins/design.md` §8 (123 lines) | 完整读取 | ✓ SHA match |
| 3 | Controller discussion Topic 6.6 (731 lines) | 完整读取 | ✓ SHA match |
| 4 | Umbrella remediation plan §17 (1270 lines) | 完整读取 §17 + R10 allowlist/coverage rows | ✓ SHA match |
| 5 | Phaseflow umbrella optimization control | 通过 umbrella plan §7 引用消费 | N/A |
| 6 | R10 plan-entry Controller validation (96 lines) | 完整读取 | ✓ SHA match |
| 7 | Controller plan validation (105 lines) | 完整读取 | —（plan 本身的 controller verdict） |
| 8 | Production code/tests/READMEs | 完整读取关键文件 | 见 §3 |

## 3. 代码事实核对

以下 production/test 文件已完整读取并与 plan lock 核对：

| File | Plan lock SHA | 实际 SHA | 一致 |
|------|-------------|----------|------|
| `dayu/fins/downloaders/hkexnews_downloader.py` (1065 lines) | `8c7c1a3b...` | `8c7c1a3b...` | ✓ |
| `tests/fins/test_hkexnews_downloader.py` (1213 lines) | `d98266b8...` | `d98266b8...` | ✓ |
| `tests/fins/test_cn_download_workflow.py` (1660 lines) | `c2d86d47...` | `c2d86d47...` | ✓ |
| `dayu/fins/pipelines/cn_download_protocols.py` (227 lines) | `a92f283c...` | `a92f283c...` | ✓ |
| `dayu/fins/pipelines/cn_download_workflow.py` (806 lines) | `3c27e009...` | `3c27e009...` | ✓ |
| `dayu/fins/downloaders/cninfo_downloader.py` (835 lines) | `baab2ae4...` | `baab2ae4...` | ✓ |
| `tests/fins/test_cninfo_downloader.py` (1397 lines) | `92e518f5...` | `92e518f5...` | ✓ |
| `tests/fins/test_cn_pipeline.py` (718 lines) | `7f00b257...` | `7f00b257...` | ✓ |
| `tests/fins/test_cn_download_runtime.py` (704 lines) | `b37a4a86...` | `b37a4a86...` | ✓ |

**关键代码事实摘要**（已逐文件核对）：

1. **当前 HKEX discovery 实现**（`hkexnews_downloader.py:365-427`）：`_query_period_announcements` 每个 language/category 只发一次固定 `rowRange="100"`（line 407），然后调用 `_extract_title_search_rows_page` → `_raise_if_title_search_truncated`。Plan 的动机诊断完全准确。

2. **Generic total aliases**（`hkexnews_downloader.py:649-658`）：`_extract_title_search_total_count` 扫描 8 个 key（`total/totalCount/total_count/recordCount/record_count/recordsTotal/records_total/count`），不包含官方 `recordCnt`。Plan 的删除清单正确。

3. **Truncated 检测**（`hkexnews_downloader.py:692-728`）：`_raise_if_title_search_truncated` 在 `total > rows` 或 `rows >= 100 且无 total` 时抛 `HkexnewsDiscoveryTruncatedError`。Plan §5.3 要求删除该逻辑——正确。

4. **cancel_checker 当前流向**（`cn_download_workflow.py:233-234`）：`discovery.list_report_candidates(query, profile)` 调用在当前代码中**不传递** cancel_checker。取消检查只在调用前后各一次（line 227, 234）。Plan 的"当前 workflow 只在整个调用前后检查"诊断**直接代码确认**。

5. **测试 fake 签名**：三个测试文件共 5 个 discovery fake client（`_FakeDiscoveryClient`、`_PipelineDownloadFakeDiscoveryClient`、`_PipelineDownloadFakeHkDiscoveryClient`、`_RuntimeFakeDiscoveryClient`、`_FailingDownloadDiscoveryClient`），其 `list_report_candidates` 当前签名均为 `(self, query, profile)` 无 cancel_checker 参数。Plan 的 test double migration 范围**精确覆盖**。

6. **cn_download_protocols.py 现有设计意图**（line 18-19）：docstring 明确写"不在协议内塞入'取消检查'……横切关注；横切由 workflow 层显式接收 `cancel_checker` 参数管理"。Plan §4.1 的 cancel seam 是对此设计决策的必要修订，因为有证据表明仅 workflow 层检查不足以覆盖多轮 HTTP 内取消。

7. **fixtures 目录**：`tests/fins/fixtures/hkexnews/` 当前不存在。Plan §9 要求新增 captured fixture——这是一个新建 artifact，无旧数据冲突。

## 4. Assumptions tested

| # | Plan assumption | 验证方法 | 结论 |
|---|----------------|---------|------|
| A1 | 当前 HKEX 实现缺少 cumulative continuation | 直接代码 audit：`_query_period_announcements` 仅一次 `rowRange=100` GET，无循环 | **成立** |
| A2 | Generic total aliases 错失官方字段 | 直接代码 audit：8 个 aliases 不含 `recordCnt`，`hasNextRow/loadedRecord` 完全未使用 | **成立** |
| A3 | cancel_checker 无法进入 downloader 多轮请求 | 直接代码 audit：workflow line 233 调用 `list_report_candidates` 不传 cancel_checker | **成立** |
| A4 | 共享 protocol 签名改动是传递 cancel 的最小 seam | 对照 protocol 现有签名与 workflow 调用链：keyword-only 参数是改动面最小的方案 | **成立** |
| A5 | CNInfo 接受 cancel_checker 不会产生语义漂移 | CNInfo 当前只有一个 discovery HTTP round；在其前后各检查一次 cancel 是实质性消费 | **成立** |
| A6 | `hasNextRow/loadedRecord/recordCnt` 是官方 JSON 字段名 | Controller discussion Topic 6.6 有 live endpoint 验证证据 | **成立（controller 已裁决）** |
| A7 | snapshot replacement 语义足够 | 对照设计真源 `docs/fins/design.md` §8 与 HKEX 官方 cumulative 行为 | **成立** |
| A8 | 单 slice 合理 | 检查：protocol 签名、HKEX 状态机、test migration、fixture、README 共享同一 owner 和 failure blast radius | **成立** |

## 5. Findings

### DS-R10-F01 — 未修复 — 中 — HKEX downloader 内 cancel 信号的 raise/lambda 策略未指定

- **位置**：Plan §6.2 state machine（"check cancellation before request" / "check cancellation immediately after response"）、§6.3 cancellation seam、§5.3 typed error
- **问题类型**：不可直接实施
- **当前写法**：Plan 明确 HKEX downloader 在每轮 HTTP 前后调用 `cancel_checker: Callable[[], bool] | None`，但未指定 downloader 检测到取消后**以何种机制**阻止 partial rows 传播。现有 workflow 使用 `_is_cancel_requested`（定义在 `cn_download_workflow.py:406-424`）和 `_raise_if_cancelled`（定义在同一文件 line 433-454）两个 workflow-private helper。HKEX downloader 不应反向依赖 workflow 内部 helper。
- **反例/失败场景**：implementation agent 可能选择以下任一方案，但 plan 未授权其中任何一个：
  a) downloader 直接调用 `cancel_checker()`，返回 True 时 raise `CnDownloadCancelledError`——这与 workflow 的 `_is_cancel_requested` 逻辑（同时处理 bool 返回和 checker 内部 raise）不一致，checker 内部 raise 的异常会被静默吞掉。
  b) downloader 仅检查 `cancel_checker()` 的 bool 返回值而忽略 checker 自身 raise——违反 §5.3 "cancel checker 自身的非取消故障以带 cause 的 RuntimeError 传播"。
  c) downloader 复制 `_is_cancel_requested` 逻辑——违反编码硬约束（重复逻辑）。
- **为什么有问题**：cancel 信号处理必须在 HKEX owner 内自足完成，但当前 plan 只描述"检查"语义，未指定"检查到取消后做什么以及用什么异常类型"。implementation agent 被留在这个设计空白中自行决定。
- **直接证据**：
  - Plan §6.2 state machine: "check cancellation before request" / "check cancellation immediately after response" — 仅说检查，未说动作
  - Plan §6.3: "HKEX downloader 在每轮 HTTP 前后检查" — 同样未指定检查到后如何传播
  - Plan §5.3: "取消使用既有 `CnDownloadCancelledError` 控制流，保持调用方主动抛出的取消对象" — 暗示由调用方（workflow）抛出，但 plan 明确每轮检查点在 downloader 内部
  - Workflow 代码事实：`_is_cancel_requested` (line 406-424) 和 `_raise_if_cancelled` (line 433-454) 是 workflow-private
- **影响**：implementation agent 在 downloader 内实现 cancel 检查时需自行设计 raise 策略，可能与 workflow 存在行为差异（尤其是 checker 自身异常的处理），后续 code review 回退
- **建议改法和验证点**：
  1. 在 §6.2 state machine 中明确：download 循环内的 cancel 检查逻辑为——
     ```text
     if cancel_checker is not None:
         try:
             cancelled = cancel_checker()
         except CnDownloadCancelledError:
             raise
         except Exception as exc:
             raise RuntimeError(f"cancel checker 故障: ...") from exc
         if cancelled:
             raise CnDownloadCancelledError("披露易 discovery 已被取消: ...")
     ```
  2. 或将此逻辑提取为模块级私有 helper `_check_cancel(cancel_checker)`，由 HKEX downloader 和 CNInfo downloader 各自调用（或放入 shared 模块），避免 workflow-private helper 的反向依赖。
  3. 在 test matrix 中补充：checker raise `CnDownloadCancelledError` 时的行为（当前只有 "checker 第一次返回 true/主动抛 typed cancel" 笼统描述）和 checker 抛非取消异常时的 behavior（当前 "checker failure" 行覆盖了 RuntimeError 传播但不是发生在循环内的场景）。
- **修复风险（低/中/高）**：低——只需在 plan 中指定已有概念（`CnDownloadCancelledError` / RuntimeError）在 downloader 内部的确切使用方式
- **严重程度（低/中/高/严重）**：中——不阻塞 plan acceptance，但 implementation agent 若选择错误方案会导致 cancel propagation 行为不一致

### DS-R10-F02 — 未修复 — 低 — protocol 文件 coverage ≥80% 对纯 Protocol 类的可实现性未验证

- **位置**：Plan §10.3 逐文件 coverage，`cn_download_protocols.py` 要求 `--fail-under=80`
- **问题类型**：不可直接实施
- **当前写法**：Plan §10.3 要求所有四个 modified production file（含 `cn_download_protocols.py`）各自 branch coverage ≥80%。未讨论 Protocol 类（方法体为 `...`）的 coverage 特征。
- **反例/失败场景**：`cn_download_protocols.py` 的改动仅是在 `list_report_candidates` 签名中增加 keyword-only 参数，方法体仍是 `...`。Protocol 类的 `...` 和 docstring 不产生可执行行。`coverage.py` 对该文件可能报告 N/A（无可执行行）或 100%（0/0 可执行行），也可能因模块级 import 和 `TypeAlias` 赋值产生少量可执行行——哪种行为取决于 coverage.py 版本和配置。若 coverage 报告为 N/A，`--fail-under=80` 的行为不确定。
- **为什么有问题**：blanket "每个文件 ≥80%" 规则对纯 Protocol 文件可能不适用。若 implementation agent 发现 protocol 文件无法达到 80% 而添加无意义的 `if TYPE_CHECKING` 块或 dummy test 来刷覆盖率，违反 AGENTS.md 禁止过度设计约束。
- **直接证据**：
  - Plan §10.3: `coverage report ... --include=dayu/fins/pipelines/cn_download_protocols.py --fail-under=80`
  - `cn_download_protocols.py` 的 `list_report_candidates` 方法体为 `...` (line 106)
  - 文件其他可执行行仅包括 import、TypeAlias 赋值——总共约 10 行可执行代码
- **影响**：implementation agent 可能被 coverage gate 卡住或添加 padding code
- **建议改法和验证点**：
  1. 在 §10.3 中补充：若 `cn_download_protocols.py` 实际可执行行数为 0 或 coverage 报告 N/A，则用显式 "no executable lines / N/A with evidence" 替代 `--fail-under=80`。
  2. 或在 R10 completion report format 中允许 protocol file 覆盖率为 `N/A (Protocol class)` 并给出 coverage JSON 证据。
- **修复风险（低/中/高）**：低——加一行说明即可
- **严重程度（低/中/高/严重）**：低——不阻塞 plan，但 implementation gate 可能被误触发

### DS-R10-F03 — 未修复 — 低 — CNInfo cancel_checker "消费"语义未定义检查时点与行为

- **位置**：Plan §4.1 owner map、§6.3、§8 test matrix "CNInfo seam regression"
- **问题类型**：契约缺失
- **当前写法**：Plan 在多处说明 CNInfo 需"消费取消"：§4.1 "CNInfo 只在自己既有单轮 discovery I/O 前后消费该 signal"；§6.3 "CNInfo 只在自己的既有 discovery I/O 前后检查以满足同一 signature 的真实语义"；Test matrix "checker 被真实消费，不是 ignored arg"。
- **反例/失败场景**：CNInfo 的 `list_report_candidates`（`cninfo_downloader.py:229`）当前按 period 循环发送 HTTP 请求（每个 `target_periods` 成员一个 POST）。单轮 CNInfo discovery 实际上可能发起多次 HTTP 请求（每个 fiscal period 一次）。若 implementation agent 在每个 period HTTP 请求前后都检查 cancel，就是实质性的行为变更（以前 CNInfo discovery 不可中途取消）；若仅在方法入口和出口各检查一次，则"消费"只是形式上的。
- **为什么有问题**：Plan 声称 CNInfo "不获得 HKEX cumulative 状态"（§6.3），但未明确 CNInfo 的 cancel check 粒度是"每个 period HTTP 前后"还是"整个方法入口/出口"。两种粒度都是"真实消费"，但取消响应性不同。Plan 不应在"不影响 CNInfo 行为"和"真实消费取消"之间留下模糊空间。
- **直接证据**：
  - `cninfo_downloader.py:229-259`：`list_report_candidates` 内按 `target_periods` 循环发起 HTTP 请求
  - Plan §6.3: "CNInfo 只在自己的既有 discovery I/O 前后检查以满足同一 signature 的真实语义，不获得 HKEX state machine"
  - Test matrix row "CNInfo seam regression": "query/selection 不变；checker 被真实消费，不是 ignored arg"
- **影响**：implementation agent 对"消费"粒度有歧义时可能选择过于激进（per-period cancel）或过于保守（仅入口/出口）的方案
- **建议改法和验证点**：
  1. 在 §6.3 中明确：CNInfo 的 cancel 检查在 `list_report_candidates` 入口（第一轮 HTTP 前）和出口（最后一轮 HTTP 后）各一次，不在各 period HTTP 之间检查——因为 CNInfo 的 period 循环是单个 discovery 的内部实现，plan 承诺不改变 CNInfo query、分页、筛选语义。
  2. 在 test matrix "CNInfo seam regression" 行中补充：断言 cancel_checker 被调用的精确次数（2 次：入口 + 出口）。
- **修复风险（低/中/高）**：低——加一行说明即可
- **严重程度（低/中/高/严重）**：低——不阻塞 plan，但可能产生实现歧义

## 6. Controller challenge areas — 独立验证

Controller plan validation §6 要求双路 review 独立挑战以下 6 个高风险点。以下逐项给出 AgentDS 独立验证结论：

### 6.1 cancel_checker direct seam 是否是 production-reachable 的最小闭环

**验证结论：是。**

直接代码证据：
- workflow `run_cn_download_stream_impl` (line 55) 已有 `cancel_checker: Callable[[], bool] | None` 参数
- 该 checker 在 line 205/207/227/234/256/345 多处被消费
- 当前 line 233 `discovery.list_report_candidates(query, profile)` 不传 checker——这是唯一需要闭合的 gap
- 增加 keyword-only `cancel_checker` 到 protocol 签名，workflow line 233 改为 `discovery.list_report_candidates(query, profile, cancel_checker=cancel_checker)` 即可闭合

CNInfo 和 test doubles 的签名迁移是 structural typing 的必然结果，不构成语义扩域。无 any ambient context、mutable setter 或 market branch。**Plan 正确。**

### 6.2 requested range 增长 + loaded/rows 严格增长是否足以有限失败

**验证结论：是，有限失败保证成立。**

Plan §6.2 的四层防护：
1. **response range equality**（§5.2.5）：若 provider clamp 了 range（请求 200 返回 range=100），第一层立即 typed fail
2. **loadedRecord monotonic**（§6.2 bullet 3）：连续 `hasNextRow=true` 响应间 loaded/rows 必须严格增加；否则 typed fail
3. **no-progress detection**（§6.2 bullet 3 补充）：即使 range 和 recordCnt 增长，若 loaded 不变，typed fail
4. **terminal precedence**（§6.2 bullet 4）：最新自洽 terminal snapshot 覆盖跨轮 progress 比较，不被历史状态误解

最坏情况下（provider 持续 hasNextRow=true 且 recordCnt 增长但 loaded 不变），第 3 层在第二轮即 fail——不会无限 doubling。**Plan 正确，不会无限循环。**

额外验证：若 provider 在连续轮次中持续返回 `hasNextRow=true` 但 `loadedRecord` 每次只增加 1 条，理论最大轮次 = `recordCnt`（第一次响应中的 recordCnt）+ 增长量。这是一个大但有限的值，且每轮都经过 HTTP retry/throttle——不是静默无限循环。若需要更紧的上界，可在 implementation 时增加 watchdog（如 range > 10000 且 loaded < range/2 时 warn），但这属于 safety net 而非 plan 缺陷。

### 6.3 exact bool/int/stringified-list parser 与官方 evidence 一致

**验证结论：一致。Parser 规格与 controller discussion Topic 6.6 live endpoint 验证一致。**

Plan §5.2 的 strict parser：
- `hasNextRow` 只接受 JSON bool → 与官方 observed behavior 一致（live 验证确认 bool）
- `rowRange/loadedRecord/recordCnt` 只接受 JSON int 且显式拒绝 bool（Python `isinstance(True, int)` 陷阱）→ 正确，防御性编程
- `result` 只接受 stringified JSON array → 与官方 observed behavior 一致
- same-round constraints（loaded ≤ count, loaded ≤ range, range equality）等 → 全部从官方协议派生

特别注意：plan 提到 `_coerce_non_negative_int` 当前接受 `isinstance(value, float) and value.is_integer()`（line 683-684 of hkexnews_downloader.py），plan §5.2.3 正确拒绝了 integral float coercion for count/range fields。**Parser 规格正确且完整。**

### 6.4 typed provider protocol error 在 list_report_candidates/workflow 中保留 type/cause

**验证结论：Plan 对此有明确要求，但实现细节有一个缺口（见 DS-R10-F01）。**

Plan §5.3 明确：
- `HkexnewsProviderProtocolError` 保持 type/cause 通过 `list_report_candidates` 传播
- 不被 `RuntimeError("披露易公告分类查询失败...")` 抹平——当前代码 line 296-299 确有这个 catch-and-rewrap pattern
- 取消用 `CnDownloadCancelledError`，checker failure 用 RuntimeError

当前的 `except HkexnewsDiscoveryTruncatedError: raise` (line 294-295) 和 `except RuntimeError as exc: raise RuntimeError(...) from exc` (line 296-299) 需要改为：对 typed protocol error 不加 `RuntimeError` wrapper，直接传播。Plan 对此有明确意图。**关闭 DS-R10-F01 后本项无剩余 gap。**

### 6.5 final-only parse/HEAD、per-language isolation、query invariance、count growth、external smoke stop policy

**验证结论：全部在 plan 中有可执行规定。**

- final-only parse/HEAD：§6.2 "每轮赋值 `latest_rows = snapshot.rows`，不使用 `extend`/`+=`" 和 "只有 complete 后才把 final rows 交给 `_parse_announcement(...)`"——明确
- per-language isolation：§6.1 每个 language/category 独立构造 base params + test matrix "per-language isolation" 行——明确
- query invariance：§6.1 每轮去除 `rowRange` 后 dict exact equality + test matrix 对应行——明确
- count growth：§6.2 "recordCnt 不缓存为第一次总数" + test matrix "multi-round count growth" 行——明确
- external smoke stop policy：§12 stop condition 4 + §9.3 分流逻辑——明确：cap/clamp/stall 时停止并记录 evidence-driven residual，不做 date recursion

### 6.6 exact allowlist、单 slice、coverage 和 README/security/deferred gates

**验证结论：全部完整，未过度设计。**

- allowlist（§4.2）：production 4 文件 + tests 6 文件 + fixture 1 文件 + README 2 文件 = 13 路径，闭合且无越界
- 单 slice（§7）：有充分理由（共享 owner、blast radius、验收矩阵），拆分确会产生不可独立接受的中间态
- coverage（§10.3）：四个文件各 ≥80%，有具体命令。protocol 文件有一项低严重度关注（DS-R10-F02）
- README（§11.1）：触发判断正确——`dayu/fins/README.md` 和 `tests/README.md` 需要更新，根 README 和 `dayu/README.md` 不需要
- security（§11.2）：明确保留 HTTP timeout/retry/throttle/HTTPS/PDF magic/size/stock matching/error hygiene
- deferred（§10.6）：明确 scanned-hunks-only 审计，不对历史文本全文 grep

**没有 generic pagination framework、第二 completeness owner、compatibility shim 或 speculative hard cap。Plan 确实没有过度设计。**

## 7. 专项检查：forbidden design patterns

按用户要求逐项检查以下 pattern 不得出现在 plan 中：

| Forbidden pattern | Plan 是否违反 | 证据 |
|------------------|-------------|------|
| hard cap / 固定最大累计条数 | **否** | §3.3 明确 "不实现 hard cap、固定最大累计条数"；§6.2 "next range 只能使用上述公式；不得加 fixed cap" |
| 日期窗口递归 | **否** | §3.3 明确禁止 "日期窗口递归"；§12 stop condition 4 明确遇到 cap 时停止而非 date recursion |
| generic pagination | **否** | §3.3 明确 "不允许 generic pagination/cursor framework"；§4.1 CNInfo 不接受 HKEX 分页语义 |
| compatibility / loose parsing | **否** | §5.3 删除 `HkexnewsDiscoveryTruncatedError`，"不得 re-export、alias、subclass 或 wrapper"；§3.3 禁止 "兼容分支" |
| Issue 142/151/175/177/178 | **否** | §3.3 明确排除所有五个 Issue；§10.6 deferred scans 以 changed hunks 审计 |
| R11/R12 | **否** | §3.3 "不进入 R11/R12"；§13 deferred gates 明确 handoff 只在 Controller closeout 后 |
| Web/WeChat/render | **否** | §3.3 non-goals |
| Topic 8/9 | **否** | §3.3 non-goals |

## 8. 专项检查：cancel seam 最小性

独立验证 cancel_checker seam 是否满足所有约束：

| Constraint (§6.3) | Plan 满足 | 证据 |
|------------------|----------|------|
| 不写入 query extra payload | ✓ | §6.3 明确禁止 |
| 不存进 CnReportQuery | ✓ | §6.3 明确禁止 |
| 不使用 ContextVar/thread/task identity/全局变量/mutable setter | ✓ | §6.3 明确禁止五种 ambient pattern |
| 不通过 isinstance market 分支调私有方法 | ✓ | §6.3 明确禁止 |
| 不只在测试 constructor 注入 | ✓ | §6.3 明确禁止（"production 永远传 None" 被视为违规） |
| 直接 keyword-only 参数 | ✓ | §6.3 明确要求 |
| 只运输既有取消信号 | ✓ | §4.1 owner map：workflow 产生/拥有，protocol 只显式运输 |
| 不拥有 HKEX pagination/completeness | ✓ | §4.1 owner map：completeness decision 仍在 HKEX owner |

**验证结论：cancel seam 确实是最小的、production-reachable 闭合方案。**

额外验证 production reachability：
- `run_cn_download_stream_impl` (workflow) → `discovery.list_report_candidates(query, profile, cancel_checker=cancel_checker)` → `HkexnewsDiscoveryClient.list_report_candidates` → `_query_period_announcements` → cumulative loop → check cancel_checker before/after each HTTP round
- 同级路径 CNInfo：`run_cn_download_stream_impl` → `discovery.list_report_candidates(query, profile, cancel_checker=cancel_checker)` → `CninfoDiscoveryClient.list_report_candidates` → entry check/exit check only
- 两个路径都是 production-reachable，不需要 mock/fake 才能触发

## 9. 专项检查：test doubles 完整性

| Test double | 位置 | Plan 要求 | 验证 |
|------------|------|---------|------|
| `_FakeDiscoveryClient` | `tests/fins/test_cn_download_workflow.py:250` | 签名加 keyword-only cancel_checker；identity/propagation 断言 | ✓ 正确识别 |
| `_FailingDownloadDiscoveryClient` | `tests/fins/test_cn_download_workflow.py:322` | 同上（子类继承 _FakeDiscoveryClient） | ✓ 隐式覆盖 |
| `_PipelineDownloadFakeDiscoveryClient` | `tests/fins/test_cn_pipeline.py:32` | 签名迁移 + 透传断言 | ✓ 正确识别 |
| `_PipelineDownloadFakeHkDiscoveryClient` | `tests/fins/test_cn_pipeline.py:118` | 同上 | ✓ 正确识别 |
| `_RuntimeFakeDiscoveryClient` | `tests/fins/test_cn_download_runtime.py:78` | 签名迁移 + 透传断言 | ✓ 正确识别 |

**验证结论：test double 矩阵完整，无遗漏。**

## 10. 专项检查：stale/removed contract 扫描

Plan 要求删除的旧 contract 全部有明确标识：

| 删除项 | Plan 位置 | 是否存在残留风险 |
|-------|----------|----------------|
| `_HkexnewsRowsPage.total_count` | §5.3 | 无——replaced by typed snapshot |
| `_extract_title_search_total_count` | §5.3 | 无——§10.5 scan 会验证 |
| `_coerce_non_negative_int` | §5.3 | 无——§10.5 scan 会验证 |
| 8 个 generic total aliases | §5.3 | 无——§10.5 scan 会验证 |
| `_raise_if_title_search_truncated` | §5.3 | 无——§10.5 scan 会验证 |
| `_HKEXNEWS_ROW_LIMIT` / `_HKEXNEWS_ROW_RANGE` 固定上限语义 | §5.3 | 100 保留为 initial range constant 但有新业务名称 |
| `HkexnewsDiscoveryTruncatedError` | §5.3 | 无——§5.3 "不得 re-export、alias、subclass 或 wrapper" |

## 11. Open questions

1. **Q1 — protocol file coverage 行为**：`coverage.py` 对纯 Protocol 文件（方法体 `...`）在不同版本下的行为不同。Protocol 方法被视为 "excluded" 还是 "covered at 100%"? 这影响 §10.3 的 coverage gate 是否可机械执行。answer：在进入 implementation 前运行一次 `coverage run --branch --data-file=workspace/tmp/.coverage-r10-pre -m pytest tests/fins/test_cn_download_workflow.py tests/fins/test_cninfo_downloader.py tests/fins/test_hkexnews_downloader.py tests/fins/test_cn_pipeline.py tests/fins/test_cn_download_runtime.py && coverage report --data-file=workspace/tmp/.coverage-r10-pre --include='dayu/fins/pipelines/cn_download_protocols.py'` 验证实际 coverage 行数和百分比，据此决定是否需要 DS-R10-F02 中建议的例外条款。

2. **Q2 — live smoke 的 query 选择**：§9.3 要求 "选择一个首轮 `recordCnt > 100` 的公开 title-search query"。该 query 的具体 stock/category/date 组合需要在 implementation 时确定。如果当前市场状况下没有 `recordCnt > 100` 的公开 query，live smoke 的 "至少两轮" 要求如何满足？这不应该成为 plan 缺陷（plan 已有外部不可用分流逻辑），但 implementation agent 应在 smoke manifest 中记录 query 选择依据。

## 12. Residual risks

| Risk | Plan 处理 | Destination |
|------|---------|-------------|
| Provider endpoint 未来出现 hard cap 或 clamp | §12 stop condition 4：停止，记录 evidence-driven residual | 未来独立 HKEX provider WU |
| Live smoke endpoint 不可达 | §9.3 / §12：记录环境限制，local protocol gate 仍必须通过 | R10 completion report 环境限制记录 |
| Coverage for protocol file | DS-R10-F02 已记录 | Implementation 前运行 pre-check |
| Downloader 内 cancel raise 策略 | DS-R10-F01 已记录 | Plan fix 或 implementation 时由 controller 裁决 |
| CNInfo cancel check 粒度 | DS-R10-F03 已记录 | Plan fix |

## 13. Final plan review conclusion

**Verdict：`pass-with-risks`**

### 通过理由

本 plan 在以下关键维度上达到了 code-generation-ready 标准：

1. **动机与 owner**：基于直接代码证据的正确诊断。HKEX cumulative protocol 的 owner 明确是 `hkexnews_downloader.py`，不在 selection、workflow、storage 或 CLI 补偿。
2. **State machine**：initial range、next-range formula、query invariance、snapshot replacement、progress detection、terminal precedence、cancel precedence、typed errors 全部明确。有限失败通过 loadedRecord monotonic + response range equality 保证。
3. **Cancel seam**：`Callable[[], bool] | None` keyword-only 参数是最小的、production-reachable 闭合。不引入 ambient context、mutable setter、market branch 或 generic framework。
4. **Test matrix**：28 个 test case 覆盖 happy path、contradiction、cancel（4 timing points）、HTTP failure、per-language isolation、CNInfo regression、test double migration。每个 case 有明确的 setup 和 required assertions。
5. **Validation matrix**：focused tests、full Fins、per-file coverage ≥80%、full pyright、scoped Ruff、diff/source/owner/deferred scans、captured fixture、live smoke——全部有可执行命令。
6. **Scope discipline**：exact allowlist 闭合；forbidden patterns（hard cap、date recursion、generic pagination、compatibility、5 个 Issues、R11/R12）全部零违反。
7. **Stop conditions**：8 个 stop condition 覆盖 source drift、controller rejection、official response contradiction、provider cap、allowlist violation、validation failure、ownership overlap、scope creep。
8. **没有过度设计**：无 generic pagination framework、第二 completeness owner、新配置项、新 public schema、callback/factory 或 speculative provider cap 机制。

### 风险说明

- **DS-R10-F01（中）**：cancel 信号在 HKEX downloader 内部的 raise/lambda 策略未指定。implementation agent 需自行决定是直接 raise `CnDownloadCancelledError` 还是复制 `_is_cancel_requested` 逻辑。建议 plan fix 中明确。
- **DS-R10-F02（低）**：protocol file coverage gate 对纯 Protocol 类的行为未验证。建议 implementation 前 pre-check。
- **DS-R10-F03（低）**：CNInfo cancel check 粒度（入口/出口 vs per-period）未定义。建议 plan fix 中明确。

以上风险均不构成 plan rejection。三个 finding 都是 moderate-low severity，可以通过小幅 plan 修订解决，不需要重新设计 state machine 或 owner boundary。

### accepted-candidate finding 数

**3**：DS-R10-F01（中）、DS-R10-F02（低）、DS-R10-F03（低）。全部是 accepted-candidate，建议 Controller 裁决后由 AgentCodex 修复。

---

## 14. Review integrity statement

- 本 review 仅读取 plan artifact、authority sources（AGENTS.md、design.md、controller discussion、umbrella plan、controller validations）和直接代码/测试证据。
- 未修改 plan、control、code、tests、README 或任何其他文件。
- 未 stage、commit、push、PR。
- 所有 finding 均附直接证据（plan 行号/段落、代码行号、测试文件/行号）。
- 如果 Controller 裁决所有三个 finding 为 rejected-with-reason，本 plan 仍可通过——三个 finding 均不构成阻塞级别的 design defect。
