# Plan：修复巨潮空公告列表 `announcements: null` 解析导致下载中断

- Gate: `plan`
- Work unit: 000333 下载时巨潮公告列表格式异常（fixture-refresh-20260925 dayu-repair-prompt）
- 日期：2026-09-25
- 分支：`codex/upload-material-oracle`（用户明确要求在当前分支修复）
- 任务书：`/Users/leo/workspace/portfolio-manager-v2/orch/workpapers/fixture-refresh-20260925/dayu-repair-prompt.md`

## 1. Goal / Motivation / Success signal

- **Goal**：恢复既有 Dayu CLI 下载美的 `000333` 2024 财年年报的能力（filing date 窗口 `2025-01-01~2025-03-31`），只修复经直接证据证实的响应解析问题。
- **Motivation**：`dayu-cli download --ticker 000333 --start 2025-01-01 --end 2025-03-31` 退出码 1，终态
  `巨潮来源返回的公告列表格式不符合预期`，下载能力不可用，阻塞 fixture-refresh 工作。
- **Success signal**：原命令（新日志文件名）退出码 0，终态无未解释 failure / reject / 缺失；用 Dayu 权威元数据核验
  目标文档（`document_id`、`meta.json` 路径、revision、`source_fingerprint`、文件 SHA、财务报表正文路径取自元数据），
  且 `ingest_complete` 为真；若被跳过则核验已有文件与元数据；若外部阻塞则精确记录 `deviations`，不把失败改成成功。

## 2. Non-goals / Scope boundary

- 不新增下载入口、配置面、字段、豁免、重试框架、旁路、诊断子系统。
- 不扩到 HK / SEC / 其它市场；不重构 downloader 架构；不动 `cn_report_selection` 既有筛选语义。
- 不改消费方 `portfolio-manager-v2` 的范式、业务代码、测试 fixture、运行状态；不手工触碰受管 workspace 文件与元数据；
  不伪造 manifest。
- 不把协议失败静默改成“空结果成功”；缺 key / 错误形态响应必须继续失败。

## 3. Goal alignment

| 计划项 | 对应 goal / success signal |
|---|---|
| `_query_announcements` 空结果编码解析修复 | 恢复下载能力（goal 本体） |
| 事件回归测试（FY 有行 + H1 null） | 证明本次失败场景不再中断（success signal 前置） |
| CLI 复验 + 元数据核验 | success signal 的验收主体 |
| 错误形态继续抛协议失败的测试 | 非目标“不把失败改成空成功” |

## 4. First-principles judgment and direct code evidence

**Root cause（已取证，逻辑/数据同源）**：

巨潮 `hisAnnouncement/query` 对“本页无结果”用 **`announcements: null`** 编码（key 存在、值为 null），而不是 `[]`。
`CninfoDiscoveryClient._query_announcements`（`dayu/fins/downloaders/cninfo_downloader.py:471-475`）把非 list 的
`announcements` 一律判为协议违规并抛 `FinsDownloadProviderError(PROTOCOL)`，导致任一空财期查询中断整个多财期
discovery。bare CN 请求的 discovery 顺序为 `FY,H1,Q1,Q3`（`cn_form_utils.py:40`），filing-date 窗口
`2025-01-01~2025-03-31` 内 H1/Q1/Q3 天然无结果 → 必然在 H1 处 abort，即使 FY 已返回目标年报候选。

**直接证据**（取证脚本 `workspace/tmp/probe_cninfo_announcement_shape.py`，沿生产
`CninfoDiscoveryClient` 同一请求构造，仅在 HTTP 边界记录脱敏特征，2026-09-25 两次运行一致）：

| 请求 | HTTP | `announcements` | `hasMore` | `totalRecordNum` |
|---|---|---|---|---|
| GET `/new/data/szse_stock.json` | 200 | —（`stockList` list，`resolve_company` 成功） | — | — |
| POST query `category_ndbg_szsh;`（FY） | 200 | **list，长度 2**（item0 `secCode=000333, adjunctType=PDF`） | false | 2 |
| POST query `category_bndbg_szsh;`（H1） | 200 | **null** | false | **0** |

- 两次 POST 顶层 key 集完全一致（`announcements/categoryList/classifiedAnnouncements/hasMore/totalAnnouncement/
  totalRecordNum/totalSecurities/totalpages`），空结果响应不是错误载荷，是同一契约的空编码。
- `null` 与 `totalRecordNum=0` 严格对应，与有结果响应的 `totalRecordNum==len(announcements)` 一致。
- 生产路径复现同一错误文案 `巨潮来源返回的公告列表格式不符合预期`，与 2026-09-25 19:09:50 事故一致（确定性，非瞬时）。
- 现有测试仅覆盖 `announcements: []`（`tests/fins/test_cninfo_downloader.py`
  `test_list_report_candidates_empty_when_no_announcements`），未覆盖 `null` / 缺 key / 错误类型。

**排除的替代假设**（均有反证）：

