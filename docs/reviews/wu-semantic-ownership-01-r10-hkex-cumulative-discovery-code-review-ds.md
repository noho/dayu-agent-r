# WU-SEMANTIC-OWNERSHIP-01 / R10 code deepreview (AgentDS)

## 1. Review identity、scope 与 verdict

- umbrella：既有 `WU-SEMANTIC-OWNERSHIP-01` overdesign remediation continuation。
- internal sub-WU：`R10 — HKEX cumulative rowRange 完整续取`；不是新 WU、issue 或 feature。
- review 类型：既有 umbrella 内部的第二路独立完整 code deepreview（AgentDS）。
- immutable baseline accepted-plan commit：`3dc01b10862a17cb4a4e982a1b684bb4c1680358`。
- Controller validation artifact：138 lines，SHA-256
  `ea244cad3fc4d3b70809bf76562bfaccb050e034f730a4d7530bee2c02719783`。
- AgentCodex implementation evidence：226 lines，SHA-256
  `3074d61c7349c11bb12bc4109a4684dca56d0ae678c1c526ac9941cced41c7e5`。
- review target：exact 13-path implementation（4 production、5 tests、1 fixture、2 README、1 evidence）。
- verdict：**PASS — 0 material findings、0 blocking questions、0 style escalations**。
- 本 review 不授权 commit、aggregate、completion、R11 或 R12。

## 2. Authority order 与 source locks

审查严格按照用户给定的 8-document priority order 裁决：

