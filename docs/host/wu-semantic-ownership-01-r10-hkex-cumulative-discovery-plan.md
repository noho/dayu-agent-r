# WU-SEMANTIC-OWNERSHIP-01 / R10 HKEX cumulative discovery 独立实施计划

## 1. Gate、定位与结论

- umbrella work unit：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- 内部 remediation sub-WU：`R10 — HKEX cumulative rowRange 完整续取`。
- work 类型：既有 umbrella 内的 provider-protocol correctness remediation；不是新 WU、issue 或 feature。
- 当前 gate：双路 plan review 后的 accepted-finding plan-only fix；修复完成后停在
  `READY_FOR_CONTROLLER_VALIDATION`，不构成 plan acceptance 或 implementation authorization。
- 风险级别：`production-high`。原因是本轮改变 provider 完整性证明、错误分类与取消时序。
- slice 决策：只设一个 implementation slice。协议解析、累计状态机、取消、owner tests、直接 workflow
  propagation、README 同步和完整验证共享同一 owner、failure blast radius 与验收矩阵，拆分只会制造不能独立接受的
  中间态。

结论：动机成立且严重性没有被高估。当前实现把官方 cumulative continuation 错建模成固定 100 条单次请求，
再从 generic total aliases 猜完整性；合法满首轮会失败，真正超过 100 条时也无法继续发现。正确修复必须在
HKEX provider owner 内消费官方 cumulative protocol，不能在 selection、workflow、storage、Service 或 CLI
补偿。

本计划对用户给定路径做一项必要收窄后的修正：当前共享 discovery protocol 明确不传递取消 checkpoint，workflow
只在整个 `list_report_candidates(...)` 调用前后检查取消。若只允许修改 downloader，downloader 内的多轮同步
请求无法获得真实 operation cancellation signal。为了同时满足“provider protocol owner 仍是 HKEX downloader”
和“每个真实 discovery request 前后均可观察 operation cancellation”，workflow 必须用既有
`_raise_if_cancelled` 语义把 raw `Callable[[], bool] | None` 收敛为一个 workflow-owned、no-arg、无返回值的
`cancellation_checkpoint: Callable[[], None] | None`；shared protocol 只原样运输该 checkpoint，provider 只调用，
不解释 bool、不复制 workflow helper。该必要 seam 不拥有 HKEX pagination/completeness，不引入 generic pagination
或 cancellation framework，也不允许 ambient context、mutable setter、constructor-only 测试注入或
market-specific downstream branch。

## 2. Authority 与 source locks

### 2.1 Authority order