- 网络不可达 / 巨潮整体故障：GET stockList 与 FY POST 均 200 + JSON 正常。
- 巨潮改版换 key / 错误载荷：空结果响应 key 集与有结果响应一致，且含 `totalRecordNum: 0`。
- 瞬时限流：两次独立取证运行结果一致。

## 5. Affected files / modules

- `dayu/fins/downloaders/cninfo_downloader.py`：唯一修改的生产文件，`_query_announcements` 响应解析边界
  （该函数是 `hisAnnouncement/query` wire format → 领域语义的唯一 owner）；模块 docstring 补一句空结果编码事实。
- `tests/fins/test_cninfo_downloader.py`：回归测试。
- 只读取证脚本 `workspace/tmp/probe_cninfo_announcement_shape.py`（已存在，不进生产）。

## 6. Contract / schema / state-machine / public-interface changes

- **无** public contract / schema / 状态机变更。`CninfoRawAnnouncement`、`CnReportCandidate`、
  `FinsDownloadProviderError`、workflow 事件与 CLI 输出契约均不变。
- 仅收紧一个内部解析规则：`hisAnnouncement/query` 响应中 `announcements` 字段允许值语义从
  `{list}` 扩为 `{list, null}`（null = 空页），缺 key 或其它类型仍为协议失败。这是 provider wire 语义适配，
  不是对下游暴露新字段。

## 7. Implementation decisions

1. **修复位置**：`_query_announcements` 分页循环内、`announcements` 解析处（owner boundary）。
   禁止在 workflow / selection / CLI 层做特判补偿。
2. **三分支语义**（显式区分缺 key 与 null）：
   - `announcements` key **不存在** → 维持协议失败（错误载荷 / 未知契约必须 fail-closed，防止“失败变空成功”）；
   - 值为 **`null`** → 视为空页，与现有 `[]` 分支同路径 `break`（不检查 `hasMore`，与 `[]` 现行为一致）；
   - 值为 **list** → 现行为不变；**其它类型**（str/int/dict/bool）→ 维持协议失败。
3. **为何不是 loose parsing**：本模块是巨潮 wire format → 领域语义的唯一 owner，且已有同型先例
   （`_format_announcement_date` 同时接受毫秒时间戳与 `YYYY-MM-DD` 字符串两种 provider 编码）。
   `null` 与 `[]` 是同一业务事实（空结果）的两种 wire 编码，在 owner 处归一正确。
4. **不改 `hasMore` 检查位置**：空页提前 break 是既有分页语义（`[]` 分支今日如此），本次不扩大。
5. **wire 字段名字面量**（`"announcements"` 等）沿用本解析器现状内联写法（provider schema 字面量，
   与工具 schema 例外同类）；不为本次修复单独引入常量造成风格分裂，也不顺手全文件重构。
6. **不做诊断增强**：协议失败时记录响应特征是真实缺口，但不是本次失败的 root cause，属新机制，
   按任务书“不顺手发明新机制”记为 deferred follow-up（见 §11）。

**为何没有过度设计 / goal drift**：改动是一处解析分支 + 回归测试，恰好覆盖已证实的失败语义；
不引入新配置、新类型、新重试、新日志通道；错误形态仍失败，未扩大成功面。

## 8. Implementation slices

**单 slice（S1）：空公告列表解析修复 + 回归测试**（一次 implementation pass + 一次 review pass 足够）：

- objective：`announcements: null` 不再中断 discovery；错误形态仍协议失败。
- allowed files：`dayu/fins/downloaders/cninfo_downloader.py`、`tests/fins/test_cninfo_downloader.py`。
- exact allowed changes：
  - `_query_announcements`：按 §7.2 三分支解析；中文行内注释说明 null 语义与 fail-closed 意图。
  - 模块 docstring 补充“空结果以 `announcements: null` 编码”的事实说明。
  - 测试新增用例（见 §9）。
- non-goals：不动 `select_cninfo_report_candidates`、workflow、其它 downloader、CLI。
- completion signal：受影响测试全绿 + pyright 无新增报错；随后进入 CLI 复验与元数据核验（验证步骤，非代码 slice）。

CLI 复验与元数据核验不构成独立实现 slice（无代码变更），作为 S1 验证与最终交付的一部分执行。

## 9. Tests / validation commands and expected assertions

新增测试（`tests/fins/test_cninfo_downloader.py`，均用现有 httpx MockTransport 注入模式）：

1. **`test_list_report_candidates_treats_null_announcements_as_empty`**：
   单财期响应 `{"announcements": None, "hasMore": False}` → 返回空 tuple，不抛。
2. **`test_list_report_candidates_null_empty_period_does_not_block_other_periods`**（事故回归）：
   FY 页返回 2 条合法 PDF 公告，H1/Q1/Q3 页返回 `announcements: None` → 只产出 FY 候选，不抛。
3. **`test_list_report_candidates_missing_announcements_key_raises`**：
   响应缺 `announcements` key（如 `{"hasMore": False}`）→ 抛 `FinsDownloadProviderError`，message 为
   `巨潮来源返回的公告列表格式不符合预期`。
4. **`test_list_report_candidates_non_list_announcements_raises`**：
   `announcements` 为 dict / str → 抛同一协议失败。