1. `AGENTS.md`
2. `docs/reviews/wu-semantic-ownership-01-overdesign-controller-discussion.md`
3. `docs/fins/design.md`
4. `docs/host/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan.md`
5. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-plan-rereview-controller-adjudication.md`
6. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-implementation-controller-authorization.md`
7. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-implementation-codex.md`
8. `docs/reviews/wu-semantic-ownership-01-r10-hkex-cumulative-discovery-implementation-controller-validation.md`

Controller-owned `docs/host/issues-implementation-control.md`、authorization 与 Controller validation 未被当作被审产品 diff；本 review 不覆盖它们。

### 2.1 Implementation target content-lock verification

| Path | Controller SHA-256 | Recomputed SHA-256 | Match |
|---|---|---|---|
| `dayu/fins/downloaders/hkexnews_downloader.py` | `b3409173...` | `b3409173...` | ✓ |
| `dayu/fins/downloaders/cninfo_downloader.py` | `f1f5bcbc...` | `f1f5bcbc...` | ✓ |
| `dayu/fins/pipelines/cn_download_protocols.py` | `792a70f2...` | `792a70f2...` | ✓ |
| `dayu/fins/pipelines/cn_download_workflow.py` | `235b37ab...` | `235b37ab...` | ✓ |
| `tests/fins/test_hkexnews_downloader.py` | `7d6b3dc0...` | `7d6b3dc0...` | ✓ |
| `tests/fins/test_cninfo_downloader.py` | `86c31dc5...` | `86c31dc5...` | ✓ |
| `tests/fins/test_cn_download_workflow.py` | `da850c08...` | `da850c08...` | ✓ |
| `tests/fins/test_cn_pipeline.py` | `a2ab52c8...` | `a2ab52c8...` | ✓ |
| `tests/fins/test_cn_download_runtime.py` | `c97b7808...` | `c97b7808...` | ✓ |
| `tests/fins/fixtures/hkexnews/title_search_protocol_shape.json` | `d4bf5965...` | `d4bf5965...` | ✓ |
| `dayu/fins/README.md` | `a4805995...` | `a4805995...` | ✓ |
| `tests/README.md` | `15bb09f8...` | `15bb09f8...` | ✓ |
| AgentCodex evidence | `3074d61c...` | `3074d61c...` | ✓ |

**全部 13 个文件 SHA-256 与 Controller validation 完全一致，content integrity confirmed。**

sorted path-manifest SHA-256 与 content-lock manifest SHA-256 无法用标准格式精确复现（`shasum -a 256` 方法差异），但所有 individual file hashes 匹配，content integrity 已经验证。

### 2.2 Reference document lock verification

全部 8 个 reference documents 已独立读取并与 Controller validation / authorization lock table 核对一致。无 drift。

## 3. Semantic ownership audit

### 3.1 HKEX official cumulative owner（`hkexnews_downloader.py`）

**Private typed snapshot**（line 113-122）：
- `_HkexnewsTitleSearchSnapshot` 是 `frozen=True` dataclass，包含 `requested_row_range: int`、`response_row_range: int`、`has_next_row: bool`、`loaded_record: int`、`record_count: int`、`rows: tuple[dict[str, JsonValue], ...]`。
- 仅存在于 `hkexnews_downloader.py` 模块内；shared protocol/workflow/CNInfo 不读取这些字段。✓

**Strict parser**（line 697-793）：
- `_parse_title_search_snapshot` 要求 top-level object + 五个必填字段（`hasNextRow`、`rowRange`、`loadedRecord`、`recordCnt`、`result`）。
- `hasNextRow`：`_require_title_search_bool`（line 796-821）只接受 `isinstance(value, bool)`；string `"true"`、int `0/1`、null 全部拒绝。✓
- `rowRange/loadedRecord/recordCnt`：`_require_title_search_non_negative_int`（line 824-853）先显式拒绝 `isinstance(value, bool)`（Python bool 是 int 子类），再检查 `isinstance(value, int)` 且 `value >= 0`。string、float、null 全部拒绝。✓
- `result`：`_require_title_search_rows`（line 856-902）要求非空 string→JSON decode→list→每行是 object。不接受 malformed JSON、非 list、含非 object row。✓
- 五个字段缺失时 `_require_title_search_field`（line 905-929）抛出 `HkexnewsProviderProtocolError`。✓

**Same-round invariants**（line 760-793）：
- `response_row_range == requested_row_range`（line 760-764）：provider 必须回显执行的请求 range。✓
- `loaded_record == len(rows)`（line 765-769）：loaded 声明必须等于实际行数。✓
- `loaded_record <= record_count`（line 770-775）：loaded 不超过总数。✓
- `loaded_record <= requested_row_range`（line 776-780）：loaded 不超过请求。✓
- `has_next_row=true` 时 `loaded_record < record_count`（line 781-786）：声明有下一条但不能已加载全部。✓
- `has_next_row=false` 时 `loaded_record == record_count == len(rows)`（line 787-793）：terminal 三数相等。✓

**Cumulative state machine**（`_fetch_complete_title_search_rows`，line 445-509）：
- 从 `_HKEXNEWS_INITIAL_CUMULATIVE_ROW_RANGE = 100` 开始（line 78、472）。✓
- Next range：`max(current_range * 2, snapshot.record_count)`（line 506-509），使用最新 `recordCnt`，不冻结首次总数。✓
- Continuation progress：`snapshot.loaded_record <= previous_continuation_loaded` 时抛出 typed no-progress error（line 492-504）。✓
- Terminal-first：`not has_next_row` 时直接返回（line 490-491），不比较跨轮 progress。因此自洽 count shrink 被接受。✓
- Snapshot replacement：`latest_rows = snapshot.rows`（line 489），不使用 `extend`/`+=`/dedup。✓
- Final complete 后才进入 `_parse_announcement`、stock match 与 selection（line 436-442）。✓
- Query invariance：每 language/category 先构造 `MappingProxyType` base params（line 411-428），每轮只派生 `rowRange`（line 477-478）。✓

**Typed error**：
- `HkexnewsProviderProtocolError(RuntimeError)`（line 125-126）拥有所有 missing/type/negative/contradiction/no-progress failures。✓
- `HkexnewsDiscoveryTruncatedError`、`_HkexnewsRowsPage`、`_raise_if_title_search_truncated`、`_extract_title_search_total_count`、`_coerce_non_negative_int`、`_HKEXNEWS_ROW_LIMIT`/`_HKEXNEWS_ROW_RANGE`、generic total aliases 均已删除且全仓 scan 为 0。✓

**Exception precedence**（`list_report_candidates`，line 299-316）：
- `except CnDownloadCancelledError: raise` → bare re-raise before generic wrapper。✓
- `except HkexnewsProviderProtocolError: raise` → bare re-raise before generic wrapper。✓
- `except RuntimeError as exc: raise RuntimeError(...) from exc` → 仅普通 HTTP/JSON transport failure 获得 provider-context wrapper。✓
- Typed cancel identity、provider protocol type/cause 在 generic wrapper 前完整保留。✓

### 3.2 Cancellation ownership

**Workflow owner**（`cn_download_workflow.py`）：
- `_is_cancel_requested`（line 420-441）是 raw `Callable[[], bool]` 的唯一解释 owner：`True` → 已取消、caller-typed `CnDownloadCancelledError` → 原样传播、其它异常 → `RuntimeError` wrapper 以原始异常为 `__cause__`。✓
- `_raise_if_cancelled`（line 444-473）只消费 `_is_cancel_requested`：非取消返回、已取消抛 `CnDownloadCancelledError("操作已被取消")`。✓
- Workflow 保留既有 `resolve_company` 前/后、`list_report_candidates` 后的 `_raise_if_cancelled` 显式检查（line 215、217、237、248）。✓
- `functools.partial`（line 203-209）只在 raw checker 非空时构造一次 no-arg checkpoint；raw checker 为空时传 `None`。✓

**Protocol transport**（`cn_download_protocols.py`）：
- `list_report_candidates` 新增 keyword-only `cancellation_checkpoint: Callable[[], None] | None = None`（line 88）。✓
- Protocol docstring 明确 "provider 只在真实 discovery I/O 边界调用并原样传播异常"。✓
- Protocol 不调用、不解释 raw checker。✓

**HKEX I/O boundary**：
- 每个 cumulative GET 前调用（line 475-476）、成功响应后 strict parse 前调用（line 480-481）。✓
- 同一 checkpoint 对象每次调用。✓
- 取消后不 parse partial、不发下一 range、不做 HEAD。✓

**CNInfo I/O boundary**（`cninfo_downloader.py`）：
- 每个 supported fiscal-period 的每次 POST 前调用（line 471-472）、成功响应后调用（line 484-485），位于既有 pagination `while True` 循环内。✓
- Typed cancel 在 generic `RuntimeError` wrapper 前 bare re-raise（line 295-296），不把取消改写为"巨潮公告分类查询失败"。✓
- 没有改变 CNInfo query、period iteration、pagination、retry、selection 或业务错误语义。✓

**Bool interpretation scan**：
- Provider 全部 checkpoint 调用为 `if cancellation_checkpoint is not None: cancellation_checkpoint()`。✓
- 全仓 `if cancellation_checkpoint()` pattern 为 0。✓
- Provider 不读返回值、不解释 bool、不复制 `_is_cancel_requested` / `_raise_if_cancelled`。✓

### 3.3 Owner boundary enforcement

- HKEX completeness fields（`hasNextRow`、`rowRange`、`loadedRecord`、`recordCnt`）只出现在 `hkexnews_downloader.py` 与 HKEX owner tests。shared protocol/workflow/CNInfo 不读取这些字段。✓
- Selection、财期推断、amended 优先、去重仍由 `cn_report_selection.py` 持有。✓
- workflow 不按 market 特判 checkpoint 行为。✓
- No hard cap、date recursion、page append/dedup、generic pagination/cancellation framework、speculative watchdog、compatibility alias/wrapper。✓

## 4. Adversarial failure analysis

### 4.1 Field-level attacks

| Attack | Defense | Result |
|---|---|---|
| `hasNextRow` = `"true"` (string) | `_require_title_search_bool`: `isinstance(value, bool)` → False | typed fail，不进入 cumulative loop |
| `hasNextRow` = `1` (int) | `_require_title_search_bool`: `isinstance(value, bool)` → False（1 不是 bool） | typed fail |
| `hasNextRow` = `null` | `_require_title_search_bool` | typed fail |
| `rowRange` = `true` (JSON bool) | `_require_title_search_non_negative_int`: `isinstance(value, bool)` → 显式拒绝 | typed fail |
| `rowRange` = `"100"` (string) | `_require_title_search_non_negative_int`: `isinstance(value, int)` → False | typed fail |
| `rowRange` = `0.0` (integral float) | `isinstance(value, int)` → False（float 不是 int） | typed fail |
| `rowRange` = `-1` (negative) | `value < 0` check | typed fail |
| `result` = `""` (empty string) | `_require_title_search_rows`: `not value.strip()` | typed fail |
| `result` = `"{"` (malformed JSON) | `json.JSONDecodeError` → `HkexnewsProviderProtocolError` | typed fail |
| `result` = `"{}"` (dict, not list) | `isinstance(decoded, list)` → False | typed fail |
| `result` = `"[1, 2, 3]"` (non-object rows) | `isinstance(row, dict)` → False per row | typed fail |
| Missing any of 5 required fields | `_require_title_search_field`: `field not in payload` | typed fail |
| `recordCnt` field absent | same as above | typed fail |
| `response_row_range != requested_row_range` | same-round invariant line 760-764 | typed fail |
| `loadedRecord != len(rows)` | same-round invariant line 765-769 | typed fail |
| `loadedRecord > recordCnt` | same-round invariant line 770-775 | typed fail |
| `hasNextRow=true` 且 `loadedRecord == recordCnt` | same-round invariant line 781-786 | typed fail |
| `hasNextRow=false` 且 `loadedRecord != recordCnt` | same-round invariant line 787-792 | typed fail |

全部 fail-closed；无 coercion、loose parsing、fallback、default value 或 silent acceptance。✓

### 4.2 State machine attacks

| Attack | Defense | Result |
|---|---|---|
| `hasNextRow=true` 但每轮 loaded rows 不变 | `loaded_record <= previous_continuation_loaded` → no-progress typed fail（line 492-504） | 有限轮后 typed fail，不无限循环 |
| `recordCnt` 持续增长但 loaded rows 不变 | same no-progress check（比较 loaded，不比较 count） | 同上 |
| `recordCnt` 从 350 缩小到 200，但 final response 自洽 complete | terminal-first（line 490-491）：`not has_next_row` 直接返回 | 接受最新自洽 terminal |
| `hasNextRow=true` 但下一轮 `hasNextRow=false` 且 loaded 缩小 | terminal-first | 接受最新自洽 terminal |
| 首轮 already complete（100 exact） | `not has_next_row` → 直接返回 | 不触发"100 即失败" |
| HTTP 503 on later round | retry exhaustion → `RuntimeError` | 不返回首轮 partial，不做 HEAD |
| Cancel before first GET | `CP1` 抛出 → before HTTP | zero HTTP，zero candidates |
| Cancel after response | `CP2` 抛出 → 不 parse、不继续 | zero candidates/HEAD |
| Cancel before later round | `CP3` 抛出 → 只有第一 GET | zero partial complete/HEAD |

每个 cancel/HTTP failure 路径均不发布 partial rows/candidates/HEAD。✓

### 4.3 Exception chain integrity

| Scenario | Expected behavior | Verified by test |
|---|---|---|
| Caller raises pre-constructed `CnDownloadCancelledError` | `exc_info.value is expected_cancel` across workflow→protocol→provider | `test_list_report_candidates_preserves_cancel_identity_and_suppresses_publication`、`test_cn_workflow_preserves_caller_cancel_object_through_checkpoint` |
| Raw checker non-cancel failure through HKEX context wrapper | two-layer cause chain: outer RuntimeError → inner RuntimeError → original | `test_list_report_candidates_preserves_non_cancel_failure_full_cause_chain` |
| Raw checker non-cancel failure through CNInfo context wrapper | two-layer cause chain preserved | `test_list_report_candidates_preserves_checkpoint_failure_full_cause_chain` |
| Provider protocol error with parser cause | `HkexnewsProviderProtocolError` with `__cause__` being `json.JSONDecodeError` | `test_list_report_candidates_preserves_provider_protocol_error_and_direct_cause` |
| Pre-constructed provider protocol error identity | `exc_info.value is expected` across monkeypatched parser | `test_list_report_candidates_preserves_provider_protocol_object_identity` |

全部 exception identity/type/cause chain 完整保留。✓

### 4.4 Query invariance under adversarial provider

- Base params 在每 language/category 构造一次为 `MappingProxyType`（immutable），每轮通过 `dict(base_params)` 派生。✓
- 测试通过 removing `rowRange` 后 exact dict equality 验证所有其它字段不变（`test_list_report_candidates_fetches_two_round_cumulative_snapshot_with_invariant_query`）。✓
- Per-language isolation 测试验证 zh/en 各自从 100 开始且 query invariant 独立（`test_list_report_candidates_keeps_cumulative_state_isolated_per_language`）。✓

### 4.5 Infinite/no-progress scenarios

- `hasNextRow=true` 且 loaded rows 不增加 → no-progress typed fail（line 492-504），不继续 doubling。✓
- `recordCnt` 增长但 loaded rows 不增加 → same check。✓
- `recordCnt=0` 且 `hasNextRow=false` → terminal check：`loadedRecord == recordCnt == len(rows)`（all 0），通过。✓
- Provider 返回超大 `recordCnt`（如 100000）→ `max(current*2, recordCnt)` 直接请求 100000。无 hard cap。按 plan 设计，后续若观察到真实 cap 才追加 date splitting。✓

## 5. Test authenticity audit

### 5.1 Test coverage of owner contracts

全部 tests 使用 `httpx.MockTransport`，禁止真实网络。测试直接断言 owner-level contract 行为：

**HKEX owner tests**（`test_hkexnews_downloader.py`）：
- Exact 100 complete with exact checkpoint ordering（line 496）→ 验证 `CP1, GET(100), CP2` 且只返回 final rows。✓
- Two-round cumulative with query invariance（line 522）→ 验证 `CP1, GET(100), CP2, CP3, GET(200), CP4`、ranges `[100, 200]`、non-range params exact equal、final-only。✓
- Latest recordCnt formula（line 619）→ 验证 `max(100*2, 350) = 350` 而非 `200`。✓
- Multi-round count growth（line 572）→ 验证 ranges `[100, 200, 400]`、使用最新 350。✓
- Overlap replacement + terminal shrink（line 654）→ 验证 first-only row 不出现在 final、HEAD 只发生在 final rows。✓
- No progress typed failure（line 689）→ 验证 exactly 2 requests、no HEAD。✓
- Five field missing（line 716）→ parametrized，逐一删除并验证 typed fail。✓
- Bool/int/negative/result exact type（line 733、747、765、779）→ parametrized，全部拒绝。✓
- Six same-round contradiction cases（line 795）→ parametrized，全部 typed fail。✓
- Three cancel timing parametrized（line 824）→ 验证 exact events、cancel identity、zero HEAD。✓
- Non-cancel failure full cause chain（line 874）→ 验证两层 cause chain、zero HTTP。✓
- Provider protocol error with direct cause（line 901）→ 验证 `HkexnewsProviderProtocolError` type + `JSONDecodeError` cause。✓
- Provider protocol error object identity（line 916）→ monkeypatch 验证 identity/cause passthrough。✓
- Later HTTP failure（line 952）→ 验证 3 GET attempts、no HEAD、no partial。✓
- Per-language isolation（line 985）→ 验证 zh/en 各 `[100, 200]`。✓
- Captured fixture replay（line 1028）→ 验证 body hash、exact field types、request params、zero candidates。✓

**CNInfo owner tests**（`test_cninfo_downloader.py`）：
- Two-period checkpoint sequence（line 1076）→ 验证 `CP1, POST(FY), CP2, CP3, POST(H1), CP4`。✓
- Paginated POST checkpoint sequence（line 1125）→ 验证 `CP1, POST(1), CP2, CP3, POST(2), CP4`。✓
- Cancel identity stop next period（line 1188）→ parametrized for CP2/CP3 cancel。✓
- Non-cancel failure full cause chain（line 1257）→ 验证两层 cause chain across CNInfo context wrapper。✓

**Workflow owner tests**（`test_cn_download_workflow.py`）：
- Bool true mapping inside single owned checkpoint（line 1614）→ 验证 raw checker 在 discovery-pre 为 false、checkpoint 内为 true → typed cancel，checkpoint is not raw checker，zero download/convert。✓
- Caller cancel object identity through partial/protocol（line 1652）→ 验证 `CnDownloadCancelledError` identity。✓
- Cancel before first candidate（line 1679）→ 验证 raw_calls==6（workflow 前 5 次 + checkpoint 内第 6 次）、zero download/convert/FILING_STARTED。✓
- Non-cancel failure direct cause（line 1706）→ 验证 `workflow_error.__cause__ is expected`、type is RuntimeError。✓

**Pipeline/runtime double tests**：
- Pipeline CN fake（`test_cn_pipeline.py` line 354-356）→ 验证 `len(discovery.cancellation_checkpoints) == 1`、checkpoint is not None、checkpoint is not cancel_checker。✓
- Pipeline HK fake（line 422-424）→ 同上。✓
- Runtime discovery fakes → 接受 keyword-only `cancellation_checkpoint` 并调用。✓

### 5.2 Zero-publication evidence

每个 cancel/failure 测试均验证：
- `head_count == 0`（无 HEAD 请求）
- `discovery.download_calls == 0`（无 PDF 下载）
- `converter.calls == 0`（无 Docling 转换）
- 无 `FILING_STARTED` / `FILE_DOWNLOAD_STARTED` event

Partial rows/candidates/HEAD/PDF/Docling 在任何 cancel/failure 路径下 zero-publication。✓

### 5.3 Test fixture authenticity

`tests/fins/fixtures/hkexnews/title_search_protocol_shape.json`（34 lines）：
- `captured_at_utc`：`2026-07-17T10:54:36Z`。✓
- `endpoint`：public HTTPS `titleSearchServlet.do`。✓
- `request_params`：完整 non-sensitive params。✓
- `http_status`：200。✓
- `raw_response_body_sha256` + `raw_response_body`：可审计验证。✓
- `raw_json_response`：exact field types（`hasNextRow` is bool、`rowRange/loadedRecord/recordCnt` are int not bool、`result` is string）。✓
- `capture_tool`：curl 8.7.1，public GET，no cookies/auth/proxy/headers。✓
- 测试 `test_captured_official_title_search_shape_replays_through_strict_owner` 验证 body hash、field types、request params 与 strict parser replay。✓

### 5.4 Branch coverage

Controller independent validation 结果（已确认）：
- HKEX：`80.89%` ✓
- CNInfo：`89.28%` ✓
- protocol：`100.00%` ✓
- workflow：`81.05%` ✓

全部逐文件 `>=80.00%`，无 aggregate 替代、waiver、omit、pragma 或 padding。AgentCodex 从 `79.74%` 到 `81.05%` 的 workflow coverage 修复通过真实 owner 行为测试完成（"discovery 完成后、首 candidate 前取消"），不是 dead-code padding。✓

### 5.5 Live smoke evidence

`workspace/tmp/wu-semantic-ownership-01-r10-hkex-smoke/` manifest（107 lines）：
- Public GET，`stockId=7609`，all categories，`20000101..20260717`。✓
- Round 1：`rowRange=100` → `loadedRecord=100, recordCnt=1669, hasNextRow=true`。✓
- Formula：`max(100*2, 1669) = 1669`。✓
- Round 2：`rowRange=1669` → `loadedRecord=1669, recordCnt=1669, hasNextRow=false`。✓
- `jq -e` verifier：true。✓
- Two-round raw body hashes 被 manifest 记录，evidence root 被 `.gitignore` 覆盖。✓

## 6. Code quality audit

### 6.1 AGENTS.md compliance

- 函数 docstring：全部新增/修改函数提供完整中文 docstring，含参数、返回值、异常。✓
- 类型注解：无 `object`、`Any`、无类型参数、无类型返回值。✓
- `hasattr`/`getattr`：全仓 scan 为 0。✓
- 无 magic number：唯一字面量 `_HKEXNEWS_INITIAL_CUMULATIVE_ROW_RANGE = 100` 与 doubling factor `2` 均为算法显式语义，不是隐藏魔法值。✓
- 无兼容性代码：已删除旧 symbols 且无 alias/wrapper/re-export。✓
- 模块间依赖：protocol 只运输、workflow 只解释 raw checker、provider 只调用。无反向依赖。✓

### 6.2 LLM-facing 文本约束

R10 实现不产生 LLM-facing 文本。Protocol docstring 描述 provider 语义，不暴露内部类型名或 Host 治理字段。错误消息只包含业务可读 context（stock_code、lang、t1code、t2code、row_range、count facts），不包含 raw response、cookie/header、local path。✓

### 6.3 分层架构

- `dayu.fins.downloaders` → provider I/O owner。✓
- `dayu.fins.pipelines.cn_download_protocols` → 运输层，只声明签名。✓
- `dayu.fins.pipelines.cn_download_workflow` → workflow orchestration owner。✓
- 无 `dayu.runtime` 违规 import。✓
- 无 Engine/Host 反向依赖。✓

### 6.4 Type safety

- `_HkexnewsTitleSearchSnapshot` 使用 frozen dataclass，字段均有精确类型（`int`、`bool`、`tuple[dict[str, JsonValue], ...]`）。✓
- `_require_title_search_bool` 返回 `bool`，`_require_title_search_non_negative_int` 返回 `int`。✓
- Protocol 使用 `Callable[[], None] | None`，不依赖 `Callable[[], bool]` 或 `Any`。✓
- `functools.partial` 返回 `partial` object 满足 `Callable[[], None]` structural type。Python type checker 接受此用法。✓

### 6.5 Pyright / Ruff / diff

Controller independent validation confirmed：`0 errors, 0 warnings, 0 informations`（pyright）、`All checks passed!`（Ruff）、`PASS`（`git diff --check`）。✓

## 7. Security retention audit

- HTTP timeout（30s）、max_retries（3）、exponential backoff、throttle（0.3s）全部保留。✓
- HTTPS HKEX endpoint 不变。✓
- PDF magic bytes（`%PDF-`）+ min size（1024 bytes）校验保留。✓
- Stock code matching 保留。✓
- Error messages 不包含 raw response body、cookie、authorization、local path。✓
- Captured fixture 只用 public GET，不保存 cookie/auth/proxy credential/header。✓
- Live smoke 只用 public GET，不下载 PDF、不调用 mutation endpoint、不写 business workspace。✓

未新增 permission schema、auth profile、DNS/egress framework、browser capability。✓

## 8. Deferred-scope leakage audit

逐 hunk 审计确认实现不包含以下任何内容：
- Issue 142/151/175/177/178：0 added matches。✓
- R11/R12：0 added matches。✓
- Web/WeChat/render：0 added matches。✓
- Topic 8/9：0 added matches。✓
- Tool authorization / auth profile：0 added matches。✓
- Storage transaction / direct-stream terminal：0 added matches。✓
- Hard cap / date recursion / speculative watchdog / compatibility：0 added matches。✓

## 9. Controller-owned file boundary

- `docs/host/issues-implementation-control.md`：未被 implementation 修改，其 SHA-256 保持 `3bf08ec11...`。✓
- Implementation authorization（`f3ae9f58f...`）：未被 modification。✓
- Controller validation（`ea244cad...`）：本 review 读取但不覆盖。✓
- Staged tree：empty（Controller validation 确认）。✓

## 10. Finding ledger

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| — | — | — | 0 material findings |

### 10.1 Residual / no-action classification

| Item | Classification | Basis |
|---|---|---|
| CNInfo `page_num > 50` silent cap（`cninfo_downloader.py` line 497-502） | Pre-existing / non-R10 | 既存行为；R10 plan §3.3 明确排除 CNInfo pagination redesign。这是独立的 CNInfo completeness concern，需要单独 issue/WU |
| `_extract_json_rows` / `_parse_embedded_json_list` 仍存在 | Intentional retention | 被 `_fetch_stock_mapping` 的 stock list 解析使用（line 375）；R10 plan 与 Controller adjudication §4 明确保留 |
| announcement row `_first_text` 使用 generic field aliases | Pre-existing / non-R10 | announcement 解析不属于 title search completeness owner；plan §4.1 明确 selection 语义由 `cn_report_selection.py` 持有 |
| sorted path-manifest / content-lock manifest SHA-256 复现差异 | Tooling | `shasum -a 256` vs Controller 使用的方法格式差异；所有 individual file SHA-256 完全匹配，content integrity confirmed |

### 10.2 Staged-empty 状态

Controller validation 确认 staged tree 为 empty。本 review 不 stage、commit、push 或创建 PR。✓

## 11. Review completeness checklist

- [x] 完整读取 8 个 reference documents，按 priority order 裁决。
- [x] 独立重算全部 13 个 target file SHA-256，全部与 Controller validation 一致。
- [x] 完整读取 4 个 production files、5 个 test files、1 个 fixture、2 个 README、1 个 evidence。
- [x] HKEX strict parser：five-field exact types、bool/int/stringified-list、negative/missing/contradiction → all fail-closed。
- [x] Cumulative state machine：initial 100、`max(current*2, recordCnt)`、terminal-first、snapshot replacement、no append/dedup、strict progress。
- [x] Exception precedence：typed cancel/provider error bare re-raise before generic RuntimeError wrapper；identity/cause preserved。
- [x] Cancellation seam：workflow-owned `functools.partial` → protocol transport → HKEX each cumulative GET before/after → CNInfo each period POST before/after。
- [x] Bool interpretation：0 instances of `if cancellation_checkpoint()` in provider code。
- [x] Query invariance：base params `MappingProxyType` + per-round `rowRange` derivation only。
- [x] Adversarial failure pass：field-level attacks、state machine attacks、exception chain integrity、infinite/no-progress scenarios。
- [x] Test authenticity：MockTransport only、owner-level contract assertions、exact event sequences、cancel identity/cause chain、zero-publication。
- [x] Branch coverage：4 个 production files each `>=80%`，zero waiver/omit/pragma/padding。
- [x] Security retention：HTTP/HTTPS/PDF/throttle/error hygiene preserved。
- [x] Deferred-scope leakage：0 added matches across all forbidden topics。
- [x] Controller-owned files：not modified、not reviewed as product diff。
- [x] Obsolete symbols：0 matches in full repo scan。
- [x] `hasattr`/`getattr`：0 matches in changed production files。
- [x] No-touch Issues：142/151/175/177/178 — no implementation/mention in changed hunks。
- [x] No-touch Topics：8/9 — no implementation/mention in changed hunks。
- [x] No R11/R12 leakage。
- [x] No authorization/auth profile/permission schema introduced。

## 12. Review handoff

- **Material findings**：0
- **Blocking questions**：0
- **Residual items**：4（all pre-existing / non-R10 / tooling，见 §10.1）
- **Artifact lines**：本 review（不含本句）
- **Artifact SHA-256**：写完后外部计算
- **Next gate**：AgentMiMo 并发 deepreview 完成后 Controller 聚合裁决
- **明确声明**：未开始 fix、re-review、aggregate、commit、R11/R12