1. `AGENTS.md` 的语义所有权、编码、测试、README 与 LLM-facing 约束；
2. `docs/fins/design.md` §8；
3. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md` Topic 6.6 与 final adjudication；
4. `docs/host/wu-semantic-ownership-01-overdesign-remediation-plan.md` §17；
5. `docs/phaseflow-umbrella-optimization-control.md` 的 high-risk、slice 与 validation 规则；
6. R10 plan-entry Controller validation；
7. AgentMiMo / AgentDS 双路 R10 plan review 与 Controller finding adjudication；
8. 当前 production code/tests/READMEs。

已裁决产品问题不重开。若历史文字与 `docs/fins/design.md` 或 Controller final adjudication 冲突，以前两者为准。

### 2.2 Baseline locks

- branch：`phaseflow/host-issues-control`。
- baseline HEAD：`1c2585275f4134d8456a3fda2d84464e4e52c9d7`。
- baseline staged tree：empty。
- 并行所有权：`docs/host/issues-implementation-control.md` 与 R10 plan-entry Controller validation 由 Controller
  持有；implementation/review Agent 只能读取，不得修改、覆盖、stage 或把它们纳入自己的 diff。

| Source | Lines | SHA-256 |
|---|---:|---|
| `AGENTS.md` | 128 | `cb26618ab566804c97a3ef2f269537b7313e59370e5ddd0258d9b753b08ac45e` |
| Controller discussion | 731 | `cd26760d626415c52caa13a724144b4d98f2a2b2fc159772e6d807833c01533a` |
| umbrella optimization control | 302 | `6d924e919a4ba797e6213879aadca7bdd4f47a37418630e1ee43cb1995e461db` |
| `docs/fins/design.md` | 123 | `97033cf1330e6018df2cf7bf676fa550c24e3e99beb99792f718eac31727abdd` |
| umbrella remediation plan | 1269 | `30c27562ece3360c7d25e55a6f2b0b189999d35cca8004e83d42de3c8ccda838` |
| R10 plan-entry validation | 96 | `885f40461b3b1fd4030437f35ee54eb8ab4227f5e5e1849ce0353d61299136ef` |
| R10 pre-fix plan | 605 | `5f8b1d3880fc5cf3fac370117edea441ffc1fc1c05574844fd0c0814e30db699` |
| AgentMiMo R10 plan review | 166 | `048c8e5998f6a9868fbc41b89127b26fec987a248d9a8aa89955b94d0634fe16` |
| AgentDS R10 plan review | 338 | `7bad9a391f19571724d3452c93797acc042c7e44ecedfb7f20c2e38697a956ce` |
| R10 plan review Controller adjudication | 106 | `3659ef62964b195cda60d4c4d5e961214594076e75fc0a52adcda4f076493f4f` |
| `dayu/fins/downloaders/hkexnews_downloader.py` | 1065 | `8c7c1a3b8e1aebc91ec82756754eb7894d6748471b69ce164a9798b260f5eb31` |
| `tests/fins/test_hkexnews_downloader.py` | 1213 | `d98266b8016e47a5ba4f77d680196b373933f71b184e559b2b483bd76f9de1d9` |
| `tests/fins/test_cn_download_workflow.py` | 1660 | `c2d86d4778002d904df40ab0c5ac67660683e76ea989a692d917650aa09b1e1f` |
| `dayu/fins/pipelines/cn_download_protocols.py` | 227 | `a92f283c0284aa1fce77031d73faf3cf9b37f6438b52b91b1cd317c26a6c003e` |
| `dayu/fins/pipelines/cn_download_workflow.py` | 806 | `3c27e009897c4c6030520f891f38648876cf3dd6a26c14d27f7ae50473f3c24f` |
| `dayu/fins/downloaders/cninfo_downloader.py` | 835 | `baab2ae471fc3f8201fc8bf97447c3fa647abd7dc25788d496d135a82f829d07` |
| `tests/fins/test_cninfo_downloader.py` | 1397 | `92e518f52401b0106c7726a7984b0d90c18cb58aba41aee7470c23864ce15399` |
| `tests/fins/test_cn_pipeline.py` | 718 | `7f00b257ecc7d128218aeca2505ea8cb6e3f89f624d58c3a8c734e8edf5189ee` |
| `tests/fins/test_cn_download_runtime.py` | 704 | `b37a4a86c607f57982536097a16b58a4297b1fcb4d99e406db49e4ec7dc95ba9` |
| `dayu/fins/README.md` | 791 | `2f94d7b7efb880063cb75ed6c8e5a7740d117761ec66a969c73bd754a3d14d76` |
| `tests/README.md` | 293 | `993ae9ce210625214a3ec4d621111e26e21c327c20cc1987636bcdc818b580c3` |

R10 pre-fix plan、双路 review 与 Controller adjudication 是本次 plan-fix 的 immutable evidence locks；pre-fix plan
路径已被本 fixed plan 替换，不要求也不允许再伪造旧 SHA。fixed plan 的新 lines/SHA 由 Codex fix artifact 与后续
Controller validation 锁定。进入 implementation 前必须重算 production/test/README implementation-input locks；
Controller 自有文件可因 gate transition 合法变化，但任何 production/test/README source drift 都必须停止并重新
裁决，不得在未知新基线上机械套用本计划。

## 3. Goal、success signal 与 non-goals

### 3.1 Goal

让 `dayu/fins/downloaders/hkexnews_downloader.py` 成为 HKEX title search 官方 cumulative
`rowRange`、严格响应协议与 completeness proof 的唯一 owner：从 100 开始，使用完全相同的业务查询扩大累计
range，直到当前 snapshot 被 provider 明确且一致地证明完整；任何 invalid/stalled response typed fail，任何取消
都不得把 partial snapshot 返回为 complete。

### 3.2 Success signals

1. 首轮恰好 100 条且官方字段证明 complete 时正常返回，不再因“100”本身失败。
2. `hasNextRow=true` 时按 `max(current_range * 2, recordCnt)` 发起下一次累计请求，除 `rowRange` 外所有
   query/sort/date/filter 参数 byte-for-byte 等价。
3. 每次响应替换上一 snapshot；只有最终 complete snapshot 进入 announcement parsing/selection，绝不 append
   overlapping prefix，也不靠 dedup 掩盖 append。
4. 只有 `hasNextRow=false` 且 `loadedRecord == recordCnt == len(rows)` 才返回 complete。
5. 官方字段缺失、严格类型错误、负值、bool 冒充整数、字段矛盾或扩大 range 后无 provider progress 时抛
   provider-owned typed protocol error。
6. `recordCnt` 在续取中增长时使用最新事实继续；不冻结第一次总数。
7. workflow 对 raw checker 的 bool true、主动 typed cancel 与非取消 failure 做唯一解释，并把同一个
   no-arg `cancellation_checkpoint` 原样传入 discovery；HKEX 每个 cumulative GET、CNInfo 每个既有 fiscal-period
   POST 前和响应返回后各调用一次。取消不启动下一 provider request、不做 HEAD、不发布 partial candidates。
8. focused workflow、full Fins、full pyright、scoped Ruff、每个 modified production file coverage `>=80%`、
   diff/scans 全部通过。

### 3.3 Non-goals / forbidden design

- 不实现 hard cap、固定最大累计条数、speculative range watchdog/warning/阈值、日期窗口递归、offset/page-number、
  page append、append 后 dedup、generic pagination/cursor framework 或第二 completeness checker。
- 不允许 generic total aliases、per-row `TOTAL_COUNT`、字符串/float count coercion、loose parsing、fallback、
  compatibility alias/wrapper 或旧 `HkexnewsDiscoveryTruncatedError` 兼容出口。
- 不把 query、sort、date、filter 或 final completeness 下移到 CN/HK selection、workflow、storage、Service、CLI、
  Host、Engine 或 UI。
- 不改 R06 transaction、R07 storage snapshot、R08 financial/XBRL、R09 direct-stream validator。
- 不进入 R11/R12，不实现 Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9 或统一 authorization。
- 除本轮必要的显式 no-arg cancellation checkpoint 参数外，不新增 public schema、provider profile、通用
  callback/factory/cancellation framework、通用 retry runtime 或新配置项。
- 不重新设计 announcement 业务筛选、语言策略、财期推断、同 period/year selection、PDF download 或 HEAD policy。

## 4. Semantic ownership 与 exact implementation allowlist

### 4.1 Owner map

| Semantic fact | 唯一 owner | Consumer |
|---|---|---|
| HKEX official response parse、cumulative state、progress、complete/error decision | `hkexnews_downloader.py` | CN/HK workflow 只消费 candidates 或 typed failure |
| raw operation `cancel_checker` 的 bool true、主动 typed cancel、非取消 failure 解释与业务可读消息 | 既有 `cn_download_workflow.py` 的 `_raise_if_cancelled` 语义 | workflow 构造 no-arg checkpoint；provider 不解释 raw checker |
| 单次 discovery 使用的 `cancellation_checkpoint` 对象、生命周期与 identity | 既有 CN/HK workflow | shared discovery protocol 原样运输同一对象 |
| checkpoint transport signature | `cn_download_protocols.py` | HKEX/CNInfo downloader 只调用或传播，不读取返回值、不捕获后改义 |
| provider I/O boundary 的 checkpoint ordering | 对应 HKEX/CNInfo downloader | HKEX 每个 cumulative GET、CNInfo 每个既有 fiscal-period POST 前/后调用 |
| raw announcement 到财报 candidate 的筛选/财期/去重 | 既有 `cn_report_selection.py` | 不变 |
| HTTP retry/throttle/timeout | 既有 HKEX downloader HTTP helper | 不变 |
| README 当前能力说明 | 对应 README | 不产生业务事实 |

`cn_download_workflow.py` 保留 discovery 方法调用前后的既有 `_raise_if_cancelled` 检查；当 raw checker 非空时，
workflow 使用 `functools.partial(_raise_if_cancelled, module=..., ticker=..., document_id="",
cancel_checker=cancel_checker)` 把同一 helper 的调用上下文绑定为一个 no-arg checkpoint，并把该对象传给 discovery；
raw checker 为空时传 `None`。这是同步 provider 内部无法直接观察 workflow 状态的必要直接参数，不是 generic
callback/factory；不得改用新的 helper 复制 bool/异常解释。
`cn_download_protocols.py` 只声明并运输 `Callable[[], None] | None`；二者都不得读取 HKEX fields、计算 range 或判断
complete。`cninfo_downloader.py` 必须同步接受 checkpoint，并在每个已有 supported fiscal period POST 前、响应返回后
各调用一次，以保持 structural typing 与真实 I/O 边界语义；这既不是 CNInfo pagination redesign，也不改变其 period
iteration、query、selection、retry 或业务错误语义。

### 4.2 Exact allowlist

Implementation 只允许修改/新增以下路径：

**Production**

- `dayu/fins/downloaders/hkexnews_downloader.py` — R10 唯一 provider-protocol 业务 owner；每个 cumulative GET 前/后
  调用 checkpoint，并按 §5.3 保留 typed cancellation/provider error precedence。
- `dayu/fins/pipelines/cn_download_protocols.py` — 仅给 `list_report_candidates(...)` 增加 keyword-only
  `cancellation_checkpoint: Callable[[], None] | None = None` 直接参数并更新中文 contract docstring；protocol 不调用、
  不解释 raw checker。
- `dayu/fins/pipelines/cn_download_workflow.py` — 保留既有 discovery 前后检查；用既有 `_raise_if_cancelled` 语义
  构造一次 no-arg checkpoint 并原样传给 discovery；不判断 HKEX fields，不按 market 特判，不新建取消解释 helper。
- `dayu/fins/downloaders/cninfo_downloader.py` — 仅完成同一 protocol 签名，并在现有 discovery request 前后
  调用 checkpoint；这里的 request 精确指每个已有 supported fiscal-period POST，不是整个方法入口/出口。不得改变
  CNInfo query、period iteration、分页、筛选、HTTP retry 或业务错误语义。

**Tests / captured fixture**

- `tests/fins/test_hkexnews_downloader.py`
- `tests/fins/test_cn_download_workflow.py`
- `tests/fins/test_cninfo_downloader.py`
- `tests/fins/test_cn_pipeline.py` — 只迁移两个 discovery test doubles 的显式 checkpoint 参数并断言透传；不得改
  pipeline 行为。
- `tests/fins/test_cn_download_runtime.py` — 只迁移 injected discovery test double 的显式 checkpoint 参数；不得改
  runtime 行为。
- `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json`（新增；只保存公开、非敏感、可审计的官方
  title-search 小响应及 request/capture metadata，不保存 cookie/auth/header）。

**README**

- `dayu/fins/README.md`
- `tests/README.md`

Response model 必须保持 downloader-private，因此不修改 `cn_download_models.py`。除 gate 自身按 Phaseflow 另行
授权的 implementation/review artifacts 与 Controller control transition 外，任何其它 tracked path 出现 diff 都
立即 stop。当前 plan gate 本身不授权上述 implementation changes。

## 5. Typed response model、strict parser 与 error owner

### 5.1 Provider-private model

在 `hkexnews_downloader.py` 用 frozen module-private dataclass 表示单轮已验证 snapshot；至少包含：

- `requested_row_range: int`：本轮请求值，由客户端状态产生；
- `response_row_range: int`：官方 top-level `rowRange`；
- `has_next_row: bool`：官方 top-level `hasNextRow`；
- `loaded_record: int`：官方 top-level `loadedRecord`；
- `record_count: int`：官方 top-level `recordCnt`；
- `rows: tuple[dict[str, JsonValue], ...]`：官方 top-level `result` 字符串解码得到的 row objects。

不得把它放进 shared CN/HK domain models；CNInfo 与 selection 不消费该 provider protocol。

### 5.2 Strict parsing

Parser 必须接受当前 HTTP helper 返回的 `JsonValue`，并执行以下 exact contract：

1. top-level 必须是 dict；`hasNextRow`、`rowRange`、`loadedRecord`、`recordCnt`、`result` 全部必填。
2. `hasNextRow` 只接受 JSON bool；字符串 `"true"`、整数 `0/1`、null 全部拒绝。
3. `rowRange`、`loadedRecord`、`recordCnt` 只接受 JSON int 且非负；由于 Python `bool` 是 `int`
   子类，必须先显式拒绝 bool。字符串数字、integral float、non-integral float、null、负值全部拒绝。
4. `result` 只接受官方实际形态：字符串化 JSON array。空字符串、malformed JSON、解码后非 list 或 list 中
   任一非-object row 全部 typed fail；不得回退到 generic `_extract_json_rows(...)` aliases。
5. `response_row_range` 必须等于本轮 `requested_row_range`；否则 provider 没有证明它执行了当前累计请求。
6. 每轮必须满足 `loadedRecord == len(rows)`、`loadedRecord <= recordCnt`、
   `loadedRecord <= requested_row_range`。
7. `hasNextRow=true` 必须满足 `loadedRecord < recordCnt`；`hasNextRow=false` 必须满足
   `loadedRecord == recordCnt == len(rows)`。

官方只读核对已观察到 `hasNextRow` 为 JSON bool，三个 range/count 字段为 JSON int，`result` 为字符串化
JSON array；该核对用于消除 parser 设计猜测，不替代 implementation gate 的 captured fixture 与 live smoke。

### 5.3 Typed error

- 用一个 provider-specific typed exception（计划名 `HkexnewsProviderProtocolError`）拥有 missing/type/
  negative/contradiction/no-progress failures。
- 删除 `HkexnewsDiscoveryTruncatedError`，不得 re-export、alias、subclass 或 wrapper 保留旧名字。
- HKEX `list_report_candidates(...)` 的 exception precedence 必须显式为：先分别
  `except CnDownloadCancelledError: raise` 与 `except HkexnewsProviderProtocolError: raise`，再进入 generic
  `except RuntimeError as exc` wrapper。前两个分支必须保持原对象 identity/type/cause，不得被
  `RuntimeError("披露易公告分类查询失败...")` 抹平；普通 HTTP/JSON transport failure 继续走现有 retry 与
  RuntimeError propagation。
- 错误消息只包含业务可读 provider/query context、失败字段与 count/range facts；不得包含 raw response、完整 rows、
  cookie/header、本地 path、authorization 信息或 generic internal governance id。
- checkpoint 返回即继续、抛出即传播；provider 不读取返回值、不调用 raw checker、不解释 bool，也不复制
  `_is_cancel_requested` / `_raise_if_cancelled`。取消使用既有 `CnDownloadCancelledError` 控制流，调用方主动抛出的
  同一取消对象必须跨 protocol/HKEX generic wrapper 保持 identity。raw checker 自身的非取消故障只由 workflow
  既有语义包装为带直接 cause 的 RuntimeError；provider 不把它归类为 provider protocol failure。若 HKEX 的
  generic provider-context wrapper 再包装该 RuntimeError，测试必须断言完整 cause chain 仍指向 workflow wrapper
  与原始 checker failure，不得用字符串识别或额外兼容类型绕过。
- CNInfo 的 checkpoint 调用必须位于现有 period transport `RuntimeError` wrapper 之外，或用
  `except CnDownloadCancelledError: raise` 把 typed cancel 放在 generic wrapper 之前；不得把取消改写成“巨潮公告
  分类查询失败”。

必须删除：`_HkexnewsRowsPage.total_count`、`_extract_title_search_total_count`、
`_coerce_non_negative_int`、八个 generic total aliases、`_raise_if_title_search_truncated`、
`_HKEXNEWS_ROW_LIMIT`/`_HKEXNEWS_ROW_RANGE` 的“固定上限”命名与 100 即失败分支。100 只保留为有业务名称的
initial cumulative range constant。

## 6. Cumulative algorithm 与 invariants

### 6.1 Query invariance

每个 language/category 先构造一次 immutable base params，包含：

`lang/category/market/stockId/searchType/documentType/t1code/t2Gcode/t2code/fromDate/toDate/MB-Daterange/
sortByOptions/sortDir`。

每轮只从 base params 派生新 dict 并写入 `rowRange=str(current_row_range)`。不得在循环中重新推断、规范化或
改变 language、stock、category、sort、from/to date 或 filter。测试必须把每轮 params 去除 `rowRange` 后做
exact equality，并断言只出现一个 `rowRange` 值。

### 6.2 State machine

单个 language/category 的算法固定为：

```text
current_range = 100
previous_continuation_loaded = None