断言要点：错误用例断言 `FinsDownloadProviderError` 的 `transport_category=PROTOCOL` 与安全文案（owner 级 contract），
不 mock 掉解析边界。

验证命令：

```bash
source .venv/bin/activate
pytest tests/fins/test_cninfo_downloader.py -q
pytest tests/fins/test_cn_download_workflow.py tests/fins/test_cn_download_runtime.py -q
pytest tests/fins -q          # fins 面上回归
pyright                       # 全库，确认无新增/扩散
```

CLI 复验（与事故命令同参，仅换新日志名，不传 `--forms/--overwrite/--rebuild`）：

```bash
/Users/leo/workspace/dayu-agent-r/.venv/bin/dayu-cli \
  --base /Users/leo/workspace/portfolio-manager-v2/workspace \
  download --ticker 000333 --start 2025-01-01 --end 2025-03-31 \
  --log-file /Users/leo/workspace/portfolio-manager-v2/orch/workpapers/fixture-refresh-20260925/midea/download-recheck-20260925.log
```

预期：

- 退出码 0；摘要 downloaded=1（或 skipped=1 且已有文件/元数据核验通过）；无 failed / rejected；
  omitted=0（单文档，不会触及 10 行 public 上限）。
- **终态预期出现 `Fins missing periods: H1,Q1,Q3`**（bare 请求 discovery 为 `FY,H1,Q1,Q3`，而该 filing
  窗口内 H1/Q1/Q3 类公告不存在，见 §11）。这是既有 designed semantics
  （“主源没有候选的请求财期；不属于 document outcome”），属**可解释缺失**，不是失败、拒收或数据缺失。
  **禁止**为消除该行修改期间策略、missing 投影或 workflow 语义（那会越权扩 scope）；交付中按下述口径解释即可。

元数据核验（通过 `dayu.fins.storage` 仓储语义读取受管 workspace 权威 meta，只读；所有事实以 meta 真源字段为准）：

- `document_id` 与 meta.json 实际路径（storage 布局下该文档的 source meta 文件）。
- revision：取 meta / 仓储的 revision 真源字段。
- `source_fingerprint`：直接取 meta 同名字段；`pdf_sha256` 同理（`cn_download_source_upsert.py:187-191`）。
- 文件 SHA 校验 = 对 **meta 指名的 PDF 文件** 重算 sha256，与 meta `pdf_sha256` 比对一致。
- 财务报表正文路径：取 meta primary 文档字段（如 `primary_document`；以 meta 实际字段名为准，
  若与任务书措辞不同按 meta 字段名上报），不得从 workspace 目录结构反推。
- `ingest_complete=true`；主体为美的 `000333` 2024 财年年报、filing date ∈ [2025-01-01, 2025-03-31]。
- 交付中每个值标注其来源 meta 字段名。

## 10. Docs decision

- `dayu/fins/` 修改 → 实现时检查 `dayu/fins/README.md` 的 `Agent更新约束【必须遵守】`，仅当解析契约事实属于
  其职责范围才更新（预期：downloader wire 适配细节若 README 不承载则不改）。
- `tests/` 修改 → 检查 `tests/README.md` 同理。
- 根 README / `dayu/README.md`：无用户可见入口、分层、装配变化 → 不更新。

## 11. Risks / open questions

| 项 | 分类 |
|---|---|
| bare 请求在 Q1 filing 窗口下终态必现 `Fins missing periods: H1,Q1,Q3` | covered by current slice：§9 解释口径已钉死（可解释缺失，非缺陷），交付中解释 |
| 巨潮未来对空结果省略 `announcements` key → 会再次协议失败（fail-closed，宁失败不假成功） | fixed in current slice 的已知残留边界；接受，不预实现 |
| 协议失败不记录响应特征（本次取证靠外部脚本） | deferred follow-up → 需新 issue / 用户决策，owner：Dayu 维护方 |
| HK downloader 若存在同型 null 假设 | 未取证；任务明确不扩其它市场 → assigned to later work unit（仅在用户要求时） |
| 取证与复验的网络环境同为本机出网，与事故时 orchestrator 环境可能有差异 | covered by S1 验证：CLI 复验即在真实入口端到端确认 |
| 消费方 CMB / YUMC 下载未尝试（任务书已声明非本任务范围） | tracked by 消费方 fixture-refresh 工作流，非本 work unit |

无 blocking open question（goal confirmation 已确认分支策略与取证方式）。

## 12. Completion report format

最终交付按任务书验收项组织：根因与直接证据 / 实际改动文件 / 测试结果 / 复验命令与退出码与终态摘要与新日志路径 /
元数据核验明细（document_id、meta.json 路径、revision、source_fingerprint、SHA、财务报表正文路径，逐项标注来源
meta 字段）/ `Fins missing periods: H1,Q1,Q3` 解释（§9 口径：窗口内无此类报告的业务事实 + 既有 missing 语义，
非失败非缺失数据）/ 跳过或阻塞说明 / residual risks。并附 gateflow final closeout 段。