loop:
    if cancellation_checkpoint is not None:
        cancellation_checkpoint()
    response = GET(same base params, rowRange=current_range)
    if cancellation_checkpoint is not None:
        cancellation_checkpoint()
    snapshot = strict parse + same-round invariants

    if snapshot.has_next_row is false:
        require loadedRecord == recordCnt == len(rows)
        return snapshot.rows

    require loadedRecord < recordCnt
    if previous_continuation_loaded is not None:
        require loadedRecord > previous_continuation_loaded

    previous_continuation_loaded = loadedRecord
    current_range = max(current_range * 2, snapshot.record_count)
```

进一步约束：

- `recordCnt` 不缓存为第一次总数。每轮用最新值计算 next range；增长场景必须继续，不能截断到旧总数。
- 在 `hasNextRow=true` 的连续响应间，`loadedRecord`（也即 rows 长度）必须严格增加；只有 requested range 或
  `recordCnt` 增长而 loaded rows 不增加，属于 no-progress typed fail。这样保证有限失败，不会用无限 doubling
  掩盖 provider 拒绝返回。
- terminal complete 优先于跨轮 progress 比较：如果最新 snapshot 因 provider 数据变化而以内部一致的
  `hasNextRow=false` 完成，使用该最新 complete snapshot；不要求历史 rows/count 单调。
- 不比较 row identity、不要求旧 rows 是新 rows 的 exact prefix，也不在本地 dedup。相同稳定 query 下新公告
  可插入或记录可撤回；唯一权威结果是最后一次完整 snapshot。
- 每轮赋值 `latest_rows = snapshot.rows`，不使用 `extend`/`+=`。只有 complete 后才把 final rows 交给
  `_parse_announcement(...)`、stock match 与 selection，因此 partial rows 不触发 HEAD，也不进入 candidate。
- “GET 前/响应后”按一次 cumulative semantic request 计数：checkpoint 紧邻现有 `_http_get_json(...)` 调用前，且仅在
  helper 成功返回响应后、strict parse 前再次调用。现有 helper 内部 retry 次数/退避保持不变；retry exhaustion 没有
  成功响应，因而不伪造 after-response checkpoint。任一 checkpoint 抛出后不得 parse 当前/历史 partial rows、进入
  下一 language/category 或做 HEAD。
- next range 只能使用上述公式；不得加 fixed cap、日期 recursion、sleep-based retry state 或第二 cursor。

### 6.3 Cancellation seam

共享 protocol 的 `list_report_candidates(...)` 新增 keyword-only
`cancellation_checkpoint: Callable[[], None] | None = None`。workflow 在 raw checker 非空时只构造一次该 no-arg
checkpoint，并把同一个对象原样传入 discovery；checkpoint 每次调用都复用既有 `_raise_if_cancelled`，所以只有
workflow 解释 bool true、调用方主动 typed cancel 与非取消 failure。raw checker 为空时 checkpoint 为 `None`。
workflow 原有 discovery 方法前/后 `_raise_if_cancelled` 检查保留。

HKEX downloader 在每个 cumulative GET 前和成功响应后各调用一次同一 checkpoint。CNInfo 在每个已有 supported
fiscal-period POST 前和成功响应后各调用一次同一 checkpoint：两个 supported periods 的正常 exact trace 是
`checkpoint, POST(period_1), checkpoint, checkpoint, POST(period_2), checkpoint`，不是只在整个方法入口/出口各
一次。provider 只把“正常返回”理解为继续、把“抛出”原样向上传播；不得出现 `if checkpoint(): ...` 或任何 raw
bool 解释。这只是 cancellation transport contract，不给 CNInfo 引入 HKEX state machine。

取消检查不得：

- 写入 query extra payload；
- 存进 `CnReportQuery`；
- 使用 `ContextVar`、thread/task identity、全局变量或 mutable client setter；
- 通过 `isinstance(HkexnewsDiscoveryClient)` 或 market 分支从 workflow 调私有方法；
- 只在测试 constructor 注入而 production 永远传 `None`。

## 7. 单 slice implementation specification

### R10-S1 — Exact official cumulative discovery closure

**Objective**：在同一 pass 内完成 explicit cancel seam、HKEX strict response/state machine、旧 generic/truncated
删除、owner tests、workflow propagation、captured fixture、README 和全部验证。

**Prerequisites**：

- Controller 接受 §4.2 的 exact allowlist，特别是 direct upstream cancel seam；
- 所有 production/test/README locks 无未知 drift；
- staged tree empty，Controller-owned dirty paths 所有权仍清晰。

**Exact changes**：

1. 先改 shared protocol/workflow/CNInfo 的最小显式 no-arg checkpoint seam：workflow 绑定既有
   `_raise_if_cancelled`，protocol 只运输，CNInfo 在每个 fiscal-period POST 前/后调用；补 exact request/checkpoint
   sequence、identity/cause 与 partial-no-publication 测试，不触碰任何 pagination/selection behavior。
2. 在 HKEX owner 内建立 private typed snapshot、strict field/parser helpers、provider protocol error 与 cumulative
   fetch loop；复用现有 `_http_get_json` retry/throttle。
3. 让每个 language/category 独立完整续取，complete 后才 parse rows；language/category 之间既有汇总保持不变。
4. 删除 generic total/truncated/cap semantics 和旧测试；不保留 compatibility。
5. 增加 local deterministic owner tests、direct workflow propagation、captured official shape fixture 与 README 同步。
6. 执行 §10 全矩阵；任何失败必须在 allowlist 内修 root cause，不能放宽 parser/progress/coverage。

**Expected outcome**：所有 HKEX candidates 都来自同一 query 的最后完整 cumulative snapshot；invalid/stalled/
cancelled/HTTP failure 都不能投影 partial complete。

**Slice stop**：完成 validation 后停在 `READY_FOR_DUAL_CODE_REVIEW`，不得 commit、push、PR、aggregate、R11。

## 8. Owner-level test matrix

所有 deterministic tests 使用 `httpx.MockTransport`；不得在默认 pytest 中访问网络。fixture builder 必须生成
官方 exact top-level keys/types，旧 `{result: ...}`、generic `total` fixture 全部迁移或删除。

取消测试必须记录单一 ordered event log，而不是只断言最终异常。记 `CPn` 为同一 checkpoint 对象第 n 次调用、
`GET(r)` 为 HKEX cumulative request、`POST(p)` 为 CNInfo fiscal-period request。每个测试同时断言 exact sequence、
request count/params、checkpoint object identity、exception identity 或 direct/full cause chain，以及取消/失败后没有
partial rows/candidates/HEAD publication。workflow mapping 测试需让 raw checker 首次在既有 discovery-pre 检查返回
false，再在 fake discovery 调用收到的 checkpoint 时返回 true/抛异常，从而证明被测的是 workflow-owned
checkpoint，不是调用前已有检查。

| Case | Setup | Required assertions |
|---|---|---|
| checkpoint normal return | 同一 recording checkpoint 始终返回 `None`；HKEX 一轮 complete | exact `CP1, GET(100), CP2`；两次均为同一对象；正常继续且只发布 final rows |
| exact 100 complete | 100 raw rows；`rowRange=loadedRecord=recordCnt=100`；`hasNextRow=false` | exact `CP1, GET(100), CP2`；无 100 failure；只使用 final rows |
| two-round cumulative | first `100/150/true`，second requested 200 and `150/150/false` | exact `CP1, GET(100), CP2, CP3, GET(200), CP4`；ranges `100,200`；all non-range params exact equal；final-only behavior |
| formula recordCnt branch | first `100/350/true` | second range exact `350`，不是固定 `200` |
| multi-round count growth | `100/150/true` -> at range 200: `200/350/true` -> at range 400 complete | ranges `100,200,400`；使用最新 350；有限完成 |
| overlapping/replacement | first 与 final 有重叠，同时 first-only row 在 final 消失 | 返回只反映 final snapshot；first-only candidate/HEAD 不出现；不能靠 downstream dedup 隐藏 append |
| final no duplicate | final snapshot 中每个目标 row 唯一 | candidate/source/HEAD 只出现一次；无 prefix append duplicate |
| query invariance | 两轮或多轮 capture params | 去除 `rowRange` 后 dict exact equality；date/sort/category/filter 全不变 |
| missing fields | 对五个 required top-level fields 逐一删除 | 每个都抛同一 typed provider protocol class，message 指出 field/reason |
| hasNext type | string/int/null/list/dict | 全拒绝；只有 exact bool 接受 |
| count/range type | string、bool、integral float、fractional float、null、list | 全拒绝；只有非负 exact int 接受 |
| negative fields | `rowRange/loadedRecord/recordCnt` 各负值 | typed fail，无下一请求 |
| rows type | `result` 非 string、malformed、解码非 list、row 非 object | typed fail，不回退 generic row aliases |
| same-round contradictions | response range != requested；loaded != len；loaded > count；loaded > range；true 且 loaded == count；false 且三数不等 | typed fail，事实不进入 selection |
| no progress | 首轮 true 后扩大 range，下一轮仍 true 且 loaded/len 未增加；可令 recordCnt 增长 | 第二轮立即 typed fail；request count 有上界；不继续 doubling |
| count change terminal | 续取时最新 count 缩小但 response 自洽 complete | 接受最新完整 snapshot，不拼旧 rows |
| workflow bool true mapping | raw checker 在 workflow discovery-pre 返回 false，fake discovery 调用收到的 checkpoint 时返回 true | workflow 产生 `CnDownloadCancelledError`；fake 收到 no-arg checkpoint 而非 raw checker；zero provider HTTP/candidates/HEAD |
| caller typed cancel identity | raw checker 在 checkpoint 调用时主动抛预构造 `CnDownloadCancelledError` | `exc.value is expected_cancel`；跨 workflow/protocol/HKEX typed passthrough identity 不变；无 publication |
| cancel before first GET | `CP1` 抛 typed cancel | exact `CP1`；zero HTTP；原取消对象保持；无 rows/candidates/HEAD |
| cancel after response | `CP1` 返回、`GET(100)` 返回 partial、`CP2` 抛 typed cancel | exact `CP1, GET(100), CP2`；不 strict-parse/publish partial，不发下一 range；无 HEAD |
| cancel before later round | first partial round 两次 checkpoint 返回，`CP3` 抛 typed cancel | exact `CP1, GET(100), CP2, CP3`；只有第一 GET；无 partial complete/HEAD |
| cancel after final round | final response 后 checkpoint 抛 typed cancel | exact `CP1, GET(100), CP2`；即使响应完整也不 parse/return candidates；取消优先 |
| checker non-cancel failure | raw checker 在 fake discovery 调用 checkpoint 时抛预构造非取消异常 | workflow-owned RuntimeError 的 direct `__cause__ is expected_failure`；若经过 HKEX generic wrapper则断言 exact 两层 cause chain；不误报 provider protocol、不发后续 request/HEAD |
| HKEX exception precedence | category query 分别抛 typed cancel、带 cause 的 provider protocol error、ordinary RuntimeError | 前两者在 generic wrapper 前原样通过（cancel identity、protocol type/cause）；只有 ordinary RuntimeError 获得既有 provider-context wrapper |
| HTTP initial failure | 503/timeout/JSON decode 按 max retries 失败 | 既有 RuntimeError/cause；无 candidates |
| HTTP later failure | 首轮 true，后续请求 retry exhaustion | 不返回首轮 partial；无 HEAD；错误传播 |
| per-language isolation | zh/en 各有自己的 cumulative rounds | 每个 language 从 100 开始且 query invariance 独立；不共享 count/range |
| CNInfo checkpoint sequence | 两个 supported fiscal periods，checkpoint 全部正常返回 | exact `CP1, POST(p1), CP2, CP3, POST(p2), CP4`；POST params/order 与 baseline 相同；selection/HEAD 只在全部 responses 通过 checkpoint 后发生 |
| CNInfo response cancel | first period POST 返回后 `CP2` 抛 typed cancel | exact `CP1, POST(p1), CP2`；不发 `POST(p2)`；取消 identity 不被 period RuntimeError wrapper 改写；无 partial candidates/HEAD |
| CNInfo before-next cancel | first period response 后 `CP2` 返回、第二 period 前 `CP3` 抛 | exact `CP1, POST(p1), CP2, CP3`；只有一个 POST；无 partial publication |
| injected test doubles | pipeline/runtime 的 CN/HK discovery fakes 接受同一 keyword-only checkpoint | structural typing 通过；fake 只调用/记录 checkpoint，不解释 raw bool 或吞掉异常 |
| workflow propagation | fake/real HK discovery 记录 checkpoint identity并主动调用；provider protocol failure/cancel | workflow 每次 discovery 只构造/传一个 no-arg checkpoint；raw checker 不跨 protocol；protocol failure 为 failed 而非 candidate-not-found；取消仍是 cancelled |

旧测试必须删除/改写：满 100 缺 generic total 即失败、`total==100` 接受、`total>rows` truncated、integral float
total 接受、invalid float 回退到“无法证明完整”。不得保留这些断言再加 compatibility branch。

## 9. Auditable captured fixture 与 official endpoint smoke

### 9.1 Captured fixture owner

`tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` 由 HKEX owner test 持有，只证明官方 public
response shape/type，不成为动态总数或业务内容真源。文件必须包含：

- `captured_at_utc`；
- endpoint；
- 完整非敏感 request params；
- HTTP status；
- raw response body SHA-256；
- raw JSON response（使用一个小结果查询，保持 provider 原值）；
- capture tool/version 说明。

生成时只做 public GET；不得保存 cookies、authorization、request/response headers、代理凭据或本地路径。测试读取
raw JSON response 交给同一 strict parser，并断言实际字段类型。fixture 若与当前 live response 类型冲突，立即 stop
并取证，不得增加 loose dual-type parser。

### 9.2 Local fixture gate

默认测试必须同时覆盖：

- captured small official shape replay；
- 程序化 100、两轮、多轮、count growth、矛盾/no-progress fixtures。

live endpoint 不可用不能跳过或替代此 gate。

### 9.3 Non-destructive official endpoint smoke

implementation validation 运行一次 opt-in、非默认、只读 smoke：

1. 仅向 `HKEXNEWS_TITLE_SEARCH_URL` 发 GET；不下载 PDF、不调用 mutation endpoint、不写 workspace business data。
2. 选择并在 evidence manifest 中记录一个首轮 `recordCnt > 100` 的公开 title-search query；不能把当次确切总数
   写成 production constant。
3. 从 `rowRange=100` 开始，按生产公式逐轮 GET；每轮保存 normalized request params、HTTP status、
   `rowRange/loadedRecord/recordCnt/hasNextRow/len(rows)` 与 raw body SHA-256 到
   `workspace/tmp/wu-semantic-ownership-01-r10-hkex-smoke/`。
4. manifest 自动证明：非 range params 每轮完全相同；requested ranges 符合公式；至少两轮；final
   `hasNextRow=false` 且三数相等；consumer 只采用 final rows。
5. 控制请求间隔，复用 production timeout/User-Agent/retry policy；不并发轰击 endpoint。
6. implementation artifact 报告 query、轮数、字段摘要、raw hashes 与 manifest path，不粘贴大量公告正文。

外部端点 DNS/网络/challenge/限流不可用时，记录环境限制；local captured/deterministic protocol gates 仍必须通过。
若 endpoint 可达却证明扩大 `rowRange` 仍被硬 cap、response range 被 clamp、或持续 true 且 loaded 无增长，按
§12 stop，不把 smoke failure 改造成日期递归。

## 10. Validation matrix

所有命令先执行：

```bash
source .venv/bin/activate
```

### 10.1 Focused owner / seam / workflow

```bash
pytest -q \
  tests/fins/test_hkexnews_downloader.py \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_cn_download_runtime.py

pytest -q \
  tests/fins/test_hkexnews_downloader.py \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_cn_download_workflow.py \
  -k 'hkex or cninfo or rowRange or cumulative or complete or protocol or cancel or checkpoint or http'
```

### 10.2 Full Fins regression

```bash
pytest -q tests/fins
```

任何 existing environment skip 必须逐项说明；任何 failure 先在 baseline commit 复现并按 umbrella baseline registry
归因。不得仅因“看起来 pre-existing”而忽略。

### 10.3 Per-file coverage `>=80%`

```bash
coverage erase
coverage run --branch --data-file=workspace/tmp/.coverage-r10 -m pytest -q \
  tests/fins/test_hkexnews_downloader.py \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_cn_download_runtime.py
coverage report --data-file=workspace/tmp/.coverage-r10 \
  --include=dayu/fins/downloaders/hkexnews_downloader.py --fail-under=80
coverage report --data-file=workspace/tmp/.coverage-r10 \
  --include=dayu/fins/downloaders/cninfo_downloader.py --fail-under=80
coverage report --data-file=workspace/tmp/.coverage-r10 \
  --include=dayu/fins/pipelines/cn_download_protocols.py --fail-under=80
coverage report --data-file=workspace/tmp/.coverage-r10 \
  --include=dayu/fins/pipelines/cn_download_workflow.py --fail-under=80
```

每条必须独立 `>=80.00%`；不得用 aggregate 百分比、omit、pragma 或 test-only dead code padding绕过。
Controller 在 locked baseline 已用同一 focused set precheck：
`dayu/fins/pipelines/cn_download_protocols.py  Stmts 40  Miss 0  Branch 0  Cover 100%`。因此四个文件仍各自
`>=80%`，protocol 文件没有 N/A waiver；不得添加 waiver、omit、pragma 或 padding。

### 10.4 Full type / scoped lint / diff

```bash
python -m pyright dayu/ tests/ utils/
python -m ruff check \
  dayu/fins/downloaders/hkexnews_downloader.py \
  dayu/fins/downloaders/cninfo_downloader.py \
  dayu/fins/pipelines/cn_download_protocols.py \
  dayu/fins/pipelines/cn_download_workflow.py \
  tests/fins/test_hkexnews_downloader.py \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_cn_download_runtime.py
git diff --check
```

pyright 必须 0 errors；不得新增、扩散、ignore 或掩盖类型错误。

### 10.5 Diff / source / ownership scans

```bash
git diff --name-only 1c2585275f4134d8456a3fda2d84464e4e52c9d7 -- \
  dayu/fins tests/fins dayu/fins/README.md tests/README.md

rg -n '_raise_if_title_search_truncated|_extract_title_search_total_count|_coerce_non_negative_int|HkexnewsDiscoveryTruncatedError' \
  dayu/fins tests/fins

rg -n 'totalCount|total_count|recordCount|record_count|recordsTotal|records_total' \
  dayu/fins/downloaders/hkexnews_downloader.py tests/fins/test_hkexnews_downloader.py

rg -n 'hasNextRow|loadedRecord|recordCnt|rowRange|HkexnewsProviderProtocolError' \
  dayu/fins/downloaders/hkexnews_downloader.py tests/fins/test_hkexnews_downloader.py

rg -n 'cancel_checker|cancellation_checkpoint|Callable\[\[\], None\]' \
  dayu/fins/pipelines/cn_download_protocols.py \
  dayu/fins/pipelines/cn_download_workflow.py \
  dayu/fins/downloaders/hkexnews_downloader.py \
  dayu/fins/downloaders/cninfo_downloader.py \
  tests/fins/test_hkexnews_downloader.py \
  tests/fins/test_cninfo_downloader.py \
  tests/fins/test_cn_download_workflow.py \
  tests/fins/test_cn_pipeline.py \
  tests/fins/test_cn_download_runtime.py

git diff --cached --name-only
git status --short
```

Expected：

- exact changed-path set 是 §4.2 的实际需要子集；无 Controller files、Service/CLI/Host/Engine/Web/WeChat/render。
- obsolete/generic scan 为零；注意 announcement raw row 可能合法包含 `TOTAL_COUNT`，但 production completeness
  不得读取它，review 需检查 call graph 而非用模糊 grep 误删 raw provider field。
- official field scan 只落在 HKEX owner/test/fixture；shared workflow 不读取这些字段。
- cancellation scan/AST review 证明 raw `Callable[[], bool]` 只由 workflow 解释；shared protocol/provider signature
  只运输 `Callable[[], None] | None`；provider 没有 `if checkpoint()`、bool 解释、duplicate helper 或异常字符串识别。
- request event logs 证明 HKEX 每个 cumulative GET、CNInfo 每个既有 fiscal-period POST 都是 before/after 两次同一
  checkpoint；response 后取消不发下一 request，任何 partial rows/candidates/HEAD 均未发布。
- AST/diff review 证明 cumulative loop 没有 rows `extend`/`+=`/dedup、没有 date recursion/hard cap、没有
  market-specific downstream branch。
- staged tree 始终 empty，直到 Controller 在后续 accepted commit gate 明确授权。

### 10.6 Deferred / forbidden scope scans

对最终 diff 执行 `git diff -U0` 内容审计，确认没有 Issue 142/151/175/177/178、R11/R12、Web/WeChat/render、
Topic 8/9、authorization/auth profile、storage transaction、direct-stream terminal 的实现或文档承诺。单纯历史文本
已有这些编号不应成为模糊全仓 grep 的 false positive；审计对象必须是 R10 changed hunks。

## 11. README 与 security decision

### 11.1 README

- `dayu/fins/README.md`：必须更新。当前 downloader architecture 说明属于其开发者读者职责；在现有
  CNInfo/HKEX downloader 段落补充 HKEX title search 使用官方 cumulative `rowRange`、final snapshot replacement
  与 strict completeness，不能写未来计划、测试清单或 WU 流水账。
- `tests/README.md`：必须更新。当前文本明确固化“HKEXNews 满页缺少完整性证明时 typed truncated failure”，已与
  新 owner contract 冲突；替换为 official fields、multi-round cumulative、contradiction/no-progress/cancel 覆盖说明。
- 根 `README.md`：不更新。CLI、安装、命令参数、工作区、用户 workflow、日志与排障方式没有变化。
- `dayu/README.md`：不更新。UI/Service/Host/Agent 分层与装配关系不变。
- design docs：不更新。`docs/fins/design.md` 已是本轮目标真源，当前 implementation 只落实既有裁决。

修改两个 README 前必须重新读取各自 update constraints；不得把 plan/future state 写成 current capability。

### 11.2 Security retention

R10 不是统一 authorization work，但必须保留当前局部安全/稳态机制：HTTP timeout、retry 上限、throttle、公开
HTTPS endpoint、PDF magic/size 校验、stock matching、error 不含 raw body/secret/local path。captured fixture/live
smoke 只用公开 GET，不保存 cookie/auth/proxy/header，不调用下载或 mutation endpoint。

不得因为 Topic 9 deferred 而删除这些边界；也不得借 R10 新增 permission schema、auth profile、DNS/egress framework
或 browser capability。

## 12. Stop conditions 与 residual ownership

遇到以下任一条件立即停止当前 gate，保留证据并交 Controller；不得自行扩设计：

1. source lock drift 导致本计划的 call path、protocol 或测试事实失效。
2. Controller 不接受 §4.2 的 direct upstream cancel seam。此时 downloader-only allowlist 无法真实满足每轮取消；
   禁止用 ambient/mutable/test-only 方案继续 implementation。
3. 官方 captured/live response 的 required field 名或严格 JSON 类型与本计划矛盾。停止并提交 raw hash/evidence；
   不加 alias、coercion 或 fallback。
4. 官方 endpoint 可达且证明扩大 `rowRange` 被 hard cap/clamp、连续 true 但 loaded 无增长，或必须用第二分页机制
   才能完成。记录 evidence-driven residual，owner/destination 为未来独立 HKEX provider WU/user decision；当前不做
   date recursion、offset 或 hard cap。
5. 正确实现需要修改 §4.2 外 production/test/README 路径，或需要下游 completeness checker。
6. focused/full Fins/pyright/Ruff/coverage/diff/scans 无法在 allowlist 内按 root cause 修复。
7. 与 Controller-owned dirty files 发生所有权重叠、staged tree 非空、或出现不明 working-tree change。
8. implementation/review 试图进入 R11/R12、Issue 142/151/175/177/178、Web/WeChat/render、Topic 8/9 或
   authorization。

外部 endpoint 单纯不可访问不是 local protocol gate blocker：记录环境限制后继续 local validation；但不得把“未
运行 live smoke”表述成真实 >100 官方验证通过。

## 13. Deferred gates 与 Gateflow handoff

本 plan gate 完成后固定顺序为：

```text
AgentCodex plan-only fix
-> READY_FOR_CONTROLLER_VALIDATION
-> Controller fixed-plan validation
-> AgentMiMo + AgentDS 对完整 fixed plan 双路 re-review
-> finding adjudication / plan fix / 双路 re-review（如仍需要）
-> accepted plan commit
-> R10-S1 implementation
-> 双路完整 code review
-> fix / 双路 re-review（如需要）
-> accepted implementation commit
-> R10 aggregate deepreview / fix / re-review
-> R10 completion / Controller closeout
-> 才可 handoff R11 独立 plan gate
```

当前只完成第一步并停在 `READY_FOR_CONTROLLER_VALIDATION`；不自行触发 Controller 或双路 re-review，不
stage/commit/push/PR，不更新 control，不 implementation，不进入 R11/R12。

## 14. Completion report format

R10-S1 implementation Agent 必须报告：

1. baseline HEAD、branch、所有 source locks 与 drift 结论；
2. exact changed paths，分别列 production/tests/fixture/README；
3. owner map 与 raw checker -> workflow-owned no-arg checkpoint -> protocol transport -> HKEX/CNInfo I/O boundary 的
   实际 call path、对象 identity 与 exact request/checkpoint trace；
4. typed model、strict field types、same-round contradictions、progress、formula、query invariance、snapshot replacement
   与 error/cancel precedence；其中必须报告 bool true mapping、caller typed cancel identity、non-cancel failure direct/full
   cause chain、HKEX typed exceptions 在 generic RuntimeError 前 passthrough；
5. obsolete symbols/测试删除清单；
6. 测试矩阵逐命令结果、HKEX/CNInfo exact request sequence、partial rows/candidates/HEAD zero-publication、full Fins、
   四个 modified production file 的逐文件 coverage（含 protocol 真实百分比且无 N/A waiver/padding）、full pyright、
   Ruff、diff/scans；
7. captured fixture provenance/body hash，live smoke query/轮次/fields/raw hashes/manifest path，或准确的外部环境限制；
8. README decision 与实际修改；
9. security retention、deferred/no-touch scan；
10. staged empty、git status、untracked artifacts 与 Controller-owned files 未触碰证明；
11. finding/residual 分类、stop status 与下一 gate；
12. 明确声明未 commit/push/PR、未进入 R11。

## 15. Plan completeness checklist

- [x] 同一 umbrella R10、非新 WU/issue/feature、单 slice。
- [x] 第一性原理动机、直接代码证据与唯一 HKEX owner 明确。
- [x] exact source locks、allowlist、Controller ownership 与 staged-empty 约束明确。
- [x] raw checker 只由 workflow 既有 `_raise_if_cancelled` 解释；显式 no-arg checkpoint 只由 protocol 原样运输，
  没有 ambient/test-only/downstream bool special case。
- [x] official fields 的 strict typed model/parser、bool/negative/type/missing/contradiction rules 明确。
- [x] initial 100、next range 公式、query invariance、count growth、progress 与 terminal condition 明确。
- [x] snapshot replacement、final-only parse、禁止 append/dedup/date recursion/hard cap 明确。
- [x] `CnDownloadCancelledError` / `HkexnewsProviderProtocolError` 在 generic RuntimeError 前 passthrough，
  identity/type/cause 与旧 contract 删除明确。
- [x] HKEX 每个 cumulative GET、CNInfo 每个 fiscal-period POST 前/后 checkpoint ordering 明确，workflow 原有
  discovery 前后检查保留。
- [x] 100 exact、两/多轮、overlap/no duplicate、count growth、矛盾/no-progress、request sequence、identity/cause、
  partial-no-publication、cancel/HTTP 测试矩阵明确。
- [x] captured fixture、non-destructive >100 official smoke、外部不可用与真实 cap stop 分流明确。
- [x] focused/workflow/full Fins/pyright/Ruff/四文件逐文件 `>=80%` coverage/diff/source/deferred scans 明确；protocol
  baseline 40/40、100%，无 N/A waiver/padding。
- [x] README、安全保留、Issues/Web/WeChat/render/Topic 8/9/auth no-touch 明确。
- [x] deferred gates、stop conditions 与 completion report 明确。

该方案没有过度设计：HKEX 累计协议只留在 provider-private model/state machine；workflow 仅把既有取消语义绑定为
一个必要的 no-arg checkpoint，shared protocol 只运输，provider 只在真实 request boundary 调用；没有新增通用分页/
cancellation 抽象、配置、durable state、schema、第二 completeness owner、speculative range watchdog 或 provider cap
机制。当前状态：`READY_FOR_CONTROLLER_VALIDATION`。
